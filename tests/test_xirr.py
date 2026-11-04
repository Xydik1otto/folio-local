# XIRR tests: closed-form cases with independently known answers.
import datetime as dt

import pytest

from backend.math_finance import npv, xirr

D = dt.date


def test_xirr_simple_one_year_10pct():
    # -1000 today, +1100 exactly one (non-leap) year later -> 10% annualised
    flows = [(D(2021, 1, 1), -1000.0), (D(2022, 1, 1), 1100.0)]
    assert xirr(flows) == pytest.approx(0.10, abs=1e-6)


def test_xirr_two_years_closed_form():
    # -1000 -> +1400 over exactly 2 (non-leap) years: r = sqrt(1.4) - 1
    flows = [(D(2021, 1, 1), -1000.0), (D(2023, 1, 1), 1400.0)]
    expected = (1400.0 / 1000.0) ** 0.5 - 1.0
    assert xirr(flows) == pytest.approx(expected, abs=1e-8)


def test_xirr_multiple_flows_npv_zero_at_solution():
    # No closed form; verify the DEFINING property: NPV at the solution is 0.
    flows = [
        (D(2023, 1, 15), -10000.0),
        (D(2023, 7, 1), 2000.0),
        (D(2024, 1, 15), 3000.0),
        (D(2024, 7, 1), 2500.0),
        (D(2025, 1, 15), 4000.0),
    ]
    r = xirr(flows)
    assert npv(flows, r) == pytest.approx(0.0, abs=1e-6)
    assert 0.0 < r < 0.5  # sanity: these flows roughly double in 2 years


def test_xirr_negative_return():
    flows = [(D(2020, 1, 1), -1000.0), (D(2021, 1, 1), 900.0)]
    r = xirr(flows)
    assert npv(flows, r) == pytest.approx(0.0, abs=1e-6)
    assert r < 0


def test_xirr_irregular_dates_nonannual_year_fraction():
    # Same 10% profile but over half a year -> annualised ~ (1.1)^2 - 1 = 21%
    flows = [(D(2020, 1, 1), -1000.0), (D(2020, 7, 1), 1100.0)]  # 182 days
    r = xirr(flows)
    expected = (1.1) ** (365 / 182) - 1.0
    assert r == pytest.approx(expected, rel=1e-3)


def test_xirr_all_positive_raises():
    flows = [(D(2020, 1, 1), 100.0), (D(2021, 1, 1), 200.0)]
    with pytest.raises(ValueError):
        xirr(flows)


def test_xirr_single_flow_raises():
    flows = [(D(2020, 1, 1), -100.0)]
    with pytest.raises(ValueError):
        xirr(flows)
