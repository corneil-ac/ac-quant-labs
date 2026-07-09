from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass
class Signal:
    symbol1: str
    symbol2: str
    z: float
    beta: float
    action: str  # LONG, SHORT, NONE
    reason: str


class PairStrategy:
    def __init__(self, window_beta: int, window_z: int, entry_z: float, exit_z: float):
        self.window_beta = window_beta
        self.window_z = window_z
        self.entry_z = entry_z
        self.exit_z = exit_z

    def calculate(self, data: pd.DataFrame, symbol1: str, symbol2: str) -> Signal | None:
        if data.empty or len(data) < max(self.window_beta, self.window_z) + 5:
            return None

        df = data.copy()

        cov = df[symbol1].rolling(self.window_beta).cov(df[symbol2])
        var = df[symbol2].rolling(self.window_beta).var()

        df["BETA"] = cov / var
        df["SPREAD"] = df[symbol1] - df["BETA"] * df[symbol2]
        df["MEAN"] = df["SPREAD"].rolling(self.window_z).mean()
        df["STD"] = df["SPREAD"].rolling(self.window_z).std()
        df["Z"] = (df["SPREAD"] - df["MEAN"]) / df["STD"]

        df = df.dropna()
        if df.empty:
            return None

        current = df.iloc[-1]
        z = float(current["Z"])
        beta = float(current["BETA"])

        if z > self.entry_z:
            return Signal(symbol1, symbol2, z, beta, "SHORT", f"z {z:.2f} > entry {self.entry_z}")
        elif z < -self.entry_z:
            return Signal(symbol1, symbol2, z, beta, "LONG", f"z {z:.2f} < -entry {self.entry_z}")

        return Signal(symbol1, symbol2, z, beta, "NONE", "no entry")
