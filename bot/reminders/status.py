"""Politics & War turn counts for the reminder scheduler."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from logic import api_client
from logic.reminders import chunked

_BATCH_SIZE = 500


class StatusFetchError(RuntimeError):
    """Politics & War didn't return a usable nation list."""


def _nation_rows(response: Any) -> list[Any]:
    """The nation rows of a response, or an error when the response isn't a clean result.

    A missing nation means it was deleted, and the scheduler removes reminders for it, so
    an error or a malformed reply must not be read as "no nations".
    """
    if not isinstance(response, Mapping):
        raise StatusFetchError("Politics & War returned no response")
    if response.get("errors"):
        raise StatusFetchError(f"Politics & War returned errors: {response['errors']!r:.500}")
    data = response.get("data")
    nations = data.get("nations") if isinstance(data, Mapping) else None
    rows = nations.get("data") if isinstance(nations, Mapping) else None
    if not isinstance(rows, list):
        raise StatusFetchError("Politics & War returned no nation list")
    return rows


class PnwStatusFetcher:
    """Reads beige and vacation-mode turns for many nations in batched GraphQL calls."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def fetch(self, nation_ids: Sequence[str]) -> dict[str, tuple[int, int]]:
        """Return ``{nation_id: (beige_turns, vacation_mode_turns)}``; unknown nations are omitted.

        Raises:
            StatusFetchError: If a batch came back with errors or without a nation list.
        """
        out: dict[str, tuple[int, int]] = {}
        for batch in chunked(list(nation_ids), _BATCH_SIZE):
            query = (
                f"{{nations(first:{_BATCH_SIZE} id:[{','.join(batch)}])"
                "{data{id beige_turns vacation_mode_turns}}}"
            )
            response = await api_client.call(query, self._api_key)
            for row in _nation_rows(response):
                try:
                    out[str(int(row["id"]))] = (
                        int(row.get("beige_turns") or 0),
                        int(row.get("vacation_mode_turns") or 0),
                    )
                except (KeyError, TypeError, ValueError):
                    continue
        return out
