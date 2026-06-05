from __future__ import annotations

from agent.ledger import Ledger


class ReportingDashboard:
    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger

    def summary(self, *, limit: int = 10) -> dict[str, object]:
        risk_reports = self.ledger.latest_portfolio_risk_reports(limit=1)
        training_runs = self.ledger.latest_model_training_runs(limit=1)
        model_versions = self.ledger.latest_model_versions(limit=3)
        promotion_events = self.ledger.latest_model_promotion_events(limit=limit)
        executions = self.ledger.latest_execution_simulations(limit=limit)
        committee = self.ledger.latest_committee_votes(limit=limit)
        news_sources = self.ledger.latest_news_source_stats(limit=limit)
        news_credibility = self.ledger.latest_news_source_credibility(limit=limit)
        features = self.ledger.latest_feature_snapshots(limit=limit)
        reliability = self.ledger.latest_reliability_reports(limit=limit)
        return {
            "latest_portfolio_risk": risk_reports[0] if risk_reports else {},
            "latest_training": training_runs[0] if training_runs else {},
            "model_versions": model_versions,
            "model_promotion_events": promotion_events,
            "recent_execution_simulations": executions,
            "recent_committee_votes": committee,
            "recent_news_sources": news_sources,
            "learned_news_credibility": news_credibility,
            "recent_feature_snapshots": features,
            "recent_reliability_reports": reliability,
        }
