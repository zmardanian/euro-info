"""'New version available' check against the project's GitHub releases.

One small anonymous request to api.github.com, at most once a day, and only
when the reader has not turned the check off in Settings.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import requests

from .. import REPOSITORY, __version__, logs

log = logs.get("updates")

LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
CHECK_INTERVAL_SECONDS = 20 * 3600


@dataclass
class Release:
    version: str
    url: str
    name: str
    notes: str


def parse_version(text: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", str(text or "").split("-", 1)[0])
    return tuple(int(number) for number in numbers[:3]) or (0,)


def is_newer(candidate: str, current: str = __version__) -> bool:
    return parse_version(candidate) > parse_version(current)


class Unavailable(RuntimeError):
    """GitHub has no public release information (for example, a private repository)."""


def latest_release(timeout=(4, 8)) -> Release | None:
    response = requests.get(LATEST_RELEASE_URL, timeout=timeout, headers={
        "Accept": "application/vnd.github+json", "User-Agent": f"EuroInfo/{__version__}"})
    if response.status_code == 404:
        raise Unavailable("GitHub has no public release information for Euro Info.")
    response.raise_for_status()
    payload = response.json()
    tag = str(payload.get("tag_name") or "")
    if not tag or payload.get("draft") or payload.get("prerelease"):
        return None
    return Release(tag.lstrip("vV"), str(payload.get("html_url") or ""),
                   str(payload.get("name") or tag), str(payload.get("body") or "")[:4000])


def check() -> Release | None:
    """The newer release, or None when up to date. Raises on network errors."""
    release = latest_release()
    if release and is_newer(release.version):
        log.info("Euro Info %s is available", release.version)
        return release
    return None
