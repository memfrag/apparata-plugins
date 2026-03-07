# Mac Migration Plugin

Generate a comprehensive, interactive HTML checklist that documents your current Mac environment for migration to a new machine.

## Skills

### mac-migration
Scans the current macOS environment — dock layout, installed apps, shell config, SSH keys, git config, Homebrew packages, fonts, developer tools, runtimes, and more — then produces a beautiful dark/light themed checklist page with progress tracking and localStorage persistence.

## What gets scanned

- Dock layout with app icons
- Installed applications (with App Store detection)
- Shell configuration (aliases, functions, exports, PATH)
- ~/bin scripts and tools
- SSH keys and config
- Git configuration
- Custom fonts
- Blender configuration
- Homebrew formulae, casks, and taps
- Mint packages
- Developer tools and signing identities
- Claude Code config and skills
- Runtimes and packages (Node, Deno, Bun, Python, uv)

## Prerequisites

- macOS
- Python 3.10+
- Xcode Command Line Tools (for icon extraction)
