# Mac Build & Notarize Plugin

Generate a complete build, sign, notarize, and release pipeline for macOS apps distributed via GitHub Releases with Sparkle auto-update support.

## Skills

### mac-build-notarize
Generates a `build-and-notarize.sh` script and all supporting files for a macOS app release pipeline. Includes archive, DMG creation, notarization, Sparkle signing, GitHub release creation, and appcast generation.

## What gets generated

- `scripts/build-and-notarize.sh` — Full release pipeline script
- `scripts/ExportOptions.plist` — Developer ID signing configuration
- Sparkle integration code (Info.plist, entitlements, updater UI)
- Manual Xcode setup instructions for SPM and EdDSA keys

## Features

- Auto-downloads Sparkle tools if not present
- Version checking against existing GitHub releases with interactive bumping
- DMG distribution (not ZIP) to preserve framework symlinks
- Appcast generation for Sparkle auto-updates
- Sandbox detection with appropriate entitlements

## Prerequisites

- macOS with Xcode
- Apple Developer account with Developer ID certificate
- `gh` CLI (GitHub CLI) installed and authenticated
- Notarization credentials stored via `xcrun notarytool store-credentials`
