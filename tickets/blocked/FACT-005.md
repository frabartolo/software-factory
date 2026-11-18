# FACT-005 — Factory-Meta: Job-Report für jedes Ticket

<!-- source: nextcloud-deck board=7 stack="Backlog / Neu" card_id=101 -->
<!-- labels: Factory, infra, feature, bootstrap -->

## Goal

Create a job report format for every factory run so that a human gate can review what happened.

## Success criteria

- Each job produces a report file or report object.
- The report contains ticket ID, repo, branch/worktree, walltime, status, checks, and a short outcome summary.
- The report is written to a reports directory.
- Reports are human-readable and machine-parseable.

## Acceptance examples

1. Normal case:
   A simulated successful job writes a report with status `waiting-review`.
2. Boundary case:
   A job with zero changed files still writes a report.
3. Failure case:
   A failed check or aborted job still writes a report with failure reason.

## Forbidden

- No audit log yet, only report generation.
- No gate logic.
- No automatic merge.

## Checks

- python3 ../../factory.py report-test tickets/sample/FACT-EXAMPLE.md
- find ../../reports -type f

## Budget

max_walltime: 20m
max_turns: 10
max_files: 6


## Factory-Result
- outcome: blocked
- model: kiara
- turns: 9
- files: []
- errors: ['walltime (1200s) überschritten']
- command-checks:
  - (keine)
- note: Implementer hat keine Dateien erzeugt.
