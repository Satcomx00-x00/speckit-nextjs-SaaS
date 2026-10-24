# Feature Specification: [FEATURE NAME]

**Feature slug**: `[feature-name]`
**Feature flag**: `[feature-name]` (default: OFF) — plain kebab-case, no `ff-` prefix; a **capability** flag in the DB-backed system (ADR-0015), never a gate on whether a surface serves at all. Or: `none — [reason]`.
**Feature branch**: `feat/[feature-name]-[short-id]`
**Created**: [DATE]
**Status**: Draft
**Verified**: not yet — [later: what automation verified (which suites, on what DB) vs what a person clicked through]
**ADR**: [none — no trigger (no pinned version/convention change, no new API surface, no new external service, no new store) | ADR-NNNN required: reason]
**Research brief**: [docs/research/<date>-<slug>/brief.md | none]

**Input**: User description: "$ARGUMENTS"

---

## Context

<!--
  What exists today (with file:line references), why it is not enough, and the
  one invariant this spec exists to protect. Measured facts beat assumptions:
  "measured <date> on <env>: N rows / N ms".
-->

---

## Clarifications

<!-- Filled by /speckit.clarify. One sub-heading per session, Q → A, dated. Never rewrite an earlier answer — amend it with a date. -->

---

## User Stories *(mandatory)*

<!--
  Each story is an independently testable, independently shippable slice.
  P1 = the MVP; later stories must not be needed for P1 to deliver value.
  Roles are the REAL ones: reader (any signed-in user), sector/resource owner,
  org owner|admin|member (only if org-scoped), platform admin (user.role = "admin").
  There is no "viewer" role.

  Acceptance criteria: AC-### numbered GLOBALLY across stories, binary (yes/no),
  written in EARS ("WHEN <trigger> THE SYSTEM SHALL <observable result>",
  "IF <failure> THEN THE SYSTEM SHALL …") or Given/When/Then. Banned words:
  should, ideally, if possible, fast, intuitive. Every IF-THEN criterion is a
  failure case someone will actually trigger in a test.
-->

### Story 1 — [Brief Title] (P1) 🎯 MVP

**As** [real role],
**I want** [action],
**so that** [benefit].

**Why P1**: [the value, and why this is the smallest slice worth shipping]

**Primary path**:
1. [step]
2. [step]

**Alternate paths**:
- [empty state, last page, flag OFF, not the owner, …]

**Acceptance criteria**:
- [ ] AC-001: WHEN [trigger] THE SYSTEM SHALL [observable result in the UI or GraphQL response]
- [ ] AC-002: IF [a caller who is not the owner calls `mutationName`] THEN THE SYSTEM SHALL [return `FORBIDDEN` and change nothing]
- [ ] AC-003: WHILE the flag `[feature-name]` is OFF THE SYSTEM SHALL [behave exactly as today]

---

### Story 2 — [Brief Title] (P2)

**As** [role], **I want** [action], **so that** [benefit].

**Acceptance criteria**:
- [ ] AC-004: …

---

## Non-Goals *(mandatory)*

- [explicitly out of scope, with "deferred to …" where it applies]

---

## Edge Cases *(mandatory)*

- Empty state / first use
- Max length, Unicode, emoji, RTL text
- Pagination boundary and ties (an `id` tiebreak is required)
- Concurrent edits / double submit / replayed request
- A dependency is down: Redis, Temporal, OpenRouter, Stripe, a source site — the feature degrades how?
- Flag flipped OFF while a user is mid-flow
- Sign-out then sign-in as another account in the same tab (no state may leak)
- Plan limit reached / subscription lapsed (if entitlement-gated)

---

## Manual Verification

<!--
  The UI criteria a PERSON must click through before Status can say "Verified".
  List them by AC id. /speckit.verify records automated evidence; it cannot tick these.
-->

| AC | What to click | Expected | Done by / date |
|---|---|---|---|

---

## RBAC Roles Affected

**Tenancy model**: owner-scoped (`owner_id`, scope key from the session) | org-scoped (`organizationId`) — declare one (Constitution IV). The scope key never comes from input.

| Role | Can do what | GraphQL directive |
|---|---|---|
| Reader (signed-in) | | `@public` / `@auth(role: MEMBER)` |
| Resource owner | | `@selfOnly` + ownership predicate |
| Platform admin | | `@auth(role: ADMIN)` + `@audited(action: "…")` |
| Anonymous | nothing on `/graphql` (ADR-0027) | — |

---

## Key Entities

- **[Entity]**: what it represents, key attributes, relationships, who owns a row.

---

## Functional Requirements

<!-- Group by concern (Data & authorization / Read path / Write path / Pipeline / UI / GraphQL surface). FR-### ids; amendments are dated inline: "FR-007a (amended 2026-10-11): …". -->

### Data & authorization
- **FR-001**: The system MUST …

### GraphQL surface
- **FR-0xx**: Every new field MUST carry `@public`, `@auth` or `@selfOnly`; every admin mutation MUST carry `@audited` with `reason` as a top-level argument.

### UI
- **FR-0xx**: All user-facing strings MUST come from `apps/web/messages/{{ var.default_locale }}.json` with parity in {{ var.locales }}.
- **FR-0xx**: The UI MUST meet WCAG 2.2 AA (labels, focus-visible, keyboard paths, 44×44 px targets, AA contrast via design tokens).

[Mark anything undecided as **[NEEDS CLARIFICATION: question — options A / B / C]**.]

---

## Kill-switch Strategy

- Flag OFF restores today's behaviour **exactly** — what guarantees that? (no materialised state that survives OFF, read-side predicates, …)
- What a flag cannot undo (written rows, sent emails, Stripe objects) and how each is handled.
- Toggle path: admin `setFeatureFlag` (`@audited`, reason required), per environment; propagation ≤ 3 s (Redis cache TTL).

---

## Performance Budget

| Surface | Budget | Measured how |
|---|---|---|
| GraphQL operation `[name]` p95 | < [N] ms | ClickHouse traces in Grafana |
| List payload per page | < [N] KB | response size in a test |
| Route LCP / INP / CLS | ≤ 2.5 s / ≤ 200 ms / ≤ 0.1 | web vitals |
| Web bundle | within `perf:budget` | CI `web-bundle-budget` |

---

## Success Metrics *(mandatory)*

| Metric | Target | Measurement (KPI in `kpi_daily`, ADR-0025, or a Grafana query) |
|---|---|---|

---

## Rollback Thresholds

Flag OFF (or pin back with `ship.py promote --to <previous>`) if, over 15 min in production:

- error rate on `[operation]` > [N] %
- p95 of `[operation]` > [N] ms
- [domain signal — e.g. "Temporal workflow failure rate > 5 %"]

Each threshold becomes an alert rule in `platform-infra` `charts/grafana/alerting/[NNN]-[feature-name].json`.

---

## Marginal Cost Estimate

<!-- Use measured volumes (CLAUDE.md / latest spec measurements), say which. -->

| Resource | Per operation | Today's volume | At 10× |
|---|---|---|---|
| Postgres rows | | | |
| Redis keys | | | |
| Temporal executions | | | |
| OpenRouter calls (tokens, $) | | | |
| ClickHouse events | 0 unless written by workers/analytics jobs | | |

---

## Plan & Entitlement Impact

- Which tiers get it (Free / Basic / Pro)? Defined in `packages/shared/src/schemas/billing.ts` and nowhere else.
- Metered / quota? Values set by an admin, not hard-coded.
- Behaviour on downgrade, lapse, trial end.
- Or: "No entitlement impact — available to every signed-in user."

---

## GDPR / Privacy Classification

| Data field | Classification | Retention (ADR-0034) | Lawful basis | Export / erasure path |
|---|---|---|---|---|

DPIA trigger? (profiling, large-scale processing, systematic monitoring) — yes/no and why.

---

## Assumptions

- [assumption — and how it will be checked]

---

## Open Questions

1. Q1: [decision needed before planning]
