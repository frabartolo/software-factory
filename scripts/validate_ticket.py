#!/usr/bin/env python3
"""Prüft, ob ein Factory-Ticket vollständig und ausführbar beschrieben ist."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory_common import FactoryError, root

REQUIRED_SECTIONS = (
    "Goal",
    "Success criteria",
    "Acceptance examples",
    "Forbidden",
    "Checks",
    "Budget",
)
BUDGET_KEYS = ("max_walltime", "max_turns", "max_files")
CASE_GROUPS = (
    ("Normalfall", "Normal case"),
    ("Grenzfall", "Boundary case", "Boundary"),
    ("Fehlerfall", "Failure case", "Failure"),
)


@dataclass
class Ticket:
    ticket_id: str
    title: str
    repo: str
    base_branch: str
    body: str
    meta: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None
    sections: dict[str, str] = field(default_factory=dict)


def split_frontmatter(text: str) -> tuple[dict[str, Any], str, list[str]]:
    errors: list[str] = []
    stripped = text.lstrip("\ufeff")
    if not stripped.startswith("---"):
        return {}, stripped, errors
    end = stripped.find("\n---", 3)
    if end == -1:
        return {}, stripped, ["Frontmatter ist nicht geschlossen"]
    raw = stripped[3:end].strip()
    rest = stripped[end + 4 :]
    if rest.startswith("\n"):
        rest = rest[1:]
    if not raw:
        return {}, rest, errors
    try:
        loaded = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        return {}, rest, [f"Frontmatter ist ungültig: {exc}"]
    if loaded is None:
        return {}, rest, errors
    if not isinstance(loaded, dict):
        return {}, rest, ["Frontmatter muss ein Objekt sein"]
    return loaded, rest, errors


def section_map(body: str) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    sections: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if current is None:
            return
        if current in sections:
            errors.append(f"Abschnitt doppelt: {current}")
        sections[current] = "\n".join(buffer).strip()

    for line in body.splitlines():
        if line.startswith("## ") and not line.startswith("### "):
            flush()
            current = line[3:].strip()
            buffer = []
            continue
        if current is not None:
            buffer.append(line)
    flush()
    return sections, errors


def parse_ticket(text: str, path: Path | None = None) -> tuple[Ticket, list[str]]:
    meta, body, errors = split_frontmatter(text)
    sections, section_errors = section_map(body)
    errors.extend(section_errors)

    for name in REQUIRED_SECTIONS:
        if name not in sections:
            errors.append(f"Pflichtabschnitt fehlt: {name}")
        elif not sections[name].strip():
            errors.append(f"Pflichtabschnitt ist leer: {name}")

    acceptance = sections.get("Acceptance examples", "")
    if acceptance.strip():
        for aliases in CASE_GROUPS:
            if not any(alias in acceptance for alias in aliases):
                errors.append(f"Akzeptanzbeispiel fehlt: {aliases[0]}")

    budget = sections.get("Budget", "")
    for key in BUDGET_KEYS:
        if key not in budget:
            errors.append(f"Budget-Feld fehlt: {key}")

    fallback_id = path.stem if path is not None else "UNKNOWN"
    ticket_id = str(meta.get("id") or fallback_id)
    title = str(meta.get("title") or ticket_id)
    repo = str(meta.get("repo") or "")
    base_branch = str(meta.get("base_branch") or "main")
    ticket = Ticket(
        ticket_id=ticket_id,
        title=title,
        repo=repo,
        base_branch=base_branch,
        body=text,
        meta=meta,
        path=path,
        sections=sections,
    )
    return ticket, errors


def validate_path(path: Path) -> tuple[Ticket, list[str]]:
    if not path.is_file():
        raise FactoryError(f"Ticketdatei fehlt: {path}")
    return parse_ticket(path.read_text(encoding="utf-8"), path)


def resolve_ticket_path(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = root() / path
    resolved = path.resolve()
    factory_root = root().resolve()
    if factory_root not in resolved.parents and resolved != factory_root:
        raise FactoryError(f"Ticketpfad liegt außerhalb der Fabrik: {raw}")
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Factory-Ticket prüfen")
    parser.add_argument("ticket", help="Pfad zur Ticketdatei")
    args = parser.parse_args(argv)
    try:
        ticket, errors = validate_path(resolve_ticket_path(args.ticket))
    except FactoryError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if errors:
        print(f"ABGELEHNT {ticket.ticket_id}", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"OK {ticket.ticket_id} repo={ticket.repo or '-'} title={ticket.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
