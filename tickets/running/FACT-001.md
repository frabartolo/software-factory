# FACT-001 — Factory-Meta: Ticket-Schema und Datei-Queue-Gerüst

<!-- source: nextcloud-deck board=7 stack="Ready / Bereit" card_id=97 -->
<!-- labels: Factory, infra, feature, bootstrap -->

## Goal

A clear, machine-readable ticket schema and the local file queue structure for the factory are created on kiara.

## Success criteria

- A local factory directory tree exists for ticket lifecycle states.
- A sample ticket file follows the schema and is accepted by a validator.
- Invalid tickets are rejected with clear error messages.

## Acceptance examples

1. Normal case:
   A sample ticket exists and contains all required sections:
   Goal, Success criteria, Acceptance examples, Forbidden, Checks, Budget.
2. Boundary case:
   A ticket with an empty Checks section is rejected by the validator.
3. Failure case:
   A malformed or missing required heading is rejected with a readable error message.

## Forbidden

- Do not implement the runner yet.
- Do not implement Git worktrees yet.
- Do not call any model endpoint.
- Do not implement model routing.

## Checks

- python3 scripts/validate_factory_schema.py tickets/sample/FACT-EXAMPLE.md
- find . -type d | grep 'tickets/new'

## Budget

max_walltime: 15m
max_turns: 8
max_files: 6
