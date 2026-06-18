# Mac Apps Plugin

Generate a modern, searchable HTML inventory of every application installed on your Mac.

## Skills

### mac-apps
Scans `/Applications`, `~/Applications`, `/System/Applications`, and the system Utilities folder — including standalone apps nested in sub-folders, while skipping internal helper apps — then extracts each app's real icon and produces a polished dark/light HTML page.

Each app card shows its icon, name, version, size, bundle ID, last-updated date, category, and a one-sentence description. The page has category filter chips and live search over names, descriptions, and bundle IDs. Common apps (Apple, popular third-party, and Apparata apps) come with descriptions built in; the skill fills in the rest from the model's own knowledge.

## Output

- `Installed Mac Apps.html` — the self-contained page (CSS and JS inline)
- `images/` — extracted app icons (PNG, 128px), referenced by the page

## Prerequisites

- macOS
- Python 3.10+
- Xcode Command Line Tools (for icon extraction; without them apps fall back to lettered badges)
