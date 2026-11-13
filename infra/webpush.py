"""Browser push delivery (Web Push with VAPID).

The private key comes from ``VAPID_PRIVATE_KEY`` (base64url raw 32-byte key or DER).
The public key browsers subscribe with is derived from it, so the two can't drift
apart. Push is disabled when the key or ``VAPID_SUBJECT`` is missing.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Optional
from urllib.parse import urlsplit

import aiohttp
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from py_vapid import Vapid, VapidException
from pywebpush import WebPushException, WebPusher

logger = logging.getLogger(__name__)

# Apple asks senders to refresh the signing token at most hourly; tokens may live 24 h.
_AUTH_REFRESH_SECONDS = 3600
_TOKEN_LIFETIME_SECONDS = 12 * 3600
DECLARATIVE_PUSH_MAGIC = 8030


class PushOutcome(str, Enum):
    """Result of one push attempt."""

    DELIVERED = "delivered"
    GONE = "gone"  # Subscription expired or was revoked: delete it.
    RETRY = "retry"  # Rate limited, push service trouble or network error.
    FAILED = "failed"  # Rejected (bad request, key mismatch, payload too large).


@dataclass(frozen=True)
class PushResult:
    """Outcome plus the HTTP status when there was one."""

    outcome: PushOutcome
    status: Optional[int] = None
    detail: str = ""


def classify_push_status(status: int) -> PushOutcome:
    """Map a push service HTTP status to an outcome."""
    if 200 <= status < 300:
        return PushOutcome.DELIVERED
    if status in (404, 410):
        return PushOutcome.GONE
    if status == 429 or status >= 500:
        return PushOutcome.RETRY
    return PushOutcome.FAILED


def _exception_result(exc: Exception) -> PushResult:
    """Outcome for an error raised while building or sending a message.

    Only a problem with the stored subscription (missing keys, keys that don't decode
    or aren't a valid point) means it can never work and should be deleted. Signing
    trouble, unreadable responses and programming errors are failures, so the device
    is kept.
    """
    if isinstance(exc, WebPushException) or (isinstance(exc, ValueError) and not isinstance(exc, UnicodeError)):
        return PushResult(PushOutcome.GONE, None, type(exc).__name__)
    return PushResult(PushOutcome.FAILED, None, type(exc).__name__)


# Errors handled per message; anything else is left to the caller.
_MESSAGE_ERRORS = (WebPushException, ValueError, VapidException, TypeError, KeyError)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def public_key_for(vapid: Vapid) -> str:
    """The applicationServerKey browsers subscribe with (base64url, uncompressed point)."""
    raw = vapid.public_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return _b64url(raw)


def key_id_for(public_key: str) -> str:
    """Short fingerprint of a public key, used to spot subscriptions made with an old key."""
    return hashlib.sha256(public_key.encode("ascii")).hexdigest()[:16]


def generate_vapid_keys() -> tuple[str, str]:
    """Create a new key pair.

    Returns:
        ``(private_key, public_key)`` as base64url strings; put the private key in
        ``VAPID_PRIVATE_KEY``.
    """
    key = ec.generate_private_key(ec.SECP256R1())
    private_raw = key.private_numbers().private_value.to_bytes(32, "big")
    return _b64url(private_raw), public_key_for(Vapid(key))


def notification_payload(
    *,
    title: str,
    body: str,
    navigate: str,
    tag: str,
    kind: str,
    timestamp: datetime,
    nation_id: Optional[str] = None,
    require_interaction: bool = True,
) -> dict[str, Any]:
    """Build a Declarative Web Push payload that the site's service worker also reads."""
    return {
        "web_push": DECLARATIVE_PUSH_MAGIC,
        "notification": {
            "title": title,
            "body": body,
            "navigate": navigate,
            "tag": tag,
            "timestamp": int(timestamp.timestamp() * 1000),
            "requireInteraction": require_interaction,
            "lang": "en",
            "dir": "ltr",
        },
        "autolycus": {"kind": kind, "nationId": nation_id},
    }


class WebPushSender:
    """Signs and sends encrypted push messages to browser push services."""

    def __init__(self, private_key: str, subject: str) -> None:
        """Load the VAPID key.

        Args:
            private_key: base64url raw or DER private key.
            subject: ``mailto:`` or ``https:`` contact URI required by push services.

        Raises:
            ValueError: If the subject isn't a mailto:/https: URI.
            Exception: If the key can't be parsed or py_vapid rejects the subject
                (for example a trailing slash or path after the https host).
        """
        if not subject.startswith(("mailto:", "https://")):
            raise ValueError("VAPID_SUBJECT must be a mailto: or https:// URI")
        self._vapid = Vapid.from_string(private_key=private_key)
        self.subject = subject
        self.public_key = public_key_for(self._vapid)
        self.key_id = key_id_for(self.public_key)
        self._auth_cache: dict[str, tuple[float, dict[str, str]]] = {}
        # Sign once now: py_vapid checks the subject only when signing, and a subject it
        # rejects would otherwise fail every send while push looks configured.
        self.auth_headers("https://fcm.googleapis.com/")
        self._auth_cache.clear()

    def auth_headers(self, endpoint: str) -> dict[str, str]:
        """VAPID headers for a push service origin, cached for an hour."""
        parts = urlsplit(endpoint)
        audience = f"{parts.scheme}://{parts.netloc}"
        now = time.time()
        cached = self._auth_cache.get(audience)
        if cached is None or now - cached[0] >= _AUTH_REFRESH_SECONDS:
            headers = self._vapid.sign(
                {"sub": self.subject, "aud": audience, "exp": int(now) + _TOKEN_LIFETIME_SECONDS}
            )
            cached = (now, dict(headers))
            self._auth_cache[audience] = cached
        return dict(cached[1])

    def _headers(self, endpoint: str, topic: Optional[str], urgency: str) -> dict[str, str]:
        headers = {"Urgency": urgency, **self.auth_headers(endpoint)}
        if topic:
            headers["Topic"] = topic
        return headers

    async def send(
        self,
        session: aiohttp.ClientSession,
        subscription: Mapping[str, Any],
        payload: Mapping[str, Any],
        *,
        ttl: int,
        topic: Optional[str] = None,
        urgency: str = "high",
        timeout_seconds: float = 10.0,
    ) -> PushResult:
        """Send one push message without blocking the event loop.

        Args:
            session: Shared aiohttp session.
            subscription: ``{"endpoint": ..., "keys": {"p256dh": ..., "auth": ...}}``.
            payload: JSON-serialisable message.
            ttl: Seconds the push service may hold the message.
            topic: Replaces an undelivered message with the same topic.
            urgency: ``very-low``, ``low``, ``normal`` or ``high``.
            timeout_seconds: Request timeout.

        Returns:
            The outcome; exceptions are converted into outcomes.
        """
        endpoint = str(subscription.get("endpoint") or "")
        data = json.dumps(payload, separators=(",", ":"))
        try:
            pusher = WebPusher(
                {"endpoint": endpoint, "keys": dict(subscription.get("keys") or {})},
                aiohttp_session=session,
            )
            response = await pusher.send_async(
                data,
                self._headers(endpoint, topic, urgency),
                ttl=max(1, int(ttl)),
                timeout=aiohttp.ClientTimeout(total=timeout_seconds),
            )
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            return PushResult(PushOutcome.RETRY, None, type(exc).__name__)
        except _MESSAGE_ERRORS as exc:
            return _exception_result(exc)
        status = int(response.status)
        return PushResult(classify_push_status(status), status)

    def send_sync(
        self,
        subscription: Mapping[str, Any],
        payload: Mapping[str, Any],
        *,
        ttl: int,
        topic: Optional[str] = None,
        urgency: str = "normal",
        timeout_seconds: float = 10.0,
    ) -> PushResult:
        """Blocking variant of :meth:`send` for the API process."""
        endpoint = str(subscription.get("endpoint") or "")
        data = json.dumps(payload, separators=(",", ":"))
        try:
            response = WebPusher(
                {"endpoint": endpoint, "keys": dict(subscription.get("keys") or {})}
            ).send(
                data,
                self._headers(endpoint, topic, urgency),
                ttl=max(1, int(ttl)),
                timeout=timeout_seconds,
            )
        except requests.RequestException as exc:
            return PushResult(PushOutcome.RETRY, None, type(exc).__name__)
        except _MESSAGE_ERRORS as exc:
            return _exception_result(exc)
        status = int(response.status_code)
        return PushResult(classify_push_status(status), status)


_sender: Optional[WebPushSender] = None
_sender_loaded = False
_sender_lock = threading.Lock()


def get_push_sender() -> Optional[WebPushSender]:
    """Shared sender built from configuration, or None when push isn't configured."""
    global _sender, _sender_loaded
    if _sender_loaded:
        return _sender
    with _sender_lock:  # API request threads may ask at the same time on startup.
        if not _sender_loaded:
            _sender = _build_sender()
            _sender_loaded = True
    return _sender


def _build_sender() -> Optional[WebPushSender]:
    from core.config import VAPID_PRIVATE_KEY, VAPID_SUBJECT

    if not VAPID_PRIVATE_KEY or not VAPID_SUBJECT:
        logger.info("Browser push disabled: VAPID_PRIVATE_KEY or VAPID_SUBJECT is not set")
        return None
    try:
        return WebPushSender(VAPID_PRIVATE_KEY, VAPID_SUBJECT)
    except Exception as exc:  # noqa: BLE001 - misconfiguration must not stop the app
        logger.error("Browser push disabled: could not load VAPID settings (%s)", exc)
        return None
