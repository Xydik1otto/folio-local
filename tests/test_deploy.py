# scripts/deploy-local.sh: self-hosted install WITHOUT containers (venv + uvicorn).
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "deploy-local.sh"


def find_bash():
    """A bash that actually works on this host (Windows: NOT the WSL stub)."""
    if os.name != "nt":
        return "bash"
    candidates = [os.environ.get("FOLIO_BASH"),
                  shutil.which("bash"),
                  r"C:\Program Files\Git\bin\bash.exe",
                  r"C:\Program Files\Git\usr\bin\bash.exe"]
    # git shipped with the hermes toolchain
    candidates += glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""),
                                         "hermes", "tools", "git-*",
                                         "usr", "bin", "bash.exe"))
    for cand in candidates:
        if cand and Path(cand).exists() and "system32" not in cand.lower():
            return cand
    pytest.skip("no usable bash found (WSL bash.exe excluded)")


def test_script_exists():
    assert SCRIPT.is_file()


def test_script_has_exec_bit_in_git():
    """Git stores the executable bit; checked out clones keep it (core.fileMode)."""
    out = subprocess.run(
        ["git", "ls-files", "-s", "scripts/deploy-local.sh"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert out.startswith("100755"), f"not executable in git index: {out!r}"


def test_script_passes_bash_syntax_check():
    bash = find_bash()
    subprocess.run([bash, "-n", str(SCRIPT)], check=True)


def test_no_docker_anywhere_in_script():
    text = SCRIPT.read_text(encoding="utf-8").lower()
    for word in ("docker", "docker-compose", "docker compose", "podman"):
        assert word not in text


def test_script_covers_install_and_serve_steps():
    text = SCRIPT.read_text(encoding="utf-8")
    assert '-m venv .venv' in text
    assert 'PYTHON:-python3' in text
    assert "pip install -r requirements.txt" in text
    assert "init_db" in text
    assert "uvicorn backend.main:app" in text
    assert "--install-only" in text
    assert 'set -euo pipefail' in text  # fail fast, no half-installed state


def test_help_option_prints_usage():
    bash = find_bash()
    out = subprocess.run([bash, str(SCRIPT), "--help"],
                         capture_output=True, text=True, check=True)
    assert "deploy-local" in out.stdout or "venv" in out.stdout


def test_install_only_runs_end_to_end(tmp_path, monkeypatch):
    """Real execution: create a venv from the script in a COPY of the repo
    (install-only mode) — proves the venv/pip/db steps actually work."""
    import shutil
    dst = tmp_path / "repo"
    shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(
        ".venv", "node_modules", "__pycache__", ".git", "folio.db",
        "android", "ios", "*.egg-info", "dotnet", "static"))
    env = dict(os.environ, PYTHON=os.environ.get("PYTHON", "python") if os.name == "nt"
               else "python3")
    bash = find_bash()
    subprocess.run([bash, "scripts/deploy-local.sh", "--install-only"],
                   cwd=dst, env=env, check=True, timeout=480,
                   capture_output=True, text=True)
    marker = dst / ".venv" / ("Scripts/python.exe" if os.name == "nt"
                              else "bin/python")
    assert marker.exists()
    assert (dst / "folio.db").exists()
