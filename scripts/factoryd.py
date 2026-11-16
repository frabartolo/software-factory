#!/usr/bin/env python3
"""Factory-Runner. Liest Ready-Tickets, prüft sie und schreibt Bericht plus Audit.

Im Bootstrap wird kein Modell aufgerufen und keine Karte nach Done oder Approved geschoben.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory_common import (
    FactoryError,
    PolicyError,
    actor_name,
    append_audit,
    check_transition,
    ensure_runtime_dirs,
    factory_config,
    load_credentials,
    stack_name,
)
from run_job import plan_job, print_plan, write_report
from validate_ticket import parse_ticket, resolve_ticket_path, validate_path


def local_ready_tickets() -> list[Path]:
    directory = root_ready()
    return sorted(path for path in directory.glob("*.md") if path.is_file())


def root_ready() -> Path:
    from factory_common import root

    return root() / "tickets" / "ready"


def audit(event: str, ticket: str, source: str, target: str, message: str, *, dry_run: bool) -> None:
    append_audit(
        {
            "ticket": ticket,
            "event": event,
            "from": source,
            "to": target,
            "actor": actor_name("runner"),
            "role": "runner",
            "message": message,
            "dry_run": dry_run,
        }
    )


@dataclass
class WorkItem:
    text: str
    origin: str
    path: Path | None = None
    card: dict[str, Any] | None = None


def collect_items(explicit: str | None, *, local_only: bool) -> tuple[list[WorkItem], str]:
    if explicit:
        path = resolve_ticket_path(explicit)
        return [WorkItem(path.read_text(encoding="utf-8"), str(path), path)], "datei"
    credentials = None if local_only else load_credentials()
    if credentials is not None:
        from deck import DeckClient

        board_id = int(factory_config()["board"]["id"])
        deck = DeckClient(credentials, board_id)
        items = [
            WorkItem(str(card.get("description") or ""), f"deck:{card.get('id')}", card=card)
            for card in deck.cards(stack_name("ready"))
        ]
        return items, "deck"
    paths = local_ready_tickets()
    return [WorkItem(path.read_text(encoding="utf-8"), str(path), path) for path in paths], "lokal"


def run_once(*, dry_run: bool, ticket: str | None, apply_deck: bool, local_only: bool = False) -> int:
    ensure_runtime_dirs()
    ready = stack_name("ready")
    running = stack_name("running")
    waiting = stack_name("waiting_review")
    blocked = stack_name("blocked")
    depth = int(factory_config()["limits"]["queue_depth"])
    items, source = collect_items(ticket, local_only=local_only)
    print(f"Quelle: {source}")
    if not items:
        print("Keine Tickets in Ready.")
        audit("queue_empty", "-", ready, ready, f"Keine Ready-Tickets ({source})", dry_run=dry_run)
        return 0

    selected = items[:depth]
    if len(items) > depth:
        print(f"Queue-Depth {depth}: {len(selected)} von {len(items)} Tickets ausgewählt")

    if source != "deck":
        print("Deck wird in diesem Lauf nicht beschrieben.")
    elif dry_run or not apply_deck:
        print("Deck wird gelesen. Karten bleiben liegen.")
    else:
        print("Ungültige Karten können nach Blocked / Failed. Gültige Karten bleiben in Ready / Bereit.")

    failures = 0
    for item in selected:
        parsed, errors = parse_ticket(item.text, item.path)
        if not parsed.repo:
            errors.append("Frontmatter-Feld repo fehlt")
        if errors:
            failures += 1
            message = "; ".join(errors)
            print(f"Abgelehnt {parsed.ticket_id}: {message}")
            check_transition("runner", ready, blocked)
            moved = False
            if source == "deck" and apply_deck and not dry_run and item.card is not None:
                from deck import DeckClient

                credentials = load_credentials()
                if credentials is None:
                    raise FactoryError("Deck-Zugangsdaten sind während des Laufs verschwunden")
                DeckClient(credentials, int(factory_config()["board"]["id"])).move_card(
                    item.card, blocked
                )
                moved = True
            audit(
                "validation_failed",
                parsed.ticket_id,
                ready,
                blocked,
                message,
                dry_run=not moved,
            )
            continue

        check_transition("runner", ready, running)
        check_transition("runner", running, waiting)
        plan = plan_job(parsed, dry_run=dry_run)
        print(f"Herkunft: {item.origin}")
        print_plan(plan)
        report = write_report(plan, reason="dry-run" if dry_run else "bootstrap ohne Worker")
        print(f"  Report: {report}")
        if source == "deck" and apply_deck and not dry_run:
            print("  Karte bleibt in Ready. Der Worker ist im Bootstrap aus.")
        audit(
            "transition_simulated",
            parsed.ticket_id,
            ready,
            running,
            "Ticket angenommen",
            dry_run=True,
        )
        audit(
            "transition_simulated",
            parsed.ticket_id,
            running,
            waiting,
            f"Bericht geschrieben: {report.name}",
            dry_run=True,
        )
    return 1 if failures and ticket else 0


def self_check() -> int:
    sample = "tickets/sample/FACT-EXAMPLE-control.md"
    invalid = "tickets/sample/INVALID_MISSING_ACCEPTANCE.md"
    checks: list[tuple[str, bool]] = []

    good, good_errors = validate_path(resolve_ticket_path(sample))
    checks.append(("Sample-Ticket akzeptiert", not good_errors and good.ticket_id == "FACT-EXAMPLE"))

    bad, bad_errors = validate_path(resolve_ticket_path(invalid))
    checks.append(
        (
            "Ticket ohne Akzeptanzbeispiele abgelehnt",
            bool(bad_errors) and any("Acceptance examples" in error for error in bad_errors),
        )
    )

    empty_code = run_once(dry_run=True, ticket=None, apply_deck=False, local_only=True)
    checks.append(("Leere Ready-Queue endet mit Status 0", empty_code == 0))

    sample_code = run_once(dry_run=True, ticket=sample, apply_deck=False, local_only=True)
    checks.append(("Dry-run des Sample-Tickets endet mit Status 0", sample_code == 0))

    from factory_common import audit_path, root

    audit_text = audit_path().read_text(encoding="utf-8") if audit_path().exists() else ""
    checks.append(("Audit enthält das Sample-Ticket", "FACT-EXAMPLE" in audit_text))
    checks.append(("Audit enthält die leere Queue", "queue_empty" in audit_text))
    reports = list((root() / "reports").glob("FACT-EXAMPLE-*.json"))
    checks.append(("Dry-run schreibt einen Report", len(reports) >= 1))

    blocked_runner = False
    try:
        check_transition("runner", stack_name("waiting_review"), stack_name("done"))
    except PolicyError:
        blocked_runner = True
    checks.append(("Runner darf Waiting Review nicht nach Done setzen", blocked_runner))

    blocked_approve = False
    try:
        check_transition("runner", stack_name("waiting_review"), stack_name("approved"))
    except PolicyError:
        blocked_approve = True
    checks.append(("Runner darf nicht freigeben", blocked_approve))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(("OK  " if ok else "FEHL ") + name)
    if failed:
        return 1
    print("Self-check bestanden")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Factory-Runner")
    parser.add_argument("--once", action="store_true", help="einen Durchlauf ausführen")
    parser.add_argument("--loop", action="store_true", help="wiederholt pollen")
    parser.add_argument("--interval", type=int, default=None, help="Sekunden zwischen Durchläufen")
    parser.add_argument("--dry-run", action="store_true", help="nur planen, nichts am Board ändern")
    parser.add_argument("--ticket", help="eine konkrete Ticketdatei statt der Ready-Queue")
    parser.add_argument(
        "--apply-deck",
        action="store_true",
        help="ungültige Ready-Karten nach Blocked / Failed schieben",
    )
    parser.add_argument("--self-check", action="store_true", help="Bootstrap-Prüfungen ausführen")
    args = parser.parse_args(argv)

    if args.self_check:
        try:
            return self_check()
        except (FactoryError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return 1

    once = args.once or not args.loop
    interval = args.interval
    if interval is None:
        interval = int(factory_config()["limits"]["poll_seconds"])
    if interval < 1:
        print("Intervall muss mindestens 1 Sekunde sein", file=sys.stderr)
        return 2

    try:
        while True:
            code = run_once(dry_run=args.dry_run, ticket=args.ticket, apply_deck=args.apply_deck)
            if once:
                return code
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Runner beendet")
        return 0
    except (FactoryError, PolicyError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
