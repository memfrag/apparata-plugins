
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
| [Mac Apps](#mac-apps) | Generate a searchable HTML inventory of every app installed on a Mac |
| [Mac Build & Notarize](#mac-build--notarize) | Generate a build, sign, notarize, and release pipeline for macOS apps |
| [Mac Migration](#mac-migration) | Generate an interactive HTML checklist for migrating to a new Mac |
| [Refine Specification](#refine-specification) | Refine a spec through an in-depth interview process |
| [Session Handoff](#session-handoff) | Capture session state to a HANDOFF doc so work resumes cleanly, even on another machine |
| [Skill to Plugin](#skill-to-plugin) | Package a local skill as a plugin in this marketplace and ship it via a merged PR |
| [Spotify](#spotify) | Control Spotify playback and check what's currently playing on macOS |
| [SwiftUI Review](#swiftui-review) | Review SwiftUI code against the patterns and anti-patterns in *The SwiftUI Way* |
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

### Mac Apps

Generate a modern, searchable HTML inventory of every application installed on your Mac.

**Skill:** `/mac-apps [output-path]` — Scan `/Applications`, `~/Applications`, `/System/Applications`, and the system Utilities folder; extract each app's icon; and produce a dark/light page with per-app version, size, bundle ID, category filter chips, live search, and descriptions

**Prerequisites:** macOS, Python 3.10+, Xcode Command Line Tools (for icon extraction)

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

### Refine Specification

Refine a specification markdown file through an in-depth interview process that uncovers gaps, ambiguities, and unstated assumptions.

**Skill:** `/refine-spec <path-to-spec.md>` — Read a spec, conduct a detailed interview, then write the refined spec back to the same file

**Prerequisites:** None

---

### Session Handoff

Capture the state of a work session in a `HANDOFF-<slug>.md` document so it can be resumed later — by a fresh session, possibly on a different machine with none of the original conversation's context.

**Skill:** `/session-handoff [output-path-or-slug]` — Reconstruct goal, progress, next steps, key files, decisions, open questions, and how to run; inspect git state and offer to commit/push (with confirmation); write a self-contained, machine-portable handoff doc

**Prerequisites:** None

---

### Skill to Plugin

Package an existing local skill (a `SKILL.md`, optionally with `scripts/`, `references/`, or `assets/`) as a plugin in this marketplace, following the repo's own "Adding a New Plugin" process end to end.

**Skill:** `/skill-to-plugin [path-to-skill]` — Create the plugin directory, adapt the frontmatter (add `user-invocable`, infer `allowed-tools`, `argument-hint`), register it in `marketplace.json`, bump the version, update `README.md`, run the validator, then branch, commit, push, open a PR, and merge

**Prerequisites:** `gh` CLI authenticated for push/PR/merge

---

### Spotify

Control Spotify playback and check what's currently playing on macOS.

**Skill:** `/spotify` — Check current track, play/pause, skip, and stop via AppleScript

**Prerequisites:** macOS with Spotify desktop app installed

---

### SwiftUI Review

Review SwiftUI code for adherence to the patterns and anti-patterns in *The SwiftUI Way* by Natalia Panferova.

**Agent:** `swiftui-reviewer` — Read-only review agent carrying the full rubric: view composition, dependency scoping, observation and model lifetime, structural identity, update-cycle cost, data loading and concurrency, list performance, animation scoping, and platform conventions and accessibility

**Skill:** `/swiftui-review [path]` — Resolve the review target (a path, the current git diff, or SwiftUI files under the working directory), dispatch the agent, and relay findings ordered by severity with `file:line` references and specific fixes

**Prerequisites:** None

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
