# Contributing

Thank you for considering a contribution to Taurus.

Taurus is a risk-first AI trading governance platform. Contributions should strengthen safety, auditability, reliability, documentation, testing, and research/demo workflows.

## Product Scope

Accepted contribution areas:

- risk governance,
- paper/demo trading safety,
- backtesting and walk-forward validation,
- model governance,
- reconciliation,
- audit logs and audit exports,
- reliability reports,
- documentation,
- tests,
- security and privacy controls,
- developer tooling.

Out of scope without prior review:

- live trading for third-party users,
- personalised investment recommendations,
- copy trading,
- managed accounts,
- paid trading signals,
- crypto promotion,
- performance or return claims,
- storing broker credentials.

## Development Setup

```bash
cp .env.example .env
cp config/strategy.example.toml config/strategy.toml
python3 -m pip install -e .
python3 -m unittest discover -s tests
```

The default mode is `shadow`, which records decisions locally without submitting broker orders.

## Before Opening A Pull Request

Run:

```bash
python3 -m unittest discover -s tests
```

Check that you have not added:

- `.env`,
- `.venv`,
- `config/strategy.toml`,
- `state/`,
- `logs/`,
- SQLite ledgers,
- JSONL audit files,
- generated caches,
- broker credentials,
- API keys,
- private account data.

## Commit And PR Guidance

- Keep changes focused.
- Add tests for behavioral changes.
- Update docs when public behavior changes.
- Avoid investment-performance claims.
- Use clear, technical language.
- Preserve the live-trading safety gates.

## Legal And Safety Language

Use language such as:

- "research/demo governance platform",
- "paper trading",
- "risk controls",
- "model governance",
- "auditability",
- "not investment advice".

Avoid language such as:

- "guaranteed returns",
- "beat the market",
- "buy/sell this asset",
- "copy my trades",
- "managed account",
- "risk-free".
