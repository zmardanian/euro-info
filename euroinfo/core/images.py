"""Article thumbnails: RSS image first, publisher og:image second, all disk cached."""
from __future__ import annotations

import hashlib
import html
import re
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from .. import logs, paths
from .feeds import session

log = logs.get("images")

IMAGE_TIMEOUT = (3.0, 7.0)
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_ARTICLE_HTML_BYTES = 2 * 1024 * 1024
FAILURE_RETRY_SECONDS = 15 * 60
MAX_CACHE_BYTES = 256 * 1024 * 1024
MAX_CACHE_AGE_SECONDS = 7 * 24 * 3600
_SIGNATURES = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"RIFF")
_META_PATTERNS = [re.compile(pattern, re.I) for pattern in (
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
)]

_prune_lock = threading.Lock()
_pruned = False
_written_since_prune = 0


def cache_dir() -> Path:
    return paths.ensure(paths.cache_dir() / "images")


def failed_dir() -> Path:
    return paths.ensure(paths.cache_dir() / "failed")


def cache_key(article: dict[str, Any]) -> str:
    source = article.get("image_url") or article.get("link") or article.get("title") or ""
    return hashlib.sha256(str(source).encode("utf-8", errors="ignore")).hexdigest()


def cache_path(article: dict[str, Any]) -> Path:
    return cache_dir() / f"{cache_key(article)}.img"


def failure_path(article: dict[str, Any]) -> Path:
    return failed_dir() / f"{cache_key(article)}.failed"


def mark_failed(article: dict[str, Any], *, invalidate_cache: bool = False) -> None:
    try:
        if invalidate_cache:
            cache_path(article).unlink(missing_ok=True)
        failure_path(article).touch()
    except OSError as exc:
        log.debug("Could not mark image failure: %s", exc)


def prune_cache(*, force: bool = False) -> None:
    """Remove expired thumbnails and cap the cache size (once per process, or forced)."""
    global _pruned
    if _pruned and not force:
        return
    with _prune_lock:
        if _pruned and not force:
            return
        now, live, total = time.time(), [], 0
        for path in cache_dir().glob("*.img"):
            try:
                stat = path.stat()
                if now - stat.st_mtime > MAX_CACHE_AGE_SECONDS:
                    path.unlink(missing_ok=True)
                    continue
                live.append((stat.st_mtime, stat.st_size, path))
                total += stat.st_size
            except OSError:
                continue
        for _mtime, size, path in sorted(live):
            if total <= MAX_CACHE_BYTES:
                break
            path.unlink(missing_ok=True)
            total -= size
        for path in failed_dir().glob("*.failed"):
            try:
                if now - path.stat().st_mtime > FAILURE_RETRY_SECONDS:
                    path.unlink(missing_ok=True)
            except OSError:
                continue
        _pruned = True


def read_cache(article: dict[str, Any]) -> bytes | None:
    path = cache_path(article)
    try:
        if time.time() - path.stat().st_mtime > MAX_CACHE_AGE_SECONDS:
            path.unlink(missing_ok=True)
            return None
        return path.read_bytes() or None
    except OSError:
        return None


def write_cache(article: dict[str, Any], data: bytes) -> None:
    global _written_since_prune
    if not data or len(data) > MAX_IMAGE_BYTES:
        return
    path = cache_path(article)
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
        failure_path(article).unlink(missing_ok=True)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        log.debug("Could not cache image: %s", exc)
        return
    with _prune_lock:
        _written_since_prune += len(data)
        should_prune = _written_since_prune >= 16 * 1024 * 1024
        if should_prune:
            _written_since_prune = 0
    if should_prune:
        prune_cache(force=True)


def is_image(data: bytes) -> bool:
    return bool(data) and len(data) <= MAX_IMAGE_BYTES and data.startswith(_SIGNATURES)


def _download(url: str) -> bytes | None:
    if urlparse(url or "").scheme not in {"http", "https"}:
        return None
    try:
        with session().get(url, timeout=IMAGE_TIMEOUT, allow_redirects=True, stream=True) as response:
            response.raise_for_status()
            if "text/html" in response.headers.get("Content-Type", "").lower():
                return None
            chunks, total = [], 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                total += len(chunk)
                if total > MAX_IMAGE_BYTES:
                    return None
                chunks.append(chunk)
        data = b"".join(chunks)
        return data if is_image(data) else None
    except (requests.RequestException, OSError) as exc:
        log.debug("Image download failed for %s: %s", url, exc)
        return None


def _publisher_image(article_url: str) -> str:
    if urlparse(article_url or "").scheme not in {"http", "https"}:
        return ""
    try:
        with session().get(article_url, timeout=IMAGE_TIMEOUT, allow_redirects=True, stream=True) as response:
            response.raise_for_status()
            if "html" not in response.headers.get("Content-Type", "").lower():
                return ""
            chunks, size = [], 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                chunks.append(chunk[:MAX_ARTICLE_HTML_BYTES - size])
                size += len(chunks[-1])
                if size >= MAX_ARTICLE_HTML_BYTES:
                    break
            text = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
            final_url = response.url or article_url
    except (requests.RequestException, OSError) as exc:
        log.debug("Publisher page unavailable for image lookup: %s", exc)
        return ""
    for pattern in _META_PATTERNS:
        match = pattern.search(text)
        if match:
            return urljoin(final_url, html.unescape(match.group(1)).strip())
    return ""


def load_article_image(article: dict[str, Any]) -> bytes | None:
    """Cached bytes, the feed's image, or the publisher's og:image; None on failure."""
    prune_cache()
    cached = read_cache(article)
    if cached:
        return cached
    try:
        if time.time() - failure_path(article).stat().st_mtime < FAILURE_RETRY_SECONDS:
            return None
    except OSError:
        pass
    for url in (article.get("image_url") or "", None):
        if url is None:
            url = _publisher_image(article.get("link") or "")
        data = _download(url) if url else None
        if data:
            write_cache(article, data)
            return data
    mark_failed(article)
    return None
