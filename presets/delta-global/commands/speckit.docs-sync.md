---
description: Delta-Global agent-context sync. Brings CLAUDE.md (primary) and AGENTS.md in line with the current constitution, ADRs and repository reality — section by section, with a reviewed diff — while preserving the <!-- SPECKIT START/END --> feature block and the turborepo-managed block untouched.
handoffs:
  - label: Scan the constitution
    agent: speckit.constitution-scan
    prompt: Check whether the constitution itself has drifted from the repository before syncing docs from it.
---

## User Input

```text
$ARGUMENTS
```

Optional flags:

- `--dry-run` — show the diff, write nothing.
- `--force` — write without the confirmation prompt (never skips the protected-block checks).
- `--targets <list>` — subset of `CLAUDE.md,AGENTS.md` (default both).
- `--section "<heading>"` — sync only that CLAUDE.md section.

## Pre-Execution Checks

Check for `.specify/extensions.yml`. If present, look for hooks under
`hooks.before_docs_sync` and apply standard hook-processing.

## What lives where (do not merge these roles)

| File | Role | Owned by |
|---|---|---|
| `CLAUDE.md` | the full runtime agent reference: Architecture at a Glance, Monorepo Layout, Tooling Quick Reference, How to Add a Feature / Temporal Workflow, TypeScript, Next.js/React, Data Access, Error Handling, Observability, Testing, Forbidden Patterns, Approved External Services, Python | humans + this command |
| `CLAUDE.md` `<!-- SPECKIT START -->…<!-- SPECKIT END -->` | the current feature's context (plan path, verified findings, state) | `/speckit.plan` and the feature workflow — **never rewritten here** |
| `AGENTS.md` | a short pointer file for other agents | this command (pointer part only) |
| `AGENTS.md` `<!-- BEGIN:turborepo-agent-rules -->…<!-- END:turborepo-agent-rules -->` | written and re-added by `turbo` | **never touched** |

Header rule, kept verbatim at the top of CLAUDE.md: the full stack reference
is `docs/adr/0000-stack-reference.md`, and when CLAUDE.md conflicts with it,
ADR-0000 wins.

## Outline

### 1. Collect the sources of truth

1. `.specify/memory/constitution.md` (version + principles + latest Sync
   Impact Report — its ⚠ items name docs that still need to change).
2. `docs/adr/*.md` with Status `Accepted`/`Superseded` (titles + decisions).
3. Repository reality: root `package.json` scripts, `.github/workflows/*.yml`,
   `.pre-commit-config.yaml`, `apps/*/package.json` scripts,
   `packages/shared/src/schemas/feature-flags.ts`, `apps/web/messages/`,
   `packages/graphql/schema/`.
4. `.specify/presets/delta-global/CONVENTIONS.md` (lowest precedence).

### 2. Find stale statements in CLAUDE.md

Section by section (outside the protected block), check every concrete claim —
a command, a path, a version, a gate, a date, a "does not exist yet" — against
step 1. Classify each:

| Class | Action |
|---|---|
| `STALE` (names a removed tool/path, wrong version) | rewrite to current reality, cite the evidence |
| `FALSE_GATE` (claims CI enforces something `ci.yml` does not run) | rewrite as "measured but not enforced" or add the gate as a follow-up — never leave the false claim |
| `MISSING` (accepted ADR or new `check:*` gate not mentioned) | add one line in the right section |
| `EXPIRED` (a dated promise whose date passed — e.g. the 70 % diff-coverage gate "on 2026-10-24") | check whether it happened; state the outcome |
| `OK` | leave untouched |

Common drift to look for on this platform: tRPC-era names (`superadminProcedure`,
`admin.setFlag`, `admin_audit_log`), "no DOM testing stack" (apps/web now has
happy-dom + Testing Library via `installDom()`), E2E gating claims, coverage
gates, new ADRs, Approved External Services vs network-policy entries.

Also read the SPECKIT block and **report** (do not edit) claims in it that are
contradicted elsewhere — the feature owner fixes those.

### 3. AGENTS.md

Keep it a pointer: the SPECKIT pointer block and one line sending agents to
`CLAUDE.md` and ADR-0000. Leave the turborepo block exactly as it is,
including its position. Create AGENTS.md only if it does not exist.

### 4. Present the plan

~~~markdown
## Docs Sync Plan — <date>
Constitution v<x> · ADRs read: n · claims checked: n

| File | Section | Class | Change | Evidence |
|---|---|---|---|---|

### Diffs
#### CLAUDE.md
```diff
- …
+ …
```
#### AGENTS.md (unchanged | pointer updated)

### Protected blocks
- SPECKIT block: untouched (n contradictions reported below)
- turborepo block: untouched
~~~

### 5. Confirm, then write

Unless `--force` or `--dry-run`, ask before writing. Before saving, assert:

- the SPECKIT block in the new file is byte-identical to the old one;
- the turborepo block in AGENTS.md is byte-identical;
- no section was removed that had no `STALE` finding.

If any assertion fails, write nothing and report it.

### 6. Report

```markdown
## Docs sync complete
- CLAUDE.md: n statements updated (STALE a · FALSE_GATE b · MISSING c · EXPIRED d)
- AGENTS.md: <unchanged | pointer updated>
- SPECKIT block contradictions for the feature owner: …
- Follow-ups (gates that should exist): …
Suggested commit: `docs: sync CLAUDE.md with constitution v<x> and ADR-<n>`
```

If the latest Sync Impact Report lists CLAUDE.md as ⚠ and this run fixed it,
say so — the constitution's next amendment can mark it ✅ with this commit as
the citation.

## Post-Execution Hooks

Check `.specify/extensions.yml` for `hooks.after_docs_sync` entries and apply
standard hook-processing.
