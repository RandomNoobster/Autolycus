"""Async client for Politics & War live subscriptions.

Politics & War publishes model events through a Pusher server (protocol 7). One
:class:`PnwSubscription` covers one connection:

1. ``GET {subscribe_url}?api_key=...`` returns ``{"channel": ...}``.
2. Open the websocket and wait for ``pusher:connection_established`` (``socket_id`` and
   ``activity_timeout``).
3. ``POST {auth_url}`` with ``socket_id`` and ``channel_name`` returns ``{"auth": ...}``.
4. Send ``pusher:subscribe`` and wait for ``pusher_internal:subscription_succeeded``.
5. Iterate: events carry a JSON-encoded ``data`` string; ``BULK_*`` events carry a list,
   which is yielded item by item.

While iterating, the client answers ``pusher:ping`` with ``pusher:pong`` and, after
``activity_timeout`` seconds without any frame, sends its own ``pusher:ping``. Iteration
always ends with :class:`SubscriptionClosed` (socket closed, errored, or no pong), so the
caller decides how to back off before reconnecting with a fresh instance.

Example::

    async with PnwSubscription(api_key, "nation", "update") as subscription:
        async for item in subscription:
            ...
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Mapping
from types import TracebackType
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

SUBSCRIBE_URL = "https://api.politicsandwar.com/subscriptions/v1/subscribe/{model}/{event}"
AUTH_URL = "https://api.politicsandwar.com/subscriptions/v1/auth"
SOCKET_URL = "wss://socket.politicsandwar.com/app/a22734a47847a64386c8?protocol=7"

# Pusher clients ping after at most 120 s of silence, or sooner if the server asks.
DEFAULT_ACTIVITY_TIMEOUT_SECONDS = 120.0
PONG_TIMEOUT_SECONDS = 30.0
HANDSHAKE_TIMEOUT_SECONDS = 30.0
SUBSCRIBE_TIMEOUT_SECONDS = 60.0
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=30)
# No total for the session: it must not bound the lifetime of the websocket.
SESSION_TIMEOUT = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=30)
# Receive timeouts are applied per call (see _next_frame), so none at the socket level.
WS_TIMEOUT = aiohttp.ClientWSTimeout(ws_receive=None, ws_close=10.0)

_CLOSED_TYPES = frozenset(
    {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED}
)


class SubscriptionError(RuntimeError):
    """Subscribing failed: the channel request, the auth request, or Pusher said no."""


class SubscriptionClosed(SubscriptionError):
    """The socket closed, errored or went silent. Reconnect with a new subscription."""

    def __init__(self, reason: str, close_code: int | None = None) -> None:
        detail = reason if close_code is None else f"{reason} (close_code={close_code})"
        super().__init__(detail)
        self.close_code = close_code


def _decode_data(data: Any) -> Any:
    """Pusher sends ``data`` as a JSON-encoded string; accept already-decoded values too."""
    return json.loads(data) if isinstance(data, str) else data


def _filters_param(filters: Mapping[str, Any]) -> dict[str, str]:
    return {
        key: ",".join(str(v) for v in value) if isinstance(value, list) else str(value)
        for key, value in filters.items()
    }


class PnwSubscription:
    """One live subscription to a Politics & War model event (see module docstring).

    Args:
        api_key: Politics & War API key used to request the channel.
        model: Subscription model, e.g. ``"nation"``.
        event: Subscription event, e.g. ``"update"``.
        filters: Optional query filters (lists are sent comma-separated).
        session: Optional session to use; one is created and closed with the
            subscription when omitted.
        subscribe_url, auth_url, socket_url: Endpoint overrides (tests use these).
        pong_timeout: Seconds to wait for any frame after sending ``pusher:ping``.
        handshake_timeout: Seconds to wait for ``pusher:connection_established``.
        subscribe_timeout: Seconds to wait for ``pusher_internal:subscription_succeeded``.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        event: str,
        filters: Mapping[str, Any] | None = None,
        *,
        session: aiohttp.ClientSession | None = None,
        subscribe_url: str = SUBSCRIBE_URL,
        auth_url: str = AUTH_URL,
        socket_url: str = SOCKET_URL,
        pong_timeout: float = PONG_TIMEOUT_SECONDS,
        handshake_timeout: float = HANDSHAKE_TIMEOUT_SECONDS,
        subscribe_timeout: float = SUBSCRIBE_TIMEOUT_SECONDS,
    ) -> None:
        self.model = model
        self.event = event
        self.channel: str | None = None
        self.socket_id: str | None = None
        self.activity_timeout = DEFAULT_ACTIVITY_TIMEOUT_SECONDS
        self._api_key = api_key
        self._filters = dict(filters or {})
        self._session = session
        self._owns_session = session is None
        self._subscribe_url = subscribe_url
        self._auth_url = auth_url
        self._socket_url = socket_url
        self._pong_timeout = pong_timeout
        self._handshake_timeout = handshake_timeout
        self._subscribe_timeout = subscribe_timeout
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._last_error: str | None = None

    async def __aenter__(self) -> PnwSubscription:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        return self.items()

    async def connect(self) -> None:
        """Request a channel, open the socket and subscribe to the channel.

        Raises:
            SubscriptionError: If any step is refused, times out, or its HTTP request
                fails (with the API key redacted from the message).
            aiohttp.ClientError: If the websocket handshake fails.
        """
        if self._ws is not None:
            raise RuntimeError("subscription is already connected")
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=SESSION_TIMEOUT)
            self._owns_session = True
        try:
            self.channel = await self._request_channel()
            self._ws = await self._session.ws_connect(
                self._socket_url, timeout=WS_TIMEOUT, max_msg_size=0
            )
            established = await self._wait_for(
                "pusher:connection_established", self._handshake_timeout
            )
            info = _decode_data(established.get("data"))
            self.socket_id = str(info["socket_id"])
            server_timeout = float(info.get("activity_timeout") or 0)
            if server_timeout > 0:
                self.activity_timeout = min(DEFAULT_ACTIVITY_TIMEOUT_SECONDS, server_timeout)
            auth = await self._authorize()
            await self._send("pusher:subscribe", {"auth": auth, "channel": self.channel})
            await self._wait_for(
                "pusher_internal:subscription_succeeded",
                self._subscribe_timeout,
                channel=self.channel,
            )
        except BaseException:
            await self.close()
            raise
        logger.debug(
            "subscribed model=%s event=%s channel=%s", self.model, self.event, self.channel
        )

    async def items(self) -> AsyncIterator[dict[str, Any]]:
        """Yield every item delivered on the channel, flattening ``BULK_*`` events.

        Raises:
            SubscriptionClosed: When the connection ends, always.
        """
        if self._ws is None:
            raise RuntimeError("call connect() before iterating")
        while True:
            frame = await self._next_frame()
            event = str(frame.get("event") or "")
            if event.startswith("pusher"):
                logger.debug("ignoring %s frame", event)
                continue
            if frame.get("channel") != self.channel:
                logger.debug("ignoring %s for channel %s", event, frame.get("channel"))
                continue
            try:
                data = _decode_data(frame.get("data"))
            except json.JSONDecodeError as exc:
                logger.warning("dropping %s with undecodable data: %s", event, exc)
                continue
            items = data if event.startswith("BULK_") and isinstance(data, list) else [data]
            for item in items:
                yield item

    async def close(self) -> None:
        """Close the socket and, if this subscription created it, the session."""
        ws, self._ws = self._ws, None
        try:
            if ws is not None and not ws.closed:
                with contextlib.suppress(Exception):
                    await ws.close()
        finally:
            # Also when cancelled while the socket closes, or the session leaks.
            if self._owns_session and self._session is not None:
                session, self._session = self._session, None
                await session.close()

    def _redact(self, text: str) -> str:
        return text.replace(self._api_key, "***") if self._api_key else text

    async def _request_channel(self) -> str:
        assert self._session is not None
        url = self._subscribe_url.format(model=self.model, event=self.event)
        params = {"api_key": self._api_key, **_filters_param(self._filters)}
        try:
            async with self._session.get(url, params=params, timeout=HTTP_TIMEOUT) as response:
                payload = await self._read_json(response, "subscribe")
        except aiohttp.ClientError as exc:
            # aiohttp's messages can include the request URL, which carries the API key;
            # `from None` keeps the original (and its URL) out of logged tracebacks.
            raise SubscriptionError(
                f"subscribe request failed: {type(exc).__name__}: {self._redact(str(exc))}"
            ) from None
        if payload.get("error") is not None:
            raise SubscriptionError(f"subscribe refused: {payload['error']}")
        channel = payload.get("channel")
        if not channel:
            raise SubscriptionError(f"subscribe response has no channel (status={response.status})")
        return str(channel)

    async def _authorize(self) -> str:
        assert self._session is not None
        form = {"socket_id": self.socket_id, "channel_name": self.channel}
        try:
            async with self._session.post(self._auth_url, data=form, timeout=HTTP_TIMEOUT) as response:
                if response.status != 200:
                    raise SubscriptionError(f"channel auth refused (status={response.status})")
                payload = await self._read_json(response, "auth")
        except aiohttp.ClientError as exc:
            raise SubscriptionError(
                f"channel auth request failed: {type(exc).__name__}: {self._redact(str(exc))}"
            ) from None
        errors = payload.get("errors") or payload.get("error")
        if errors:
            raise SubscriptionError(f"channel auth refused: {errors}")
        auth = payload.get("auth")
        if not auth:
            raise SubscriptionError("channel auth response has no auth signature")
        return str(auth)

    @staticmethod
    async def _read_json(response: aiohttp.ClientResponse, step: str) -> dict[str, Any]:
        # Never put the request URL in errors: it carries the API key.
        try:
            payload = await response.json(content_type=None)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise SubscriptionError(
                f"{step} response is not JSON (status={response.status})"
            ) from exc
        if not isinstance(payload, dict):
            raise SubscriptionError(f"{step} response is not an object (status={response.status})")
        return payload

    async def _send(self, event: str, data: dict[str, Any]) -> None:
        assert self._ws is not None
        try:
            await self._ws.send_json({"event": event, "data": data})
        except (ConnectionResetError, aiohttp.ClientConnectionError) as exc:
            raise SubscriptionClosed(f"send failed: {exc}", self._ws.close_code) from exc

    async def _wait_for(
        self, expected: str, timeout: float, *, channel: str | None = None
    ) -> dict[str, Any]:
        try:
            async with asyncio.timeout(timeout):
                while True:
                    frame = await self._next_frame()
                    event = frame.get("event")
                    if event == expected and (channel is None or frame.get("channel") == channel):
                        return frame
                    if event == "pusher:subscription_error":
                        raise SubscriptionError(
                            f"subscription refused: {_decode_data(frame.get('data'))}"
                        )
                    logger.debug("ignoring %s while waiting for %s", event, expected)
        except TimeoutError:
            reason = f" after pusher:error {self._last_error}" if self._last_error else ""
            raise SubscriptionError(f"no {expected} within {timeout:g}s{reason}") from None

    async def _next_frame(self) -> dict[str, Any]:
        """Return the next frame that is not keepalive traffic, answering pings on the way."""
        assert self._ws is not None
        awaiting_pong = False
        while True:
            timeout = self._pong_timeout if awaiting_pong else self.activity_timeout
            try:
                message = await self._ws.receive(timeout=timeout)
            except TimeoutError:
                if awaiting_pong:
                    raise SubscriptionClosed(
                        f"no pong within {self._pong_timeout:g}s of pusher:ping"
                    ) from None
                await self._send("pusher:ping", {})
                awaiting_pong = True
                continue
            # Any frame proves the connection is alive, not only pusher:pong.
            awaiting_pong = False
            frame = self._parse(message)
            if frame is None:
                continue
            event = frame.get("event")
            if event == "pusher:ping":
                await self._send("pusher:pong", {})
            elif event == "pusher:pong":
                pass
            elif event == "pusher:error":
                self._last_error = str(_decode_data(frame.get("data")))
                logger.warning("pusher:error %s", self._last_error)
            else:
                return frame

    def _parse(self, message: aiohttp.WSMessage) -> dict[str, Any] | None:
        assert self._ws is not None
        if message.type in _CLOSED_TYPES:
            reason = "socket closed"
            if self._last_error:
                reason += f" after pusher:error {self._last_error}"
            raise SubscriptionClosed(reason, self._ws.close_code)
        if message.type == aiohttp.WSMsgType.ERROR:
            raise SubscriptionClosed(f"socket error: {self._ws.exception()!r}", self._ws.close_code)
        if message.type != aiohttp.WSMsgType.TEXT:
            return None
        try:
            frame = json.loads(message.data)
        except json.JSONDecodeError:
            logger.warning("ignoring non-JSON websocket frame (%d chars)", len(message.data))
            return None
        if not isinstance(frame, dict):
            logger.warning("ignoring websocket frame that is not an object")
            return None
        return frame
