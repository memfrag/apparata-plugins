---
name: spotify
description: Control Spotify playback and check what's currently playing. Use when the user asks what music or song is playing, wants to play/pause/stop music, skip tracks, or interact with Spotify in any way.
allowed-tools: Bash(osascript -e *)
---

# Spotify Control Skill

Use AppleScript via `osascript` to interact with the Spotify desktop app on macOS.

## When the user asks what music is playing

Run this command to get the current track info:

```bash
osascript -e '
tell application "Spotify"
  if player state is playing then
    set trackName to name of current track
    set artistName to artist of current track
    set albumName to album of current track
    set trackDuration to duration of current track
    set trackPosition to player position
    set durationSec to trackDuration / 1000
    set mins to (durationSec div 60) as integer
    set secs to (durationSec mod 60) as integer
    set posMins to (trackPosition div 60) as integer
    set posSecs to (trackPosition mod 60 div 1) as integer
    return "Now playing: " & trackName & " by " & artistName & " from the album " & albumName & " (" & posMins & ":" & (text -2 thru -1 of ("0" & posSecs)) & " / " & mins & ":" & (text -2 thru -1 of ("0" & secs)) & ")"
  else
    return "Spotify is not currently playing anything."
  end if
end tell'
```

Present the result conversationally to the user.

## When the user asks to play music

Run: `osascript -e 'tell application "Spotify" to play'`

## When the user asks to pause or stop music

Run: `osascript -e 'tell application "Spotify" to pause'`

## When the user asks to skip or play the next track

Run: `osascript -e 'tell application "Spotify" to next track'`

## When the user asks to go back or play the previous track

Run: `osascript -e 'tell application "Spotify" to previous track'`

## Important notes

- If Spotify is not running, tell the user to open Spotify first.
- Keep responses short and conversational.
- Do not use the Skill tool recursively.
