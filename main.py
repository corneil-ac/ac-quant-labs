from __future__ import annotations

import time
import MetaTrader5 as mt5

import config
from logger_setup import setup_logger
from broker import Broker
from data_manager import DataManager
from strategy import PairStrategy
from risk_manager import RiskManager
from trade_manager import TradeManager
from dashboard import show_dashboard
from calendar_provider import CalendarProvider
from calendar_filter import CalendarFilter

TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}


def main():
    logger = setup_logger()

    timeframe = TIMEFRAMES.get(config.TIMEFRAME_NAME.upper())
    if timeframe is None:
        raise ValueError(f"Unsupported TIMEFRAME_NAME: {config.TIMEFRAME_NAME}")

    broker = Broker(
        logger=logger,
        magic=config.MAGIC,
        deviation=config.DEVIATION,
        dry_run=config.DRY_RUN,
    )

    if not broker.initialize():
        return

    all_symbols = []
    for s1, s2 in config.PAIRS:
        all_symbols.extend([s1, s2])
    broker.ensure_symbols(all_symbols)

    data_manager = DataManager(
        logger=logger,
        timeframe=timeframe,
        history_bars=config.HISTORY_BARS,
    )

    strategy = PairStrategy(
        window_beta=config.WINDOW_BETA,
        window_z=config.WINDOW_Z,
    )

    calendar_provider = CalendarProvider(
        logger=logger,
        url=config.CALENDAR_URL,
        cache_path=config.CALENDAR_CACHE_PATH,
        refresh_hours=config.CALENDAR_REFRESH_HOURS,
    )
    calendar_provider.refresh(force=True)
    calendar_filter = CalendarFilter(
        provider=calendar_provider,
        minutes_before=config.CALENDAR_BLACKOUT_MINUTES_BEFORE,
        minutes_after=config.CALENDAR_BLACKOUT_MINUTES_AFTER,
        blocked_impacts=config.CALENDAR_BLOCKED_IMPACTS,
    )

    risk_manager = RiskManager(
        logger=logger,
        broker=broker,
        max_total_pairs=config.MAX_TOTAL_PAIRS,
        cooldown_minutes=config.COOLDOWN_MINUTES,
    )

    trade_manager = TradeManager(
        logger=logger,
        broker=broker,
        risk_manager=risk_manager,
        lot_size=config.LOT_SIZE,
        profit_target=config.PROFIT_TARGET,
        stop_loss=config.STOP_LOSS,
        entry_comment=config.ORDER_COMMENT_ENTRY,
        exit_comment=config.ORDER_COMMENT_EXIT,
        execution_modes=config.PAIR_EXECUTION_MODES,
        close_first_leg_if_second_fails=config.CLOSE_FIRST_LEG_IF_SECOND_FAILS,
    )

    logger.info("Bot started")

    try:
        while True:
            snapshots = []
            calendar_provider.refresh()

            for symbol1, symbol2 in config.PAIRS:
                profile = config.PAIR_PROFILES[(symbol1, symbol2)]
                data = data_manager.get_pair_data(symbol1, symbol2)
                signal = strategy.calculate(data, symbol1, symbol2, profile)

                if signal is None:
                    logger.info(f"{symbol1}/{symbol2}: not enough data")
                    snapshots.append(
                        {
                            "pair": f"{symbol1}/{symbol2}",
                            "z": "N/A",
                            "signal": "NONE",
                            "open": len(broker.pair_positions(symbol1, symbol2)),
                            "profit": f"{broker.pair_profit(symbol1, symbol2):.2f}",
                        }
                    )
                    trade_manager.manage_existing_pair(
                        symbol1, symbol2, None, profile
                    )
                    continue

                open_positions = broker.pair_positions(symbol1, symbol2)
                profit = broker.pair_profit(symbol1, symbol2)

                snapshots.append(
                    {
                        "pair": f"{symbol1}/{symbol2}",
                        "z": f"{signal.z:.2f}",
                        "signal": signal.action,
                        "open": len(open_positions),
                        "profit": f"{profit:.2f}",
                    }
                )

                # EXIT/MANAGEMENT FIRST. This fixes the V1 bug.
                had_open_pair = trade_manager.manage_existing_pair(
                    symbol1, symbol2, signal.z, profile
                )
                if had_open_pair:
                    continue

                # ENTRY SECOND.
                if signal.action in ("LONG", "SHORT"):
                    calendar_ok, calendar_reason = calendar_filter.can_open_pair(
                        symbol1, symbol2
                    )
                    if calendar_ok:
                        trade_manager.open_pair(signal)
                    else:
                        logger.info(
                            f"{symbol1}/{symbol2}: entry blocked -> {calendar_reason}"
                        )
                else:
                    logger.info(f"{symbol1}/{symbol2}: waiting | z={signal.z:.2f}")

            show_dashboard(logger, broker, snapshots)
            time.sleep(config.SCAN_SECONDS)

    except KeyboardInterrupt:
        logger.info("CTRL+C received. Bot stopped by user.")

    finally:
        broker.shutdown()


if __name__ == "__main__":
    main()
