"""
Pair Trading Bot V2 configuration.

Edit this file only when you want to change pairs, lot size, entry/exit rules,
risk limits, or scan timing.
"""

# ==============================
# ==============================
# SYMBOL PAIRS
# ==============================
PAIRS = [
    # Existing
    ("EURUSD", "GBPUSD"),
    ("XAUUSD", "XAGUSD"),
    ("AUDUSD", "NZDUSD"),
    ("EURUSD", "USDCHF"),
    ("GBPUSD", "EURGBP"),
    # Additional EUR / GBP
    ("EURJPY", "GBPJPY"),
    ("EURAUD", "EURNZD"),
    # Additional Australian / New Zealand
    ("AUDJPY", "NZDJPY"),
    ("AUDCAD", "NZDCAD"),
    ("AUDCHF", "NZDCHF"),
]

# ==============================
# PAIR EXECUTION MODES
# ==============================
PAIR_EXECUTION_MODES = {
    ("EURUSD", "GBPUSD"): "HEDGED",
    ("XAUUSD", "XAGUSD"): "SAME_DIRECTION",
    ("AUDUSD", "NZDUSD"): "HEDGED",
    ("EURUSD", "USDCHF"): "HEDGED",
    ("GBPUSD", "EURGBP"): "HEDGED",
    ("EURJPY", "GBPJPY"): "HEDGED",
    ("EURAUD", "EURNZD"): "HEDGED",
    ("AUDJPY", "NZDJPY"): "HEDGED",
    ("AUDCAD", "NZDCAD"): "HEDGED",
    ("AUDCHF", "NZDCHF"): "HEDGED",
}

# ==============================
# STRATEGY SETTINGS
# ==============================
LOT_SIZE = 0.01

# Keep False to reject lot sizes that do not exactly match each symbol's MT5
# volume contract. Set True only when automatic clamping/step rounding is desired.
ALLOW_VOLUME_NORMALIZATION = False

WINDOW_BETA = 200
WINDOW_Z = 80
HISTORY_BARS = 600

PAIR_PROFILES = {
    pair: {
        "name": "standard",
        "entry_z": 1.30,
        "exit_z": 0.20,
    }
    for pair in PAIRS
}

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

# Economic calendar. New entries are blocked around matching high-impact events.
CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CALENDAR_CACHE_PATH = "data/calendar_cache.json"
CALENDAR_REFRESH_HOURS = 6
CALENDAR_BLACKOUT_MINUTES_BEFORE = 30
CALENDAR_BLACKOUT_MINUTES_AFTER = 30
CALENDAR_BLOCKED_IMPACTS = {"High"}
