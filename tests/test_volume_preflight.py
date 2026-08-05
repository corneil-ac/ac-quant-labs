import importlib
import logging
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


if "MetaTrader5" not in sys.modules:
    sys.modules["MetaTrader5"] = types.ModuleType("MetaTrader5")

broker_module = importlib.import_module("broker")
from trade_manager import TradeManager


class BrokerVolumeValidationTests(unittest.TestCase):
    def setUp(self):
        self.broker = broker_module.Broker(logging.getLogger(__name__), 1, 10)

    def test_rejects_invalid_step_without_explicit_normalization(self):
        info = SimpleNamespace(volume_min=0.01, volume_max=10.0, volume_step=0.01)
        with patch.object(broker_module.mt5, "symbol_select", return_value=True, create=True), patch.object(
            broker_module.mt5, "symbol_info", return_value=info, create=True
        ):
            result = self.broker.validate_volume("EURUSD", 0.015)

        self.assertFalse(result.ok)
        self.assertEqual(result.normalized, 0.02)
        self.assertEqual((result.volume_min, result.volume_max, result.volume_step), (0.01, 10.0, 0.01))

    def test_normalizes_only_when_explicitly_allowed(self):
        info = SimpleNamespace(volume_min=0.1, volume_max=2.0, volume_step=0.1)
        with patch.object(broker_module.mt5, "symbol_select", return_value=True, create=True), patch.object(
            broker_module.mt5, "symbol_info", return_value=info, create=True
        ):
            result = self.broker.validate_volume("XAUUSD", 0.16, allow_normalization=True)

        self.assertTrue(result.ok)
        self.assertEqual(result.normalized, 0.2)


class TradeManagerPreflightTests(unittest.TestCase):
    def make_manager(self, broker):
        risk = Mock()
        risk.can_open_pair.return_value = (True, "")
        manager = TradeManager(
            logger=Mock(), broker=broker, risk_manager=risk, lot_size=0.01,
            profit_target=10, stop_loss=-10, entry_comment="entry",
            exit_comment="exit", execution_modes={},
        )
        return manager

    @staticmethod
    def signal():
        return SimpleNamespace(
            symbol1="EURUSD", symbol2="GBPUSD", action="LONG",
            profile_name="test", threshold_used=1.0, z=-2.0, beta=1.0,
        )

    def test_invalid_second_leg_prevents_first_order_and_future_retries(self):
        broker = Mock()
        valid = broker_module.VolumeValidation(True, "EURUSD", 0.01, 0.01, 0.01, 10.0, 0.01)
        invalid = broker_module.VolumeValidation(False, "GBPUSD", 0.01, 0.1, 0.1, 10.0, 0.1, "invalid")
        broker.validate_volume.side_effect = [valid, invalid]
        manager = self.make_manager(broker)

        manager.open_pair(self.signal())
        manager.open_pair(self.signal())

        self.assertEqual(broker.validate_volume.call_count, 2)
        broker.buy.assert_not_called()
        broker.sell.assert_not_called()

    def test_both_legs_use_preflighted_normalized_volumes(self):
        broker = Mock()
        broker.validate_volume.side_effect = [
            broker_module.VolumeValidation(True, "EURUSD", 0.01, 0.1, 0.1, 10.0, 0.1),
            broker_module.VolumeValidation(True, "GBPUSD", 0.01, 0.2, 0.2, 10.0, 0.2),
        ]
        broker.buy.return_value = SimpleNamespace(ok=True)
        broker.sell.return_value = SimpleNamespace(ok=True)
        manager = self.make_manager(broker)

        manager.open_pair(self.signal())

        broker.buy.assert_called_once_with("EURUSD", 0.1, comment="entry")
        broker.sell.assert_called_once_with("GBPUSD", 0.2, comment="entry")

    def test_second_order_failure_keeps_emergency_close_safeguard(self):
        broker = Mock()
        valid_first = broker_module.VolumeValidation(True, "EURUSD", 0.01, 0.01, 0.01, 10.0, 0.01)
        valid_second = broker_module.VolumeValidation(True, "GBPUSD", 0.01, 0.01, 0.01, 10.0, 0.01)
        broker.validate_volume.side_effect = [valid_first, valid_second]
        broker.buy.return_value = SimpleNamespace(ok=True)
        broker.sell.return_value = SimpleNamespace(ok=False)
        manager = self.make_manager(broker)
        manager._close_newest_position_for_symbol = Mock()

        manager.open_pair(self.signal())

        manager._close_newest_position_for_symbol.assert_called_once_with("EURUSD")


if __name__ == "__main__":
    unittest.main()
