from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from models import SignalDecision


@dataclass(frozen=True)
class CommitteeVote:
    member: str
    score: float
    approved: bool
    reason: str


@dataclass(frozen=True)
class CommitteeResult:
    symbol: str
    action: str
    approved: bool
    consensus_score: float
    reason: str
    votes: tuple[CommitteeVote, ...]

    def as_features(self) -> dict[str, float | str | bool]:
        return {
            "committee_approved": self.approved,
            "committee_consensus_score": self.consensus_score,
            "committee_reason": self.reason,
            "committee_member_count": len(self.votes),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "approved": self.approved,
            "consensus_score": self.consensus_score,
            "reason": self.reason,
            "votes": [vote.__dict__ for vote in self.votes],
        }


class DecisionCommittee:
    """Independent decision checks that prevent one noisy signal from dominating."""

    def evaluate(self, decision: SignalDecision) -> CommitteeResult:
        if decision.action == "HOLD":
            return CommitteeResult(
                symbol=decision.symbol,
                action=decision.action,
                approved=True,
                consensus_score=1.0,
                reason="hold_decision_no_order_risk",
                votes=(),
            )

        features = decision.features
        votes = (
            _vote("alpha", _mean(_num(decision.score), _num(decision.confidence), _num(features.get("meta_approval_score"), 0.55)), 0.55),
            _vote("regime", _regime_score(features), 0.48),
            _vote("portfolio", _portfolio_score(features), 0.50),
            _vote("execution", _execution_score(features), 0.50),
            _vote("news", _news_score(features), 0.42),
            _vote("timing", _timing_score(features), 0.45),
            _vote("veto_memory", _veto_memory_score(features), 0.48),
        )
        consensus = sum(vote.score for vote in votes) / len(votes)
        approvals = sum(1 for vote in votes if vote.approved)
        required_score = 0.45 if decision.action == "SELL" else 0.52
        required_approvals = 3 if decision.action == "SELL" else 4
        approved = consensus >= required_score and approvals >= required_approvals
        weak_members = [vote.member for vote in votes if not vote.approved]
        reason = (
            f"committee_consensus_ok score={consensus:.3f}"
            if approved
            else f"committee_rejected weak={','.join(weak_members[:3])} score={consensus:.3f}"
        )
        return CommitteeResult(decision.symbol, decision.action, approved, consensus, reason, votes)


def _vote(member: str, score: float, threshold: float) -> CommitteeVote:
    clean_score = max(min(score, 1.0), 0.0)
    return CommitteeVote(
        member=member,
        score=clean_score,
        approved=clean_score >= threshold,
        reason=f"{member}_score={clean_score:.3f} threshold={threshold:.3f}",
    )


def _regime_score(features: dict[str, Any]) -> float:
    strength = _num(features.get("market_regime_strength"), _num(features.get("regime_confidence"), 0.5))
    stress = _num(features.get("regime_stress_score"), 0.4)
    return strength * 0.75 + (1 - stress) * 0.25


def _portfolio_score(features: dict[str, Any]) -> float:
    if features.get("allocation_approved") is False:
        return 0.0
    diversification = _num(features.get("allocation_diversification_score"), 0.7)
    stress = _num(features.get("allocation_max_stress_loss_pct"), 0.03)
    return diversification * 0.65 + max(0.0, 1 - stress * 12) * 0.35


def _execution_score(features: dict[str, Any]) -> float:
    quality = _num(features.get("execution_sim_quality_score"), _num(features.get("risk_execution_quality_score"), 0.65))
    fill_probability = _num(features.get("execution_sim_fill_probability"), 0.75)
    return quality * 0.70 + fill_probability * 0.30


def _news_score(features: dict[str, Any]) -> float:
    sentiment = _num(features.get("news_sentiment"), 0.0)
    catalyst = _num(features.get("news_catalyst"), 0.0)
    return 0.50 + sentiment * 0.25 + catalyst * 0.25


def _timing_score(features: dict[str, Any]) -> float:
    confidence = _num(features.get("timing_confidence"), 0.55)
    invalidation = _num(features.get("timing_invalidation_days"), 3.0)
    return confidence * 0.75 + min(invalidation / 10, 1.0) * 0.25


def _veto_memory_score(features: dict[str, Any]) -> float:
    veto_score = _num(features.get("veto_memory_score"), 0.0)
    loss_count = _num(features.get("veto_memory_loss_count"), 0.0)
    if loss_count < 3:
        return 0.70
    return max(0.0, 1.0 - veto_score)


def _mean(*values: float) -> float:
    return sum(values) / len(values) if values else 0.0


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
