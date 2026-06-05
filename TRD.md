# Technical Requirements Document

## Product

Taurus: Risk-First AI Trading Governance Platform

## Version

Draft v1.0

## Source Inputs

- Roadmap and implementation schedule from `Pasted text.txt`.
- Product requirements in `PRD.md`.
- Current codebase modules under `src/agent`, `src/etoro_api`, and `src/models`.

## 1. Technical Objective

Build the current local risk-first trading agent into a production-ready SaaS platform for paper trading, backtesting, model governance, audit exports, API access, and operational monitoring.

The production platform must preserve the current safety posture:

- AI may score, rank, and explain.
- deterministic risk controls approve or reject,
- public beta users cannot access live execution,
- no investment advice, copy trading, managed accounts, or performance claims.

This TRD defines implementation-level requirements for authentication, payments, billing logic, subscription states, CRUD, access controls, data integrity, scalability, latency, load balancing, logging, alerting, incident response, disaster recovery, data retention, GDPR/CCPA, rate limiting, CI/CD, environments, rollbacks, feature flags, test coverage, instrumentation, conversion, retention, churn control, cloud costs, multi-region readiness, idempotency, support operations, escalations, governance, platform support, adtech/cookies, secrets management, documentation, A/B testing, vendor lock-in, and platform development.

## 2. Target Architecture

### 2.1 Logical Components

The platform must be split into clear technical domains:

- Web app: FastAPI routes, Jinja templates, static assets, auth/session handling.
- API: `/api/v1` JSON endpoints with API-key authentication.
- Core engine: existing trading decision cycle, risk gates, execution simulation, reconciliation, ledger writes.
- Paper broker: workspace-scoped simulated broker and portfolio state.
- Broker adapters: shadow, paper, eToro, and future adapters behind a shared protocol.
- Reporting layer: dashboard summaries, beta metrics, growth reports, audit exports, compliance packs.
- Model governance: training runs, model registry, promotion gates, rollback, reliability, drift detection.
- Billing and entitlements: billing interest, subscription state machine, plan limits, feature access.
- Admin platform: users, workspaces, incidents, billing interest, exports, security events, feature flags.
- Jobs/worker layer: backtests, walk-forward runs, model training, exports, reports, emails, retention jobs.
- Observability layer: logs, metrics, alerts, incidents, status page.
- Documentation platform: MkDocs/docs site, API docs, SDK docs, operational runbooks.

### 2.2 Deployment Shape

Initial hosted beta:

- One web service running FastAPI.
- One worker process for long-running jobs.
- One managed Postgres database for hosted environments.
- SQLite retained for local development and single-user local mode.
- Object storage for audit exports, model artifacts, screenshots, generated reports, and compliance packs.
- Managed HTTPS endpoint.
- Load balancer in front of web workers.
- Background job queue using a simple provider-neutral abstraction.

Future production:

- Horizontally scaled stateless web workers.
- Dedicated worker pools by workload type.
- Postgres primary plus replicas.
- Redis-compatible cache/rate-limit store.
- S3-compatible object storage.
- Multi-region read replicas and active-passive failover.

### 2.3 Environment Profiles

Required environment profiles:

- `local`: SQLite, local state/logs, no external billing, no live execution by default.
- `test`: temporary database, fake broker/payment/email providers, deterministic fixtures.
- `ci`: isolated install, test, lint, secret scan, no credentials.
- `staging`: hosted app, sample data, paper-only, test payment provider disabled by default.
- `production_beta`: hosted app, real users, paper-only, public beta controls.
- `production_commercial`: paid plans only after legal/accounting review.

All environments must load config from environment variables and safe config files. Secrets must never be committed.

## 3. Repository And Platform Development Requirements

### 3.1 Package Layout

Target package additions:

```text
src/agent/web/
  app.py
  auth.py
  sessions.py
  csrf.py
  routes/
  templates/
  static/

src/agent/api/
  v1/
  auth.py
  schemas.py
  rate_limits.py

src/agent/brokers/
  base.py
  registry.py
  shadow.py
  paper.py
  etoro.py

src/agent/platform/
  billing.py
  entitlements.py
  feature_flags.py
  idempotency.py
  analytics.py
  audit_export.py
  incidents.py
  status.py
  retention.py
  privacy.py
  security.py
  support.py

src/agent/jobs/
  queue.py
  workers.py
  tasks.py

sdk/python/
  autotrading_agent_client/
```

### 3.2 Development Standards

Requirements:

- Keep core trading logic out of route handlers.
- All web/API routes must call service functions.
- All service functions must accept explicit `workspace_id` where data is tenant-owned.
- All state-changing operations must write audit events.
- Use structured schemas for API request/response validation.
- Use migrations or idempotent schema creation.
- Prefer provider abstractions for broker, billing, email, analytics, queue, storage, and secrets.
- Preserve local CLI workflows while adding hosted platform features.

## 4. Data Architecture

### 4.1 Database Strategy

Local mode:

- SQLite supported for developer and single-user workflows.
- Existing ledger behavior must remain backward-compatible.

Hosted mode:

- Postgres required before public beta if concurrent users are expected.
- Every tenant-owned table must include `workspace_id`.
- Every table must include `created_at`.
- Mutable business tables should include `updated_at`.
- Sensitive state changes should include `created_by_user_id` or `actor_user_id` where applicable.

### 4.2 Required Core Tables

Identity and tenancy:

- `users`
- `sessions`
- `workspaces`
- `workspace_members`
- `workspace_settings`
- `workspace_invites`
- `roles`

Auth/security:

- `password_credentials` or `magic_links`
- `security_events`
- `failed_login_attempts`
- `api_keys`
- `csrf_tokens` if server-stored

Trading governance:

- `decisions`
- `risk_checks`
- `orders`
- `execution_simulations`
- `paper_accounts`
- `paper_positions`
- `paper_orders`
- `paper_trades`
- `reconciliation_runs`
- `reconciliation_alerts`

Validation/model governance:

- `backtest_runs`
- `walk_forward_runs`
- `model_versions`
- `model_events`
- `reliability_reports`
- `drift_reports`

Platform:

- `audit_events`
- `audit_exports`
- `idempotency_keys`
- `feature_flags`
- `feature_flag_assignments`
- `experiments`
- `experiment_events`
- `product_events`
- `incidents`
- `incident_events`
- `status_components`
- `status_updates`
- `support_tickets`
- `feedback`
- `testimonials`

Commercial:

- `billing_interest`
- `billing_customers`
- `subscriptions`
- `subscription_events`
- `invoices`
- `leads`
- `lois`
- `pilots`

Privacy/compliance:

- `consents`
- `data_export_requests`
- `deletion_requests`
- `retention_policies`
- `admin_data_access_events`
- `processing_activity_records`

### 4.3 Data Integrity Rules

Requirements:

- Foreign keys must be enabled and enforced.
- All workspace-owned rows must reference a valid workspace.
- Unique constraints:
  - user email,
  - workspace slug where used,
  - active API key prefix,
  - idempotency key per workspace and actor,
  - subscription external ID per provider,
  - model version per model name and workspace.
- Use transactions for:
  - signup + default workspace creation,
  - invite acceptance,
  - paper order fill,
  - subscription webhook processing,
  - audit export manifest creation,
  - incident detector upsert,
  - model promotion/rollback.
- Store SHA-256 checksums for export files and model artifacts.
- Store request hashes for idempotent POST operations.

Acceptance criteria:

- No partially created workspace after failed signup.
- No duplicate billing state change from webhook retry.
- No paper order can create negative cash unless explicitly allowed by configuration.
- No audit export can complete without manifest and checksums.

## 5. Authentication Requirements

### 5.1 Authentication Methods

MVP options:

- Email/password with strong password hashing.
- Or passwordless magic link if preferred.

Password requirements:

- Use Argon2id or bcrypt with safe parameters.
- Never log passwords.
- Enforce minimum length.
- Add password reset flow if password auth is used.

Session requirements:

- HTTP-only signed session cookie.
- `Secure=true` in hosted environments.
- `SameSite=Lax` minimum.
- Configurable session TTL.
- Session rotation after login.
- Session revocation on password reset, account disable, and high-risk security event.

Acceptance criteria:

- Protected routes redirect or return 401 when unauthenticated.
- Disabled users cannot authenticate.
- Existing sessions become invalid after account disable.

## 6. Access Control Requirements

### 6.1 RBAC

Roles:

- `owner`
- `admin`
- `viewer`
- `support_operator`
- `platform_admin`

Permission model:

- Permissions must be checked server-side for every route and API endpoint.
- UI hiding is not authorization.
- Admin actions must be audited.
- Support operator access must be scoped and logged.

Minimum permissions:

| Resource | Owner | Admin | Viewer | Support Operator |
| --- | --- | --- | --- | --- |
| Dashboard read | yes | yes | yes | limited |
| Workspace settings | yes | yes | no | no |
| Member management | yes | yes | no | no |
| API keys | yes | yes | no | no |
| Audit exports | yes | yes | read metadata only | limited |
| Billing interest | yes | no/limited | no | no |
| Feature flags | yes | admin if allowed | no | no |
| Incidents | yes | yes | read public-safe only | yes |
| Security events | yes | yes | no | yes |
| Data deletion/export | yes | no/limited | own data only | no |

### 6.2 Tenant Isolation

Requirements:

- Every dashboard query must be scoped by active workspace.
- Every API query must be scoped by API key workspace.
- Every export must be scoped by workspace and date range.
- Background jobs must store and enforce workspace context.
- Admin support access must be audited and reason-coded.

Launch blocker:

- Public beta cannot launch unless automated tests prove no cross-workspace access for decisions, orders, paper positions, backtests, models, audit exports, API keys, feedback, incidents, billing interest, and testimonials.

## 7. CRUD Requirements

Every CRUD module must implement:

- create validation,
- read authorization,
- update authorization,
- delete/archive authorization,
- audit logging,
- workspace scoping,
- pagination for list reads,
- search/filter where needed,
- export where relevant,
- soft delete where audit integrity matters.

Required CRUD modules:

- users,
- workspaces,
- workspace members,
- invites,
- API keys,
- paper accounts,
- backtest runs,
- walk-forward runs,
- model versions,
- drift reports,
- audit exports,
- incidents,
- feedback,
- testimonials,
- billing interest,
- subscriptions,
- leads/LOIs/pilots,
- feature flags,
- retention settings,
- support tickets.

Destructive operations must be either:

- soft delete,
- archive,
- revoke,
- cancel,
- pseudonymise,
- or mark inactive.

Hard deletion is allowed only for non-audit temporary data or privacy workflows where legally safe.

## 8. Billing, Payments, And Subscription State Machine

### 8.1 Billing Scope

Initial implementation:

- Billing waitlist and paid-beta interest only.
- Stripe test mode may be added only behind `BILLING_PROVIDER=stripe_test` and disabled by default.
- No live charging until legal/accounting review.

Future implementation:

- Billing provider abstraction.
- Stripe first provider, but avoid coupling internal state to Stripe-specific concepts.
- Webhook verification.
- Webhook idempotency.
- Plan entitlement checks.

### 8.2 Subscription States

Required states:

- `none`
- `waitlist_interest`
- `trial_pending`
- `trial_active`
- `trial_expired`
- `beta_free`
- `beta_paid_pending`
- `active`
- `past_due`
- `payment_failed`
- `cancelled`
- `suspended`
- `comped`
- `enterprise_invoice_pending`

Allowed transitions must be explicit in code.

Examples:

- `none -> waitlist_interest`
- `waitlist_interest -> beta_free`
- `beta_free -> beta_paid_pending`
- `beta_paid_pending -> active`
- `active -> past_due`
- `past_due -> payment_failed`
- `past_due -> active`
- `active -> cancelled`
- `active -> suspended`
- `suspended -> active`

### 8.3 Entitlements

Entitlements must be derived from:

- subscription state,
- plan tier,
- workspace role,
- feature flags,
- usage quotas.

Plan tiers:

- `builder`: dashboard, paper broker, basic backtests.
- `team`: workspaces, API keys, audit exports.
- `research_lab`: model registry, walk-forward, drift, compliance exports.
- `enterprise`: admin controls, retention settings, SSO-ready design, commercial terms.

Acceptance criteria:

- `past_due` workspaces retain data export and read-only access during grace period.
- `cancelled` workspaces retain legal/privacy export and deletion controls.
- Failed webhooks do not corrupt subscription state.
- Duplicate webhooks do not double-apply changes.

## 9. Feature Flags And A/B Testing

### 9.1 Feature Flags

Required flag scopes:

- global,
- environment,
- workspace,
- user,
- plan tier.

Required flags:

- `public_beta`
- `paper_broker`
- `api_v1`
- `sdk_docs`
- `audit_export`
- `billing_interest`
- `model_registry`
- `walk_forward_ui`
- `drift_detection`
- `incident_admin`
- `status_page`
- `gdpr_tools`
- `enterprise_admin`
- `growth_dashboard`

Requirements:

- Disabled route returns 404 or 403 safely.
- Disabled API feature returns stable error code.
- Flag changes must be audited.
- Live-trading gates must not be controlled only by feature flags.

### 9.2 A/B Testing

Allowed tests:

- landing copy,
- onboarding sequence,
- pricing interest page,
- docs CTA,
- feedback prompts.

Disallowed tests:

- risk thresholds,
- live execution gates,
- disclaimers,
- security controls,
- billing charge behavior.

Experiment requirements:

- Stable assignment per user/workspace.
- Exposure event recorded.
- Conversion event recorded.
- Stop condition and owner recorded.

## 10. API Requirements

### 10.1 API Authentication

Requirements:

- API keys scoped to workspace.
- API key plaintext shown once.
- Store only hash, prefix, last four characters, created timestamp, revoked timestamp.
- Support key revocation.
- Rate limit by key, workspace, and IP.

### 10.2 Required Endpoints

```text
GET  /api/v1/health
GET  /api/v1/workspace
GET  /api/v1/decisions
GET  /api/v1/risk-reports
GET  /api/v1/backtests
POST /api/v1/backtests
GET  /api/v1/walk-forward
POST /api/v1/walk-forward
GET  /api/v1/models
GET  /api/v1/models/{version}
GET  /api/v1/models/drift
GET  /api/v1/paper/portfolio
GET  /api/v1/audit/events
POST /api/v1/audit/exports
GET  /api/v1/audit/exports/{id}
GET  /api/v1/incidents
GET  /api/v1/status
```

Requirements:

- All list endpoints paginated.
- All date filters use ISO 8601.
- All write endpoints support idempotency keys where side effects are possible.
- OpenAPI docs generated.
- SDK examples must not include live trading.

## 11. Idempotency Requirements

Use idempotency for:

- billing webhooks,
- API POST requests,
- backtest creation,
- walk-forward creation,
- model training trigger,
- audit export creation,
- paper broker reset/seed,
- incident detector upsert,
- invite acceptance,
- email sends.

Implementation:

- Table: `idempotency_keys`.
- Columns: `workspace_id`, `actor_type`, `actor_id`, `key`, `request_hash`, `response_hash`, `status`, `expires_at`, `created_at`.
- Same key and same request returns original response.
- Same key and different request returns conflict.
- Expiry defaults to 24 hours for API keys, longer for billing webhooks.

## 12. Rate Limiting Requirements

Required limits:

- Login by IP and email.
- Signup by IP and email.
- Magic link/password reset by email.
- API by API key, workspace, and IP.
- Backtest/model/export jobs by workspace and plan.
- Feedback/waitlist forms by IP and email.
- Billing webhook replay protection.

Implementation:

- Local mode may use in-memory limiter.
- Hosted mode must use shared store such as Redis-compatible backend.
- Rate limit events must be recorded as security/product events.

Acceptance criteria:

- Rate limits do not reveal whether an email exists.
- Suspicious bursts can create incidents.

## 13. Observability: Logging, Metrics, Alerting

### 13.1 Logging

Requirements:

- Structured JSON logs.
- Include `request_id`.
- Include `workspace_id` only where safe.
- Include `user_id` only where needed and permitted.
- Never log passwords, API key plaintext, tokens, broker credentials, cookies, raw card data, or private financial details.
- Apply redaction before writing logs.

Log categories:

- application,
- audit,
- security,
- billing,
- API,
- job,
- broker,
- model,
- incident.

### 13.2 Metrics

Required technical metrics:

- request count,
- response latency,
- error rate,
- job duration,
- queue depth,
- database query latency,
- database size,
- cache hit rate,
- API rate-limit count,
- failed login count,
- export duration,
- backup success/failure,
- incident MTTA/MTTR.

Required product metrics:

- signups,
- workspace creation,
- paper account seeded,
- paper orders simulated,
- backtests run,
- walk-forward runs,
- model training attempts,
- audit exports,
- API key creation,
- feedback submitted,
- billing interest submitted,
- retention and churn indicators.

### 13.3 Alerting

Alerts must cover:

- app error spike,
- API 5xx spike,
- login attack,
- rate limit breach spike,
- tenant isolation violation attempt,
- failed billing webhook,
- failed audit export,
- backup failure,
- queue backlog,
- paper broker inconsistency,
- data ingestion failure,
- broker adapter failure,
- reconciliation drift,
- high order rejection rate,
- model drift medium/high,
- kill switch activation,
- cloud cost threshold breach.

Alert destinations:

- local logs in development,
- email/webhook placeholder in beta,
- incident system in hosted environments.

## 14. Incident Response Requirements

Incident fields:

- `id`
- `workspace_id` nullable for platform-wide incidents
- `category`
- `severity`
- `status`
- `title`
- `description`
- `source`
- `owner`
- `first_seen_at`
- `last_seen_at`
- `resolved_at`
- `related_event_ids`
- `raw_json`

Severity:

- `info`
- `low`
- `medium`
- `high`
- `critical`

Status:

- `open`
- `investigating`
- `resolved`
- `postmortem_required`

Required detectors:

- halted cycles,
- repeated data failures,
- high order rejection rate,
- reconciliation alerts,
- model drift alerts,
- API error spikes,
- login/rate-limit security events,
- paper broker consistency errors,
- failed audit exports,
- kill switch activation,
- backup failure,
- billing webhook failures.

Acceptance criteria:

- Duplicate detector events update existing open incident where appropriate.
- High/critical incidents require postmortem template.
- Public status page never reveals private workspace data, security details, stack traces, or tokens.

## 15. Disaster Recovery Requirements

Targets:

- Beta RPO: 24 hours.
- Beta RTO: 8 hours.
- Production RPO: 1 hour.
- Production RTO: 2 hours.

Requirements:

- Automated database backups.
- Object storage backup/replication plan.
- Monthly restore test.
- Backup failure alert.
- Disaster recovery runbook.
- Export of critical workspace evidence before account deletion.
- Deployment rollback runbook.

Acceptance criteria:

- Restore test result is documented.
- App can be restored into staging from latest backup.
- Recovery procedure includes database, object storage, env vars, DNS, and feature flags.

## 16. Data Retention, GDPR, And CCPA

### 16.1 Data Retention

Default retention:

- Security logs: 12 months.
- API usage logs: 12 months, aggregate after 90 days.
- Product events: 24 months, anonymise after 12 months.
- Audit logs: 7 years unless legal review changes policy.
- Paper trading records: retained while workspace active.
- Feedback/testimonials: until withdrawal or deletion.
- Billing interest: 24 months inactivity or consent withdrawal.
- Incidents: 3 years.

### 16.2 GDPR/CCPA Features

Requirements:

- Privacy notice.
- Cookie notice for non-essential cookies.
- Consent records.
- User data export.
- Account deletion request.
- Workspace deletion request.
- Pseudonymisation where full deletion conflicts with audit integrity.
- Testimonial consent withdrawal.
- Marketing consent withdrawal.
- Admin data access audit.
- Personal data inventory.
- DPIA-lite.
- CCPA opt-out of sale/share; default is no sale of personal data.

Acceptance criteria:

- User can export personal data without admin support.
- User can request deletion/pseudonymisation.
- Admin access to personal data is audited.
- Public evidence exports are redacted by default.

## 17. Security And Secrets Management

Requirements:

- No `.env`, private config, credentials, SQLite ledgers, audit logs, market cache, or private trading records in Git.
- Secret scanning in CI.
- Environment-specific secrets.
- API keys hashed.
- Billing webhook secrets stored only in secret manager/env vars.
- Broker credentials not stored in MVP.
- If broker credentials are later stored, use envelope encryption and legal review first.
- Redaction utility shared by logs, exports, errors, and reports.
- Secure headers:
  - `Content-Security-Policy`,
  - `X-Frame-Options` or CSP frame ancestors,
  - `X-Content-Type-Options`,
  - `Referrer-Policy`,
  - `Permissions-Policy`.
- CSRF protection for forms.
- Safe error pages with no stack traces in production.

Acceptance criteria:

- Secret redaction tests cover keys, tokens, passwords, cookies, broker credentials, and webhook secrets.
- CI fails if unsafe runtime files are tracked.

## 18. Scalability And Latency Requirements

### 18.1 Initial Scale

Beta target:

- 100 public beta users.
- 20 weekly active users.
- 200 workspaces.
- 10,000 product events/day.
- 1,000 API requests/day.
- 500 validation jobs/month.

### 18.2 Performance Targets

- `/healthz`: p95 under 100 ms.
- Cached dashboard pages: p95 under 500 ms.
- API list endpoints: p95 under 800 ms.
- Job creation endpoints: p95 under 1 second.
- Audit export creation request: p95 under 1 second, async processing allowed.

### 18.3 Technical Requirements

- Stateless web workers.
- Background jobs for backtests, walk-forward, model training, audit exports, reports, and emails.
- Index all `workspace_id`, `created_at`, `status`, foreign key, and high-cardinality filter columns.
- Paginate all list endpoints.
- Cache reporting summaries.
- Avoid N+1 queries.
- Store large artifacts in object storage.

## 19. Load Balancing And Multi-Region Support

### 19.1 Load Balancing

Requirements:

- Web app must support multiple replicas behind load balancer.
- No in-memory-only sessions in hosted environments.
- `/healthz` for liveness.
- `/readyz` for readiness after database and dependency checks.
- Graceful shutdown for deployments.

### 19.2 Multi-Region Readiness

Initial:

- Single-region primary.

Future:

- Read replicas for analytics/docs/API reads.
- Active-passive failover.
- Object storage replication.
- Region-aware backups.
- Data residency review before multi-region personal data replication.

Acceptance criteria:

- App can scale to two web replicas without session or job corruption.
- Multi-region plan documented before enterprise launch.

## 20. CI/CD, Rollbacks, And Release Management

### 20.1 CI

CI must run:

- package install,
- unit tests,
- integration tests,
- route/API smoke tests,
- tenant isolation tests,
- secret tracking checks,
- dependency/security scan where practical,
- docs build after docs site exists,
- SDK smoke tests after SDK exists.

### 20.2 CD

Deployment flow:

1. Build immutable artifact.
2. Deploy to staging.
3. Run smoke tests.
4. Run migrations.
5. Verify health/readiness.
6. Manual approval for production.
7. Deploy production.
8. Verify production smoke tests.
9. Record release metadata.

### 20.3 Rollbacks

Requirements:

- App rollback to prior artifact.
- Feature flags for risky feature disable.
- Migration rollback or forward-fix plan.
- Public status update for user-facing incidents.
- Changelog and release notes.

Launch blocker:

- Public beta cannot launch without documented rollback runbook.

## 21. Test Coverage Requirements

Required tests:

- Authentication flow.
- Password/magic link security.
- Sessions and revocation.
- CSRF.
- Rate limiting.
- RBAC.
- Tenant isolation.
- API key hashing/revocation.
- Billing state transitions.
- Billing webhook idempotency.
- Subscription entitlement checks.
- Feature flags.
- A/B assignment stability.
- Paper broker buy/sell/reset/P&L.
- No broker API calls in paper mode.
- Backtest/walk-forward persistence.
- Model promotion/rollback governance.
- Drift detection.
- Audit export redaction/checksum.
- Incident creation/dedup/escalation.
- Data export/deletion/pseudonymisation.
- Retention jobs.
- Secret redaction.
- Rollback/health smoke tests where practical.

Coverage gates:

- Critical governance and security modules require high branch coverage.
- Tenant isolation, live-trading gates, billing idempotency, secret redaction, and auth tests are launch blockers.

## 22. Instrumentation, Conversion, Retention, And Churn

### 22.1 Event Instrumentation

Track events:

- signup started/completed,
- login,
- workspace created,
- invite accepted,
- paper account seeded,
- first paper order,
- first backtest,
- first audit export,
- model registry viewed,
- API key created,
- feedback submitted,
- billing interest submitted,
- testimonial consent,
- subscription changed,
- cancellation/churn event.

Event fields:

- `event_name`
- `user_id` nullable
- `workspace_id` nullable
- `anonymous_id` nullable
- `source`
- `utm_source`
- `feature_variant`
- `plan`
- `created_at`
- `metadata_json`

Do not track investment preferences, broker credentials, private financial account data, or raw portfolio values in analytics.

### 22.2 Funnels

Activation funnel:

1. Landing/docs view.
2. Signup.
3. Email verification or first login.
4. Workspace created.
5. Paper account seeded.
6. Backtest or paper order completed.
7. Audit/export/API feature used.

Billing interest funnel:

1. Pricing page viewed.
2. Tier selected.
3. Billing interest form submitted.
4. Sales/support follow-up.
5. LOI/pilot/paid beta.

### 22.3 Churn Signals

Detect:

- no login after signup,
- no activation event within 7 days,
- no workspace activity in 14/30 days,
- repeated failed jobs,
- cancellation,
- past due subscription,
- negative feedback,
- disabled API keys with no replacement.

Churn controls:

- onboarding checklist,
- sample data,
- failure recovery prompts,
- support follow-up queue,
- product education emails only with consent,
- admin retention dashboard.

## 23. Support Operations And Escalations

### 23.1 Support System

Required features:

- In-app feedback.
- Bug report button.
- Admin support dashboard.
- Support ticket table.
- Category, severity, owner, status, workspace, user, and related incident.
- Export monthly support themes.

Categories:

- product bug,
- security,
- privacy/data,
- billing,
- compliance,
- docs,
- feature request,
- incident follow-up.

### 23.2 Escalation Rules

- Security/data leak: critical incident, owner notified immediately, affected features disabled.
- Tenant isolation issue: critical incident, disable affected routes/exports/API.
- Live execution exposure: critical incident, kill switch, disable execution features.
- Billing failure: high incident if charges affected, notify users where required.
- Backup failure: high incident if unresolved after retry.
- Compliance/legal concern: pause copy/feature and mark legal review required.

Beta support SLA:

- Critical: acknowledge within 4 hours.
- High: acknowledge within 8 hours.
- Billing/account: acknowledge within 1 business day.
- General feedback: acknowledge within 3 business days.

## 24. Governance Requirements

Technical governance documents:

- architecture,
- risk governance,
- model governance,
- broker execution boundaries,
- legal-safe scope,
- compliance review,
- security controls,
- data protection,
- incident response,
- disaster recovery,
- retention policy,
- audit export guide,
- billing/subscription behavior,
- API/SDK reference.

Governance controls:

- Release checklist.
- Marketing copy review.
- Feature legal review tags.
- Admin audit events.
- Model promotion gates.
- Drift review gates.
- Audit export checksums.
- Public beta safety notice.

Features requiring legal review:

- live execution for users,
- broker credential storage,
- personalised recommendations,
- copy trading,
- managed accounts,
- paid trading signals,
- crypto promotion,
- return claims,
- financial promotions.

## 25. Adtech, Cookies, And Consent

Requirements:

- Essential cookies only by default.
- Cookie notice if analytics, ad pixels, session replay, or marketing cookies are added.
- No adtech pixels in authenticated app without explicit review.
- Analytics must be privacy-preserving.
- Marketing consent separate from terms.
- Testimonial consent separate from marketing consent.
- User can change consent preferences.
- Consent changes audited.

Acceptance criteria:

- Product works without non-essential cookies.
- No personal data is sent to adtech providers without consent and review.

## 26. Cloud Costs And Quotas

Cost tracking:

- monthly spend by environment,
- database size,
- object storage size,
- logs volume,
- job counts,
- API usage,
- cost per active workspace,
- cost per audit export,
- cost per model/backtest job.

Quotas:

- backtests per workspace per month,
- walk-forward runs,
- model training attempts,
- audit exports,
- API requests,
- report generation,
- storage usage.

Alerts:

- monthly budget threshold,
- unusual job spike,
- object storage growth,
- log volume spike,
- database growth spike.

## 27. Platform Support

Supported:

- macOS/Linux local development.
- Docker.
- Hosted cloud deployment.
- Python 3.11 and 3.12.
- Modern browsers: Chrome, Safari, Firefox, Edge.
- Desktop-first dashboard with responsive read-only views.

Not required initially:

- Native mobile app.
- Browser extension.
- Windows-specific support outside Docker/Python compatibility.

## 28. Vendor Lock-In Controls

Abstractions required:

- broker provider,
- billing provider,
- email provider,
- queue provider,
- storage provider,
- analytics provider,
- secret manager,
- database migration path.

Standards:

- JSON, CSV, Markdown, ZIP exports.
- OpenAPI for API.
- Python SDK generated or manually maintained from stable API contracts.
- S3-compatible storage where practical.
- Postgres-compatible SQL for hosted production.

Exit requirements:

- Document how to migrate from SQLite to Postgres.
- Document how to switch billing provider.
- Document how to switch hosting provider.
- Document how to export all workspace data.

## 29. Documentation Requirements

Technical docs must include:

- local setup,
- Docker setup,
- hosted deployment,
- environment variables,
- database schema,
- migration process,
- API reference,
- SDK guide,
- auth/session design,
- billing/subscription state machine,
- feature flags,
- background jobs,
- observability,
- incident response,
- disaster recovery,
- data protection,
- security controls,
- support operations,
- release and rollback runbook.

Docs acceptance:

- Every production feature has operator documentation.
- Every public feature has user documentation.
- No docs contain secrets, private ledgers, account IDs, private financial data, or investment advice.

## 30. Timeline-Aligned Engineering Milestones

June 2026:

- repository hygiene,
- public-safe docs,
- architecture and governance docs,
- demo-only protocol.

July 2026:

- read-only dashboard,
- Docker,
- CI,
- legal-safe scope.

August 2026:

- auth,
- workspaces,
- hosted staging,
- paper broker,
- early-user collection.

September 2026:

- backtest UI,
- walk-forward UI,
- model registry,
- docs site,
- private beta support.

October 2026:

- API v1,
- Python SDK,
- broker adapter abstraction,
- audit exports.

November 2026:

- billing interest,
- subscription state machine,
- tenant isolation hardening,
- security controls,
- compliance workflow,
- growth dashboard.

December 2026:

- public beta,
- status/incidents page,
- changelog,
- testimonials,
- whitepaper.

January 2027:

- drift detection,
- incident management,
- public status page,
- enterprise admin,
- commercial traction tracker.

February 2027:

- three-month paper trading report,
- open-source adoption metrics,
- media/recommender evidence packs.

March 2027:

- security hardening,
- GDPR/CCPA controls,
- audit/compliance pack,
- pitch deck source.

April-May 2027:

- product freeze,
- metrics dossier,
- final demo,
- evidence pack,
- readiness scorecard.

## 31. Production Readiness Gates

Private beta gate:

- auth and workspace isolation implemented,
- paper broker complete,
- live trading disabled for beta,
- basic security controls,
- CI passing,
- feedback and product events,
- legal-safe copy.

Public beta gate:

- rate limiting,
- incident system,
- status page,
- audit export redaction,
- privacy notice,
- feature flags,
- support workflow,
- backup/restore runbook,
- rollback runbook.

Paid beta gate:

- legal/accounting review,
- billing state machine,
- webhook idempotency,
- entitlement checks,
- support escalation,
- refund/cancellation policy,
- no regulated activity scope creep.

Enterprise pilot gate:

- tenant isolation proof,
- enterprise admin,
- audit/compliance pack,
- data retention controls,
- GDPR/CCPA workflows,
- incident/postmortem process,
- backup restore test,
- commercial tracking.

## 32. Open Technical Decisions

- Use password auth or passwordless magic links?
- Move hosted beta to Postgres immediately or start hosted SQLite with migration plan?
- Which queue backend should be used first?
- Which object storage provider should be used?
- Which analytics provider can satisfy privacy requirements?
- Which hosting provider will be primary?
- Which billing provider will be used after review?
- When, if ever, should encrypted broker credential storage be introduced?
- What support channel becomes official for public beta?

