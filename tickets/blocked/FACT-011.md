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

## Cwd
cotrack

## Checks

- python3 -m pytest -v

## Budget

max_walltime: 35m
max_turns: 15
max_files: 10


## Factory-Result
- outcome: blocked
- model: kiara
- turns: 14
- files: ['cotrack/__init__.py', 'cotrack/model.py', 'cotrack/test_model.py', 'cotrack/web.py', 'factory.py']
- errors: ['walltime (2100s) überschritten']
- command-checks:
  - PASS (exit 0): python3 factory.py check --repo cotrack --dry-run

  - PASS (exit 0): python3 factory.py check --repo cotrack
- scenario-judge: FAIL (model=flaps) — Die Ticket-Detail-Ansicht enthält zwar ein Status-Dropdown, aber die UI-Formularübermittlung ist nicht mit dem Backend kompatibel: Das Formular sendet einen klassischen HTML-Formular-POST (application/x-www-form-urlencoded), während do_POST einen JSON-Body erwartet und sonst 400 'Invalid JSON body' zurückgibt. Damit ist der Normalfall 'new -> ready bleibt nach Refresh erhalten' über die UI nicht nachweisbar erfüllt. Zusätzlich zeigt die UI bei POST-Erfolg/Fehlern nur JSON-Antworten, nicht aber eine konsistente HTML-Fehlerdarstellung; die Persistenzfehlerbehandlung ist im Modell vorhanden, aber die UI zeigt den Fehler nicht als benutzerseitige Fehlermeldung.
- note: Check(s) fehlgeschlagen:  | judge: Die Ticket-Detail-Ansicht enthält zwar ein Status-Dropdown, 
