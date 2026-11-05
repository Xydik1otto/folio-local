#!/usr/bin/env python3
"""Benchmark: pure-Python XIRR vs the native .NET core (FolioCore).

Usage:
    python scripts/benchmark_native.py [--flows 100000] [--ops 2000]

Scenario A — one XIRR over a large cash-flow list (deep history).
Scenario B — a realistic batch: many small XIRR computations delivered to
the native CLI as ONE subprocess call (that is how the app uses it).

The numbers quoted in README came from this script. If the native
executable is not built (scripts/build_native.sh) the script reports it
and exits non-zero instead of printing invented numbers.
"""
from __future__ import annotations

import argparse
import random
import sys
import time

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from backend import math_finance, native_accel  # noqa: E402


def make_flows(n: int, seed: int = 42):
    """Deterministic 5-year transaction history with n external flows."""
    rng = random.Random(seed)
    base = __import__("datetime").date(2020, 1, 1)
    flows = []
    day = 0
    for i in range(n):
        day += i % 3  # a few flows share a date
        d = base + __import__("datetime").timedelta(days=day % 1800)
        if i % 4 == 3:
            amount = rng.uniform(50.0, 500.0)     # withdrawal
        else:
            amount = -rng.uniform(100.0, 1000.0)  # deposit
        flows.append((d, amount))
    flows.sort(key=lambda x: x[0])
    # close the portfolio: final valuation as a positive flow
    flows[-1] = (flows[-1][0], abs(sum(a for _, a in flows)) * 1.35)
    return flows


def make_small_flows(n_ops: int, seed: int = 7):
    """Deterministic small portfolios (7 deposits + closing valuation) —
    every one guaranteed to have a sign change, so XIRR always solves."""
    rng = random.Random(seed)
    base = __import__("datetime").date(2020, 1, 1)
    out = []
    for k in range(n_ops):
        f = [(base + __import__("datetime").timedelta(days=k + i * 37),
              -rng.uniform(100.0, 1000.0)) for i in range(7)]
        total = -sum(a for _, a in f)
        f.append((base + __import__("datetime").timedelta(days=k + 289),
                  total * rng.uniform(1.0, 1.8)))
        out.append(f)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--flows", type=int, default=100_000)
    ap.add_argument("--ops", type=int, default=2_000)
    ap.add_argument("--repeat", type=int, default=3)
    args = ap.parse_args()

    if not native_accel.available():
        print("native FolioCli executable not found — build it first:")
        print("    scripts/build_native.sh   (Windows: scripts/build_native.bat)")
        return 1

    flows = make_flows(args.flows)
    print(f"XIRR input: {len(flows):,} cash flows\n")

    # Scenario A ------------------------------------------------------------
    r_py = math_finance.xirr(flows)
    t_py = min(_time(lambda: math_finance.xirr(flows)) for _ in range(args.repeat))
    r_nat = native_accel.xirr(flows)
    t_nat = min(_time(lambda: native_accel.xirr(flows)) for _ in range(args.repeat))
    _report("A. single XIRR over the full cash-flow list",
            t_py, t_nat, r_py, r_nat)
    a = (t_py, t_nat)

    # Scenario B ------------------------------------------------------------
    small = make_small_flows(args.ops)
    ops = [{"op": "xirr", "flows": [{"d": d.isoformat(), "a": a} for d, a in f]}
           for f in small]

    def py_batch() -> None:
        for f in small:
            math_finance.xirr(f)

    def nat_batch() -> None:
        res = native_accel.batch(ops, timeout=600)
        if res is None or not all(r.get("ok") for r in res):
            raise RuntimeError("native batch failed")

    t_py = min(_time(py_batch) for _ in range(args.repeat))
    t_nat = min(_time(nat_batch) for _ in range(args.repeat))
    print(f"\nScenario B: {len(ops):,} small XIRR ops in one native call")
    print(f"  Python : {t_py * 1000:10.1f} ms")
    print(f"  native : {t_nat * 1000:10.1f} ms  (includes one process spawn)")
    print(f"  speedup: {t_py / t_nat:10.1f}x")
    print("\nMarkdown (paste into README):\n")
    print("| Scenario | Python | .NET core | speedup |")
    print("|---|---:|---:|---:|")
    print(f"| One XIRR, {len(flows):,} flows | {a[0] * 1000:.0f} ms "
          f"| {a[1] * 1000:.0f} ms | {a[0] / a[1]:.1f}x |")
    print(f"| {len(ops):,} XIRR ops in one native call | {t_py * 1000:.0f} ms "
          f"| {t_nat * 1000:.0f} ms | {t_py / t_nat:.1f}x |")
    return 0


def _time(fn):
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


def _report(title, t_py, t_nat, r_py, r_nat):
    print(f"Scenario {title}")
    print(f"  Python : {t_py * 1000:10.1f} ms   rate = {r_py:.12f}")
    print(f"  native : {t_nat * 1000:10.1f} ms   rate = {r_nat:.12f}")
    print(f"  speedup: {t_py / t_nat:10.1f}x   "
          f"parity = {abs(r_py - r_nat) <= 1e-9 * max(1.0, abs(r_py))}")


if __name__ == "__main__":
    raise SystemExit(main())
