"""Politics & War turn counts for the reminder scheduler."""
from __future__ import annotations

from typing import Sequence

from logic import api_client
from logic.reminders import chunked

_BATCH_SIZE = 500


class PnwStatusFetcher:
    """Reads beige and vacation-mode turns for many nations in batched GraphQL calls."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def fetch(self, nation_ids: Sequence[str]) -> dict[str, tuple[int, int]]:
        """Return ``{nation_id: (beige_turns, vacation_mode_turns)}``; unknown nations are omitted."""
        out: dict[str, tuple[int, int]] = {}
        for batch in chunked(list(nation_ids), _BATCH_SIZE):
            query = (
                f"{{nations(first:{_BATCH_SIZE} id:[{','.join(batch)}])"
                "{data{id beige_turns vacation_mode_turns}}}"
            )
            response = await api_client.call(query, self._api_key)
            rows = (((response or {}).get("data") or {}).get("nations") or {}).get("data") or []
            for row in rows:
                try:
                    out[str(int(row["id"]))] = (
                        int(row.get("beige_turns") or 0),
                        int(row.get("vacation_mode_turns") or 0),
                    )
                except (KeyError, TypeError, ValueError):
                    continue
        return out
