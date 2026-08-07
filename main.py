from __future__ import annotations

import time

import MetaTrader5 as mt5

import config
from broker import Broker
from calendar_filter import CalendarFilter
from calendar_provider import CalendarProvider
from dashboard import show_dashboard
from data_manager import DataManager
from execution_manager import ExecutionManager
from logger_setup import setup_logger
from maximum_hold_manager import MaximumHoldManager, process_entry_unless_expired
from risk_manager import RiskManager
from strategy_diagnostics import diagnose_trend_momentum
from strategy_framework import strategy_registry
import trend_momentum_strategy  # noqa: F401 - registers the configured strategy


TIMEFRAMES = {"M15": mt5.TIMEFRAME_M15, "H1": mt5.TIMEFRAME_H1}


def build_runtime(logger):
    broker = Broker(logger, config.MAGIC, config.DEVIATION, config.DRY_RUN)
    data = DataManager(logger, TIMEFRAMES["M15"], config.HISTORY_BARS)
    strategy = strategy_registry.create(config.ACTIVE_STRATEGY)
    provider = CalendarProvider(
        logger, config.CALENDAR_URL, config.CALENDAR_CACHE_PATH,
        config.CALENDAR_REFRESH_HOURS,
    )
    calendar = CalendarFilter(
        provider, config.CALENDAR_BLACKOUT_MINUTES_BEFORE,
        config.CALENDAR_BLACKOUT_MINUTES_AFTER, config.CALENDAR_BLOCKED_IMPACTS,
    )
    risk = RiskManager(logger, broker, config.MAX_OPEN_POSITIONS, config.COOLDOWN_MINUTES)
    execution = ExecutionManager(
        logger, broker, risk, calendar, config.FIXED_VOLUME,
        config.ORDER_COMMENT_ENTRY, config.ALLOW_VOLUME_NORMALIZATION,
        config.TRADE_JOURNAL_PATH,
    )
    return broker, data, strategy, provider, execution


def run_scan(logger, broker, data, strategy, calendar_provider, execution):
    snapshots = []
    calendar_provider.refresh()
    expired_symbols = MaximumHoldManager(
        logger, broker, config.MAX_HOLD_HOURS, config.ENABLE_MAX_HOLD
    ).expire_positions()
    for symbol in config.SYMBOLS:
        candles = {
            "H1": data.get_closed_candles(symbol, TIMEFRAMES["H1"]),
            "M15": data.get_closed_candles(symbol, TIMEFRAMES["M15"]),
        }
        signal = strategy.evaluate(symbol, candles)
        diagnostics = diagnose_trend_momentum(
            signal,
            candles,
            strategy.trend_ema_period,
            strategy.fast_ema_period,
            strategy.slow_ema_period,
            strategy.atr_period,
        )
        logger.info("\n%s", diagnostics.format())
        opened = process_entry_unless_expired(execution, signal, expired_symbols)
        logger.info(
            f"{symbol}: {signal.action.value} | candle={signal.signal_candle_timestamp} | "
            f"reason={diagnostics.reason} | submitted={opened}"
        )
        positions = [p for p in broker.positions() if p.symbol == symbol]
        snapshots.append({
            "symbol": symbol, "signal": signal.action.value,
            "open": len(positions), "profit": f"{sum(p.profit for p in positions):.2f}",
        })
    show_dashboard(logger, broker, snapshots)


def main():
    logger = setup_logger()
    broker, data, strategy, provider, execution = build_runtime(logger)
    if not broker.initialize():
        return
    broker.ensure_symbols(config.SYMBOLS)
    provider.refresh(force=True)
    logger.info(f"BULLET started | strategy={strategy.name} | dry_run={config.DRY_RUN}")
    try:
        while True:
            run_scan(logger, broker, data, strategy, provider, execution)
            time.sleep(config.SCAN_SECONDS)
    except KeyboardInterrupt:
        logger.info("CTRL+C received. Bot stopped by user.")
    finally:
        broker.shutdown()


if __name__ == "__main__":
    main()
