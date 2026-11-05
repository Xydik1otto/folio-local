# Financial math: XIRR (money-weighted return) and TWR (time-weighted return).
# This module is deliberately dependency-free and pure: date -> float cash flows.
from __future__ import annotations

import datetime as dt
from typing import Sequence

# A cash flow is (date, amount). Sign convention for XIRR here:
#   negative = money paid INTO the portfolio (deposit/buy),
#   positive = money received OUT of the portfolio (withdrawal, final value).


def _year_fraction(d0: dt.date, d1: dt.date) -> float:
    """ACT/365 year fraction, same convention as Excel's XIRR."""
    return (d1 - d0).days / 365.0


def npv(cashflows: Sequence[tuple[dt.date, float]], rate: float) -> float:
    """Net present value of cashflows discounted at an annual rate, ACT/365."""
    if not cashflows:
        return 0.0
    t0 = min(d for d, _ in cashflows)
    return sum(a / (1.0 + rate) ** _year_fraction(t0, d) for d, a in cashflows)


def xirr(cashflows: Sequence[tuple[dt.date, float]],
         lo: float = -0.9999, hi: float = 10.0,
         tol: float = 1e-10, max_iter: int = 200) -> float:
    """Annualised money-weighted return via Newton-Raphson with a bisection fallback.

    Raises ValueError when no sign change exists in [lo, hi] (no solution) or the
    cash flows are degenerate (all same sign / empty / single flow).
    """
    flows = [(d, float(a)) for d, a in cashflows if a != 0.0]
    if len(flows) < 2:
        raise ValueError("XIRR needs at least two non-zero cash flows")
    if not (any(a < 0 for _, a in flows) and any(a > 0 for _, a in flows)):
        raise ValueError("XIRR needs at least one negative and one positive cash flow")

    def f(r: float) -> float:
        return npv(flows, r)

    def df(r: float) -> float:
        t0 = min(d for d, _ in flows)
        # d/dr of a/(1+r)^t = -t*a/(1+r)^(t+1)
        return sum(-_year_fraction(t0, d) * a / (1.0 + r) ** (_year_fraction(t0, d) + 1)
                   for d, a in flows)

    a, b = lo, hi
    fa, fb = f(a), f(b)
    if fa * fb > 0:
        raise ValueError("no XIRR solution in search bracket")

    # Try Newton first from the midpoint; fall back to guaranteed bisection.
    r = (a + b) / 2.0
    for _ in range(max_iter):
        fr = f(r)
        if abs(fr) < tol:
            return r
        dr = df(r)
        if dr == 0:
            break
        step = fr / dr
        nr = r - step
        if not (lo < nr < hi) or nr == r:
            break
        r = nr

    # Bisection (always converges given the sign change).
    for _ in range(max_iter):
        m = (a + b) / 2.0
        fm = f(m)
        if abs(fm) < tol or (b - a) / 2.0 < tol:
            return m
        if fa * fm < 0:
            b, fb = m, fm
        else:
            a, fa = m, fm
    return (a + b) / 2.0


# --- TWR -------------------------------------------------------------------
# Time-weighted return chains sub-period returns between EXTERNAL flows
# (deposits/withdrawals). Internal activity (buys/sells/dividends/fees) does
# not create a sub-period boundary: it moves money inside the portfolio.
# With flows occurring at the END of each sub-period i:
#   r_i = (V(t_i) - F_i) / V(t_{i-1}),   TWR = prod(1 + r_i) - 1


def twr(valuations: Sequence[tuple[dt.date, float, float]]) -> float:
    """TWR from a series of (date, portfolio_value, external_flow_at_that_date).

    The first entry must carry flow 0.0 (opening value). Internal-only dates
    may be omitted entirely; only dates with a valuation are needed.
    """
    pts = sorted((d, float(v), float(f)) for d, v, f in valuations)
    if len(pts) < 2:
        raise ValueError("TWR needs at least two valuation points")
    product = 1.0
    for (_, v_prev, _), (d, v, flow) in zip(pts, pts[1:]):
        base = v_prev
        if base <= 0:
            raise ValueError(f"non-positive opening value on {d}")
        product *= (v - flow) / base
    return product - 1.0


def normalized_benchmark(
    port: Sequence[tuple[dt.date, float]],
    bench: Sequence[tuple[dt.date, float]],
) -> list[tuple[dt.date, float, float | None]]:
    """Normalized comparison series: both indexed to 100 at the first date.

    port: (date, portfolio_value) pairs; bench: (date, index close) pairs.
    The benchmark is a step function: the last known close on or before each
    portfolio date. Returns RAW normalized values — rounding to 2 decimals is
    presentation and belongs to the caller (this keeps parity with the native
    core, which also returns raw values; Python's round-half-even applies
    uniformly in both paths).
    """
    port_pts = sorted((d, float(v)) for d, v in port)
    bench_pts = sorted((d, float(v)) for d, v in bench)
    if not port_pts:
        raise ValueError("no portfolio valuation in range")

    def bench_at(day: dt.date) -> float | None:
        last = None
        for bd, close in bench_pts:
            if bd <= day:
                last = close
            else:
                break
        return last

    d0, p0 = port_pts[0]
    b0 = bench_at(d0)
    if b0 is None or p0 <= 1e-9:
        raise ValueError("cannot normalize benchmark series")
    out: list[tuple[dt.date, float, float | None]] = []
    for d, total in port_pts:
        b = bench_at(d)
        out.append((d, 100.0 * total / p0, None if b is None else 100.0 * b / b0))
    return out
