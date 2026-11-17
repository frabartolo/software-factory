#!/usr/bin/env python3
"""Plant einen Factory-Job und schreibt den Bericht. Kein Push, kein Merge, kein Modell."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory_common import FactoryError, factory_config, resolve_project, root, safe_checks
from validate_ticket import Ticket, resolve_ticket_path, validate_path

import worktree


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


def run_worktree_test(ticket: Ticket) -> int:
    """FACT-003-Akzeptanz: Worktree anlegen, Hauptcheckout unangetastet,
    sauberer Abbruch bei falschem Repo-Pfad, kein halbes Verzeichnis."""
    tid = ticket.ticket_id
    report: dict[str, Any] = {
        "ticket_id": tid,
        "started": datetime.now(timezone.utc).isoformat(),
        "cases": {},
        "ok": True,
    }
    wrong_repo: Path | None = None
    before: list[str] = []

    def git_list() -> list[str]:
        r = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=str(root()), capture_output=True, text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"git worktree list: {r.stderr.strip()}")
        return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]

    def record(case: str, fn):
        try:
            fn()
            report["cases"][case] = "ok"
        except Exception as e:
            report["cases"][case] = f"FAIL: {type(e).__name__}: {e}"
            report["ok"] = False

    try:
        # Baseline stabilisieren (inaktive Worktree-Registry auflösen)
        subprocess.run(["git", "worktree", "prune"], cwd=str(root()),
                       capture_output=True, text=True)
        before = git_list()
        report["main_checkout_before"] = before
        wrong_repo = Path(tempfile.mkdtemp(prefix="worktree-test-wrong-repo-"))

        def case_create() -> None:
            s = worktree.create(tid, status="running", model="worktree-test")
            if not s or not s.get("path"):
                raise AssertionError("create: path fehlt")
            st = worktree.status(tid)
            if not st or st.get("ticket_id") != tid:
                raise AssertionError(f"status stimmt nicht: {st}")
            p = Path(s["path"])
            if not p.exists():
                raise AssertionError(f"Worktree-Verzeichnis fehlt: {p}")
            report["created_path"] = str(p)

        def case_reuse() -> None:
            s = worktree.create(tid, status="running", model="worktree-test")
            if s.get("status") != "running" or not s.get("path"):
                raise AssertionError(f"reuse: falscher Zustand {s}")

        def case_abort() -> None:
            # Falscher Repo-Pfad (keine Git-Repo): sauber abbrechen,
            # keine Reste (work/ oder .git-Datei) hinterlassen.
            try:
                worktree.create("WORKTREE-ABORT", repo=wrong_repo)
                raise AssertionError("create hat kein RuntimeError geworfen")
            except RuntimeError:
                pass
            if (wrong_repo / "work").exists():
                raise AssertionError(f"Halbes Worktree-Verzeichnis: {wrong_repo / 'work'}")
            if (wrong_repo / ".git").exists():
                raise AssertionError(f".git-Reste: {wrong_repo / '.git'}")
            report["aborted_cleanly"] = True

        record("create", case_create)
        record("reuse", case_reuse)
        record("abort-wrong-repo", case_abort)

        # Cleanup: Worktree entfernen
        try:
            worktree.remove(tid)
            tid_path = root() / "work" / tid
            if tid_path.exists():
                raise AssertionError(f"Worktree-Verzeichnis bleibt: {tid_path}")
            report["cleanup"] = "ok"
        except Exception as e:
            report["cleanup"] = f"FAIL: {e}"
            report["ok"] = False

    except Exception as e:
        report["fatal"] = f"{type(e).__name__}: {e}"
        report["ok"] = False

    finally:
        if wrong_repo:
            shutil.rmtree(wrong_repo, ignore_errors=True)

    # Hauptcheckout nach Abschluss == Baseline?
    try:
        after = git_list()
        report["main_checkout_after"] = after
        report["main_checkout_untouched"] = (set(before) == set(after))
    except Exception as e:
        report["after-check"] = f"FAIL: {e}"
        report["main_checkout_untouched"] = False

    report["ok"] = report.get("ok", False) and report.get("main_checkout_untouched", False)
    if report.get("fatal"):
        report["ok"] = False
    report["finished"] = datetime.now(timezone.utc).isoformat()

    report_path = root() / "state" / "reports" / "worktree-test.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"# Worktree-Test {tid}")
    print(f"  angelegter Worktree : {report.get('created_path', '(keiner)')}")
    print(f"  Hauptcheckout unangetastet: {report['main_checkout_untouched']}")
    print(f"  Cleanup               : {report.get('cleanup', 'n/a')}")
    for case, result in report["cases"].items():
        print(f"    - {case}: {result}")
    if report.get("fatal"):
        print(f"  fatal               : {report['fatal']}")
    print(f"  Report                : {report_path}")
    print(f"  OK                    : {report['ok']}")
    return 0 if report["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Factory-Job planen und Bericht schreiben")
    parser.add_argument("command", choices=("plan", "report-test", "worktree-test"))
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    dry_run = args.dry_run or args.command != "plan"
    try:
        ticket = load_ticket(args.ticket)
        plan = plan_job(ticket, dry_run=True)
        print_plan(plan)
        if args.command == "worktree-test":
            return run_worktree_test(ticket)
        reason = "dry-run" if dry_run else "bootstrap ohne Worker"
        path = write_report(plan, reason=reason)
        print(f"  Report: {path}")
    except FactoryError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
