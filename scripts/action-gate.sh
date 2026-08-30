#!/bin/sh
# Classify a pull request before any credentials are introduced.

set -eu

if [ -z "${GITHUB_EVENT_PATH:-}" ]; then
    echo "error: GITHUB_EVENT_PATH is required" >&2
    exit 2
fi
if [ ! -r "$GITHUB_EVENT_PATH" ]; then
    echo "error: GITHUB_EVENT_PATH is not readable" >&2
    exit 2
fi
if [ -z "${GITHUB_OUTPUT:-}" ]; then
    echo "error: GITHUB_OUTPUT is required" >&2
    exit 2
fi

is_trusted=$(python3 - "$GITHUB_EVENT_PATH" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as event_file:
        event = json.load(event_file)
    repository = event["repository"]["full_name"]
    head_repository = event["pull_request"]["head"]["repo"]["full_name"]
    print("true" if head_repository == repository else "false")
except (KeyError, TypeError, ValueError, OSError):
    sys.exit(2)
PY
) || {
    echo "error: invalid pull request event" >&2
    exit 2
}

printf 'trusted=%s\n' "$is_trusted" >> "$GITHUB_OUTPUT"
if [ "$is_trusted" = "false" ]; then
    echo "::notice title=attest::Fork pull request skipped before credentials or head-code execution"
fi
