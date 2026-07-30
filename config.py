"""
BULLET configuration.

Edit this file to change pairs, thresholds, risk limits, calendar behavior,
or scan timing.
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
    ("EURJPY", "GBPJPY"),
    ("EURAUD", "EURNZD"),
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
WINDOW_BETA = 200
WINDOW_Z = 80
HISTORY_BARS = 600

# Global fallbacks. Active pairs should use PAIR_PROFILES below.
ENTRY_Z = 1.30
EXIT_Z = 0.20

PAIR_PROFILES = {
    ("EURUSD", "GBPUSD"): {"name": "EURGBP_CORE", "entry_z": 1.40, "exit_z": 0.15, "news_filter": True},
    ("XAUUSD", "XAGUSD"): {"name": "METALS_CORE", "entry_z": 1.80, "exit_z": 0.20, "news_filter": True},
    ("AUDUSD", "NZDUSD"): {"name": "AUDNZD_CORE", "entry_z": 1.50, "exit_z": 0.15, "news_filter": True},
    ("EURUSD", "USDCHF"): {"name": "EURCHF_USD", "entry_z": 1.80, "exit_z": 0.10, "news_filter": True},
    ("GBPUSD", "EURGBP"): {"name": "GBP_EUR_CROSS", "entry_z": 1.60, "exit_z": 0.15, "news_filter": True},
    ("EURJPY", "GBPJPY"): {"name": "EURGBP_JPY", "entry_z": 1.40, "exit_z": 0.15, "news_filter": True},
    ("EURAUD", "EURNZD"): {"name": "EUR_AUDNZD", "entry_z": 1.50, "exit_z": 0.15, "news_filter": True},
    ("AUDJPY", "NZDJPY"): {"name": "AUDNZD_JPY", "entry_z": 1.50, "exit_z": 0.15, "news_filter": True},
    ("AUDCAD", "NZDCAD"): {"name": "AUDNZD_CAD", "entry_z": 1.50, "exit_z": 0.15, "news_filter": True},
    ("AUDCHF", "NZDCHF"): {"name": "AUDNZD_CHF", "entry_z": 1.50, "exit_z": 0.15, "news_filter": True},
}

SCAN_SECONDS = 60

# ==============================
# ECONOMIC CALENDAR
# ==============================
CALENDAR_ENABLED = True
CALENDAR_SOURCE_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CALENDAR_CACHE_PATH = "data/calendar_cache.json"
CALENDAR_REFRESH_SECONDS = 6 * 60 * 60
CALENDAR_MAX_CACHE_AGE_SECONDS = 12 * 60 * 60
CALENDAR_REQUEST_TIMEOUT_SECONDS = 15
CALENDAR_IMPACTS = {"High"}
CALENDAR_BLACKOUT_MINUTES_BEFORE = 120
CALENDAR_BLACKOUT_MINUTES_AFTER = 120
CALENDAR_FAIL_CLOSED = True

# ==============================
# RISK / SAFETY SETTINGS
# ==============================
MAX_TOTAL_PAIRS = 2
MAX_PAIRS_PER_STRATEGY = 1
COOLDOWN_MINUTES = 15
PROFIT_TARGET = 40.0
STOP_LOSS = -20.0
DRY_RUN = False
MAGIC = 999999
TIMEFRAME_NAME = "M5"
DEVIATION = 10
ORDER_COMMENT_ENTRY = "pair_trade_v2"
ORDER_COMMENT_EXIT = "close_pair_v2"
CLOSE_FIRST_LEG_IF_SECOND_FAILS = True
