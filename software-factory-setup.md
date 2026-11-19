Ja — hier ist die vollständige Datei. Du kannst den folgenden Markdown-Codeblock als Datei speichern, z. B. als:

```text
software-factory-setup.md
```

und dann direkt in Nextcloud Notizen einfügen.

````markdown
# Local Software Factory Setup

**Stand:** 13.11.2026  
**Zweck:** Lokale, agentische Software-Factory mit Nextcloud Deck als Kontrollfläche, kiara als Ausführungs-Host, Hermes/KIara als Aufnahme- und Kontrollkanal, OpenCode als Implementierungs-Worker und klar getrennten Rollen.

---

## 1. Kurzfassung

Wir bauen eine lokale Software-Factory nach diesem Prinzip:

```text
Discord Hermes/KIara
        │
        │ Aufgaben aufnehmen, klären, Status kontrollieren, Freigabe anstoßen
        ▼
Nextcloud Deck „Software Factory“
        │
        │ Tickets, Status, Review, Gate
        ▼
Factory Runner / Orchestrator auf kiara
        │
        ├── Ticket validieren
        ├── Git Worktree anlegen
        ├── OpenCode Worker starten
        ├── Build/Test/Lint/Szenario-Checks ausführen
        ├── Job-Report erzeugen
        ├── Audit-Log schreiben
        └── Deck-Status zurückschreiben
```

Wichtige Rollen:

- **Nextcloud Deck (Single Source of Truth):** menschliche Kontrolle, Ticket-Queue, Statusanzeige, Review-Historie — dort werden Vorgänge bearbeitet, ergänzt und durch den Prozess geschoben
- **Hermes/KIara im Discord:** Aufnahme, Rückfragen, Spec-Engineering, Statuskontrolle, Freigabe-Anstoß, Review-Zusammenfassung
- **Factory Runner / Orchestrator auf kiara:** eigentliche Factory-Logik
- **OpenCode:** Implementierungs-Agent
- **Checks / Verifikation:** independent von implementierendem Agenten
- **Mensch:** finales Gate und Verantwortung

---

## 2. Grundsatz

Die Factory ist kein Modell, kein Chatbot, keine einzelne App, sondern ein System:

```text
Mensch steuert Tickets.
Runner orchestriert den Prozess.
OpenCode implementiert.
Checks verifizieren.
Mensch gibt frei.
Hermes unterstützt Aufnahme und Kontrolle.
Audit dokumentiert alles.
```

Die Factory soll nicht blind automatisch Done setzen. Sie soll wiederholbar, steuerbar und vorhersehbar arbeiten.

---

## 3. Hosts und Komponenten

### 3.1 kiara

Haupt-Fabric-Host.

Aufgaben:

- Ollama / OpenAI-kompatibler Endpunkt:

```text
http://127.0.0.1:8080/v1
```

- Modell Default:

```text
bonsai2-27b
```

- OpenCode installiert und angebunden.
- Factory Runner / Orchestrator läuft lokal.
- Repositories lokal vorhanden.
- Git Worktrees laufen isoliert pro Task.
- Build/Test/Lint laufen lokal.
- Audit-Log liegt lokal.

Wichtig:

- OpenCode sollte nicht automatisch Merge, Push oder Deploy ausführen.
- Nextcloud-Zugangsdaten gehören nicht in OpenCode.
- Produktionszugriff ist gesperrt.

### 3.2 flaps

Optional, intermittierend verfügbar.

Zweck:

- schwerere Review-/Verifikationsaufgaben
- Cross-Check-Judge
- tiefe Diff-Analyse
- Spec-Qualitätsprüfung
- Szenario-Review

Endpunkt-Beispiel:

```text
http://192.168.5.20:8080/v1
```

Health-Check vor jedem Job:

```bash
curl -s http://192.168.5.20:8080/v1/models
```

Aktuell bekannte Besonderheit:

- Modell kann `reasoning_content` statt `content` zurückgeben.
- Harness/Adapter sollte beide Felder lesen.
- `max_tokens` entsprechend höher stellen.

### 3.3 Nextcloud

Zweck:

- Deck „Software Factory“ als Ticket-Queue
- menschliche Steuerung
- Status und Review-Fläche
- optional Notizen, Dateien, Specs

Empfohlene Instanz:

```text
https://wilhelmscloud
```

Board:

```text
Software Factory
Board-ID: 7
```

---

## 4. Rollenmodell

Die Factory braucht getrennte Rollen. Nicht nur technisch, sondern auch prozessual.

### 4.1 Mensch

Verantwortlich für:

- finale Freigabe
- Gate-Entscheidung
- Verantwortung für Merge/Deploy
- Review bei kritischen Änderungen

Regel:

```text
Kein Ticket ist Done ohne menschliches Gate, solange Auto-Merge nicht explizit freigeschaltet ist.
```

### 4.2 Hermes/KIara im Discord

Verantwortlich für:

- Aufgaben aufnehmen
- Rückfragen stellen
- Specs vervollständigen
- Karten nach `Ready` bringen, wenn Spec vollständig ist
- Statuskontrolle
- Review-Zusammenfassung
- Freigabe nur nach expliziter menschlicher Freigabe

Empfehlung:

Hermes sollte einen eigenen Nextcloud-Account haben:

```text
factory-hermes
```

Hermes darf am Anfang nicht:

- `Done` setzen
- Merge ausführen
- Push ausführen
- ohne namentliche menschliche Freigabe `Approved` setzen
- Repo-Secrets sehen
- OpenCode direkt starten
- Checks selbst grün machen

### 4.3 Factory Runner

Verantwortlich für:

- Tickets aus `Ready` lesen
- Ticket validieren
- Worktree anlegen
- OpenCode starten
- Checks ausführen
- Reports schreiben
- Statuswechsel im Deck
- Audit-Log appenden

Empfohlener Nextcloud-Account:

```text
factory-runner
```

Runner darf:

```text
Ready -> Running
Running -> Waiting Review
Running -> Blocked / Failed
```

Runner darf am Anfang nicht:

```text
Waiting Review -> Approved
Waiting Review -> Done
Approved -> Done
Merge
Push
Deploy
```

### 4.4 OpenCode

Verantwortlich für:

- Implementierung im zugewiesenen Worktree
- kleine, fokussierte Änderungen
- Beantwortung der Task-Spec
- keine Selbstverifikation als Done

Empfehlung:

OpenCode bekommt keinen Nextcloud-Zugang.

OpenCode bekommt nur:

- Ticket-Spec
- Repo-Worktree
- erlaubte Tools
- Budget
- Prompt-Policy

### 4.5 Observer

Optional, aber sinnvoll.

Zweck:

- Status lesen
- Queue anzeigen
- Audit lesen
- Dashboard versorgen

Empfohlener Account:

```text
factory-observer
```

Rechte:

- nur lesen
- keine Kartenbewegung
- keine Beschreibung ändern
- keine Kommentare schreiben

---

## 5. Nextcloud Deck: Listen

Im Board `Software Factory` sollten diese Listen/Stacks existieren:

```text
Backlog
Ready
Running
Waiting Review
Approved
Done
Blocked / Failed
```

Bedeutung:

### Backlog

- rohe Ideen
- unvollständige Tickets
- keine automatische Ausführung

### Ready

- vollständig beschrieben
- akzeptanzgetestet definierbar
- Runner darf das Ticket holen

### Running

- Runner/OpenCode arbeitet aktuell
- Mensch editiert Karte während Laufzeit nicht

### Waiting Review

- Agent fertig
- Checks ausgeführt
- Menschliches Gate erforderlich

### Approved

- menschliche Freigabe vorhanden
- Merge/Deploy darf vorbereitet werden

### Done

- Code tatsächlich gemerged/deployed
- nicht nur „Agent fertig“

### Blocked / Failed

- Agent-Fehler
- Review abgelehnt
- Spec unvollständig
- Task zu groß
- Runner-Fehler
- Modell-/Infrafehler

---

## 6. Factory-Zustandsmaschine

Empfohlene MVP-Zustände:

```text
Backlog
Ready
Running
Waiting Review
Approved
Done
Blocked / Failed
```

Empfohlene Übergänge:

```text
Backlog -> Ready
Backlog -> Blocked / Failed

Ready -> Running
Ready -> Blocked / Failed

Running -> Waiting Review
Running -> Blocked / Failed

Waiting Review -> Approved
Waiting Review -> Blocked / Failed

Approved -> Done
```

Verboten für MVP:

```text
Backlog -> Done
Ready -> Done
Running -> Done
Waiting Review -> Done
Backlog -> Approved
Ready -> Approved
```

Grund:

- Done erfordert Approved.
- Approved erfordert menschliche Freigabe.
- Running und Waiting Review werden durch Runner gesetzt.

---

## 7. Nextcloud OAuth und getrennte Zugänge

Wenn Nextcloud-OAuth verwendet wird, sollten mehrere Clients/Accounts getrennt angelegt werden.

Empfehlung:

```text
OAuth-Client: Factory Runner
Nextcloud-User: factory-runner

OAuth-Client: Factory Hermes
Nextcloud-User: factory-hermes

OAuth-Client: Factory Observer
Nextcloud-User: factory-observer
```

Optional:

```text
OAuth-Client: Factory Panel
Nextcloud-User: factory-panel
```

Warum getrennt?

- Audit kann zuordnen, wer welche Aktion ausführte.
- Ein geleaktes Credential ist nicht sofort Factory-full-access.
- Runner und Hermes dürfen nicht dieselbe Identität missbrauchen.
- Hermes kann nicht unbemerkt Running/WaitingReview setzen.
- Observer kann nur lesen.

Wichtig:

> OAuth-Client allein ist nicht die Sicherheitsgrenze.  
> Die entscheidende Trennung entsteht durch:
>
> - eigener Nextcloud-User
> - eigener Token/App-Passwort
> - getrennte Env-Datei
> - Policy-Checks im Factory-Adapter
> - Audit-Log mit Rolle und Actor

---

## 8. Empfohlene Nextcloud-Berechtigungen für Board 7

Board:

```text
Software Factory
Board-ID: 7
```

Empfohlene Mitglieder:

```text
dein menschlicher Nextcloud-User   Owner/Admin
factory-runner                     Board-Mitglied, darf bearbeiten
factory-hermes                     Board-Mitglied, darf bearbeiten
factory-observer                   optional, nur lesen
```

Aber: Die echten Rollenregeln müssen im Factory-Code durchgesetzt werden, weil Nextcloud Deck nicht feingranular erzwingt:

```text
darf nur Ready lesen
darf nur Running setzen
darf nur Approved setzen
```

Deshalb braucht es Factory-Policies.

---

## 9. Factory-Dateistruktur auf kiara

Empfohlene Struktur:

```text
/srv/factory/
├── config/
│   ├── factory.yaml
│   ├── roles.yaml
│   └── projects.yaml
├── prompts/
│   ├── orchestrator.md
│   ├── implementer.md
│   ├── reviewer.md
│   └── hermes_intake.md
├── scripts/
│   ├── deck.py
│   ├── factoryd.py
│   ├── run_job.py
│   ├── validate_ticket.py
│   ├── audit_append.py
│   └── hermes_adapter.py
├── tickets/
│   ├── sample/
│   │   └── FACT-EXAMPLE.md
│   ├── new/
│   ├── ready/
│   ├── running/
│   ├── waiting-review/
│   ├── approved/
│   ├── done/
│   └── blocked/
├── worktrees/
├── reports/
├── logs/
└── audit/
    └── audit.jsonl
```

Auf kiara vorbereiten:

```bash
sudo useradd -m -s /bin/bash factory
sudo mkdir -p /srv/factory/{config,prompts,scripts,repos,worktrees,reports,logs,audit}
sudo mkdir -p /etc/factory
sudo chown -R factory:factory /srv/factory
```

---

## 10. Env-Dateien für getrennte Nextcloud-Rollen

Empfohlene Dateien:

```text
/etc/factory/runner.env
/etc/factory/hermes.env
/etc/factory/observer.env
```

Beispiel:

```bash
sudo install -o factory -g factory -m 0600 /dev/null /etc/factory/runner.env
sudo install -o factory -g factory -m 0600 /dev/null /etc/factory/hermes.env
sudo install -o factory -g factory -m 0600 /dev/null /etc/factory/observer.env
```

Inhalt runner.env:

```bash
NC_BASE=https://wilhelmscloud
NC_USER=factory-runner
NC_APP_PASSWORD=HIER_DEIN_APP_PASSWORD_FUER_RUNNER
FACTORY_BOARD_ID=7
FACTORY_BOARD_NAME=Software Factory
FACTORY_TOKEN_SOURCE=app_password
```

Inhalt hermes.env:

```bash
NC_BASE=https://wilhelmscloud
NC_USER=factory-hermes
NC_APP_PASSWORD=HIER_DEIN_APP_PASSWORD_FUER_HERMES
FACTORY_BOARD_ID=7
FACTORY_BOARD_NAME=Software Factory
FACTORY_TOKEN_SOURCE=app_password
```

Inhalt observer.env:

```bash
NC_BASE=https://wilhelmscloud
NC_USER=factory-observer
NC_APP_PASSWORD=HIER_DEIN_APP_PASSWORD_FUER_OBSERVER
FACTORY_BOARD_ID=7
FACTORY_BOARD_NAME=Software Factory
FACTORY_TOKEN_SOURCE=app_password
```

Wenn OAuth statt App-Passwörtern verwendet wird:

```bash
NC_BASE=https://wilhelmscloud
NC_USER=factory-runner
NC_OAUTH_CLIENT_ID=...
NC_OAUTH_CLIENT_SECRET=...
NC_OAUTH_ACCESS_TOKEN=...
NC_OAUTH_REFRESH_TOKEN=...
FACTORY_BOARD_ID=7
FACTORY_TOKEN_SOURCE=oauth
```

Wichtig:

- niemals in Git
- niemals ins Deck
- niemals ins Audit-Log
- niemals in Discord
- niemals in Karten
- Dateirechte auf `0600`

---

## 11. Factory-Konfiguration

Beispiel: `/srv/factory/config/factory.yaml`

```yaml
board:
  id: 7
  name: Software Factory

stacks:
  backlog: "Backlog"
  ready: "Ready"
  running: "Running"
  waiting_review: "Waiting Review"
  approved: "Approved"
  done: "Done"
  blocked: "Blocked / Failed"

models:
  default_worker: kiara
  worker_model: bonsai2-27b
  kiara_endpoint: http://127.0.0.1:8080/v1
  flaps_endpoint: http://192.168.5.20:8080/v1
  flaps_model: qwen3.8-flash-next-iq3_s

routing:
  kiara:
    role: implementation_default
    health:
      endpoint: http://127.0.0.1:8080/v1/models
      required: true
  flaps:
    role: review_verification
    health:
      endpoint: http://192.168.5.20:8080/v1/models
      required: false
    on_unavailable:
      - decompose_for_kiara
      - queue_for_next_window
      - escalate_human_with_spec

limits:
  queue_depth: 2
  poll_seconds: 30
  max_walltime_minutes: 30
  max_turns: 15
  max_files: 10

gate:
  auto_merge: false
  require_human_approval: true
  named_approver_required: true
  zero_gate_escape: true

harness:
  runner_env: /etc/factory/runner.env
  hermes_env: /etc/factory/hermes.env
  observer_env: /etc/factory/observer.env
  implementation_env: none
```

---

## 12. Rollen-Policies

Beispiel: `/srv/factory/config/roles.yaml`

```yaml
accounts:
  runner:
    nextcloud_user: factory-runner
    role: runner
    label: factory-runner

  hermes:
    nextcloud_user: factory-hermes
    role: hermes
    label: factory-hermes

  observer:
    nextcloud_user: factory-observer
    role: observer
    label: factory-observer

policies:
  runner:
    can_read_board: true
    can_comment: true
    can_update_description: true
    allowed_transitions:
      - from: "Ready"
        to: "Running"
      - from: "Ready"
        to: "Blocked / Failed"
      - from: "Running"
        to: "Waiting Review"
      - from: "Running"
        to: "Blocked / Failed"
    forbidden_transitions:
      - from: "Waiting Review"
        to: "Approved"
      - from: "Waiting Review"
        to: "Done"
      - from: "Approved"
        to: "Done"

  hermes:
    can_read_board: true
    can_comment: true
    can_update_description: true
    allowed_transitions:
      - from: "Backlog"
        to: "Ready"
      - from: "Backlog"
        to: "Blocked / Failed"
      - from: "Ready"
        to: "Blocked / Failed"
      - from: "Waiting Review"
        to: "Approved"
      - from: "Waiting Review"
        to: "Blocked / Failed"
    approve_requires_human_name: true
    forbidden_transitions:
      - from: "Ready"
        to: "Running"
      - from: "Running"
        to: "Waiting Review"
      - from: "Waiting Review"
        to: "Done"
      - from: "Approved"
        to: "Done"

  observer:
    can_read_board: true
    can_comment: false
    can_update_description: false
    allowed_transitions: []
```

Wichtig:

Diese Policies müssen im Adapter erzwungen werden. OAuth/App-User allein reicht nicht.

---

## 13. Projekt-Konfiguration

Beispiel: `/srv/factory/config/projects.yaml`

```yaml
projects:
  factory:
    repo: /srv/factory/repos/factory
    base_branch: main
    checks:
      - python3 -m py_compile scripts/deck.py
      - python3 -m py_compile scripts/factoryd.py
      - python3 -m py_compile scripts/run_job.py
      - python3 -m py_compile scripts/validate_ticket.py
      - python3 scripts/validate_ticket.py tickets/sample/FACT-EXAMPLE.md
      - python3 scripts/factoryd.py --once --dry-run

  cotrack:
    repo: /srv/factory/repos/cotrack
    base_branch: main
    checks:
      - npm run lint
      - npm run build
      - npm run test

  example-web:
    repo: /srv/factory/repos/example-web
    base_branch: main
    checks:
      - npm run lint
      - npm run build
      - npm run test
      - npx playwright test
```

Der Runner ermittelt das Projekt:

1. aus Ticket-Feld `repo`
2. aus Label wie `Cotrack`
3. aus Deck-Label
4. aus expliziter Ticket-Metadatei

Beispiel:

```text
Repo: cotrack
Branch: main
Labels: Cotrack, feature
```

---

## 14. Ticket-Schema

Ein Ticket braucht folgende Abschnitte:

```markdown
## Goal

## Success criteria

## Acceptance examples

1. Normalfall:
2. Grenzfall:
3. Fehlerfall:

## Forbidden

## Checks

## Budget

max_walltime: 30m
max_turns: 15
max_files: 10
```

Empfohlene Metadaten:

```markdown
---
id: FACT-XXX
title: ...
task_class: small-feature
repo: cotrack
base_branch: main
status: ready
owner: human
approver:
model_policy: kiara-first
max_walltime: 30m
max_turns: 15
max_files: 10
---
```

Validator muss ablehnen, wenn Pflichtfelder fehlen:

- Goal
- Success criteria
- Acceptance examples
- Forbidden
- Checks
- Budget

Das ist wichtig, damit die Fabrik nicht mit unklaren Tickets arbeitet.

---

## 15. Sample-Ticket für Factory-Validierung

Datei:

```text
/srv/factory/tickets/sample/FACT-EXAMPLE.md
```

```markdown
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
```

---

## 16. Factory-Prompts

### 16.1 Orchestrator-Prompt

Datei:

```text
/srv/factory/prompts/orchestrator.md
```

```markdown
# Factory Orchestrator Policy

You are the process controller for a local software factory.

## Hard rules

1. You never execute implementation yourself if a worker agent is available.
2. You never merge, push, deploy, or mark a ticket as Done directly.
3. You never allow a ticket to bypass the human gate.
4. You never let the implementing agent verify itself as done.
5. You enforce task budgets: walltime, turns, file count.
6. You prepare worktrees, collect reports, and move tickets to Waiting Review.
7. If a task is too large, you reject or decompose it.

## Allowed states

- Ready: may start
- Running: currently executed
- Waiting Review: report written, human gate required
- Blocked / Failed: stop and explain
- Approved: human gate passed
- Done: only after human approval and actual merge/deploy

## Gate escape protection

A ticket may only move to Done if:
- it was previously Approved,
- a named human approver exists,
- checks and report are present,
- merge/deploy happened.

## Model policy

- kiara is default worker.
- flaps is optional reviewer/verifier when reachable.
- OpenRouter is optional and budget-controlled.
- No model switching mid-task without checkpointing and logging.

## Audit requirement

Every state transition must append an audit entry:

```json
{
  "timestamp": "...",
  "ticket": "...",
  "event": "...",
  "from": "...",
  "to": "...",
  "actor": "...",
  "role": "..."
}
```
```

### 16.2 Implementer-Prompt

Datei:

```text
/srv/factory/prompts/implementer.md
```

```markdown
# Factory Implementer Prompt

You are the implementing agent for one factory ticket.

## Scope

- Work only inside the assigned worktree.
- Do not touch other repositories or worktrees.
- Do not push.
- Do not merge.
- Do not deploy.
- Do not access production systems.
- Do not access secrets unless explicitly provided by the runner.
- Do not modify acceptance criteria to make the task pass.

## Task behavior

- Start by reading the ticket spec.
- If the spec is ambiguous, stop and report the exact blocker.
- Keep the diff small and focused.
- Prefer existing project patterns.
- Stop when budget is reached.
- If too many files are required, stop and report scope escalation.

## Required output

At the end, produce:

1. Changed files summary
2. Commands executed
3. Open issues
4. Suggested checks
5. Risk assessment

## Forbidden

- No self-declared Done.
- No silent scope growth.
- No hidden dependency installation.
- No rewriting project config without ticket approval.
```

### 16.3 Reviewer-Prompt

Datei:

```text
/srv/factory/prompts/reviewer.md
```

```markdown
# Factory Reviewer / Judge Prompt

You are an independent reviewer for a completed factory job.

You do NOT implement. You do NOT merge.

## Review focus

- Does the diff satisfy the acceptance examples?
- Are there regressions?
- Did the agent weaken tests or checks?
- Are forbidden areas untouched?
- Are edge cases handled?
- Is the diff reviewable?

## Output format

### Verdict

- APPROVE
- APPROVE_WITH_COMMENTS
- REQUEST_CHANGES

### Findings

1. ...
2. ...

### Test / scenario coverage

- ...

### Residual risk

- ...
```

### 16.4 Hermes Intake-Prompt

Datei:

```text
/srv/factory/prompts/hermes_intake.md
```

```markdown
# Hermes/KIara Factory Intake Prompt

Du bist der Factory-Controller im Discord.

## Grundrolle

Du hilfst Menschen, Tickets für die lokale Software-Factory korrekt aufzunehmen, zu klären und in die Factory-Queue zu überführen.

Du bist nicht der Implementierungs-Agent.
Du bist nicht der Merge-Agent.
Du bist nicht der finale Gate-Owner, außer ein Mensch autorisiert explizit eine Freigabe mit namentlichem Approver.

## Aufnahmeprozess

Wenn ein Mensch ein Ticket anlegt, stelle Rückfragen, bis die Spec vollständig ist.

Pflichtfelder:

1. Ziel
2. Akzeptanzbeispiele
   - Normalfall
   - Grenzfall
   - Fehlerfall
3. Erfolgskriterien
4. Repo/Projekt
5. Task-Klasse
6. Nicht tun / Forbidden
7. Checks / Befehle
8. Budget
   - max_walltime
   - max_turns
   - max_files

Erst wenn alle Felder sauber gefüllt sind, darfst du die Karte nach `Ready` bewegen.

## Ready-Regel

Eine Karte darf nur `Ready` sein, wenn ein Runner sie ohne weitere Klärung bearbeiten könnte.

Wenn Informationen fehlen:
- nicht Ready
- stattdessen `Backlog` oder `Blocked`

## Gate-Regeln

Du darfst Review-Zusammenfassungen erzeugen.

Beispiel:

Review summary for FACT-001
- Checks: lint/test/build passed
- Files changed: 6
- Diff: UI dropdown, status API, model migration
- Risk: migration requires human review
- Suggested next: human approves or rejects

Du darfst nicht:
- Done setzen
- Merge auslösen
- Push auslösen
- ohne namentlichen menschlichen Approver `Approved` setzen

## Sicherheit

- Kein Secrets ausgeben.
- Kein App-Passwort ausgeben.
- Keine Production-Befehle ausführen.
- Keine Shell-Kommandos auf Servern ausführen, außer klar whitelisted Factory-Adapter-Kommandos.
- Keine Ticketbeschreibung als Code ausführen.
- Keine Tests abschwächen, um ein Ticket „grün“ zu machen.

## Ausgabeformat für fertige Spec

Wenn die Spec vollständig ist, schreibe genau dieses Markdown-Format:

## Goal
...

## Success criteria
- ...

## Acceptance examples
1. Normalfall:
   ...
2. Grenzfall:
   ...
3. Fehlerfall:
   ...

## Forbidden
- ...

## Checks
- ...

## Budget
max_walltime: 30m
max_turns: 15
max_files: 10
```

### 16.5 Hermes Gate-Controller-Prompt

```markdown
# Hermes/KIara Gate Controller Prompt

Du bist der Gate-Controller der Factory.

## Aufgabe

Du liest Job-Reports, Check-Ergebnisse und Diffs und erzeugst eine Review-Zusammenfassung für den Menschen.

## Erlaubt

- Status lesen
- Checks zusammenfassen
- Diff-Erfassung zusammenfassen
- Risiken benennen
- Approve/Reject-Vorschlag machen
- Menschliche Freigabe anfordern
- Nach expliziter menschlicher Freigabe mit Name:
  Approved-Status schreiben

## Nicht erlaubt

- Selbst freigeben ohne menschlichen namentlichen Approver
- Done setzen
- Merge auslösen
- Push auslösen
- Checks ignorieren
- Ticket schließen, wenn Checks rot sind
- Akzeptanzkriterien nachträglich abschwächen

## Freigabebefehl

Menschlicher Approve muss explizit sein:

/approve FACT-001 approver=<name>

Erst dann darfst du:

Waiting Review -> Approved

und ins Audit schreiben:

{
  "event": "gate_approved",
  "ticket": "FACT-001",
  "approver": "<name>",
  "actor": "hermes"
}

## Gate-Regel

Wenn Checks fehlen oder rot sind:
- kein Approve
- Rückmeldung: REQUEST_CHANGES

Wenn Diff zu groß ist:
- kein Approve
- Rückmeldung: TOO_LARGE

Wenn Tests nicht abgedeckt sind:
- kein Approve
- Rückmeldung: MISSING_SCENARIOS
```

---

## 17. Factory-Karten für Nextcloud Deck

Diese Karten können direkt im Deck angelegt werden.

---

## FACT-000 — Factory Bootstrap

**Liste:** Ready  
**Labels:** Factory, infra, bootstrap

```markdown
## Goal

Create the minimum runnable factory scaffold on kiara so the Nextcloud Deck board „Software Factory“ can become the human control surface and a local Runner can later execute OpenCode jobs safely.

## Scope

Implement or scaffold:

1. `/srv/factory/config/factory.yaml` with board_id 7 and named stacks.
2. `/srv/factory/scripts/deck.py`
   - list stacks
   - list cards in a stack
   - move card to stack
   - update card description
3. `/srv/factory/scripts/factoryd.py`
   - `--once`
   - `--once --dry-run`
   - `--loop --interval 30`
4. `/srv/factory/scripts/validate_ticket.py`
5. `/srv/factory/scripts/run_job.py`
   - create worktree
   - write job report
   - optional OpenCode wrapper call
6. `/srv/factory/prompts/orchestrator.md`
7. `/srv/factory/prompts/implementer.md`
8. `/srv/factory/prompts/reviewer.md`
9. `/srv/factory/prompts/hermes_intake.md`
10. sample ticket:
    `/srv/factory/tickets/sample/FACT-EXAMPLE.md`

## Success criteria

- `factoryd.py --once --dry-run` runs without errors
- `deck.py` can list stacks for configured board if credentials are available
- `validate_ticket.py` accepts sample ticket and rejects malformed one
- dry-run job writes report file
- audit.jsonl receives at least one event
- no model call happens in dry-run mode
- no merge, push, deploy, Done transition happens

## Acceptance examples

1. Normal case:
   `python3 scripts/factoryd.py --once --dry-run`
   finds a valid Ready ticket, prints planned actions, writes simulated audit event.

2. Boundary case:
   No Ready ticket exists -> clean exit code 0.

3. Failure case:
   Ticket lacks acceptance examples -> runner rejects it, writes audit event.

## Forbidden

- No real model invocation.
- No OpenCode execution.
- No Git push.
- No merge.
- No automatic Done.
- No secrets in code/config/repo/audit.
- No Hermes direct merge/Done capability in this ticket.

## Checks

- python3 -m py_compile scripts/deck.py
- python3 -m py_compile scripts/factoryd.py
- python3 -m py_compile scripts/run_job.py
- python3 -m py_compile scripts/validate_ticket.py
- python3 scripts/validate_ticket.py tickets/sample/FACT-EXAMPLE.md
- python3 scripts/factoryd.py --once --dry-run

## Budget

max_walltime: 45m
max_turns: 18
max_files: 16
```

---

## FACT-001 — Ticket-Schema und Validator härten

**Liste:** Backlog  
**Labels:** Factory, infra, feature

```markdown
## Goal

Harden the ticket schema and validator so the factory only accepts executable, reviewable tickets.

## Success criteria

- Parser supports required fields:
  Goal, Success criteria, Acceptance examples, Forbidden, Checks, Budget.
- Invalid tickets are rejected with clear section names.
- Sample ticket passes.
- Missing required fields are rejected.
- Optional fields may be empty.

## Acceptance examples

1. Normal case:
   A fully-formed ticket is accepted.

2. Boundary case:
   Missing approver is allowed before gate.

3. Failure case:
   Missing acceptance examples is rejected.

## Forbidden

- No runner execution.
- No model calls.
- No merge.
- No push.

## Checks

- python3 scripts/validate_ticket.py tickets/sample/FACT-EXAMPLE.md
- python3 scripts/validate_ticket.py tickets/sample/INVALID_MISSING_ACCEPTANCE.md

## Budget

max_walltime: 25m
max_turns: 10
max_files: 6
```

---

## FACT-002 — Runner: Ticket-Auswahl und Queue-Depth

**Liste:** Backlog  
**Labels:** Factory, infra, feature

```markdown
## Goal

Implement ticket selection and queue-depth control in the Runner.

## Success criteria

- Runner selects at most `queue_depth` tickets.
- Default queue depth is 1 or 2 on kiara.
- Runner marks selected ticket as Running.
- Runner supports dry-run.
- Runner supports single-run and loop mode.

## Acceptance examples

1. Normal case:
   With 3 ready tickets and queue_depth 1, runner selects exactly 1.

2. Boundary case:
   With 0 ready tickets, runner exits cleanly.

3. Failure case:
   Invalid ticket is skipped and logged.

## Forbidden

- No model call in dry-run.
- No real OpenCode call in dry-run.
- No merge.
- No push.
- No Done.

## Checks

- python3 scripts/factoryd.py --once --dry-run
- python3 scripts/factoryd.py --loop --interval 1 --once

## Budget

max_walltime: 25m
max_turns: 12
max_files: 8
```

---

## FACT-003 — Git-Worktree-Lifecycle

**Liste:** Backlog  
**Labels:** Factory, infra, feature

```markdown
## Goal

Implement safe Git worktree lifecycle for factory jobs.

## Success criteria

- Each ticket gets a deterministic worktree name, e.g. FACT-001.
- Worktree is based on configured base branch.
- Runner does not touch main working tree.
- Cleanup after success/failure is supported.
- No push, merge, or deploy is introduced.

## Acceptance examples

1. Normal case:
   Starting FACT-003 creates a worktree without changing main checkout.

2. Boundary case:
   Existing worktree is reused or fails predictably without destroying work.

3. Failure case:
   Invalid repo path fails clearly without partial broken worktree.

## Forbidden

- No merge.
- No push.
- No production access.
- No automatic commit/publish flow yet.

## Checks

- python3 scripts/run_job.py worktree-test --ticket tickets/sample/FACT-EXAMPLE.md
- git worktree list

## Budget

max_walltime: 30m
max_turns: 14
max_files: 10
```

---

## FACT-004 — Check-Pipeline-Wrapper

**Liste:** Backlog  
**Labels:** Factory, infra, feature

```markdown
## Goal

Implement configurable project check commands for the factory.

## Success criteria

- Project config contains checks per repo.
- Runner can execute checks from project config.
- Check output is captured.
- Check failures produce structured result.
- Check execution happens outside implementing agent logic.

## Acceptance examples

1. Normal case:
   Checks for configured project execute all commands in order.

2. Boundary case:
   Project with no checks reports explicit “no checks configured”.

3. Failure case:
   Failed check produces failure summary without crashing runner.

## Forbidden

- No self-verification by implementer.
- No merging.
- No deployment.
- No secrets in config.

## Checks

- python3 scripts/factoryd.py check --repo factory --dry-run
- python3 scripts/factoryd.py check --repo factory

## Budget

max_walltime: 25m
max_turns: 10
max_files: 6
```

---

## FACT-005 — Job-Report

**Liste:** Backlog  
**Labels:** Factory, infra, feature

```markdown
## Goal

Generate a human-reviewable and machine-readable job report for every factory run.

## Success criteria

- Report contains:
  ticket id, repo, worktree, branch, walltime, status, checks, diff summary, result.
- Report written to reports directory.
- Dry-run produces simulated report.
- Failed jobs still produce report.

## Acceptance examples

1. Normal case:
   Successful simulated job writes report with status waiting-review.

2. Boundary case:
   Zero changed files still writes report.

3. Failure case:
   Failed check writes report with failure reason.

## Forbidden

- No gate logic.
- No automatic merge.
- No Done.

## Checks

- python3 scripts/run_job.py report-test --ticket tickets/sample/FACT-EXAMPLE.md
- find reports -type f

## Budget

max_walltime: 20m
max_turns: 10
max_files: 6
```

---

## FACT-006 — Audit-JSONL

**Liste:** Backlog  
**Labels:** Factory, infra, feature

```markdown
## Goal

Add append-only JSONL audit logging for every meaningful factory event.

## Success criteria

- audit.jsonl receives one line per event.
- Events include:
  timestamp, ticket, event, from, to, actor, role, message.
- State changes are auditable.
- Logs are append-only in application logic.

## Acceptance examples

1. Normal case:
   Ready -> Running creates audit event.

2. Boundary case:
   Dry-run writes simulated audit events.

3. Failure case:
   Validation failure writes audit event with error metadata.

## Forbidden

- No secrets in logs.
- No large diffs in logs.
- No mutable audit log.

## Checks

- python3 scripts/factoryd.py audit-test --ticket tickets/sample/FACT-EXAMPLE.md
- tail -n 1 audit/audit.jsonl

## Budget

max_walltime: 20m
max_turns: 10
max_files: 5
```

---

## FACT-100 — Hermes/KIara Discord Adapter

**Liste:** Backlog  
**Labels:** Factory, hermes, infra, feature

```markdown
## Goal

Build an adapter that lets Hermes/KIara (Discord) create, clarify, validate, and hand off tickets into the Nextcloud Deck board „Software Factory“, while keeping final gate authority with a named human.

## Scope

1. Hermes command handlers:
   - `/ticket`
   - `/clarify`
   - `/ready`
   - `/status`
   - `/approve`
   - `/reject`
   - `/report`

2. Hermes intake rules:
   - Hermes asks until spec contains:
     - Goal
     - Success criteria
     - Acceptance examples
     - Forbidden
     - Checks
     - Budget
   - Hermes refuses to move ticket to Ready without these fields.

3. Nextcloud Deck actions:
   - Hermes may create cards in Backlog
   - Hermes may update description
   - Hermes may move Backlog -> Ready only if valid
   - Hermes may move Backlog/Ready -> Blocked
   - Hermes may comment review summary
   - Hermes must not directly move Waiting Review -> Done
   - Hermes may move Waiting Review -> Approved only after explicit human approval command with named approver

4. Review summary mode:
   - Given ticket id, Hermes reads latest job report/checks from factory reports/audit
   - Hermes produces gate checklist for human reviewer

## Success criteria

- A Discord command can create a valid ticket and move it to Ready.
- Invalid tickets remain in Backlog or Blocked.
- A human approval command produces an audit event with approver name.
- Hermes never marks Done without prior Approved and merge/deploy evidence.
- Hermes has no repo push/merge secret.

## Acceptance examples

1. Normal case:
   User asks Hermes in Discord to create a small-feature ticket. Hermes clarifies fields, writes Markdown spec, creates card in Backlog, then moves it to Ready when complete.

2. Boundary case:
   User asks to move Waiting Review to Done directly. Hermes refuses and explains gate rule.

3. Failure case:
   Hermes tries to move Waiting Review to Approved without human approver name. Adapter rejects and logs violation.

## Forbidden

- No secrets in Hermes config.
- No direct merge.
- No direct push.
- No Done without Approved.
- No auto-approve.
- No direct OpenCode shell execution by Hermes.
- No model switching decisions inside task runtime.

## Checks

- python3 scripts/hermes_adapter.py --once --dry-run
- python3 scripts/hermes_adapter.py test-intake
- python3 scripts/hermes_adapter.py test-gate-reject
- audit.jsonl contains approval violation events when tested

## Budget

max_walltime: 60m
max_turns: 24
max_files: 18
```

---

## FACT-200 — Cotrack Pilot: Status-Änderung im Ticket-Detail

**Liste:** Backlog  
**Labels:** Cotrack, feature, pilot

```markdown
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

## Checks

- npm run lint
- npm run build
- npm run test

## Budget

max_walltime: 35m
max_turns: 15
max_files: 10
```

---

## FACT-201 — Cotrack Pilot: Factory-Statusfelder im Modell und UI

**Liste:** Backlog  
**Labels:** Cotrack, feature, pilot

```markdown
## Goal

Expose factory-related ticket state and metadata clearly in cotrack UI so humans can use it for gate review and queue control.

## Success criteria

- Ticket detail shows current factory status.
- Ticket detail shows last run status or last check result if available.
- UI labels are consistent with Deck/factory naming.
- No breaking changes to existing ticket flows.

## Acceptance examples

1. Normal case:
   A ticket shows `status: waiting-review` and the most recent run outcome.

2. Boundary case:
   If no run data exists, the UI still renders cleanly with a neutral default.

3. Failure case:
   If run data is malformed, the UI falls back to a safe representation instead of crashing.

## Forbidden

- No automatic transitions based on hidden logic.
- No direct DB hacks.
- No auto-close tickets.
- No production data exposure.

## Checks

- npm run lint
- npm run build
- npm run test

## Budget

max_walltime: 40m
max_turns: 16
max_files: 12
```

---

## 18. Empfohlene Hermes/Discord-Kommandos

MVP-Kommandos für Hermes:

```text
/ticket <kurzer Titel>
/spec
/clarify
/ready FACT-001
/reject FACT-001
/status
/watch FACT-001
/report FACT-001
/approve FACT-001 approver=<name>
/reject-review FACT-001 reason=<text>
```

Beispiel:

```text
User:
/ticket Cotrack: Status dropdown im Ticket-Detail

Hermes:
Klärt:
- Repo
- Ziel
- Normalfall
- Grenzfall
- Fehlerfall
- Nicht tun
- Checks
- Budget

Wenn vollständig:
- schreibt Markdown-Spec in Karte
- schiebt Karte nach Ready
```

Wichtig:

```text
Hermes darf Ready nur setzen, wenn Spec vollständig ist.
```

---

## 19. Hermes-Freigabe sauber machen

Freigabe braucht namentlichen Approver:

```text
/approve FACT-001 approver=Andreas
```

Erst danach darf Hermes:

```text
Waiting Review -> Approved
```

Audit-Event:

```json
{
  "timestamp": "2026-11-13T15:00:00Z",
  "ticket": "FACT-001",
  "event": "gate_approved",
  "from": "Waiting Review",
  "to": "Approved",
  "actor": "factory-hermes",
  "role": "hermes",
  "human_approver": "Andreas",
  "approval_channel": "discord"
}
```

Wenn kein Approver-Name vorhanden ist:

```text
Hermes:
Ich kann FACT-001 nicht freigeben.
Bitte namentliche Freigabe:
/approve FACT-001 approver=<dein Name>
```

---

## 20. Factory-Runner Ablauf

Empfohlener Runner-Zyklus:

```text
1. Karten aus Deck-Stack Ready lesen
2. Ticket validieren
3. Projekt/Repo ermitteln
4. Ticket nach Running verschieben
5. Git-Worktree anlegen
6. OpenCode Worker starten
7. Check-Pipeline ausführen
8. Job-Report schreiben
9. Diff-Statistik berechnen
10. Ticket nach Waiting Review verschieben
11. Hermes informieren
12. Audit schreiben
```

Runner darf am Anfang nicht:

```text
Approved setzen
Done setzen
Merge ausführen
Push ausführen
Deploy ausführen
```

---

## 21. OpenCode-Ablauf

Empfohlener OpenCode-Zyklus:

```text
1. Ticket lesen
2. Spec prüfen
3. Worktree öffnen
4. Code analysieren
5. Implementierung umsetzen
6. Dateien ändern
7. Report abgeben
8. Kein Done
9. Kein Merge
10. Kein Push
```

OpenCode bekommt:

```text
- Ticket
- Repo-Pfad
- Worktree-Pfad
- Budget
- Prompt-Policy
```

OpenCode bekommt nicht:

```text
- Nextcloud-Passwort
- OAuth-Token
- Produktionszugriff
- Merge-Recht
- Secrets
```

---

## 22. Verifikation

Wichtigster Grundsatz:

> Die Verifikation kommt nicht vom implementierenden Agenten.

Verifikationsebenen:

1. **Automatische Checks**
   - Build
   - Lint
   - Tests
   - Playwright/Szenarien
   - SAST optional

2. **Cross-Check**
   - kiara implementiert
   - flaps/Qwen prüft optional

3. **Menschliches Gate**
   - namentlicher Approver
   - Diff prüfen
   - Checks ansehen
   - Szenarien prüfen

4. **Audit**
   - Walltime
   - Queue-Zeit
   - Statuswechsel
   - Approver
   - Check-Ergebnisse

---

## 23. Gate-Escape vermeiden

Gate-Escape wäre:

```text
Ticket wurde abgeschlossen, ohne dass ein Mensch geprüft und freigegeben hat.
```

Schutzregeln:

```text
- Waiting Review -> Done ist verboten.
- Approved -> Done nur nach Merge/Deploy-Evidenz.
- Approved nur mit human_approver.
- Runner schreibt niemals Done ohne Approved.
- Hermes schreibt niemals Approved ohne expliziten menschlichen Approver.
- Audit-Log erzwingt Approver-Feld für Approved-Events.
```

Abnahmekriterium Factory-Pilot:

```text
null Gate-Escape
```

---

## 24. Sicherheit

Niemals speichern:

```text
- Nextcloud-Passwort
- App-Passwort
- OAuth Client Secret
- OAuth Access Token
- Refresh Token
- OpenRouter API Key
- GitHub Token
- SSH Keys
- Secrets
- .env Inhalte
```

Speicherorte:

```text
/etc/factory/runner.env
/etc/factory/hermes.env
/etc/factory/observer.env
```

Rechte:

```bash
chmod 600 /etc/factory/*.env
```

Keine Nutzung in:

```text
- Git
- Deck-Karten
- Kartenkommentaren
- Audit-Log
- Discord
- OpenCode-Projekt
- Reports
- Logs
```

---

## 25. OAuth-Strategie

Wenn OAuth verwendet wird:

### Mindestempfehlung

```text
Factory Runner
Factory Hermes
```

### Sauber

```text
Factory Runner
Factory Hermes
Factory Observer
```

### Optional

```text
Factory Panel
Factory CLI
```

Wichtig:

```text
OAuth-Client + Nextcloud-User + Token getrennt halten.
```

Empfohlene Paare:

```text
Factory Runner   -> factory-runner
Factory Hermes   -> factory-hermes
Factory Observer -> factory-observer
```

---

## 26. Modell-Routing

Empfohlene Priorität:

```text
1. kiara / bonsai2-27b       Default-Implementierung
2. flaps / Qwen              Review/Verifikation, wenn erreichbar
3. OpenRouter Free           nur leichte Aufgaben
4. OpenRouter Paid           nur mit Budget-Check
```

Regeln:

- Health-Check vor Job.
- Kein Modellwechsel mitten in Task.
- Checkpoint-basierter Zustand.
- flaps unavailable:
  - Task zerlegen
  - im nächsten flaps-Fenster queuen
  - mit fertiger Spec an Mensch eskalieren
- OpenRouter Paid nur mit expliziter Freigabe.
- OpenRouter `model` und Kosten aus API-Antwort ins Audit schreiben.

---

## 27. Metriken

Wichtige KPIs:

```text
Walltime je Task
Queue-Wartezeit
Gate-Pass-Rate
Human-Override-Rate
Change-Failure-Rate
Deploy-Frequency
Lead-Time
MTTR
```

Wichtig:

- Walltime und Queue-Zeit sind lokal die Haupt-KPIs.
- Energie-KPI fällt weg, solange kein Solar-/Strombudget relevant ist.
- Human-Override-Rate ist wichtigstes Qualitätssignal.

---

## 28. Roadmap

### Phase A — MVP auf kiara

Ziel:

```text
Eine Fabrik, die eine Task-Klasse sauber durchführt und null Gate-Escape zeigt.
```

MVP:

```text
- Nextcloud Deck als Queue
- Factory Runner auf kiara
- OpenCode implementiert
- Checks ausführen
- Waiting Review erzwingen
- Audit schreiben
```

Nicht bauen:

```text
- Cloud-Sandbox-Infra
- Auto-Merge
- Multi-Agenten-Overhead
- Web-Panel
- zu viele Modelle
- automatische Produktivdeployments
```

### Phase B — Hermes integrieren

Ziel:

```text
Hermes kann Aufgaben aufnehmen, Specs klären, Ready machen, Status lesen und Freigaben protokollieren.
```

### Phase C — Cotrack-Pilot

Ziel:

```text
Erste echte Fabrik-Tickets an Cotrack abarbeiten, aber menschliches Gate bleibt hart.
```

### Phase D — flaps als Judge

Ziel:

```text
flaps übernimmt Review/Verifikation, wenn erreichbar.
```

### Phase E — Auto-Merge für banale Klassen

Nur nach langer stabiler Laufzeit:

```text
- 10–20 saubere Tickets
- null Gate-Escape
- hohe Gate-Pass-Rate
- niedrige Override-Rate
- saubere CI
```

Erst dann:

```yaml
auto_merge_classes:
  - dependency-bump
```

---

## 29. Nächste konkrete Schritte

### Schritt 1: Factory-Infra auf kiara anlegen

```bash
sudo useradd -m -s /bin/bash factory
sudo mkdir -p /srv/factory/{config,prompts,scripts,repos,worktrees,reports,logs,audit}
sudo mkdir -p /etc/factory
sudo chown -R factory:factory /srv/factory
```

### Schritt 2: Repos anlegen

```bash
cd /srv/factory/repos
git clone https://github.com/IlianP/cotrack cotrack
mkdir factory
cd factory
git init
```

### Schritt 3: Nextcloud Service-Accounts und OAuth-Apps anlegen

Empfohlen:

```text
factory-runner
factory-hermes
factory-observer optional
```

OAuth-Apps:

```text
Factory Runner
Factory Hermes
Factory Observer optional
```

### Schritt 4: Env-Dateien anlegen

```bash
sudo install -o factory -g factory -m 0600 /dev/null /etc/factory/runner.env
sudo install -o factory -g factory -m 0600 /dev/null /etc/factory/hermes.env
sudo install -o factory -g factory -m 0600 /dev/null /etc/factory/observer.env
```

### Schritt 5: FACT-000 in Nextcloud Deck anlegen

Board:

```text
Software Factory
```

Liste:

```text
Ready
```

Titel:

```text
FACT-000 - Factory Bootstrap: Runner, Deck-Adapter und Hermes-Adapter-Design anlegen
```

Labels:

```text
Factory
infra
bootstrap
```

### Schritt 6: FACT-000 agentisch ausführen

Mit OpenCode oder Runner:

```bash
python3 scripts/factoryd.py --once --dry-run
python3 scripts/factoryd.py --once
```

### Schritt 7: FACT-100 Hermes Adapter vorbereiten

Nach FACT-000:

```text
FACT-100 in Ready legen
Hermes-Adapter mit getrenntem factory-hermes Zugang implementieren
```

### Schritt 8: FACT-001 bis FACT-006 abarbeiten

Reihenfolge:

```text
FACT-001 Validator härten
FACT-002 Queue-Depth
FACT-003 Worktree-Lifecycle
FACT-004 Check-Pipeline
FACT-005 Job-Report
FACT-006 Audit-JSONL
```

### Schritt 9: Pilotbetrieb mit 10–20 Tickets

Abnahmekriterium:

```text
null Gate-Escape
```

---

## 30. Direkte Empfehlungen

### Do

- Deck als Kontrollfläche nutzen.
- Runner als eigentlichen Factory-State-Owner nutzen.
- OpenCode als Worker nutzen.
- Hermes als Aufnahme- und Kontrollkanal nutzen.
- getrennte Nextcloud-Accounts verwenden.
- Policies im Code erzwingen.
- namentliche Freigaben erzwingen.
- Audit-Log von Anfang an nutzen.
- Walltime und Queue-Zeit als KPI nutzen.
- kleine Features als erste Task-Klasse nutzen.

### Don’t

- OpenCode nicht direkt in Nextcloud schreiben lassen.
- Hermes nicht Done setzen lassen.
- Runner nicht Approved setzen lassen.
- Auto-Merge nicht zu früh aktivieren.
- keine gemeinsamen Tokens für alle Rollen verwenden.
- keine Tickets ohne Akzeptanzbeispiele in Ready schieben.
- keine Tests nur durch Implementierungsagenten prüfen lassen.
- keine Secrets in Repos, Logs, Deck oder Discord ablegen.

---

## 31. Kurzarchitektur als Merksatz

```text
Nextcloud Deck ist die Straße.
Hermes ist der Empfang und Dispatcher.
Runner ist die Fabriksteuerung.
OpenCode ist die Werkstatt.
Checks sind die Qualitätskontrolle.
Der Mensch ist die Freigabe.
Das Audit ist die Kamera.
```
````