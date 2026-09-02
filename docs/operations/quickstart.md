# Quickstart: from a fresh clone to the first receipt-backed comment or an explicit silence

This is the L-01 quickstart for one outside Python repository. It is written to be executed
verbatim. Every step either produces a verified comment backed by an evidence bundle or an
explicit, explained silence; there is no third outcome.

## What you need

- a Linux or macOS machine with Python 3.11+ and Docker (the production backend runs every
  reproduction in a container; without Docker the local `attest review` falls back to the
  host adapter and says so — CI never does);
- a model API key for the provider in `src/attest/data/pricing.toml` (`ANTHROPIC_API_KEY`),
  kept in the shell, never in the repository;
- for the GitHub Action: a repository token that may update pull-request comments.

## 1. Install attest from a stable ref

```bash
git clone https://github.com/IcantFind-a-username/Attest.git
cd Attest
git checkout v0.1.0-pilot.1   # the ref in docs/operations/install-ref.md
python -m venv .venv
.venv/bin/python -m pip install -r requirements-toolchain.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/attest --help
```

## 2. Review one change locally

In the repository you want reviewed, commit the change on a branch so the head is immutable,
then:

```bash
cd /path/to/your-repo
ANTHROPIC_API_KEY=... /path/to/Attest/.venv/bin/attest review --base main --k 4 --budget 0.25
```

`attest review` proposes candidates, runs the differential reproduction stage (the generated
test must fail on your head three times and pass on the merge-base three times, inside a
container), and prints one of:

- `verified findings (each backed by one accepted receipt):` followed by the test, the
  command to run it yourself, the run summaries, the bundle path and the offline
  verification command; or
- `checked N candidate(s); none was verified by a reproduction ... — abstained.` followed by
  `run status:` with the change units read, candidates, eligible, reproductions attempted
  and one line per reproduction failure with its category.

Nothing else is a finding. `attest stats --drawer` lists what was held back and why;
`attest feedback <id> --fix|--good|--dismiss` labels it.

## 3. Verify a receipt offline

```bash
/path/to/Attest/.venv/bin/attest verify --bundle .attest/evidence/<task>/<candidate> --require-seal
```

This recomputes every digest and the controller seal from the bundle alone.

## 4. Enable the Action on pull requests

Copy [`examples/pull-request.yml`](../../examples/pull-request.yml) into
`.github/workflows/`, pin `uses:` to the same ref you installed
(`IcantFind-a-username/Attest@v0.1.0-pilot.1`, see [`install-ref.md`](install-ref.md)), and
set the two secrets the workflow names. Fork pull requests are skipped before any credential or head code is touched.
The Action posts a running comment, then a final comment that is either the verified
findings (each with its test) or an explicit abstention, always with a collapsed run status.

The base branch owns the policy the review runs under; see
[`base-policy.md`](base-policy.md) for every key and its factory default.

## 5. Turn it off without a deploy

Commit `enabled = false` in `.attest.toml` on the base branch (see
[`kill-switch-and-rollback.md`](kill-switch-and-rollback.md)). The head of a pull request
cannot override it.
