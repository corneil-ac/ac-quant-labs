from types import SimpleNamespace
from unittest.mock import Mock
import unittest

from trade_manager import TradeManager


class AdaptiveExitManagerTests(unittest.TestCase):
    def make_manager(self, positions, now=10_000, **overrides):
        broker = Mock()
        broker.pair_positions.return_value = positions
        broker.close_position = Mock()
        defaults = dict(
            logger=Mock(),
            broker=broker,
            risk_manager=Mock(),
            lot_size=0.01,
            profit_target=40.0,
            stop_loss=-20.0,
            entry_comment="entry",
            exit_comment="exit",
            execution_modes={},
            enable_time_exit=True,
            time_exit_hours=6.0,
            time_exit_min_profit=5.0,
            enable_max_hold=True,
            max_hold_hours=24.0,
            min_hold_minutes=30.0,
            now_provider=lambda: now,
        )
        defaults.update(overrides)
        return TradeManager(**defaults), broker

    @staticmethod
    def position(symbol, profit, opened_at):
        return SimpleNamespace(symbol=symbol, profit=profit, time=opened_at)

    def assert_closed_for_reason(self, profit, z, expected_reason, opened_at=0, **overrides):
        positions = [
            self.position("EURUSD", profit / 2, opened_at),
            self.position("GBPUSD", profit / 2, opened_at),
        ]
        manager, broker = self.make_manager(positions, **overrides)

        managed = manager.manage_existing_pair("EURUSD", "GBPUSD", z, {"exit_z": 0.2})

        self.assertTrue(managed)
        self.assertEqual(broker.close_position.call_count, 2)
        exit_log = manager.logger.info.call_args_list[-1].args[0]
        self.assertIn(expected_reason, exit_log)
        self.assertIn("pair=EURUSD/GBPUSD", exit_log)
        self.assertIn("holding=", exit_log)
        self.assertIn("profit=", exit_log)
        self.assertIn("z=", exit_log)
        return exit_log

    def test_stop_loss_priority_precedes_profit_z_and_time_rules(self):
        log = self.assert_closed_for_reason(
            -25.0,
            0.0,
            "reason=stop loss",
            profit_target=-30.0,
            stop_loss=-20.0,
            time_exit_min_profit=-50.0,
        )
        self.assertNotIn("profit target", log)
        self.assertNotIn("mean reversion", log)
        self.assertNotIn("time exit", log)

    def test_profit_target_priority_precedes_mean_reversion_and_time_rules(self):
        log = self.assert_closed_for_reason(
            45.0,
            0.0,
            "reason=profit target",
            profit_target=40.0,
        )
        self.assertNotIn("mean reversion", log)
        self.assertNotIn("time exit", log)

    def test_mean_reversion_priority_precedes_time_and_max_hold_rules(self):
        log = self.assert_closed_for_reason(
            10.0,
            0.1,
            "reason=mean reversion",
            profit_target=40.0,
            time_exit_min_profit=5.0,
            max_hold_hours=1.0,
        )
        self.assertNotIn("time exit", log)
        self.assertNotIn("maximum hold", log)

    def test_time_exit_after_minimum_hold_and_profit_threshold(self):
        self.assert_closed_for_reason(
            6.0,
            1.0,
            "reason=time exit",
            opened_at=10_000 - (6 * 3600),
        )

    def test_minimum_hold_grace_period_blocks_time_exit(self):
        positions = [
            self.position("EURUSD", 3.0, 10_000 - (20 * 60)),
            self.position("GBPUSD", 3.0, 10_000 - (20 * 60)),
        ]
        manager, broker = self.make_manager(
            positions,
            time_exit_hours=0.1,
            min_hold_minutes=30.0,
            max_hold_hours=24.0,
        )

        managed = manager.manage_existing_pair("EURUSD", "GBPUSD", 1.0, {"exit_z": 0.2})

        self.assertTrue(managed)
        broker.close_position.assert_not_called()

    def test_maximum_hold_closes_regardless_of_profit(self):
        self.assert_closed_for_reason(
            -5.0,
            1.0,
            "reason=maximum hold",
            opened_at=10_000 - (24 * 3600),
            stop_loss=-20.0,
            max_hold_hours=24.0,
        )

    def test_holding_duration_uses_oldest_open_pair_position(self):
        newer = self.position("EURUSD", 1.0, 10_000 - 3600)
        older = self.position("GBPUSD", 1.0, 10_000 - 7200)
        manager, broker = self.make_manager(
            [newer, older],
            time_exit_hours=2.0,
            time_exit_min_profit=1.0,
            min_hold_minutes=30.0,
        )

        manager.manage_existing_pair("EURUSD", "GBPUSD", 1.0, {"exit_z": 0.2})

        self.assertEqual(broker.close_position.call_count, 2)
        exit_log = manager.logger.info.call_args_list[-1].args[0]
        self.assertIn("holding=02:00:00", exit_log)
        self.assertIn("reason=time exit", exit_log)


if __name__ == "__main__":
    unittest.main()
