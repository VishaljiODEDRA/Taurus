# Changelog

All notable changes to Taurus will be documented in this file.

The format follows a simple date-based project log while the project is pre-1.0.

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
