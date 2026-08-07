from __future__ import annotations

from numbers import Real
from typing import Mapping

import pandas as pd

from strategy_framework import (
    SignalAction,
    StrategySignal,
    TradingStrategy,
    strategy_registry,
)


def has_ema_pullback(
    candles: pd.DataFrame,
    ema: pd.Series,
    direction: SignalAction,
    lookback: int,
) -> bool:
    """Return whether price has touched the EMA in the recent entry setup.

    A pullback and its confirmation do not necessarily happen in the same
    candle.  Compare every candle with the EMA value calculated for that
    candle, rather than comparing earlier prices with today's EMA.
    """
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

    def __init__(
        self,
        trend_ema_period: int = 200,
        fast_ema_period: int = 20,
        slow_ema_period: int = 50,
        atr_period: int = 14,
        stop_atr_multiple: float = 2.0,
        reward_to_risk: float = 2.0,
        pullback_lookback: int = 3,
    ) -> None:
        self.trend_ema_period = trend_ema_period
        self.fast_ema_period = fast_ema_period
        self.slow_ema_period = slow_ema_period
        self.atr_period = atr_period
        if pullback_lookback < 1:
            raise ValueError("pullback_lookback must be at least 1")
        self.pullback_lookback = pullback_lookback
        self.stop_atr_multiple = stop_atr_multiple
        self.reward_to_risk = reward_to_risk

    def evaluate(
        self, symbol: str, candles: Mapping[str, pd.DataFrame]
    ) -> StrategySignal:
        h1 = candles.get("H1", pd.DataFrame()).copy()
        m15 = candles.get("M15", pd.DataFrame()).copy()
        required = {"time", "open", "high", "low", "close"}
        if (
            not required.issubset(h1.columns)
            or not required.issubset(m15.columns)
            or len(h1) < self.trend_ema_period
            or len(m15) < max(self.slow_ema_period, self.atr_period + 1)
        ):
            return self._hold(symbol, None, "insufficient closed candle data")

        h1["ema_trend"] = h1["close"].ewm(
            span=self.trend_ema_period, adjust=False
        ).mean()
        m15["ema_fast"] = m15["close"].ewm(
            span=self.fast_ema_period, adjust=False
        ).mean()
        m15["ema_slow"] = m15["close"].ewm(
            span=self.slow_ema_period, adjust=False
        ).mean()
        previous_close = m15["close"].shift(1)
        true_range = pd.concat(
            [
                m15["high"] - m15["low"],
                (m15["high"] - previous_close).abs(),
                (m15["low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        m15["atr"] = true_range.ewm(
            alpha=1 / self.atr_period, adjust=False
        ).mean()

        trend = h1.iloc[-1]
        candle = m15.iloc[-1]
        timestamp = pd.to_datetime(candle["time"], unit="s", utc=True) if isinstance(
            candle["time"], Real
        ) else pd.to_datetime(candle["time"], utc=True)
        entry = float(candle["close"])
        atr = float(candle["atr"])
        if pd.isna(atr) or atr <= 0:
            return self._hold(symbol, timestamp, "ATR unavailable")

        bullish = float(candle["close"]) > float(candle["open"])
        bearish = float(candle["close"]) < float(candle["open"])
        buy_pullback = has_ema_pullback(
            m15, m15["ema_fast"], SignalAction.BUY, self.pullback_lookback
        )
        sell_pullback = has_ema_pullback(
            m15, m15["ema_fast"], SignalAction.SELL, self.pullback_lookback
        )
        buy = (
            trend["close"] > trend["ema_trend"]
            and candle["ema_fast"] > candle["ema_slow"]
            and candle["close"] > candle["ema_fast"]
            and candle["close"] > candle["ema_slow"]
            and buy_pullback
            and bullish
        )
        sell = (
            trend["close"] < trend["ema_trend"]
            and candle["ema_fast"] < candle["ema_slow"]
            and candle["close"] < candle["ema_fast"]
            and candle["close"] < candle["ema_slow"]
            and sell_pullback
            and bearish
        )
        distance = self.stop_atr_multiple * atr
        if buy:
            return StrategySignal(
                symbol, SignalAction.BUY, timestamp, entry, entry - distance,
                entry + distance * self.reward_to_risk, self.name, self.timeframe,
                "H1 uptrend; M15 bullish momentum, EMA20 pullback and confirmation",
            )
        if sell:
            return StrategySignal(
                symbol, SignalAction.SELL, timestamp, entry, entry + distance,
                entry - distance * self.reward_to_risk, self.name, self.timeframe,
                "H1 downtrend; M15 bearish momentum, EMA20 pullback and confirmation",
            )
        return self._hold(symbol, timestamp, "trend, momentum, and entry trigger not aligned")

    def _hold(self, symbol, timestamp, reason: str) -> StrategySignal:
        return StrategySignal(
            symbol, SignalAction.HOLD, timestamp, None, None, None,
            self.name, self.timeframe, reason,
        )


strategy_registry.register(TrendMomentumStrategy.name, TrendMomentumStrategy)
