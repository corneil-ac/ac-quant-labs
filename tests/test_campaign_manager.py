from types import SimpleNamespace

import MetaTrader5 as mt5
import pytest

from campaign_manager import CampaignManager


class Logger:
    def warning(self, *args, **kwargs):
        pass


def position(ticket, side, entry, volume=0.03, profit=0.0, symbol="EURUSD"):
    return SimpleNamespace(
        ticket=ticket,
        symbol=symbol,
        type=side,
        price_open=entry,
        volume=volume,
        profit=profit,
    )


def test_single_position_campaign_snapshot():
    manager = CampaignManager(Logger())
    snap = manager.snapshot(
        "EURUSD",
        [position(1, mt5.POSITION_TYPE_BUY, 1.1700, volume=0.03, profit=12.5)],
    )

    assert snap is not None
    assert snap.valid is True
    assert snap.direction == "BUY"
    assert snap.position_count == 1
    assert snap.total_volume == pytest.approx(0.03)
    assert snap.weighted_entry == pytest.approx(1.1700)
    assert snap.combined_profit == pytest.approx(12.5)


def test_two_equal_volume_positions_use_simple_weighted_average():
    manager = CampaignManager(Logger())
    snap = manager.snapshot(
        "EURUSD",
        [
            position(1, mt5.POSITION_TYPE_BUY, 1.1700, volume=0.03, profit=-20.0),
            position(2, mt5.POSITION_TYPE_BUY, 1.1688, volume=0.03, profit=5.0),
        ],
    )

    assert snap is not None
    assert snap.position_count == 2
    assert snap.total_volume == pytest.approx(0.06)
    assert snap.weighted_entry == pytest.approx(1.1694)
    assert snap.combined_profit == pytest.approx(-15.0)
    assert snap.tickets == (1, 2)


def test_unequal_volume_positions_use_true_volume_weighting():
    manager = CampaignManager(Logger())
    snap = manager.snapshot(
        "EURUSD",
        [
            position(1, mt5.POSITION_TYPE_SELL, 1.2000, volume=0.02),
            position(2, mt5.POSITION_TYPE_SELL, 1.1900, volume=0.04),
        ],
    )

    assert snap is not None
    expected = ((1.2000 * 0.02) + (1.1900 * 0.04)) / 0.06
    assert snap.direction == "SELL"
    assert snap.weighted_entry == pytest.approx(expected)
    assert snap.total_volume == pytest.approx(0.06)


def test_snapshot_ignores_other_symbols():
    manager = CampaignManager(Logger())
    snap = manager.snapshot(
        "EURUSD",
        [
            position(1, mt5.POSITION_TYPE_BUY, 1.1000, symbol="EURUSD"),
            position(2, mt5.POSITION_TYPE_SELL, 2000.0, symbol="XAUUSD"),
        ],
    )

    assert snap is not None
    assert snap.position_count == 1
    assert snap.tickets == (1,)
    assert snap.direction == "BUY"


def test_mixed_direction_campaign_is_invalid():
    manager = CampaignManager(Logger())
    snap = manager.snapshot(
        "EURUSD",
        [
            position(1, mt5.POSITION_TYPE_BUY, 1.1000),
            position(2, mt5.POSITION_TYPE_SELL, 1.1010),
        ],
    )

    assert snap is not None
    assert snap.valid is False
    assert snap.direction == "MIXED"
    assert "mixed" in snap.reason


def test_no_positions_returns_none():
    manager = CampaignManager(Logger())
    assert manager.snapshot("EURUSD", []) is None
