from __future__ import annotations

from dataclasses import dataclass

from agent.config import RiskSettings
from models import MarketSnapshot, OrderRequest, PortfolioState


@dataclass(frozen=True)
class PreTradePolicyResult:
    approved: bool
    reason: str


class ImmutablePreTradePolicy:
    """Final market-access style controls that run immediately before broker submission."""

    def __init__(self, risk: RiskSettings) -> None:
        self.risk = risk

    def evaluate(
        self,
        *,
        order: OrderRequest,
        snapshot: MarketSnapshot,
        portfolio: PortfolioState,
    ) -> PreTradePolicyResult:
        if order.action not in {"BUY", "SELL"}:
            return PreTradePolicyResult(False, "policy_invalid_action")
        if order.amount_usd <= 0:
            return PreTradePolicyResult(False, "policy_non_positive_order_amount")
        if order.leverage > 1:
            return PreTradePolicyResult(False, "policy_leverage_blocked")
        if snapshot.rate.age_seconds() > self.risk.max_data_staleness_seconds:
            return PreTradePolicyResult(False, "policy_stale_market_data")
        if snapshot.rate.spread_bps > self.risk.max_spread_bps:
            return PreTradePolicyResult(False, "policy_spread_too_wide")
        if not snapshot.instrument.is_currently_tradable:
            return PreTradePolicyResult(False, "policy_instrument_not_tradable")
        if not snapshot.instrument.is_exchange_open:
            return PreTradePolicyResult(False, "policy_exchange_closed")
        if order.action == "BUY":
            if order.stop_loss_rate is None or order.take_profit_rate is None:
                return PreTradePolicyResult(False, "policy_missing_protection")
            if order.stop_loss_rate >= snapshot.rate.mid or order.take_profit_rate <= snapshot.rate.mid:
                return PreTradePolicyResult(False, "policy_invalid_protection_prices")
            if order.amount_usd > portfolio.nav_usd * self.risk.max_position_pct_nav * 1.05:
                return PreTradePolicyResult(False, "policy_position_cap_breach")
            if order.amount_usd > portfolio.available_cash_usd * 0.98:
                return PreTradePolicyResult(False, "policy_cash_cap_breach")
        if order.action == "SELL" and not order.position_id:
            return PreTradePolicyResult(False, "policy_missing_position_id")
        return PreTradePolicyResult(True, "policy_approved")
