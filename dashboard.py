from __future__ import annotations

import os
from datetime import datetime


def clear_console():
    os.system("cls" if os.name == "nt" else "clear")


def show_dashboard(logger, broker, snapshots):
    clear_console()

    account = broker.account_info()
    account_positions = broker.account_positions()
    bullet_positions = broker.positions()
    print("=" * 60)
    print("BULLET STRATEGY RUNTIME")
    print("=" * 60)
    print(f"Time       : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if account:
        print(f"Account    : {account.login}")
        print(f"Balance    : {account.balance:.2f}")
        print(f"Equity     : {account.equity:.2f}")
        print(f"Margin Free: {account.margin_free:.2f}")

    print(f"Account Positions : {len(account_positions)}")
    print(f"BULLET Positions  : {len(bullet_positions)}")
    print("-" * 60)

    for snap in snapshots:
        print(
            f"{snap['symbol']:<18} | Signal={snap['signal']:<6} | "
            f"Open={snap['open']:<3} | PnL={snap['profit']}"
        )

    print("-" * 60)
    print("Press CTRL+C to stop the bot safely.")
