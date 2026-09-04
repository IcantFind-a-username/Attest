#!/bin/sh
# Launch attest CI only after rejecting fork pull requests.

set -eu

if [ -z "${GITHUB_EVENT_PATH:-}" ]; then
    echo "error: GITHUB_EVENT_PATH is required" >&2
    exit 2
fi
if [ ! -r "$GITHUB_EVENT_PATH" ]; then
    echo "error: GITHUB_EVENT_PATH is not readable" >&2
    exit 2
fi

event_details=$(
    python3 - "$GITHUB_EVENT_PATH" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as event_file:
        event = json.load(event_file)
    repository = event["repository"]["full_name"]
    head_repository = event["pull_request"]["head"]["repo"]["full_name"]
    head_sha = event["pull_request"]["head"]["sha"]
    if not isinstance(head_sha, str) or not head_sha or any(character.isspace() for character in head_sha):
        raise ValueError("invalid head SHA")
    print(("true" if head_repository == repository else "false") + " " + head_sha)
except (KeyError, TypeError, ValueError, OSError):
    sys.exit(2)
PY
) || {
    echo "error: invalid pull request event" >&2
    exit 2
}
is_trusted=${event_details%% *}
expected_head=${event_details#* }

if [ "$is_trusted" = "false" ]; then
    echo "attest: fork pull request skipped before credentials or head-code execution"
    exit 0
fi

actual_head=$(git -C "${GITHUB_WORKSPACE:-}" rev-parse HEAD 2>/dev/null) || {
    echo "error: workspace HEAD is unavailable" >&2
    exit 2
}
if [ "$actual_head" != "$expected_head" ]; then
    echo "error: workspace HEAD does not match pull request head" >&2
    exit 2
fi

github_token=${INPUT_GITHUB_TOKEN:-}
model_api_key=${INPUT_MODEL_API_KEY:-}
unset INPUT_GITHUB_TOKEN INPUT_MODEL_API_KEY

# A missing credential is the most common first-run failure and the operator can
# fix it in under a minute -- if the message says where, what the name has to be,
# and that nothing has happened yet. It names no value, only names.
secrets_url="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-OWNER/REPO}/settings/secrets/actions/new"
if [ -z "$model_api_key" ]; then
    cat >&2 <<EOF
error: attest did not run -- the model API key secret is empty or missing.

  Nothing was sent anywhere. No model was called, no code left this runner, and
  no key was read, stored or logged.

  Fix it once, in this repository:
    1. open $secrets_url
    2. Name:   ANTHROPIC_API_KEY      <- exactly this, case-sensitive
       Secret: your Anthropic API key
    3. re-run this job

  Your workflow passes it through as:
        model-api-key: \${{ secrets.ANTHROPIC_API_KEY }}
  so the secret's Name and the name inside secrets.* must be the same word. A
  secret also arrives empty when the pull request comes from a fork -- forks
  never receive secrets, and attest skips them before this point.
EOF
    exit 2
fi
if [ -z "$github_token" ]; then
    cat >&2 <<EOF
error: attest did not run -- the GitHub token input is empty or missing.

  Nothing was sent anywhere and no model was called.

  Your workflow must pass the token GitHub already gives the job:
        github-token: \${{ secrets.GITHUB_TOKEN }}
  and the job needs "permissions: pull-requests: write" to leave a comment.
  There is nothing to create in $secrets_url for this one -- GITHUB_TOKEN is
  provided by Actions itself.
EOF
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
