from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

import pandas as pd


class MarketRegime(str, Enum):
    STRONG_TREND = "STRONG_TREND"
    WEAK_TREND = "WEAK_TREND"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    UNSTABLE = "UNSTABLE"


@dataclass(frozen=True)
class RegimeAssessment:
    regime: MarketRegime
    metrics: Mapping[str, float | bool | str]
    reason: str


class RegimeDetector:
    """Deterministic, explainable market-regime classifier for BULLET."""

    def __init__(self, atr_period: int = 14, fast_ema: int = 20, slow_ema: int = 50,
                 adx_period: int = 14, slope_lookback: int = 3,
                 high_vol_ratio: float = 1.35, low_vol_ratio: float = 0.75,
                 strong_adx: float = 28.0, weak_adx: float = 20.0,
                 strong_slope_atr: float = 0.08, weak_slope_atr: float = 0.03,
                 range_ema_spread_atr: float = 0.25) -> None:
        self.atr_period = atr_period
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.adx_period = adx_period
        self.slope_lookback = slope_lookback
        self.high_vol_ratio = high_vol_ratio
        self.low_vol_ratio = low_vol_ratio
        self.strong_adx = strong_adx
        self.weak_adx = weak_adx
        self.strong_slope_atr = strong_slope_atr
        self.weak_slope_atr = weak_slope_atr
        self.range_ema_spread_atr = range_ema_spread_atr

    @staticmethod
    def _true_range(frame: pd.DataFrame) -> pd.Series:
        previous = frame["close"].shift(1)
        return pd.concat(
            (
                frame["high"] - frame["low"],
                (frame["high"] - previous).abs(),
                (frame["low"] - previous).abs(),
            ), axis=1,
        ).max(axis=1)

    def _atr(self, frame: pd.DataFrame) -> pd.Series:
        return self._true_range(frame).ewm(alpha=1 / self.atr_period, adjust=False).mean()

    def _adx(self, frame: pd.DataFrame) -> pd.Series:
        up, down = frame["high"].diff(), -frame["low"].diff()
        plus_dm = up.where((up > down) & (up > 0), 0.0)
        minus_dm = down.where((down > up) & (down > 0), 0.0)
        atr = self._true_range(frame).ewm(alpha=1 / self.adx_period, adjust=False).mean().replace(0, 1e-12)
        plus_di = 100 * plus_dm.ewm(alpha=1 / self.adx_period, adjust=False).mean() / atr
        minus_di = 100 * minus_dm.ewm(alpha=1 / self.adx_period, adjust=False).mean() / atr
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-12)
        return dx.ewm(alpha=1 / self.adx_period, adjust=False).mean()

    def classify(self, candles: pd.DataFrame) -> RegimeAssessment:
        required = {"open", "high", "low", "close"}
        min_bars = max(self.slow_ema + self.slope_lookback, self.atr_period * 4)
        if not required.issubset(candles.columns) or len(candles) < min_bars:
            return RegimeAssessment(
                MarketRegime.UNSTABLE,
                {"sufficient_data": False},
                "insufficient candle data for regime classification",
            )

        close = candles["close"].astype(float)
        fast = close.ewm(span=self.fast_ema, adjust=False).mean()
        slow = close.ewm(span=self.slow_ema, adjust=False).mean()
        atr_series = self._atr(candles)
        adx_series = self._adx(candles)

        atr = float(atr_series.iloc[-1])
        if pd.isna(atr) or atr <= 0:
            return RegimeAssessment(
                MarketRegime.UNSTABLE,
                {"sufficient_data": True, "atr": atr},
                "ATR unavailable for regime classification",
            )

        atr_baseline = float(atr_series.tail(self.atr_period * 3).median())
        vol_ratio = atr / max(atr_baseline, 1e-12)
        adx = float(adx_series.iloc[-1])
        fast_now, slow_now = float(fast.iloc[-1]), float(slow.iloc[-1])
        slope = (fast_now - float(fast.iloc[-1 - self.slope_lookback])) / atr
        ema_spread = abs(fast_now - slow_now) / atr
        price = float(close.iloc[-1])
        directional_alignment = (price > fast_now > slow_now) or (price < fast_now < slow_now)

        metrics = {
            "sufficient_data": True,
            "atr": atr,
            "atr_baseline": atr_baseline,
            "volatility_ratio": vol_ratio,
            "adx": adx,
            "ema20_slope_atr": slope,
            "ema20_ema50_spread_atr": ema_spread,
            "directional_alignment": directional_alignment,
        }

        if vol_ratio >= self.high_vol_ratio:
            return RegimeAssessment(MarketRegime.HIGH_VOLATILITY, metrics,
                                    f"ATR ratio {vol_ratio:.2f} indicates volatility expansion")
        if vol_ratio <= self.low_vol_ratio:
            return RegimeAssessment(MarketRegime.LOW_VOLATILITY, metrics,
                                    f"ATR ratio {vol_ratio:.2f} indicates volatility compression")

        abs_slope = abs(slope)
        if directional_alignment and adx >= self.strong_adx and abs_slope >= self.strong_slope_atr:
            return RegimeAssessment(MarketRegime.STRONG_TREND, metrics,
                                    f"ADX {adx:.1f}, aligned EMA structure, slope {slope:.3f} ATR")
        if directional_alignment and adx >= self.weak_adx and abs_slope >= self.weak_slope_atr:
            return RegimeAssessment(MarketRegime.WEAK_TREND, metrics,
                                    f"moderate ADX {adx:.1f} with aligned EMA structure")
        if adx < self.weak_adx and ema_spread <= self.range_ema_spread_atr:
            return RegimeAssessment(MarketRegime.RANGE, metrics,
                                    f"ADX {adx:.1f} and EMA spread {ema_spread:.3f} ATR indicate range")

        return RegimeAssessment(MarketRegime.UNSTABLE, metrics,
                                "mixed trend/volatility signals indicate transition")
