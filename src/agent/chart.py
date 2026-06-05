from __future__ import annotations

import math
from dataclasses import dataclass

from agent.config import StrategySettings
from models import Candle


@dataclass(frozen=True)
class ChartAnalysis:
    return_1d: float = 0.0
    return_5d: float = 0.0
    return_1m: float = 0.0
    volatility_5d: float = 0.0
    volatility_1m: float = 0.0
    trend_slope_5d: float = 0.0
    trend_slope_1m: float = 0.0
    ma_fast: float = 0.0
    ma_slow: float = 0.0
    ma_alignment: float = 0.0
    ema_20: float = 0.0
    ema_50: float = 0.0
    ema_gap_pct: float = 0.0
    rsi_14: float = 50.0
    macd_histogram: float = 0.0
    stochastic_k: float = 50.0
    stochastic_d: float = 50.0
    atr_14_pct: float = 0.0
    adx_14: float = 0.0
    cci_20: float = 0.0
    bollinger_bandwidth: float = 0.0
    bollinger_percent_b: float = 0.5
    obv_slope: float = 0.0
    vwap_distance_pct: float = 0.0
    close_location_1d: float = 0.5
    range_pct_1d: float = 0.0
    volume_ratio_5_30: float = 1.0
    drawdown_from_1m_high: float = 0.0
    breakout_1m: float = 0.0
    support_bounce: float = 0.0
    overextension_penalty: float = 0.0
    downtrend_penalty: float = 0.0
    trend_quality: float = 0.0
    momentum_strength: float = 0.5
    micro_volatility_burst: float = 0.0
    micro_liquidity_stress: float = 0.0
    micro_range_expansion: float = 0.0
    micro_close_imbalance: float = 0.5
    micro_gap_pressure: float = 0.0
    micro_order_flow_bias: float = 0.0
    chart_score: float = 0.5

    def as_features(self) -> dict[str, float]:
        return {
            "chart_return_1d": self.return_1d,
            "chart_return_5d": self.return_5d,
            "chart_return_1m": self.return_1m,
            "chart_volatility_5d": self.volatility_5d,
            "chart_volatility_1m": self.volatility_1m,
            "chart_trend_slope_5d": self.trend_slope_5d,
            "chart_trend_slope_1m": self.trend_slope_1m,
            "chart_ma_fast": self.ma_fast,
            "chart_ma_slow": self.ma_slow,
            "chart_ma_alignment": self.ma_alignment,
            "chart_ema_20": self.ema_20,
            "chart_ema_50": self.ema_50,
            "chart_ema_gap_pct": self.ema_gap_pct,
            "chart_rsi_14": self.rsi_14,
            "chart_macd_histogram": self.macd_histogram,
            "chart_stochastic_k": self.stochastic_k,
            "chart_stochastic_d": self.stochastic_d,
            "chart_atr_14_pct": self.atr_14_pct,
            "chart_adx_14": self.adx_14,
            "chart_cci_20": self.cci_20,
            "chart_bollinger_bandwidth": self.bollinger_bandwidth,
            "chart_bollinger_percent_b": self.bollinger_percent_b,
            "chart_obv_slope": self.obv_slope,
            "chart_vwap_distance_pct": self.vwap_distance_pct,
            "chart_close_location_1d": self.close_location_1d,
            "chart_range_pct_1d": self.range_pct_1d,
            "chart_volume_ratio_5_30": self.volume_ratio_5_30,
            "chart_drawdown_from_1m_high": self.drawdown_from_1m_high,
            "chart_breakout_1m": self.breakout_1m,
            "chart_support_bounce": self.support_bounce,
            "chart_overextension_penalty": self.overextension_penalty,
            "chart_downtrend_penalty": self.downtrend_penalty,
            "chart_trend_quality": self.trend_quality,
            "chart_momentum_strength": self.momentum_strength,
            "micro_volatility_burst": self.micro_volatility_burst,
            "micro_liquidity_stress": self.micro_liquidity_stress,
            "micro_range_expansion": self.micro_range_expansion,
            "micro_close_imbalance": self.micro_close_imbalance,
            "micro_gap_pressure": self.micro_gap_pressure,
            "micro_order_flow_bias": self.micro_order_flow_bias,
            "chart_score": self.chart_score,
        }


class ChartAnalyzer:
    def __init__(self, strategy: StrategySettings) -> None:
        self.strategy = strategy

    def analyze(self, candles: list[Candle]) -> ChartAnalysis:
        if len(candles) < 2:
            return ChartAnalysis()

        day_window = self.strategy.previous_day_window
        week_window = self.strategy.previous_week_window
        month_window = self.strategy.previous_month_window
        volatility_window = self.strategy.volatility_window

        return_1d = _window_return(candles, day_window)
        return_5d = _window_return(candles, week_window)
        return_1m = _window_return(candles, month_window)
        volatility_5d = _volatility(candles, week_window)
        volatility_1m = _volatility(candles, volatility_window)
        trend_slope_5d = _trend_slope(candles, week_window)
        trend_slope_1m = _trend_slope(candles, month_window)
        ma_fast = _simple_ma(candles, self.strategy.fast_ma_period)
        ma_slow = _simple_ma(candles, self.strategy.slow_ma_period)
        current_price = candles[-1].close
        ma_alignment = (ma_fast - ma_slow) / current_price if current_price > 0 else 0.0
        ema_20 = _ema_value(candles, 20)
        ema_50 = _ema_value(candles, 50)
        ema_gap_pct = (ema_20 - ema_50) / current_price if current_price > 0 else 0.0
        rsi_14 = _rsi(candles, self.strategy.rsi_period)
        macd_histogram = _macd_histogram(candles)
        stochastic_k, stochastic_d = _stochastic(candles, 14, 3)
        atr_14_pct = _atr_pct(candles, 14)
        adx_14 = _adx(candles, 14)
        cci_20 = _cci(candles, 20)
        bollinger_bandwidth, bollinger_percent_b = _bollinger(candles, 20, 2.0)
        obv_slope = _obv_slope(candles, 20)
        vwap_distance_pct = _vwap_distance_pct(candles, 20)
        close_location_1d = _close_location(candles[-1])
        range_pct_1d = _range_pct(candles[-1])
        volume_ratio = _volume_ratio(candles, short=5, long=30)
        drawdown = _drawdown_from_high(candles, month_window)
        breakout_1m = _breakout_score(candles, month_window)
        support_bounce = _support_bounce_score(candles, month_window)
        trend_quality = _trend_quality(candles, month_window)
        micro_volatility_burst = _volatility_burst(candles, volatility_window, week_window)
        micro_liquidity_stress = _liquidity_stress(volume_ratio, range_pct_1d, atr_14_pct)
        micro_range_expansion = _range_expansion(candles, week_window)
        micro_close_imbalance = close_location_1d
        micro_gap_pressure = _gap_pressure(candles)
        micro_order_flow_bias = _order_flow_bias(candles)
        momentum_strength = _clamp(
            0.22 * (0.5 + return_1d * 8)
            + 0.18 * (0.5 + return_5d * 6)
            + 0.16 * (0.5 + trend_slope_5d * 160)
            + 0.12 * (0.5 + ema_gap_pct * 10)
            + 0.10 * (stochastic_k / 100)
            + 0.08 * (adx_14 / 50)
            + 0.08 * _clamp(0.5 + obv_slope * 25)
            + 0.06 * _clamp(0.5 + vwap_distance_pct * 8)
        )

        overextension_penalty = _clamp((rsi_14 - 72) / 18) + _clamp((return_5d - 0.10) / 0.12)
        downtrend_penalty = _clamp((-trend_slope_1m * 120) + (-ma_alignment * 6))

        trend_component = _clamp(0.5 + trend_slope_1m * 85 + ma_alignment * 4)
        short_component = _clamp(0.5 + trend_slope_5d * 120 + return_1d * 4)
        rsi_component = _rsi_component(rsi_14)
        macd_component = _clamp(0.5 + macd_histogram * 25)
        volume_component = _clamp((volume_ratio - 0.8) / 1.3)
        location_component = _clamp(close_location_1d)
        breakout_component = _clamp(max(breakout_1m, support_bounce))
        indicator_component = _clamp(
            0.22 * (stochastic_k / 100)
            + 0.18 * _clamp(0.5 + ema_gap_pct * 10)
            + 0.14 * _clamp(0.5 + obv_slope * 25)
            + 0.12 * _clamp(0.5 + vwap_distance_pct * 6)
            + 0.10 * _clamp(0.5 + cci_20 / 250)
            + 0.12 * _clamp(0.5 + bollinger_percent_b - 0.5)
            + 0.12 * _clamp(adx_14 / 40)
        )

        gross_score = (
            0.20 * trend_component
            + 0.15 * short_component
            + 0.12 * rsi_component
            + 0.10 * macd_component
            + 0.10 * volume_component
            + 0.08 * location_component
            + 0.10 * breakout_component
            + 0.15 * indicator_component
        )
        chart_score = _clamp(
            gross_score
            + 0.06 * momentum_strength
            - 0.09 * overextension_penalty
            - 0.14 * downtrend_penalty
            - 0.05 * _clamp(atr_14_pct / 0.08)
        )

        return ChartAnalysis(
            return_1d=return_1d,
            return_5d=return_5d,
            return_1m=return_1m,
            volatility_5d=volatility_5d,
            volatility_1m=volatility_1m,
            trend_slope_5d=trend_slope_5d,
            trend_slope_1m=trend_slope_1m,
            ma_fast=ma_fast,
            ma_slow=ma_slow,
            ma_alignment=ma_alignment,
            ema_20=ema_20,
            ema_50=ema_50,
            ema_gap_pct=ema_gap_pct,
            rsi_14=rsi_14,
            macd_histogram=macd_histogram,
            stochastic_k=stochastic_k,
            stochastic_d=stochastic_d,
            atr_14_pct=atr_14_pct,
            adx_14=adx_14,
            cci_20=cci_20,
            bollinger_bandwidth=bollinger_bandwidth,
            bollinger_percent_b=bollinger_percent_b,
            obv_slope=obv_slope,
            vwap_distance_pct=vwap_distance_pct,
            close_location_1d=close_location_1d,
            range_pct_1d=range_pct_1d,
            volume_ratio_5_30=volume_ratio,
            drawdown_from_1m_high=drawdown,
            breakout_1m=breakout_1m,
            support_bounce=support_bounce,
            overextension_penalty=overextension_penalty,
            downtrend_penalty=downtrend_penalty,
            trend_quality=trend_quality,
            momentum_strength=momentum_strength,
            micro_volatility_burst=micro_volatility_burst,
            micro_liquidity_stress=micro_liquidity_stress,
            micro_range_expansion=micro_range_expansion,
            micro_close_imbalance=micro_close_imbalance,
            micro_gap_pressure=micro_gap_pressure,
            micro_order_flow_bias=micro_order_flow_bias,
            chart_score=chart_score,
        )


def _window_return(candles: list[Candle], window: int) -> float:
    if len(candles) < window + 1:
        return 0.0
    start = candles[-window - 1].close
    end = candles[-1].close
    if start <= 0:
        return 0.0
    return (end - start) / start


def _simple_ma(candles: list[Candle], window: int) -> float:
    if len(candles) < window:
        return candles[-1].close if candles else 0.0
    return sum(candle.close for candle in candles[-window:]) / window


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    output = [values[0]]
    for value in values[1:]:
        output.append((value * alpha) + output[-1] * (1 - alpha))
    return output


def _ema_value(candles: list[Candle], period: int) -> float:
    if not candles:
        return 0.0
    return _ema([candle.close for candle in candles], period)[-1]


def _macd_histogram(candles: list[Candle]) -> float:
    if len(candles) < 35:
        return 0.0
    closes = [candle.close for candle in candles]
    ema_12 = _ema(closes, 12)
    ema_26 = _ema(closes, 26)
    macd = [fast - slow for fast, slow in zip(ema_12[-len(ema_26) :], ema_26)]
    signal = _ema(macd, 9)
    if not signal or closes[-1] <= 0:
        return 0.0
    return (macd[-1] - signal[-1]) / closes[-1]


def _rsi(candles: list[Candle], period: int) -> float:
    if len(candles) < period + 1:
        return 50.0
    gains = []
    losses = []
    selected = candles[-period - 1 :]
    for previous, current in zip(selected, selected[1:]):
        change = current.close - previous.close
        gains.append(max(change, 0.0))
        losses.append(abs(min(change, 0.0)))
    average_gain = sum(gains) / period
    average_loss = sum(losses) / period
    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0
    relative_strength = average_gain / average_loss
    return 100 - (100 / (1 + relative_strength))


def _rsi_component(rsi: float) -> float:
    if 52 <= rsi <= 68:
        return 1.0
    if 45 <= rsi < 52:
        return 0.55 + (rsi - 45) / 15
    if 68 < rsi <= 76:
        return 0.85 - (rsi - 68) / 20
    if rsi < 45:
        return _clamp(rsi / 75)
    return _clamp(1 - (rsi - 76) / 18)


def _stochastic(candles: list[Candle], period: int, smooth: int) -> tuple[float, float]:
    if len(candles) < period:
        return 50.0, 50.0
    values: list[float] = []
    for end in range(period, len(candles) + 1):
        window = candles[end - period : end]
        high = max(candle.high for candle in window)
        low = min(candle.low for candle in window)
        if high <= low:
            values.append(50.0)
        else:
            values.append(((window[-1].close - low) / (high - low)) * 100)
    if not values:
        return 50.0, 50.0
    k = values[-1]
    d_window = values[-smooth:] if len(values) >= smooth else values
    d = sum(d_window) / len(d_window)
    return k, d


def _true_range(current: Candle, previous_close: float) -> float:
    return max(
        current.high - current.low,
        abs(current.high - previous_close),
        abs(current.low - previous_close),
    )


def _atr_pct(candles: list[Candle], period: int) -> float:
    if len(candles) < period + 1:
        return 0.0
    ranges = [
        _true_range(current, previous.close)
        for previous, current in zip(candles[-period - 1 : -1], candles[-period:])
    ]
    close = candles[-1].close
    if close <= 0 or not ranges:
        return 0.0
    return (sum(ranges) / len(ranges)) / close


def _adx(candles: list[Candle], period: int) -> float:
    if len(candles) < period + 1:
        return 0.0
    selected = candles[-period - 1 :]
    tr_values: list[float] = []
    plus_dm_values: list[float] = []
    minus_dm_values: list[float] = []
    for previous, current in zip(selected, selected[1:]):
        up_move = current.high - previous.high
        down_move = previous.low - current.low
        plus_dm_values.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm_values.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        tr_values.append(_true_range(current, previous.close))
    tr_sum = sum(tr_values)
    if tr_sum <= 0:
        return 0.0
    plus_di = 100 * (sum(plus_dm_values) / tr_sum)
    minus_di = 100 * (sum(minus_dm_values) / tr_sum)
    if plus_di + minus_di <= 0:
        return 0.0
    return abs(plus_di - minus_di) / (plus_di + minus_di) * 100


def _cci(candles: list[Candle], period: int) -> float:
    if len(candles) < period:
        return 0.0
    selected = candles[-period:]
    typical_prices = [(candle.high + candle.low + candle.close) / 3 for candle in selected]
    sma = sum(typical_prices) / len(typical_prices)
    mean_deviation = sum(abs(value - sma) for value in typical_prices) / len(typical_prices)
    if mean_deviation == 0:
        return 0.0
    return (typical_prices[-1] - sma) / (0.015 * mean_deviation)


def _bollinger(candles: list[Candle], period: int, std_mult: float) -> tuple[float, float]:
    if len(candles) < period:
        return 0.0, 0.5
    closes = [candle.close for candle in candles[-period:]]
    mean = sum(closes) / len(closes)
    variance = sum((value - mean) ** 2 for value in closes) / len(closes)
    std = math.sqrt(variance)
    upper = mean + std_mult * std
    lower = mean - std_mult * std
    if mean <= 0 or upper <= lower:
        return 0.0, 0.5
    bandwidth = (upper - lower) / mean
    percent_b = (closes[-1] - lower) / (upper - lower)
    return bandwidth, _clamp(percent_b)


def _obv_slope(candles: list[Candle], window: int) -> float:
    if len(candles) < 2:
        return 0.0
    selected = candles[-window:]
    obv = [0.0]
    for previous, current in zip(selected, selected[1:]):
        if current.close > previous.close:
            obv.append(obv[-1] + current.volume)
        elif current.close < previous.close:
            obv.append(obv[-1] - current.volume)
        else:
            obv.append(obv[-1])
    price = selected[-1].close
    if price <= 0 or len(obv) < 2:
        return 0.0
    return (obv[-1] - obv[0]) / max(len(obv) - 1, 1) / max(price * 100_000, 1)


def _vwap_distance_pct(candles: list[Candle], window: int) -> float:
    if len(candles) < window:
        return 0.0
    selected = candles[-window:]
    total_volume = sum(candle.volume for candle in selected)
    if total_volume <= 0:
        return 0.0
    vwap = sum(((candle.high + candle.low + candle.close) / 3) * candle.volume for candle in selected) / total_volume
    close = selected[-1].close
    if close <= 0:
        return 0.0
    return (close - vwap) / close


def _trend_slope(candles: list[Candle], window: int) -> float:
    if len(candles) < window + 1:
        return 0.0
    selected = candles[-window:]
    closes = [math.log(max(candle.close, 0.0001)) for candle in selected]
    n = len(closes)
    x_mean = (n - 1) / 2
    y_mean = sum(closes) / n
    denominator = sum((index - x_mean) ** 2 for index in range(n))
    if denominator == 0:
        return 0.0
    return sum((index - x_mean) * (value - y_mean) for index, value in enumerate(closes)) / denominator


def _trend_quality(candles: list[Candle], window: int) -> float:
    if len(candles) < window + 1:
        return 0.0
    selected = candles[-window:]
    up_days = 0
    for previous, current in zip(selected, selected[1:]):
        if current.close >= previous.close:
            up_days += 1
    return up_days / max(len(selected) - 1, 1)


def _volatility_burst(candles: list[Candle], short_window: int, reference_window: int) -> float:
    short_vol = _volatility(candles, max(short_window, 2))
    reference_vol = _volatility(candles, max(reference_window, 3))
    if reference_vol <= 0:
        return 0.0
    return _clamp((short_vol / reference_vol - 1.0) / 1.5)


def _liquidity_stress(volume_ratio: float, range_pct_1d: float, atr_14_pct: float) -> float:
    return _clamp(
        0.45 * _clamp((1.0 - min(volume_ratio, 1.0)) / 0.6)
        + 0.30 * _clamp(range_pct_1d / 0.035)
        + 0.25 * _clamp(atr_14_pct / 0.03)
    )


def _range_expansion(candles: list[Candle], window: int) -> float:
    if len(candles) < max(window, 3):
        return 0.0
    recent = [_range_pct(candle) for candle in candles[-3:]]
    baseline = [_range_pct(candle) for candle in candles[-window:]]
    baseline_mean = sum(baseline) / len(baseline) if baseline else 0.0
    if baseline_mean <= 0:
        return 0.0
    return _clamp(((sum(recent) / len(recent)) / baseline_mean - 1.0) / 2.0)


def _gap_pressure(candles: list[Candle]) -> float:
    if len(candles) < 2:
        return 0.0
    previous = candles[-2]
    current = candles[-1]
    if previous.close <= 0:
        return 0.0
    return _clamp(abs(current.open - previous.close) / previous.close / 0.03)


def _order_flow_bias(candles: list[Candle]) -> float:
    if not candles:
        return 0.0
    recent = candles[-10:] if len(candles) >= 10 else candles
    weighted_bias = 0.0
    total_volume = 0.0
    for candle in recent:
        range_span = max(candle.high - candle.low, 0.0001)
        close_bias = ((candle.close - candle.low) - (candle.high - candle.close)) / range_span
        volume = max(candle.volume, 0.0)
        weighted_bias += close_bias * volume
        total_volume += volume
    if total_volume <= 0:
        return 0.0
    return _clamp(0.5 + (weighted_bias / total_volume) / 2.0) - 0.5


def _volatility(candles: list[Candle], window: int) -> float:
    if len(candles) < window + 1:
        return 0.0
    returns = []
    selected = candles[-window - 1 :]
    for previous, current in zip(selected, selected[1:]):
        if previous.close > 0:
            returns.append((current.close - previous.close) / previous.close)
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    return math.sqrt(variance)


def _close_location(candle: Candle) -> float:
    day_range = candle.high - candle.low
    if day_range <= 0:
        return 0.5
    return _clamp((candle.close - candle.low) / day_range)


def _range_pct(candle: Candle) -> float:
    if candle.close <= 0:
        return 0.0
    return (candle.high - candle.low) / candle.close


def _volume_ratio(candles: list[Candle], *, short: int, long: int) -> float:
    if len(candles) < long:
        return 1.0
    short_avg = sum(candle.volume for candle in candles[-short:]) / short
    long_avg = sum(candle.volume for candle in candles[-long:]) / long
    if long_avg <= 0:
        return 1.0
    return short_avg / long_avg


def _drawdown_from_high(candles: list[Candle], window: int) -> float:
    if len(candles) < 2:
        return 0.0
    selected = candles[-min(window, len(candles)) :]
    high = max(candle.high for candle in selected)
    if high <= 0:
        return 0.0
    return (candles[-1].close - high) / high


def _breakout_score(candles: list[Candle], window: int) -> float:
    if len(candles) < window + 1:
        return 0.0
    previous = candles[-window - 1 : -1]
    prior_high = max(candle.high for candle in previous)
    if prior_high <= 0:
        return 0.0
    return _clamp((candles[-1].close - prior_high) / prior_high / 0.03)


def _support_bounce_score(candles: list[Candle], window: int) -> float:
    if len(candles) < window:
        return 0.0
    selected = candles[-window:]
    support = min(candle.low for candle in selected)
    current = candles[-1]
    if support <= 0 or current.close <= 0:
        return 0.0
    near_support = _clamp(1 - ((current.low - support) / support) / 0.035)
    strong_close = _close_location(current)
    return _clamp(near_support * strong_close)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(min(value, high), low)
