from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.ledger import Ledger


@dataclass(frozen=True)
class ReliabilityReport:
    report_type: str
    status: str
    summary: str
    raw: dict[str, Any]


class ReliabilityAnalyzer:
    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger

    def feature_ablation_report(self, *, limit: int = 5000) -> ReliabilityReport:
        rows = self.ledger.cycle_feature_training_rows(limit=limit)
        if len(rows) < 10:
            report = ReliabilityReport("feature_ablation", "insufficient_data", "not enough outcomes for feature ablation", {"rows": len(rows)})
            self.ledger.record_reliability_report(**report.__dict__)
            return report
        features = _numeric_features(rows)
        baseline = _profit_capture(rows)
        entries: list[dict[str, Any]] = []
        for feature in features:
            filtered = [row for row in rows if _as_float(_feature_value(row, feature), 0.0) >= _median(rows, feature)]
            if len(filtered) < 3:
                continue
            capture = _profit_capture(filtered)
            false_positive_rate = _false_positive_rate(filtered)
            entries.append(
                {
                    "feature": feature,
                    "baseline_profit_capture": baseline,
                    "filtered_profit_capture": capture,
                    "profit_lift": capture - baseline,
                    "false_positive_rate": false_positive_rate,
                    "sample_count": len(filtered),
                }
            )
        entries.sort(key=lambda row: (row["profit_lift"], -row["false_positive_rate"]), reverse=True)
        groups = _group_ablation(rows)
        report = ReliabilityReport(
            "feature_ablation",
            "ok",
            f"ranked {len(entries)} numeric features by profit lift and false-positive rate",
            {"baseline_profit_capture": baseline, "features": entries[:50], "groups": groups},
        )
        self.ledger.record_reliability_report(**report.__dict__)
        return report

    def calibration_report(self, *, limit: int = 5000) -> ReliabilityReport:
        rows = self.ledger.cycle_feature_training_rows(limit=limit)
        if len(rows) < 10:
            report = ReliabilityReport("calibration", "insufficient_data", "not enough outcomes for calibration", {"rows": len(rows)})
            self.ledger.record_reliability_report(**report.__dict__)
            return report
        fields = (
            "decision_confidence",
            "meta_approval_score",
            "regime_confidence",
            "news_source_credibility",
            "execution_sim_fill_probability",
        )
        buckets = {field: _calibration_buckets(rows, field) for field in fields}
        ece = {
            field: _expected_calibration_error(buckets[field])
            for field in fields
        }
        report = ReliabilityReport(
            "calibration",
            "ok",
            "calibrated predicted confidence fields against realized win rates",
            {"fields": buckets, "expected_calibration_error": ece},
        )
        self.ledger.record_reliability_report(**report.__dict__)
        return report

    def paper_scorecard(self, *, limit: int = 5000) -> ReliabilityReport:
        rows = self.ledger.cycle_feature_training_rows(limit=limit)
        orders = self.ledger.latest_orders(limit=500)
        reconciliations = self.ledger.latest_reliability_reports("reconciliation", limit=20)
        trades = len(rows)
        returns = [_as_float(row.get("outcome_return_pct"), 0.0) for row in rows]
        wins = sum(1 for value in returns if value > 0)
        max_drawdown = _max_drawdown([1.0 + sum(returns[: index + 1]) for index in range(len(returns))])
        rejected_orders = sum(1 for order in orders if not int(order.get("accepted") or 0))
        reject_rate = rejected_orders / len(orders) if orders else 0.0
        win_rate = wins / trades if trades else 0.0
        status = "pass" if trades >= 30 and win_rate >= 0.48 and max_drawdown <= 0.12 and reject_rate <= 0.15 else "not_ready"
        report = ReliabilityReport(
            "paper_scorecard",
            status,
            f"paper readiness {status}: trades={trades} win_rate={win_rate:.2f} drawdown={max_drawdown:.2%}",
            {
                "trades": trades,
                "win_rate": win_rate,
                "max_drawdown": max_drawdown,
                "order_reject_rate": reject_rate,
                "recent_reconciliation_reports": reconciliations,
            },
        )
        self.ledger.record_reliability_report(**report.__dict__)
        return report

    def labeled_dataset_report(self, *, limit: int = 5000) -> ReliabilityReport:
        examples = self.ledger.training_examples(limit=limit)
        complete = 0
        for row in examples:
            features = row.get("entry_features_json", {})
            if not isinstance(features, dict):
                continue
            required = ("news_sentiment", "regime_confidence", "execution_sim_fill_probability", "timing_confidence")
            if all(key in features for key in required):
                complete += 1
        completeness = complete / len(examples) if examples else 0.0
        status = "ok" if len(examples) >= 30 and completeness >= 0.85 else "needs_more_clean_labels"
        report = ReliabilityReport(
            "labeled_dataset",
            status,
            f"labeled outcomes={len(examples)} feature_completeness={completeness:.1%}",
            {"sample_count": len(examples), "complete_samples": complete, "feature_completeness": completeness},
        )
        self.ledger.record_reliability_report(**report.__dict__)
        return report

    def governance_dashboard(self, *, limit: int = 5000) -> ReliabilityReport:
        rows = self.ledger.cycle_feature_training_rows(limit=limit)
        execution = self.ledger.execution_slippage_profile(limit=500)
        source_profiles = self.ledger.news_source_credibility_profiles()
        drift = _drift_report(rows)
        noisy_sources = [
            {"source": source, "noise_score": profile.get("noise_score"), "samples": profile.get("sample_count")}
            for source, profile in source_profiles.items()
            if _as_float(profile.get("noise_score"), 0.0) >= 0.55 and int(profile.get("sample_count", 0) or 0) >= 3
        ]
        status = "ok"
        if drift.get("max_feature_drift", 0.0) > 1.0 or _as_float(execution.get("avg_prediction_error_bps"), 0.0) > 20:
            status = "review"
        report = ReliabilityReport(
            "governance_dashboard",
            status,
            "AI reliability dashboard for model, feature, source, execution, and decision drift",
            {
                "feature_drift": drift,
                "execution_drift": execution,
                "noisy_sources": noisy_sources[:20],
            },
        )
        self.ledger.record_reliability_report(**report.__dict__)
        return report


def classify_trade_root_cause(raw: dict[str, Any], return_pct: float) -> dict[str, Any]:
    entry = raw.get("entry_context", {})
    features = entry.get("features_json", entry.get("features", {})) if isinstance(entry, dict) else {}
    exit_features = raw.get("exit_features", {}) if isinstance(raw.get("exit_features", {}), dict) else {}
    causes: dict[str, float] = {
        "bad_entry": max(0.0, 0.55 - _as_float(features.get("timing_confidence"), 0.55)),
        "news_failure": max(0.0, _as_float(features.get("news_sentiment"), 0.0) - return_pct * 8),
        "regime_shift": max(0.0, _as_float(exit_features.get("regime_stress_score"), 0.0) - _as_float(features.get("regime_stress_score"), 0.0)),
        "execution_slippage": _as_float(features.get("execution_sim_expected_slippage_bps"), 0.0) / 100,
        "portfolio_beta": max(0.0, _as_float(features.get("allocation_max_stress_loss_pct"), 0.0) * 12),
    }
    if return_pct > 0:
        causes["winner"] = max(return_pct * 10, 0.1)
    primary = max(causes, key=causes.get)
    return {"primary_cause": primary, "severity": min(causes[primary], 1.0), "causes": causes}


def veto_patterns_from_features(features: dict[str, Any]) -> list[tuple[str, str]]:
    patterns: list[tuple[str, str]] = []
    regime = str(features.get("regime_name", "")).strip().lower()
    if regime:
        patterns.append((f"regime:{regime}", f"regime {regime}"))
    if _as_float(features.get("news_sentiment"), 0.0) <= -0.25:
        patterns.append(("news:negative", "negative news"))
    if _as_float(features.get("execution_sim_expected_slippage_bps"), 0.0) >= 20:
        patterns.append(("execution:high_slippage", "high expected slippage"))
    if _as_float(features.get("allocation_max_stress_loss_pct"), 0.0) >= 0.04:
        patterns.append(("portfolio:stress", "high portfolio stress"))
    if _as_float(features.get("timing_confidence"), 1.0) <= 0.45:
        patterns.append(("timing:low_confidence", "low timing confidence"))
    return patterns


def _numeric_features(rows: list[dict[str, Any]]) -> list[str]:
    names: set[str] = set()
    for row in rows:
        raw = row.get("raw_features_json", {})
        for key, value in {**row, **(raw if isinstance(raw, dict) else {})}.items():
            if isinstance(value, (int, float, bool)) and not str(key).startswith("outcome_"):
                names.add(str(key))
    return sorted(names)


def _group_ablation(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = {
        "news": ("news_sentiment", "news_catalyst", "news_source_count", "news_source_credibility"),
        "regime": ("regime_confidence", "regime_stress_score", "regime_size_multiplier"),
        "execution": ("execution_sim_quality_score", "execution_sim_fill_probability", "execution_sim_expected_slippage_bps"),
        "committee": ("committee_consensus_score", "committee_approved"),
        "timing": ("timing_confidence", "timing_likely_days", "timing_invalidation_days"),
        "portfolio": ("allocation_diversification_score", "allocation_max_stress_loss_pct", "allocation_hhi"),
    }
    baseline = _profit_capture(rows)
    output = []
    for name, fields in groups.items():
        selected = []
        for row in rows:
            values = [_as_float(_feature_value(row, field), 0.0) for field in fields]
            if values and sum(values) / len(values) >= _group_median(rows, fields):
                selected.append(row)
        if len(selected) < 3:
            continue
        output.append(
            {
                "group": name,
                "sample_count": len(selected),
                "profit_lift": _profit_capture(selected) - baseline,
                "false_positive_rate": _false_positive_rate(selected),
            }
        )
    output.sort(key=lambda row: row["profit_lift"], reverse=True)
    return output


def _group_median(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> float:
    values = []
    for row in rows:
        row_values = [_as_float(_feature_value(row, field), 0.0) for field in fields]
        values.append(sum(row_values) / len(row_values))
    values.sort()
    return values[len(values) // 2] if values else 0.0


def _feature_value(row: dict[str, Any], feature: str) -> Any:
    raw = row.get("raw_features_json", {})
    if isinstance(raw, dict) and feature in raw:
        return raw[feature]
    return row.get(feature)


def _profit_capture(rows: list[dict[str, Any]]) -> float:
    positives = sum(max(_as_float(row.get("outcome_return_pct"), 0.0), 0.0) for row in rows)
    losses = abs(sum(min(_as_float(row.get("outcome_return_pct"), 0.0), 0.0) for row in rows))
    return positives / max(positives + losses, 0.0001)


def _false_positive_rate(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return sum(1 for row in rows if _as_float(row.get("outcome_return_pct"), 0.0) <= 0) / len(rows)


def _median(rows: list[dict[str, Any]], feature: str) -> float:
    values = sorted(_as_float(_feature_value(row, feature), 0.0) for row in rows)
    return values[len(values) // 2] if values else 0.0


def _calibration_buckets(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []
    for start in (0.0, 0.2, 0.4, 0.6, 0.8):
        end = start + 0.2
        selected = [
            row for row in rows
            if start <= _as_float(_feature_value(row, field), -1.0) < end
        ]
        if not selected:
            continue
        win_rate = sum(1 for row in selected if _as_float(row.get("outcome_return_pct"), 0.0) > 0) / len(selected)
        avg_prediction = sum(_as_float(_feature_value(row, field), 0.0) for row in selected) / len(selected)
        buckets.append(
            {
                "bucket": f"{start:.1f}-{end:.1f}",
                "sample_count": len(selected),
                "avg_prediction": avg_prediction,
                "realized_win_rate": win_rate,
                "calibration_error": abs(avg_prediction - win_rate),
            }
        )
    return buckets


def _expected_calibration_error(buckets: list[dict[str, Any]]) -> float:
    total = sum(int(bucket["sample_count"]) for bucket in buckets)
    if total <= 0:
        return 0.0
    return sum(
        int(bucket["sample_count"]) / total * float(bucket["calibration_error"])
        for bucket in buckets
    )


def _drift_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(rows) < 20:
        return {"status": "insufficient_data", "rows": len(rows), "max_feature_drift": 0.0}
    midpoint = len(rows) // 2
    prior = rows[:midpoint]
    recent = rows[midpoint:]
    features = _numeric_features(rows)
    drifts = []
    for feature in features:
        prior_values = [_as_float(_feature_value(row, feature), 0.0) for row in prior]
        recent_values = [_as_float(_feature_value(row, feature), 0.0) for row in recent]
        prior_mean = sum(prior_values) / len(prior_values)
        recent_mean = sum(recent_values) / len(recent_values)
        prior_scale = max((sum((value - prior_mean) ** 2 for value in prior_values) / len(prior_values)) ** 0.5, 1e-6)
        drifts.append({"feature": feature, "z_drift": abs(recent_mean - prior_mean) / prior_scale})
    drifts.sort(key=lambda row: row["z_drift"], reverse=True)
    return {"status": "ok", "max_feature_drift": drifts[0]["z_drift"] if drifts else 0.0, "top": drifts[:20]}


def _max_drawdown(values: list[float]) -> float:
    peak = values[0] if values else 1.0
    drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        drawdown = max(drawdown, (peak - value) / max(peak, 0.0001))
    return drawdown


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
