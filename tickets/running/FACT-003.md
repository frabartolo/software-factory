# FACT-003 — Worktree-Lifecycle
card_id=99

## Goal
Für jedes Ticket einen isolierten Workspace (Worktree) `work/<Ticket-ID>/` anlegen:
- Checkout in einen sauberen, isolierten Zustand (kein Merge-Konflikt)
- `work/<Ticket-ID>/factory_state.json` schreiben: Ticket-ID, Start, Status, Model
- Nach Report: Workspace sauber entfernen

## Success criteria
- `worktree.py` mit `create`, `remove`, `status`
- `test_worktree.py`: 3+ Szenarien (leeres Repo, existing worktree, Cleanup)
- `create` legt den Workspace an und schreibt `factory_state.json`
- `remove` entfernt den Workspace sauber
- `status` zeigt Ticket-ID, Start, Status, Model

## Acceptance examples
- `create("FACT-003", "work/FACT-003")` legt den Workspace an; `factory_state.json` existiert
- `status("FACT-003", "work/FACT-003")` liefert die Daten (ticket_id, start, status, model)
- `remove("FACT-003", "work/FACT-003")` löscht den Workspace (existiert danach nicht)
- Bestehende/defekte Worktree wird erkannt und gemeldet

## Forbidden
- Kein `rm -rf` ohne Kontrolle (saubere Löschung bevorzugen)
- Kein `git worktree`-Aufruf außerhalb von `worktree.py`
- Keine Cloud-/OpenRouter-Aufrufe ohne expliziten Hinweis

## Checks
- `python3 -m pytest test_worktree.py -q`
- `grep -q "def create" worktree.py`
- `grep -q "def remove" worktree.py`
- `grep -q "def status" worktree.py`

## Budget
max_walltime: 300s
max_turns: 60
max_files: 12

## Router
- primary: kiara
- fallback: flaps
- exception: openrouter
