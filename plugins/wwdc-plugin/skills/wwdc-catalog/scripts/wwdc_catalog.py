#!/usr/bin/env python3
"""
Extract the WWDC session catalog URL from the Apple Developer app on macOS
and fetch the catalog JSON.

This is a Python port of the WWDCKit Swift package.
"""

import gzip
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

CDN_URL_PREFIX = b"https://devimages-cdn.apple.com/wwdc-services/"

DEFAULT_DEVELOPER_APP_PATH = "/Applications/Developer.app"
WWDCCORE_RELATIVE_PATH = "Contents/Frameworks/WWDCCore.framework/Versions/A/WWDCCore"


def extract_base_url(data: bytes) -> str:
    """Extract the CDN base URL from the WWDCCore binary data."""
    pos = data.find(CDN_URL_PREFIX)
    if pos == -1:
        raise ValueError("Could not find CDN URL prefix in binary data")

    end = pos + len(CDN_URL_PREFIX)
    while end < len(data) and data[end] != 0x00:
        end += 1

    url = data[pos:end].decode("ascii")
    return url


def extract_contents_url(data: bytes) -> str:
    """Extract the full contents.json URL from the WWDCCore binary data."""
    base = extract_base_url(data)
    if not base.endswith("/"):
        base += "/"
    return base + "contents.json"


def read_wwdccore_binary(app_path: str = DEFAULT_DEVELOPER_APP_PATH) -> bytes:
    """Read the WWDCCore binary from Developer.app."""
    if not os.path.basename(app_path) == "Developer.app":
        raise ValueError(f"Not a Developer.app path: {app_path}")

    binary_path = os.path.join(app_path, WWDCCORE_RELATIVE_PATH)
    if not os.path.exists(binary_path):
        raise FileNotFoundError(f"WWDCCore binary not found at: {binary_path}")

    with open(binary_path, "rb") as f:
        return f.read()


def fetch_url(url: str) -> bytes:
    """Fetch URL content, with SSL certificate fallback for macOS."""
    req = urllib.request.Request(url)
    req.add_header("Accept-Encoding", "gzip, deflate")
    try:
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLCertVerificationError):
            # macOS standalone Python installs often lack certs until you run
            # "Install Certificates.command". Fall back to unverified context.
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, context=ctx) as resp:
                data = resp.read()
        else:
            raise
    # Decompress gzip if needed
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data


def normalize_catalog(catalog: dict) -> dict:
    """Normalize the catalog so content types are consistent across years.

    Older WWDCs (<=2019) use "Session" while newer ones use "Video" for the
    same kind of content. This rewrites all "Session" types to "Video" so
    consumers can filter on a single type.
    """
    for item in catalog.get("contents", []):
        if item.get("type") == "Session":
            item["type"] = "Video"
    return catalog


def fetch_catalog(url: str) -> dict:
    """Fetch and parse the WWDC catalog JSON from the given URL."""
    return json.loads(fetch_url(url))


def get_wwdc_catalog(app_path: str = DEFAULT_DEVELOPER_APP_PATH) -> dict:
    """
    Main entry point: extract the catalog URL from Developer.app
    and fetch the catalog. Returns a normalized catalog where all
    session/video content is typed as "Video".
    """
    data = read_wwdccore_binary(app_path)
    url = extract_contents_url(data)
    print(f"Catalog URL: {url}", file=sys.stderr)
    catalog = fetch_catalog(url)
    return normalize_catalog(catalog)


def print_catalog_summary(catalog: dict):
    """Print a summary of the catalog contents."""
    events = catalog.get("events", [])
    contents = catalog.get("contents", [])
    topics = catalog.get("topics", [])

    print(f"Events: {len(events)}")
    for event in events:
        print(f"  - {event.get('name', 'Unknown')} ({event.get('id', '?')})")

    print(f"Content items: {len(contents)}")
    print(f"Topics: {len(topics)}")

    videos = [c for c in contents if c.get("type") == "Video"]
    labs = [c for c in contents if "lab" in c.get("type", "").lower()]
    print(f"  Videos: {len(videos)}")
    print(f"  Labs: {len(labs)}")


if __name__ == "__main__":
    app = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DEVELOPER_APP_PATH
    try:
        catalog = get_wwdc_catalog(app)
        print_catalog_summary(catalog)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
