---
name: wwdc-transcript
description: Extract timestamped transcripts from WWDC session videos. Use this skill whenever the user wants to read, search, or get the transcript of a WWDC session or Apple developer video — even if they just say something like "what did they say about concurrency in that talk" or "get me the transcript for session 230". Also use this when the user provides a developer.apple.com/videos URL and wants to know what the video covers.
---

# WWDC Transcript Extractor

This skill extracts timestamped transcripts from WWDC session pages on developer.apple.com. Each transcript line includes the time offset in seconds and the spoken text.

## How it works

WWDC session pages embed transcripts as HTML with `<span data-start="N">` elements inside a `#transcript-content` section. The bundled script fetches the page and parses these into a clean JSON array.

## Prerequisites

- Python 3
- Internet access to developer.apple.com

## Extracting a transcript

Run the bundled script with a session URL:

```bash
# Human-readable with timestamps
python3 <skill-dir>/scripts/wwdc_transcript.py https://developer.apple.com/videos/play/wwdc2025/230/

# JSON output
python3 <skill-dir>/scripts/wwdc_transcript.py https://developer.apple.com/videos/play/wwdc2025/230/ --json
```

Or import as a module:

```python
import sys; sys.path.insert(0, '<skill-dir>/scripts')
from wwdc_transcript import get_transcript

transcript = get_transcript("https://developer.apple.com/videos/play/wwdc2025/230/")
# Returns: [{"time": 7.0, "text": "Hey, I'm Anton..."}, ...]
```

Replace `<skill-dir>` with the actual path to this skill's directory.

## Output format

### JSON (`--json`)

```json
[
  {"time": 7.0, "text": "Hey, I'm Anton, an engineer on the system experience team."},
  {"time": 11.0, "text": "In this session, you'll meet AlarmKit,"},
  {"time": 13.0, "text": "a framework that allows you to create alarms in your app."}
]
```

- `time` — seconds from the start of the video (float)
- `text` — the spoken text for that line

### Plain text (default)

```
[0:07] Hey, I'm Anton, an engineer on the system experience team.
[0:11] In this session, you'll meet AlarmKit,
[0:13] a framework that allows you to create alarms in your app.
```

## Combining with wwdc-catalog

Use the `wwdc-catalog` skill to find session URLs, then extract transcripts:

```python
# Get the webPermalink from a catalog content item
url = session["webPermalink"]  # e.g. https://developer.apple.com/videos/play/wwdc2025/230
transcript = get_transcript(url)
```

## Tips

- Not all sessions have transcripts — very old or non-video content may lack them. The script raises `ValueError` if no transcript section is found.
- Transcripts typically have 100-1500 lines depending on session length.
- The `time` field can be used to link directly to that point in the video by appending `?time=N` to the session URL.
