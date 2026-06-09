#!/usr/bin/env python3
"""
Extract timestamped transcripts from WWDC session web pages.

Parses the transcript section from a developer.apple.com session page
and returns a JSON array of {time, text} entries.
"""

import gzip
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request

# Developer.app caches per-session transcripts as JSON here. Each file is named
# "<event>-<session>.json" (e.g. "wwdc2026-269.json") and contains:
#   {"<event>-<session>": {"language": "eng",
#                          "transcript": [[start_seconds, "text "], ...]}}
TRANSCRIPT_CACHE_DIR = os.path.expanduser(
    "~/Library/Group Containers/group.developer.apple.wwdc/Library/Caches/Transcripts/ByID"
)


def fetch_url(url: str) -> bytes:
    """Fetch URL content, with SSL certificate fallback for macOS."""
    req = urllib.request.Request(url)
    req.add_header("Accept-Encoding", "gzip, deflate")
    try:
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLCertVerificationError):
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, context=ctx) as resp:
                data = resp.read()
        else:
            raise
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data


def extract_transcript(html: str) -> list[dict]:
    """Extract transcript entries from WWDC session HTML.

    Returns a list of dicts with 'time' (float seconds), 'text' (string),
    and 'paragraph' (bool, True if this entry starts a new paragraph).

    Paragraph boundaries are detected from <p> tags in the transcript HTML.
    """
    # Find the transcript section
    match = re.search(r'id="transcript-content">(.*?)</section>', html, re.DOTALL)
    if not match:
        raise ValueError("No transcript section found on page")

    transcript_html = match.group(1)

    # Split transcript into paragraphs by <p> tags, then extract spans from each.
    # The HTML uses <p>...</p> blocks containing <span data-start="...">text</span>.
    # Some spans straddle </p><p> boundaries, so we track which <p> block each span
    # starts in by scanning sequentially.
    entries = []
    # Find all <p> start positions and span positions
    p_starts = [m.start() for m in re.finditer(r'<p[^>]*>', transcript_html)]

    for m in re.finditer(r'<span\s+data-start="([^"]+)">(.*?)</span>', transcript_html):
        time_val = float(m.group(1))
        text = m.group(2).strip()
        # Clean any remaining HTML tags from the text
        text = re.sub(r'<[^>]+>', '', text)
        text = text.strip()
        if not text:
            continue

        # Determine which <p> block this span belongs to
        span_pos = m.start()
        p_idx = 0
        for i, ps in enumerate(p_starts):
            if ps <= span_pos:
                p_idx = i
            else:
                break

        # First entry in a new <p> block starts a paragraph
        is_para_start = not entries or (entries and entries[-1].get("_p_idx") != p_idx)
        entry = {"time": time_val, "text": text, "paragraph": is_para_start, "_p_idx": p_idx}
        entries.append(entry)

    # Clean up internal tracking field
    for e in entries:
        del e["_p_idx"]
    # First entry is always a paragraph start
    if entries:
        entries[0]["paragraph"] = True

    return entries


def extract_chapters(html_text: str) -> list[dict]:
    """Extract chapter markers from WWDC session HTML.

    Returns a list of dicts with 'time' (float seconds) and 'title' (string).
    """
    match = re.search(r'class="no-bullet chapter-list">(.*?)</ul>', html_text, re.DOTALL)
    if not match:
        return []

    chapters = []
    for m in re.finditer(
        r'<a\s+class="jump-to-time"[^>]*data-start-time="(\d+)"[^>]*>(.*?)</a>',
        match.group(1), re.DOTALL
    ):
        time_val = float(m.group(1))
        title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if title:
            chapters.append({"time": time_val, "title": title})

    return chapters


def cache_key_from_url(url: str) -> str | None:
    """Derive the Developer.app transcript cache key ("<event>-<session>") from a
    session URL like https://developer.apple.com/videos/play/wwdc2026/269/."""
    m = re.search(r"/videos/play/([^/]+)/([^/?#]+)", url)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}"


def _group_cache_entries(transcript: list) -> list[dict]:
    """Turn Developer.app cache rows ([start_seconds, text]) into transcript
    entries with paragraph flags. The cache has no paragraph markers, so break
    paragraphs after sentence-ending punctuation once enough words accumulate."""
    entries = []
    words_in_para = 0
    for i, row in enumerate(transcript):
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        time_val = float(row[0])
        text = str(row[1]).strip()
        if not text:
            continue
        is_para = not entries
        if entries and words_in_para >= 45:
            prev = entries[-1]["text"].rstrip()
            if prev and prev[-1] in ".!?…":
                is_para = True
        if is_para:
            words_in_para = 0
        words_in_para += len(text.split())
        entries.append({"time": time_val, "text": text, "paragraph": is_para})
    if entries:
        entries[0]["paragraph"] = True
    return entries


def extract_transcript_from_cache(url: str) -> list[dict]:
    """Load a transcript from Developer.app's local JSON cache, if present.

    Returns [] when the cache directory, file, or session entry is missing so
    callers can fall back to scraping the web page.
    """
    key = cache_key_from_url(url)
    if not key:
        return []
    path = os.path.join(TRANSCRIPT_CACHE_DIR, f"{key}.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    # File is keyed by the session id; tolerate the entry being the sole value.
    inner = data.get(key)
    if inner is None and len(data) == 1:
        inner = next(iter(data.values()))
    if not isinstance(inner, dict):
        return []
    return _group_cache_entries(inner.get("transcript", []))


def get_transcript(url: str) -> list[dict]:
    """Return a session transcript, preferring Developer.app's local cache and
    falling back to scraping the session web page."""
    entries = extract_transcript_from_cache(url)
    if entries:
        return entries
    html = fetch_url(url).decode("utf-8")
    return extract_transcript(html)


def get_transcript_and_chapters(url: str) -> tuple[list[dict], list[dict]]:
    """Fetch a WWDC session's transcript + chapter markers. The transcript comes
    from Developer.app's local cache when available; chapters come from the page."""
    html = fetch_url(url).decode("utf-8")
    entries = extract_transcript_from_cache(url)
    if not entries:
        entries = extract_transcript(html)
    return entries, extract_chapters(html)


def format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS or MM:SS."""
    s = int(seconds)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: wwdc_transcript.py <url> [--json]", file=sys.stderr)
        print("Example: wwdc_transcript.py https://developer.apple.com/videos/play/wwdc2025/230/", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    as_json = "--json" in sys.argv

    try:
        transcript = get_transcript(url)
        if as_json:
            print(json.dumps(transcript, indent=2))
        else:
            for entry in transcript:
                ts = format_timestamp(entry["time"])
                print(f"[{ts}] {entry['text']}")
            print(f"\n{len(transcript)} lines", file=sys.stderr)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
