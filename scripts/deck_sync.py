#!/usr/bin/env python3
"""FACT-009: Deck-Adapter — importiert "Ready"-Cards in die lokale Datei-Queue.

Liest Karten vom Nextcloud-Deck (Board "Software Factory", Stack "Ready") und
materialisiert sie als lokale Markdown-Tickets in `tickets/new`.

Verwendung:
    python3 deck_sync.py --once            # einmal importieren (Default)
    python3 deck_sync.py --once --dry-run  # nur anzeigen, nichts schreiben
    python3 deck_sync.py --once --board 7 --stack "Ready"

Regeln:
- Keine Card-Verschiebung, kein Writeback an den Deck (nur Lesen).
- Keine Secrets im Repo: Credentials kommen aus OUTSIDE (.hermes/config).
- Keine Code-Execution aus Kartentext (Text wird nur als Text geschrieben).
- Dedup über state/imported.json (nach card_id).

Auth:
- HTTP Basic Auth mit Service-User + App-Password (deck-auth.env).
- Kein OAuth2-Client-Flow, kein Browser, kein Token-Refresh.

Exit-Codes:
    0  Erfolg (auch 0 importierte Karten)
    2  Fehler (Auth/Deck API nicht erreichbar, Stack nicht gefunden, ...)
"""
from __future__ import annotations
import argparse
import base64
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

FACTORY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TICKETS_NEW = os.path.join(FACTORY_DIR, "tickets", "new")
STATE_DIR = os.path.join(FACTORY_DIR, "state")
STATE_FILE = os.path.join(STATE_DIR, "imported.json")

# Credentials OUTSIDE der Factory (keine Secrets im Repo)
CONFIG_BASE = "/home/kiara/.hermes/config/software-factory"
DECK_ENV = os.path.join(CONFIG_BASE, "deck-auth.env")  # DECK_USERNAME + DECK_APP_PASSWORD
NC = "https://192.168.5.46"

BOARD_ID = 7
STACK_ID_DEFAULT = 22
STACK_TITLE_DEFAULT = "Ready"  # matcht "Ready / Bereit"


# --- HTTP / Auth -----------------------------------------------------------
def _ctx() -> ssl.SSLContext:
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def http(method: str, path: str, headers: dict = None, data: bytes = None):
    """Führt ein HTTP-Request aus. Liefert (status, body) zurück (kein Throw)."""
    h = dict(headers or {})
    r = urllib.request.Request(NC + path, method=method, data=data, headers=h)
    try:
        resp = urllib.request.urlopen(r, context=_ctx(), timeout=30)
        return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
        except Exception:
            body = str(getattr(e, "reason", e))
        return e.code, body
    except urllib.error.URLError as e:
        return (getattr(e, "code", 0) or 0), str(e)
    except Exception as e:
        return 0, str(e)


def _load_env() -> dict:
    """Lädt DECK_USERNAME / DECK_APP_PASSWORD aus deck-auth.env.
    Wert: nur umgebende identische Anführungszeichen + Whitespace werden
    entfernt — innere Zeichen (z. B. %, $, *) bleiben exakt erhalten."""
    env: dict = {}
    try:
        with open(DECK_ENV) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                    v = v[1:-1]
                env[k.strip()] = v
    except OSError:
        pass
    return env


def get_auth():
    """Liefert (headers or None, status_string). Basic-Auth aus deck-auth.env."""
    env = _load_env()
    user = env.get("DECK_USERNAME", "").strip()
    pwd = env.get("DECK_APP_PASSWORD", "").strip()
    if not user:
        return None, "username fehlt in deck-auth.env (DECK_USERNAME)"
    if not pwd:
        return None, "App-Passwort fehlt in deck-auth.env (DECK_APP_PASSWORD) — bitte über Nextcloud erzeugen"
    token = base64.b64encode(f"{user}:{pwd}".encode("utf-8")).decode("ascii")
    h = {
        "Authorization": "Basic " + token,
        "OCS-APIRequest": "true",
        "Content-Type": "application/json",
    }
    return h, f"Basic-Auth ok ({user})"


# --- State (Dedup) ---------------------------------------------------------
def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# --- Mapping (Deck-Card -> lokales Ticket) ---------------------------------
def make_filename(card_id: int, title: str) -> str:
    """Normales, kollision-sicheres Dateinamen aus card_id + title."""
    title = (title or "").strip()
    m = re.match(r"\s*FACT-(\d{3,})", title)
    if m:
        return f"FACT-{m.group(1)}.md"
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]
    slug = f"{slug}-{card_id}" if slug else f"card-{card_id}"
    return f"{slug}.md"


def find_stack(stacks: list, match: str, stack_id: int = None):
    """Aktiven Stack finden: per Titel-Substring (case-insensitive) oder Stack-Id."""
    active = [s for s in stacks if not s.get("deletedAt")]
    match_l = (match or "").strip().lower()
    if match_l:
        for s in active:
            if match_l in (s.get("title") or "").lower():
                return s
    if stack_id is not None:
        for s in active:
            if s.get("id") == stack_id:
                return s
    return None


def build_content(card: dict, stack: dict) -> str:
    """Lokales Ticket-Text: normalisierte Title + Description (nur Text, kein Exec)."""
    title = (card.get("title") or "").strip()
    desc = (card.get("description") or "").strip()
    labels = [ (l or {}).get("title") or "" for l in (card.get("labels") or []) ]
    labels = [l for l in labels if l]
    lines = [f"# {title}", ""]
    lines.append(
        f"<!-- source: nextcloud-deck board={stack.get('boardId')} "
        f"stack=\"{stack.get('title')}\" card_id={card.get('id')} -->"
    )
    if labels:
        lines.append(f"<!-- labels: {', '.join(labels)} -->")
    lines.append("")
    if desc:
        lines.append(desc)
    return "\n".join(lines).rstrip() + "\n"


# --- Main -------------------------------------------------------------------
def main(argv: list = None) -> int:
    ap = argparse.ArgumentParser(description="Importiert Deck-Ready-Cards in die Datei-Queue.")
    ap.add_argument("--once", action="store_true", default=True,
                    help="einmal ausführen und beenden (Default)")
    ap.add_argument("--dry-run", action="store_true",
                    help="nur anzeigen, was importiert würde; nichts schreiben")
    ap.add_argument("--board", type=int, default=BOARD_ID,
                    help=f"Deck-Board-ID (Default {BOARD_ID})")
    ap.add_argument("--stack", type=str, default=STACK_TITLE_DEFAULT,
                    help=f"Stack-Titel zu matchen (Default '{STACK_TITLE_DEFAULT}')")
    args = ap.parse_args(argv)

    h, auth_status = get_auth()
    if h is None:
        print(f"ERROR: {auth_status}", file=sys.stderr)
        return 2

    st, body = http("GET",
        f"/index.php/apps/deck/api/v1.0/boards/{args.board}/stacks",
        headers=h)
    if st != 200:
        print(f"ERROR: Deck API nicht erreichbar (HTTP {st}): {body[:200]}", file=sys.stderr)
        return 2
    try:
        stacks = json.loads(body)
    except json.JSONDecodeError as e:
        print(f"ERROR: Stack-Listung unlesbar: {e}", file=sys.stderr)
        return 2

    stack = find_stack(stacks, args.stack, STACK_ID_DEFAULT)
    if not stack:
        print(f"ERROR: aktiver Stack mit Titel/Id '{args.stack}' nicht gefunden "
              f"(Board {args.board}).")
        return 2

    cards = [c for c in stack.get("cards", []) if not c.get("deletedAt")]
    if not cards:
        print(f"Stack '{stack.get('title')}' hat keine aktiven Karten. Nichts zu importieren.")
        return 0

    state = load_state()
    os.makedirs(TICKETS_NEW, exist_ok=True)
    imported = 0
    for card in cards:
        card_id = card.get("id")
        sid = str(card_id)  # State-Keys als String (JSON-Standard), einheitlich
        title = card.get("title") or "(keine Titel)"
        filename = make_filename(card_id, title)
        content = build_content(card, stack)
        path = os.path.join(TICKETS_NEW, filename)
        # Kollision (anderes card, gleicher Slug) -> card_id ins Name einbauen
        if os.path.exists(path) and sid not in state:
            base, ext = os.path.splitext(path)
            filename = f"{base}-{card_id}{ext}"
            path = os.path.join(TICKETS_NEW, filename)
        if args.dry_run:
            print(f"[dry-run] card {card_id} -> {path}")
            continue
        if sid in state:
            print(f"[skip] card {card_id} bereits importiert -> {state[sid].get('file')}")
            continue
        with open(path, "w") as f:
            f.write(content)
        state[sid] = {"file": filename, "title": title,
                      "imported_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        save_state(state)
        imported += 1
        print(f"[import] card {card_id} -> {path}")

    print(f"Fertig. importiert={imported} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())