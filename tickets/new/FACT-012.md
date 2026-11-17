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

## Checks

- npm run lint
- npm run build
- npm run test
- manual check: verify at least one ticket with no run data renders safely

## Budget

max_walltime: 40m
max_turns: 16
max_files: 12
