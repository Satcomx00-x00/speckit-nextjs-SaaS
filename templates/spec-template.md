# Feature Specification: [FEATURE NAME]

**Feature slug**: `[feature-name]`
**Feature flag**: `ff-[feature-name]` (default: OFF)
**Feature branch**: `feat/[feature-name]`
**Created**: [DATE]
**Status**: Draft
**RFC PR**: [link — must be merged before implementation PR is opened]

**Input**: User description: "$ARGUMENTS"

---

## User Stories *(mandatory)*

<!--
  Each story is a binary, independently testable slice.
  Acceptance criteria must be yes/no verifiable — no "should", "ideally", "if possible".
  Prioritize by user value: P1 = blocks everything else, P3 = nice to have.
-->

### Story 1 — [Brief Title] (P1)

**As** [role: owner / admin / member / viewer],
**I want** [action],
**so that** [benefit].

**Why P1**: [explain the value and why this is the most critical slice]

**Primary path**:
1. [step 1]
2. [step 2]
3. [step 3]

**Alternate paths**:
- [alternate: e.g. empty state, pagination end]

**Acceptance criteria** (binary — each must be verifiable yes/no):
- [ ] AC-001: [Given X, when Y, then Z — observable in the UI or API response]
- [ ] AC-002: [Given X, when Y, then Z]
- [ ] AC-003: [Given X, when Y, then Z]

---

### Story 2 — [Brief Title] (P2)

**As** [role],
**I want** [action],
**so that** [benefit].

**Acceptance criteria**:
- [ ] AC-004: [Given X, when Y, then Z]
- [ ] AC-005: [Given X, when Y, then Z]

---

[Add more stories as needed. Each story must be independently deployable and testable.]

---

## Non-Goals *(mandatory)*

What is explicitly out of scope for this feature:

- [Non-goal 1 — e.g. "Real-time collaboration (deferred to P3)"]
- [Non-goal 2 — e.g. "Mobile-native push notifications"]
- [Non-goal 3 — e.g. "Bulk export > 10k rows"]

---

## Edge Cases *(mandatory)*

- Empty state: what happens when [the list is empty / no data exists]?
- Max length: what happens when [a field exceeds its maximum]?
- Timeout: what happens when [the background job takes > N minutes]?
- Offline: what happens when [the client loses connectivity mid-action]?
- Unicode / emoji: what happens with [non-ASCII input in text fields]?
- Concurrent writes: what happens when [two users edit the same resource simultaneously]?
- Quota: what happens when [the org hits its plan limit]?

---

## RBAC Roles Affected

| Role | Can do what |
|---|---|
| owner | [list actions] |
| admin | [list actions] |
| member | [list actions] |
| viewer | [list actions — typically read-only] |
| public | [list actions — typically none] |

---

## Key Entities

- **[Entity 1]**: [what it represents, key attributes, relationships]
- **[Entity 2]**: [what it represents, relationships to other entities]

Tenant scoping: every entity must carry `organizationId` as a non-nullable FK → `organizations.id`.

---

## Functional Requirements

- **FR-001**: System MUST [specific, verifiable capability]
- **FR-002**: System MUST [specific, verifiable capability]
- **FR-003**: System MUST [specific, verifiable capability]

Flag requirements where the spec is unclear:
- **FR-004**: System MUST [NEEDS CLARIFICATION: X not specified — options are A / B / C]

---

## Success Metrics *(mandatory)*

Measurable, time-bound, technology-agnostic:

| Metric | Target | Measurement |
|---|---|---|
| Adoption | ≥ X% of active orgs use the feature within 30 days | analytics event count |
| J7 retention | ≥ Y% of users who try it return within 7 days | cohort analysis |
| J30 retention | ≥ Z% retention at 30 days | cohort analysis |
| p95 latency | < N ms end-to-end on primary mutation | Tempo / Grafana |
| Error rate | < M% on primary procedures | GlitchTip / Loki |

---

## Rollback Thresholds

Revert the feature flag (set to OFF for all orgs) if:

- Error rate > [N]% over a 15-minute window
- p95 latency > [N ms] over a 15-minute window
- [Domain-specific threshold — e.g. "failed job rate > 5%"]

Flag OFF restores previous behavior without a deployment.

---

## Marginal Cost Estimate

| Resource | Per operation | At 10k ops/day | At 100k ops/day |
|---|---|---|---|
| Postgres rows | [+N] | [~Nk rows/day] | [~Nk rows/day] |
| Redis keys | [+N] | negligible | negligible |
| BullMQ / Temporal jobs | [+N] | [~Nk/day] | [~Nk/day] |
| ClickHouse events | [+N] | [~Nk/day] | [~Nk/day] |
| Storage (if files) | [+N bytes] | [~N GB/day] | [~N GB/day] |

---

## GDPR / Privacy Classification

| Data field | Classification | Retention | Basis |
|---|---|---|---|
| [field name] | Personal / Sensitive / Non-personal | [N days / until deletion] | [consent / contract / legitimate interest] |

Data minimization: collect only fields required for the feature. Provide deletion flow if personal data is stored.

---

## Assumptions

- [Assumption about target users — e.g. "Users have stable internet connectivity"]
- [Assumption about scope — e.g. "Mobile support is out of scope for v1"]
- [Dependency — e.g. "Requires the organization plan quota service to be available"]
- [Stack assumption — e.g. "BetterAuth session is available on all authenticated routes"]

---

## Open Questions

1. [Decision needed before implementation — e.g. "Soft-delete or hard-delete?"]
2. [Decision needed — e.g. "Quota: per-org flat limit or per-plan tiered?"]

*(Delete this section if there are none before the RFC is approved.)*
