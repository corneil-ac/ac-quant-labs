from __future__ import annotations

from datetime import datetime, timedelta, timezone


class CalendarFilter:
    """Blocks entries around relevant economic events."""

    def __init__(
        self,
        provider,
        minutes_before: int,
        minutes_after: int,
        blocked_impacts: set[str],
    ):
        self.provider = provider
        self.before = timedelta(minutes=minutes_before)
        self.after = timedelta(minutes=minutes_after)
        self.blocked_impacts = {impact.casefold() for impact in blocked_impacts}

    @staticmethod
    def _currencies(symbol: str) -> set[str]:
        symbol = symbol.upper()
        currencies = {symbol[:3], symbol[3:6]} if len(symbol) >= 6 else set()
        return {currency for currency in currencies if currency.isalpha()}

    @staticmethod
    def _event_time(event: dict) -> datetime | None:
        raw_date = event.get("date")
        if not raw_date:
            return None
        try:
            parsed = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def can_open_pair(
        self, symbol1: str, symbol2: str, now: datetime | None = None
    ) -> tuple[bool, str]:
        if not self.provider.available:
            return False, "economic calendar unavailable or stale"

        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        currencies = self._currencies(symbol1) | self._currencies(symbol2)

        for event in self.provider.events:
            if str(event.get("impact", "")).casefold() not in self.blocked_impacts:
                continue
            if str(event.get("country", "")).upper() not in currencies:
                continue
            event_time = self._event_time(event)
            if event_time is None:
                continue
            if event_time - self.before <= now <= event_time + self.after:
                title = event.get("title", "economic event")
                return False, (
                    f"calendar blackout: {event.get('country')} {title} "
                    f"at {event_time.isoformat()}"
                )

        return True, "ok"
