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

## Dependencies

keine
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

    def update_description(self, card: dict, description: str) -> None:
        card["description"] = description

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
        self.assertIn("Ein anderes Modell prüft", deck.comments[15][-1])

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

    def test_incomplete_spec_is_completed_and_records_dependency(self) -> None:
        deck = MemoryDeck()
        deck.add(stack_name("backlog"), {"id": 19, "title": "FACT-001 — Schema", "description": SPEC, "order": 0})
        deck.add(stack_name("backlog"), {"id": 12, "title": "FACT-019", "description": "## Goal\n\nNur ein Ziel.\n", "order": 1})

        def prepare(card, model, catalog):
            self.assertIn("FACT-001", catalog)
            return {"usable": True, "description": SPEC, "questions": [], "dependencies": ["FACT-001", "FACT-999"]}

        run_pipeline(
            deck,
            live_pair(),
            assess=lambda card, model: {"pass": True, "reason": "soll nicht entscheiden"},
            prepare=prepare,
            implement=lambda card, model, todos="": {"ok": True, "files": ["a.py"], "summary": "x", "errors": []},
            critique=lambda card, model, work: {"pass": True, "reason": "ok", "findings": []},
            card_id=12,
        )
        self.assertEqual(deck.where(12), stack_name("ready"))
        self.assertIn("FACT-001", deck.comments[12][0])
        self.assertNotIn("FACT-999", deck.comments[12][0])
        self.assertIn("- FACT-001", [item for item in deck.stacks[stack_name("ready")] if item["id"] == 12][0]["description"])

    def test_open_question_stays_in_neu(self) -> None:
        deck = MemoryDeck()
        deck.add(stack_name("backlog"), {"id": 12, "title": "FACT-019", "description": "## Goal\n\nNur ein Ziel.\n", "order": 0})

        def prepare(card, model, catalog):
            return {"usable": True, "description": SPEC, "questions": ["Welches Repository ist gemeint?"], "dependencies": []}

        run_pipeline(
            deck,
            live_pair(),
            assess=lambda card, model: {"pass": True, "reason": "ok"},
            prepare=prepare,
            implement=lambda card, model, todos="": {"ok": True, "files": ["a.py"], "summary": "x", "errors": []},
            critique=lambda card, model, work: {"pass": True, "reason": "ok", "findings": []},
            card_id=12,
        )
        self.assertEqual(deck.where(12), stack_name("backlog"))
        self.assertIn("Welches Repository ist gemeint?", deck.comments[12][0])
        self.assertNotIn(stack_name("blocked"), deck.where(12))

    def test_summary_without_new_files_goes_to_review(self) -> None:
        deck = MemoryDeck()
        deck.add(stack_name("running"), {"id": 20, "title": "FACT-006 — Audit", "description": SPEC, "order": 0})
        run_pipeline(
            deck,
            live_pair(),
            assess=lambda card, model: {"pass": True, "reason": "ok"},
            implement=lambda card, model, todos="": {
                "ok": True,
                "files": [],
                "summary": "The factory.py already contained a complete audit log. No changes needed.",
                "errors": [],
            },
            critique=lambda card, model, work: {"pass": True, "reason": "ok", "findings": []},
            card_id=20,
        )
        self.assertEqual(deck.where(20), stack_name("waiting_review"))
        self.assertIn("keine neuen Dateien", deck.comments[20][-1])
        self.assertIn("already contained", deck.comments[20][-1])

    def test_unreadable_review_does_not_block(self) -> None:
        deck = MemoryDeck()
        deck.add(stack_name("waiting_review"), {"id": 21, "title": "FACT-006", "description": SPEC, "order": 0})
        deck.add_comment(21, "Implementierer (kiara): Arbeitsergebnis für FACT-006.\nDateien: factory.py\nZusammenfassung: Audit.")
        deck.add_comment(21, "Prüfer (flaps): Rückgabe an den Implementierer.\nOffene Punkte:\n- erste")
        deck.add_comment(21, "Prüfer (flaps): Rückgabe an den Implementierer.\nOffene Punkte:\n- zweite")
        run_pipeline(
            deck,
            live_pair(),
            assess=lambda card, model: {"pass": True, "reason": "ok"},
            implement=lambda card, model, todos="": {"ok": True, "files": ["a.py"], "summary": "x", "errors": []},
            critique=lambda card, model, work: {"pass": False, "reason": "Antwort war kein JSON", "findings": ["Antwort war kein JSON"]},
            card_id=21,
        )
        self.assertEqual(deck.where(21), stack_name("waiting_review"))
        self.assertIn("nicht als Rückgabe", deck.comments[21][-1])

    def test_open_dependency_keeps_ready_card(self) -> None:
        deck = MemoryDeck()
        deck.add(stack_name("backlog"), {"id": 29, "title": "FACT-001 — Schema", "description": SPEC, "order": 0})
        waiting = SPEC.replace("keine", "- FACT-001")
        deck.add(stack_name("ready"), {"id": 30, "title": "FACT-002 — Runner", "description": waiting, "order": 0})
        called = {"implement": False}

        def implement(card, model, todos=""):
            called["implement"] = True
            return {"ok": True, "files": ["a.py"], "summary": "x", "errors": []}

        run_pipeline(
            deck,
            live_pair(),
            assess=lambda card, model: {"pass": True, "reason": "ok"},
            implement=implement,
            critique=lambda card, model, work: {"pass": True, "reason": "ok", "findings": []},
            card_id=30,
        )
        self.assertFalse(called["implement"])
        self.assertEqual(deck.where(30), stack_name("ready"))
        self.assertIn("FACT-001 liegt in", deck.comments[30][-1])

    def test_open_dependency_blocks_approval(self) -> None:
        deck = MemoryDeck()
        deck.add(stack_name("running"), {"id": 29, "title": "FACT-001 — Schema", "description": SPEC, "order": 0})
        waiting = SPEC.replace("keine", "- FACT-001")
        deck.add(stack_name("waiting_review"), {"id": 30, "title": "FACT-002 — Runner", "description": waiting, "order": 0})
        deck.add_comment(30, "Implementierer (kiara): Arbeitsergebnis für FACT-002.\nDateien: runner.py\nZusammenfassung: Lauf.")
        run_pipeline(
            deck,
            live_pair(),
            assess=lambda card, model: {"pass": True, "reason": "ok"},
            implement=lambda card, model, todos="": {"ok": True, "files": ["a.py"], "summary": "x", "errors": []},
            critique=lambda card, model, work: {"pass": True, "reason": "soll nicht freigeben", "findings": []},
            card_id=30,
        )
        self.assertEqual(deck.where(30), stack_name("waiting_review"))
        self.assertIn("offene Abhängigkeiten", deck.comments[30][-1])

    def test_hathi_reviews_when_flaps_is_absent(self) -> None:
        deck = MemoryDeck()
        deck.add(stack_name("waiting_review"), {"id": 16, "title": "FACT-021", "description": SPEC, "order": 0})
        deck.add_comment(16, "Implementierer (kiara): Arbeitsergebnis für FACT-021.\nDateien: hello.py\nZusammenfassung: Hallo.")
        actions = run_pipeline(
            deck,
            [("kiara", {"type": "local"}), ("hathi", {"type": "local", "model": "swift-1.5-iq2_xs"})],
            assess=lambda card, model: {"pass": True, "reason": "ok"},
            implement=lambda card, model, todos="": {"ok": True, "files": ["hello.py"], "summary": "x", "errors": []},
            critique=lambda card, model, work: {"pass": True, "reason": "Die Datei trägt die Abnahme.", "findings": []},
            card_id=16,
        )
        self.assertEqual(actions[0]["model"], "hathi")
        self.assertEqual(deck.where(16), stack_name("approved"))
        self.assertIn("Prüfer (hathi)", deck.comments[16][-1])

    def test_hathi_implements_when_kiara_is_absent(self) -> None:
        deck = MemoryDeck()
        deck.add(stack_name("ready"), {"id": 17, "title": "FACT-022", "description": SPEC, "order": 0})
        actions = run_pipeline(
            deck,
            [("flaps", {"type": "local"}), ("hathi", {"type": "local", "model": "swift-1.5-iq2_xs"})],
            assess=lambda card, model: {"pass": True, "reason": "ok"},
            implement=lambda card, model, todos="": {"ok": True, "files": ["hello.py"], "summary": "von hathi", "errors": []},
            critique=lambda card, model, work: {"pass": True, "reason": "ok", "findings": []},
            follow=True,
            card_id=17,
        )
        self.assertEqual([item["model"] for item in actions], ["hathi", "flaps"])
        self.assertEqual(deck.where(17), stack_name("approved"))

    def test_hathi_stays_unused_when_kiara_and_flaps_answer(self) -> None:
        deck = MemoryDeck()
        deck.add(stack_name("ready"), {"id": 18, "title": "FACT-023", "description": SPEC, "order": 0})
        actions = run_pipeline(
            deck,
            [
                ("kiara", {"type": "local"}),
                ("flaps", {"type": "local"}),
                ("hathi", {"type": "local", "model": "swift-1.5-iq2_xs"}),
            ],
            assess=lambda card, model: {"pass": True, "reason": "ok"},
            implement=lambda card, model, todos="": {"ok": True, "files": ["hello.py"], "summary": "x", "errors": []},
            critique=lambda card, model, work: {"pass": True, "reason": "ok", "findings": []},
            card_id=18,
        )
        self.assertEqual(actions[0]["model"], "kiara")
        self.assertNotIn("hathi", [item["model"] for item in actions])

    def test_roles_keep_done_closed(self) -> None:
        with self.assertRaises(PolicyError):
            check_transition("reviewer", stack_name("waiting_review"), stack_name("done"))
        with self.assertRaises(PolicyError):
            check_transition("runner", stack_name("waiting_review"), stack_name("approved"))
        with self.assertRaises(PolicyError):
            check_transition("reviewer", stack_name("approved"), stack_name("done"))


class DeckOwnerSerializationTest(unittest.TestCase):
    """deck.py: Card-PUTs senden owner als UID-String, nie als dict (HTTP-400-Fix)."""

    def _deck(self):
        import types

        from deck import DeckClient

        cred = types.SimpleNamespace(
            base_url="https://192.168.5.46/",
            tls_verify=False,
            user="hermes",
            secret="secret",
            source="basic",
        )
        deck = DeckClient(cred, 1)
        requests = []

        def fake_request(method, path, body):
            requests.append((method, path, dict(body)))
            return {}

        deck._request = fake_request
        return deck, requests

    def _card(self, owner):
        card = {
            "id": 102,
            "stackId": 21,
            "title": "FACT-006",
            "type": "plain",
            "order": 0,
            "description": "alt",
        }
        card["owner"] = owner
        return card

    def test_update_description_sends_uid_string_not_dict(self):
        deck, requests = self._deck()
        deck.update_description(
            self._card({"uid": "stefan", "primaryKey": "stefan", "type": 0}), "neu"
        )
        body = requests[-1][2]
        self.assertEqual(body["owner"], "stefan")
        self.assertIsInstance(body["owner"], str)
        self.assertNotIsInstance(body["owner"], dict)

    def test_update_description_no_owner_falls_back_to_user(self):
        deck, requests = self._deck()
        deck.update_description(self._card(None), "neu")
        body = requests[-1][2]
        self.assertEqual(body["owner"], "hermes")
        self.assertIsInstance(body["owner"], str)

    def test_update_description_numeric_string_uid(self):
        """Realistic Deck uid is a numeric string (e.g. '42'), returned as-is."""
        deck, requests = self._deck()
        deck.update_description(self._card({"uid": "42"}), "neu")
        body = requests[-1][2]
        self.assertEqual(body["owner"], "42")
        self.assertIsInstance(body["owner"], str)

    def test_update_description_non_string_uid_falls_back_to_user(self):
        """A non-string uid (e.g. int) is not a real Deck uid -> fallback."""
        deck, requests = self._deck()
        deck.update_description(self._card({"uid": 42}), "neu")
        body = requests[-1][2]
        self.assertEqual(body["owner"], "hermes")
        self.assertIsInstance(body["owner"], str)


    def test_owner_in_changes_is_converted_to_uid(self):
        """PR#9's guard: a later owner override (passed via changes) is also
        converted to a uid string, never left as a dict (HTTP 400)."""
        deck, requests = self._deck()
        card = self._card({"uid": "stefan", "primaryKey": "stefan", "type": 0})
        deck._update_card(
            card,
            {"description": "neu", "owner": {"uid": "other", "primaryKey": "other"}},
        )
        body = requests[-1][2]
        self.assertEqual(body["owner"], "other")
        self.assertIsInstance(body["owner"], str)
        self.assertNotIsInstance(body["owner"], dict)

if __name__ == "__main__":
    unittest.main()
