---
id: INVALID-MISSING-ACCEPTANCE
title: Ticket without acceptance examples
task_class: small-feature
repo: factory
base_branch: main
status: ready
owner: human
approver:
model_policy: kiara-first
max_walltime: 10m
max_turns: 4
max_files: 2
---

## Goal

This ticket is intentionally incomplete so the validator must reject it.

## Success criteria

- The validator reports the missing section by name.

## Forbidden

- No model call
- No push
- No merge

## Checks

- python3 scripts/validate_ticket.py tickets/sample/INVALID_MISSING_ACCEPTANCE.md

## Budget

max_walltime: 10m
max_turns: 4
max_files: 2
