# FACT-011 — Cotrack Pilot: Statusänderung über Dropdown in der Ticketansicht

<!-- source: nextcloud-deck board=7 stack="Backlog / Neu" card_id=107 -->
<!-- labels: feature, pilot, Cotrack -->

## Goal

Add a status-change dropdown in the ticket detail view of cotrack so a human can explicitly change ticket state.

## Success criteria

- The dropdown is visible in the ticket detail view.
- Valid factory statuses are available.
- Changing status persists the new value.
- The UI reflects the new status immediately.
- Existing tests/build remain green.

## Acceptance examples

1. Normal case:
   A ticket currently in `new` can be changed to `ready` and remains in `ready` after refresh.
2. Boundary case:
   Invalid transitions are either blocked or rejected clearly, depending on existing business rules.
3. Failure case:
   If persistence fails, the UI shows an error and the previous state remains consistent.

## Forbidden

- No automatic merge.
- No new dependencies without approval.
- No schema migration without explicit review.
- No unrelated refactoring.

## Checks

- npm run lint
- npm run build
- npm run test
- manual check: open ticket detail, change status, refresh page

## Budget

max_walltime: 35m
max_turns: 15
max_files: 10
