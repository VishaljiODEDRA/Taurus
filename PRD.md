# Product Requirements Document

## Product

Taurus: Risk-First AI Trading Governance Platform

## Version

Draft v1.0, based on the June 2026 to May 2027 product roadmap.

## Owner

Founder/Product Engineering

## Status

Planning and implementation guidance for a production-ready SaaS beta.

## 1. Executive Summary

The product is a risk-first AI trading governance platform for paper trading, backtesting, model governance, auditability, and fintech developer infrastructure. It must not be positioned as a profit bot, investment adviser, copy-trading service, managed account, financial promotion, or live trading service for third-party users.

The current repository is a local autonomous trading agent scaffold with:

- deterministic risk gates,
- shadow/demo/live execution modes with strict live gates,
- eToro integration,
- SQLite ledger,
- audit logs,
- model training and promotion controls,
- backtesting and walk-forward validation,
- reconciliation,
- reliability reports,
- kill switch,
- local CLI workflows.

The roadmap evolves this into a production-ready SaaS platform with web dashboard, authentication, workspaces, paper broker, hosted staging, API/SDK, audit exports, model registry, compliance controls, incident response, public beta, and evidence-grade reporting.

## 2. Product Thesis

AI can generate research, score signals, and propose actions, but deterministic governance must decide whether anything is allowed to execute. The platform should help traders, fintech builders, AI-agent developers, small funds, and research teams validate autonomous trading workflows safely before any regulated or live use.

The first production product is not "AI that trades for you." It is infrastructure for:

- paper trading,
- simulation,
- risk governance,
- model governance,
- audit exports,
- broker reconciliation,
- compliance-aware reporting,
- developer access through API/SDK.

## 3. Goals

- Provide a secure, hosted, multi-tenant dashboard for paper/research trading workflows.
- Allow users to create workspaces, run safe simulations, inspect decisions, run backtests, and export audit evidence.
- Enforce tenant isolation, role-based access, billing state, and feature flags.
- Build fintech-grade reliability: monitoring, alerting, incident response, rollback, backup, data retention, audit logs, and disaster recovery.
- Provide production telemetry for conversion, activation, retention, churn, product usage, cloud costs, and operational quality.
- Maintain legally safe product boundaries: no investment advice, no copy trading, no managed accounts, no public live execution, no performance promises.
- Support a public beta and future commercial pilots with clear governance and support operations.

## 4. Non-Goals

- No public personalised investment advice.
- No stock recommendations to users.
- No copy trading.
- No managed accounts.
- No pooled funds.
- No public financial promotions.
- No crypto promotion.
- No guaranteed return claims.
- No live broker execution for beta users.
- No storing broker credentials until encrypted key management, legal review, and regulated activity review are complete.
- No arbitrary user-uploaded model files in the MVP.

## 5. Target Users

### Primary Users

- Fintech engineers building autonomous finance systems.
- AI-agent developers validating trading-agent workflows.
- Advanced traders and researchers using paper trading and backtesting.
- Small research teams that need auditability and model governance.

### Secondary Users

- Risk/compliance reviewers.
- Startup advisers and technical investors.
- Open-source contributors.
- Beta testers evaluating product usability and architecture.

### Admin Users

- Platform owner.
- Workspace owner.
- Workspace admin.
- Viewer/read-only user.
- Support operator.

## 6. User Problems

- AI trading systems often lack explainability and deterministic risk controls.
- Paper and demo validation workflows are fragmented.
- Backtest results are easy to overstate and hard to audit.
- Model versions, promotion decisions, and drift are rarely tracked clearly.
- Broker reconciliation, slippage, and execution simulation are often treated as afterthoughts.
- Early fintech products need safe legal positioning, access control, audit logs, and incident response before public beta.

## 7. Product Scope By Phase

### Phase 0: June 2026 - Public Foundation

Required outcomes:

- Clean public repository hygiene.
- Safe `.gitignore` and no committed secrets, ledgers, logs, credentials, caches, or private runtime state.
- Product vision document.
- Architecture, risk governance, model governance, and broker execution docs.
- Demo-only trading protocol.
- Weekly public build logs.
- Outreach pack for technical feedback.

Production relevance:

- Establish safe public positioning.
- Document product category and compliance boundaries.
- Create repeatable engineering evidence.

### Phase 1: July 2026 - Read-Only Dashboard And CI

Required features:

- Read-only FastAPI + Jinja2 dashboard.
- Routes for overview, decisions, risk, models, reliability, reconciliation, and audit.
- Persistent safety notice: "Research/paper/demo trading. Not investment advice."
- Dockerfile, `.dockerignore`, `docker-compose.yml`.
- GitHub Actions CI for install, tests, and unsafe-file checks.
- First technical article and demo video pack.
- Legal-safe product scope.

Production relevance:

- First visible product surface.
- CI/CD foundation.
- Safe external demo without private account data.

### Phase 2: August 2026 - Auth, Workspaces, Hosted Staging, Paper Broker

Required features:

- Users, sessions, workspaces, workspace members, workspace settings.
- Default personal workspace.
- Roles: owner, admin, viewer.
- Secure password hashing or passwordless architecture.
- Workspace-scoped dashboard queries.
- Hosted staging with HTTPS, `/healthz`, production config, environment variables, sample data, and safe shadow/paper defaults.
- Paper broker simulator with cash, positions, fills, P&L, order IDs, reset, and workspace-scoped paper accounts.
- Early-user collection flow with consent and minimal data collection.

Production relevance:

- Turns local dashboard into SaaS foundation.
- Establishes tenant boundaries.
- Provides safe beta workflow without broker credentials.

### Phase 3: September 2026 - Validation UI, Model Registry, Docs, Private Beta

Required features:

- Backtest UI with run/list/detail/export.
- Walk-forward UI with train/test windows and period metrics.
- Model registry UI with candidate, active, rejected, archived, promote, rollback, lineage, metrics, and reliability reports.
- Public MkDocs documentation site.
- Invite-only private beta for 10 to 20 users.
- Admin beta dashboard.
- Feedback form.
- Usage events.
- Weekly beta report exports.

Production relevance:

- Product becomes useful for early users.
- Adds repeatable validation and governance workflows.
- Starts measuring activation and product feedback.

### Phase 4: October 2026 - API, SDK, Broker Abstraction, Audit Export

Required features:

- REST API under `/api/v1`.
- Workspace-scoped API keys.
- Endpoints for health, summary, decisions, risk, backtests, walk-forward, models, paper portfolio, audit events, and export metadata.
- Python SDK with examples.
- Broker adapter abstraction with shadow, paper, and eToro adapters.
- Broker capability discovery.
- Workspace/date-scoped audit exports in JSON, CSV, Markdown, and optional ZIP.
- Redaction, checksums, manifest, and admin-only access.
- Public case study based on demo/paper validation only.

Production relevance:

- Platform extends beyond UI.
- Audit/export becomes enterprise-grade evidence.
- Broker layer becomes scalable and testable.

### Phase 5: November 2026 - Billing Interest, Tenant Isolation, Security, Growth

Required features:

- Billing waitlist or paid-beta interest flow.
- Pricing interest tiers: Builder, Team, Research Lab.
- No active payment collection unless Stripe test mode is isolated and disabled by default.
- Subscription model and billing state design.
- Tenant isolation hardening across all user-owned records.
- Security controls: password hashing, secure cookies, CSRF, rate limits, hashed API keys, audit logs, security headers, failed login tracking, session revocation, dependency scans.
- Compliance review workflow and safe language.
- Growth dashboard and evidence export.

Production relevance:

- Commercial validation without crossing legal boundaries.
- Security and tenant isolation become launch blockers.
- Conversion and growth metrics become measurable.

### Phase 6: December 2026 - Public Beta

Required features:

- Public beta landing and onboarding.
- Signup/waitlist capture.
- Paper broker onboarding.
- Docs link.
- Product safety notice.
- Feedback form.
- Admin beta metrics dashboard.
- Public changelog.
- Basic status/incidents page.
- Technical whitepaper.
- Testimonial collection and evidence tracking.

Production relevance:

- Product becomes publicly usable.
- Requires operational readiness, support, privacy controls, and beta governance.

### Phase 7: January 2027 - Drift, Incidents, Status, Enterprise Admin

Required features:

- Model drift detection: feature, prediction, outcome, data quality, news/source credibility, execution/slippage.
- Drift dashboard and API endpoint.
- "Model review required" flag.
- Incident system with categories, severity, status, owner, timeline, export, and postmortem template.
- Public status page with safe incident summaries.
- Enterprise admin area: users, roles, API keys, audit exports, incidents, billing/LOI tracker, retention settings, feature flags, usage metrics.
- Commercial traction tracker for leads, LOIs, pilots, and revenue status.

Production relevance:

- Adds operational maturity and B2B readiness.
- Converts failures into managed incidents.
- Supports enterprise evaluation.

### Phase 8: February 2027 - Reports, Adoption, External Coverage

Required features:

- Three-month paper trading and governance report generator.
- Open-source adoption metrics report.
- Media/blog coverage pack.
- Recommender outreach pack.

Production relevance:

- Produces evidence-grade, redacted reporting.
- Increases public trust and external validation.

### Phase 9: March 2027 - Security, GDPR, Compliance Pack, Pitch

Required features:

- Security hardening pass.
- GDPR/data protection controls.
- Privacy notice.
- Cookie notice where required.
- Data export request.
- Account/workspace deletion request.
- Consent tracking.
- Retention settings.
- Personal data inventory.
- DPIA-lite.
- Compliance/audit pack.
- Pitch deck source content.

Production relevance:

- Data protection becomes productized.
- Enterprise and public beta readiness improves.

### Phase 10: April-May 2027 - Evidence Freeze And Final Demo

Required features:

- Product freeze tag and release notes.
- Stable demo URL checklist.
- Changelog and known limitations.
- Metrics dossier.
- Final demo script.
- Final evidence pack.
- Readiness scorecard.
- Apply-or-delay decision workflow.

Production relevance:

- Stabilizes the product for external review.
- Prevents last-minute unstable feature changes.

## 8. Core Functional Requirements

### 8.1 Authentication

Requirements:

- Support secure signup, login, logout, password reset or passwordless magic link.
- Use modern password hashing if passwords are used.
- Enforce email uniqueness.
- Support account disable and session revocation.
- Track failed login attempts.
- Add login and API rate limiting.
- Store sessions in secure, signed, HTTP-only cookies.
- Use `Secure` and `SameSite=Lax` or stricter in production.
- Support local development without weakening production defaults.

Acceptance criteria:

- Unauthenticated users cannot access protected dashboard, API, exports, admin, or workspace routes.
- Disabled users cannot log in or use existing sessions.
- Failed login attempts generate security events.
- Passwords and API keys are never stored in plaintext.

### 8.2 Workspaces And Access Controls

Requirements:

- Every user belongs to at least one workspace.
- Every user-owned record must include `workspace_id` unless explicitly global.
- Roles: owner, admin, viewer.
- Owner can manage workspace, billing interest, invites, API keys, exports, retention, and feature flags.
- Admin can manage operational resources but not delete owner or change billing owner unless explicitly granted.
- Viewer can read dashboards and reports only.
- Support invite codes for private beta.
- Log every admin action.

Acceptance criteria:

- Two workspaces cannot read each other's decisions, orders, paper positions, backtests, models, API keys, feedback, exports, billing interest, or incidents.
- API keys are scoped to one workspace.
- Audit exports are workspace-scoped.
- Workspace switching changes all dashboard and API query scope.

### 8.3 CRUD Logic

CRUD resources:

- Users.
- Workspaces.
- Workspace members.
- Invites.
- API keys.
- Paper accounts.
- Backtest runs.
- Walk-forward runs.
- Model versions.
- Drift reports.
- Incidents.
- Audit exports.
- Feedback.
- Testimonials.
- Billing interest.
- Leads, LOIs, pilots.
- Feature flags.
- Retention settings.
- Status page components and updates.

Requirements:

- All write operations must validate permissions.
- Soft delete or archive should be preferred where audit integrity matters.
- State-changing actions must be CSRF-protected in web forms.
- All destructive or sensitive actions must create audit events.
- Admin exports must redact personal and secret data.

### 8.4 Paper Broker

Requirements:

- Support `paper` execution mode separate from `shadow`, `demo`, and `live`.
- Simulate cash, positions, fills, slippage, P&L, open/closed trades, and broker order IDs.
- Persist workspace-specific paper account state.
- Provide reset and seed sample capital controls.
- Ensure no eToro API calls occur in paper mode.
- Show paper portfolio in dashboard and API.

Acceptance criteria:

- Insufficient cash blocks paper buy orders.
- Position size and P&L update correctly after buy/sell.
- Reset only affects active workspace.
- Public beta defaults to paper-only.

### 8.5 Backtesting And Walk-Forward Validation

Requirements:

- Run backtests from cached/sample data.
- Show trades, win rate, profit factor, Sharpe, max drawdown, equity curve, assumptions, and config snapshot.
- Support walk-forward runs with train/test windows.
- Store run outputs with `workspace_id`.
- Export Markdown and JSON reports.
- Display legal-safe disclaimer: historical/paper results do not predict future results and are not investment advice.

Acceptance criteria:

- Results are reproducible from stored config snapshot and data references.
- Runs cannot leak across workspaces.
- Exports include date range, input assumptions, metrics, and limitations.

### 8.6 Model Registry And Governance

Requirements:

- Track model name, version, status, artifact path/hash, feature list, training window, validation metrics, holdout metrics, walk-forward metrics, promotion/rejection reason, lineage, and active model status.
- Status values: candidate, active, rejected, archived, review_required.
- Promotion must pass governance gates.
- Rollback must be audited.
- Arbitrary user-uploaded model files are out of scope for MVP.

Acceptance criteria:

- Candidate models cannot become active without governance approval.
- Every train, promote, reject, archive, rollback, and drift review action is audited.
- Severe drift marks active model as review required.

### 8.7 Broker Adapter Abstraction

Requirements:

- Implement broker adapter protocol and registry.
- Required adapters: shadow, paper, eToro.
- Expose capabilities: market order, close position, demo, live, fractional amount, stop loss, take profit, reconciliation.
- Hosted demo must reject live mode.
- Live mode remains gated by environment variable and explicit CLI flag.

Acceptance criteria:

- Every adapter passes contract tests.
- Unsupported capabilities fail safely before order submission.
- No public beta path can trigger live broker execution.

### 8.8 API And SDK

Requirements:

- REST API under `/api/v1`.
- API-key authentication with hashed storage and one-time reveal.
- Endpoints for health, workspace summary, decisions, risk reports, backtests, walk-forward, models, drift, paper portfolio, audit events, audit export metadata, incidents, and status feed.
- API rate limiting by key, workspace, and IP.
- Usage events recorded.
- Python SDK with typed methods and examples.

Acceptance criteria:

- Revoked API keys fail immediately.
- API responses are workspace-scoped.
- API docs do not expose live trading endpoints for beta.

### 8.9 Payments, Billing Logic, And Subscription States

Initial requirement:

- Start with billing waitlist and paid-beta interest.
- Do not charge users until legal/accounting review is complete.
- Optional Stripe test-mode integration can exist only if disabled by default and clearly isolated.

Future billing requirements:

- Billing provider abstraction to reduce vendor lock-in.
- Stripe test mode first, production mode only after review.
- Subscription states:
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
- Entitlements must be derived from subscription state and feature flags, not hardcoded UI checks.
- Store payment processor customer ID, subscription ID, status, current period, cancellation date, and plan ID.
- Do not store raw card data.
- Billing webhooks must be idempotent.
- Invoice/payment events must be audited.

Plan tiers:

- Builder: paper broker, dashboard, basic backtests.
- Team: workspaces, audit exports, API keys.
- Research Lab: model registry, walk-forward reports, compliance exports, advanced governance.

Acceptance criteria:

- Users in `past_due` retain safe read access but lose paid write/export features after grace period.
- `cancelled` users retain data export and account deletion rights.
- Subscription changes are logged and reversible by admin with audit event.
- Webhook retries do not double-apply billing changes.

### 8.10 Feature Flags And A/B Testing

Requirements:

- Workspace-level and global feature flags.
- Flags for public beta, paper broker, API, SDK docs, audit export, billing waitlist, model registry, drift, incident admin, GDPR tools, and experimental UI.
- A/B tests for onboarding, pricing interest, dashboard activation, docs CTA, and waitlist copy.
- Experiment assignment must be stable per user/workspace.
- Experiments must not alter risk controls, legal disclaimers, live-trading gates, or safety notices.

Acceptance criteria:

- Feature disabled means route, API, and UI controls are inaccessible.
- Experiment exposure and conversion events are recorded.
- Admin can disable any experimental feature quickly.

## 9. Data Requirements

### 9.1 Data Integrity

Requirements:

- Use database constraints for foreign keys, uniqueness, timestamps, and valid status values where practical.
- Use migrations or idempotent table creation.
- Use transactions for multi-table writes.
- Use optimistic concurrency or row versioning for sensitive updates where needed.
- Store immutable audit records for security, admin, billing, model, export, and incident events.
- Store checksums for audit exports and model artifacts.

Acceptance criteria:

- Partial writes cannot create orphan records.
- Audit export manifests include row counts and SHA-256 checksums.
- Retried requests do not create duplicate orders, exports, billing events, or incidents.

### 9.2 Idempotency

Required idempotent operations:

- Billing webhooks.
- API order/simulation requests.
- Audit export creation.
- Backtest/walk-forward run creation.
- Model training trigger.
- Paper broker reset/seed.
- Incident detector upserts.
- Invite acceptance.
- Email/notification sends.

Requirements:

- Accept `Idempotency-Key` header for API POST requests where duplicate side effects are possible.
- Store idempotency key, workspace, user/API key, request hash, response hash, status, and expiry.
- Reject same key with different request body.

### 9.3 Data Retention

Default retention policy:

- Auth/security logs: 12 months.
- API usage logs: 12 months aggregated after 90 days.
- Product analytics events: 24 months aggregated or anonymised after 12 months.
- Audit logs: 7 years where required for governance evidence, unless legal review sets a different policy.
- Paper trading records: retained while workspace active, exportable before deletion.
- Feedback/testimonials: retained until withdrawn or deleted.
- Billing interest: retained until consent withdrawal or 24 months of inactivity.
- Incident records: 3 years, high/critical postmortems retained longer if needed.

Requirements:

- Workspace-level retention settings for enterprise users.
- Deletion requests must pseudonymise where immutable audit integrity must be preserved.
- Retention jobs must be logged and reversible only from backups.

### 9.4 GDPR/CCPA

Requirements:

- Privacy notice.
- Cookie notice and consent where non-essential cookies are used.
- Personal data inventory.
- Data export request.
- Delete account/workspace request.
- Consent preferences for marketing, testimonials, analytics, and anonymised evidence use.
- Admin data-access audit.
- DPIA-lite for AI/fintech data risks.
- CCPA-style opt-out of sale/share where applicable. Default: do not sell personal data.
- Pseudonymisation for analytics and evidence exports.

Acceptance criteria:

- User can export their personal data.
- User can request deletion or pseudonymisation.
- Admin access to personal data is audited.
- Public exports never contain personal data unless explicit consent exists.

## 10. Non-Functional Requirements

### 10.1 Security And Secrets Management

Requirements:

- Environment variables for secrets.
- No secrets in Git, logs, audit exports, screenshots, or docs.
- Secret redaction utility used across logs and exports.
- API keys hashed at rest.
- Optional broker credentials must not be stored until encrypted key storage is designed and approved.
- Rotate secrets through documented runbook.
- Separate secrets by environment.
- Dependency scanning in CI.
- Security headers for web app.
- CSRF protection.
- Rate limiting.
- Secure cookies.
- Least-privilege cloud credentials.

Acceptance criteria:

- Secret scanning CI fails if `.env`, SQLite ledgers, audit logs, market cache, private config, or keys are tracked.
- Redaction tests cover API keys, broker keys, tokens, cookies, and passwords.

### 10.2 Scalability

Initial scale targets:

- 100 public beta users.
- 20 active weekly users.
- 200 workspaces.
- 10,000 product events per day.
- 1,000 API requests per day.
- 500 backtest/walk-forward runs per month.

Future scale targets:

- 10,000 users.
- 2,000 active weekly users.
- 10,000 workspaces.
- 1 million product/API events per day.

Requirements:

- Stateless web workers.
- Database connection pooling.
- Background jobs for long-running backtests, exports, reports, and model training.
- Queue abstraction for async work.
- Cache read-heavy dashboard summaries.
- Paginate all list endpoints.
- Use object storage for large exports/artifacts.

### 10.3 Latency Optimization

Targets:

- Dashboard p95 server response under 500 ms for cached summary pages.
- API health p95 under 100 ms.
- API list endpoints p95 under 800 ms.
- Audit export creation accepted under 1 second, processed asynchronously if large.
- Backtest/model training actions return job ID immediately.

Requirements:

- Precompute reporting summaries.
- Add database indexes for `workspace_id`, timestamps, status, and foreign keys.
- Avoid N+1 queries in dashboard.
- Use background workers for heavy tasks.
- Add performance tests for high-volume ledger data.

### 10.4 Load Balancing And Multi-Region Support

Initial requirement:

- Single-region deployment with horizontal web worker scaling behind managed load balancer.
- Sticky sessions not required because sessions are cookie or shared-store based.

Future requirement:

- Multi-region read replicas for docs/API/dashboard reads.
- Active-passive failover for production database.
- Regional data residency review before storing personal data outside primary region.
- Multi-region object storage replication for exports and artifacts.

Acceptance criteria:

- App can run multiple web replicas without session loss.
- Health checks support load balancer routing.
- Deployment docs include scaling and failover plan.

### 10.5 Availability And Disaster Recovery

Targets:

- Public beta uptime target: 99.5%.
- Production target: 99.9% after commercial launch.
- RPO: 24 hours for beta, 1 hour for production.
- RTO: 8 hours for beta, 2 hours for production.

Requirements:

- Automated database backups.
- Backup restore test at least monthly.
- Export artifact backup policy.
- Disaster recovery runbook.
- Kill switch remains available locally and in hosted control plane.
- Incident response integration for backup failures.

### 10.6 Logging, Alerting, And Incident Response

Logging requirements:

- Structured JSON logs.
- Request ID and workspace ID where safe.
- No secrets, tokens, broker credentials, or sensitive personal data.
- Separate audit events from application logs.
- Security, billing, admin, model, export, incident, and API events logged.

Alerting requirements:

- Data ingestion failure.
- Broker adapter failure.
- Paper broker inconsistency.
- Reconciliation drift.
- Model drift medium/high.
- API error spike.
- Login attack/rate limit breach.
- Tenant isolation violation attempt.
- Failed audit export.
- Web app exception spike.
- High order rejection rate.
- Kill switch activation.
- Backup failure.
- Billing webhook failure.

Incident response requirements:

- Incident severity: info, low, medium, high, critical.
- Incident status: open, investigating, resolved, postmortem_required.
- Timeline events and owner.
- Public status page updates for user-facing incidents.
- Postmortem required for high/critical incidents.
- Escalation runbook for security, data integrity, billing, and platform outages.

### 10.7 Rate Limiting

Requirements:

- Login attempts by IP and email.
- Signup and waitlist submission by IP/email.
- API requests by key, workspace, and IP.
- Billing webhook verification and replay protection.
- Export/report generation quotas.
- Backtest/model training quotas by plan.
- Admin override with audit logging.

Acceptance criteria:

- Rate limit responses are safe and do not reveal account existence.
- Rate limit events can create incidents if suspicious.

## 11. CI/CD, Environments, And Rollbacks

### 11.1 Environments

Required environments:

- Local development.
- Test/CI.
- Staging.
- Production beta.
- Production commercial.

Environment rules:

- Separate secrets per environment.
- Production defaults must disable live trading for public users.
- Staging uses sample/sanitized data only.
- Test uses temporary databases and fake providers.
- CI must not require real broker credentials.

### 11.2 CI/CD

CI requirements:

- Install package.
- Run unit tests.
- Run route/API smoke tests.
- Run security/secret scan.
- Run lint/format check if configured.
- Run dependency scan where practical.
- Run docs build after docs site exists.
- Run SDK smoke tests.
- Fail if unsafe runtime files are tracked.

CD requirements:

- Deploy staging first.
- Run smoke tests after deployment.
- Manual approval for production.
- Database migrations reviewed and reversible where possible.
- Record deployment version, commit, migration IDs, and feature flags.

### 11.3 Rollbacks

Requirements:

- One-command rollback to previous app version.
- Database migration rollback or forward-fix plan.
- Feature flags can disable risky features without deploy.
- Billing/provider changes behind flags.
- Public incident/status update if rollback affects users.

Acceptance criteria:

- Failed deployment can be rolled back within RTO.
- Rollback runbook exists and is tested before public beta.

## 12. Instrumentation And Analytics

### 12.1 Product Events

Track:

- Signup started/completed.
- Login.
- Workspace created.
- Invite accepted.
- Dashboard viewed.
- Paper account seeded/reset.
- Paper order simulated.
- Backtest run started/completed.
- Walk-forward run started/completed.
- Model training attempted.
- Model promoted/rejected/rolled back.
- Drift report viewed.
- Audit export generated.
- API key created/revoked.
- API call made.
- Feedback submitted.
- Billing waitlist submitted.
- Pricing tier selected.
- Docs viewed where allowed.
- Testimonial consent granted/withdrawn.

Requirements:

- Events must include timestamp, user ID where allowed, workspace ID, anonymous session ID if applicable, source, plan, feature flag variants, and metadata.
- Do not store investment preferences, portfolio values, or broker credentials in analytics.

### 12.2 Conversion, Retention, And Churn Control

Activation definition:

- User signs up, creates workspace, seeds paper account, and runs at least one paper/backtest workflow.

Retention metrics:

- Day 1, Day 7, Day 30 retention.
- Weekly active users.
- Active workspaces.
- Repeat backtest runs.
- Paper trading usage.
- Audit export usage.
- API key usage.

Conversion funnel:

- Landing view.
- Signup/waitlist.
- Email verified.
- Workspace created.
- Paper account seeded.
- First backtest/paper order.
- First audit export.
- Billing interest submitted.
- Paid beta/LOI/pilot.

Churn signals:

- No login for 14/30 days.
- Failed onboarding.
- No paper/backtest action after signup.
- Repeated failed jobs.
- Cancelled subscription.
- Past-due billing.
- Negative feedback.

Churn controls:

- Onboarding checklist.
- Docs and sample data.
- Support follow-up after failed workflows.
- Admin retention dashboard.
- Feedback prompts after job failures.
- Clear plan limits and upgrade paths.

### 12.3 A/B Testing

Allowed experiments:

- Landing page value proposition.
- Early-access form copy.
- Pricing interest tier presentation.
- Onboarding checklist order.
- Docs CTA placement.

Disallowed experiments:

- Risk thresholds.
- Live-trading gates.
- Legal disclaimers.
- Safety notice visibility.
- Security controls.
- Billing charge behavior without explicit review.

## 13. Support Operations And Escalations

Support channels:

- In-app feedback/bug report.
- Admin feedback dashboard.
- Email support alias.
- GitHub issues for open-source bugs.
- Private support notes for beta users.

Support workflows:

- Triage new issue.
- Categorize: bug, security, data, billing, compliance, docs, product feedback.
- Assign severity.
- Link to incident if operational.
- Reply within SLA.
- Export monthly support themes.

SLA targets for beta:

- Critical security/data issue: acknowledge within 4 hours.
- High platform outage: acknowledge within 8 hours.
- Billing/account issue: acknowledge within 1 business day.
- General feedback: acknowledge within 3 business days.

Escalation paths:

- Security/data leak: owner immediately, incident critical, public/private communication plan.
- Billing/payment failure: owner, provider dashboard, customer notification.
- Tenant isolation issue: owner immediately, disable affected feature, incident critical.
- Broker/live-trading gate issue: kill switch, disable execution features, incident critical.
- Legal/compliance concern: pause copy/feature, mark requires legal review.

## 14. Governance And Compliance

### 14.1 Product Governance

Requirements:

- Product scope matrix.
- Feature legal review tags.
- Release checklist for public-facing copy.
- Approved and blocked language list.
- Model governance policy.
- Risk governance policy.
- Incident response policy.
- Data retention policy.
- Security controls document.
- Compliance/audit pack.

### 14.2 Financial Regulation Boundaries

The product must consistently state:

- Paper/research/governance-first.
- Not investment advice.
- Not a financial promotion.
- No copy trading.
- No managed accounts.
- No live trading for beta users.
- Historical and paper results do not predict future results.
- Legal review is required before regulated features.

Features requiring legal review before launch:

- Live execution for users.
- Broker credential storage.
- Personalised investment recommendations.
- Copy trading.
- Managed accounts.
- Paid trading signals.
- Public financial promotions.
- Crypto-related promotion.
- Revenue sharing tied to trading performance.

## 15. Adtech, Cookies, And Marketing Consent

Requirements:

- Default to privacy-preserving analytics.
- Essential cookies only before consent.
- Cookie banner if analytics, ad pixels, or non-essential cookies are added.
- No adtech pixels on authenticated app pages unless explicitly reviewed.
- Marketing consent separate from product terms.
- Testimonial consent separate from marketing consent.
- Track referral source without collecting sensitive financial data.
- CCPA/GDPR opt-out support for marketing/ad tracking.

Acceptance criteria:

- User can use core product without accepting non-essential cookies.
- Cookie preferences can be changed.
- Consent state is audited.

## 16. Cloud Costs

Cost principles:

- Keep public beta low-cost and observable.
- Use managed services where they reduce operational risk.
- Avoid expensive always-on workers until usage requires them.
- Prefer scheduled/background jobs with quotas.
- Store large exports/artifacts in object storage, not database.
- Add cost tags per environment.

Required dashboards:

- Monthly cloud spend.
- Database size.
- Object storage size.
- Background job counts.
- API request volume.
- Export generation volume.
- Cost per active workspace.

Cost controls:

- Plan-based quotas for backtests, exports, model training, and API calls.
- Admin cost alerts.
- Staging auto-sleep where provider supports it.
- Log retention limits.

## 17. Platform Support

Supported platforms:

- Local development on macOS/Linux.
- Docker.
- Hosted cloud staging.
- Modern desktop browsers: Chrome, Safari, Firefox, Edge.
- Responsive dashboard for tablet/mobile reading, with core workflows optimized for desktop.
- Python 3.11 and 3.12 in CI.

Out of scope initially:

- Native mobile apps.
- Browser extensions.
- Windows-specific local support beyond Docker/Python compatibility.

## 18. Vendor Lock-In Strategy

Known vendors/providers:

- Broker: eToro adapter initially.
- Payments: Stripe test mode likely.
- Hosting: Render/Fly.io/Railway/AWS Lightsail candidate.
- Docs: MkDocs/GitHub Pages.
- Database: SQLite initially, Postgres for hosted production.
- Object storage: provider-neutral S3-compatible preferred.

Requirements:

- Abstract broker adapters.
- Abstract billing provider.
- Keep API/SDK independent of hosting provider.
- Use portable SQL where practical.
- Keep exports in standard formats: JSON, CSV, Markdown, ZIP.
- Document migration path from SQLite to Postgres.
- Do not couple user identity to a single OAuth provider in MVP.

## 19. Documentation Requirements

Required docs:

- README.
- Product vision.
- Architecture.
- Risk governance.
- Model governance.
- Broker and execution.
- Demo trading protocol.
- Legal-safe scope.
- Deployment.
- Security controls.
- Compliance review.
- Data protection/privacy.
- Incident response.
- Status page.
- Enterprise admin.
- API/SDK reference.
- Beta user guide.
- Billing/subscription behavior.
- Audit export guide.
- Disaster recovery.
- Runbooks.
- Changelog.
- Public docs site.

Acceptance criteria:

- Every public feature has user-facing docs.
- Every operational control has an owner-facing runbook.
- Docs avoid investment advice, profit claims, and unsafe financial promotion language.

## 20. Test Coverage

Required test categories:

- Unit tests for risk, broker, paper broker, ledger, model governance, drift, billing state, and redaction.
- Integration tests for auth, workspaces, API, dashboard routes, exports, backtests, model registry, incidents, and retention.
- Security tests for CSRF, rate limits, API key hashing, disabled users, role enforcement, and secret redaction.
- Tenant isolation tests across every workspace-owned resource.
- Idempotency tests for billing webhooks, API writes, exports, incidents, and jobs.
- Migration tests.
- SDK smoke tests.
- CI secret-tracking tests.
- Docs build tests.

Coverage targets:

- MVP dashboard: meaningful route and service coverage.
- Public beta: 80%+ on security, tenant isolation, billing state, and audit/export modules.
- Critical financial governance paths: branch coverage for allow/block decisions.

Launch blockers:

- Failing tenant isolation tests.
- Failing live-trading gate tests.
- Failing secret redaction tests.
- Failing billing idempotency tests.
- Failing auth/access-control tests.

## 21. Launch Readiness Gates

### Private Beta Gate

Must have:

- Auth and workspace isolation.
- Paper broker.
- No live trading for beta users.
- Feedback form.
- Basic usage analytics.
- Admin beta dashboard.
- Security basics.
- Legal-safe copy.
- CI passing.

### Public Beta Gate

Must have:

- Public onboarding.
- Privacy notice.
- Cookie handling if needed.
- Status page.
- Incident response.
- Audit export redaction.
- Rate limiting.
- Feature flags.
- Support workflow.
- Admin metrics export.
- Disaster recovery plan.
- Rollback plan.

### Paid Beta Gate

Must have:

- Legal/accounting review.
- Billing state machine.
- Provider webhook idempotency.
- Entitlement enforcement.
- Refund/cancellation policy.
- Invoice/payment event audit.
- Support escalation workflow.
- No regulated activity scope creep.

### Enterprise Pilot Gate

Must have:

- Strong tenant isolation proof.
- Enterprise admin.
- Audit/compliance pack.
- Data retention settings.
- GDPR controls.
- Incident/postmortem process.
- Security controls documentation.
- Backup/restore test.
- DPA/legal templates reviewed externally.

## 22. Metrics And Success Criteria

### Product Metrics

- 50 to 100 waitlist signups by November 2026.
- 20 private beta accounts by September/November 2026.
- 10 weekly active users by November 2026.
- 10 feedback calls by November 2026.
- 5 testimonials with explicit consent by December 2026.
- 1 paid research beta customer, 2 to 3 LOIs, or 1 to 2 pilots by January 2027 if legally safe.

### Usage Metrics

- Workspaces created.
- Backtests run.
- Walk-forward validations run.
- Paper trades simulated.
- Risk rejections.
- Model training attempts.
- Model promotions/rejections.
- Drift alerts.
- Audit exports generated.
- API keys created.
- API calls.
- Feedback submissions.

### Reliability Metrics

- Uptime.
- Error rate.
- p95 dashboard latency.
- p95 API latency.
- Failed jobs.
- Incident count by severity.
- MTTA and MTTR.
- Backup success rate.
- Restore test result.

### Commercial Metrics

- Billing waitlist submissions.
- Pricing tier interest.
- Paid beta interest by role/company.
- LOIs.
- Pilots.
- Revenue status.
- Churn/cancellation reasons.

## 23. Risks And Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Product copy sounds like investment advice | Regulatory/reputation risk | Compliance review workflow, approved language, legal-safe scope |
| Tenant data leak | Critical trust/security failure | Workspace-scoped schema, tests, access helpers, audit logs |
| Live trading accidentally exposed | Critical financial/regulatory risk | Feature flags, hosted live rejection, env+CLI gates, kill switch tests |
| Billing before legal clarity | Legal/accounting risk | Start with billing interest only, Stripe test mode disabled by default |
| Model promoted incorrectly | User trust/risk issue | Governance gates, audit logs, rollback, drift detection |
| Backtest results overinterpreted | Legal/reputation risk | Disclaimers, methodology, limitations, no return claims |
| Cloud costs grow unexpectedly | Business risk | Quotas, cost dashboard, async job limits |
| Vendor lock-in | Strategic risk | Adapter layers, standard exports, provider-neutral docs |
| Weak incident response | Trust risk | Incident system, status page, runbooks, postmortems |
| Personal data mishandling | GDPR/CCPA risk | Privacy controls, data inventory, deletion/export, consent tracking |

## 24. Open Questions

- Which hosting provider will be used for staging and public beta?
- Will the production database be Postgres from first hosted beta, or SQLite first with a migration path?
- Will authentication use passwords, magic links, or external identity provider?
- Which billing provider will be used after legal/accounting review?
- What analytics provider, if any, will be used while preserving privacy?
- What legal jurisdiction and company structure will apply before paid beta?
- What customer support channel will be official for public beta?
- What external legal review is required before broker credential storage or live execution?

## 25. Immediate Next Actions

1. Create public-safe repository hygiene and documentation foundation.
2. Build read-only dashboard MVP.
3. Add Docker and CI.
4. Add legal-safe scope and demo-only protocol.
5. Add authentication, workspaces, and paper broker.
6. Add tenant isolation tests early and keep them as launch blockers.
7. Add hosted staging with `/healthz`, safe defaults, sample data, and no live trading.
8. Build private beta feedback loop and product instrumentation.
9. Add billing interest only, then implement subscription state machine before any real payments.
10. Treat security, privacy, incident response, and compliance docs as product features, not afterthoughts.
