---
description: Cross-artifact consistency checker for the Delta-Global stack. Reads spec, plan, RFC, and implementation files then reports drift — orphan tables, missing procedures, uncovered Zod schemas, unguarded cache tags, RBAC gaps, and hard-constraint violations. Produces a structured drift report with severity tiers and a prioritized remediation list.
handoffs:
  - label: Fix drift with tasks
    agent: speckit.tasks
    prompt: Generate fix tasks for every drift item in the analyze report. One task per finding, ordered by severity.
  - label: Re-check after fixes
    agent: speckit.analyze
    prompt: Re-run the consistency check on the same scope to verify all drift items are resolved.
  - label: Audit codebase
    agent: speckit.audit
    prompt: Run the full constitution audit on the implementation files flagged in the drift report.
---

## User Input

```text
$ARGUMENTS
```

The argument describes **what to cross-check**. Examples:

- `"Cross-check the RFC against the implementation for feature post-publishing"` — drift between RFC.md and code
- `"Every table is referenced by at least one DAL or procedure"` — orphan-table scan
- `"Every cache tag has an invalidation site"` — cache consistency scan
- `"Every RBAC entry maps to a procedure"` — permission coverage scan

If the argument is empty, run the **full cross-artifact consistency check** (all layers, all rules).

---

## Pre-Execution Checks

Check for `.specify/extensions.yml`. If present, look for hooks under `hooks.before_analyze`. Apply standard hook-processing: skip disabled hooks, skip hooks with non-empty condition, surface optional as instructions, auto-execute mandatory.

---

## Outline

You are running a **cross-artifact consistency analysis** for the Delta-Global stack. The goal is to surface drift between design artifacts (spec, plan, RFC) and implementation files — not to evaluate code quality (use `/speckit.audit` for that).

### 1. Resolve scope

From `$ARGUMENTS` extract:

- **Feature name** (kebab-case) — if absent, derive from the most recently modified plan or RFC under `.specify/plans/` or `docs/rfcs/`.
- **Layers to check** — default: all. Explicit overrides: `"only RFC"`, `"only cache"`, `"only RBAC"`, etc.
- **Hard-constraint mode** — if the argument mentions "hard constraints", treat any violation as `CRITICAL` and prepend it to the report.

Resolve paths relative to the monorepo root:

| Artifact | Default path |
|---|---|
| Spec / scope | `.specify/specs/<feature>.md` |
| Plan / RFC | `.specify/plans/<feature>.md` or `docs/rfcs/<feature>.md` |
| Drizzle schema | `packages/db/src/schema/<feature>.ts` |
| Zod contracts | `packages/shared/src/schemas/<feature>.ts` |
| DAL | `apps/api/src/dal/<feature>.ts` |
| Services | `apps/api/src/services/<feature>.ts` |
| tRPC router | `apps/api/src/routers/<feature>.ts` |
| Temporal workflows | `packages/temporal-workflows/src/workflows/<feature>.ts` |
| UI page | `apps/web/app/(app)/[workspace]/<feature>/page.tsx` |
| E2E tests | `apps/web/tests/e2e/<feature>/` |

If a file does not exist, note it as **MISSING** in the report but continue.

---

### 2. Run consistency checks

Execute each check group below. For every finding record:

```
finding = {
  id:       "<check-group>.<rule>",
  severity: "CRITICAL | HIGH | MEDIUM | LOW",
  artifact: "<which file/layer the finding is in>",
  message:  "<what is wrong>",
  fix:      "<one-line remediation>"
}
```

#### 2a. Table ↔ DAL / Procedure coverage

For every table declared in the Drizzle schema:
- At least one DAL function queries it → else `HIGH: TABLE_NO_DAL`
- At least one tRPC procedure references it (directly or via DAL) → else `MEDIUM: TABLE_NO_PROCEDURE`
- `organizationId` column present AND used in a `where` clause in every DAL query → else `CRITICAL: MISSING_ORG_SCOPE`

For every DAL function:
- References an existing Drizzle table → else `CRITICAL: DAL_UNKNOWN_TABLE`
- `organizationId` is a required parameter (non-optional) → else `CRITICAL: DAL_ORG_OPTIONAL`
- `import "server-only"` is the first non-comment line → else `HIGH: DAL_MISSING_SERVER_ONLY`

#### 2b. Zod schema ↔ Procedure coverage

For every tRPC procedure in the router:
- A named input Zod schema exists in `packages/shared` → else `HIGH: PROCEDURE_NO_ZOD_INPUT`
- A named output Zod schema exists → else `MEDIUM: PROCEDURE_NO_ZOD_OUTPUT`
- Schema is imported from `@delta-global/shared`, never inlined → else `HIGH: PROCEDURE_INLINE_ZOD`

For every Zod schema in `packages/shared/src/schemas/<feature>.ts`:
- Referenced by at least one procedure or DAL function → else `MEDIUM: ORPHAN_ZOD_SCHEMA`

#### 2c. Cache tag ↔ Invalidation coverage

For every Redis cache key pattern defined in the RFC or DAL:
- A corresponding invalidation call exists in at least one mutation procedure → else `HIGH: CACHE_TAG_NO_INVALIDATION`
- The invalidation uses `DEL` on the correct key prefix → else `MEDIUM: CACHE_WRONG_INVALIDATION`

For every `queryClient.invalidateQueries` call in the UI:
- Matches a server-side cache key pattern → else `MEDIUM: CLIENT_CACHE_KEY_MISMATCH`

#### 2d. RBAC matrix ↔ Procedure enforcement

For every action × role entry in the RFC RBAC matrix:
- A corresponding role check exists in the procedure (`session.member.role`) → else `CRITICAL: RBAC_UNENFORCED`
- Role insufficient → `TRPCError FORBIDDEN` is thrown (not silently ignored) → else `CRITICAL: RBAC_SILENT_PASS`

For every procedure using `orgScopedProcedure`:
- `organizationId` is extracted from the BetterAuth session, NOT from `input` → else `CRITICAL: ORG_ID_FROM_INPUT`

#### 2e. Hard constraint violations

Check each hard constraint defined in the stack. Any violation is `CRITICAL`:

| Constraint | Detection |
|---|---|
| No raw SQL | any `sql\`` template literal in `apps/api` or `packages/db` outside migrations |
| No analytics-db imports | `@delta-global/analytics-db` imported in `apps/api` or `apps/web` |
| organizationId on every tenant table | tables in `packages/db/src/schema/<feature>.ts` lacking `organizationId` column |
| tRPC for internal calls | `fetch('/api/...')` calls inside RSC pages or client components (use SDK caller) |
| Secrets via Infisical | `process.env.*` used directly in app code (outside `env.ts` / `@t3-oss/env-*`) |
| No relative cross-workspace imports | `../../packages/...` or `../../../apps/...` import paths |
| No `z.any` / `z.unknown` / `z.record(z.any)` | pattern match in all Zod schema files |

#### 2f. RFC ↔ implementation completeness

For every section declared in the RFC (Schema / Zod / Procedures / DAL / Services / Feature Flag / Cache / Background Jobs / RBAC / Observability):
- Corresponding implementation file exists and is non-empty → else `HIGH: RFC_SECTION_NOT_IMPLEMENTED`
- No `// TODO:` or `throw new Error('not implemented')` remaining in production paths → else `MEDIUM: TODO_IN_PRODUCTION`

For feature flag `ff-<feature>`:
- Declared in the flag service with `default: false` → else `HIGH: FLAG_NOT_DECLARED`
- Guard present in the tRPC procedure (throws `FORBIDDEN` if flag OFF) → else `HIGH: FLAG_GUARD_MISSING`
- Guard present in the RSC page (redirect if flag OFF) → else `MEDIUM: FLAG_PAGE_GUARD_MISSING`

#### 2g. Type consistency (Drizzle ↔ Zod)

For every field in a Drizzle table:
- Corresponding field in the output Zod DTO schema uses a compatible type → else `HIGH: TYPE_MISMATCH`
- Sensitive fields (`passwordHash`, `token`, `secret`, `apiKey`) are absent from DTO schemas → else `CRITICAL: SENSITIVE_FIELD_IN_DTO`

---

### 3. Produce the drift report

Output to the user in this exact structure:

```
# Cross-Artifact Consistency Report

**Feature**: <feature-name>
**Layers checked**: <list>
**Artifacts found**: <N> / <N expected>
**Total findings**: <total> (critical: <c> · high: <h> · medium: <m> · low: <l>)

---

## CRITICAL — Block merge / deployment

### <finding.id> — <message>
*Artifact*: `<file or layer>`
*Fix*: <one-line remediation>

### <next finding> ...

---

## HIGH — Fix before PR review

### <finding.id> — <message>
...

---

## MEDIUM — Fix before merge

...

---

## LOW — Track, fix in cleanup PR

...

---

## Missing artifacts

The following expected files were not found:
- `<path>` — <which RFC section this should implement>
- ...

---

## All-clear checks

The following check groups passed with zero findings:
- ✓ Table ↔ DAL / Procedure coverage
- ✓ Hard constraint violations
- ... (list only passing groups)

---

## Prioritized remediation

1. <most impactful action> — resolves <N> findings (<ids>)
2. ...
(top 5 only)
```

If there are **zero findings**, output:

```
# Cross-Artifact Consistency Report — Clean ✓

**Feature**: <feature>
All <N> checks passed. No drift detected between RFC and implementation.

Verified: tables ↔ DAL, Zod schemas ↔ procedures, cache ↔ invalidation,
RBAC ↔ enforcement, hard constraints, RFC completeness, type consistency.
```

---

### 4. Validation before output

- Every finding references a real file path or explicitly notes **MISSING**.
- No invented findings — only what was observed in the artifacts.
- Severity assignments follow the table in section 2 exactly — do not upgrade or downgrade.
- If an artifact was not found, mark checks dependent on it as **SKIPPED (artifact missing)**, not as failures.

---

## Formatting & Style

- Use Markdown headings exactly as shown.
- Keep fix lines to one sentence.
- File paths use backtick code spans.
- Report is read by developers triaging before merge — favor scannable bullets.
- No trailing whitespace.

---

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_analyze`. Apply standard hook-processing.
