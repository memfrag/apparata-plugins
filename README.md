
# Apparata Plugins

A Claude Code plugin marketplace for experimental plugins. Use these plugins at your own risk.

## Installation

Install all plugins from the marketplace:

```
/install-marketplace https://github.com/user/apparata-plugins
```

Or install individual plugins by adding them to your Claude Code settings.

## Plugins

| Plugin | Description |
|---|---|
| [App Design Review](#app-design-review) | Analyze and review mobile app screenshots from a UX/UI design perspective |
| [Bootstrapp](#bootstrapp) | Instantiate projects from template bundles with parameter substitution |
| [EPUB Summarizer](#epub-summarizer) | Summarize every chapter of an EPUB or iBooks book into markdown |
| [Mac Build & Notarize](#mac-build--notarize) | Generate a build, sign, notarize, and release pipeline for macOS apps |
| [Mac Migration](#mac-migration) | Generate an interactive HTML checklist for migrating to a new Mac |
| [Spotify](#spotify) | Control Spotify playback and check what's currently playing on macOS |
| [WWDC](#wwdc) | Browse, download, transcribe, and blog about Apple WWDC sessions |

---

### App Design Review

Analyze and review mobile app screenshots from a UX/UI design perspective.

**Skill:** `/app-design-review` — Expert UX/UI analysis covering visual hierarchy, navigation, mental models, and actionable design suggestions

**Prerequisites:** Screenshots in a `Screenshots/` subdirectory of the current working directory

---

### Bootstrapp

Instantiate projects from Bootstrapp template bundles with parameter substitution, conditional file inclusion, and optional Xcode project generation.

**Skill:** `/bootstrapp` — Interactively create a new project from a template bundle

**Prerequisites:** XcodeGen (for Xcode project templates)

---

### EPUB Summarizer

Summarize every chapter of an EPUB or iBooks book into a markdown file.

**Skill:** `/summarize-epub` — Generate chapter-by-chapter summaries from EPUB and iBooks files, with Apple Books library browsing

**Prerequisites:** Path to an EPUB file or access to the Apple Books library

---

### Mac Build & Notarize

Generate a complete build, sign, notarize, and release pipeline for macOS apps distributed via GitHub Releases with Sparkle auto-update support.

**Skill:** `/mac-build-notarize` — Generate a release pipeline script handling archive, DMG creation, notarization, Sparkle signing, GitHub release, and appcast generation

**Prerequisites:** macOS with Xcode, Apple Developer ID certificate, `gh` CLI installed and authenticated, notarization credentials stored via `xcrun notarytool store-credentials`

---

### Mac Migration

Generate a comprehensive, interactive HTML checklist documenting the current Mac environment for migration to a new machine.

**Skill:** `/mac-migration` — Scan Dock layout, installed apps, shell config, SSH keys, git config, Homebrew packages, fonts, dev tools, and runtimes, then generate an interactive checklist with progress tracking

**Prerequisites:** macOS, Python 3.10+, Xcode Command Line Tools

---

### Spotify

Control Spotify playback and check what's currently playing on macOS.

**Skill:** `/spotify` — Check current track, play/pause, skip, and stop via AppleScript

**Prerequisites:** macOS with Spotify desktop app installed

---

### WWDC

A collection of skills for working with Apple WWDC session content.

| Skill | Description |
|---|---|
| `/wwdc-catalog` | Fetch the full WWDC session catalog from Apple's CDN (WWDC14 through latest) |
| `/wwdc-download` | Download session videos in HD or SD by URL, session ID, or title |
| `/wwdc-transcript` | Extract timestamped transcripts from WWDC session pages |
| `/wwdc-blog` | Generate blog-post HTML interleaving transcript text with slide screenshots |

**Prerequisites:** macOS with Developer.app installed (free from Mac App Store), Python 3.10+, ffmpeg (for `/wwdc-blog`)

## License

See LICENSE for details.
