#!/usr/bin/env python3
"""Factory status CLI - simple terminal view of factory state."""

import json
import os
import sys

STATE_FILE = "factory_state.json"
AUDIT_FILE = "audit.log"

STATES = ["new", "running", "waiting-review", "passed", "failed"]


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"tickets": []}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"tickets": []}


def cmd_status():
    state = load_state()
    tickets = state.get("tickets", [])

    counts = {s: 0 for s in STATES}
    for t in tickets:
        s = t.get("state", "unknown")
        if s in counts:
            counts[s] += 1

    print("Factory Status")
    print("=" * 40)
    for s in STATES:
        print(f"  {s:15s} {counts[s]:4d}")
    print("-" * 40)
    print(f"  {'total':15s} {len(tickets):4d}")
    print()


def cmd_jobs():
    state = load_state()
    tickets = state.get("tickets", [])

    active = [t for t in tickets if t.get("state") in ("running", "waiting-review")]

    if not active:
        print("No running or waiting-review jobs.")
        return

    print("Active Jobs (running / waiting-review)")
    print("=" * 60)
    print(f"{'ID':<10} {'State':<18} {'Title':<30} {'Assigned':<15}")
    print("-" * 60)
    for t in active:
        tid = t.get("id", "N/A")
        st = t.get("state", "unknown")
        title = t.get("title", "")
        assigned = t.get("assigned_to", "")
        print(f"{tid:<10} {st:<18} {title:<30} {assigned:<15}")
    print()


def cmd_tail_audit():
    if not os.path.exists(AUDIT_FILE):
        print(f"WARNING: Audit log not found at '{AUDIT_FILE}'.")
        print("No audit entries to display.")
        return

    try:
        with open(AUDIT_FILE, "r") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"WARNING: Cannot read audit log: {e}")
        return

    if not lines:
        print("Audit log is empty.")
        return

    last_n = lines[-20:]
    print("Last 20 audit entries:")
    print("-" * 60)
    for line in last_n:
        print(line.rstrip())
    print()


def main():
    if len(sys.argv) < 2:
        print("Usage: factory.py <status|jobs|tail-audit>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "status":
        cmd_status()
    elif cmd == "jobs":
        cmd_jobs()
    elif cmd == "tail-audit":
        cmd_tail_audit()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: factory.py <status|jobs|tail-audit>")
        sys.exit(1)


if __name__ == "__main__":
    main()
