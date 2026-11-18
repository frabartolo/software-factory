# FACT-013 — Runner- und Deck-Compliance-Check

## Goal
Verifiziere den in PR #2 `ticket/FACT-013-findings` (Cursor) beschriebenen
Ablauf und schließe verbleibende Lücken: Eine Karte aus der Datei-Queue läuft
durch die Stationen und erreicht `tickets/done` NUR nach namentlicher
menschlicher Freigabe — nie automatisch. Lücken in `runner.py` /
`deck_sync.py` schließen und den Ablauf in der README dokumentieren.

## Success criteria
1. Die Datei-Queue ist die einzige Eingangsdatei für neue Vorgänge
   (`deck_sync.py` → `tickets/new/`).
2. Der Gate-Block stoppt bei fehlgeschlagenen Checks (Runner
   `shift_ticket(..., "blocked")`, nie `approved`).
3. Ein Ticket darf nie automatisch nach `done` verschoben werden, sondern
   nur bis `approved`.
4. Die menschliche Freigabe ist namentlich dokumentiert (z. B.
   Approved-Freigabe in README/Deck).
5. Die sechs Pflicht-Sektionen sind im Ticket-Validator abgedeckt
   (`validate_factory_schema.py`).
6. `max_turns` ist in den Budgets der Tickets gesetzt.

## Acceptance examples
- `deck_sync.py --once` importiert eine `Ready`-Card nach `tickets/new/`
  und validiert sie per `validate_ticket.py` (ungültig → skip).
- `runner.py --ticket <pfad>` verschiebt das Ticket nach Checks-Fehler nach
  `tickets/blocked/` (nicht `approved/` oder `done/`).
- `runner.py` verschiebt ein Ticket nur nach `tickets/approved/` (nicht
  `done/`) — die `done`-Station ist ausschließlich manuell.
- `validate_factory_schema.py` meldet fehlende Pflicht-Sektionen als Exit 1.
- Die README dokumentiert den 5-Station-Ablauf mit den Verzeichnissen
  `new/ ready/ running/ gate/ approved/ done/ blocked/`.

## Forbidden
- Keine `shift_ticket(..., "done")` in `runner.py` (kein auto-release).
- Keine Secrets (Keys, Passwörter, Tokens) in Dateien unter dem Repo.
- Keine Code-Execution aus Ticket-Inhalten (keine `exec`/`eval`/Shell-
  Einbettung).
- Keine Änderung des Ticket-Schemas (sechs Pflicht-Sektionen) ohne
  Update von `schema/ticket.schema.json`.
- Keine `approved`-Verschiebung ohne explizite menschliche Freigabe.

## Checks
- grep -q 'shift_ticket.*"approved"' ../../scripts/runner.py
- python3 -c "import pathlib; t=pathlib.Path('../../scripts/runner.py').read_text(); assert 'shift_ticket(current, \"done\"' not in t"
- python3 -c "import pathlib; t=pathlib.Path('../../scripts/deck_sync.py').read_text(); assert 'validate_ticket' in t"
- test -f ../../README.md && grep -qi 'queue' ../../README.md
- grep -qi 'gate\|approved' ../../README.md
- head -n 60 ../../scripts/runner.py | grep -q 'approved'

## Budget
max_walltime: 45min
max_turns: 16
max_files: 10


## Factory-Result
- outcome: blocked
- model: kiara
- turns: 16
- files: ['README.md', 'scripts/deck_sync.py', 'scripts/runner.py', 'scripts/validate_factory_schema.py']
- errors: ['max_turns erreicht, kein done']
- command-checks:
  - PASS (exit 0): grep -q 'shift_ticket.*"approved"' ../../scripts/runner.py

  - PASS (exit 0): python3 -c "import pathlib; t=pathlib.Path('../../scripts/runner.py').read_text(); assert 'shift_ticket(current, \"done\"' not in t"

  - PASS (exit 0): python3 -c "import pathlib; t=pathlib.Path('../../scripts/deck_sync.py').read_text(); assert 'validate_ticket' in t"

  - PASS (exit 0): test -f ../../README.md && grep -qi 'queue' ../../README.md

  - PASS (exit 0): grep -qi 'gate\|approved' ../../README.md

  - PASS (exit 0): head -n 60 ../../scripts/runner.py | grep -q 'approved'
- scenario-judge: FAIL (model=flaps) — Die meisten Kriterien sind erfüllt: deck_sync.py importiert Ready-Cards nach tickets/new/, validiert sie und überspringt ungültige Karten; runner.py stoppt nach approved und verschiebt niemals nach done; validate_factory_schema.py gibt bei fehlenden Pflicht-Sektionen Exit 1 zurück; README dokumentiert die geforderten Verzeichnisse. Es gibt jedoch eine nachweisbare Lücke: runner.py verschiebt Tickets nicht explizit nach tickets/running/, obwohl README und Akzeptanzkriterien die Station running/ als Verzeichnis im Ablauf verlangen. Zudem verwendet deck_sync.py nicht die im Kriterium genannte validate_ticket.py, sondern validate_factory_schema.py.
- note: Check(s) fehlgeschlagen:  | judge: Die meisten Kriterien sind erfüllt: deck_sync.py importiert 
