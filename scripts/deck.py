#!/usr/bin/env python3
"""Nextcloud-Deck-Adapter mit Rollenprüfung vor jedem Schreibzugriff."""

from __future__ import annotations

import argparse
import base64
import json
import socket
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory_common import (
    Credentials,
    FactoryError,
    PolicyError,
    actor_name,
    append_audit,
    assert_no_secrets,
    check_transition,
    factory_config,
    load_credentials,
    policy_for,
)


def owner_uid(owner: Any, fallback: str = "") -> str:
    """Deck liefert den Besitzer als Objekt. Der Schreibaufruf erwartet die uid."""
    if isinstance(owner, dict):
        uid = owner.get("uid") or owner.get("primaryKey") or ""
        if isinstance(uid, str) and uid.strip():
            return uid.strip()
    elif isinstance(owner, str) and owner.strip():
        return owner.strip()
    return fallback


class DeckClient:
    def __init__(self, credentials: Credentials, board_id: int) -> None:
        self.credentials = credentials
        self.board_id = board_id
        self.prefix = f"{credentials.base_url}/index.php/apps/deck/api/v1.0"
        self.ssl_context = None if credentials.tls_verify else ssl._create_unverified_context()

    def stacks(self) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/boards/{self.board_id}/stacks")
        if not isinstance(payload, list):
            raise FactoryError("Deck hat keine Stack-Liste geliefert")
        return payload

    def cards(self, stack_title: str) -> list[dict[str, Any]]:
        stack = self.stack_by_title(stack_title)
        cards = stack.get("cards") or []
        if not isinstance(cards, list):
            raise FactoryError(f"Stack „{stack_title}“ enthält keine Kartenliste")
        for card in cards:
            card.setdefault("stackId", stack.get("id"))
        return cards

    def stack_by_title(self, title: str) -> dict[str, Any]:
        for stack in self.stacks():
            if str(stack.get("title")) == title:
                return stack
        known = ", ".join(str(stack.get("title")) for stack in self.stacks())
        raise FactoryError(f"Stack „{title}“ fehlt auf dem Board. Vorhanden: {known}")

    def move_card(self, card: dict[str, Any], target_title: str) -> None:
        card_id = int(card["id"])
        target = self.stack_by_title(target_title)
        target_id = int(target["id"])
        # Deck-Issue #6830/#7933: reorder() liest den Target-Stack aus dem
        # URL-Pfad (Route-Parameter {stackId}); der stackId-Wert im Body
        # wird ignoriert. Target-Stack muss also in den Pfad.
        path = f"/boards/{self.board_id}/stacks/{target_id}/cards/{card_id}/reorder"
        try:
            self._request("PUT", path, {"order": 0, "stackId": target_id})
        except FactoryError as exc:
            if "HTTP 404" not in str(exc) and "HTTP 405" not in str(exc):
                raise
            self._update_card(card, {"stackId": target_id})

    def update_description(self, card: dict[str, Any], description: str) -> None:
        self._update_card(card, {"description": description})

    def list_comments(self, card_id: int) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            f"/cards/{int(card_id)}/comments",
            prefix=self._ocs_prefix(),
        )
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def add_comment(self, card_id: int, message: str) -> Any:
        text = message.strip()[:1000]
        assert_no_secrets(text, "kommentar")
        return self._request(
            "POST",
            f"/cards/{int(card_id)}/comments",
            {"message": text},
            prefix=self._ocs_prefix(),
        )

    def _ocs_prefix(self) -> str:
        # Kommentare liegen nicht unter index.php/apps/deck. Dort antwortet
        # Nextcloud mit HTTP 405. Die OCS-Route ist die gültige.
        return self.credentials.base_url.rstrip("/") + "/ocs/v2.php/apps/deck/api/v1.0"

    def _update_card(self, card: dict[str, Any], changes: dict[str, Any]) -> None:
        stack_id = int(card["stackId"])
        card_id = int(card["id"])
        body = {
            "title": card.get("title") or "",
            "type": card.get("type") or "plain",
            "order": card.get("order") or 0,
            "description": card.get("description") or "",
            "owner": owner_uid(card.get("owner"), self.credentials.user),
        }
        body.update(changes)
        # Ein nachgereichtes Owner-Objekt würde Deck wieder mit HTTP 400 ablehnen.
        if "owner" in body:
            body["owner"] = owner_uid(body.get("owner"), self.credentials.user)
        path = f"/boards/{self.board_id}/stacks/{stack_id}/cards/{card_id}"
        self._request("PUT", path, body)

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        prefix: str | None = None,
    ) -> Any:
        data = None
        headers = {"OCS-APIRequest": "true", "Accept": "application/json"}
        if self.credentials.source == "oauth":
            headers["Authorization"] = f"Bearer {self.credentials.secret}"
        else:
            basic = base64.b64encode(
                f"{self.credentials.user}:{self.credentials.secret}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {basic}"
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            (prefix or self.prefix) + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=120, context=self.ssl_context) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise FactoryError(f"Nextcloud Deck antwortet mit HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise FactoryError(self._reachability_message(exc)) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise FactoryError(
                "Nextcloud hat 120 Sekunden nicht geantwortet. "
                "Nach mehreren fehlgeschlagenen Anmeldungen bremst Nextcloud die IP aus. "
                "Einige Minuten warten und den Aufruf einmal wiederholen."
            ) from exc
        if not raw:
            return None
        payload = json.loads(raw.decode())
        if isinstance(payload, dict) and isinstance(payload.get("ocs"), dict):
            return payload["ocs"].get("data")
        return payload

    def _reachability_message(self, exc: urllib.error.URLError) -> str:
        reason = exc.reason
        if isinstance(reason, socket.gaierror):
            return (
                f"Der Host in NC_BASE wird nicht aufgelöst ({self.credentials.base_url}). "
                "Trag NC_BASE=https://192.168.5.46 ein. "
                "wilhelmscloud allein funktioniert nur, wenn die Suchdomain fritz.box gesetzt ist."
            )
        if isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(reason):
            return (
                "Das Nextcloud-Zertifikat ist selbstsigniert und enthält keinen Hostnamen. "
                "Setze in der Env-Datei NC_TLS_VERIFY=false."
            )
        return f"Nextcloud ist nicht erreichbar: {reason}"


def client_or_exit() -> DeckClient:
    credentials = load_credentials()
    if credentials is None:
        raise FactoryError(
            "Keine Nextcloud-Zugangsdaten. Lege /etc/factory/runner.env an "
            "oder setze NC_BASE, NC_USER und NC_APP_PASSWORD. "
            "Der Hermes-Token auf kiara wird hier nicht verwendet."
        )
    board_id = int(factory_config()["board"]["id"])
    return DeckClient(credentials, board_id)


def find_card(deck: DeckClient, card_id: int) -> tuple[dict[str, Any], str]:
    for stack in deck.stacks():
        for card in stack.get("cards") or []:
            if int(card["id"]) == card_id:
                return card, str(stack.get("title"))
    raise FactoryError(f"Karte {card_id} nicht auf dem Board gefunden")


def require_permission(role: str, flag: str) -> None:
    policy = policy_for(role)
    if not policy.get(flag):
        raise PolicyError(f"{role} darf diese Deck-Aktion nicht ausführen")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nextcloud Deck für die Software-Factory")
    parser.add_argument(
        "--role",
        default="runner",
        choices=("runner", "hermes", "observer", "reviewer"),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("auth-status", help="zeigt, ob Zugangsdaten vorhanden sind")
    sub.add_parser("stacks", help="Stacks des Boards auflisten")

    cards = sub.add_parser("cards", help="Karten eines Stacks auflisten")
    cards.add_argument("--stack", required=True)
    cards.add_argument("--validate", action="store_true", help="Prüft die Beschreibung gegen das Ticket-Schema")

    move = sub.add_parser("move", help="Karte in einen anderen Stack schieben")
    move.add_argument("--card", type=int, required=True)
    move.add_argument("--to", required=True)
    move.add_argument("--dry-run", action="store_true")

    describe = sub.add_parser("describe", help="Kartenbeschreibung ersetzen")
    describe.add_argument("--card", type=int, required=True)
    describe.add_argument("--file", required=True)
    describe.add_argument("--dry-run", action="store_true")

    comment = sub.add_parser("comment", help="Kommentar an eine Karte hängen")
    comment.add_argument("--card", type=int, required=True)
    comment.add_argument("--message", required=True)
    comment.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "auth-status":
            credentials = load_credentials()
            if credentials is None:
                print("Deck: keine Zugangsdaten konfiguriert")
                return 2
            print(f"Deck: Zugangsdaten vorhanden für {credentials.label()}")
            return 0
        deck = client_or_exit()
        if args.command == "stacks":
            require_permission(args.role, "can_read_board")
            for stack in deck.stacks():
                count = len(stack.get("cards") or [])
                print(f"{stack.get('title')}\tid={stack.get('id')}\tcards={count}")
            return 0
        if args.command == "cards":
            require_permission(args.role, "can_read_board")
            for card in deck.cards(args.stack):
                if not args.validate:
                    print(f"{card.get('id')}\t{card.get('title')}")
                    continue
                from validate_ticket import parse_ticket

                parsed, errors = parse_ticket(str(card.get("description") or ""))
                if not parsed.repo:
                    errors.append("Frontmatter-Feld repo fehlt")
                state = "vollständig" if not errors else "unvollständig"
                print(f"{card.get('id')}\t{state}\t{card.get('title')}")
                for error in errors:
                    print(f"  - {error}")
            return 0
        if args.command == "move":
            card, source = find_card(deck, args.card)
            check_transition(args.role, source, args.to)
            if args.dry_run:
                print(f"Dry-run: Karte {args.card} „{source}“ → „{args.to}“ als {args.role}")
                return 0
            deck.move_card(card, args.to)
            append_audit(
                {
                    "ticket": str(card.get("title") or args.card),
                    "event": "deck_move",
                    "from": source,
                    "to": args.to,
                    "actor": actor_name(args.role),
                    "role": args.role,
                    "message": f"Karte {args.card} verschoben",
                    "card_id": args.card,
                }
            )
            print(f"Verschoben: {args.card} „{source}“ → „{args.to}“")
            return 0
        if args.command == "describe":
            require_permission(args.role, "can_update_description")
            source_path = Path(args.file)
            if source_path.name.startswith(".env") or source_path.name.endswith(".env"):
                raise FactoryError("Umgebungsdateien werden nicht ins Deck geschrieben")
            description = source_path.read_text(encoding="utf-8")
            assert_no_secrets(description, "beschreibung")
            if args.dry_run:
                print(f"Dry-run: Beschreibung von Karte {args.card} würde ersetzt")
                return 0
            card, source = find_card(deck, args.card)
            deck.update_description(card, description)
            append_audit(
                {
                    "ticket": str(card.get("title") or args.card),
                    "event": "deck_description",
                    "from": source,
                    "to": source,
                    "actor": actor_name(args.role),
                    "role": args.role,
                    "message": f"Beschreibung von Karte {args.card} aktualisiert",
                    "card_id": args.card,
                }
            )
            print(f"Beschreibung aktualisiert: {args.card}")
            return 0
        if args.command == "comment":
            require_permission(args.role, "can_comment")
            if args.dry_run:
                print(f"Dry-run: Kommentar an Karte {args.card}")
                return 0
            deck.add_comment(args.card, args.message)
            print(f"Kommentar geschrieben: {args.card}")
            return 0
    except (FactoryError, PolicyError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("Unbekannter Befehl", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
