from __future__ import annotations

import os
from datetime import datetime


def clear_console():
    os.system("cls" if os.name == "nt" else "clear")


def show_dashboard(logger, broker, pair_snapshots):
    clear_console()

    account = broker.account_info()
    positions = broker.positions()
    orphan_count = sum(1 for snap in pair_snapshots if snap.get("open") == 1)

    print("=" * 60)
    print("PAIR TRADING BOT V2.1")
    print("=" * 60)
    print(f"Time       : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if account:
        print(f"Account    : {account.login}")
        print(f"Balance    : {account.balance:.2f}")
        print(f"Equity     : {account.equity:.2f}")
        print(f"Margin Free: {account.margin_free:.2f}")

    print(f"Open Legs  : {len(positions)}")
    print(f"Open Pairs : {len(positions) // 2}")
    if orphan_count:
        print(f"WARNING    : {orphan_count} incomplete pair(s) detected")
    print("-" * 60)

    for snap in pair_snapshots:
        warning = " ORPHAN" if snap.get("open") == 1 else ""
        print(
            f"{snap['pair']:<18} | Z={snap['z']:<7} | Signal={snap['signal']:<6} | "
            f"Open={snap['open']:<3} | PnL={snap['profit']}{warning}"
        )

    print("-" * 60)
    print("Press CTRL+C to stop the bot safely.")
