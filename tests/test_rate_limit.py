"""Tests for the in-process API rate limiter."""
import pytest
from flask import Flask

from api import rate_limit


@pytest.fixture(autouse=True)
def clean_limiter(monkeypatch):
    monkeypatch.setattr(rate_limit, "_hits", {})
    monkeypatch.setattr(rate_limit, "_calls_since_sweep", 0)
    monkeypatch.setattr(rate_limit, "_longest_window", 0.0)


@pytest.fixture
def app():
    return Flask(__name__)


def _acquire(app, remote_addr, **kwargs):
    with app.test_request_context(environ_base={"REMOTE_ADDR": remote_addr}):
        return rate_limit.try_acquire_rate_limit(2, 60, scope="test", **kwargs)


def test_ipv6_addresses_in_one_slash_64_share_a_bucket(app):
    assert _acquire(app, "2001:db8:1:2::1")
    assert _acquire(app, "2001:db8:1:2::ffff")
    assert not _acquire(app, "2001:db8:1:2:abcd::9")
    # A different /64 is a different client.
    assert _acquire(app, "2001:db8:1:3::1")


def test_ipv4_clients_are_still_keyed_per_address(app):
    assert _acquire(app, "203.0.113.5")
    assert _acquire(app, "203.0.113.5")
    assert not _acquire(app, "203.0.113.5")
    assert _acquire(app, "203.0.113.6")


def test_idle_buckets_are_swept(app, monkeypatch):
    monkeypatch.setattr(rate_limit, "_SWEEP_EVERY", 3)
    clock = iter([0.0, 1.0, 1000.0, 1000.5])
    monkeypatch.setattr(rate_limit, "monotonic", lambda: next(clock))

    _acquire(app, "198.51.100.1")
    _acquire(app, "198.51.100.2")
    assert len(rate_limit._hits) == 2

    # Third call triggers a sweep long after both clients went quiet.
    _acquire(app, "198.51.100.3")
    assert set(rate_limit._hits) == {"test:ip:198.51.100.3"}
