---
name: mac-build-notarize
description: Generate a build, sign, notarize, and package script for a macOS app with Sparkle auto-update support via GitHub Releases. Use when the user asks to create a build script, notarization script, distribution script, release pipeline, or auto-update setup for a Mac app. Also use when the user mentions Sparkle, appcast, notarization, or distributing a macOS app outside the App Store.
user-invocable: true
argument-hint: [app-name]
allowed-tools: Write, Read, Bash, Glob, Grep, Agent, AskUserQuestion
---

# macOS Build, Notarize & Sparkle Release Pipeline Generator

Generate a complete release pipeline for a macOS app distributed via GitHub Releases with Sparkle auto-updates.

## Developer Details

Discover the Team ID by running:
```bash
security find-identity -v -p codesigning | grep "Developer ID Application" | head -1
```
Extract the team ID (the 10-character alphanumeric string in parentheses at the end).

The keychain profile for notarization defaults to `notary` (stored via `xcrun notarytool store-credentials`). Ask the user if they have a different profile name.

## Task

Generate the release pipeline for the app: **$ARGUMENTS**

## Step 1: Discover the project

- Look for `.xcodeproj` or `.xcworkspace` in the current directory
- List available schemes with `xcodebuild -list`
- If `$ARGUMENTS` is provided, use it as the app name; otherwise infer from the project
- Check `project.pbxproj` for: bundle identifier, sandbox status (`ENABLE_APP_SANDBOX`), current `MARKETING_VERSION` and `CURRENT_PROJECT_VERSION`
- Identify the GitHub repo by checking `git remote get-url origin`

## Step 2: Ask the user

Before generating, ask:

1. **Version management**: Should the script check the version against the latest GitHub release and prompt for a new version if needed? (This also updates `MARKETING_VERSION` and `CURRENT_PROJECT_VERSION` in `project.pbxproj`, commits, and pushes.)
2. **Release title**: Should the script prompt for a release title/subtitle?
3. **Architecture**: arm64 only, or universal (`-arch arm64 -arch x86_64`)?

## Step 3: Create `scripts/ExportOptions.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>developer-id</string>
    <key>teamID</key>
    <string>TEAM_ID_HERE</string>
    <key>signingStyle</key>
    <string>automatic</string>
</dict>
</plist>
```

## Step 4: Create `scripts/build-and-notarize.sh`

The script should follow this flow:

### 4a. Setup and Sparkle tools download
- `set -euo pipefail`
- Define constants: `SCHEME`, `APP_NAME`, `KEYCHAIN_PROFILE="notary"`, `SPARKLE_VERSION="2.9.0"`
- Set up paths: `SCRIPT_DIR`, `PROJECT_DIR`, `BUILD_DIR`, `SPARKLE_TOOLS_DIR`, `ARCHIVE_PATH`, `EXPORT_DIR`, `EXPORT_OPTIONS`
- Clean and create `build/` directory
- Auto-download Sparkle tools if not present:
  ```bash
  if [ ! -x "$SPARKLE_TOOLS_DIR/bin/sign_update" ]; then
      curl -sL "https://github.com/sparkle-project/Sparkle/releases/download/$SPARKLE_VERSION/Sparkle-$SPARKLE_VERSION.tar.xz" -o "$BUILD_DIR/Sparkle.tar.xz"
      mkdir -p "$SPARKLE_TOOLS_DIR"
      tar -xf "$BUILD_DIR/Sparkle.tar.xz" -C "$SPARKLE_TOOLS_DIR"
      rm "$BUILD_DIR/Sparkle.tar.xz"
  fi
  ```
- Add `Sparkle-tools/` to `.gitignore`

### 4b. Version checking (if enabled)
- Read current version from project with `xcodebuild -showBuildSettings | grep MARKETING_VERSION`
- Check against latest GitHub release with `gh release view --repo <owner/repo> --json tagName -q '.tagName'`
- If not newer: prompt for new version, validate it's newer, update both `MARKETING_VERSION` and `CURRENT_PROJECT_VERSION` in `project.pbxproj` via `sed`, commit and push

Both `MARKETING_VERSION` and `CURRENT_PROJECT_VERSION` must be updated because Sparkle uses `CFBundleVersion` (from `CURRENT_PROJECT_VERSION`) for version comparison. If `CURRENT_PROJECT_VERSION` stays at a fixed value like `1`, Sparkle cannot distinguish between releases.

### 4c. Archive and export
- `xcodebuild archive` with `-arch arm64`, `ENABLE_HARDENED_RUNTIME=YES`
- `xcodebuild -exportArchive` with ExportOptions.plist
- Extract version from exported app's Info.plist

### 4d. Create DMG (not ZIP!)
Distribute as DMG, not ZIP. Finder's Archive Utility resolves symlinks when extracting zips, which breaks Sparkle's framework seal and causes Gatekeeper to reject the app with "unsealed contents present in the root directory of an embedded framework."

```bash
DMG_STAGING="$BUILD_DIR/dmg-staging"
mkdir -p "$DMG_STAGING"
cp -a "$APP_PATH" "$DMG_STAGING/"
ln -s /Applications "$DMG_STAGING/Applications"
hdiutil create -volname "$APP_NAME" -srcfolder "$DMG_STAGING" -ov -format UDZO "$DMG_PATH"
rm -rf "$DMG_STAGING"
```

### 4e. Notarize and staple
- Verify codesign: `codesign --verify --deep --strict`
- Submit DMG directly for notarization (not a zip of the app)
- Staple the DMG: `xcrun stapler staple`

### 4f. Sign for Sparkle
- `"$SPARKLE_TOOLS_DIR/bin/sign_update" "$DMG_PATH"`

### 4g. Create GitHub release
- Prompt for release title if enabled
- Tag the commit with the version number (no `v` prefix)
- Push the tag
- Create release with `gh release create` attaching the DMG
- Use `--generate-notes` for auto-generated release notes

### 4h. Generate appcast
Do NOT download all old release DMGs — older releases may share the same `CFBundleVersion`, causing `generate_appcast` to fail with "Duplicate updates" errors. Instead:

```bash
APPCAST_DIR="$BUILD_DIR/appcast-assets"
mkdir -p "$APPCAST_DIR"

# Copy existing appcast so generate_appcast can append to it
if [ -f "$PROJECT_DIR/appcast.xml" ]; then
    cp "$PROJECT_DIR/appcast.xml" "$APPCAST_DIR/"
fi

# Only include the new DMG
cp "$DMG_PATH" "$APPCAST_DIR/"

"$SPARKLE_TOOLS_DIR/bin/generate_appcast" \
    --download-url-prefix "https://github.com/<owner>/<repo>/releases/download/$TAG/" \
    -o "$APPCAST_DIR/appcast.xml" \
    "$APPCAST_DIR"

cp "$APPCAST_DIR/appcast.xml" "$PROJECT_DIR/appcast.xml"
cd "$PROJECT_DIR"
git add appcast.xml
git commit -m "Update appcast for $VERSION"
git push origin HEAD
```

## Step 5: Make the script executable

`chmod +x scripts/build-and-notarize.sh`

## Step 6: Create Sparkle integration code

### 6a. Info.plist

Create or update the app's `Info.plist` with Sparkle keys. The `SUFeedURL` should point to the raw appcast in the repo:

```xml
<key>SUFeedURL</key>
<string>https://raw.githubusercontent.com/<owner>/<repo>/main/appcast.xml</string>
<key>SUPublicEDKey</key>
<string>USER_MUST_PROVIDE_THIS</string>
<key>SUEnableInstallerLauncherService</key>
<true/>
```

Do NOT use `INFOPLIST_KEY_` build settings for Sparkle keys — Xcode only recognizes Apple's own keys with that prefix. Custom keys are silently ignored.

Do NOT use the GitHub Atom feed (`releases.atom`) as `SUFeedURL` — it lacks the `sparkle:version` and `enclosure` metadata Sparkle needs.

Set `INFOPLIST_FILE` in build settings to point to this file, keeping `GENERATE_INFOPLIST_FILE = YES` so Xcode merges both.

### 6b. Entitlements (sandboxed apps only)

If the app has `ENABLE_APP_SANDBOX = YES`, create an entitlements file with the Sparkle mach-lookup exceptions:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.app-sandbox</key>
    <true/>
    <key>com.apple.security.network.client</key>
    <true/>
    <key>com.apple.security.files.user-selected.read-write</key>
    <true/>
    <key>com.apple.security.temporary-exception.mach-lookup.global-name</key>
    <array>
        <string>$(PRODUCT_BUNDLE_IDENTIFIER)-spks</string>
        <string>$(PRODUCT_BUNDLE_IDENTIFIER)-spki</string>
    </array>
</dict>
</plist>
```

Include any other entitlements the app already uses (check existing build settings like `ENABLE_OUTGOING_NETWORK_CONNECTIONS`, `ENABLE_USER_SELECTED_FILES`, etc.).

Tell the user to set `CODE_SIGN_ENTITLEMENTS` in build settings to point to this file.

### 6c. CheckForUpdatesCommand.swift

Create a SwiftUI Commands struct:

```swift
import SwiftUI
import Sparkle

struct CheckForUpdatesCommand: Commands {
    let updater: SPUUpdater

    var body: some Commands {
        CommandGroup(after: .appInfo) {
            Button("Check for Updates…") {
                updater.checkForUpdates()
            }
            .disabled(!updater.canCheckForUpdates)
        }
    }
}
```

### 6d. Integrate into App struct

Add `SPUStandardUpdaterController` to the main App struct and wire the `CheckForUpdatesCommand` into the window's `.commands`:

```swift
import Sparkle

// In the App struct:
private let updaterController = SPUStandardUpdaterController(
    startingUpdater: true,
    updaterDelegate: nil,
    userDriverDelegate: nil
)

// Pass updater to the window/scene that has .commands:
CheckForUpdatesCommand(updater: updaterController.updater)
```

## Step 7: Tell the user what to do manually in Xcode

After generating all files, instruct the user to:

1. **Add Sparkle SPM package** in Xcode: File > Add Package Dependencies > `https://github.com/sparkle-project/Sparkle` (Up to Next Major from 2.9.0)

2. **Generate EdDSA keys** using the Sparkle tools:
   ```
   ./Sparkle-tools/bin/generate_keys
   ```
   Then paste the public key into the `Info.plist` where it says `USER_MUST_PROVIDE_THIS`.

3. **Set build settings** in Xcode:
   - `INFOPLIST_FILE` → path to the Info.plist created above
   - `CODE_SIGN_ENTITLEMENTS` → path to the entitlements file (if sandboxed)

4. **Set up notarization credentials** (if not already done):
   ```
   xcrun notarytool store-credentials notary --apple-id <APPLE_ID> --team-id TEAM_ID_HERE
   ```

5. **Add `build/` and `Sparkle-tools/` to `.gitignore`**

## Important gotchas

- **DMG not ZIP**: Always distribute as DMG. Finder resolves symlinks in ZIPs, breaking Sparkle's framework seal.
- **Both versions must match**: `MARKETING_VERSION` and `CURRENT_PROJECT_VERSION` must both be updated for each release.
- **No Run Script build phase needed**: SPM handles Sparkle framework embedding. Do not strip or copy XPC services manually.
- **Sparkle MIT license**: Remind the user to add Sparkle (MIT, 2006-2017, Andy Matuschak et al.) to their app's attributions/LICENSE file.

## Notes

- If the project uses a workspace (`.xcworkspace`), use `-workspace` instead of `-project` in xcodebuild commands.
- Pick the most appropriate release scheme from `xcodebuild -list`.
