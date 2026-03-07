---
description: Generate a blog-post-style HTML page from a WWDC session, interleaving transcript text with slide screenshots. Use when the user wants to create a blog post, readable page, or visual summary from a WWDC talk — e.g. "create blog post from WWDC session 230", "generate HTML for that WWDC talk", "make a readable version of the AlarmKit session".
---

# wwdc-blog

Generate a blog-post HTML page for a WWDC session by combining video, transcript, and slide screenshots.

## What it does

1. Resolves the session from the WWDC catalog
2. Downloads the HD video
3. Extracts the timestamped transcript
4. Detects scene changes in the video using ffmpeg
5. Captures settled frames (slide screenshots) at each scene change
6. Filters out speaker-only frames using macOS Vision face detection + brightness analysis
7. Generates a clean HTML page interleaving transcript text with slide images

## Usage

```bash
python3 ~/.claude/skills/wwdc-blog/scripts/wwdc_blog.py "wwdc2025/230"
python3 ~/.claude/skills/wwdc-blog/scripts/wwdc_blog.py "AlarmKit" -o /tmp/wwdcvids
python3 ~/.claude/skills/wwdc-blog/scripts/wwdc_blog.py "wwdc2025/230" --threshold 0.25 --settle 1.0
python3 ~/.claude/skills/wwdc-blog/scripts/wwdc_blog.py "wwdc2025/230" --no-filter
```

### Options

- `-o, --output-dir`: Base output directory (default: current directory)
- `-q, --quality`: Video quality `hd` or `sd` (default: hd)
- `--threshold`: Scene change sensitivity 0-1 (default: 0.3, lower = more scenes detected)
- `--settle`: Seconds to wait after scene change before capturing frame (default: 0.4)
- `--min-gap`: Minimum seconds between frame captures (default: 3.0)
- `--no-filter`: Disable speaker-frame filtering (keep all frames)
- `--bright-threshold`: Bright pixel % threshold for split-screen detection (default: 25)

### Output

```
output-dir/<eventId>-<sessionNum>/
  index.html        # The blog post
  images/           # Slide screenshots
    frame_001.jpg
    frame_002.jpg
    ...
  <video>.mp4       # Downloaded video
```

## Prerequisites

- macOS with Developer.app installed (for catalog access)
- ffmpeg installed and on PATH
- Python 3.10+

## Programmatic use

```python
from wwdc_blog import create_blog
html_path = create_blog("wwdc2025/230", output_dir="/tmp/wwdcvids")
```
