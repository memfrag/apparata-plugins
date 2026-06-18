#!/usr/bin/env python3
"""Generate a modern, self-describing HTML inventory of installed Mac apps.

Scans /Applications, ~/Applications, /System/Applications and
/System/Applications/Utilities (plus standalone apps nested in sub-folders,
while skipping internal helper apps inside other bundles), extracts each app's
icon to an images/ folder, and writes a searchable, filterable HTML page.

Usage:
    python3 generate.py [output.html] [--title "Installed Mac Apps"]

Apps not covered by the built-in baseline get an empty description and the
"Other" category — the SKILL instructs Claude to fill those in afterward.
"""
import argparse
import datetime
import html
import os
import plistlib
import re
import subprocess
import sys

# (description, category) keyed by CFBundleIdentifier. A curated baseline so the
# most common apps render with sensible text immediately; everything else is
# left blank for Claude to fill in based on its own knowledge.
INFO = {
    # --- Apple iWork / creativity ---
    "com.apple.iWork.Keynote": ("Apple's presentation app for animated slide decks.", "Apple"),
    "com.apple.iWork.Numbers": ("Apple's spreadsheet app with free-form canvas layouts.", "Apple"),
    "com.apple.iWork.Pages": ("Apple's word processor and page-layout app.", "Apple"),
    "com.apple.Keynote": ("Keynote — Apple's presentation app.", "Apple"),
    "com.apple.Numbers": ("Numbers — Apple's spreadsheet app.", "Apple"),
    "com.apple.Pages": ("Pages — Apple's word processor.", "Apple"),
    "com.apple.garageband10": ("Music creation studio with instruments and recording.", "Media"),
    "com.apple.iMovieApp": ("Apple's video editor.", "Media"),

    # --- Apple developer ---
    "com.apple.dt.Xcode": ("Apple's IDE for building apps across Apple platforms.", "Developer"),
    "com.apple.TestFlight": ("Install and test beta builds of apps.", "Developer"),
    "com.apple.SFSymbols": ("Browser for Apple's SF Symbols icon library.", "Developer"),
    "developer.apple.wwdc-Release": ("Apple Developer app — WWDC videos and resources.", "Developer"),

    # --- Browsers ---
    "com.apple.Safari": ("Apple's native web browser.", "Browser"),
    "com.google.Chrome": ("Google's Chromium-based web browser.", "Browser"),

    # --- AI ---
    "com.anthropic.claudefordesktop": ("Anthropic's Claude desktop app.", "AI"),
    "com.openai.chat": ("OpenAI's ChatGPT desktop app.", "AI"),
    "com.openai.codex": ("OpenAI's Codex coding agent.", "AI"),
    "com.electron.ollama": ("Run open-source LLMs locally.", "AI"),
    "com.google.AIEdgeEloquent": ("Google AI Edge on-device generative AI playground.", "AI"),

    # --- Developer tools ---
    "com.panic.Nova": ("Panic's modern macOS code editor.", "Developer"),
    "com.torusknot.SourceTreeNotMAS": ("Atlassian's free Git GUI client (Sourcetree).", "Developer"),
    "com.panic.Transmit": ("Panic's file-transfer client (FTP/SFTP/cloud).", "Developer"),
    "com.proxyman.NSProxy": ("HTTP debugging proxy for inspecting traffic.", "Developer"),
    "com.ridiculousfish.HexFiend": ("Fast, free hex editor.", "Developer"),
    "com.cmuxterm.app": ("Terminal workspace for coding-agent sessions.", "Developer"),
    "com.brettterpstra.marked2": ("Live Markdown previewer with export.", "Developer"),
    "com.apple.Terminal": ("Command-line access to macOS via a shell.", "Developer"),
    "com.apple.ScriptEditor2": ("Write and run AppleScript/JavaScript automation.", "Developer"),
    "org.python.IDLE": ("Python's built-in IDE.", "Developer"),
    "org.python.PythonLauncher": ("Helper for launching Python scripts.", "Developer"),
    "com.apple.Automator": ("Build automation workflows without code.", "Apple"),

    # --- Design ---
    "com.figma.Desktop": ("Collaborative interface design and prototyping.", "Design"),
    "com.bohemiancoding.sketch3": ("Vector design tool for UI work.", "Design"),
    "com.nonstrict.Bezel-direct": ("Mirror and frame your iPhone/iPad for demos.", "Design"),
    "pl.maketheweb.cleanshotx": ("Screenshot and screen-recording tool with annotation.", "Design"),
    "com.flyingmeat.Retrobatch": ("Node-based batch image processor.", "Design"),
    "co.kiteapp.Kite": ("Animation and interactive UI prototyping tool.", "Design"),
    "com.adobe.Photoshop": ("Adobe's image editing and compositing app.", "Design"),

    # --- 3D & Games ---
    "org.blenderfoundation.blender": ("Free, open-source 3D creation suite.", "3D & Games"),
    "de.wengenmayer.Cheetah3D": ("Approachable 3D modeling and animation app.", "3D & Games"),
    "org.godotengine.godot": ("Free, open-source 2D/3D game engine.", "3D & Games"),
    "com.apple.Chess": ("Apple's built-in 3D chess game.", "3D & Games"),
    "org.viceteam.VICE": ("VICE — the Versatile Commodore Emulator launcher.", "3D & Games"),
    "org.viceteam.vsid": ("VICE SID player — Commodore chiptune music.", "3D & Games"),
    "org.viceteam.x128": ("Emulates the Commodore 128.", "3D & Games"),
    "org.viceteam.x64dtv": ("Emulates the Commodore 64 DTV.", "3D & Games"),
    "org.viceteam.x64sc": ("Cycle-accurate Commodore 64 emulator.", "3D & Games"),
    "org.viceteam.xcbm2": ("Emulates the Commodore CBM-II (6x0).", "3D & Games"),
    "org.viceteam.xcbm5x0": ("Emulates the Commodore CBM-II (5x0).", "3D & Games"),
    "org.viceteam.xpet": ("Emulates the Commodore PET.", "3D & Games"),
    "org.viceteam.xplus4": ("Emulates the Commodore Plus/4 and C16.", "3D & Games"),
    "org.viceteam.xscpu64": ("Emulates a C64 with a SuperCPU accelerator.", "3D & Games"),
    "org.viceteam.xvic": ("Emulates the Commodore VIC-20.", "3D & Games"),

    # --- Media ---
    "org.videolan.vlc": ("Free, open-source media player.", "Media"),
    "org.audacityteam.audacity": ("Free, open-source multi-track audio editor.", "Media"),
    "com.spotify.client": ("Music and podcast streaming.", "Media"),
    "com.charliemonroe.Downie-4": ("Download videos from thousands of sites.", "Media"),
    "com.charliemonroe.Permute-4": ("Convert video, audio, and image files.", "Media"),
    "com.apple.Music": ("Apple Music streaming and your library.", "Media"),
    "com.apple.TV": ("Apple TV app for movies and shows.", "Media"),
    "com.apple.podcasts": ("Apple Podcasts — subscribe and listen.", "Media"),
    "com.apple.QuickTimePlayerX": ("Play, record, and trim audio and video.", "Media"),
    "com.apple.PhotoBooth": ("Take photos and videos with fun effects.", "Media"),
    "com.apple.VoiceMemos": ("Record and manage voice memos.", "Media"),
    "com.apple.Photos": ("Apple's photo library, editing, and organization.", "Media"),

    # --- Productivity ---
    "com.1password.1password": ("Password manager and secure vault.", "Productivity"),
    "com.culturedcode.ThingsMac": ("Elegant personal task manager.", "Productivity"),
    "com.linear": ("Issue tracking and project management.", "Productivity"),
    "io.raindrop.macapp": ("All-in-one bookmark manager (Raindrop.io).", "Productivity"),
    "com.prof18.feedflow": ("Minimal RSS feed reader.", "Productivity"),
    "app.soulver.appstore.mac": ("Notepad calculator that does math as you type.", "Productivity"),
    "com.tinyspeck.slackmacgap": ("Team messaging and collaboration.", "Productivity"),
    "com.apple.mail": ("Apple's email client.", "Productivity"),
    "com.apple.iCal": ("Apple's calendar app.", "Productivity"),
    "com.apple.Notes": ("Apple's note-taking app.", "Productivity"),
    "com.apple.reminders": ("Apple's reminders and to-do lists.", "Productivity"),
    "com.apple.AddressBook": ("Apple's contacts manager.", "Productivity"),
    "com.apple.freeform": ("Flexible whiteboard for brainstorming.", "Productivity"),
    "com.apple.shortcuts": ("Create and run automation shortcuts.", "Productivity"),
    "com.apple.iBooksX": ("Read and organize ebooks and PDFs.", "Productivity"),
    "com.apple.journal": ("Apple's journaling app.", "Productivity"),

    # --- Apple system / misc ---
    "com.apple.AppStore": ("Browse, buy, and update apps.", "Apple"),
    "com.apple.apps.launcher": ("Apple's Apps hub for managing applications.", "Apple"),
    "com.apple.calculator": ("Apple's calculator (basic/scientific/programmer).", "Apple"),
    "com.apple.clock": ("World clock, alarms, stopwatch, timers.", "Apple"),
    "com.apple.Dictionary": ("Look up definitions and synonyms.", "Apple"),
    "com.apple.FaceTime": ("Apple's video and audio calling.", "Apple"),
    "com.apple.findmy": ("Locate your Apple devices and items.", "Apple"),
    "com.apple.FontBook": ("Install, preview, and manage fonts.", "Apple"),
    "com.apple.games": ("Apple's games and Game Center hub.", "Apple"),
    "com.apple.Home": ("Control HomeKit smart-home accessories.", "Apple"),
    "com.apple.Image_Capture": ("Transfer images from cameras and scanners.", "Apple"),
    "com.apple.GenerativePlaygroundApp": ("Image Playground — generate images with AI.", "Apple"),
    "com.apple.ScreenContinuity": ("Mirror and control your iPhone from your Mac.", "Apple"),
    "com.apple.Maps": ("Apple's maps, directions, and navigation.", "Apple"),
    "com.apple.MobileSMS": ("Apple's Messages app for iMessage and SMS.", "Apple"),
    "com.apple.exposelauncher": ("Mission Control — view all open windows.", "Apple"),
    "com.apple.news": ("Apple News — articles from many sources.", "Apple"),
    "com.apple.Passwords": ("Apple's standalone password manager.", "Apple"),
    "com.apple.mobilephone": ("Make and receive phone calls via iPhone.", "Apple"),
    "com.apple.Preview": ("View and annotate PDFs and images.", "Apple"),
    "com.apple.siri.launcher": ("Apple's Siri assistant.", "Apple"),
    "com.apple.Stickies": ("Sticky notes on your desktop.", "Apple"),
    "com.apple.stocks": ("Track stock prices and market news.", "Apple"),
    "com.apple.systempreferences": ("Configure macOS in System Settings.", "Apple"),
    "com.apple.TextEdit": ("Apple's simple text editor.", "Apple"),
    "com.apple.backup.launcher": ("Time Machine — back up and restore.", "Apple"),
    "com.apple.helpviewer": ("Apple Tips — learn features of your Mac.", "Apple"),
    "com.apple.weather": ("Apple's weather forecasts.", "Apple"),

    # --- Apple utilities ---
    "com.apple.ActivityMonitor": ("Monitor CPU, memory, energy, disk, network.", "Utilities"),
    "com.apple.airport.airportutility": ("Configure Apple AirPort base stations.", "Utilities"),
    "com.apple.audio.AudioMIDISetup": ("Configure audio devices and MIDI.", "Utilities"),
    "com.apple.BluetoothFileExchange": ("Send and receive files over Bluetooth.", "Utilities"),
    "com.apple.bootcampassistant": ("Install Windows on a partition (Intel Macs).", "Utilities"),
    "com.apple.ColorSyncUtility": ("Inspect and repair color profiles.", "Utilities"),
    "com.apple.Console": ("View system logs and diagnostics.", "Utilities"),
    "com.apple.DigitalColorMeter": ("Read the precise color of any pixel.", "Utilities"),
    "com.apple.DiskUtility": ("Manage disks, partitions, and disk images.", "Utilities"),
    "com.apple.grapher": ("Plot 2D and 3D mathematical graphs.", "Utilities"),
    "com.apple.Magnifier": ("Apple's accessibility magnifier.", "Utilities"),
    "com.apple.MigrateAssistant": ("Transfer data from another Mac or PC.", "Utilities"),
    "com.apple.printcenter": ("Manage printers and print jobs.", "Utilities"),
    "com.apple.ScreenSharing": ("Control another Mac remotely.", "Utilities"),
    "com.apple.screenshot.launcher": ("Capture screenshots and screen recordings.", "Utilities"),
    "com.apple.SystemProfiler": ("Detailed report of your Mac's hardware/software.", "Utilities"),
    "com.apple.VoiceOverUtility": ("Configure the VoiceOver screen reader.", "Utilities"),
    "me.damir.dropover-mac": ("Drag-and-drop shelf for stashing files.", "Utilities"),

    # --- Apparata (descriptions from the Dockyard manifest) ---
    "se.apparata.tools.Automata": ("Design Swift state machines.", "Apparata"),
    "se.apparata.Bootstrapp": ("Instantiate app project templates.", "Apparata"),
    "io.apparata.Dockyard": ("Apparata's app catalog — browse and install in-house apps.", "Apparata"),
    "io.apparata.Blogged": ("Static blog generator.", "Apparata"),
    "se.apparata.AppSnap": ("Add a bezel to iOS screenshots (Embezel).", "Apparata"),
    "io.apparata.RepoRanger": ("Keep track of your app projects.", "Apparata"),
    "io.apparata.Statement": ("SEB bank statement analyzer.", "Apparata"),
    "io.apparata.app.tempo": ("Client for Noko time reporting.", "Apparata"),
    "io.apparata.Tokenforge": ("Experimental design token viewer.", "Apparata"),
    "io.apparata.Unfold": ("View Markdown files.", "Apparata"),
    "io.apparata.game.overdrift": ("Early-access racing game (Överdrift).", "Apparata"),
}

HOME = os.path.expanduser("~")


def roots():
    """Scan roots, in priority order. Walking /System/Applications also covers
    its Utilities sub-folder, so it is not listed separately."""
    return [
        "/Applications",
        os.path.join(HOME, "Applications"),
        "/System/Applications",
    ]


def loc_label(path):
    if path.startswith("/System/Applications/Utilities"):
        return "/System/Applications/Utilities"
    if path.startswith("/System/Applications"):
        return "/System/Applications"
    if path.startswith(os.path.join(HOME, "Applications")):
        return "~/Applications"
    if path.startswith("/Applications"):
        return "/Applications"
    return os.path.dirname(path)


def loc_key(path):
    return {
        "/Applications": "sys",
        "~/Applications": "usr",
        "/System/Applications": "sysapp",
        "/System/Applications/Utilities": "util",
    }.get(loc_label(path), "other")


def discover():
    """Find standalone .app bundles, skipping helper apps nested inside other
    bundles (anything under a '.app/Contents' path)."""
    found = {}
    for root in roots():
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, _ in os.walk(root):
            # never descend into a .app bundle's internals
            for d in list(dirnames):
                full = os.path.join(dirpath, d)
                if d.endswith(".app"):
                    dirnames.remove(d)
                    if ".app/Contents" in full:
                        continue
                    found.setdefault(os.path.realpath(full), full)
    return sorted(found.values())


def read_plist(app):
    plist = os.path.join(app, "Contents", "Info.plist")
    try:
        with open(plist, "rb") as f:
            return plistlib.load(f)
    except Exception:
        return {}


def app_size_mb(app):
    try:
        out = subprocess.run(["du", "-sk", app], capture_output=True, text=True, timeout=60)
        kb = int(out.stdout.split("\t")[0])
        return max(1, round(kb / 1024))
    except Exception:
        return 0


def mod_date(app):
    try:
        ts = os.path.getmtime(app)
        return datetime.date.fromtimestamp(ts).isoformat()
    except Exception:
        return ""


def size_str(mb):
    if mb >= 1024:
        return f"{mb/1024:.1f} GB"
    return f"{mb} MB"


def build_extractor(images_dir):
    """Compile the Swift icon extractor once; return the binary path or None."""
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extract_icon.swift")
    if not os.path.exists(src):
        return None
    binpath = os.path.join(images_dir, ".extract_icon")
    try:
        r = subprocess.run(["swiftc", src, "-o", binpath], capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and os.path.exists(binpath):
            return binpath
    except Exception:
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output", nargs="?", default="Installed Mac Apps.html")
    ap.add_argument("--title", default="Installed Mac Apps")
    args = ap.parse_args()

    out_path = os.path.abspath(args.output)
    out_dir = os.path.dirname(out_path)
    images_dir = os.path.join(out_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    extractor = build_extractor(images_dir)
    if not extractor:
        print("WARN: could not compile Swift icon extractor (need Xcode CLT); "
              "apps will show initial badges instead of icons.", file=sys.stderr)

    apps = discover()
    print(f"Found {len(apps)} apps. Extracting icons...", file=sys.stderr)

    used = set()
    rows = []
    for app in apps:
        name = os.path.basename(app)[:-4]  # strip .app
        info = read_plist(app)
        ver = str(info.get("CFBundleShortVersionString", "") or "")
        bid = str(info.get("CFBundleIdentifier", "") or "")
        desc, cat = INFO.get(bid, ("", "Other"))
        key = loc_key(app)

        safe = re.sub(r"[^A-Za-z0-9]", "_", name)
        base = f"{key}_{safe}"
        fn = base
        i = 2
        while fn in used:
            fn = f"{base}_{i}"
            i += 1
        used.add(fn)
        icon_rel = f"images/{fn}.png"
        icon_abs = os.path.join(images_dir, f"{fn}.png")
        if extractor:
            try:
                subprocess.run([extractor, app, icon_abs, "128"],
                               capture_output=True, timeout=30)
            except Exception:
                pass
        if not os.path.exists(icon_abs):
            icon_rel = ""

        rows.append({
            "name": name, "ver": ver, "bid": bid, "desc": desc, "cat": cat,
            "loc": loc_label(app), "size": app_size_mb(app), "mod": mod_date(app),
            "icon": icon_rel,
        })

    rows.sort(key=lambda x: x["name"].lower())
    write_html(rows, out_path, args.title)
    other = sum(1 for r in rows if r["cat"] == "Other")
    print(f"Wrote {out_path} — {len(rows)} apps ({other} need descriptions).", file=sys.stderr)


def esc(s):
    return html.escape(str(s))


CSS = r"""
  :root {
    --bg: #0b0d12;
    --bg-grad: radial-gradient(1200px 800px at 15% -10%, #1a2540 0%, transparent 55%),
               radial-gradient(1000px 700px at 100% 0%, #2a1840 0%, transparent 50%);
    --surface: rgba(255,255,255,0.04);
    --surface-2: rgba(255,255,255,0.06);
    --border: rgba(255,255,255,0.09);
    --border-strong: rgba(255,255,255,0.16);
    --text: #eef1f7;
    --muted: #9aa3b2;
    --faint: #6b7382;
    --accent: #6ea8ff;
    --accent-2: #b98cff;
    --shadow: 0 10px 30px rgba(0,0,0,0.35);
  }
  @media (prefers-color-scheme: light) {
    :root {
      --bg: #f4f6fb;
      --bg-grad: radial-gradient(1200px 800px at 15% -10%, #dbe6ff 0%, transparent 55%),
                 radial-gradient(1000px 700px at 100% 0%, #ecdfff 0%, transparent 50%);
      --surface: rgba(255,255,255,0.7);
      --surface-2: #ffffff;
      --border: rgba(15,23,42,0.10);
      --border-strong: rgba(15,23,42,0.18);
      --text: #131722;
      --muted: #5a6577;
      --faint: #8a93a3;
      --accent: #2b6fff;
      --accent-2: #8b4dff;
      --shadow: 0 10px 30px rgba(20,30,60,0.12);
    }
  }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", system-ui, sans-serif;
    color: var(--text); background: var(--bg); background-image: var(--bg-grad);
    background-attachment: fixed; -webkit-font-smoothing: antialiased; line-height: 1.5;
  }
  .wrap { max-width: 1280px; margin: 0 auto; padding: 48px 28px 80px; }
  .eyebrow { font-size: 12px; letter-spacing: .14em; text-transform: uppercase; color: var(--faint); font-weight: 600; }
  h1 {
    font-size: clamp(30px, 5vw, 46px); margin: 8px 0 6px; letter-spacing: -0.02em;
    background: linear-gradient(120deg, var(--text), var(--accent) 70%, var(--accent-2));
    -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
  }
  .lede { color: var(--muted); font-size: 15px; margin: 0; }
  .controls { position: sticky; top: 0; z-index: 20; margin: 26px 0 30px; padding: 14px 0;
    backdrop-filter: blur(14px) saturate(140%); -webkit-backdrop-filter: blur(14px) saturate(140%); }
  .search {
    width: 100%; padding: 13px 16px 13px 44px; border-radius: 14px;
    background: var(--surface-2); border: 1px solid var(--border); color: var(--text);
    font-size: 15px; outline: none; box-shadow: var(--shadow);
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='%239aa3b2' stroke-width='2' stroke-linecap='round'%3E%3Ccircle cx='11' cy='11' r='7'/%3E%3Cpath d='m21 21-4.3-4.3'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: 16px center;
  }
  .search:focus { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 25%, transparent); }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
  .chip {
    border: 1px solid var(--border); background: var(--surface); color: var(--muted);
    padding: 7px 13px; border-radius: 999px; font-size: 13px; font-weight: 500;
    cursor: pointer; transition: .15s; display: inline-flex; align-items: center; gap: 6px;
  }
  .chip span { font-size: 11px; color: var(--faint); background: var(--surface-2); border-radius: 999px; padding: 1px 7px; }
  .chip:hover { border-color: var(--border-strong); color: var(--text); }
  .chip.active { background: linear-gradient(120deg, var(--accent), var(--accent-2)); border-color: transparent; color: #fff; }
  .chip.active span { background: rgba(255,255,255,0.22); color: #fff; }
  .grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); }
  .card {
    display: flex; gap: 16px; padding: 18px; background: var(--surface);
    border: 1px solid var(--border); border-radius: 18px; box-shadow: var(--shadow);
    transition: transform .18s ease, border-color .18s ease, background .18s ease;
  }
  .card:hover { transform: translateY(-3px); border-color: var(--border-strong); background: var(--surface-2); }
  .icon { flex: 0 0 64px; width: 64px; height: 64px; }
  .icon img { width: 64px; height: 64px; object-fit: contain; filter: drop-shadow(0 4px 8px rgba(0,0,0,.25)); }
  .noicon {
    width: 64px; height: 64px; border-radius: 15px; display: grid; place-items: center;
    font-size: 26px; font-weight: 700; color: #fff; background: linear-gradient(135deg, var(--accent), var(--accent-2));
  }
  .body { min-width: 0; flex: 1; }
  .title-row { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
  .body h2 { font-size: 17px; margin: 0; letter-spacing: -0.01em; }
  .ver { font-size: 12px; color: var(--faint); font-variant-numeric: tabular-nums; }
  .desc { margin: 6px 0 12px; font-size: 13.5px; color: var(--muted); }
  .nodesc { font-style: italic; color: var(--faint); }
  .meta { display: flex; flex-wrap: wrap; gap: 6px; }
  .tag { font-size: 11px; font-weight: 600; padding: 3px 9px; border-radius: 7px;
    background: var(--surface-2); border: 1px solid var(--border); color: var(--muted); }
  .tag.cat { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 35%, transparent); }
  .sub { margin-top: 10px; font-size: 11px; color: var(--faint); word-break: break-all; }
  .empty { display: none; text-align: center; color: var(--muted); padding: 60px 0; font-size: 15px; }
  footer { margin-top: 40px; text-align: center; color: var(--faint); font-size: 12px; }
  @media (max-width: 520px) { .wrap { padding: 32px 16px 60px; } .grid { grid-template-columns: 1fr; } }
"""

JS = r"""
  const search = document.getElementById('search');
  const chips = document.querySelectorAll('.chip');
  const cards = Array.from(document.querySelectorAll('.card'));
  const empty = document.getElementById('empty');
  let filter = 'all';
  function apply() {
    const q = search.value.trim().toLowerCase();
    let shown = 0;
    cards.forEach(c => {
      const matchCat = filter === 'all' || c.dataset.cat === filter;
      const matchQ = !q || c.dataset.name.includes(q) || c.dataset.desc.includes(q) || c.textContent.toLowerCase().includes(q);
      const on = matchCat && matchQ;
      c.style.display = on ? '' : 'none';
      if (on) shown++;
    });
    empty.style.display = shown ? 'none' : 'block';
  }
  chips.forEach(ch => ch.addEventListener('click', () => {
    chips.forEach(c => c.classList.remove('active'));
    ch.classList.add('active');
    filter = ch.dataset.filter;
    apply();
  }));
  search.addEventListener('input', apply);
"""


def write_html(rows, out_path, title):
    total = len(rows)
    cats = sorted(set(r["cat"] for r in rows))
    gen_date = datetime.date.today().strftime("%B %-d, %Y")

    cards = []
    for r in rows:
        icon_html = (f'<img src="{esc(r["icon"])}" alt="" loading="lazy">'
                     if r["icon"] else f'<div class="noicon">{esc(r["name"][:1])}</div>')
        ver = f'<span class="ver">v{esc(r["ver"])}</span>' if r["ver"] else ""
        desc = esc(r["desc"]) if r["desc"] else '<span class="nodesc">No description available.</span>'
        cards.append(
            f'      <article class="card" data-cat="{esc(r["cat"])}" '
            f'data-name="{esc(r["name"].lower())}" data-desc="{esc(r["desc"].lower())}">\n'
            f'        <div class="icon">{icon_html}</div>\n'
            f'        <div class="body">\n'
            f'          <div class="title-row"><h2>{esc(r["name"])}</h2>{ver}</div>\n'
            f'          <p class="desc">{desc}</p>\n'
            f'          <div class="meta">\n'
            f'            <span class="tag cat">{esc(r["cat"])}</span>\n'
            f'            <span class="tag loc">{esc(r["loc"])}</span>\n'
            f'            <span class="tag size">{esc(size_str(r["size"]))}</span>\n'
            f'          </div>\n'
            f'          <div class="sub">{esc(r["bid"])} · updated {esc(r["mod"])}</div>\n'
            f'        </div>\n'
            f'      </article>'
        )

    chips = [f'<button class="chip active" data-filter="all">All <span>{total}</span></button>']
    for c in cats:
        n = sum(1 for r in rows if r["cat"] == c)
        chips.append(f'<button class="chip" data-filter="{esc(c)}">{esc(c)} <span>{n}</span></button>')

    doc = (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{esc(title)}</title>\n<style>{CSS}</style>\n</head>\n<body>\n"
        "  <div class=\"wrap\">\n    <header class=\"page\">\n"
        "      <div class=\"eyebrow\">Application Inventory</div>\n"
        f"      <h1>{esc(title)}</h1>\n"
        f"      <p class=\"lede\">{total} applications · generated {gen_date}</p>\n"
        "    </header>\n\n    <div class=\"controls\">\n"
        "      <input id=\"search\" class=\"search\" type=\"search\" "
        "placeholder=\"Search apps, descriptions, bundle IDs…\" autocomplete=\"off\">\n"
        "      <div class=\"chips\" id=\"chips\">\n      "
        + "\n      ".join(chips)
        + "\n      </div>\n    </div>\n\n    <main class=\"grid\" id=\"grid\">\n"
        + "\n".join(cards)
        + "\n    </main>\n    <div class=\"empty\" id=\"empty\">No apps match your search.</div>\n\n"
        "    <footer>Icons stored in <code>images/</code></footer>\n  </div>\n"
        f"<script>{JS}</script>\n</body>\n</html>\n"
    )
    with open(out_path, "w") as f:
        f.write(doc)


if __name__ == "__main__":
    main()
