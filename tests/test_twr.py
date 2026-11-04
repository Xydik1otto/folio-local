# TWR tests on artificial transaction sets with known answers.
import datetime as dt

import pytest

from backend.math_finance import twr

D = dt.date


def test_twr_classic_21_percent():
    # Textbook example: 100 grows to 110 (+10%), then a deposit of 100
    # brings the pot to 210 which grows to 231 (+10%) -> TWR = 1.1*1.1 - 1 = 21%.
    # Convention: each valuation is measured AFTER that day's external flow.
    pts = [
        (D(2024, 1, 1), 100.0, 0.0),
        (D(2024, 4, 1), 210.0, 100.0),  # 110 before the flow, 210 after
        (D(2024, 7, 1), 231.0, 0.0),
    ]
    assert twr(pts) == pytest.approx(0.21, abs=1e-9)


def test_twr_withdrawal_adjusted():
    # 200 -> 240 (+20%), withdraw 40 (leaving 200) -> 220 (+10%)
    # TWR = 1.2 * 1.1 - 1 = 32%
    pts = [
        (D(2024, 1, 1), 200.0, 0.0),
        (D(2024, 3, 1), 200.0, -40.0),  # 240 before the withdrawal, 200 after
        (D(2024, 6, 1), 220.0, 0.0),
    ]
    assert twr(pts) == pytest.approx(0.32, abs=1e-9)


def test_twr_ignores_internal_activity():
    # A buy/sell is internal: if valuations already reflect it, TWR must not
    # double-count. A flat market with a mid-period buy stays flat.
    pts = [
        (D(2024, 1, 1), 100.0, 0.0),
        (D(2024, 2, 1), 100.0, 0.0),  # market flat, no flows
        (D(2024, 3, 1), 100.0, 0.0),
    ]
    assert twr(pts) == pytest.approx(0.0, abs=1e-12)


def test_twr_negative_period():
    pts = [
        (D(2024, 1, 1), 100.0, 0.0),
        (D(2024, 4, 1), 80.0, 0.0),   # -20%
        (D(2024, 7, 1), 96.0, 0.0),   # +20% back
    ]
    # 0.8 * 1.2 = 0.96 -> -4%
    assert twr(pts) == pytest.approx(-0.04, abs=1e-9)


def test_twr_needs_two_points():
    with pytest.raises(ValueError):
        twr([(D(2024, 1, 1), 100.0, 0.0)])


def test_twr_unsorted_input_ok():
    # Sorting must not change the result of the classic case.
    pts = [
        (D(2024, 7, 1), 231.0, 0.0),
        (D(2024, 1, 1), 100.0, 0.0),
        (D(2024, 4, 1), 210.0, 100.0),
    ]
    assert twr(pts) == pytest.approx(0.21, abs=1e-9)
