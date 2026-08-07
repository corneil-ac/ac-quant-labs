import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

from strategy_diagnostics import diagnose_trend_momentum
from strategy_framework import SignalAction
from trend_momentum_strategy import TrendMomentumStrategy


def candles(values):
    values = np.asarray(values, dtype=float)
    return pd.DataFrame({
        "time": np.arange(len(values)), "open": values,
        "high": values + 0.2, "low": values - 0.2, "close": values,
    })


def market(direction):
    if direction == "BUY":
        h1 = candles(np.linspace(100, 200, 220))
        m15 = candles(np.linspace(150, 200, 70))
        m15.loc[69, ["open", "high", "low", "close"]] = [198, 202, 197, 201]
    else:
        h1 = candles(np.linspace(200, 100, 220))
        m15 = candles(np.linspace(150, 100, 70))
        m15.loc[69, ["open", "high", "low", "close"]] = [102, 103, 98, 99]
    return {"H1": h1, "M15": m15}


@pytest.mark.parametrize("action", ["BUY", "SELL"])
def test_diagnostics_explain_directional_decisions(action):
    data = market(action)
    signal = TrendMomentumStrategy().evaluate("EURUSD", data)
    diagnostics = diagnose_trend_momentum(signal, data)

    assert diagnostics.final_decision == action
    assert diagnostics.h1_direction == action
    assert diagnostics.m15_direction == action
    assert diagnostics.h1_trend == "PASS"
    assert diagnostics.m15_momentum == "PASS"
    assert diagnostics.ema20_pullback == "PASS"
    assert diagnostics.confirmation_candle == "PASS"
    assert diagnostics.atr is not None
    assert diagnostics.stop_loss == signal.stop_loss
    assert diagnostics.take_profit == signal.take_profit


def test_hold_reports_exact_failed_gate_and_complete_format():
    data = market("BUY")
    data["M15"].loc[67:, "low"] = data["M15"].loc[67:, "close"]
    signal = TrendMomentumStrategy().evaluate("EURUSD", data)
    diagnostics = diagnose_trend_momentum(signal, data)
    output = diagnostics.format()

    assert signal.action is SignalAction.HOLD
    assert diagnostics.reason == "Waiting for EMA20 pullback."
    assert "ATR(14)" in output
    assert "Calculated Stop Loss" in output
    assert "Calculated Take Profit" in output
    assert "Final Decision          : HOLD" in output
    assert output.endswith("Reason:\nWaiting for EMA20 pullback.")


def test_insufficient_data_hold_is_diagnostic():
    data = {"H1": pd.DataFrame(), "M15": pd.DataFrame()}
    signal = TrendMomentumStrategy().evaluate("EURUSD", data)
    diagnostics = diagnose_trend_momentum(signal, data)

    assert diagnostics.final_decision == "HOLD"
    assert diagnostics.reason == "Insufficient closed candle data."
