from __future__ import annotations

import time

import pandas as pd
import MetaTrader5 as mt5


class DataManager:
    REQUIRED_CANDLE_COLUMNS = {"time", "open", "high", "low", "close"}

    def __init__(
        self,
        logger,
        timeframe,
        history_bars: int,
        fetch_retries: int = 3,
        retry_seconds: float = 2,
        recovery_wait_seconds: float = 1,
    ):
        self.logger = logger
        self.timeframe = timeframe
        self.history_bars = history_bars
        self.fetch_retries = max(1, fetch_retries)
        self.retry_seconds = max(0, retry_seconds)
        self.recovery_wait_seconds = max(0, recovery_wait_seconds)
        self._recovery_attempted_this_scan = False

    def begin_scan(self) -> None:
        """Reset the scan-scoped reconnect guard.

        A single broken feed can affect every symbol.  This guard prevents each
        symbol/timeframe from independently restarting MT5 during one scan.
        """
        self._recovery_attempted_this_scan = False

    @staticmethod
    def _timeframe_name(timeframe) -> str:
        return str(timeframe)

    def _fetch_once(self, symbol: str, timeframe, bars: int):
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 1, bars)
        if rates is None:
            return None, "None"
        try:
            candles = pd.DataFrame(rates)
        except (TypeError, ValueError):
            return None, "malformed"
        if candles.empty:
            return None, "empty"
        if not self.REQUIRED_CANDLE_COLUMNS.issubset(candles.columns):
            return None, "malformed"
        return candles.sort_values("time").reset_index(drop=True), None

    def _fetch_with_retries(self, symbol: str, timeframe, bars: int):
        for attempt in range(1, self.fetch_retries + 1):
            candles, failure = self._fetch_once(symbol, timeframe, bars)
            if candles is not None:
                if attempt > 1:
                    self.logger.info(
                        "%s timeframe=%s: candle fetch succeeded on attempt=%s",
                        symbol, self._timeframe_name(timeframe), attempt,
                    )
                return candles
            self.logger.error(
                "%s timeframe=%s: candle fetch failure type=%s attempt=%s/%s "
                "mt5.last_error=%r",
                symbol, self._timeframe_name(timeframe), failure, attempt,
                self.fetch_retries, mt5.last_error(),
            )
            if attempt < self.fetch_retries and self.retry_seconds:
                time.sleep(self.retry_seconds)
        return None

    def _log_connection_health(self, symbol: str, timeframe) -> tuple[object, object]:
        terminal = mt5.terminal_info()
        account = mt5.account_info()
        connected = terminal is not None and bool(getattr(terminal, "connected", False))
        self.logger.warning(
            "%s timeframe=%s: MT5 connection health terminal_present=%s "
            "connected=%s account_present=%s mt5.last_error=%r",
            symbol, self._timeframe_name(timeframe), terminal is not None,
            connected, account is not None, mt5.last_error(),
        )
        return terminal, account

    def _recover(self, symbol: str, timeframe) -> bool:
        self._recovery_attempted_this_scan = True
        self.logger.warning(
            "MT5 DATA FEED RECOVERY STARTING | symbol=%s timeframe=%s",
            symbol, self._timeframe_name(timeframe),
        )
        mt5.shutdown()
        if self.recovery_wait_seconds:
            time.sleep(self.recovery_wait_seconds)
        initialized = bool(mt5.initialize())
        terminal = mt5.terminal_info() if initialized else None
        account = mt5.account_info() if initialized else None
        connected = terminal is not None and bool(getattr(terminal, "connected", False))
        selected = bool(mt5.symbol_select(symbol, True)) if connected and account is not None else False
        if not (initialized and connected and account is not None and selected):
            self.logger.critical(
                "MT5 DATA FEED RECOVERY FAILED | symbol=%s timeframe=%s "
                "initialized=%s terminal_present=%s connected=%s "
                "account_present=%s symbol_selected=%s mt5.last_error=%r",
                symbol, self._timeframe_name(timeframe), initialized,
                terminal is not None, connected, account is not None, selected,
                mt5.last_error(),
            )
            return False
        return True

    def get_pair_data(self, symbol1: str, symbol2: str) -> pd.DataFrame:
        r1 = mt5.copy_rates_from_pos(symbol1, self.timeframe, 0, self.history_bars)
        r2 = mt5.copy_rates_from_pos(symbol2, self.timeframe, 0, self.history_bars)

        if r1 is None or r2 is None:
            self.logger.error(f"{symbol1}/{symbol2}: copy_rates_from_pos returned None")
            return pd.DataFrame()

        df1 = pd.DataFrame(r1)
        df2 = pd.DataFrame(r2)

        if df1.empty or df2.empty or "close" not in df1.columns or "close" not in df2.columns:
            self.logger.error(f"{symbol1}/{symbol2}: missing candle data")
            return pd.DataFrame()

        # Align by candle time, not row position. This is safer across symbols.
        df1 = df1[["time", "close"]].rename(columns={"close": symbol1})
        df2 = df2[["time", "close"]].rename(columns={"close": symbol2})

        df = pd.merge(df1, df2, on="time", how="inner")
        return df.dropna()

    def get_closed_candles(self, symbol: str, timeframe, bars: int | None = None) -> pd.DataFrame:
        """Return completed candles only (MT5 position zero is still forming)."""
        count = bars or self.history_bars
        candles = self._fetch_with_retries(symbol, timeframe, count)
        if candles is not None:
            return candles

        self._log_connection_health(symbol, timeframe)
        if self._recovery_attempted_this_scan:
            self.logger.error(
                "%s timeframe=%s: DATA UNAVAILABLE / DATA FEED FAILURE; "
                "scan recovery already attempted",
                symbol, self._timeframe_name(timeframe),
            )
            return pd.DataFrame()

        if not self._recover(symbol, timeframe):
            return pd.DataFrame()

        # One post-recovery retry sequence, with no recursive recovery path.
        candles = self._fetch_with_retries(symbol, timeframe, count)
        if candles is not None:
            self.logger.warning(
                "MT5 DATA FEED RECOVERED | symbol=%s timeframe=%s",
                symbol, self._timeframe_name(timeframe),
            )
            return candles
        self.logger.critical(
            "MT5 DATA FEED RECOVERY FAILED | symbol=%s timeframe=%s "
            "post-recovery candle fetch failed mt5.last_error=%r",
            symbol, self._timeframe_name(timeframe), mt5.last_error(),
        )
        return pd.DataFrame()
