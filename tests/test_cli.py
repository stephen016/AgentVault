"""Tests for the CLI inspector."""

from __future__ import annotations

import subprocess
import sys

from agentvault import Vault


def _run_cli(*args: str, db_path: str) -> subprocess.CompletedProcess[str]:
    """Run the agentvault CLI as a subprocess."""
    return subprocess.run(
        [sys.executable, "-m", "agentvault.cli", *args],
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_inspect_lists_entries(tmp_path: object) -> None:
    db = str(tmp_path / "test.db")  # type: ignore[operator]
    vault = Vault("test", path=db)
    vault.put("findings", {"papers": ["a", "b"]}, agent="researcher")
    vault.put("status", "complete", agent="manager")
    vault.close()

    result = _run_cli("inspect", "test", "--path", db, db_path=db)
    assert result.returncode == 0
    assert "findings" in result.stdout
    assert "status" in result.stdout
    assert "researcher" in result.stdout
    assert "manager" in result.stdout


def test_inspect_key_detail(tmp_path: object) -> None:
    db = str(tmp_path / "test.db")  # type: ignore[operator]
    vault = Vault("test", path=db)
    vault.put("mykey", {"hello": "world"}, agent="agent-1")
    vault.close()

    result = _run_cli("inspect", "test", "--path", db, "--key", "mykey", db_path=db)
    assert result.returncode == 0
    assert "Key:       mykey" in result.stdout
    assert "Agent:     agent-1" in result.stdout
    assert "hello" in result.stdout


def test_inspect_key_history(tmp_path: object) -> None:
    db = str(tmp_path / "test.db")  # type: ignore[operator]
    vault = Vault("test", path=db)
    vault.put("doc", "v1", agent="alice")
    vault.put("doc", "v2", agent="bob")
    vault.put("doc", "v3", agent="alice")
    vault.close()

    result = _run_cli(
        "inspect", "test", "--path", db, "--key", "doc", "--history", db_path=db
    )
    assert result.returncode == 0
    assert "3 versions" in result.stdout
    assert "alice" in result.stdout
    assert "bob" in result.stdout


def test_inspect_filter_by_agent(tmp_path: object) -> None:
    db = str(tmp_path / "test.db")  # type: ignore[operator]
    vault = Vault("test", path=db)
    vault.put("a", 1, agent="alice")
    vault.put("b", 2, agent="bob")
    vault.put("c", 3, agent="alice")
    vault.close()

    result = _run_cli(
        "inspect", "test", "--path", db, "--agent", "alice", db_path=db
    )
    assert result.returncode == 0
    assert "alice" in result.stdout
    # bob's key "b" should not appear
    lines = [ln for ln in result.stdout.strip().split("\n") if ln and not ln.startswith("-")]
    data_lines = [ln for ln in lines if not ln.startswith("KEY")]
    for line in data_lines:
        assert "bob" not in line


def test_inspect_empty_vault(tmp_path: object) -> None:
    db = str(tmp_path / "test.db")  # type: ignore[operator]
    vault = Vault("test", path=db)
    vault.close()

    result = _run_cli("inspect", "test", "--path", db, db_path=db)
    assert result.returncode == 0
    assert "empty" in result.stdout
