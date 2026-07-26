# Speckit Upgrade Audit — 2026-07-26

Cross-audit of this spec-kit fork against its main consumer
(`/home/satcom/dev/platform`, 22 shipped specs) and against industry-standard
SaaS development practice (Google SRE PRR, AWS SaaS Lens, OWASP ASVS, upstream
spec-kit evolution, Kiro/BMAD/OpenSpec). Scope agreed with the maintainer:
target = **any Next.js/TypeScript SaaS**, project specifics move into presets;
priority areas = production readiness & ops, security & compliance, SaaS
business concerns, quality/process gates, **performance**.

The core finding, in one sentence: **the kit is strong at *specifying* and
*scaffolding*, but almost every real-world failure in the platform repo comes
from the absence of a closing loop — nothing verifies that what the spec
promised actually exists, works, and stays true after implementation.**

---

## 1. P0 — The kit is currently broken as a product

These block "works with any SaaS" before any new feature does.

### 1.1 Packaging defects (fresh installs cannot get the fork's value)

| Defect | Evidence |
|---|---|
| `presets/nextjs`, `workflows/saas-feature`, `workflows/hotfix`, `workflows/migration-only`, root `commands/`, `templates/agent-context.md` are **not in the wheel** | `pyproject.toml:32-45` force-includes only `workflows/speckit` + `presets/lean` |
| `presets/catalog.json` lists only `lean` → `specify preset add nextjs` cannot resolve | `presets/catalog.json` |
| Root `preset.yml` declares 10 provides but `commands/` has 13 files; the undeclared ones (`speckit.analyze`, `speckit.checklist`, `speckit.feature`, `scaffold.temporal`, `scaffold.trpc`) are **called by `saas-feature` at 5 steps** → installed workflow references commands that were never installed | root `preset.yml` vs `commands/` |
| Root `preset.yml` and `presets/nextjs/preset.yml` share `id: nextjs`, `version: 0.2.0` but ship **divergent bodies** (Delta-Global vs generic) | both files |
| `workflows/catalog.json` mixes fork URLs with upstream `catalog_url` | `workflows/catalog.json` |
| `README.md` is unmodified upstream — the fork is undocumented at its front door | `README.md` |
| No test references `saas-feature`, `hotfix`, `migration-only`, or the `nextjs` preset | `tests/` |
| `commands/speckit.scaffold.trpc.md` is the only fork command missing `handoffs:` frontmatter | that file |

**Fix**: collapse to a **single command layer** = the generic `presets/nextjs`
one; delete or demote the Delta-Global root `commands/` into a
`presets/delta-global` (or an example "company preset" showing how to
specialize). Package everything, register catalogs, add engine tests for the
three SaaS workflows, rewrite README.

### 1.2 Stack lock-in vs "any Next.js/TS SaaS"

Hardcoded, non-configurable today: Bun/Turborepo, `apps/api`+Hono+tRPC v11,
Drizzle-only, BetterAuth, ioredis key shapes, BullMQ+Temporal, ClickHouse,
GlitchTip, ArgoCD+Kustomize, Infisical, `organizationId` as the literal tenancy
column, role set `owner/admin/member/viewer`, French UI strings in generated
code (`scaffold.route`), `@delta-global/*` package names in command bodies
(workflow inputs are overridable, command bodies are not).

**Fix**: introduce **preset variables** resolved at install/run time
(`{{ stack.orm }}`, `{{ tenancy.column }}`, `{{ tenancy.model }}`,
`{{ paths.api }}`, `{{ packages.db }}`, `{{ runtime.pm }}`, `{{ locale }}`…)
with defaults in `preset.yml`, consumed by command bodies and workflow shell
steps. The constitution scan (`speckit.constitution.scan`) already detects most
of these signals — feed its output into the variable store instead of only into
prose.

### 1.3 Tenancy model must be configurable — proven by the platform itself

The kit's single most-enforced invariant (`organizationId` on everything) did
not survive contact with its **only real consumer**: the platform is
owner-scoped with one seeded `org-public`, and its constitution had to be
amended to v2.1.0 *after 19 features shipped* to legalize reality
(`platform/.specify/memory/constitution.md` Sync Impact Report).

**Fix**: make tenancy a first-class preset choice per AWS SaaS Lens models —
`org-scoped | user-scoped | hybrid | single-tenant` — driving the spec RBAC
section, scaffold column names, analyze checks, and the `@critical` isolation
test generation. Ref: https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/

---

## 2. P1 — Close the loop (the platform's failures are all "open loop" failures)

### 2.1 Add `/speckit.verify` — post-implement live verification

Upstream spec-kit's #1 community-requested gap
(https://github.com/github/spec-kit/discussions/1662). Platform evidence that
paper gates don't verify anything:

- Every `checklists/requirements.md` across 22 specs is **16/16 checked, 0
  open** — a rubber stamp. The only evidence-derived checklist (`ux-audit`) is
  0/36 open since June.
- E2E is `workflow_dispatch`-only while CLAUDE.md claims "E2E on main +
  nightly"; the claimed Codecov 70% gate and `knip` gate **do not exist**.
- `specs/023` tasks.md ends with a table literally titled *"Open Findings Not
  Addressed Here"* — five HIGH `/speckit-analyze` findings shipped unowned.
- OTel spans asserted in every plan §Observability; in reality
  auto-instrumentation was dead under Bun (~210 ms cold-start for **zero
  spans**, `platform/fixes.md` A4).

**Design**: `/speckit.verify` runs after implement and produces
`verify-report.md` with evidence per acceptance criterion: build+boot, route
smoke (browser or curl), each spec success-criterion measured or explicitly
`UNVERIFIABLE`, feature-flag key exists in the flag registry, migrations
applied cleanly, spans/metrics actually observed (not asserted), and the CI
gates the constitution claims actually present in workflow files. FAIL blocks
the `ready-for-review` gate. Checklist items must cite evidence
(file path / command output), not just `[x]`.

### 2.2 Add `/speckit.reconcile` (drift + brownfield) — delta specs

Spec drift is upstream criticism #2; OpenSpec's diff-based "delta specs" are
the community's preferred answer; upstream now ships `converge`. Platform
evidence: ADR-0000 pins Biome 1.9/Next 15/Lefthook/Vitest — all false;
CLAUDE.md lists three gates that don't exist; a 983-line hand-maintained
`migration.md` outranked the kit for the repo's biggest change; the
constitution's own "apply 3 template edits" follow-up was never done; spec 020
gates on **ADR-0021 which does not exist**.

**Design**: `/speckit.reconcile` = scan (reuse `scan-repo.sh`) → diff detected
reality vs constitution/ADRs/agent-context/stack-reference → emit a delta
report with proposed doc patches → on approval apply and bump the constitution
Sync Impact Report. Add a `--feature <slug>` mode that diffs one spec against
its implementation (converge-style) and appends remaining work to tasks.md.
Refs: https://codemyspec.com/blog/openspec-vs-spec-kit,
https://github.com/github/spec-kit (converge).

### 2.3 Make gates machine-checkable, or they will be skipped

Platform evidence of decorative gates: the RFC-PR gate is the raw template
placeholder in **9 of 22 specs** ("design PR merged before code" never once
executed); 7 feature flags declared in specs were **never added** to
`FEATURE_FLAG_KEYS` (two features shipped unflagged, including admin-console
v2); Grafana alert rules were authored in-spec and never provisioned; rollback
thresholds exist in every spec and are wired to **nothing** (finding C6).

**Design**: every gate in the three workflows gets a `check:` script hook that
must pass before the human approve is even offered — e.g. `review-rfc` checks
the ADR/RFC file exists and is merged; `ready-for-review` runs
`/speckit.verify`; rollout gates check the flag key is registered and the alert
rules for the spec's rollback thresholds are deployed. The kit's audit engine
gets new rule sections for this (see 2.6).

### 2.4 Harden `migration-only` into expand-contract + data-migration records

Platform evidence: 9 drizzle migrations contain backfill DML with **no
down-path**; one-shot scripts (`cleanup-article-text.ts`,
`schedule-feeds.ts --delete-all`) mutate production data with no spec, no
record of when/where they ran; spec 018 invented its own
`ops/pre-migration-snapshot-dev.json` artifact — one feature, one bespoke
practice; a conditional-GET correctness bug (fixes.md A7) silently dropped
crawl cycles across three specs.

**Design**: encode **expand → dual-write/backfill → verify-consistency →
contract** as explicit phases with flag gates; require a
`migration-record.md` artifact (what ran, where, when, row counts
before/after, snapshot ref, down-path or explicit "irreversible" sign-off);
template the pre-migration snapshot; add a guardrail step that greps generated
SQL for destructive DDL outside a `contract` phase. Refs:
https://launchdarkly.com/blog/3-best-practices-for-zero-downtime-database-migrations/

### 2.5 Performance as a first-class dimension (maintainer priority)

Platform evidence: −97 % payload fix (340.7 KB → 9.1 KB per feed page) found
only by a post-hoc audit; one upvote invalidated the whole feed cache for
every user; a concurrency limiter that limited nothing; Core Web Vitals
"NOT MEASURED"; the regression guards for all of these (fixes.md phase C) were
never built.

**Design**:
- spec template: **Performance Budget** section (p95 per route, payload ceiling
  per list endpoint, CWV targets) with EARS-style testable form;
- plan template: cache invalidation blast-radius analysis (what does one write
  invalidate?), N+1/over-fetch review of every list read;
- tasks template: a perf-gate task (payload-size assertion test, budget check);
- `/speckit.verify`: measure the budget (curl content-length, Lighthouse/CWV
  where a browser is available);
- audit engine: new `PERF.*` rules — bare-table `select(schema.x)` on wide
  tables, cache-tag granularity smells, missing `LIMIT` on list queries.

### 2.6 Extend the audit engine to cover what the kit calls CRITICAL

The 21 regex rules today are TS/Next hygiene only — **nothing enforces
tenancy, RBAC, PII, rate limits, flags, or i18n**, i.e. the concerns the
commands treat as blocking. The platform meanwhile hand-wrote exactly these as
custom CI guards (`guard-admin-dal-isolation.sh`, `i18n-parity.ts`,
`i18n-scan.ts`) — proof of demand.

**Design**: new rule sections, parameterized by preset variables:
`TENANCY.*` (tenant column missing on table/query/cache key, tenant id from
input not session), `RBAC.*` (procedure without role check), `SEC.PII.*`
(sensitive field in log/console/OTel attributes — the platform prints **2FA
OTPs to stdout** today), `FLAG.*` (spec-declared flag absent from registry),
`I18N.*` (hardcoded user-facing strings), `CI.*` (constitution-mandated gate
absent from workflow files — catches the fake Codecov/knip/E2E claims).

### 2.7 EARS-format acceptance criteria

Adopt Kiro's EARS syntax ("WHEN <trigger> THE SYSTEM SHALL <behavior>") for
spec acceptance criteria — testable by construction, edge-case-forcing, and it
gives `/speckit.verify` something mechanical to check. The platform's WCAG
"target" with zero testable ACs is the counter-example. Ref:
https://kiro.dev/docs/specs/

---

## 3. P2 — Conventional SaaS lifecycle workflows the kit lacks

Each validated by both industry practice and a concrete platform gap.

### 3.1 `/speckit.preflight` — Production Readiness Review gate (new workflow phase)

The canonical Google SRE launch checklist as a blocking phase between quality
gates and rollout: SLOs defined + alert rules **deployed** (not authored),
runbook exists and is linked, rollback rehearsed or at least scripted, dashboards
live, capacity/cost estimate revisited, on-call owner named. Platform gap:
8 runbooks exist but no spec references one; whether a feature gets a runbook
is discretionary; alerts never provisioned. Refs:
https://sre.google/sre-book/launch-checklist/

### 3.2 Security: `/speckit.threat-model` + secret-hygiene workflow

- Lightweight STRIDE pass at plan time for features touching auth, money, PII,
  or new external surfaces; map mitigations to OWASP ASVS L2 items; output a
  `threat-model.md` consumed by `preset:security`. Refs:
  https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html
- **Secret-leak response workflow** (detect → revoke → rotate → verify →
  postmortem). Platform evidence this is needed: a real Google OAuth secret
  file handled by appending its filename to `.gitignore`; a checklist opening
  with "the PAT shared in chat is COMPROMISED" with rotation still unticked;
  "rotate every legacy secret" unchecked since May.

### 3.3 Postmortem & retrospective as real templates

`hotfix` conditionally names a postmortem step but there is no template or
storage convention. Add `postmortem.md` (SEV level, timeline, contributing
causes, corrective actions **with owners that become follow-up entries**) and a
lightweight `/speckit.retro` after each `saas-feature` run (BMAD's most
portable idea). Formalize `follow-ups.md` as a first-class kit artifact with
owner + review cadence — the platform invented it (spec 017, 13/17 still open)
because the kit had no home for post-merge debt. Ref:
https://sre.google/sre-book/postmortem-culture/

### 3.4 GDPR/privacy sections must generate tasks, or they're decorative

Every platform spec since 006 has the GDPR classification table; the codebase
has **no export, no deletion, no consent, no retention job**. Fix: the spec's
privacy table feeds task generation — retention field ⇒ retention-job task;
"Personal" classification ⇒ DSAR-export coverage task; deletion ⇒ erasure-path
task + test. Add a DPIA trigger question to `clarify`
(profiling? large-scale sensitive data? monitoring?). Ref:
https://gdpr.eu/data-protection-impact-assessment-template/

### 3.5 Billing & entitlements (the largest absence for a kit named "SaaS")

Zero coverage in kit and platform alike: no plan/quota/entitlement modeling,
no billing-change workflow. Add:
- spec template: **Plan & Entitlement Impact** section (which tiers get this?
  metered? quota? trial behavior?) — `docs/feature-dev-workflow.md` in the
  platform already asks "Quotas par plan définis" and no spec ever answered;
- an `entitlement-check` scaffold pattern + audit rule (mutation without
  entitlement guard);
- a **billing-change workflow**: grandfathering vs migration decision, staged
  comms (90/60/30 d), 5 % legacy-cohort canary, Stripe price-ID mapping record.
  Refs: https://www.zuora.com/guides/saas-pricing-iteration-versioning/,
  https://stripe.com/resources/more/usage-based-pricing-strategy-for-saas

### 3.6 Tenant lifecycle workflow

Onboarding (signup → org provisioning → seeding → activation email) and
offboarding (export → grace → reliable deletion, tied to 3.4 retention) as a
workflow with verify steps. AWS SaaS Lens: onboarding must be one automated
control-plane mechanism. Platform gap: org bootstrap is a 14-phase manual
runbook (`docs/restart-checklist.md`), transactional email is a `console.log`
stub tracked in a 2-line TODO file. Ref:
https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/operate.html

### 3.7 Accessibility & i18n gates

- a11y: promote from constitution prose to **testable spec ACs** (EARS) + an
  axe/Playwright step in quality gates + the four-UI-states check in verify.
  Platform evidence: WCAG 2.2 AA declared, zero testable ACs, and a Critical
  mobile-nav reachability failure found only by post-hoc audit. EAA is in
  force since 2025-06-28 for EU-serving SaaS.
- i18n: kit currently **hardcodes French strings** in scaffolds while the
  platform built real next-intl with CI parity gates. Parameterize locale,
  scaffold `next-intl` message keys instead of literals, adopt the platform's
  parity/no-hardcoded-string checks as kit audit rules.

### 3.8 Release & deprecation

- Release: changelog (Keep a Changelog) + semver + release-notes artifact as
  workflow outputs; the platform's bespoke `release(<app>):` empty-commit
  ritual and manual `PROMOTE` typing are exactly what a templated release
  workflow should replace.
- Deprecation/sunset workflow for features and public APIs (announce →
  migrate → verify zero usage → remove), RFC 8594/9745 headers for public
  APIs. Lower urgency while the API surface is internal tRPC.

---

## 4. P3 — Product layer & process ecosystem

- **Product intake** (Agent-OS pattern): `/speckit.product` maintaining
  `mission.md`, `roadmap.md`, backlog — the platform keeps user stories in
  `Almanach/UserStories.md`, candidate work in `TODO`/`FUTURE.md`, i.e. intake
  has no home in the workflow. Feeds `specify` instead of starting from ad-hoc
  prompts.
- **Experiment workflow**: flags today are release-gates only; add hypothesis,
  primary/guardrail metrics, sample-size pre-registration, SRM check.
- **Spec retrofit command**: template evolved, old specs never updated (specs
  004/007/009 lack GDPR/rollback/metrics sections entirely); a
  `/speckit.spec.upgrade` that diffs a spec against the current template and
  backfills sections.
- **Quick-spec weight dial** (Kiro): a `--quick` variant that skips gates for
  small well-understood changes — the platform's 5 specs that skipped
  plan/tasks show people already do this, ungoverned; give it a sanctioned
  path instead.
- Upstream parity: adopt `taskstoissues` wiring into the fork workflows,
  evaluate upstream v0.10 `--integration` system, hooks, bundles.

---

## 5. Suggested implementation order

| Wave | Items | Rationale |
|---|---|---|
| **0** | §1.1 packaging + layer dedupe, §1.2 preset variables, §1.3 tenancy config, README | Kit must install and be generic before anything else compounds |
| **1** | §2.1 verify, §2.3 machine-checkable gates, §2.7 EARS ACs | Highest-leverage: closes the loop every platform failure traces to |
| **2** | §2.2 reconcile/drift, §2.4 migration hardening, §2.5 performance, §2.6 audit-engine rules | Drift + the two riskiest technical surfaces |
| **3** | §3.1 PRR, §3.2 security, §3.3 postmortem/retro/follow-ups, §3.4 GDPR task-gen | Ops & compliance maturity |
| **4** | §3.5 billing, §3.6 tenant lifecycle, §3.7 a11y+i18n, §3.8 release/deprecation | SaaS business completeness |
| **5** | §4 product layer, experiments, retrofit, quick-spec, upstream parity | Ecosystem polish |

---

*Sources: full inventory of this repo (3 command layers, 4 workflows, 21 audit
rules); audit of `/home/satcom/dev/platform` (22 specs, fixes.md, migration.md,
audit-output/, follow-ups.md, constitution history); web research on upstream
spec-kit discussions #1662/#1686, Kiro, BMAD, OpenSpec, Agent-OS, Google SRE,
AWS SaaS Lens, OWASP ASVS, GDPR/EAA, Stripe/Zuora billing practice.*
