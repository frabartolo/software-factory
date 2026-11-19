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

- python3 /home/kiara/software-factory/factory.py check --repo cotrack --dry-run
- python3 /home/kiara/software-factory/factory.py check --repo cotrack

## Budget

max_walltime: 25m
max_turns: 10
max_files: 6


## Factory-Result
- outcome: blocked
- model: kiara
- turns: 5
- files: ['factory.config.json']
- errors: ['Agent-JJSON unlesbar nach 3 Versuchen']
- command-checks:
  - PASS (exit 0): python3 /home/kiara/software-factory/factory.py check --repo cotrack --dry-run

  - PASS (exit 0): python3 /home/kiara/software-factory/factory.py check --repo cotrack
- scenario-judge: FAIL (model=flaps) — Es wurde nur eine Konfigurationsdatei bereitgestellt. Es fehlt eine nachweisbare Implementierung eines konfigurierbaren Projekt-Check-Wrappers/Runners, der die konfigurierten Befehle ausführt, fehlende Checks explizit meldet und fehlgeschlagene Checks aggregiert statt abzustürzen.
- note: Check(s) fehlgeschlagen:  | judge: Es wurde nur eine Konfigurationsdatei bereitgestellt. Es feh
