"""Besitzer einer Deck-Karte muss als uid in den Schreibaufruf."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from deck import owner_uid  # noqa: E402


class OwnerUidTest(unittest.TestCase):
    def test_dict_owner_becomes_uid(self) -> None:
        owner = {"uid": "stefan", "primaryKey": "stefan", "displayname": "Stefan", "type": 0}
        self.assertEqual(owner_uid(owner, "factory-runner"), "stefan")

    def test_primary_key_is_used_when_uid_is_missing(self) -> None:
        self.assertEqual(owner_uid({"primaryKey": "factory-runner"}, "stefan"), "factory-runner")

    def test_string_owner_stays(self) -> None:
        self.assertEqual(owner_uid("stefan", "factory-runner"), "stefan")

    def test_missing_owner_uses_fallback(self) -> None:
        self.assertEqual(owner_uid(None, "factory-runner"), "factory-runner")
        self.assertEqual(owner_uid({}, "factory-runner"), "factory-runner")


if __name__ == "__main__":
    unittest.main()
