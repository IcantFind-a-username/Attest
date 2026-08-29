# attest

Fast, precise, evidence-first AI code review. Says at most 3 things per PR, in under
60 seconds, each with evidence you can click and re-run — and says nothing rather than
something wrong.

The core is a sequential betting engine over evidence channels: each candidate finding
is a wager, evidence purchases multiply a wealth process (an e-process), and only the
wealth threshold decides who gets to speak — surface at wealth >= 1/alpha, discard at
wealth <= alpha, hold in the drawer otherwise. No vote counting, no vibes-based
confidence scores.

## Status

- Phase 0 — `attest.core` betting engine library: done (independently reviewed; regression-pinned to the seed experiment record)
- Phase 1 — `attest review` CLI: done (independently reviewed)
- Phase 2 — dogfood: done on 3 repos (5 verified findings surfaced, 2 negative controls silent, oversized diff budget-deferred); live-API path pending an ANTHROPIC_API_KEY

## Usage

```
attest review [--base REF] [--alpha X] [--budget USD] [--k N]   # review the diff
attest verify <finding-id> --reproduced|--not-reproduced        # record a reproduction attempt
attest feedback <finding-id> --fix|--good|--dismiss             # label a finding
attest stats                                                     # ledger summary
```

BYOK: set ANTHROPIC_API_KEY (resolved through the SDK's standard credential
chain). Per-repo configuration lives in `.attest.toml`; the local evidence
ledger in `.attest/` (gitignored).

Local development only; not published.

## Development

```
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
```

Design decisions are logged in [DECISIONS.md](DECISIONS.md).

License: Apache-2.0. Copyright 2026 Franz Xu.
