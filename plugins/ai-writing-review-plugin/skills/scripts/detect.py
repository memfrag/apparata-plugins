#!/usr/bin/env python3
"""Scan prose for countable markers of LLM authorship.

Emits metrics and located pattern hits. Judgment (does this sentence carry
information? does this paragraph leave a takeaway?) is left to the caller.

Usage:
    detect.py DRAFT.md [--json] [--full]
"""

import argparse
import json
import math
import re
import statistics
import sys
import unicodedata
from collections import Counter

# --------------------------------------------------------------------------
# Word lists
# --------------------------------------------------------------------------

# From the PubMed excess-vocabulary study (arxiv 2406.07016) plus the
# Wikipedia:Signs of AI writing catalogue. Edit here; nothing else reads
# these directly.
EXCESS_WORDS = {
    "delve", "delves", "delved", "delving",
    "tapestry", "tapestries",
    "underscore", "underscores", "underscored", "underscoring",
    "showcase", "showcases", "showcased", "showcasing",
    "intricate", "intricacies",
    "realm", "realms",
    "meticulous", "meticulously",
    "pivotal", "crucial", "crucially",
    "robust", "robustly",
    "testament",
    "landscape", "landscapes",
    "boast", "boasts", "boasting",
    "bolster", "bolsters", "bolstered", "bolstering",
    "garner", "garners", "garnered", "garnering",
    "interplay",
    "vibrant",
    "foster", "fosters", "fostered", "fostering",
    "enhance", "enhances", "enhanced", "enhancing",
    "comprehensive", "comprehensively",
    "notably", "particularly",
    "insights",
    "resonate", "resonates", "resonated", "resonating",
    "multifaceted", "nuanced", "seamless", "seamlessly",
    "holistic", "holistically",
    "myriad", "paradigm", "paradigms",
    "ever-evolving", "ever-changing",
    "profound", "profoundly",
    "invaluable", "unwavering", "indelible",
    "harness", "harnesses", "harnessing",
    "pave", "paves", "paving",
    "empower", "empowers", "empowered", "empowering",
    "unlock", "unlocks", "unlocking",
    "transformative", "groundbreaking", "cutting-edge",
    "vital", "essential", "significant",
}

# Multi-word members of the same family, matched separately.
EXCESS_PHRASES = [
    r"deep dive", r"dive into", r"align(?:s|ed|ing)? with",
    r"a testament to", r"plays? a (?:key|vital|crucial|pivotal|significant) role",
    r"rich (?:tapestry|history|tradition)", r"diverse (?:array|range)",
    r"wide (?:array|range) of", r"in the realm of", r"navigate the",
    r"at the forefront of", r"a beacon of", r"the (?:very )?fabric of",
]

# Plain-word substitutes the model reaches past.
INFLATED_VERBS = {
    "leverage": "use", "leverages": "uses", "leveraging": "using",
    "utilize": "use", "utilizes": "uses", "utilizing": "using",
    "utilization": "use",
    "facilitate": "help", "facilitates": "helps", "facilitating": "helping",
    "spearhead": "lead", "spearheads": "leads", "spearheaded": "led",
    "streamline": "simplify", "streamlines": "simplifies",
    "streamlined": "simplified",
    "commence": "start", "commences": "starts", "commenced": "started",
    "endeavor": "try", "endeavors": "tries",
    "ascertain": "find out", "ascertains": "finds out",
    "elucidate": "explain", "elucidates": "explains",
    "necessitate": "require", "necessitates": "requires",
    "demonstrate": "show", "demonstrates": "shows",
    "encompass": "include", "encompasses": "includes",
    "exemplify": "show", "exemplifies": "shows",
}

NEGATIVE_PARALLELISM = [
    r"\b(?:it|this|that|there)'?s not (?:just|only|merely|simply)\b",
    r"\b(?:is|are|was|were)n'?t (?:just|only|merely|simply)\b",
    r"\bnot (?:just|only|merely|simply)\s+\w[\w\s,'-]{0,60}?\s+but\b",
    r"\bmore than (?:just|simply)\b",
    r"\bnot\s+\w[\w\s'-]{0,40}?,\s*but\s+\w",
    r"\brather than (?:merely|simply|just)\b",
    r"\bisn'?t about\s+\w[\w\s'-]{0,40}?\.\s*(?:It|It'?s)\b",
]

TRAILING_PARTICIPLES = [
    "highlighting", "underscoring", "reflecting", "emphasizing",
    "showcasing", "demonstrating", "cementing", "solidifying",
    "ensuring", "fostering", "cultivating", "encompassing",
    "enhancing", "symbolizing", "signaling", "marking",
    "contributing to", "paving the way", "allowing for",
    "making it", "helping to",
]

COPULA_AVOIDANCE = [
    r"\bserves? as\b", r"\bstands? as\b", r"\bfunctions? as\b",
    r"\brepresents? an?\b", r"\bmarks? an?\b", r"\bremains? an?\b",
    r"\bboasts? an?\b", r"\bfeatures? an?\b", r"\bconstitutes? an?\b",
    r"\bemerges? as\b", r"\bpositions? (?:itself|themselves) as\b",
]

THROAT_CLEARING = [
    r"\bin today'?s (?:fast-paced|digital|modern|ever-changing|competitive)\b",
    r"\bin the (?:ever-)?(?:evolving|changing|shifting) (?:world|landscape|realm|field)\b",
    r"\bin an era (?:of|where)\b",
    r"\bin the (?:world|age|realm) of\b",
    r"\bwhen it comes to\b",
    r"\bit'?s no secret that\b",
    r"\blet'?s (?:face it|be honest|be clear|dive in|explore|take a look)\b",
    r"\bhere(?:'?s| is) the thing\b",
    r"\bthe (?:truth|reality|fact) is\b",
    r"\bwe'?ve all been there\b",
    r"\bimagine (?:a|an|this|for a moment)\b",
    r"\bpicture this\b",
    r"\bhas become increasingly (?:important|popular|common|prevalent)\b",
    r"\bplays? a (?:vital|crucial|key|pivotal|significant) role\b",
]

VAGUE_AUTHORITY = [
    r"\b(?:experts?|researchers?|scientists?|analysts?|observers?|critics?)\s+"
    r"(?:say|says|said|argue|argues|argued|note|notes|noted|suggest|suggests|"
    r"believe|believes|contend|contends|point out|have (?:noted|argued|suggested))\b",
    r"\b(?:studies|research|reports?|surveys?|data)\s+"
    r"(?:show|shows|shown|suggest|suggests|indicate|indicates|reveal|reveals|"
    r"confirm|confirms|demonstrate|demonstrates|found|find)\b",
    r"\b(?:industry|market|recent|several|various|numerous)\s+"
    r"(?:reports?|studies|sources|analyses|observers)\b",
    r"\bit is (?:widely|generally|commonly) (?:believed|accepted|known|recognized)\b",
    r"\bmany (?:people|experts|believe|argue|consider)\b",
    r"\bsome (?:critics|experts|observers|argue|say|believe)\b",
]

TRANSITIONS = [
    "furthermore", "moreover", "additionally", "however", "in addition",
    "nevertheless", "nonetheless", "consequently", "therefore", "thus",
    "similarly", "likewise", "in contrast", "on the other hand",
    "that said", "notably", "importantly", "indeed", "overall",
    "ultimately", "meanwhile", "subsequently", "accordingly",
]

CONCLUSION_REFLEX = [
    r"^in conclusion\b", r"^in summary\b", r"^to sum(?:marize| up)\b",
    r"^ultimately,", r"^at the end of the day\b", r"^in essence\b",
    r"^all in all\b", r"^to conclude\b", r"^in short\b",
    r"^the bottom line is\b", r"^whether you'?re\b",
]

HEDGE_BOILERPLATE = [
    r"\bit'?s (?:worth|important) (?:noting|to note|to remember|to mention)\b",
    r"\bit should be noted\b",
    # Require a clause boundary: "that said," not "a note that said ...".
    r"(?:^|(?<=[.!?]\s)|(?<=\n))\s*That (?:being )?said,",
    r"\bgenerally speaking\b",
    r"\bin many (?:ways|cases|respects)\b",
    r"\bto some extent\b",
    r"\bwhile .{0,50}, it'?s (?:also|equally|still)\b",
    r"\bcan be a (?:double-edged sword|game[- ]changer)\b",
    r"\bthere'?s no one-size-fits-all\b",
    r"\bnot a silver bullet\b",
]

PUFFERY = [
    r"\bnestled (?:in|within|among|between)\b",
    r"\bin the heart of\b",
    r"\brenowned for\b",
    r"\bworld-class\b", r"\bstate-of-the-art\b", r"\bbest-in-class\b",
    r"\bleft an indelible mark\b",
    r"\breflects? (?:a )?broader\b",
    r"\ba (?:key|major|significant) turning point\b",
    r"\bstands? out as\b",
    r"\bcontinues? to (?:evolve|inspire|shape|grow)\b",
    r"\bhas (?:come a long way|only just begun)\b",
]

ABBREVIATIONS = {
    "dr", "mr", "mrs", "ms", "prof", "sr", "jr", "st", "vs", "etc",
    "eg", "ie", "cf", "al", "fig", "no", "inc", "ltd", "co", "corp",
    "approx", "est", "dept", "univ", "ed", "eds", "vol", "pp", "ch",
}

UNICODE_ARTIFACTS = {
    "‘": "left single curly quote",
    "’": "right single curly quote / apostrophe",
    "“": "left double curly quote",
    "”": "right double curly quote",
    "→": "rightwards arrow",
    "✓": "check mark",
    "✔": "heavy check mark",
    " ": "non-breaking space",
    "‑": "non-breaking hyphen",
    "…": "horizontal ellipsis",
    "•": "bullet",
    "️": "variation selector (emoji presentation)",
}

# --------------------------------------------------------------------------
# Preprocessing
# --------------------------------------------------------------------------


class Document:
    """Holds the raw text plus a prose view with markup masked out.

    Masking replaces non-prose spans with spaces of equal length, so every
    offset in the prose view still maps to the same offset in the raw text.
    That keeps line numbers exact without any offset bookkeeping.
    """

    def __init__(self, raw, path):
        self.raw = raw
        self.path = path
        self.lines = raw.split("\n")
        self._line_starts = self._compute_line_starts(raw)
        self.prose = self._build_prose_view(raw)
        self.masked_spans = self._masked_span_count

    @staticmethod
    def _compute_line_starts(raw):
        starts = [0]
        for i, ch in enumerate(raw):
            if ch == "\n":
                starts.append(i + 1)
        return starts

    def line_of(self, offset):
        """1-indexed line number for a character offset."""
        lo, hi = 0, len(self._line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._line_starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    def _build_prose_view(self, raw):
        text = list(raw)
        count = 0

        def mask(start, end):
            nonlocal count
            for i in range(start, min(end, len(text))):
                if text[i] != "\n":
                    text[i] = " "
            count += 1

        # YAML front matter
        fm = re.match(r"\A---\n.*?\n---\n", raw, re.S)
        if fm:
            mask(fm.start(), fm.end())

        # Fenced code blocks (``` and ~~~), including unterminated ones.
        for m in re.finditer(
            r"^(```|~~~).*?(?:\n(?:.*?)\n\1\s*$|\Z)", raw, re.S | re.M
        ):
            mask(m.start(), m.end())

        # Indented code blocks: 4+ spaces at line start, not inside a list.
        for m in re.finditer(r"^(?: {4,}|\t)\S.*$", raw, re.M):
            mask(m.start(), m.end())

        # Inline code
        for m in re.finditer(r"`[^`\n]+`", raw):
            mask(m.start(), m.end())

        # Markdown tables (any line that is pipe-delimited)
        for m in re.finditer(r"^\s*\|.*\|\s*$", raw, re.M):
            mask(m.start(), m.end())

        # Bare URLs and link targets
        for m in re.finditer(r"https?://\S+|\]\([^)]*\)", raw):
            mask(m.start(), m.end())

        # HTML tags and comments
        for m in re.finditer(r"<!--.*?-->|</?[a-zA-Z][^>\n]*>", raw, re.S):
            mask(m.start(), m.end())

        # Footnote/citation markers
        for m in re.finditer(r"\[\^[^\]]+\]|\[\d+\]", raw):
            mask(m.start(), m.end())

        self._masked_span_count = count
        return "".join(text)


def strip_markdown_emphasis(text):
    """Remove emphasis markers and heading/list prefixes for word counting."""
    text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text, flags=re.M)
    text = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", text, flags=re.M)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.M)
    text = re.sub(r"(\*\*|__|\*|_)", "", text)
    return text


WORD_RE = re.compile(r"\b[\w'’-]+\b", re.UNICODE)


def words_of(text):
    return WORD_RE.findall(text)


def split_sentences(text):
    """Split prose into (offset, sentence) pairs, guarding abbreviations."""
    sentences = []
    start = 0
    for m in re.finditer(r"([.!?]+)([\"'’”)\]]*)(\s+|\Z)", text):
        end = m.end(2)
        preceding = text[max(0, m.start() - 12):m.start()]
        token = re.search(r"([\w'’-]+)\Z", preceding)
        if token:
            word = token.group(1).lower().replace(".", "")
            if word in ABBREVIATIONS:
                continue
            if len(word) == 1 and word.isalpha():  # initials: "J. R. R."
                continue
        if m.group(1) == "." and re.match(r"\s*[a-z]", text[end:end + 4]):
            continue
        chunk = text[start:end]
        if chunk.strip():
            sentences.append((start + len(chunk) - len(chunk.lstrip()),
                              chunk.strip()))
        start = m.end()
    tail = text[start:]
    if tail.strip():
        sentences.append((start + len(tail) - len(tail.lstrip()), tail.strip()))
    return sentences


def split_paragraphs(doc):
    """Return prose paragraphs as (index, offset, text) tuples."""
    paras = []
    idx = 0
    for m in re.finditer(r"[^\n]+(?:\n[^\n]+)*", doc.prose):
        chunk = m.group(0)
        if not chunk.strip():
            continue
        # Skip headings, list-only blocks, and horizontal rules.
        stripped = strip_markdown_emphasis(chunk).strip()
        if not stripped or len(words_of(stripped)) < 3:
            continue
        paras.append((idx, m.start(), chunk))
        idx += 1
    return paras


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------

SEVERITY_WEIGHT = {"info": 1.0, "elevated": 2.0, "flag": 3.5}


class Finding:
    def __init__(self, key, title, severity, value, baseline, note="", hits=None):
        self.key = key
        self.title = title
        self.severity = severity
        self.value = value
        self.baseline = baseline
        self.note = note
        self.hits = hits or []
        self.cluster_bonus = 0.0

    @property
    def score(self):
        n = len(self.hits) or 1
        return (SEVERITY_WEIGHT[self.severity] * math.log(1 + n)
                + self.cluster_bonus)

    def to_dict(self):
        return {
            "pattern": self.key,
            "title": self.title,
            "severity": self.severity,
            "value": self.value,
            "baseline": self.baseline,
            "note": self.note,
            "score": round(self.score, 3),
            "count": len(self.hits),
            "hits": self.hits,
        }


def hit(doc, offset, text, extra=None):
    line = doc.line_of(offset)
    entry = {
        "line": line,
        "offset": offset,
        "text": text.strip(),
        "context": doc.lines[line - 1].strip()[:200],
    }
    if extra:
        entry.update(extra)
    return entry


def scan_regexes(doc, patterns, flags=re.I):
    hits = []
    for pat in patterns:
        for m in re.finditer(pat, doc.prose, flags):
            if not m.group(0).strip():
                continue
            hits.append(hit(doc, m.start(), m.group(0), {"pattern": pat}))
    hits.sort(key=lambda h: h["offset"])
    return hits


def band(value, elevated_at, flag_at, higher_is_worse=True):
    if higher_is_worse:
        if value > flag_at:
            return "flag"
        if value > elevated_at:
            return "elevated"
    else:
        if value < flag_at:
            return "flag"
        if value < elevated_at:
            return "elevated"
    return "info"


# --------------------------------------------------------------------------
# Individual checks
# --------------------------------------------------------------------------


def check_em_dash(doc, stats):
    hits = []
    for m in re.finditer(r"—|\s--\s|\s–\s", doc.prose):
        hits.append(hit(doc, m.start(), m.group(0)))
    rate = 1000.0 * len(hits) / max(stats["words"], 1)
    sev = band(rate, 10, 20)
    note = ("Human prose averages 3.7-10 per 1k words; GPT-4.1 measured 10.6. "
            "Rate alone is weak evidence - check whether the dashes vary in "
            "function or always sit in the same parenthetical rhythm.")
    return Finding("em_dash_density", "Em dash density", sev,
                   f"{rate:.1f} per 1k words ({len(hits)} total)",
                   "3.7-10 per 1k words", note, hits)


def check_burstiness(doc, stats):
    lengths = stats["sentence_lengths"]
    if len(lengths) < 10:
        return Finding("burstiness", "Sentence length variance (burstiness)",
                       "info", "n/a", "0.6-1.2",
                       f"Only {len(lengths)} sentences; too few to be "
                       "meaningful. Needs 10+.", [])
    mean = statistics.mean(lengths)
    sd = statistics.pstdev(lengths)
    b = sd / mean if mean else 0.0
    sev = band(b, 0.6, 0.4, higher_is_worse=False)
    note = ("Human prose spreads 0.6-1.2 - short declaratives punctuated by "
            "long clausal sentences. LLM output clusters 0.2-0.4. This is the "
            "single most robust structural signal.")
    return Finding("burstiness", "Sentence length variance (burstiness)", sev,
                   f"{b:.2f} (mean {mean:.1f}, sd {sd:.1f})", "0.6-1.2",
                   note, [])


def check_metronome(doc, stats):
    lengths = stats["sentence_lengths"]
    if len(lengths) < 10:
        return None
    median = statistics.median(lengths)
    mean = statistics.mean(lengths)
    sd = statistics.pstdev(lengths)
    b = sd / mean if mean else 1.0
    in_band = 14 <= median <= 22
    sev = "flag" if (in_band and b < 0.45) else (
        "elevated" if in_band and b < 0.6 else "info")
    return Finding("metronomic_median", "Metronomic sentence length", sev,
                   f"median {median:.0f} words",
                   "varied; 14-22 with low variance is the LLM signature",
                   "Flagged only when the median sits in the LLM band AND "
                   "variance is low - median alone means nothing.", [])


def check_excess_vocabulary(doc, stats):
    hits = []
    for m in WORD_RE.finditer(doc.prose):
        w = m.group(0).lower().strip("'’")
        if w in EXCESS_WORDS:
            hits.append(hit(doc, m.start(), m.group(0), {"word": w}))
    for m in re.finditer("|".join(EXCESS_PHRASES), doc.prose, re.I):
        hits.append(hit(doc, m.start(), m.group(0), {"word": m.group(0).lower()}))
    hits.sort(key=lambda h: h["offset"])
    rate = 500.0 * len(hits) / max(stats["words"], 1)
    sev = band(rate, 3, 6)
    counts = Counter(h["word"] for h in hits)
    note = ("Words whose frequency spiked in 2024 abstracts vs. the 2021-22 "
            "trend line ('delves' at 25x expected). Check each against the "
            "subject matter - 'robust' in statistics is the right word.")
    f = Finding("excess_vocabulary", "Excess vocabulary", sev,
                f"{rate:.1f} per 500 words ({len(hits)} total)",
                "<=3 per 500 words", note, hits)
    f.top = counts.most_common(12)
    return f


def check_verb_inflation(doc, stats):
    hits = []
    for m in WORD_RE.finditer(doc.prose):
        w = m.group(0).lower()
        if w in INFLATED_VERBS:
            hits.append(hit(doc, m.start(), m.group(0),
                            {"plain": INFLATED_VERBS[w]}))
    rate = 300.0 * len(hits) / max(stats["words"], 1)
    sev = band(rate, 1, 2.5)
    return Finding("verb_inflation", "Corporate verb inflation", sev,
                   f"{rate:.1f} per 300 words ({len(hits)} total)",
                   "<=1 per 300 words",
                   "A plainer verb was available and was passed over.", hits)


def check_negative_parallelism(doc, stats):
    hits = scan_regexes(doc, NEGATIVE_PARALLELISM)
    sev = "flag" if len(hits) >= 3 else ("elevated" if len(hits) >= 1 else "info")
    return Finding("negative_parallelism",
                   "Negative parallelism (\"not just X, but Y\")", sev,
                   f"{len(hits)} occurrences", "0-2 per document",
                   "The reversal template. One is rhetoric; three is a tic.",
                   hits)


def check_trailing_participle(doc, stats):
    alts = "|".join(re.escape(p) for p in TRAILING_PARTICIPLES)
    hits = []
    for offset, sentence in stats["sentences_abs"]:
        m = re.search(r",\s+(" + alts + r")\b[^.!?]*[.!?]?\s*$", sentence, re.I)
        if m:
            hits.append(hit(doc, offset + m.start(), m.group(0)))
    sev = "flag" if len(hits) >= 4 else ("elevated" if len(hits) >= 2 else "info")
    return Finding("trailing_participle",
                   "Trailing participial summary", sev,
                   f"{len(hits)} sentences", "rare",
                   "Sentences that end by restating their own significance "
                   "(\"..., underscoring the broader shift\"). Almost always "
                   "deletable without information loss.", hits)


def check_copula_avoidance(doc, stats):
    hits = scan_regexes(doc, COPULA_AVOIDANCE)
    rate = 1000.0 * len(hits) / max(stats["words"], 1)
    sev = "flag" if len(hits) >= 5 else ("elevated" if len(hits) >= 3 else "info")
    return Finding("copula_avoidance", "Copula avoidance", sev,
                   f"{len(hits)} occurrences ({rate:.1f} per 1k words)",
                   "occasional",
                   "\"serves as / stands as / represents a\" where \"is\" "
                   "would do; \"boasts / features\" where \"has\" would do.",
                   hits)


def check_throat_clearing(doc, stats):
    hits = scan_regexes(doc, THROAT_CLEARING)
    rate = 500.0 * len(hits) / max(stats["words"], 1)
    sev = band(rate, 1, 2)
    return Finding("throat_clearing", "Throat-clearing openers", sev,
                   f"{rate:.1f} per 500 words ({len(hits)} total)",
                   "<=1 per 500 words",
                   "Filler that delays the first real claim.", hits)


def check_vague_authority(doc, stats):
    raw_hits = scan_regexes(doc, VAGUE_AUTHORITY)
    hits = []
    for h in raw_hits:
        window = doc.prose[h["offset"]:h["offset"] + 220]
        # Stop at the paragraph break. A number in the *next* paragraph belongs
        # to a different claim and must not redeem this one.
        window = re.split(r"\n\s*\n", window)[0]
        # A nearby citation, year, figure, or proper name redeems the claim.
        cited = bool(re.search(r"\d{4}|\d+\s?%|\[\d|\(\w+,?\s*\d{4}\)|"
                               r"et al\.|https?://|doi", window, re.I))
        h["cited_nearby"] = cited
        if not cited:
            hits.append(h)
    sev = "flag" if len(hits) >= 3 else ("elevated" if hits else "info")
    return Finding("vague_authority", "Uncited authority", sev,
                   f"{len(hits)} uncited of {len(raw_hits)} total",
                   "every authority claim carries a name, number, or link",
                   "\"Experts say\" / \"studies show\" with no number, name, "
                   "or link within 220 characters.", hits)


def check_transition_stacking(doc, stats):
    paras = stats["paragraphs"]
    if not paras:
        return None
    alts = "|".join(re.escape(t) for t in TRANSITIONS)
    hits = []
    for idx, offset, chunk in paras:
        head = strip_markdown_emphasis(chunk).lstrip()
        m = re.match(r"(" + alts + r")\b[,\s]", head, re.I)
        if m:
            hits.append(hit(doc, offset, m.group(1), {"paragraph": idx}))
    pct = 100.0 * len(hits) / len(paras)
    sev = band(pct, 30, 50)
    return Finding("transition_stacking", "Transition-word stacking", sev,
                   f"{pct:.0f}% of paragraphs ({len(hits)}/{len(paras)})",
                   "<30% of paragraphs",
                   "Paragraphs opening with a formal connective. Signals "
                   "sequencing applied after the fact rather than an argument "
                   "that actually flows.", hits)


def check_paragraph_uniformity(doc, stats):
    counts = stats["paragraph_sentence_counts"]
    if len(counts) < 5:
        return None
    mean = statistics.mean(counts)
    sd = statistics.pstdev(counts)
    ratio = sd / mean if mean else 0.0
    mode = Counter(counts).most_common(1)[0][0]
    sev = "flag" if (ratio < 0.35 and 2 <= mode <= 4) else (
        "elevated" if ratio < 0.5 else "info")
    return Finding("paragraph_uniformity", "Paragraph uniformity", sev,
                   f"ratio {ratio:.2f} (mean {mean:.1f} sentences, mode {mode})",
                   ">0.5",
                   "Every paragraph the same shape. Human paragraphs vary with "
                   "what they have to say.", [])


def check_vocabulary_range(doc, stats):
    words = [w.lower() for w in words_of(strip_markdown_emphasis(doc.prose))]
    window = 500
    if len(words) < window:
        if not words:
            return None
        ttr = len(set(words)) / len(words)
        return Finding("vocabulary_range", "Vocabulary range (TTR)", "info",
                       f"{ttr:.3f} over {len(words)} words",
                       "supporting signal only",
                       "Text shorter than the 500-word window; not comparable.",
                       [])
    ratios = []
    for i in range(0, len(words) - window + 1, 25):
        chunk = words[i:i + window]
        ratios.append(len(set(chunk)) / window)
    mattr = statistics.mean(ratios)
    sev = "elevated" if mattr < 0.42 else "info"
    return Finding("vocabulary_range", "Vocabulary range (MATTR)", sev,
                   f"{mattr:.3f} over 500-word windows",
                   "~0.45-0.55 typical",
                   "Supporting signal only - never flag on this alone. "
                   "Length-independent by construction.", [])


def check_unicode(doc, stats):
    hits = []
    counts = Counter()
    for i, ch in enumerate(doc.raw):
        if ch in UNICODE_ARTIFACTS:
            counts[ch] += 1
            if counts[ch] <= 5:
                hits.append(hit(doc, i, ch, {"name": UNICODE_ARTIFACTS[ch]}))
        elif ord(ch) > 0x2500 and unicodedata.category(ch) == "So":
            counts[ch] += 1
            if counts[ch] <= 5:
                hits.append(hit(doc, i, ch,
                                {"name": unicodedata.name(ch, "symbol")}))
    total = sum(counts.values())
    sev = "elevated" if total else "info"
    summary = ", ".join(f"{UNICODE_ARTIFACTS.get(c, c)} x{n}"
                        for c, n in counts.most_common(8))
    return Finding("unicode_artifacts", "Unicode artifacts", sev,
                   f"{total} characters" + (f" - {summary}" if summary else ""),
                   "depends on the authoring tool",
                   "Curly quotes and arrows are a tell only when the "
                   "surrounding workflow produces straight ASCII. Weak on its "
                   "own.", hits)


def check_conclusion_reflex(doc, stats):
    paras = stats["paragraphs"]
    if not paras:
        return None
    hits = []
    for idx, offset, chunk in paras:
        head = strip_markdown_emphasis(chunk).lstrip()
        for pat in CONCLUSION_REFLEX:
            m = re.match(pat, head, re.I)
            if m:
                hits.append(hit(doc, offset, m.group(0),
                                {"paragraph": idx,
                                 "final_third": idx >= 2 * len(paras) / 3}))
                break
    sev = "flag" if len(hits) >= 2 else ("elevated" if hits else "info")
    return Finding("conclusion_reflex", "Summary/conclusion reflex", sev,
                   f"{len(hits)} occurrences", "0",
                   "Restating what was just said instead of ending on "
                   "something new.", hits)


def check_hedging(doc, stats):
    hits = scan_regexes(doc, HEDGE_BOILERPLATE)
    sev = "flag" if len(hits) >= 4 else ("elevated" if len(hits) >= 2 else "info")
    return Finding("hedge_boilerplate", "Hedge boilerplate", sev,
                   f"{len(hits)} occurrences", "<=1",
                   "Softening phrases that carry no content.", hits)


def check_puffery(doc, stats):
    hits = scan_regexes(doc, PUFFERY)
    sev = "flag" if len(hits) >= 3 else ("elevated" if hits else "info")
    return Finding("puffery", "Puffery / significance inflation", sev,
                   f"{len(hits)} occurrences", "0",
                   "Brochure register: asserting importance rather than "
                   "showing it.", hits)


# An item may carry a comparative intensifier ("more reliable"); capture the
# head word, which is what decides whether the triplet is rhetorical.
_TRI_ITEM = r"(?:(?:more|less|most|least|very|highly|far)\s+)?([A-Za-z][\w-]{2,16})"

TRICOLON_RE = re.compile(
    r"\b" + _TRI_ITEM + r"\s*,\s+" + _TRI_ITEM + r"\s*,\s+"
    r"(?:and|or)\s+" + _TRI_ITEM + r"\b"
)

# Suffixes that mark an adjective or an abstract noun. The autopilot tricolon
# stacks these; an enumeration of concrete things ("bikes, trees, and boats")
# does not.
_RHETORICAL_SUFFIXES = (
    # adjectival
    "ive", "ous", "ful", "able", "ible", "ic", "al", "ing", "ed", "less",
    "ary", "ish", "ent", "ant", "ile", "ory", "er", "est",
    # abstract nominal
    "tion", "sion", "ment", "ity", "ness", "ance", "ence", "ism", "ship",
    "hood", "cy", "logy",
)

# Short adjectives with no distinguishing suffix.
_PLAIN_ADJECTIVES = {
    "big", "small", "fast", "slow", "new", "old", "good", "bad", "cheap",
    "quick", "clean", "clear", "safe", "strong", "simple", "smart", "bold",
    "rich", "deep", "warm", "cool", "dry", "soft", "hard", "light", "dark",
    "free", "full", "thin", "wide", "long", "short", "high", "low", "sharp",
    "smooth", "solid", "sound", "true", "real", "fair", "keen", "lean",
}

# If one of these lands in an item slot the regex mis-parsed the phrase.
_TRI_STOPWORDS = {
    "the", "and", "or", "but", "for", "nor", "yet", "its", "his", "her",
    "their", "our", "your", "this", "that", "these", "those", "some", "many",
    "most", "much", "other", "such", "any", "all", "both", "each", "more",
    "one", "two", "with", "from", "into", "onto", "than", "then", "was",
    "were", "are", "has", "had", "have", "not", "who", "whose", "which",
}


def _is_rhetorical_item(word):
    w = word.lower()
    if w in _PLAIN_ADJECTIVES:
        return True
    return any(w.endswith(s) and len(w) > len(s) + 1
               for s in _RHETORICAL_SUFFIXES)


def check_tricolon(doc, stats):
    list_item_lines = {doc.line_of(m.start())
                       for m in re.finditer(r"^\s*(?:[-*+]|\d+[.)])\s+",
                                            doc.raw, re.M)}
    hits = []
    skipped = 0
    for m in TRICOLON_RE.finditer(doc.prose):
        parts = [m.group(1), m.group(2), m.group(3)]

        # A mis-parse: a function word landed in an item slot.
        if any(p.lower() in _TRI_STOPWORDS for p in parts):
            continue

        # Proper-noun enumeration ("Keizersgracht, Herengracht, and Singel").
        # Slots 2 and 3 are always mid-sentence, so a capital there is a name.
        if parts[1][0].isupper() or parts[2][0].isupper():
            skipped += 1
            continue

        # Shot lists, ingredient lists, and feature bullets are enumerations
        # by construction, not rhetoric.
        if doc.line_of(m.start()) in list_item_lines:
            skipped += 1
            continue

        # The tell is stacked adjectives or abstract nouns, not a list of
        # concrete things. Require a majority of the heads to look rhetorical.
        if sum(_is_rhetorical_item(p) for p in parts) < 2:
            skipped += 1
            continue

        hits.append(hit(doc, m.start(), m.group(0), {"items": parts}))

    rate = 200.0 * len(hits) / max(stats["words"], 1)
    sev = band(rate, 1, 2)
    note = ("Three-item lists where the third adds nothing, stacking "
            "adjectives or abstract nouns. Enumerations of concrete things, "
            "proper nouns, and list items are excluded. Deliberate tricolon "
            "in persuasive writing is legitimate - read each one.")
    if skipped:
        note += f" ({skipped} enumeration(s) excluded.)"
    return Finding("tricolon", "Rule of three on autopilot", sev,
                   f"{rate:.1f} per 200 words ({len(hits)} total)",
                   "<=1 per 200 words", note, hits)


# --- markdown structure (raw view) ----------------------------------------


def check_markdown(doc, stats):
    raw = doc.raw
    sub = []
    words = max(stats["words"], 1)

    # Bold inside table cells and definition-list bullets is ordinary doc
    # formatting, not prose decoration. Only count bold in running text.
    table_lines = {doc.line_of(m.start())
                   for m in re.finditer(r"^\s*\|.*\|\s*$", raw, re.M)}
    bold = [m for m in re.finditer(r"\*\*[^*\n]{2,80}\*\*|__[^_\n]{2,80}__", raw)
            if doc.line_of(m.start()) not in table_lines]
    bold_rate = 100.0 * len(bold) / words
    if bold_rate > 1.5:
        sub.append(("bold_overuse",
                    f"{len(bold)} bold runs ({bold_rate:.1f} per 100 words)",
                    "flag" if bold_rate > 3 else "elevated",
                    [hit(doc, m.start(), m.group(0)) for m in bold[:20]]))

    headings = list(re.finditer(r"^(#{1,6})\s+(.+)$", raw, re.M))

    title_case = []
    for m in headings:
        text = re.sub(r"[*_`]", "", m.group(2)).strip()
        tokens = [t for t in text.split() if re.match(r"^[A-Za-z]", t)]
        if len(tokens) >= 3:
            minor = {"a", "an", "the", "and", "or", "but", "of", "in", "on",
                     "to", "for", "with", "at", "by", "from", "as", "is"}
            capped = [t for t in tokens[1:]
                      if t[0].isupper() and t.lower() not in minor]
            eligible = [t for t in tokens[1:] if t.lower() not in minor]
            if eligible and len(capped) / len(eligible) > 0.8:
                title_case.append(m)
    if title_case:
        sub.append(("title_case_headings",
                    f"{len(title_case)} of {len(headings)} headings",
                    "flag" if len(title_case) > 2 else "elevated",
                    [hit(doc, m.start(), m.group(0)) for m in title_case[:20]]))

    emoji = []
    for m in re.finditer(r"^(?:\s*(?:[-*+]|\d+[.)])\s+|#{1,6}\s+)(\S)", raw, re.M):
        ch = m.group(1)
        if ord(ch) > 0x2100 and unicodedata.category(ch) in ("So", "Sk"):
            emoji.append(m)
    if emoji:
        sub.append(("emoji_decoration",
                    f"{len(emoji)} headings/bullets open with an emoji",
                    "flag" if len(emoji) > 3 else "elevated",
                    [hit(doc, m.start(), m.group(0)) for m in emoji[:20]]))

    rules = list(re.finditer(r"^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$", raw, re.M))
    # The first one may be front matter; already masked, but be safe.
    rules = [m for m in rules if m.start() > 4]
    if len(rules) >= 3:
        sub.append(("thematic_breaks",
                    f"{len(rules)} horizontal rules",
                    "flag" if len(rules) > 5 else "elevated",
                    [hit(doc, m.start(), m.group(0)) for m in rules[:20]]))

    empty_sections = []
    skipped = []
    prev_level = None
    for i, m in enumerate(headings):
        level = len(m.group(1))
        if prev_level is not None and level > prev_level + 1:
            skipped.append(m)
        prev_level = level
        nxt = headings[i + 1].start() if i + 1 < len(headings) else len(raw)
        body = raw[m.end():nxt].strip()
        # A parent heading followed by its own subsection is normal nesting.
        # Only an empty section at the same or higher level is a real tell.
        deeper_next = (i + 1 < len(headings)
                       and len(headings[i + 1].group(1)) > level)
        if not body and not deeper_next:
            empty_sections.append(m)
    if empty_sections:
        sub.append(("heading_only_sections",
                    f"{len(empty_sections)} headings with no body",
                    "elevated",
                    [hit(doc, m.start(), m.group(0))
                     for m in empty_sections[:20]]))
    if skipped:
        sub.append(("skipped_heading_levels",
                    f"{len(skipped)} level jumps",
                    "elevated",
                    [hit(doc, m.start(), m.group(0)) for m in skipped[:20]]))

    tables = re.findall(r"(?:^\s*\|.*\|\s*$\n?){2,}", raw, re.M)
    thin = [t for t in tables if len(t.strip().split("\n")) <= 3]
    if thin:
        sub.append(("thin_tables",
                    f"{len(thin)} tables with <=1 data row",
                    "elevated", []))

    if not sub:
        return Finding("markdown_structure", "Markdown structure", "info",
                       "no structural tells", "-",
                       "Bold density, heading case, emoji decoration, rules, "
                       "empty sections, and thin tables all within range.", [])

    worst = "flag" if any(s[2] == "flag" for s in sub) else "elevated"
    hits = [h for s in sub for h in s[3]]
    value = "; ".join(f"{name}: {desc}" for name, desc, _, _ in sub)
    f = Finding("markdown_structure", "Markdown structure", worst, value, "-",
                "Formatting applied as decoration rather than meaning.", hits)
    f.subchecks = [{"check": n, "detail": d, "severity": s} for n, d, s, _ in sub]
    return f


CHECKS = [
    check_em_dash,
    check_burstiness,
    check_metronome,
    check_excess_vocabulary,
    check_verb_inflation,
    check_negative_parallelism,
    check_tricolon,
    check_trailing_participle,
    check_copula_avoidance,
    check_throat_clearing,
    check_vague_authority,
    check_transition_stacking,
    check_paragraph_uniformity,
    check_vocabulary_range,
    check_unicode,
    check_conclusion_reflex,
    check_hedging,
    check_puffery,
    check_markdown,
]


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def build_stats(doc):
    clean = strip_markdown_emphasis(doc.prose)
    all_words = words_of(clean)
    paragraphs = split_paragraphs(doc)

    sentences_abs = []
    para_counts = []
    for _, offset, chunk in paragraphs:
        sents = split_sentences(chunk)
        para_counts.append(max(len(sents), 1))
        for s_off, s_text in sents:
            sentences_abs.append((offset + s_off, s_text))

    lengths = []
    for _, s_text in sentences_abs:
        n = len(words_of(strip_markdown_emphasis(s_text)))
        if n:
            lengths.append(n)

    return {
        "words": len(all_words),
        "sentences_abs": sentences_abs,
        "sentence_lengths": lengths,
        "paragraphs": paragraphs,
        "paragraph_sentence_counts": para_counts,
    }


# Weak signals per REFERENCE section D. They may appear in a report, but they
# must never be one of the patterns that makes a paragraph a convergence hit.
WEAK_FOR_CONVERGENCE = {
    "em_dash_density",
    "unicode_artifacts",
    "vocabulary_range",
    "markdown_structure",
}


def build_clusters(doc, findings, stats):
    """Group hits by paragraph; report paragraphs with 3+ distinct patterns."""
    paras = stats["paragraphs"]
    if not paras:
        return []
    bounds = []
    for idx, offset, chunk in paras:
        bounds.append((offset, offset + len(chunk), idx))

    def para_of(offset):
        for start, end, idx in bounds:
            if start <= offset < end:
                return idx
        return None

    buckets = {}
    for f in findings:
        # Severity is a document-wide rate; convergence is per paragraph. A
        # pattern occurring twice in the whole text, both times in one
        # paragraph, is stronger evidence for that paragraph rather than
        # weaker, so hits count here regardless of the document-level band.
        # Only the inherently weak signals of REFERENCE section D are held out,
        # since they should never be what makes a paragraph look hot.
        if f.key in WEAK_FOR_CONVERGENCE:
            continue
        for h in f.hits:
            p = para_of(h["offset"])
            if p is None:
                continue
            buckets.setdefault(p, {}).setdefault(f.key, []).append(h["line"])

    clusters = []
    for p, patterns in buckets.items():
        if len(patterns) < 3:
            continue
        _, offset, chunk = paras[p]
        clusters.append({
            "paragraph": p,
            "line": doc.line_of(offset),
            "distinct_patterns": len(patterns),
            "total_hits": sum(len(v) for v in patterns.values()),
            "patterns": sorted(patterns),
            "excerpt": " ".join(strip_markdown_emphasis(chunk).split())[:300],
        })
    clusters.sort(key=lambda c: (-c["distinct_patterns"], -c["total_hits"]))

    # Feed convergence back into ranking.
    hot = {k for c in clusters for k in c["patterns"]}
    for f in findings:
        if f.key in hot:
            f.cluster_bonus = 1.5
    return clusters


def analyze(path):
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    doc = Document(raw, path)
    stats = build_stats(doc)

    findings = []
    for check in CHECKS:
        try:
            f = check(doc, stats)
        except Exception as exc:  # a broken check must not sink the report
            f = Finding(check.__name__, check.__name__, "info", "error",
                        "-", f"check failed: {exc}", [])
        if f is not None:
            findings.append(f)

    clusters = build_clusters(doc, findings, stats)
    findings.sort(key=lambda f: -f.score)

    flags = sum(1 for f in findings if f.severity == "flag")
    elevated = sum(1 for f in findings if f.severity == "elevated")

    return {
        "file": path,
        "words": stats["words"],
        "sentences": len(stats["sentence_lengths"]),
        "paragraphs": len(stats["paragraphs"]),
        "counts": {"flag": flags, "elevated": elevated,
                   "info": len(findings) - flags - elevated},
        "findings": [f.to_dict() for f in findings],
        "clusters": clusters,
    }


MARK = {"flag": "FLAG", "elevated": "ELEV", "info": "ok  "}


def render_text(result, full=False):
    out = []
    out.append(f"{result['file']}  -  {result['words']} words, "
               f"{result['sentences']} sentences, "
               f"{result['paragraphs']} paragraphs")
    c = result["counts"]
    out.append(f"{c['flag']} flagged, {c['elevated']} elevated, "
               f"{c['info']} within range")
    out.append("")

    width = max((len(f["title"]) for f in result["findings"]), default=10)
    for f in result["findings"]:
        out.append(f"{MARK[f['severity']]}  {f['title']:<{width}}  {f['value']}")
        if f["severity"] != "info":
            out.append(f"      baseline: {f['baseline']}")
        shown = f["hits"] if full else f["hits"][:6]
        for h in shown:
            out.append(f"      L{h['line']:<5} {h['text'][:90]}")
        if not full and len(f["hits"]) > 6:
            out.append(f"      ... {len(f['hits']) - 6} more "
                       f"(use --full to list)")
        if f["severity"] != "info" or f["hits"]:
            out.append("")

    if result["clusters"]:
        out.append("Convergence - paragraphs carrying 3+ distinct patterns:")
        out.append("")
        for cl in result["clusters"]:
            out.append(f"  L{cl['line']}  {cl['distinct_patterns']} patterns, "
                       f"{cl['total_hits']} hits: {', '.join(cl['patterns'])}")
            out.append(f"       {cl['excerpt'][:160]}")
            out.append("")
    else:
        out.append("Convergence: no paragraph carries 3+ distinct patterns.")
        out.append("")

    out.append("No single signal is conclusive. Weigh the convergence section "
               "above the individual counts.")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="file to analyze")
    ap.add_argument("--json", action="store_true", help="structured output")
    ap.add_argument("--full", action="store_true", help="list every hit")
    args = ap.parse_args()

    try:
        result = analyze(args.path)
    except OSError as exc:
        print(f"cannot read {args.path}: {exc}", file=sys.stderr)
        return 0

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(render_text(result, full=args.full))
    return 0


if __name__ == "__main__":
    sys.exit(main())
