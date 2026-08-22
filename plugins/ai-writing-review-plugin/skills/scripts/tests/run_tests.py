#!/usr/bin/env python3
"""Regression tests for detect.py. Standard library only.

    python3 tests/run_tests.py [-v]

Assertions are deliberately stated as bounds rather than exact numbers, so
tuning a threshold does not break the suite while a behavioural regression
still does. Where an exact value is pinned it is because that value *is* the
behaviour under test.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
FIXTURES = os.path.join(HERE, "fixtures")
sys.path.insert(0, SCRIPTS)

import detect  # noqa: E402

VERBOSE = "-v" in sys.argv
_results = []


def check(name, condition, detail=""):
    _results.append((name, bool(condition), detail))
    if VERBOSE or not condition:
        mark = "pass" if condition else "FAIL"
        print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))


def analyze(fixture):
    return detect.analyze(os.path.join(FIXTURES, fixture))


def by_key(result):
    return {f["pattern"]: f for f in result["findings"]}


def value_of(result, key):
    return by_key(result).get(key, {}).get("value", "")


def severity(result, key):
    return by_key(result).get(key, {}).get("severity", "missing")


def count(result, key):
    return by_key(result).get(key, {}).get("count", 0)


def lines(result, key):
    return sorted({h["line"] for h in by_key(result).get(key, {}).get("hits", [])})


def num(text, pattern):
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


# ---------------------------------------------------------------------------


def test_ai_sample():
    """Obvious slop must convict. Guards against false negatives."""
    print("\nai_sample.md — machine-written throughout")
    r = analyze("ai_sample.md")

    b = num(value_of(r, "burstiness"), r"^([\d.]+)")
    check("burstiness below the human band", b is not None and b < 0.45, f"{b}")
    check("excess vocabulary flagged", severity(r, "excess_vocabulary") == "flag",
          value_of(r, "excess_vocabulary"))
    check("trailing participles flagged",
          severity(r, "trailing_participle") == "flag", value_of(r, "trailing_participle"))
    check("uncited authority flagged", severity(r, "vague_authority") == "flag",
          value_of(r, "vague_authority"))
    check("throat-clearing flagged", severity(r, "throat_clearing") == "flag",
          value_of(r, "throat_clearing"))
    check("several convergence clusters", len(r["clusters"]) >= 5,
          f"{len(r['clusters'])} clusters")
    check("at least 5 checks flagged", r["counts"]["flag"] >= 5,
          f"{r['counts']['flag']} flagged")
    # Uniformly flat, so the split check must stay quiet: plain burstiness
    # already covers this document.
    check("rhythm_split silent on a uniformly flat file",
          severity(r, "rhythm_split") == "info", value_of(r, "rhythm_split"))


def test_human_sample():
    """The most important fixture: good human writing must survive."""
    print("\nhuman_sample.md — human, em-dash-heavy, contains a code fence")
    r = analyze("human_sample.md")

    check("nothing flagged", r["counts"]["flag"] == 0,
          f"{r['counts']['flag']} flagged")
    check("no convergence clusters", not r["clusters"],
          f"{len(r['clusters'])} clusters")

    b = num(value_of(r, "burstiness"), r"^([\d.]+)")
    check("burstiness in the human band", b is not None and b >= 0.6, f"{b}")
    check("em dashes present but not flagged",
          count(r, "em_dash_density") >= 3 and severity(r, "em_dash_density") == "info",
          value_of(r, "em_dash_density"))
    check("no metronomic paragraphs", severity(r, "rhythm_split") == "info",
          value_of(r, "rhythm_split"))
    check("no excess vocabulary", count(r, "excess_vocabulary") == 0)
    check("no negative parallelism", count(r, "negative_parallelism") == 0)
    check("no autopilot tricolon", count(r, "tricolon") == 0)

    # "a note from Dennis that said" must not read as the hedge "that said,".
    check("hedge boilerplate does not fire on a relative clause",
          count(r, "hedge_boilerplate") == 0, value_of(r, "hedge_boilerplate"))

    # The fenced block holds ' -- ' and an em dash; neither may be counted.
    check("code fence masked from em dash count",
          count(r, "em_dash_density") == 3, value_of(r, "em_dash_density"))


def test_markdown_sample():
    """Formatting tells, and code masking."""
    print("\nmarkdown_sample.md — formatting tells only")
    r = analyze("markdown_sample.md")

    md = by_key(r).get("markdown_structure", {})
    check("markdown structure flagged", md.get("severity") == "flag",
          md.get("value", ""))
    detail = md.get("value", "")
    for sub in ("bold_overuse", "title_case_headings", "emoji_decoration",
                "thematic_breaks", "skipped_heading_levels"):
        check(f"sub-check fires: {sub}", sub in detail)

    # One em dash in prose; the fence's ' -- ' and em dash must not count.
    check("only the prose em dash counted", count(r, "em_dash_density") == 1,
          value_of(r, "em_dash_density"))
    # A parent heading followed by its own subsection is normal nesting.
    check("nesting not reported as empty sections",
          "heading_only_sections" not in detail)


def test_inline_code_masked():
    """Inline code must not contribute to prose metrics."""
    print("\ninline code — masked from prose")
    plain = detect.Document("A sentence — with a dash in prose.\n", "<mem>")
    coded = detect.Document("A sentence `— with a dash in code` here.\n", "<mem>")
    for label, doc, expect in [("prose dash counted", plain, 1),
                               ("inline-code dash ignored", coded, 0)]:
        stats = detect.build_stats(doc)
        got = len(detect.check_em_dash(doc, stats).hits)
        check(label, got == expect, f"got {got}, expected {expect}")


def test_mixed_draft():
    """The discriminating fixture: localise, do not condemn the file."""
    print("\nmixed_draft.md — human essay, three planted paragraphs (L5, L11, L19)")
    r = analyze("mixed_draft.md")

    cluster_lines = sorted(c["line"] for c in r["clusters"])
    check("clusters land exactly on the planted paragraphs",
          cluster_lines == [5, 11, 19], f"got {cluster_lines}")

    # Every lexical hit belongs to a planted paragraph; the other six are clean.
    planted = {5, 11, 19}
    for key in ("excess_vocabulary", "trailing_participle", "vague_authority",
                "copula_avoidance", "throat_clearing"):
        hit_lines = set(lines(r, key))
        check(f"{key} confined to planted paragraphs",
              hit_lines <= planted, f"lines {sorted(hit_lines)}")

    # Document burstiness reads healthy; the split is what carries the finding.
    b = num(value_of(r, "burstiness"), r"^([\d.]+)")
    check("document burstiness looks healthy", b is not None and b >= 0.55, f"{b}")
    check("rhythm split reported anyway",
          severity(r, "rhythm_split") in ("elevated", "flag"),
          value_of(r, "rhythm_split"))
    flat = num(value_of(r, "rhythm_split"), r"flat ([\d.]+)")
    rest = num(value_of(r, "rhythm_split"), r"rest ([\d.]+)")
    check("flat pool far below the varied pool",
          flat is not None and rest is not None and rest - flat > 0.3,
          f"flat {flat} vs rest {rest}")

    # Uncontracted negative parallelism must be caught (L19 "is not merely").
    check("both negative parallelisms found, contracted and not",
          sorted(lines(r, "negative_parallelism")) == [5, 19],
          f"lines {lines(r, 'negative_parallelism')}")

    # A number in a later paragraph must not excuse an uncited claim.
    check("citation window does not cross paragraphs",
          count(r, "vague_authority") == 3, value_of(r, "vague_authority"))


def test_tricolon_discrimination():
    """Padded triplets convict; enumerations do not."""
    print("\ntricolon — rhetorical stacking vs plain enumeration")
    should_flag = [
        "The system is faster, cheaper, and more reliable than before.",
        "Issues of isolation, communication, and management persist here.",
        "Employees feel connected, valued, and supported at all times.",
        "We want it clean, simple, and fast for everyone involved.",
    ]
    should_pass = [
        "We walked along Keizersgracht, Herengracht, and Singel today.",
        "Photograph the trees, bikes, and boats near the water.",
        "Bring glass, water, and ferries into the frame somehow.",
        "Look for symbols, flags, and banners along the street.",
    ]
    for text, expect in [(t, True) for t in should_flag] + \
                        [(t, False) for t in should_pass]:
        doc = detect.Document(text + "\n", "<mem>")
        stats = detect.build_stats(doc)
        got = detect.check_tricolon(doc, stats).hits
        check(("flags: " if expect else "ignores: ") + text[:46],
              bool(got) == expect)

    # The same rhetorical triplet is an enumeration once it is a bullet.
    prose = "We want it clean, simple, and fast for everyone involved.\n"
    listed = "- clean, simple, and fast for everyone involved\n"
    for label, text, expect in [("as prose", prose, True),
                                ("as a list item", listed, False)]:
        doc = detect.Document(text, "<mem>")
        stats = detect.build_stats(doc)
        got = detect.check_tricolon(doc, stats).hits
        check(f"triplet {label}: {'flagged' if expect else 'excluded'}",
              bool(got) == expect)


def test_negative_parallelism_forms():
    """Contracted and uncontracted forms alike; no false firing."""
    print("\nnegative parallelism — contracted and uncontracted")
    cases = [
        ("It's not just a quality gate", True),
        ("code review is not merely a process", True),
        ("this is not simply a tool", True),
        ("it was not only slow", True),
        ("these are not just numbers", True),
        ("it does not merely describe the problem", True),
        ("it isn't just slow", True),
        ("the file is not present", False),
        ("there is not a single test", False),
    ]
    for text, expect in cases:
        got = any(re.search(p, text, re.I) for p in detect.NEGATIVE_PARALLELISM)
        check(("matches: " if expect else "ignores: ") + text[:46], got == expect)


def test_no_double_counting():
    """Overlapping patterns in one family must count a phrase once."""
    print("\noverlap — one construction, one hit")
    text = "It's not just a gate, but a culture entirely.\n"
    doc = detect.Document(text, "<mem>")
    hits = detect.scan_regexes(doc, detect.NEGATIVE_PARALLELISM)
    starts = [h["offset"] for h in hits]
    check("no two hits share an offset", len(starts) == len(set(starts)),
          f"offsets {starts}")

    # Several patterns in this family match at the same "not", with different
    # lengths. The longest is the informative one, so it must be the one kept.
    at_not = text.index("not just")
    candidates = [m.group(0) for p in detect.NEGATIVE_PARALLELISM
                  for m in re.finditer(p, text, re.I) if m.start() == at_not]
    check("precondition: multiple patterns match the same offset",
          len(candidates) >= 2, f"{len(candidates)} candidates")
    if len(candidates) >= 2:
        longest = max(candidates, key=len)
        kept = [h["text"] for h in hits if h["offset"] == at_not]
        check("the longest match is the one kept",
              kept and kept[0] == longest, f"kept {kept}, longest {longest!r}")


def test_edge_cases():
    """Degenerate input must not raise."""
    print("\nedge cases")
    for label, text in [
        ("empty file", ""),
        ("single word", "One.\n"),
        ("no trailing newline", "no trailing newline"),
        ("front matter only", "---\ntitle: x\n---\n"),
        ("front matter stripped", "---\ntitle: x\n---\n\nHello world. This is fine.\n"),
        ("code fence only", "```\nx -- y — z\n```\n"),
        ("unterminated fence", "```\nx\n"),
    ]:
        try:
            doc = detect.Document(text, "<mem>")
            stats = detect.build_stats(doc)
            for fn in detect.CHECKS:
                fn(doc, stats)
            ok, detail = True, ""
        except Exception as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        check(f"survives {label}", ok, detail)

    # Front matter must not reach the prose view.
    doc = detect.Document("---\ntitle: x\n---\n\nHello world. This is fine.\n", "<mem>")
    stats = detect.build_stats(doc)
    check("front matter excluded from word count", stats["words"] == 5,
          f"{stats['words']} words")


def test_clustering_counts_low_rate_patterns():
    """Convergence must not discard a pattern for its document-wide rate.

    Severity is a document-wide rate; convergence is per paragraph. A pattern
    hitting twice in the whole text, both times in one paragraph, is stronger
    evidence for that paragraph rather than weaker. This is tested directly
    because no end-to-end fixture isolates it: in mixed_draft.md the citation
    fix independently supplies the same paragraph's third pattern, so that
    fixture passes whether or not this behaviour is correct.
    """
    print("\nclustering — low document-rate patterns still converge")
    text = (
        "# Title\n\n"
        "A short opening line about the work.\n\n"
        "The project serves as a cornerstone of the field, fostering "
        "collaboration and enhancing quality. It represents a robust "
        "framework, highlighting the importance of scale.\n"
    )
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".md")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        r = detect.analyze(path)
    finally:
        os.unlink(path)

    # Precondition: copula avoidance is present but rates as "info" document-wide.
    check("precondition: copula avoidance present", count(r, "copula_avoidance") == 2,
          value_of(r, "copula_avoidance"))
    check("precondition: and rates as info document-wide",
          severity(r, "copula_avoidance") == "info",
          severity(r, "copula_avoidance"))

    target = [c for c in r["clusters"] if "copula_avoidance" in c["patterns"]]
    check("the info-severity pattern still counts toward convergence",
          bool(target),
          f"clusters: {[(c['line'], c['patterns']) for c in r['clusters']]}")
    if target:
        check("paragraph reaches three distinct patterns",
              target[0]["distinct_patterns"] >= 3,
              f"{target[0]['distinct_patterns']} patterns")


TESTS = [
    test_ai_sample,
    test_human_sample,
    test_markdown_sample,
    test_inline_code_masked,
    test_mixed_draft,
    test_tricolon_discrimination,
    test_negative_parallelism_forms,
    test_no_double_counting,
    test_clustering_counts_low_rate_patterns,
    test_edge_cases,
]


def main():
    for fn in TESTS:
        try:
            fn()
        except Exception as exc:
            check(f"{fn.__name__} raised", False, f"{type(exc).__name__}: {exc}")

    failed = [(n, d) for n, ok, d in _results if not ok]
    print("\n" + "-" * 62)
    print(f"{len(_results) - len(failed)} passed, {len(failed)} failed")
    if failed:
        print("\nFailures:")
        for n, d in failed:
            print(f"  {n}" + (f" — {d}" if d else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
