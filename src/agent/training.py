from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent.ledger import Ledger


DEFAULT_FEATURES = (
    "score",
    "confidence",
    "meta_approval_score",
    "meta_learned_edge",
    "meta_expected_return",
    "news_catalyst",
    "news_sentiment",
    "news_source_credibility",
    "momentum_strength",
    "relative_strength",
    "market_regime_strength",
    "regime_confidence",
    "regime_stress_score",
    "committee_consensus_score",
    "execution_sim_quality_score",
    "execution_sim_expected_slippage_bps",
    "execution_sim_fill_probability",
    "risk_expected_slippage_bps",
    "risk_execution_quality_score",
    "allocation_diversification_score",
    "allocation_max_stress_loss_pct",
    "timing_confidence",
    "timing_likely_days",
)


@dataclass(frozen=True)
class TrainingRunResult:
    model_name: str
    model_version: str
    sample_count: int
    train_count: int
    validation_count: int
    test_count: int
    metrics: dict[str, Any]
    parameters: dict[str, Any]
    artifact_path: str


@dataclass(frozen=True)
class _Dataset:
    rows: list[dict[str, Any]]
    feature_names: list[str]
    x: list[list[float]]
    y: list[int]
    returns: list[float]


@dataclass(frozen=True)
class _LogisticModel:
    feature_names: list[str]
    means: list[float]
    scales: list[float]
    weights: list[float]
    bias: float
    threshold: float

    def predict_proba(self, row: list[float]) -> float:
        z = self.bias
        for value, mean, scale, weight in zip(row, self.means, self.scales, self.weights):
            z += ((value - mean) / scale) * weight
        return _sigmoid(z)

    def as_dict(self) -> dict[str, Any]:
        return {
            "algorithm": "pure_python_logistic_regression",
            "feature_names": self.feature_names,
            "means": self.means,
            "scales": self.scales,
            "weights": self.weights,
            "bias": self.bias,
            "threshold": self.threshold,
        }


class WalkForwardModelTrainer:
    def __init__(self, ledger: Ledger, *, artifact_dir: str | Path | None = None) -> None:
        self.ledger = ledger
        base_dir = Path(artifact_dir) if artifact_dir else ledger.sqlite_path.parent / "models"
        self.artifact_dir = base_dir

    def train(
        self,
        *,
        min_samples: int = 40,
        train_fraction: float = 0.60,
        validation_fraction: float = 0.20,
        walk_forward_min_train: int | None = None,
        walk_forward_test_size: int | None = None,
        as_of: str | None = None,
    ) -> TrainingRunResult:
        dataset = self._dataset(as_of=as_of)
        model_name = "supervised_meta_label_filter"
        if len(dataset.rows) < min_samples:
            result = TrainingRunResult(
                model_name=model_name,
                model_version="untrained",
                sample_count=len(dataset.rows),
                train_count=0,
                validation_count=0,
                test_count=0,
                metrics={"status": "insufficient_samples", "min_samples": min_samples},
                parameters={"feature_names": dataset.feature_names, "as_of": as_of},
                artifact_path="",
            )
            self._record(result)
            return result

        train_rows, validation_rows, test_rows = _time_split(
            dataset,
            train_fraction=train_fraction,
            validation_fraction=validation_fraction,
        )
        model = _fit_model(train_rows.x, train_rows.y, train_rows.feature_names)
        threshold = _select_threshold(model, validation_rows)
        model = _LogisticModel(
            feature_names=model.feature_names,
            means=model.means,
            scales=model.scales,
            weights=model.weights,
            bias=model.bias,
            threshold=threshold,
        )
        test_metrics = _evaluate(model, test_rows)
        validation_metrics = _evaluate(model, validation_rows)
        walk_forward_metrics = self._walk_forward(
            dataset,
            min_train=walk_forward_min_train,
            test_size=walk_forward_test_size,
        )
        final_model = _fit_model(dataset.x, dataset.y, dataset.feature_names, threshold=threshold)
        model_version = _model_version(model_name, dataset.rows, final_model.as_dict())
        artifact_path = self._write_artifact(
            model_name=model_name,
            model_version=model_version,
            model=final_model,
            metrics={
                "validation": validation_metrics,
                "holdout": test_metrics,
                "walk_forward": walk_forward_metrics,
            },
            sample_count=len(dataset.rows),
        )
        metrics = {
            "status": "trained",
            "validation": validation_metrics,
            "holdout": test_metrics,
            "walk_forward": walk_forward_metrics,
            "feature_count": len(dataset.feature_names),
        }
        parameters = {
            "model_version": model_version,
            "artifact_path": str(artifact_path),
            "feature_names": dataset.feature_names,
            "algorithm": "logistic_regression",
            "threshold": threshold,
            "train_fraction": train_fraction,
            "validation_fraction": validation_fraction,
            "as_of": as_of,
        }
        result = TrainingRunResult(
            model_name=model_name,
            model_version=model_version,
            sample_count=len(dataset.rows),
            train_count=len(train_rows.rows),
            validation_count=len(validation_rows.rows),
            test_count=len(test_rows.rows),
            metrics=metrics,
            parameters=parameters,
            artifact_path=str(artifact_path),
        )
        self._record(result)
        self.ledger.register_model_version(
            model_name=model_name,
            model_version=model_version,
            artifact_path=str(artifact_path),
            status="candidate",
            trained_until=str(dataset.rows[-1].get("created_at", "")),
            feature_names=dataset.feature_names,
            metrics=metrics,
            parameters=parameters,
        )
        active = self.ledger.active_model_version(model_name)
        if active is None:
            self.ledger.promote_model_version(
                model_name=model_name,
                model_version=model_version,
                reason="first_trained_model",
                raw={"candidate": metrics},
            )
        elif _candidate_beats_active(metrics, active.get("metrics_json", {})):
            self.ledger.promote_model_version(
                model_name=model_name,
                model_version=model_version,
                reason="candidate_outperformed_active_on_holdout_and_walk_forward",
                raw={"candidate": metrics, "active": active.get("metrics_json", {})},
            )
        else:
            self.ledger.record_model_promotion_rejection(
                model_name=model_name,
                model_version=model_version,
                reason="candidate_did_not_clear_promotion_gate",
                raw={"candidate": metrics, "active": active.get("metrics_json", {})},
            )
        return result

    def _dataset(self, *, as_of: str | None = None) -> _Dataset:
        rows = self.ledger.cycle_feature_training_rows(limit=10_000, as_of=as_of)
        if not rows:
            rows = self.ledger.training_examples(limit=10_000)
            if as_of:
                rows = [row for row in rows if str(row.get("created_at", "")) <= as_of]
        rows.sort(key=lambda row: str(row.get("created_at", "")))
        feature_names = _available_features(rows)
        x = [_vector(row, feature_names) for row in rows]
        y = [int(row.get("outcome_label", row.get("label", 0)) or 0) for row in rows]
        returns = [float(row.get("outcome_return_pct", row.get("return_pct", 0.0)) or 0.0) for row in rows]
        return _Dataset(rows=rows, feature_names=feature_names, x=x, y=y, returns=returns)

    def _walk_forward(
        self,
        dataset: _Dataset,
        *,
        min_train: int | None,
        test_size: int | None,
    ) -> dict[str, Any]:
        n = len(dataset.rows)
        min_train = min_train or max(int(n * 0.45), 20)
        test_size = test_size or max(int(n * 0.15), 5)
        if n < min_train + test_size:
            return {"windows": 0, "status": "not_enough_samples_for_walk_forward"}

        windows: list[dict[str, Any]] = []
        start = min_train
        while start + test_size <= n:
            train = _slice_dataset(dataset, 0, start)
            test = _slice_dataset(dataset, start, start + test_size)
            validation_cut = max(int(len(train.rows) * 0.80), 1)
            fit = _slice_dataset(train, 0, validation_cut)
            validation = _slice_dataset(train, validation_cut, len(train.rows))
            model = _fit_model(fit.x, fit.y, fit.feature_names)
            threshold = _select_threshold(model, validation if validation.rows else fit)
            model = _fit_model(train.x, train.y, train.feature_names, threshold=threshold)
            metrics = _evaluate(model, test)
            windows.append(
                {
                    "train_count": len(train.rows),
                    "test_count": len(test.rows),
                    "threshold": threshold,
                    "metrics": metrics,
                }
            )
            start += test_size

        return {
            "windows": len(windows),
            "average_accuracy": _avg_window_metric(windows, "accuracy"),
            "average_precision": _avg_window_metric(windows, "precision"),
            "average_recall": _avg_window_metric(windows, "recall"),
            "average_profit_capture": _avg_window_metric(windows, "profit_capture"),
            "details": windows,
        }

    def _write_artifact(
        self,
        *,
        model_name: str,
        model_version: str,
        model: _LogisticModel,
        metrics: dict[str, Any],
        sample_count: int,
    ) -> Path:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = self.artifact_dir / f"{model_version}.json"
        payload = {
            "model_name": model_name,
            "model_version": model_version,
            "created_at": datetime.now(tz=UTC).isoformat(),
            "sample_count": sample_count,
            "model": model.as_dict(),
            "metrics": metrics,
        }
        artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return artifact_path

    def _record(self, result: TrainingRunResult) -> None:
        self.ledger.record_model_training_run(
            model_name=result.model_name,
            sample_count=result.sample_count,
            train_window=str(result.train_count),
            test_window=str(result.test_count),
            metrics=result.metrics,
            parameters=result.parameters,
        )


def _available_features(rows: list[dict[str, Any]]) -> list[str]:
    available: set[str] = set()
    for row in rows:
        features = _merged_features(row)
        for name, value in features.items():
            if isinstance(value, bool) or _is_number(value):
                available.add(str(name))
    ordered = [name for name in DEFAULT_FEATURES if name in available]
    ordered.extend(sorted(name for name in available if name not in ordered))
    return ordered or ["score"]


def _candidate_beats_active(candidate: dict[str, Any], active: dict[str, Any]) -> bool:
    candidate_holdout = candidate.get("holdout", {}) if isinstance(candidate.get("holdout"), dict) else {}
    active_holdout = active.get("holdout", {}) if isinstance(active.get("holdout"), dict) else {}
    candidate_walk = candidate.get("walk_forward", {}) if isinstance(candidate.get("walk_forward"), dict) else {}
    active_walk = active.get("walk_forward", {}) if isinstance(active.get("walk_forward"), dict) else {}
    candidate_score = (
        0.40 * _metric(candidate_holdout, "profit_capture")
        + 0.25 * _metric(candidate_holdout, "precision")
        + 0.20 * _metric(candidate_walk, "average_profit_capture")
        + 0.15 * _metric(candidate_holdout, "accuracy")
    )
    active_score = (
        0.40 * _metric(active_holdout, "profit_capture")
        + 0.25 * _metric(active_holdout, "precision")
        + 0.20 * _metric(active_walk, "average_profit_capture")
        + 0.15 * _metric(active_holdout, "accuracy")
    )
    candidate_calibration = _metric(candidate_holdout, "brier_score")
    active_calibration = _metric(active_holdout, "brier_score")
    candidate_drawdown = _metric(candidate_holdout, "max_loss_capture")
    active_drawdown = _metric(active_holdout, "max_loss_capture")
    clears_core = candidate_score >= active_score + 0.01
    clears_calibration = active_calibration <= 0 or candidate_calibration <= active_calibration + 0.03
    clears_drawdown = active_drawdown <= 0 or candidate_drawdown <= active_drawdown + 0.05
    return clears_core and clears_calibration and clears_drawdown


def _metric(metrics: dict[str, Any], name: str) -> float:
    try:
        return float(metrics.get(name, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _merged_features(row: dict[str, Any]) -> dict[str, Any]:
    features: dict[str, Any] = {}
    for key, value in row.items():
        if key in {
            "id",
            "created_at",
            "cycle_id",
            "symbol",
            "benchmark_symbol",
            "action",
            "regime_name",
            "raw_features_json",
            "entry_features_json",
            "exit_features_json",
            "raw_json",
        }:
            continue
        if isinstance(value, bool) or _is_number(value):
            features[key] = value
    entry = row.get("entry_features_json", {})
    exit_features = row.get("exit_features_json", {})
    raw = row.get("raw_json", {})
    raw_features = row.get("raw_features_json", {})
    if isinstance(raw_features, dict):
        features.update(raw_features)
    if isinstance(entry, dict):
        features.update(entry)
    if isinstance(raw, dict):
        for container_name in ("entry_context", "exit_risk_details"):
            container = raw.get(container_name, {})
            if isinstance(container, dict):
                nested = container.get("features_json", container.get("features", {}))
                if isinstance(nested, dict):
                    features.update(nested)
        execution = raw.get("execution", {})
        if isinstance(execution, dict):
            for key, value in execution.items():
                features[f"execution_{key}"] = value
    if isinstance(exit_features, dict):
        for key, value in exit_features.items():
            features[f"exit_{key}"] = value
    features.setdefault("score", features.get("decision_score", 0.0))
    features.setdefault("confidence", features.get("decision_confidence", 0.0))
    return features


def _vector(row: dict[str, Any], feature_names: list[str]) -> list[float]:
    features = _merged_features(row)
    return [_num(features.get(name), 0.0) for name in feature_names]


def _time_split(dataset: _Dataset, *, train_fraction: float, validation_fraction: float) -> tuple[_Dataset, _Dataset, _Dataset]:
    n = len(dataset.rows)
    train_end = max(int(n * train_fraction), 1)
    validation_end = max(int(n * (train_fraction + validation_fraction)), train_end + 1)
    validation_end = min(validation_end, n - 1)
    return (
        _slice_dataset(dataset, 0, train_end),
        _slice_dataset(dataset, train_end, validation_end),
        _slice_dataset(dataset, validation_end, n),
    )


def _slice_dataset(dataset: _Dataset, start: int, end: int) -> _Dataset:
    return _Dataset(
        rows=dataset.rows[start:end],
        feature_names=dataset.feature_names,
        x=dataset.x[start:end],
        y=dataset.y[start:end],
        returns=dataset.returns[start:end],
    )


def _fit_model(
    x: list[list[float]],
    y: list[int],
    feature_names: list[str],
    *,
    threshold: float = 0.5,
    learning_rate: float = 0.08,
    epochs: int = 600,
    l2: float = 0.01,
) -> _LogisticModel:
    if not x:
        zeros = [0.0 for _ in feature_names]
        ones = [1.0 for _ in feature_names]
        return _LogisticModel(feature_names, zeros, ones, zeros, 0.0, threshold)
    means, scales = _scaler(x)
    xs = [[(value - mean) / scale for value, mean, scale in zip(row, means, scales)] for row in x]
    weights = [0.0 for _ in feature_names]
    positive_rate = sum(y) / len(y) if y else 0.5
    bias = math.log(max(positive_rate, 1e-4) / max(1 - positive_rate, 1e-4))
    for _ in range(epochs):
        grad_w = [0.0 for _ in weights]
        grad_b = 0.0
        for row, label in zip(xs, y):
            prediction = _sigmoid(bias + sum(weight * value for weight, value in zip(weights, row)))
            error = prediction - label
            grad_b += error
            for index, value in enumerate(row):
                grad_w[index] += error * value
        count = max(len(xs), 1)
        bias -= learning_rate * (grad_b / count)
        for index in range(len(weights)):
            penalty = l2 * weights[index]
            weights[index] -= learning_rate * ((grad_w[index] / count) + penalty)
    return _LogisticModel(feature_names, means, scales, weights, bias, threshold)


def _select_threshold(model: _LogisticModel, dataset: _Dataset) -> float:
    if not dataset.rows:
        return 0.5
    best_threshold = 0.5
    best_score = -1.0
    for threshold in (0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70):
        candidate = _LogisticModel(
            model.feature_names,
            model.means,
            model.scales,
            model.weights,
            model.bias,
            threshold,
        )
        metrics = _evaluate(candidate, dataset)
        objective = (
            metrics["precision"] * 0.40
            + metrics["recall"] * 0.20
            + metrics["profit_capture"] * 0.25
            + metrics["accuracy"] * 0.15
        )
        if objective > best_score:
            best_score = objective
            best_threshold = threshold
    return best_threshold


def _evaluate(model: _LogisticModel, dataset: _Dataset) -> dict[str, float]:
    probabilities = [model.predict_proba(row) for row in dataset.x]
    predictions = [1 if probability >= model.threshold else 0 for probability in probabilities]
    return _classification_metrics(dataset.y, predictions, probabilities, dataset.returns)


def _classification_metrics(
    labels: list[int],
    predictions: list[int],
    probabilities: list[float],
    returns: list[float],
) -> dict[str, float]:
    total = len(labels) or 1
    tp = sum(1 for label, pred in zip(labels, predictions) if label == 1 and pred == 1)
    tn = sum(1 for label, pred in zip(labels, predictions) if label == 0 and pred == 0)
    fp = sum(1 for label, pred in zip(labels, predictions) if label == 0 and pred == 1)
    fn = sum(1 for label, pred in zip(labels, predictions) if label == 1 and pred == 0)
    selected_returns = [ret for pred, ret in zip(predictions, returns) if pred == 1]
    all_positive_return = sum(ret for ret in returns if ret > 0)
    captured_positive_return = sum(ret for pred, ret in zip(predictions, returns) if pred == 1 and ret > 0)
    brier = sum((prob - label) ** 2 for prob, label in zip(probabilities, labels)) / len(probabilities) if probabilities else 0.0
    selected_losses = abs(sum(ret for pred, ret in zip(predictions, returns) if pred == 1 and ret < 0))
    all_losses = abs(sum(ret for ret in returns if ret < 0))
    return {
        "accuracy": (tp + tn) / total,
        "precision": tp / max(tp + fp, 1),
        "recall": tp / max(tp + fn, 1),
        "false_positive_rate": fp / max(fp + tn, 1),
        "average_probability": sum(probabilities) / len(probabilities) if probabilities else 0.0,
        "selected_rate": sum(predictions) / total,
        "average_selected_return": sum(selected_returns) / len(selected_returns) if selected_returns else 0.0,
        "profit_capture": captured_positive_return / max(all_positive_return, 1e-9),
        "brier_score": brier,
        "max_loss_capture": selected_losses / max(all_losses, 1e-9),
    }


def _scaler(x: list[list[float]]) -> tuple[list[float], list[float]]:
    width = len(x[0]) if x else 0
    means: list[float] = []
    scales: list[float] = []
    for index in range(width):
        values = [row[index] for row in x]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        means.append(mean)
        scales.append(max(variance ** 0.5, 1e-6))
    return means, scales


def _avg_window_metric(windows: list[dict[str, Any]], name: str) -> float:
    values = [
        float(window.get("metrics", {}).get(name, 0.0))
        for window in windows
        if isinstance(window.get("metrics", {}).get(name), (int, float))
    ]
    return sum(values) / len(values) if values else 0.0


def _model_version(model_name: str, rows: list[dict[str, Any]], model_payload: dict[str, Any]) -> str:
    latest = str(rows[-1].get("created_at", "")) if rows else ""
    digest = hashlib.sha256(json.dumps(model_payload, sort_keys=True).encode("utf-8")).hexdigest()[:10]
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{model_name}_{stamp}_{digest}_{len(rows)}_{hashlib.sha1(latest.encode('utf-8')).hexdigest()[:6]}"


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1 / (1 + z)
    z = math.exp(value)
    return z / (1 + z)


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
