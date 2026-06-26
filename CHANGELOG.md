# Changelog

All notable changes to Taurus will be documented in this file.

The format follows a simple date-based project log while the project is pre-1.0.

## [Unreleased]

### Added

- Public build-log system under `docs/build-logs/` with publishing rules, weekly template, index, and first founder-engineer build log.
- Demo-only trading protocol documenting shadow/demo operation, live-trading blocks, kill-switch usage, safe validation commands, reconciliation/report workflow, and weekly redacted evidence summaries.
- Architecture pack with system architecture, risk governance, model governance, and broker/execution documentation, including Mermaid diagrams for decision flow, data flow, ledger/audit trail, risk gates, model lifecycle, and demo/live safety gates.
- Product vision document positioning Taurus as a global fintech AI trading governance platform with mission, target users, safety principles, compliance boundaries, roadmap, and innovation thesis.

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
