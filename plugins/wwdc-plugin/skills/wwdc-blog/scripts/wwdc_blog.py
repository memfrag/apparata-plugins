#!/usr/bin/env python3
"""
Generate a blog-post-style HTML page for a WWDC session.

Interleaves transcript text with slide screenshots extracted from the video
at moments where the visual content has settled after scene changes.
"""

import glob
import html
import json
import os
import re
import subprocess
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Import from sibling skills
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", "..", "wwdc-catalog", "scripts"))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", "..", "wwdc-download", "scripts"))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", "..", "wwdc-transcript", "scripts"))

from wwdc_catalog import get_wwdc_catalog
from wwdc_download import find_session, download_session, sanitize_filename
from wwdc_transcript import get_transcript_and_chapters, format_timestamp, fetch_url


FACE_DETECT_SWIFT = r'''
import Vision
import Foundation
for path in CommandLine.arguments.dropFirst() {
    let url = URL(fileURLWithPath: path)
    do {
        let handler = VNImageRequestHandler(url: url)
        let faceReq = VNDetectFaceRectanglesRequest()
        let textReq = VNDetectTextRectanglesRequest()
        try handler.perform([faceReq, textReq])
        let faces = faceReq.results ?? []
        let textCount = textReq.results?.count ?? 0
        let maxArea = faces.map { $0.boundingBox.width * $0.boundingBox.height }.max() ?? 0.0
        print("\(path)\t\(faces.count)\t\(maxArea)\t\(textCount)")
    } catch { print("\(path)\t0\t0.0\t0") }
}
'''


def find_youtube_video(event_id: str, title: str) -> str | None:
    """Search YouTube for the official Apple Developer video and return the video ID.

    Uses YouTube search scraping + oEmbed verification. Best-effort, never fatal.
    """
    try:
        # Extract 2-digit year suffix from event ID (e.g. "wwdc2025" -> "25")
        year_match = re.search(r'(\d{4})$', event_id)
        if not year_match:
            return None
        yy = year_match.group(1)[-2:]
        wwdc_prefix = f"WWDC{yy}"

        # Normalize curly quotes/apostrophes to ASCII for search
        normalized_title = title.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')

        # Build search query
        query = f"{wwdc_prefix} {normalized_title} Apple Developer"
        search_url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"

        print(f"  Searching YouTube: {query}", file=sys.stderr)
        search_html = fetch_url(search_url).decode("utf-8", errors="replace")

        # Extract unique video IDs
        video_ids = list(dict.fromkeys(re.findall(r'"videoId":"([^"]+)"', search_html)))
        if not video_ids:
            print("  No YouTube videos found", file=sys.stderr)
            return None

        # Verify via oEmbed - check first few candidates
        for vid in video_ids[:5]:
            oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json"
            try:
                oembed_data = json.loads(fetch_url(oembed_url).decode("utf-8"))
                author = oembed_data.get("author_name", "")
                oembed_title = oembed_data.get("title", "")
                if author == "Apple Developer" and wwdc_prefix in oembed_title:
                    print(f"  Found YouTube video: {vid} ({oembed_title})", file=sys.stderr)
                    return vid
            except Exception:
                continue

        print("  No verified Apple Developer video found", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  YouTube search failed: {e}", file=sys.stderr)
        return None


def detect_faces_batch(image_paths: list[str]) -> dict[str, tuple[int, float, int]]:
    """Detect faces and text in a batch of images using macOS Vision framework.

    Returns dict mapping image path to (face_count, max_face_area_fraction, text_block_count).
    """
    if not image_paths:
        return {}
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".swift", delete=False) as f:
            f.write(FACE_DETECT_SWIFT)
            swift_path = f.name
        try:
            result = subprocess.run(
                ["swift", swift_path] + image_paths,
                capture_output=True, text=True, timeout=120
            )
            faces = {}
            for line in result.stdout.strip().splitlines():
                parts = line.rsplit("\t", 3)
                if len(parts) == 4:
                    faces[parts[0]] = (int(parts[1]), float(parts[2]), int(parts[3]))
                elif len(parts) == 3:
                    faces[parts[0]] = (int(parts[1]), float(parts[2]), 0)
                elif len(parts) == 2:
                    faces[parts[0]] = (int(parts[1]), 0.0, 0)
            return faces
        finally:
            os.unlink(swift_path)
    except Exception as e:
        print(f"  Face detection unavailable ({e}), keeping all frames", file=sys.stderr)
        return {}


def compute_bright_pct(image_path: str, luma_threshold: int = 200) -> float:
    """Compute percentage of pixels with luma > threshold."""
    cmd = [
        "ffmpeg", "-i", image_path,
        "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if not result.stdout:
        return 0.0
    data = result.stdout
    bright = sum(1 for b in data if b > luma_threshold)
    return (bright / len(data)) * 100.0


def filter_speaker_frames(frames: list[dict], images_dir: str,
                          bright_threshold: float = 25.0) -> list[dict]:
    """Filter out speaker-only frames using face detection + brightness check.

    Logic:
    - No face detected → keep (it's a slide)
    - Face detected + text detected → keep (speaker with content overlay)
    - Face detected + no text + large face (>1.5%) → remove (speaker shot)
    - Face detected + no text + small face + bright → keep (PiP or similar)
    - Face detected + no text + small face + dark → remove
    """
    paths = [os.path.join(images_dir, f["path"]) for f in frames]
    print("Running face detection...", file=sys.stderr)
    face_counts = detect_faces_batch(paths)

    if not face_counts:
        # Face detection unavailable, keep all
        return frames

    kept = []
    removed = 0
    for frame in frames:
        path = os.path.join(images_dir, frame["path"])
        face_info = face_counts.get(path, (0, 0.0, 0))
        face_count, max_face_area, text_count = face_info
        if face_count == 0:
            kept.append(frame)
        elif text_count >= 3:
            # Face + significant text = speaker with content overlay, keep
            kept.append(frame)
        elif max_face_area > 0.015:
            # Large face, no text = speaker shot, remove
            os.remove(path)
            removed += 1
        elif compute_bright_pct(path) >= bright_threshold:
            # Small face + bright background = likely has slide content
            kept.append(frame)
        else:
            os.remove(path)
            removed += 1

    print(f"  Filtered {removed} speaker-only frames, kept {len(kept)}", file=sys.stderr)
    return kept


def detect_scene_changes(video_path: str, threshold: float = 0.3) -> list[float]:
    """Detect scene change timestamps using ffmpeg's select filter."""
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-vsync", "vfr", "-f", "null", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    stderr = result.stderr

    timestamps = []
    for line in stderr.splitlines():
        if "showinfo" not in line:
            continue
        m = re.search(r"pts_time:(\d+\.?\d*)", line)
        if m:
            timestamps.append(float(m.group(1)))

    return timestamps


def deduplicate_timestamps(timestamps: list[float], min_gap: float = 3.0) -> list[float]:
    """Remove timestamps that are too close together, keeping the last in a cluster."""
    if not timestamps:
        return []
    timestamps.sort()
    result = [timestamps[0]]
    for t in timestamps[1:]:
        if t - result[-1] >= min_gap:
            result.append(t)
        else:
            # Replace previous with this later one (keep the settled state)
            result[-1] = t
    return result


def extract_frames(video_path: str, timestamps: list[float], output_dir: str, settle_delay: float = 1.0) -> list[dict]:
    """Extract a frame at each timestamp + settle_delay. Returns list of {time, path}."""
    os.makedirs(output_dir, exist_ok=True)
    frames = []

    for i, t in enumerate(timestamps):
        capture_time = t + settle_delay
        filename = f"frame_{i+1:03d}.jpg"
        output_path = os.path.join(output_dir, filename)

        cmd = [
            "ffmpeg", "-ss", str(capture_time),
            "-i", video_path,
            "-frames:v", "1", "-q:v", "2",
            "-y", output_path
        ]
        subprocess.run(cmd, capture_output=True, timeout=30)

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            frames.append({"time": capture_time, "path": filename})
            print(f"  Frame {i+1}/{len(timestamps)}: {capture_time:.1f}s -> {filename}", file=sys.stderr)

    return frames


def build_web_permalink(session: dict) -> str:
    """Build the developer.apple.com permalink for a session."""
    wp = session.get("webPermalink")
    if wp:
        if wp.startswith("http"):
            return wp
        return "https://developer.apple.com" + wp
    event_id = session.get("eventId", "")
    session_id = session.get("id", "")
    num = session_id.split("-")[-1] if "-" in session_id else session_id
    return f"https://developer.apple.com/videos/play/{event_id}/{num}/"


def generate_html(session: dict, transcript: list[dict], frames: list[dict],
                   images_dir: str, chapters: list[dict] | None = None,
                   code_snippets: list[dict] | None = None,
                   youtube_id: str | None = None) -> str:
    """Generate blog-post HTML interleaving transcript with slide images."""
    title = html.escape(session.get("title", "WWDC Session"))
    event_id = session.get("eventId", "")
    description = html.escape(session.get("description", ""))
    permalink = build_web_permalink(session)
    event_name = event_id.upper().replace("WWDC", "WWDC ")

    if chapters is None:
        chapters = []
    chapters_sorted = sorted(chapters, key=lambda c: c["time"])

    if code_snippets is None:
        code_snippets = []
    snippets_sorted = sorted(code_snippets, key=lambda s: s.get("startTimeSeconds", 0))

    # Sort frames by time
    frames_sorted = sorted(frames, key=lambda f: f["time"])

    # Build HTML body: interleave transcript paragraphs with images.
    # Frames are deferred to the next paragraph boundary so they don't
    # break mid-paragraph.  If a paragraph runs too long (>max_defer
    # sentences past the frame's timestamp), insert between sentences.
    max_defer_sentences = 8
    body_parts = []
    frame_idx = 0
    chapter_idx = 0
    snippet_idx = 0
    paragraph_lines = []
    pending_frames = []
    pending_snippets = []
    sentences_since_pending = 0

    def flush_paragraph():
        if paragraph_lines:
            text = " ".join(paragraph_lines)
            body_parts.append(f'      <p>{text}</p>')
            paragraph_lines.clear()

    def insert_frame(frame):
        img_path = f"images/{frame['path']}"
        img_tag = f'<img src="{img_path}" alt="Slide at {format_timestamp(frame["time"])}" loading="lazy">'
        if youtube_id:
            yt_t = int(frame["time"])
            body_parts.append(f'      <figure><a href="https://www.youtube.com/watch?v={youtube_id}&amp;t={yt_t}s" target="_blank" rel="noopener">{img_tag}</a></figure>')
        else:
            body_parts.append(f'      <figure>{img_tag}</figure>')

    def insert_snippet(snip):
        snip_title = html.escape(snip.get("title", "Code"))
        raw_lang = snip.get("language", "")
        # Use the pre-highlighted HTML if available, otherwise plain text
        if snip.get("code"):
            code_content = snip["code"]
        else:
            code_content = html.escape(snip.get("unstyledCode", ""))
        # Encode unstyled code for the copy button via a data attribute
        unstyled = html.escape(snip.get("unstyledCode", ""), quote=True)
        copy_svg = ('<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                    '<rect x="9" y="9" width="13" height="13" rx="2"/>'
                    '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>')
        # Swift gets special treatment: logo icon + title-cased name
        if raw_lang.lower() == "swift":
            swift_svg = ('<svg class="lang-icon" width="14" height="14" viewBox="0 0 32 32" fill="none">'
                         '<defs><linearGradient id="swg" x1="15" y1="2" x2="15" y2="27" gradientUnits="userSpaceOnUse">'
                         '<stop stop-color="#F88A36"/><stop offset="1" stop-color="#FD2020"/></linearGradient></defs>'
                         '<path d="M22.136 25.272C18.835 27.17 14.297 27.365 9.731 25.417C6.034 23.85 '
                         '2.966 21.11 1 17.977c.944.783 2.045 1.41 3.225 1.957 4.715 2.2 9.43 2.05 '
                         '12.747.006C12.253 16.337 8.236 11.633 5.248 7.795c-.63-.626-1.102-1.41-1.574'
                         '-2.114 3.618 3.289 9.36 7.44 11.405 8.614C10.754 9.753 6.9 4.115 7.056 '
                         '4.271c6.843 6.892 13.215 10.808 13.215 10.808.21.118.374.217.504.305.138-.35'
                         '.259-.712.361-1.088 1.1-3.994-.159-8.537-2.912-12.296 6.371 3.838 10.147 '
                         '11.043 8.573 17.073-.04.163-.085.324-.133.481 3.145 3.917 2.336 8.135 1.942 '
                         '7.352-1.706-3.325-4.866-2.308-6.472-1.634z" fill="url(#swg)"/></svg>')
            lang_html = f'{swift_svg}Swift'
        else:
            lang_html = html.escape(raw_lang).upper()
        body_parts.append(
            f'      <details class="code-snippet">\n'
            f'        <summary><span class="snippet-title">{snip_title}</span>'
            f'<span class="snippet-lang">{lang_html}</span>'
            f'<button class="copy-btn" data-code="{unstyled}" aria-label="Copy code">'
            f'{copy_svg}<span>Copy</span></button></summary>\n'
            f'        <pre><code>{code_content}</code></pre>\n'
            f'      </details>'
        )

    def flush_pending():
        nonlocal sentences_since_pending
        for frame in pending_frames:
            insert_frame(frame)
        pending_frames.clear()
        for snip in pending_snippets:
            insert_snippet(snip)
        pending_snippets.clear()
        sentences_since_pending = 0

    def insert_chapter_heading(ch):
        slug = re.sub(r'[^a-z0-9]+', '-', ch["title"].lower()).strip('-')
        body_parts.append(f'      <h2 id="{slug}">{html.escape(ch["title"])}</h2>')

    for entry in transcript:
        t = entry["time"]
        raw_text = html.escape(entry["text"])
        if youtube_id:
            yt_t = int(t)
            text = f'<a href="https://www.youtube.com/watch?v={youtube_id}&amp;t={yt_t}s" target="_blank" rel="noopener" class="ts-link">{raw_text}</a>'
        else:
            text = raw_text

        # At paragraph boundaries, flush paragraph then insert deferred content
        if entry.get("paragraph") and paragraph_lines:
            flush_paragraph()
            flush_pending()

        # Insert chapter headings whose time <= this entry's time
        while chapter_idx < len(chapters_sorted) and chapters_sorted[chapter_idx]["time"] <= t:
            flush_paragraph()
            flush_pending()
            insert_chapter_heading(chapters_sorted[chapter_idx])
            chapter_idx += 1

        # Collect frames whose capture time <= this entry's time
        while frame_idx < len(frames_sorted) and frames_sorted[frame_idx]["time"] <= t:
            pending_frames.append(frames_sorted[frame_idx])
            frame_idx += 1
            sentences_since_pending = 0

        # Collect code snippets whose start time <= this entry's time
        while snippet_idx < len(snippets_sorted) and snippets_sorted[snippet_idx].get("startTimeSeconds", 0) <= t:
            pending_snippets.append(snippets_sorted[snippet_idx])
            snippet_idx += 1
            sentences_since_pending = 0

        # If deferred content has waited too long, insert between sentences
        if pending_frames or pending_snippets:
            sentences_since_pending += 1
            if sentences_since_pending > max_defer_sentences:
                flush_paragraph()
                flush_pending()

        paragraph_lines.append(text)

    # Flush remaining content
    flush_paragraph()
    flush_pending()

    # Insert any remaining frames at the end
    while frame_idx < len(frames_sorted):
        insert_frame(frames_sorted[frame_idx])
        frame_idx += 1
    while snippet_idx < len(snippets_sorted):
        insert_snippet(snippets_sorted[snippet_idx])
        snippet_idx += 1

    body_html = "\n".join(body_parts)

    # Build sidebar TOC from chapters
    toc_items = []
    for ch in chapters_sorted:
        slug = re.sub(r'[^a-z0-9]+', '-', ch["title"].lower()).strip('-')
        toc_items.append(f'          <li><a href="#{slug}">{html.escape(ch["title"])}</a></li>')

    has_toc = bool(toc_items)
    permalink_escaped = html.escape(permalink)

    # --- Assemble HTML from plain strings (no f-strings for JS/CSS) ---
    parts = []

    # Head
    parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>{title} - {event_name}</title>
  <link rel="icon" href="../../favicon.ico">
""")

    # CSS — use plain string to avoid {{ }} escaping issues
    parts.append("""  <style>
    :root {
      --text-primary: #1a1a1a;
      --text-body: #333336;
      --text-secondary: #6e6e73;
      --text-toc: #48484a;
      --bg-page: #fafafa;
      --bg-surface: #ffffff;
      --bg-toc: rgba(255,255,255,0.85);
      --border: #e0e0e3;
      --border-section: #ebebee;
      --accent: #0071e3;
      --accent-hover: #0077ED;
      --img-shadow: 0 4px 24px rgba(0,0,0,0.06), 0 1px 4px rgba(0,0,0,0.04);
      --img-radius: 12px;
      --toggle-bg: rgba(0,0,0,0.04);
      --toggle-hover: rgba(0,0,0,0.08);
      --toggle-border: rgba(0,0,0,0.06);
      --heading-tracking: -0.025em;
      --chapter-dot: #d1d1d6;
      --chapter-dot-active: var(--accent);
      --font-display: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', sans-serif;
      --font-body: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', sans-serif;
    }
    @media (prefers-color-scheme: dark) {
      :root:not([data-theme="light"]) {
        --text-primary: #f5f5f7;
        --text-body: #d1d1d6;
        --text-secondary: #8e8e93;
        --text-toc: #a1a1a6;
        --bg-page: #111113;
        --bg-surface: #1c1c1e;
        --bg-toc: rgba(28,28,30,0.88);
        --border: #2c2c2e;
        --border-section: #2c2c2e;
        --accent: #4db8ff;
        --accent-hover: #66c3ff;
        --img-shadow: 0 4px 24px rgba(0,0,0,0.25), 0 1px 4px rgba(0,0,0,0.15);
        --toggle-bg: rgba(255,255,255,0.06);
        --toggle-hover: rgba(255,255,255,0.1);
        --toggle-border: rgba(255,255,255,0.08);
        --chapter-dot: #48484a;
      }
    }
    [data-theme="dark"] {
      --text-primary: #f5f5f7;
      --text-body: #d1d1d6;
      --text-secondary: #8e8e93;
      --text-toc: #a1a1a6;
      --bg-page: #111113;
      --bg-surface: #1c1c1e;
      --bg-toc: rgba(28,28,30,0.88);
      --border: #2c2c2e;
      --border-section: #2c2c2e;
      --accent: #4db8ff;
      --accent-hover: #66c3ff;
      --img-shadow: 0 4px 24px rgba(0,0,0,0.25), 0 1px 4px rgba(0,0,0,0.15);
      --toggle-bg: rgba(255,255,255,0.06);
      --toggle-hover: rgba(255,255,255,0.1);
      --toggle-border: rgba(255,255,255,0.08);
      --chapter-dot: #48484a;
    }

    *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

    html { scroll-behavior: smooth; }

    body {
      font-family: var(--font-body);
      font-size: 16px;
      line-height: 1.55;
      color: var(--text-body);
      background: var(--bg-page);
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      transition: color 0.3s ease, background-color 0.3s ease;
    }

    /* Layout */
    .page-layout {
      display: flex;
      max-width: 1200px;
      margin: 0 auto;
      position: relative;
    }

    /* Theme toggle */
    .theme-toggle {
      position: fixed;
      top: 1.25rem;
      right: 1.25rem;
      z-index: 200;
      width: 40px;
      height: 40px;
      border-radius: 12px;
      border: 1px solid var(--toggle-border);
      background: var(--toggle-bg);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--text-secondary);
      transition: background 0.2s ease, transform 0.15s ease, color 0.2s ease;
    }
    .theme-toggle:hover {
      background: var(--toggle-hover);
      transform: scale(1.05);
    }
    .theme-toggle:active { transform: scale(0.95); }

    /* Sidebar TOC */
    .toc-sidebar {
      position: sticky;
      top: 2.5rem;
      align-self: flex-start;
      width: 240px;
      min-width: 240px;
      padding: 0 1.5rem 2rem 2rem;
      margin-top: 10rem;
    }
    .toc-sidebar .toc-label {
      font-family: var(--font-body);
      font-size: 0.6875rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-secondary);
      margin-bottom: 1rem;
    }
    .toc-sidebar ul { list-style: none; }
    .toc-sidebar li {
      position: relative;
      margin-bottom: 0.125rem;
    }
    .toc-sidebar a {
      display: block;
      font-family: var(--font-body);
      font-size: 0.8125rem;
      font-weight: 400;
      color: var(--text-toc);
      text-decoration: none;
      padding: 0.375rem 0 0.375rem 1.125rem;
      border-left: 2px solid var(--chapter-dot);
      transition: color 0.2s ease, border-color 0.2s ease;
    }
    .toc-sidebar a:hover {
      color: var(--accent);
    }
    .toc-sidebar a.active {
      color: var(--accent);
      font-weight: 600;
      border-left-color: var(--chapter-dot-active);
    }

    /* Main content */
    .content-main {
      flex: 1;
      min-width: 0;
      max-width: 780px;
      margin: 0 auto;
      padding: 4rem 2rem 6rem;
    }

    /* Header */
    .session-header {
      margin-bottom: 3.5rem;
    }
    .session-header .badge-row {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-bottom: 1rem;
    }
    .session-header .event-badge,
    .session-header .breadcrumb-link {
      font-family: var(--font-body);
      font-size: 0.75rem;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--accent);
      text-decoration: none;
    }
    .session-header .breadcrumb-link:hover { color: var(--accent-hover); }
    .session-header .breadcrumb-sep {
      font-size: 0.75rem;
      color: var(--text-secondary);
      opacity: 0.4;
    }
    .session-header h1 {
      font-family: var(--font-display);
      font-size: 2.75rem;
      font-weight: 700;
      line-height: 1.15;
      letter-spacing: var(--heading-tracking);
      color: var(--text-primary);
      margin-bottom: 1.25rem;
    }
    .session-header .description {
      font-family: var(--font-display);
      font-size: 1.25rem;
      font-weight: 400;
      font-style: italic;
      line-height: 1.4;
      color: var(--text-secondary);
      margin-bottom: 1.25rem;
    }
    .session-header .watch-links {
      display: flex;
      align-items: center;
      gap: 1.25rem;
      flex-wrap: wrap;
    }
    .session-header .watch-link {
      display: inline-flex;
      align-items: center;
      gap: 0.375rem;
      font-family: var(--font-body);
      font-size: 0.875rem;
      font-weight: 500;
      color: var(--accent);
      text-decoration: none;
      transition: color 0.15s ease;
    }
    .session-header .watch-link:hover {
      color: var(--accent-hover);
    }
    .session-header .platform-pill {
      display: inline-block;
      font-family: var(--font-body);
      font-size: 0.6875rem;
      font-weight: 600;
      letter-spacing: 0.02em;
      border-radius: 100px;
      padding: 0.2rem 0.625rem;
      --pill-color: var(--text-secondary);
      color: var(--pill-color);
      background: color-mix(in srgb, var(--pill-color) 8%, transparent);
      border: 1px solid color-mix(in srgb, var(--pill-color) 20%, transparent);
    }
    .platform-pill[data-platform="ios"] { --pill-color: #007aff; }
    .platform-pill[data-platform="ipados"] { --pill-color: #5856d6; }
    .platform-pill[data-platform="macos"] { --pill-color: #34c759; }
    .platform-pill[data-platform="watchos"] { --pill-color: #ff9500; }
    .platform-pill[data-platform="visionos"] { --pill-color: #ac8e68; }
    .session-header::after {
      content: '';
      display: block;
      width: 48px;
      height: 3px;
      background: var(--accent);
      border-radius: 2px;
      margin-top: 2rem;
    }

    /* Article content */
    article h2 {
      font-family: var(--font-display);
      font-size: 1.625rem;
      font-weight: 600;
      line-height: 1.3;
      letter-spacing: var(--heading-tracking);
      color: var(--text-primary);
      margin: 3.5rem 0 1.25rem;
      padding-top: 2rem;
      border-top: 1px solid var(--border-section);
    }
    article h2:first-child {
      margin-top: 0;
      padding-top: 0;
      border-top: none;
    }
    article p {
      font-family: var(--font-body);
      font-size: 1.0625rem;
      line-height: 1.55;
      color: var(--text-body);
      margin-bottom: 1rem;
    }
    .ts-link {
      color: inherit;
      text-decoration: none;
      border-bottom: 1px solid transparent;
      transition: border-color 0.15s ease, color 0.15s ease;
    }
    .ts-link:hover {
      color: var(--accent);
      border-bottom-color: var(--accent);
    }
    article figure {
      margin: 2.5rem -2rem;
      position: relative;
    }
    article figure img {
      width: 100%;
      height: auto;
      display: block;
      border-radius: var(--img-radius);
      box-shadow: var(--img-shadow);
      transition: box-shadow 0.3s ease;
    }
    article figure:hover img {
      box-shadow: 0 8px 32px rgba(0,0,0,0.1), 0 2px 8px rgba(0,0,0,0.06);
    }
    [data-theme="dark"] article figure:hover img,
    @media (prefers-color-scheme: dark) {
      article figure:hover img {
        box-shadow: 0 8px 32px rgba(0,0,0,0.35), 0 2px 8px rgba(0,0,0,0.2);
      }
    }

    /* Code snippets */
    .code-snippet {
      margin: 1.5rem 0;
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
      transition: border-color 0.2s ease;
    }
    .code-snippet[open] {
      border-color: var(--accent);
    }
    .code-snippet summary {
      display: flex;
      align-items: center;
      gap: 0.625rem;
      padding: 0.75rem 1rem;
      cursor: pointer;
      font-family: var(--font-body);
      font-size: 0.875rem;
      color: var(--text-primary);
      background: var(--toggle-bg);
      list-style: none;
      transition: background 0.15s ease;
    }
    .code-snippet summary::-webkit-details-marker { display: none; }
    .code-snippet summary::before {
      content: '';
      display: inline-block;
      width: 0;
      height: 0;
      border-left: 5px solid var(--text-secondary);
      border-top: 4px solid transparent;
      border-bottom: 4px solid transparent;
      transition: transform 0.2s ease;
      flex-shrink: 0;
    }
    .code-snippet[open] summary::before {
      transform: rotate(90deg);
    }
    .code-snippet summary:hover { opacity: 0.85; }
    .snippet-title { font-weight: 600; }
    .snippet-lang {
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      margin-left: auto;
      font-size: 0.75rem;
      font-weight: 500;
      letter-spacing: 0.04em;
      color: var(--text-secondary);
    }
    .snippet-lang .lang-icon {
      flex-shrink: 0;
      position: relative;
      top: -0.5px;
    }
    .copy-btn {
      display: inline-flex;
      align-items: center;
      gap: 0.375rem;
      margin-left: 0.625rem;
      padding: 0.2rem 0.5rem;
      font-family: var(--font-body);
      font-size: 0.6875rem;
      font-weight: 500;
      color: var(--text-secondary);
      background: transparent;
      border: 1px solid var(--border);
      border-radius: 5px;
      cursor: pointer;
      transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
    }
    .copy-btn:hover {
      background: var(--toggle-hover);
      color: var(--text-primary);
    }
    .copy-btn.copied {
      color: #34c759;
      border-color: #34c759;
    }
    .code-snippet pre {
      margin: 0;
      padding: 1.25rem 1.25rem;
      overflow-x: auto;
      background: var(--bg-surface);
      border-top: 1px solid var(--border);
      -webkit-overflow-scrolling: touch;
    }
    .code-snippet code {
      font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', Menlo, Consolas, monospace;
      font-size: 0.8125rem;
      line-height: 1.65;
      color: var(--text-body);
    }
    .code-snippet .syntax-keyword { color: #ad3da4; font-weight: 600; }
    .code-snippet .syntax-type { color: #5856d6; }
    .code-snippet .syntax-title { color: #1d6fa5; }
    .code-snippet .syntax-comment { color: #8e8e93; font-style: italic; }
    .code-snippet .syntax-string { color: #c41a16; }
    .code-snippet .syntax-number { color: #1c00cf; }
    .code-snippet .syntax-operator { color: var(--text-body); }
    [data-theme="dark"] .code-snippet .syntax-keyword,
    @media (prefers-color-scheme: dark) { :root:not([data-theme="light"])
      .code-snippet .syntax-keyword { color: #ff7ab2; }
    }
    [data-theme="dark"] .code-snippet .syntax-type { color: #b281eb; }
    [data-theme="dark"] .code-snippet .syntax-title { color: #6bdfff; }
    [data-theme="dark"] .code-snippet .syntax-comment { color: #7f8c8d; }
    [data-theme="dark"] .code-snippet .syntax-string { color: #ff8170; }
    [data-theme="dark"] .code-snippet .syntax-number { color: #d9c97c; }

    /* Responsive */
    @media (min-width: 900px) {
      article figure {
        margin-left: -3rem;
        margin-right: -3rem;
      }
    }
    .back-to-top-footer {
      margin-top: 4rem;
      padding: 2rem 0;
      border-top: 1px solid var(--border);
      text-align: center;
    }
    .back-to-top-link {
      color: var(--text-secondary);
      font-family: var(--font-body);
      font-size: 0.875rem;
      text-decoration: none;
      letter-spacing: 0.02em;
      transition: color 0.15s ease;
    }
    .back-to-top-link:hover {
      color: var(--accent);
    }
    @media (max-width: 1080px) {
      .toc-sidebar { display: none; }
      .page-layout { display: block; }
      .content-main { max-width: 720px; margin: 0 auto; }
    }
    @media (max-width: 640px) {
      .content-main { padding: 2.5rem 1.25rem 4rem; }
      .session-header h1 { font-size: 2rem; }
      .session-header .description { font-size: 1.0625rem; }
      article figure { margin: 2rem -1.25rem; }
      article figure img { border-radius: 8px; }
      article h2 { font-size: 1.375rem; margin-top: 2.5rem; }
    }
  </style>
</head>""")

    # Body open + theme toggle
    parts.append("""<body id="top">
  <button class="theme-toggle" id="theme-toggle" aria-label="Toggle theme" title="Toggle light/dark mode"></button>
  <div class="page-layout">""")

    # TOC sidebar
    if has_toc:
        parts.append('    <nav class="toc-sidebar" aria-label="Table of contents">')
        parts.append('      <div class="toc-label">Contents</div>')
        parts.append('        <ul>')
        parts.extend(toc_items)
        parts.append('        </ul>')
        parts.append('    </nav>')

    # Header + article
    parts.append(f'    <main class="content-main">')
    parts.append(f'      <header class="session-header">')
    platforms = session.get("platforms", [])
    pills_html = ""
    if platforms:
        pills_html = "".join(
            f'<span class="platform-pill" data-platform="{html.escape(p.lower())}">{html.escape(p)}</span>'
            for p in platforms
        )
    parts.append(f'        <div class="badge-row">'
                 f'<a class="breadcrumb-link" href="../../index.html">All Years</a>'
                 f'<span class="breadcrumb-sep">/</span>'
                 f'<a class="breadcrumb-link" href="../index.html">{event_name}</a>'
                 f'{pills_html}</div>')
    parts.append(f'        <h1>{title}</h1>')
    if description:
        parts.append(f'        <p class="description">{description}</p>')
    parts.append(f'        <div class="watch-links">')
    parts.append(f'          <a class="watch-link" href="{permalink_escaped}" target="_blank" rel="noopener">\U0000F8FF Watch on Apple Developer</a>')
    if youtube_id:
        yt_url = html.escape(f"https://www.youtube.com/watch?v={youtube_id}")
        yt_svg = ('<svg class="yt-icon" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">'
                  '<path d="M23.5 6.19a3.02 3.02 0 0 0-2.12-2.14C19.5 3.5 12 3.5 12 3.5s-7.5 0-9.38.55A3.02 3.02 0 0 0 .5 6.19 31.6 31.6 0 0 0 0 12a31.6 31.6 0 0 0 .5 5.81 3.02 3.02 0 0 0 2.12 2.14c1.88.55 9.38.55 9.38.55s7.5 0 9.38-.55a3.02 3.02 0 0 0 2.12-2.14A31.6 31.6 0 0 0 24 12a31.6 31.6 0 0 0-.5-5.81zM9.55 15.57V8.43L15.82 12l-6.27 3.57z"/></svg>')
        parts.append(f'          <a class="watch-link" href="{yt_url}" target="_blank" rel="noopener">{yt_svg} Watch on YouTube</a>')
    parts.append(f'        </div>')
    parts.append(f'      </header>')
    parts.append(f'      <article>')
    parts.append(body_html)
    parts.append('      </article>')
    parts.append('      <footer class="back-to-top-footer"><a href="#top" class="back-to-top-link">Back to top &uarr;</a></footer>')
    parts.append('    </main>')
    parts.append('  </div>')

    # JavaScript — plain strings, no f-strings
    parts.append("""  <script>
    (function() {
      var root = document.documentElement;
      var toggle = document.getElementById('theme-toggle');
      var sun = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
      var moon = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
      function getTheme() {
        var t = root.getAttribute('data-theme');
        if (t) return t;
        return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      }
      function applyIcon() {
        toggle.innerHTML = getTheme() === 'dark' ? sun : moon;
      }
      var saved = localStorage.getItem('wwdc-blog-theme');
      if (saved) root.setAttribute('data-theme', saved);
      applyIcon();
      matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyIcon);
      toggle.addEventListener('click', function() {
        var next = getTheme() === 'dark' ? 'light' : 'dark';
        root.setAttribute('data-theme', next);
        localStorage.setItem('wwdc-blog-theme', next);
        applyIcon();
      });""")

    if has_toc:
        parts.append("""
      var headings = document.querySelectorAll('article h2[id]');
      var tocLinks = document.querySelectorAll('.toc-sidebar a');
      if (headings.length && tocLinks.length) {
        var observer = new IntersectionObserver(function(entries) {
          entries.forEach(function(e) {
            if (e.isIntersecting) {
              tocLinks.forEach(function(a) { a.classList.remove('active'); });
              var sel = '.toc-sidebar a[href="#' + e.target.id + '"]';
              var active = document.querySelector(sel);
              if (active) active.classList.add('active');
            }
          });
        }, { rootMargin: '0px 0px -75% 0px' });
        headings.forEach(function(h) { observer.observe(h); });
        tocLinks[0].classList.add('active');
      }""")

    parts.append("""
      document.addEventListener('click', function(e) {
        var btn = e.target.closest('.copy-btn');
        if (!btn) return;
        var code = btn.getAttribute('data-code');
        var label = btn.querySelector('span');
        navigator.clipboard.writeText(code).then(function() {
          btn.classList.add('copied');
          label.textContent = 'Copied';
          setTimeout(function() {
            btn.classList.remove('copied');
            label.textContent = 'Copy';
          }, 1500);
        });
      });
    })();
  </script>
</body>
</html>""")

    return "\n".join(parts)


def _index_page_shell(title: str, body_html: str, sidebar_html: str = "", favicon_path: str = "favicon.ico") -> str:
    """Wrap body HTML in a styled index page shell matching the blog aesthetic."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>{html.escape(title)}</title>
  <link rel="icon" href="{favicon_path}">
  <style>
    :root {{
      --text-primary: #1a1a1a; --text-body: #333336; --text-secondary: #6e6e73;
      --bg-page: #fafafa; --bg-surface: #ffffff; --border: #e0e0e3;
      --accent: #0071e3; --accent-hover: #0077ED;
      --toggle-bg: rgba(0,0,0,0.04); --toggle-hover: rgba(0,0,0,0.08); --toggle-border: rgba(0,0,0,0.06);
      --font-display: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', sans-serif;
      --font-body: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', sans-serif;
    }}
    @media (prefers-color-scheme: dark) {{
      :root:not([data-theme="light"]) {{
        --text-primary: #f5f5f7; --text-body: #d1d1d6; --text-secondary: #8e8e93;
        --bg-page: #111113; --bg-surface: #1c1c1e; --border: #2c2c2e;
        --accent: #4db8ff; --accent-hover: #66c3ff;
        --toggle-bg: rgba(255,255,255,0.06); --toggle-hover: rgba(255,255,255,0.1); --toggle-border: rgba(255,255,255,0.08);
      }}
    }}
    [data-theme="dark"] {{
      --text-primary: #f5f5f7; --text-body: #d1d1d6; --text-secondary: #8e8e93;
      --bg-page: #111113; --bg-surface: #1c1c1e; --border: #2c2c2e;
      --accent: #4db8ff; --accent-hover: #66c3ff;
      --toggle-bg: rgba(255,255,255,0.06); --toggle-hover: rgba(255,255,255,0.1); --toggle-border: rgba(255,255,255,0.08);
    }}
    *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      font-family: var(--font-body); font-size: 16px; line-height: 1.55;
      color: var(--text-body); background: var(--bg-page);
      -webkit-font-smoothing: antialiased;
      transition: color 0.3s ease, background-color 0.3s ease;
    }}
    .theme-toggle {{
      position: fixed; top: 1.25rem; right: 1.25rem; z-index: 200;
      width: 40px; height: 40px; border-radius: 12px;
      border: 1px solid var(--toggle-border); background: var(--toggle-bg);
      backdrop-filter: blur(12px); cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      color: var(--text-secondary); transition: background 0.2s ease, transform 0.15s ease;
    }}
    .theme-toggle:hover {{ background: var(--toggle-hover); transform: scale(1.05); }}
    .page-layout {{
      display: flex; max-width: 1200px; margin: 0 auto; position: relative;
    }}
    .toc-sidebar {{
      position: sticky; top: 2.5rem; align-self: flex-start;
      width: 220px; min-width: 220px; padding: 0 1.5rem 2rem 2rem; margin-top: 10rem;
    }}
    .toc-sidebar .toc-label {{
      font-family: var(--font-body); font-size: 0.6875rem; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.1em;
      color: var(--text-secondary); margin-bottom: 1rem;
    }}
    .toc-sidebar ul {{ list-style: none; }}
    .toc-sidebar li {{ margin-bottom: 0.125rem; }}
    .toc-sidebar a {{
      display: block; font-family: var(--font-body); font-size: 0.8125rem; font-weight: 400;
      color: var(--text-secondary); text-decoration: none;
      padding: 0.3rem 0 0.3rem 1rem; border-left: 2px solid var(--border);
      transition: color 0.2s ease, border-color 0.2s ease;
    }}
    .toc-sidebar a:hover {{ color: var(--accent); }}
    .toc-sidebar a.active {{ color: var(--accent); font-weight: 600; border-left-color: var(--accent); }}
    .container {{ flex: 1; min-width: 0; max-width: 780px; margin: 0 auto; padding: 4rem 2rem 6rem; }}
    h1 {{
      font-family: var(--font-display); font-size: 2.75rem; font-weight: 700;
      line-height: 1.15; letter-spacing: -0.025em; color: var(--text-primary);
      margin-bottom: 0.5rem;
    }}
    .subtitle {{
      font-family: var(--font-display); font-size: 1.125rem; font-style: italic;
      color: var(--text-secondary); margin-bottom: 2.5rem;
    }}
    .year-card {{
      display: flex; align-items: center; gap: 1.25rem;
      padding: 1.25rem 1.5rem; margin-bottom: 0.75rem;
      background: var(--bg-surface); border: 1px solid var(--border); border-radius: 12px;
      text-decoration: none; transition: border-color 0.2s ease, transform 0.1s ease;
    }}
    a.year-card:hover {{ border-color: var(--accent); transform: translateY(-1px); }}
    .year-thumb {{
      width: 120px; height: 68px; border-radius: 8px; object-fit: cover;
      flex-shrink: 0; background: var(--toggle-bg);
    }}
    .year-card-info {{ flex: 1; min-width: 0; }}
    .year-card .year-title {{
      font-family: var(--font-display); font-size: 1.375rem; font-weight: 600;
      color: var(--text-primary);
    }}
    .year-card .year-meta {{
      font-size: 0.8125rem; color: var(--text-secondary); margin-top: 0.25rem;
    }}
    .session-list {{ list-style: none; }}
    .session-item {{
      padding: 1rem 1.25rem; margin-bottom: 0.5rem;
      background: var(--bg-surface); border: 1px solid var(--border); border-radius: 10px;
      transition: border-color 0.2s ease, transform 0.1s ease;
    }}
    .session-item.has-article {{ display: flex; align-items: center; gap: 1rem; }}
    .session-item a {{
      text-decoration: none; display: flex; align-items: center; gap: 1rem; flex: 1; min-width: 0;
    }}
    .session-item a .session-info, .session-item-inner .session-info {{ flex: 1; min-width: 0; }}
    .session-item-inner {{
      display: flex; align-items: center; gap: 1rem;
    }}
    .session-item.has-article:hover {{ border-color: var(--accent); transform: translateY(-1px); }}
    .session-thumb {{
      width: 100px; height: 56px; border-radius: 6px; object-fit: cover;
      flex-shrink: 0; background: var(--toggle-bg);
    }}
    .session-item:not(.has-article) .session-thumb {{ opacity: 0.6; }}
    .session-title {{
      font-family: var(--font-body); font-size: 1rem; font-weight: 600;
      color: var(--text-primary);
    }}
    .session-item:not(.has-article) .session-title {{ color: var(--text-secondary); }}
    .session-meta {{
      font-size: 0.8125rem; color: var(--text-secondary); margin-top: 0.25rem;
    }}
    .badge.available {{
      flex-shrink: 0; align-self: center;
      font-family: var(--font-body); font-size: 0.6875rem; font-weight: 600;
      letter-spacing: 0.03em;
      padding: 0.25rem 0.75rem; border-radius: 100px;
      color: var(--accent);
      background: color-mix(in srgb, var(--accent) 10%, transparent);
      border: 1px solid color-mix(in srgb, var(--accent) 20%, transparent);
    }}
    .topic-heading {{
      font-family: var(--font-display); font-size: 1.375rem; font-weight: 600;
      color: var(--text-primary); letter-spacing: -0.02em;
      margin: 2.5rem 0 0.75rem; padding-top: 1.5rem;
      border-top: 1px solid var(--border);
      display: flex; align-items: center; gap: 0.625rem;
    }}
    .topic-heading:first-of-type {{ margin-top: 0; padding-top: 0; border-top: none; }}
    .topic-count {{
      font-family: var(--font-body); font-size: 0.75rem; font-weight: 600;
      color: var(--text-secondary); background: var(--toggle-bg);
      border-radius: 100px; padding: 0.125rem 0.5rem;
    }}
    .back-link {{
      display: inline-flex; align-items: center; gap: 0.375rem;
      font-size: 0.875rem; font-weight: 500; color: var(--accent);
      text-decoration: none; margin-bottom: 2rem;
    }}
    .back-link:hover {{ color: var(--accent-hover); }}
    .btn-prompt {{
      flex-shrink: 0; align-self: center;
      font-family: var(--font-body); font-size: 0.6875rem; font-weight: 600;
      letter-spacing: 0.03em;
      padding: 0.25rem 0.75rem; border-radius: 100px;
      color: var(--text-secondary);
      background: var(--toggle-bg);
      border: 1px solid var(--border);
      cursor: pointer;
      transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
    }}
    .btn-prompt:hover {{ color: var(--accent); border-color: var(--accent); background: color-mix(in srgb, var(--accent) 8%, transparent); }}
    .btn-prompt.copied {{ color: #34c759; border-color: #34c759; background: color-mix(in srgb, #34c759 8%, transparent); }}
    @media (max-width: 1080px) {{
      .toc-sidebar {{ display: none; }}
      .page-layout {{ display: block; }}
      .container {{ max-width: 720px; margin: 0 auto; }}
    }}
    @media (max-width: 640px) {{
      .container {{ padding: 2.5rem 1.25rem 4rem; }}
      h1 {{ font-size: 2rem; }}
    }}
    .read-check {{
      flex-shrink: 0; align-self: center; cursor: pointer;
      display: flex; align-items: center;
      position: relative; z-index: 10; padding: 0.25rem;
    }}
    .read-check input[type="checkbox"] {{
      width: 18px; height: 18px; cursor: pointer;
      accent-color: var(--accent); border-radius: 4px;
      pointer-events: auto;
    }}
    .session-item.is-read {{ opacity: 0.5; }}
    .session-item.is-read:hover {{ opacity: 0.75; }}
    .hero-gradient {{
      position: fixed; top: 0; left: 0; right: 0; height: 420px;
      overflow: hidden; pointer-events: none; z-index: 0;
      mask-image: linear-gradient(to bottom, black 40%, transparent 100%);
      -webkit-mask-image: linear-gradient(to bottom, black 40%, transparent 100%);
    }}
    .hero-orb {{
      position: absolute; border-radius: 50%; filter: blur(80px); opacity: 0.5;
      animation: orb-drift 12s ease-in-out infinite alternate;
    }}
    @keyframes orb-drift {{
      0% {{ transform: translate(0, 0) scale(1); }}
      33% {{ transform: translate(15px, 10px) scale(1.05); }}
      66% {{ transform: translate(-10px, 15px) scale(0.95); }}
      100% {{ transform: translate(5px, -5px) scale(1.02); }}
    }}
  </style>
</head>
<body>
  <button class="theme-toggle" id="theme-toggle" aria-label="Toggle theme"></button>
  <div class="page-layout">
{sidebar_html}    <div class="container">
{body_html}
    </div>
  </div>
  <script>
    (function() {{
      var root = document.documentElement, toggle = document.getElementById('theme-toggle');
      var sun = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
      var moon = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
      function getTheme() {{ var t = root.getAttribute('data-theme'); if (t) return t; return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'; }}
      function applyIcon() {{ toggle.innerHTML = getTheme() === 'dark' ? sun : moon; }}
      var saved = localStorage.getItem('wwdc-blog-theme'); if (saved) root.setAttribute('data-theme', saved);
      applyIcon(); matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyIcon);
      toggle.addEventListener('click', function() {{
        var next = getTheme() === 'dark' ? 'light' : 'dark';
        root.setAttribute('data-theme', next); localStorage.setItem('wwdc-blog-theme', next); applyIcon();
      }});
      var headings = document.querySelectorAll('h2[id]');
      var tocLinks = document.querySelectorAll('.toc-sidebar a');
      if (headings.length && tocLinks.length) {{
        var observer = new IntersectionObserver(function(entries) {{
          entries.forEach(function(e) {{
            if (e.isIntersecting) {{
              tocLinks.forEach(function(a) {{ a.classList.remove('active'); }});
              var sel = '.toc-sidebar a[href="#' + e.target.id + '"]';
              var active = document.querySelector(sel);
              if (active) active.classList.add('active');
            }}
          }});
        }}, {{ rootMargin: '0px 0px -75% 0px' }});
        headings.forEach(function(h) {{ observer.observe(h); }});
        tocLinks[0].classList.add('active');
      }}
      document.querySelectorAll('.btn-prompt').forEach(function(btn) {{
        btn.addEventListener('click', function() {{
          var text = btn.getAttribute('data-prompt');
          navigator.clipboard.writeText(text).then(function() {{
            var orig = btn.textContent;
            btn.textContent = 'Copied!';
            btn.classList.add('copied');
            setTimeout(function() {{ btn.textContent = orig; btn.classList.remove('copied'); }}, 1500);
          }});
        }});
      }});
      // Read checkboxes — localStorage persistence
      var readState = JSON.parse(localStorage.getItem('wwdc-blog-read') || '{{}}');
      document.querySelectorAll('.read-check input[type="checkbox"]').forEach(function(cb) {{
        var key = cb.getAttribute('data-session');
        var item = cb.closest('.session-item');
        if (readState[key]) {{ cb.checked = true; item.classList.add('is-read'); }}
        cb.addEventListener('click', function(e) {{
          e.stopPropagation();
        }});
        cb.addEventListener('change', function() {{
          if (cb.checked) {{ readState[key] = true; }} else {{ delete readState[key]; }}
          localStorage.setItem('wwdc-blog-read', JSON.stringify(readState));
          item.classList.toggle('is-read', cb.checked);
        }});
      }});
    }})();
  </script>
</body>
</html>"""


def generate_year_index(catalog: dict, event_id: str, output_base: str) -> str:
    """Generate an index page listing all sessions for a given WWDC year.

    Sessions are grouped by topic, with articles-first within each group.
    Returns the path to the generated index.html.
    """
    contents = catalog.get("contents", [])
    sessions = [c for c in contents if c.get("eventId") == event_id and c.get("media")]

    # Build topic ID -> name map
    topic_map = {t["id"]: t["title"] for t in catalog.get("topics", [])}
    topic_order = {t["id"]: t.get("ordinal", 999) for t in catalog.get("topics", [])}

    # Build event images base path for thumbnails
    event_images_path = ""
    for ev in catalog.get("events", []):
        if ev.get("id") == event_id:
            event_images_path = ev.get("imagesPath", "")
            break

    event_dir = os.path.join(output_base, event_id)
    os.makedirs(event_dir, exist_ok=True)

    # Helper to check if a session has a generated article
    def _has_article(s):
        sid = s.get("id", "")
        num = sid.split("-")[-1] if "-" in sid else sid
        return os.path.isfile(os.path.join(event_dir, num, "index.html"))

    def _thumbnail_url(s):
        scid = s.get("staticContentId")
        if event_images_path and scid:
            return f"{event_images_path}/{scid}/{scid}_wide_250x141_2x.jpg"
        return ""

    # Group sessions by primary topic
    from collections import defaultdict
    groups = defaultdict(list)
    for s in sessions:
        topic_id = s.get("primaryTopicID")
        groups[topic_id].append(s)

    # Sort groups: topics with articles first, then by catalog ordinal
    def _group_sort_key(topic_id):
        has_any_article = any(_has_article(s) for s in groups[topic_id])
        return (0 if has_any_article else 1, topic_order.get(topic_id, 999))

    sorted_topic_ids = sorted(groups.keys(), key=_group_sort_key)

    # Sort sessions within each group: articles first, then alphabetically
    for topic_id in sorted_topic_ids:
        groups[topic_id].sort(key=lambda s: (0 if _has_article(s) else 1, s.get("title", "")))

    event_name = event_id.upper().replace("WWDC", "WWDC ")
    total_articles = sum(1 for s in sessions if _has_article(s))

    # Build slug for each topic (for anchors and TOC)
    def _topic_slug(topic_id):
        name = topic_map.get(topic_id, "other")
        return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

    # Build sidebar TOC
    sidebar_parts = []
    sidebar_parts.append('    <nav class="toc-sidebar" aria-label="Topics">')
    sidebar_parts.append('      <div class="toc-label">Topics</div>')
    sidebar_parts.append('      <ul>')
    for topic_id in sorted_topic_ids:
        topic_name = topic_map.get(topic_id, "Other")
        slug = _topic_slug(topic_id)
        sidebar_parts.append(f'        <li><a href="#{slug}">{html.escape(topic_name)}</a></li>')
    sidebar_parts.append('      </ul>')
    sidebar_parts.append('    </nav>')
    sidebar_html = "\n".join(sidebar_parts) + "\n"

    body = []
    body.append(f'    <a class="back-link" href="../index.html">&larr; All years</a>')
    body.append(f'    <h1>{html.escape(event_name)}</h1>')
    body.append(f'    <p class="subtitle">{len(sessions)} sessions &middot; {total_articles} articles</p>')

    for topic_id in sorted_topic_ids:
        topic_name = topic_map.get(topic_id, "Other")
        slug = _topic_slug(topic_id)
        topic_sessions = groups[topic_id]

        body.append(f'    <h2 id="{slug}" class="topic-heading">{html.escape(topic_name)}'
                    f'<span class="topic-count">{len(topic_sessions)}</span></h2>')
        body.append(f'    <ul class="session-list">')

        for s in topic_sessions:
            sid = s.get("id", "")
            num = sid.split("-")[-1] if "-" in sid else sid
            stitle = html.escape(s.get("title", "Untitled"))
            desc = s.get("description", "")
            short_desc = html.escape(desc[:120] + "..." if len(desc) > 120 else desc)
            has_art = _has_article(s)
            # Use local thumbnail for sessions with articles, CDN for others
            local_thumb = os.path.join(event_dir, num, "thumb.jpg")
            if has_art and os.path.isfile(local_thumb):
                thumb_src = f"{num}/thumb.jpg"
            else:
                thumb_src = _thumbnail_url(s)
            thumb_html = f'<img class="session-thumb" src="{html.escape(thumb_src)}" alt="" loading="lazy">' if thumb_src else ""

            if has_art:
                body.append(f'      <li class="session-item has-article"><a href="{num}/index.html">')
                body.append(f'        {thumb_html}')
                body.append(f'        <div class="session-info"><div class="session-title">{stitle}</div>')
                if short_desc:
                    body.append(f'        <div class="session-meta">{short_desc}</div>')
                body.append(f'        </div><span class="badge available">Article</span>')
                body.append(f'      </a><label class="read-check"><input type="checkbox" data-session="{event_id}/{num}"></label></li>')
            else:
                prompt_text = f'/wwdc-blog for &quot;{stitle}&quot; from {event_name}'
                body.append(f'      <li class="session-item"><div class="session-item-inner">')
                body.append(f'        {thumb_html}')
                body.append(f'        <div class="session-info"><div class="session-title">{stitle}</div>')
                if short_desc:
                    body.append(f'        <div class="session-meta">{short_desc}</div>')
                body.append(f'        </div>')
                body.append(f'        <button class="btn-prompt" data-prompt="{prompt_text}" title="Copy prompt to clipboard">Prompt</button>')
                body.append(f'        <label class="read-check"><input type="checkbox" data-session="{event_id}/{num}"></label>')
                body.append(f'      </div></li>')

        body.append(f'    </ul>')

    page_html = _index_page_shell(event_name, "\n".join(body), sidebar_html, favicon_path="../favicon.ico")
    index_path = os.path.join(event_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(page_html)
    return index_path


def generate_root_index(catalog: dict, output_base: str) -> str:
    """Generate the root index page listing all WWDC years that have content.

    Returns the path to the generated index.html.
    """
    contents = catalog.get("contents", [])

    # Collect all event IDs from the catalog
    all_events = sorted(set(c.get("eventId", "") for c in contents if c.get("eventId")), reverse=True)

    import random as _rng
    _seed = _rng.Random("wwdc-root")
    root_colors = ("#6e3aff", "#ff6b9d", "#00b4d8", "#ffc857")
    root_orbs = []
    for color in root_colors:
        w = _seed.randint(200, 360)
        h = w + _seed.randint(-30, 30)
        top = _seed.randint(-90, 60)
        left = _seed.randint(5, 65)
        dur = _seed.uniform(9, 15)
        delay = _seed.uniform(-10, 0)
        root_orbs.append(
            f'      <div class="hero-orb" style="width:{w}px;height:{h}px;top:{top}px;left:{left}%;'
            f'background:radial-gradient(circle,{color} 0%,transparent 70%);'
            f'animation-duration:{dur:.1f}s;animation-delay:{delay:.1f}s"></div>'
        )
    body = []
    body.append('    <div class="hero-gradient" aria-hidden="true">')
    body.append("\n".join(root_orbs))
    body.append('    </div>')
    body.append(f'    <h1>WWDC Sessions</h1>')
    body.append(f'    <p class="subtitle">Blog posts generated from Apple developer session videos</p>')

    for event_id in all_events:
        event_dir = os.path.join(output_base, event_id)
        if not os.path.isdir(event_dir):
            continue

        # Count generated articles
        event_sessions = [c for c in contents if c.get("eventId") == event_id and c.get("media")]
        generated = sum(
            1 for c in event_sessions
            if os.path.isfile(os.path.join(event_dir,
                                           (c.get("id", "").split("-")[-1] if "-" in c.get("id", "") else c.get("id", "")),
                                           "index.html"))
        )
        total = len(event_sessions)
        event_name = event_id.upper().replace("WWDC", "WWDC ")

        has_year_index = os.path.isfile(os.path.join(event_dir, "index.html"))
        tag = "a" if has_year_index else "div"
        href = f' href="{event_id}/index.html"' if has_year_index else ""
        body.append(f'    <{tag} class="year-card"{href}>')
        year_thumb = os.path.join(event_dir, "thumb.jpg")
        if os.path.isfile(year_thumb):
            body.append(f'      <img class="year-thumb" src="{event_id}/thumb.jpg" alt="{html.escape(event_name)}">')
        body.append(f'      <div class="year-card-info">')
        body.append(f'        <div class="year-title">{html.escape(event_name)}</div>')
        body.append(f'        <div class="year-meta">{generated} of {total} sessions generated</div>')
        body.append(f'      </div>')
        body.append(f'    </{tag}>')

    page_html = _index_page_shell("WWDC Sessions", "\n".join(body))
    index_path = os.path.join(output_base, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(page_html)
    return index_path


def create_blog(query: str, output_base: str = ".", quality: str = "hd",
                scene_threshold: float = 0.3, settle_delay: float = 1.0,
                min_gap: float = 3.0, filter_frames: bool = True,
                bright_threshold: float = 25.0,
                keep_video: bool = False,
                retake_snapshots: bool = False) -> str:
    """Main pipeline: resolve session, download video, extract transcript, detect scenes, generate HTML.

    Returns the path to the generated index.html.
    """
    # Step 1: Resolve session
    print("Fetching WWDC catalog...", file=sys.stderr)
    catalog = get_wwdc_catalog()
    session = find_session(catalog, query)
    if not session:
        raise ValueError(f"No session found matching: {query}")

    event_id = session.get("eventId", "unknown")
    session_id = session.get("id", "unknown")
    session_num = session_id.split("-")[-1] if "-" in session_id else session_id
    title = session.get("title", "session")

    print(f"Found: {title} ({event_id}/{session_num})", file=sys.stderr)

    # Step 2: Download video
    output_dir = os.path.join(output_base, event_id, session_num)
    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    # Download session thumbnail
    thumb_path = os.path.join(output_dir, "thumb.jpg")
    if not os.path.exists(thumb_path):
        scid = session.get("staticContentId")
        event_images_path = ""
        for ev in catalog.get("events", []):
            if ev.get("id") == event_id:
                event_images_path = ev.get("imagesPath", "")
                break
        if event_images_path and scid:
            thumb_url = f"{event_images_path}/{scid}/{scid}_wide_250x141_2x.jpg"
            try:
                data = fetch_url(thumb_url)
                with open(thumb_path, "wb") as f:
                    f.write(data)
                print(f"  Thumbnail saved: {thumb_path}", file=sys.stderr)
            except Exception as e:
                print(f"  Thumbnail download failed: {e}", file=sys.stderr)

    # Download year thumbnail from wwdcnotes.com if not already present
    event_dir = os.path.join(output_base, event_id)
    year_thumb_path = os.path.join(event_dir, "thumb.jpg")
    if not os.path.exists(year_thumb_path):
        year_suffix = event_id.replace("wwdc", "")[-2:]
        downloaded = False
        for ext in ("jpg", "jpeg"):
            year_thumb_url = f"https://wwdcnotes.com/images/WWDCNotes/WWDC{year_suffix}.{ext}"
            try:
                subprocess.run(
                    ["curl", "-sL", "--fail", "-o", year_thumb_path, year_thumb_url],
                    timeout=30, check=True
                )
                print(f"  Year thumbnail saved: {year_thumb_path}", file=sys.stderr)
                downloaded = True
                break
            except Exception:
                if os.path.exists(year_thumb_path):
                    os.remove(year_thumb_path)
        if not downloaded:
            print(f"  Year thumbnail not available for {event_id}", file=sys.stderr)

    # Step 3: Extract transcript and chapters (cached as JSON)
    permalink = build_web_permalink(session)
    transcript_cache = os.path.join(output_dir, "transcript.json")
    if os.path.exists(transcript_cache):
        print(f"Loading cached transcript from {transcript_cache}...", file=sys.stderr)
        with open(transcript_cache, "r", encoding="utf-8") as f:
            cached = json.load(f)
        transcript, chapters = cached["transcript"], cached["chapters"]
    else:
        print(f"Fetching transcript from {permalink}...", file=sys.stderr)
        transcript, chapters = get_transcript_and_chapters(permalink)
        with open(transcript_cache, "w", encoding="utf-8") as f:
            json.dump({"transcript": transcript, "chapters": chapters}, f)
    print(f"  {len(transcript)} transcript lines, {len(chapters)} chapters", file=sys.stderr)

    # Step 3b: YouTube video lookup (cached)
    youtube_cache = os.path.join(output_dir, "youtube.json")
    youtube_id = None
    if os.path.exists(youtube_cache):
        with open(youtube_cache, "r") as f:
            youtube_id = json.load(f).get("id")
        if youtube_id:
            print(f"  Using cached YouTube video: {youtube_id}", file=sys.stderr)
    else:
        youtube_id = find_youtube_video(event_id, title)
        with open(youtube_cache, "w") as f:
            json.dump({"id": youtube_id}, f)

    # Step 4-6: Detect scenes, extract frames, filter (cached as JSON)
    frames_cache = os.path.join(output_dir, "frames.json")
    need_video = retake_snapshots or not os.path.exists(frames_cache)

    if retake_snapshots and os.path.exists(frames_cache):
        os.remove(frames_cache)
        for f in glob.glob(os.path.join(images_dir, "frame_*.jpg")):
            os.remove(f)
        print("  Cleared existing frames for retake", file=sys.stderr)

    if need_video:
        print("Downloading video...", file=sys.stderr)
        video_path = download_session(query, output_dir, quality)

        print("Detecting scene changes...", file=sys.stderr)
        scene_times = detect_scene_changes(video_path, scene_threshold)
        print(f"  {len(scene_times)} raw scene changes detected", file=sys.stderr)

        scene_times = deduplicate_timestamps(scene_times, min_gap)
        print(f"  {len(scene_times)} after deduplication (min gap {min_gap}s)", file=sys.stderr)

        print("Extracting frames...", file=sys.stderr)
        frames = extract_frames(video_path, scene_times, images_dir, settle_delay)
        print(f"  {len(frames)} frames captured", file=sys.stderr)

        if filter_frames:
            frames = filter_speaker_frames(frames, images_dir, bright_threshold)

        with open(frames_cache, "w") as f:
            json.dump(frames, f)

        if not keep_video:
            os.remove(video_path)
            print(f"  Video deleted: {video_path}", file=sys.stderr)
    else:
        print(f"Loading cached frames from {frames_cache}...", file=sys.stderr)
        with open(frames_cache, "r") as f:
            frames = json.load(f)
        print(f"  {len(frames)} cached frames", file=sys.stderr)

    # Step 7: Generate HTML
    print("Generating HTML...", file=sys.stderr)
    code_snippets = session.get("codeSnippets", [])
    if code_snippets:
        print(f"  {len(code_snippets)} code snippets", file=sys.stderr)
    html_content = generate_html(session, transcript, frames, images_dir, chapters, code_snippets, youtube_id)
    html_path = os.path.join(output_dir, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\nBlog post created: {html_path}", file=sys.stderr)
    print(f"  {len(frames)} slide images in {images_dir}", file=sys.stderr)
    print(f"  {len(transcript)} transcript lines", file=sys.stderr)

    # Download favicon to root if not present
    favicon_path = os.path.join(output_base, "favicon.ico")
    if not os.path.exists(favicon_path):
        try:
            data = fetch_url("https://developer.apple.com/favicon.ico")
            with open(favicon_path, "wb") as f:
                f.write(data)
            print(f"  Favicon saved: {favicon_path}", file=sys.stderr)
        except Exception as e:
            print(f"  Favicon download failed: {e}", file=sys.stderr)

    # Step 8: Update index pages
    print("Updating index pages...", file=sys.stderr)
    year_index = generate_year_index(catalog, event_id, output_base)
    root_index = generate_root_index(catalog, output_base)
    print(f"  Year index: {year_index}", file=sys.stderr)
    print(f"  Root index: {root_index}", file=sys.stderr)

    return html_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate a blog-post HTML from a WWDC session")
    parser.add_argument("query", help="Session URL, ID (wwdc2025/230), number, or title")
    parser.add_argument("-o", "--output-dir", default=".", help="Base output directory")
    parser.add_argument("-q", "--quality", choices=["hd", "sd"], default="hd", help="Video quality")
    parser.add_argument("--threshold", type=float, default=0.3, help="Scene change threshold (0-1)")
    parser.add_argument("--settle", type=float, default=1.0, help="Seconds to wait after scene change")
    parser.add_argument("--min-gap", type=float, default=3.0, help="Min seconds between captures")
    parser.add_argument("--no-filter", action="store_true", help="Disable speaker-frame filtering")
    parser.add_argument("--bright-threshold", type=float, default=25.0,
                        help="Bright pixel %% threshold for split-screen detection (default: 25)")
    parser.add_argument("--keep-video", action="store_true",
                        help="Keep the downloaded video after frame extraction")
    parser.add_argument("--retake-snapshots", action="store_true",
                        help="Force re-download video and re-extract frames")
    args = parser.parse_args()

    try:
        path = create_blog(args.query, args.output_dir, args.quality,
                          args.threshold, args.settle, args.min_gap,
                          filter_frames=not args.no_filter,
                          bright_threshold=args.bright_threshold,
                          keep_video=args.keep_video,
                          retake_snapshots=args.retake_snapshots)
        print(path)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
