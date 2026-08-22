# Test fixtures

Corpora for `run_tests.py`. Each exists to pin a specific behaviour, and the
set is chosen so that a change which improves one usually threatens another.

| Fixture | Ground truth | Guards against |
|---|---|---|
| `ai_sample.md` | Machine-written throughout | False negatives — the detector must convict obvious slop |
| `human_sample.md` | Human-written, deliberately em-dash-heavy, contains a code fence | **False positives.** The most important fixture. Its dashes must not convict it, and its code block must not distort the prose metrics |
| `markdown_sample.md` | Formatting tells only | The `markdown_structure` sub-checks, and that code fences are masked |
| `mixed_draft.md` | Human essay with three planted filler paragraphs (L5, L11, L19) | Whole-document verdicts. The detector must localise, not condemn the file |

`mixed_draft.md` is the discriminating one. Six of its paragraphs are dense with
specifics and three carry every tell; a change that makes the detector flag the
whole file is a regression even if it "found" the slop.
