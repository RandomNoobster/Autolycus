"""Local stand-in for the PnW subscribe/auth endpoints and Pusher socket, for tests.

It replays the frames in ``fixtures/pnw_nation_subscription.json`` and records what the
client sent, so tests can drive :class:`infra.pnw_subscriptions.PnwSubscription` (and
the scanner worker) without the network.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web
from aiohttp.test_utils import TestServer

FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures" / "pnw_nation_subscription.json").read_text()
)
FRAMES = FIXTURE["frames"]
SOCKET_ID = json.loads(FRAMES["connection_established"]["data"])["socket_id"]
_CLOSED = {WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED}

StreamScript = Callable[[web.WebSocketResponse, "FakePusher"], Awaitable[None]]


async def replay_recorded_stream(ws: web.WebSocketResponse, server: FakePusher) -> None:
    """Send the recorded frames, read the pong owed for their ``pusher:ping``, close 4200."""
    for frame in FRAMES["stream"]:
        await ws.send_json(frame)
    await server.receive_client_frame(ws)
    await ws.close(code=4200, message=b"reconnect")


async def record_until_client_closes(ws: web.WebSocketResponse, server: FakePusher) -> None:
    """Send nothing; record client frames until the client hangs up."""
    while await server.receive_client_frame(ws, timeout=10.0) is not None:
        pass


class FakePusher:
    """Serve one scripted subscription; use as ``async with FakePusher(...) as server``."""

    def __init__(
        self,
        stream: StreamScript = replay_recorded_stream,
        *,
        activity_timeout: float | None = None,
        subscribe_response: dict[str, Any] | None = None,
        auth_status: int = 200,
        subscribed_frame: dict[str, Any] | None = None,
        send_established: bool = True,
    ) -> None:
        self.stream = stream
        self.activity_timeout = activity_timeout
        self.subscribe_response = (
            {"channel": FIXTURE["channel"]} if subscribe_response is None else subscribe_response
        )
        self.auth_status = auth_status
        self.subscribed_frame = subscribed_frame or FRAMES["subscription_succeeded"]
        self.send_established = send_established
        self.subscribe_requests: list[dict[str, Any]] = []
        self.auth_forms: list[dict[str, str]] = []
        self.client_frames: list[dict[str, Any]] = []
        self.sockets_opened = 0
        self._server: TestServer | None = None

    async def __aenter__(self) -> FakePusher:
        app = web.Application()
        app.router.add_get("/subscriptions/v1/subscribe/{model}/{event}", self._subscribe)
        app.router.add_post("/subscriptions/v1/auth", self._auth)
        app.router.add_get("/app/{key}", self._socket)
        self._server = TestServer(app)
        await self._server.start_server()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        assert self._server is not None
        await self._server.close()

    def urls(self) -> dict[str, str]:
        """Keyword arguments pointing a ``PnwSubscription`` at this server."""
        assert self._server is not None
        host, port = self._server.host, self._server.port
        return {
            "subscribe_url": f"http://{host}:{port}/subscriptions/v1/subscribe/{{model}}/{{event}}",
            "auth_url": f"http://{host}:{port}/subscriptions/v1/auth",
            "socket_url": f"ws://{host}:{port}/app/a22734a47847a64386c8?protocol=7",
        }

    def client_events(self) -> list[str]:
        return [frame.get("event") for frame in self.client_frames]

    async def receive_client_frame(
        self, ws: web.WebSocketResponse, timeout: float = 5.0
    ) -> dict[str, Any] | None:
        """Record and return the next client frame, or ``None`` once the client closed."""
        message = await ws.receive(timeout=timeout)
        if message.type in _CLOSED:
            return None
        frame = json.loads(message.data)
        self.client_frames.append(frame)
        return frame

    async def _subscribe(self, request: web.Request) -> web.Response:
        self.subscribe_requests.append(
            {"path": request.match_info.copy(), "query": dict(request.query)}
        )
        return web.json_response(self.subscribe_response)

    async def _auth(self, request: web.Request) -> web.Response:
        self.auth_forms.append({key: str(value) for key, value in (await request.post()).items()})
        if self.auth_status != 200:
            return web.json_response({"error": "unauthorized"}, status=self.auth_status)
        return web.json_response({"auth": FIXTURE["auth"]})

    async def _socket(self, request: web.Request) -> web.WebSocketResponse:
        self.sockets_opened += 1
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        if not self.send_established:
            await record_until_client_closes(ws, self)
            return ws
        established = dict(FRAMES["connection_established"])
        if self.activity_timeout is not None:
            established["data"] = json.dumps(
                {"socket_id": SOCKET_ID, "activity_timeout": self.activity_timeout}
            )
        await ws.send_json(established)
        await self.receive_client_frame(ws)  # pusher:subscribe
        await ws.send_json(self.subscribed_frame)
        await self.stream(ws, self)
        return ws


async def wait_for(predicate: Callable[[], bool], timeout: float = 10.0) -> None:
    """Poll ``predicate`` until it is true, failing the test after ``timeout`` seconds."""
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.02)
