from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GovernedRole:
    name: str
    purpose: str
    allowed_actions: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    evidence_outputs: tuple[str, ...]
    module_mapping: tuple[str, ...]
    deterministic_required: bool
    can_execute_trade: bool


def governed_roles() -> tuple[GovernedRole, ...]:
    return (
        GovernedRole(
            name="Research Agent",
            purpose="Gather market, chart, news, and regime context for review.",
            allowed_actions=("collect evidence", "score source context", "summarize market state"),
            forbidden_actions=("place orders", "bypass risk", "promote models"),
            evidence_outputs=("market snapshots", "news context", "regime features"),
            module_mapping=("data.py", "news.py", "chart.py", "regime.py"),
            deterministic_required=False,
            can_execute_trade=False,
        ),
        GovernedRole(
            name="Signal Agent",
            purpose="Propose BUY/SELL/HOLD decisions with reasons and confidence.",
            allowed_actions=("rank signals", "explain decisions", "attach confidence"),
            forbidden_actions=("execute trades", "override risk", "change policy"),
            evidence_outputs=("signal decisions", "feature snapshots", "decision reasons"),
            module_mapping=("signals.py", "ml.py", "timing.py", "allocation.py", "committee.py"),
            deterministic_required=False,
            can_execute_trade=False,
        ),
        GovernedRole(
            name="Risk Governor",
            purpose="Apply deterministic safety gates before any broker-facing action.",
            allowed_actions=("approve risk", "block risk", "enforce kill switch", "apply pre-trade policy"),
            forbidden_actions=("generate trading ideas", "ignore policy", "self-promote models"),
            evidence_outputs=("risk checks", "blocked reasons", "policy decisions"),
            module_mapping=("risk.py", "order_policy.py", "broker.py"),
            deterministic_required=True,
            can_execute_trade=False,
        ),
        GovernedRole(
            name="Model Governance Agent",
            purpose="Review training, drift, calibration, feature ablation, and promotion evidence.",
            allowed_actions=("record training runs", "record model versions", "reject candidates", "flag drift"),
            forbidden_actions=("guarantee performance", "promote without evidence", "trade directly"),
            evidence_outputs=("training runs", "model registry", "promotion events", "reliability reports"),
            module_mapping=("training.py", "reliability.py", "calibration.py"),
            deterministic_required=True,
            can_execute_trade=False,
        ),
        GovernedRole(
            name="Reconciliation Agent",
            purpose="Compare broker/demo state with local ledger expectations and raise alerts.",
            allowed_actions=("sync broker state", "compare positions", "raise reconciliation alerts"),
            forbidden_actions=("hide mismatches", "place orders", "change risk limits"),
            evidence_outputs=("broker snapshots", "reconciliation reports", "position drift alerts"),
            module_mapping=("reconcile.py", "broker_sync.py"),
            deterministic_required=True,
            can_execute_trade=False,
        ),
        GovernedRole(
            name="Reliability Agent",
            purpose="Create governance scorecards and detect insufficient or degraded evidence.",
            allowed_actions=("score reliability", "flag review states", "summarize drift"),
            forbidden_actions=("claim future returns", "override risk", "execute trades"),
            evidence_outputs=("feature ablation", "calibration", "paper scorecards", "governance reports"),
            module_mapping=("reliability.py", "monitoring.py"),
            deterministic_required=True,
            can_execute_trade=False,
        ),
        GovernedRole(
            name="Report Agent",
            purpose="Create public-safe summaries and private operator reports.",
            allowed_actions=("summarize evidence", "export redacted packs", "prepare dashboard views"),
            forbidden_actions=("include secrets", "publish raw ledgers", "make performance claims"),
            evidence_outputs=("dashboard views", "audit export packs", "weekly summaries"),
            module_mapping=("reporting.py", "export_pack.py", "web/service.py"),
            deterministic_required=True,
            can_execute_trade=False,
        ),
    )

