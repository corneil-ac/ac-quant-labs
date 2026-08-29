from __future__ import annotations

from datetime import datetime, timedelta


class RiskManager:
    def __init__(
        self,
        logger,
        broker,
        max_total_pairs: int,
        cooldown_minutes: int,
        max_positions_per_symbol: int = 1,
    ):
        if max_positions_per_symbol < 1:
            raise ValueError("max_positions_per_symbol must be at least 1")
        self.logger = logger
        self.broker = broker
        self.max_total_pairs = max_total_pairs
        self.max_positions_per_symbol = max_positions_per_symbol
        self.cooldown = timedelta(minutes=cooldown_minutes)
        self.last_trade_time: dict[str, datetime] = {}

    @staticmethod
    def pair_key(symbol1: str, symbol2: str) -> str:
        return f"{symbol1}_{symbol2}"

    def mark_trade_time(self, symbol1: str, symbol2: str | None = None) -> None:
        key = self.pair_key(symbol1, symbol2) if symbol2 else symbol1
        self.last_trade_time[key] = datetime.now()

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

    def can_open_symbol(self, symbol: str) -> tuple[bool, str]:
        """Apply portfolio and per-symbol limits to a trend entry.

        Positions are read once so that both checks use the same broker snapshot.
        A per-symbol limit greater than one enables deliberate scale-in entries;
        the cooldown still prevents repeated scans from filling every slot at once.
        """
        positions = self.broker.positions()
        symbol_positions = [position for position in positions if position.symbol == symbol]
        if len(symbol_positions) >= self.max_positions_per_symbol:
            return False, (
                "max positions for symbol reached: "
                f"{len(symbol_positions)}/{self.max_positions_per_symbol}"
            )
        if len(positions) >= self.max_total_pairs:
            return False, f"max total positions reached: {len(positions)}/{self.max_total_pairs}"
        last = self.last_trade_time.get(symbol)
        if last is not None:
            remaining = self.cooldown - (datetime.now() - last)
            if remaining.total_seconds() > 0:
                return False, "symbol cooldown active"
        return True, "ok"
