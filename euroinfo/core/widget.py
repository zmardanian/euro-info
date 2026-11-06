"""JSON for the KDE Plasma widget: `euro-info --widget-json`.

The widget runs the installed app with this flag, so it needs no Python setup
of its own. stdout carries JSON only; diagnostics go to the log.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import sys

from . import feeds


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime.datetime):
        return value.isoformat(sep=" ", timespec="minutes")
    if isinstance(value, datetime.date):
        return value.isoformat()
    return value if isinstance(value, str) else str(value)


def _article(article: dict) -> dict:
    return {
        "title": _text(article.get("title")),
        "source": _text(article.get("source")),
        "link": _text(article.get("link")),
        "image_url": _text(article.get("image_url")),
        "published": _text(article.get("time") or article.get("published")),
        "category": feeds.classify_article(article),
    }


def selected_sources() -> list[dict]:
    """The sources chosen in the app, when its settings can be read."""
    try:
        from .. import settings
        chosen = settings.get().value("selected_sources", None)
    except Exception:  # widget output must never fail because of settings
        chosen = None
    if isinstance(chosen, str):
        chosen = [chosen]
    if not chosen:
        return feeds.NEWS_SOURCES
    names = set(chosen)
    return [source for source in feeds.NEWS_SOURCES if source["name"] in names] or feeds.NEWS_SOURCES


def payload() -> dict:
    from .intel import NewsIndex
    with contextlib.redirect_stdout(sys.stderr):
        weather = feeds.get_weather() or {}
        news = [item for item in feeds.get_news(selected_sources()) if isinstance(item, dict)]
        # Most important first; sport, celebrity and local US news stay out of the widget.
        index = NewsIndex(news)
        ranked = index.rank([item for item in news if not index.is_low_priority(item)])
        articles = [dict(_article(item), importance=index.score(item)) for item in ranked]
    images = sum(bool(item["image_url"]) for item in articles)
    return {"ok": True, "articles": articles, "weather": weather,
            "status": f"Updated • {len(articles)} stories • {images} RSS images"}


def main() -> int:
    try:
        result, code = payload(), 0
    except Exception as exc:  # report every failure to the widget as JSON
        result, code = {"ok": False, "articles": [], "weather": {}, "status": f"Backend error: {exc}"}, 1
    sys.stdout.write(json.dumps(result, ensure_ascii=False, default=_text, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return code
