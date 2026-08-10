import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("pandas")
import data_manager


def rates():
    return np.array(
        [(1, 1.0, 1.1, 0.9, 1.05)],
        dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"),
               ("low", "f8"), ("close", "f8")],
    )


def manager(logger=None, retries=3):
    return data_manager.DataManager(
        logger or Mock(), 15, 300, fetch_retries=retries,
        retry_seconds=0, recovery_wait_seconds=0,
    )


def healthy_mt5(monkeypatch, copy_side_effect):
    monkeypatch.setattr(data_manager.mt5, "copy_rates_from_pos", Mock(side_effect=copy_side_effect))
    monkeypatch.setattr(data_manager.mt5, "last_error", Mock(return_value=(-1, "feed stale")))
    monkeypatch.setattr(data_manager.mt5, "terminal_info", Mock(return_value=SimpleNamespace(connected=True)))
    monkeypatch.setattr(data_manager.mt5, "account_info", Mock(return_value=SimpleNamespace(login=1)))
    monkeypatch.setattr(data_manager.mt5, "shutdown", Mock())
    monkeypatch.setattr(data_manager.mt5, "initialize", Mock(return_value=True))
    monkeypatch.setattr(data_manager.mt5, "symbol_select", Mock(return_value=True))


def test_successful_fetch_needs_no_recovery(monkeypatch):
    healthy_mt5(monkeypatch, [rates()])
    result = manager().get_closed_candles("EURUSD", 15)
    assert not result.empty
    data_manager.mt5.shutdown.assert_not_called()


def test_none_then_success_retries_without_recovery(monkeypatch):
    healthy_mt5(monkeypatch, [None, rates()])
    result = manager().get_closed_candles("EURUSD", 15)
    assert not result.empty
    assert data_manager.mt5.copy_rates_from_pos.call_count == 2
    data_manager.mt5.shutdown.assert_not_called()


def test_repeated_none_recovers_once_and_reselects_symbol(monkeypatch):
    healthy_mt5(monkeypatch, [None, None, None, rates()])
    result = manager().get_closed_candles("EURUSD", 15)
    assert not result.empty
    data_manager.mt5.shutdown.assert_called_once_with()
    data_manager.mt5.initialize.assert_called_once_with()
    data_manager.mt5.symbol_select.assert_called_once_with("EURUSD", True)


def test_failed_recovery_is_safe_and_bounded(monkeypatch):
    healthy_mt5(monkeypatch, [None, None, None])
    data_manager.mt5.initialize.return_value = False
    result = manager().get_closed_candles("EURUSD", 15)
    assert result.empty
    assert data_manager.mt5.copy_rates_from_pos.call_count == 3
    data_manager.mt5.shutdown.assert_called_once_with()


def test_malformed_and_empty_data_are_retried_safely(monkeypatch):
    malformed = np.array([(1, 1.0)], dtype=[("time", "i8"), ("close", "f8")])
    healthy_mt5(monkeypatch, [[], malformed, rates()])
    result = manager().get_closed_candles("EURUSD", 15)
    assert not result.empty
    assert data_manager.mt5.copy_rates_from_pos.call_count == 3


def test_last_error_and_disconnected_terminal_are_logged(monkeypatch, caplog):
    healthy_mt5(monkeypatch, [None])
    data_manager.mt5.terminal_info.return_value = SimpleNamespace(connected=False)
    data_manager.mt5.initialize.return_value = False
    logger = logging.getLogger("watchdog-test")
    with caplog.at_level(logging.WARNING, logger="watchdog-test"):
        assert manager(logger, retries=1).get_closed_candles("EURUSD", 15).empty
    assert "feed stale" in caplog.text
    assert "connected=False" in caplog.text


def test_only_one_recovery_is_allowed_for_multiple_failures_in_scan(monkeypatch):
    healthy_mt5(monkeypatch, [None] * 20)
    dm = manager(retries=1)
    assert dm.get_closed_candles("EURUSD", 15).empty
    assert dm.get_closed_candles("GBPUSD", 15).empty
    assert dm.get_closed_candles("USDJPY", 60).empty
    data_manager.mt5.shutdown.assert_called_once_with()
