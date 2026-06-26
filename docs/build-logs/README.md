# Taurus Public Build Logs

## Purpose

This folder contains public build logs for Taurus, a risk-first AI trading governance platform.

The build-log system is designed to create a visible, consistent timeline of founder-engineer execution from June 2026 through May 2027. By May 2027, the target is 40-50 public logs showing steady progress across product, engineering, safety, documentation, validation, and commercial-readiness work.

These logs are public evidence of disciplined product development. They are not trading performance reports, investment advice, financial promotions, copy-trading material, or managed-account updates.

## Publishing Rules

Each public build log should be safe to publish on GitHub and adapt for LinkedIn, Medium, or dev.to.

Allowed:

- product and engineering shipped,
- architecture and governance decisions,
- tests run and high-level results,
- demo/shadow validation findings without private account data,
- safety controls and compliance boundaries,
- risks and mitigations,
- next implementation priorities.

Not allowed:

- broker credentials,
- account IDs,
- private balances or positions,
- raw `state/*.sqlite3` files,
- raw `logs/*.jsonl` files,
- raw broker payloads,
- private P&L screenshots,
- claims that Taurus produced profit or can predict returns,
- recommendations to buy, sell, or hold any asset.

## Naming Convention

Use one file per week:

```text
YYYY-MM-DD-week-NN.md
```

Examples:

```text
2026-06-07-week-01.md
2026-06-14-week-02.md
2026-06-21-week-03.md
```

Use the Sunday date for the week ending, unless a future publishing schedule deliberately changes that convention.

## Weekly Workflow

1. Review the previous week's implementation plan.
2. Check `git status --short`.
3. Run the relevant test suite or smoke checks.
4. Summarize only non-sensitive demo/shadow findings.
5. Write the build log in this folder.
6. Publish the same public-safe story to GitHub and adapt it for LinkedIn, Medium, or dev.to.
7. Link any public article, demo, or release in a future log.

## Reusable Template

Copy this template for each weekly log.

```markdown
# Taurus Build Log: Week NN

Date: YYYY-MM-DD

## Context

One short paragraph explaining where the project is in the roadmap and what this week was meant to prove.

## What Shipped

- Public-safe product or engineering work completed.
- Documents, modules, tests, demos, or workflows added.
- Any visible user-facing or developer-facing improvement.

## Technical Decisions

- Architecture, data, security, risk, model governance, broker, or UX decisions made.
- Why the decision keeps the product safer, clearer, or more scalable.

## Tests And Verification

- Test commands run.
- Smoke checks run.
- High-level result only.
- Any known limitations or follow-up checks.

## Demo And Validation Findings

- Shadow/demo-only findings.
- Reconciliation or data-health notes without private account data.
- Product lessons from running the system.

## Safety And Compliance Notes

- Confirm no public investment advice.
- Confirm no copy trading or managed-account positioning.
- Confirm no public live execution.
- Confirm private ledgers, logs, credentials, and account details were not published.

## Risks And Open Questions

- Engineering risks.
- Product risks.
- Compliance or operational questions.
- Data or reliability gaps.

## Next Week

- The next 3-7 concrete implementation priorities.
```

## Current Index

| Week | Date | Log |
| --- | --- | --- |
| 01 | 2026-06-07 | [2026-06-07-week-01.md](2026-06-07-week-01.md) |

