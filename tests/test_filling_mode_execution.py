import importlib
import logging
import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock, patch


if "MetaTrader5" not in sys.modules:
    sys.modules["MetaTrader5"] = types.ModuleType("MetaTrader5")

broker_module = importlib.import_module("broker")


CONSTANTS = {
    "ORDER_FILLING_FOK": 0,
    "ORDER_FILLING_IOC": 1,
    "ORDER_FILLING_RETURN": 2,
    "SYMBOL_FILLING_FOK": 1,
    "SYMBOL_FILLING_IOC": 2,
    "SYMBOL_TRADE_EXECUTION_MARKET": 2,
    "ORDER_TYPE_BUY": 0,
    "ORDER_TYPE_SELL": 1,
    "TRADE_ACTION_DEAL": 1,
    "ORDER_TIME_GTC": 0,
    "TRADE_RETCODE_DONE": 10009,
    "TRADE_RETCODE_INVALID_FILL": 10030,
    "TRADE_RETCODE_PRICE_OFF": 10021,
    "TRADE_RETCODE_MARKET_CLOSED": 10018,
    "TRADE_RETCODE_INVALID_STOPS": 10016,
    "TRADE_RETCODE_INVALID_VOLUME": 10014,
    "TRADE_RETCODE_NO_MONEY": 10019,
    "POSITION_TYPE_BUY": 0,
}


def result(retcode, comment=""):
    return SimpleNamespace(retcode=retcode, comment=comment, order=42)


class TestFillingModeExecution:
    def setup_method(self):
        self.logger = Mock()
        self.broker = broker_module.Broker(self.logger, magic=300040, deviation=10)
        self.info = SimpleNamespace(filling_mode=2, trade_exemode=2)
        self.tick = SimpleNamespace(bid=1.1, ask=1.2)
        self.constant_patches = [
            patch.object(broker_module.mt5, name, value, create=True)
            for name, value in CONSTANTS.items()
        ]
        for active_patch in self.constant_patches:
            active_patch.start()

    def teardown_method(self):
        for active_patch in reversed(self.constant_patches):
            active_patch.stop()

    def execute(self, responses, close=False):
        send = Mock(side_effect=responses)
        position = SimpleNamespace(symbol="EURUSD", volume=0.1, ticket=7, type=0)
        with patch.object(broker_module.mt5, "symbol_info", return_value=self.info, create=True), patch.object(
            broker_module.mt5, "symbol_info_tick", return_value=self.tick, create=True
        ), patch.object(broker_module.mt5, "order_send", send, create=True):
            order = (self.broker.close_position(position, "close") if close else
                     self.broker.buy("EURUSD", 0.1, "entry"))
        return order, send

    def test_capability_mode_succeeds_without_fallback_and_is_cached(self):
        order, send = self.execute([result(10009, "done")])
        assert order.ok
        assert send.call_count == 1
        assert send.call_args.args[0]["type_filling"] == 1
        assert self.broker._successful_filling_modes["EURUSD"] == 1

    def test_cached_mode_is_preferred_on_next_entry(self):
        self.broker._successful_filling_modes["EURUSD"] = 0
        order, send = self.execute([result(10009)])
        assert order.ok
        assert send.call_args.args[0]["type_filling"] == 0

    def test_cached_unsupported_mode_is_invalidated_and_fallback_cached(self):
        self.broker._successful_filling_modes["EURUSD"] = 0
        order, send = self.execute([
            result(10030, "Unsupported filling mode"), result(10009, "done")
        ])
        assert order.ok
        assert [call.args[0]["type_filling"] for call in send.call_args_list] == [0, 1]
        assert self.broker._successful_filling_modes["EURUSD"] == 1
        self.logger.error.assert_not_called()
        assert self.logger.warning.called

    def test_fallback_is_unique_and_bounded(self):
        order, send = self.execute([result(10030, "bad")] * 10)
        attempted = [call.args[0]["type_filling"] for call in send.call_args_list]
        assert not order.ok
        assert attempted == [1, 0]
        assert len(attempted) == len(set(attempted))
        self.logger.error.assert_called_once()

    def test_no_prices_and_market_closed_do_not_cycle_modes(self):
        for retcode, expected in ((10021, "NO_PRICES"), (10018, "MARKET_CLOSED")):
            self.logger.reset_mock()
            order, send = self.execute([result(retcode, expected)])
            assert not order.ok
            assert order.failure_reason == expected
            assert send.call_count == 1

    def test_close_uses_same_selector_and_includes_position(self):
        order, send = self.execute([result(10009)], close=True)
        assert order.ok
        assert send.call_args.args[0]["type_filling"] == 1
        assert send.call_args.args[0]["position"] == 7

    def test_rejection_classifications(self):
        cases = {
            10030: "UNSUPPORTED_FILLING_MODE",
            10021: "NO_PRICES",
            10018: "MARKET_CLOSED",
            10016: "INVALID_STOPS",
            10014: "INVALID_VOLUME",
            10019: "INSUFFICIENT_MARGIN",
            19999: "OTHER_MT5_REJECTION",
        }
        for retcode, classification in cases.items():
            assert self.broker.classify_rejection(retcode) == classification
