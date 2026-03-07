#!/usr/bin/env python3
"""
Mac Migration Checklist Generator

Scans the current macOS environment and generates a self-contained
interactive HTML checklist for setting up a new Mac.
"""

import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from html import escape

SCRIPT_DIR = Path(__file__).parent
ASSETS_DIR = SCRIPT_DIR.parent / "assets"

# ─── Utilities ───────────────────────────────────────────────────────────────

def run(cmd, **kwargs):
    """Run a shell command and return stdout, or empty string on failure."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, **kwargs)
        return r.stdout.strip()
    except Exception:
        return ""


SWIFT_ICON_TOOL = SCRIPT_DIR / "extract_icon"

def _compile_swift_icon_tool():
    """Compile the Swift icon extraction helper if needed."""
    swift_src = SCRIPT_DIR / "extract_icon.swift"
    if SWIFT_ICON_TOOL.exists():
        return True
    if not swift_src.exists():
        return False
    try:
        r = subprocess.run(
            ["swiftc", "-O", str(swift_src), "-o", str(SWIFT_ICON_TOOL)],
            capture_output=True, timeout=60
        )
        return r.returncode == 0
    except Exception:
        return False


def extract_app_icon(app_path, images_dir, size=64):
    """Extract an app's icon as a PNG file in images_dir. Returns filename or None."""
    app_path = str(app_path)
    if not os.path.exists(app_path):
        return None

    # Derive a safe filename from the app name
    app_name = Path(app_path).stem
    filename = re.sub(r'[^a-zA-Z0-9_-]', '_', app_name) + ".png"
    out_path = os.path.join(images_dir, filename)

    # Skip if already extracted
    if os.path.exists(out_path) and os.path.getsize(out_path) > 500:
        return filename

    # Use Swift helper (handles Asset Catalogs, system apps, etc.)
    if SWIFT_ICON_TOOL.exists():
        try:
            subprocess.run(
                [str(SWIFT_ICON_TOOL), app_path, out_path, str(size)],
                capture_output=True, timeout=10
            )
            if os.path.exists(out_path) and os.path.getsize(out_path) > 500:
                return filename
            if os.path.exists(out_path):
                os.unlink(out_path)
        except Exception:
            pass

    # Fallback: sips on .icns file
    app = Path(app_path)
    info_plist = app / "Contents" / "Info.plist"
    if not info_plist.exists():
        return None
    try:
        with open(info_plist, "rb") as f:
            info = plistlib.load(f)
    except Exception:
        return None

    icon_name = info.get("CFBundleIconFile", "AppIcon")
    if not icon_name.endswith(".icns"):
        icon_name += ".icns"

    icns = app / "Contents" / "Resources" / icon_name
    if not icns.exists():
        resources = app / "Contents" / "Resources"
        if resources.exists():
            icns_files = list(resources.glob("*.icns"))
            if icns_files:
                icns = icns_files[0]
            else:
                return None
        else:
            return None

    try:
        subprocess.run(
            ["sips", "-s", "format", "png", "-z", str(size), str(size),
             str(icns), "--out", out_path],
            capture_output=True, timeout=10
        )
        if os.path.exists(out_path) and os.path.getsize(out_path) > 500:
            return filename
        if os.path.exists(out_path):
            os.unlink(out_path)
    except Exception:
        pass

    return None


# ─── Scanners ────────────────────────────────────────────────────────────────

def scan_dock(images_dir):
    """Scan dock persistent apps with icons."""
    try:
        data = subprocess.run(
            ["defaults", "export", "com.apple.dock", "-"],
            capture_output=True, timeout=10
        ).stdout
        plist = plistlib.loads(data)
    except Exception:
        return []

    apps = []

    # Finder is always the leftmost dock item but not in persistent-apps
    finder_path = "/System/Library/CoreServices/Finder.app"
    if os.path.exists(finder_path):
        icon = extract_app_icon(finder_path, images_dir)
        apps.append({"name": "Finder", "path": finder_path, "icon": icon})

    for entry in plist.get("persistent-apps", []):
        tile = entry.get("tile-data", {})
        label = tile.get("file-label", "")
        file_data = tile.get("file-data", {})
        url = file_data.get("_CFURLString", "")

        # Resolve app path
        app_path = ""
        if url.startswith("file://"):
            app_path = url.replace("file://", "").replace("%20", " ")
            app_path = app_path.rstrip("/")

        icon = None
        if app_path and os.path.exists(app_path):
            icon = extract_app_icon(app_path, images_dir)

        if label:
            apps.append({
                "name": label,
                "path": app_path,
                "icon": icon
            })

    return apps


def _get_app_description(app_name):
    """Return empty — descriptions are filled in by Claude after generation."""
    return ""


def scan_applications(images_dir):
    """Scan installed applications."""
    apps = []
    app_dirs = [Path("/Applications"), Path.home() / "Applications"]

    for app_dir in app_dirs:
        if not app_dir.exists():
            continue
        for item in sorted(app_dir.iterdir()):
            if item.suffix == ".app":
                apps.append({
                    "name": item.stem,
                    "path": str(item),
                    "source": str(app_dir),
                    "description": _get_app_description(item.stem),
                    "app_store": (item / "Contents" / "_MASReceipt" / "receipt").exists(),
                    "icon": extract_app_icon(str(item), images_dir, size=32),
                })
            elif item.is_dir() and not item.suffix:
                # Subdirectory (e.g., /Applications/Utilities/)
                for sub in sorted(item.iterdir()):
                    if sub.suffix == ".app":
                        apps.append({
                            "name": sub.stem,
                            "path": str(sub),
                            "source": f"{app_dir}/{item.name}",
                            "description": _get_app_description(sub.stem),
                            "app_store": (sub / "Contents" / "_MASReceipt" / "receipt").exists(),
                            "icon": extract_app_icon(str(sub), images_dir, size=32),
                        })
    return apps


def scan_shell_config():
    """Parse shell configuration files."""
    home = Path.home()
    configs = {}

    # Files to check
    shell_files = [
        (".zshrc", "Main shell configuration"),
        (".zprofile", "Login shell profile"),
        (".bashrc", "Bash configuration"),
        (".bash_profile", "Bash login profile"),
    ]

    for filename, desc in shell_files:
        path = home / filename
        if path.exists():
            content = path.read_text(errors="replace")
            configs[filename] = {
                "description": desc,
                "content": content,
                "aliases": _parse_aliases(content),
                "functions": _parse_functions(content),
                "exports": _parse_exports(content),
                "path_entries": _parse_path_entries(content),
                "sources": _parse_sources(content),
            }

    # Check for additional shell dirs
    zsh_dir = home / ".zsh"
    if zsh_dir.exists():
        configs[".zsh/"] = {
            "description": "Zsh directory (completions, etc.)",
            "items": [str(p.relative_to(home)) for p in zsh_dir.rglob("*") if p.is_file()]
        }

    # Deno env
    deno_env = home / ".deno" / "env"
    if deno_env.exists():
        configs[".deno/env"] = {"description": "Deno environment setup"}

    # Bun
    bun_dir = home / ".bun"
    if bun_dir.exists():
        configs[".bun/"] = {"description": "Bun runtime & completions"}

    return configs


def _parse_aliases(content):
    """Extract aliases from shell config."""
    aliases = []
    for m in re.finditer(r'^alias\s+(\S+?)=["\'](.+?)["\']', content, re.MULTILINE):
        aliases.append({"name": m.group(1), "value": m.group(2)})
    return aliases


def _parse_functions(content):
    """Extract function names from shell config."""
    functions = []
    for m in re.finditer(r'^(?:function\s+)?(\w[\w-]*)\s*\(\)\s*\{', content, re.MULTILINE):
        name = m.group(1)
        # Try to get a brief description from a comment above
        lines = content[:m.start()].rstrip().split("\n")
        desc = ""
        if lines and lines[-1].strip().startswith("#"):
            desc = lines[-1].strip().lstrip("# ")
        functions.append({"name": name, "description": desc})
    return functions


def _parse_exports(content):
    """Extract export statements."""
    exports = []
    for m in re.finditer(r'^export\s+(\w+)=(.+)$', content, re.MULTILINE):
        exports.append({"name": m.group(1), "value": m.group(2).strip('"\'')})
    return exports


def _parse_path_entries(content):
    """Extract PATH modifications."""
    entries = []
    for m in re.finditer(r'(?:export\s+)?PATH=[""]?([^""\n]+)', content, re.MULTILINE):
        for part in m.group(1).split(":"):
            part = part.strip()
            if part and part != "$PATH" and part not in entries:
                entries.append(part)
    return entries


def _parse_sources(content):
    """Extract source/. commands."""
    sources = []
    for m in re.finditer(r'^(?:source|\.)\s+(.+)$', content, re.MULTILINE):
        sources.append(m.group(1).strip('"\''))
    return sources


def _summarize_script(path):
    """Try to produce a short description of what a script does."""
    try:
        with open(path, "r", errors="replace") as fh:
            first_bytes = fh.read(4096)
    except Exception:
        return ""

    # Detect binary files (compiled executables)
    if "\x00" in first_bytes[:512]:
        name = path.name.lower()
        # Well-known binaries
        known = {
            "ffmpeg": "Video/audio converter and processor",
            "ffplay": "FFmpeg media player",
            "ffprobe": "FFmpeg media file analyzer",
            "gh": "GitHub CLI",
            "glow": "Terminal Markdown renderer",
            "ngrok": "Expose local servers to the internet",
        }
        if name in known:
            return known[name]
        # Check for framework references to guess purpose
        lower = first_bytes.lower()
        if "webkit" in lower:
            return "Compiled app (WebKit-based)"
        if "swiftui" in lower:
            return "Compiled Swift app"
        return "Compiled binary"

    lines = first_bytes.splitlines()
    if not lines:
        return ""

    # 1. Look for a descriptive comment near the top (skip shebang)
    for line in lines[1:15]:
        stripped = line.strip()
        # Handle // comments (Swift, JS) and # comments (shell, Python, Ruby)
        comment = ""
        if stripped.startswith("#") and not stripped.startswith("#!"):
            comment = stripped.lstrip("# ").strip()
        elif stripped.startswith("//"):
            comment = stripped.lstrip("/ ").strip()
        if comment:
            cl = comment.lower()
            # Skip boilerplate and inline code comments
            if (len(comment) > 5
                and not cl.startswith(("!/", "-*-", "encoding", "vim:", "copyright", "mark:", "mark -"))
                and not cl.startswith(("check ", "set ", "get ", "parse ", "define ", "if ", "loop "))):
                return comment
        elif stripped and not stripped.startswith(("#", "//", "/*", "*", "import", "use", "require")):
            break  # hit actual code, stop looking for header comments

    # 2. Infer from content patterns
    shebang = lines[0].strip() if lines else ""
    content = first_bytes
    lower = content.lower()

    # Detect the script running a specific tool via mint
    mint_match = re.search(r'mint run [\w/]+[/ ](\w+)', content)
    if mint_match:
        return f"Runs {mint_match.group(1)} via Mint"

    # iOS Simulator utilities
    if "simctl" in lower:
        return "iOS Simulator utility"

    # Directory tree printer
    if "tree" in path.name.lower() and ("hierarchy" in lower or "indent" in lower or "├" in content or "└" in content):
        return "Print directory tree"

    # IP / network utilities
    if "ipconfig" in lower or "ifconfig" in lower:
        if "dhcp" in lower:
            return "Renew network IP address"
        return "Show local IP address"

    # Usage messages
    if "usage()" in lower or "usage:" in lower or "getopts" in lower:
        for line in lines:
            if "usage" in line.lower() and ("echo" in line.lower() or "print" in line.lower()):
                msg = re.search(r'["\'](.+?)["\']', line)
                if msg:
                    text = msg.group(1).strip()
                    if len(text) > 5:
                        return text

    # Linear API / branch creation
    if "linear" in lower and ("branch" in lower or "api" in lower):
        return "Create git branch from Linear issue"

    # SPM / Swift Package repos
    if "swift package" in lower or "package.swift" in lower or "spm" in path.name.lower():
        if "resolve" in lower or "repo" in lower or "clone" in lower:
            return "List or manage Swift package repos"
        return "Swift package utility"

    if "curl " in lower or "wget " in lower:
        if "api" in lower or "json" in lower:
            return "API request script"
        return "Download/fetch script"
    if "ffmpeg" in lower:
        return "Media conversion script"
    if "rsync" in lower or "scp " in lower:
        return "File sync/copy script"
    if "git " in lower and ("clone" in lower or "push" in lower or "pull" in lower):
        return "Git automation script"
    if "docker" in lower:
        return "Docker automation script"
    if "ssh " in lower:
        return "Remote SSH script"
    if "xcrun" in lower or "xcodebuild" in lower:
        return "Xcode build script"
    if "swift " in lower and ("build" in lower or "package" in lower):
        return "Swift build script"

    # Language-based fallbacks from shebang
    if "swift" in shebang:
        return "Swift script"
    if "python" in shebang:
        return "Python script"
    if "node" in shebang or "deno" in shebang or "bun" in shebang:
        return "JavaScript/TypeScript script"
    if "ruby" in shebang:
        return "Ruby script"

    return ""


def _is_binary_file(path):
    """Check if a file is a compiled binary (not a text script)."""
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(512)
        return b"\x00" in chunk
    except Exception:
        return False


def scan_bin():
    """Scan ~/bin directory."""
    bin_dir = Path.home() / "bin"
    if not bin_dir.exists():
        return None

    items = []
    for f in sorted(bin_dir.iterdir()):
        if f.name.startswith("."):
            continue
        desc = ""
        is_binary = False
        if f.is_file():
            is_binary = _is_binary_file(f)
            desc = _summarize_script(f)
        items.append({
            "name": f.name,
            "is_dir": f.is_dir(),
            "is_symlink": f.is_symlink(),
            "is_binary": is_binary,
            "description": desc,
            "executable": os.access(f, os.X_OK),
        })
    return items


def scan_ssh():
    """Scan SSH configuration and keys."""
    ssh_dir = Path.home() / ".ssh"
    if not ssh_dir.exists():
        return None

    result = {"keys": [], "hosts": [], "config_exists": False}

    # Keys
    for f in sorted(ssh_dir.iterdir()):
        if f.suffix == ".pub":
            key_name = f.stem
            result["keys"].append({
                "name": key_name,
                "public": f.name,
                "private_exists": (ssh_dir / key_name).exists(),
            })

    # Config
    config = ssh_dir / "config"
    if config.exists():
        result["config_exists"] = True
        content = config.read_text(errors="replace")
        current_host = None
        for line in content.split("\n"):
            line = line.strip()
            if line.lower().startswith("host ") and "*" not in line:
                current_host = {"name": line.split(None, 1)[1], "hostname": ""}
                result["hosts"].append(current_host)
            elif current_host and line.lower().startswith("hostname "):
                current_host["hostname"] = line.split(None, 1)[1]

    return result


def scan_git():
    """Scan git configuration."""
    gitconfig = Path.home() / ".gitconfig"
    if not gitconfig.exists():
        return None

    result = {"settings": {}, "aliases": []}
    content = gitconfig.read_text(errors="replace")

    current_section = ""
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("["):
            current_section = line.strip("[]").split('"')[0].strip()
        elif "=" in line and current_section:
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if current_section == "alias":
                result["aliases"].append({"name": key, "command": val})
            else:
                result["settings"][f"{current_section}.{key}"] = val

    return result


def scan_fonts():
    """Scan custom user fonts."""
    font_dir = Path.home() / "Library" / "Fonts"
    if not font_dir.exists():
        return None

    fonts = {}
    for f in sorted(font_dir.iterdir()):
        if f.name.startswith("."):
            continue
        # Group by family (strip weight/style suffixes)
        family = re.sub(r'[-_ ]?(Regular|Bold|Italic|Light|Medium|Thin|Semi|Mono|Book|Heavy|Black|ExtraLight|Variable|Nerd.*|Complete).*$', '', f.stem, flags=re.IGNORECASE)
        family = family.rstrip("-_ ")
        if family not in fonts:
            fonts[family] = []
        fonts[family].append(f.name)

    return fonts



def scan_homebrew():
    """Scan Homebrew packages."""
    if not shutil.which("brew"):
        return None

    result = {"formulae": [], "casks": [], "taps": []}

    formulae = run(["brew", "list", "--formula", "-1"])
    if formulae:
        result["formulae"] = formulae.split("\n")

    casks = run(["brew", "list", "--cask", "-1"])
    if casks:
        result["casks"] = casks.split("\n")

    taps = run(["brew", "tap"])
    if taps:
        result["taps"] = taps.split("\n")

    return result


def scan_mint():
    """Scan Mint packages."""
    if not shutil.which("mint"):
        return None

    result = run(["mint", "list"])
    if not result:
        return None

    packages = []
    for line in result.split("\n"):
        line = line.strip()
        if line and not line.startswith("🌱"):
            packages.append(line)

    return packages if packages else None


def scan_dev_tools():
    """Scan developer tools and signing identities."""
    result = {"tools": [], "signing_identities": []}

    # Check common dev tools
    tools = [
        ("xcode-select", "Xcode Command Line Tools"),
        ("xcrun", "Xcode toolchain runner"),
        ("swift", "Swift compiler"),
        ("python3", "Python 3"),
        ("node", "Node.js"),
        ("deno", "Deno"),
        ("bun", "Bun"),
        ("go", "Go"),
        ("rustc", "Rust compiler"),
        ("ruby", "Ruby"),
    ]

    for cmd, desc in tools:
        path = shutil.which(cmd)
        if path:
            version = run([cmd, "--version"])
            if version:
                version = version.split("\n")[0][:80]
            result["tools"].append({"name": cmd, "description": desc, "version": version, "path": path})

    # Signing identities
    identities = run(["security", "find-identity", "-v", "-p", "codesigning"])
    if identities:
        for m in re.finditer(r'\d+\)\s+\S+\s+"(.+?)"', identities):
            result["signing_identities"].append(m.group(1))

    return result


def scan_claude_code():
    """Scan Claude Code configuration."""
    claude_dir = Path.home() / ".claude"
    if not claude_dir.exists():
        return None

    result = {"files": [], "skills": [], "plugins": []}

    # Global config
    claude_md = claude_dir / "CLAUDE.md"
    if claude_md.exists():
        result["files"].append("~/.claude/CLAUDE.md")

    # Settings
    settings = claude_dir / "settings.json"
    if settings.exists():
        result["files"].append("~/.claude/settings.json")

    # Keybindings
    keybindings = claude_dir / "keybindings.json"
    if keybindings.exists():
        result["files"].append("~/.claude/keybindings.json")

    # Skills directory
    skills_dir = claude_dir / "skills"
    if skills_dir.exists():
        for skill in sorted(skills_dir.iterdir()):
            if skill.is_dir():
                result["skills"].append(skill.name)

    return result


def scan_runtimes():
    """Scan language runtimes and their global packages."""
    runtimes = []

    # Node.js / npm
    node_path = shutil.which("node")
    if node_path:
        version = run(["node", "--version"])
        npm_globals = run(["npm", "list", "-g", "--depth=0", "--parseable"])
        global_pkgs = []
        if npm_globals:
            for line in npm_globals.split("\n"):
                pkg = Path(line).name
                if pkg and pkg != "lib":
                    global_pkgs.append(pkg)
        runtimes.append({
            "name": "Node.js",
            "version": version,
            "manager": "npm",
            "globals": global_pkgs,
        })

    # Deno
    deno_path = shutil.which("deno")
    if deno_path:
        version = run(["deno", "--version"])
        if version:
            version = version.split("\n")[0]
        runtimes.append({
            "name": "Deno",
            "version": version,
            "manager": None,
            "globals": [],
        })

    # Bun
    bun_path = shutil.which("bun")
    if bun_path:
        version = run(["bun", "--version"])
        runtimes.append({
            "name": "Bun",
            "version": version,
            "manager": None,
            "globals": [],
        })

    # Python / pip
    python_path = shutil.which("python3")
    if python_path:
        version = run(["python3", "--version"])
        pip_pkgs = []
        pip_output = run(["python3", "-m", "pip", "list", "--user", "--format=columns"])
        if pip_output:
            for line in pip_output.split("\n")[2:]:  # skip header
                parts = line.split()
                if parts:
                    pip_pkgs.append(f"{parts[0]} {parts[1]}" if len(parts) > 1 else parts[0])
        runtimes.append({
            "name": "Python",
            "version": version,
            "manager": "pip (user)",
            "globals": pip_pkgs,
        })

    # uv
    uv_path = shutil.which("uv")
    if uv_path:
        version = run(["uv", "--version"])
        # List uv-managed tools
        uv_tools = []
        uv_tool_output = run(["uv", "tool", "list"])
        if uv_tool_output:
            for line in uv_tool_output.split("\n"):
                line = line.strip()
                if line and not line.startswith("-"):
                    uv_tools.append(line.split()[0] if line.split() else line)
        runtimes.append({
            "name": "uv",
            "version": version,
            "manager": "uv tool",
            "globals": uv_tools,
        })

    return runtimes if runtimes else None


def scan_app_configs():
    """Scan for Blender user preferences (latest installed version)."""
    home = Path.home()
    blender_dir = home / "Library" / "Application Support" / "Blender"
    if not blender_dir.exists():
        return []

    # Find the latest version directory with a userpref.blend
    candidates = []
    for ver_dir in blender_dir.iterdir():
        if not ver_dir.is_dir():
            continue
        pref = ver_dir / "config" / "userpref.blend"
        if pref.exists():
            candidates.append((ver_dir.name, str(pref.relative_to(home))))

    if not candidates:
        return []

    # Sort by version string descending, take the latest
    candidates.sort(key=lambda x: x[0], reverse=True)
    latest_ver, latest_path = candidates[0]
    return [{"app": f"Blender {latest_ver}", "files": [latest_path]}]


# ─── HTML Generation ─────────────────────────────────────────────────────────

def make_id(text):
    """Create a safe HTML id from text."""
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def item_html(data_id, label, desc="", badge="", icon=""):
    """Generate a checklist item."""
    desc_html = f'<span class="item-desc">{escape(desc)}</span>' if desc else ""
    badge_html = f'<span class="app-store-badge">{escape(badge)}</span>' if badge else ""
    if icon:
        content_cls = "item-content-with-icon"
        icon_html = f'<img class="app-icon" src="images/{escape(icon)}" alt="">'
    else:
        content_cls = "item-content"
        icon_html = ""
    return (
        f'<label class="item" data-id="{escape(data_id)}">'
        f'<input type="checkbox"><div class="{content_cls}">'
        f'{icon_html}<div class="item-text">'
        f'<span class="item-label">{escape(label)}</span>{desc_html}'
        f'</div></div>{badge_html}</label>'
    )


def expandable_item_html(data_id, label, desc, detail_html):
    """Generate an expandable checklist item."""
    return (
        f'<div class="item-expandable" data-id="{escape(data_id)}">'
        f'<div class="item-row">'
        f'<input type="checkbox">'
        f'<div class="item-content"><span class="item-label">{escape(label)}</span>'
        f'<span class="item-desc">{escape(desc)}</span></div>'
        f'<button class="item-expand-btn" onclick="toggleExpand(event, this)">'
        f'<svg width="12" height="12" viewBox="0 0 12 12" fill="none">'
        f'<path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'
        f'</svg></button>'
        f'</div>'
        f'<div class="item-detail">{detail_html}</div>'
        f'</div>'
    )


def cmd_detail_html(command):
    """Generate a copyable command detail."""
    return (
        f'<div class="item-detail-cmd" onclick="copyCmd(this)">'
        f'<code><span class="cmd-prefix">$ </span>{escape(command)}</code>'
        f'<span class="cmd-copy">copy</span></div>'
    )


def card_html(content, title=None):
    """Wrap content in a card."""
    title_html = f'<div class="card-group-title">{escape(title)}</div>' if title else ""
    return f'<div class="card">{title_html}{content}</div>'


def section_html(num, section_id, title, content, note=""):
    """Generate a full section."""
    note_html = f'<p class="section-note">{escape(note)}</p>' if note else ""
    return (
        f'<!-- ═══ {num}. {title} ═══ -->\n'
        f'<div class="section" id="{section_id}">\n'
        f'  <div class="section-header">\n'
        f'    <span class="section-num">{num:02d}</span>\n'
        f'    <span class="section-title">{escape(title)}</span>\n'
        f'    <span class="section-count" data-section="{section_id}"></span>\n'
        f'  </div>\n'
        f'  {note_html}\n'
        f'  {content}\n'
        f'</div>\n'
    )


# ─── Section Builders ────────────────────────────────────────────────────────

def build_dock_section(dock_apps, section_num):
    """Build the dock layout section."""
    icons = []
    for app in dock_apps:
        if app["icon"]:
            src = f'images/{app["icon"]}'
        else:
            src = ""
        icons.append(
            f'<div class="dock-icon-wrap">'
            f'<img src="{src}" alt="">'
            f'<span class="dock-tooltip">{escape(app["name"])}</span>'
            f'</div>'
        )

    icons_html = "\n          ".join(icons)
    content = (
        f'<div class="card" style="padding: 0.7rem 0.9rem; overflow: visible;">\n'
        f'  <div class="dock-icons">\n'
        f'    {icons_html}\n'
        f'  </div>\n'
        f'</div>'
    )
    return section_html(section_num, "s1", "Dock Layout", content,
                        "Your current Dock app arrangement for reference when setting up the new Mac.")


def build_apps_section(apps, section_num):
    """Build the applications section."""
    # Group by source directory
    groups = {}
    for app in apps:
        source = app["source"]
        if source not in groups:
            groups[source] = []
        groups[source].append(app)

    cards = []
    for source, group_apps in groups.items():
        items = []
        for app in group_apps:
            aid = f'app-{make_id(app["name"])}'
            desc = app.get("description", "")
            badge = "App Store" if app.get("app_store") else ""
            icon = app.get("icon", "")
            items.append(item_html(aid, app["name"], desc, badge, icon))
        cards.append(card_html("\n".join(items), source))

    return section_html(section_num, f"s{section_num}", "Applications",
                        "\n".join(cards),
                        "Applications to install on the new Mac.")


def build_shell_section(shell_config, section_num):
    """Build the shell configuration section."""
    cards = []

    # Config files card
    file_items = []
    for filename, cfg in shell_config.items():
        if isinstance(cfg, dict) and "content" in cfg:
            aid = f'shell-{make_id(filename)}'
            file_items.append(item_html(aid, f"~/{filename}", cfg["description"]))
        elif isinstance(cfg, dict) and "description" in cfg:
            aid = f'shell-{make_id(filename)}'
            file_items.append(item_html(aid, f"~/{filename}", cfg["description"]))

    if file_items:
        cards.append(card_html("\n".join(file_items)))

    # Detailed breakdown for .zshrc
    zshrc = shell_config.get(".zshrc")
    if zshrc and isinstance(zshrc, dict) and "content" in zshrc:
        # Aliases
        if zshrc["aliases"]:
            alias_items = []
            for a in zshrc["aliases"]:
                aid = f'zsh-alias-{make_id(a["name"])}'
                alias_items.append(item_html(aid, a["name"], a["value"]))
            cards.append(card_html("\n".join(alias_items), "Aliases"))

        # Functions
        if zshrc["functions"]:
            func_items = []
            for fn in zshrc["functions"]:
                aid = f'zsh-func-{make_id(fn["name"])}'
                func_items.append(item_html(aid, f'{fn["name"]}()', fn["description"]))
            cards.append(card_html("\n".join(func_items), "Functions"))

        # Exports
        if zshrc["exports"]:
            export_items = []
            for ex in zshrc["exports"]:
                aid = f'zsh-export-{make_id(ex["name"])}'
                export_items.append(item_html(aid, ex["name"], ex["value"]))
            cards.append(card_html("\n".join(export_items), "Environment Variables"))

        # PATH entries
        if zshrc["path_entries"]:
            path_items = []
            for p in zshrc["path_entries"]:
                aid = f'zsh-path-{make_id(p)}'
                path_items.append(item_html(aid, p, "PATH entry"))
            cards.append(card_html("\n".join(path_items), "PATH Entries"))

        # Sources
        if zshrc["sources"]:
            src_items = []
            for s in zshrc["sources"]:
                aid = f'zsh-source-{make_id(s)}'
                src_items.append(item_html(aid, s, "Sourced file"))
            cards.append(card_html("\n".join(src_items), "Sourced Files"))

    return section_html(section_num, f"s{section_num}", "Shell Configuration",
                        "\n".join(cards),
                        "Shell configuration files and their contents.")


def build_bin_section(bin_items, section_num):
    """Build the ~/bin section."""
    scripts = []
    binaries = []
    for b in bin_items:
        aid = f'bin-{make_id(b["name"])}'
        desc = b["description"] or ("directory" if b["is_dir"] else "")
        item = item_html(aid, b["name"], desc)
        if b.get("is_binary"):
            binaries.append(item)
        else:
            scripts.append(item)

    cards = []
    if scripts:
        cards.append(card_html("\n".join(scripts), f"Scripts ({len(scripts)})"))
    if binaries:
        cards.append(card_html("\n".join(binaries), f"Binaries ({len(binaries)})"))

    return section_html(section_num, f"s{section_num}", "~/bin Scripts & Tools",
                        "\n".join(cards), "Custom scripts and tools in ~/bin.")


def build_ssh_section(ssh_data, section_num):
    """Build the SSH section."""
    cards = []

    # Keys
    if ssh_data["keys"]:
        key_items = []
        for k in ssh_data["keys"]:
            aid = f'ssh-key-{make_id(k["name"])}'
            key_items.append(item_html(aid, k["name"], f'{k["public"]}'))
        cards.append(card_html("\n".join(key_items), "SSH Keys"))

    # Config
    if ssh_data["config_exists"]:
        cards.append(card_html(item_html("ssh-config", "~/.ssh/config", "SSH client configuration")))

    # Hosts
    if ssh_data["hosts"]:
        host_items = []
        for h in ssh_data["hosts"]:
            aid = f'ssh-host-{make_id(h["name"])}'
            detail = cmd_detail_html(f'ssh {h["name"]}')
            host_items.append(expandable_item_html(aid, h["name"], h.get("hostname", ""), detail))
        cards.append(card_html("\n".join(host_items), "SSH Hosts"))

    return section_html(section_num, f"s{section_num}", "SSH Keys & Config",
                        "\n".join(cards))


def build_git_section(git_data, section_num):
    """Build the git configuration section."""
    cards = []

    # Settings
    if git_data["settings"]:
        setting_items = []
        for key, val in git_data["settings"].items():
            aid = f'git-{make_id(key)}'
            setting_items.append(item_html(aid, key, val))
        cards.append(card_html("\n".join(setting_items), "Settings"))

    # Aliases
    if git_data["aliases"]:
        alias_items = []
        for a in git_data["aliases"]:
            aid = f'git-alias-{make_id(a["name"])}'
            alias_items.append(item_html(aid, a["name"], a["command"]))
        cards.append(card_html("\n".join(alias_items), "Aliases"))

    return section_html(section_num, f"s{section_num}", "Git Configuration",
                        "\n".join(cards))


def build_fonts_section(fonts, section_num):
    """Build the fonts section."""
    items = []
    for family, files in sorted(fonts.items()):
        aid = f'font-{make_id(family)}'
        count = len(files)
        desc = f'{count} file{"s" if count > 1 else ""}'
        items.append(item_html(aid, family, desc))

    content = card_html("\n".join(items))
    return section_html(section_num, f"s{section_num}", "Custom Fonts",
                        content, "Fonts installed in ~/Library/Fonts.")



def build_homebrew_section(brew_data, section_num):
    """Build the Homebrew section."""
    cards = []

    if brew_data["formulae"]:
        items = [item_html(f'brew-{make_id(f)}', f) for f in brew_data["formulae"]]
        cards.append(card_html("\n".join(items), f'Formulae ({len(brew_data["formulae"])})'))

    if brew_data["casks"]:
        items = [item_html(f'cask-{make_id(c)}', c) for c in brew_data["casks"]]
        cards.append(card_html("\n".join(items), f'Casks ({len(brew_data["casks"])})'))

    if brew_data["taps"]:
        items = [item_html(f'tap-{make_id(t)}', t) for t in brew_data["taps"]]
        cards.append(card_html("\n".join(items), "Taps"))

    return section_html(section_num, f"s{section_num}", "Homebrew",
                        "\n".join(cards),
                        "Homebrew packages to install.")


def build_mint_section(packages, section_num):
    """Build the Mint packages section."""
    items = [item_html(f'mint-{make_id(p)}', p) for p in packages]
    content = card_html("\n".join(items))
    return section_html(section_num, f"s{section_num}", "Mint Packages", content)


def build_dev_tools_section(dev_data, section_num):
    """Build the developer tools section."""
    cards = []

    if dev_data["tools"]:
        items = []
        for t in dev_data["tools"]:
            aid = f'dev-{make_id(t["name"])}'
            desc = t["version"] or t["description"]
            items.append(item_html(aid, t["name"], desc))
        cards.append(card_html("\n".join(items), "Installed Tools"))

    if dev_data["signing_identities"]:
        items = []
        for ident in dev_data["signing_identities"]:
            aid = f'sign-{make_id(ident[:30])}'
            items.append(item_html(aid, ident))
        cards.append(card_html("\n".join(items), "Signing Identities"))

    return section_html(section_num, f"s{section_num}", "Developer Tools",
                        "\n".join(cards))


def build_claude_code_section(claude_data, section_num):
    """Build the Claude Code section."""
    cards = []

    if claude_data["files"]:
        items = [item_html(f'claude-{make_id(f)}', f) for f in claude_data["files"]]
        cards.append(card_html("\n".join(items), "Configuration Files"))

    if claude_data["skills"]:
        items = [item_html(f'claude-skill-{make_id(s)}', s) for s in claude_data["skills"]]
        cards.append(card_html("\n".join(items), "Custom Skills"))

    return section_html(section_num, f"s{section_num}", "Claude Code",
                        "\n".join(cards),
                        "Claude Code configuration and skills.")


def build_runtimes_section(runtimes, section_num):
    """Build the runtimes & package managers section."""
    cards = []
    for rt in runtimes:
        items = []
        aid = f'rt-{make_id(rt["name"])}'
        items.append(item_html(aid, rt["name"], rt["version"]))

        if rt["globals"]:
            for pkg in rt["globals"]:
                pid = f'rt-{make_id(rt["name"])}-{make_id(pkg[:30])}'
                manager_label = rt["manager"] or rt["name"]
                items.append(item_html(pid, pkg, f"via {manager_label}"))

        title = rt["name"]
        if rt["manager"]:
            title += f" / {rt['manager']}"
        cards.append(card_html("\n".join(items), title))

    return section_html(section_num, f"s{section_num}",
                        "Runtimes & Packages",
                        "\n".join(cards),
                        "Language runtimes and their globally installed packages.")


def build_app_configs_section(app_configs, section_num):
    """Build the app configurations section."""
    cards = []
    for cfg in app_configs:
        items = []
        for f in cfg["files"]:
            aid = f'cfg-{make_id(cfg["app"])}-{make_id(f[:30])}'
            items.append(item_html(aid, f"~/{f}"))
        cards.append(card_html("\n".join(items), cfg["app"]))

    return section_html(section_num, f"s{section_num}", "Blender Configuration",
                        "\n".join(cards),
                        "Custom input mapping and user preferences.")


# ─── Main Generator ──────────────────────────────────────────────────────────

def generate(output_path, user_name=None):
    """Scan the environment and generate the HTML checklist."""
    print("Compiling icon extractor...", file=sys.stderr)
    _compile_swift_icon_tool()

    # Create images directory next to the output HTML
    output = Path(output_path)
    images_dir = output.parent / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    print("Scanning environment...", file=sys.stderr)

    # Run all scans
    print("  Scanning dock...", file=sys.stderr)
    dock_apps = scan_dock(str(images_dir))
    print(f"    Found {len(dock_apps)} dock apps", file=sys.stderr)

    print("  Scanning applications...", file=sys.stderr)
    applications = scan_applications(str(images_dir))
    print(f"    Found {len(applications)} apps", file=sys.stderr)

    print("  Scanning shell config...", file=sys.stderr)
    shell_config = scan_shell_config()

    print("  Scanning ~/bin...", file=sys.stderr)
    bin_items = scan_bin()

    print("  Scanning SSH...", file=sys.stderr)
    ssh_data = scan_ssh()

    print("  Scanning git config...", file=sys.stderr)
    git_data = scan_git()

    print("  Scanning fonts...", file=sys.stderr)
    fonts = scan_fonts()

    print("  Scanning Homebrew...", file=sys.stderr)
    brew_data = scan_homebrew()

    print("  Scanning Mint...", file=sys.stderr)
    mint_data = scan_mint()

    print("  Scanning developer tools...", file=sys.stderr)
    dev_tools = scan_dev_tools()

    print("  Scanning Claude Code...", file=sys.stderr)
    claude_data = scan_claude_code()

    print("  Scanning runtimes...", file=sys.stderr)
    runtimes = scan_runtimes()

    print("  Scanning app configs...", file=sys.stderr)
    app_configs = scan_app_configs()

    # Build sections (only include detected ones)
    sections = []
    toc_entries = []
    section_num = 0

    # 1. Dock Layout (always)
    if dock_apps:
        section_num += 1
        sections.append(build_dock_section(dock_apps, section_num))
        toc_entries.append(("Dock Layout", section_num, False))

    # 2. Applications (always)
    if applications:
        section_num += 1
        sections.append(build_apps_section(applications, section_num))
        toc_entries.append(("Applications", section_num, True))

    # 3. Shell Configuration
    if shell_config:
        section_num += 1
        sections.append(build_shell_section(shell_config, section_num))
        toc_entries.append(("Shell Configuration", section_num, True))

    # 4. ~/bin
    if bin_items:
        section_num += 1
        sections.append(build_bin_section(bin_items, section_num))
        toc_entries.append(("~/bin Scripts & Tools", section_num, True))

    # 5. SSH
    if ssh_data:
        section_num += 1
        sections.append(build_ssh_section(ssh_data, section_num))
        toc_entries.append(("SSH Keys & Config", section_num, True))

    # 6. Git
    if git_data:
        section_num += 1
        sections.append(build_git_section(git_data, section_num))
        toc_entries.append(("Git Configuration", section_num, True))

    # 7. Fonts
    if fonts:
        section_num += 1
        sections.append(build_fonts_section(fonts, section_num))
        toc_entries.append(("Custom Fonts", section_num, True))

    # 8. App Configs
    if app_configs:
        section_num += 1
        sections.append(build_app_configs_section(app_configs, section_num))
        toc_entries.append(("App Configurations", section_num, True))

    # 9. Runtimes
    if runtimes:
        section_num += 1
        sections.append(build_runtimes_section(runtimes, section_num))
        toc_entries.append(("Runtimes & Packages", section_num, True))

    # 11. Homebrew
    if brew_data:
        section_num += 1
        sections.append(build_homebrew_section(brew_data, section_num))
        toc_entries.append(("Homebrew", section_num, True))

    # 11. Mint
    if mint_data:
        section_num += 1
        sections.append(build_mint_section(mint_data, section_num))
        toc_entries.append(("Mint Packages", section_num, True))

    # 12. Developer Tools
    if dev_tools and (dev_tools["tools"] or dev_tools["signing_identities"]):
        section_num += 1
        sections.append(build_dev_tools_section(dev_tools, section_num))
        toc_entries.append(("Developer Tools", section_num, True))

    # 13. Claude Code
    if claude_data:
        section_num += 1
        sections.append(build_claude_code_section(claude_data, section_num))
        toc_entries.append(("Claude Code", section_num, True))

    # Build TOC
    toc_html = ""
    for title, num, has_count in toc_entries:
        count_span = f'<span class="toc-count" data-toc="s{num}"></span>' if has_count else ""
        toc_html += (
            f'    <a class="toc-item" href="#s{num}" data-section="s{num}">'
            f'<span class="toc-num">{num:02d}</span>{escape(title)}{count_span}</a>\n'
        )

    # Load CSS and JS
    css = ASSETS_DIR / "styles.css"
    js = ASSETS_DIR / "template.js"
    css_content = css.read_text() if css.exists() else "/* CSS not found */"
    js_content = js.read_text() if js.exists() else "// JS not found"

    # Title
    title_name = user_name or run(["id", "-F"]) or "Developer"

    # Assemble HTML
    html = f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mac Migration &mdash; {escape(title_name)}</title>
<style>
{css_content}
</style>
</head>
<body>

<!-- Mobile toggle -->
<button class="sidebar-toggle" onclick="toggleSidebar()" aria-label="Toggle menu">
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
</button>
<div class="sidebar-overlay" id="sidebarOverlay" onclick="toggleSidebar()"></div>

<!-- Sidebar -->
<aside class="sidebar" id="sidebar">
  <div class="sidebar-header">
    <h1>Mac Migration</h1>
  </div>
  <div class="sidebar-progress">
    <div class="progress-top">
      <span class="progress-label">Progress</span>
      <span class="progress-pct" id="progressPct">0%</span>
    </div>
    <div class="progress-track"><div class="progress-fill" id="progressFill"></div></div>
  </div>
  <nav class="toc" id="toc">
{toc_html}
  </nav>
  <div class="sidebar-footer">
    <div class="sidebar-footer-controls">
      <button class="theme-toggle" onclick="toggleTheme()" id="themeToggle">
        <svg id="themeIcon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></svg>
        <span id="themeLabel">Light</span>
      </button>
      <button class="btn-reset" onclick="resetAll()">Reset</button>
    </div>
  </div>
</aside>

<!-- Main content -->
<div class="main">
  <div class="container">
    <div class="hero">
      <div class="hero-eyebrow">Field Manual</div>
      <h2 class="hero-title">Mac Migration</h2>
      <p class="hero-sub">{escape(title_name)}</p>
    </div>

{"".join(sections)}
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
{js_content}
</script>
</body>
</html>"""

    # Write output
    output = Path(output_path)
    output.write_text(html)
    print(f"\nGenerated: {output}", file=sys.stderr)
    print(f"Sections: {section_num}", file=sys.stderr)
    print(f"File size: {output.stat().st_size / 1024:.0f} KB", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Mac migration checklist")
    parser.add_argument("output", nargs="?", default="mac-migration.html",
                        help="Output HTML file path (default: mac-migration.html)")
    parser.add_argument("--name", "-n", default=None,
                        help="Your name for the title (default: auto-detect)")
    args = parser.parse_args()
    generate(args.output, args.name)
