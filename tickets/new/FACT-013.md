# FACT-013 — Findings

<!-- source: nextcloud-deck board=7 stack="Ready / Bereit" card_id=120 -->
<!-- labels: Factory, Findings -->

**Quelle:** PR #2 `ticket/FACT-013-findings` (andere KI, Cursor)

****

Die zwei Steuerungen auf main zu einem Ablauf machen. Eine Karte aus Deck Ready läuft durch eine Queue, endet bei grünen Checks in der Review-Station und erreicht Done nur nach namentlicher menschlicher Freigabe.

****

- `scripts/runner.py` verschiebt ein bestandenes Ticket nach der Gate-Station und nicht nach `tickets/done`.
- Das Audit enthält für diesen Lauf kein Ereignis mit Station `done`.
- `scripts/deck_sync.py` legt Ready-Karten in `tickets/ready` ab, und der Runner liest diese Station.
- Der Runner ruft nur noch einen Validator auf. Der prüft die sechs Pflichtabschnitte, die drei Akzeptanzfälle und die Budget-Schlüssel.
- Kommandos aus dem Modell und aus den Check-Zeilen können `git push` und `git merge` nicht ausführen.
- Die README nennt die eine Queue, den Gate-Stopp und die eine Zugangsdatei.

****

1. Normal case:
   Ein gültiges Ticket in `tickets/ready` mit grünen Checks liegt danach in der Review-Station. `tickets/done` bleibt unverändert, und das Audit hat keinen `done`-Eintrag.

2. Boundary case:
   `tickets/ready` ist leer. Der Runner beendet sich mit Exit-Code 0 und schreibt kein Done.

3. Failure case:
   Eine Check-Zeile oder ein Modell-Kommando enthält `git push` oder `git merge`. Der Lauf lehnt das Kommando ab, verschiebt die Karte nicht nach Done und mergt nichts.

****

- Kein automatisches Merge.
- Kein Done ohne namentlichen Approver.
- Keine Secrets, App-Passwörter oder Tokens ins Repo, ins Audit oder in Deck-Kommentare.
- Keine Cotrack-UI und kein Umbau von FACT-011 oder FACT-012.
- Die bestehenden Skripte `runner.py` und `deck_sync.py` nicht durch ein zweites Runner-Programm ersetzen. Die Lücke in diesen Dateien schließen.

****

- python3 scripts/validate_ticket.py tickets/new/FACT-013.md
- python3 scripts/validate_factory_schema.py tickets/new/FACT-013.md
- python3 -c "import pathlib; t=pathlib.Path('scripts/runner.py').read_text(); assert 'shift_ticket(current, \"done\"' not in t"

****

max_walltime: 45m
max_turns: 16
max_files: 10

---
*Owner bleibt der Mensch (stefan). Karte ist Lead-Auftrag an die andere KI (Option B).*
