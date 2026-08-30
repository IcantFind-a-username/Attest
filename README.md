# attest

No differential reproduction, no published finding: attest is fast, precise,
evidence-first AI code review that publishes a finding only when the same generated
reproduction test deterministically fails on the reviewed head and passes on its base,
across repeated runs (N=3 per side) — otherwise it stays silent or explicitly defers.
At most 3 things per PR, in under 60 seconds, each backed by a test you can click and
re-run yourself. 宁可不说,不说错: better silent than wrong.

Underneath, a sequential betting process prices every piece of evidence —
correlation-discounted votes, capped static corroboration, differential reproduction —
and keeps an auditable ledger of why each finding did or did not speak. Its wealth
threshold, and nothing else, decides: surface at wealth >= 1/alpha, discard at wealth
<= alpha, hold in the drawer otherwise. At the factory constants, votes and
corroboration alone can never clear that bar — reproduction is the only evidence
strong enough to, by design (see DECISIONS.md, D-008). No vote counting, no
vibes-based confidence scores.

Be precise about where the error control comes from, because it is not where you
might assume. The vote and corroboration channels price only positive evidence and
have no factor below one, so they are not valid e-values and the wealth process is
not an e-process; a measured diagnostic puts their null expectation at 1.8-2.3x and
1.1-1.5x rather than the 1.0 an e-value requires (DECISIONS.md, D-026). What actually
holds the line at the shipped settings is arithmetic plus reproduction: the caps make
votes and corroboration unable to reach the gate at all, so the false-certification
rate equals the rate at which a differential reproduction confirms something false.
That is why reproduction must fail on head and pass on base across repeated runs —
it is not a feature on top of the guarantee, it is the guarantee.

## Status

- Phase 0 — `attest.core` betting engine library: done (independently reviewed; regression-pinned to the seed experiment record)
- Phase 1 — `attest review` CLI: done (independently reviewed)
- Phase 2 — dogfood: done on 3 repos (5 verified findings surfaced, 2 negative controls silent, oversized diff budget-deferred)
- Phase 3 — GitHub Action + differential-evidence executor: implemented locally (generates and runs the reproduction test that gates every finding)
- Live-API validation: done (real review surfaced in 11.1s wall clock at $0.04; negative control silent incl. a V-channel refutation; see DEVSPEND.md)
- Real-data benchmark: corpus frozen and preregistered — 20 bug-fix pairs, 40 cases, 4 open-source projects — no validation receipt yet, so no accuracy, stability, or precision numbers anywhere in this doc.

No live numbers to report until that receipt exists; next step is running the frozen corpus through the real pipeline.

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

## GitHub Action

The repository includes a self-installing composite action for pull-request review.
Start with [the workflow example](examples/pull-request.yml) and read the
[GitHub Action safety guide](docs/github-action.md) before enabling it.

## Development

```
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
```

Design decisions are logged in [DECISIONS.md](DECISIONS.md).

## Origin

attest grew out of [Corum](https://github.com/IcantFind-a-username/Corum), a
preregistered research project on dependence-aware consensus among unreliable
reviewers. Corum's formal experiment returned an honest negative result —
clever aggregation has almost no headroom over simple reliability weighting —
but the audit of that failure identified what *did* work: a calibrated betting
core whose confidence stays honest under correlated evidence, and a redundancy
discount that refuses to double-count clone opinions. attest is what those
survivors became when the goal changed from "aggregate opinions better" to
"speak only with evidence." The Corum repository is kept frozen as the
research record.

License: Apache-2.0. Copyright 2026 Franz Xu.
