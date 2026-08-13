import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

from broker import VolumeValidation
from execution_manager import ExecutionManager
from strategy_framework import SignalAction, StrategySignal, TradingStrategy, strategy_registry
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

        # Recent EMA20 pullback followed by bullish confirmation
        m15.loc[68, "low"] = 190
        m15.loc[69, ["open", "high", "low", "close"]] = [198, 202, 197, 201]

    else:
        h1 = candles(np.linspace(200, 100, 220))
        m15 = candles(np.linspace(150, 100, 70))

        # Recent EMA20 pullback followed by bearish confirmation
        m15.loc[68, "high"] = 110
        m15.loc[69, ["open", "high", "low", "close"]] = [102, 103, 98, 99]

    return {"H1": h1, "M15": m15}


def test_strategy_interface_and_registry():
    assert issubclass(TrendMomentumStrategy, TradingStrategy)
    assert isinstance(strategy_registry.create("TrendMomentumStrategy"), TradingStrategy)


@pytest.mark.parametrize("action", ["BUY", "SELL"])
def test_directional_conditions(action):
    signal = TrendMomentumStrategy().evaluate("EURUSD", market(action))
    assert signal.action is SignalAction(action)
    assert signal.stop_loss is not None and signal.take_profit is not None
    risk = abs(signal.entry_reference - signal.stop_loss)
    assert abs(signal.take_profit - signal.entry_reference) == pytest.approx(2 * risk)


def test_hold_conditions():
    signal = TrendMomentumStrategy().evaluate("EURUSD", {"H1": pd.DataFrame(), "M15": pd.DataFrame()})
    assert signal.action is SignalAction.HOLD


def test_confirmation_can_follow_ema20_pullback():
    data = market("BUY")
    data["M15"].loc[69, "low"] = 200.5
    data["M15"].loc[68, "low"] = 190

    signal = TrendMomentumStrategy().evaluate("EURUSD", data)

    assert signal.action is SignalAction.BUY


def test_pullback_outside_lookback_does_not_trigger_entry():
    data = market("BUY")
    data["M15"].loc[67:, "low"] = data["M15"].loc[67:, "close"]

    signal = TrendMomentumStrategy().evaluate("EURUSD", data)

    assert signal.action is SignalAction.HOLD


def test_pullback_lookback_must_be_positive():
    with pytest.raises(ValueError, match="pullback_lookback"):
        TrendMomentumStrategy(pullback_lookback=0)


def test_closed_candle_fetch_excludes_forming_bar(monkeypatch):
    import data_manager
    rates = np.array([(1, 1., 1., 1., 1.)], dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8")])
    copy = Mock(return_value=rates)
    monkeypatch.setattr(data_manager.mt5, "copy_rates_from_pos", copy, raising=False)
    data_manager.DataManager(Mock(), 15, 300).get_closed_candles("EURUSD", 15)
    copy.assert_called_once_with("EURUSD", 15, 1, 300)


def signal():
    return StrategySignal("EURUSD", SignalAction.BUY, pd.Timestamp("2026-01-01", tz="UTC"), 1.1, 1.0, 1.3, "test", "M15", "test")


def manager(calendar_ok=True, position_ok=True, volume_ok=True):
    broker = Mock()
    broker.validate_volume.return_value = VolumeValidation(volume_ok, "EURUSD", .01, .01, .01, 1., .01, "bad" if not volume_ok else "")
    broker.buy.return_value = SimpleNamespace(ok=True, ticket=1)
    risk = Mock(); risk.can_open_symbol.return_value = (position_ok, "owned")
    calendar = Mock(); calendar.can_open_symbol.return_value = (calendar_ok, "news")
    return ExecutionManager(Mock(), broker, risk, calendar, .01, "entry", journal_path="/tmp/aql-test-journal.csv"), broker, risk, calendar


def test_duplicate_signal_suppression():
    execution, broker, _, _ = manager()
    assert execution.process(signal())
    assert not execution.process(signal())
    assert broker.buy.call_count == 1


def test_one_position_per_symbol_rule():
    execution, broker, _, calendar = manager(position_ok=False)
    assert not execution.process(signal())
    calendar.can_open_symbol.assert_not_called()
    broker.validate_volume.assert_not_called()


def test_calendar_blocks_before_volume_preflight():
    execution, broker, _, _ = manager(calendar_ok=False)
    assert not execution.process(signal())
    broker.validate_volume.assert_not_called()


def test_volume_preflight_is_preserved():
    execution, broker, _, _ = manager(volume_ok=False)
    assert not execution.process(signal())
    broker.validate_volume.assert_called_once()
    broker.buy.assert_not_called()


def test_main_does_not_import_legacy_pair_runtime():
    tree = ast.parse(Path("main.py").read_text(encoding="utf-8"))
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
    assert not {"strategy", "PairStrategy", "trade_manager", "TradeManager"} & imports
