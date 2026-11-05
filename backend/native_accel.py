# Native accelerator for the financial-math core.
#
# FolioCore (dotnet/, C# .NET 10) is a 1:1 port of backend/math_finance.py
# (XIRR Newton+bisection ACT/365, TWR) plus the normalized benchmark series.
# When the compiled FolioCli executable is available, the math is delegated
# to it through a subprocess (JSON on stdin -> JSON on stdout, batch
# operations in a single call); otherwise everything silently falls back to
# the pure-Python implementation — the results are identical (within a float
# tolerance of 1e-9), only the speed differs.
#
# Executable resolution order:
#   1. $FOLIO_NATIVE — path to the FolioCli executable;
#   2. dotnet/FolioCli/bin/Release/net10.0/<rid>/publish/FolioCli(.exe);
#   3. `dotnet` on PATH + dotnet/FolioCli/bin/Release/net10.0/FolioCli.dll.
# Build it with scripts/build_native.sh (Windows: scripts/build_native.bat).
#
# Any native failure (missing exe, crash, malformed output) degrades to the
# Python implementation — the app must never break because the accelerator
# is absent.
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from backend import math_finance

_REPO = Path(__file__).resolve().parent.parent
_EXE_NAME = "FolioCli.exe" if os.name == "nt" else "FolioCli"

# A cheap valid request used to verify a candidate executable actually works.
_PROBE_OP = {"op": "xirr",
             "flows": [{"d": "2021-01-01", "a": -1000.0},
                       {"d": "2022-01-01", "a": 1100.0}]}

# env FOLIO_NATIVE value -> (checked, resolved command). One probe per process.
_resolved: dict[str, list[str] | None] = {}
_checked: set[str] = set()


def _candidates() -> list[list[str]]:
    cands: list[list[str]] = []
    env = os.environ.get("FOLIO_NATIVE")
    if env:
        cands.append([env])
    base = _REPO / "dotnet" / "FolioCli" / "bin" / "Release" / "net10.0"
    for exe in sorted(base.glob(f"*/publish/{_EXE_NAME}")):
        cands.append([str(exe)])
    dotnet = shutil.which("dotnet")
    if dotnet:
        cands.append([dotnet, str(base / "FolioCli.dll")])
    return cands


def _resolve() -> list[str] | None:
    """Find and probe the native CLI once per process; None = unavailable."""
    key = os.environ.get("FOLIO_NATIVE", "")
    if key in _checked:
        return _resolved.get(key)
    cmd: list[str] | None = None
    for cand in _candidates():
        try:
            proc = subprocess.run(
                cand, input=json.dumps({"ops": [_PROBE_OP]}).encode("utf-8"),
                capture_output=True, timeout=60)
            out = json.loads(proc.stdout.decode("utf-8"))
            if (proc.returncode == 0 and out.get("engine") == "dotnet"
                    and out.get("results", [{}])[0].get("ok")):
                cmd = cand
                break
        except Exception:
            continue
    _checked.add(key)
    _resolved[key] = cmd
    return cmd


def reset_cache() -> None:
    """Forget the probe result (used by tests and after env changes)."""
    _checked.clear()
    _resolved.clear()


def available() -> bool:
    return _resolve() is not None


def batch(ops: list[dict], timeout: float = 300) -> list[dict] | None:
    """Run a batch of operations natively; None means 'not available / failed'.

    On a structural failure the accelerator is disabled for the rest of the
    process so we stop paying the cost of discovering it is broken.
    """
    cmd = _resolve()
    if cmd is None:
        return None
    try:
        proc = subprocess.run(
            cmd, input=json.dumps({"ops": ops}).encode("utf-8"),
            capture_output=True, timeout=timeout)
        if proc.returncode != 0:
            raise OSError(f"native CLI exited {proc.returncode}")
        out = json.loads(proc.stdout.decode("utf-8"))
        results = out.get("results")
        if not isinstance(results, list) or len(results) != len(ops):
            raise ValueError("malformed native CLI response")
        return results
    except Exception:
        _disable()
        return None


def _disable() -> None:
    key = os.environ.get("FOLIO_NATIVE", "")
    _checked.clear()
    _resolved.clear()
    _checked.add(key)
    _resolved[key] = None


def _iso(d) -> str:
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def xirr(cashflows: Sequence[tuple], lo: float = -0.9999, hi: float = 10.0,
         tol: float = 1e-10, max_iter: int = 200) -> float:
    """math_finance.xirr, accelerated when the native core is available."""
    op = {"op": "xirr",
          "flows": [{"d": _iso(d), "a": float(a)} for d, a in cashflows],
          "lo": lo, "hi": hi, "tol": tol, "max_iter": max_iter}
    res = batch([op])
    if res is not None:
        r = res[0]
        if r.get("ok"):
            return float(r["value"])
        raise ValueError(r.get("error", "native XIRR failed"))
    return math_finance.xirr(cashflows, lo, hi, tol, max_iter)


def twr(valuations: Sequence[tuple]) -> float:
    """math_finance.twr, accelerated when the native core is available."""
    op = {"op": "twr",
          "valuations": [{"d": _iso(d), "v": float(v), "f": float(f)}
                         for d, v, f in valuations]}
    res = batch([op])
    if res is not None:
        r = res[0]
        if r.get("ok"):
            return float(r["value"])
        raise ValueError(r.get("error", "native TWR failed"))
    return math_finance.twr(valuations)


def normalized_benchmark(
    port: Sequence[tuple],
    bench: Sequence[tuple],
) -> list[tuple[dt.date, float, float | None]]:
    """Normalized series rounded to 2 decimals (same presentation as the
    /api/portfolio/benchmark endpoint), accelerated when available."""
    op = {"op": "benchmark",
          "portfolio": [{"d": _iso(d), "v": float(v)} for d, v in port],
          "bench": [{"d": _iso(d), "v": float(v)} for d, v in bench]}
    res = batch([op])
    if res is not None:
        r = res[0]
        if r.get("ok"):
            out: list[tuple[dt.date, float, float | None]] = []
            for row in r["points"]:
                b = row.get("benchmark")
                out.append((dt.date.fromisoformat(row["d"]),
                            round(float(row["portfolio"]), 2),
                            None if b is None else round(float(b), 2)))
            return out
        raise ValueError(r.get("error", "native benchmark failed"))
    return [(d, round(p, 2), None if b is None else round(b, 2))
            for d, p, b in math_finance.normalized_benchmark(port, bench)]
