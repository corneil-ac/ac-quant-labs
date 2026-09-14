from types import SimpleNamespace

import MetaTrader5 as mt5
import pytest

from scale_in_manager import ScaleInManager
from strategy_framework import SignalAction, StrategySignal


class Logger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass


def signal(action=SignalAction.BUY, price=99.0, atr=1.0, adx=30.0):
    return StrategySignal(
        symbol="EURUSD",
        action=action,
        signal_candle_timestamp=None,
        entry_reference=price,
        stop_loss=95.0,
        take_profit=105.0,
        strategy_name="TEST",
        timeframe="M15",
        reason="trend remains valid",
        entry_source="MOMENTUM_CONTINUATION",
        entry_reason="trend remains valid",
        entry_details={"atr": atr, "adx": adx},
    )


def position(ticket=1, side=mt5.POSITION_TYPE_BUY, entry=100.0):
    return SimpleNamespace(
        ticket=ticket,
        symbol="EURUSD",
        type=side,
        price_open=entry,
        volume=0.03,
    )


def test_authorizes_second_buy_after_adverse_atr_move():
    manager = ScaleInManager(Logger(), min_adverse_atr=1.0, min_adx=20.0)
    result = manager.authorize(signal(price=98.8, atr=1.0, adx=30.0), [position(entry=100.0)])

    assert result.entry_details["scale_in_authorized"] is True
    assert result.entry_details["scale_in_adverse_atr"] == pytest.approx(1.2)
    assert result.entry_details["scale_in_position_count_before"] == 1
    assert "scale-in authorized" in result.reason


def test_does_not_authorize_before_adverse_trigger():
    manager = ScaleInManager(Logger(), min_adverse_atr=1.0, min_adx=20.0)
    result = manager.authorize(signal(price=99.4, atr=1.0, adx=30.0), [position(entry=100.0)])

    assert result.entry_details.get("scale_in_authorized") is not True


def test_does_not_authorize_when_strategy_reverses_direction():
    manager = ScaleInManager(Logger(), min_adverse_atr=1.0, min_adx=20.0)
    result = manager.authorize(
        signal(action=SignalAction.SELL, price=101.5, atr=1.0, adx=30.0),
        [position(side=mt5.POSITION_TYPE_BUY, entry=100.0)],
    )

    assert result.entry_details.get("scale_in_authorized") is not True


def test_does_not_authorize_when_two_positions_already_exist():
    manager = ScaleInManager(Logger(), max_entries_per_symbol=2, min_adverse_atr=1.0)
    result = manager.authorize(
        signal(price=98.0),
        [position(ticket=1, entry=100.0), position(ticket=2, entry=99.0)],
    )

    assert result.entry_details.get("scale_in_authorized") is not True


def test_does_not_authorize_weak_trend():
    manager = ScaleInManager(Logger(), min_adverse_atr=1.0, min_adx=25.0)
    result = manager.authorize(signal(price=98.0, atr=1.0, adx=18.0), [position(entry=100.0)])

    assert result.entry_details.get("scale_in_authorized") is not True


def test_sell_scale_in_uses_inverse_adverse_distance():
    manager = ScaleInManager(Logger(), min_adverse_atr=1.0, min_adx=20.0)
    result = manager.authorize(
        signal(action=SignalAction.SELL, price=102.0, atr=1.0, adx=30.0),
        [position(side=mt5.POSITION_TYPE_SELL, entry=100.0)],
    )

    assert result.entry_details["scale_in_authorized"] is True
    assert result.entry_details["scale_in_adverse_atr"] == 2.0
