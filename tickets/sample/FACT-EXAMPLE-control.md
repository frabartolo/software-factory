---
id: FACT-EXAMPLE
title: Sample ticket for factory schema test
task_class: small-feature
repo: factory
base_branch: main
status: ready
owner: human
approver:
model_policy: kiara-first
max_walltime: 15m
max_turns: 8
max_files: 5
---

## Goal

Validate that the factory schema parser accepts a fully-formed ticket.

## Success criteria

- Parser accepts the sample file.
- Required fields are readable.
- Invalid missing sections are rejected.

## Acceptance examples

1. Normalfall:
   Die Datei wird ohne Fehler gelesen.

2. Grenzfall:
   Ein optionales Feld `approver` darf leer sein.

3. Fehlerfall:
   Wenn `Success criteria` fehlt, lehnt der Parser die Datei ab.

## Forbidden

- No model call
- No push
- No merge
- No production access

## Checks

- python3 scripts/validate_ticket.py tickets/sample/FACT-EXAMPLE.md

## Budget

max_walltime: 15m
max_turns: 8
max_files: 5
