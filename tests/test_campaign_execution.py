from datetime import datetime, timezone
from types import SimpleNamespace

import MetaTrader5 as mt5

from campaign_manager import CampaignManager
from execution_manager import ExecutionManager
from strategy_framework import SignalAction, StrategySignal


class Logger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def critical(self, *args, **kwargs):
        pass


class Risk:
    def can_open_symbol(self, symbol, allow_additional_position=False):
        return True, "ok"

    def mark_trade_time(self, symbol):
        pass


class Calendar:
    def can_open_symbol(self, symbol):
        return True, "ok"


class Broker:
    def __init__(self):
        self.positions_store = [
            SimpleNamespace(
                ticket=1,
                symbol="EURUSD",
                type=mt5.POSITION_TYPE_BUY,
                price_open=1.1700,
                volume=0.03,
                profit=-10.0,
            )
        ]

    def validate_volume(self, symbol, volume, allow_normalization):
        return SimpleNamespace(
            requested=volume,
            normalized=volume,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            ok=True,
            deterministic=True,
            reason="ok",
        )

    def buy(self, symbol, volume, comment=None, stop_loss=None, take_profit=None):
        self.positions_store.append(
            SimpleNamespace(
                ticket=2,
                symbol=symbol,
                type=mt5.POSITION_TYPE_BUY,
                price_open=1.1688,
                volume=volume,
                profit=0.0,
            )
        )
        return SimpleNamespace(ok=True, ticket=2)

    def sell(self, *args, **kwargs):
        raise AssertionError("SELL not expected")

    def query_owned_positions(self):
        return True, list(self.positions_store), "ok"


def test_successful_scale_in_journals_campaign_snapshot(tmp_path):
    broker = Broker()
    journal = tmp_path / "journal.csv"
    manager = CampaignManager(Logger())
    execution = ExecutionManager(
        Logger(), broker, Risk(), Calendar(), 0.03, "TEST",
        journal_path=str(journal), campaign_manager=manager,
    )
    signal = StrategySignal(
        symbol="EURUSD",
        action=SignalAction.BUY,
        signal_candle_timestamp=datetime.now(timezone.utc),
        entry_reference=1.1688,
        stop_loss=1.1660,
        take_profit=1.1740,
        strategy_name="TEST",
        timeframe="M15",
        reason="scale-in",
        entry_source="MOMENTUM_CONTINUATION",
        entry_reason="scale-in",
        entry_details={"scale_in_authorized": True},
    )

    assert execution.process(signal) is True
    text = journal.read_text(encoding="utf-8")
    assert '"campaign_after_entry"' in text
    assert '"position_count": 2' in text
    assert '"total_volume": 0.06' in text
    assert '"weighted_entry": 1.1694' in text
