---
name: wwdc-download
description: Download WWDC session videos in HD or SD quality. Use this skill whenever the user wants to download a WWDC video, save a session video to disk, or get the video file for a specific WWDC talk. Supports lookup by URL, session ID (e.g. "wwdc2025/230"), session number, or title. Also use when the user says things like "download the AlarmKit session" or "grab the HD video for session 287".
---

# WWDC Video Downloader

Downloads WWDC session videos from Apple's CDN. Finds the session in the catalog by URL, ID, session number, or title, then downloads the HD (or SD) MP4 file with progress reporting.

## Prerequisites

- macOS with `/Applications/Developer.app` installed (the `wwdc-catalog` skill is used to look up sessions)
- Python 3
- Internet access to devstreaming-cdn.apple.com

## Downloading a video

```bash
# By session URL
python3 <skill-dir>/scripts/wwdc_download.py "https://developer.apple.com/videos/play/wwdc2025/230/"

# By event/session ID
python3 <skill-dir>/scripts/wwdc_download.py "wwdc2025/230"

# By session number (picks most recent event)
python3 <skill-dir>/scripts/wwdc_download.py "230"

# By title
python3 <skill-dir>/scripts/wwdc_download.py "AlarmKit"

# SD quality, custom output directory
python3 <skill-dir>/scripts/wwdc_download.py "wwdc2025/230" -q sd -o ~/Downloads
```

Replace `<skill-dir>` with the actual path to this skill's directory.

## Options

| Flag | Description |
|------|-------------|
| `-q`, `--quality` | `hd` (default) or `sd`. Falls back to the other if preferred isn't available. |
| `-o`, `--output-dir` | Directory to save the file (default: current directory). |

## Output

The script saves the video as `{eventId}_{Title}.mp4` (e.g. `wwdc2025_Wake_up_to_the_AlarmKit_API.mp4`) and prints the output path to stdout. Progress is shown on stderr.

## As a module

```python
import sys; sys.path.insert(0, '<skill-dir>/scripts')
from wwdc_download import download_session, find_session
from wwdc_catalog import get_wwdc_catalog

# Download directly
path = download_session("wwdc2025/230", output_dir="~/Downloads")

# Or find the session first to inspect it
catalog = get_wwdc_catalog()
session = find_session(catalog, "wwdc2025/230")
print(session["media"]["downloadHD"])  # Just get the URL without downloading
```

## Tips

- HD videos are typically 100-500 MB for a 20-40 minute session. SD is roughly a third of that.
- Not all sessions have download URLs — some only have HLS streams. The script will report this.
- When searching by bare session number, the most recent event is preferred if multiple events have the same number.
- The script depends on the `wwdc-catalog` skill being installed alongside it.
