#!/usr/bin/env python3
"""OVERNIGHT-Poller mit Round-Robin-Rotation.

Läuft agent_pipeline.py  --once --card <id>  alle INTERVAL seconds, aber
ROTIERT über alle aktiven Karten (Waiting Review → Running → Ready → Neu).

Warum: Die Pipeline wählt ohne --card immer das höchste Priority-Karte
(running > backlog). Eine im Running hängende Karte (z. B. kiara-Timeout,
„kein Modell erreichbar“) würde so endlos wiederverwiesen und die Backlog-
Karten hungern. Durch die Rotation bekommt jede Karte pro Durchgang
genau einen Versuch — eine hängt Karte blockiert nicht mehr die anderen.

Log: logs/overnight_run.log. Stündlich (alle SNAPSHOT_EVERY Iterationen)
einen Deck-Snapshot mit den Karten pro Stack.

Start:  python3 scripts/overnight_run.py
Test:   python3 scripts/overnight_run.py --dry-run   (nichts verschieben)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "logs" / "overnight_run.log"
INTERVAL = 300           # seconds between attempts (~5 min)
SNAPSHOT_EVERY = 12      # every 12 attempts (~60 min) -> Deck snapshot
PER_RUN_TIMEOUT = 6000   # seconds per single --card attempt (kiara implement is heavy; walltime-floor 5400s + margin)
RECENT_WINDOW = 32       # safety cap on the "recent" set (active cards ~13)

os.environ.setdefault("FACTORY_ROLE", "hermes")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    line = f"[{ts()}] {msg}"
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


def _sub(args, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(ROOT),
        env=dict(os.environ),
        timeout=timeout,
        capture_output=True,
    )


def run_once_card(card_id: int, dry_run: bool) -> int:
    """Run agent_pipeline.py --follow --card <card_id> (+ optional --dry-run).

    --follow führt die Karte bis Approved/Stopp (max. 4 Stufen) in einem
    Aufruf — für den Overnight-Run effizienter als ein einzelner --once-
    Schritt.
    """
    log(f"--card {card_id} START (follow, timeout={PER_RUN_TIMEOUT}s dry_run={dry_run})")
    args = [
        sys.executable,
        str(ROOT / "scripts" / "agent_pipeline.py"),
        "--follow",
        "--card", str(card_id),
    ]
    if dry_run:
        args.append("--dry-run")
    try:
        p = _sub(args, timeout=PER_RUN_TIMEOUT)
    except subprocess.TimeoutExpired:
        log(f"--card {card_id}: TIMEOUT after {PER_RUN_TIMEOUT}s")
        return 999
    rc = p.returncode
    out = ((p.stdout or b"").decode("utf-8", "replace")
           + (p.stderr or b"").decode("utf-8", "replace")).strip()
    log(f"--card {card_id} exit={rc}")
    if out:
        for ln in out.splitlines()[:25]:
            log("    " + ln)
    return rc


def deck_client():
    from deck import client_or_exit
    return client_or_exit()


def active_queue(deck) -> list:
    """Card IDs, priority-ordered: waiting_review, running, ready, backlog."""
    from factory_common import stack_name
    out = []
    for state in ("waiting_review", "running", "ready", "backlog"):
        title = stack_name(state)
        try:
            cards = deck.cards(title) or []
        except Exception as exc:
            log(f"deck.cards({title!r}) error: {exc!r}")
            continue
        for card in cards:
            if card.get("deleted_at"):
                continue
            try:
                out.append(int(card.get("id")))
            except (TypeError, ValueError):
                continue
    seen = set()
    uniq = []
    for cid in out:
        if cid not in seen:
            seen.add(cid)
            uniq.append(cid)
    return uniq


def snapshot(deck) -> None:
    from factory_common import stack_name
    log("SNAPSHOT:")
    for state in ("waiting_review", "running", "ready", "backlog",
                  "blocked", "approved", "done"):
        title = stack_name(state)
        try:
            cards = deck.cards(title) or []
            ids = [c.get("id") for c in cards if not c.get("deleted_at")]
        except Exception as exc:
            ids = [f"error:{exc}"]
        log(f"    {title}: {ids}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Overnight-Poller mit Round-Robin-Rotation")
    ap.add_argument("--dry-run", action="store_true", help="Karten NICHT verschieben")
    ap.add_argument("--interval", type=int, default=INTERVAL,
                    help=f"Seconds zwischen Versuchen (Default {INTERVAL})")
    ap.add_argument("--max", type=int, default=None,
                    help="Stoppt nach N Iterationen (für Tests)")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log(f"OVERNIGHT-RUN START pid={os.getpid()} interval={args.interval}s "
        f"snapshot_every={SNAPSHOT_EVERY} per_run_timeout={PER_RUN_TIMEOUT}s "
        f"dry_run={args.dry_run} max={args.max}")
    recent = set()
    it = 0
    while True:
        it += 1
        try:
            deck = deck_client()
            queue = active_queue(deck)
            if not queue:
                log(f"it={it} keine aktiven Karten (Deck leer) -> {args.interval}s sleep")
                time.sleep(args.interval)
                continue
            pick = None
            for cid in queue:
                if cid not in recent:
                    pick = cid
                    break
            if pick is None:
                recent.clear()
                pick = queue[0]
            log(f"it={it} PICK {pick} (queue={len(queue)}: {queue})")
            rc = run_once_card(pick, args.dry_run)
            recent.add(pick)
            if len(recent) > RECENT_WINDOW:
                recent.clear()
            if it % SNAPSHOT_EVERY == 0:
                snapshot(deck)
        except Exception as exc:
            log(f"it={it} EXCEPTION {exc!r}")
            time.sleep(30)
        time.sleep(args.interval)
        if args.max is not None and it >= args.max:
            log(f"OVERNIGHT-RUN STOP nach {it} Iterationen (max={args.max})")
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
