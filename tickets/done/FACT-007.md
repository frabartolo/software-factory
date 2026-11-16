# FACT-007 — Factory-Meta: CLI/TUI-Statusansicht für Queue und Jobs

<!-- source: nextcloud-deck board=7 stack="Backlog / Neu" card_id=103 -->

## Goal

Provide a simple CLI/TUI view for the current factory status, queue depth, and running jobs.

## Success criteria

- `factory.py status` shows queue counts by state.
- `factory.py jobs` shows currently running or waiting-review tickets.
- `factory.py tail-audit` prints the last audit lines.
- The view is simple enough to use from SSH/terminal.

## Acceptance examples

1. Normal case:
   The status view shows counts for new, running, waiting-review, passed, failed.
2. Boundary case:
   If no jobs are running, the view still exits cleanly.
3. Failure case:
   If audit log is missing, the tool gives a clear warning.

## Forbidden

- No web dashboard.
- No fancy animations.
- No database.

## Checks

- python3 factory.py status
- python3 factory.py jobs

## Budget

max_walltime: 25m
max_turns: 12
max_files: 6


## Factory-Result
- outcome: approved
- model: kiara
- turns: 10
- files: ['factory.py', 'factory_state.json']
- command-checks:
  - PASS (exit 0): python3 factory.py status

  - PASS (exit 0): python3 factory.py jobs
- scenario-judge: PASS (model=kiara) — Alle drei Akzeptanzkriterien sind erfüllt: (1) cmd_status() zeigt alle fünf Zustände (new, running, waiting-review, passed, failed) mit korrekten Counts aus der State-Datei an. (2) Bei fehlenden aktiven Jobs (cmd_jobs) wird die Nachricht 'No running or waiting-review jobs.' ausgegeben und der Prozess endet sauber mit Exit-Code 0; cmd_status() zeigt bei leeren/fehlenden Tickets ebenfalls saubere Null-Zähler. (3) cmd_tail_audit() prüft die Existenz von audit.log und gibt bei Fehlschlag die klare Warnung 'WARNING: Audit log not found at ...' aus, ohne abzukrauschen.
