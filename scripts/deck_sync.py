#!/usr/bin/env python3
"""Adapter: liest Karten aus dem „Ready"-Stack des Nextcloud-Deck-Boards
„Software Factory" und materialisiert sie als Markdown-Tickets in tickets/new.

Verbindet sich über den bestehenden DeckClient (scripts/deck.py) mit der
Nextcloud-Deck-API. Zugangsdaten kommen aus der Factory-Env (NC_BASE /
NC_USER / NC_APP_PASSWORD in /etc/factory/runner.env).

Usage:
    python3 deck_sync.py --once --dry-run
    python3 deck_sync.py --once

Verhalten:
  * Duplikatsschutz über tickets/.imported.json (gesammelte Card-IDs).
  * --dry-run: nur anzeigen, was importiert würde; schreibt nichts.
  * Klare Fehlermeldung + exit 1, wenn die Deck-API unerreichbar ist.
  * exit 0, wenn alles funktioniert (auch „keine Karten").
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# DeckClient & factory-common importieren (sitzt unter scripts/).
# Funktioniert unabhängig vom Startpfad (work/FACT-009/ oder scripts/):
def _scripts_dir():
    start = Path(__file__).resolve().parent
    for parent in [start, *start.parents]:
        for sub in (parent / "scripts", parent):
            if (sub / "factory_common.py").exists():
                return sub
    raise RuntimeError("factory_common.py / scripts-Verzeichnis nicht gefunden")


_SCRIPTS_DIR = _scripts_dir()
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from factory_common import FactoryError, factory_config, load_credentials  # noqa: E402
from deck import DeckClient  # noqa: E402

BOARD_NAME = "Software Factory"
STACK_TITLE = "Ready / Bereit"
TICKETS_DIR = "tickets/new"
IMPORTED_FILE = os.path.join("tickets", ".imported.json")

# Test-Hook: callable -> Deck-Objekt. None = echtes Deck (DeckClient).
_deck = None


def deck():
    """Deck-Objekt liefern. In Tests wird _deck auf einen Mock gesetzt."""
    if _deck is not None:
        return _deck()
    credentials = load_credentials()
    if credentials is None:
        raise ConnectionError(
            "Keine Nextcloud-Zugangsdaten gefunden. Lege /etc/factory/runner.env "
            "mit NC_BASE, NC_USER und NC_APP_PASSWORD an."
        )
    board_id = int(factory_config()["board"]["id"])
    return DeckClient(credentials, board_id)


def load_state():
    if os.path.exists(IMPORTED_FILE):
        try:
            with open(IMPORTED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("card_ids", [])
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_state(card_ids):
    os.makedirs(os.path.dirname(IMPORTED_FILE), exist_ok=True)
    with open(IMPORTED_FILE, "w", encoding="utf-8") as f:
        json.dump({"card_ids": card_ids}, f, indent=2)


def normalize_filename(title):
    stem = (title or "").lower().strip()
    stem = re.sub(r"[^a-z0-9_\-]", "-", stem)
    stem = re.sub(r"-{2,}", "-", stem)
    stem = stem.strip("-")
    return stem if stem else "untitled"


def create_ticket_file(card_id, title, description, dry_run):
    os.makedirs(TICKETS_DIR, exist_ok=True)
    filename = normalize_filename(title) + ".md"
    filepath = os.path.join(TICKETS_DIR, filename)
    content = (
        "# %s\n\n%s\n\n---\n"
        "Card ID: %s\nBoard: %s\nStack: %s\nImported: %s\n"
    ) % (
        title, description, card_id, BOARD_NAME, STACK_TITLE,
        datetime.now().isoformat()
    )
    if dry_run:
        print("[DRY-RUN] Would create: %s" % filepath)
        print("[DRY-RUN]   Title: %s" % title)
        print("[DRY-RUN]   Card ID: %s" % card_id)
        return filepath
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print("[OK] Created: %s" % filepath)
    return filepath


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        description="Sync Nextcloud Deck cards (Stack Ready) to local tickets."
    )
    parser.add_argument("--once", action="store_true", help="Run a single sync cycle.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only print what would be imported; write nothing.")
    args = parser.parse_args(argv)

    if not args.once:
        parser.error("Must specify --once")

    print("Deck Sync: board='%s', stack='%s'" % (BOARD_NAME, STACK_TITLE))
    print("Mode: %s" % ("DRY-RUN" if args.dry_run else "LIVE"))
    print()

    try:
        cards = deck().cards(STACK_TITLE)
    except (ConnectionError, OSError, FactoryError) as e:
        print("[ERROR] %s" % e, file=sys.stderr)
        return 1

    if not cards:
        print("[INFO] No cards found in the specified stack.")
        return 0

    imported_ids = load_state()
    imported_count = 0
    skipped_count = 0

    for card in cards:
        card_id = int(card.get("id", 0))
        title = card.get("title", "Untitled") or "Untitled"
        description = card.get("description") or ""

        if card_id in imported_ids:
            print("[SKIP] Card %s (%s) already imported." % (card_id, title))
            skipped_count += 1
            continue

        create_ticket_file(card_id, title, description, args.dry_run)
        imported_ids.append(card_id)
        imported_count += 1

    if not args.dry_run:
        save_state(imported_ids)

    print()
    print("Summary: %d imported, %d skipped, %d total."
          % (imported_count, skipped_count, len(cards)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
