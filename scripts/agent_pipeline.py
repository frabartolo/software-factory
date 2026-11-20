#!/usr/bin/env python3
"""Führt Deck-Karten mit getrennten Agenten von Neu bis Approved.

Intake und Prüfer sind flaps, der Implementierer ist kiara. hathi springt nur
ein, wenn das bevorzugte Modell dieses Laufs fehlt. Der Prüfer muss ein
anderes Modell sein als der Implementierer. Done setzt diese Pipeline nie.
Jedes Urteil landet als Kommentar auf der Karte.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory_common import (
    FactoryError,
    PolicyError,
    append_audit,
    assert_no_secrets,
    check_transition,
    factory_config,
    stack_name,
)
from validate_ticket import parse_ticket

Assess = Callable[[dict[str, Any], tuple[str, dict[str, Any]]], dict[str, Any]]
Prepare = Callable[[dict[str, Any], tuple[str, dict[str, Any]], str], dict[str, Any]]
Implement = Callable[[dict[str, Any], tuple[str, dict[str, Any]], str], dict[str, Any]]
Critique = Callable[[dict[str, Any], tuple[str, dict[str, Any]], str], dict[str, Any]]
BUDGET_DEFAULTS = {"max_walltime": "30m", "max_turns": "15", "max_files": "10"}


def agent_names() -> tuple[str, str, str, str | None]:
    agents = factory_config().get("agents") or {}
    implementer = str(agents.get("implementer") or "kiara")
    reviewer = str(agents.get("reviewer") or "flaps")
    intake = str(agents.get("intake") or reviewer)
    substitute = str(agents.get("substitute") or "").strip() or None
    return implementer, intake, reviewer, substitute


def assign_models(
    live: list[tuple[str, dict[str, Any]]],
) -> tuple[tuple[str, dict[str, Any]] | None, tuple[str, dict[str, Any]] | None, tuple[str, dict[str, Any]] | None]:
    by = {name: (name, cfg) for name, cfg in live}
    implementer_name, intake_name, reviewer_name, substitute_name = agent_names()
    implementer = by.get(implementer_name)
    intake = by.get(intake_name)
    reviewer = by.get(reviewer_name)
    substitute = by.get(substitute_name) if substitute_name else None
    if implementer is None and substitute is not None:
        implementer = substitute
    if substitute is not None and (implementer is None or substitute[0] != implementer[0]):
        if reviewer is None:
            reviewer = substitute
        if intake is None:
            intake = substitute
    if implementer and reviewer and reviewer[0] == implementer[0]:
        reviewer = None
    if implementer and intake and intake[0] == implementer[0]:
        intake = None
    return implementer, intake, reviewer


def ticket_label(card: dict[str, Any]) -> str:
    title = str(card.get("title") or "")
    match = re.search(r"FACT-\d+", title)
    if match:
        return match.group(0)
    return f"card-{card.get('id')}"


def spec_errors(text: str) -> list[str]:
    _ticket, errors = parse_ticket(text)
    return errors


def _sections(text: str) -> dict[str, str]:
    ticket, _errors = parse_ticket(text)
    return ticket.sections


def dependency_ids(text: str) -> list[str] | None:
    """None, wenn der Abschnitt fehlt. Sonst die genannten FACT-Nummern."""
    sections = _sections(text)
    if "Dependencies" not in sections:
        return None
    found: list[str] = []
    for item in re.findall(r"FACT-\d+", sections["Dependencies"]):
        if item not in found:
            found.append(item)
    return found


def replace_section(text: str, name: str, body: str) -> str:
    lines = text.splitlines()
    start: int | None = None
    end: int | None = None
    for index, line in enumerate(lines):
        if line.startswith("## ") and not line.startswith("### "):
            if start is not None and end is None:
                end = index
                break
            if line[3:].strip() == name:
                start = index
    block = [f"## {name}", ""] + body.strip().splitlines()
    if start is None:
        return text.rstrip() + "\n\n" + "\n".join(block) + "\n"
    if end is None:
        end = len(lines)
    merged = lines[:start] + block + [""] + lines[end:]
    return "\n".join(merged).rstrip() + "\n"


def fill_budget(text: str) -> tuple[str, list[str]]:
    sections = _sections(text)
    budget = sections.get("Budget", "")
    missing = [key for key in BUDGET_DEFAULTS if key not in budget]
    if "Budget" in sections and not missing:
        return text, []
    keys = missing or list(BUDGET_DEFAULTS)
    extra = "\n".join(f"{key}: {BUDGET_DEFAULTS[key]}" for key in keys)
    if "Budget" not in sections:
        return text.rstrip() + "\n\n## Budget\n\n" + extra + "\n", keys
    return replace_section(text, "Budget", (budget + "\n" + extra).strip()), keys


def board_catalog(deck: Any, card: dict[str, Any]) -> str:
    own = int(card["id"])
    lines: list[str] = []
    for key in ("backlog", "ready", "running", "waiting_review", "approved", "done", "blocked"):
        title = stack_name(key)
        for other in deck.cards(title) or []:
            if int(other.get("id") or 0) == own:
                continue
            lines.append(f"{ticket_label(other)} | {title} | {other.get('title') or ''}")
    return "\n".join(lines)


def known_labels(catalog: str) -> set[str]:
    return set(re.findall(r"FACT-\d+", catalog))


def card_locations(deck: Any) -> dict[str, str]:
    found: dict[str, str] = {}
    for key in ("backlog", "ready", "running", "waiting_review", "approved", "done", "blocked"):
        title = stack_name(key)
        for other in deck.cards(title) or []:
            label = ticket_label(other)
            if label.startswith("FACT-"):
                found[label] = title
    return found


def open_dependencies(deck: Any, card: dict[str, Any]) -> list[tuple[str, str]]:
    ids = dependency_ids(str(card.get("description") or ""))
    if not ids:
        return []
    located = card_locations(deck)
    own = ticket_label(card)
    done = {stack_name("approved"), stack_name("done")}
    pending: list[tuple[str, str]] = []
    for dep in ids:
        if dep == own:
            continue
        where = located.get(dep, "fehlt")
        if where not in done:
            pending.append((dep, where))
    return pending


def apply_dependencies(text: str, deps: list[str], known: set[str], own: str) -> tuple[str, list[str]]:
    cleaned: list[str] = []
    for dep in deps:
        if dep in known and dep != own and dep not in cleaned and re.fullmatch(r"FACT-\d+", dep):
            cleaned.append(dep)
    body = "\n".join(f"- {dep}" for dep in cleaned) if cleaned else "keine"
    return replace_section(text, "Dependencies", body), cleaned


def _question_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:5]


MAX_RETURNS = 2
RETURN_MARK = "Rückgabe an den Implementierer."


def _model_fault(points: list[str]) -> str:
    """Eine unlesbare Modellantwort ist kein fachlicher Mangel der Arbeit."""
    blob = " ".join(points)
    if "kein JSON" in blob or "nicht verwertbar" in blob:
        real = [item for item in points if "kein JSON" not in item and "nicht verwertbar" not in item]
        if not real:
            return blob[:300]
    return ""


def return_count(comments: list[dict[str, Any]]) -> int:
    return sum(1 for item in comments if RETURN_MARK in str(item.get("message") or ""))


def latest_return(comments: list[dict[str, Any]]) -> str:
    for item in reversed(comments):
        message = str(item.get("message") or "")
        if RETURN_MARK in message:
            return message
    return ""


def return_comment(model: str, points: list[str]) -> str:
    lines = [f"Prüfer ({model}): {RETURN_MARK}", "Offene Punkte:"]
    for point in points:
        lines.append(f"- {point}")
    lines.append(
        "Die Karte liegt wieder in Running / In Arbeit. "
        "Der Implementierer setzt diese Punkte um und schreibt danach einen Kommentar "
        "mit Dateien und Zusammenfassung, der mit „Implementierer („ beginnt."
    )
    return "\n".join(lines)


def implementer_name_from_comments(comments: list[dict[str, Any]]) -> str | None:
    pattern = re.compile(r"^Implementierer \(([^)]+)\):", re.MULTILINE)
    for item in reversed(comments):
        message = str(item.get("message") or "")
        match = pattern.search(message)
        if match:
            return match.group(1).strip()
    return None


def _clip(text: str, limit: int = 1000) -> str:
    cleaned = text.strip()
    try:
        assert_no_secrets(cleaned, "kommentar")
    except FactoryError:
        return "Kommentar verworfen, weil der Text wie Zugangsdaten aussah."
    return cleaned[:limit]


def post_comment(deck: Any, card_id: int, message: str, *, dry_run: bool) -> str | None:
    text = _clip(message)
    existing = deck.list_comments(card_id)
    if any(str(item.get("message") or "").strip() == text for item in existing):
        return None
    if not dry_run:
        deck.add_comment(card_id, text)
    return text


def move_card(deck: Any, card: dict[str, Any], role: str, source: str, target: str, *, dry_run: bool) -> None:
    if target == stack_name("done"):
        raise PolicyError("Done setzt nur ein Mensch")
    check_transition(role, source, target)
    if dry_run:
        return
    deck.move_card(card, target)
    append_audit(
        {
            "ticket": ticket_label(card),
            "event": "agent_move",
            "from": source,
            "to": target,
            "actor": role,
            "role": role,
            "message": f"Karte {card.get('id')} nach {target}",
            "card_id": int(card["id"]),
        }
    )


def _action(card: dict[str, Any], agent: str, model: str | None, source: str, target: str, comment: str | None, *, moved: bool) -> dict[str, Any]:
    return {
        "card_id": int(card["id"]),
        "ticket": ticket_label(card),
        "agent": agent,
        "model": model,
        "from": source,
        "to": target,
        "moved": moved,
        "comment": comment,
    }


def _ordered(deck: Any, title: str) -> list[dict[str, Any]]:
    cards = list(deck.cards(title) or [])
    return sorted(cards, key=lambda card: (card.get("order") or 0, int(card.get("id") or 0)))


def find_card(deck: Any, card_id: int) -> tuple[dict[str, Any] | None, str | None]:
    for key in ("waiting_review", "running", "ready", "backlog", "approved", "blocked", "done"):
        title = stack_name(key)
        for card in deck.cards(title) or []:
            if int(card.get("id") or 0) == card_id:
                return card, title
    return None, None


def pick_card(deck: Any, card_id: int | None) -> tuple[dict[str, Any] | None, str | None]:
    if card_id is not None:
        return find_card(deck, card_id)
    for key in ("waiting_review", "running", "ready", "backlog"):
        title = stack_name(key)
        cards = _ordered(deck, title)
        if cards:
            return cards[0], title
    return None, None


def _save_description(deck: Any, card: dict[str, Any], description: str, *, dry_run: bool) -> None:
    if description == str(card.get("description") or ""):
        return
    card["description"] = description
    if not dry_run:
        deck.update_description(card, description)


def _dependency_line(ids: list[str] | None) -> str:
    if ids is None:
        return "Abhängigkeiten: noch nicht ermittelt."
    if not ids:
        return "Abhängigkeiten: keine."
    return "Abhängigkeiten: " + ", ".join(ids) + "."


def step_intake(
    deck: Any,
    card: dict[str, Any],
    intake: tuple[str, dict[str, Any]] | None,
    prepare: Prepare,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    source = stack_name("backlog")
    ready = stack_name("ready")
    if intake is None:
        comment = post_comment(
            deck,
            int(card["id"]),
            "Intake: Der Auftrag bleibt in Backlog / Neu.\n"
            "Begründung: Der Intake-Agent ist nicht erreichbar oder wäre dasselbe Modell wie der Implementierer.",
            dry_run=dry_run,
        )
        return _action(card, "intake", None, source, source, comment, moved=False)
    original = str(card.get("description") or "")
    errors = spec_errors(original)
    deps = dependency_ids(original)
    if not errors and deps is not None:
        if dry_run:
            comment = post_comment(
                deck,
                int(card["id"]),
                f"Intake ({intake[0]}): Dry-run, die Karte würde nach {ready} gehen. "
                + _dependency_line(deps),
                dry_run=True,
            )
            return _action(card, "intake", intake[0], source, source, comment, moved=False)
        move_card(deck, card, "hermes", source, ready, dry_run=False)
        comment = post_comment(
            deck,
            int(card["id"]),
            f"Intake ({intake[0]}): Der Auftrag ist ausführbar und geht nach {ready}.\n"
            "Die Pflichtabschnitte sind vollständig.\n"
            + _dependency_line(deps),
            dry_run=False,
        )
        return _action(card, "intake", intake[0], source, ready, comment, moved=True)
    if dry_run:
        comment = post_comment(
            deck,
            int(card["id"]),
            f"Intake ({intake[0]}): Dry-run, fehlende Abschnitte und Abhängigkeiten würden ergänzt. "
            "Die Karte bliebe in Backlog / Neu, bis das Ergebnis ausführbar ist.",
            dry_run=True,
        )
        return _action(card, "intake", intake[0], source, source, comment, moved=False)
    catalog = board_catalog(deck, card)
    try:
        prepared = prepare(card, intake, catalog)
    except Exception as exc:
        prepared = {"usable": False, "error": str(exc)}
    if not prepared.get("usable"):
        detail = str(prepared.get("error") or "Antwort war kein JSON")
        comment = post_comment(
            deck,
            int(card["id"]),
            f"Intake ({intake[0]}): Der Auftrag bleibt in Backlog / Neu.\n"
            f"Begründung: die Ergänzung war nicht verwertbar ({detail}).",
            dry_run=False,
        )
        return _action(card, "intake", intake[0], source, source, comment, moved=False)
    text = str(prepared.get("description") or original)
    before = set(_sections(original))
    text, budget_keys = fill_budget(text)
    text, cleaned = apply_dependencies(text, _question_list(prepared.get("dependencies")), known_labels(catalog), ticket_label(card))
    questions = _question_list(prepared.get("questions"))
    _save_description(deck, card, text, dry_run=False)
    added = [name for name in _sections(text) if name not in before]
    if budget_keys:
        added.append("Budget-Vorgaben")
    remaining = spec_errors(text)
    if remaining or questions:
        lines = [f"Intake ({intake[0]}): Der Auftrag bleibt in Backlog / Neu."]
        if added:
            lines.append("Ergänzt: " + ", ".join(added) + ".")
        lines.append(_dependency_line(cleaned))
        if questions:
            lines.append("Rückfragen:")
            lines.extend(f"- {item}" for item in questions)
        if remaining:
            lines.append("Noch offen: " + "; ".join(remaining) + ".")
        comment = post_comment(deck, int(card["id"]), "\n".join(lines), dry_run=False)
        return _action(card, "intake", intake[0], source, source, comment, moved=False)
    move_card(deck, card, "hermes", source, ready, dry_run=False)
    lines = [f"Intake ({intake[0]}): Der Auftrag ist ausführbar und geht nach {ready}."]
    if added:
        lines.append("Ergänzt: " + ", ".join(added) + ".")
    lines.append(_dependency_line(cleaned))
    comment = post_comment(deck, int(card["id"]), "\n".join(lines), dry_run=False)
    return _action(card, "intake", intake[0], source, ready, comment, moved=True)


def step_implement(deck: Any, card: dict[str, Any], source: str, implementer: tuple[str, dict[str, Any]] | None, implement: Implement, *, dry_run: bool) -> dict[str, Any]:
    review = stack_name("waiting_review")
    running = stack_name("running")
    pending = open_dependencies(deck, card)
    if pending:
        listed = ", ".join(f"{dep} liegt in {where}" for dep, where in pending)
        comment = post_comment(
            deck,
            int(card["id"]),
            f"Implementierer ({implementer[0] if implementer else '-'}): Die Karte bleibt in {source}.\n"
            f"Begründung: offene Abhängigkeiten: {listed}.\n"
            "Die Arbeit beginnt, wenn diese Karten in Approved / Freigegeben oder Done / Erledigt liegen.",
            dry_run=dry_run,
        )
        model_name = implementer[0] if implementer else None
        return _action(card, "implementer", model_name, source, source, comment, moved=False)
    if implementer is None:
        comment = post_comment(
            deck,
            int(card["id"]),
            "Implementierer: Die Karte bleibt liegen.\nBegründung: kiara ist nicht erreichbar.",
            dry_run=dry_run,
        )
        return _action(card, "implementer", None, source, source, comment, moved=False)
    if dry_run:
        todos = latest_return(deck.list_comments(int(card["id"])))
        hint = " Die offenen Punkte aus der Rückgabe würden mit umgesetzt." if todos else ""
        comment = post_comment(
            deck,
            int(card["id"]),
            f"Implementierer ({implementer[0]}): Dry-run, die Karte würde nach {review} gehen. "
            f"Der Prüfer ist ein anderes Modell.{hint}",
            dry_run=True,
        )
        return _action(card, "implementer", implementer[0], source, source, comment, moved=False)
    if source == stack_name("ready"):
        move_card(deck, card, "runner", source, running, dry_run=False)
        source = running
    todos = latest_return(deck.list_comments(int(card["id"])))
    try:
        work = implement(card, implementer, todos)
    except Exception as exc:
        work = {"ok": False, "files": [], "summary": str(exc), "errors": [str(exc)]}
    files = [str(item) for item in (work.get("files") or [])]
    summary = str(work.get("summary") or "").strip()
    if not (work.get("ok") and (files or summary)):
        reason = summary or "; ".join(str(item) for item in (work.get("errors") or [])) or "kein Arbeitsergebnis"
        url = str(implementer[1].get("url") or "")
        extra = f"\nAufgerufen wurde {url}." if "kein Modell erreichbar" in reason else ""
        comment = post_comment(
            deck,
            int(card["id"]),
            f"Implementierer ({implementer[0]}): die Karte bleibt in {source}.\n"
            f"Begründung: {reason}{extra}\n"
            "Ein anderes Modell prüft die Arbeit und baut sie nicht.\n"
            "Die Karte bleibt liegen, bis ein Arbeitsergebnis vorliegt.",
            dry_run=False,
        )
        return _action(card, "implementer", implementer[0], source, source, comment, moved=False)
    listed = ", ".join(files) if files else "(keine neuen Dateien)"
    move_card(deck, card, "runner", source, review, dry_run=False)
    comment = post_comment(
        deck,
        int(card["id"]),
        f"Implementierer ({implementer[0]}): Arbeitsergebnis für {ticket_label(card)}.\n"
        f"Dateien: {listed}\n"
        f"Zusammenfassung: {summary or '(keine)'}\n"
        f"Die Karte liegt jetzt in {review}. Freigabe prüft ein anderes Modell.",
        dry_run=False,
    )
    return _action(card, "implementer", implementer[0], source, review, comment, moved=True)


def step_review(deck: Any, card: dict[str, Any], reviewer: tuple[str, dict[str, Any]] | None, critique: Critique, *, dry_run: bool) -> dict[str, Any]:
    source = stack_name("waiting_review")
    comments = deck.list_comments(int(card["id"]))
    built_by = implementer_name_from_comments(comments)
    if reviewer is None:
        comment = post_comment(
            deck,
            int(card["id"]),
            "Prüfer: Die Karte bleibt in Waiting Review / Gate.\n"
            "Begründung: Der unabhängige Prüfer ist nicht erreichbar.\n"
            "Approved gibt es nur von einem anderen Modell als dem Implementierer. Done setzt nur ein Mensch.",
            dry_run=dry_run,
        )
        return _action(card, "reviewer", None, source, source, comment, moved=False)
    if built_by is None:
        return _send_back(
            deck,
            card,
            reviewer,
            comments,
            [
                "Ein Arbeitsergebnis fehlt.",
                "Setze den Auftrag aus der Kartenbeschreibung um.",
                "Schreibe danach einen Kommentar mit den erzeugten Dateien und einer Zusammenfassung.",
            ],
            dry_run=dry_run,
        )
    if built_by == reviewer[0]:
        comment = post_comment(
            deck,
            int(card["id"]),
            f"Prüfer ({reviewer[0]}): Die Karte bleibt in Waiting Review / Gate.\n"
            f"Begründung: {reviewer[0]} hat die Arbeit selbst gebaut und darf sie nicht freigeben.",
            dry_run=dry_run,
        )
        return _action(card, "reviewer", reviewer[0], source, source, comment, moved=False)
    pending = open_dependencies(deck, card)
    if pending:
        listed = ", ".join(f"{dep} liegt in {where}" for dep, where in pending)
        comment = post_comment(
            deck,
            int(card["id"]),
            f"Prüfer ({reviewer[0]}): Die Karte bleibt in Waiting Review / Gate.\n"
            f"Begründung: offene Abhängigkeiten: {listed}.\n"
            "Freigabe gibt es, wenn diese Karten in Approved / Freigegeben oder Done / Erledigt liegen.",
            dry_run=dry_run,
        )
        return _action(card, "reviewer", reviewer[0], source, source, comment, moved=False)
    if dry_run:
        comment = post_comment(
            deck,
            int(card["id"]),
            f"Prüfer ({reviewer[0]}): Dry-run, die Arbeit von {built_by} würde kritisch geprüft.",
            dry_run=True,
        )
        return _action(card, "reviewer", reviewer[0], source, source, comment, moved=False)
    work_comment = ""
    for item in reversed(comments):
        message = str(item.get("message") or "")
        if message.startswith(f"Implementierer ({built_by}):"):
            work_comment = message
            break
    verdict = critique(card, reviewer, work_comment)
    reason = str(verdict.get("reason") or "").strip()
    findings = [str(item) for item in (verdict.get("findings") or [])]
    passed = bool(verdict.get("pass")) and bool(reason)
    if bool(verdict.get("pass")) and not reason:
        reason = "Prüfer hat kein Urteil begründet."
        passed = False
    if not passed:
        points = findings or [reason]
        fault = _model_fault(points)
        if fault:
            comment = post_comment(
                deck,
                int(card["id"]),
                f"Prüfer ({reviewer[0]}): Die Karte bleibt in Waiting Review / Gate.\n"
                f"Begründung: {fault}\n"
                "Das zählt nicht als Rückgabe an den Implementierer.",
                dry_run=False,
            )
            return _action(card, "reviewer", reviewer[0], source, source, comment, moved=False)
        return _send_back(deck, card, reviewer, comments, points, dry_run=False)
    target = stack_name("approved")
    move_card(deck, card, "reviewer", source, target, dry_run=False)
    finding_lines = "\n".join(f"- {item}" for item in findings) if findings else "- (keine einzelnen Befunde)"
    comment = post_comment(
        deck,
        int(card["id"]),
        f"Prüfer ({reviewer[0]}): kritisches Urteil: bestanden.\n"
        f"Geprüft wurde die Arbeit von {built_by}.\n"
        f"Begründung: {reason}\n"
        f"Befunde:\n{finding_lines}\n"
        f"Nächste Spalte: {target}. Done setzt nur ein Mensch.",
        dry_run=False,
    )
    return _action(card, "reviewer", reviewer[0], source, target, comment, moved=True)


def _send_back(
    deck: Any,
    card: dict[str, Any],
    reviewer: tuple[str, dict[str, Any]],
    comments: list[dict[str, Any]],
    points: list[str],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    source = stack_name("waiting_review")
    if return_count(comments) >= MAX_RETURNS:
        target = stack_name("blocked")
        text = (
            f"Prüfer ({reviewer[0]}): Die Karte geht nach {target}.\n"
            f"Begründung: Nach {MAX_RETURNS} Rückgaben liegt noch kein bestandenes Arbeitsergebnis vor.\n"
            "Done setzt nur ein Mensch."
        )
    else:
        target = stack_name("running")
        text = return_comment(reviewer[0], points)
    if dry_run:
        comment = post_comment(deck, int(card["id"]), text, dry_run=True)
        return _action(card, "reviewer", reviewer[0], source, target, comment, moved=False)
    move_card(deck, card, "reviewer", source, target, dry_run=False)
    comment = post_comment(deck, int(card["id"]), text, dry_run=False)
    return _action(card, "reviewer", reviewer[0], source, target, comment, moved=True)


def run_pipeline(
    deck: Any,
    live: list[tuple[str, dict[str, Any]]],
    *,
    assess: Assess,
    implement: Implement,
    critique: Critique,
    prepare: Prepare | None = None,
    dry_run: bool = False,
    follow: bool = False,
    card_id: int | None = None,
) -> list[dict[str, Any]]:
    del assess  # Die Ausführbarkeit entscheidet die vollständige Beschreibung, nicht ein zweites JSON-Urteil.
    implementer, intake, reviewer = assign_models(live)
    planner = prepare or default_prepare
    actions: list[dict[str, Any]] = []
    target = card_id
    rounds = 4 if follow and not dry_run else 1
    for _ in range(rounds):
        card, source = pick_card(deck, target)
        if card is None or source is None:
            break
        if source in {stack_name("approved"), stack_name("done"), stack_name("blocked")}:
            break
        if source == stack_name("backlog"):
            action = step_intake(deck, card, intake, planner, dry_run=dry_run)
        elif source in {stack_name("ready"), stack_name("running")}:
            action = step_implement(deck, card, source, implementer, implement, dry_run=dry_run)
        elif source == stack_name("waiting_review"):
            action = step_review(deck, card, reviewer, critique, dry_run=dry_run)
        else:
            break
        actions.append(action)
        if not follow or dry_run or not action["moved"]:
            break
        if action["to"] in {stack_name("approved"), stack_name("blocked")}:
            break
        target = int(card["id"])
    return actions


def _json_verdict(text: str) -> dict[str, Any]:
    import runner

    parsed = runner.extract_json(text)
    if not isinstance(parsed, dict):
        return {"pass": False, "reason": "Antwort war kein JSON", "findings": ["Antwort war kein JSON"]}
    findings = parsed.get("findings") or parsed.get("violations") or []
    if isinstance(findings, str):
        findings = [findings]
    reason = str(parsed.get("reason") or "").strip()
    return {"pass": bool(parsed.get("pass")), "reason": reason, "findings": [str(item) for item in findings][:8]}


def _complete(model: tuple[str, dict[str, Any]], system: str, user: str) -> str:
    import runner

    return runner.llm_call(
        model[0],
        model[1],
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=1024,
    )


def default_prepare(card: dict[str, Any], model: tuple[str, dict[str, Any]], catalog: str) -> dict[str, Any]:
    import runner

    raw = runner.llm_call(
        model[0],
        model[1],
        [
            {
                "role": "system",
                "content": (
                    "Du ergänzt einen Factory-Auftrag. Du schreibst keinen Code. "
                    "Erfinde keine Zugangsdaten und kein Repository. "
                    "Was du aus Titel und Text ableiten kannst, schreibst du in die Abschnitte "
                    "Goal, Success criteria, Acceptance examples, Forbidden, Checks, Budget. "
                    "Acceptance examples enthalten Normalfall, Grenzfall und Fehlerfall. "
                    "Ist eine nötige Tatsache unbekannt, setze sie als Frage und lass den Abschnitt ehrlich. "
                    "dependencies enthält nur FACT-Nummern aus der Liste anderer Karten, und nur wenn diese Karte "
                    "deren Ergebnis braucht. Sonst eine leere Liste. "
                    "Antworte nur mit JSON: "
                    '{"description":"...","questions":["..."],"dependencies":["FACT-001"]}'
                ),
            },
            {
                "role": "user",
                "content": "TITEL:\n"
                + str(card.get("title") or "")
                + "\n\nANDERE KARTEN:\n"
                + (catalog or "(keine)")
                + "\n\nAUFTRAG:\n"
                + str(card.get("description") or ""),
            },
        ],
        max_tokens=3072,
    )
    parsed = runner.extract_json(raw)
    if isinstance(parsed, dict) and (parsed.get("description") or parsed.get("questions") is not None or parsed.get("dependencies") is not None):
        return {
            "usable": True,
            "description": str(parsed.get("description") or card.get("description") or ""),
            "questions": parsed.get("questions") or [],
            "dependencies": parsed.get("dependencies") or [],
        }
    if isinstance(raw, str) and "## Goal" in raw and "## Acceptance examples" in raw:
        return {"usable": True, "description": raw, "questions": [], "dependencies": []}
    return {"usable": False, "error": "Antwort war kein JSON"}


def default_assess(card: dict[str, Any], model: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    text = _complete(
        model,
        "Du prüfst nur, ob der Auftrag ausführbar beschrieben ist. Du schreibst keinen Code. "
        "Antworte nur mit JSON: {\"pass\": true|false, \"reason\": \"...\", \"findings\": [\"...\"]}. "
        "pass ist nur true, wenn Ziel, Abnahme und Grenzen konkret genug sind.",
        str(card.get("description") or ""),
    )
    return _json_verdict(text)


def default_implement(card: dict[str, Any], model: tuple[str, dict[str, Any]], todos: str = "") -> dict[str, Any]:
    import runner

    description = str(card.get("description") or "")
    norm = runner.parse_ticket(description)
    deps = dependency_ids(description) or []
    goal = str(norm.get("goal") or "")
    if deps:
        goal += "\n\nABHÄNGIGKEITEN, DIE BEREITS FREIGEGEBEN SIND:\n" + "\n".join(f"- {dep}" for dep in deps)
    if todos.strip():
        goal += "\n\nOFFENE PUNKTE AUS DER PRÜFUNG:\n" + todos.strip()
    norm["goal"] = goal
    ticket_id = ticket_label(card)
    workdir = Path(__file__).resolve().parent.parent / "work" / ticket_id
    budget = runner.parse_budget(norm.get("budget", ""))
    work = runner.do_work(ticket_id, norm, [model], budget, workdir)
    return {
        "ok": bool(work.get("ok")),
        "summary": str(work.get("summary") or ""),
        "files": list(work.get("files") or []),
        "model": model[0],
        "errors": list(work.get("errors") or []),
    }


def default_critique(card: dict[str, Any], model: tuple[str, dict[str, Any]], work_comment: str) -> dict[str, Any]:
    text = _complete(
        model,
        "Du bist ein unabhängiger Prüfer. Du hast die Arbeit nicht gebaut. "
        "Suche Lücken gegenüber Ziel, Abnahme, Verboten und Abhängigkeiten. "
        "Antworte nur mit JSON: {\"pass\": true|false, \"reason\": \"...\", \"findings\": [\"...\"]}. "
        "pass ist nur true, wenn die genannten Dateien die Abnahme tragen. "
        "Eine leere Begründung ist kein Bestehen.",
        "AUFTRAG:\n"
        + str(card.get("description") or "")
        + "\n\nARBEITSERGEBNIS:\n"
        + work_comment,
    )
    return _json_verdict(text)


def live_models() -> list[tuple[str, dict[str, Any]]]:
    import runner

    return runner.choose_models({})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deck von Neu bis Approved mit getrennten Agenten")
    parser.add_argument("--once", action="store_true", help="einen Schritt ausführen")
    parser.add_argument("--follow", action="store_true", help="dieselbe Karte bis Approved oder Stopp führen")
    parser.add_argument("--dry-run", action="store_true", help="nichts verschieben und nichts kommentieren")
    parser.add_argument("--card", type=int, help="eine konkrete Karten-ID")
    args = parser.parse_args(argv)
    if not args.once and not args.follow:
        args.once = True
    try:
        from deck import client_or_exit

        deck = client_or_exit()
        actions = run_pipeline(
            deck,
            live_models(),
            assess=default_assess,
            implement=default_implement,
            critique=default_critique,
            dry_run=args.dry_run,
            follow=args.follow,
            card_id=args.card,
        )
    except (FactoryError, PolicyError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not actions:
        print("Keine Karte in Neu, Ready, Running oder Review.")
        return 0
    for action in actions:
        print(
            f"{action['ticket']} {action['agent']} ({action['model'] or '-'}) "
            f"{action['from']} → {action['to']}"
        )
        if action.get("comment"):
            print(action["comment"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
