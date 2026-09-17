import pytest

from trade_quality_scorer import TradeQualityScorer


def test_high_quality_setup_scores_above_marginal_setup():
    scorer = TradeQualityScorer()
    high = scorer.score(regime="STRONG_TREND", adx=40, rsi=65, direction="BUY",
                        ema_distance_atr=0.2, ema_slope_atr=0.15,
                        module="MOMENTUM_CONTINUATION")
    marginal = scorer.score(regime="RANGE", adx=18, rsi=52, direction="BUY",
                            ema_distance_atr=0.7, ema_slope_atr=0.01,
                            module="EMA20_PULLBACK")
    assert 0 <= marginal.score < high.score <= 100
    assert high.components.keys() == marginal.components.keys()


def test_conflicting_setup_is_penalized_but_normalized():
    scorer = TradeQualityScorer()
    result = scorer.score(regime="UNSTABLE", adx=12, rsi=45, direction="BUY",
                          ema_distance_atr=2.5, ema_slope_atr=0.0,
                          module="BREAKOUT_CONTINUATION")
    assert 0 <= result.score <= 100
    assert result.components["regime"] == 0


def test_sell_momentum_is_direction_aware():
    scorer = TradeQualityScorer()
    strong_sell = scorer.score(regime="STRONG_TREND", adx=35, rsi=35, direction="SELL",
                               ema_distance_atr=0.3, ema_slope_atr=-0.12,
                               module="MOMENTUM_CONTINUATION")
    weak_sell = scorer.score(regime="STRONG_TREND", adx=35, rsi=65, direction="SELL",
                             ema_distance_atr=0.3, ema_slope_atr=-0.12,
                             module="MOMENTUM_CONTINUATION")
    assert strong_sell.score > weak_sell.score


def test_scoring_is_deterministic():
    scorer = TradeQualityScorer()
    kwargs = dict(regime="WEAK_TREND", adx=27, rsi=57, direction="BUY",
                  ema_distance_atr=0.25, ema_slope_atr=0.07, module="NEAR_EMA")
    assert scorer.score(**kwargs) == scorer.score(**kwargs)


def test_invalid_weights_rejected():
    with pytest.raises(ValueError):
        TradeQualityScorer({"regime": 0.0})
