---
name: claude-md-curator
description: Use this skill when CLAUDE.md may have grown bloated with historical notes, dated fix-logs, or duplicated context — and needs evaluation for possible compaction. Trigger conditions include the user explicitly asking to "check / clean / optimize / shrink CLAUDE.md", or noticing CLAUDE.md is large (>400 lines) or contains many dated fix-blocks ("YYYY-MM-DD fix:..."). Also use proactively before major releases or when onboarding new agents to the repo. This skill performs diagnosis first and may conclude that no action is needed. It NEVER deletes content silently — every removal goes through a user-visible diff gate.
---

# CLAUDE.md Curator

You curate the repo's `CLAUDE.md` to keep it useful for future Claude sessions: navigation-friendly, full of operational context, free of stale historical residue. This is **diagnostic-first** — most invocations should not result in changes. When changes are needed, they go through explicit approval gates, never silent rewrites.

## Phase 1 — Diagnose (always run)

Read the current `CLAUDE.md` in full. Then produce a one-screen diagnostic report covering:

1. **Size**: total lines, approximate token count.
2. **Dated blocks**: count of paragraphs containing explicit dates in form `YYYY-MM-DD` or `Sprint N` references that describe past events (not current behavior).
3. **Duplication map**: list any topic mentioned in 3+ sections (e.g. "UK Integration appears in Key Patterns, Module section, API Routes, and DB tables").
4. **Active warnings inventory**: scan for and list every imperative statement that warns future code (look broadly — not just the obvious ones; signals include "NEVER", "must not", "gotcha", "критично", "always", "if you ever", commit-hash references, "do not delete", parenthetical "(fix: ...)", or "header note for any future..."). This list is the protected set — nothing in it gets removed without explicit user override.
5. **Path references**: count of `src/`, `database/`, `docs/`, `public/` paths. These are navigation aids — never reduce.

Output the diagnostic and **stop**. Wait for user response.

## Phase 2 — Verdict

Based on the diagnostic, give one of three verdicts:

- **GREEN** — file is healthy, no action recommended. Explain briefly which thresholds are within bounds. Exit.
- **YELLOW** — moderate bloat (typically >400 lines, 5–15 dated blocks, 1–2 duplicated topics). Propose targeted compaction without restructuring sections. Wait for user approval.
- **RED** — severe bloat (>600 lines, 15+ dated blocks, or 3+ duplicated topics) OR structural problems (sections out of order, lost hierarchy). Propose full audit + extraction to a history file. Wait for user approval.

Do not pre-commit to a verdict before showing the diagnostic.

## Phase 3 — Plan (only if YELLOW or RED, and only after approval)

Produce a written plan listing:

- Each block proposed for removal/compaction with: location (line range), one-line summary of content, destination (delete / archive in `docs/audit/CLAUDE-MD-ARCHIVE.md` / compact to N lines).
- Each block proposed to keep verbatim, with rationale (path reference / active warning / current behavior).
- Sections proposed to be reorganized (if RED only).

For every block in the **active warnings inventory** from Phase 1: state it explicitly in the "keep verbatim" list. If you propose to touch one, justify why it is no longer active.

If the user has an existing changelog location (e.g. `docs/audit/`, `docs/changelog/`), use that — do not invent a new directory without asking. Run `ls docs/` first.

Stop. Wait for plan approval.

## Phase 4 — Execute (only after plan approval)

1. Create branch `chore/claude-md-curator-YYYY-MM-DD`.
2. Make a "preservation commit" first: copy the current `CLAUDE.md` to `docs/audit/CLAUDE-MD-snapshots/YYYY-MM-DD-CLAUDE.md.bak`. This guarantees a recoverable point regardless of what comes next.
3. If extracting to archive: write the archive file. Each extracted block goes in **verbatim**, with its original heading preserved and date prepended. Commit.
4. Rewrite `CLAUDE.md`. Commit separately.

## Phase 5 — Verify (mandatory, do not skip)

Before declaring done, run these checks and report results:

1. **Warning preservation check**: for every item in the Phase 1 active warnings inventory, `grep` the new `CLAUDE.md` and confirm it is present (verbatim or near-verbatim). List each one with ✓/✗.
2. **Path reference check**: count `src/`, `database/`, `docs/`, `public/` references in old vs new. Drop should be <10%. If higher, list which paths were removed and why.
3. **Round-trip question test**: pose 5 concrete questions a future Claude session might ask, drawn from the archived blocks (e.g. "what's the webhook signature header format?", "which env-flag disables MV refresh?", "what is the cooldown gotcha for checkLeak?"). For each, search only the new `CLAUDE.md` and confirm the answer is findable. Report ✓/✗.
4. **Anti-deletion anchor check**: verify the final line is the `NEVER delete...` anchor (or equivalent if user has a different one). 

If any check fails: roll back the rewrite commit (keep the preservation snapshot and archive), report the failure, and ask the user how to proceed. Do not auto-fix.

## Anti-patterns — never do these

- Do not target a line count. Compaction is a side effect of removing redundancy, not a goal. If you cannot find redundancy, recommend GREEN.
- Do not run subagents or split this across a swarm. CLAUDE.md is small enough for one synchronous session, and parallel edits will desync.
- Do not edit `.claude/`, `.gitignore`, or any other file. Only `CLAUDE.md`, the archive file, and the preservation snapshot.
- Do not translate content between Russian and English. Preserve the original language of each block.
- Do not treat the example warnings in this skill (cooldown gotcha, webhook header, UK_USE_WEBHOOK_SENDER) as the closed set. They were examples; the real list comes from Phase 1 scan.
- If the user added a new dated fix-block in the past 7 days, treat it as still active (give it time to age) — do not extract it yet.

## When to escalate / recommend a different approach

If you find that >40% of CLAUDE.md is dated fix-notes accumulating across many sprints, this is a process problem, not a curation problem. After completing the cleanup, recommend to the user one of:

- Adding a rule to `CLAUDE.md` itself: "new fix-notes go in `docs/audit/` with a one-line back-reference here, not inline".
- Setting up a pre-commit hook or CI check that flags CLAUDE.md additions containing date patterns.

Mention this only once, in the final report. Do not lecture.