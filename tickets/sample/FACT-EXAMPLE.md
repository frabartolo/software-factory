# FACT-EXAMPLE — Beispiel-Ticket (gültig)

## Goal
Gerüst der Software-Factory anlegen: lokale Datei-Queue für den Ticket-Lifecycle,
maschinenlesbares Ticket-Schema und einen Validator.

## Success criteria
- Die Verzeichnisstruktur für alle Lifecycle-Stationen existiert (u. a. `tickets/new`).
- Dieses Beispielticket wird vom Validator akzeptiert (Exit 0).
- Ungültige Tickets (leeres Checks / fehlende Heading) werden mit einer lesbaren
  Meldung abgelehnt (Exit 1).

## Acceptance examples
1. Normal case: `python3 scripts/validate_factory_schema.py tickets/sample/FACT-EXAMPLE.md`
   liefert Exit 0.
2. Boundary case: Ein Ticket mit leerem `## Checks`-Abschnitt wird mit einer
   lesbaren Meldung abgelehnt.
3. Failure case: Ein Ticket ohne `## Budget`-Heading wird mit einer lesbaren
   Meldung abgelehnt.

## Forbidden
- Keine Implementierung des Runners.
- Keine Implementierung von Git-Worktrees.
- Kein Aufruf eines Modell-Endpoints.
- Keine Modell-Routing-Logik.

## Checks
- python3 scripts/validate_factory_schema.py tickets/sample/FACT-EXAMPLE.md
- find . -type d | grep 'tickets/new'

## Budget
max_walltime: 15m
max_turns: 8
max_files: 6
