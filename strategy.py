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
    profile_name: str
    threshold_used: float


class PairStrategy:
    def __init__(self, window_beta: int, window_z: int):
        self.window_beta = window_beta
        self.window_z = window_z

    def calculate(
        self,
        data: pd.DataFrame,
        symbol1: str,
        symbol2: str,
        profile: dict,
    ) -> Signal | None:
        profile_name = str(profile["name"])
        entry_z = float(profile["entry_z"])

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

        if z > entry_z:
            return Signal(
                symbol1, symbol2, z, beta, "SHORT",
                f"z {z:.2f} > entry {entry_z}", profile_name, entry_z,
            )
        elif z < -entry_z:
            return Signal(
                symbol1, symbol2, z, beta, "LONG",
                f"z {z:.2f} < -entry {entry_z}", profile_name, entry_z,
            )

        return Signal(
            symbol1, symbol2, z, beta, "NONE", "no entry", profile_name, entry_z
        )
