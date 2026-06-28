# Taurus Governance Cockpit

## Purpose

The Taurus governance cockpit turns the local ledger and audit trail into a read-only product surface. It is designed to answer whether an AI-assisted trading workflow is explainable, replayable, risk-controlled, reconciled, and safe enough for paper/demo review.

The product stance is:

- AI components may propose, summarize, and explain.
- Deterministic controls decide whether broker-facing action is allowed.
- Public product evidence must not expose private runtime data.

## What It Shows

The cockpit includes:

- dashboard overview,
- chronological evidence timeline,
- decision drill-down,
- risk control matrix,
- model cards,
- reliability reports,
- broker reconciliation status,
- incident and halt timeline,
- governed agent role boundaries,
- decision replay,
- audit metadata,
- redacted audit export packs.

## Demo Data Mode

Run a public-safe demo without private ledgers or broker data:

```bash
python3 -m agent.web --demo-data --host 127.0.0.1 --port 8000
```

Demo mode creates an obviously synthetic ledger in a temporary location. It includes approved and blocked decisions, risk checks, orders, model promotion/rejection events, reliability reports, reconciliation warnings, broker snapshots, committee votes, and execution simulations.

## Replay

Replay is the signature governance workflow. It lets a reviewer select one recorded decision and inspect:

- what Taurus knew at the time,
- feature and decision evidence,
- related risk checks,
- related orders,
- related model version,
- related reconciliation evidence,
- later reliability warnings,
- replay coverage gaps.

Replay is not a performance backtest page. It is a governed causality view.

## Audit Export Pack

Create a redacted audit pack:

```bash
python3 -m agent export-audit-pack --config config/strategy.toml --output exports/YYYY-MM-DD-taurus-audit-pack.zip
```

The ZIP contains:

- `summary.json`,
- `report.html`,
- `manifest.json`,
- `checksums.sha256`,
- `README.txt`.

The export excludes credentials, account identifiers, raw broker payloads, full private paths, raw audit logs, and performance claims.

## Governed Agent Roles

The cockpit documents the system as governed roles rather than one opaque trading loop:

- Research Agent,
- Signal Agent,
- Risk Governor,
- Model Governance Agent,
- Reconciliation Agent,
- Reliability Agent,
- Report Agent.

Only deterministic controls can approve or block broker-facing action. Agent roles cannot bypass risk gates.

## Out Of Scope

This phase does not add:

- live trading controls,
- public live execution,
- SaaS accounts,
- authentication,
- billing,
- multi-user workspaces,
- broker credential entry,
- investment advice,
- copy trading,
- managed accounts,
- return or profit claims.

Taurus remains paper/demo/research-first infrastructure.
