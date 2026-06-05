# Security Policy

## Scope

Taurus is currently a research/demo governance platform and local agent scaffold. Security reports are welcome for:

- leaked secret handling,
- unsafe Git-tracked runtime files,
- authentication or session issues once web auth is implemented,
- tenant isolation issues once workspaces are implemented,
- API key handling once API access is implemented,
- audit export redaction,
- live-trading safety gates,
- dependency or supply-chain risks.

## Reporting A Vulnerability

Please do not open a public issue for suspected vulnerabilities or leaked credentials. Report privately to the maintainer first, with:

- a short summary,
- affected file, command, or feature,
- reproduction steps,
- expected impact,
- any safe proof of concept without real credentials or private trading data.

If a public GitHub repository is enabled, use GitHub private vulnerability reporting if available. Until then, contact the maintainer privately through the project's published contact channel.

## Sensitive Data Rules

Do not submit:

- real broker credentials,
- API keys,
- account IDs,
- private trading records,
- SQLite ledgers,
- audit JSONL files,
- screenshots containing private account values,
- personal financial data.

## Supported Versions

The project is pre-1.0. Security fixes will target the latest `main` branch until stable releases are introduced.

## Safety Boundaries

Taurus is research, paper/demo trading, and governance infrastructure. Public beta scope must not expose live trading for users, personalised investment advice, copy trading, managed accounts, or guaranteed returns.
