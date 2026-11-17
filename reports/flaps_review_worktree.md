### flaps-Review (2026-11-17) — worktree.py + runner.py Fixes
(dt=128s, response_len=2743) — via llm_call + fixed reasoning_content fallback
## Kurzfazit
Die Architektur ist **grundsätzlich plausibel**: Runner-Engine mit Pipeline pick -> VALIDATE -> ROUTE -> IMPLEMENT -> CHECK -> STATUS -> REPORT. Umsetzung von worktree.py ist pragmatisch, aber an mehreren Stellen **zu destruktiv, zu implizit, zu wenig robust**.
Größter Risiko-Bereich: **Sicherheit und Idempotenz**:
- worktree.py kann unter Umständen fremde Verzeichnisse löschen.
- runner.py sollte Tickets atomar claimen, sonst Race Conditions.
- llm_call sollte nicht blind reasoning_content als Antwort verwenden.
- Der Judge-Pfad sollte Deliverables sauber filtern und gegen Prompt Injection härten.

# 1) Architektur plausibel? Ja.
pick muss atomar claimen (Race: Runner A & B lesen beide T1 als new -> doppelte Verarbeitung).
Empfehlung: claim(ticket_id) atomar new -> running (Datei-Lock, atomarer Rename, SQLite, oder claimed_by/claimed_at + CAS).
Ohne Claim ist die Pipeline nicht robust.

# 2) STATUS ...
(llm_call soll nicht blind reasoning_content verwenden; Judge-Pfad gegen Prompt Injection härten; worktree.py sicher/idempotent)
