from types import SimpleNamespace

import MetaTrader5 as mt5

from campaign_exit_manager import CampaignExitManager
from campaign_manager import CampaignManager


class Logger:
    def info(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass


class Broker:
    def __init__(self, fail_ticket=None):
        self.fail_ticket = fail_ticket
        self.closed = []

    def close_position(self, position, comment):
        ok = position.ticket != self.fail_ticket
        if ok:
            self.closed.append(position.ticket)
        return SimpleNamespace(ok=ok)


def position(ticket, profit, entry=1.1700, volume=0.03):
    return SimpleNamespace(
        ticket=ticket, symbol="EURUSD", type=mt5.POSITION_TYPE_BUY,
        price_open=entry, volume=volume, profit=profit,
    )


def manager(broker, enabled=True):
    logger = Logger()
    campaigns = CampaignManager(logger)
    return CampaignExitManager(
        logger, broker, campaigns, enabled=enabled,
        profit_target=40.0, stop_loss=-20.0,
    )


def test_profit_target_closes_both_campaign_tickets():
    broker = Broker()
    result = manager(broker).process_symbol(
        "EURUSD", [position(1, 25.0), position(2, 16.0, entry=1.1688)]
    )
    assert result.triggered is True
    assert result.complete is True
    assert result.closed_tickets == (1, 2)
    assert broker.closed == [1, 2]


def test_combined_stop_closes_both_campaign_tickets():
    broker = Broker()
    result = manager(broker).process_symbol(
        "EURUSD", [position(1, -12.0), position(2, -9.0, entry=1.1688)]
    )
    assert result.triggered is True
    assert result.complete is True
    assert result.closed_tickets == (1, 2)


def test_inside_exit_band_does_not_close_campaign():
    broker = Broker()
    result = manager(broker).process_symbol(
        "EURUSD", [position(1, 5.0), position(2, 4.0, entry=1.1688)]
    )
    assert result.triggered is False
    assert broker.closed == []


def test_single_position_is_not_managed_as_campaign_exit():
    broker = Broker()
    result = manager(broker).process_symbol("EURUSD", [position(1, 50.0)])
    assert result.triggered is False
    assert broker.closed == []


def test_disabled_manager_never_closes():
    broker = Broker()
    result = manager(broker, enabled=False).process_symbol(
        "EURUSD", [position(1, 30.0), position(2, 20.0)]
    )
    assert result.triggered is False
    assert broker.closed == []


def test_partial_close_failure_is_explicit():
    broker = Broker(fail_ticket=2)
    result = manager(broker).process_symbol(
        "EURUSD", [position(1, 25.0), position(2, 16.0, entry=1.1688)]
    )
    assert result.triggered is True
    assert result.complete is False
    assert result.closed_tickets == (1,)
    assert result.failed_tickets == (2,)
