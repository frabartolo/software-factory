#!/usr/bin/env python3
"""Plant einen Factory-Job und schreibt den Bericht. Kein Push, kein Merge, kein Modell."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory_common import FactoryError, factory_config, resolve_project, root, safe_checks
from validate_ticket import Ticket, resolve_ticket_path, validate_path


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def plan_job(ticket: Ticket, *, dry_run: bool) -> dict[str, Any]:
    if not ticket.repo:
        raise FactoryError(f"{ticket.ticket_id}: Frontmatter-Feld repo fehlt")
    project = resolve_project(ticket.repo)
    checks = safe_checks(project.get("checks") or [])
    worktree = root() / "worktrees" / ticket.ticket_id
    branch = f"factory/{ticket.ticket_id}"
    worker_enabled = bool(factory_config().get("worker", {}).get("execute"))
    return {
        "ticket_id": ticket.ticket_id,
        "title": ticket.title,
        "repo": ticket.repo,
        "repo_path": project["resolved_repo"],
        "repo_location": project["repo_location"],
        "base_branch": ticket.base_branch or project.get("base_branch") or "main",
        "worktree": str(worktree),
        "branch": branch,
        "checks_configured": checks,
        "checks_executed": False,
        "worker_invoked": False,
        "worker_skipped": "dry-run" if dry_run else "worker im Bootstrap aus",
        "worker_enabled": worker_enabled and not dry_run,
        "dry_run": dry_run,
        "diff_summary": {"files": 0, "insertions": 0, "deletions": 0},
        "walltime_seconds": 0,
        "status": "waiting-review",
        "result": "simulated" if dry_run else "planned",
    }


def write_report(plan: dict[str, Any], *, reason: str) -> Path:
    directory = root() / "reports"
    directory.mkdir(parents=True, exist_ok=True)
    moment = stamp()
    payload = dict(plan)
    payload["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload["reason"] = reason
    json_path = directory / f"{plan['ticket_id']}-{moment}.json"
    md_path = directory / f"{plan['ticket_id']}-{moment}.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        f"# Job-Report {payload['ticket_id']}",
        "",
        f"- Status: {payload['status']}",
        f"- Ergebnis: {payload['result']}",
        f"- Repo: {payload['repo']} ({payload['repo_path']})",
        f"- Worktree: {payload['worktree']}",
        f"- Branch: {payload['branch']}",
        f"- Dry-run: {payload['dry_run']}",
        f"- Worker aufgerufen: {payload['worker_invoked']}",
        f"- Checks ausgeführt: {payload['checks_executed']}",
        f"- Grund: {reason}",
        "",
        "Konfigurierte Checks:",
        "",
    ]
    if payload["checks_configured"]:
        lines.extend(f"- `{command}`" for command in payload["checks_configured"])
    else:
        lines.append("- keine Checks konfiguriert")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path


def print_plan(plan: dict[str, Any]) -> None:
    print(f"Ticket {plan['ticket_id']}: {plan['title']}")
    print(f"  Repo: {plan['repo_path']} ({plan['repo_location']})")
    print(f"  Worktree: {plan['worktree']}")
    print(f"  Branch: {plan['branch']}")
    print("  Übergang: Ready / Bereit → Running / In Arbeit → Waiting Review / Gate")
    print(f"  Worker: {plan['worker_skipped']}")
    print("  Ausgeschlossen: Modellaufruf, Push, Merge, Deploy, Done")


def load_ticket(raw: str) -> Ticket:
    ticket, errors = validate_path(resolve_ticket_path(raw))
    if errors:
        joined = "; ".join(errors)
        raise FactoryError(f"{ticket.ticket_id} ist ungültig: {joined}")
    return ticket


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Factory-Job planen und Bericht schreiben")
    parser.add_argument("command", choices=("plan", "report-test", "worktree-test"))
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    dry_run = args.dry_run or args.command != "plan"
    try:
        ticket = load_ticket(args.ticket)
        plan = plan_job(ticket, dry_run=dry_run or args.command == "worktree-test")
        if args.command == "worktree-test":
            print_plan(plan)
            print("Worktree wird im Bootstrap nur geplant, nicht angelegt.")
            return 0
        reason = "dry-run" if plan["dry_run"] else "bootstrap ohne Worker"
        path = write_report(plan, reason=reason)
        print_plan(plan)
        print(f"  Report: {path}")
    except FactoryError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
