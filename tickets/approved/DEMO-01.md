# DEMO-01 — Pipeline-Validierung (kiara implementiert, flaps prüft)

## Goal
Lege in der Workspace die Datei `greet.py` an. Sie muss eine Funktion `greet(name)` enthalten, die den String `Hallo, ` + name zurückgibt (z. B. greet('Welt') -> 'Hallo, Welt').

## Success criteria
- `python3 -c "from greet import greet; print(greet('Welt'))"` gibt `Hallo, Welt` aus.
- `python3 -c "from greet import greet; print(greet(''))"` gibt `Hallo, ` aus.

## Acceptance examples
- Normalfall: greet('Welt') liefert 'Hallo, Welt'.
- Grenzfall: greet('') liefert 'Hallo, ' (leerer Name ist erlaubt).
- Fehlerfall: greet(None) wirft eine Exception (keine leisen Strings).

## Forbidden
- Keine externen Pakete (nur Python-Standardbibliothek).
- Keine Datei außer `greet.py` in der Workspace-Root.
- Keine Ausgabe von Prosa in die Artefakte (nur die Datei selbst).

## Checks
- python3 -c "from greet import greet; assert greet('Welt')=='Hallo, Welt'; assert greet('')=='Hallo, '"

## Budget
max_walltime: 10m
max_turns: 8
max_files: 3


## Factory-Result
- outcome: approved
- model: kiara
- turns: 7
- files: ['greet.py']
- command-checks:
  - PASS (exit 0): python3 -c "from greet import greet; assert greet('Welt')=='Hallo, Welt'; assert greet('')=='Hallo, '"
- scenario-judge: PASS (model=flaps) — greet.py enthält die Funktion greet(name). greet('Welt') liefert 'Hallo, Welt', greet('') liefert 'Hallo, ', und greet(None) wirft eine TypeError-Exception.
