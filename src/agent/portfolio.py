from __future__ import annotations

from dataclasses import dataclass

from agent.config import RiskSettings, StrategySettings, StressScenarioSettings, UniverseSettings
from agent.regime import MarketRegime
from models import MarketSnapshot, PortfolioState


@dataclass(frozen=True)
class PortfolioOverlayReport:
    approved: bool
    adjusted_notional_usd: float
    reason: str
    hhi: float
    diversification_score: float
    var_95_pct: float
    cvar_95_pct: float
    expected_shortfall_95_pct: float
    max_stress_loss_pct: float
    scenario_losses: dict[str, float]


@dataclass(frozen=True)
class ScenarioDefinition:
    name: str
    benchmark_shock_pct: float
    volatility_multiplier: float
    liquidity_shock_pct: float
    idiosyncratic_shock_pct: float
    rates_shock_pct: float = 0.0
    usd_shock_pct: float = 0.0
    commodity_shock_pct: float = 0.0
    crypto_shock_pct: float = 0.0
    spread_widening_bps: float = 0.0
    sector_shocks: dict[str, float] | None = None


@dataclass(frozen=True)
class PortfolioRiskReport:
    var_95_pct: float
    cvar_95_pct: float
    var_99_pct: float
    cvar_99_pct: float
    expected_shortfall_95_pct: float
    expected_shortfall_95_usd: float
    tail_observation_count: int
    component_expected_shortfall: dict[str, float]
    marginal_expected_shortfall: dict[str, float]
    factor_exposures: dict[str, float]
    scenario_losses: dict[str, float]
    max_scenario_loss_pct: float
    hhi: float
    concentration_score: float

    def as_dict(self) -> dict[str, object]:
        return {
            "var_95_pct": self.var_95_pct,
            "cvar_95_pct": self.cvar_95_pct,
            "var_99_pct": self.var_99_pct,
            "cvar_99_pct": self.cvar_99_pct,
            "expected_shortfall_95_pct": self.expected_shortfall_95_pct,
            "expected_shortfall_95_usd": self.expected_shortfall_95_usd,
            "tail_observation_count": self.tail_observation_count,
            "component_expected_shortfall": self.component_expected_shortfall,
            "marginal_expected_shortfall": self.marginal_expected_shortfall,
            "factor_exposures": self.factor_exposures,
            "scenario_losses": self.scenario_losses,
            "max_scenario_loss_pct": self.max_scenario_loss_pct,
            "hhi": self.hhi,
            "concentration_score": self.concentration_score,
        }


class PortfolioOptimizer:
    def __init__(self, risk: RiskSettings, strategy: StrategySettings, universe: UniverseSettings) -> None:
        self.risk = risk
        self.strategy = strategy
        self.universe = universe

    def evaluate_candidate(
        self,
        *,
        symbol: str,
        target_notional_usd: float,
        portfolio: PortfolioState,
        all_snapshots: dict[str, MarketSnapshot],
        benchmark_symbol: str,
        market_regime: MarketRegime | None,
    ) -> PortfolioOverlayReport:
        if not self.risk.portfolio_optimization_enabled:
            return PortfolioOverlayReport(
                approved=True,
                adjusted_notional_usd=target_notional_usd,
                reason="portfolio_optimization_disabled",
                hhi=0.0,
                diversification_score=1.0,
                var_95_pct=0.0,
                cvar_95_pct=0.0,
                expected_shortfall_95_pct=0.0,
                max_stress_loss_pct=0.0,
                scenario_losses={},
            )

        benchmark_snapshot = all_snapshots.get(benchmark_symbol.upper())
        for multiplier in (1.0, 0.85, 0.7, 0.55, 0.4, 0.25):
            proposed = round(target_notional_usd * multiplier, 2)
            if proposed < self.risk.min_order_usd:
                continue
            weights = _projected_weights(symbol, proposed, portfolio)
            hhi = sum(weight * weight for weight in weights.values())
            diversification_score = max(0.0, 1.0 - hhi)
            risk_samples = _historical_portfolio_loss_samples(
                weights,
                all_snapshots,
                _recent_returns(benchmark_snapshot.candles if benchmark_snapshot else [], 60),
            )
            tail_metrics = _tail_risk_metrics(risk_samples, portfolio.nav_usd)
            scenario_losses = _scenario_losses(
                weights=weights,
                all_snapshots=all_snapshots,
                benchmark_snapshot=benchmark_snapshot,
                regime=market_regime,
                universe=self.universe,
                scenario_library=_scenario_library(market_regime, self.risk),
            )
            max_stress = max(scenario_losses.values(), default=0.0)
            if (
                hhi <= self.risk.max_portfolio_hhi
                and max_stress <= self.risk.max_projected_stress_loss_pct
                and tail_metrics["expected_shortfall_95_pct"] <= self.risk.max_expected_shortfall_pct
            ):
                reason = (
                    f"portfolio_overlay_ok adjusted_notional={proposed:.2f} "
                    f"hhi={hhi:.3f} diversification={diversification_score:.3f} "
                    f"max_stress={max_stress:.3%} es95={tail_metrics['expected_shortfall_95_pct']:.3%}"
                )
                return PortfolioOverlayReport(
                    approved=True,
                    adjusted_notional_usd=proposed,
                    reason=reason,
                    hhi=hhi,
                    diversification_score=diversification_score,
                    var_95_pct=tail_metrics["var_95_pct"],
                    cvar_95_pct=tail_metrics["cvar_95_pct"],
                    expected_shortfall_95_pct=tail_metrics["expected_shortfall_95_pct"],
                    max_stress_loss_pct=max_stress,
                    scenario_losses=scenario_losses,
                )

        final_weights = _projected_weights(symbol, target_notional_usd, portfolio)
        final_hhi = sum(weight * weight for weight in final_weights.values())
        final_tail_metrics = _tail_risk_metrics(
            _historical_portfolio_loss_samples(
                final_weights,
                all_snapshots,
                _recent_returns(benchmark_snapshot.candles if benchmark_snapshot else [], 60),
            ),
            portfolio.nav_usd,
        )
        final_losses = _scenario_losses(
            weights=final_weights,
            all_snapshots=all_snapshots,
            benchmark_snapshot=benchmark_snapshot,
            regime=market_regime,
            universe=self.universe,
            scenario_library=_scenario_library(market_regime, self.risk),
        )
        final_max_stress = max(final_losses.values(), default=0.0)
        reject_reason = "portfolio_stress_limit"
        if final_hhi > self.risk.max_portfolio_hhi:
            reject_reason = "portfolio_concentration_limit"
        elif final_tail_metrics["expected_shortfall_95_pct"] > self.risk.max_expected_shortfall_pct:
            reject_reason = "portfolio_expected_shortfall_limit"
        return PortfolioOverlayReport(
            approved=False,
            adjusted_notional_usd=0.0,
            reason=reject_reason,
            hhi=final_hhi,
            diversification_score=max(0.0, 1.0 - final_hhi),
            var_95_pct=final_tail_metrics["var_95_pct"],
            cvar_95_pct=final_tail_metrics["cvar_95_pct"],
            expected_shortfall_95_pct=final_tail_metrics["expected_shortfall_95_pct"],
            max_stress_loss_pct=final_max_stress,
            scenario_losses=final_losses,
        )


class PortfolioRiskAnalyzer:
    def __init__(self, risk: RiskSettings, strategy: StrategySettings, universe: UniverseSettings) -> None:
        self.risk = risk
        self.strategy = strategy
        self.universe = universe

    def evaluate(
        self,
        *,
        portfolio: PortfolioState,
        all_snapshots: dict[str, MarketSnapshot],
        benchmark_symbol: str,
        market_regime: MarketRegime | None,
    ) -> PortfolioRiskReport:
        weights = _current_weights(portfolio)
        benchmark_snapshot = all_snapshots.get(benchmark_symbol.upper())
        benchmark_returns = _recent_returns(benchmark_snapshot.candles if benchmark_snapshot else [], 60)
        loss_samples = _historical_portfolio_loss_samples(weights, all_snapshots, benchmark_returns)
        tail_metrics = _tail_risk_metrics(loss_samples, portfolio.nav_usd)
        scenario_losses = _scenario_losses(
            weights=weights,
            all_snapshots=all_snapshots,
            benchmark_snapshot=benchmark_snapshot,
            regime=market_regime,
            universe=self.universe,
            scenario_library=_scenario_library(market_regime, self.risk),
        )
        factor_exposures = _factor_exposures(
            weights,
            all_snapshots,
            benchmark_returns,
            universe=self.universe,
        )
        hhi = sum(weight * weight for weight in weights.values())
        return PortfolioRiskReport(
            var_95_pct=tail_metrics["var_95_pct"],
            cvar_95_pct=tail_metrics["cvar_95_pct"],
            var_99_pct=tail_metrics["var_99_pct"],
            cvar_99_pct=tail_metrics["cvar_99_pct"],
            expected_shortfall_95_pct=tail_metrics["expected_shortfall_95_pct"],
            expected_shortfall_95_usd=tail_metrics["expected_shortfall_95_usd"],
            tail_observation_count=int(tail_metrics["tail_observation_count"]),
            component_expected_shortfall=tail_metrics["component_expected_shortfall"],
            marginal_expected_shortfall=tail_metrics["marginal_expected_shortfall"],
            factor_exposures=factor_exposures,
            scenario_losses=scenario_losses,
            max_scenario_loss_pct=max(scenario_losses.values(), default=0.0),
            hhi=hhi,
            concentration_score=min(hhi / max(self.risk.max_portfolio_hhi, 0.01), 2.0),
        )


def _projected_weights(symbol: str, target_notional_usd: float, portfolio: PortfolioState) -> dict[str, float]:
    nav = max(portfolio.nav_usd, 1.0)
    weights = {position.symbol.upper(): max(position.current_value_usd, 0.0) / nav for position in portfolio.positions}
    weights[symbol.upper()] = weights.get(symbol.upper(), 0.0) + (target_notional_usd / nav)
    return weights


def _scenario_losses(
    *,
    weights: dict[str, float],
    all_snapshots: dict[str, MarketSnapshot],
    benchmark_snapshot: MarketSnapshot | None,
    regime: MarketRegime | None,
    universe: UniverseSettings,
    scenario_library: tuple[ScenarioDefinition, ...] | None = None,
) -> dict[str, float]:
    scenarios = scenario_library or _default_scenario_book(regime)
    benchmark_returns = _recent_returns(benchmark_snapshot.candles if benchmark_snapshot else [], 20)
    losses: dict[str, float] = {}
    for scenario in scenarios:
        total_loss = 0.0
        for symbol, weight in weights.items():
            snapshot = all_snapshots.get(symbol)
            if snapshot is None:
                total_loss += weight * scenario.benchmark_shock_pct
                continue
            symbol_returns = _recent_returns(snapshot.candles, 20)
            corr = _correlation(symbol_returns, benchmark_returns) if benchmark_returns else 0.5
            beta_proxy = _beta_proxy(symbol_returns, benchmark_returns)
            idiosyncratic = _idiosyncratic_risk(snapshot)
            sector = _sector_for_symbol(symbol, universe)
            rates_loss = abs(_rates_heuristic(sector) * scenario.rates_shock_pct)
            usd_loss = abs(_usd_heuristic(sector, snapshot) * scenario.usd_shock_pct)
            commodity_loss = abs(_commodity_heuristic(sector) * scenario.commodity_shock_pct)
            crypto_loss = abs(_crypto_heuristic(snapshot) * scenario.crypto_shock_pct)
            sector_loss = (scenario.sector_shocks or {}).get(sector, 0.0)
            spread_loss = (scenario.spread_widening_bps / 10_000) * (0.35 + _liquidity_stress(snapshot))
            scenario_impact = (
                scenario.benchmark_shock_pct * max(0.6, corr + beta_proxy * 0.35)
                + idiosyncratic * scenario.volatility_multiplier
                + scenario.liquidity_shock_pct
                + scenario.idiosyncratic_shock_pct
                + rates_loss
                + usd_loss
                + commodity_loss
                + crypto_loss
                + sector_loss
                + spread_loss
            )
            total_loss += weight * scenario_impact
        losses[scenario.name] = max(total_loss, 0.0)
    return losses


def _scenario_library(regime: MarketRegime | None, risk: RiskSettings) -> tuple[ScenarioDefinition, ...]:
    if risk.scenarios:
        return tuple(_configured_scenario(raw, regime) for raw in risk.scenarios)
    return _default_scenario_book(regime)


def _configured_scenario(raw: StressScenarioSettings, regime: MarketRegime | None) -> ScenarioDefinition:
    regime_multiplier = 1.0 + ((regime.stress_score - 0.4) if regime is not None else 0.0)
    return ScenarioDefinition(
        name=raw.name,
        benchmark_shock_pct=raw.benchmark_shock_pct * regime_multiplier,
        volatility_multiplier=raw.volatility_multiplier,
        liquidity_shock_pct=raw.liquidity_shock_pct * regime_multiplier,
        idiosyncratic_shock_pct=raw.idiosyncratic_shock_pct,
        rates_shock_pct=raw.rates_shock_pct,
        usd_shock_pct=raw.usd_shock_pct,
        commodity_shock_pct=raw.commodity_shock_pct,
        crypto_shock_pct=raw.crypto_shock_pct,
        spread_widening_bps=raw.spread_widening_bps,
        sector_shocks=raw.sector_shocks,
    )


def _default_scenario_book(regime: MarketRegime | None) -> tuple[ScenarioDefinition, ...]:
    regime_multiplier = 1.0 + ((regime.stress_score - 0.4) if regime is not None else 0.0)
    return (
        ScenarioDefinition("cpi_shock", 0.045 * regime_multiplier, 1.30, 0.004, 0.004, rates_shock_pct=0.020, usd_shock_pct=0.012),
        ScenarioDefinition("fed_surprise", 0.050 * regime_multiplier, 1.35, 0.006, 0.004, rates_shock_pct=0.030, usd_shock_pct=0.015),
        ScenarioDefinition("earnings_miss", 0.020 * regime_multiplier, 1.15, 0.002, 0.035),
        ScenarioDefinition("tech_selloff", 0.060 * regime_multiplier, 1.45, 0.008, 0.010, sector_shocks={"technology": 0.040, "communication_services": 0.030}),
        ScenarioDefinition("oil_spike", 0.030 * regime_multiplier, 1.20, 0.005, 0.004, commodity_shock_pct=0.050, sector_shocks={"energy": 0.020, "airlines": 0.035, "consumer_discretionary": 0.015}),
        ScenarioDefinition("usd_spike", 0.035 * regime_multiplier, 1.20, 0.004, 0.003, usd_shock_pct=0.030, commodity_shock_pct=0.020),
        ScenarioDefinition("liquidity_gap", 0.035 * regime_multiplier, 1.65, 0.020, 0.006, spread_widening_bps=35),
        ScenarioDefinition("risk_off_crash", 0.080 * regime_multiplier, 1.70, 0.014, 0.010, rates_shock_pct=0.012, crypto_shock_pct=0.080, spread_widening_bps=45),
        ScenarioDefinition("sector_rotation", 0.025 * regime_multiplier, 1.10, 0.002, 0.018, sector_shocks={"technology": 0.030, "consumer_discretionary": 0.020, "energy": 0.012}),
        ScenarioDefinition("single_name_fraud_shock", 0.012 * regime_multiplier, 1.35, 0.005, 0.070, spread_widening_bps=20),
        ScenarioDefinition("broker_spread_widening", 0.015 * regime_multiplier, 1.10, 0.012, 0.004, spread_widening_bps=80),
    )


def _current_weights(portfolio: PortfolioState) -> dict[str, float]:
    nav = max(portfolio.nav_usd, 1.0)
    return {
        position.symbol.upper(): max(position.current_value_usd, 0.0) / nav
        for position in portfolio.positions
        if position.current_value_usd > 0
    }


def _historical_portfolio_losses(
    weights: dict[str, float],
    all_snapshots: dict[str, MarketSnapshot],
    benchmark_returns: list[float],
) -> list[float]:
    return sorted(sample["total_loss"] for sample in _historical_portfolio_loss_samples(weights, all_snapshots, benchmark_returns))


def _historical_portfolio_loss_samples(
    weights: dict[str, float],
    all_snapshots: dict[str, MarketSnapshot],
    benchmark_returns: list[float],
) -> list[dict[str, object]]:
    if not weights:
        return [{"total_loss": 0.0, "contributions": {}}]
    series_by_symbol = {
        symbol: _recent_returns(snapshot.candles, 60)
        for symbol, snapshot in all_snapshots.items()
        if symbol.upper() in weights
    }
    length = min((len(values) for values in series_by_symbol.values() if values), default=0)
    if length < 5:
        fallback_vol = _volatility(benchmark_returns) if benchmark_returns else 0.01
        samples: list[dict[str, object]] = []
        for shock in (0.4, 0.7, 1.0, 1.3, 1.6):
            contributions = {
                symbol: max(weight * fallback_vol * shock, 0.0)
                for symbol, weight in weights.items()
            }
            samples.append({"total_loss": sum(contributions.values()), "contributions": contributions})
        return samples
    samples: list[dict[str, object]] = []
    for index in range(-length, 0):
        contributions: dict[str, float] = {}
        for symbol, weight in weights.items():
            returns = series_by_symbol.get(symbol, [])
            symbol_return = returns[index] if len(returns) >= abs(index) else 0.0
            contributions[symbol] = max(-(weight * symbol_return), 0.0)
        samples.append({"total_loss": sum(contributions.values()), "contributions": contributions})
    return samples


def _tail_risk_metrics(samples: list[dict[str, object]], nav_usd: float) -> dict[str, object]:
    losses = sorted(max(float(sample.get("total_loss", 0.0)), 0.0) for sample in samples)
    var_95 = _percentile(losses, 0.95)
    var_99 = _percentile(losses, 0.99)
    tail_95 = [sample for sample in samples if float(sample.get("total_loss", 0.0)) >= var_95]
    tail_99 = [sample for sample in samples if float(sample.get("total_loss", 0.0)) >= var_99]
    cvar_95 = _average_loss(tail_95, default=var_95)
    cvar_99 = _average_loss(tail_99, default=var_99)
    component_es: dict[str, float] = {}
    for sample in tail_95:
        contributions = sample.get("contributions", {})
        if not isinstance(contributions, dict):
            continue
        for symbol, value in contributions.items():
            component_es[str(symbol).upper()] = component_es.get(str(symbol).upper(), 0.0) + max(float(value), 0.0)
    tail_count = max(len(tail_95), 1)
    component_es = {
        symbol: value / tail_count
        for symbol, value in sorted(component_es.items())
    }
    total_es = sum(component_es.values()) or cvar_95 or 1.0
    marginal_es = {
        symbol: value / total_es
        for symbol, value in component_es.items()
    }
    nav = max(nav_usd, 1.0)
    return {
        "var_95_pct": max(var_95, 0.0),
        "cvar_95_pct": max(cvar_95, 0.0),
        "var_99_pct": max(var_99, 0.0),
        "cvar_99_pct": max(cvar_99, 0.0),
        "expected_shortfall_95_pct": max(cvar_95, 0.0),
        "expected_shortfall_95_usd": max(cvar_95, 0.0) * nav,
        "tail_observation_count": len(tail_95),
        "component_expected_shortfall": component_es,
        "marginal_expected_shortfall": marginal_es,
    }


def _average_loss(samples: list[dict[str, object]], *, default: float) -> float:
    if not samples:
        return default
    return sum(max(float(sample.get("total_loss", 0.0)), 0.0) for sample in samples) / len(samples)


def _factor_exposures(
    weights: dict[str, float],
    all_snapshots: dict[str, MarketSnapshot],
    benchmark_returns: list[float],
    *,
    universe: UniverseSettings,
) -> dict[str, float]:
    if not weights:
        return {
            "market_beta": 0.0,
            "sector_beta": 0.0,
            "volatility_beta": 0.0,
            "rates_sensitivity": 0.0,
            "usd_sensitivity": 0.0,
            "commodity_sensitivity": 0.0,
            "crypto_correlation": 0.0,
            "idiosyncratic_volatility": 0.0,
            "average_correlation": 0.0,
            "volatility_exposure": 0.0,
            "liquidity_stress": 0.0,
        }
    factor_series = _factor_proxy_returns(all_snapshots)
    weighted_beta = 0.0
    weighted_sector_beta = 0.0
    weighted_vol_beta = 0.0
    weighted_rates = 0.0
    weighted_usd = 0.0
    weighted_commodity = 0.0
    weighted_crypto_corr = 0.0
    weighted_idiosyncratic_vol = 0.0
    weighted_corr = 0.0
    weighted_vol = 0.0
    weighted_liquidity = 0.0
    sector_weights: dict[str, float] = {}
    sector_beta_weights: dict[str, float] = {}
    total_weight = sum(weights.values()) or 1.0
    for symbol, weight in weights.items():
        snapshot = all_snapshots.get(symbol)
        if snapshot is None:
            continue
        returns = _recent_returns(snapshot.candles, 60)
        market_beta = _beta_proxy(returns, benchmark_returns)
        sector = _sector_for_symbol(symbol, universe)
        sector_returns = _sector_returns(sector, symbol, all_snapshots, universe)
        sector_beta = _beta_proxy(returns, sector_returns or benchmark_returns)
        volatility_beta = _volatility_beta(returns, benchmark_returns)
        rates = _factor_beta_or_heuristic(returns, factor_series.get("rates", []), _rates_heuristic(sector))
        usd = _factor_beta_or_heuristic(returns, factor_series.get("usd", []), _usd_heuristic(sector, snapshot))
        commodity = _factor_beta_or_heuristic(returns, factor_series.get("commodity", []), _commodity_heuristic(sector))
        crypto_corr = _factor_correlation_or_heuristic(returns, factor_series.get("crypto", []), _crypto_heuristic(snapshot))
        idio_vol = _idiosyncratic_volatility(returns, benchmark_returns, market_beta)

        weighted_beta += weight * market_beta
        weighted_sector_beta += weight * sector_beta
        weighted_vol_beta += weight * volatility_beta
        weighted_rates += weight * rates
        weighted_usd += weight * usd
        weighted_commodity += weight * commodity
        weighted_crypto_corr += weight * crypto_corr
        weighted_idiosyncratic_vol += weight * idio_vol
        weighted_corr += weight * _correlation(returns, benchmark_returns)
        weighted_vol += weight * _volatility(returns)
        weighted_liquidity += weight * _liquidity_stress(snapshot)
        sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
        sector_beta_weights[sector] = sector_beta_weights.get(sector, 0.0) + weight * sector_beta
    factors = {
        "market_beta": weighted_beta / total_weight,
        "sector_beta": weighted_sector_beta / total_weight,
        "volatility_beta": weighted_vol_beta / total_weight,
        "rates_sensitivity": weighted_rates / total_weight,
        "usd_sensitivity": weighted_usd / total_weight,
        "commodity_sensitivity": weighted_commodity / total_weight,
        "crypto_correlation": weighted_crypto_corr / total_weight,
        "idiosyncratic_volatility": weighted_idiosyncratic_vol / total_weight,
        "average_correlation": weighted_corr / total_weight,
        "volatility_exposure": weighted_vol / total_weight,
        "liquidity_stress": weighted_liquidity / total_weight,
    }
    for sector, weight in sorted(sector_weights.items()):
        safe_sector = _safe_factor_name(sector)
        factors[f"sector_exposure_{safe_sector}"] = weight
        factors[f"sector_beta_{safe_sector}"] = sector_beta_weights.get(sector, 0.0) / max(weight, 1e-9)
    return factors


def _factor_proxy_returns(all_snapshots: dict[str, MarketSnapshot]) -> dict[str, list[float]]:
    proxy_groups = {
        "rates": ("TLT", "IEF", "SHY", "GOVT"),
        "usd": ("UUP", "DXY", "USDU"),
        "commodity": ("GLD", "SLV", "USO", "DBC", "PDBC"),
        "crypto": ("BTC", "BTC-USD", "ETH", "ETH-USD", "IBIT", "ETHE"),
    }
    series: dict[str, list[float]] = {}
    for factor, symbols in proxy_groups.items():
        returns = [
            _recent_returns(snapshot.candles, 60)
            for symbol, snapshot in all_snapshots.items()
            if symbol.upper() in symbols
        ]
        series[factor] = _average_return_series(returns)
    return series


def _sector_returns(
    sector: str,
    symbol: str,
    all_snapshots: dict[str, MarketSnapshot],
    universe: UniverseSettings,
) -> list[float]:
    peers = [
        _recent_returns(snapshot.candles, 60)
        for peer_symbol, snapshot in all_snapshots.items()
        if peer_symbol.upper() != symbol.upper()
        and _sector_for_symbol(peer_symbol, universe) == sector
    ]
    return _average_return_series(peers)


def _average_return_series(series: list[list[float]]) -> list[float]:
    usable = [values for values in series if values]
    length = min((len(values) for values in usable), default=0)
    if length <= 0:
        return []
    output: list[float] = []
    for index in range(-length, 0):
        output.append(sum(values[index] for values in usable) / len(usable))
    return output


def _factor_beta_or_heuristic(returns: list[float], factor_returns: list[float], fallback: float) -> float:
    if len(returns) >= 5 and len(factor_returns) >= 5:
        return _linear_beta(returns, factor_returns)
    return fallback


def _factor_correlation_or_heuristic(returns: list[float], factor_returns: list[float], fallback: float) -> float:
    if len(returns) >= 5 and len(factor_returns) >= 5:
        return _correlation(returns, factor_returns)
    return fallback


def _linear_beta(left: list[float], right: list[float]) -> float:
    n = min(len(left), len(right))
    if n < 3:
        return 0.0
    left = left[-n:]
    right = right[-n:]
    left_mean = sum(left) / n
    right_mean = sum(right) / n
    cov = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    right_var = sum((b - right_mean) ** 2 for b in right)
    if right_var <= 0:
        return 0.0
    return max(min(cov / right_var, 3.0), -3.0)


def _volatility_beta(returns: list[float], benchmark_returns: list[float]) -> float:
    n = min(len(returns), len(benchmark_returns))
    if n < 5:
        return 0.0
    absolute_benchmark = [abs(value) for value in benchmark_returns[-n:]]
    absolute_returns = [abs(value) for value in returns[-n:]]
    return _linear_beta(absolute_returns, absolute_benchmark)


def _idiosyncratic_volatility(
    returns: list[float],
    benchmark_returns: list[float],
    market_beta: float,
) -> float:
    n = min(len(returns), len(benchmark_returns))
    if n < 5:
        return _volatility(returns)
    residuals = [
        symbol_return - market_beta * benchmark_return
        for symbol_return, benchmark_return in zip(returns[-n:], benchmark_returns[-n:])
    ]
    return _volatility(residuals)


def _sector_for_symbol(symbol: str, universe: UniverseSettings) -> str:
    mapped = universe.sector_map.get(symbol.upper())
    if mapped:
        return mapped.strip().lower().replace(" ", "_")
    upper = symbol.upper()
    if upper in {"BTC", "BTC-USD", "ETH", "ETH-USD", "IBIT", "ETHE"}:
        return "crypto"
    if upper in {"GLD", "SLV", "USO", "DBC", "PDBC"}:
        return "commodity"
    if upper in {"TLT", "IEF", "SHY", "GOVT"}:
        return "rates"
    if upper in {"UUP", "DXY", "USDU"}:
        return "usd"
    return "unknown"


def _rates_heuristic(sector: str) -> float:
    return {
        "utilities": -0.70,
        "real_estate": -0.85,
        "financials": 0.35,
        "technology": -0.25,
        "consumer_discretionary": -0.30,
        "rates": 1.00,
    }.get(sector, -0.10)


def _usd_heuristic(sector: str, snapshot: MarketSnapshot) -> float:
    if snapshot.instrument.asset_type.lower() in {"crypto", "currency"}:
        return -0.50
    return {
        "commodity": -0.65,
        "materials": -0.35,
        "energy": -0.25,
        "technology": -0.15,
        "usd": 1.00,
    }.get(sector, -0.05)


def _commodity_heuristic(sector: str) -> float:
    return {
        "energy": 0.75,
        "materials": 0.65,
        "commodity": 1.00,
        "industrials": 0.20,
        "consumer_discretionary": -0.15,
    }.get(sector, 0.0)


def _crypto_heuristic(snapshot: MarketSnapshot) -> float:
    symbol = snapshot.symbol.upper()
    if symbol in {"BTC", "BTC-USD", "ETH", "ETH-USD", "IBIT", "ETHE"}:
        return 1.0
    if snapshot.instrument.asset_type.lower() == "crypto":
        return 1.0
    return 0.0


def _safe_factor_name(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_") or "unknown"


def _liquidity_stress(snapshot: MarketSnapshot) -> float:
    candles = snapshot.candles[-20:]
    if not candles:
        return 0.5
    avg_volume = sum(max(candle.volume, 0.0) for candle in candles) / len(candles)
    spread_component = min(snapshot.rate.spread_bps / 80, 1.0)
    volume_component = 1.0 / (1.0 + avg_volume / 1_000_000)
    return min((spread_component + volume_component) / 2, 1.0)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(max(int(round((len(ordered) - 1) * percentile)), 0), len(ordered) - 1)
    return ordered[index]


def _beta_proxy(symbol_returns: list[float], benchmark_returns: list[float]) -> float:
    if not symbol_returns or not benchmark_returns:
        return 1.0
    symbol_vol = _volatility(symbol_returns)
    benchmark_vol = _volatility(benchmark_returns)
    if benchmark_vol <= 0:
        return 1.0
    return min(max(symbol_vol / benchmark_vol, 0.5), 1.8)


def _idiosyncratic_risk(snapshot: MarketSnapshot) -> float:
    closes = snapshot.candles[-20:] if len(snapshot.candles) >= 20 else snapshot.candles
    if not closes:
        return 0.01
    range_mean = sum((candle.high - candle.low) / max(candle.close, 1.0) for candle in closes) / len(closes)
    return min(range_mean * 0.30, 0.02)


def _recent_returns(candles, window: int) -> list[float]:
    if len(candles) < 3:
        return []
    selected = candles[-window - 1 :] if len(candles) >= window + 1 else candles
    returns: list[float] = []
    for previous, current in zip(selected, selected[1:]):
        if previous.close > 0:
            returns.append((current.close - previous.close) / previous.close)
    return returns


def _volatility(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return variance ** 0.5


def _correlation(left: list[float], right: list[float]) -> float:
    n = min(len(left), len(right))
    if n < 3:
        return 0.5
    left = left[-n:]
    right = right[-n:]
    left_mean = sum(left) / n
    right_mean = sum(right) / n
    cov = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_var = sum((a - left_mean) ** 2 for a in left)
    right_var = sum((b - right_mean) ** 2 for b in right)
    if left_var <= 0 or right_var <= 0:
        return 0.5
    return cov / ((left_var * right_var) ** 0.5)
