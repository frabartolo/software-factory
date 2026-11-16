#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_factory_schema.py — Validiert Factory-Tickets gegen das maschinenlesbare
Schema (schema/ticket.schema.json).

Ein Ticket ist eine Markdown-Datei mit den Pflicht-Sektionen (## -Headings):
    Goal, Success criteria, Acceptance examples, Forbidden, Checks, Budget
Jede Pflicht-Sektion muss Inhalt haben. Die Sektion 'Budget' muss die Schlüssel
    max_walltime, max_turns, max_files   (Format 'schlüssel: Wert')
enthalten.

Verwendung:
    python3 scripts/validate_factory_schema.py <ticket.md> [<ticket2.md> ...]
Exit-Code: 0 = alle Tickets gültig, 1 = mindestens ein Ticket ungültig,
             2 = Fehler (z. B. keine Tickets übergeben).
"""

import json
import re
import sys
from pathlib import Path

HEADING_RE = re.compile(r"^##\s+(.*)$")
KV_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")

FALLBACK_SCHEMA = {
    "heading_prefix": "##",
    "required_headings": [
        "Goal",
        "Success criteria",
        "Acceptance examples",
        "Forbidden",
        "Checks",
        "Budget",
    ],
    "budget_required_keys": ["max_walltime", "max_turns", "max_files"],
}


def load_schema(factory_root):
    """Lädt das maschinenlesbare Schema; Fallback, falls Datei fehlt/defekt ist."""
    schema_path = factory_root / "schema" / "ticket.schema.json"
    if schema_path.is_file():
        try:
            return json.loads(schema_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(
                f"Warning: Schema nicht lesbar ({e}) — nutze Fallback-Schema.",
                file=sys.stderr,
            )
    return dict(FALLBACK_SCHEMA)


def parse_sections(text):
    """
    Parse '## ' Sektionen aus Markdown-Text.
    Gibt ({heading: roher_Inhalt}, [headings in Reihenfolge]) zurück.
    """
    sections = {}
    order = []
    current = None
    buf = []
    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if m:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = m.group(1).strip()
            if current and current not in order:
                order.append(current)
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None and current:
        sections[current] = "\n".join(buf).strip()
    return sections, order


def parse_kv_section(text):
    """Les 'schlüssel: Wert'-Zeilen aus einer Sektion."""
    kv = {}
    for line in text.splitlines():
        m = KV_RE.match(line)
        if m:
            kv[m.group(1)] = m.group(2).strip()
    return kv


def validate_ticket(path, schema):
    """Gibt eine Liste von Fehlermeldungen zurück (leere Liste = gültig)."""
    p = Path(path)
    if not p.is_file():
        return [f"Datei existiert nicht: {p}"]
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as e:
        return [f"nicht lesbar: {p} ({e})"]

    sections, _ = parse_sections(text)
    errors = []

    if not sections:
        return [
            "Keine Sektionen gefunden — das Ticket muss '## '-Headings enthalten "
            "(erwartet: '## Goal', '## Success criteria', ...). "
            "Mögliche Ursachen: leere Datei, keine Headings, oder Headings "
            "mit vorangehendem Leerzeichen."
        ]

    required = schema.get("required_headings", [])
    for h in required:
        if h not in sections:
            errors.append(f"Fehlendes Pflichtfeld: '## {h}'")
        elif not sections[h]:
            errors.append(f"Pflichtfeld '## {h}' ist leer.")

    if "Budget" in required and "Budget" in sections:
        budget = parse_kv_section(sections["Budget"])
        for k in schema.get("budget_required_keys", []):
            if k not in budget:
                errors.append(f"Sektion 'Budget' fehlt den Schlüssel: {k}.")

    return errors


def main(argv):
    if len(argv) < 2:
        print(
            "Verwendung: python3 validate_factory_schema.py <ticket.md> [<ticket2.md> ...]",
            file=sys.stderr,
        )
        return 2

    factory_root = Path(__file__).resolve().parent.parent
    schema = load_schema(factory_root)

    failed = 0
    for ticket in argv[1:]:
        errors = validate_ticket(ticket, schema)
        name = Path(ticket).name
        if errors:
            failed += 1
            print(f"[FEHLER] {name}")
            for e in errors:
                print(f"    - {e}")
        else:
            print(f"[OK]   {name}  (gültig)")

    print()
    print(f"{len(argv) - 1} Tickete geprüft, {failed} ungültig.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
