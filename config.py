"""BULLET single-symbol strategy runtime configuration."""

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
ACTIVE_STRATEGY = "TrendMomentumStrategy"
FIXED_VOLUME = 0.01
ALLOW_VOLUME_NORMALIZATION = False
HISTORY_BARS = 300
SCAN_SECONDS = 60
DATA_FETCH_RETRIES = 3
DATA_FETCH_RETRY_SECONDS = 2
MT5_RECOVERY_WAIT_SECONDS = 1
# A scan with this many symbols missing either required timeframe is treated as
# a probable feed-wide outage.  Keep this configurable for other deployments.
DATA_FEED_OUTAGE_THRESHOLD = len(SYMBOLS)

ENABLE_MAX_HOLD = True
MAX_HOLD_HOURS = 2.0

MAX_OPEN_POSITIONS = 2
COOLDOWN_MINUTES = 15
DRY_RUN = False
MAGIC = 999999
DEVIATION = 10
ORDER_COMMENT_ENTRY = "bullet_trend_momentum"
TRADE_JOURNAL_PATH = "data/trade_journal.csv"

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CALENDAR_CACHE_PATH = "data/calendar_cache.json"
CALENDAR_REFRESH_HOURS = 6
CALENDAR_BLACKOUT_MINUTES_BEFORE = 30
CALENDAR_BLACKOUT_MINUTES_AFTER = 30
CALENDAR_BLOCKED_IMPACTS = {"High"}
