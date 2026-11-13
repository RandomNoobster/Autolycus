from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from collections.abc import Mapping
from typing import Any

import aiohttp
import requests

# External Politics & War GraphQL client. Pure logic, no Discord imports.
logger = logging.getLogger(__name__)
MAX_LOGGED_RESPONSE_BODY_CHARS = 2000
MAX_LOGGED_QUERY_PREVIEW_CHARS = 10_000
# Upper bound for one HTTP request; large scanner pages can take a while to build.
REQUEST_TIMEOUT_SECONDS = 90
SYNC_REQUEST_TIMEOUT_SECONDS = 10
# A call waits out at most this many rate-limit replies (429 / Retry-After) before failing,
# so a throttled key can't hold an API worker thread indefinitely.
MAX_RATE_LIMIT_WAITS = 5
DEFAULT_RESET_AFTER_SECONDS = 5
# Cap on any single wait taken from a response header.
MAX_RATE_LIMIT_WAIT_SECONDS = 120
DIAGNOSTIC_RESPONSE_HEADERS = (
    "Content-Type",
    "Content-Length",
    "Server",
    "Via",
    "CF-Ray",
    "X-Cache",
    "Retry-After",
    "X-Ratelimit-Remaining",
    "X-Ratelimit-Reset-After",
)


class PnWServerError(RuntimeError):
    """Politics & War server-side failure (5xx / internal errors)."""


def _error_messages(payload: Any) -> list[str]:
    """Message strings from a GraphQL ``errors`` list or a P&W ``error`` object.

    Only the error envelope is read: ``data`` holds player-written text (nation,
    leader and alliance names, the Discord field) that must never be mistaken for
    an error message.
    """
    messages: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, str):
            messages.append(value)
        elif isinstance(value, Mapping):
            message = value.get("message")
            if isinstance(message, str):
                messages.append(message)
            if value.get("errors") is not None:
                collect(value.get("errors"))
        elif isinstance(value, list):
            for item in value:
                collect(item)

    if isinstance(payload, Mapping):
        collect(payload.get("errors"))
        collect(payload.get("error"))
    return messages


def _is_pnw_server_error_response(status: int, payload: Any) -> bool:
    if status >= 500:
        return True
    return any("internal server error" in message.lower() for message in _error_messages(payload))


def _is_invalid_api_key_response(payload: Any) -> bool:
    return any("invalid api_key" in message.lower() for message in _error_messages(payload))


# Rate-limit state shared by every call in this process (they all use the same key).
_rate_limit_lock = threading.Lock()
_rate_limited_until = 0.0  # time.monotonic() value before which no request should be sent


def _header_seconds(headers: Mapping[str, str], name: str, default: float) -> float:
    """Parse a seconds header, falling back to ``default`` when missing or malformed."""
    raw = headers.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(value) or value < 0:
        return default
    return min(value, MAX_RATE_LIMIT_WAIT_SECONDS)


def _seconds_until_rate_limit_resets() -> float:
    return max(0.0, _rate_limited_until - time.monotonic())


def _note_rate_limit_headers(headers: Mapping[str, str]) -> None:
    """After the reply that used the window's last request, hold back the *next* request.

    ``X-Ratelimit-Remaining`` counts the requests left after this one, so a reply
    carrying ``0`` is still a valid answer and is returned to the caller.
    """
    global _rate_limited_until
    if headers.get("X-Ratelimit-Remaining") != "0":
        return
    reset_after = _header_seconds(headers, "X-Ratelimit-Reset-After", DEFAULT_RESET_AFTER_SECONDS)
    with _rate_limit_lock:
        _rate_limited_until = max(_rate_limited_until, time.monotonic() + reset_after)


def _rate_limit_wait_seconds(status: int, headers: Mapping[str, str]) -> float | None:
    """Seconds to wait before resending a rejected request, or None if it wasn't rate limited."""
    if status == 429:
        if "Retry-After" in headers:
            return _header_seconds(headers, "Retry-After", DEFAULT_RESET_AFTER_SECONDS)
        return _header_seconds(headers, "X-Ratelimit-Reset-After", DEFAULT_RESET_AFTER_SECONDS)
    if status >= 400 and "Retry-After" in headers:
        return _header_seconds(headers, "Retry-After", DEFAULT_RESET_AFTER_SECONDS)
    return None


def _rate_limit_exhausted_error(status: int) -> PnWServerError:
    return PnWServerError(
        f"PnW server error: still rate limited after {MAX_RATE_LIMIT_WAITS} waits (status={status})"
    )


def _redact(text: str, secret: str) -> str:
    return text.replace(secret, "***") if secret else text


async def paginate_call(data: str, path: str, api_key: str, use_bot_key: bool = False) -> list[dict[str, Any]]:
    n = 0
    has_more_pages = True
    data_to_return: list[dict[str, Any]] = []

    while has_more_pages:
        n += 1
        response = await call(data.replace("page_number", str(n), 1), api_key, use_bot_key=use_bot_key)
        data_to_return += response['data'][path]['data']
        has_more_pages = response['data'][path]['paginatorInfo']['hasMorePages']

    return data_to_return

async def call(data: str, api_key: str, retry_limit: int = 2, use_bot_key: bool = False, bot_key: str | None = None) -> dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        retry = 0
        rate_limit_waits = 0
        while True:
            pending = _seconds_until_rate_limit_resets()
            if pending > 0:
                await asyncio.sleep(pending)
            headers: dict[str, str] = {}
            if use_bot_key and bot_key:
                headers = {'X-Bot-Key': bot_key, 'X-Api-Key': api_key}
            async with session.post(f'https://api.politicsandwar.com/graphql?api_key={api_key}', json={"query": data}, headers=headers) as response:
                wait = _rate_limit_wait_seconds(response.status, response.headers)
                if wait is not None:
                    rate_limit_waits += 1
                    if rate_limit_waits > MAX_RATE_LIMIT_WAITS:
                        raise _rate_limit_exhausted_error(response.status)
                    await asyncio.sleep(wait)
                    continue
                _note_rate_limit_headers(response.headers)
                try:
                    json_response = await response.json()
                except aiohttp.ContentTypeError:
                    raw_body = await response.read()
                    body_preview = raw_body[:MAX_LOGGED_RESPONSE_BODY_CHARS].decode("utf-8", errors="replace")
                    sanitized_url = str(response.url).replace(api_key, "***")
                    header_snapshot = {
                        key: response.headers.get(key)
                        for key in DIAGNOSTIC_RESPONSE_HEADERS
                        if response.headers.get(key) is not None
                    }
                    logger.error(
                        "Unexpected non-JSON API response method=POST url=%s status=%s reason=%s "
                        "content_type=%s body_len=%s headers=%s query_len=%s query_preview=%r body_preview=%r",
                        sanitized_url,
                        response.status,
                        response.reason,
                        response.headers.get("Content-Type"),
                        len(raw_body),
                        header_snapshot,
                        len(data),
                        data[:MAX_LOGGED_QUERY_PREVIEW_CHARS],
                        body_preview,
                    )
                    raise ValueError(
                        "Attempt to decode JSON with unexpected mimetype: "
                        f"status={response.status} reason={response.reason} "
                        f"content_type={response.headers.get('Content-Type')} body_len={len(raw_body)} "
                        f"query_len={len(data)} body_preview={body_preview!r}"
                    )
                if _is_pnw_server_error_response(response.status, json_response):
                    # Usually transient: retry before reporting an outage.
                    if retry < retry_limit:
                        retry += 1
                        await asyncio.sleep(1)
                        continue
                    raise PnWServerError(
                        f"PnW server error (status={response.status}, reason={response.reason})"
                    )
                if response.status == 401 and _is_invalid_api_key_response(json_response):
                    raise ConnectionError("Invalid API key.")
                if "data" not in json_response and not use_bot_key:
                    if retry < retry_limit:
                        retry += 1
                        await asyncio.sleep(1)
                        continue
                    elif "error" in json_response:
                        raise Exception(json_response["error"])
                    elif "errors" in json_response:
                        raise Exception(json_response["errors"])
                return json_response


def query_sync(query_string: str, api_key: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Synchronous GraphQL query to Politics & War API.
    
    Args:
        query_string: GraphQL query string
        api_key: P&W API key
        variables: Optional query variables
        
    Returns:
        Response dictionary with 'data' and possibly 'errors' keys
        
    Raises:
        ConnectionError: If API key is invalid
        Exception: For other API errors
    """
    url = f"https://api.politicsandwar.com/graphql?api_key={api_key}"
    payload = {"query": query_string}
    if variables:
        payload["variables"] = variables
    
    retry_count = 0
    max_retries = 2
    rate_limit_waits = 0

    while True:
        pending = _seconds_until_rate_limit_resets()
        if pending > 0:
            time.sleep(pending)
        try:
            response = requests.post(url, json=payload, timeout=SYNC_REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            # requests repeats the request URL, which carries the API key, in its messages.
            raise ConnectionError(_redact(str(exc), api_key)) from None

        wait = _rate_limit_wait_seconds(response.status_code, response.headers)
        if wait is not None:
            rate_limit_waits += 1
            if rate_limit_waits > MAX_RATE_LIMIT_WAITS:
                raise _rate_limit_exhausted_error(response.status_code)
            time.sleep(wait)
            continue
        _note_rate_limit_headers(response.headers)

        try:
            json_response = response.json()
        except requests.exceptions.JSONDecodeError:
            raise Exception(f"Invalid JSON response: {response.text}")
        if _is_pnw_server_error_response(response.status_code, json_response):
            # Usually transient: retry before reporting an outage.
            if retry_count < max_retries:
                retry_count += 1
                time.sleep(1)
                continue
            raise PnWServerError(
                f"PnW server error (status={response.status_code}, reason={response.reason})"
            )

        # Check for authentication errors
        if response.status_code == 401 and _is_invalid_api_key_response(json_response):
            raise ConnectionError("Invalid API key.")

        # Retry on error if retries remain
        if "data" not in json_response:
            if retry_count < max_retries:
                retry_count += 1
                time.sleep(1)
                continue
            elif "error" in json_response:
                raise Exception(json_response["error"])
            elif "errors" in json_response:
                raise Exception(json_response["errors"])

        return json_response
