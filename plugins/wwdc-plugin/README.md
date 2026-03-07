# WWDC Plugin

A collection of skills for working with Apple WWDC session content. Browse the session catalog, download videos, extract transcripts, and generate blog-style HTML pages with interleaved slides and transcript text.

## Skills

### wwdc-catalog
Fetch the full WWDC session catalog from Apple's CDN. Browse, search, and look up sessions from WWDC14 through the latest year.

### wwdc-download
Download WWDC session videos in HD or SD quality by URL, session ID, session number, or title.

### wwdc-transcript
Extract timestamped transcripts from WWDC session pages on developer.apple.com.

### wwdc-blog
Generate blog-post-style HTML pages from WWDC sessions, interleaving transcript text with slide screenshots captured at scene changes. Uses macOS Vision framework to filter out speaker-only frames.

## Prerequisites

- macOS with `/Applications/Developer.app` installed (free from the Mac App Store)
- ffmpeg installed and on PATH (for wwdc-blog)
- Python 3.10+
