#!/usr/bin/env python3
"""Noko Time API helper — single module for all API operations."""

import json
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = None

BASE_URL = "https://api.nokotime.com/v2"


def get_token():
    result = subprocess.run(
        ["security", "find-generic-password", "-s", "noko-api", "-a", "noko", "-w"],
        capture_output=True, text=True,
    )
    token = result.stdout.strip()
    if not token:
        print("ERROR: No Noko API token found. Run /noko setup to store your token.")
        sys.exit(1)
    return token


def api_get(path, token):
    req = urllib.request.Request(
        f"{BASE_URL}/{path}",
        headers={"X-FreckleToken": token, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, context=SSL_CONTEXT) as resp:
        return json.load(resp)


def api_post(path, body, token):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/{path}",
        data=data,
        headers={
            "X-FreckleToken": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, context=SSL_CONTEXT) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}")
        sys.exit(1)


def cmd_verify():
    token = get_token()
    req = urllib.request.Request(
        f"{BASE_URL}/current_user",
        headers={"X-FreckleToken": token, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, context=SSL_CONTEXT) as resp:
            print(f"OK ({resp.getcode()})")
    except urllib.error.HTTPError as e:
        print(f"FAILED ({e.code})")
        sys.exit(1)


def cmd_projects(search=None):
    token = get_token()
    qs = "enabled=true"
    if search:
        qs += f"&name={urllib.parse.quote(search)}"
    print(json.dumps(api_get(f"projects?{qs}", token), indent=2))


def cmd_entries(from_date, to_date):
    token = get_token()
    print(json.dumps(
        api_get(f"current_user/entries?from={from_date}&to={to_date}", token),
        indent=2,
    ))


def cmd_create(date, minutes, description, project_id):
    token = get_token()
    body = {
        "date": date,
        "minutes": int(minutes),
        "description": description,
        "project_id": int(project_id),
    }
    result = api_post("entries", body, token)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: noko_api.py <verify|projects|entries|create> [args...]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "verify":
        cmd_verify()
    elif command == "projects":
        cmd_projects(sys.argv[2] if len(sys.argv) > 2 else None)
    elif command == "entries":
        if len(sys.argv) < 4:
            print("Usage: noko_api.py entries <from_date> <to_date>")
            sys.exit(1)
        cmd_entries(sys.argv[2], sys.argv[3])
    elif command == "create":
        if len(sys.argv) < 6:
            print("Usage: noko_api.py create <date> <minutes> <description> <project_id>")
            sys.exit(1)
        cmd_create(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
