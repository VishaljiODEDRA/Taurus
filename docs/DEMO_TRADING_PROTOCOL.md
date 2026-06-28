# Taurus Demo Trading Protocol

## Purpose

This protocol defines the safe June 2026 operating workflow for Taurus.

The goal is to produce disciplined product-validation evidence without regulatory, privacy, or capital-risk mistakes. Taurus should be operated as research, paper/demo trading, and governance infrastructure. It must not be presented as investment advice, a trading signal service, copy trading, a managed account, or a guarantee of trading performance.

For June 2026:

- Use `shadow` or `demo` mode only.
- Keep `AUTOTRADER_ALLOW_LIVE=false`.
- Never run any command with `--allow-live`.
- Do not publish credentials, account IDs, raw ledgers, raw audit logs, broker screenshots, private account values, or personal trading records.
- Publish only redacted, non-sensitive weekly summaries that show disciplined validation.

## Operating Modes

Taurus supports three execution modes in `config/strategy.toml`:

| Mode | Meaning | June 2026 use |
| --- | --- | --- |
| `shadow` | Records decisions and synthetic order results locally. No broker order is submitted. | Safe for local dry runs and public demos. |
| `demo` | Uses eToro demo endpoints when credentials are configured. | Allowed for disciplined demo-only validation. |
| `live` | Uses eToro real endpoints only when both live gates are enabled. | Not allowed in June 2026. |

The public repository should keep only `config/strategy.example.toml`. The local `config/strategy.toml` may be used for private demo settings, but it must remain untracked.

## Required Local Safety Settings

Before any operating session, verify:

```bash
rg -n 'mode =|environment =' config/strategy.toml
rg -n '^AUTOTRADER_ALLOW_LIVE=' .env
```

Expected safe state:

```text
mode = "shadow"
```

or:

```text
mode = "demo"
environment = "demo"
AUTOTRADER_ALLOW_LIVE=false
```

Do not continue if:

- `mode = "live"`,
- `environment = "real"` for a live workflow,
- `AUTOTRADER_ALLOW_LIVE=true`,
- a command includes `--allow-live`.

## Verify Live Trading Is Blocked

The code requires both live gates before live broker construction:

- environment variable: `AUTOTRADER_ALLOW_LIVE=true`,
- CLI flag: `--allow-live`.

June protocol requires the opposite:

```bash
rg -n '^AUTOTRADER_ALLOW_LIVE=' .env
```

Expected:

```text
AUTOTRADER_ALLOW_LIVE=false
```

A safe live-block check is:

```bash
python3 -m agent run-once --config config/strategy.toml
```

This command must be run without `--allow-live`. If the local config is accidentally set to `live`, Taurus should halt before broker construction because the live CLI gate and environment gate are missing. After confirming the block, immediately return the config to `shadow` or `demo`.

Do not run an actual live command for testing. The absence of `--allow-live`, `AUTOTRADER_ALLOW_LIVE=false`, `.gitignore` protection, and the documented dual-gate design are sufficient June evidence.

## Kill Switch

The kill switch is the emergency halt. The default path is:

```text
state/KILL_SWITCH
```

Check status:

```bash
python3 -m agent kill-switch status --config config/strategy.toml
```

Turn it on:

```bash
python3 -m agent kill-switch on --config config/strategy.toml --reason "demo validation pause"
```

Turn it off only when intentionally resuming a safe shadow/demo session:

```bash
python3 -m agent kill-switch off --config config/strategy.toml --reason "resume demo validation"
```

If the kill switch is on, `run-once` returns a halted cycle and does not reach broker execution.

## Standard Demo Validation Workflow

Run the following commands from the repository root. Do not add `--allow-live`.

If the editable package is not installed and `python3 -m agent ...` fails with `No module named agent`, use the local runner with the same subcommand:

```bash
python3 run_agent.py <command> --config config/strategy.toml
```

### 1. Check Configuration And Connectivity

```bash
python3 -m agent doctor --config config/strategy.toml
```

Purpose:

- confirms local config can load,
- checks whether eToro authentication is configured,
- helps identify setup problems before a cycle.

Do not publish raw doctor output if it includes account-specific details.

### 2. Check Cached Market Data Health

```bash
python3 -m agent data-health --config config/strategy.toml
```

Purpose:

- summarizes candle-cache coverage,
- confirms whether backtest/walk-forward inputs are available,
- supports evidence that validation is data-quality aware.

Safe summary fields:

- number of symbols with usable candles,
- minimum/median candle counts,
- missing or stale coverage counts.

Do not publish raw cache files.

### 3. Run One Shadow Or Demo Cycle

```bash
python3 -m agent run-once --config config/strategy.toml
```

Purpose:

- loads market/news/portfolio context,
- ranks decisions,
- records decision evidence,
- runs risk gates,
- records risk checks,
- records order results only if all controls approve.

Safety requirements:

- no `--allow-live`,
- `AUTOTRADER_ALLOW_LIVE=false`,
- mode must be `shadow` or `demo`,
- kill switch should be checked before and after the run.

Public summaries may mention counts, such as decisions, risk checks, rejected orders, halted cycles, and reconciliation status. Do not publish symbols tied to private account state, broker order IDs, account balances, screenshots, raw JSON, SQLite ledgers, or audit logs.

### 4. Sync Broker State For Demo Research

```bash
python3 -m agent sync-broker --config config/strategy.toml
```

Purpose:

- imports available demo/real account metadata only for private reconciliation and research,
- records broker account snapshots and available trade-history-derived outcomes when returned by the API.

June safety rule:

- use this only with demo-mode operating discipline,
- do not publish raw broker history,
- do not publish account IDs, balances, positions, order IDs, or private P&L.

If raw history diagnostics are needed, use a private ignored path such as:

```bash
python3 -m agent sync-broker --config config/strategy.toml --dump-history state/etoro_history_dump.json
```

Never commit files under `state/`.

### 5. Reconcile Broker And Ledger

```bash
python3 -m agent reconcile --config config/strategy.toml
```

Purpose:

- compares broker portfolio state with local accepted orders and open trade contexts,
- detects duplicate exposure, missing local orders, missing broker positions, position drift, stale protection, and P&L mismatch,
- records a reconciliation report in the local ledger.

Safe public summary:

- reconciliation status: `ok`, `warning`, `alert`, `skipped`, or `error`,
- alert count by severity,
- whether follow-up was required.

Do not publish raw reconciliation payloads.

### 6. Generate Local Governance Report

```bash
python3 -m agent report --config config/strategy.toml
```

Purpose:

- summarizes institutional decision/risk/execution evidence from the ledger,
- supports weekly validation notes,
- helps identify whether risk gates and execution controls behaved as expected.

Safe summary fields:

- cycle count,
- decision count,
- risk approval/rejection count,
- order acceptance/rejection count,
- top rejection reasons after removing sensitive details,
- model/reliability report status,
- reconciliation status.

Do not publish raw private ledger rows.

## Optional Reliability Evidence

For weekly governance evidence, run:

```bash
python3 -m agent reliability-report --config config/strategy.toml --type all
```

Safe summary fields:

- report type,
- status,
- high-level summary,
- whether more data is needed.

Do not present paper/demo results as future-performance evidence.

## Weekly Non-Sensitive Summary

Create a short weekly summary for public build logs, investor evidence, or founder evidence. Store only redacted summaries in public docs. Keep raw ledgers, logs, account snapshots, broker payloads, and screenshots private.

Suggested filename:

```text
docs/weekly-summaries/YYYY-MM-DD-demo-validation.md
```

Suggested structure:

```markdown
# Taurus Weekly Demo Validation Summary: YYYY-MM-DD

## Scope

- Mode used: shadow/demo only
- Live gate: AUTOTRADER_ALLOW_LIVE=false
- CLI live flag: not used
- Kill switch status checked: yes/no

## Commands Run

- doctor
- data-health
- run-once
- sync-broker
- reconcile
- report
- reliability-report, if run

## Governance Outcomes

- Cycles run:
- Decisions recorded:
- Risk checks recorded:
- Orders recorded:
- Rejections by category:
- Reconciliation status:
- Reliability report status:

## Safety Notes

- No live execution.
- No public investment advice.
- No copy trading or managed account activity.
- No raw ledger, audit log, credentials, account IDs, balances, or broker payloads published.

## Product Learning

- What worked:
- What failed or halted:
- Follow-up engineering tasks:
```

Keep the summary focused on operating discipline, technical validation, auditability, and safety controls. Avoid trading claims such as profit, alpha, guaranteed returns, or recommendations to buy or sell any asset.

## Public Evidence Rules

Allowed public evidence:

- redacted command checklist,
- mode and live-gate confirmation,
- high-level counts,
- safety decisions,
- risk rejection categories,
- reconciliation status,
- reliability report status,
- engineering follow-up tasks,
- screenshots only if they contain no account data, order IDs, credentials, personal financial data, or private broker payloads.

Not allowed publicly:

- `.env`,
- broker credentials,
- account IDs,
- broker order IDs,
- private balances or positions,
- raw `state/*.sqlite3`,
- raw `logs/*.jsonl`,
- raw `state/market_cache.json`,
- raw broker history dumps,
- screenshots with private account values,
- claims that Taurus generated returns or can predict future returns.

## Session Checklist

Before running:

- `config/strategy.toml` is untracked.
- `.env` is untracked.
- `mode` is `shadow` or `demo`.
- `environment` is `demo` for demo mode.
- `AUTOTRADER_ALLOW_LIVE=false`.
- Command does not include `--allow-live`.
- Kill switch status is known.

During running:

- Stop if any command reports live mode or real environment.
- Stop if unexpected broker/account data appears in output intended for public use.
- Use the kill switch for any uncertainty.

After running:

- Run `reconcile`.
- Run `report`.
- Create a redacted weekly summary.
- Do not commit private runtime files.
- Record engineering follow-ups in public-safe language.

## Product Validation and Evidence Positioning

This protocol supports future evidence by showing:

- disciplined product validation,
- safety-first engineering practice,
- clear regulatory boundaries,
- audit-focused operations,
- repeatable validation workflows,
- separation of private account data from public technical evidence,
- technical leadership in AI trading governance infrastructure.

The evidence story should be: Taurus is building fintech infrastructure for safe AI trading governance, not operating a personal trading strategy.
