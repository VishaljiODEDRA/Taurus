# Changelog

All notable changes to Taurus will be documented in this file.

The format follows a simple date-based project log while the project is pre-1.0.

## [Unreleased]

### Added

- Governance cockpit upgrades for demo data mode, evidence timeline, decision drill-down, risk control matrix, model cards, incident timeline, governed agent role boundaries, and decision replay flow.
- Redacted audit export pack command that writes `summary.json`, `report.html`, `manifest.json`, `checksums.sha256`, and `README.txt` into a public-safe ZIP archive.
- Synthetic public-safe demo ledger generator for dashboard review without private runtime data.
- Read-only FastAPI/Jinja2 web dashboard MVP with overview, decision, risk, model governance, reliability, reconciliation, and audit views backed by the existing ledger/reporting layer.
- Local dashboard run commands through `python3 -m agent.web` and `python3 -m agent web`, plus README branching workflow guidance for feature, docs, fix, chore, and release branches.
- Feedback-first outreach pack with public target research, founder/AI/risk message drafts, demo outline, funding-aware notes, and private CRM template.
- Public build-log system under `docs/build-logs/` with publishing rules, weekly template, index, and first founder-engineer build log.
- Demo-only trading protocol documenting shadow/demo operation, live-trading blocks, kill-switch usage, safe validation commands, reconciliation/report workflow, and weekly redacted evidence summaries.
- Architecture pack with system architecture, risk governance, model governance, and broker/execution documentation, including Mermaid diagrams for decision flow, data flow, ledger/audit trail, risk gates, model lifecycle, and demo/live safety gates.
- Product vision document positioning Taurus as a global fintech AI trading governance platform with mission, target users, safety principles, compliance boundaries, roadmap, and innovation thesis.

### Fixed

- Corrected active kill-switch dashboard styling so halted runtime state appears as a critical safety condition, not a healthy status.
- Made audit export manifests account for every ZIP member and document the checksum integrity model.
- Ignored generated `exports/` packs by default and tightened replay/model evidence rendering to avoid raw payload-style dashboard output.

## [0.1.0] - 2026-06-05

### Added

- Initial public-ready local agent scaffold.
- Risk-first Taurus README and planning documentation.
- Product requirements document.
- Technical requirements document.
- Production app flow.
- UI/UX design brief.
- Production backend schema plan.
- Implementation plan.
- eToro client, market data adapters, strategy engine, risk layer, broker execution, ledger, reconciliation, monitoring, backtesting, walk-forward validation, model governance, and reliability reports.
- Unit test suite for core research and governance behavior.
- Public repository files: license, security policy, contributing guide, changelog.

### Safety

- Default execution mode remains `shadow`.
- Live mode remains guarded by both `AUTOTRADER_ALLOW_LIVE=true` and `--allow-live`.
- Runtime secrets, private config, state, ledgers, logs, caches, and generated files are excluded from Git.
