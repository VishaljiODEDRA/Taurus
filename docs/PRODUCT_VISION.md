# Taurus Product Vision

## Mission

Taurus exists to make AI-assisted trading systems governable.

The mission is to build global fintech infrastructure that lets advanced traders, builders, researchers, and AI-agent teams test automated trading workflows with deterministic risk controls, complete auditability, model governance, broker reconciliation, and operational safety before any live or regulated use is considered.

Taurus is not a profit-guarantee bot. It is not a signal service. It is not a managed account product. The long-term company thesis is that AI will increasingly participate in financial research and execution workflows, but serious financial systems need proof, controls, replay, and accountability more than they need another black-box prediction engine.

## Product Category

Taurus is an AI trading governance platform.

The product category sits at the intersection of:

- fintech infrastructure,
- autonomous agent governance,
- model-risk management,
- paper/demo trading validation,
- audit and compliance tooling,
- broker reconciliation,
- research operations for systematic trading.

The current repository is the local governance engine for that platform. It already includes eToro integration, shadow/demo/live execution modes, deterministic risk controls, a SQLite ledger, JSONL audit logs, backtesting, walk-forward validation, reconciliation, model training, reliability reports, news scoring, and an emergency kill switch.

The 2026-2027 product roadmap evolves this local engine into a hosted SaaS platform for paper trading, governance dashboards, model registry, audit exports, API/SDK access, private beta, public beta, enterprise-style administration, and compliance evidence.

## Target Users

Taurus is designed for users who already understand that automated trading is operationally risky, technically complex, and legally sensitive.

Primary users:

- Advanced traders who want paper/demo validation, risk visibility, and replayable evidence before live experiments.
- Fintech builders creating autonomous finance workflows and needing governance infrastructure instead of ad hoc scripts.
- Small funds and research teams that need backtesting, walk-forward validation, model promotion controls, and audit trails.
- AI-agent developers who need a deterministic approval layer between model output and any broker-facing action.

Secondary users:

- Risk and compliance reviewers evaluating whether an automated workflow is explainable and controlled.
- Technical investors and startup advisers assessing whether the system is infrastructure rather than personal trading activity.
- Open-source contributors who want a clear architecture for safe AI trading research.
- Beta users who need a paper/research platform, not investment recommendations.

## Painful Problem

AI trading systems are becoming easier to prototype and harder to trust.

A model can generate a market thesis, rank assets, summarize news, score momentum, or propose an order. That does not mean the system is safe, auditable, compliant, or production-ready. Most early AI trading projects fail to answer basic governance questions:

- Why did the system make this decision?
- Which data, features, news items, and model version influenced it?
- Which deterministic risk checks approved or vetoed it?
- Can the decision be replayed later with the same evidence?
- Did the broker account actually match the expected positions and orders?
- Was slippage, spread, staleness, or duplicate exposure controlled?
- Was the model promoted with evidence or simply trusted after a backtest?
- Can a reviewer export a reliable audit trail without private data leakage?
- Can the system halt itself when risk, reconciliation, or reliability fails?

The market does not need another product promising that AI can beat markets. It needs infrastructure that makes AI trading workflows testable, bounded, explainable, and operationally accountable.

## Product Thesis

AI can research, score, rank, and explain. Deterministic governance must decide what is allowed.

Taurus is built on a risk-first operating model:

1. AI-generated signals are treated as proposals, not authority.
2. Every decision is passed through deterministic risk gates.
3. Every order attempt is recorded in a ledger and audit log.
4. Every model version needs training, calibration, promotion, rejection, rollback, and reliability evidence.
5. Every strategy needs backtesting, walk-forward validation, realistic replay, and reconciliation before trust.
6. Every public product surface must be paper/research/governance-first until legal, security, and regulatory reviews justify more.

The result is a deterministic risk-first agent framework: a platform where autonomous systems can be evaluated under clear controls, with evidence that users, operators, and reviewers can inspect.

## Core Modules

### 1. Agent Decision Engine

The current engine runs a decision cycle that combines market data, chart context, relative strength, news scoring, regime context, learned outcome signals, and portfolio state. It records transparent reasoning rather than hiding the decision behind a single opaque score.

### 2. Risk Engine

The risk layer enforces hard controls before any execution path is allowed. Existing controls include position caps, daily loss halt, drawdown halt, spread and staleness checks, leverage caps, no averaging down, and a kill switch.

The product principle is that risk gates are not UI warnings. They are deterministic approvals or vetoes.

### 3. Broker And Execution Modes

Taurus supports shadow, demo, and guarded live modes in the local engine:

- `shadow`: records decisions and intended orders without broker submission.
- `demo`: uses broker demo capabilities where available.
- `live`: guarded by both environment and CLI flags and blocked by the kill switch.

The hosted beta roadmap remains paper/research-first and does not expose public live execution.

### 4. Ledger And Audit Logs

The local SQLite ledger and JSONL audit log capture decisions, risk checks, orders, market snapshots, cycle health, feature snapshots, model events, reliability reports, reconciliation findings, and execution simulations.

The hosted product roadmap expands this into workspace-scoped governance records, audit exports, redaction, checksums, export manifests, and compliance packs.

### 5. Backtesting And Walk-Forward Validation

Taurus includes backtesting and walk-forward validation because static backtests are easy to overstate. The product direction is to show train/test windows, period metrics, assumptions, failure cases, and replay evidence so users can understand the limits of a strategy.

### 6. Model Governance

The model layer supports calibration, training, reliability reporting, model registry records, and promotion or rejection events. The roadmap expands this into a hosted model registry with candidate, active, rejected, archived, promote, rollback, lineage, drift, and reliability views.

### 7. Reconciliation And Reliability

Broker reconciliation checks for position drift, missing orders, duplicate exposure, stale protection, and P&L mismatches. Reliability reports summarize operational quality, model behavior, and areas requiring review.

This is central to the product thesis: a trading agent is not trustworthy because it can generate decisions; it becomes trustworthy only when its expected state can be reconciled against reality.

### 8. News Scoring And Source Credibility

The current system uses news scoring and source credibility tracking as part of the decision context. The platform direction is to make this evidence visible and auditable instead of letting news sentiment become an unexplained hidden input.

### 9. Kill Switch And Operational Controls

Taurus treats emergency stop behavior as a core product feature, not an afterthought. The current kill switch blocks live execution locally, and the roadmap adds incident management, status pages, alerts, support workflows, and operational runbooks.

### 10. API, SDK, And Hosted Platform

The roadmap introduces API v1, Python SDK access, workspace-scoped API keys, paper broker endpoints, audit export metadata, model governance endpoints, and enterprise administration. This turns Taurus from a local agent into reusable fintech infrastructure.

## Safety Principles

Taurus is designed around safety constraints that shape both engineering and product language.

- Governance before performance.
- Paper/demo validation before live execution.
- Deterministic risk gates before broker-facing actions.
- Evidence before confidence.
- Reconciliation before trust.
- Model promotion only with recorded reliability evidence.
- Auditability by default.
- Least-privilege access for hosted users and workspaces.
- No public beta feature should require broker credentials.
- No product surface should imply guaranteed returns or investment recommendations.
- Critical risk, reliability, or reconciliation failures should be able to halt operation.

These principles are commercially important because they define Taurus as infrastructure. They are also legally important because they keep the product away from unsafe financial promotion, copy trading, and managed-account positioning.

## Compliance Boundaries

Taurus must stay inside clear boundaries while the product matures.

What Taurus is:

- A research, paper/demo trading, and governance platform.
- A model-risk and execution-governance system for AI-assisted trading workflows.
- A technical infrastructure product for testing, auditability, replay, and operational control.
- A platform for users to evaluate their own systems and assumptions.

What Taurus will not do yet:

- No public personalised investment advice.
- No copy trading.
- No managed accounts.
- No pooled capital.
- No paid trading signals.
- No guarantee of returns.
- No public live execution for beta users.
- No broker credential storage for hosted users until legal, security, encryption, and regulated-activity reviews are complete.
- No marketing language that suggests users should buy, sell, or hold a specific asset.

Historical, simulated, backtested, demo, and paper results must be described as research evidence, not proof of future performance.

## 12-Month Vision

Over the next 12 months, Taurus should evolve from a strong local governance engine into a credible global fintech AI governance platform with public evidence, hosted workflows, and commercial validation.

### June 2026: Public Foundation

Establish public-safe positioning, repository hygiene, product vision, architecture docs, risk governance docs, model governance docs, broker boundaries, demo-only protocol, and weekly build logs.

Success means the project clearly says: this is fintech infrastructure for AI trading governance, not personal trading activity or a profit bot.

### July 2026: Read-Only Dashboard And CI

Launch a read-only FastAPI dashboard over the existing ledger with routes for overview, decisions, risk, models, reliability, reconciliation, and audit. Add Docker and CI checks that protect tests and unsafe-file tracking.

Success means a user can see the governance engine as a product surface without changing trading behavior.

### August 2026: Auth, Workspaces, Hosted Staging, Paper Broker

Add users, sessions, workspaces, RBAC, workspace-scoped queries, hosted staging, health checks, and a first-class paper broker simulator.

Success means Taurus becomes a safe multi-user product shell without requiring broker credentials.

### September 2026: Validation UI, Model Registry, Docs, Private Beta

Add backtest UI, walk-forward UI, model registry, reliability views, public docs, invite-only beta, admin beta dashboard, feedback collection, and usage events.

Success means early users can validate workflows and provide evidence-based feedback.

### October 2026: API, SDK, Broker Abstraction, Audit Export

Introduce API v1, workspace-scoped API keys, Python SDK, broker adapter capability discovery, and exportable audit packs with redaction, checksums, and manifests.

Success means Taurus becomes programmable infrastructure and can support enterprise evaluation.

### November 2026: Billing Interest, Tenant Isolation, Security, Growth

Add billing interest flows, subscription state design, plan limits, tenant isolation hardening, hashed API keys, rate limits, security events, secure cookies, dependency checks, and growth dashboards.

Success means commercial validation starts without crossing regulatory boundaries.

### December 2026: Public Beta

Open a public beta for paper/research workflows with onboarding, safety notices, feedback, beta metrics, public changelog, basic status page, and technical whitepaper.

Success means Taurus becomes publicly usable while remaining legally safe and operationally controlled.

### January 2027: Drift, Incidents, Status, Enterprise Admin

Add drift detection, model review flags, incident management, public status summaries, enterprise admin, retention settings, feature flags, usage metrics, and commercial traction tracking.

Success means the platform handles failure as a first-class workflow.

### February 2027: Reports, Adoption, External Coverage

Generate three-month paper trading and governance reports, open-source adoption reports, media/blog packs, and recommender outreach materials.

Success means Taurus can show external evidence without exposing private financial data or making performance claims.

### March 2027: Security, GDPR, Compliance Pack, Pitch

Add security evidence, privacy workflows, data export/deletion requests, retention policies, admin access logs, compliance packs, and investor-ready technical materials.

Success means Taurus can support serious due diligence.

### April 2027: Commercial Pilots

Use the product, reports, docs, and evidence pack to support pilot conversations with builders, research teams, and small fintech organizations.

Success means the company has credible user demand for governance infrastructure, not speculative trading claims.

### May 2027: The Goal

Package the product, technical evidence, roadmap execution, adoption, pilots, public writing, and external feedback into a coherent founder narrative.

Success means the project demonstrates innovation, technical depth, commercial potential, and leadership in AI-fintech infrastructure.

## Why Taurus Is Innovative

Most AI trading products start from prediction. Taurus starts from governance.

The innovation is not claiming that an AI model can always find profitable trades. The innovation is creating a deterministic operating layer around AI-generated trading decisions so those decisions can be constrained, replayed, audited, reconciled, and improved.

Taurus is differentiated by combining capabilities that are often fragmented across separate tools:

- AI signal generation and news scoring.
- Deterministic risk approvals and vetoes.
- Broker-aware execution modes.
- Ledger-first auditability.
- Backtesting and walk-forward validation.
- Model training, calibration, reliability, promotion, rejection, and rollback.
- Broker reconciliation and execution simulation.
- Kill-switch safety controls.
- Future hosted workspaces, API access, audit exports, incident workflows, and compliance packs.

This combination matters because the next generation of financial automation will not be judged only by model accuracy. It will be judged by whether teams can explain what happened, prove what controls were active, stop unsafe behavior, and learn from failures.

Taurus aims to become the governance layer for that future: a global fintech platform where AI trading agents can be tested and operated with discipline, evidence, and accountability.

## Founder Positioning

The startup story is:

I am building fintech infrastructure for AI trading governance.

The evidence story is:

- The system already has a working local governance engine.
- The roadmap moves from local proof to hosted SaaS infrastructure.
- The product is legally cautious and compliance-aware.
- The technical architecture includes risk, ledger, model governance, reconciliation, audit export, incident response, privacy, and commercial operations.
- The public narrative avoids investment advice and return claims.

Taurus should be evaluated as an infrastructure company: a platform that helps the market adopt AI in trading workflows more safely, not as a personal trading account or a speculative performance product.
