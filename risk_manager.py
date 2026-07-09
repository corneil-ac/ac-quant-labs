from __future__ import annotations

from datetime import datetime, timedelta


class RiskManager:
    def __init__(
        self,
        logger,
        broker,
        max_total_pairs: int,
        cooldown_minutes: int,
    ):
        self.logger = logger
        self.broker = broker
        self.max_total_pairs = max_total_pairs
        self.cooldown = timedelta(minutes=cooldown_minutes)
        self.last_trade_time: dict[str, datetime] = {}

    @staticmethod
    def pair_key(symbol1: str, symbol2: str) -> str:
        return f"{symbol1}_{symbol2}"

    def mark_trade_time(self, symbol1: str, symbol2: str) -> None:
        self.last_trade_time[self.pair_key(symbol1, symbol2)] = datetime.now()

    def cooldown_remaining(self, symbol1: str, symbol2: str):
        key = self.pair_key(symbol1, symbol2)
        last = self.last_trade_time.get(key)
        if last is None:
            return None

        remaining = self.cooldown - (datetime.now() - last)
        if remaining.total_seconds() > 0:
            return remaining

        return None

    def can_open_pair(self, symbol1: str, symbol2: str) -> tuple[bool, str]:
        open_symbols = self.broker.open_symbols()

        if symbol1 in open_symbols or symbol2 in open_symbols:
            return False, "symbol already in use"

        total_pairs = self.broker.count_total_pairs()
        if total_pairs >= self.max_total_pairs:
            return False, f"max total pairs reached: {total_pairs}/{self.max_total_pairs}"

        remaining = self.cooldown_remaining(symbol1, symbol2)
        if remaining is not None:
            mins = int(remaining.total_seconds() // 60)
            secs = int(remaining.total_seconds() % 60)
            return False, f"cooldown {mins:02d}:{secs:02d} remaining"

        return True, "ok"
