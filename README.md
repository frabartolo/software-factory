# Software-Factory — lokales Gerüst (2 Personen)

Lokale Software-Factory für den Haushalt (2 Personen: Nutzer + Sohn). Tickets kommen aus dem Nextcloud-Deck-Board **„Software-Factory"** (Board 7).
**Das Deck ist die Single Source of Truth:** Alle Vorgänge werden dort
**bearbeitet**, **ergänzt** und **durch den Prozess geschoben**. Die lokale
**Datei-Queue** (`tickets/`) ist nur ein abgeleiteter Puffer — jede Station
der Pipeline ist ein Verzeichnis, jedes Ticket eine Markdown-Datei.

## Pipeline & Stations-Mapping (5 Stationen)

1. **Aufnahme** → `tickets/new` (Deck: Backlog / Neu)
2. **Startklar** → `tickets/ready` (Deck: Ready / Bereit)
3. **Agenten-Arbeit** → `tickets/running` (Deck: Running / In Arbeit)
4. **Checks / menschliches Gate** → `tickets/gate` (Deck: Waiting Review / Gate)
5. **Freigabe → Release** → `tickets/approved` → `tickets/done`
   (Deck: Approved / Freigegeben → Done / Erledigt)
   + Fehler → `tickets/blocked` (Deck: Blocked / Failed)

> Hinweis: Für dieses PoC (FACT-001) wird nur das **Gerüst** angelegt und der
> **Validator** geprüft. Die eigentliche Automatisierung der Stationen folgt in
> FACT-002 (Runner), FACT-003 (Git-Worktree) u. a.

## Verzeichnisstruktur

```
tickets/
  new/            # Aufnahme (neue Tickets landen hier)
  ready/          # Startklar
  running/        # Agenten-Arbeit
  gate/           # Checks / menschliches Gate
  approved/       # Freigegeben
  done/           # Release
  blocked/        # Fehler
  sample/         # Beispieldateien (nicht Teil der aktiven Queue)
scripts/
  validate_factory_schema.py   # Validiert Tickets gegen das Schema
schema/
  ticket.schema.json           # Maschinenlesbares Ticket-Schema
README.md
```

## Ticket-Schema

Ein Ticket ist eine Markdown-Datei mit diesen **Pflicht-Sektionen** (`##`):

- `## Goal`
- `## Success criteria`
- `## Acceptance examples`
- `## Forbidden`
- `## Checks`
- `## Budget`
- `## Dependencies` — vorausgesetzte Karten `FACT-NNN`, oder `keine`

Jede Pflicht-Sektion muss **nicht leer** sein. Die Sektion `## Budget` muss die
maschinenlesbaren Schlüssel `max_walltime`, `max_turns` und `max_files` im Format
`schlüssel: Wert` enthalten. Die vollständige, maschinenlesbare Definition liegt
in `schema/ticket.schema.json`.

## Validierung

```
python3 scripts/validate_factory_schema.py tickets/sample/FACT-EXAMPLE.md
```

- **Exit 0** → Ticket gültig (alle Pflichtfelder vorhanden + nicht leer, Budget vollständig).
- **Exit 1** → Ticket ungültig (fehlende/leere Pflichtfelder, fehlende
  Budget-Schlüssel oder keine Sektionen). Die Meldung ist menschenlesbar.

Die Zeilen unter `## Checks` enthalten die Kommandos, die die jeweilige Station
abführen soll (z. B. `find . -type d | grep 'tickets/new'`).

## Ablauf

Der laufende Weg ist das Deck. `scripts/agent_pipeline.py` führt eine Karte von Neu bis Approved. Die Anforderungen, Abhängigkeiten, Rollen und Grenzen stehen in `docs/anforderungen.md`.

Die Verzeichnisse unter `tickets/` sind der abgeleitete Puffer. `deck_sync.py` schreibt Ready-Karten noch nach `tickets/new`, der Datei-Runner liest `tickets/new`, `factory.py run-once` liest `tickets/ready`. Das ist offen und in `docs/anforderungen.md` unter „Noch nicht erfüllt“ beschrieben.
