# Implementation Plan

## Product

Taurus: Risk-First AI Trading Governance Platform

## Version

Draft v1.0

## Source Documents

- `PRD.md`
- `TRD.md`
- `APP_FLOW.md`
- `DESIGN_UI_UX_BRIEF.md`
- `BACKEND_SCHEMA.md`
- `README.md`
- Roadmap and implementation schedule from `Pasted text.txt`

## 1. Objective

This implementation plan converts the Taurus roadmap into an engineering sequence for building a production-ready fintech SaaS platform from the existing local trading-governance agent.

The plan focuses on:

- authentication,
- payments,
- billing logic,
- subscription states,
- CRUD logic,
- access controls,
- data integrity,
- scalability,
- latency optimization,
- load balancing,
- logging,
- alerting,
- incident response,
- disaster recovery,
- data retention,
- GDPR/CCPA,
- rate limiting,
- CI/CD,
- environments,
- rollbacks,
- feature flags,
- test coverage,
- instrumentation,
- conversion,
- retention,
- churn control,
- cloud costs,
- multi-region support,
- idempotency,
- support operations,
- escalations,
- governance,
- platform support,
- adtech,
- cookies,
- secrets management,
- documentation,
- A/B testing,
- vendor lock-in,
- platform development.

## 2. Existing Platform Analysis

### 2.1 Current Foundation

The current repository already contains a credible local governance engine:

- Python CLI entrypoints through `python3 -m agent` and `run_agent.py`.
- eToro client and market-data adapters.
- Shadow/demo/live execution modes.
- Live execution gates using `AUTOTRADER_ALLOW_LIVE=true` and `--allow-live`.
- Kill switch through `state/KILL_SWITCH`.
- Deterministic risk controls.
- SQLite ledger.
- JSONL audit logs.
- Backtesting and walk-forward validation.
- Model training, calibration, promotion/rejection, and reliability reporting.
- Reconciliation and monitoring alerts.
- Tests covering core research, risk, data, reliability, reconciliation, and shadow engine behavior.

### 2.2 Production Gaps

The existing platform is not yet production SaaS-ready because it lacks:

- web dashboard,
- authentication,
- workspace tenancy,
- RBAC,
- hosted database,
- production migrations,
- workspace-scoped data model,
- paper broker as a first-class hosted workflow,
- API keys and API v1,
- billing and subscription state,
- feature flags,
- product analytics,
- incident management,
- public status page,
- support operations,
- GDPR/CCPA self-service,
- backup/restore and disaster recovery runbooks,
- CI/CD deployment pipeline,
- cloud cost visibility,
- multi-region plan,
- premium authenticated UI.

### 2.3 Implementation Principle

Do not rebuild the trading engine first. Wrap the existing governance engine with production platform layers in a controlled sequence:

1. Stabilize repo and docs.
2. Add read-only dashboard.
3. Add auth/workspaces.
4. Add workspace scoping.
5. Add paper broker.
6. Add hosted operations.
7. Add API, billing, privacy, incidents, and enterprise controls.

## 3. Workstreams

### 3.1 Product And Documentation

Owns:

- product scope,
- legal-safe language,
- public documentation,
- roadmap docs,
- changelog,
- release notes,
- demo scripts,
- evidence reports.

### 3.2 Platform Foundation

Owns:

- Docker,
- CI/CD,
- environments,
- config,
- health/readiness checks,
- migrations,
- deployment,
- rollback.

### 3.3 Identity And Tenancy

Owns:

- authentication,
- sessions,
- users,
- workspaces,
- members,
- RBAC,
- invite flow,
- access-control tests.

### 3.4 Trading Governance Product

Owns:

- dashboard,
- decisions,
- risk views,
- paper broker,
- backtests,
- walk-forward,
- model registry,
- drift,
- reconciliation,
- audit exports.

### 3.5 Commercial Platform

Owns:

- billing interest,
- plans,
- subscription states,
- entitlement checks,
- quotas,
- future payment provider integration.

### 3.6 Operations And Compliance

Owns:

- logging,
- alerts,
- incidents,
- status page,
- support,
- security events,
- GDPR/CCPA,
- data retention,
- disaster recovery,
- cloud costs,
- multi-region planning.

### 3.7 Growth And Analytics

Owns:

- product events,
- conversion funnels,
- activation,
- retention,
- churn signals,
- A/B testing,
- waitlist/beta metrics,
- commercial evidence exports.

## 4. Phase Plan

## Phase 0: Repository And Product Foundation

Timeline:

- June 2026.

Goal:

Make the current project public-safe and establish the Taurus product narrative.

Implementation tasks:

- Review `.gitignore`.
- Confirm private files remain untracked:
  - `.env`,
  - `.venv`,
  - `state/*.sqlite3`,
  - `state/market_cache.json`,
  - `logs/*.jsonl`,
  - broker credentials,
  - personal trading records.
- Add public-safe docs:
  - product vision,
  - architecture,
  - risk governance,
  - model governance,
  - broker/execution boundaries,
  - demo-only protocol.
- Add build log template.
- Keep public positioning as research/paper/governance-first.

Acceptance criteria:

- Tests pass locally.
- Public README does not contain profit claims.
- Unsafe runtime files are excluded.
- Product scope is clear.

## Phase 1: Read-Only Dashboard And CI

Timeline:

- July 2026.

Goal:

Create the first visible product surface without changing trading behavior.

Implementation tasks:

- Add FastAPI and Jinja2 dependencies.
- Add `src/agent/web/`.
- Add routes:
  - `/`,
  - `/decisions`,
  - `/risk`,
  - `/models`,
  - `/reliability`,
  - `/reconciliation`,
  - `/audit`,
  - `/healthz`.
- Reuse `Ledger` and `ReportingDashboard`.
- Add static CSS aligned with `DESIGN_UI_UX_BRIEF.md`.
- Add persistent safety notice.
- Add app creation tests and route smoke tests.
- Add Dockerfile, `.dockerignore`, `docker-compose.yml`.
- Add CI workflow:
  - install,
  - tests,
  - unsafe-file tracking check.

Production controls:

- Read-only dashboard only.
- No credentials or private ledgers in screenshots/docs.
- No live trading controls in UI.

Acceptance criteria:

- Dashboard starts locally.
- Key routes return 200 with temporary ledger.
- CI passes.
- Docker can run CLI and dashboard.

## Phase 2: Authentication, Workspaces, RBAC

Timeline:

- August 2026.

Goal:

Turn local dashboard into a multi-user product shell.

Implementation tasks:

- Add schema migrations or idempotent table creation.
- Add tables:
  - `users`,
  - `password_credentials` or `magic_links`,
  - `sessions`,
  - `workspaces`,
  - `workspace_members`,
  - `workspace_invites`,
  - `audit_events`.
- Add signup, login, logout.
- Add secure password hashing or passwordless login.
- Add default Personal Workspace.
- Add workspace selector.
- Add role model:
  - owner,
  - admin,
  - viewer.
- Protect dashboard routes.
- Add RBAC helpers.
- Add tests:
  - signup,
  - login,
  - logout,
  - protected route,
  - workspace creation,
  - role checks.

Production controls:

- Secure cookies in hosted environments.
- Session revocation.
- Failed login tracking.
- CSRF for state-changing forms.

Acceptance criteria:

- No protected route is reachable unauthenticated.
- Viewer cannot perform admin actions.
- Disabled user cannot use old session.

## Phase 3: Workspace-Scoped Data And Paper Broker

Timeline:

- August to September 2026.

Goal:

Make the app safe for beta users with strict tenant boundaries and paper-only workflows.

Implementation tasks:

- Add `workspace_id` to tenant-owned ledger records.
- Backfill existing rows into default workspace.
- Add query helpers that require workspace context.
- Add tenant isolation tests across:
  - decisions,
  - risk checks,
  - orders,
  - paper positions,
  - backtests,
  - models,
  - audit exports,
  - API keys,
  - feedback,
  - billing interest.
- Add paper broker tables:
  - `paper_accounts`,
  - `paper_positions`,
  - `paper_orders`,
  - `paper_cash_ledger`.
- Add `execution.mode = "paper"` support.
- Add paper portfolio UI.
- Add reset/seed controls.
- Add tests:
  - buy,
  - sell,
  - insufficient cash,
  - P&L,
  - reset,
  - no eToro API calls.

Production controls:

- Hosted beta defaults to paper.
- Hosted beta rejects live execution.
- Reset requires confirmation.

Acceptance criteria:

- Two workspaces cannot read each other's records.
- Paper order writes cash, position, order, and audit records transactionally.
- Public beta users cannot reach live mode.

## Phase 4: Hosted Staging And Deployment Foundation

Timeline:

- August to September 2026.

Goal:

Make Taurus deployable and operable.

Implementation tasks:

- Add environment profiles:
  - local,
  - test,
  - ci,
  - staging,
  - production_beta.
- Add `/healthz` and `/readyz`.
- Add production config loader from environment variables.
- Add safe default execution mode: `paper` or `shadow`.
- Add sample/demo data seeding.
- Add deployment guide for one provider.
- Add database backup notes.
- Add rollback notes.
- Add smoke tests.

Production controls:

- No live trading in hosted demo.
- No committed environment secrets.
- Staging uses sample/sanitized data.

Acceptance criteria:

- Hosted staging deploys.
- Health and readiness checks pass.
- Rollback path documented.

## Phase 5: Validation UI And Model Registry

Timeline:

- September 2026.

Goal:

Expose validation and model governance workflows through the dashboard.

Implementation tasks:

- Add backtest routes:
  - `GET /backtests`,
  - `POST /backtests/run`,
  - `GET /backtests/{id}`,
  - export Markdown/JSON.
- Add walk-forward routes:
  - `GET /walk-forward`,
  - `POST /walk-forward/run`,
  - `GET /walk-forward/{id}`.
- Move long runs into background jobs.
- Add model registry routes:
  - `GET /models`,
  - `GET /models/{version}`,
  - `POST /models/train`,
  - `POST /models/{version}/promote`,
  - `POST /models/{version}/rollback`.
- Add audit records for train/promote/rollback.
- Add tests for:
  - run creation,
  - result persistence,
  - workspace isolation,
  - insufficient sample handling,
  - promotion governance,
  - rollback audit logging.

Production controls:

- Historical/paper results disclaimer.
- No arbitrary model upload.
- Promotion only through governance gate.

Acceptance criteria:

- Backtests and model actions are workspace-scoped.
- Long jobs do not block request thread.
- Model rollback requires reason and audit event.

## Phase 6: Private Beta, Feedback, And Usage Instrumentation

Timeline:

- September 2026.

Goal:

Support 10 to 20 invited users and collect structured feedback.

Implementation tasks:

- Add invite-only registration.
- Add beta onboarding page.
- Add feedback form and table.
- Add usage event tracking:
  - signup,
  - login,
  - workspace created,
  - backtest run,
  - paper order,
  - model training attempt,
  - feedback submitted.
- Add admin beta dashboard.
- Add weekly beta report export.
- Add docs/beta outreach materials.

Production controls:

- No broker credentials collected.
- No investment preferences collected.
- Feedback and usage exports are redacted.

Acceptance criteria:

- Invite-only registration works.
- Admin can see beta usage metrics.
- Feedback is workspace/user scoped.

## Phase 7: API v1, SDK, Broker Adapter Layer

Timeline:

- October 2026.

Goal:

Make Taurus a developer platform.

Implementation tasks:

- Add API package under `src/agent/api/v1`.
- Add hashed API keys with one-time reveal.
- Add API endpoints:
  - health,
  - workspace summary,
  - decisions,
  - risk reports,
  - backtests,
  - walk-forward,
  - models,
  - paper portfolio,
  - audit events,
  - audit exports.
- Add API rate limiting.
- Add API usage events.
- Add Python SDK under `sdk/python`.
- Refactor broker layer into:
  - `shadow`,
  - `paper`,
  - `etoro`,
  - registry/factory,
  - capability discovery.
- Add adapter contract tests.

Production controls:

- API keys scoped to workspace.
- Revoked API keys fail immediately.
- No live trading endpoint for beta.

Acceptance criteria:

- SDK smoke tests pass.
- API cannot leak cross-workspace data.
- Broker adapter contract tests pass.

## Phase 8: Audit Export And Compliance Pack

Timeline:

- October 2026 to March 2027.

Goal:

Make governance evidence exportable and enterprise-review friendly.

Implementation tasks:

- Add audit export builder.
- Add formats:
  - JSON,
  - CSV,
  - Markdown,
  - ZIP optional.
- Add redaction service.
- Add manifest with row counts and SHA-256 checksums.
- Add generated artifacts table/object storage.
- Add compliance pack export:
  - product scope,
  - risk governance,
  - model governance,
  - audit exports,
  - incidents,
  - security,
  - GDPR controls,
  - limitations.
- Add tests:
  - redaction,
  - workspace isolation,
  - checksum generation,
  - date filtering,
  - export completeness.

Production controls:

- Admin/owner-only.
- Secrets and personal data redacted by default.
- Export artifacts expire according to retention policy.

Acceptance criteria:

- Export cannot include another workspace.
- Export has manifest and checksums.
- Redaction tests pass.

## Phase 9: Billing Interest, Subscription States, Entitlements

Timeline:

- November 2026.

Goal:

Validate commercial demand without unsafe payment or regulated scope.

Implementation tasks:

- Add pricing/billing interest page.
- Add `plans`, `billing_interest`, `subscriptions`, `subscription_events`, `entitlement_snapshots`.
- Add subscription states:
  - none,
  - waitlist_interest,
  - trial_pending,
  - trial_active,
  - trial_expired,
  - beta_free,
  - beta_paid_pending,
  - active,
  - past_due,
  - payment_failed,
  - cancelled,
  - suspended,
  - comped,
  - enterprise_invoice_pending.
- Add entitlement service.
- Add quota checks.
- Add optional Stripe test-mode provider behind disabled feature flag.
- Add webhook idempotency design.
- Add tests:
  - state transitions,
  - entitlement checks,
  - duplicate webhook,
  - past due behavior,
  - cancelled data export rights.

Production controls:

- No card data stored.
- No live trading sold.
- No investment advice sold.
- Real payments require legal/accounting review.

Acceptance criteria:

- Billing interest works without payment provider.
- Entitlements derive from state, plan, role, quota, and feature flags.
- Billing webhooks are idempotent before any live integration.

## Phase 10: Security Hardening, Rate Limits, Feature Flags

Timeline:

- November 2026 to March 2027.

Goal:

Make the product safe for public beta and enterprise review.

Implementation tasks:

- Add CSRF to state-changing forms.
- Add secure cookie settings.
- Add security headers.
- Add login and API rate limits.
- Add hashed API keys.
- Add user disable/session revocation.
- Add secret redaction utility.
- Add feature flag system:
  - global,
  - environment,
  - workspace,
  - user,
  - plan.
- Add security events table.
- Add dependency/security scan in CI where practical.
- Add tests:
  - CSRF,
  - rate limit,
  - API key hashing,
  - revoked keys,
  - disabled users,
  - role enforcement,
  - redaction,
  - security headers.

Production controls:

- Feature flags cannot be sole live-trading gate.
- Secrets never rendered in templates.
- CI fails if unsafe files are tracked.

Acceptance criteria:

- Security test suite passes.
- Tenant isolation tests remain launch blockers.
- Rate limit UX and API errors are stable.

## Phase 11: Public Beta Launch

Timeline:

- December 2026.

Goal:

Make the product publicly usable in paper/research mode.

Implementation tasks:

- Add public beta landing.
- Add public signup/waitlist.
- Add paper-only onboarding.
- Add public changelog.
- Add public status page.
- Add beta feedback form.
- Add admin beta metrics dashboard.
- Add testimonial collection with explicit consent.
- Add docs links and public safety notices.

Production controls:

- No live trading for public users.
- No personalised advice.
- No financial promotion.
- No broker credentials.

Acceptance criteria:

- Public beta users can onboard to paper workflow.
- Admin can export beta metrics.
- Status page is public-safe.

## Phase 12: Incidents, Observability, Support Operations

Timeline:

- December 2026 to January 2027.

Goal:

Operate Taurus as a production platform.

Implementation tasks:

- Add structured JSON logging.
- Add request IDs.
- Add alert rules:
  - API errors,
  - login attacks,
  - rate-limit spikes,
  - backup failures,
  - failed exports,
  - model drift,
  - reconciliation drift,
  - paper broker inconsistency,
  - billing webhook failure.
- Add incident tables and UI.
- Add public status page management.
- Add support ticket system.
- Add escalation workflows.
- Add postmortem template.
- Add tests:
  - incident creation,
  - dedupe,
  - escalation,
  - status redaction,
  - support permissions.

Production controls:

- Public status must not leak private workspace/security data.
- Critical incidents require postmortem.
- Support access to personal data requires reason and audit.

Acceptance criteria:

- Incidents can be created, assigned, resolved, exported.
- Status page can show safe component status.
- Support workflow is auditable.

## Phase 13: GDPR/CCPA, Retention, Cookies, Adtech Controls

Timeline:

- March 2027.

Goal:

Provide responsible data protection controls before growth.

Implementation tasks:

- Add privacy notice.
- Add cookie preferences.
- Add consent table and consent settings UI.
- Add user data export.
- Add account/workspace deletion request.
- Add pseudonymisation workflow.
- Add testimonial consent withdrawal.
- Add marketing consent withdrawal.
- Add retention policies.
- Add admin data-access audit.
- Add DPIA-lite docs.
- Add tests:
  - data export,
  - deletion/pseudonymisation,
  - consent updates,
  - retention dry-run,
  - admin access logging,
  - tenant isolation.

Production controls:

- Essential cookies only before consent.
- No adtech pixels in authenticated app by default.
- Public exports redacted.

Acceptance criteria:

- User can export data.
- User can request deletion.
- Consent changes are audited.
- Retention job behavior is test-covered.

## Phase 14: Growth, Conversion, Retention, Churn, Cloud Costs

Timeline:

- November 2026 to April 2027.

Goal:

Measure product value and cost discipline.

Implementation tasks:

- Add product events:
  - signup,
  - workspace created,
  - paper account seeded,
  - first backtest,
  - first paper order,
  - first audit export,
  - API key created,
  - billing interest submitted.
- Add activation snapshot.
- Add retention snapshots.
- Add churn risk scoring.
- Add admin growth dashboard.
- Add commercial traction tracker.
- Add cloud cost snapshots.
- Add quota usage tracking.
- Add A/B testing for allowed surfaces:
  - landing copy,
  - onboarding order,
  - pricing interest layout,
  - docs CTA.

Production controls:

- Do not track investment preferences.
- Do not send private financial data to analytics.
- A/B tests cannot change safety notices, risk controls, billing charges, or live gates.

Acceptance criteria:

- Admin can view conversion and retention.
- Churn signals create support follow-up.
- Cloud cost dashboard shows spend and quotas.

## Phase 15: Disaster Recovery, Multi-Region, Vendor Lock-In

Timeline:

- January to May 2027.

Goal:

Prepare Taurus for enterprise and commercial pilots.

Implementation tasks:

- Add automated backups.
- Add monthly restore test.
- Add disaster recovery runbook.
- Add rollback runbook.
- Add object storage lifecycle policy.
- Add provider abstraction docs:
  - broker,
  - billing,
  - storage,
  - queue,
  - email,
  - analytics,
  - secrets.
- Add multi-region plan:
  - single-region beta,
  - read replicas later,
  - object storage replication,
  - active-passive failover,
  - data residency review.

Production controls:

- Beta RPO: 24 hours.
- Beta RTO: 8 hours.
- Production target RPO: 1 hour.
- Production target RTO: 2 hours.

Acceptance criteria:

- Restore test documented.
- Rollback tested.
- Vendor exit paths documented.
- Multi-region plan exists before enterprise launch.

## Phase 16: Evidence Freeze And Final Demo

Timeline:

- April to May 2027.

Goal:

Stabilize the product for external review, beta evidence, and other founder evidence materials.

Implementation tasks:

- Create release tag.
- Create changelog.
- Freeze risky product changes.
- Export metrics dossier.
- Generate final demo script.
- Verify docs links.
- Verify no secrets/private user data in screenshots.
- Run test suite and record result.
- Create readiness scorecard.

Acceptance criteria:

- Stable demo URL.
- CI passing.
- Docs complete.
- Known limitations documented.
- Product remains paper/research/governance-first.

## 5. Cross-Cutting Engineering Requirements

### 5.1 Data Integrity

Implementation rules:

- Use transactions for multi-table writes.
- Enforce foreign keys.
- Add unique constraints for idempotent actions.
- Use checksums for exports and model artifacts.
- Preserve raw JSON for auditability.
- Add normalized indexed fields for dashboard/API performance.

### 5.2 Latency And Scalability

Implementation rules:

- Keep web workers stateless.
- Move long work to background jobs.
- Add pagination to all list pages.
- Cache dashboard summaries.
- Add database indexes on `workspace_id`, `created_at`, status, symbol, model version, and event name.
- Use object storage for large artifacts.
- Use load balancer health/readiness checks.

Targets:

- `/healthz` p95 under 100 ms.
- Cached dashboard p95 under 500 ms.
- API list p95 under 800 ms.
- Job creation p95 under 1 second.

### 5.3 Test Coverage

Launch-blocking tests:

- auth,
- RBAC,
- tenant isolation,
- live-trading gates,
- paper broker integrity,
- API key hashing/revocation,
- billing idempotency,
- audit export redaction,
- secret redaction,
- GDPR export/deletion,
- incident redaction,
- migrations.

### 5.4 Documentation

Every phase must update:

- README when public behavior changes.
- PRD/TRD/app flow if scope changes.
- schema docs when tables change.
- deployment docs when infrastructure changes.
- security/privacy/compliance docs when controls change.
- changelog for user-facing changes.

## 6. Production Readiness Gates

Private beta gate:

- auth,
- workspace isolation,
- paper broker,
- protected dashboard,
- feedback,
- product events,
- CI,
- legal-safe copy.

Public beta gate:

- rate limiting,
- feature flags,
- incident system,
- status page,
- privacy/cookie controls,
- audit export redaction,
- backup/restore runbook,
- rollback runbook,
- support workflow.

Paid beta gate:

- legal/accounting review,
- subscription state machine,
- entitlement checks,
- billing webhook idempotency,
- cancellation/refund policy,
- billing support escalation,
- no regulated scope creep.

Enterprise pilot gate:

- tenant isolation proof,
- enterprise admin,
- audit/compliance pack,
- data retention settings,
- GDPR/CCPA workflow,
- incident postmortems,
- backup restore test,
- vendor exit plan.

## 7. Recommended Immediate Next Steps

1. Keep the current repo safe by excluding private runtime files.
2. Add the July read-only dashboard with FastAPI and Jinja2.
3. Add Docker and CI.
4. Add health/readiness endpoints.
5. Add auth, sessions, workspaces, and RBAC.
6. Add workspace-scoped ledger migration.
7. Add paper broker tables and simulator.
8. Add tenant isolation tests before expanding beta functionality.
9. Add deployment docs and hosted staging.
10. Add product instrumentation from the first authenticated workflow.
