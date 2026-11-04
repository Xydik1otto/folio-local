# Multi-currency conversion via ECB-style EUR-base rates.
import pytest

from backend.fx import convert, to_eur

RATES = {"EUR": 1.0, "USD": 1.10, "UAH": 41.0, "PLN": 4.30}


def test_to_eur_from_usd():
    assert to_eur(110.0, "USD", RATES) == pytest.approx(100.0)


def test_to_eur_eur_passthrough():
    assert to_eur(55.0, "EUR", RATES) == 55.0


def test_convert_usd_to_uah():
    # 110 USD = 100 EUR = 4100 UAH
    assert convert(110.0, "USD", "UAH", RATES) == pytest.approx(4100.0)


def test_convert_uah_to_usd_roundtrip():
    there = convert(820.0, "UAH", "USD", RATES)
    back = convert(there, "USD", "UAH", RATES)
    assert back == pytest.approx(820.0)


def test_convert_same_currency_identity():
    assert convert(123.45, "PLN", "PLN", RATES) == 123.45


def test_unknown_currency_raises():
    with pytest.raises(ValueError):
        to_eur(10.0, "GBP", RATES)
