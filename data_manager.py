from __future__ import annotations

import pandas as pd
import MetaTrader5 as mt5


class DataManager:
    def __init__(self, logger, timeframe, history_bars: int):
        self.logger = logger
        self.timeframe = timeframe
        self.history_bars = history_bars

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
