"""FACT-003 Tests: isolierte Git-Worktree (create / remove / status)."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

# worktree.py liegt in ./scripts -> auf sys.path legen
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import worktree  # noqa: E401


def _make_repo() -> Path:
    """Ein minimales Git-Repo mit einem Commit (frisches/ leeres Repo)."""
    tmp = tempfile.mkdtemp()
    repo = Path(tmp) / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("minimal repo\n")
    subprocess.run(["git", "init", "-b", "main", str(repo)],
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo


def _new_ticket_path(name: str) -> Path:
    tmp = Path(tempfile.mkdtemp()) / name
    return tmp


class TestWorktree:
    def test_create_makes_worktree_and_state(self):
        repo = _make_repo()
        path = _new_ticket_path("w1")
        state = worktree.create("FACT-003", str(path), repo=str(repo),
                                status="running", model="kiara")
        assert state["ticket_id"] == "FACT-003"
        assert state["model"] == "kiara"
        assert state["status"] == "running"
        assert Path(state["path"]).exists()
        assert (Path(state["path"]) / "factory_state.json").exists()
        assert worktree.is_worktree("FACT-003", path=str(path), repo=str(repo))

    def test_status_returns_state(self):
        repo = _make_repo()
        path = _new_ticket_path("w2")
        worktree.create("T1", str(path), repo=str(repo))
        s = worktree.status("T1", path=str(path), repo=str(repo))
        assert s is not None
        assert s["ticket_id"] == "T1"

    def test_status_missing(self):
        repo = _make_repo()
        path = _new_ticket_path("w3")
        assert worktree.status("T2", path=str(path), repo=str(repo)) is None

    def test_remove_clean(self):
        repo = _make_repo()
        path = _new_ticket_path("w4")
        worktree.create("T2", str(path), repo=str(repo))
        assert worktree.remove("T2", path=str(path), repo=str(repo))
        assert not Path(path).exists()
        assert not worktree.is_worktree("T2", path=str(path), repo=str(repo))

    def test_remove_missing_noop(self):
        repo = _make_repo()
        path = _new_ticket_path("w5")
        assert worktree.remove("T3", path=str(path), repo=str(repo)) is True

    def test_create_idempotent_existing(self):
        """Bestehendes Worktree wird sauber neu aufgesetzt."""
        repo = _make_repo()
        path = _new_ticket_path("w6")
        s1 = worktree.create("T4", str(path), repo=str(repo))
        s2 = worktree.create("T4", str(path), repo=str(repo))
        assert s2["ticket_id"] == "T4"
        assert (Path(s2["path"]) / "factory_state.json").exists()
        assert worktree.is_worktree("T4", path=str(path), repo=str(repo))
