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

MAX_OPEN_POSITIONS = 4
COOLDOWN_MINUTES = 15
DRY_RUN = False
MAGIC = 300040
DEVIATION = 10
ORDER_COMMENT_ENTRY = "bullet_trend_momentum"
TRADE_JOURNAL_PATH = "data/trade_journal.csv"

# AQL-0047: temporary no-stop-loss observation mode. The strategy continues to
# calculate its theoretical ATR stop for diagnostics and later comparison, but
# ExecutionManager omits SL from the MT5 order while this flag is False.
ENABLE_STOP_LOSS = False

# AQL-0049: regime-aware entry gating. Keep the mapping explicit and configurable.
ENABLE_REGIME_GATING = True
REGIME_ENTRY_RULES = {
    "STRONG_TREND": {
        "EMA20_PULLBACK", "NEAR_EMA", "MOMENTUM_CONTINUATION",
        "BREAKOUT_CONTINUATION", "STRONG_TREND_CONTINUATION",
    },
    "WEAK_TREND": {
        "EMA20_PULLBACK", "NEAR_EMA", "MOMENTUM_CONTINUATION",
    },
    "RANGE": {
        "EMA20_PULLBACK", "NEAR_EMA",
    },
    "HIGH_VOLATILITY": {
        "EMA20_PULLBACK", "MOMENTUM_CONTINUATION",
    },
    "LOW_VOLATILITY": {
        "EMA20_PULLBACK", "NEAR_EMA",
    },
    # UNSTABLE intentionally allows no entry modules while gating is enabled.
    "UNSTABLE": set(),
}

# AQL-0044 multi-entry engine.  Thresholds are deliberately moderately
# permissive for demo observation, while every module still sits behind the H1
# trend and M15 directional alignment gates.
ENTRY_PRIORITY = [
    "EMA20_PULLBACK", "NEAR_EMA", "BREAKOUT_CONTINUATION",
    "MOMENTUM_CONTINUATION", "STRONG_TREND_CONTINUATION",
]
MULTI_ENTRY_CONFIG = {
    "EMA20_PULLBACK": {"enabled": True, "pullback_lookback": 3},
    "NEAR_EMA": {"enabled": True, "max_distance_atr": 0.35, "min_rsi": 52, "max_rsi": 48},
    "MOMENTUM_CONTINUATION": {
        "enabled": True, "min_rsi": 55, "max_rsi": 45,
        "min_ema_slope_atr": 0.03, "slope_lookback": 3,
    },
    "BREAKOUT_CONTINUATION": {
        "enabled": True, "breakout_lookback": 10, "min_rsi": 55, "max_rsi": 45,
        "min_breakout_atr": 0.0,
    },
    "STRONG_TREND_CONTINUATION": {
        "enabled": True, "min_adx": 25, "min_rsi": 58, "max_rsi": 42,
        "min_ema_slope_atr": 0.08, "slope_lookback": 3, "sustained_bars": 3,
    },
}

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CALENDAR_CACHE_PATH = "data/calendar_cache.json"
CALENDAR_REFRESH_HOURS = 6
CALENDAR_BLACKOUT_MINUTES_BEFORE = 30
CALENDAR_BLACKOUT_MINUTES_AFTER = 30
CALENDAR_BLOCKED_IMPACTS = {"High"}
