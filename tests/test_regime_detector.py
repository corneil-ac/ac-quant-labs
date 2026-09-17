import pandas as pd

from regime_detector import MarketRegime, RegimeDetector


def make_frame(closes, spread=0.2):
    rows = []
    for i, close in enumerate(closes):
        rows.append({
            "time": i,
            "open": close - 0.02,
            "high": close + spread,
            "low": close - spread,
            "close": close,
        })
    return pd.DataFrame(rows)


def test_insufficient_data_is_unstable():
    detector = RegimeDetector()
    result = detector.classify(make_frame([100 + i * 0.1 for i in range(20)]))
    assert result.regime is MarketRegime.UNSTABLE
    assert result.metrics["sufficient_data"] is False


def test_strong_trend_classification():
    detector = RegimeDetector(high_vol_ratio=10.0, low_vol_ratio=0.0)
    closes = [100 + i * 0.25 for i in range(90)]
    result = detector.classify(make_frame(closes, spread=0.35))
    assert result.regime in {MarketRegime.STRONG_TREND, MarketRegime.WEAK_TREND}
    assert result.metrics["directional_alignment"] is True


def test_low_volatility_classification():
    detector = RegimeDetector(low_vol_ratio=1.01, high_vol_ratio=10.0)
    closes = [100 + (i % 2) * 0.01 for i in range(90)]
    result = detector.classify(make_frame(closes, spread=0.01))
    assert result.regime is MarketRegime.LOW_VOLATILITY


def test_range_classification():
    detector = RegimeDetector(high_vol_ratio=10.0, low_vol_ratio=0.0,
                              weak_adx=100.0, range_ema_spread_atr=5.0)
    closes = [100 + ((i % 10) - 5) * 0.02 for i in range(90)]
    result = detector.classify(make_frame(closes, spread=0.2))
    assert result.regime is MarketRegime.RANGE


def test_classification_is_deterministic():
    detector = RegimeDetector()
    frame = make_frame([100 + i * 0.05 for i in range(90)], spread=0.15)
    first = detector.classify(frame)
    second = detector.classify(frame)
    assert first == second
