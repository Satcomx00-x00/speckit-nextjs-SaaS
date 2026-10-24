---
description: Delta-Global constitution drift scan. Scans the platform (package.json scripts, tsconfig, Biome, depcruise, CI workflows, pre-commit hooks, ADRs, CLAUDE.md, recent specs) against the existing constitution and proposes a versioned AMENDMENT — semver bump plus a new Sync Impact Report whose every ✅ is verified — never a rewrite. Creates a constitution from scratch only when none exists.
handoffs:
  - label: Refine the amendment interactively
    agent: speckit.constitution
    prompt: Refine the proposed amendment. Adjust wording, scope or version bump based on…
  - label: Sync agent context files
    agent: speckit.docs.sync
    prompt: Propagate the amended constitution to CLAUDE.md and AGENTS.md.
---

## User Input

```text
$ARGUMENTS
```

Optional context: a principle to focus on ("only Principle III"), a decision
already taken ("ADR-0036 accepted"), `--dry-run` (report only, write
nothing), `--apply` (write the amendment as PROPOSED without asking).

## Pre-Execution Checks

Check for `.specify/extensions.yml`. If present, look for hooks under
`hooks.before_constitution` and apply standard hook-processing.

## Ground rules

- **Amend, never overwrite.** `.specify/memory/constitution.md` is a governed
  document (v3.x, five Sync Impact Reports at the top, newest first). Existing
  principles, wording and history stay unless the amendment explicitly changes
  them. Previous Sync Impact Reports are never edited.
- **A ✅ is a verified fact.** The v3.1.1 report recorded the lesson: two
  follow-ups claimed "landed" had never been made. Every dependent-artifact
  line you mark ✅ must cite the file and the line you read that proves it;
  otherwise mark it ⚠ (pending, with what remains) or ⃠ (deliberately not
  changed — historical record).
- **Evidence over intent.** A rule the constitution states but nothing
  enforces is reported as a gap, not assumed true. A practice the code follows
  but the constitution does not state is a candidate addition, not a violation.
- **Precedence**: constitution → `docs/adr/` (ADR-0000 first) → `CLAUDE.md` →
  `.specify/presets/delta-global/CONVENTIONS.md`. A disagreement between them
  is itself a finding.

## Outline

### 1. Load the current constitution

Read `.specify/memory/constitution.md`: version, ratified/last-amended dates,
principles I–VI with their MUSTs, Technology Stack tables, Development
Workflow, Governance, and the most recent Sync Impact Report (its ⚠ items and
Deferred TODOs are the first things to re-check).

If the file does not exist, switch to **bootstrap mode**: draft v1.0.0 from
the scan using `.specify/templates/constitution-template.md` and the
conventions file, mark it PROPOSED, and skip to step 6.

### 2. Scan the repository

Run the scan script if installed (`.specify/scripts/bash/scan-repo.sh --json`,
or the PowerShell equivalent) for the inventory, then collect directly:

| Evidence | Where |
|---|---|
| Scripts & gates | root `package.json` scripts (`check:*`, `typecheck`, `test`, `depcruise`), `turbo.json` task deps |
| Compiler | `tsconfig.base.json` flags |
| Lint | `biome.json` (rules on/off) |
| Dependency rules | `dependency-cruiser.config.cjs` rule names |
| CI reality | `.github/workflows/ci.yml`, `e2e.yml`, `release.yml`, `gitleaks.yml` — which commands run, on which triggers, with which thresholds (`diff-cover --fail-under`) |
| Hooks | `.pre-commit-config.yaml` (stage per hook), `commitlint.config.ts` |
| Decisions | `docs/adr/*.md` titles + Status lines; app ADRs under `apps/*/docs/adr/` |
| Agent guidance | `CLAUDE.md` (Architecture, Forbidden Patterns, Approved External Services, Testing) |
| Practice | the three most recent `specs/*/plan.md` + `tasks.md` (what the team actually does: tenancy model declared, story grouping, one commit per phase, `@critical` naming) |

### 3. Diff constitution ↔ reality

For each principle and table row, classify:

| Class | Meaning | Example |
|---|---|---|
| `ENFORCED` | stated and a gate enforces it | field auth — `check:field-auth` via typecheck |
| `STATED_UNENFORCED` | stated, nothing checks it | "every mutation has `@critical` tests" — no script counts them |
| `PRACTICED_UNSTATED` | done consistently, not in the constitution | expand-only migrations + `Allow-Contract-Migration:` trailer |
| `CONTRADICTED` | the repo or another source of truth says otherwise | "PRs require one approving review" vs ADR-0006 (no required reviewers); "hand-written SQL forbidden" vs the `--custom` RLS migrations |
| `STALE` | names a removed tool/path | tRPC, `analytics-db`, LGTM, Lefthook |

Always re-check these known-sensitive areas: tenancy models (owner-scoped vs
org-scoped), gate list in Principle III vs `ci.yml`, coverage threshold and its
date, E2E gating, flag granularity (global only), the admin realm (ADR-0013
Addendum 1), migration rules vs `check:migration-expand-contract`, approved
external services vs ADRs.

### 4. Decide the amendment and its version

- **MAJOR** — a principle removed or redefined incompatibly (something that
  complied stops complying).
- **MINOR** — a principle or obligation added or materially widened.
- **PATCH** — wording corrected to match reality; no obligation changed.

One amendment per concern is better than a grab-bag: if findings span
unrelated principles, propose the highest-value one and list the others as
deferred amendments.

### 5. Draft the change

Edit only the affected principle/section text. Keep the house style: MUST /
MUST NOT, a short "Why" where the rule is non-obvious, ADR references in
parentheses. Update `Last Amended` and the version line.

### 6. Write the new Sync Impact Report

Prepend (above the previous ones) an HTML comment in the established format:

```
<!--
  Sync Impact Report — v<old> → v<new>

  Version change: <old> → <new>
  Status: PROPOSED <YYYY-MM-DD>, in the PR that carries it; accepted when that
  PR is approved and merged, per Governance.
  Rationale: <MAJOR|MINOR|PATCH> — <why this bump, what stops/starts complying>

  Principles modified:
    - <principle> → <old statement> now reads <new statement>.
      Why: <evidence: file:line / ADR / command output>

  Sections modified: … | Sections added / removed: …

  Dependent artifacts:
    - ✅ <path> — <what was changed> (verified: <path:line>)
    - ⚠ <path> — <what still has to change>
    - ⃠ <path> — left as written (historical record)

  Deferred TODOs: <each with an owner or "none">
-->
```

Dependent artifacts to consider every time: `CLAUDE.md`,
`docs/adr/0000-stack-reference.md`, `.specify/templates/{spec,plan,tasks}-template.md`,
installed preset templates, `docs/feature-dev-workflow.md`, any `scripts/check-*.ts`
that should enforce the new rule.

### 7. Validate before writing

- No placeholder tokens left; dates ISO; version bumped exactly once.
- Every ✅ has a `verified:` citation you actually read.
- No previous Sync Impact Report modified.
- Every MUST is testable (names what checks it, or is listed as
  `STATED_UNENFORCED` in the report).

### 8. Write and report

Unless `--dry-run`, write the file (Status PROPOSED unless the user said the
amendment is accepted). Then print:

```markdown
## Constitution scan — v<old> → v<new> (<bump>)
| Class | Count |
| ENFORCED | … | STATED_UNENFORCED | … | PRACTICED_UNSTATED | … | CONTRADICTED | … | STALE | … |

### Amendment proposed
<principle → change, one line each>

### Gaps not addressed by this amendment
<each with a suggested gate or follow-up amendment>

### Next
- Open a PR titled `docs(config): constitution v<new> — <summary>`
- Run `/speckit.docs.sync` after it merges
```

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_constitution` entries and
apply standard hook-processing.
