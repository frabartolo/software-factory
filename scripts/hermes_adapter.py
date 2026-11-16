#!/usr/bin/env python3
"""Hermes-Adapter ohne Discord: Spec-Prüfung, Ready-Regel und Gate.

Der bestehende Agent KIara auf kiara bleibt der Gesprächskanal.
Dieses Skript erzwingt die Factory-Regeln, bevor eine Karte bewegt wird.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory_common import (
    FactoryError,
    PolicyError,
    actor_name,
    append_audit,
    check_named_approver,
    check_transition,
    stack_name,
)
from validate_ticket import parse_ticket, resolve_ticket_path, validate_path


def decide_ready(text: str) -> tuple[str, list[str]]:
    ticket, errors = parse_ticket(text)
    if errors or not ticket.repo:
        if not ticket.repo:
            errors.append("Frontmatter-Feld repo fehlt")
        return ticket.ticket_id, errors
    check_transition("hermes", stack_name("backlog"), stack_name("ready"))
    return ticket.ticket_id, []


def approve(ticket_id: str, approver: str | None, *, source: str | None = None) -> str:
    origin = source or stack_name("waiting_review")
    try:
        name = check_named_approver("hermes", approver)
    except PolicyError as exc:
        append_audit(
            {
                "ticket": ticket_id,
                "event": "approval_violation",
                "from": origin,
                "to": stack_name("approved"),
                "actor": actor_name("hermes"),
                "role": "hermes",
                "message": str(exc),
                "dry_run": True,
            }
        )
        raise
    check_transition("hermes", origin, stack_name("approved"))
    append_audit(
        {
            "ticket": ticket_id,
            "event": "gate_approved",
            "from": origin,
            "to": stack_name("approved"),
            "actor": actor_name("hermes"),
            "role": "hermes",
            "message": "Menschliche Freigabe übernommen",
            "human_approver": name,
            "approval_channel": "adapter",
            "dry_run": True,
        }
    )
    return name


def reject_done(source: str) -> None:
    check_transition("hermes", source, stack_name("done"))


def test_intake() -> int:
    incomplete = "## Goal\n\nNur ein Ziel, sonst nichts.\n"
    ticket_id, errors = decide_ready(incomplete)
    if not errors:
        print("Unvollständige Spec wurde fälschlich akzeptiert", file=sys.stderr)
        return 1
    print(f"Unvollständige Spec bleibt zurück: {ticket_id} ({len(errors)} Fehler)")

    sample, sample_errors = validate_path(resolve_ticket_path("tickets/sample/FACT-EXAMPLE-control.md"))
    if sample_errors:
        print("Sample-Ticket ist nicht vollständig", file=sys.stderr)
        return 1
    ready_id, ready_errors = decide_ready(sample.body)
    if ready_errors:
        print(f"Vollständige Spec wurde abgelehnt: {ready_errors}", file=sys.stderr)
        return 1
    print(f"Vollständige Spec darf nach Ready: {ready_id}")
    return 0


def test_gate_reject() -> int:
    try:
        approve("FACT-001", None)
    except PolicyError as exc:
        print(f"Freigabe ohne Namen abgelehnt: {exc}")
    else:
        print("Freigabe ohne Namen wurde akzeptiert", file=sys.stderr)
        return 1

    try:
        reject_done(stack_name("waiting_review"))
    except PolicyError as exc:
        print(f"Done aus Waiting Review abgelehnt: {exc}")
    else:
        print("Done wurde erlaubt", file=sys.stderr)
        return 1

    name = approve("FACT-001", "Andreas")
    print(f"Freigabe mit Namen vorgemerkt: {name}")
    try:
        reject_done(stack_name("approved"))
    except PolicyError as exc:
        print(f"Done bleibt auch nach Approved gesperrt: {exc}")
    else:
        print("Done nach Approved wurde erlaubt", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hermes-Factory-Adapter")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("test-intake", "test-gate-reject"),
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "test-intake":
            return test_intake()
        if args.command == "test-gate-reject":
            return test_gate_reject()
        append_audit(
            {
                "ticket": "-",
                "event": "hermes_adapter_dry_run",
                "from": "",
                "to": "",
                "actor": actor_name("hermes"),
                "role": "hermes",
                "message": "Adapter geprüft, Discord bleibt bei KIara auf kiara",
                "dry_run": True,
            }
        )
        print("Hermes-Adapter dry-run")
        print("Befehle später: /ticket /clarify /ready /status /approve /reject /report")
        print("Ready nur bei vollständiger Spec. Approved nur mit approver=<name>. Done bleibt zu.")
        return 0
    except (FactoryError, PolicyError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
