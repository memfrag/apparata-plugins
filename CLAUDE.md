# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a Claude Code plugin marketplace — a collection of skill-based plugins registered in `.claude-plugin/marketplace.json`. Each plugin provides one or more skills that Claude Code can invoke.

## Validation

```bash
bash scripts/validate-marketplace.sh
```

Run this after adding or modifying plugins. It checks that `marketplace.json` is valid, all registered source directories exist, and no plugin directories are unregistered orphans.

## Architecture

### Plugin Structure

Every plugin lives under `plugins/<name>-plugin/` (the `-plugin` suffix is a convention). Two patterns exist:

**Single-skill plugin** (e.g., `spotify-plugin`):
```
plugins/<name>-plugin/
├── README.md
└── skills/
    ├── SKILL.md
    └── scripts/
```

**Multi-skill plugin** (e.g., `wwdc-plugin`):
```
plugins/<name>-plugin/
├── README.md
└── skills/
    ├── <skill-a>/
    │   ├── SKILL.md
    │   └── scripts/
    └── <skill-b>/
        ├── SKILL.md
        └── scripts/
```

### SKILL.md

Each skill is defined by a `SKILL.md` with YAML frontmatter (`name`, `description`, `user-invocable`, `allowed-tools`, `argument-hint`) followed by step-by-step instructions for Claude to execute. The body references `<skill-dir>/scripts/` for implementation files and may use `$ARGUMENTS` for positional args.

### Marketplace Registry

`.claude-plugin/marketplace.json` is the central registry. Each plugin entry needs `name`, `source` (path to the plugin directory), and `description`. The `metadata.version` field tracks the marketplace version.

## Adding a New Plugin

1. Create `plugins/<name>-plugin/` with `skills/SKILL.md` (and `scripts/` if needed)
2. Add an entry to `.claude-plugin/marketplace.json` in the `plugins` array
3. Bump the minor version in `marketplace.json` `metadata.version` (e.g., `2.1.0` → `2.2.0`)
4. Add the plugin to `README.md` — both the summary table and a detail section, in alphabetical order
5. Run `bash scripts/validate-marketplace.sh` to verify
