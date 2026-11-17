# FACT-004 — Factory-Meta: Check-Pipeline wrapper für Projekt-Build/Test/Lint

<!-- source: nextcloud-deck board=7 stack="Backlog / Neu" card_id=100 -->
<!-- labels: Factory, infra, feature, bootstrap -->

## Goal

Add a configurable project-check wrapper so the factory can run build/test/lint for a given repository without hardcoding commands inside the agent logic.

## Success criteria

- A project config exists, e.g. `factory.config.yaml`.
- For each project, the runner can read a list of shell commands for checks.
- Checks are executed in the job environment and results are captured.
- Check results are written in a structured way for later reporting.

## Acceptance examples

1. Normal case:
   Running checks for a configured project executes all configured commands in order.
2. Boundary case:
   If a project has no checks configured, the runner reports that explicitly instead of silently succeeding.
3. Failure case:
   If a check command fails, the runner records the failure and continues to aggregate a summary rather than crashing the whole system.

## Forbidden

- No self-verification by the implementing agent.
- No merging.
- No deployment.
- No secrets in config.

## Checks

- python3 factory.py check --repo cotrack --dry-run
- python3 factory.py check --repo cotrack

## Budget

max_walltime: 25m
max_turns: 10
max_files: 6
