---
name: mac-apps
description: >
  Generate a modern, searchable HTML inventory of every app installed on a Mac.
  Scans /Applications, ~/Applications, /System/Applications and the system
  Utilities folder (plus standalone apps nested in sub-folders, while skipping
  internal helper apps), extracts each app's real icon into an images/ folder,
  and produces a polished dark/light page with per-app version, size, bundle ID,
  category filter chips, and live search. Use this skill whenever the user wants
  to list, catalog, document, or inventory the apps installed on their Mac, see
  all their applications with icons and descriptions, or generate an "installed
  apps" page. Also trigger on phrases like "list my mac apps", "app inventory",
  "what apps do I have installed", or "make a page of my applications".
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, WebFetch
argument-hint: "[output-path]"
---

# Mac App Inventory Generator

Generate a self-describing HTML page listing every application installed on the
Mac, each with its icon, version, size, bundle ID, category, and a short
description.

## Step 1: Generate the page

Run the generator. `$ARGUMENTS` is an optional output path (defaults to
`Installed Mac Apps.html` in the current directory); a sibling `images/` folder
holds the extracted icons.

```bash
python3 <skill-path>/scripts/generate.py $ARGUMENTS
```

Optional flags:
- A custom title: append `--title "My Mac Apps"`.

The script scans the standard application locations, extracts each app's icon at
128px (via a small Swift/NSWorkspace helper it compiles on first run — requires
Xcode Command Line Tools; without them apps fall back to a lettered badge), and
writes a single HTML file with category filter chips and live search over names,
descriptions, and bundle IDs.

It prints how many apps were found and **how many still need a description** —
these are apps not covered by the built-in baseline and are tagged with the
`Other` category.

## Step 2: Fill in the missing descriptions

The generator covers common apps (Apple, popular third-party, and Apparata apps)
out of the box. For the remaining `Other`-category apps, add real descriptions
from your own knowledge.

1. Read the generated HTML and find every card with `data-cat="Other"`.
2. For each, pick the best category from the existing set — **Apple, AI, Browser,
   Developer, Design, Media, Productivity, 3D & Games, Utilities, Apparata** — or
   coin a new one if nothing fits.
3. Edit that card: replace the `<p class="desc">…No description available.…</p>`
   text with a concise one-sentence description, and update its `data-cat`
   attribute, the `<span class="tag cat">` label, and the `data-desc` attribute.
4. Skip anything you genuinely don't recognize rather than guessing — leave it for
   the user to fill in.

Keep descriptions short (roughly under 10 words) and focused on what the app does.

### Apparata apps

For apps with an `io.apparata.*` or `se.apparata.*` bundle ID, the authoritative
descriptions live in the Dockyard manifest. If any are missing or you want to
refresh them, fetch:

```
https://raw.githubusercontent.com/memfrag/DockyardManifest/refs/heads/main/dockyard.config.json
```

Each entry has `id` (bundle ID), `displayName`, `category`, and `summary` — use
the `summary` verbatim as the description.

## Step 3: Review with the user

Open the page (`open "Installed Mac Apps.html"`) and review it. The user may want
to adjust categories, reword descriptions, change the title, or exclude certain
locations (e.g. system apps). The HTML is self-contained apart from the `images/`
folder — the CSS is in a `<style>` tag and the JS in a `<script>` tag at the
bottom, so edits are straightforward.

## What gets scanned

| Location | Notes |
|----------|-------|
| `/Applications` | Top-level apps and standalone apps in sub-folders (e.g. Adobe, Python, emulator suites) |
| `~/Applications` | User-installed apps, including Chrome PWAs |
| `/System/Applications` | Apple's bundled stock apps |
| `/System/Applications/Utilities` | Terminal, Activity Monitor, Disk Utility, etc. |

Internal helper apps nested inside other bundles (anything under a
`.app/Contents/` path — e.g. "Claude Helper", "Figma Helper") are skipped, so the
list matches the apps a user actually launches.
