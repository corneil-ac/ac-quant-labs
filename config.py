"""
Pair Trading Bot V2 configuration.

Edit this file only when you want to change pairs, lot size, entry/exit rules,
risk limits, or scan timing.
"""

# ==============================
# SYMBOL PAIRS
# ==============================
PAIRS = [
    ("EURUSD", "GBPUSD"),
    ("XAUUSD", "XAGUSD"),
    ("AUDUSD", "NZDUSD"),
    ("EURUSD", "USDCHF"),
    ("GBPUSD", "EURGBP"),
]

# ==============================
# STRATEGY SETTINGS
# ==============================
LOT_SIZE = 0.01

WINDOW_BETA = 200
WINDOW_Z = 80
HISTORY_BARS = 600

ENTRY_Z = 1.30
EXIT_Z = 0.20

# Scan every 60 seconds. Since strategy uses M5 candles, 60 seconds is OK for testing.
SCAN_SECONDS = 60

# ==============================
# RISK / SAFETY SETTINGS
# ==============================
MAX_TOTAL_PAIRS = 2
MAX_PAIRS_PER_STRATEGY = 1
COOLDOWN_MINUTES = 15

# Profit/loss is total floating PnL for both legs of the pair.
PROFIT_TARGET = 40.0
STOP_LOSS = -20.0

# If True, bot will print signals but will NOT place trades.
DRY_RUN = False

# Your bot's magic number. Keep this unique.
MAGIC = 999999

# MT5 timeframe as a string. main.py converts it to the MT5 constant.
TIMEFRAME_NAME = "M5"

# Order settings
DEVIATION = 10
ORDER_COMMENT_ENTRY = "pair_trade_v2"
ORDER_COMMENT_EXIT = "close_pair_v2"

# If leg 1 succeeds but leg 2 fails, immediately close leg 1.
CLOSE_FIRST_LEG_IF_SECOND_FAILS = True
