#!/usr/bin/env python3
"""
FACT-002: Runner — das Work-Engine / der zentrale Hub der Software-Factory.

Stationen (README.md):
    new -> ready -> running -> gate -> approved (Review-Station)
                                          (oder) -> blocked
    done: nur nach namentlicher menschlicher Freigabe (niemals automatisch)

Dieser Runner führt ein Ticket durch einen vollständigen, autonomen Zyklus:
    pick (tickets/new)
      -> VALIDATE   (schema/ticket.schema.json via validate_factory_schema.py)
      -> ROUTE      (Modell nach Aufgabe: kiara primary, flaps fallback,
                    OpenRouter als Ausnahme — Orchestrator-Entscheidung)
      -> IMPLEMENT  (Implementier-Agent, lokales Modell, Budget:
                    max_walltime / max_turns / max_files)
      -> CHECK      (UNABHÄNGIG: deterministische ## Checks-Commands +
                    scenario-basiertes Szenario-Judge — NIEMALS der
                    implementierende Agent)
      -> STATUS     (Station-Shift: running -> gate -> approved
                    oder blocked; kein automatisches done)
      -> REPORT     (Job-Report state/reports/<ticket>.json + Audit-Log
                    state/audit.log)
      -> (opt) DECK-WRITEBACK  (Deck-Karte in die neue Station schieben,
                    nur mit --deck-writeback)

Regeln (Constraints):
  - Nur lokale LLMs (kiara:8080 primary, flaps:8080 fallback).
  - OpenRouter = Ausnahme für bestimmte Task-Klassen (per Ticket-Hinweis
    "Router: openrouter" + OPENROUTER_API_KEY), nie der Default.
  - Budget wird hart erzwungen (Walltime/Turns/Files).
  - Checks laufen in einer eigenen, vom Implementer unabhängigen Station
    (Subprozesse + frischer LLM-Judge), nie vom implementierenden Agenten.
    Checks sind scenario-basiert, kein Vertrauen auf selbstgenerierte Tests.
  - Kein Cloud-Zugriff außer explizitem OpenRouter-Request.
  - Keine Secrets im Repo (Deck-Credentials aus .hermes/config).

Verwendung:
    python3 scripts/runner.py --once
    python3 scripts/runner.py --once --dry-run
    python3 scripts/runner.py --once --ticket tickets/new/FACT-XXX.md
    python3 scripts/runner.py --once --ticket tickets/new/FACT-XXX.md --deck-writeback

Exit-Codes:
    0  erfolgreich (mindestens ein Ticket verarbeitet)
    1  mindestens ein Ticket blockiert/failed
    2  Fehler (kein Ticket, fehlende Env, ...)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import time
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# --- Pfade -----------------------------------------------------------------
FACTORY_DIR = Path(__file__).resolve().parent.parent
TICKETS = FACTORY_DIR / "tickets"
WORK_ROOT = FACTORY_DIR / "work"
STATE = FACTORY_DIR / "state"
REPORTS = STATE / "reports"
AUDIT_LOG = STATE / "audit.log"
VALIDATOR = FACTORY_DIR / "scripts" / "validate_factory_schema.py"

# --- Deck (Nextcloud) ------------------------------------------------------
NC = "https://192.168.5.46"
BOARD_ID = 7
CONFIG_BASE = os.path.join(os.path.expanduser("~"), ".hermes", "config", "software-factory")
DECK_ENV = os.path.join(CONFIG_BASE, "deck-auth.env")

# --- LLM-Endpoints (OpenAI-kompatibel) -------------------------------------
MODELS = [
    {"type": "local", "name": "kiara", "url": "http://127.0.0.1:8080/v1", "model": "bonsai2-27b"},
    {"type": "local", "name": "flaps", "url": "http://192.168.5.20:8080/v1", "model": "strata"},
]
OPENROUTER_URL = "https://openrouter.ai/api/v1"
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct")

# --- Budget-Defaultwerte ---------------------------------------------------
DEFAULT_WALLTIME = 1800  # 30 min, falls Ticket nichts angibt
DEFAULT_TURNS = 20
DEFAULT_FILES = 15
LLM_MAX_TOKENS = 3072
LLM_TIMEOUT = 240        # pro LLM-Call (s)
RUN_TIMEOUT = 60         # pro Check-Subprozess (s)

# --- Deck-Station -> mögliche Stack-Titel (substring-match) -----------------
STATION_STACK_TITLES = {
    "new": ["Backlog", "Neu", "New", "To Do"],
    "ready": ["Ready", "Bereit"],
    "running": ["Running", "In Arbeit", "Working", "Arbeiten"],
    "gate": ["Waiting Review", "Review", "Gate", "Review"],
    "approved": ["Approved", "Freigegeben", "Freigabe", "Approved"],
    "done": ["Done", "Erledigt", "Finished", "Komplett", "Done"],
    "blocked": ["Blocked", "Failed", "Nicht gelöst", "Error", "Gestohnt"],
}


# =============================================================================
# Deck-HTTP / Auth (mirrors deck_sync.py)
# =============================================================================
def _ctx() -> ssl.SSLContext:
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def _load_env() -> dict:
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


def _deck_auth() -> dict:
    e = _load_env()
    user = e.get("DECK_USERNAME", "").strip()
    pwd = e.get("DECK_APP_PASSWORD", "").strip()
    if not user or not pwd:
        return {}
    token = base64.b64encode(f"{user}:{pwd}".encode("utf-8")).decode("ascii")
    return {"Authorization": "Basic " + token,
            "OCS-APIRequest": "true",
            "Content-Type": "application/json"}


def deck_http(method: str, path: str, headers: dict = None, data: bytes = None):
    """Führt ein Deck-API-Request aus. Liefert (status, body) ohne Throw."""
    h = dict(_deck_auth())
    h.update(headers or {})
    r = urllib.request.Request(NC + path, method=method, data=data, headers=h)
    try:
        resp = urllib.request.urlopen(r, context=_ctx(), timeout=30)
        return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            body = str(getattr(e, "reason", e))
        return e.code, body
    except urllib.error.URLError as e:
        return (getattr(e, "code", 0) or 0), str(e)
    except Exception as e:
        return 0, str(e)


def deck_stacks():
    """Liest alle aktiven Stacks: {Title: stack_id}."""
    s, body = deck_http("GET", f"/index.php/apps/deck/api/v1.0/boards/{BOARD_ID}/stacks")
    if s != 200:
        return {}
    try:
        data = json.loads(body)
    except Exception:
        return {}
    if isinstance(data, dict):
        data = data.get("data", [])
    out = {}
    for st in (data if isinstance(data, list) else []):
        if st.get("deletedAt"):
            continue
        name = (st.get("title") or st.get("name") or "").strip()
        sid = st.get("id")
        if name and sid is not None:
            out[name] = sid
    return out


def _deck_stacks_raw():
    """Liest die raw Stacks-Liste (mit Karten) zurück: list[stack-dict]."""
    s, body = deck_http("GET", f"/index.php/apps/deck/api/v1.0/boards/{BOARD_ID}/stacks")
    if s != 200:
        return []
    try:
        data = json.loads(body)
    except Exception:
        return []
    if isinstance(data, dict):
        data = data.get("data", [])
    return data if isinstance(data, list) else []


def _find_card(card_id, raw_stacks):
    """Findet die aktive Card (per id) in der raw-Stacks-Liste."""
    for st in raw_stacks:
        if st.get("deletedAt"):
            continue
        for c in st.get("cards", []):
            if c.get("id") == card_id:
                return c
    return None


def deck_move_card(card_id, stack_id, done=False):
    """Verschiebt die Card in den Stack. PUT + exakter ncdeck-Client-Payload (status, body)."""
    if not card_id or not stack_id:
        return -1, "fehlender card_id oder stack_id"
    card = _find_card(card_id, _deck_stacks_raw())
    if not card:
        return -1, f"card {card_id} nicht im Deck (Board {BOARD_ID}) gefunden"
    owner = card.get("owner")
    if isinstance(owner, dict):
        owner = owner.get("uid") or owner.get("primaryKey")
    payload = {
        "title": card.get("title", ""),
        "type": card.get("type", "plain"),
        "owner": owner,
        "description": card.get("description") or "",
        "order": 0,
        "duedate": card.get("duedate"),
        "deletedAt": card.get("deletedAt", 0) or 0,
        "archived": card.get("archived", False),
    }
    if done:
        payload["done"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    data = json.dumps(payload).encode("utf-8")
    s, body = deck_http(
        "PUT",
        f"/index.php/apps/deck/api/v1.0/boards/{BOARD_ID}/stacks/"
        f"{stack_id}/cards/{card_id}",
        data=data,
    )
    return s, body


def find_stack_title(stacks: dict, station: str):
    """Passt die lokale Station an einen Stack-Titel (substring)."""
    titles = STATION_STACK_TITLES.get(station, [])
    for t in titles:
        if not t:
            continue
        for name, sid in stacks.items():
            if name == t or t.lower() in name.lower() or name.lower() in t.lower():
                return sid
    return None


# =============================================================================
# Audit-Log
# =============================================================================
def audit(ticket_id, station, note, **kw):
    STATE.mkdir(parents=True, exist_ok=True)
    entry = {"ts": datetime.now().isoformat(timespec="seconds"),
             "ticket": ticket_id, "station": station, "note": note, **kw}
    try:
        with open(AUDIT_LOG, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


# =============================================================================
# Ticket-Parsing
# =============================================================================
def parse_ticket(text: str) -> dict:
    """Parsiert '## ' Sektionen in ein normalisiertes dict."""
    sections = {}
    order = []
    current = None
    buf = []
    for line in text.splitlines():
        m = re.match(r"^##\s+(.*)$", line.strip())
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
    norm = {}
    for k, v in sections.items():
        key = k.lower().strip()
        if key == "goal":
            norm["goal"] = v
        elif key == "success criteria" or key == "success_criteria":
            norm["success_criteria"] = v
        elif key in ("acceptance examples", "acceptance_examples", "acceptance"):
            norm["acceptance"] = v
        elif key == "forbidden":
            norm["forbidden"] = v
        elif key == "checks":
            norm["checks"] = v
        elif key == "budget":
            norm["budget"] = v
        elif key in ("router", "model"):
            norm["router"] = v
        elif key in ("cwd", "workdir"):
            norm["cwd"] = v
    return norm


def parse_kv_section(text: str) -> dict:
    kv = {}
    for line in text.splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if m:
            kv[m.group(1)] = m.group(2).strip()
    return kv


def parse_time_or_int(v: str):
    """Parsiert '15m' -> 900, '2h' -> 7200, '300' -> 300 (Sekunden)."""
    v = v.strip().lower()
    if not v:
        return None
    if v.isdigit():
        return int(v)
    m = re.match(r"^(\d+)(ms|h|m|s)?$", v)
    if m:
        n = int(m.group(1))
        u = m.group(2) or "s"
        return n * (1000 if u == "ms" else 1 if u == "s" else 60 if u == "m" else 3600)
    try:
        return int(v)
    except Exception:
        return None


def parse_budget(budget_text: str) -> dict:
    b = {"max_walltime": DEFAULT_WALLTIME, "max_turns": DEFAULT_TURNS,
         "max_files": DEFAULT_FILES}
    kv = parse_kv_section(budget_text or "")
    for k in b:
        val = kv.get(k)
        if val is None:
            continue
        if k == "max_walltime":
            b[k] = parse_time_or_int(val) or b[k]
        elif k == "max_files":
            try: b[k] = int(val)
            except Exception: pass
        elif k == "max_turns":
            try: b[k] = int(val)
            except Exception: pass
    return b


def extract_card_id(text: str):
    m = re.search(r"card_id=(\d+)", text or "")
    return m.group(1) if m else None


# =============================================================================
# Station-Shift
# =============================================================================
def shift_ticket(old_path, dest_station, ticket_id, note):
    """Bewegt die Ticket-Datei in die Ziel-Station, meldet (audit) und
    gibt den neuen Pfad zurück."""
    old_path = Path(old_path)
    dest_dir = TICKETS / dest_station
    dest_dir.mkdir(parents=True, exist_ok=True)
    newp = dest_dir / old_path.name
    if newp.exists() and not newp.resolve() == old_path.resolve():
        newp = dest_dir / f"{old_path.stem}-{uuid.uuid4().hex[:6]}{old_path.suffix}"
    shutil.move(str(old_path), str(newp))
    audit(ticket_id, dest_station, note)
    return newp


# =============================================================================
# Modell-Choice / LLM-Abfrage
# =============================================================================
def get_available_model(url: str, preferred: str):
    """Ollama OpenAI-kompatibel: GET /v1/models -> verfügbares Modell-Name."""
    try:
        req = urllib.request.Request(url.rstrip("/") + "/models", method="GET")
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
        models = [(m.get("id") or m.get("model")) for m in data.get("data", [])]
    except Exception:
        return None
    models = [m for m in models if m]
    if preferred in models:
        return preferred
    return models[0] if models else None


def choose_models(norm: dict):
    """Orchestrator-Entscheidung (nach Aufgabe): Liste (name, cfg), primary zuerst."""
    hint = (norm.get("router") or norm.get("model") or "").strip().lower()
    order = []
    if hint in ("openrouter", "openrouter.com", "cloud") and OPENROUTER_KEY:
        order.append(("openrouter", {"type": "openrouter", "url": OPENROUTER_URL,
                                     "model": OPENROUTER_MODEL, "key": OPENROUTER_KEY}))
    order.extend((cfg["name"], cfg) for cfg in MODELS)
    live = []
    for name, cfg in order:
        if cfg["type"] == "openrouter":
            live.append((name, cfg))
        else:
            model = get_available_model(cfg["url"], cfg["model"])
            if model:
                c = dict(cfg)
                c["model"] = model
                live.append((name, c))
    return live


def llm_call(name, cfg, messages, max_tokens=LLM_MAX_TOKENS, timeout=LLM_TIMEOUT, temperature=0.2):
    """OpenAI-kompatibler Chat-Completion. Gibt den Message-Content zurück."""
    if cfg["type"] == "openrouter":
        url = cfg["url"] + "/chat/completions"
        headers = {"Content-Type": "application/json",
                   "Authorization": "Bearer " + cfg["key"]}
        model = cfg["model"]
    else:
        url = cfg["url"].rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        model = cfg["model"]
    body = json.dumps({"model": model, "messages": messages, "temperature": temperature,
                       "max_tokens": max_tokens, "top_p": 1.0}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    with urllib.request.urlopen(req, context=_ctx(), timeout=timeout) as r:
        data = json.loads(r.read().decode())
    msg = data["choices"][0]["message"]
    # kiara antwortet in "content", flaps teils nur in "reasoning_content".
    return (msg.get("content") or msg.get("reasoning_content") or "").strip()


def llm_call_any(models, messages, max_tokens=LLM_MAX_TOKENS, timeout=LLM_TIMEOUT):
    """Probiert Modelle in Reihenfolge; (name, content) oder (None, None)."""
    for name, cfg in models:
        try:
            return name, llm_call(name, cfg, messages, max_tokens, timeout)
        except Exception:
            continue
    return None, None


def judge_models_for(implementer_model, models):
    """Für den unabhängigen Judge: bevorzugt ein Modell != Implementer."""
    alt = [m for m in models if m[0] != implementer_model]
    return alt if alt else models


# =============================================================================
# Implementier-Agent (Work-Loop)
# =============================================================================
SYSTEM_IMPLEMENTER = (
    "Du bist der IMPLEMENTIERER in einer lokalen Software-Factory (autonome "
    "Arbeitsumgebung, nur Python-Standardbibliothek, keine Cloud).\n"
    "Erstelle das Artefakt, das das Ticket verlangt, direkt in der aktuellen "
    "Workspace-Datei (alle Pfade relativ).\n"
    "Du hast ein kleines Toolkit. Du darfst pro Runde EXAKT einen der folgenden "
    "JSON-Aufrufe tun (nichts anderes, kein Prosa, keine Code-Blöcke):\n"
    '  {"tool":"write","args":{"path":"...","content":"..."}}  -> Datei anlegen/überschreiben\n'
    '  {"tool":"read","args":{"path":"..."}}  -> Datei lesen\n'
    '  {"tool":"run","args":{"cmd":"..."}}  -> Kommando ausführen (z. B. python3 ...)\n'
    '  {"tool":"list","args":{}}  -> Dateien auflisten\n'
    '  {"tool":"done","args":{"summary":"..."}}  -> fertig, am Ende\n'
    "Regeln:\n"
    "- Teste deinen Code mit `run`, bevor du `done` antwortest.\n"
    "- Erstelle nur die Dateien, die nötig sind (respektiere Budget max_files).\n"
    "- Mache den Code so, dass die CHECKS passgen.\n"
    "- Bei `done` gib eine kurze Zusammenfassung der Arbeit (1-3 Sätze).\n"
)


def build_ticket_block(norm: dict) -> str:
    b = []
    if norm.get("goal"):
        b.append("ZIEL:\n" + norm["goal"])
    if norm.get("success_criteria"):
        b.append("ERFOLGSKRITERIEN:\n" + norm["success_criteria"])
    if norm.get("acceptance"):
        b.append("AKzeptANZBEISPIELE:\n" + norm["acceptance"])
    if norm.get("forbidden"):
        b.append("VERBOTEN:\n" + norm["forbidden"])
    b.append("CHECKS (müssen am Ende passgen; werden von der Station, NICHT von dir "
             "ausgeführt):\n" + (norm.get("checks") or "(keine)"))
    return "\n\n".join([s for s in b if s])


def execute_tool(tool, a, cwd, files):
    """Führt ein Werkzeug aus (sandbox: cwd). (ausgabe, fehler) zurück."""
    cw = os.path.normpath(cwd)
    if tool == "write":
        p = os.path.normpath(os.path.join(cwd, a.get("path", "")))
        if not (p == cw or p.startswith(cw + os.sep)):
            return "blockiert: Pfad außerhalb Workspace", "write-path"
        os.makedirs(os.path.dirname(p) or cwd, exist_ok=True)
        content = a.get("content", "")
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            files.add(os.path.relpath(p, cw))
        except OSError as e:
            return "schreibfehler: " + str(e), "write-err"
        return f"geschrieben: {os.path.relpath(p, cw)}", None
    elif tool == "read":
        p = os.path.normpath(os.path.join(cwd, a.get("path", "")))
        if not (p == cw or p.startswith(cw + os.sep)):
            return "blockiert", "read-path"
        if not os.path.isfile(p):
            return "nicht gefunden", "read-missing"
        try:
            return open(p, encoding="utf-8").read()[:3000], None
        except Exception as e:
            return "fehlgeschlagen: " + str(e), "read"
    elif tool == "run":
        cmd = (a.get("cmd") or "").strip()
        if not cmd:
            return "leeres Kommando", "run"
        blocked = [r"rm\s+-r\s", r"\bshred\b", r"\bmkfs\b", r"\bwipefs\b",
                   r"\bformat\b", r"\bsudo\b", r"\bmkfifo\b", r"\btruncate\b",
                   r"\bmkfifo\b", r"\bblkid\b", r"\bgit\s+push\b", r"\bgit\s+merge\b"]
        if any(re.search(p, cmd, re.I) for p in blocked):
            return "blockiert: " + cmd[:200], "run-blocked"
        try:
            r = subprocess.run(cmd, shell=True, cwd=cwd, timeout=RUN_TIMEOUT,
                               capture_output=True, text=True)
            out = (r.stdout or "").strip()
            err = (r.stderr or "").strip()
            if r.returncode:
                out = (out + ("\n[stderr] " + err if err else ""))[:3000]
            return out, (f"exit {r.returncode}" if r.returncode else "exit 0")
        except subprocess.TimeoutExpired:
            return "", "timeout"
        except Exception as e:
            return "", "fehlgeschlagen: " + str(e)
    elif tool == "list":
        entries = []
        for root, dirs, files_ in os.walk(cwd):
            for fn in sorted(files_):
                rel = os.path.relpath(os.path.join(root, fn), cwd)
                try:
                    size = os.path.getsize(os.path.join(root, fn))
                except Exception:
                    size = "?"
                entries.append(f"{rel} ({size})")
        return "\n".join(entries[:200]) or "(leer)", None
    else:
        return "unbekanntes Werkzeug", f"tool {tool}"


def do_work(ticket_id, norm, models, budget, workdir):
    """Implementier-Agent: baut das Artefakt in workdir (Budget-beschränkt)."""
    os.makedirs(workdir, exist_ok=True)
    max_turns = int(budget.get("max_turns") or DEFAULT_TURNS)
    max_files = int(budget.get("max_files") or DEFAULT_FILES)
    walltime = int(budget.get("max_walltime") or DEFAULT_WALLTIME)
    start = time.monotonic()
    ticket_block = build_ticket_block(norm)
    messages = [
        {"role": "system", "content": SYSTEM_IMPLEMENTER},
        {"role": "user", "content":
         "WORKSPACE = . (alle Pfade relativ)\n\n"
         + ticket_block + "\n\nBEGIN"},
    ]
    files = set()
    summary = ""
    last_model = None
    parse_fail = 0
    errors = []
    turn = 0
    done_called = False
    for turn in range(1, max_turns + 1):
        if time.monotonic() - start > walltime:
            errors.append(f"walltime ({walltime}s) überschritten")
            break
        if len(files) > max_files:
            errors.append(f"max_files ({max_files}) überschritten")
            break
        model_name, content = llm_call_any(models, messages, LLM_MAX_TOKENS, LLM_TIMEOUT)
        if content is None:
            errors.append("kein Modell erreichbar")
            break
        last_model = model_name
        parsed = extract_json(content)
        if parsed is None:
            parse_fail += 1
            if parse_fail >= 3:
                errors.append(f"Agent-JJSON unlesbar nach {parse_fail} Versuchen")
                break
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content":
                "Deine Antwort war KEIN gültiges JSON-Objekt. Antworte EXAKT mit "
                "einem einzigen JSON-Objekt (Schema oben): kein Prosa, keine "
                "Code-Blöcke."})
            continue
        tool = (parsed.get("tool") or "").lower()
        a = parsed.get("args") or {}
        if tool == "done":
            summary = a.get("summary", "")
            done_called = True
            break
        result, err = execute_tool(tool, a, workdir, files)
        messages.append({"role": "assistant", "content": json.dumps(parsed)})
        out = result or ""
        errpart = f"\n[exit {err}]" if err else ""
        messages.append({"role": "user", "content": f"TOOL_RESULT {tool}:\n{out[:3000]}{errpart}"})
    else:
        errors.append("max_turns erreicht, kein done")
    return {
        "ok": done_called,
        "model": last_model,
        "summary": summary,
        "turns": turn,
        "files": sorted(files),
        "errors": errors,
    }


# =============================================================================
# Unabhängige Checks (Gate)
# =============================================================================
def extract_json(s):
    if not s or not isinstance(s, str):
        return None
    t = s.strip()
    t = re.sub(r"(?s)^```.*?```$", "", t).strip()
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    first = t.find("{")
    last = t.rfind("}")
    if first != -1 and last > first:
        try:
            obj = json.loads(t[first:last + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    return None


def run_command_checks(norm, cwd, budget=0):
    """Führt die ## Checks-Commands aus (unabhängig vom Implementierer)."""
    checks_text = norm.get("checks") or ""
    results = []
    # Checks validieren das Projekt-Root der Deliverable ("## Cwd", relativ zur
    # Workdir). Ohne "## Cwd" -> Workdir-Root. Damit die Checks die tatsächlich
    # implementierte Arbeit prüfen, nicht den Repo-Checkout (local_repo).
    check_cwd = os.path.normpath(os.path.join(cwd, (norm.get("cwd") or "").strip()))
    for raw in checks_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^\s*[-*]\s*", "", line).strip()
        line = re.sub(r"^\s*\d+\.\s*", "", line).strip()
        if not line or line.startswith("#"):
            continue
        if re.search(r"(?i)\bgit\s+(push|merge)\b", line):
            results.append({"cmd": line, "ok": False, "exit": -1, "out": "blockiert"})
            continue
        try:
            r = subprocess.run(line, shell=True, cwd=check_cwd, timeout=RUN_TIMEOUT,
                               capture_output=True, text=True)
            results.append({"cmd": line, "ok": r.returncode == 0, "exit": r.returncode,
                            "out": (r.stdout + "\n" + r.stderr).strip()[:1000]})
        except subprocess.TimeoutExpired:
            results.append({"cmd": line, "ok": False, "exit": -1, "out": "timeout"})
        except Exception as e:
            results.append({"cmd": line, "ok": False, "exit": -1, "out": str(e)})
    return results


def scenario_judge(norm, models, cwd):
    """Unabhängiger Szenario-Judge (frischer LLM-Aufruf, anderer Rollenprompt)."""
    deliverables = {}
    for root, dirs, files_ in os.walk(cwd):
        for fn in files_:
            full = os.path.join(root, fn)
            if fn.lower() == ".gitkeep":
                continue
            rel = os.path.relpath(full, cwd)
            try:
                if os.path.getsize(full) > 50000:
                    content = "<zu groß, abgeschnitten>"
                else:
                    content = open(full, encoding="utf-8").read()
            except Exception:
                content = "<nicht lesbar>"
            deliverables[rel] = content
    dt = "\n\n".join(f"===== {p} =====\n{c}" for p, c in deliverables.items())
    if not deliverables:
        dt = "(kein Artefakt erzeugt)"
    acceptance = norm.get("acceptance") or norm.get("success_criteria") or "(keine Akzeptanzbeispiele)"
    goal = norm.get("goal", "")
    prompt = (
        "Du bist ein UNABHÄNGIGER Verifier (Szenario-Judge) in einer Software-Factory. "
        "Du bist ein anderes Rollen-Modell als der Implementierer und darfst NICHT "
        "selbst arbeiten — nur PRÜFEN.\n\n"
        f"GOAL:\n{goal}\n\n"
        f"AKzeptANZBEISPIELE / ERFOLGSKRITERIEN:\n{acceptance}\n\n"
        f"ARTIFAKTE (Dateien, die der Implementer in seiner Workspace erzeugt hat):\n"
        f"{dt}\n\n"
        "Bewertene, ob ALLE Akzeptanzkriterien erfüllt sind. Antworte EXAKT mit einem "
        "JSON-Objekt (nichts sonst):\n"
        '  { "pass": true|false, "reason": "...", "violations": ["..."] }\\n'
        "Nur pass=true, wenn ALLE Kriterien nachweisbar erfüllt sind."
    )
    model_name, content = llm_call_any(models, [{"role": "user", "content": prompt}],
                                       max_tokens=1024, timeout=LLM_TIMEOUT)
    parsed = extract_json(content)
    if parsed is None:
        return {"pass": False, "reason": "Judge antwortete nicht parsebar: " +
                    (content[:300] if content else ""), "violations": ["judge-parse-error"],
                "model": model_name}
    return {**parsed, "model": model_name}


# =============================================================================
# Ergebnis-Section + Report
# =============================================================================
def append_result_section(path, outcome, work, cmd_checks, scenario, extra=""):
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n\n## Factory-Result\n")
            f.write(f"- outcome: {outcome}\n")
            if work:
                f.write(f"- model: {work.get('model')}\n")
                f.write(f"- turns: {work.get('turns')}\n")
                f.write(f"- files: {work.get('files')}\n")
                if work.get("errors"):
                    f.write(f"- errors: {work.get('errors')}\n")
            f.write("- command-checks:")
            if cmd_checks:
                for c in cmd_checks:
                    f.write(f"\n  - {'PASS' if c.get('ok') else 'FAIL'} (exit "
                            f"{c.get('exit')}): {c.get('cmd')}\n")
            else:
                f.write("\n  - (keine)\n")
            if scenario:
                f.write(f"- scenario-judge: {'PASS' if scenario.get('pass') else 'FAIL'} "
                        f"(model={scenario.get('model')}) — {scenario.get('reason')}\n")
            if extra:
                f.write(f"- note: {extra}\n")
    except OSError:
        pass


def write_report(ticket_id, data):
    REPORTS.mkdir(parents=True, exist_ok=True)
    p = REPORTS / f"{ticket_id}.json"
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        return None
    return p


def validate_ticket(path):
    r = subprocess.run([sys.executable, str(VALIDATOR), str(path)],
                       capture_output=True, text=True, cwd=FACTORY_DIR)
    ok = r.returncode == 0
    msg = (r.stdout + "\n" + r.stderr).strip()
    return ok, msg


# =============================================================================
# Deck-Writeback
# =============================================================================
def deck_writeback(card_id, outcome):
    if not card_id:
        print("[runner] deck-writeback: kein card_id im Ticket — übersprungen")
        return
    stacks = deck_stacks()
    if not stacks:
        print("[runner] deck-writeback: Stacks nicht lesbar — übersprungen")
        return
    sid = find_stack_title(stacks, outcome)
    if not sid:
        print(f"[runner] deck-writeback: Stack für '{outcome}' nicht im Deck "
              f"gefunden — übersprungen")
        return
    done = (outcome == "done")
    s, body = deck_move_card(card_id, sid, done=done)
    if s in (200, 204):
        stack_title = next((k for k, v in stacks.items() if v == sid), "unbekannt")
        print(f"[runner] deck-writeback: card {card_id} -> {outcome} "
              f"(Stack '{stack_title}') OK")
    else:
        print(f"[runner] deck-writeback FEHLER (HTTP {s}): {body[:200]}")


# =============================================================================
# Prozess ein Ticket
# =============================================================================
def process_ticket(path, args):
    path = Path(path).resolve()
    current = path
    reason = ""
    try:
        text = current.read_text(encoding="utf-8")
        norm = parse_ticket(text)
        ticket_id = current.stem
        print(f"[runner] pick: {ticket_id} ({current.parent.name})")
        budget = parse_budget(norm.get("budget", ""))
        models = choose_models(norm)
        if args.dry_run:
            print(f"[dry-run] Modell-Reihenfolge: "
                  + (", ".join(m[0] for m in models) or "KEINE erreichbar"))
            print(f"[dry-run] workdir: {WORK_ROOT / ticket_id}")
            print("[dry-run] Checks:")
            for line in (norm.get("checks") or "").splitlines():
                l = re.sub(r"^\s*[-*]\s*", "", line.strip()).strip()
                if l:
                    print(f"[dry-run]   - {l}")
            print("[dry-run] keine Aktionen ausgeführt (dry-run)")
            return {"ticket": ticket_id, "ok": True, "dry_run": True,
                    "models": [m[0] for m in models]}
        audit(ticket_id, "new", "pick")
        # --- CLAIM (atomar new->running, verhindert doppelte Verarbeitung) ---
        current = shift_ticket(current, "running", ticket_id, "claimed")
        # --- Validierung ---
        ok, msg = validate_ticket(current)
        if not ok:
            print(f"[runner] BLOCKED (validierung): {msg}")
            current = shift_ticket(current, "blocked", ticket_id, "validation-failed")
            write_report(ticket_id, {"ticket": ticket_id, "file": str(current),
                                     "outcome": "blocked", "stage": "validation",
                                     "error": msg,
                                     "started": datetime.now().isoformat(),
                                     "finished": datetime.now().isoformat()})
            return {"ticket": ticket_id, "ok": False, "stage": "validation", "error": msg}
        if not models:
            print("[runner] BLOCKED: kein Modell erreichbar (kiara/flaps)")
            current = shift_ticket(current, "blocked", ticket_id, "no-model")
            write_report(ticket_id, {"ticket": ticket_id, "file": str(current),
                                     "outcome": "blocked", "stage": "no-model",
                                     "started": datetime.now().isoformat(),
                                     "finished": datetime.now().isoformat()})
            return {"ticket": ticket_id, "ok": False, "stage": "no-model"}
        # --- RUNNING (Implementer) ---
        current = shift_ticket(current, "running", ticket_id, "work-start")
        workdir = WORK_ROOT / ticket_id
        print(f"[runner] work: {ticket_id} (model={models[0][0]}, workdir={workdir})")
        work = do_work(ticket_id, norm, models, budget, workdir)
        print(f"[runner] work fertig: model={work.get('model')} "
              f"turns={work.get('turns')} files={work.get('files')} "
              f"summary={work.get('summary')[:60]}")
        # --- GATE (Checks, solange die Datei noch in running liegt) ---
        files = work.get("files") or []
        if not files:
            final_ok = False
            cmd_checks = []
            scenario = None
            reason = "Implementer hat keine Dateien erzeugt."
        else:
            cmd_checks = run_command_checks(norm, workdir, budget)
            jmodels = judge_models_for(work.get("model"), models)
            scenario = scenario_judge(norm, jmodels, workdir)
            cmd_ok = all(c.get("ok") for c in cmd_checks) if cmd_checks else True
            final_ok = cmd_ok and bool(scenario.get("pass"))
            print(f"[runner] checks: cmd={len(cmd_checks)} "
                  f"(pass={all(c.get('ok') for c in cmd_checks) if cmd_checks else 'n/a'}), "
                  f"scenario={scenario.get('pass') if scenario else '?'}")
        # --- Ergebnis ---
        outcome = "gate" if final_ok else "blocked"
        if final_ok:
            append_result_section(current, "waiting-review", work, cmd_checks, scenario)
            # Approved spricht nur der unabhängige Prüfer in agent_pipeline.py aus.
            current = shift_ticket(current, "gate", ticket_id, "waiting-review")
            outcome = "gate"
        else:
            extra = reason or ""
            if not reason:
                if cmd_checks:
                    fails = [c["cmd"] for c in cmd_checks if not c.get("ok")]
                    reason = "Check(s) fehlgeschlagen: " + "; ".join(fails)
                    if scenario and not scenario.get("pass"):
                        reason += f" | judge: {str(scenario.get('reason') or '')[:60]}"
                else:
                    reason = "Keine Checks definiert."
            append_result_section(current, "blocked", work, cmd_checks, scenario, extra=reason)
            current = shift_ticket(current, "blocked", ticket_id, "blocked")
            outcome = "blocked"
        # --- Report + Audit ---
        data = {
            "ticket": ticket_id, "file": str(current), "outcome": outcome,
            "model": work.get("model"), "budget": budget,
            "work": work, "command_checks": cmd_checks,
            "scenario_judge": scenario, "reason": reason,
            "started": datetime.now().isoformat(timespec="seconds"),
            "finished": datetime.now().isoformat(timespec="seconds"),
            "dry_run": bool(args.dry_run),
            "deck_writeback": bool(args.deck_writeback),
        }
        write_report(ticket_id, data)
        audit(ticket_id, outcome, "finish", model=work.get("model"),
              files=work.get("files"),
              cmd_ok=all(c.get("ok") for c in cmd_checks) if cmd_checks else None)
        # --- Deck-Writeback (opt) ---
        if args.deck_writeback:
            card_id = extract_card_id(text)
            if card_id:
                deck_writeback(card_id, outcome)
        print(f"[runner] {ticket_id} -> {outcome}")
        return {"ticket": ticket_id, "ok": final_ok, "outcome": outcome}
    except Exception as e:
        print(f"[runner] EXCEPTION {Path(path).stem}: {e}")
        try:
            if current is not None and current.parent.name not in ("blocked", "done"):
                shift_ticket(current, "blocked", Path(path).stem,
                             f"exception {str(e)[:80]}")
        except Exception:
            pass
        return {"ticket": Path(path).stem, "ok": False, "stage": "exception",
                "error": str(e)}


# =============================================================================
# Main
# =============================================================================
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="FACT-002 Runner — Software-Factory Work-Engine (Orchestrator).")
    ap.add_argument("--ticket", help="Pfad eines einzelnen Tickets")
    ap.add_argument("--dry-run", action="store_true", help="nur anzeigen, nichts ausführen")
    ap.add_argument("--deck-writeback", action="store_true",
                    help="Deck-Karte in die neue Station schieben (Standard: nur lokal)")
    ap.add_argument("--once", action="store_true", default=True,
                    help="einen Zyklus ausführen und beenden (Default)")
    args = ap.parse_args(argv)

    STATE.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    tickets = []
    if args.ticket:
        tickets = [args.ticket]
    else:
        ndir = TICKETS / "new"
        if ndir.exists():
            tickets = sorted([p for p in ndir.glob("*.md") if p.is_file()])
    if not tickets:
        print("[runner] keine Tickets in tickets/new/ (nichts zu tun)")
        return 0

    results = []
    for t in tickets:
        try:
            results.append(process_ticket(t, args))
        except Exception as e:
            results.append({"ticket": Path(t).stem, "ok": False,
                            "stage": "exception", "error": str(e)})
    planned = sum(1 for r in results if r.get("dry_run"))
    ok_count = sum(1 for r in results if r.get("ok") and not r.get("dry_run"))
    failed = len(results) - ok_count - planned
    print(f"[runner] FERTIG: {len(results)} Tickets, "
          f"{ok_count} done/pass, {planned} geplant, {failed} failed/blocked")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
