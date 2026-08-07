import importlib
import logging
import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

if "MetaTrader5" not in sys.modules:
    sys.modules["MetaTrader5"] = types.ModuleType("MetaTrader5")

broker_module = importlib.import_module("broker")
from dashboard import show_dashboard
from position_exit_manager import PositionExitManager
from risk_manager import RiskManager


def position(magic, symbol="EURUSD", opened=0, profit=1.25):
    return SimpleNamespace(
        magic=magic, symbol=symbol, time=opened, profit=profit,
        type=0, volume=0.01, ticket=magic,
    )


def exit_manager(positions, *, dry_run=False, now=7200):
    broker = Mock()
    broker.positions.return_value = positions
    broker.dry_run = dry_run
    manager = PositionExitManager(
        Mock(), broker, enable_max_hold=True, max_hold_hours=2,
        exit_comment="exit", now_provider=lambda: now,
    )
    return manager, broker


def test_broker_ignores_manual_and_legacy_positions():
    owned = position(999999)
    manual = position(0)
    legacy = position(123456)
    broker = broker_module.Broker(logging.getLogger(__name__), 999999, 10)
    with patch.object(broker_module.mt5, "positions_get", return_value=(manual, legacy, owned), create=True):
        assert broker.account_positions() == [manual, legacy, owned]
        assert broker.positions() == [owned]


def test_risk_counts_only_current_magic_via_owned_broker_positions():
    broker = Mock()
    broker.positions.return_value = [position(999999)]
    broker.open_symbols.return_value = {"EURUSD"}
    risk = RiskManager(Mock(), broker, 2, 0)
    assert risk.can_open_symbol("GBPUSD") == (True, "ok")
    assert risk.can_open_symbol("EURUSD")[0] is False


def test_closes_at_two_hours_but_not_before():
    manager, broker = exit_manager([position(999999)], now=7200)
    manager.manage_exits()
    broker.close_position.assert_called_once()

    manager, broker = exit_manager([position(999999)], now=7199)
    manager.manage_exits()
    broker.close_position.assert_not_called()


def test_dry_run_logs_exit_details_without_close_order():
    manager, broker = exit_manager([position(999999, profit=-3.5)], dry_run=True)
    manager.manage_exits()
    broker.close_position.assert_not_called()
    message = manager.logger.info.call_args.args[0]
    assert "AUTO EXIT" in message
    assert "Symbol=EURUSD" in message
    assert "Holding duration=02:00:00" in message
    assert "Profit=-3.50" in message
    assert "Reason=Maximum hold exceeded" in message


def test_dashboard_shows_account_and_bullet_counts(capsys):
    broker = Mock()
    broker.account_info.return_value = None
    broker.account_positions.return_value = [position(0), position(1), position(999999)]
    broker.positions.return_value = [position(999999)]
    with patch("dashboard.clear_console"):
        show_dashboard(Mock(), broker, [])
    output = capsys.readouterr().out
    assert "Account Positions : 3" in output
    assert "BULLET Positions  : 1" in output
