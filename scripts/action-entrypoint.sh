#!/bin/sh
# Launch attest CI only after rejecting fork pull requests.

set -eu

github_token=${INPUT_GITHUB_TOKEN:-}
model_api_key=${INPUT_MODEL_API_KEY:-}
unset INPUT_GITHUB_TOKEN INPUT_MODEL_API_KEY

if [ -z "${GITHUB_EVENT_PATH:-}" ]; then
    echo "error: GITHUB_EVENT_PATH is required" >&2
    exit 2
fi
if [ ! -r "$GITHUB_EVENT_PATH" ]; then
    echo "error: GITHUB_EVENT_PATH is not readable" >&2
    exit 2
fi

is_fork=$(
    python3 - "$GITHUB_EVENT_PATH" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as event_file:
        event = json.load(event_file)
    print("true" if event["pull_request"]["head"]["repo"]["fork"] else "false")
except (KeyError, TypeError, ValueError, OSError):
    sys.exit(2)
PY
) || {
    echo "error: invalid pull request event" >&2
    exit 2
}

if [ "$is_fork" = "true" ]; then
    echo "attest: fork pull request skipped before head-code execution"
    exit 0
fi

if [ -z "$github_token" ] || [ -z "$model_api_key" ]; then
    echo "error: trusted pull requests require both action credentials" >&2
    exit 2
fi
if [ -z "${ATTEST_VENV:-}" ]; then
    echo "error: ATTEST_VENV is required" >&2
    exit 2
fi
if [ -z "${GITHUB_WORKSPACE:-}" ]; then
    echo "error: GITHUB_WORKSPACE is required" >&2
    exit 2
fi
if [ ! -x "$ATTEST_VENV/bin/attest" ]; then
    echo "error: attest executable is unavailable" >&2
    exit 2
fi

export GITHUB_TOKEN=$github_token
export ANTHROPIC_API_KEY=$model_api_key
exec "$ATTEST_VENV/bin/attest" --repo "$GITHUB_WORKSPACE" ci \
    --event-path "$GITHUB_EVENT_PATH" \
    --budget "${INPUT_BUDGET_USD:-0.25}" \
    --k "${INPUT_SAMPLES:-5}" \
    --verification-timeout "${INPUT_VERIFICATION_TIMEOUT:-600}"
