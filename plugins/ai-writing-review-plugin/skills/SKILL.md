---
name: ai-writing-review
description: >
  Review prose for "AI-isms" — the markers that betray LLM authorship. Covers em
  dash monotony, excess vocabulary ("delve", "tapestry", "underscores",
  "intricate"), the "it's not just X, it's Y" reversal, trailing participial
  summaries ("..., highlighting the broader shift"), uncited authority ("experts
  say", "studies show"), throat-clearing openers ("in today's fast-paced
  world"), metronomic sentence rhythm, transition stacking, and paragraphs that
  read fluently but carry no retrievable information. Use this skill whenever the
  user wants writing checked for AI tells, AI slop, or "does this sound like
  ChatGPT wrote it" — phrases like "review this draft for AI-isms", "does this
  sound AI-generated", "de-slop this", "make this sound less like AI", "check my
  post for AI writing patterns". Works on essays and blog posts, READMEs and
  documentation, and academic or report writing.
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash, Agent
argument-hint: "[file-path]"
---

# AI Writing Review

Review a piece of writing for markers of LLM authorship using this plugin's
**`ai-ism-reviewer`** agent, which pairs a statistical detector with a judgment
pass.

The review **reports only** — it never edits the text.

## Step 1 — Resolve the target

From `$ARGUMENTS`, in order:

- **A file path** → review that file.
- **A directory** → find prose files (`*.md`, `*.txt`, `*.mdx`) inside it. If
  there is more than one, ask which to review rather than reviewing all of them.
- **Nothing** → look for prose in the working directory. If exactly one obvious
  candidate exists (a single `.md` that isn't a README boilerplate), use it.
  Otherwise ask.
- **Pasted text with no file** → write it to a temp file first; the detector
  needs a path.

Resolve to a concrete absolute path before continuing.

## Step 2 — Locate the scripts directory

The detector and reference live in this skill's `scripts/` directory:

```
<skill-path>/scripts/detect.py
<skill-path>/scripts/REFERENCE.md
```

Resolve `<skill-path>` to an absolute path. You will pass it to the agent.

## Step 3 — Dispatch the agent

Launch the **`ai-ism-reviewer`** agent. Give it, explicitly:

- The absolute path of the file to review.
- The absolute path of the `scripts/` directory.
- The **genre**, if you can tell — blog/essay, README/docs, or academic/report.
  This matters: the agent raises its threshold for academic and reference text,
  where formal register legitimately resembles LLM output.
- Any calibration the user asked for (for example, "I use em dashes on purpose").

Do not run the detector yourself and hand the agent the output — let the agent
run it, so the raw JSON stays out of the main conversation.

## Step 4 — Present the review

Relay the agent's report. It is the deliverable, so pass it through in full
rather than summarizing it away.

Then offer, without doing it unprompted:

- Applying a specific subset of the suggested rewrites.
- Re-running the review after the user edits.

## Notes

- The detector needs only Python 3 and the standard library.
- It masks code fences, inline code, tables, URLs, and front matter before
  measuring prose, so code blocks do not distort the rhythm metrics.
- Under ~300 words the rate-based metrics are noise, and the agent will say so
  rather than quoting them.
- The review cannot prove authorship, and does not claim to. It reports what the
  prose does. Human-edited AI text and AI-assisted human text both land in the
  middle, which is a legitimate outcome rather than a failure of the tool.

## Running the detector directly

For a quick check without the judgment pass:

```bash
python3 <skill-path>/scripts/detect.py DRAFT.md          # summary table
python3 <skill-path>/scripts/detect.py DRAFT.md --full   # every hit
python3 <skill-path>/scripts/detect.py DRAFT.md --json   # structured
```
