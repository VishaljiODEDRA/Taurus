from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def load_env_file(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class AgentSettings:
    name: str = "autotrading-agent"
    timezone: str = "Europe/London"
    loop_interval_seconds: int = 300
    max_candidates_per_cycle: int = 20


@dataclass(frozen=True)
class ExecutionSettings:
    mode: str = "shadow"
    environment: str = "demo"
    base_currency: str = "USD"

    def normalized_mode(self) -> str:
        return self.mode.lower()

    def normalized_environment(self) -> str:
        return self.environment.lower()


@dataclass(frozen=True)
class UniverseSettings:
    symbols: tuple[str, ...] = ()
    benchmark_symbol: str = "SPY"
    allowed_asset_types: tuple[str, ...] = ("Stock", "ETF")
    long_only: bool = True
    max_symbols_per_cycle: int = 10
    cursor_path: str = "state/universe_cursor.txt"
    market_cache_path: str = "state/market_cache.json"
    instrument_cache_ttl_days: int = 14
    candle_cache_ttl_minutes: int = 360
    chart_data_source: str = "tradingview"
    chart_data_fallback_source: str = "yahoo"
    tradingview_timeout_seconds: float = 8.0
    instrument_ids: dict[str, int] = field(default_factory=dict)
    sector_map: dict[str, str] = field(default_factory=dict)

    @property
    def all_symbols(self) -> tuple[str, ...]:
        symbols = [symbol.upper() for symbol in self.symbols]
        benchmark = self.benchmark_symbol.upper()
        if benchmark and benchmark not in symbols:
            symbols.append(benchmark)
        return tuple(symbols)


@dataclass(frozen=True)
class StressScenarioSettings:
    name: str
    benchmark_shock_pct: float = 0.0
    volatility_multiplier: float = 1.0
    liquidity_shock_pct: float = 0.0
    idiosyncratic_shock_pct: float = 0.0
    rates_shock_pct: float = 0.0
    usd_shock_pct: float = 0.0
    commodity_shock_pct: float = 0.0
    crypto_shock_pct: float = 0.0
    spread_widening_bps: float = 0.0
    sector_shocks: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class RiskSettings:
    min_order_usd: float = 25.0
    max_positions: int = 2
    max_position_pct_nav: float = 0.05
    max_gross_exposure_pct: float = 1.0
    max_daily_loss_pct: float = 0.02
    max_rolling_drawdown_pct: float = 0.08
    max_spread_bps: float = 30.0
    max_data_staleness_seconds: int = 60
    cooldown_after_loss_minutes: int = 120
    one_order_per_symbol_per_cycle: bool = True
    allow_averaging_down: bool = False
    max_leverage: int = 1
    kill_switch_path: str = "state/KILL_SWITCH"
    adaptive_protection_enabled: bool = True
    min_stop_loss_pct: float = 0.008
    max_stop_loss_pct: float = 0.03
    min_take_profit_pct: float = 0.012
    max_take_profit_pct: float = 0.09
    min_reward_to_risk: float = 1.2
    max_reward_to_risk: float = 3.2
    max_sector_exposure_pct: float = 0.25
    max_sector_positions: int = 3
    max_peer_group_positions: int = 2
    max_symbol_correlation: float = 0.88
    max_average_correlation: float = 0.72
    regime_risk_off_buy_block: bool = True
    regime_event_driven_buy_block: bool = True
    regime_volatile_size_multiplier: float = 0.6
    regime_weak_size_multiplier: float = 0.75
    regime_bullish_size_multiplier: float = 1.05
    min_avg_daily_dollar_volume: float = 50_000_000.0
    max_expected_slippage_bps: float = 25.0
    min_execution_quality_score: float = 0.42
    unstable_gap_threshold_pct: float = 0.025
    minimum_close_location_for_entry: float = 0.35
    execution_retry_attempts: int = 2
    portfolio_optimization_enabled: bool = True
    max_portfolio_hhi: float = 0.16
    max_projected_stress_loss_pct: float = 0.05
    max_expected_shortfall_pct: float = 0.06
    scenarios: tuple[StressScenarioSettings, ...] = ()


@dataclass(frozen=True)
class ExitSettings:
    enabled: bool = True
    max_holding_days: int = 10
    hard_stop_loss_pct: float = 0.025
    take_profit_pct: float = 0.06
    momentum_take_profit_min_pct: float = 0.01
    momentum_take_profit_max_pct: float = 0.015
    trailing_stop_pct: float = 0.035
    min_exit_score: float = 0.38
    exit_on_ma_break: bool = True
    exit_on_negative_news: bool = True
    hold_on_positive_momentum: bool = True
    require_market_confirmation_for_take_profit: bool = True
    require_news_confirmation_for_take_profit: bool = True
    momentum_hold_threshold: float = 0.58
    market_hold_threshold: float = 0.55
    news_hold_sentiment_floor: float = 0.05
    min_dynamic_stop_loss_pct: float = 0.008
    max_dynamic_stop_loss_pct: float = 0.03
    min_dynamic_take_profit_pct: float = 0.012
    max_dynamic_take_profit_pct: float = 0.09
    exit_pressure_threshold: float = 0.58
    loss_pressure_threshold: float = 0.45


@dataclass(frozen=True)
class MonitoringSettings:
    enabled: bool = True
    max_order_reject_rate: float = 0.25
    max_consecutive_rejects: int = 3
    max_halted_cycles: int = 3
    auto_kill_switch_on_breach: bool = True
    alert_log_path: str = "logs/alerts.jsonl"


@dataclass(frozen=True)
class ValidationSettings:
    backtest_initial_cash_usd: float = 10_000.0
    backtest_position_pct_nav: float = 0.05
    backtest_fee_bps: float = 2.0
    backtest_slippage_bps: float = 5.0
    backtest_max_holding_days: int = 10
    walk_forward_train_days: int = 60
    walk_forward_test_days: int = 20
    walk_forward_step_days: int = 20
    min_backtest_trades: int = 10
    min_walk_forward_trades: int = 5
    min_profit_factor: float = 1.15
    min_sharpe: float = 0.25
    max_backtest_drawdown_pct: float = 0.12
    calibration_min_samples: int = 20
    multiple_testing_penalty_trials: int = 25
    min_deflated_sharpe_proxy: float = 0.05


@dataclass(frozen=True)
class PeerGroupSettings:
    symbols: tuple[str, ...] = ()
    leader_move_threshold_pct: float = 0.03
    laggard_max_move_pct: float = 0.01


@dataclass(frozen=True)
class StrategySettings:
    buy_threshold: float = 0.72
    sell_threshold: float = 0.30
    news_weight: float = 0.18
    momentum_weight: float = 0.32
    relative_strength_weight: float = 0.20
    volume_weight: float = 0.12
    catalyst_weight: float = 0.10
    chart_weight: float = 0.26
    ml_weight: float = 0.22
    risk_penalty_weight: float = 0.08
    previous_day_window: int = 1
    previous_week_window: int = 5
    previous_month_window: int = 21
    rsi_period: int = 14
    fast_ma_period: int = 10
    slow_ma_period: int = 30
    volatility_window: int = 20
    take_profit_pct: float = 0.06
    stop_loss_pct: float = 0.025
    trailing_stop: bool = False
    meta_labeling_enabled: bool = True
    meta_label_min_samples: int = 12
    meta_label_take_threshold: float = 0.57
    meta_label_block_threshold: float = 0.46
    edge_sizing_enabled: bool = True
    min_edge_size_multiplier: float = 0.55
    max_edge_size_multiplier: float = 1.15
    peer_groups: dict[str, PeerGroupSettings] = field(default_factory=dict)


@dataclass(frozen=True)
class NewsSettings:
    enabled: bool = True
    lookback_hours: int = 48
    local_news_path: str = "data/news.json"
    local_social_path: str = "data/social.json"
    entity_map_path: str = "data/news_entities.json"
    rss_urls: tuple[str, ...] = ()
    rss_timeout_seconds: float = 4.0
    rss_max_workers: int = 12
    scrape_articles: bool = True
    scrape_max_articles_per_cycle: int = 30
    article_timeout_seconds: float = 4.0
    article_max_chars: int = 5_000
    use_openai_context: bool = False


@dataclass(frozen=True)
class StorageSettings:
    sqlite_path: str = "state/agent_ledger.sqlite3"
    audit_log_path: str = "logs/audit.jsonl"


@dataclass(frozen=True)
class Secrets:
    etoro_api_key: str = ""
    etoro_user_key: str = ""
    etoro_base_url: str = "https://public-api.etoro.com/api/v1"
    etoro_user_agent: str = "AutoTrading-Agent/0.1 (+https://api-portal.etoro.com/)"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    allow_live: bool = False


@dataclass(frozen=True)
class AppConfig:
    agent: AgentSettings
    execution: ExecutionSettings
    universe: UniverseSettings
    risk: RiskSettings
    exits: ExitSettings
    monitoring: MonitoringSettings
    validation: ValidationSettings
    strategy: StrategySettings
    news: NewsSettings
    storage: StorageSettings
    secrets: Secrets

    @property
    def is_shadow(self) -> bool:
        return self.execution.normalized_mode() == "shadow"

    @property
    def is_live(self) -> bool:
        return self.execution.normalized_mode() == "live"


def load_config(path: str | Path = "config/strategy.toml") -> AppConfig:
    load_env_file()
    config_path = Path(path)
    if not config_path.exists():
        fallback = Path("config/strategy.example.toml")
        if fallback.exists():
            config_path = fallback
        else:
            raise FileNotFoundError(f"Config file not found: {path}")

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return AppConfig(
        agent=_agent_settings(data.get("agent", {})),
        execution=_execution_settings(data.get("execution", {})),
        universe=_universe_settings(data.get("universe", {})),
        risk=_risk_settings(data.get("risk", {})),
        exits=_exit_settings(data.get("exits", {})),
        monitoring=_monitoring_settings(data.get("monitoring", {})),
        validation=_validation_settings(data.get("validation", {})),
        strategy=_strategy_settings(data.get("strategy", {})),
        news=_news_settings(data.get("news", {})),
        storage=_storage_settings(data.get("storage", {})),
        secrets=_secrets(),
    )


def _agent_settings(data: dict[str, Any]) -> AgentSettings:
    return AgentSettings(
        name=str(data.get("name", "autotrading-agent")),
        timezone=str(data.get("timezone", "Europe/London")),
        loop_interval_seconds=int(data.get("loop_interval_seconds", 300)),
        max_candidates_per_cycle=int(data.get("max_candidates_per_cycle", 20)),
    )


def _execution_settings(data: dict[str, Any]) -> ExecutionSettings:
    return ExecutionSettings(
        mode=str(data.get("mode", "shadow")).lower(),
        environment=str(data.get("environment", "demo")).lower(),
        base_currency=str(data.get("base_currency", "USD")).upper(),
    )


def _universe_settings(data: dict[str, Any]) -> UniverseSettings:
    return UniverseSettings(
        symbols=tuple(str(symbol).upper() for symbol in data.get("symbols", [])),
        benchmark_symbol=str(data.get("benchmark_symbol", "SPY")).upper(),
        allowed_asset_types=tuple(str(item) for item in data.get("allowed_asset_types", ["Stock", "ETF"])),
        long_only=bool(data.get("long_only", True)),
        max_symbols_per_cycle=int(data.get("max_symbols_per_cycle", 10)),
        cursor_path=str(data.get("cursor_path", "state/universe_cursor.txt")),
        market_cache_path=str(data.get("market_cache_path", "state/market_cache.json")),
        instrument_cache_ttl_days=int(data.get("instrument_cache_ttl_days", 14)),
        candle_cache_ttl_minutes=int(data.get("candle_cache_ttl_minutes", 360)),
        chart_data_source=str(data.get("chart_data_source", "tradingview")).lower(),
        chart_data_fallback_source=str(data.get("chart_data_fallback_source", "yahoo")).lower(),
        tradingview_timeout_seconds=float(data.get("tradingview_timeout_seconds", 8.0)),
        instrument_ids={
            str(symbol).upper(): int(instrument_id)
            for symbol, instrument_id in data.get("instrument_ids", {}).items()
        },
        sector_map={
            str(symbol).upper(): str(sector)
            for symbol, sector in data.get("sector_map", {}).items()
        },
    )


def _risk_settings(data: dict[str, Any]) -> RiskSettings:
    return RiskSettings(
        min_order_usd=float(data.get("min_order_usd", 25)),
        max_positions=int(data.get("max_positions", 2)),
        max_position_pct_nav=float(data.get("max_position_pct_nav", 0.05)),
        max_gross_exposure_pct=float(data.get("max_gross_exposure_pct", 1.0)),
        max_daily_loss_pct=float(data.get("max_daily_loss_pct", 0.02)),
        max_rolling_drawdown_pct=float(data.get("max_rolling_drawdown_pct", 0.08)),
        max_spread_bps=float(data.get("max_spread_bps", 30)),
        max_data_staleness_seconds=int(data.get("max_data_staleness_seconds", 60)),
        cooldown_after_loss_minutes=int(data.get("cooldown_after_loss_minutes", 120)),
        one_order_per_symbol_per_cycle=bool(data.get("one_order_per_symbol_per_cycle", True)),
        allow_averaging_down=bool(data.get("allow_averaging_down", False)),
        max_leverage=int(data.get("max_leverage", 1)),
        kill_switch_path=str(data.get("kill_switch_path", "state/KILL_SWITCH")),
        adaptive_protection_enabled=bool(data.get("adaptive_protection_enabled", True)),
        min_stop_loss_pct=float(data.get("min_stop_loss_pct", 0.008)),
        max_stop_loss_pct=float(data.get("max_stop_loss_pct", 0.03)),
        min_take_profit_pct=float(data.get("min_take_profit_pct", 0.012)),
        max_take_profit_pct=float(data.get("max_take_profit_pct", 0.09)),
        min_reward_to_risk=float(data.get("min_reward_to_risk", 1.2)),
        max_reward_to_risk=float(data.get("max_reward_to_risk", 3.2)),
        max_sector_exposure_pct=float(data.get("max_sector_exposure_pct", 0.25)),
        max_sector_positions=int(data.get("max_sector_positions", 3)),
        max_peer_group_positions=int(data.get("max_peer_group_positions", 2)),
        max_symbol_correlation=float(data.get("max_symbol_correlation", 0.88)),
        max_average_correlation=float(data.get("max_average_correlation", 0.72)),
        regime_risk_off_buy_block=bool(data.get("regime_risk_off_buy_block", True)),
        regime_event_driven_buy_block=bool(data.get("regime_event_driven_buy_block", True)),
        regime_volatile_size_multiplier=float(data.get("regime_volatile_size_multiplier", 0.6)),
        regime_weak_size_multiplier=float(data.get("regime_weak_size_multiplier", 0.75)),
        regime_bullish_size_multiplier=float(data.get("regime_bullish_size_multiplier", 1.05)),
        min_avg_daily_dollar_volume=float(data.get("min_avg_daily_dollar_volume", 50_000_000)),
        max_expected_slippage_bps=float(data.get("max_expected_slippage_bps", 25)),
        min_execution_quality_score=float(data.get("min_execution_quality_score", 0.42)),
        unstable_gap_threshold_pct=float(data.get("unstable_gap_threshold_pct", 0.025)),
        minimum_close_location_for_entry=float(data.get("minimum_close_location_for_entry", 0.35)),
        execution_retry_attempts=int(data.get("execution_retry_attempts", 2)),
        portfolio_optimization_enabled=bool(data.get("portfolio_optimization_enabled", True)),
        max_portfolio_hhi=float(data.get("max_portfolio_hhi", 0.16)),
        max_projected_stress_loss_pct=float(data.get("max_projected_stress_loss_pct", 0.05)),
        max_expected_shortfall_pct=float(data.get("max_expected_shortfall_pct", 0.06)),
        scenarios=tuple(_stress_scenario_settings(raw) for raw in data.get("scenarios", [])),
    )


def _stress_scenario_settings(data: dict[str, Any]) -> StressScenarioSettings:
    return StressScenarioSettings(
        name=str(data.get("name", "custom_scenario")),
        benchmark_shock_pct=float(data.get("benchmark_shock_pct", 0.0)),
        volatility_multiplier=float(data.get("volatility_multiplier", 1.0)),
        liquidity_shock_pct=float(data.get("liquidity_shock_pct", 0.0)),
        idiosyncratic_shock_pct=float(data.get("idiosyncratic_shock_pct", 0.0)),
        rates_shock_pct=float(data.get("rates_shock_pct", 0.0)),
        usd_shock_pct=float(data.get("usd_shock_pct", 0.0)),
        commodity_shock_pct=float(data.get("commodity_shock_pct", 0.0)),
        crypto_shock_pct=float(data.get("crypto_shock_pct", 0.0)),
        spread_widening_bps=float(data.get("spread_widening_bps", 0.0)),
        sector_shocks={
            _normalize_scenario_key(str(sector)): float(shock)
            for sector, shock in data.get("sector_shocks", {}).items()
        },
    )


def _normalize_scenario_key(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _exit_settings(data: dict[str, Any]) -> ExitSettings:
    return ExitSettings(
        enabled=bool(data.get("enabled", True)),
        max_holding_days=int(data.get("max_holding_days", 10)),
        hard_stop_loss_pct=float(data.get("hard_stop_loss_pct", 0.025)),
        take_profit_pct=float(data.get("take_profit_pct", 0.06)),
        momentum_take_profit_min_pct=float(data.get("momentum_take_profit_min_pct", 0.01)),
        momentum_take_profit_max_pct=float(data.get("momentum_take_profit_max_pct", 0.015)),
        trailing_stop_pct=float(data.get("trailing_stop_pct", 0.035)),
        min_exit_score=float(data.get("min_exit_score", 0.38)),
        exit_on_ma_break=bool(data.get("exit_on_ma_break", True)),
        exit_on_negative_news=bool(data.get("exit_on_negative_news", True)),
        hold_on_positive_momentum=bool(data.get("hold_on_positive_momentum", True)),
        require_market_confirmation_for_take_profit=bool(
            data.get("require_market_confirmation_for_take_profit", True)
        ),
        require_news_confirmation_for_take_profit=bool(
            data.get("require_news_confirmation_for_take_profit", True)
        ),
        momentum_hold_threshold=float(data.get("momentum_hold_threshold", 0.58)),
        market_hold_threshold=float(data.get("market_hold_threshold", 0.55)),
        news_hold_sentiment_floor=float(data.get("news_hold_sentiment_floor", 0.05)),
        min_dynamic_stop_loss_pct=float(data.get("min_dynamic_stop_loss_pct", 0.008)),
        max_dynamic_stop_loss_pct=float(data.get("max_dynamic_stop_loss_pct", 0.03)),
        min_dynamic_take_profit_pct=float(data.get("min_dynamic_take_profit_pct", 0.012)),
        max_dynamic_take_profit_pct=float(data.get("max_dynamic_take_profit_pct", 0.09)),
        exit_pressure_threshold=float(data.get("exit_pressure_threshold", 0.58)),
        loss_pressure_threshold=float(data.get("loss_pressure_threshold", 0.45)),
    )


def _monitoring_settings(data: dict[str, Any]) -> MonitoringSettings:
    return MonitoringSettings(
        enabled=bool(data.get("enabled", True)),
        max_order_reject_rate=float(data.get("max_order_reject_rate", 0.25)),
        max_consecutive_rejects=int(data.get("max_consecutive_rejects", 3)),
        max_halted_cycles=int(data.get("max_halted_cycles", 3)),
        auto_kill_switch_on_breach=bool(data.get("auto_kill_switch_on_breach", True)),
        alert_log_path=str(data.get("alert_log_path", "logs/alerts.jsonl")),
    )


def _validation_settings(data: dict[str, Any]) -> ValidationSettings:
    return ValidationSettings(
        backtest_initial_cash_usd=float(data.get("backtest_initial_cash_usd", 10_000)),
        backtest_position_pct_nav=float(data.get("backtest_position_pct_nav", 0.05)),
        backtest_fee_bps=float(data.get("backtest_fee_bps", 2)),
        backtest_slippage_bps=float(data.get("backtest_slippage_bps", 5)),
        backtest_max_holding_days=int(data.get("backtest_max_holding_days", 10)),
        walk_forward_train_days=int(data.get("walk_forward_train_days", 60)),
        walk_forward_test_days=int(data.get("walk_forward_test_days", 20)),
        walk_forward_step_days=int(data.get("walk_forward_step_days", 20)),
        min_backtest_trades=int(data.get("min_backtest_trades", 10)),
        min_walk_forward_trades=int(data.get("min_walk_forward_trades", 5)),
        min_profit_factor=float(data.get("min_profit_factor", 1.15)),
        min_sharpe=float(data.get("min_sharpe", 0.25)),
        max_backtest_drawdown_pct=float(data.get("max_backtest_drawdown_pct", 0.12)),
        calibration_min_samples=int(data.get("calibration_min_samples", 20)),
        multiple_testing_penalty_trials=int(data.get("multiple_testing_penalty_trials", 25)),
        min_deflated_sharpe_proxy=float(data.get("min_deflated_sharpe_proxy", 0.05)),
    )


def _strategy_settings(data: dict[str, Any]) -> StrategySettings:
    peer_groups: dict[str, PeerGroupSettings] = {}
    for name, raw_group in data.get("peer_groups", {}).items():
        peer_groups[name] = PeerGroupSettings(
            symbols=tuple(str(symbol).upper() for symbol in raw_group.get("symbols", [])),
            leader_move_threshold_pct=float(raw_group.get("leader_move_threshold_pct", 0.03)),
            laggard_max_move_pct=float(raw_group.get("laggard_max_move_pct", 0.01)),
        )
    return StrategySettings(
        buy_threshold=float(data.get("buy_threshold", 0.72)),
        sell_threshold=float(data.get("sell_threshold", 0.30)),
        news_weight=float(data.get("news_weight", 0.18)),
        momentum_weight=float(data.get("momentum_weight", 0.32)),
        relative_strength_weight=float(data.get("relative_strength_weight", 0.20)),
        volume_weight=float(data.get("volume_weight", 0.12)),
        catalyst_weight=float(data.get("catalyst_weight", 0.10)),
        chart_weight=float(data.get("chart_weight", 0.26)),
        ml_weight=float(data.get("ml_weight", 0.22)),
        risk_penalty_weight=float(data.get("risk_penalty_weight", 0.08)),
        previous_day_window=int(data.get("previous_day_window", 1)),
        previous_week_window=int(data.get("previous_week_window", 5)),
        previous_month_window=int(data.get("previous_month_window", 21)),
        rsi_period=int(data.get("rsi_period", 14)),
        fast_ma_period=int(data.get("fast_ma_period", 10)),
        slow_ma_period=int(data.get("slow_ma_period", 30)),
        volatility_window=int(data.get("volatility_window", 20)),
        take_profit_pct=float(data.get("take_profit_pct", 0.06)),
        stop_loss_pct=float(data.get("stop_loss_pct", 0.025)),
        trailing_stop=bool(data.get("trailing_stop", False)),
        meta_labeling_enabled=bool(data.get("meta_labeling_enabled", True)),
        meta_label_min_samples=int(data.get("meta_label_min_samples", 12)),
        meta_label_take_threshold=float(data.get("meta_label_take_threshold", 0.57)),
        meta_label_block_threshold=float(data.get("meta_label_block_threshold", 0.46)),
        edge_sizing_enabled=bool(data.get("edge_sizing_enabled", True)),
        min_edge_size_multiplier=float(data.get("min_edge_size_multiplier", 0.55)),
        max_edge_size_multiplier=float(data.get("max_edge_size_multiplier", 1.15)),
        peer_groups=peer_groups,
    )


def _news_settings(data: dict[str, Any]) -> NewsSettings:
    return NewsSettings(
        enabled=bool(data.get("enabled", True)),
        lookback_hours=int(data.get("lookback_hours", 48)),
        local_news_path=str(data.get("local_news_path", "data/news.json")),
        local_social_path=str(data.get("local_social_path", "data/social.json")),
        entity_map_path=str(data.get("entity_map_path", "data/news_entities.json")),
        rss_urls=tuple(str(url) for url in data.get("rss_urls", [])),
        rss_timeout_seconds=float(data.get("rss_timeout_seconds", 4.0)),
        rss_max_workers=int(data.get("rss_max_workers", 12)),
        scrape_articles=bool(data.get("scrape_articles", True)),
        scrape_max_articles_per_cycle=int(data.get("scrape_max_articles_per_cycle", 30)),
        article_timeout_seconds=float(data.get("article_timeout_seconds", 4.0)),
        article_max_chars=int(data.get("article_max_chars", 5_000)),
        use_openai_context=bool(data.get("use_openai_context", False)),
    )


def _storage_settings(data: dict[str, Any]) -> StorageSettings:
    return StorageSettings(
        sqlite_path=str(data.get("sqlite_path", "state/agent_ledger.sqlite3")),
        audit_log_path=str(data.get("audit_log_path", "logs/audit.jsonl")),
    )


def _secrets() -> Secrets:
    return Secrets(
        etoro_api_key=os.getenv("ETORO_API_KEY", ""),
        etoro_user_key=os.getenv("ETORO_USER_KEY", ""),
        etoro_base_url=os.getenv("ETORO_BASE_URL", "https://public-api.etoro.com/api/v1"),
        etoro_user_agent=os.getenv(
            "ETORO_USER_AGENT",
            "AutoTrading-Agent/0.1 (+https://api-portal.etoro.com/)",
        ),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        allow_live=os.getenv("AUTOTRADER_ALLOW_LIVE", "").lower() in {"1", "true", "yes"},
    )
