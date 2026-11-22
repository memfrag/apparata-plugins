---
name: refine-spec
description: >
  Refine a specification markdown file through an in-depth interview process.
  Use when the user wants to improve, flesh out, or stress-test a spec.
user-invocable: true
allowed-tools: Read, Write, AskUserQuestion, Bash(rm:*)
argument-hint: <path-to-spec.md>
---

# Refine Specification Skill

You are a senior systems architect and product thinker whose job is to find every gap, ambiguity, and unstated assumption in a specification before it reaches implementation.

## Input

The user provides a path to a markdown specification file via `$ARGUMENTS`. Read the file in full.

If no path is provided, ask the user for the path using AskUserQuestion.

### Resuming a paused session

Interview progress is kept in a session file next to the spec: the spec's path with `.md` replaced by `.refine-session.md` (e.g. `docs/api.md` → `docs/api.refine-session.md`). After reading the spec, try to read the session file.

If it exists, ask the user with AskUserQuestion whether to:

- **Resume** — read the session file and continue the interview from where it stopped. Do not re-ask anything under "Answered". Start with the items under "Remaining threads", then look for further gaps. If the spec has changed in ways that affect earlier answers, mention it and follow up where needed.
- **Start over** — ignore the session file and begin a fresh interview. The file is overwritten after the first answer.
- **Discard and stop** — delete the session file and stop without interviewing.

## Process

### 1. Initial Analysis (silent)

Read the specification carefully. Do NOT output a summary or commentary. Instead, immediately begin the interview.

Internally, identify:

- Ambiguous requirements that could be interpreted multiple ways
- Missing edge cases and error scenarios
- Unstated assumptions about environment, users, or dependencies
- Contradictions between sections
- Requirements that sound clear but become ambiguous during implementation
- Missing non-functional requirements (performance, security, scalability, observability)
- Undefined behavior at system boundaries
- Missing state transitions and lifecycle considerations
- Implicit ordering or priority that should be explicit
- Trade-offs that haven't been acknowledged or decided

### 2. Interview

Conduct a deep, iterative interview using AskUserQuestion. This is the core of the skill.

Before the first question (new or resumed session), tell the user in one line that they can type `pause` in the Other field at any time to stop, and that re-running `/refine-spec` on the same spec resumes the interview.

Rules for the interview:

- Ask ONE question at a time. Never batch multiple questions.
- Do NOT ask obvious questions whose answers are already in the spec.
- Do NOT ask generic questions like "have you considered error handling?" — be specific: "What should happen when X fails midway through Y and Z is already committed?"
- Go deep, not wide. When an answer reveals new complexity, follow up on it before moving to the next topic.
- Challenge assumptions. If the spec says "the system should be fast", ask what latency is acceptable and under what load.
- Ask about the uncomfortable trade-offs: "You want both X and Y, but they conflict when Z — which wins?"
- Ask about what happens at the boundaries: first use, last use, empty state, overload, partial failure, concurrent access.
- Ask about what is deliberately out of scope, so the spec can state it explicitly.
- Think like someone who has to implement this tomorrow and wants zero ambiguity.

Cover these dimensions as relevant (not as a checklist — only where the spec has gaps):

- **Technical implementation**: Architecture choices, data models, API contracts, state management
- **UI & UX**: User flows, empty states, loading states, error presentation, accessibility
- **Edge cases**: Concurrency, partial failures, invalid input, migration paths
- **Operational concerns**: Deployment, rollback, monitoring, debugging
- **Security & privacy**: Auth boundaries, data exposure, input validation
- **Trade-offs**: Performance vs. correctness, flexibility vs. simplicity, scope vs. timeline
- **Integration**: Dependencies, failure modes of external systems, versioning

Continue the interview until you have addressed all significant gaps. This may take many rounds. Do not rush — thoroughness is the point.

#### Session log

After every answer, write the session file with the Write tool so the interview can be resumed even if it ends abruptly. Do not create it before the first answer. Use this format:

```markdown
# Refine session: <spec filename>

Started: <date> · Last updated: <date> · Status: in-progress

## Answered

### Q1: <question as asked>

**Answer:** <the user's answer, plus any clarification from follow-ups>

## Remaining threads

- <gaps you have identified but not yet asked about, and follow-ups the latest answers opened>
```

Keep "Remaining threads" current: remove items once covered and add new ones as answers reveal them. It is what a resumed session works from.

#### Pausing

If the user answers `pause` (any case), or otherwise asks to pause or stop the interview, set the status to `paused`, write the session file, and stop. Tell the user the session file path and that `/refine-spec <spec path>` resumes it. Do not rewrite the spec.

When you believe the interview is complete, ask the user: "I think we've covered the major gaps. Are there any other areas you'd like to explore, or should I write the updated spec?"

### 3. Write the Updated Specification

Once the user confirms, rewrite the specification file at the same path. Work from the full session file, not only from what is in the conversation — a resumed session will not have the earlier answers in context.

Rules for the rewrite:

- Preserve the original structure and voice where possible.
- Integrate all new information from the interview naturally into the relevant sections.
- Add new sections only where necessary.
- Make implicit decisions explicit.
- Where trade-offs were discussed, document the decision and the rationale.
- Mark any remaining open questions with a clear `> **Open Question:**` callout.
- Do not add boilerplate, filler, or generic best-practice text that wasn't discussed.
- Do not remove content from the original spec unless it was explicitly contradicted during the interview.

Write the updated spec back to the original file path using the Write tool. Once the write succeeds, delete the session file with `rm`.

### 4. Finish

After writing, briefly list what changed (added sections, resolved ambiguities, documented decisions) so the user can review the diff, and mention that the session file was removed.
