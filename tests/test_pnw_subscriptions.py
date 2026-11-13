"""Tests for the Politics & War subscription client, replaying recorded Pusher frames."""

import asyncio
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from infra.pnw_payloads import coerce_payload
from infra.pnw_subscriptions import PnwSubscription, SubscriptionClosed, SubscriptionError
from tests.pnw_fake_pusher import (
    FIXTURE,
    FRAMES,
    SOCKET_ID,
    FakePusher,
    record_until_client_closes,
)


def _subscription(server: FakePusher, **kwargs) -> PnwSubscription:
    return PnwSubscription("test-key", "nation", "update", **server.urls(), **kwargs)


async def _collect(subscription: PnwSubscription) -> tuple[list[dict], SubscriptionClosed]:
    items: list[dict] = []
    with pytest.raises(SubscriptionClosed) as closed:
        async with subscription:
            async for item in subscription:
                items.append(item)
    return items, closed.value


def test_recorded_frames_are_subscribed_and_yielded():
    async def scenario():
        async with FakePusher() as server:
            subscription = _subscription(server)
            items, closed = await _collect(subscription)
        return server, subscription, items, closed

    server, subscription, items, closed = asyncio.run(scenario())

    # NATION_UPDATE as-is, BULK_NATION_UPDATE flattened, other channels ignored.
    assert items == FIXTURE["expected_items"]
    assert closed.close_code == 4200
    assert server.subscribe_requests == [
        {"path": {"model": "nation", "event": "update"}, "query": {"api_key": "test-key"}}
    ]
    assert server.auth_forms == [{"socket_id": SOCKET_ID, "channel_name": FIXTURE["channel"]}]
    assert server.client_frames == [
        {
            "event": "pusher:subscribe",
            "data": {"auth": FIXTURE["auth"], "channel": FIXTURE["channel"]},
        },
        {"event": "pusher:pong", "data": {}},
    ]
    assert subscription.channel == FIXTURE["channel"]
    assert subscription.socket_id == SOCKET_ID
    assert subscription.activity_timeout == 120
    assert subscription._session is None  # owned session closed on exit


def test_recorded_items_coerce_to_the_rows_pnwkit_produced():
    rows = [coerce_payload("nation", item) for item in FIXTURE["expected_items"]]
    assert rows == FIXTURE["expected_rows"]
    assert "__dict__" not in json.dumps(rows)


def test_filters_are_sent_comma_separated():
    async def scenario():
        async with FakePusher() as server:
            subscription = PnwSubscription(
                "test-key", "nation", "update", {"alliance_id": [1, 2], "x": 3}, **server.urls()
            )
            await _collect(subscription)
        return server

    server = asyncio.run(scenario())
    assert server.subscribe_requests[0]["query"] == {
        "api_key": "test-key",
        "alliance_id": "1,2",
        "x": "3",
    }


def test_idle_socket_is_pinged_and_closed_without_pong():
    async def scenario():
        async with FakePusher(record_until_client_closes, activity_timeout=0.05) as server:
            items, closed = await _collect(_subscription(server, pong_timeout=0.1))
        return server, items, closed

    server, items, closed = asyncio.run(scenario())
    assert items == []
    assert "no pong" in str(closed)
    assert server.client_events() == ["pusher:subscribe", "pusher:ping"]


def test_answered_pings_keep_the_stream_alive():
    async def answer_pings_then_update(ws, server):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 0.3
        while loop.time() < deadline:
            frame = await server.receive_client_frame(ws, timeout=2.0)
            if frame and frame["event"] == "pusher:ping":
                await ws.send_json({"event": "pusher:pong", "data": "{}"})
        await ws.send_json(FRAMES["stream"][0])
        await ws.close(code=4200)

    async def scenario():
        async with FakePusher(answer_pings_then_update, activity_timeout=0.05) as server:
            items, closed = await _collect(_subscription(server, pong_timeout=0.5))
        return server, items, closed

    server, items, closed = asyncio.run(scenario())
    assert items == FIXTURE["expected_items"][:1]
    assert closed.close_code == 4200
    assert server.client_events().count("pusher:ping") >= 2


@pytest.mark.parametrize(
    ("server_kwargs", "message", "opens_socket"),
    [
        ({"subscribe_response": {"error": "Invalid API key"}}, "subscribe refused", False),
        ({"subscribe_response": {}}, "no channel", False),
        ({"auth_status": 401}, "auth refused", True),
        (
            {
                "subscribed_frame": {
                    "event": "pusher:subscription_error",
                    "channel": FIXTURE["channel"],
                    "data": json.dumps({"type": "AuthError", "error": "bad signature"}),
                }
            },
            "subscription refused",
            True,
        ),
        ({"send_established": False}, "no pusher:connection_established", True),
    ],
)
def test_refused_subscriptions_raise_and_release_resources(server_kwargs, message, opens_socket):
    async def scenario():
        async with FakePusher(record_until_client_closes, **server_kwargs) as server:
            subscription = _subscription(server, handshake_timeout=0.2, subscribe_timeout=0.2)
            with pytest.raises(SubscriptionError) as refused:
                await subscription.connect()
        return server, subscription, refused.value

    server, subscription, error = asyncio.run(scenario())
    assert message in str(error)
    assert not isinstance(error, SubscriptionClosed)
    assert "test-key" not in str(error)
    assert (server.sockets_opened == 1) is opens_socket
    assert subscription._ws is None and subscription._session is None


def test_iterating_before_connect_is_an_error():
    async def scenario():
        async for _ in PnwSubscription("k", "nation", "update"):
            pass

    with pytest.raises(RuntimeError, match="connect"):
        asyncio.run(scenario())
