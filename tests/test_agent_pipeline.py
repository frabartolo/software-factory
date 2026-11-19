"""Pipeline Neu → Approved mit getrennten Agenten, ohne Netz und ohne Deck."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from agent_pipeline import run_pipeline  # noqa: E402
from factory_common import PolicyError, check_transition, stack_name  # noqa: E402


SPEC = """
## Goal

Eine Hello-World-Ausgabe.

## Success criteria

- Das Programm druckt Hallo.

## Acceptance examples

1. Normal case:
   Hallo
2. Boundary case:
   leere Eingabe bleibt Hallo
3. Failure case:
   fehlende Datei wird gemeldet

## Forbidden

- Kein Netz.

## Checks

- python3 hello.py

## Budget

max_walltime: 5m
max_turns: 4
max_files: 2
"""


class MemoryDeck:
    def __init__(self) -> None:
        self.stacks: dict[str, list[dict]] = {}
        self.comments: dict[int, list[str]] = {}

    def add(self, title: str, card: dict) -> None:
        self.stacks.setdefault(title, []).append(card)

    def cards(self, title: str) -> list[dict]:
        return list(self.stacks.get(title, []))

    def move_card(self, card: dict, target: str) -> None:
        card_id = int(card["id"])
        for title, items in self.stacks.items():
            for index, item in enumerate(items):
                if int(item["id"]) == card_id:
                    items.pop(index)
                    self.stacks.setdefault(target, []).append(item)
                    return
        raise AssertionError(card_id)

    def add_comment(self, card_id: int, message: str) -> None:
        self.comments.setdefault(int(card_id), []).append(message)

    def list_comments(self, card_id: int) -> list[dict]:
        return [{"message": message} for message in self.comments.get(int(card_id), [])]

    def where(self, card_id: int) -> str:
        for title, items in self.stacks.items():
            if any(int(item["id"]) == card_id for item in items):
                return title
        raise AssertionError(card_id)


def live_pair() -> list[tuple[str, dict]]:
    return [("kiara", {"type": "local"}), ("flaps", {"type": "local"})]


class AgentPipelineTest(unittest.TestCase):
    def test_follow_reaches_approved_with_comments(self) -> None:
        deck = MemoryDeck()
        deck.add(stack_name("backlog"), {"id": 7, "title": "FACT-014 — Hello World", "description": SPEC, "order": 0})

        def assess(card, model):
            return {"pass": True, "reason": "Ziel und Abnahme sind konkret.", "findings": []}

        def implement(card, model, todos=""):
            return {"ok": True, "files": ["hello.py"], "summary": "hello.py druckt Hallo.", "errors": []}

        def critique(card, model, work_comment):
            self.assertIn("hello.py", work_comment)
            self.assertIn("Implementierer (kiara)", work_comment)
            return {
                "pass": True,
                "reason": "Die Datei trägt die Abnahme.",
                "findings": ["Die Ausgabe ist fest verdrahtet."],
            }

        actions = run_pipeline(
            deck,
            live_pair(),
            assess=assess,
            implement=implement,
            critique=critique,
            follow=True,
        )
        self.assertEqual(deck.where(7), stack_name("approved"))
        self.assertEqual([item["agent"] for item in actions], ["intake", "implementer", "reviewer"])
        text = "\n".join(deck.comments[7])
        self.assertIn("Intake (flaps)", text)
        self.assertIn("Dateien: hello.py", text)
        self.assertIn("Zusammenfassung: hello.py druckt Hallo.", text)
        self.assertIn("Prüfer (flaps)", text)
        self.assertIn("Die Ausgabe ist fest verdrahtet.", text)
        self.assertIn("Done setzt nur ein Mensch.", text)
        self.assertNotIn(stack_name("done"), deck.stacks)

    def test_same_model_cannot_approve(self) -> None:
        deck = MemoryDeck()
        deck.add(
            stack_name("waiting_review"),
            {"id": 8, "title": "FACT-015 — Hello", "description": SPEC, "order": 0},
        )
        deck.add_comment(8, "Implementierer (flaps): Arbeitsergebnis für FACT-015.\nDateien: hello.py\nZusammenfassung: Hallo.")
        actions = run_pipeline(
            deck,
            live_pair(),
            assess=lambda card, model: {"pass": True, "reason": "ok"},
            implement=lambda card, model, todos="": {"ok": True, "files": ["hello.py"], "summary": "x", "errors": []},
            critique=lambda card, model, work: {"pass": True, "reason": "soll nicht laufen", "findings": []},
            card_id=8,
        )
        self.assertEqual(deck.where(8), stack_name("waiting_review"))
        self.assertFalse(actions[0]["moved"])
        self.assertIn("nicht freigeben", deck.comments[8][-1])

    def test_missing_reviewer_stays_in_review(self) -> None:
        deck = MemoryDeck()
        deck.add(stack_name("waiting_review"), {"id": 9, "title": "FACT-016", "description": SPEC, "order": 0})
        deck.add_comment(9, "Implementierer (kiara): Arbeitsergebnis für FACT-016.\nDateien: hello.py\nZusammenfassung: Hallo.")
        actions = run_pipeline(
            deck,
            [("kiara", {"type": "local"})],
            assess=lambda card, model: {"pass": True, "reason": "ok"},
            implement=lambda card, model, todos="": {"ok": True, "files": ["a.py"], "summary": "x", "errors": []},
            critique=lambda card, model, work: {"pass": True, "reason": "nein", "findings": []},
            card_id=9,
        )
        self.assertEqual(deck.where(9), stack_name("waiting_review"))
        self.assertIn("nicht erreichbar", actions[0]["comment"])

    def test_failed_review_returns_to_running(self) -> None:
        deck = MemoryDeck()
        deck.add(stack_name("waiting_review"), {"id": 10, "title": "FACT-017", "description": SPEC, "order": 0})
        deck.add_comment(10, "Implementierer (kiara): Arbeitsergebnis für FACT-017.\nDateien: hello.py\nZusammenfassung: Hallo.")
        run_pipeline(
            deck,
            live_pair(),
            assess=lambda card, model: {"pass": True, "reason": "ok"},
            implement=lambda card, model, todos="": {"ok": True, "files": ["a.py"], "summary": "x", "errors": []},
            critique=lambda card, model, work: {
                "pass": False,
                "reason": "Die Abnahme ist nicht erfüllt.",
                "findings": ["Kein Ausdruck Hallo."],
            },
            card_id=10,
        )
        self.assertEqual(deck.where(10), stack_name("running"))
        self.assertIn("Rückgabe an den Implementierer.", deck.comments[10][-1])
        self.assertIn("Kein Ausdruck Hallo.", deck.comments[10][-1])

    def test_missing_result_returns_todos_to_implementer(self) -> None:
        deck = MemoryDeck()
        deck.add(stack_name("waiting_review"), {"id": 13, "title": "FACT-003 — Worktree", "description": SPEC, "order": 0})
        seen: dict[str, str] = {}

        def implement(card, model, todos=""):
            seen["todos"] = todos
            return {"ok": True, "files": ["worktree.py"], "summary": "Worktree angelegt.", "errors": []}

        actions = run_pipeline(
            deck,
            live_pair(),
            assess=lambda card, model: {"pass": True, "reason": "ok"},
            implement=implement,
            critique=lambda card, model, work: {
                "pass": True,
                "reason": "Die Datei trägt die Abnahme.",
                "findings": ["Pfad bleibt erhalten."],
            },
            follow=True,
            card_id=13,
        )
        self.assertEqual(deck.where(13), stack_name("approved"))
        self.assertIn("Ein Arbeitsergebnis fehlt.", seen["todos"])
        self.assertEqual([item["to"] for item in actions], [
            stack_name("running"),
            stack_name("waiting_review"),
            stack_name("approved"),
        ])

    def test_unreachable_implementer_stays_in_running(self) -> None:
        deck = MemoryDeck()
        deck.add(stack_name("running"), {"id": 15, "title": "FACT-003 — Worktree", "description": SPEC, "order": 0})
        run_pipeline(
            deck,
            live_pair(),
            assess=lambda card, model: {"pass": True, "reason": "ok"},
            implement=lambda card, model, todos="": {
                "ok": False,
                "files": [],
                "summary": "",
                "errors": ["kein Modell erreichbar: kiara http://127.0.0.1:8080/v1: timed out"],
            },
            critique=lambda card, model, work: {"pass": True, "reason": "ok", "findings": []},
            card_id=15,
        )
        self.assertEqual(deck.where(15), stack_name("running"))
        self.assertIn("127.0.0.1:8080", deck.comments[15][-1])
        self.assertIn("flaps prüft", deck.comments[15][-1])

    def test_third_failure_blocks(self) -> None:
        deck = MemoryDeck()
        deck.add(stack_name("waiting_review"), {"id": 14, "title": "FACT-020", "description": SPEC, "order": 0})
        deck.add_comment(14, "Implementierer (kiara): Arbeitsergebnis für FACT-020.\nDateien: hello.py\nZusammenfassung: Hallo.")
        deck.add_comment(14, "Prüfer (flaps): Rückgabe an den Implementierer.\nOffene Punkte:\n- erste")
        deck.add_comment(14, "Prüfer (flaps): Rückgabe an den Implementierer.\nOffene Punkte:\n- zweite")
        run_pipeline(
            deck,
            live_pair(),
            assess=lambda card, model: {"pass": True, "reason": "ok"},
            implement=lambda card, model, todos="": {"ok": True, "files": ["a.py"], "summary": "x", "errors": []},
            critique=lambda card, model, work: {"pass": False, "reason": "weiterhin offen", "findings": ["immer noch falsch"]},
            card_id=14,
        )
        self.assertEqual(deck.where(14), stack_name("blocked"))

    def test_dry_run_writes_nothing(self) -> None:
        deck = MemoryDeck()
        deck.add(stack_name("backlog"), {"id": 11, "title": "FACT-018", "description": SPEC, "order": 0})
        actions = run_pipeline(
            deck,
            live_pair(),
            assess=lambda card, model: {"pass": True, "reason": "ok"},
            implement=lambda card, model, todos="": {"ok": True, "files": ["a.py"], "summary": "x", "errors": []},
            critique=lambda card, model, work: {"pass": True, "reason": "ok", "findings": []},
            dry_run=True,
            follow=True,
        )
        self.assertEqual(deck.where(11), stack_name("backlog"))
        self.assertEqual(deck.comments, {})
        self.assertFalse(actions[0]["moved"])

    def test_incomplete_spec_stays_in_neu(self) -> None:
        deck = MemoryDeck()
        deck.add(stack_name("backlog"), {"id": 12, "title": "FACT-019", "description": "## Goal\n\nNur ein Ziel.\n", "order": 0})
        run_pipeline(
            deck,
            live_pair(),
            assess=lambda card, model: {"pass": True, "reason": "soll nicht reichen"},
            implement=lambda card, model, todos="": {"ok": True, "files": ["a.py"], "summary": "x", "errors": []},
            critique=lambda card, model, work: {"pass": True, "reason": "ok", "findings": []},
            card_id=12,
        )
        self.assertEqual(deck.where(12), stack_name("backlog"))
        self.assertIn("Pflichtabschnitt fehlt", deck.comments[12][0])

    def test_roles_keep_done_closed(self) -> None:
        with self.assertRaises(PolicyError):
            check_transition("reviewer", stack_name("waiting_review"), stack_name("done"))
        with self.assertRaises(PolicyError):
            check_transition("runner", stack_name("waiting_review"), stack_name("approved"))
        with self.assertRaises(PolicyError):
            check_transition("reviewer", stack_name("approved"), stack_name("done"))


if __name__ == "__main__":
    unittest.main()
