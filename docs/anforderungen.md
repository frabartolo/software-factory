# Anforderungen der Software-Factory

Stand 19. November 2026. Das Board ist „Software-Factory“, Id 7, auf Nextcloud. Die Spalten heißen Backlog / Neu, Ready / Bereit, Running / In Arbeit, Waiting Review / Gate, Approved / Freigegeben, Done / Erledigt und Blocked / Failed. **Das Deck ist die Single Source of Truth:** Alle Vorgänge (FACT-…-Tickets) werden dort **bearbeitet**, **ergänzt** und **durch den Prozess** auf den Stacks geschoben.

## Ablauf einer Karte

Eine Karte startet in Backlog / Neu und läuft durch getrennte Agenten bis Approved / Freigegeben.

1. Intake prüft den Auftrag und schiebt eine ausführbare Karte nach Ready / Bereit.
2. Der Implementierer nimmt sie aus Ready, setzt sie auf Running / In Arbeit und liefert das Arbeitsergebnis.
3. Danach liegt die Karte in Waiting Review / Gate.
4. Der Prüfer urteilt kritisch. Bei Bestand geht die Karte nach Approved / Freigegeben. Offene Punkte schreibt er als Kommentar und gibt die Karte zurück nach Running / In Arbeit.
5. Der Implementierer liest diese Punkte zusammen mit dem Auftrag, setzt sie um und schreibt ein neues Arbeitsergebnis. Danach prüft der Prüfer erneut.
6. Nach zwei Rückgaben ohne bestandenes Ergebnis geht die Karte nach Blocked / Failed.
7. Done / Erledigt setzt nur ein Mensch, mit Namen, und erst nachdem der Commit auf `main` liegt.

Der Implementierer gibt die eigene Arbeit nicht frei. Fehlt der unabhängige Prüfer, bleibt die Karte in Waiting Review / Gate und der Grund steht im Kommentar.

## Agenten

Die drei Agenten sind getrennte Rollen. Prüfer und Implementierer sind zwei Modelle.

| Rolle | Modell, wenn erreichbar | Darf |
|---|---|---|
| Intake | flaps, sonst hathi | Backlog / Neu nach Ready / Bereit oder in Neu lassen |
| Implementierer | kiara, sonst hathi | Ready / Bereit nach Running / In Arbeit und weiter nach Waiting Review / Gate |
| Prüfer | flaps, sonst hathi | Waiting Review / Gate nach Approved / Freigegeben, zurück nach Running / In Arbeit, oder nach zwei Rückgaben nach Blocked / Failed |
| Mensch | — | Approved / Freigegeben nach Done / Erledigt |

hathi (`swift-1.5-iq2_xs` auf `http://hathi:8080/v1`, Ersatzadresse `http://192.168.5.26:8080/v1`) ist der gelegentliche Ersatz. Es übernimmt eine Rolle nur, wenn das bevorzugte Modell in diesem Lauf nicht antwortet. Sind kiara und flaps beide erreichbar, bleibt hathi ungenutzt. Ein Modell gibt die eigene Arbeit nicht frei. Fehlen flaps und hathi, bleibt die Karte in Neu oder in Review.

Ein unvollständiger Auftrag bleibt in Backlog / Neu. Fehlt das Arbeitsergebnis oder fällt die Prüfung durch, geht die Karte mit den offenen Punkten zurück nach Running / In Arbeit. Der Implementierer arbeitet diese Punkte ab. Done entsteht daraus nicht.

## Wirkung der Modellprüfung

`scripts/model_health.py` stellt fest, ob kiara, flaps und hathi antworten. Die Pipeline besetzt den Lauf nach derselben Erreichbarkeit.

- flaps erreichbar: flaps wird Intake und Prüfer, kiara bleibt Implementierer.
- flaps nicht erreichbar und hathi erreichbar: hathi wird Intake und Prüfer, kiara bleibt Implementierer.
- kiara nicht erreichbar und hathi erreichbar: hathi wird Implementierer, flaps bleibt Prüfer.
- flaps und hathi nicht erreichbar: die Karte bleibt in Neu oder in Review, mit dem Grund aus der Prüfung. Es gibt kein stilles Weiterlaufen und kein Done.

`factory.py route-test` allein reicht dafür nicht. Der Lauf muss die Rollen aus der Prüfung setzen.

## Kommentare an der Karte

Jeder Agent schreibt sein Ergebnis als Kommentar an die Deck-Karte.

- Intake: ob der Auftrag ausführbar ist, und die Begründung.
- Implementierer: Ticket, Dateien, Zusammenfassung.
- Prüfer: Urteil, Begründung, Befunde, nächste Spalte.

Kommentare laufen über `GET` und `POST /ocs/v2.php/apps/deck/api/v1.0/cards/{id}/comments`. Die Route unter `/index.php/apps/deck/api/v1.0/cards/{id}/comments` antwortet mit HTTP 405 und wird nicht verwendet. Ein Kommentar hat höchstens 1000 Zeichen. Zugangsdaten, Tokens und App-Passwörter stehen nicht im Kommentar, nicht in der Beschreibung, nicht im Audit und nicht im Repository.

Ein Dry-run verschiebt keine Karte und schreibt keinen Kommentar.

## Datei-Queue

Es gibt eine Queue. Karten aus Ready / Bereit werden als Dateien unter `tickets/ready` abgelegt. Der Runner liest diese Station.

Ein Dry-run des Datei-Runners verschiebt die Datei nicht und gilt nicht als Fehlschlag. Grüne Checks enden in der Review-Station. Sie setzen weder `tickets/approved` noch `tickets/done`.

Check-Zeilen aus dem Ticket und Kommandos des Modells führen `git push` und `git merge` nicht aus. Ein solcher Befehl wird abgelehnt, die Karte geht nach Blocked / Failed, und es wird nichts gemergt.

## Worktree

Für ein Ticket gibt es höchstens einen Worktree unter `work/<Ticket-ID>`. Existiert er schon, wird er wiederverwendet oder der Lauf bricht ab. Das vorhandene Verzeichnis bleibt stehen. Ein falscher Repository-Pfad erzeugt keinen halben Worktree.

## Form eines Auftrags

Ein ausführbarer Auftrag enthält die Abschnitte Goal, Success criteria, Acceptance examples, Forbidden, Checks und Budget. Die Abnahme nennt Normalfall, Grenzfall und Fehlerfall. Das Budget nennt `max_walltime`, `max_turns` und `max_files`.

## Sicherheit und Grenzen

- Kein automatisches Merge.
- Kein Done ohne namentlichen Menschen und ohne Commit auf `main`.
- OpenCode erhält keine Nextcloud-Zugangsdaten und kein Recht auf `git push` oder `git merge`.
- Nextcloud ist über `NC_BASE=https://192.168.5.46` erreichbar. Das Zertifikat ist selbstsigniert, deshalb steht `NC_TLS_VERIFY=false` in der Env-Datei auf kiara und nicht im Repository.
- Die Pipeline startet nicht von selbst. Auf kiara lautet der Lauf `python3 scripts/agent_pipeline.py --once` für einen Schritt und `python3 scripts/agent_pipeline.py --once --follow --card <id>` für dieselbe Karte bis Approved, Blocked oder einen Stopp. `--dry-run` verändert das Board nicht.

## Noch nicht erfüllt

Diese Punkte sind festgelegt und im aktuellen Code noch offen.

- `scripts/deck_sync.py` schreibt Ready-Karten nach `tickets/new`. Der Runner liest `tickets/new`, `factory.py run-once` liest `tickets/ready`.
- `scripts/model_health.py` ändert die Agentenbesetzung nicht. `factory.py route-test` endet auch bei fehlendem flaps mit OK.
- `scripts/worktree.py` löscht einen bestehenden Pfad bei `create` mit `worktree remove --force`.
