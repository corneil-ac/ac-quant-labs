from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen


class CalendarProvider:
    """Downloads the economic calendar and maintains a timestamped local cache."""

    def __init__(
        self,
        logger,
        url: str,
        cache_path: str | Path,
        refresh_hours: int = 6,
        opener: Callable = urlopen,
    ):
        self.logger = logger
        self.url = url
        self.cache_path = Path(cache_path)
        self.refresh_interval = timedelta(hours=refresh_hours)
        self.opener = opener
        self.events: list[dict] = []
        self.fetched_at: datetime | None = None
        self._load_cache()

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def _load_cache(self) -> None:
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(payload["fetched_at"])
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            events = payload["events"]
            if not isinstance(events, list):
                raise ValueError("events must be a list")
            self.fetched_at = fetched_at.astimezone(timezone.utc)
            self.events = events
            self.logger.info(
                f"Calendar cache loaded | events={len(events)} | "
                f"fetched_at={self.fetched_at.isoformat()}"
            )
        except FileNotFoundError:
            self.logger.info("Calendar cache not found")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.logger.error(f"Calendar cache is invalid: {exc}")

    def is_stale(self, now: datetime | None = None) -> bool:
        now = now or self._utc_now()
        return self.fetched_at is None or now - self.fetched_at >= self.refresh_interval

    @property
    def available(self) -> bool:
        return bool(self.events) and not self.is_stale()

    def refresh(self, force: bool = False) -> bool:
        """Refresh when due. A failure leaves a still-fresh cache usable."""
        if not force and not self.is_stale():
            return True

        try:
            request = Request(self.url, headers={"User-Agent": "ac-quant-labs/1.0"})
            with self.opener(request, timeout=20) as response:
                events = json.load(response)
            if not isinstance(events, list):
                raise ValueError("calendar response must be a JSON list")

            fetched_at = self._utc_now()
            payload = {"fetched_at": fetched_at.isoformat(), "events": events}
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
            temporary_path.write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
            temporary_path.replace(self.cache_path)

            self.events = events
            self.fetched_at = fetched_at
            self.logger.info(f"Calendar refreshed | events={len(events)}")
            return True
        except Exception as exc:
            self.logger.error(f"Calendar refresh failed: {exc}")
            if self.is_stale():
                self.logger.error("Calendar cache is stale; new entries are blocked")
                return False
            self.logger.warning("Calendar refresh failed; using fresh cached calendar")
            return True
