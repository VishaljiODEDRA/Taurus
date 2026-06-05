# Design UI/UX Brief

## Product

Taurus: Risk-First AI Trading Governance Platform

## Version

Draft v1.0

## Source Documents

- `PRD.md`
- `TRD.md`
- `APP_FLOW.md`
- Roadmap and implementation schedule from `Pasted text.txt`
- Existing platform modules under `src/agent`, `src/etoro_api`, and `src/models`

## 1. Design Objective

Design a production-ready fintech SaaS experience that makes a complex autonomous trading governance system feel trustworthy, disciplined, premium, and usable.

The product must look and feel like serious operational infrastructure, not a hype-driven trading bot. Users should immediately understand that the platform is built for paper trading, risk governance, model governance, auditability, and technical validation.

The UI must reinforce three promises:

- Safety before execution.
- Evidence before confidence.
- Governance before performance.

## 2. Existing Platform UI/UX Analysis

### 2.1 Current Experience

The current platform is primarily CLI-first. It has strong backend capabilities but no dedicated product UI yet.

Current user experience:

- User edits local `.env` and `config/strategy.toml`.
- User runs CLI commands such as `scan`, `run-once`, `backtest`, `walk-forward`, `reconcile`, `monitor`, `kill-switch`, and reports.
- Output is inspected through terminal, SQLite ledger, JSONL logs, and generated reports.
- Safety controls exist technically, especially shadow mode, live gates, and kill switch.
- Existing README explains the system clearly for a technical user.

### 2.2 Current Strengths To Preserve

- Risk-first positioning is already credible.
- Live trading is explicitly gated.
- Local CLI flows are transparent and developer-friendly.
- Ledger, audit logs, backtesting, reconciliation, and reliability reports create a strong foundation for dashboard surfaces.
- Existing tests and architecture make the product feel more serious than a decorative UI would.

### 2.3 Current UX Gaps

- No web dashboard.
- No authenticated user journey.
- No workspace or tenant concept.
- No onboarding.
- No visual model/risk/audit explanation.
- No admin console.
- No billing/waitlist UI.
- No support or incident UX.
- No privacy, cookie, consent, or GDPR self-service UX.
- No public docs-site UI or public beta landing flow.
- No production status page.

### 2.4 Design Implication

The UI should not invent a new story. It should expose the already-strong governance engine with a polished, operator-grade interface. The product should feel like a fintech control room: calm, precise, auditable, and controlled.

## 3. Brand And Experience Principles

### 3.1 Brand Attributes

- Premium but restrained.
- Technical but readable.
- Trustworthy, not theatrical.
- Dense but calm.
- Operational, not promotional.
- Compliance-aware.
- Evidence-led.
- Founder-engineer credible.

### 3.2 Experience Principles

- Lead with current system state, not marketing copy.
- Make risk approvals and rejections visible.
- Make all actions reversible, auditable, or clearly final.
- Show confidence with evidence, not decoration.
- Treat latency and failure states as first-class UX.
- Never hide legal/safety context.
- Keep workflows short for repeat expert users.
- Support beginners with progressive disclosure, not long explanatory pages.

### 3.3 Design Anti-Patterns To Avoid

- Profit-focused visuals.
- Green/red casino-style trading UI.
- "Guaranteed returns" tone.
- Crypto-exchange visual language.
- Oversized hero sections inside authenticated app.
- Decorative gradients/orbs.
- Card-inside-card layouts.
- Sparse dashboards that waste screen space.
- Hidden safety notices.
- UI that suggests live trading is available to public beta users.

## 4. Visual Direction

### 4.1 Overall Look

The app should feel like a premium B2B fintech operations dashboard.

Recommended visual language:

- Light-first interface with optional dark mode later.
- Off-white or very light neutral background.
- White or near-white panels for operational surfaces.
- Subtle borders, not heavy shadows.
- 8px or smaller border radius for cards and panels.
- Dense table-first layouts.
- Compact typography.
- Clear status chips and alert banners.
- Minimal color, used meaningfully.

### 4.2 Color System

Use color as status, not decoration.

Suggested palette roles:

- Background: warm-neutral white or very light grey.
- Text primary: near-black neutral.
- Text secondary: slate/grey.
- Border: cool neutral grey.
- Success/approved: restrained green.
- Warning/review: amber.
- Danger/blocked/critical: red.
- Info/paper mode: blue.
- Governance/model: violet or indigo as accent only.

Rules:

- Do not dominate the UI with one hue family.
- Do not overuse purple/blue gradients.
- Do not use red/green alone without labels or icons.
- Do not use financial "green means profit" as a primary visual idea.

### 4.3 Typography

Requirements:

- Use a professional sans-serif font stack.
- Use tabular numbers for metrics, money, percentages, and counts.
- Keep dashboard headings compact.
- Reserve large display type for public landing/whitepaper pages only.
- Do not scale font size with viewport width.
- Letter spacing should remain normal.

### 4.4 Iconography

Use familiar icons for:

- dashboard,
- shield/risk,
- activity/status,
- database/ledger,
- chart/backtest,
- model/brain or nodes,
- key/API,
- lock/security,
- alert/incident,
- file/export,
- users/workspaces,
- credit card/billing,
- settings,
- help/support.

Use icon buttons for repeated tools with tooltips:

- refresh,
- export,
- filter,
- search,
- copy,
- revoke,
- archive,
- rollback,
- open details.

## 5. Information Architecture

### 5.1 Public Navigation

Public pages:

- Overview.
- Product demo.
- Docs.
- Whitepaper.
- Case studies.
- Pricing interest.
- Public beta signup.
- Status.
- Legal-safe scope.
- Privacy.
- Security.

Public pages must keep the product positioned as paper/research/governance infrastructure.

### 5.2 Authenticated App Navigation

Primary sidebar:

- Overview.
- Decisions.
- Risk.
- Paper Portfolio.
- Backtests.
- Walk-Forward.
- Models.
- Drift.
- Reliability.
- Reconciliation.
- Audit.
- API.
- Reports.
- Feedback.
- Billing.
- Workspace Settings.

Admin sidebar:

- Users.
- Invites.
- Feature Flags.
- Incidents.
- Status.
- Security Events.
- Audit Exports.
- Growth Metrics.
- Billing Interest.
- Leads/LOIs/Pilots.
- Data Retention.
- Privacy Requests.
- Support.

### 5.3 Persistent App Chrome

Top bar:

- Workspace selector.
- Mode badge: `paper`, `shadow`, `demo`, or `live unavailable`.
- Safety badge: `Not investment advice`.
- System health indicator.
- Notifications/incidents.
- User menu.

Left sidebar:

- Main product areas.
- Admin section shown only for permitted roles.

Footer or lower utility area:

- Docs link.
- Status link.
- Privacy/security links.
- Version/build identifier.

## 6. Key Screen Briefs

### 6.1 Public Beta Landing Page

Purpose:

Convert qualified users without unsafe financial claims.

First viewport:

- Product name.
- Literal category headline: "Risk-first AI trading governance for paper trading and model auditability."
- Short supporting copy.
- Primary CTA: Join paper/research beta.
- Secondary CTA: View technical docs.
- Safety line: "Paper/research environment. Not investment advice. No live trading for beta users."

Sections:

- Governance workflow.
- Dashboard screenshots or generated product mockups.
- Paper broker and backtesting.
- Model registry and audit exports.
- API/SDK for builders.
- Legal-safe scope.
- Pricing interest.
- FAQ.

Design:

- Premium technical product page.
- Real product screenshots should replace abstract illustrations as soon as available.
- Avoid hype and performance claims.

### 6.2 Signup/Login

Screens:

- Signup.
- Login.
- Forgot password or magic link.
- Invite code entry.
- Email verification.
- Disabled account state.
- Rate-limited state.

UX requirements:

- Clear but minimal security copy.
- Show privacy and terms links.
- No social login required in MVP.
- Errors must be specific enough to help but not reveal account existence.
- Login failures should feel calm, not alarming.

### 6.3 Onboarding

Purpose:

Move user to first safe value moment.

Checklist:

- Confirm product scope.
- Create/select workspace.
- Seed paper account.
- Load sample data.
- Run first backtest.
- Review risk dashboard.
- Export first audit sample.
- Invite teammate or create API key later.

Design:

- Use compact checklist, progress indicator, and next best action.
- Do not use long educational text.
- Provide "Use sample data" path.
- Display paper-only safety notice.

### 6.4 Overview Dashboard

Purpose:

Answer: "Is the system healthy, safe, and producing auditable decisions?"

Top metrics:

- Current mode.
- System health.
- Last cycle status.
- Kill switch status.
- Open incidents.
- Recent decisions.
- Risk blocks.
- Paper portfolio value.
- Backtests run.
- Active model status.
- Audit export count.

Main panels:

- Latest cycle timeline.
- Risk approval/rejection summary.
- Recent decisions table.
- Paper portfolio snapshot.
- Model registry summary.
- Reconciliation status.
- Incident/status summary.

Design:

- Compact operational dashboard.
- Tables and status panels over decorative cards.
- Status labels must include text and icon.
- Critical warnings must be visible above fold.

### 6.5 Decisions

Purpose:

Show why the agent proposed, approved, rejected, or skipped actions.

Table columns:

- timestamp,
- symbol,
- action,
- confidence,
- score,
- risk approval,
- block reason,
- model version,
- execution mode,
- audit link.

Detail drawer:

- signal inputs,
- chart/news/context features,
- risk gate outcomes,
- committee summary,
- execution simulation,
- final decision,
- audit event chain.

UX requirements:

- Filters by symbol, action, approval, date, model, risk reason.
- Export visible only for permitted roles.
- Explainability should be structured, not long prose.

### 6.6 Risk Dashboard

Purpose:

Make deterministic governance visible and inspectable.

Sections:

- Portfolio exposure.
- Position caps.
- Daily loss halt.
- Drawdown halt.
- Spread/staleness checks.
- Leverage cap.
- No averaging down.
- Stress scenarios.
- VaR/CVaR.
- Recent risk blocks.

Design:

- Use severity indicators.
- Show pass/fail/check states.
- Every block should have a clear reason and linked decision.
- Risk thresholds should be readable but editable only by permitted admin/owner roles.

### 6.7 Paper Portfolio

Purpose:

Make simulated trading safe, realistic, and inspectable.

Sections:

- Paper cash.
- Simulated positions.
- Open/closed trades.
- P&L.
- Simulated fills and slippage.
- Reset/seed controls.

UX requirements:

- Reset requires confirmation.
- Reset action must state it affects paper state only.
- No live broker CTA.
- Paper orders must link to risk checks and audit events.

### 6.8 Backtests And Walk-Forward

Purpose:

Help users validate research without implying future returns.

Backtests screens:

- Run setup.
- Runs list.
- Run detail.
- Export report.

Walk-forward screens:

- Run setup.
- Period list.
- Period detail.
- Metrics comparison.

Metrics:

- trades,
- win rate,
- profit factor,
- Sharpe,
- max drawdown,
- equity curve,
- assumptions,
- config snapshot.

UX requirements:

- Disclaimer visible near run and report actions.
- Long jobs show queued/running/completed/failed states.
- Failed jobs include recovery guidance.
- Export is owner/admin only unless plan allows viewer export.

### 6.9 Model Registry

Purpose:

Make AI governance credible.

Screens:

- Model overview.
- Model detail.
- Training run detail.
- Promotion/rejection history.
- Rollback confirmation.
- Reliability report.
- Drift dashboard.

Model status chips:

- candidate,
- active,
- rejected,
- archived,
- review required.

UX requirements:

- Promotion controls hidden unless user has permission.
- Rollback requires confirmation and reason.
- Severe drift must be visually prominent.
- Arbitrary model upload should not appear in MVP.

### 6.10 Audit And Exports

Purpose:

Enable governance evidence and compliance review.

Screens:

- Audit event list.
- Audit event detail.
- Export builder.
- Export history.
- Export manifest.

Export options:

- JSON.
- CSV.
- Markdown.
- ZIP package.

UX requirements:

- Date range required.
- Workspace scope visible.
- Redaction notice visible.
- Checksum and manifest visible after generation.
- Export job states are clear.

### 6.11 API And SDK

Purpose:

Serve fintech/AI developers.

Screens:

- API overview.
- API key list.
- Create key.
- One-time key reveal.
- Revoke key.
- API usage metrics.
- SDK examples.

UX requirements:

- API keys shown once only.
- Copy button for key.
- Revocation confirmation.
- Rate limit and plan limits visible.
- No live trading endpoints shown to beta users.

### 6.12 Billing And Subscription

Purpose:

Validate commercial interest safely and later support paid beta.

Initial screens:

- Pricing interest.
- Billing waitlist form.
- Admin billing interest dashboard.

Future screens:

- Plan overview.
- Subscription state.
- Usage/quotas.
- Invoice history.
- Payment method through provider-hosted UI.
- Cancellation flow.

Subscription states shown in UI:

- waitlist interest,
- beta free,
- beta paid pending,
- active,
- past due,
- payment failed,
- cancelled,
- suspended,
- comped,
- enterprise invoice pending.

UX requirements:

- Do not sell investment advice, signals, live trading, or copy trading.
- Past-due state should be clear but not hostile.
- Cancelled users keep data export and deletion access.
- Billing errors must include support path.

### 6.13 Admin Console

Purpose:

Support production operation.

Admin areas:

- users,
- workspaces,
- invites,
- roles,
- feature flags,
- incidents,
- status page,
- security events,
- audit exports,
- support tickets,
- privacy requests,
- retention settings,
- billing interest,
- leads/LOIs/pilots,
- growth metrics,
- cloud cost dashboard.

UX requirements:

- Admin area must feel distinct but still part of app.
- Dangerous actions use confirmation dialogs.
- Every admin action shows audit trail.
- Support access to personal data requires reason code.

### 6.14 Status Page

Purpose:

Public trust and operational transparency.

Public sections:

- Web app.
- API.
- Paper broker.
- Backtesting.
- Model registry.
- Audit exports.
- Docs.
- Hosted database.
- Current incidents.
- Maintenance notices.
- Historical incidents.

UX requirements:

- Public-safe incident summaries only.
- No private workspace data.
- No security detail leakage.
- Status labels: operational, degraded, partial outage, major outage.

### 6.15 Privacy And Data Controls

Screens:

- Privacy notice.
- Cookie preferences.
- Consent settings.
- Export my data.
- Request deletion.
- Testimonial consent management.
- Marketing consent.

UX requirements:

- Make privacy controls easy to find.
- Explain pseudonymisation where audit integrity requires retained records.
- Consent choices must be granular.
- Non-essential cookies disabled until consent.

## 7. Interaction Design Requirements

### 7.1 Common Patterns

Use:

- tables for operational records,
- drawers for detail inspection,
- modals for confirmations,
- tabs for detail sections,
- segmented controls for mode/status filters,
- toggles for feature flags,
- checkboxes for consent,
- menus for row actions,
- icon buttons for repeated actions,
- tooltips for unfamiliar icons,
- banners for safety/incidents,
- chips for status and severity.

### 7.2 State Design

Every core surface must define:

- loading,
- empty,
- populated,
- filtered empty,
- error,
- permission denied,
- feature disabled,
- rate limited,
- degraded service,
- incident active,
- export/job queued,
- export/job running,
- export/job failed,
- export/job completed.

### 7.3 Confirmation Patterns

Require confirmation for:

- paper account reset,
- model rollback,
- API key revoke,
- user disable,
- role downgrade/removal,
- feature flag disable/enable in production,
- audit export with personal data risk,
- data deletion/pseudonymisation,
- subscription cancellation,
- incident resolution,
- status page public update.

Confirmation dialogs must state:

- action,
- affected workspace,
- reversibility,
- audit logging,
- next step.

## 8. Production Controls In UX

### 8.1 Authentication And Access UX

UI must show:

- active workspace,
- user role,
- session/account controls,
- disabled state,
- rate-limited state,
- permission-denied state.

Role-sensitive UI:

- Hide unavailable actions.
- Explain unavailable actions when useful.
- Never rely on hidden UI for security.

### 8.2 Data Integrity UX

UI must show:

- job IDs,
- export IDs,
- model version IDs,
- audit event links,
- checksums,
- timestamps,
- source data windows,
- config snapshots.

Purpose:

Users should see that actions are traceable and reproducible.

### 8.3 Scalability And Latency UX

UX requirements:

- Long jobs are async with status.
- Dashboard shows last updated timestamp.
- Large tables paginate and filter.
- Heavy reports use background generation.
- App shows degraded-state banners when services are slow.
- Optimistic UI only where safe and reversible.

### 8.4 Rate Limiting UX

UI must:

- show calm retry messages,
- avoid exposing whether an email/account exists,
- tell API users current limits,
- show quota usage by plan,
- provide upgrade/contact path where appropriate.

### 8.5 Feature Flag UX

For disabled features:

- show nothing for unauthorized users,
- show "not available on this plan" where commercial,
- show "not enabled for this workspace" where beta/admin,
- show "requires legal review" for blocked financial-risk features.

## 9. Observability, Incident, And Support UX

### 9.1 Logging And Audit UX

Audit views must support:

- actor,
- action,
- target,
- workspace,
- timestamp,
- request ID,
- metadata,
- related records.

Security logs must be admin-only.

### 9.2 Alert UX

Alert severity:

- info,
- low,
- medium,
- high,
- critical.

Use:

- banners for active high/critical issues,
- subtle indicators for low/info,
- incident links for operational details,
- public-safe text for status page.

### 9.3 Incident Response UX

Admin incident detail:

- category,
- severity,
- status,
- owner,
- timeline,
- related logs/events,
- affected components,
- affected workspace if applicable,
- next actions,
- postmortem generation.

### 9.4 Support UX

Support entry points:

- feedback button,
- bug report,
- docs search,
- contact support,
- incident follow-up.

Support ticket form:

- category,
- severity,
- message,
- affected feature,
- screenshot optional later,
- consent for support access if needed.

## 10. Compliance, Governance, And Legal-Safe UX

### 10.1 Safety Notices

Persistent notices:

- Public pages: "Paper/research environment. Not investment advice."
- Authenticated app: mode badge and beta safety banner.
- Backtests: "Historical and paper results do not predict future results."
- Billing: "Paid beta interest is for software infrastructure, not investment advice or live trading."
- API docs: "No live trading endpoints for beta users."

### 10.2 Legal Review UX

Features requiring legal review should be marked internally:

- live execution for users,
- broker credential storage,
- personalised recommendations,
- copy trading,
- managed accounts,
- paid signals,
- crypto promotion,
- return claims.

Admin UI should support:

- legal review status,
- owner,
- decision date,
- approved copy,
- blocked copy,
- release checklist.

### 10.3 GDPR/CCPA UX

User controls:

- privacy notice,
- cookie preferences,
- consent settings,
- export my data,
- delete account/request deletion,
- testimonial permission management,
- marketing unsubscribe.

Admin controls:

- privacy request queue,
- retention settings,
- personal data inventory,
- processing activity records,
- data access audit.

## 11. Conversion, Retention, And Churn UX

### 11.1 Conversion Design

Primary conversion events:

- signup,
- workspace creation,
- paper account seed,
- first backtest,
- first paper order,
- first audit export,
- API key creation,
- billing interest.

UX tactics:

- Short onboarding checklist.
- Sample data.
- Clear next action.
- Progress indicators.
- Success summaries.
- Low-friction feedback prompts.

### 11.2 Retention Design

Retention surfaces:

- recent activity.
- saved reports.
- model version history.
- audit export history.
- weekly beta report.
- docs recommendations.
- support follow-up.

### 11.3 Churn Control UX

Churn risk prompts:

- user has not seeded paper account,
- repeated job failures,
- no activity for 14/30 days,
- billing past due,
- negative feedback.

Response:

- show help/docs,
- offer sample workflow,
- prompt feedback,
- create support follow-up,
- show clear billing recovery path.

## 12. Documentation And Developer Experience UX

Docs site should include:

- overview,
- quickstart,
- dashboard guide,
- paper broker guide,
- backtesting,
- walk-forward,
- model registry,
- API reference,
- SDK guide,
- audit exports,
- security,
- privacy,
- legal-safe scope,
- incident/status,
- changelog,
- FAQ.

Developer UX:

- API key creation in app.
- One-time key reveal.
- Copyable code examples.
- SDK quickstart.
- OpenAPI reference.
- Clear rate limits.
- Sandbox/sample workspace examples.

## 13. Responsive And Platform Support

Primary target:

- desktop and laptop web browsers.

Secondary:

- tablet read-only review.
- mobile for status, incidents, approvals, and basic dashboard reading.

Supported browsers:

- Chrome,
- Safari,
- Firefox,
- Edge.

Responsive requirements:

- Tables collapse into stacked rows on small screens.
- Critical status and safety notices remain visible.
- No text overlaps.
- Buttons maintain stable size.
- Charts and metric panels use fixed responsive constraints.
- Admin workflows can be desktop-first.

## 14. A/B Testing UX

Allowed experiments:

- landing headline,
- CTA copy,
- onboarding step order,
- pricing interest layout,
- docs CTA,
- feedback prompt timing.

UX requirements:

- Stable assignment.
- No visible flicker.
- Exposure and conversion events recorded.
- Experiments must not affect risk controls, safety notices, legal disclaimers, security, billing charge logic, or live-trading gates.

## 15. Premium Look And Feel Acceptance Criteria

The product should feel premium when:

- The first authenticated screen shows real system state, not marketing filler.
- Tables, filters, and detail drawers make complex data readable.
- Safety/risk states are visible without feeling alarmist.
- Empty states guide users to sample/paper workflows.
- Admin, billing, support, privacy, and incident areas feel integrated.
- All actions have clear consequences and audit trails.
- Latency, job progress, and failures are handled gracefully.
- Copy sounds measured and technical.
- Visual hierarchy is tight, calm, and consistent.

## 16. Screen Inventory By Roadmap

### July 2026

- Read-only dashboard.
- Decisions.
- Risk.
- Models summary.
- Reliability.
- Reconciliation.
- Audit events.
- Safety banner.

### August 2026

- Signup.
- Login.
- Logout.
- Workspace selector.
- Workspace creation.
- Protected dashboard.
- Hosted demo health page.
- Paper portfolio.
- Early-access form.

### September 2026

- Backtests.
- Backtest detail.
- Walk-forward.
- Walk-forward detail.
- Model registry.
- Model detail.
- Private beta invites.
- Feedback form.
- Beta admin dashboard.

### October 2026

- API keys.
- API docs.
- SDK examples.
- Broker adapter status.
- Audit export builder.
- Export manifest.

### November 2026

- Billing interest.
- Pricing interest.
- Subscription state admin.
- Security controls.
- Tenant isolation admin checks.
- Compliance review.
- Growth dashboard.

### December 2026

- Public beta landing.
- Public onboarding.
- Public changelog.
- Public status page.
- Testimonial collection.
- Whitepaper/docs integration.

### January 2027

- Drift dashboard.
- Incident admin.
- Status management.
- Enterprise admin.
- Security events.
- Data retention settings.
- Commercial traction tracker.

### February-May 2027

- Three-month report.
- Open-source adoption metrics.
- Media/evidence dashboard.
- Privacy/GDPR controls.
- Compliance pack export.
- Final product demo checklist.
- Metrics dossier.

## 17. Design System Requirements

Core components:

- app shell,
- top bar,
- sidebar,
- workspace selector,
- mode badge,
- safety banner,
- status chip,
- severity chip,
- metric tile,
- data table,
- filter bar,
- detail drawer,
- confirmation modal,
- tabs,
- segmented control,
- toggle,
- checkbox,
- select menu,
- tooltip,
- toast,
- empty state,
- job progress state,
- incident banner,
- audit event timeline,
- export manifest panel.

Component requirements:

- Accessible labels.
- Keyboard navigable.
- Clear focus states.
- No layout shift from dynamic labels.
- Consistent spacing.
- Works with long workspace names, model names, and symbols.
- All destructive actions require confirmation.

## 18. Accessibility Requirements

Requirements:

- WCAG 2.1 AA target.
- Keyboard navigation for all actions.
- Visible focus indicators.
- Sufficient contrast.
- Text labels with icons.
- No status conveyed by color alone.
- Form errors associated with fields.
- Tables have clear headers.
- Dialogs trap focus.
- Toasts and alerts announced appropriately.

## 19. Implementation Notes For Future Frontend Build

Recommended frontend approach:

- Start with FastAPI + Jinja2 templates for July dashboard MVP.
- Use server-rendered pages for operational reliability and simplicity.
- Add lightweight JavaScript only for filters, drawers, charts, and async job polling.
- Avoid introducing a heavy SPA until user workflows require it.
- Use a small design token file for colors, spacing, typography, and status states.
- Build components incrementally in `src/agent/web/templates/partials/`.
- Keep UI copy centralized where possible for compliance review.

Performance guidance:

- Paginate tables.
- Cache summary cards.
- Poll async jobs with sensible interval.
- Avoid loading all audit rows at once.
- Use progressive disclosure in detail drawers.

Security guidance:

- CSRF tokens in all state-changing forms.
- No secrets rendered in templates.
- API keys shown once and never again.
- Permission checks in route handlers and services.

## 20. Design Review Checklist

Before shipping each major UI release:

- Does the screen preserve paper/research/governance positioning?
- Are legal/safety notices visible where needed?
- Are all actions role-checked and server-authorized?
- Are empty/loading/error/rate-limited states designed?
- Are long jobs async with progress?
- Are audit trails visible for sensitive actions?
- Are personal data and secrets redacted?
- Does the screen work in desktop and mobile/tablet read views?
- Does the copy avoid investment advice and return claims?
- Are product events instrumented with consent rules?
- Are support and recovery paths available after failure?
- Is the design consistent with the premium fintech operations style?

