from types import SimpleNamespace

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

from strategy_framework import SignalAction
from trend_momentum_strategy import TrendMomentumStrategy


MODULES = (
    "EMA20_PULLBACK",
    "NEAR_EMA",
    "MOMENTUM_CONTINUATION",
    "BREAKOUT_CONTINUATION",
    "STRONG_TREND_CONTINUATION",
)


def _candles(values):
    values = np.asarray(values, dtype=float)
    return pd.DataFrame({
        "time": np.arange(len(values)),
        "open": values,
        "high": values + 0.2,
        "low": values - 0.2,
        "close": values,
    })


def _market():
    h1 = _candles(np.linspace(100, 200, 220))
    m15 = _candles(np.linspace(150, 200, 70))
    m15.loc[68, "low"] = 190
    m15.loc[69, ["open", "high", "low", "close"]] = [198, 202, 197, 201]
    return {"H1": h1, "M15": m15}


def _config():
    return {
        "EMA20_PULLBACK": {"enabled": True, "pullback_lookback": 3},
        "NEAR_EMA": {"enabled": True, "max_distance_atr": 100, "min_rsi": 0, "max_rsi": 100},
        "MOMENTUM_CONTINUATION": {"enabled": True, "min_rsi": 0, "max_rsi": 100, "min_ema_slope_atr": -100, "slope_lookback": 3},
        "BREAKOUT_CONTINUATION": {"enabled": True, "breakout_lookback": 10, "min_rsi": 0, "max_rsi": 100, "min_breakout_atr": 0},
        "STRONG_TREND_CONTINUATION": {"enabled": True, "min_adx": 0, "min_rsi": 0, "max_rsi": 100, "min_ema_slope_atr": -100, "slope_lookback": 3, "sustained_bars": 3},
    }


def _strategy(regime, rules, enabled=True):
    strategy = TrendMomentumStrategy(
        multi_entry_config=_config(),
        enable_regime_gating=enabled,
        regime_entry_rules=rules,
    )
    strategy.regime_detector = SimpleNamespace(
        classify=lambda _m15: SimpleNamespace(
            regime=SimpleNamespace(value=regime),
            metrics={"stub": True},
            reason=f"stub {regime}",
        )
    )
    return strategy


def test_strong_trend_preserves_entry_priority_when_all_modules_allowed():
    rules = {"STRONG_TREND": set(MODULES)}
    signal = _strategy("STRONG_TREND", rules).evaluate("EURUSD", _market())
    assert signal.action is SignalAction.BUY
    assert signal.entry_source == "EMA20_PULLBACK"
    assert signal.entry_details["module_results"]["EMA20_PULLBACK"]["status"] == "PASS"


def test_regime_blocks_incompatible_module_but_allows_compatible_module():
    rules = {"WEAK_TREND": {"NEAR_EMA"}}
    signal = _strategy("WEAK_TREND", rules).evaluate("EURUSD", _market())
    assert signal.action is SignalAction.BUY
    assert signal.entry_source == "NEAR_EMA"
    assert signal.entry_details["module_results"]["EMA20_PULLBACK"]["status"] == "BLOCKED_REGIME"


def test_unstable_regime_blocks_all_new_entries():
    rules = {"UNSTABLE": set()}
    signal = _strategy("UNSTABLE", rules).evaluate("EURUSD", _market())
    assert signal.action is SignalAction.HOLD
    assert all(
        result["status"] in {"BLOCKED_REGIME", "DISABLED"}
        for result in signal.entry_details["module_results"].values()
    )
    assert "regime UNSTABLE blocked" in signal.reason


def test_missing_regime_rule_falls_back_to_existing_behavior():
    signal = _strategy("UNKNOWN_REGIME", {}).evaluate("EURUSD", _market())
    assert signal.action is SignalAction.BUY
    assert signal.entry_source == "EMA20_PULLBACK"


def test_gating_can_be_disabled_for_safe_fallback():
    rules = {"UNSTABLE": set()}
    signal = _strategy("UNSTABLE", rules, enabled=False).evaluate("EURUSD", _market())
    assert signal.action is SignalAction.BUY
    assert signal.entry_source == "EMA20_PULLBACK"
