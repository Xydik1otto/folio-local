# Parity tests: native .NET core (FolioCore via FolioCli) vs pure-Python
# implementation. The contract is bit-comparable results (float tolerance
# 1e-9) and identical error messages, because native_accel must be a
# drop-in replacement for backend.math_finance.
# Native-parity tests skip (gracefully) when the executable was not built;
# the fallback tests always run.
import datetime as dt
import json
import subprocess
import sys

import pytest

from backend import math_finance, native_accel

D = dt.date

XIRR_CASES = [
    # 10% over exactly one year
    [(D(2021, 1, 1), -1000.0), (D(2022, 1, 1), 1100.0)],
    # negative rate
    [(D(2020, 1, 1), -1000.0), (D(2021, 1, 1), 900.0)],
    # irregular dates: 10% over half a year annualises to ~21%
    [(D(2020, 1, 1), -1000.0), (D(2020, 7, 1), 1100.0)],
    # multiple flows, no closed form
    [(D(2023, 1, 15), -10000.0), (D(2023, 7, 1), 2000.0),
     (D(2024, 1, 15), 3000.0), (D(2024, 7, 1), 2500.0),
     (D(2025, 1, 15), 4000.0)],
    # zero amounts must be ignored, same as Python
    [(D(2021, 1, 1), -1000.0), (D(2021, 6, 1), 0.0), (D(2022, 1, 1), 1100.0)],
    # deposits and withdrawals interleaved
    [(D(2020, 1, 1), -5000.0), (D(2020, 7, 1), -2000.0),
     (D(2021, 1, 1), 1500.0), (D(2021, 7, 1), 6500.0)],
]


@pytest.fixture(autouse=True)
def _fresh_cache():
    native_accel.reset_cache()
    yield
    native_accel.reset_cache()


def _native_available() -> bool:
    return native_accel.available()


requires_native = pytest.mark.skipif(
    not _native_available(), reason="native FolioCli executable not built")


# --- XIRR parity -------------------------------------------------------------

@requires_native
@pytest.mark.parametrize("flows", XIRR_CASES)
def test_native_xirr_matches_python(flows):
    assert native_accel.xirr(flows) == pytest.approx(
        math_finance.xirr(flows), abs=1e-9)


@requires_native
def test_native_xirr_respects_custom_bracket():
    flows = XIRR_CASES[1]
    r_py = math_finance.xirr(flows, lo=-0.5, hi=0.5)
    r_nat = native_accel.xirr(flows, lo=-0.5, hi=0.5)
    assert r_nat == pytest.approx(r_py, abs=1e-9)


# --- error-message parity ----------------------------------------------------

@requires_native
def test_native_single_flow_error_matches_python():
    flows = [(D(2020, 1, 1), -100.0)]
    with pytest.raises(ValueError) as nat:
        native_accel.xirr(flows)
    with pytest.raises(ValueError) as py:
        math_finance.xirr(flows)
    assert str(nat.value) == str(py.value)
    assert str(py.value) == "XIRR needs at least two non-zero cash flows"


@requires_native
def test_native_all_positive_error_matches_python():
    flows = [(D(2020, 1, 1), 100.0), (D(2021, 1, 1), 200.0)]
    with pytest.raises(ValueError) as nat:
        native_accel.xirr(flows)
    with pytest.raises(ValueError) as py:
        math_finance.xirr(flows)
    assert str(nat.value) == str(py.value)


# --- TWR parity --------------------------------------------------------------

@requires_native
def test_native_twr_matches_python():
    valuations = [(D(2024, 1, 1), 1000.0, 0.0),
                  (D(2024, 3, 1), 1200.0, 0.0)]
    assert native_accel.twr(valuations) == pytest.approx(
        math_finance.twr(valuations), abs=1e-9)


@requires_native
def test_native_twr_with_external_flow_matches_python():
    valuations = [(D(2024, 1, 1), 1000.0, 0.0),
                  (D(2024, 3, 1), 1300.0, 100.0),
                  (D(2024, 6, 1), 1100.0, -200.0)]
    assert native_accel.twr(valuations) == pytest.approx(
        math_finance.twr(valuations), abs=1e-9)


@requires_native
def test_native_twr_error_message_matches_python():
    valuations = [(D(2024, 1, 1), 0.0, 0.0), (D(2024, 3, 1), 100.0, 0.0)]
    with pytest.raises(ValueError) as nat:
        native_accel.twr(valuations)
    with pytest.raises(ValueError) as py:
        math_finance.twr(valuations)
    assert str(nat.value) == str(py.value)
    assert str(py.value) == "non-positive opening value on 2024-03-01"


# --- normalized benchmark parity ---------------------------------------------

BENCH_PORT = [(D(2024, 1, 1), 1000.0), (D(2024, 2, 1), 1100.0),
              (D(2024, 3, 1), 990.0)]
BENCH_BENCH = [(D(2024, 1, 1), 400.0), (D(2024, 3, 1), 480.0)]  # gap on Feb 1


@requires_native
def test_native_benchmark_raw_values_match_python():
    raw_py = math_finance.normalized_benchmark(BENCH_PORT, BENCH_BENCH)
    op = {"op": "benchmark",
          "portfolio": [{"d": d.isoformat(), "v": v} for d, v in BENCH_PORT],
          "bench": [{"d": d.isoformat(), "v": v} for d, v in BENCH_BENCH]}
    results = native_accel.batch([op])
    assert results is not None and results[0]["ok"]
    rows = results[0]["points"]
    assert len(rows) == len(raw_py)
    for row, (d, p, b) in zip(rows, raw_py):
        assert row["d"] == d.isoformat()
        assert row["portfolio"] == pytest.approx(p, abs=1e-9)
        if b is None:
            assert "benchmark" not in row
        else:
            assert row["benchmark"] == pytest.approx(b, abs=1e-9)
    # forward-fill through the gap: Feb 1 shows the Jan close (400/400 = 100)
    assert raw_py[1][2] == pytest.approx(100.0)


@requires_native
def test_native_benchmark_wrapper_rounds_like_endpoint():
    native = native_accel.normalized_benchmark(BENCH_PORT, BENCH_BENCH)
    fallback = [(d, round(p, 2), None if b is None else round(b, 2))
                for d, p, b in math_finance.normalized_benchmark(
                    BENCH_PORT, BENCH_BENCH)]
    assert native == fallback
    assert native[0][1] == 100.0 and native[0][2] == 100.0


@requires_native
def test_native_benchmark_error_message_matches_python():
    with pytest.raises(ValueError) as nat:
        native_accel.normalized_benchmark(BENCH_PORT, [])  # bench starts later
    with pytest.raises(ValueError) as py:
        math_finance.normalized_benchmark(BENCH_PORT, [])
    assert str(nat.value) == str(py.value)


# --- batch mode (one subprocess call, many operations) ------------------------

@requires_native
def test_native_batch_of_mixed_ops_matches_python():
    ops = [{"op": "xirr", "flows": [{"d": d.isoformat(), "a": a}
                                    for d, a in flows]}
           for flows in XIRR_CASES]
    ops.append({"op": "twr", "valuations": [
        {"d": "2024-01-01", "v": 1000.0, "f": 0.0},
        {"d": "2024-03-01", "v": 1200.0, "f": 0.0}]})
    ops.append({"op": "xirr", "flows": [{"d": "2020-01-01", "a": -100.0}]})
    ops.append({"op": "benchmark",
                "portfolio": [{"d": d.isoformat(), "v": v}
                              for d, v in BENCH_PORT],
                "bench": [{"d": d.isoformat(), "v": v}
                          for d, v in BENCH_BENCH]})
    results = native_accel.batch(ops)
    assert results is not None and len(results) == len(ops)
    for i, flows in enumerate(XIRR_CASES):
        assert results[i]["ok"]
        assert results[i]["value"] == pytest.approx(
            math_finance.xirr(flows), abs=1e-9)
    assert results[-3]["value"] == pytest.approx(
        math_finance.twr([(D(2024, 1, 1), 1000.0, 0.0),
                          (D(2024, 3, 1), 1200.0, 0.0)]), abs=1e-9)
    assert not results[-2]["ok"]          # single flow -> in-band error
    assert results[-1]["ok"]              # benchmark op


# --- fallback ------------------------------------------------------------------

def test_fallback_without_native_exe(monkeypatch):
    """exe absent -> silent graceful fallback to the Python implementation."""
    monkeypatch.setattr(native_accel, "batch", lambda ops, timeout=300: None)
    flows = XIRR_CASES[0]
    assert native_accel.xirr(flows) == math_finance.xirr(flows)
    valuations = [(D(2024, 1, 1), 1000.0, 0.0), (D(2024, 3, 1), 1200.0, 0.0)]
    assert native_accel.twr(valuations) == math_finance.twr(valuations)


@pytest.mark.skipif(sys.platform != "win32", reason="uses a .cmd stub")
def test_fallback_on_broken_native_exe(monkeypatch, tmp_path):
    """A native command that exits non-zero must degrade to Python."""
    stub = tmp_path / "broken.cmd"
    stub.write_text("@exit /b 1\r\n", encoding="ascii")
    monkeypatch.setenv("FOLIO_NATIVE", str(stub))
    monkeypatch.setattr(native_accel, "_candidates", lambda: [[str(stub)]])
    native_accel.reset_cache()
    flows = XIRR_CASES[0]
    assert native_accel.xirr(flows) == pytest.approx(0.10, abs=1e-6)
    assert not native_accel.available()   # disabled for the rest of the process


@pytest.mark.skipif(sys.platform != "win32", reason="uses a .cmd stub")
def test_fallback_on_native_stderr_crash(monkeypatch, tmp_path):
    stub = tmp_path / "garbled.cmd"
    stub.write_text("@echo not json\r\n", encoding="ascii")
    monkeypatch.setenv("FOLIO_NATIVE", str(stub))
    monkeypatch.setattr(native_accel, "_candidates", lambda: [[str(stub)]])
    native_accel.reset_cache()
    assert native_accel.xirr(XIRR_CASES[0]) == pytest.approx(0.10, abs=1e-6)


def test_missing_folio_native_env_means_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv("FOLIO_NATIVE", str(tmp_path / "nope" / "FolioCli.exe"))
    native_accel.reset_cache()
    assert not native_accel.available()
    # and the Python path still answers correctly
    assert native_accel.xirr(XIRR_CASES[0]) == pytest.approx(0.10, abs=1e-6)


@requires_native
def test_folio_native_env_points_at_real_exe(monkeypatch):
    cmd = native_accel._resolve()
    assert cmd is not None
    monkeypatch.setenv("FOLIO_NATIVE", cmd[0])
    native_accel.reset_cache()
    assert native_accel.available()
    assert native_accel.xirr(XIRR_CASES[0]) == pytest.approx(0.10, abs=1e-6)


@requires_native
def test_cli_rejects_malformed_request():
    """Top-level garbage exits non-zero; the wrapper falls back, not crashes."""
    cmd = native_accel._resolve()
    assert cmd is not None
    proc = subprocess.run(cmd, input=b"{not json", capture_output=True)
    assert proc.returncode != 0
    with pytest.raises(json.JSONDecodeError):
        json.loads(proc.stdout.decode())
