#!/usr/bin/env python3
"""End-to-end resident-flow simulator.

Drives the same MCP tool handlers that OpenCLAW would invoke when a real
WhatsApp message arrives. Useful to:
  - smoke-test the skills service without WhatsApp,
  - watch a complaint appear in the admin portal,
  - rehearse classification on a Hindi / Hinglish sample.

Run from inside docker-compose (the `skills` container has the env wired)
or from a host with DATABASE_URL pointing at Postgres:

  python scripts/simulate_inbound.py \
    --jid 9198xxxxxxxx@s.whatsapp.net \
    --name "Rohit Sharma" --tower "Tower B" --flat 1804 \
    --message "kitchen sink leak ho raha hai" \
    --image /path/to/leak.jpg
"""
from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import sys
from pathlib import Path

# allow running from repo root without an install step
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services/skills/src"))

from society_skills import mcp_tools, storage  # noqa: E402


async def _call(name: str, **args):
    return await mcp_tools._HANDLERS[name](args)


async def run(args: argparse.Namespace) -> None:
    storage.ensure_bucket()

    # 1) register / fetch resident
    reg = await _call("register_or_get_resident", wa_jid=args.jid, display_name=args.name)
    print("register_or_get_resident →", json.dumps(reg.model_dump(mode="json"), indent=2))
    rid = reg.resident.id

    # 2) profile (idempotent — fills in anything missing)
    if args.tower and args.flat:
        prof = await _call(
            "update_resident_profile",
            resident_id=str(rid),
            tower_name=args.tower,
            flat_number=args.flat,
            language=args.language,
            status="verified",
        )
        print("update_resident_profile →", json.dumps(prof.model_dump(mode="json"), indent=2))

    # 3) upload any attached media to storage first
    media_payload = []
    if args.image:
        path = Path(args.image)
        mime, _ = mimetypes.guess_type(path.name)
        key = storage.put_bytes(path.read_bytes(), kind="image", mime=mime)
        media_payload.append({"kind": "image", "storage_key": key, "mime": mime})
        print(f"media uploaded → {key}")

    # 4) classify
    cls = await _call(
        "classify_complaint", text=args.message, media_descriptions=args.media_desc or [],
    )
    print("classify_complaint →", json.dumps(cls.model_dump(mode="json"), indent=2))

    # 5) create complaint
    res = await _call(
        "create_complaint",
        resident_id=str(rid),
        category=cls.category,
        severity=cls.severity,
        title=cls.title,
        description=args.message,
        media_storage_keys=media_payload,
        raw_input={"language": args.language, "source": "simulator"},
    )
    print("create_complaint →", json.dumps(res, indent=2, default=str))

    # 6) if critical, escalate
    if cls.severity == "critical":
        esc = await _call(
            "escalate_to_admin",
            complaint_id=res["complaint"]["id"],
            reason=cls.rationale or "auto-classified critical",
        )
        print("escalate_to_admin →", json.dumps(esc, indent=2, default=str))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--jid", required=True, help="WhatsApp JID, e.g. 9198xxxxxxxx@s.whatsapp.net")
    p.add_argument("--name", default=None)
    p.add_argument("--tower", default=None)
    p.add_argument("--flat", default=None)
    p.add_argument("--language", default="en")
    p.add_argument("--message", required=True)
    p.add_argument("--image", default=None, help="Path to an image to attach")
    p.add_argument(
        "--media-desc",
        action="append",
        default=None,
        help="Short text description of attached media (repeatable)",
    )
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
