#!/usr/bin/env python3
"""Hängt ein Ereignis an das Audit-Log an. Das Log wird nur fortgeschrieben."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory_common import FactoryError, actor_name, append_audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit-Ereignis anhängen")
    parser.add_argument("--event", required=True)
    parser.add_argument("--ticket", default="-")
    parser.add_argument("--role", default="runner")
    parser.add_argument("--from-stack", dest="from_stack", default="")
    parser.add_argument("--to-stack", dest="to_stack", default="")
    parser.add_argument("--message", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    event = {
        "ticket": args.ticket,
        "event": args.event,
        "from": args.from_stack,
        "to": args.to_stack,
        "actor": actor_name(args.role),
        "role": args.role,
        "message": args.message,
        "dry_run": args.dry_run,
    }
    try:
        path = append_audit(event)
    except FactoryError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Audit geschrieben: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
