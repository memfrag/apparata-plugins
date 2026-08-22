# Tests

Standard library only. No pytest, no install step.

```bash
python3 tests/run_tests.py       # 73 assertions
python3 tests/run_tests.py -v    # show every assertion, not just failures
python3 tests/mutate.py          # verify the suite can actually fail
```

## Two layers

`run_tests.py` covers the deterministic half — everything `detect.py` counts.
It mixes end-to-end fixture assertions with unit tests for behaviour no fixture
isolates cleanly.

Assertions are stated as bounds rather than exact numbers wherever the exact
number is not itself the behaviour, so tuning a threshold does not break the
suite while a real regression still does.

`mutate.py` breaks `detect.py` on purpose, once per shipped bug, and requires
each break to fail at least one test. **A suite that never fails proves
nothing.** This is not decorative: the first run found three behaviours with no
coverage, including the convergence-clustering fix, which `mixed_draft.md`
passed with the fix reverted because a second fix independently supplied the
same paragraph's third pattern. Fixtures overlap in what they exercise, and
mutation is how you find out where.

If a mutation reports `SKIP (target not found)`, `detect.py` has drifted from
the mutation's needle — update the needle, do not ignore it, or that behaviour
is silently uncovered.

## What is not covered

The judgment layer. The deletion and restatement tests, puffery, abstraction
shuffling, and the calibration rules all live in `REFERENCE.md` and are carried
out by the agent, so nothing here exercises them. `mixed_draft.md` is built for
that job — three hollow paragraphs planted in specific prose — but grading the
agent's reading of it needs an eval, not an assertion.
