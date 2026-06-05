from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from agent.config import MonitoringSettings, RiskSettings
from agent.ledger import Ledger
from agent.risk import set_kill_switch
from models import AgentCycleResult


@dataclass(frozen=True)
class Alert:
    level: str
    message: str
    details: dict


class HealthMonitor:
    def __init__(self, settings: MonitoringSettings, risk: RiskSettings, ledger: Ledger) -> None:
        self.settings = settings
        self.risk = risk
        self.ledger = ledger

    def record_cycle(self, result: AgentCycleResult) -> list[Alert]:
        rejected_orders = sum(1 for order in result.orders if not order.accepted)
        self.ledger.record_cycle_health(
            halted=result.halted,
            halt_reason=result.halt_reason,
            decision_count=len(result.decisions),
            risk_check_count=len(result.risk_decisions),
            order_count=len(result.orders),
            rejected_order_count=rejected_orders,
        )
        alerts = self.evaluate()
        for alert in alerts:
            self._write_alert(alert)
            if self.settings.auto_kill_switch_on_breach and alert.level == "critical":
                set_kill_switch(self.risk.kill_switch_path, True, alert.message)
        return alerts

    def evaluate(self) -> list[Alert]:
        if not self.settings.enabled:
            return []
        rows = self.ledger.recent_cycle_health(limit=20)
        if not rows:
            return []

        alerts: list[Alert] = []
        halted_count = sum(1 for row in rows[: self.settings.max_halted_cycles] if row["halted"])
        if halted_count >= self.settings.max_halted_cycles:
            alerts.append(
                Alert(
                    level="critical",
                    message="consecutive halted cycles breached",
                    details={"halted_count": halted_count},
                )
            )

        order_count = sum(int(row["order_count"]) for row in rows)
        rejected = sum(int(row["rejected_order_count"]) for row in rows)
        reject_rate = rejected / order_count if order_count else 0.0
        if order_count and reject_rate > self.settings.max_order_reject_rate:
            alerts.append(
                Alert(
                    level="critical",
                    message="order reject rate breached",
                    details={"reject_rate": reject_rate, "orders": order_count, "rejected": rejected},
                )
            )

        consecutive_rejects = 0
        for row in rows:
            if int(row["order_count"]) > 0 and int(row["rejected_order_count"]) >= int(row["order_count"]):
                consecutive_rejects += 1
            else:
                break
        if consecutive_rejects >= self.settings.max_consecutive_rejects:
            alerts.append(
                Alert(
                    level="critical",
                    message="consecutive rejected order cycles breached",
                    details={"consecutive_rejects": consecutive_rejects},
                )
            )
        return alerts

    def _write_alert(self, alert: Alert) -> None:
        path = Path(self.settings.alert_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "created_at": datetime.now(tz=UTC).isoformat(),
            "level": alert.level,
            "message": alert.message,
            "details": alert.details,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

