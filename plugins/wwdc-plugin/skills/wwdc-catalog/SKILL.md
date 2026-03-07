---
name: wwdc-catalog
description: Fetch the WWDC session catalog from Apple's CDN by extracting the catalog URL from the Developer.app's WWDCCore binary. Use this skill whenever the user asks about WWDC sessions, WWDC videos, WWDC catalog, Apple developer conference content, or wants to browse, search, list, or look up any WWDC session or talk — even if they just say something like "what sessions are there about SwiftUI" or "find me that WWDC video about concurrency". Also use this when the user wants to download or work with WWDC session metadata.
---

# WWDC Catalog

This skill fetches the full WWDC session catalog from Apple's CDN. The catalog includes all events from WWDC14 through the latest year, along with videos, labs, articles, topics, and media URLs (video downloads, HLS streams, slides).

## How it works

The Apple Developer app (`/Applications/Developer.app`) ships with a framework called `WWDCCore` that contains an embedded CDN URL pointing to the session catalog. The bundled script reads this binary, finds the URL by searching for the `https://devimages-cdn.apple.com/wwdc-services/` prefix, and appends `contents.json` to fetch the full catalog.

The catalog is normalized after fetching: older WWDCs (<=2019) used `"Session"` as the content type while newer ones use `"Video"` — the script rewrites all `"Session"` types to `"Video"` so you can always filter on `type == "Video"` regardless of year.

## Prerequisites

- macOS with `/Applications/Developer.app` installed (free from the Mac App Store)
- Python 3

## Fetching the catalog

Run the bundled script to fetch the catalog as JSON:

```bash
python3 <skill-dir>/scripts/wwdc_catalog.py
```

This prints a summary to stdout and the catalog URL to stderr. To capture the full catalog as JSON, use the script as a module:

```bash
python3 -c "
import sys; sys.path.insert(0, '<skill-dir>/scripts')
from wwdc_catalog import get_wwdc_catalog
import json
catalog = get_wwdc_catalog()
print(json.dumps(catalog, indent=2))
" > /tmp/wwdc_catalog.json
```

Or import the individual functions for more control:

```python
import sys; sys.path.insert(0, '<skill-dir>/scripts')
from wwdc_catalog import read_wwdccore_binary, extract_contents_url, fetch_catalog, normalize_catalog

data = read_wwdccore_binary("/Applications/Developer.app")
url = extract_contents_url(data)
catalog = normalize_catalog(fetch_catalog(url))
```

Replace `<skill-dir>` with the actual path to this skill's directory (the parent of this SKILL.md).

## Catalog structure

The catalog JSON has these top-level keys:

| Key | Description |
|-----|-------------|
| `events` | List of WWDC events (WWDC14–WWDC25, Tech Talks, etc.) |
| `contents` | All content items — videos, labs, articles, etc. |
| `rooms` | Rooms where events/sessions take place |
| `topics` | Topics like "SwiftUI", "Machine Learning", etc. |
| `topicCategories` | Groupings of topics |
| `resources` | Linked resources |
| `imageTypes` | Image type definitions |
| `updated` | Last update timestamp |
| `snapshotId` | Catalog snapshot identifier |

### Content items (videos, labs, etc.)

Each item in `contents` has:

- `id`, `title`, `description`, `type` — always `"Video"` for session videos (normalized across all years)
- `eventId` — which event it belongs to (e.g. "wwdc2025")
- `webPermalink` — link to the session page on developer.apple.com
- `topicIds` — associated topic IDs
- `platforms` — e.g. ["iOS", "macOS"]
- `media.hls` — HLS video stream URL
- `media.downloadHD` / `media.downloadSD` — direct video download URLs
- `media.slides` — slide deck URL
- `media.duration` — duration in seconds
- `media.chapters` — chapter markers with timestamps
- `keywords` — search keywords
- `startTime` / `endTime` — for scheduled content like labs

### Filtering examples

To find all videos for a specific year:
```python
wwdc25_videos = [c for c in catalog["contents"]
                 if c["eventId"] == "wwdc2025" and c["type"] == "Video"]
```

To search by keyword in title/description:
```python
query = "swiftui"
matches = [c for c in catalog["contents"]
           if query in c["title"].lower() or query in c["description"].lower()]
```

To get video download URLs:
```python
for video in wwdc25_videos:
    media = video.get("media")
    if media and media.get("downloadHD"):
        print(f"{video['title']}: {media['downloadHD']}")
```

## Tips

- The catalog is large (~3000+ items). Filter by `eventId` and `type` to narrow results before presenting to the user.
- Topic names are in the `topics` list — join on `topicIds` from content items to get human-readable topic names.
- Not all content items have video — articles and labs typically don't have a `media` field.
