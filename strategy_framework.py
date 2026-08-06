from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Mapping

import pandas as pd


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class StrategySignal:
    symbol: str
    action: SignalAction
    signal_candle_timestamp: datetime | pd.Timestamp | None
    entry_reference: float | None
    stop_loss: float | None
    take_profit: float | None
    strategy_name: str
    timeframe: str
    reason: str


class TradingStrategy(ABC):
    name: str

    @abstractmethod
    def evaluate(
        self, symbol: str, candles: Mapping[str, pd.DataFrame]
    ) -> StrategySignal:
        """Evaluate closed candles and return a complete, executable signal."""


class StrategyRegistry:
    def __init__(self) -> None:
        self._strategies: dict[str, type[TradingStrategy]] = {}

    def register(self, name: str, strategy_type: type[TradingStrategy]) -> None:
        if not issubclass(strategy_type, TradingStrategy):
            raise TypeError("registered strategies must implement TradingStrategy")
        self._strategies[name.casefold()] = strategy_type

    def create(self, name: str, **kwargs) -> TradingStrategy:
        try:
            strategy_type = self._strategies[name.casefold()]
        except KeyError as exc:
            raise ValueError(f"Unknown strategy: {name}") from exc
        return strategy_type(**kwargs)


strategy_registry = StrategyRegistry()
