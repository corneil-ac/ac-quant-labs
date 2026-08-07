from types import SimpleNamespace
from unittest.mock import Mock

import config
from maximum_hold_manager import MaximumHoldManager, process_entry_unless_expired


NOW = 2_000_000_000.0
MAGIC = config.MAGIC


def position(age_seconds, magic=MAGIC, symbol="EURUSD", ticket=1):
    return SimpleNamespace(
        symbol=symbol, magic=magic, time=NOW - age_seconds, ticket=ticket,
    )


def manager(positions, dry_run=False):
    broker = Mock(magic=MAGIC, dry_run=dry_run)
    broker.positions.return_value = positions
    broker.close_position.return_value = SimpleNamespace(ok=True)
    return MaximumHoldManager(Mock(), broker, config.MAX_HOLD_HOURS), broker


def test_maximum_hold_configuration_is_two_hours():
    assert config.ENABLE_MAX_HOLD is True
    assert config.MAX_HOLD_HOURS == 2.0


def test_position_at_exactly_two_hours_closes():
    hold_manager, broker = manager([position(2 * 3600)])

    assert hold_manager.expire_positions(NOW) == {"EURUSD"}
    broker.close_position.assert_called_once()


def test_position_older_than_two_hours_closes():
    hold_manager, broker = manager([position(2 * 3600 + 1)])

    assert hold_manager.expire_positions(NOW) == {"EURUSD"}
    broker.close_position.assert_called_once()


def test_position_at_one_hour_fifty_nine_minutes_remains_open():
    hold_manager, broker = manager([position(1 * 3600 + 59 * 60)])

    assert hold_manager.expire_positions(NOW) == set()
    broker.close_position.assert_not_called()


def test_foreign_magic_number_is_ignored():
    hold_manager, broker = manager([position(3 * 3600, magic=MAGIC + 1)])

    assert hold_manager.expire_positions(NOW) == set()
    broker.close_position.assert_not_called()


def test_dry_run_does_not_close():
    hold_manager, broker = manager([position(3 * 3600)], dry_run=True)

    assert hold_manager.expire_positions(NOW) == {"EURUSD"}
    broker.close_position.assert_not_called()


def test_no_same_scan_reentry_after_forced_expiration():
    hold_manager, broker = manager([position(2 * 3600)])
    execution = Mock()
    signal = SimpleNamespace(symbol="EURUSD")

    expired_symbols = hold_manager.expire_positions(NOW)
    opened = process_entry_unless_expired(execution, signal, expired_symbols)

    assert opened is False
    broker.close_position.assert_called_once()
    execution.process.assert_not_called()
