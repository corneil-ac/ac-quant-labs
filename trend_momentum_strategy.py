from __future__ import annotations

from copy import deepcopy
from numbers import Real
from typing import Any, Mapping

import pandas as pd

import config
from strategy_framework import SignalAction, StrategySignal, TradingStrategy, strategy_registry


def has_ema_pullback(candles: pd.DataFrame, ema: pd.Series,
                     direction: SignalAction, lookback: int) -> bool:
    """Whether the recent per-candle range touched EMA20 (AQL-0043)."""
    if lookback < 1:
        raise ValueError("pullback_lookback must be at least 1")
    recent = candles.tail(lookback)
    recent_ema = ema.reindex(recent.index)
    if direction is SignalAction.BUY:
        return bool((recent["low"] <= recent_ema).any())
    if direction is SignalAction.SELL:
        return bool((recent["high"] >= recent_ema).any())
    return False


class TrendMomentumStrategy(TradingStrategy):
    name = "TrendMomentumStrategy"
    timeframe = "M15"

    def __init__(self, trend_ema_period: int = 200, fast_ema_period: int = 20,
                 slow_ema_period: int = 50, atr_period: int = 14,
                 stop_atr_multiple: float = 2.0, reward_to_risk: float = 2.0,
                 pullback_lookback: int | None = None,
                 multi_entry_config: Mapping[str, Mapping[str, Any]] | None = None,
                 entry_priority: list[str] | tuple[str, ...] | None = None) -> None:
        self.trend_ema_period, self.fast_ema_period = trend_ema_period, fast_ema_period
        self.slow_ema_period, self.atr_period = slow_ema_period, atr_period
        self.stop_atr_multiple, self.reward_to_risk = stop_atr_multiple, reward_to_risk
        self.multi_entry_config = deepcopy(dict(multi_entry_config or config.MULTI_ENTRY_CONFIG))
        if pullback_lookback is not None:
            self.multi_entry_config.setdefault("EMA20_PULLBACK", {})["pullback_lookback"] = pullback_lookback
        self.pullback_lookback = int(self.multi_entry_config.get("EMA20_PULLBACK", {}).get("pullback_lookback", 3))
        if self.pullback_lookback < 1:
            raise ValueError("pullback_lookback must be at least 1")
        self.entry_priority = tuple(entry_priority or config.ENTRY_PRIORITY)

    @staticmethod
    def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
        delta = close.diff()
        gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, 1e-12)
        return 100 - 100 / (1 + rs)

    @staticmethod
    def _adx(frame: pd.DataFrame, period: int = 14) -> pd.Series:
        up, down = frame["high"].diff(), -frame["low"].diff()
        plus_dm = up.where((up > down) & (up > 0), 0.0)
        minus_dm = down.where((down > up) & (down > 0), 0.0)
        previous = frame["close"].shift(1)
        tr = pd.concat((frame["high"] - frame["low"],
                        (frame["high"] - previous).abs(),
                        (frame["low"] - previous).abs()), axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / period, adjust=False).mean().replace(0, 1e-12)
        plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
        minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-12)
        return dx.ewm(alpha=1 / period, adjust=False).mean()

    def evaluate(self, symbol: str, candles: Mapping[str, pd.DataFrame]) -> StrategySignal:
        h1, m15 = candles.get("H1", pd.DataFrame()).copy(), candles.get("M15", pd.DataFrame()).copy()
        required = {"time", "open", "high", "low", "close"}
        if (not required.issubset(h1.columns) or not required.issubset(m15.columns)
                or len(h1) < self.trend_ema_period
                or len(m15) < max(self.slow_ema_period, self.atr_period + 1)):
            return self._hold(symbol, None, "insufficient closed candle data")

        h1_ema = h1["close"].ewm(span=self.trend_ema_period, adjust=False).mean()
        fast = m15["close"].ewm(span=self.fast_ema_period, adjust=False).mean()
        slow = m15["close"].ewm(span=self.slow_ema_period, adjust=False).mean()
        previous = m15["close"].shift(1)
        tr = pd.concat((m15["high"] - m15["low"], (m15["high"] - previous).abs(),
                        (m15["low"] - previous).abs()), axis=1).max(axis=1)
        atr_series = tr.ewm(alpha=1 / self.atr_period, adjust=False).mean()
        candle, trend = m15.iloc[-1], h1.iloc[-1]
        timestamp = (pd.to_datetime(candle["time"], unit="s", utc=True)
                     if isinstance(candle["time"], Real) else pd.to_datetime(candle["time"], utc=True))
        close, open_, atr = float(candle["close"]), float(candle["open"]), float(atr_series.iloc[-1])
        if pd.isna(atr) or atr <= 0:
            return self._hold(symbol, timestamp, "ATR unavailable")

        h1_direction = (SignalAction.BUY if float(trend["close"]) > float(h1_ema.iloc[-1])
                        else SignalAction.SELL if float(trend["close"]) < float(h1_ema.iloc[-1]) else None)
        buy_aligned = float(fast.iloc[-1]) > float(slow.iloc[-1]) and close > float(fast.iloc[-1]) and close > float(slow.iloc[-1])
        sell_aligned = float(fast.iloc[-1]) < float(slow.iloc[-1]) and close < float(fast.iloc[-1]) and close < float(slow.iloc[-1])
        direction = h1_direction if ((h1_direction is SignalAction.BUY and buy_aligned)
                                     or (h1_direction is SignalAction.SELL and sell_aligned)) else None
        if direction is None:
            return self._hold(symbol, timestamp, "H1 trend and M15 direction are not aligned",
                              common={"h1_direction": getattr(h1_direction, "value", "NEUTRAL"), "m15_aligned": False})

        bullish = close > open_
        confirmation = bullish if direction is SignalAction.BUY else close < open_
        rsi, adx = float(self._rsi(m15["close"]).iloc[-1]), float(self._adx(m15).iloc[-1])
        side = 1 if direction is SignalAction.BUY else -1
        metrics = {"h1_direction": direction.value, "m15_aligned": True, "rsi": rsi,
                   "adx": adx, "atr": atr, "ema20_distance_atr": abs(close - float(fast.iloc[-1])) / atr}
        results: dict[str, dict[str, Any]] = {}
        for module, settings in self.multi_entry_config.items():
            if not settings.get("enabled", True):
                results[module] = {"status": "DISABLED", "reason": "module disabled"}
                continue
            passed, why = self._evaluate_module(module, settings, m15, fast, atr_series,
                                                direction, confirmation, rsi, adx)
            results[module] = {"status": "PASS" if passed else "FAIL", "reason": why}

        selected = next((name for name in self.entry_priority
                         if results.get(name, {}).get("status") == "PASS"), None)
        details = {**metrics, "module_results": results}
        if selected is None:
            return self._hold(symbol, timestamp, "no enabled entry module qualified", details)
        reason = results[selected]["reason"]
        distance = self.stop_atr_multiple * atr
        stop, target = close - side * distance, close + side * distance * self.reward_to_risk
        return StrategySignal(symbol, direction, timestamp, close, stop, target, self.name,
                              self.timeframe, reason, selected, reason, details)

    def _evaluate_module(self, name, cfg, m15, fast, atr_series, direction,
                         confirmation, rsi, adx) -> tuple[bool, str]:
        buy = direction is SignalAction.BUY
        momentum = rsi >= float(cfg.get("min_rsi", 0)) if buy else rsi <= float(cfg.get("max_rsi", 100))
        if name == "EMA20_PULLBACK":
            ok = confirmation and has_ema_pullback(m15, fast, direction, int(cfg.get("pullback_lookback", 3)))
            return ok, "EMA20 pullback followed by directional confirmation" if ok else "pullback or confirmation absent"
        if name == "NEAR_EMA":
            distance = abs(float(m15["close"].iloc[-1]) - float(fast.iloc[-1])) / float(atr_series.iloc[-1])
            ok = confirmation and momentum and distance <= float(cfg["max_distance_atr"])
            return ok, f"price near EMA20 ({distance:.3f} ATR) with directional momentum" if ok else "price not near EMA20 or momentum absent"
        if name == "BREAKOUT_CONTINUATION":
            lookback = int(cfg["breakout_lookback"])
            prior = m15.iloc[-lookback-1:-1]
            level = float(prior["high"].max() if buy else prior["low"].min())
            margin = float(cfg.get("min_breakout_atr", 0)) * float(atr_series.iloc[-1])
            broken = float(m15["close"].iloc[-1]) > level + margin if buy else float(m15["close"].iloc[-1]) < level - margin
            ok = confirmation and momentum and len(prior) == lookback and broken
            return ok, f"closed beyond {lookback}-bar range with directional momentum" if ok else "recent range not broken with confirmation"
        slope_lookback = int(cfg.get("slope_lookback", 3))
        slope = (float(fast.iloc[-1]) - float(fast.iloc[-1-slope_lookback])) / float(atr_series.iloc[-1])
        slope_ok = side_sign(direction) * slope >= float(cfg.get("min_ema_slope_atr", 0))
        if name == "MOMENTUM_CONTINUATION":
            ok = confirmation and momentum and slope_ok
            return ok, f"EMA20 slope {slope:.3f} ATR and RSI {rsi:.1f} confirm continuation" if ok else "continuation slope, RSI, or candle insufficient"
        if name == "STRONG_TREND_CONTINUATION":
            bars = int(cfg.get("sustained_bars", 3))
            sustained = bool((m15["close"].tail(bars) > fast.tail(bars)).all()) if buy else bool((m15["close"].tail(bars) < fast.tail(bars)).all())
            ok = confirmation and momentum and slope_ok and adx >= float(cfg["min_adx"]) and sustained
            return ok, f"strong trend: ADX {adx:.1f}, sustained EMA20 location and slope" if ok else "strong-trend ADX, slope, momentum, or persistence insufficient"
        return False, "unknown entry module"

    def _hold(self, symbol, timestamp, reason: str, common=None) -> StrategySignal:
        details = common or {}
        if "module_results" not in details:
            details = {**details, "module_results": {
                name: {"status": "DISABLED" if not cfg.get("enabled", True) else "FAIL", "reason": reason}
                for name, cfg in self.multi_entry_config.items()}}
        return StrategySignal(symbol, SignalAction.HOLD, timestamp, None, None, None,
                              self.name, self.timeframe, reason, None, reason, details)


def side_sign(direction: SignalAction) -> int:
    return 1 if direction is SignalAction.BUY else -1


strategy_registry.register(TrendMomentumStrategy.name, TrendMomentumStrategy)
