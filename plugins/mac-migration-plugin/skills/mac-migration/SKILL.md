---
name: mac-migration
description: >
  Generate a comprehensive Mac setup migration checklist as a self-contained interactive HTML file.
  Scans the current macOS environment — dock layout, installed apps, shell config, SSH keys,
  git config, Homebrew packages, fonts, developer tools, app-specific configs, and more — then
  produces a beautiful dark/light themed checklist page with progress tracking and localStorage
  persistence. Use this skill whenever the user wants to create a migration checklist, document
  their Mac setup, prepare for a new Mac, generate a setup guide, or capture their development
  environment configuration. Also trigger when users mention "mac migration", "new mac setup",
  "machine setup checklist", "dev environment snapshot", or similar phrases.
---

# Mac Migration Checklist Generator

Generate a comprehensive, interactive HTML checklist that documents the current Mac environment
for migration to a new machine.

## How to use

### Step 1: Generate the checklist

Run the generator script:

```bash
python3 <skill-path>/scripts/generate.py [output-path] [--name "User Name"]
```

- `output-path` defaults to `mac-migration.html` in the current directory
- `--name` sets the title; auto-detects from the system if omitted

The script scans the environment and produces a single self-contained HTML file with:
- Sidebar navigation with progress tracking
- Dark/light theme toggle
- Checklist items with localStorage persistence
- Expandable items with copyable commands
- Dock layout with embedded app icons

### Step 2: Fill in app descriptions

The generator leaves application descriptions empty. After generation, read the
Applications section of the HTML and fill in brief one-sentence descriptions for
each app based on your knowledge. For example:

- Spotify &rarr; "Streaming music player"
- Ghostty &rarr; "GPU-accelerated terminal emulator"
- Kaleidoscope &rarr; "File and image diff tool"

Keep descriptions short (under 8 words) and focused on what the app does, not who
made it. Skip apps you don't recognize — the user can fill those in later.

### Step 3: Review and customize

Review the generated HTML with the user. They may want to add, remove, or reorder
sections, add extra detail to specific items, or adjust the styling.

## What gets scanned

The generator auto-detects which sections to include based on what's installed:

| Section | Detects |
|---------|---------|
| Dock Layout | Persistent dock apps with embedded icons extracted from .icns bundles |
| Applications | Apps in /Applications and ~/Applications |
| Shell Configuration | ~/.zshrc, ~/.zprofile, ~/.bashrc — parses aliases, functions, exports, PATH entries |
| ~/bin Scripts | Custom scripts and tools in ~/bin |
| SSH Keys & Config | Keys in ~/.ssh, hosts from ~/.ssh/config |
| Git Configuration | Settings and aliases from ~/.gitconfig |
| Custom Fonts | Font families in ~/Library/Fonts |
| Blender Configuration | User preferences and input mapping from latest installed Blender version |
| Runtimes & Packages | Node/npm, Deno, Bun, Python/pip, uv — with global packages |
| Homebrew | Formulae, casks, and taps |
| Mint Packages | Swift package manager packages |
| Developer Tools | Installed dev tools, versions, signing identities |
| Claude Code | ~/.claude config, skills, plugins |

Sections are omitted if the relevant tool or config is not found on the system.

## Customizing the output

After generation, the user may want to:
- **Add sections** for tools or configs not auto-detected
- **Remove sections** that aren't relevant
- **Reorder items** within sections
- **Add descriptions** to items for additional context
- **Add expandable details** with commands to copy

Edit the generated HTML directly — it's self-contained. The CSS is in a `<style>` tag and
the JS is in a `<script>` tag at the bottom.

## HTML patterns for manual edits

**Simple checklist item:**
```html
<label class="item" data-id="unique-id">
  <input type="checkbox">
  <div class="item-content">
    <span class="item-label">Item name</span>
    <span class="item-desc">Description</span>
  </div>
</label>
```

**Expandable item with copyable command:**
```html
<div class="item-expandable" data-id="unique-id">
  <div class="item-row">
    <input type="checkbox">
    <div class="item-content">
      <span class="item-label">Item name</span>
      <span class="item-desc">Description</span>
    </div>
    <button class="item-expand-btn" onclick="toggleExpand(event, this)">
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
    </button>
  </div>
  <div class="item-detail">
    <div class="item-detail-cmd" onclick="copyCmd(this)">
      <code><span class="cmd-prefix">$ </span>your command here</code>
      <span class="cmd-copy">copy</span>
    </div>
  </div>
</div>
```

**Card with group title:**
```html
<div class="card">
  <div class="card-group-title">Group Name</div>
  <!-- items go here -->
</div>
```
