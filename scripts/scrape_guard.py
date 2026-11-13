"""Stop a wiki scrape as soon as the site starts blocking it.

The scrapers never try to get past bot protection. A challenge page, a rate
limit or an access-denied response ends the run, and the previous dump is kept:
scrapers write to ``partial_path(out)`` and only ``publish(out)`` on success.
"""
from __future__ import annotations

import os

import requests

BLOCK_STATUSES = {401, 403, 429, 503}
_CHALLENGE_TITLES = ("just a moment", "attention required", "access denied")


class BotBlockedError(RuntimeError):
    """The site answered with a bot challenge, a rate limit or an access denial."""


def check_response(response: requests.Response) -> None:
    """Raise BotBlockedError if the response is a block rather than content."""
    reasons = []
    if response.status_code in BLOCK_STATUSES:
        reasons.append(f"HTTP {response.status_code}")
    if response.headers.get("cf-mitigated"):
        reasons.append(f"cf-mitigated={response.headers['cf-mitigated']}")
    head = response.text[:4000].lower()
    reasons += [f"page title '{title}'" for title in _CHALLENGE_TITLES if f"<title>{title}" in head]
    if reasons:
        if response.headers.get("retry-after"):
            reasons.append(f"retry-after={response.headers['retry-after']}")
        raise BotBlockedError(f"{response.url}: " + ", ".join(reasons))


def partial_path(path: str) -> str:
    return path + ".partial"


def publish(path: str) -> None:
    """Replace the previous dump with the finished partial file."""
    os.replace(partial_path(path), path)
