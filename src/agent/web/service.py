from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from agent.config import AppConfig
from agent.governance.events import GovernanceEvent
from agent.governance.roles import governed_roles
from agent.ledger import Ledger
from agent.point_in_time import PointInTimeReplayer
from agent.redaction import is_private_key, redact_identifier, redact_value
from agent.reporting import ReportingDashboard
from agent.risk import is_kill_switch_active


SAFETY_NOTICE = "Research/paper/demo trading only. Not investment advice. No performance promises."


class DashboardService:
    def __init__(
        self,
        config: AppConfig,
        ledger: Ledger,
        *,
        limit: int = 25,
        demo_data: bool = False,
    ) -> None:
        self.config = config
        self.ledger = ledger
        self.limit = limit
        self.demo_data = demo_data

    def base_context(self, *, active: str) -> dict[str, Any]:
        mode = self.config.execution.normalized_mode()
        environment = self.config.execution.normalized_environment()
        kill_switch_active = is_kill_switch_active(self.config.risk.kill_switch_path)
        return {
            "active": active,
            "safety_notice": SAFETY_NOTICE,
            "nav_items": [
                ("dashboard", "Overview", "/"),
                ("timeline", "Timeline", "/timeline"),
                ("decisions", "Decisions", "/decisions"),
                ("risk", "Risk", "/risk"),
                ("models", "Models", "/models"),
                ("reliability", "Reliability", "/reliability"),
                ("reconciliation", "Reconciliation", "/reconciliation"),
                ("incidents", "Incidents", "/incidents"),
                ("roles", "Agent Roles", "/governance/roles"),
                ("replay", "Replay", "/replay"),
                ("audit", "Audit", "/audit"),
            ],
            "runtime": {
                "mode": mode,
                "environment": environment,
                "kill_switch_active": kill_switch_active,
                "kill_switch_status_class": "bad" if kill_switch_active else "good",
                "ledger_name": Path(self.config.storage.sqlite_path).name,
                "audit_log_name": Path(self.config.storage.audit_log_path).name,
                "dangerous_runtime": mode == "live" or environment == "real",
                "demo_data": self.demo_data,
            },
        }

    def overview(self) -> dict[str, Any]:
        summary = ReportingDashboard(self.ledger).summary(limit=10)
        cycle_health = self.ledger.recent_cycle_health(limit=1)
        reconciliations = self.ledger.latest_reconciliations(limit=1)
        orders = self.ledger.latest_orders(limit=8)
        features = self.ledger.latest_feature_snapshots(limit=8)
        reliability = self.ledger.latest_reliability_reports(limit=5)
        return {
            "summary": summary,
            "latest_cycle": cycle_health[0] if cycle_health else {},
            "latest_reconciliation": reconciliations[0] if reconciliations else {},
            "recent_orders": self._public_orders(orders),
            "recent_features": self._public_features(features),
            "recent_reliability": reliability,
            "latest_risk": summary.get("latest_portfolio_risk", {}),
            "latest_training": self._public_training(summary.get("latest_training", {})),
        }

    def decisions(self) -> dict[str, Any]:
        features = self.ledger.latest_feature_snapshots(limit=self.limit)
        cycle_features = self.ledger.latest_cycle_features(limit=self.limit)
        committee_votes = self.ledger.latest_committee_votes(limit=self.limit)
        executions = self.ledger.latest_execution_simulations(limit=self.limit)
        return {
            "features": self._public_features(features),
            "cycle_features": cycle_features,
            "committee_votes": committee_votes,
            "executions": self._public_executions(executions),
        }

    def risk(self) -> dict[str, Any]:
        reports = self.ledger.latest_portfolio_risk_reports(limit=5)
        cycle_features = self.ledger.latest_cycle_features(limit=self.limit)
        blocked = [row for row in cycle_features if _boolish(row.get("risk_approved")) is False]
        return {
            "latest": reports[0] if reports else {},
            "reports": reports,
            "blocked": blocked,
            "settings": {
                "max_positions": self.config.risk.max_positions,
                "max_position_pct_nav": self.config.risk.max_position_pct_nav,
                "max_daily_loss_pct": self.config.risk.max_daily_loss_pct,
                "max_rolling_drawdown_pct": self.config.risk.max_rolling_drawdown_pct,
                "max_spread_bps": self.config.risk.max_spread_bps,
                "max_leverage": self.config.risk.max_leverage,
                "allow_averaging_down": self.config.risk.allow_averaging_down,
                "max_projected_stress_loss_pct": self.config.risk.max_projected_stress_loss_pct,
                "max_expected_shortfall_pct": self.config.risk.max_expected_shortfall_pct,
            },
        }

    def models(self) -> dict[str, Any]:
        training_runs = [self._public_training(row) for row in self.ledger.latest_model_training_runs(limit=10)]
        versions = [self._public_model_version(row) for row in self.ledger.latest_model_versions(limit=10)]
        promotions = self.ledger.latest_model_promotion_events(limit=self.limit)
        return {
            "latest_training": training_runs[0] if training_runs else {},
            "training_runs": training_runs,
            "model_versions": versions,
            "promotion_events": promotions,
        }

    def reliability(self) -> dict[str, Any]:
        reports = self.ledger.latest_reliability_reports(limit=self.limit)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for report in reports:
            grouped.setdefault(str(report.get("report_type", "unknown")), []).append(report)
        return {"reports": reports, "grouped_reports": grouped}

    def reconciliation(self) -> dict[str, Any]:
        environment = self.config.execution.normalized_environment()
        reconciliations = self.ledger.latest_reconciliations(limit=self.limit)
        latest = reconciliations[0] if reconciliations else {}
        broker_snapshot = self.ledger.latest_broker_account_snapshot(environment)
        if broker_snapshot is None:
            broker_snapshot = self.ledger.latest_broker_account_snapshot()
        return {
            "latest": latest,
            "reconciliations": reconciliations,
            "broker_snapshot": self._public_broker_snapshot(broker_snapshot or {}),
            "alerts": _alerts_from_reconciliation(latest),
            "recent_orders": self._public_orders(self.ledger.latest_orders(limit=10)),
        }

    def audit(self) -> dict[str, Any]:
        audit_path = Path(self.config.storage.audit_log_path)
        stat = audit_path.stat() if audit_path.exists() else None
        return {
            "orders": self._public_orders(self.ledger.latest_orders(limit=self.limit)),
            "features": self._public_features(self.ledger.latest_feature_snapshots(limit=self.limit)),
            "position_reviews": self._public_position_reviews(
                self.ledger.latest_position_reviews(limit=self.limit)
            ),
            "cycle_health": self.ledger.recent_cycle_health(limit=self.limit),
            "audit_log": {
                "exists": audit_path.exists(),
                "name": audit_path.name,
                "size_kb": round((stat.st_size if stat else 0) / 1024, 2),
                "modified_at": _timestamp_from_stat(stat),
            },
        }

    def timeline(self) -> dict[str, Any]:
        events: list[GovernanceEvent] = []
        for row in self.ledger.recent_cycle_health(limit=self.limit):
            halted = bool(row.get("halted"))
            events.append(
                GovernanceEvent(
                    timestamp=str(row.get("created_at", "")),
                    event_type="cycle",
                    title="Cycle halted" if halted else "Cycle completed",
                    status="halted" if halted else "operational",
                    summary=(
                        str(row.get("halt_reason") or "Cycle recorded governance evidence.")
                        if halted
                        else f"{row.get('decision_count', 0)} decisions, {row.get('order_count', 0)} orders."
                    ),
                    severity="bad" if halted else "good",
                    evidence_link="/audit",
                )
            )
        for row in self._public_features(self.ledger.latest_feature_snapshots(limit=self.limit)):
            events.append(
                GovernanceEvent(
                    timestamp=str(row.get("created_at", "")),
                    event_type="decision",
                    title=f"{row.get('symbol')} {row.get('action')} decision evidence",
                    status="recorded",
                    summary=str(row.get("reason") or "Decision feature snapshot recorded."),
                    severity=status_class(row.get("risk_approved")),
                    symbol=str(row.get("symbol") or ""),
                    evidence_link=f"/decisions/{row.get('id')}",
                )
            )
        for row in self.ledger.latest_risk_checks(limit=self.limit):
            approved = bool(row.get("approved"))
            events.append(
                GovernanceEvent(
                    timestamp=str(row.get("created_at", "")),
                    event_type="risk",
                    title=f"{row.get('symbol')} risk {'approved' if approved else 'blocked'}",
                    status="approved" if approved else "blocked",
                    summary=str(row.get("reason") or ""),
                    severity="good" if approved else "bad",
                    symbol=str(row.get("symbol") or ""),
                    evidence_link="/risk/controls",
                )
            )
        for row in self._public_orders(self.ledger.latest_orders(limit=self.limit)):
            events.append(
                GovernanceEvent(
                    timestamp=str(row.get("created_at", "")),
                    event_type="order",
                    title=f"{row.get('symbol')} {row.get('action')} order record",
                    status="accepted" if row.get("accepted") else "rejected",
                    summary=str(row.get("message") or "Order event recorded."),
                    severity=status_class(row.get("accepted")),
                    symbol=str(row.get("symbol") or ""),
                    evidence_link="/audit",
                )
            )
        for row in self._public_executions(self.ledger.latest_execution_simulations(limit=self.limit)):
            events.append(
                GovernanceEvent(
                    timestamp=str(row.get("created_at", "")),
                    event_type="order",
                    title=f"{row.get('symbol')} execution simulation",
                    status="simulated",
                    summary=(
                        f"Quality {format_number(row.get('quality_score'))}, "
                        f"expected slippage {format_number(row.get('expected_slippage_bps'))} bps."
                    ),
                    severity="neutral",
                    symbol=str(row.get("symbol") or ""),
                    evidence_link="/decisions",
                )
            )
        for row in self.ledger.latest_reconciliations(limit=self.limit):
            events.append(
                GovernanceEvent(
                    timestamp=str(row.get("created_at", "")),
                    event_type="reconciliation",
                    title="Broker reconciliation",
                    status=str(row.get("status") or "recorded"),
                    summary=str(row.get("message") or ""),
                    severity=status_class(row.get("status")),
                    evidence_link="/reconciliation",
                )
            )
        for row in self.ledger.latest_reliability_reports(limit=self.limit):
            events.append(
                GovernanceEvent(
                    timestamp=str(row.get("created_at", "")),
                    event_type="reliability",
                    title=f"{row.get('report_type')} reliability report",
                    status=str(row.get("status") or "recorded"),
                    summary=str(row.get("summary") or ""),
                    severity=status_class(row.get("status")),
                    evidence_link="/reliability",
                )
            )
        for row in self.ledger.latest_model_promotion_events(limit=self.limit):
            promoted = bool(row.get("promoted"))
            events.append(
                GovernanceEvent(
                    timestamp=str(row.get("created_at", "")),
                    event_type="model",
                    title=f"{row.get('model_version')} {'promoted' if promoted else 'rejected'}",
                    status="promoted" if promoted else "rejected",
                    summary=str(row.get("reason") or ""),
                    severity="good" if promoted else "bad",
                    evidence_link=f"/models/{row.get('model_version')}",
                )
            )
        output = sorted((asdict(event) for event in events), key=lambda item: item["timestamp"], reverse=True)
        return {"events": output}

    def decision_detail(self, snapshot_id: int) -> dict[str, Any]:
        snapshot = self.ledger.feature_snapshot_by_id(snapshot_id)
        if not snapshot:
            return {"decision": {}, "missing": True}
        public_snapshot = self._public_features([snapshot])[0]
        symbol = str(snapshot.get("symbol") or "")
        features = snapshot.get("features_json") if isinstance(snapshot.get("features_json"), dict) else {}
        risk_checks = self.ledger.latest_risk_checks_for_symbol(symbol, limit=5)
        orders = self._public_orders(self.ledger.latest_orders_for_symbol(symbol, limit=5))
        cycle_rows = [
            row
            for row in self.ledger.latest_cycle_features(limit=100)
            if str(row.get("symbol", "")).upper() == symbol.upper()
        ][:5]
        committee_votes = [
            row
            for row in self.ledger.latest_committee_votes(limit=50)
            if str(row.get("symbol", "")).upper() == symbol.upper()
        ][:5]
        executions = [
            row
            for row in self._public_executions(self.ledger.latest_execution_simulations(limit=50))
            if str(row.get("symbol", "")).upper() == symbol.upper()
        ][:5]
        reconciliations = self.ledger.latest_reconciliations(limit=5)
        reliability_warnings = [
            row
            for row in self.ledger.latest_reliability_reports(limit=20)
            if status_class(row.get("status")) in {"warn", "bad"}
        ][:5]
        return {
            "decision": public_snapshot,
            "feature_groups": _feature_groups(features),
            "risk_checks": risk_checks,
            "orders": orders,
            "cycle_rows": cycle_rows,
            "committee_votes": committee_votes,
            "executions": executions,
            "reconciliations": reconciliations,
            "reliability_warnings": reliability_warnings,
            "relationship_labels": {
                "risk": "same_symbol_recent" if risk_checks else "unavailable",
                "orders": "same_symbol_recent" if orders else "unavailable",
                "cycle": "same_cycle" if cycle_rows else "unavailable",
                "committee": "same_symbol_recent" if committee_votes else "unavailable",
            },
            "missing": False,
        }

    def risk_controls(self) -> dict[str, Any]:
        latest_risk = self.ledger.latest_risk_checks(limit=100)
        latest_by_reason: dict[str, dict[str, Any]] = {}
        for row in latest_risk:
            reason = str(row.get("reason") or "approved")
            latest_by_reason.setdefault(reason, row)
        controls = [
            _control(
                "Kill switch",
                True,
                self.config.risk.kill_switch_path,
                "halted" if is_kill_switch_active(self.config.risk.kill_switch_path) else "inactive",
                "Kill switch file is present." if is_kill_switch_active(self.config.risk.kill_switch_path) else "No active halt file.",
                "",
                "risk.py",
            ),
            _control("Max positions", True, self.config.risk.max_positions, *_breach("max_positions_reached", latest_by_reason), "risk.py"),
            _control("Max position pct NAV", True, format_percent(self.config.risk.max_position_pct_nav), *_breach("position_cap", latest_by_reason), "risk.py"),
            _control("Max gross exposure", True, format_percent(self.config.risk.max_gross_exposure_pct), *_breach("gross_exposure_limit", latest_by_reason), "portfolio.py"),
            _control("Max daily loss", True, format_percent(self.config.risk.max_daily_loss_pct), *_breach("daily_loss_limit", latest_by_reason), "risk.py"),
            _control("Max rolling drawdown", True, format_percent(self.config.risk.max_rolling_drawdown_pct), *_breach("rolling_drawdown_limit", latest_by_reason), "risk.py"),
            _control("Max spread bps", True, self.config.risk.max_spread_bps, *_breach("spread_too_wide", latest_by_reason), "risk.py"),
            _control("Max data staleness", True, f"{self.config.risk.max_data_staleness_seconds}s", *_breach("stale_market_data", latest_by_reason), "risk.py"),
            _control("Cooldown after loss", True, f"{self.config.risk.cooldown_after_loss_minutes}m", *_breach("cooldown_after_loss", latest_by_reason), "risk.py"),
            _control("One order per symbol per cycle", self.config.risk.one_order_per_symbol_per_cycle, "enabled", *_breach("one_order_per_symbol_per_cycle", latest_by_reason), "risk.py"),
            _control("Averaging down", not self.config.risk.allow_averaging_down, "disabled", *_breach("averaging_down_disabled", latest_by_reason), "risk.py"),
            _control("Max leverage", True, self.config.risk.max_leverage, *_breach("live_leverage_disabled_for_phase_one", latest_by_reason), "risk.py"),
            _control("Regime risk-off buy block", self.config.risk.regime_risk_off_buy_block, "enabled", *_breach("regime_risk_off_buy_block", latest_by_reason), "risk.py"),
            _control("Event-driven buy block", self.config.risk.regime_event_driven_buy_block, "enabled", *_breach("regime_event_driven_buy_block", latest_by_reason), "risk.py"),
            _control("Min avg daily dollar volume", True, format_money(self.config.risk.min_avg_daily_dollar_volume), *_breach("liquidity_too_thin", latest_by_reason), "execution.py"),
            _control("Max expected slippage", True, f"{self.config.risk.max_expected_slippage_bps} bps", *_breach("expected_slippage_too_high", latest_by_reason), "execution.py"),
            _control("Min execution quality", True, self.config.risk.min_execution_quality_score, *_breach("execution_quality_too_low", latest_by_reason), "execution.py"),
            _control("Sector exposure limit", True, format_percent(self.config.risk.max_sector_exposure_pct), *_breach("sector_exposure_limit", latest_by_reason), "portfolio.py"),
            _control("Sector position limit", True, self.config.risk.max_sector_positions, *_breach("sector_position_limit", latest_by_reason), "portfolio.py"),
            _control("Peer group crowding", True, self.config.risk.max_peer_group_positions, *_breach("peer_group_crowding_limit", latest_by_reason), "portfolio.py"),
            _control("Symbol correlation limit", True, self.config.risk.max_symbol_correlation, *_breach("symbol_correlation_limit", latest_by_reason), "portfolio.py"),
            _control("Average correlation limit", True, self.config.risk.max_average_correlation, *_breach("average_correlation_limit", latest_by_reason), "portfolio.py"),
            _control("Max portfolio HHI", True, self.config.risk.max_portfolio_hhi, *_breach("portfolio_hhi_limit", latest_by_reason), "portfolio.py"),
            _control("Max projected stress loss", True, format_percent(self.config.risk.max_projected_stress_loss_pct), *_breach("projected_stress_loss_limit", latest_by_reason), "portfolio.py"),
            _control("Max expected shortfall", True, format_percent(self.config.risk.max_expected_shortfall_pct), *_breach("expected_shortfall_limit", latest_by_reason), "portfolio.py"),
            _control("Immutable pre-trade policy", True, "present", "pass", "Policy module loaded", "", "order_policy.py"),
            _control("Live mode dual gate", True, "AUTOTRADER_ALLOW_LIVE + --allow-live", "pass", "No live controls in dashboard", "", "broker.py"),
        ]
        return {"controls": controls}

    def model_card(self, model_version: str) -> dict[str, Any]:
        model = self.ledger.model_version_by_version(model_version)
        if not model:
            return {"model": {}, "missing": True}
        public_model = self._public_model_version(model)
        training_runs = [
            self._public_training(row)
            for row in self.ledger.latest_model_training_runs(limit=20)
            if row.get("model_version") == model_version
            or (isinstance(row.get("parameters_json"), dict) and row["parameters_json"].get("model_version") == model_version)
        ]
        events = [
            row for row in self.ledger.latest_model_promotion_events(limit=50)
            if row.get("model_version") == model_version
        ]
        reliability = self.ledger.latest_reliability_reports(limit=5)
        limitations = _model_limitations(public_model, training_runs, reliability)
        return {
            "model": public_model,
            "training": training_runs[0] if training_runs else {},
            "training_evidence_status": "matched" if training_runs else "not_found",
            "promotion_events": events,
            "reliability_context": reliability,
            "known_limitations": limitations,
            "missing": False,
        }

    def incidents(self) -> dict[str, Any]:
        incidents: list[dict[str, Any]] = []
        for row in self.ledger.recent_cycle_health(limit=self.limit):
            if row.get("halted"):
                incidents.append(_incident(row.get("created_at"), "halt", "critical", "open", "cycle_health", f"Cycle halted: {row.get('halt_reason')}", "Review kill-switch and cycle logs."))
        if is_kill_switch_active(self.config.risk.kill_switch_path):
            incidents.append(_incident("", "kill_switch", "critical", "open", "risk.py", "Kill switch is currently active.", "Confirm whether the halt is intentional."))
        rejected_orders = [row for row in self.ledger.latest_orders(limit=50) if not row.get("accepted")]
        if len(rejected_orders) >= 3:
            incidents.append(_incident(rejected_orders[0].get("created_at"), "rejected_orders", "warning", "review", "orders", f"{len(rejected_orders)} recent rejected orders.", "Inspect order policy and broker messages."))
        for row in self.ledger.latest_reconciliations(limit=self.limit):
            if status_class(row.get("status")) in {"warn", "bad"}:
                incidents.append(_incident(row.get("created_at"), "reconciliation", "warning", str(row.get("status")), "reconciliations", str(row.get("message")), "Review broker/local state differences."))
        for row in self.ledger.latest_reliability_reports(limit=self.limit):
            if status_class(row.get("status")) in {"warn", "bad"}:
                incidents.append(_incident(row.get("created_at"), "reliability", "review", str(row.get("status")), "reliability_reports", str(row.get("summary")), "Review reliability report before trusting future decisions."))
        for row in self.ledger.latest_model_promotion_events(limit=self.limit):
            if not row.get("promoted"):
                incidents.append(_incident(row.get("created_at"), "model_rejection", "review", "rejected", "model_promotion_events", f"Model {row.get('model_version')} rejected: {row.get('reason')}", "Review model card and promotion gate metrics."))
        for row in self.ledger.latest_risk_checks(limit=self.limit):
            if not row.get("approved"):
                incidents.append(_incident(row.get("created_at"), "risk_block", "warning", "blocked", "risk_checks", f"{row.get('symbol')} blocked: {row.get('reason')}", "Inspect risk control matrix."))
        counts = {"critical": 0, "warning": 0, "review": 0, "ok": 0}
        for incident in incidents:
            counts[str(incident["severity"])] = counts.get(str(incident["severity"]), 0) + 1
        return {"incidents": sorted(incidents, key=lambda item: item.get("timestamp", ""), reverse=True), "counts": counts}

    def governance_roles(self) -> dict[str, Any]:
        return {"roles": [asdict(role) for role in governed_roles()]}

    def replay_index(self) -> dict[str, Any]:
        return {"features": self._public_features(self.ledger.latest_feature_snapshots(limit=self.limit))}

    def replay_decision(self, snapshot_id: int) -> dict[str, Any]:
        detail = self.decision_detail(snapshot_id)
        if detail.get("missing"):
            return {"missing": True}
        decision = detail["decision"]
        as_of = str(decision.get("created_at") or "")
        symbol = str(decision.get("symbol") or "")
        missing: list[str] = []
        try:
            replay = PointInTimeReplayer(self.ledger).replay(as_of, symbol=symbol, limit=20)
            context = _replay_context_summary(replay)
        except Exception as exc:  # defensive: replay must never break the UI
            context = {"error": str(exc)}
            missing.append("point-in-time replay")
        if not detail.get("cycle_rows"):
            missing.append("no related cycle feature row")
        if not detail.get("risk_checks"):
            missing.append("no related risk check")
        if not self.ledger.latest_model_versions(limit=1):
            missing.append("no model version")
        if not detail.get("reconciliations"):
            missing.append("no reconciliation after decision")
        confidence = "complete" if not missing else "partial" if len(missing) <= 2 else "limited"
        return {
            "missing": False,
            "selected_decision": decision,
            "as_of_timestamp": as_of,
            "point_in_time_context": context,
            "related_features": detail.get("feature_groups", {}),
            "related_risk": detail.get("risk_checks", []),
            "related_orders": detail.get("orders", []),
            "related_model": self._public_model_version(self.ledger.latest_model_versions(limit=1)[0]) if self.ledger.latest_model_versions(limit=1) else {},
            "related_reconciliation": detail.get("reconciliations", []),
            "changed_afterward": {
                "later_reliability_warnings": detail.get("reliability_warnings", []),
                "later_orders": detail.get("orders", []),
            },
            "replay_confidence": confidence,
            "missing_evidence": missing,
        }

    def _public_orders(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output = []
        for row in rows:
            public = dict(row)
            public["broker_order_id"] = _redact_identifier(public.get("broker_order_id"))
            public.pop("raw_json", None)
            output.append(public)
        return output

    def _public_features(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output = []
        for row in rows:
            features = row.get("features_json")
            public = dict(row)
            if isinstance(features, dict):
                public["reason"] = _first_text(
                    features,
                    ("reasoning_summary", "news_summary", "market_summary", "timing_reason"),
                )
                public["risk_approved"] = features.get("risk_approved")
                public["committee_approved"] = features.get("committee_approved")
            else:
                public["reason"] = ""
            public.pop("features_json", None)
            output.append(public)
        return output

    def _public_position_reviews(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output = []
        for row in rows:
            public = dict(row)
            public.pop("features_json", None)
            output.append(public)
        return output

    def _public_executions(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output = []
        for row in rows:
            public = dict(row)
            public.pop("raw_json", None)
            output.append(public)
        return output

    def _public_training(self, row: object) -> dict[str, Any]:
        if not isinstance(row, dict) or not row:
            return {}
        public = dict(row)
        params = public.get("parameters_json")
        if isinstance(params, dict) and params.get("artifact_path"):
            params = dict(params)
            params["artifact_path"] = Path(str(params["artifact_path"])).name
            public["parameters_json"] = params
        return public

    def _public_model_version(self, row: dict[str, Any]) -> dict[str, Any]:
        public = dict(row)
        if public.get("artifact_path"):
            public["artifact_path"] = Path(str(public["artifact_path"])).name
        return public

    def _public_broker_snapshot(self, row: dict[str, Any]) -> dict[str, Any]:
        public = dict(row)
        public.pop("raw_json", None)
        return public


def as_public_value(value: Any) -> Any:
    return redact_value(value)


def format_percent(value: Any) -> str:
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return "n/a"


def format_number(value: Any, *, digits: int = 3) -> str:
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"


def format_money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "n/a"


def status_class(value: Any) -> str:
    text = str(value).lower()
    if text in {"ok", "pass", "passed", "approved", "active", "healthy"} or value is True:
        return "good"
    if text in {"warning", "review", "not_ready", "insufficient_data", "candidate"}:
        return "warn"
    if text in {"alert", "fail", "failed", "rejected", "halted", "blocked"} or value is False:
        return "bad"
    return "neutral"


def compact_items(value: Any, *, limit: int = 8) -> list[tuple[str, Any]]:
    public = as_public_value(value)
    if not isinstance(public, dict):
        return []
    return [(str(key), _display_value(val)) for key, val in list(public.items())[:limit]]


def _display_value(value: Any) -> Any:
    if isinstance(value, dict):
        return f"{len(value)} fields summarized"
    if isinstance(value, list):
        return f"{len(value)} records summarized"
    if isinstance(value, tuple):
        return f"{len(value)} records summarized"
    return value


def _replay_context_summary(replay: Any) -> dict[str, Any]:
    cycle_features = list(getattr(replay, "cycle_features", ()))
    decisions = list(getattr(replay, "decisions", ()))
    risk_checks = list(getattr(replay, "risk_checks", ()))
    orders = list(getattr(replay, "orders", ()))
    news_source_stats = list(getattr(replay, "news_source_stats", ()))
    portfolio_risk_reports = list(getattr(replay, "portfolio_risk_reports", ()))
    symbols = sorted(
        {
            str(row.get("symbol"))
            for row in cycle_features
            if row.get("symbol") not in ("", None)
        }
    )
    approved = sum(1 for row in cycle_features if _boolish(row.get("risk_approved")) is True)
    blocked = sum(1 for row in cycle_features if _boolish(row.get("risk_approved")) is False)
    latest_cycle = next((row.get("cycle_id") for row in cycle_features if row.get("cycle_id")), "")
    latest_order = orders[0] if orders else {}
    return {
        "cycle_feature_rows": len(cycle_features),
        "decision_rows": len(decisions),
        "risk_check_rows": len(risk_checks),
        "order_rows": len(orders),
        "news_source_rows": len(news_source_stats),
        "portfolio_risk_rows": len(portfolio_risk_reports),
        "symbols_seen": ", ".join(symbols[:8]) if symbols else "n/a",
        "risk_approved_rows": approved,
        "risk_blocked_rows": blocked,
        "latest_cycle_id": latest_cycle or "n/a",
        "latest_order_symbol": latest_order.get("symbol", "n/a"),
        "latest_order_status": "accepted" if latest_order.get("accepted") else "rejected" if latest_order else "n/a",
    }


def _alerts_from_reconciliation(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw = row.get("raw_json") if isinstance(row, dict) else {}
    if not isinstance(raw, dict):
        return []
    alerts = raw.get("alerts", [])
    return alerts if isinstance(alerts, list) else []


def _timestamp_from_stat(stat: Any) -> str:
    if stat is None:
        return "n/a"
    from datetime import UTC, datetime

    return datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()


def _first_text(features: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = features.get(key)
        if value:
            return str(value)
    return ""


def _redact_identifier(value: Any) -> str:
    return redact_identifier(value)


def _looks_private(key: Any) -> bool:
    return is_private_key(str(key))


def _boolish(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"true", "1", "yes", "approved"}:
            return True
        if lowered in {"false", "0", "no", "rejected", "blocked"}:
            return False
    return None


def _feature_groups(features: dict[str, Any]) -> dict[str, list[tuple[str, Any]]]:
    groups = {
        "Decision scoring": ("score", "confidence", "reasoning_summary", "model_version"),
        "Market context": ("market_summary", "symbol_last_price", "symbol_spread_bps", "relative_strength_21d"),
        "News context": ("news_summary", "news_sentiment", "news_catalyst", "news_source_count"),
        "Regime context": ("regime_name", "regime_confidence", "regime_stress_score"),
        "Allocation context": ("allocation_approved", "allocation_target_notional_usd"),
        "Risk context": ("risk_approved", "risk_reason", "risk_target_notional_usd"),
        "Execution context": ("execution_quality_score", "expected_slippage_bps", "fill_probability"),
        "Model context": ("model_version", "meta_summary", "meta_approval_score"),
        "Timing context": ("timing_reason", "timing_confidence", "timing_earliest_days", "timing_latest_days"),
    }
    output: dict[str, list[tuple[str, Any]]] = {}
    for group, keys in groups.items():
        values = [(key, features[key]) for key in keys if key in features and features[key] not in ("", None)]
        if values:
            output[group] = values
    return output


def _control(
    name: str,
    enabled: bool,
    threshold: Any,
    latest_status: str,
    latest_reason: str,
    last_breach_time: str,
    evidence_source: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "enabled": enabled,
        "threshold": threshold,
        "latest_status": latest_status,
        "latest_reason": latest_reason,
        "last_breach_time": last_breach_time,
        "evidence_source": evidence_source,
        "severity": status_class(latest_status),
    }


def _breach(reason: str, latest_by_reason: dict[str, dict[str, Any]]) -> tuple[str, str, str]:
    row = latest_by_reason.get(reason)
    if not row:
        return ("pass", "No recent breach recorded.", "")
    return ("blocked", str(row.get("reason") or reason), str(row.get("created_at") or ""))


def _model_limitations(
    model: dict[str, Any],
    training_runs: list[dict[str, Any]],
    reliability: list[dict[str, Any]],
) -> list[str]:
    limitations: list[str] = []
    training = training_runs[0] if training_runs else {}
    metrics = model.get("metrics_json") if isinstance(model.get("metrics_json"), dict) else {}
    if not training:
        limitations.append("No matching training run was found for this model version.")
    if int(training.get("sample_count") or 0) < 100:
        limitations.append("Sample count is still limited for production confidence.")
    if model.get("status") == "rejected":
        limitations.append("Model was rejected by the promotion gate.")
    if not model.get("feature_names_json"):
        limitations.append("Feature names are missing from the model registry record.")
    if not any("holdout" in str(key) for key in metrics):
        limitations.append("Holdout metrics are not fully populated.")
    if not any("walk" in str(key) for key in metrics):
        limitations.append("Walk-forward metrics are not fully populated.")
    if not reliability:
        limitations.append("No active reliability report is available.")
    return limitations or ["No major limitations inferred from the current registry record."]


def _incident(
    timestamp: Any,
    incident_type: str,
    severity: str,
    status: str,
    source: str,
    summary: str,
    recommended_next_step: str,
) -> dict[str, str]:
    return {
        "timestamp": str(timestamp or ""),
        "incident_type": incident_type,
        "severity": severity,
        "status": status,
        "source": source,
        "summary": summary,
        "recommended_next_step": recommended_next_step,
    }
