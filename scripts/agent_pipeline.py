#!/usr/bin/env python3
"""Führt Deck-Karten mit getrennten Agenten von Neu bis Approved.

Intake und Prüfer sind flaps, der Implementierer ist kiara. Der Prüfer muss
ein anderes Modell sein als der Implementierer. Done setzt diese Pipeline nie.
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
Implement = Callable[[dict[str, Any], tuple[str, dict[str, Any]], str], dict[str, Any]]
Critique = Callable[[dict[str, Any], tuple[str, dict[str, Any]], str], dict[str, Any]]


def agent_names() -> tuple[str, str, str]:
    agents = factory_config().get("agents") or {}
    implementer = str(agents.get("implementer") or "kiara")
    reviewer = str(agents.get("reviewer") or "flaps")
    intake = str(agents.get("intake") or reviewer)
    return implementer, intake, reviewer


def assign_models(
    live: list[tuple[str, dict[str, Any]]],
) -> tuple[tuple[str, dict[str, Any]] | None, tuple[str, dict[str, Any]] | None, tuple[str, dict[str, Any]] | None]:
    by = {name: (name, cfg) for name, cfg in live}
    implementer_name, intake_name, reviewer_name = agent_names()
    implementer = by.get(implementer_name)
    intake = by.get(intake_name)
    reviewer = by.get(reviewer_name)
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


MAX_RETURNS = 2
RETURN_MARK = "Rückgabe an den Implementierer."


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


def step_intake(deck: Any, card: dict[str, Any], intake: tuple[str, dict[str, Any]] | None, assess: Assess, *, dry_run: bool) -> dict[str, Any]:
    source = stack_name("backlog")
    errors = spec_errors(str(card.get("description") or ""))
    if intake is None:
        comment = post_comment(
            deck,
            int(card["id"]),
            "Intake: Der Auftrag bleibt in Backlog / Neu.\n"
            "Begründung: Der Intake-Agent ist nicht erreichbar oder wäre dasselbe Modell wie der Implementierer.",
            dry_run=dry_run,
        )
        return _action(card, "intake", None, source, source, comment, moved=False)
    if errors:
        comment = post_comment(
            deck,
            int(card["id"]),
            "Intake (" + intake[0] + "): Der Auftrag bleibt in Backlog / Neu.\n"
            "Begründung: " + "; ".join(errors),
            dry_run=dry_run,
        )
        return _action(card, "intake", intake[0], source, source, comment, moved=False)
    if dry_run:
        comment = post_comment(
            deck,
            int(card["id"]),
            f"Intake ({intake[0]}): Dry-run, die Karte bliebe in Backlog / Neu, bis der Agent sie prüft.",
            dry_run=True,
        )
        return _action(card, "intake", intake[0], source, source, comment, moved=False)
    verdict = assess(card, intake)
    reason = str(verdict.get("reason") or "").strip() or "keine Begründung"
    if verdict.get("pass"):
        move_card(deck, card, "hermes", source, stack_name("ready"), dry_run=False)
        comment = post_comment(
            deck,
            int(card["id"]),
            f"Intake ({intake[0]}): Der Auftrag ist ausführbar und geht nach {stack_name('ready')}.\n"
            f"Begründung: {reason}",
            dry_run=False,
        )
        return _action(card, "intake", intake[0], source, stack_name("ready"), comment, moved=True)
    comment = post_comment(
        deck,
        int(card["id"]),
        f"Intake ({intake[0]}): Der Auftrag bleibt in Backlog / Neu.\nBegründung: {reason}",
        dry_run=False,
    )
    return _action(card, "intake", intake[0], source, source, comment, moved=False)


def step_implement(deck: Any, card: dict[str, Any], source: str, implementer: tuple[str, dict[str, Any]] | None, implement: Implement, *, dry_run: bool) -> dict[str, Any]:
    review = stack_name("waiting_review")
    running = stack_name("running")
    blocked = stack_name("blocked")
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
    if not work.get("ok") or not files:
        reason = summary or "; ".join(str(item) for item in (work.get("errors") or [])) or "kein Arbeitsergebnis"
        if "kein Modell erreichbar" in reason:
            url = str(implementer[1].get("url") or "")
            comment = post_comment(
                deck,
                int(card["id"]),
                f"Implementierer ({implementer[0]}): die Karte bleibt in {source}.\n"
                f"Begründung: {reason}\n"
                f"Aufgerufen wurde {url}. flaps prüft die Arbeit und baut sie nicht.\n"
                "Die Karte bleibt liegen, bis dieser Aufruf gelingt.",
                dry_run=False,
            )
            return _action(card, "implementer", implementer[0], source, source, comment, moved=False)
        move_card(deck, card, "runner", source, blocked, dry_run=False)
        comment = post_comment(
            deck,
            int(card["id"]),
            f"Implementierer ({implementer[0]}): kein verwertbares Arbeitsergebnis.\n"
            f"Begründung: {reason}\n"
            f"Die Karte geht nach {blocked}.",
            dry_run=False,
        )
        return _action(card, "implementer", implementer[0], source, blocked, comment, moved=True)
    listed = ", ".join(files)
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
    dry_run: bool = False,
    follow: bool = False,
    card_id: int | None = None,
) -> list[dict[str, Any]]:
    implementer, intake, reviewer = assign_models(live)
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
            action = step_intake(deck, card, intake, assess, dry_run=dry_run)
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
    if todos.strip():
        goal = str(norm.get("goal") or "")
        norm["goal"] = goal + "\n\nOFFENE PUNKTE AUS DER PRÜFUNG:\n" + todos.strip()
    ticket_id = ticket_label(card)
    workdir = Path(__file__).resolve().parent.parent / "work" / ticket_id
    budget = runner.parse_budget(norm.get("budget", ""))
    work = runner.do_work(ticket_id, norm, [model], budget, workdir)
    return {
        "ok": bool(work.get("ok")) and bool(work.get("files")),
        "summary": str(work.get("summary") or ""),
        "files": list(work.get("files") or []),
        "model": model[0],
        "errors": list(work.get("errors") or []),
    }


def default_critique(card: dict[str, Any], model: tuple[str, dict[str, Any]], work_comment: str) -> dict[str, Any]:
    text = _complete(
        model,
        "Du bist ein unabhängiger Prüfer. Du hast die Arbeit nicht gebaut. "
        "Suche Lücken gegenüber Ziel, Abnahme und Verboten. "
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
