#!/usr/bin/env python3
"""Fetch the live Politics & War GraphQL schema into ``.ctx/pnwSchema.graphql``.

Requires ``API_KEY`` (or ``PNW_API_KEY``) in the environment.

Usage:
  API_KEY=... PYTHONPATH=. python3 scripts/fetch_pnw_schema.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".ctx" / "pnwSchema.graphql"
ENDPOINT = "https://api.politicsandwar.com/graphql"

# Minimal introspection sufficient to rebuild SDL for WarAttack loot fields.
INTROSPECTION = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    types {
      kind
      name
      description
      fields(includeDeprecated: true) {
        name
        description
        args {
          name
          description
          type { ...TypeRef }
          defaultValue
        }
        type { ...TypeRef }
        isDeprecated
        deprecationReason
      }
      inputFields {
        name
        description
        type { ...TypeRef }
        defaultValue
      }
      interfaces { ...TypeRef }
      enumValues(includeDeprecated: true) {
        name
        description
        isDeprecated
        deprecationReason
      }
      possibleTypes { ...TypeRef }
    }
  }
}

fragment TypeRef on __Type {
  kind
  name
  ofType {
    kind
    name
    ofType {
      kind
      name
      ofType {
        kind
        name
        ofType {
          kind
          name
          ofType {
            kind
            name
            ofType {
              kind
              name
              ofType { kind name }
            }
          }
        }
      }
    }
  }
}
"""


def _type_to_sdl(t: dict | None) -> str:
    if not t:
        return "Unknown"
    kind = t.get("kind")
    name = t.get("name")
    of_type = t.get("ofType")
    if kind == "NON_NULL":
        return f"{_type_to_sdl(of_type)}!"
    if kind == "LIST":
        return f"[{_type_to_sdl(of_type)}]"
    return name or "Unknown"


def schema_to_approximate_sdl(schema: dict) -> str:
    """Render a readable GraphQL SDL approximation from introspection JSON."""
    lines: list[str] = []
    types = schema.get("__schema", {}).get("types") or []
    for t in sorted(types, key=lambda x: x.get("name") or ""):
        name = t.get("name") or ""
        if name.startswith("__"):
            continue
        kind = t.get("kind")
        desc = (t.get("description") or "").strip()
        if desc:
            for dline in desc.splitlines():
                lines.append(f"# {dline}")
        if kind == "ENUM":
            lines.append(f"enum {name} {{")
            for ev in t.get("enumValues") or []:
                extra = ""
                if ev.get("isDeprecated"):
                    reason = (ev.get("deprecationReason") or "").replace('"', '\\"')
                    extra = f' @deprecated(reason: "{reason}")'
                lines.append(f"  {ev['name']}{extra}")
            lines.append("}")
            lines.append("")
            continue
        if kind not in ("OBJECT", "INPUT_OBJECT", "INTERFACE"):
            continue
        keyword = {
            "OBJECT": "type",
            "INPUT_OBJECT": "input",
            "INTERFACE": "interface",
        }[kind]
        lines.append(f"{keyword} {name} {{")
        fields = t.get("fields") or t.get("inputFields") or []
        for field in fields:
            fdesc = (field.get("description") or "").strip()
            if fdesc:
                for dline in fdesc.splitlines():
                    lines.append(f"  # {dline}")
            args = field.get("args") or []
            arg_sdl = ""
            if args:
                parts = []
                for arg in args:
                    part = f"{arg['name']}: {_type_to_sdl(arg.get('type'))}"
                    if arg.get("defaultValue") is not None:
                        part += f" = {arg['defaultValue']}"
                    parts.append(part)
                arg_sdl = "(" + ", ".join(parts) + ")"
            deprecated = ""
            if field.get("isDeprecated"):
                reason = (field.get("deprecationReason") or "").replace('"', '\\"')
                deprecated = f' @deprecated(reason: "{reason}")'
            lines.append(
                f"  {field['name']}{arg_sdl}: {_type_to_sdl(field.get('type'))}{deprecated}"
            )
        lines.append("}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    api_key = (os.getenv("API_KEY") or os.getenv("PNW_API_KEY") or "").strip()
    if not api_key:
        print("API_KEY (or PNW_API_KEY) is required", file=sys.stderr)
        return 1

    url = f"{ENDPOINT}?api_key={api_key}"
    response = requests.post(url, json={"query": INTROSPECTION}, timeout=60)
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        print(payload["errors"], file=sys.stderr)
        return 1

    data = payload.get("data") or {}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Keep raw introspection alongside SDL for tooling.
    raw_path = OUT.with_suffix(".introspection.json")
    raw_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    OUT.write_text(schema_to_approximate_sdl(data), encoding="utf-8")

    # Highlight loot-related fields for quick verification.
    war_attack = next(
        (
            t
            for t in (data.get("__schema", {}).get("types") or [])
            if t.get("name") == "WarAttack"
        ),
        None,
    )
    if war_attack:
        names = sorted(f["name"] for f in (war_attack.get("fields") or []))
        lootish = [n for n in names if "loot" in n.lower() or n in {"type", "victor", "moneystolen"}]
        print("WarAttack loot-related fields:", ", ".join(lootish))
    print(f"Wrote {OUT}")
    print(f"Wrote {raw_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
