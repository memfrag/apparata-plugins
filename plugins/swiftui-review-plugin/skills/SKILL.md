---
name: swiftui-review
description: >
  Review SwiftUI code for adherence to the patterns and anti-patterns in
  "The SwiftUI Way" by Natalia Panferova — view composition, dependency scoping,
  observation and model lifetime, structural identity, update-cycle cost, data
  loading and concurrency, list performance, animation scoping, and platform
  conventions and accessibility. Use this skill whenever the user wants SwiftUI
  code reviewed, critiqued, audited, or checked against best practices — phrases
  like "review this SwiftUI view", "is this idiomatic SwiftUI", "check my SwiftUI
  for anti-patterns", or "why does this view keep re-rendering". Also trigger
  when diagnosing SwiftUI symptoms with no obvious cause: sluggish scrolling,
  dropped frames, input lag while typing, state that resets unexpectedly,
  animations that fire on the wrong views, or a custom control that VoiceOver
  cannot see.
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash, Agent
argument-hint: "[path-or-empty-for-current-diff]"
---

# SwiftUI Review

Review SwiftUI code against *The SwiftUI Way* (Natalia Panferova, Nil Coalescing, 2026) using this plugin's **`swiftui-reviewer`** agent.

## Step 1 — Determine the review target

From `$ARGUMENTS`, in order:

- **A file or directory path** → review that.
- **`diff`, `staged`, or nothing, inside a git repo** → review the working-tree changes. Prefer `git diff` (falling back to `git diff --staged`, then `git diff HEAD~1`) and pass the changed Swift files as the target. If the diff contains no `.swift` files, say so and stop rather than silently widening scope.
- **Nothing, outside a git repo** → look for SwiftUI files under the current directory (`Glob` for `**/*.swift`, filtered to files importing SwiftUI). If there are more than ~30, ask the user to narrow the scope instead of reviewing everything.

Resolve the target to concrete file paths before continuing. The agent should never have to guess what it is reviewing.

## Step 2 — Dispatch the agent

Launch the **`swiftui-reviewer`** agent with the resolved paths. Give it, explicitly:

- The exact files (or the diff command whose output defines the scope).
- The absolute path of this plugin's `references/` directory, which holds `swiftui-best-practices.md`.
- Whether it is reviewing **a diff** (judge only what changed, but read surrounding code for context) or **whole files**.
- Any focus the user asked for — e.g. "just the performance rules", "accessibility only". Absent that, it applies the full rubric.

Do not re-derive the review rubric here or in the prompt; it lives in the agent definition, and the reasoning behind it lives in `references/swiftui-best-practices.md`. Do not read the reference yourself and summarize it into the prompt — let the agent read it, so the full text stays out of the main conversation. Do not review the code yourself in parallel — wait for the agent.

## Step 3 — Relay the findings

The agent's report is not shown to the user, so **relay it**. Preserve:

- Severity ordering (Critical → Important → Minor).
- `file:line` references, so they stay clickable.
- The concrete failure trigger for each finding and its specific fix.

Keep the agent's verdict line at the end. If the agent found nothing, say that plainly and name what was checked — do not invent findings to fill the report.

## Step 4 — Offer to apply fixes

Ask whether to apply any of the findings. Apply only what the user selects; some findings (extracting subviews, switching `ObservableObject` to `@Observable`) touch call sites and are better done deliberately than in bulk.

## Notes

- The review is **read-only** by default. The agent has no write tools.
- Findings are grounded in framework mechanics — attribute-graph boundaries, view-value comparison, structural identity, eager identifier gathering in lists, actor inheritance — not in style preference. If a finding cannot name what concretely goes wrong and when, it does not belong in the report.
- The book reflects SwiftUI as of Xcode 27 / iOS 26. Notably, `@State` is now a macro with lazy initial-value evaluation (back-deployed to iOS 17 and equivalents), so the old "optional `@State` assigned in `.task`" allocation workaround is obsolete — the agent flags it as such rather than as a bug.
