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

- Phase 0 — `attest.core` betting engine library: in progress
- Phase 1 — `attest review` CLI: pending
- Phase 2 — dogfood: pending

Local development only; not published.

## Development

```
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
```

Design decisions are logged in [DECISIONS.md](DECISIONS.md).

License: Apache-2.0. Copyright 2026 Franz Xu.
