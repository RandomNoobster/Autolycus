"""Print a new VAPID key for browser push notifications.

Usage:
    uv run python scripts/generate_vapid_keys.py

Copy the printed lines into ``.env``. The public key browsers need is derived from
the private key at runtime. Replacing the key turns browser notifications off on
every device until users turn them on again.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from infra.webpush import generate_vapid_keys  # noqa: E402


def main() -> None:
    private_key, public_key = generate_vapid_keys()
    print("# Browser push notifications. Keep VAPID_PRIVATE_KEY secret.")
    print(f"VAPID_PRIVATE_KEY={private_key}")
    print("VAPID_SUBJECT=mailto:you@example.com")
    print(f"# Public key (derived automatically; shown for reference): {public_key}")


if __name__ == "__main__":
    main()
