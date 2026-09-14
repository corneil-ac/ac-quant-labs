from __future__ import annotations

import time
from collections import Counter

import MetaTrader5 as mt5

import config
from broker import Broker
from calendar_filter import CalendarFilter
from calendar_provider import CalendarProvider
from campaign_manager import CampaignManager
from dashboard import show_dashboard
from data_manager import DataManager
from execution_manager import ExecutionManager
from logger_setup import setup_logger
from maximum_hold_manager import MaximumHoldManager, process_entry_unless_expired
from risk_manager import RiskManager
from scale_in_manager import ScaleInManager
from startup_reconciliation import reconcile_startup
from strategy_diagnostics import diagnose_trend_momentum
from strategy_framework import strategy_registry
import trend_momentum_strategy  # noqa: F401 - registers the configured strategy


TIMEFRAMES = {"M15": mt5.TIMEFRAME_M15, "H1": mt5.TIMEFRAME_H1}
ACTIVITY_METRICS = Counter()


def build_runtime(logger):
    broker = Broker(logger, config.MAGIC, config.DEVIATION, config.DRY_RUN)
    data = DataManager(
        logger, TIMEFRAMES["M15"], config.HISTORY_BARS,
        config.DATA_FETCH_RETRIES, config.DATA_FETCH_RETRY_SECONDS,
        config.MT5_RECOVERY_WAIT_SECONDS,
    )
    strategy = strategy_registry.create(config.ACTIVE_STRATEGY)
    provider = CalendarProvider(
        logger, config.CALENDAR_URL, config.CALENDAR_CACHE_PATH,
        config.CALENDAR_REFRESH_HOURS,
    )
    calendar = CalendarFilter(
        provider, config.CALENDAR_BLACKOUT_MINUTES_BEFORE,
        config.CALENDAR_BLACKOUT_MINUTES_AFTER, config.CALENDAR_BLOCKED_IMPACTS,
    )
    risk = RiskManager(
        logger, broker, config.MAX_OPEN_POSITIONS, config.COOLDOWN_MINUTES,
        max_positions_per_symbol=2,
    )
    campaign = CampaignManager(logger)
    execution = ExecutionManager(
        logger, broker, risk, calendar, config.FIXED_VOLUME,
        config.ORDER_COMMENT_ENTRY, config.ALLOW_VOLUME_NORMALIZATION,
        config.TRADE_JOURNAL_PATH, campaign_manager=campaign,
    )
    scale_in = ScaleInManager(
        logger,
        enabled=getattr(config, "SCALE_IN_ENABLED", True),
        max_entries_per_symbol=getattr(config, "SCALE_IN_MAX_ENTRIES_PER_SYMBOL", 2),
        min_adverse_atr=getattr(config, "SCALE_IN_MIN_ADVERSE_ATR", 1.0),
        max_adverse_atr=getattr(config, "SCALE_IN_MAX_ADVERSE_ATR", 2.0),
        min_adx=getattr(config, "SCALE_IN_MIN_ADX", 20.0),
        require_h1_direction=getattr(config, "SCALE_IN_REQUIRE_H1_DIRECTION", True),
        require_m15_alignment=getattr(config, "SCALE_IN_REQUIRE_M15_ALIGNMENT", True),
    )
    return broker, data, strategy, provider, execution, scale_in, campaign


def run_scan(logger, broker, data, strategy, calendar_provider, execution, scale_in, campaign):
    ACTIVITY_METRICS["scans"] += 1
    snapshots = []
    failed_symbols = []
    data.begin_scan()
    calendar_provider.refresh()

    if execution.safe_mode:
        logger.critical(
            "BULLET SAFE MODE ACTIVE | scan continues | new entries and automatic max-hold closes blocked | reason=%s",
            execution.safe_mode_reason,
        )
        expired_symbols = set()
    else:
        expired_symbols = MaximumHoldManager(
            logger, broker, config.MAX_HOLD_HOURS, config.ENABLE_MAX_HOLD
        ).expire_positions()

    for symbol in config.SYMBOLS:
        candles = {
            "H1": data.get_closed_candles(symbol, TIMEFRAMES["H1"]),
            "M15": data.get_closed_candles(symbol, TIMEFRAMES["M15"]),
        }
        if any(frame.empty for frame in candles.values()):
            failed_symbols.append(symbol)
            logger.error(
                "%s: DATA UNAVAILABLE / DATA FEED FAILURE | no strategy "
                "decision or order submission",
                symbol,
            )
            positions = [p for p in broker.positions() if p.symbol == symbol]
            snapshots.append({
                "symbol": symbol, "signal": "DATA_UNAVAILABLE",
                "open": len(positions),
                "profit": f"{sum(p.profit for p in positions):.2f}",
            })
            continue

        signal = strategy.evaluate(symbol, candles)
        ACTIVITY_METRICS["signals_evaluated"] += 1
        ACTIVITY_METRICS[f"{signal.action.value.lower()}_signals"] += 1
        for source, result in (signal.entry_details or {}).get("module_results", {}).items():
            if result.get("status") == "PASS":
                ACTIVITY_METRICS[f"qualified_{source}"] += 1

        if signal.action.value != "HOLD" and not execution.safe_mode:
            positions_ok, owned_positions, position_reason = broker.query_owned_positions()
            if not positions_ok:
                execution.set_safe_mode(
                    True,
                    f"position state unavailable during scale-in evaluation: {position_reason}",
                )
            else:
                signal = scale_in.authorize(signal, owned_positions)
                if (signal.entry_details or {}).get("scale_in_authorized"):
                    ACTIVITY_METRICS["scale_in_authorized"] += 1

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
        if opened and signal.entry_source:
            ACTIVITY_METRICS[f"trades_opened_{signal.entry_source}"] += 1
            if (signal.entry_details or {}).get("scale_in_authorized"):
                ACTIVITY_METRICS["scale_in_opened"] += 1
        decision_kind = (
            "STRATEGY HOLD" if signal.action.value == "HOLD" else "STRATEGY SIGNAL"
        )
        logger.info(
            f"{symbol}: {decision_kind} ({signal.action.value}) | "
            f"candle={signal.signal_candle_timestamp} | "
            f"reason={diagnostics.reason} | submitted={opened}"
        )
        positions = [p for p in broker.positions() if p.symbol == symbol]
        campaign_snapshot = campaign.snapshot(symbol, positions)
        if campaign_snapshot is not None:
            ACTIVITY_METRICS["campaign_snapshots"] += 1
            logger.info(
                "%s: CAMPAIGN SNAPSHOT | direction=%s | positions=%s | volume=%.4f | weighted_entry=%.8f | pnl=%.2f | valid=%s",
                symbol,
                campaign_snapshot.direction,
                campaign_snapshot.position_count,
                campaign_snapshot.total_volume,
                campaign_snapshot.weighted_entry,
                campaign_snapshot.combined_profit,
                campaign_snapshot.valid,
            )
        snapshots.append({
            "symbol": symbol, "signal": signal.action.value,
            "open": len(positions), "profit": f"{sum(p.profit for p in positions):.2f}",
        })
    threshold = max(1, min(config.DATA_FEED_OUTAGE_THRESHOLD, len(config.SYMBOLS)))
    if len(failed_symbols) >= threshold:
        logger.critical(
            "PROBABLE MT5/DATA-FEED OUTAGE | failed_symbols=%s/%s | symbols=%s",
            len(failed_symbols), len(config.SYMBOLS), ",".join(failed_symbols),
        )
    logger.info("AQL-0044 activity metrics | %s", dict(sorted(ACTIVITY_METRICS.items())))
    show_dashboard(logger, broker, snapshots)


def main():
    logger = setup_logger()
    broker, data, strategy, provider, execution, scale_in, campaign = build_runtime(logger)
    if not broker.initialize():
        return

    broker.ensure_symbols(config.SYMBOLS)

    reconciliation = reconcile_startup(
        logger,
        broker,
        config.SYMBOLS,
        max_positions_per_symbol=2,
    )
    execution.set_safe_mode(not reconciliation.ok, reconciliation.reason)

    provider.refresh(force=True)
    logger.info(
        "BULLET started | strategy=%s | dry_run=%s | trading_state=%s | scale_in=%s | scale_in_window=%.2f-%.2f_ATR | scale_in_min_adx=%.1f | campaign_tracking=ENABLED",
        strategy.name,
        config.DRY_RUN,
        "SAFE_MODE" if execution.safe_mode else "NORMAL",
        "ENABLED" if scale_in.enabled else "DISABLED",
        scale_in.min_adverse_atr,
        scale_in.max_adverse_atr,
        scale_in.min_adx,
    )
    try:
        while True:
            run_scan(logger, broker, data, strategy, provider, execution, scale_in, campaign)
            time.sleep(config.SCAN_SECONDS)
    except KeyboardInterrupt:
        logger.info("CTRL+C received. Bot stopped by user.")
    finally:
        broker.shutdown()


if __name__ == "__main__":
    main()
