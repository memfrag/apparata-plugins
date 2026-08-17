# AI Writing Review Plugin

Review prose for "AI-isms": the vocabulary, cadence, and structure that betray LLM authorship.

Two things shape the design, and both come out of the research:

**Most of the strongest tells are countable, not perceivable.** Em dash *rate*, sentence-length variance, transition-stacking percentage, excess-word density. These are statistical properties of a document. A model reading prose will not reliably notice that burstiness is 0.31 or that 60% of paragraphs open with a connective. A script notices every time. So a detector does the counting, and the agent spends its judgment on what a script cannot evaluate: whether a sentence carries information at all.

**No single tell convicts.** Em dashes are the notorious false positive; plenty of good writers use them heavily. The signal is *convergence*: several independent tells landing in the same paragraph. The plugin reports everything it finds, but ranks by convergence and labels weak signals as weak.

## Agent

### ai-ism-reviewer
A read-only review agent (`Read`, `Grep`, `Glob`, `Bash`) that runs the detector, reads the text, applies the judgment pass, calibrates away false positives, and reports. It has no write tools, so "report only" is enforced by the harness rather than by instruction.

## Skills

### ai-writing-review
`/ai-writing-review [file]` resolves the target, detects the genre, dispatches the agent, and relays the report.

## What it checks

The detector runs 19 checks. Every hit carries a line number.

| Check | Measure | Flags at |
|---|---|---|
| **Burstiness** | stdev ÷ mean of sentence lengths | < 0.4 (human 0.6–1.2, LLM 0.2–0.4) |
| **Em dash density** | per 1,000 words | > 20 (human 3.7–10; GPT-4.1 measured 10.6) |
| **Metronomic median** | median sentence length | 14–22 words *and* low variance |
| **Excess vocabulary** | ~90 words and phrases, per 500 words | > 3 |
| **Verb inflation** | leverage/utilize/facilitate, per 300 words | > 1 |
| **Negative parallelism** | "it's not just X, it's Y" family | ≥ 3 |
| **Autopilot tricolon** | three single-word items of similar length | > 1 per 200 words |
| **Trailing participle** | "…, underscoring the broader shift." | ≥ 2 |
| **Copula avoidance** | "serves as" / "boasts" where "is"/"has" would do | ≥ 3 |
| **Throat-clearing** | "in today's fast-paced world" | ≥ 2 per 500 words |
| **Uncited authority** | "experts say" with no number, name, or link nearby | any |
| **Transition stacking** | paragraphs opening Furthermore/Moreover/Additionally | > 50% |
| **Paragraph uniformity** | variance in paragraph length | ratio < 0.35 |
| **Vocabulary range** | MATTR over 500-word windows | supporting signal only |
| **Unicode artifacts** | curly quotes, arrows, check marks | any |
| **Conclusion reflex** | "In conclusion" / "At the end of the day" | any |
| **Hedge boilerplate** | "it's worth noting", "that said," | ≥ 2 |
| **Puffery** | "nestled in the heart of", "world-class" | ≥ 3 |
| **Markdown structure** | bold density, Title Case headings, emoji bullets, thematic breaks, heading-only sections, skipped levels, thin tables | per sub-check |

Code fences, inline code, tables, URLs, and front matter are masked before the prose metrics run, so a code block never distorts the rhythm numbers.

Beyond the detector, the agent applies the judgment layer, and these findings outrank the metrics:

- **Deletion test:** sentences removable with no information lost. Over a third means the text is padded whatever the metrics say.
- **Restatement test:** can you state one concrete fact from the paragraph after reading it? Fluency hides this well; you have to try the recall.
- **Significance inflation:** asserting importance instead of demonstrating it.
- **The "Challenges and Future Prospects" reflex:** abstract difficulties resolving into vague optimism.
- **Elegant variation:** synonym-swapping one term across four sentences.
- **Symmetry of coverage:** every subtopic given equal space regardless of how much there was to say.

## Calibration

The dominant failure mode of every AI-detection tool is convicting good human writing, so a full section of `REFERENCE.md` is about what *not* to flag, and the agent reports which exclusions it applied:

- **Em dashes are never evidence on their own.** The tell is monotony of function — every dash doing the same job — not the count.
- **Domain vocabulary is checked against the subject.** "Robust" in a statistics paper is the right word; so is "landscape" in ecology and "delve" in archaeology.
- **Deliberate rhetoric is craft.** Tricolon and antithesis in an op-ed are not slop.
- **Academic register gets a much higher bar.** A methods section *should* be uniform.
- **Non-native English is discounted heavily.** Detectors systematically over-flag it; lower TTR and higher transition density are expected, not suspicious.
- **Under ~300 words** the rate metrics are noise, and the agent says so instead of quoting them.

The review reports what the prose *does*. It does not claim to prove authorship. Human-edited AI and AI-assisted human writing both land in the middle, and that is a legitimate finding rather than a failure.

## Running the detector directly

```bash
python3 skills/scripts/detect.py DRAFT.md          # summary table
python3 skills/scripts/detect.py DRAFT.md --full   # every hit
python3 skills/scripts/detect.py DRAFT.md --json   # structured, for the agent
```

## Sources

- [Wikipedia:Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) — the most complete catalogue of tells
- Kobak et al., [*Delving into ChatGPT usage in academic writing through excess vocabulary*](https://arxiv.org/abs/2406.07016) — the excess-vocabulary method; "delves" at 25× its expected rate
- Juzek & Ward, [*Why Does ChatGPT "Delve" So Much?*](https://arxiv.org/abs/2412.11385) — why RLHF produces the lexical skew
- [Signs of AI Writing: 12 Patterns With Reproducible Thresholds](https://slopdetector.org/blog/signs-of-ai-writing) — source of the numeric cutoffs in the table above, including the burstiness bands and the em dash baselines

The burstiness and em dash figures are working thresholds drawn from the last of these, not measurements this plugin reproduced. Treat them as calibration starting points and adjust them to your own corpus.

## Prerequisites

Python 3, standard library only. Reviews are read-only.
