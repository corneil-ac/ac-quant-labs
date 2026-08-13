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
    return pd.DataFrame(
        {
            "time": np.arange(len(values)),
            "open": values,
            "high": values + 0.2,
            "low": values - 0.2,
            "close": values,
        }
    )


def _market(direction):
    if direction == "BUY":
        h1 = _candles(np.linspace(100, 200, 220))
        m15 = _candles(np.linspace(150, 200, 70))

        # Recent EMA20 pullback followed by bullish confirmation
        m15.loc[68, "low"] = 190
        m15.loc[69, ["open", "high", "low", "close"]] = [198, 202, 197, 201]

    else:
        h1 = _candles(np.linspace(200, 100, 220))
        m15 = _candles(np.linspace(150, 100, 70))

        # Recent EMA20 pullback followed by bearish confirmation
        m15.loc[68, "high"] = 110
        m15.loc[69, ["open", "high", "low", "close"]] = [102, 103, 98, 99]

    return {"H1": h1, "M15": m15}


def _config(selected, enabled=True):
    cfg = {name: {"enabled": False} for name in MODULES}
    settings = {
        "EMA20_PULLBACK": {"pullback_lookback": 3},
        "NEAR_EMA": {"max_distance_atr": 100, "min_rsi": 0, "max_rsi": 100},
        "MOMENTUM_CONTINUATION": {
            "min_rsi": 0,
            "max_rsi": 100,
            "min_ema_slope_atr": -100,
            "slope_lookback": 3,
        },
        "BREAKOUT_CONTINUATION": {
            "breakout_lookback": 10,
            "min_rsi": 0,
            "max_rsi": 100,
            "min_breakout_atr": 0,
        },
        "STRONG_TREND_CONTINUATION": {
            "min_adx": 0,
            "min_rsi": 0,
            "max_rsi": 100,
            "min_ema_slope_atr": -100,
            "slope_lookback": 3,
            "sustained_bars": 3,
        },
    }[selected]
    cfg[selected] = {"enabled": enabled, **settings}
    return cfg


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize("direction", ("BUY", "SELL"))
def test_each_entry_module_selects_buy_and_sell(module, direction):
    signal = TrendMomentumStrategy(multi_entry_config=_config(module)).evaluate(
        "EURUSD", _market(direction)
    )
    assert signal.action is SignalAction(direction)
    assert signal.entry_source == module
    assert signal.entry_reason
    assert signal.entry_details["module_results"][module]["status"] == "PASS"


@pytest.mark.parametrize("module", MODULES)
def test_each_module_has_a_non_qualifying_case(module):
    flat = {"H1": _candles(np.ones(220) * 100), "M15": _candles(np.ones(70) * 100)}
    signal = TrendMomentumStrategy(multi_entry_config=_config(module)).evaluate(
        "EURUSD", flat
    )
    assert signal.action is SignalAction.HOLD
    assert signal.entry_details["module_results"][module]["status"] == "FAIL"


def test_disabled_module_cannot_trigger():
    signal = TrendMomentumStrategy(
        multi_entry_config=_config("EMA20_PULLBACK", False)
    ).evaluate("EURUSD", _market("BUY"))
    assert signal.action is SignalAction.HOLD
    assert (
        signal.entry_details["module_results"]["EMA20_PULLBACK"]["status"] == "DISABLED"
    )


def test_priority_is_deterministic_and_only_one_signal_is_returned():
    cfg = _config("EMA20_PULLBACK")
    cfg["NEAR_EMA"] = {
        "enabled": True,
        "max_distance_atr": 100,
        "min_rsi": 0,
        "max_rsi": 100,
    }
    signal = TrendMomentumStrategy(multi_entry_config=cfg).evaluate(
        "EURUSD", _market("BUY")
    )
    assert signal.entry_source == "EMA20_PULLBACK"
    assert signal.entry_details["module_results"]["EMA20_PULLBACK"]["status"] == "PASS"
    assert signal.entry_details["module_results"]["NEAR_EMA"]["status"] == "PASS"
    assert isinstance(signal.action, SignalAction)


def test_h1_disagreement_blocks_all_modules():
    data = _market("BUY")
    data["H1"] = _candles(np.linspace(200, 100, 220))
    signal = TrendMomentumStrategy(multi_entry_config=_config("NEAR_EMA")).evaluate(
        "EURUSD", data
    )
    assert signal.action is SignalAction.HOLD
    assert "not aligned" in signal.reason


def test_m15_directional_disagreement_blocks_all_modules():
    data = _market("BUY")
    data["M15"] = _candles(np.linspace(200, 150, 70))
    signal = TrendMomentumStrategy(multi_entry_config=_config("NEAR_EMA")).evaluate(
        "EURUSD", data
    )
    assert signal.action is SignalAction.HOLD
    assert "not aligned" in signal.reason
