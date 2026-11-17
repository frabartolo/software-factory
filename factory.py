#!/usr/bin/env python3
"""
factory.py — Factory-CLI (FACT-002).

Schlankes Kommandozeilen-Wrapper um die bestehende Pipeline. Es führt keine
eigene Implementierung aus und dupliziert den Runner, sondern verdrahtet
die vorhandenen Bausteine:

    scripts/runner.py        Implementierung + Checks (Engine)
    scripts/worktree.py      Worktree-Lifecycle
    scripts/audit.py         Audit-Log
    scripts/deck.py          Nextcloud Deck
    scripts/factory_common.py Konfiguration, Credentials, Policies

Verwendung:
    python3 factory.py --help
    python3 factory.py scan --dry-run
    python3 factory.py run-once --dry-run
    python3 factory.py worktree-test <id> --status running
    python3 factory.py check --repo factory --dry-run
    python3 factory.py report-test <ticket>
    python3 factory.py audit-test <ticket>
    python3 factory.py health --model kiara
    python3 factory.py route-test
    python3 factory.py pilot-report
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from factory_common import (
    factory_config,
    actor_name,
    append_audit,
)
from validate_factory_schema import (
    load_schema,
    validate_ticket,
    parse_sections,
    parse_kv_section,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_ticket_metadata(path: Path) -> dict:
    """Liest card_id und Sektionen aus einem Ticket (ohne Validierung)."""
    sections, _ = parse_sections(path.read_text(encoding="utf-8"))
    meta = dict(sections)
    text = path.read_text(encoding="utf-8")
    # card_id kann als `card_id: 99` oder `card_id=99` vorkommen
    m = re.search(r"^\s*card_id\s*[:=]\s*(\d+)\s*$", text, re.MULTILINE)
    if m:
        meta["card_id"] = int(m.group(1))
    return meta


def list_tickets(directory: Path) -> list[Path]:
    if directory.is_dir():
        return sorted(directory.glob("*.md"))
    return []


def cmd_scan(args: argparse.Namespace) -> int:
    """Listet Tickets der Queues new/ready/running auf."""
    cfg = factory_config()
    base = cfg["paths"]["tickets"]
    queues = {"new": "neu", "ready": "bereit", "running": "in-arbeit"}
    total = 0
    print("Tickets im Factory-Queue:")
    for qkey in ("new", "ready", "running"):
        files = list_tickets(Path(base) / qkey)
        total += len(files)
        print(f"\n{qkey.upper()} ({len(files)}):")
        if not files:
            print("  (leer)")
        for f in files:
            m = None
            try:
                m = parse_ticket_metadata(f)
            except Exception:
                m = {}
            cid = m.get("card_id", "-")
            print(f"  {f.name}  [card_id={cid}]")
    print(f"\nSumme: {total} Tickets.")
    if args.dry_run:
        print("[dry-run] Nur Auflistung, keine Änderungen.")
    return 0


def cmd_run_once(args: argparse.Namespace) -> int:
    """Wählt das erste gültige ready-Ticket aus und plant den Lauf."""
    cfg = factory_config()
    base = Path(cfg["paths"]["tickets"])
    ready_files = list_tickets(base / "ready")

    if not ready_files:
        print("Keine Tickets in tickets/ready.")
        print("[dry-run] Nichts zu tun." if args.dry_run else "Kein Ticket, um zu starten.")
        return 0

    schema = load_schema(ROOT)
    valid = []
    for f in ready_files:
        errors = validate_ticket(f, schema)
        if not errors:
            valid.append(f)

    if not valid:
        print(f"{len(ready_files)} Tickete in ready, aber keines gültig (Schema).")
        return 1

    ticket = valid[0]
    meta = parse_ticket_metadata(ticket)
    checks_section = meta.get("Checks", "").strip()
    checks = [c.strip() for c in checks_section.splitlines() if c.strip()]
    budget = parse_kv_section(meta.get("Budget", ""))
    model = cfg["models"]["default_worker"]
    model_name = cfg["models"].get("worker_model", model)

    print(f"Wahl: {ticket.name}")
    print(f"  Modell: {model} ({model_name})")
    print(f"  Workdir: work/{ticket.stem}/")
    print(f"  Budget: {json.dumps(budget, ensure_ascii=False)}")
    print(f"  Checks ({len(checks)}):")
    for c in checks:
        print(f"    - {c}")
    print("[dry-run] Nur Planung — kein echter Model-Call, kein Dateimove." if args.dry_run else "Start")
    if args.dry_run:
        return 0

    # Nicht-dry-run: ins running-Queue verschieben (Engine führt aus)
    target = (base / "running" / ticket.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    ticket.rename(target)
    print(f"Verschieben: {ticket.name} → tickets/running/")
    append_audit({
        "ticket": ticket.stem,
        "event": "run_once_started",
        "actor": actor_name("runner"),
        "role": "runner",
        "message": f"Ticket {ticket.stem} zur Umsetzung eingelegt",
    })
    return 0


def cmd_worktree_test(args: argparse.Namespace) -> int:
    """Worktree-Lifecycle für ein Ticket (create/status/remove)."""
    import worktree
    ticket_id = args.id
    path = Path(args.path) if args.path else None
    if args.dry_run:
        print(f"[dry-run] worktree-test {ticket_id} status={args.status}:")
        print(f"  worktree.create(ticket_id='{ticket_id}', status='{args.status}')")
        print("  (kein Worktree angelegt, kein State geschrieben)")
        return 0
    try:
        if args.status and args.status.lower() in ("running", "started"):
            path = worktree.create(ticket_id, path=path, status="running")
            print(f"Worktree erstellt: {path}")
        elif args.status and args.status.lower() in ("done", "blocked"):
            path = worktree.remove(ticket_id, path=path, force=True)
            print(f"Worktree entfernt: {ticket_id}")
        else:
            print(f"Status: {ticket_id}")
        print("[OK]")
        return 0
    except Exception as exc:
        print(f"[FEHLER] worktree-test: {exc}", file=sys.stderr)
        return 1


def resolve_project(name: str) -> dict:
    """Löst ein Projekt in projects.yaml auf."""
    import yaml
    path = ROOT / "config" / "projects.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    projects = data.get("projects", {})
    if name not in projects:
        known = ", ".join(sorted(projects))
        raise ValueError(f"Projekt '{name}' unbekannt. Verfügbar: {known}")
    return projects[name]


def cmd_check(args: argparse.Namespace) -> int:
    """Führt die Checks eines Projekts aus (oder listet sie in dry-run)."""
    project = resolve_project(args.repo)
    checks = project.get("checks", [])
    local_repo = project.get("local_repo", None)
    print(f"Projekt: {args.repo}")
    print(f"  checks: {len(checks)}")
    if args.dry_run:
        for i, c in enumerate(checks, 1):
            print(f"    {i}. {c}")
        print("[dry-run] Keine Checks ausgeführt.")
        return 0
    results = []
    for c in checks:
        try:
            res = subprocess.run(
                c, shell=True, capture_output=True, text=True, cwd=str(ROOT), timeout=300,
            )
            ok = res.returncode == 0
        except Exception as exc:
            ok, res = False, None
        results.append((ok, c))
        marker = "OK " if ok else "FAIL"
        print(f"  {marker} {c}")
        if not ok and res:
            print(f"      stdout: {res.stdout[-300:]}" if res.stdout else "")
            print(f"      stderr: {res.stderr[-300:]}" if res.stderr else "")
    failed = sum(1 for ok, _ in results if not ok)
    print(f"\nErgebnis: {len(results) - failed}/{len(results)} OK")
    return 0 if failed == 0 else 1


def cmd_report_test(args: argparse.Namespace) -> int:
    """Erstellt einen Bericht für ein Ticket."""
    ticket_path = Path(args.ticket)
    if not ticket_path.is_absolute():
        ticket_path = ROOT / ticket_path
    if not ticket_path.is_file():
        print(f"Ticket nicht gefunden: {ticket_path}", file=sys.stderr)
        return 1
    meta = parse_ticket_metadata(ticket_path)
    report_dir = ROOT / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{ticket_path.stem}.report.md"
    lines = [
        f"# Bericht: {ticket_path.stem}",
        f"Erstellt: {now_iso()}",
        "",
        f"## Ziel",
        meta.get("Goal", "").strip(),
        "",
        f"## Checks",
    ]
    checks = [c.strip() for c in meta.get("Checks", "").splitlines() if c.strip()]
    lines += [f"- {c}" for c in checks]
    lines.append("")
    lines.append("## Status")
    lines.append("- [ ] Umsetzung")
    lines.append("- [ ] Checks")
    lines.append("- [ ] Bericht")
    lines.append("- [ ] Approval")
    content = "\n".join(lines) + "\n"
    report_path.write_text(content, encoding="utf-8")
    append_audit({
        "ticket": ticket_path.stem,
        "event": "report_generated",
        "actor": actor_name("runner"),
        "role": "runner",
        "message": f"Bericht erzeugt: {report_path}",
    })
    print(f"Bericht geschrieben: {report_path}")
    return 0


def cmd_audit_test(args: argparse.Namespace) -> int:
    """Hängt ein Ticket-Ereignis an das Audit-Log."""
    ticket_path = Path(args.ticket)
    name = ticket_path.stem if ticket_path else "unknown"
    path = append_audit({
        "ticket": name,
        "event": "ticket_processed",
        "actor": actor_name("runner"),
        "role": "runner",
        "message": f"Audit-Test für Ticket {name}",
    })
    print(f"Audit geschrieben: {path}")
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    """Prüft die Erreichbarkeit eines Modells."""
    import model_health
    return model_health.main([args.model])


def cmd_route_test(args: argparse.Namespace) -> int:
    """Zeigt die Routing-Entscheidung für ein Ticket."""
    cfg = factory_config()
    routing = cfg.get("routing", {})
    models = cfg["models"]
    default = models["default_worker"]
    print(f"Routing-Test (default={default}):")
    print(f"  kiara  = implementation_default")
    if "flaps" in routing:
        print(f"  flaps  = review_verification")
        print(f"  fallback bei Ausfall: {routing.get('flaps', {}).get('on_unavailable', [])}")
    print("[OK]")
    return 0


def cmd_pilot_report(args: argparse.Namespace) -> int:
    """Erstellt einen Pilot-Bericht über den Factory-Stand."""
    cfg = factory_config()
    base = Path(cfg["paths"]["tickets"])
    lines = [
        f"# Pilot-Report",
        f"Erstellt: {now_iso()}",
        "",
        "## Status",
    ]
    for qkey in ("new", "ready", "running", "blocked"):
        files = list_tickets(base / qkey)
        lines.append(f"- {qkey}: {len(files)} Tickete")
    lines.append("")
    lines.append("## Modelle")
    lines.append(f"- kiara (default): {cfg['models'].get('worker_model', 'n/a')}")
    lines.append(f"- flaps (review): {cfg['models'].get('flaps_model', 'n/a')}")
    lines.append("")
    lines.append("## Engine")
    worker = cfg.get("worker", {})
    execute = worker.get("execute", False)
    if execute:
        lines.append("- Execute: true")
    else:
        lines.append("- Execute: false (Bootstrap-Modus — kein Implementierungs-Run)")
    report_dir = ROOT / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "pilot-report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Pilot-Report geschrieben: {report_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Factory-CLI — Wrapper um Runner, Worktree, Audit, Deck",
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Listet Tickets der Queues auf")
    p_scan.add_argument("--dry-run", action="store_true")
    p_scan.set_defaults(func=cmd_scan)

    p_run = sub.add_parser("run-once", help="Startet das erste gültige ready-Ticket")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.set_defaults(func=cmd_run_once)

    p_wt = sub.add_parser("worktree-test", help="Worktree-Lifecycle für ein Ticket")
    p_wt.add_argument("id", help="Ticket-ID")
    p_wt.add_argument("--path", default=None, help="Worktree-Pfad (optional)")
    p_wt.add_argument("--status", default=None, help="Status: running|done|blocked")
    p_wt.add_argument("--dry-run", action="store_true")
    p_wt.set_defaults(func=cmd_worktree_test)

    p_ch = sub.add_parser("check", help="Führt Checks eines Projekts aus")
    p_ch.add_argument("--repo", required=True, help="Projektname (projects.yaml)")
    p_ch.add_argument("--dry-run", action="store_true")
    p_ch.set_defaults(func=cmd_check)

    p_rpt = sub.add_parser("report-test", help="Erstellt einen Bericht für ein Ticket")
    p_rpt.add_argument("ticket", help="Pfad zum Ticket")
    p_rpt.set_defaults(func=cmd_report_test)

    p_aud = sub.add_parser("audit-test", help="Hängt ein Ticket an das Audit-Log")
    p_aud.add_argument("ticket", help="Ticket-ID oder Pfad")
    p_aud.set_defaults(func=cmd_audit_test)

    p_he = sub.add_parser("health", help="Prüft die Modell-Erreichbarkeit")
    p_he.add_argument("--model", required=True, help="Modell: kiara|flaps")
    p_he.set_defaults(func=cmd_health)

    p_rt = sub.add_parser("route-test", help="Zeigt die Routing-Entscheidung")
    p_rt.set_defaults(func=cmd_route_test)

    p_pr = sub.add_parser("pilot-report", help="Erstellt einen Pilot-Bericht")
    p_pr.set_defaults(func=cmd_pilot_report)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
