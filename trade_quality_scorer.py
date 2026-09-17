from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class QualityAssessment:
    score: float
    components: Mapping[str, float]


class TradeQualityScorer:
    """Deterministic, explainable 0-100 setup-quality scorer."""

    def __init__(self, weights: Mapping[str, float] | None = None) -> None:
        self.weights = dict(weights or {
            "regime": 25.0,
            "trend_strength": 20.0,
            "momentum": 20.0,
            "ema_structure": 20.0,
            "entry_location": 15.0,
        })
        if any(weight < 0 for weight in self.weights.values()) or sum(self.weights.values()) <= 0:
            raise ValueError("quality-score weights must be non-negative with positive total")

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    def score(self, *, regime: str, adx: float, rsi: float, direction: str,
              ema_distance_atr: float, ema_slope_atr: float,
              module: str) -> QualityAssessment:
        regime_values = {
            "STRONG_TREND": 1.0,
            "WEAK_TREND": 0.75,
            "HIGH_VOLATILITY": 0.65,
            "LOW_VOLATILITY": 0.55,
            "RANGE": 0.50,
            "UNSTABLE": 0.0,
        }
        regime_component = regime_values.get(regime, 0.50)
        trend_component = self._clamp((adx - 15.0) / 25.0)

        directional_rsi = rsi if direction == "BUY" else 100.0 - rsi
        momentum_component = self._clamp((directional_rsi - 50.0) / 20.0)
        slope_component = self._clamp(abs(ema_slope_atr) / 0.15)

        if module in {"EMA20_PULLBACK", "NEAR_EMA"}:
            location_component = self._clamp(1.0 - ema_distance_atr / 0.75)
        else:
            # Continuation setups should not be scored down merely for being
            # farther from EMA20, but extreme extension is still undesirable.
            location_component = self._clamp(1.0 - max(0.0, ema_distance_atr - 0.75) / 1.25)

        raw = {
            "regime": regime_component,
            "trend_strength": trend_component,
            "momentum": momentum_component,
            "ema_structure": slope_component,
            "entry_location": location_component,
        }
        total_weight = sum(self.weights.values())
        components = {
            name: round(100.0 * raw.get(name, 0.0), 2)
            for name in self.weights
        }
        score = sum(self.weights[name] * raw.get(name, 0.0) for name in self.weights) / total_weight
        return QualityAssessment(round(100.0 * self._clamp(score), 2), components)
