import logging
from unittest.mock import Mock

import pytest

pd = pytest.importorskip("pandas")
import main


def test_data_failure_skips_strategy_and_is_not_reported_as_hold(monkeypatch, caplog):
    monkeypatch.setattr(main.config, "SYMBOLS", ["EURUSD", "GBPUSD"])
    monkeypatch.setattr(main.config, "DATA_FEED_OUTAGE_THRESHOLD", 2)
    monkeypatch.setattr(main, "show_dashboard", Mock())
    monkeypatch.setattr(main.MaximumHoldManager, "expire_positions", Mock(return_value=set()))
    data = Mock()
    data.get_closed_candles.return_value = pd.DataFrame()
    strategy, execution = Mock(), Mock()
    broker = Mock()
    broker.positions.return_value = []
    logger = logging.getLogger("runtime-feed-test")

    with caplog.at_level(logging.INFO, logger="runtime-feed-test"):
        main.run_scan(logger, broker, data, strategy, Mock(), execution)

    data.begin_scan.assert_called_once_with()
    strategy.evaluate.assert_not_called()
    execution.process.assert_not_called()
    assert caplog.text.count("DATA UNAVAILABLE / DATA FEED FAILURE") == 2
    assert "PROBABLE MT5/DATA-FEED OUTAGE" in caplog.text
    assert "STRATEGY HOLD" not in caplog.text
