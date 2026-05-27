---
description: Validation checklist runner for the Delta-Global stack. Takes a list of items to verify, inspects the codebase or artifacts, and produces a structured pass/fail report. Used by the saas-feature workflow at scope validation, RFC validation, and pre-merge gates. Can also be invoked standalone for ad-hoc compliance checks.
handoffs:
  - label: Fix failing items
    agent: speckit.tasks
    prompt: Generate one fix task per failing checklist item. Order by severity (FAIL before WARN).
  - label: Analyze drift
    agent: speckit.analyze
    prompt: Run a full cross-artifact consistency check to investigate any checklist failures in depth.
  - label: Run audit
    agent: speckit.audit
    prompt: Run the full constitution audit for deeper rule-level analysis of the failing items.
---

## User Input

```text
$ARGUMENTS
```

The argument is a **checklist definition** — a list of items to verify, provided either as:

1. **Inline bullet list**: items passed directly in the argument text (most common — used by the workflow engine)
2. **File reference**: a path to a markdown file containing checklist items (e.g. `.specify/checklists/pre-merge.md`)
3. **Named preset**: one of the built-in presets listed below (e.g. `preset:scope`, `preset:rfc`, `preset:pre-merge`)

If the argument is empty, ask the user for the checklist items before proceeding.

### Built-in presets

| Preset | Contents |
|---|---|
| `preset:scope` | Binary acceptance criteria, measurable metrics, rollback thresholds, GDPR classification |
| `preset:rfc` | Tenant tables, procedure contracts, analytics paths, feature flag, GDPR consistency, hard constraints |
| `preset:pre-merge` | Migration rollback, feature flag OFF, @critical tests green, diff size, Infisical secrets, .env.example |
| `preset:security` | Auth enforcement, input validation, rate limiting, multi-tenant scoping, output sanitization, secrets |
| `preset:observability` | OTel spans, structured logs, analytics events, alert thresholds, Grafana dashboard committed |

---

## Pre-Execution Checks

Check for `.specify/extensions.yml`. If present, look for hooks under `hooks.before_checklist`. Apply standard hook-processing.

---

## Outline

You are running a **validation checklist** against the codebase and design artifacts. Each item resolves to `PASS`, `FAIL`, `WARN`, or `SKIP`.

### 1. Parse the checklist

Extract individual items from `$ARGUMENTS`. Each item is one verifiable statement. Normalize to a canonical form:

```
item = {
  id:        "CL-<N>",
  text:      "<original item text>",
  category:  "<inferred — Schema | DAL | Procedure | Flag | Cache | Security | Observability | Process | Other>",
  blocking:  true  // FAIL on this item blocks the workflow gate; default true unless item says "track" or "warn"
}
```

If a preset is referenced, expand it to its item list before proceeding.

### 2. Resolve artifacts

Determine which files to inspect based on the items. Common resolution paths for the Delta-Global stack:

| Item topic | Inspect |
|---|---|
| Drizzle schema / migration | `packages/db/src/schema/`, `packages/db/drizzle/` |
| Zod schemas | `packages/shared/src/schemas/` |
| tRPC procedures | `apps/api/src/routers/` |
| DAL functions | `apps/api/src/dal/` |
| Services | `apps/api/src/services/` |
| Feature flags | flag service config, procedure guards, page guards |
| Redis cache / invalidation | DAL files, procedure files |
| Temporal workflows | `packages/temporal-workflows/src/` |
| E2E tests / @critical | `apps/web/tests/e2e/`, CI config |
| Env vars / secrets | `apps/*/src/lib/env.ts`, `.env.example`, Infisical config |
| RBAC / auth | procedure files, BetterAuth session usage |
| Migration rollback plan | PR description, migration file comments |
| Diff size | `git diff --stat HEAD` |
| Bun lockfile | `bun.lockb` git status |
| Observability | OTel config, Grafana dashboard files, alert rules |

### 3. Evaluate each item

For each item in the checklist, inspect the resolved artifacts and assign a verdict:

| Verdict | Meaning |
|---|---|
| `PASS ✓` | Evidence found — item satisfied |
| `FAIL ✗` | Evidence contradicts the item or is absent |
| `WARN ⚠` | Item partially satisfied or could not be fully verified |
| `SKIP —` | Not applicable to this feature (document why) |

**Evaluation rules:**

- **Binary criteria** (items with "yes/no", "present/absent", "declared/missing"): must be `PASS` or `FAIL` — no `WARN`.
- **Threshold criteria** (items with `>`, `<`, `%`, ms): `PASS` if measured value is within threshold, `FAIL` if exceeded, `WARN` if unmeasured.
- **Process criteria** (items about PRs, tickets, approvals): `WARN` if cannot be verified from code alone — do not assume `PASS`.
- **Hard constraints** (any item containing "CRITICAL", "never", "must not", "hard constraint"): treat as blocking regardless of the `item.blocking` flag.

**Delta-Global specific evaluation hints:**

| Item pattern | How to verify |
|---|---|
| "organizationId on every tenant table" | Check Drizzle schema files for `organizationId` column |
| "feature flag declared and OFF" | Check flag service + procedure guards + page guards |
| "@critical isolation tests green" | Check `isolation.spec.ts` tagged `@critical` exists and CI is passing |
| "Diff < 600 lines" | Run `git diff --stat HEAD \| tail -1` and parse the number |
| "Bun lockfile committed" | `git status bun.lockb` — must not show as modified/untracked if deps changed |
| "Infisical secrets registered" | Check `.infisical.json` or Infisical config for new env var entries |
| ".env.example updated" | Check `.env.example` contains new env var keys (values can be placeholders) |
| "No raw SQL" | Search for `sql\`` template literals outside migration files |
| "No analytics-db imports" | Search for `@delta-global/analytics-db` in `apps/api` and `apps/web` |
| "No relative cross-workspace imports" | Search for `../../packages` or `../../../apps` patterns |
| "Migration rollback plan documented" | Check PR description or migration file for rollback instructions |
| "Conventional Commit title" | PR title matches `^(feat|fix|refactor|chore|docs|test|perf)(\(.+\))?:` |

### 4. Produce the checklist report

Output to the user in this exact structure:

```
# Checklist Report

**Items**: <total> (pass: <p> · fail: <f> · warn: <w> · skip: <s>)
**Gate status**: PASS ✓  |  FAIL ✗  |  WARN ⚠  (first FAIL on a blocking item = gate FAIL)

---

## Failing items (blocking)

- [CL-<N>] ✗ **<item text>**
  Evidence: <what was found or not found>
  Fix: <one-line remediation>

- [CL-<N>] ✗ ...

---

## Warnings (non-blocking, review required)

- [CL-<N>] ⚠ **<item text>**
  Evidence: <partial evidence or unable to verify>
  Note: <what to manually confirm>

---

## Passing items

- [CL-<N>] ✓ <item text>
- [CL-<N>] ✓ ...

---

## Skipped items

- [CL-<N>] — <item text> — *Reason: <why not applicable>*

---

## Gate verdict

**PASS** — All blocking items satisfied. Proceed to next step.

— or —

**FAIL** — <N> blocking item(s) failed. Resolve before continuing:
1. [CL-<N>] <item text> — <one-line fix>
2. ...
```

### 5. Validation before output

- Every `FAIL` has a concrete evidence statement (not "item not checked").
- Every `PASS` has observed evidence (not assumed).
- `SKIP` always includes a reason.
- Gate verdict is derived strictly from the item verdicts — not from overall impression.
- No invented findings or false positives.

---

## Formatting & Style

- Markdown headings exactly as shown.
- Fix lines are one sentence, actionable.
- Bold item text for failing/warning items only — passing items stay plain.
- Report is read by a developer at a workflow gate — keep it scannable.
- No trailing whitespace.

---

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_checklist`. Apply standard hook-processing.
