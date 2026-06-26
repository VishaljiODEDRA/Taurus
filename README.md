# Taurus: Risk-First AI Trading Governance Platform

Taurus is a risk-first AI trading governance platform in development. The current repository contains the local autonomous trading agent core: a Python CLI system for shadow/demo trading research, deterministic risk controls, eToro integration, SQLite ledgering, audit logs, backtesting, walk-forward validation, model governance, reconciliation, reliability reports, and live-trading safety gates.

The product roadmap evolves this core into a production-ready SaaS platform for paper trading, risk governance, model governance, audit exports, API/SDK access, public beta onboarding, compliance-aware reporting, incident response, and enterprise-style administration.

Taurus is not a profit bot, investment adviser, financial promotion, copy-trading service, managed account, or guarantee of trading performance. It is built as paper/research/governance-first infrastructure.

## Product Thesis

AI can research, score, rank, and explain. Deterministic governance must decide whether anything is allowed to execute.

Taurus is designed around:

- paper trading before live execution,
- deterministic risk gates before orders,
- audit logs before confidence,
- model governance before model promotion,
- reconciliation before trust,
- compliance-aware product scope before commercial launch.

## Public Repository Metadata

Recommended GitHub repository name:

- `risk-first-ai-trading-agent`

Recommended description:

> Taurus: risk-first autonomous trading platform with auditable decisions, broker reconciliation, model governance, and demo/live readiness controls.

Recommended topics:

- `fintech`
- `algorithmic-trading`
- `risk-management`
- `ai-agents`
- `model-governance`
- `python`
- `trading-systems`

This repository is intended to be externally verifiable engineering evidence for a research/demo governance platform. Public materials should describe Taurus as educational, paper/demo trading, model-risk, auditability, and developer infrastructure. They should not claim investment performance or imply that users should buy or sell any asset.

## Current Status

This repo is currently the local agent and governance engine. It is not yet the hosted SaaS app described in the roadmap documents.

Built today:

- eToro REST client using `x-api-key`, `x-user-key`, and `x-request-id`.
- Market-data adapter for eToro instruments, rates, portfolio, P&L, and orders.
- TradingView daily candles as the primary chart source, with Yahoo daily history fallback.
- Strategy engine for liquid US stock/ETF momentum, relative strength, catalysts, peer-laggard context, and news scoring.
- Chart analysis across prior day, 5-day cycle, and monthly windows.
- Transparent alpha scoring that blends chart structure, relative strength, news catalysts, spread/risk context, and learned outcome signals.
- Hard risk layer: position caps, daily loss halt, drawdown halt, spread/staleness checks, leverage cap, no averaging down, kill switch.
- Execution layer with `shadow`, `demo`, and guarded `live` modes.
- SQLite ledger and JSONL audit log for explainability.
- Backtesting, walk-forward validation, calibration, model training, model promotion/rejection, reliability reports, and realistic replay.
- Broker reconciliation for position drift, missing orders, duplicate exposure, stale protection, and P&L mismatches.
- Monitoring alerts that can trigger the kill switch for critical conditions.

Planned through the Taurus roadmap:

- Read-only web dashboard.
- Authentication, sessions, users, workspaces, and RBAC.
- Hosted staging and public beta.
- Workspace-scoped paper broker simulator.
- Backtest and walk-forward web UI.
- Model registry and drift detection UI.
- API v1 and Python SDK.
- Audit export packs with redaction and checksums.
- Billing interest, subscription states, entitlements, and future paid beta support.
- Feature flags, A/B testing, product instrumentation, conversion, retention, and churn dashboards.
- Incident management, public status page, support operations, escalation workflows.
- GDPR/CCPA controls, data retention policies, cookie consent, and privacy self-service.
- Enterprise admin, commercial traction tracking, compliance packs, and disaster recovery runbooks.

## Safety And Scope

Current default behavior is `shadow` mode. It records decisions and suggested orders to the local ledger without submitting anything to eToro.

Trading modes:

- `shadow`: no order submission. The agent logs decisions and planned orders only.
- `demo`: uses eToro demo trading endpoints.
- `live`: uses eToro real trading endpoints only when both gates are enabled:
  - `AUTOTRADER_ALLOW_LIVE=true`
  - CLI flag `--allow-live`

The agent also refuses live trading when the kill switch exists.

Public beta and hosted product plans are paper/research/governance-first. Live execution for users, broker credential storage, personalised investment recommendations, copy trading, managed accounts, paid trading signals, crypto promotion, and return claims require legal review and are out of scope for the beta plan.

For the June 2026 operating workflow, see [docs/DEMO_TRADING_PROTOCOL.md](docs/DEMO_TRADING_PROTOCOL.md). It defines the shadow/demo-only process, live-trading blocks, kill-switch checks, safe validation commands, and redacted weekly evidence summaries.

## Regulatory And Educational Caution

Taurus is published for technical research, educational development, paper/demo trading workflows, and risk-governance exploration. It is not regulated investment advice, a financial promotion, a trading signal service, copy trading, a managed account, or an offer to manage money.

Historical, simulated, backtested, demo, or paper-trading results do not predict future results. Any live use is experimental capital at risk and requires independent legal, regulatory, operational, and security review.

## Quick Start

```bash
cp .env.example .env
cp config/strategy.example.toml config/strategy.toml
python3 -m pip install -e .
python3 -m unittest discover -s tests
python3 -m agent scan --config config/strategy.toml
```

Without installing the package first, use the local runner:

```bash
python3 run_agent.py scan --config config/strategy.toml
```

Run a single shadow cycle:

```bash
python3 -m agent run-once --config config/strategy.toml
```

Or without install:

```bash
python3 run_agent.py run-once --config config/strategy.toml
```

Toggle the emergency kill switch:

```bash
python3 -m agent kill-switch on --config config/strategy.toml
python3 -m agent kill-switch status --config config/strategy.toml
python3 -m agent kill-switch off --config config/strategy.toml
```

## Readiness Workflow

Taurus includes a readiness workflow for validating the system before any live consideration:

```bash
python3 -m agent backtest --config config/strategy.toml
python3 -m agent walk-forward --config config/strategy.toml
python3 -m agent calibrate --config config/strategy.toml --source backtest
python3 -m agent calibrate --config config/strategy.toml --source outcomes
python3 -m agent train-model --config config/strategy.toml --min-samples 40
python3 -m agent reliability-report --config config/strategy.toml --type all
python3 -m agent realistic-replay --config config/strategy.toml --as-of 2026-05-15T10:30:00Z
python3 -m agent cycle-history --config config/strategy.toml
python3 -m agent reconcile --config config/strategy.toml
python3 -m agent monitor --config config/strategy.toml
```

Backtests and walk-forward validation use cached candle data from `state/market_cache.json`. Build that cache by running `scan` or repeated `run-once` cycles.

## Architecture Overview

Current local architecture:

```text
config/strategy.toml
        |
        v
TradingAgent
        |
        +-- market data provider
        +-- chart/news/regime/ML scoring
        +-- deterministic risk gates
        +-- allocation and execution simulation
        +-- broker adapter: shadow/demo/live
        +-- SQLite ledger
        +-- JSONL audit log
        +-- reconciliation and monitoring
```

Target Taurus SaaS architecture:

```text
Public app + authenticated dashboard
        |
        +-- auth, workspaces, RBAC
        +-- paper broker and validation UI
        +-- API v1 and SDK
        +-- model registry and drift
        +-- audit exports and compliance packs
        +-- billing interest and entitlements
        +-- incidents, status, support, privacy controls
        |
        v
Workspace-scoped governance ledger
```

## Data And Audit Model

The existing ledger stores:

- decisions,
- risk checks,
- orders,
- cycle health,
- market snapshots,
- candle history,
- news items,
- portfolio snapshots,
- regime history,
- feature snapshots,
- training examples,
- model training runs,
- model registry records,
- promotion/rejection events,
- reliability reports,
- reconciliation results,
- execution simulations,
- source credibility records.

The production backend schema extends this with:

- users and sessions,
- workspaces and workspace members,
- API keys,
- paper accounts and paper orders,
- audit exports and generated artifacts,
- subscriptions and entitlement snapshots,
- feature flags and experiments,
- product events and retention snapshots,
- incidents and status updates,
- support tickets,
- consent, cookie, export, deletion, and retention records,
- cloud cost and quota tracking.

See [BACKEND_SCHEMA.md](BACKEND_SCHEMA.md) for the production schema plan.

## Product And Engineering Documents

The Taurus production plan is captured in these documents:

- [PRD.md](PRD.md): product requirements, roadmap, launch gates, metrics, commercial scope, compliance boundaries.
- [TRD.md](TRD.md): technical architecture, services, tables, APIs, jobs, security, CI/CD, observability, and platform requirements.
- [APP_FLOW.md](APP_FLOW.md): end-to-end public, authenticated, admin, billing, support, operational, privacy, and governance flows.
- [DESIGN_UI_UX_BRIEF.md](DESIGN_UI_UX_BRIEF.md): premium fintech UI/UX direction, information architecture, key screens, accessibility, and design system.
- [BACKEND_SCHEMA.md](BACKEND_SCHEMA.md): production backend schema, migration strategy, indexes, retention, billing, incidents, analytics, GDPR/CCPA, and scalability requirements.
- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md): phased build plan, dependencies, production controls, launch gates, and immediate engineering sequence.
- [SECURITY.md](SECURITY.md): vulnerability reporting, sensitive-data handling, supported scope, and safety boundaries.
- [CONTRIBUTING.md](CONTRIBUTING.md): contribution setup, testing, safety scope, and public-language guidance.
- [CHANGELOG.md](CHANGELOG.md): dated project changes and release notes.
- [docs/PRODUCT_VISION.md](docs/PRODUCT_VISION.md): founder/product vision, mission, safety principles, roadmap, and innovation thesis.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): current architecture, decision cycle, data flow, ledger/audit trail, and built-now versus planned-next boundaries.
- [docs/RISK_GOVERNANCE.md](docs/RISK_GOVERNANCE.md): deterministic risk gates, kill switch, pre-trade policy, portfolio risk, and compliance boundaries.
- [docs/MODEL_GOVERNANCE.md](docs/MODEL_GOVERNANCE.md): feature evidence, training lifecycle, promotion gates, reliability reports, drift, and replay.
- [docs/BROKER_AND_EXECUTION.md](docs/BROKER_AND_EXECUTION.md): shadow/demo/live modes, broker selection, eToro execution flow, demo/live safety gates, and reconciliation.
- [docs/DEMO_TRADING_PROTOCOL.md](docs/DEMO_TRADING_PROTOCOL.md): demo-only operating workflow, validation commands, live-block checks, and weekly redacted summaries.
- [docs/build-logs/README.md](docs/build-logs/README.md): public build-log system, publishing rules, weekly template, and index.
- [docs/OUTREACH.md](docs/OUTREACH.md): feedback-first outreach pack, demo outline, public target research, message drafts, and private CRM template.

## Roadmap Summary

June 2026:

- public-safe repository hygiene,
- product vision,
- architecture and governance docs,
- demo-only operating protocol,
- weekly build logs.
- feedback-first outreach pack.

July 2026:

- read-only web dashboard MVP,
- Docker and CI,
- first technical article,
- public demo pack,
- legal-safe product scope.

August 2026:

- authentication,
- workspaces,
- hosted staging,
- paper broker simulator,
- early-user collection.

September 2026:

- backtest and walk-forward UI,
- model registry UI,
- public docs site,
- private beta support.

October 2026:

- API v1,
- Python SDK,
- broker adapter abstraction,
- audit exports.

November 2026:

- billing interest,
- subscription state design,
- tenant isolation hardening,
- security controls,
- compliance review workflow,
- growth dashboard.

December 2026:

- public beta,
- status/incidents page,
- changelog,
- testimonials,
- whitepaper.

January to May 2027:

- drift detection,
- incident management,
- enterprise admin,
- commercial traction tracking,
- GDPR/security hardening,
- compliance pack,
- product freeze,
- metrics dossier,
- final demo and evidence pack.

## Secret And Runtime File Safety

Do not commit:

- `.env`
- `.venv`
- `config/strategy.toml`
- `state/*.sqlite3`
- `state/market_cache.json`
- `logs/*.jsonl`
- broker credentials
- API keys
- personal trading records
- generated caches

Commit only safe source code, tests, examples, documentation, and configuration templates such as `config/strategy.example.toml`.

## Large Universe And Data Sources

`config/strategy.toml` can be configured with a broad US large-cap universe plus `SPY` as benchmark. To respect API limits, the agent scans `max_symbols_per_cycle` symbols per run and advances `state/universe_cursor.txt` after each `run-once`.

Symbols that eToro search/rates cannot resolve are skipped for that cycle. Instrument lookups and candles are cached in `state/market_cache.json`. Daily chart history is loaded from TradingView first, then Yahoo if TradingView is unavailable, while eToro remains the source for tradability, spreads, portfolio state, and execution.

## News Context

News scoring reads RSS feeds from config, local catalyst items from `data/news.json`, and optionally scraped article text when BeautifulSoup is available. Entity mappings from `data/news_entities.json` let company names, products, subsidiaries, suppliers, competitors, and executives map back to tickers.

OpenAI context is optional and disabled by default through `news.use_openai_context = false`.

## Testing

Run the test suite:

```bash
python3 -m unittest discover -s tests
```

The current test suite covers core research/governance behavior, including data, chart analysis, news, ML scoring, risk, order policy, reconciliation, reliability, eToro client behavior, portfolio logic, and shadow engine execution.

Planned production test gates include auth, tenant isolation, RBAC, API keys, billing idempotency, feature flags, paper broker, audit export redaction, incident flows, GDPR/CCPA flows, schema migrations, CI/CD, and rollback smoke tests.

## Important Disclaimer

No code can guarantee trading profit. Taurus is built to make autonomous trading research safer, more auditable, and more governable. Historical, backtested, paper, demo, or simulated results do not predict future results and are not investment advice.

Any live deployment is experimental capital at risk and requires appropriate legal, regulatory, operational, and security review.

## External References

- eToro Developer Portal: https://api-portal.etoro.com/
- eToro API authentication: https://api-portal.etoro.com/getting-started/authentication
- eToro API rate limits: https://api-portal.etoro.com/getting-started/rate-limits
- eToro market order guide: https://api-portal.etoro.com/guides/market-orders
- eToro Agent Portfolios update: https://www.etoro.com/news-and-analysis/etoro-updates/agent-portfolios-let-your-ai-agent-trade-for-you/
