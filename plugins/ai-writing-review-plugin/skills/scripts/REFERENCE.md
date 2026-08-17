# AI writing tells — reference

Companion to `detect.py`. The script counts what can be counted; this file covers
the judgment layer, the calibration rules that keep the tool from convicting good
human writing, and concrete rewrites.

Sources: [Wikipedia:Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing),
[Kobak et al., *Delving into ChatGPT usage in academic writing through excess vocabulary*](https://arxiv.org/abs/2406.07016),
[Juzek & Ward, *Why Does ChatGPT "Delve" So Much?*](https://arxiv.org/abs/2412.11385),
[Signs of AI Writing: 12 Patterns With Reproducible Thresholds](https://slopdetector.org/blog/signs-of-ai-writing).

The numeric cutoffs in `detect.py` (burstiness bands, em dash baselines, per-500
and per-300 rates) come from the last of these. They are working thresholds, not
figures this plugin reproduced independently — adjust them to your own corpus
rather than treating them as settled.

---

## A. Judgment-only tells

The script cannot evaluate meaning. These are yours.

### A1. The deletion test

Read each sentence and ask: **if I delete this, what information is lost?**

If the answer is "nothing" — the sentence restated the previous one, asserted
importance without evidence, or previewed what comes next — it is filler.

Count them. If more than a third of sentences survive deletion with no
information loss, the text is padded regardless of what the metrics say. This is
the single most reliable judgment signal, and it is what makes AI prose feel
simultaneously fluent and empty.

Common deletable shapes:

- Sentences that announce what the next paragraph will do.
- Sentences that restate the heading in prose.
- "This is important because it affects many areas."
- Any sentence whose content is fully implied by its neighbours.

### A2. The restatement test

After reading a paragraph, close it and try to state **one concrete fact** from
it — a number, a name, a date, a mechanism, a claim you could disagree with.

If you can't, the paragraph is hollow. Fluency masks this well; you have to
actually try the recall, not just judge how it read.

Flag the document if more than half the paragraphs fail.

### A3. Significance inflation

Asserting importance instead of demonstrating it:

> played a key role in · left an indelible mark · reflects a broader trend ·
> marks a turning point · stands as a reminder · has profound implications ·
> cannot be overstated

The giveaway is that the claim is unfalsifiable and unattributed. Real analysis
says *who* it mattered to and *what changed*.

### A4. The "Challenges and Future Prospects" reflex

A section that raises difficulties in the abstract and resolves into vague
optimism:

> "Despite its many advantages, X faces challenges. Issues of cost, adoption,
> and regulation persist. Looking ahead, the future appears bright…"

Notice it names no specific challenge, no specific actor, and no specific
outcome. Related shapes: "Awards and Recognition", "Impact and Legacy",
"Criticism and Controversy" — sections that exist because the template has them,
not because there was something to say.

### A5. Puffery / brochure register

> nestled in the heart of · renowned for · a diverse array of · world-class ·
> boasts a rich history · a hidden gem

Travel-guide prose applied to something that isn't a destination. The script
catches the fixed phrases; you catch the register.

### A6. Elegant variation

Swapping synonyms for a term across paragraphs to avoid repeating it — "the
company", "the firm", "the organization", "the business" all referring to the
same entity in four consecutive sentences.

Human technical writers repeat the term. This is a repetition-penalty artifact.

### A7. Symmetry of coverage

Every subtopic given roughly equal space regardless of how much there is to say
about it. Real writing is lumpy: the interesting part gets six paragraphs and
the obvious part gets one clause.

Check whether section lengths track actual importance, or whether they're all
suspiciously similar.

### A8. Ungrounded specificity

Numbers, percentages, and dates that appear precise but are sourced to nothing —
"studies show a 40% improvement". Either the figure has a citation or it was
invented to sound concrete. Cross-reference with the script's `vague_authority`
hits.

**It also runs backwards, and that version is more diagnostic.** Watch for vague
quantities in a text that is otherwise precise: "significantly more defects" in
an essay that elsewhere supplies 19 hours, 640 lines, 8% and 61%. An author with
that measurement habit does not reach for "significantly more" when reaching for
evidence. The vagueness is out of character for its surroundings, and a register
discontinuity inside one document is stronger evidence than any absolute rate.

### A9. Abstraction shuffling

The subject term stays fixed, but the predicate cycles through several
abstractions for the same claim:

> Code review is **a cornerstone of engineering excellence**… **a meaningful
> investment in the long-term health of the codebase**… not merely **a process**
> — it's **a mindset**… **a collaborative practice** rather than **a
> bureaucratic checkpoint**.

Six different nouns; not one is a different claim. Each restates "review is
good" in a new costume.

**The test:** list the predicates applied to the subject, then ask what changes
between them. If you cannot name a claim that one makes and the next does not,
they are one assertion repeated, and all but the best are deletable.

**Distinguish it from two neighbours.** In *elegant variation* (A6) the
**subject** term is what varies, and that is a repetition-penalty artifact. Here
the subject is repeated faithfully — often a sign of a technical writer — while
the predicate does the shuffling. And *significance inflation* (A3) asserts
importance once; this asserts it repeatedly, each time in different clothes.
A passage frequently shows both.

**Why it matters:** it is the mechanism behind a paragraph that fails A2. The
text feels substantive because each sentence introduces a new noun, and the
reader mistakes new vocabulary for new information.

---

## B. Calibration — what NOT to flag

**This section matters as much as the detection list.** Every AI-detection tool's
dominant failure mode is convicting good human writing. A reviewer that cries
wolf is worse than no reviewer, because the author stops listening.

### B1. Em dashes

**Never flag em dashes on count alone.** Plenty of excellent human writers use
them heavily; the association with AI is largely a 2024–25 moral panic.

The real tell is **monotony of function**. Em dashes legitimately do several
different jobs:

- interruption — like this — mid-clause
- appositive expansion at the end of a sentence
- replacing a colon before a list
- marking a sharp turn or punchline

If every dash in the document does the *same* job (almost always: a trailing
appositive that restates the first half of the sentence), that's the signal. If
they vary, high density is just the author's voice.

### B2. Domain vocabulary

The excess-vocabulary list is derived from *scientific abstracts*. Many entries
are the correct word in the right field:

- "robust" — statistics, engineering
- "landscape" — ecology, geography
- "delve" — mining, archaeology
- "crucial", "significant" — where they carry technical meaning
- "comprehensive" — of an actually exhaustive survey
- "harness" — equestrian, climbing, electrical

Check each hit against the subject matter. Density across many *different* words
is the signal, not the presence of any one word.

### B3. Deliberate rhetoric

Tricolon, anaphora, and antithesis ("not X but Y") are ancient rhetorical
devices. In a speech, an op-ed, or persuasive marketing copy they are craft, not
slop. Flag them when they appear on autopilot in expository prose — every third
list padded to three items — not when they're clearly doing work.

The tricolon check only counts triplets whose head words are stacked adjectives
or abstract nouns ("faster, cheaper, and more reliable"; "isolation,
communication, and management"). It already excludes proper-noun enumerations
("Keizersgracht, Herengracht, and Singel"), triplets inside list items, and
lists of concrete things ("trees, bikes, and boats"), because those are
enumerations by construction. The count in the report notes how many it excluded.
If you are reviewing a shot list, recipe, or feature table and still see hits,
check whether the items are genuinely adjectival before reporting them.

### B4. Formal academic register

Academic writing legitimately shares surface features with LLM output: hedging,
passive voice, nominalization, formal connectives, uniform paragraph structure.
A methods section *should* be uniform. Raise the bar substantially for academic
text and lean much harder on A1/A2 than on the surface metrics.

### B5. Non-native English

Detectors systematically over-flag non-native writers, who use more formal
register, more common vocabulary, and more explicit connectives. Lower TTR and
higher transition density are expected here and are **not** evidence of AI
authorship. If there are signs of a non-native voice, discount the vocabulary and
transition metrics almost entirely and rely on A1/A2.

### B6. Genre conventions

- **Reference docs and READMEs** legitimately use bold, headings, and tables
  densely. Judge against comparable human docs, not against prose.
- **Structured reports** legitimately have parallel sections.
- **Listicles** legitimately have uniform paragraphs.

### B7. Short texts

Under ~300 words, burstiness, TTR, and every rate-based metric are noise. Say so
rather than reporting a number that means nothing.

### B8. Human-edited AI text, and AI-assisted human text

Neither is a binary. A human draft lightly polished by a model, and a model draft
heavily rewritten by a human, both land in the middle. Report *what the text
does*, not a verdict on how it was produced. You are reviewing prose quality with
AI tells as the lens — you are not an authorship tribunal, and you cannot prove
authorship.

---

## C. Rewrite patterns

| Tell | Before | After |
|---|---|---|
| Throat-clearing | "In today's fast-paced digital landscape, security matters." | "Most breaches start with a stolen password." |
| Negative parallelism | "It's not just a tool — it's a platform." | "It started as a tool. It's now a platform." |
| Trailing participle | "Sales rose 12%, underscoring the strength of the strategy." | "Sales rose 12%." |
| Copula avoidance | "The library serves as a wrapper around libcurl." | "The library wraps libcurl." |
| Verb inflation | "We leveraged the API to facilitate the migration." | "We used the API to migrate." |
| Vague authority | "Experts say remote work boosts productivity." | "Bloom's 2015 Ctrip trial found a 13% productivity gain." |
| Excess vocabulary | "This delves into the intricate tapestry of the landscape." | "This looks at how the parts fit together." |
| Hedge boilerplate | "It's worth noting that results may vary." | "Results varied by 30% across the three sites." |
| Conclusion reflex | "In conclusion, remote work is here to stay." | *(cut it — end on the last real point)* |
| Autopilot tricolon | "faster, cheaper, and more reliable" | "faster and cheaper" *(if the third adds nothing)* |
| Puffery | "a world-class, state-of-the-art facility" | "a 40,000 m² plant built in 2023" |
| Significance inflation | "This played a key role in the industry's evolution." | "Three competitors copied the format within a year." |
| Abstraction shuffling | "It is a cornerstone, an investment, a culture — a mindset rather than a process." | *(pick the one true claim and cut the rest)* |
| Low burstiness | Six consecutive 18-word sentences. | Break one to four words. Let another run long, with subordinate clauses that earn their length. |
| Title Case heading | "## Getting Started With Installation" | "## Installation" |
| Bold overuse | "The **fast**, **flexible**, **modern** library." | "The library is fast and flexible." |

### Rewriting for burstiness

Don't tell the author to "vary sentence length" — that's the diagnosis, not the
fix. Point at a specific run of same-length sentences and show the break:

> Three sentences of 17, 19, and 18 words in a row (L22–24). Cut the second to
> its main clause and let the third carry the qualification.

---

## D. Weighting

Ordered by how much a positive result should move your verdict:

**Strong** — deletion test (A1), restatement test (A2), burstiness, a rhythm
split between pooled flat and pooled varied paragraphs, convergence of 3+
distinct patterns in one paragraph.

On the rhythm split: document burstiness is an average, so a human text with
generated paragraphs dropped into it reports as healthy. The `rhythm_split`
check locates paragraphs whose longest and shortest sentences differ by less
than 35% of their mean, then pools those against the rest. A large gap between
the two pools (say 0.24 against 0.72) is evidence of two registers in one file,
and points you at which paragraphs to apply A1 and A2 to first. A document that
is uniformly flat will not trigger it — plain burstiness already covers that
case. Treat a single flat paragraph in a long document as weak on its own.

**Moderate** — excess-vocabulary density across many distinct words, uncited
authority, trailing participles, transition stacking, negative parallelism at 3+,
paragraph uniformity.

**Weak** — em dash density, curly quotes and Unicode artifacts, TTR, any single
lexical hit, markdown formatting on its own.

**Decisive only in combination.** Three or four converging signals in the same
passage is genuine evidence. One flagged metric is not.
