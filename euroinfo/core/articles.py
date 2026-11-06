"""Article identity, display helpers and the small JSON stores (saved stories, snapshot)."""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
from pathlib import Path

from .. import logs, paths

log = logs.get("articles")

MAX_TOTAL_ARTICLES = 720
SNAPSHOT_FIELDS = (
    "title", "summary", "link", "source", "source_region",
    "source_language", "time", "timestamp", "image_url",
)
# Display-only fields that must never be persisted as if they came from a feed.
TRANSIENT_FIELDS = ("localized_title", "localized_summary", "reader_text")


def article_key(article: dict) -> str:
    """Stable 24-character id; the research library is keyed by this value."""
    raw = article.get("link") or f"{article.get('source', '')}|{article.get('title', '')}"
    return hashlib.sha256(str(raw).encode("utf-8", "ignore")).hexdigest()[:24]


def storable(article: dict, *, keep_localized: bool = False) -> dict:
    """Copy of an article without transient display or analysis fields."""
    dropped = TRANSIENT_FIELDS if not keep_localized else ("reader_text",)
    return {key: value for key, value in article.items()
            if key not in dropped and not key.startswith("_")}


_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def plain_text(value) -> str:
    return _SPACE.sub(" ", _TAG.sub(" ", html.unescape(str(value or "")))).strip()


def reading_excerpt(value, limit: int) -> str:
    text = plain_text(value)
    if len(text) <= limit:
        return text
    clipped = text[:limit].rsplit(" ", 1)[0]
    return clipped.rstrip(" ,;:—-") + "…"


def normalized_headline(article: dict) -> str:
    return re.sub(r"\W+", " ", str(article.get("title", "")).casefold()).strip()


# ------------------------------------------------------------------ JSON stores

def saved_stories_file() -> Path:
    return paths.data_dir() / "saved-stories.json"


def snapshot_file() -> Path:
    return paths.cache_dir() / "reader-snapshot.json"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def load_saved_stories() -> dict[str, dict]:
    """The reading list, keyed by article_key. A damaged file never blocks startup."""
    try:
        payload = json.loads(saved_stories_file().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, TypeError) as exc:
        log.warning("Could not read saved stories: %s", exc)
        return {}
    if not isinstance(payload, list):
        return {}
    return {article_key(item): storable(item) for item in payload
            if isinstance(item, dict) and item.get("title")}


def store_saved_stories(stories: dict[str, dict]) -> None:
    _atomic_write(saved_stories_file(), json.dumps(
        [storable(item) for item in stories.values()], ensure_ascii=False, indent=2))


def load_snapshot() -> dict:
    """Last known dashboard data, so the window fills instantly while feeds refresh."""
    try:
        payload = json.loads(snapshot_file().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, TypeError) as exc:
        log.warning("Could not read the news snapshot: %s", exc)
        return {}
    if not isinstance(payload, dict) or payload.get("schema") != 1 or not isinstance(payload.get("news"), list):
        return {}
    news = [item for item in payload["news"]
            if isinstance(item, dict) and item.get("title") and item.get("link")]
    weather = payload.get("weather")
    rates = payload.get("exchange_rates")
    return {
        "news": news[:MAX_TOTAL_ARTICLES],
        "weather": weather if isinstance(weather, dict) else {},
        "exchange_rates": rates if isinstance(rates, dict) else {},
        "saved_at": payload.get("saved_at", 0),
    }


def save_snapshot(news: list[dict], weather: dict, exchange_rates: dict) -> None:
    payload = {
        "schema": 1,
        "saved_at": time.time(),
        "news": [{key: item.get(key) for key in SNAPSHOT_FIELDS if item.get(key) is not None}
                 for item in news[:MAX_TOTAL_ARTICLES]],
        "weather": weather,
        "exchange_rates": exchange_rates,
    }
    try:
        _atomic_write(snapshot_file(), json.dumps(payload, ensure_ascii=False))
    except OSError as exc:
        log.warning("Could not store the news snapshot: %s", exc)


# ------------------------------------------------------------------ "new since your last visit"

def seen_file() -> Path:
    return paths.cache_dir() / "seen.json"


def load_seen() -> set[str]:
    try:
        payload = json.loads(seen_file().read_text(encoding="utf-8"))
        return set(payload) if isinstance(payload, list) else set()
    except FileNotFoundError:
        return set()
    except (OSError, ValueError, TypeError) as exc:
        log.warning("Could not read seen stories: %s", exc)
        return set()


def save_seen(keys: set[str], limit: int = 6000) -> None:
    try:
        _atomic_write(seen_file(), json.dumps(sorted(keys)[:limit]))
    except OSError as exc:
        log.warning("Could not store seen stories: %s", exc)
