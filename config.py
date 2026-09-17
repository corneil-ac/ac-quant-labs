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
DATA_FEED_OUTAGE_THRESHOLD = len(SYMBOLS)

# Temporary AQL-0047 observation mode: max-hold exits are paused alongside
# broker-side stop losses so positions can be observed without BULLET's timed exit.
ENABLE_MAX_HOLD = False
MAX_HOLD_HOURS = 2.0
MAX_OPEN_POSITIONS = 4
COOLDOWN_MINUTES = 15
DRY_RUN = False
MAGIC = 300040
DEVIATION = 10
ORDER_COMMENT_ENTRY = "bullet_trend_momentum"
TRADE_JOURNAL_PATH = "data/trade_journal.csv"

# AQL-0047 temporary no-stop-loss observation mode.
ENABLE_STOP_LOSS = False

# AQL-0049 regime-aware entry gating.
ENABLE_REGIME_GATING = True
REGIME_ENTRY_RULES = {
    "STRONG_TREND": {"EMA20_PULLBACK", "NEAR_EMA", "MOMENTUM_CONTINUATION", "BREAKOUT_CONTINUATION", "STRONG_TREND_CONTINUATION"},
    "WEAK_TREND": {"EMA20_PULLBACK", "NEAR_EMA", "MOMENTUM_CONTINUATION"},
    "RANGE": {"EMA20_PULLBACK", "NEAR_EMA"},
    "HIGH_VOLATILITY": {"EMA20_PULLBACK", "MOMENTUM_CONTINUATION"},
    "LOW_VOLATILITY": {"EMA20_PULLBACK", "NEAR_EMA"},
    "UNSTABLE": set(),
}

# AQL-0050: scoring is observational first. Every actionable candidate receives
# an explainable 0-100 score, but MIN_TRADE_QUALITY is ignored until gating is
# explicitly enabled in a later evidence-driven step.
ENABLE_TRADE_QUALITY_SCORING = True
ENABLE_TRADE_QUALITY_GATING = False
MIN_TRADE_QUALITY = 60.0
TRADE_QUALITY_WEIGHTS = {
    "regime": 25.0,
    "trend_strength": 20.0,
    "momentum": 20.0,
    "ema_structure": 20.0,
    "entry_location": 15.0,
}

ENTRY_PRIORITY = [
    "EMA20_PULLBACK", "NEAR_EMA", "BREAKOUT_CONTINUATION",
    "MOMENTUM_CONTINUATION", "STRONG_TREND_CONTINUATION",
]
MULTI_ENTRY_CONFIG = {
    "EMA20_PULLBACK": {"enabled": True, "pullback_lookback": 3},
    "NEAR_EMA": {"enabled": True, "max_distance_atr": 0.35, "min_rsi": 52, "max_rsi": 48},
    "MOMENTUM_CONTINUATION": {"enabled": True, "min_rsi": 55, "max_rsi": 45, "min_ema_slope_atr": 0.03, "slope_lookback": 3},
    "BREAKOUT_CONTINUATION": {"enabled": True, "breakout_lookback": 10, "min_rsi": 55, "max_rsi": 45, "min_breakout_atr": 0.0},
    "STRONG_TREND_CONTINUATION": {"enabled": True, "min_adx": 25, "min_rsi": 58, "max_rsi": 42, "min_ema_slope_atr": 0.08, "slope_lookback": 3, "sustained_bars": 3},
}

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CALENDAR_CACHE_PATH = "data/calendar_cache.json"
CALENDAR_REFRESH_HOURS = 6
CALENDAR_BLACKOUT_MINUTES_BEFORE = 30
CALENDAR_BLACKOUT_MINUTES_AFTER = 30
CALENDAR_BLOCKED_IMPACTS = {"High"}
