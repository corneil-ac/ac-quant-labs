from __future__ import annotations

"""P1.2D guarded MT5 demo validation harness.

This script deliberately does NOT open positions. It only works with two existing
BULLET-owned same-symbol positions and requires explicit CLI confirmation before
it is allowed to submit coordinated closes.
"""

import argparse
import sys

import MetaTrader5 as mt5

import config
from broker import Broker
from campaign_exit_manager import CampaignExitManager
from campaign_manager import CampaignManager
from logger_setup import setup_logger
from startup_reconciliation import reconcile_startup


def parse_args():
    parser = argparse.ArgumentParser(description="P1.2D MT5 demo campaign validation")
    parser.add_argument("--symbol", required=True, help="Configured symbol to validate, e.g. EURUSD")
    parser.add_argument("--inspect", action="store_true", help="Inspect/reconcile only; never submit closes")
    parser.add_argument("--close-campaign", action="store_true", help="Close the validated two-position campaign")
    parser.add_argument("--confirm-demo", action="store_true", help="Required acknowledgement for close mode")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger = setup_logger()

    if args.inspect == args.close_campaign:
        print("ERROR: choose exactly one of --inspect or --close-campaign")
        return 2
    if args.symbol not in config.SYMBOLS:
        print(f"ERROR: {args.symbol} is not in config.SYMBOLS")
        return 2

    broker = Broker(logger, config.MAGIC, config.DEVIATION, dry_run=False)
    if not broker.initialize():
        return 3

    try:
        account = broker.account_info()
        if account is None:
            print("ERROR: MT5 account_info unavailable")
            return 3

        # MetaTrader exposes trade_mode; demo is conventionally ACCOUNT_TRADE_MODE_DEMO.
        demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
        trade_mode = getattr(account, "trade_mode", None)
        if trade_mode != demo_mode:
            print(f"REFUSED: account {account.login} is not an MT5 demo account (trade_mode={trade_mode})")
            return 4

        print(f"DEMO ACCOUNT VERIFIED: {account.login}")

        reconciliation = reconcile_startup(
            logger, broker, config.SYMBOLS, max_positions_per_symbol=2
        )
        if not reconciliation.ok:
            print(f"REFUSED: P0 reconciliation failed: {reconciliation.reason}")
            return 5

        ok, positions, reason = broker.query_owned_positions()
        if not ok:
            print(f"REFUSED: owned-position query failed: {reason}")
            return 5

        symbol_positions = [p for p in positions if p.symbol == args.symbol]
        campaigns = CampaignManager(logger)
        snapshot = campaigns.snapshot(args.symbol, symbol_positions)
        if snapshot is None:
            print(f"NO CAMPAIGN: BULLET owns no {args.symbol} positions")
            return 6
        if not snapshot.valid:
            print(f"REFUSED: invalid campaign: {snapshot.reason}")
            return 6

        print("CAMPAIGN SNAPSHOT")
        print(f"  symbol         : {snapshot.symbol}")
        print(f"  direction      : {snapshot.direction}")
        print(f"  positions      : {snapshot.position_count}")
        print(f"  tickets        : {list(snapshot.tickets)}")
        print(f"  total volume   : {snapshot.total_volume:.4f}")
        print(f"  weighted entry : {snapshot.weighted_entry:.8f}")
        print(f"  combined P&L   : {snapshot.combined_profit:.2f}")

        if args.inspect:
            print("RESULT: INSPECTION PASS - no orders submitted")
            return 0

        if not args.confirm_demo:
            print("REFUSED: --close-campaign requires --confirm-demo")
            return 7
        if snapshot.position_count != 2:
            print(f"REFUSED: close validation requires exactly 2 positions; found {snapshot.position_count}")
            return 7

        # Use a threshold guaranteed to trigger from the current snapshot while
        # preserving CampaignExitManager's real close path. This harness is the
        # authorization boundary; normal runtime config remains untouched/off.
        if snapshot.combined_profit >= 0:
            profit_target = max(0.01, snapshot.combined_profit)
            stop_loss = -1_000_000_000.0
        else:
            profit_target = 1_000_000_000.0
            stop_loss = min(-0.01, snapshot.combined_profit)

        exits = CampaignExitManager(
            logger, broker, campaigns, enabled=True,
            profit_target=profit_target, stop_loss=stop_loss,
            close_comment="bullet_p12d_demo_exit",
        )
        result = exits.process_symbol(args.symbol, symbol_positions)
        if not result.triggered:
            print(f"FAIL: campaign exit did not trigger: {result.reason}")
            return 8
        if not result.complete:
            print(f"FAIL: incomplete close; failed tickets={list(result.failed_tickets)}")
            return 9

        ok, remaining, reason = broker.query_owned_positions()
        if not ok:
            print(f"FAIL: post-close reconciliation query failed: {reason}")
            return 10
        remaining_symbol = [p for p in remaining if p.symbol == args.symbol]
        if remaining_symbol:
            print(f"FAIL: {len(remaining_symbol)} {args.symbol} BULLET position(s) remain after coordinated close")
            return 10

        print(f"CLOSED TICKETS: {list(result.closed_tickets)}")
        print("RESULT: P1.2D COORDINATED MT5 DEMO EXIT PASS - zero campaign positions remain")
        return 0
    finally:
        broker.shutdown()


if __name__ == "__main__":
    sys.exit(main())
