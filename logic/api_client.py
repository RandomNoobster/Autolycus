from __future__ import annotations

import asyncio
import logging
from typing import Any, Union

import aiohttp
import requests

from .merge_utils import get_query, merge  # re-export convenience

# External Politics & War GraphQL client. Pure logic, no Discord imports.
logger = logging.getLogger(__name__)
MAX_LOGGED_RESPONSE_BODY_CHARS = 2000
MAX_LOGGED_QUERY_PREVIEW_CHARS = 10_000
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
    async with aiohttp.ClientSession() as session:
        retry = 0
        while True:
            headers: dict[str, str] = {}
            if use_bot_key and bot_key:
                headers = {'X-Bot-Key': bot_key, 'X-Api-Key': api_key}
            async with session.post(f'https://api.politicsandwar.com/graphql?api_key={api_key}', json={"query": data}, headers=headers) as response:
                if "X-Ratelimit-Remaining" in response.headers and response.headers['X-Ratelimit-Remaining'] == '0':
                    await asyncio.sleep(int(response.headers['X-Ratelimit-Reset-After']))
                    continue
                if "Retry-After" in response.headers:
                    await asyncio.sleep(int(response.headers['Retry-After']))
                    continue
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
                if response.status == 401 and "error" in json_response:
                    if "invalid api_key" in json_response["error"]["errors"][0]["message"]:
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
    
    while retry_count <= max_retries:
        response = requests.post(url, json=payload, timeout=10)
        
        # Handle rate limiting
        if response.headers.get('X-Ratelimit-Remaining') == '0':
            import time
            reset_after = int(response.headers.get('X-Ratelimit-Reset-After', 5))
            time.sleep(reset_after)
            continue
            
        if 'Retry-After' in response.headers:
            import time
            time.sleep(int(response.headers['Retry-After']))
            continue
        
        try:
            json_response = response.json()
        except requests.exceptions.JSONDecodeError:
            raise Exception(f"Invalid JSON response: {response.text}")
        
        # Check for authentication errors
        if response.status_code == 401 and "error" in json_response:
            if "invalid api_key" in str(json_response.get("error", "")).lower():
                raise ConnectionError("Invalid API key.")
        
        # Retry on error if retries remain
        if "data" not in json_response:
            if retry_count < max_retries:
                retry_count += 1
                import time
                time.sleep(1)
                continue
            elif "error" in json_response:
                raise Exception(json_response["error"])
            elif "errors" in json_response:
                raise Exception(json_response["errors"])
        
        return json_response
    
    raise Exception("Max retries exceeded")
