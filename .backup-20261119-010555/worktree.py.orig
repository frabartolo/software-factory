"""FACT-003: Isolierte Git-Worktree für die Software Factory.

Jedes Ticket arbeitet in `work/<Ticket-ID>/` als isoliertes Worktree.
`factory_state.json` dokumentiert Ticket-ID, Start, Status, Model.
Nach Report wird der Worktree sauber entfernt.

API (auch als CLI):
    python worktree.py create <ticket_id> [--path P] [--status S] [--model M]
    python worktree.py remove <ticket_id> [--path P]
    python worktree.py status <ticket_id> [--path P]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional


def _git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    """git ausführen; returncode/STDOUT/STDERR zurückgeben (kein Crashing auf check=False)."""
    return subprocess.run(["git"] + args, cwd=str(cwd),
                          capture_output=True, text=True)


def _find_repo_root(path: Path) -> Path:
    """Läuft nach oben bis ein `.git` VERZEICHNIS gefunden wird (Haupt-Repo).
    Worktree-`.git`-Dateien (Pointer) werden bewusst übersprungen."""
    p = Path(path).resolve()
    while True:
        if (p / ".git").is_dir():
            return p
        p = p.parent
        if p == p.parent:
            raise RuntimeError(f"Keine Git-Repo gefunden oberhalb von {p}")


def _main_repo(path: Path) -> Path:
    """Haupt-Repo für einen (ggf. bestehenden) Worktree-Pfad auflösen.

    In einem Worktree ist `.git` eine DATEI (Zeiger auf
    <mainrepo>/.git/worktrees/<name>). Der eigentliche Repo-Root liegt dort.
    """
    p = Path(path).resolve()
    g = p / ".git"
    if g.is_file():
        try:
            ref = g.read_text().strip()
        except OSError:
            ref = ""
        # ref: "[gitdir: ]<mainrepo>/.git/worktrees/<name>"
        if ref.startswith("gitdir:"):
            ref = ref[len("gitdir:"):].strip()
        idx = ref.find("/.git")
        if idx >= 0:
            return Path(ref[:idx])
        return _find_repo_root(p)
    return _find_repo_root(p)


def _state_file(path: Path) -> Path:
    return path / "factory_state.json"


def _default_path(ticket_id: str, repo: Optional[Path] = None) -> Path:
    repo_root = Path(repo).resolve() if repo else Path(__file__).resolve().parents[1]
    return repo_root / "work" / ticket_id


def _resolve_repo_root(repo: Optional[Path]) -> Path:
    """Repo-Root normalisieren (str oder Path) und Haupt-Repo auflösen."""
    repo_root = Path(repo).resolve() if repo else Path(__file__).resolve().parents[1]
    return _find_repo_root(repo_root)


def create(ticket_id: str, path: Optional[Path] = None,
           repo: Optional[Path] = None, status: str = "running",
           model: str = "") -> dict:
    """Legt einen isolierten Git-Worktree unter `path` an.

    `path` default: `work/<ticket_id>/` relativ zum Repo-Root.
    `repo` default: Repo-Root oberhalb von worktree.py.
    Schreibt factory_state.json (ticket_id, start, status, model, path).
    """
    path = _resolve_path(ticket_id, path, repo)
    repo_root = _resolve_repo_root(repo)

    # Sauberer Zustand: stale/inaktive Worktree-Registry-Entries entfernen,
    # damit `worktree add` auf dem Ziel-Pfad succeeds.
    _git(["worktree", "prune"], cwd=repo_root, check=False)
    if path.exists():
        if path.is_dir():
            # Bestehendes (ggf. inaktiv/detached) Worktree: force-remove
            _git(["worktree", "remove", "--force", str(path)], cwd=repo_root, check=False)
            shutil.rmtree(str(path), ignore_errors=True)
        elif path.is_file():
            path.unlink()

    # `git worktree add` legt den Ziel-Pfad (inkl. Parent-Verzeichnisse) selbst an.
    r = _git(["worktree", "add", "--detach", str(path)], cwd=repo_root, check=False)
    if r.returncode != 0:
        # Sauber abbrechen: Registry auflösen + evtl. angelegtes Verzeichnis löschen
        _git(["worktree", "prune"], cwd=repo_root, check=False)
        shutil.rmtree(str(path), ignore_errors=True)
        raise RuntimeError(f"git worktree add fehlgeschlagen: {r.stderr.strip()}")

    state = {
        "ticket_id": ticket_id,
        "start": datetime.now().astimezone().isoformat(),
        "status": status,
        "model": model,
        "path": str(path),
    }
    _state_file(path).write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def status(ticket_id: str, path: Optional[Path] = None,
           repo: Optional[Path] = None) -> Optional[dict]:
    """Gibt factory_state.json zurück (oder None, wenn der Worktree fehlt)."""
    path = _resolve_path(ticket_id, path, repo)
    if not path.exists():
        return None
    sf = _state_file(path)
    if sf.exists():
        try:
            return json.loads(sf.read_text(encoding="utf-8"))
        except ValueError:
            return {"ticket_id": ticket_id, "path": str(path), "error": "invalid state"}
    return {"ticket_id": ticket_id, "path": str(path)}


def _resolve_path(ticket_id: str, path: Optional[Path],
                  repo: Optional[Path]) -> Path:
    return Path(path).expanduser().absolute() if path else _default_path(ticket_id, repo)


def remove(ticket_id: str, path: Optional[Path] = None,
           repo: Optional[Path] = None, force: bool = False) -> bool:
    """Entfernt den isolierten Worktree unter `path`.

    Nutzt das Haupt-Repo (Worktree-`.git`-Datei wird aufgesolgt),
    um die Gits Registry zu klären und das Verzeichnis zu löschen.
    """
    path = _resolve_path(ticket_id, path, repo)
    if not path.exists():
        return True  # nicht gefunden = nichts zu tun
    main = Path(repo).resolve() if repo else _main_repo(path)
    cmd = ["worktree", "remove"]
    if force:
        cmd.append("--force")
    cmd.append(str(path))
    r = _git(cmd, cwd=main, check=False)
    if r.returncode != 0:
        # git konnte das Worktree nicht (z. B. dirty): Verzeichnis zwangsweise
        # entfernen und die Registry-Entries auflösen.
        shutil.rmtree(str(path), ignore_errors=True)
        _git(["worktree", "prune"], cwd=main, check=False)
    return True


def is_worktree(ticket_id: str, path: Optional[Path] = None,
                repo: Optional[Path] = None) -> bool:
    """Ist `path` ein aktives Git-Worktree (oder zumindest existiert es)?"""
    p = _resolve_path(ticket_id, path, repo)
    if not p.exists():
        return False
    return (p / ".git").exists() or (p / ".gitworktree").exists()


def __main_main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="FACT-003: isolierte Git-Worktree")
    ap.add_argument("command", choices=["create", "remove", "status"])
    ap.add_argument("ticket_id")
    ap.add_argument("--path", help="Pfad (default: work/<ticket_id>/)")
    ap.add_argument("--status", default="running")
    ap.add_argument("--model", default="")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.command == "create":
            s = create(args.ticket_id, Path(args.path) if args.path else None,
                       status=args.status, model=args.model)
            print(json.dumps(s, indent=2))
            return 0
        if args.command == "remove":
            remove(args.ticket_id, Path(args.path) if args.path else None,
                   force=args.force)
            print("removed")
            return 0
        if args.command == "status":
            s = status(args.ticket_id, Path(args.path) if args.path else None)
            print(json.dumps(s, indent=2) if s else "nicht gefunden")
            return 0
    except Exception as e:
        print(f"FEHLER: {e}", file=__import__("sys").stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(__main_main())
