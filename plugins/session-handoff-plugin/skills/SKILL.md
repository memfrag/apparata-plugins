---
name: session-handoff
description: >
  Generate a HANDOFF-<slug>.md document that captures the full state of the
  current work session — goal, progress, next steps, key files, decisions, open
  questions, and how to run/resume — so the work can be picked up later,
  including on a different machine by a fresh session with none of this
  conversation's context. Use this skill whenever the user wants to wrap up,
  pause, end, stop, or save a session to continue later; whenever they mention a
  "handoff", "pick this up later", "resume on another computer/machine",
  "continue tomorrow", "save where we are", "hand off to someone else", or want
  to carry context into a fresh session. Trigger even if they don't say the word
  "handoff" but clearly want to preserve session state for later continuation.
user-invocable: true
allowed-tools: Read, Write, Bash, AskUserQuestion
argument-hint: "[output-path-or-slug]"
---

# Session Handoff

## What this is for

You're writing a document that lets work resume cleanly after this session ends — often **on a different machine, by a fresh instance of Claude that has none of this conversation's context.**

That framing drives every choice below. The next reader will not have: this chat history, the local `~/.claude` memory files, the same absolute file paths, or the uncommitted changes sitting in this working tree. The handoff has to stand on its own. The biggest failure mode is writing a doc that only makes sense to *you, right now* — vague references ("the bug we fixed"), relative dates ("yesterday"), or an assumption that the code is already wherever it needs to be.

A second, quieter failure mode: a tidy-looking doc that quietly drops the one detail that actually unblocks the next session. Completeness on the *load-bearing* facts (next action, how to run it, where the code is) matters more than polish.

## Input

`$ARGUMENTS` is optional. If provided, treat it as either an output file path
(ends in `.md` or contains a `/`) or a slug to use in the default filename.
If absent, derive the slug yourself from the goal (see step 4).

## Process

### 1. Reconstruct the session state from the conversation

Read back over what happened this session and pull out:

- **The goal** — what we're ultimately trying to accomplish, in a sentence or two. Not "fix the test" but *why*.
- **What's actually done** — and be honest about what's *verified* vs. *assumed*. "Wrote the parser; have NOT run it" is far more useful to the next session than an optimistic "done."
- **The immediate next step** — the single most important thing. If the next session reads nothing else, this is what they act on.
- **Decisions and the alternatives we rejected** — so the next session doesn't relitigate them. "Chose X over Y because Z" prevents hours of re-deriving.
- **Open questions / blockers** — anything unresolved or waiting on the user.
- **Gotchas** — what surprised us or wasted time.

If any load-bearing fact lives only in your local memory (the `~/.claude` memory files) rather than in the repo, surface it *into the doc* — memory does not travel to another machine.

### 2. Inspect the environment and code state

The next session needs to get the project running before it can do anything. Capture how. Check git so you can record exactly where the code is:

```bash
git rev-parse --is-inside-work-tree 2>/dev/null && \
  echo "branch: $(git branch --show-current)" && \
  echo "head:   $(git rev-parse --short HEAD)" && \
  git remote -v && \
  echo "--- dirty files ---" && git status --short
```

Also note the run/test/build commands actually used this session (don't guess — prefer what you saw work), and the absolute working directory, since paths may differ on the other machine.

### 3. Make the code portable — check, then prompt

The markdown describes the code; it cannot *carry* it. So the code has to reach the other machine some other way, and the doc must say how.

- **It's a git repo with uncommitted work:** tell the user what's uncommitted and **offer to commit and push to a branch — but only with their confirmation.** Never push silently; pushing is outward-facing and hard to take back. If they decline, that's fine — record that the work is uncommitted and won't travel as-is. If they accept, follow their existing commit conventions, then record the branch + commit SHA in the doc.
- **It's a git repo and clean:** just record branch + SHA + remote.
- **Not a git repo:** flag plainly that the code won't travel via git. Ask where the work should live or whether to `git init`. Don't paper over this — it's the most common reason a handoff fails on the other end.
- **Deliberately local files** (untracked `.env`, scratch files, local config): these won't follow either. Name them and say how to recreate them — but see the secrets rule below.

### 4. Write the handoff file

Use the template below. **Default filename `HANDOFF-<slug>.md`** in the project root, where `<slug>` is a short kebab-case summary of the task derived from the goal (e.g. `HANDOFF-payment-retry-bug.md`, `HANDOFF-onboarding-redesign.md`). The slug lets a reader tell what the file is about before opening it, and keeps multiple handoffs distinguishable instead of clobbering one `HANDOFF.md`. Keep it to ~2–4 words. If `$ARGUMENTS` gave a path or slug, honor that instead.

Fill every section that applies; drop sections that genuinely don't (an empty "Gotchas" is fine to omit). Resolve all relative dates to absolute ones (today is whatever the session's current date is) — "fix by Friday" is meaningless to a reader next week.

### 5. Tell the user how to resume

End your turn by telling the user the exact path and the one-liner to resume next time, e.g.: *"Open `HANDOFF-payment-retry-bug.md` and say 'read HANDOFF-payment-retry-bug.md and pick up where we left off.'"* Use the real filename you wrote, not a placeholder.

## HANDOFF template

```markdown
# Handoff: <short project / task name>

> **To resume:** read this file, then continue from **Next steps**.
> Generated <absolute date> on <machine / working dir>.

## Goal
<One or two sentences: what we're ultimately trying to accomplish and why.>

## Current state
<What's done and working. Mark clearly what is verified vs. assumed-but-untested.>

## Next steps
1. <The single most important next action, concrete enough to act on.>
2. <...>

## Code & how to run
- **Repo / branch / commit:** <remote> @ `<branch>` `<short-sha>`
  (or: "not a git repo — code lives at <path>, must be copied manually")
- **Uncommitted work:** <none / what's uncommitted and whether it was pushed>
- **Setup:** <install / env steps>
- **Run / test:** <exact commands that worked this session>
- **Working dir this session:** <absolute path — may differ on the new machine>

## Key files
- `path/to/file` — <what it is / why it matters> (line refs if useful)

## Decisions & rationale
- <Chose X over Y because Z.>

## Open questions / blockers
- <Unresolved things, or what's waiting on the user.>

## Gotchas
- <What surprised us or wasted time.>
```

## Hard rules

- **Never write secrets, tokens, API keys, or passwords into the doc.** A handoff file often syncs through cloud storage, gets committed, or is shared with a teammate — anything in it may be cached or indexed even if later deleted. When a secret is *needed*, describe what it is and where to obtain it, not its value.
- **Never push or commit without explicit confirmation.** Capturing git state is read-only and always fine; changing the remote is not.
