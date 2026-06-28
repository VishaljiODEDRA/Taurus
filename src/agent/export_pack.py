from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent.config import AppConfig
from agent.ledger import Ledger
from agent.redaction import basename_only, redact_value
from agent.web.service import SAFETY_NOTICE


EXPORT_REDACTION_POLICY_VERSION = "taurus-redaction-v1"


def build_audit_export_pack(config: AppConfig, ledger: Ledger, output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload_files = _export_files(config, ledger)
    checksums = _checksums_text(payload_files)
    manifest = _manifest_for(payload_files, checksums)
    files = {
        **payload_files,
        "manifest.json": json.dumps(manifest, indent=2, sort_keys=True),
        "checksums.sha256": checksums,
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output


def build_export_summary(config: AppConfig, ledger: Ledger) -> dict[str, Any]:
    latest_cycle = _first(ledger.recent_cycle_health(limit=1))
    latest_reconciliation = _first(ledger.latest_reconciliations(limit=1))
    latest_reliability = _first(ledger.latest_reliability_reports(limit=1))
    latest_model = _first(ledger.latest_model_versions(limit=1))
    latest_risk = _first(ledger.latest_portfolio_risk_reports(limit=1))
    summary = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "mode": config.execution.normalized_mode(),
        "environment": config.execution.normalized_environment(),
        "ledger": basename_only(config.storage.sqlite_path),
        "safety_statement": SAFETY_NOTICE,
        "redaction_policy": EXPORT_REDACTION_POLICY_VERSION,
        "counts": {
            "decisions": ledger.table_count("decisions"),
            "orders": ledger.table_count("orders"),
            "risk_checks": ledger.table_count("risk_checks"),
            "cycle_health": ledger.table_count("cycle_health"),
            "model_versions": ledger.table_count("model_registry"),
            "reliability_reports": ledger.table_count("reliability_reports"),
            "reconciliations": ledger.table_count("reconciliations"),
        },
        "latest_statuses": {
            "cycle": _cycle_status(latest_cycle),
            "reconciliation": latest_reconciliation.get("status") if latest_reconciliation else "not_recorded",
            "reliability": latest_reliability.get("status") if latest_reliability else "not_recorded",
            "model": latest_model.get("status") if latest_model else "not_recorded",
            "risk": "recorded" if latest_risk else "not_recorded",
        },
    }
    return redact_value(summary)


def _export_files(config: AppConfig, ledger: Ledger) -> dict[str, str]:
    summary = build_export_summary(config, ledger)
    summary_json = json.dumps(summary, indent=2, sort_keys=True)
    report_html = _report_html(summary)
    readme = (
        "Taurus Redacted Audit Export Pack\n\n"
        "This pack summarizes paper/demo governance evidence from a local Taurus ledger.\n"
        "It is not investment advice, a trading signal service, a financial promotion, "
        "or evidence of future trading performance.\n\n"
        f"Redaction policy: {EXPORT_REDACTION_POLICY_VERSION}\n"
        "Raw broker payloads, credentials, account identifiers, full private paths, and raw audit logs are excluded.\n"
    )
    return {
        "summary.json": summary_json,
        "report.html": report_html,
        "README.txt": readme,
    }


def _report_html(summary: dict[str, Any]) -> str:
    counts = "".join(
        f"<tr><th>{key}</th><td>{value}</td></tr>"
        for key, value in summary.get("counts", {}).items()
    )
    statuses = "".join(
        f"<tr><th>{key}</th><td>{value}</td></tr>"
        for key, value in summary.get("latest_statuses", {}).items()
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Taurus Audit Export</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:32px;color:#18212f}"
        "table{border-collapse:collapse;width:100%;max-width:760px;margin-bottom:24px}"
        "th,td{border:1px solid #d8dee7;padding:8px;text-align:left}th{background:#f4f6f8}</style>"
        "</head><body>"
        "<h1>Taurus Redacted Audit Export</h1>"
        f"<p>{summary.get('safety_statement')}</p>"
        "<h2>Runtime</h2>"
        f"<p>Mode: {summary.get('mode')} | Environment: {summary.get('environment')} | Ledger: {summary.get('ledger')}</p>"
        "<h2>Counts</h2><table>"
        f"{counts}</table><h2>Latest Statuses</h2><table>{statuses}</table>"
        "<p>Raw private runtime data is not included in this pack.</p>"
        "</body></html>"
    )


def _manifest_for(payload_files: dict[str, str], checksums_text: str) -> dict[str, Any]:
    checksum_bytes = checksums_text.encode("utf-8")
    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "redaction_policy": EXPORT_REDACTION_POLICY_VERSION,
        "integrity_model": (
            "checksums.sha256 contains payload file hashes. manifest.json and checksums.sha256 "
            "are listed as integrity metadata to avoid self-referential checksum ambiguity."
        ),
        "files": [
            {
                "name": name,
                "bytes": len(content.encode("utf-8")),
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "role": "payload",
            }
            for name, content in sorted(payload_files.items())
        ] + [
            {
                "name": "manifest.json",
                "bytes": None,
                "sha256": None,
                "role": "integrity_metadata",
            },
            {
                "name": "checksums.sha256",
                "bytes": len(checksum_bytes),
                "sha256": hashlib.sha256(checksum_bytes).hexdigest(),
                "role": "integrity_metadata",
            },
        ],
    }


def _checksums_text(files: dict[str, str]) -> str:
    lines = []
    for name, content in sorted(files.items()):
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        lines.append(f"{digest}  {name}")
    return "\n".join(lines) + "\n"


def _first(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return rows[0] if rows else {}


def _cycle_status(row: dict[str, Any]) -> str:
    if not row:
        return "not_recorded"
    return "halted" if row.get("halted") else "operational"
