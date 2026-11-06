"""News feeds, weather and ECB rates.

feedparser parses; requests performs all network I/O and owns every timeout.
Nothing here imports Qt, so the Plasma widget and tests can use it directly.
"""
from __future__ import annotations

import calendar
import json
import math
import re
import threading
import time
import unicodedata
from email.utils import parsedate_to_datetime
from datetime import timezone
# Imported from the submodule on purpose: Python 3.15 makes the package attribute
# a lazy import, which the packaged (PyInstaller) app cannot resolve.
from concurrent.futures.thread import ThreadPoolExecutor
from functools import lru_cache
from typing import Any
from urllib.parse import urljoin

import feedparser
import requests

from .. import REPOSITORY_URL, __version__, logs, paths
from .articles import MAX_TOTAL_ARTICLES, article_key, plain_text
from .quality import annotate_article, canonical_link, publisher_family
from .sources import CITIES, COUNTRY_TERMS, NEWS_SOURCES, SOURCE_BY_NAME, SOURCE_COUNTRIES  # noqa: F401

log = logs.get("feeds")

USER_AGENT = f"EuroInfo/{__version__} (Linux; RSS reader; +{REPOSITORY_URL})"
FEED_TIMEOUT = (3.0, 8.0)
MAX_ARTICLES_PER_FEED = 18
MAX_ARTICLES_PER_SOURCE = 9
FEED_WORKERS = 16
CACHED_FEED_MAX_AGE = 24 * 3600


WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
EXCHANGE_RATES_URL = "https://api.frankfurter.dev/v2/providers/ecb/rates"
EXCHANGE_RATE_CURRENCIES = ("USD", "GBP", "RON", "CHF", "PLN")

WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}


# ------------------------------------------------------------------ HTTP

_thread_local = threading.local()


def session() -> requests.Session:
    """One requests.Session per worker thread: connection reuse without sharing."""
    current = getattr(_thread_local, "session", None)
    if current is None:
        current = requests.Session()
        current.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,*/*;q=0.8",
        })
        _thread_local.session = current
    return current


# ------------------------------------------------------------------ weather and rates

def _weather_entry(current: dict) -> dict[str, Any]:
    return {
        "temperature": float(current.get("temperature_2m", 0.0)),
        "feels_like": float(current.get("apparent_temperature", 0.0)),
        "humidity": float(current.get("relative_humidity_2m", 0.0)),
        "wind": float(current.get("wind_speed_10m", 0.0)),
        "gusts": float(current.get("wind_gusts_10m", 0.0)),
        "description": WEATHER_CODES.get(current.get("weather_code"), "Unknown"),
    }


def get_weather() -> dict[str, dict[str, Any]]:
    """Current conditions for every city in one Open-Meteo request."""
    names = list(CITIES)
    params = {
        "latitude": ",".join(str(CITIES[name][0]) for name in names),
        "longitude": ",".join(str(CITIES[name][1]) for name in names),
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                   "weather_code,wind_speed_10m,wind_gusts_10m",
        "timezone": "auto",
    }
    try:
        response = session().get(WEATHER_URL, params=params, timeout=FEED_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        rows = payload if isinstance(payload, list) else [payload]
        if len(rows) != len(names):
            raise ValueError(f"expected {len(names)} locations, received {len(rows)}")
        return {name: _weather_entry(row.get("current", {})) for name, row in zip(names, rows, strict=True)}
    except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
        log.warning("Weather unavailable: %s", exc)
        return {name: {"error": str(exc)} for name in names}


def get_exchange_rates() -> dict[str, Any]:
    """Latest daily ECB reference rates against the euro."""
    try:
        response = session().get(
            EXCHANGE_RATES_URL,
            params={"base": "EUR", "quotes": ",".join(EXCHANGE_RATE_CURRENCIES)},
            timeout=FEED_TIMEOUT)
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            raise ValueError("Unexpected exchange-rate response")
        rates, dates = {}, set()
        for row in rows:
            if not isinstance(row, dict) or row.get("quote") not in EXCHANGE_RATE_CURRENCIES:
                continue
            try:
                rate = float(row["rate"])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(rate) and rate > 0:
                rates[row["quote"]] = rate
                if row.get("date"):
                    dates.add(str(row["date"]))
        return {"base": "EUR", "date": max(dates) if dates else "", "rates": rates}
    except (requests.RequestException, ValueError, TypeError) as exc:
        log.warning("Exchange rates unavailable: %s", exc)
        return {"error": str(exc), "base": "EUR", "date": "", "rates": {}}


# ------------------------------------------------------------------ feed entries

def _absolute_url(value: str, base: str) -> str:
    value = (value or "").strip()
    return urljoin(base, value) if value else ""


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+([,.;:!?])", r"\1", plain_text(value))


def _entry_time(entry) -> str:
    for value in (entry.get("published"), entry.get("updated"), entry.get("created")):
        if not value:
            continue
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone().strftime("%a, %d %b %Y %H:%M:%S %z")
    return ""


def _entry_timestamp(entry) -> float:
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(field)
        if value:
            try:
                return float(calendar.timegm(value))
            except (TypeError, ValueError, OverflowError):
                continue
    return 0.0


_IMG_TAG = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)


def _extract_rss_image(entry, feed_url: str) -> str:
    for item in entry.get("media_content", []) or []:
        if isinstance(item, dict) and (item.get("url") or item.get("href")):
            return _absolute_url(item.get("url") or item.get("href"), feed_url)
    for item in entry.get("media_thumbnail", []) or []:
        if isinstance(item, dict) and item.get("url"):
            return _absolute_url(item["url"], feed_url)
    for enclosure in entry.get("enclosures", []) or []:
        if isinstance(enclosure, dict):
            url = enclosure.get("href") or enclosure.get("url")
            mime = (enclosure.get("type") or "").lower()
            if url and (not mime or mime.startswith("image/")):
                return _absolute_url(url, feed_url)
    for link in entry.get("links", []) or []:
        if isinstance(link, dict) and link.get("rel") == "enclosure" and link.get("href"):
            mime = (link.get("type") or "").lower()
            if not mime or mime.startswith("image/"):
                return _absolute_url(link["href"], feed_url)
    fragments = [str(entry.get("description") or "")]
    fragments += [str(item.get("value") or "") for item in entry.get("content", []) or [] if isinstance(item, dict)]
    match = _IMG_TAG.search(" ".join(fragments))
    return _absolute_url(match.group(1), feed_url) if match else ""


def _normalize_entry(entry, source: dict, feed_url: str) -> dict[str, Any] | None:
    title = _clean_text(entry.get("title", ""))
    link = (entry.get("link", "") or "").strip()
    if not title or not link:
        return None
    article = {
        "title": title,
        "summary": _clean_text(entry.get("summary", "") or entry.get("description", ""))[:900],
        "link": _absolute_url(link, feed_url),
        "source": source["name"],
        "source_region": source.get("region", "WORLD"),
        "source_language": source.get("language", "en"),
        "time": _entry_time(entry),
        "timestamp": _entry_timestamp(entry),
        "image_url": _extract_rss_image(entry, feed_url),
    }
    updated = _entry_timestamp({"updated_parsed": entry.get("updated_parsed")})
    return annotate_article(article, source, entry.get("author", ""), updated)


# ------------------------------------------------------------------ feed fetching

_FEED_HEALTH: dict[str, dict] = {}
_FEED_VALIDATORS: dict[str, dict] = {}
_FEED_LOCK = threading.Lock()


_POOL: ThreadPoolExecutor | None = None
_CACHE_LOADED = False
FEED_CACHE_VERSION = 1


def _pool() -> ThreadPoolExecutor:
    """Long-lived download workers: their HTTP connections stay open between refreshes."""
    global _POOL
    if _POOL is None:
        _POOL = ThreadPoolExecutor(max_workers=FEED_WORKERS, thread_name_prefix="rss")
    return _POOL


def feed_cache_file():
    return paths.cache_dir() / "feeds.json"


def load_feed_cache() -> None:
    """Restore ETag/Last-Modified validators and last good entries from the previous session."""
    global _CACHE_LOADED
    if _CACHE_LOADED:
        return
    _CACHE_LOADED = True
    try:
        payload = json.loads(feed_cache_file().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return
    except (OSError, ValueError) as exc:
        log.warning("Feed cache unreadable: %s", exc)
        return
    if not isinstance(payload, dict) or payload.get("version") != FEED_CACHE_VERSION:
        return
    cutoff = time.time() - CACHED_FEED_MAX_AGE
    with _FEED_LOCK:
        for url, entry in (payload.get("feeds") or {}).items():
            if isinstance(entry, dict) and entry.get("fetched", 0) > cutoff and isinstance(entry.get("articles"), list):
                _FEED_VALIDATORS.setdefault(url, entry)


def save_feed_cache() -> None:
    with _FEED_LOCK:
        payload = {"version": FEED_CACHE_VERSION, "feeds": dict(_FEED_VALIDATORS)}
    path = feed_cache_file()
    try:
        paths.ensure(path.parent)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    except (OSError, TypeError, ValueError) as exc:
        log.warning("Could not store the feed cache: %s", exc)


def feed_health_snapshot() -> dict[str, dict]:
    with _FEED_LOCK:
        return {name: dict(item) for name, item in _FEED_HEALTH.items()}


def _record_feed_health(name, began, articles, error="", cached=False):
    with _FEED_LOCK:
        _FEED_HEALTH[name] = {"checked": time.time(), "seconds": round(time.monotonic() - began, 3),
                              "articles": articles, "error": str(error)[:400], "cached": cached}


def _fetch_feed(source: dict) -> list[dict[str, Any]]:
    began = time.monotonic()
    name, url = source["name"], source["url"]
    with _FEED_LOCK:
        previous = _FEED_VALIDATORS.get(url)
    try:
        headers = {}
        if previous and previous["etag"]:
            headers["If-None-Match"] = previous["etag"]
        if previous and previous["modified"]:
            headers["If-Modified-Since"] = previous["modified"]
        response = session().get(url, timeout=FEED_TIMEOUT, allow_redirects=True, headers=headers)
        if response.status_code == 304:
            if not previous:
                raise RuntimeError("Publisher returned 304 without a previous feed.")
            articles = [dict(article) for article in previous["articles"]]
            _record_feed_health(name, began, len(articles), cached=True)
            return articles
        response.raise_for_status()
        if not response.content:
            raise RuntimeError("empty RSS response")
        feed = feedparser.parse(response.content)
        # A "bozo" feed is malformed XML but can still contain usable entries.
        if getattr(feed, "bozo", False) and not feed.entries:
            raise RuntimeError(str(getattr(feed, "bozo_exception", "") or "invalid RSS feed"))
        articles = [article for entry in feed.entries[:MAX_ARTICLES_PER_FEED]
                    if (article := _normalize_entry(entry, source, response.url or url))]
        with _FEED_LOCK:
            _FEED_VALIDATORS[url] = {
                "etag": response.headers.get("ETag", ""),
                "modified": response.headers.get("Last-Modified", ""),
                "fetched": time.time(),
                "articles": [dict(article) for article in articles],
            }
        _record_feed_health(name, began, len(articles))
        return articles
    except Exception as exc:  # one broken feed must never break the refresh
        fallback = []
        if previous and time.time() - previous["fetched"] < CACHED_FEED_MAX_AGE:
            fallback = [dict(item) for item in previous["articles"]]
        _record_feed_health(name, began, len(fallback), exc, cached=bool(fallback))
        log.warning("Feed %s failed: %s", name, exc)
        return fallback


def remove_duplicates(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen, result = set(), []
    for article in articles:
        key = (canonical_link(article.get("link")) or article.get("title") or "").strip()
        if key and key not in seen:
            seen.add(key)
            result.append(article)
    return result


def get_news(sources: list[dict] | None = None) -> list[dict[str, Any]]:
    """Fetch every feed concurrently, newest first, with fair per-source balance."""
    sources = NEWS_SOURCES if sources is None else sources
    load_feed_cache()
    articles: list[dict] = []
    for result in _pool().map(_fetch_feed, sources):
        articles.extend(result)
    save_feed_cache()
    articles.sort(key=lambda item: item.get("timestamp", 0), reverse=True)
    # Give every responding feed a turn before high-volume desks fill the cap.
    buckets: dict[str, list] = {}
    for article in remove_duplicates(articles):
        bucket = buckets.setdefault(article.get("source", ""), [])
        if len(bucket) < MAX_ARTICLES_PER_SOURCE:
            bucket.append(article)
    balanced = []
    for slot in range(MAX_ARTICLES_PER_SOURCE):
        for bucket in buckets.values():
            if slot < len(bucket) and len(balanced) < MAX_TOTAL_ARTICLES:
                balanced.append(bucket[slot])
    balanced.sort(key=lambda item: item.get("timestamp", 0), reverse=True)
    return balanced


# ------------------------------------------------------------------ ranking and grouping

def prioritize_articles(articles: list[dict[str, Any]], country: str) -> list[dict[str, Any]]:
    """Stable relevance ordering; keeps every article and feed order within ranks."""
    country = (country or "").upper()
    terms = COUNTRY_TERMS.get(country)
    if not terms:
        return list(articles)

    def rank(article: dict[str, Any]) -> int:
        text = " ".join(str(article.get(key, "")) for key in
                        ("title", "localized_title", "summary", "localized_summary", "description")).casefold()
        return int(any(term in text for term in terms)) * 2 + int(SOURCE_COUNTRIES.get(article.get("source", "")) == country)

    return [article for _, article in sorted(enumerate(articles), key=lambda pair: (-rank(pair[1]), pair[0]))]


_STORY_STOP_WORDS = frozenset(
    """a an and are as at be by for from in into is it of on or that the to was were with after amid over says say
    new how what who why their his her its this these those update updates live latest breaking according report
    reports news europe european eu europe's across will could would has have had about against between during
    following one two si pentru din intre dupa cu la de der die das den des und von zu im am ist mit auf bei an um
    ein eine el los las del degli delle il che per con en un una y por para como que da do dos das nach wa dla jest
    oraz po z na i o w ze przez pod nad jako aby jak go jego jej oni ich od przy taki tej ten""".split())

_STORY_TERM_ALIASES = {
    "ukraine": "ukraine", "ucraina": "ukraine", "ukrainy": "ukraine",
    "germany": "germany", "german": "germany", "germans": "germany", "germania": "germany",
    "aid": "aid", "aids": "aid", "support": "aid", "sprijin": "aid", "sprijinul": "aid",
    "ajutor": "aid", "ajutorul": "aid", "asistenta": "aid", "assistance": "aid",
    "military": "military", "militar": "military", "militare": "military", "militara": "military",
    "alliance": "alliance", "alliances": "alliance", "alianta": "alliance",
    "halt": "halt", "halting": "halt", "end": "halt", "ending": "halt", "stop": "halt",
    "incetarea": "halt", "oprire": "halt", "oprirea": "halt", "oppose": "oppose", "opposition": "oppose",
    "russia": "russia", "russian": "russia", "rusiei": "russia", "rusia": "russia",
    "france": "france", "francei": "france", "franciei": "france",
    "poland": "poland", "polonia": "poland", "polski": "poland",
    "election": "election", "elections": "election", "alegeri": "election", "wahl": "election", "wahlkampf": "election",
}
_ACTORS = frozenset({"sefcovic", "kushner", "trump", "macron", "merz", "putin", "zelenskiy"})
_WORD = re.compile(r"[\w’'-]{3,}")


@lru_cache(maxsize=8192)
def _terms_of(text: str) -> frozenset[str]:
    terms = set()
    for word in _WORD.findall(text.casefold()):
        word = "".join(char for char in unicodedata.normalize("NFKD", word.strip("’'-"))
                       if not unicodedata.combining(char))
        if len(word) >= 3 and word not in _STORY_STOP_WORDS:
            terms.add(_STORY_TERM_ALIASES.get(word, word))
    return frozenset(terms)


def _story_terms(article: dict[str, Any]) -> frozenset[str]:
    return _terms_of(str(article.get("title", "")))


def _within_three_days(left: dict, right: dict) -> bool:
    a, b = left.get("timestamp"), right.get("timestamp")
    return not (a and b and abs(a - b) > 72 * 3600)


def related_articles(target: dict[str, Any], articles: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    """Likely coverage of the same event from already-loaded feeds, selected story first."""
    target_terms = _story_terms(target)
    target_extended = target_terms | _terms_of(str(target.get("summary") or target.get("reader_text") or "")[:1200])
    target_key = article_key(target)
    ranked: list[tuple[float, float, dict[str, Any]]] = []
    for item in articles:
        if not isinstance(item, dict) or article_key(item) == target_key or not _within_three_days(target, item):
            continue
        item_terms = _story_terms(item)
        item_extended = item_terms | _terms_of(str(item.get("summary") or "")[:1200])
        if len(target_extended) < 2 or len(item_extended) < 2:
            continue
        headline_overlap = len(target_terms & item_terms)
        shared_terms = target_extended & item_extended
        shared = len(shared_terms)
        actor_overlap = shared_terms & _ACTORS
        if shared < 2 or (headline_overlap == 0 and shared < 4 and not actor_overlap):
            continue
        jaccard = shared / len(target_extended | item_extended)
        containment = shared / min(len(target_extended), len(item_extended))
        # Distinctive named actors plus a shared issue can link headlines that use
        # different wording; generic excerpt overlap stays strict.
        if jaccard < 0.20 and containment < 0.50 and (shared < 3 or jaccard < 0.10) and not actor_overlap:
            continue
        ranked.append((containment * 0.65 + jaccard * 0.35, jaccard, item))
    ranked.sort(key=lambda row: (row[0], row[2].get("timestamp", 0)), reverse=True)

    selected, seen_keys = [target], {target_key}
    seen_sources = {publisher_family(target).casefold()}
    max_items = max(1, min(int(limit), 12))
    # First pass: one top match per publisher so no outlet crowds out the rest.
    for diverse_only in (True, False):
        for _score, _jaccard, item in ranked:
            key = article_key(item)
            family = publisher_family(item).casefold()
            if key in seen_keys or (diverse_only and family in seen_sources):
                continue
            selected.append(item)
            seen_keys.add(key)
            seen_sources.add(family)
            if len(selected) >= max_items:
                return selected
    return selected


def cluster_stories(articles: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group headlines that likely cover the same event.

    A conservative, explainable title-overlap rule: a group is a reading aid, not a
    claim that the reports are identical or mutually corroborating.
    """
    if len(articles) < 2:
        return [[article] for article in articles]
    terms = [_story_terms(article) for article in articles]
    parents = list(range(len(articles)))
    postings: dict[str, list[int]] = {}

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for index, words in enumerate(terms):
        if len(words) >= 3:
            overlaps: dict[int, int] = {}
            for word in words:
                for previous in postings.get(word, ()):
                    overlaps[previous] = overlaps.get(previous, 0) + 1
            for previous, shared in overlaps.items():
                other = terms[previous]
                if shared < 3 or min(len(words), len(other)) < 3 or not _within_three_days(articles[index], articles[previous]):
                    continue
                if shared / len(words | other) >= 0.30 and shared / min(len(words), len(other)) >= 0.55:
                    anchor = find(previous)
                    anchor_shared = len(words & terms[anchor])
                    if (anchor_shared >= 3 and anchor_shared / max(1, len(words | terms[anchor])) >= 0.30
                            and _within_three_days(articles[anchor], articles[index])):
                        root_left, root_right = find(previous), find(index)
                        if root_left != root_right:
                            parents[root_right] = root_left
        for word in words:
            postings.setdefault(word, []).append(index)

    grouped: dict[int, list[dict[str, Any]]] = {}
    for index, article in enumerate(articles):
        grouped.setdefault(find(index), []).append(article)
    groups = list(grouped.values())
    for group in groups:
        group.sort(key=lambda item: item.get("timestamp", 0), reverse=True)
    groups.sort(key=lambda group: group[0].get("timestamp", 0), reverse=True)
    return groups


def classify_article(article: dict[str, Any]) -> str:
    """POLITICS, ECONOMY, TECHNOLOGY, SECURITY or GENERAL (see intel.py)."""
    from .intel import topic_of
    return topic_of(article)


def source_region(article: dict[str, Any]) -> str:
    region = article.get("source_region")
    if region:
        return region
    source = SOURCE_BY_NAME.get(article.get("source", ""))
    return source["region"] if source else "WORLD"
