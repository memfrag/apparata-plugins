#!/usr/bin/env python3
"""
Download HD (or SD) video for a WWDC session.

Looks up the session in the WWDC catalog by URL, event+session ID, or title,
then downloads the video file with progress reporting.
"""

import os
import re
import ssl
import sys
import urllib.error
import urllib.request

# Reuse the catalog fetcher
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CATALOG_SCRIPT = os.path.join(SCRIPT_DIR, "..", "..", "wwdc-catalog", "scripts")
sys.path.insert(0, CATALOG_SCRIPT)
from wwdc_catalog import get_wwdc_catalog


def find_session(catalog: dict, query: str) -> dict | None:
    """Find a session in the catalog by URL, event/session ID, or title search.

    Supports:
      - Full URL: https://developer.apple.com/videos/play/wwdc2025/230
      - Short ID: wwdc2025/230 or wwdc2025-230
      - Session number: 230 (matches most recent event first)
      - Title substring: "AlarmKit"
    """
    contents = catalog.get("contents", [])

    # Try URL match — extract event and session number, build exact ID
    url_match = re.search(r"/videos/play/([^/]+)/(\d+)", query)
    if url_match:
        event_id, session_num = url_match.group(1), url_match.group(2)
        expected_id = f"{event_id}-{session_num}"
        for c in contents:
            if c.get("id") == expected_id:
                return c

    # Try event/session ID (e.g. wwdc2025/230 or wwdc2025-230)
    id_match = re.match(r"([a-z-]+\d{4})[/-](\d+)", query, re.I)
    if id_match:
        event_id, session_num = id_match.group(1).lower(), id_match.group(2)
        expected_id = f"{event_id}-{session_num}"
        for c in contents:
            if c.get("id") == expected_id:
                return c

    # Try bare session number — exact suffix match, prefer most recent event
    if re.match(r"^\d+$", query):
        candidates = [c for c in contents
                      if c.get("id", "").endswith(f"-{query}") and c.get("media")]
        if candidates:
            candidates.sort(key=lambda c: c.get("eventId", ""), reverse=True)
            return candidates[0]

    # Try title substring search
    q = query.lower()
    candidates = [c for c in contents
                  if q in c.get("title", "").lower() and c.get("media")]
    if candidates:
        candidates.sort(key=lambda c: c.get("eventId", ""), reverse=True)
        return candidates[0]

    return None


def download_video(url: str, output_path: str) -> str:
    """Download a video file with progress reporting. Returns the output path."""
    req = urllib.request.Request(url)
    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLCertVerificationError):
            ctx = ssl._create_unverified_context()
            resp = urllib.request.urlopen(req, context=ctx)
        else:
            raise

    total = int(resp.headers.get("Content-Length", 0))
    downloaded = 0
    block_size = 1024 * 1024  # 1 MB

    with open(output_path, "wb") as f:
        while True:
            chunk = resp.read(block_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = downloaded * 100 / total
                mb = downloaded / (1024 * 1024)
                total_mb = total / (1024 * 1024)
                print(f"\r  {mb:.0f}/{total_mb:.0f} MB ({pct:.1f}%)", end="", file=sys.stderr)
            else:
                mb = downloaded / (1024 * 1024)
                print(f"\r  {mb:.0f} MB", end="", file=sys.stderr)

    resp.close()
    print(file=sys.stderr)
    return output_path


def sanitize_filename(name: str) -> str:
    """Create a safe filename from a session title."""
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    return name


def download_session(query: str, output_dir: str = ".", quality: str = "hd") -> str:
    """Find a session and download its video. Returns the output file path."""
    catalog = get_wwdc_catalog()
    session = find_session(catalog, query)

    if not session:
        raise ValueError(f"No session found matching: {query}")

    media = session.get("media")
    if not media:
        raise ValueError(f"Session '{session['title']}' has no media")

    key = "downloadHD" if quality == "hd" else "downloadSD"
    url = media.get(key)
    if not url:
        alt_key = "downloadSD" if quality == "hd" else "downloadHD"
        url = media.get(alt_key)
        if url:
            actual = "SD" if quality == "hd" else "HD"
            print(f"  {quality.upper()} not available, falling back to {actual}", file=sys.stderr)
        else:
            raise ValueError(f"Session '{session['title']}' has no download URL")

    event_id = session.get("eventId", "unknown")
    title = sanitize_filename(session.get("title", "session"))
    ext = os.path.splitext(url.split("?")[0])[-1] or ".mp4"
    filename = f"{event_id}_{title}{ext}"
    output_path = os.path.join(output_dir, filename)

    print(f"Session: {session['title']}", file=sys.stderr)
    print(f"Event:   {event_id}", file=sys.stderr)
    print(f"URL:     {url}", file=sys.stderr)
    print(f"Output:  {output_path}", file=sys.stderr)

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"Already downloaded: {output_path} ({size_mb:.1f} MB)", file=sys.stderr)
        return output_path

    print(f"Downloading...", file=sys.stderr)

    download_video(url, output_path)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"Done: {output_path} ({size_mb:.1f} MB)", file=sys.stderr)
    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Download WWDC session video")
    parser.add_argument("query", help="Session URL, ID (wwdc2025/230), number, or title")
    parser.add_argument("-o", "--output-dir", default=".", help="Output directory")
    parser.add_argument("-q", "--quality", choices=["hd", "sd"], default="hd",
                        help="Video quality (default: hd)")
    args = parser.parse_args()

    try:
        path = download_session(args.query, args.output_dir, args.quality)
        print(path)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
