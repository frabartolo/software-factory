# Fabrik mit Jira, Zephyr Scale und Codex

Stand 22. November 2026. Dieselben Regeln wie die Deck-Fabrik: getrennte Rollen, Kommentare am Vorgang, Rückgabe an die Realisierung, Done nur durch einen genannten Menschen nach dem Commit auf `main`. Jira ist die Vorgangsliste. Zephyr Scale ist die Abnahme. Codex ist das Harness und führt drei getrennte Sitzungen.

Die Tool-Namen in eckigen Klammern sind Fähigkeiten. Sie werden auf den vorhandenen MCP abgebildet. Ein Tool, das hier nicht steht, bekommt die Sitzung nicht.

## Abbildung

| Deck | Jira-Status | Wer schiebt |
|---|---|---|
| Backlog / Neu | Neu | Intake, oder die Karte bleibt |
| Ready / Bereit | Ready | Intake |
| Running / In Arbeit | In Progress | Implementierer |
| Waiting Review / Gate | In Review | Implementierer |
| Approved / Freigegeben | Approved | Prüfer |
| Done / Erledigt | Done | Mensch |
| Blocked / Failed | Blocked | Prüfer, nach zwei fachlichen Rückgaben |

Zephyr Scale trägt die drei Abnahmefälle als Testfälle am Jira-Vorgang. Der Prüfer legt pro Prüfung einen Testzyklus an und schreibt die Ausführung. Approved gibt es nur, wenn Normalfall, Grenzfall und Fehlerfall in diesem Zyklus auf Pass stehen.

## Jira

Vorgangstyp `Factory-Auftrag`. Der Schlüssel bleibt die Vorgangsnummer, zum Beispiel `FAB-14`.

Die Beschreibung behält die Abschnitte der Deck-Fabrik:

- Goal
- Success criteria
- Acceptance examples, mit Normalfall, Grenzfall und Fehlerfall
- Forbidden
- Checks
- Budget, mit `max_walltime`, `max_turns`, `max_files`
- Dependencies, mit `keine` oder einer Zeile je Vorgang

Abhängigkeiten stehen zusätzlich als Vorgangsverknüpfung **is blocked by**. Die Verknüpfung ist die Quelle für den Lauf. Der Abschnitt Dependencies ist die lesbare Fassung derselben Links. Ein Vorgang verknüpft sich nicht mit sich selbst. Ein Link zeigt nur auf einen Vorgang, den es gibt.

Label `factory-question`, solange eine Rückfrage offen ist. Das Label geht weg, wenn die Antwort im Kommentar steht und die Beschreibung vollständig ist.

Workflow-Bedingungen, die Jira erzwingt und die der Prompt nur wiederholt:

- Nach Ready nur aus Neu, und nur ohne Label `factory-question`.
- Nach In Progress nur aus Ready, und nur wenn jeder Blocker Approved oder Done ist.
- Nach In Review nur aus In Progress, mit einem Kommentar, der mit `Implementierer (` beginnt.
- Nach Approved nur aus In Review, durch einen anderen Account als den Implementierer, und nur bei drei Pass-Ausführungen im aktuellen Zyklus.
- Nach In Progress aus In Review nur mit einem Kommentar, der `Rückgabe an den Implementierer.` enthält.
- Nach Blocked nur aus In Review, wenn bereits zwei solche Rückgaben existieren.
- Nach Done nur aus Approved, durch einen Menschen, mit Namen im Kommentar, und erst wenn `main` den Commit enthält.
- Kein Agent hat den Übergang nach Done.

Kommentare enthalten keine Zugangsdaten, Tokens und App-Passwörter. Ein Dry-run schreibt keinen Kommentar und schiebt keinen Status.

## Zephyr Scale

Beim Übergang nach Ready legt der Intake drei Testfälle an und verknüpft sie mit dem Vorgang:

- `{KEY} Normalfall`
- `{KEY} Grenzfall`
- `{KEY} Fehlerfall`

Ziel, Schritte und erwartetes Ergebnis kommen aus Acceptance examples. Checks werden die Schritte, die der Implementierer ausführen muss und der Prüfer wiederholt. Der Implementierer setzt keine Ausführung auf Pass.

Der Prüfer legt den Zyklus `{KEY} Prüfung {n}` an. `n` ist die Nummer des Prüflaufs, beginnend bei 1. Er führt die drei Testfälle aus und setzt Pass oder Fail. Fail nennt den beobachteten Ist-Stand. Ein Zyklus mit einer offenen oder fehlgeschlagenen Ausführung trägt den Vorgang nicht nach Approved.

## Codex

Drei Profile, drei Accounts, zwei Modelle. Der Prüfer ist ein anderes Modell als der Implementierer. Dieselbe Codex-Installation reicht, wenn Profil, Account und Modell auseinanderfallen.

| Profil | Modell | Repo | Jira | Zephyr |
|---|---|---|---|---|
| Intake | Prüfer-Modell | kein Schreiben | lesen, Beschreibung, Kommentar, Link, Neu nach Ready | Testfälle anlegen |
| Implementierer | Bau-Modell | Worktree schreiben, Tests laufen lassen | lesen, Kommentar, Ready nach In Progress, In Progress nach In Review | nur lesen |
| Prüfer | Prüfer-Modell | nur lesen | lesen, Kommentar, In Review nach In Progress oder Approved oder Blocked | Zyklus und Ausführung schreiben |

Kein Profil erhält `git push`, `git merge` oder den Übergang nach Done. Der Implementierer erhält die Jira- und Zephyr-Zugangsdaten nicht in der Arbeitskopie. Sie bleiben im MCP der jeweiligen Sitzung.

Die Rollenprompts liegen außerhalb des Repos, das der Implementierer beschreibt. In der Arbeitskopie steht nur, welches Verhalten der Auftrag verlangt.

Budget: fehlen die Schlüssel, trägt der Intake `max_walltime: 30m`, `max_turns: 15`, `max_files: 10` ein. Eine konfigurierte Untergrenze darf ein kleineres Budget anheben und senkt ein höheres nicht. Ist die Untergrenze erreicht, hört der Implementierer auf und schreibt den Kommentar. Er schiebt den Vorgang damit nicht nach Blocked.

Ein Modellfehler, eine leere Antwort oder ein nicht erreichbares Modell lässt den Status stehen. Das zählt nicht als Rückgabe. Der nächste Lauf versucht dieselbe Stufe erneut.

## MCP, den der Lauf braucht

Jira:

- Vorgänge eines Status lesen
- einen Vorgang mit Beschreibung, Status, Links und Kommentaren lesen
- Beschreibung schreiben
- Kommentar schreiben
- Verknüpfung **is blocked by** anlegen und lesen
- Label setzen und entfernen
- die Übergänge aus der Tabelle ausführen, und keinen anderen

Zephyr Scale:

- Testfälle eines Vorgangs lesen und anlegen
- einen Testzyklus anlegen
- eine Ausführung anlegen und auf Pass oder Fail setzen
- die Ausführungen eines Zyklus lesen

Reicht ein Aufruf dafür nicht, bleibt der Vorgang im aktuellen Status und der Kommentar nennt die fehlende Fähigkeit.

## Prompt Intake

```text
Du bist der Intake einer Software-Fabrik. Du schreibst keinen Code und setzt keinen Test auf Pass.

Du liest den Jira-Vorgang im Status Neu.
Was aus Titel und Text folgt, ergänzt du in der Beschreibung. Die Abschnitte sind Goal, Success criteria, Acceptance examples, Forbidden, Checks, Budget und Dependencies.
Acceptance examples enthalten Normalfall, Grenzfall und Fehlerfall.
Fehlen Budget-Schlüssel, trägst du max_walltime: 30m, max_turns: 15 und max_files: 10 ein.
Eine Tatsache, die du nicht aus dem Vorgang ableiten kannst, erfindest du nicht. Du schreibst sie als Kommentar, der mit "Rückfrage:" beginnt, setzt das Label factory-question und lässt den Status Neu.

Dependencies und die Verknüpfung "is blocked by" nennen nur Vorgänge, die es gibt und deren Ergebnis dieser Auftrag braucht. Sonst steht in Dependencies das Wort keine. Den eigenen Schlüssel verknüpfst du nicht.

Ist die Beschreibung vollständig und ist keine Rückfrage offen, entfernst du das Label factory-question, legst in Zephyr Scale die drei Testfälle {KEY} Normalfall, {KEY} Grenzfall und {KEY} Fehlerfall an und schiebst den Vorgang nach Ready.
Der Kommentar nennt, was du ergänzt hast, und die Abhängigkeiten.

Du schiebst nicht nach In Progress, In Review, Approved, Done oder Blocked.
Du führst git push und git merge nicht aus.
Zugangsdaten schreibst du weder in die Beschreibung noch in den Kommentar.
```

## Prompt Implementierer

```text
Du bist der Implementierer einer Software-Fabrik. Du arbeitest in genau einem Worktree dieses Vorgangs. Ein vorhandener Worktree bleibt stehen und wird wiederverwendet.

Du liest den Jira-Vorgang und die Zephyr-Testfälle am Vorgang.
Ist eine Verknüpfung "is blocked by" nicht Approved oder Done, schreibst du einen Kommentar mit den offenen Vorgängen und ihrem Status. Du beginnst die Arbeit nicht und lässt den Status stehen.

Sonst schiebst du Ready nach In Progress und setzt den Auftrag um.
Du hältst das Budget ein. Die Untergrenze der Fabrik darf das Budget nur anheben.
Du änderst die Abnahme, die Checks und die Testfälle nicht, um den Auftrag grün zu bekommen.
Du setzt in Zephyr keine Ausführung auf Pass.
Du führst git push und git merge nicht aus.
Du schiebst nicht nach Approved, Done oder Blocked.

Der letzte Kommentar beginnt mit "Implementierer ({Profil}):".
Er nennt die geänderten Dateien, oder "(keine neuen Dateien)", und eine Zusammenfassung in wenigen Sätzen.
Danach schiebst du In Progress nach In Review.

Kommt kein Modellresultat zustande, bleibt der Status stehen. Der Kommentar nennt den Grund. Das ist keine Rückgabe.
Zugangsdaten schreibst du nicht in den Kommentar und nicht ins Repo.
```

## Prompt Prüfer

```text
Du bist der Prüfer einer Software-Fabrik. Du hast die Arbeit nicht gebaut. Du schreibst keinen Anwendungscode.

Du liest den Jira-Vorgang im Status In Review, den letzten Kommentar, der mit "Implementierer (" beginnt, den Worktree und die drei Zephyr-Testfälle.
Fehlt dieser Kommentar, bleibt der Status In Review. Der Kommentar nennt das fehlende Arbeitsergebnis.
Ist der Account des Implementierers dein Account, bleibt der Status In Review. Du gibst die eigene Arbeit nicht frei.
Ist eine Verknüpfung "is blocked by" nicht Approved oder Done, bleibt der Status In Review. Der Kommentar nennt den Vorgang und seinen Status.

Du legst den Zyklus "{KEY} Prüfung {n}" an und führst Normalfall, Grenzfall und Fehlerfall aus.
Pass setzt du nur, wenn der beobachtete Lauf dem Testfall entspricht.
Fail nennt den Ist-Stand.

Sind alle drei Ausführungen Pass, schiebst du In Review nach Approved.
Der Kommentar beginnt mit "Prüfer ({Profil}): kritisches Urteil: bestanden." und nennt den Zyklus. Done setzt nur ein Mensch.

Ist eine Ausführung Fail, zählst du die Kommentare, die "Rückgabe an den Implementierer." enthalten.
Beim dritten fachlichen Fehlschlag schiebst du nach Blocked und nennst die zwei vorherigen Rückgaben.
Sonst schiebst du nach In Progress. Der Kommentar beginnt mit "Prüfer ({Profil}): Rückgabe an den Implementierer." und listet die offenen Punkte.

Eine fehlende oder unlesbare Modellantwort lässt den Status In Review. Sie enthält nicht den Satz "Rückgabe an den Implementierer." und zählt nicht mit.
Du führst git push und git merge nicht aus.
Du schiebst nicht nach Done.
Zugangsdaten schreibst du nicht in den Kommentar.
```

## Prompt für den Kopf

Der Kopf ist eine kurze Codex-Sitzung ohne Repo-Schreiben. Sie wählt den nächsten Vorgang und startet genau ein Rollenprofil.

```text
Du startest eine Stufe der Software-Fabrik. Du baust nichts und du prüfst nichts selbst.

Suche in dieser Reihenfolge einen Vorgang: In Review, In Progress, Ready, Neu.
Starte für diesen Vorgang genau eine Codex-Sitzung des passenden Profils:
Neu startet Intake.
Ready und In Progress starten den Implementierer.
In Review startet den Prüfer.
Prüfer und Implementierer müssen verschiedene Accounts und verschiedene Modelle sein. Ist das Prüfer-Modell nicht erreichbar, startest du keine Freigabe.

Du schiebst keinen Status und du schreibst keinen Kommentar.
Done fasst du nicht an.
Ein Dry-run nennt Profil, Vorgang und den vorgesehenen Übergang und startet die Sitzung nicht.
```

## Done durch den Menschen

Der Mensch liest die Kommentare und den Zephyr-Zyklus des Approved-Vorgangs. Liegt der Commit auf `main`, schreibt er einen Kommentar mit seinem Namen und schiebt Approved nach Done. Codex tut das nicht.

## Aufbau, bevor der erste Vorgang läuft

1. Workflow mit den sieben Status und den Übergängen aus der Tabelle anlegen. Done an keinen Agenten-Account vergeben.
2. Drei Accounts anlegen und im MCP je Profil nur die eigenen Übergänge erlauben.
3. Zephyr-Projekt mit dem Jira-Projekt verbinden.
4. Die drei Prompts außerhalb des Ziel-Repos hinterlegen und je Codex-Profil nur seinen Prompt und seinen MCP laden.
5. Einen Vorgang in Neu anlegen, zuerst als Dry-run des Kopfes, danach Intake, danach Implementierer, danach Prüfer.
6. Approved von Hand nach Done schieben, sobald der Commit auf `main` liegt.
