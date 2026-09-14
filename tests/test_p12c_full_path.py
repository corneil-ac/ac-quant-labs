from types import SimpleNamespace

import MetaTrader5 as mt5

from campaign_exit_manager import CampaignExitManager
from campaign_manager import CampaignManager


class Logger:
    def info(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass
    def critical(self, *args, **kwargs): pass


class SimBroker:
    """In-memory broker used to prove P1.2C without touching MT5."""

    def __init__(self, fail_ticket=None):
        self.fail_ticket = fail_ticket
        self.positions_store = []
        self.close_attempts = []

    def add_buy(self, ticket, entry, profit, volume=0.03):
        self.positions_store.append(SimpleNamespace(
            ticket=ticket,
            symbol="EURUSD",
            type=mt5.POSITION_TYPE_BUY,
            price_open=entry,
            volume=volume,
            profit=profit,
        ))

    def close_position(self, position, comment):
        self.close_attempts.append(position.ticket)
        if position.ticket == self.fail_ticket:
            return SimpleNamespace(ok=False)
        self.positions_store = [p for p in self.positions_store if p.ticket != position.ticket]
        return SimpleNamespace(ok=True)

    def query_owned_positions(self):
        return True, list(self.positions_store), "ok"


class SafeModeState:
    def __init__(self):
        self.safe_mode = False
        self.reason = ""

    def set_safe_mode(self, enabled, reason=""):
        self.safe_mode = bool(enabled)
        self.reason = reason


def build_exit(broker):
    logger = Logger()
    campaigns = CampaignManager(logger)
    return campaigns, CampaignExitManager(
        logger,
        broker,
        campaigns,
        enabled=True,
        profit_target=40.0,
        stop_loss=-20.0,
    )


def test_full_path_profit_exit_leaves_zero_campaign_positions():
    broker = SimBroker()

    # Entry #1 then Entry #2: same-size scale-in campaign.
    broker.add_buy(1001, 1.1700, 22.0)
    broker.add_buy(1002, 1.1688, 19.0)

    campaigns, exit_manager = build_exit(broker)
    before = campaigns.snapshot("EURUSD", broker.positions_store)
    assert before.position_count == 2
    assert before.total_volume == 0.06
    assert before.weighted_entry == pytest.approx(1.1694)
    assert before.combined_profit == 41.0

    result = exit_manager.process_symbol("EURUSD", broker.positions_store)
    assert result.triggered is True
    assert result.complete is True
    assert result.closed_tickets == (1001, 1002)
    assert broker.close_attempts == [1001, 1002]

    ok, remaining, reason = broker.query_owned_positions()
    assert ok is True
    assert reason == "ok"
    assert remaining == []
    assert campaigns.snapshot("EURUSD", remaining) is None


def test_full_path_partial_failure_enters_safe_mode_and_preserves_survivor():
    broker = SimBroker(fail_ticket=1002)
    broker.add_buy(1001, 1.1700, 22.0)
    broker.add_buy(1002, 1.1688, 19.0)

    campaigns, exit_manager = build_exit(broker)
    safety = SafeModeState()

    result = exit_manager.process_symbol("EURUSD", broker.positions_store)
    if result.triggered and not result.complete:
        safety.set_safe_mode(
            True,
            f"campaign exit incomplete for EURUSD; failed_tickets={list(result.failed_tickets)}",
        )

    assert result.triggered is True
    assert result.complete is False
    assert result.closed_tickets == (1001,)
    assert result.failed_tickets == (1002,)
    assert safety.safe_mode is True
    assert "1002" in safety.reason

    ok, remaining, _ = broker.query_owned_positions()
    assert ok is True
    assert [p.ticket for p in remaining] == [1002]
    survivor = campaigns.snapshot("EURUSD", remaining)
    assert survivor is not None
    assert survivor.position_count == 1
    assert survivor.tickets == (1002,)


# pytest is intentionally imported last to keep the simulation dependencies obvious.
import pytest
