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
        entry_z=config.ENTRY_Z,
        exit_z=config.EXIT_Z,
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
        exit_z=config.EXIT_Z,
        entry_comment=config.ORDER_COMMENT_ENTRY,
        exit_comment=config.ORDER_COMMENT_EXIT,
        close_first_leg_if_second_fails=config.CLOSE_FIRST_LEG_IF_SECOND_FAILS,
    )

    logger.info("Bot started")

    try:
        while True:
            snapshots = []

            for symbol1, symbol2 in config.PAIRS:
                data = data_manager.get_pair_data(symbol1, symbol2)
                signal = strategy.calculate(data, symbol1, symbol2)

                if signal is None:
                    logger.info(f"{symbol1}/{symbol2}: not enough data")
                    snapshots.append({
                        "pair": f"{symbol1}/{symbol2}",
                        "z": "N/A",
                        "signal": "NONE",
                        "open": 0,
                        "profit": "0.00",
                    })
                    continue

                open_positions = broker.pair_positions(symbol1, symbol2)
                profit = broker.pair_profit(symbol1, symbol2)

                snapshots.append({
                    "pair": f"{symbol1}/{symbol2}",
                    "z": f"{signal.z:.2f}",
                    "signal": signal.action,
                    "open": len(open_positions),
                    "profit": f"{profit:.2f}",
                })

                # EXIT/MANAGEMENT FIRST. This fixes the V1 bug.
                had_open_pair = trade_manager.manage_existing_pair(symbol1, symbol2, signal.z)
                if had_open_pair:
                    continue

                # ENTRY SECOND.
                if signal.action in ("LONG", "SHORT"):
                    trade_manager.open_pair(signal)
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
