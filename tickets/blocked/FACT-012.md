# FACT-012 — Cotrack Pilot: Factory-Statusfelder im Modell und UI sichtbar machen

<!-- source: nextcloud-deck board=7 stack="Backlog / Neu" card_id=108 -->
<!-- labels: feature, pilot, Cotrack -->

## Goal

Expose factory-related ticket state and metadata clearly in cotrack UI so humans can use it for gate review and queue control.

## Success criteria

- Ticket detail shows current factory status.
- Ticket detail shows last run status or last check result if available.
- UI labels are consistent with Deck/factory naming.
- No breaking changes to existing ticket flows.

## Acceptance examples

1. Normal case:
   A ticket shows `status: waiting-review` and the most recent run outcome.
2. Boundary case:
   If no run data exists, the UI still renders cleanly with a neutral default.
3. Failure case:
   If run data is malformed, the UI falls back to a safe representation instead of crashing.

## Forbidden

- No automatic transitions based on hidden logic.
- No direct DB hacks.
- No auto-close tickets.
- No production data exposure.

## Cwd
cotrack

## Checks
node --check src/worker.js
node --check src/mcp.js
node --check src/store.js
node --check src/view.js
node smoke_test.js

## Budget

max_walltime: 40m
max_turns: 16
max_files: 12


## Factory-Result
- outcome: blocked
- model: kiara
- turns: 10
- files: ['cotrack/factory.yaml', 'cotrack/src/mcp.js', 'cotrack/src/worker.js', 'cotrack/wrangler.tom']
- command-checks:
  - PASS (exit 0): python3 /home/kiara/software-factory/factory.py check --repo cotrack --dry-run

  - PASS (exit 0): python3 /home/kiara/software-factory/factory.py check --repo cotrack
- scenario-judge: FAIL (model=flaps) — Die Implementierung stellt Factory-Status und Run-Outcome in JSON-Views bereit und behandelt fehlende sowie malformed Run-Daten defensiv. Allerdings fehlt eine echte UI-Darstellung, und die Worker-/MCP-Handler liefern im Normalfall keine tatsächlichen Run-Daten, sondern immer lastRun: null. Damit ist das Normalbeispiel nicht nachweisbar erfüllt.
- note: Check(s) fehlgeschlagen:  | judge: Die Implementierung stellt Factory-Status und Run-Outcome in
