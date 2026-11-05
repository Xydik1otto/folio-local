# Packaging: pyproject.toml metadata, entry point, installability.
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_metadata():
    py = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    proj = py["project"]
    assert proj["name"] == "folio-local"
    assert proj["version"] == "1.0.0"
    assert proj["requires-python"] == ">=3.12"
    assert "fastapi" in " ".join(proj["dependencies"])
    assert "folio-local = backend.main:run" in " ".join(
        proj["scripts"].values()) or proj["scripts"]["folio-local"] == "backend.main:run"


def test_run_entry_point_importable():
    from backend.main import run
    assert callable(run)


def test_requirements_match_dependencies():
    reqs = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for pkg in ("fastapi", "uvicorn", "httpx"):
        assert pkg in reqs


def test_editable_install_works(tmp_path):
    """`pip install -e .` succeeds (metadata is valid)."""
    import subprocess
    import sys
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)],
                   check=True, capture_output=True)
    py = str(venv / "Scripts" / "python.exe") if sys.platform == "win32" \
        else str(venv / "bin" / "python")
    subprocess.run([py, "-m", "pip", "install", "--quiet", "-e", str(ROOT)],
                   check=True, capture_output=True, cwd=str(ROOT))
    # entry point script exists
    script = venv / "Scripts" / "folio-local.exe" if sys.platform == "win32" \
        else venv / "bin" / "folio-local"
    assert script.exists()
