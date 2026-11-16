#!/usr/bin/env python3
"""Prüft eine Backlog-Karte und schiebt sie bei Bestand nach Ready.

Der Prüfer arbeitet mit der Hermes-Rolle. Der Runner darf diesen Übergang nicht.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deck import client_or_exit
from factory_common import (
    FactoryError,
    PolicyError,
    actor_name,
    append_audit,
    check_transition,
    stack_name,
)
from validate_ticket import Ticket, parse_ticket

QUEUE_WORDS = ("queue", "warteschlange", "runner", "datei-queue", "dateiqueue", "ready")
SUCCESS_BLOCKERS = (
    "git push",
    "git merge",
    "auto-merge",
    "automatisch mergen",
    "nach done",
    "auf done setzen",
    "status done",
)
RUNNER_ALREADY = (
    "factoryd.py liest tickets/ready und bei Zugangsdaten die Deck-Liste Ready",
    "queue_depth begrenzt die Auswahl",
    "ein Dry-Run schreibt Report und Audit und lässt die Karte liegen",
)
RUNNER_STILL_OPEN = (
    "die Karte wird auf dem Board noch nicht nach Running gesetzt",
    "ein Worker wird nicht gestartet",
)


def promotion_blockers(ticket: Ticket, title: str) -> list[str]:
    blockers: list[str] = []
    parsed, errors = parse_ticket(ticket.body)
    blockers.extend(errors)
    if not parsed.repo and not re.search(r"(?im)^repo:\s*\S+", ticket.body):
        blockers.append("Frontmatter-Feld repo fehlt")
    haystack = " ".join(
        (
            title,
            ticket.sections.get("Goal", ""),
            ticket.sections.get("Success criteria", ""),
        )
    ).lower()
    if not any(word in haystack for word in QUEUE_WORDS):
        blockers.append("Ziel beschreibt keine Runner- oder Queue-Arbeit")
    success = ticket.sections.get("Success criteria", "").lower()
    for phrase in SUCCESS_BLOCKERS:
        if phrase in success:
            blockers.append(f"Erfolgskriterium verlangt „{phrase}“")
    return blockers


def locate_card(deck: Any, fact_id: str) -> tuple[dict[str, Any], str] | None:
    pattern = re.compile(rf"\b{re.escape(fact_id)}\b")
    for stack in deck.stacks():
        title = str(stack.get("title") or "")
        for card in stack.get("cards") or []:
            card_title = str(card.get("title") or "")
            if pattern.search(card_title):
                card.setdefault("stackId", stack.get("id"))
                return card, title
    return None


def review_fact(fact_id: str, *, dry_run: bool) -> int:
    if fact_id != "FACT-002":
        print("Dieser Prüfer entscheidet nur über FACT-002.", file=sys.stderr)
        return 2
    deck = client_or_exit()
    found = locate_card(deck, fact_id)
    if found is None:
        print(f"{fact_id} liegt auf Board 7 nicht.", file=sys.stderr)
        return 1
    card, source = found
    title = str(card.get("title") or "")
    ready = stack_name("ready")
    backlog = stack_name("backlog")
    print(f"{fact_id} Karte {card.get('id')}")
    print(f"Titel: {title}")
    print(f"Liste: {source}")
    for line in RUNNER_ALREADY:
        print(f"Ist-Stand: {line}")
    for line in RUNNER_STILL_OPEN:
        print(f"Offen: {line}")

    if source == ready:
        print("Entscheidung: liegt schon in Ready.")
        return 0
    if source != backlog:
        print(f"Entscheidung: bleibt in „{source}“. Nur {backlog} wird nach Ready geprüft.")
        return 1

    description = str(card.get("description") or "")
    ticket, _errors = parse_ticket(description)
    blockers = promotion_blockers(ticket, title)
    if blockers:
        print("Entscheidung: bleibt im Backlog.")
        for blocker in blockers:
            print(f"- {blocker}")
        append_audit(
            {
                "ticket": fact_id,
                "event": "ready_rejected",
                "from": source,
                "to": ready,
                "actor": actor_name("hermes"),
                "role": "hermes",
                "message": "; ".join(blockers),
                "card_id": card.get("id"),
                "dry_run": dry_run,
            }
        )
        return 1

    check_transition("hermes", source, ready)
    if dry_run:
        print(f"Entscheidung: würde nach „{ready}“ schieben.")
        return 0
    deck.move_card(card, ready)
    append_audit(
        {
            "ticket": fact_id,
            "event": "promoted_ready",
            "from": source,
            "to": ready,
            "actor": actor_name("hermes"),
            "role": "hermes",
            "message": "Prüfer hat FACT-002 nach Ready geschoben",
            "card_id": card.get("id"),
            "dry_run": False,
        }
    )
    print(f"Entscheidung: nach „{ready}“ verschoben.")
    return 0


def self_test() -> int:
    good = """---
id: FACT-002
title: Runner-MVP
repo: factory
---

## Goal

Der Runner liest die Datei-Queue und die Ready-Liste.

## Success criteria

- Höchstens queue_depth Tickets werden gewählt.
- Ein Dry-run verändert das Board nicht.

## Acceptance examples

1. Normalfall:
   Eine gültige Karte wird geplant.
2. Grenzfall:
   Eine leere Queue endet ohne Fehler.
3. Fehlerfall:
   Eine Karte ohne Repo bleibt liegen.

## Forbidden

- No merge
- No push
- No Done

## Checks

- python3 scripts/factoryd.py --once --dry-run

## Budget

max_walltime: 25m
max_turns: 12
max_files: 8
"""
    good_ticket, _ = parse_ticket(good)
    good_blockers = promotion_blockers(good_ticket, "FACT-002 — Runner-MVP")
    bad = good.replace("## Success criteria\n\n- Höchstens queue_depth Tickets werden gewählt.\n- Ein Dry-run verändert das Board nicht.", "## Success criteria\n\n- Der Runner führt git push aus.")
    bad_ticket, _ = parse_ticket(bad)
    bad_blockers = promotion_blockers(bad_ticket, "FACT-002 — Runner-MVP")
    ok = not good_blockers and any("git push" in item for item in bad_blockers)
    print("OK  gültige FACT-002-Spec hat keine Blocker" if not good_blockers else f"FEHL {good_blockers}")
    print("OK  git push im Erfolg blockiert" if any("git push" in item for item in bad_blockers) else f"FEHL {bad_blockers}")
    if not ok:
        return 1
    print("Self-check bestanden")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prüft FACT-002 und schiebt sie nach Ready")
    parser.add_argument("ticket", nargs="?", default="FACT-002")
    parser.add_argument("--dry-run", action="store_true", help="nur prüfen, die Karte nicht verschieben")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.self_test:
            return self_test()
        return review_fact(args.ticket.upper(), dry_run=args.dry_run)
    except (FactoryError, PolicyError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
