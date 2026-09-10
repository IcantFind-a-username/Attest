# Contributing to attest

This page is for someone changing attest, not someone using it. If you are installing it, the
[README](../README.md) is the whole of what you need and this page is not.

**Start with [`AGENTS.md`](../AGENTS.md).** It is the standing construction guide and it binds
coding agents and people equally: instruction authority, the product invariants, git discipline,
the spend rules, and the stop-and-ask conditions. The complete documentation map is
[`docs/README.md`](README.md).

| what you want | where it is |
|---|---|
| why something is the way it is | [`DECISIONS.md`](../DECISIONS.md) — every material trade-off, dated, with its reversal condition |
| what has been measured, and when | [`docs/acceptance/`](acceptance/) — dated reports; append-only evidence, never current plans |
| the gates a change has to pass | [`docs/acceptance/evolution-gates.md`](acceptance/evolution-gates.md) |
| the order the remaining work is done in | [`docs/mainline.md`](mainline.md), then [`docs/roadmap.md`](roadmap.md) |
| what every API dollar was spent on | [`DEVSPEND.md`](../DEVSPEND.md) — the sole owner of the cap, the settled total and the remaining headroom |
| the drawer of findings that did not earn a fix | [`docs/backlog.md`](backlog.md) |
| the target contracts | [`docs/architecture/target-algorithm.md`](architecture/target-algorithm.md) |

## The rules that are not obvious

- **`DEVSPEND.md` is authority, not a log.** Read it before any paid work. Its
  `Total API spend: $X of $Y.` line is the only machine-readable one and every paid preflight
  parses it; it is updated at the end of every window.
- **A measurement is named at its actual evidence level**, with numerator, denominator, interval,
  abstention and version. A silence is an abstention and never a true negative.
- **Never weaken a regression pin, skip or xfail a failing security test, lower the kernel
  coverage floor, change a denominator, or relax a receipt check to make the suite pass.**
- **One RED test per behaviour change**, observed failing before the implementation. Orders that
  only diagnose or measure carry no RED — their deliverable is the number.
- **Historical acceptance reports are append-only.** A correction is a visible erratum, never a
  rewrite that erases the original observation.

## Local development usage

The current CLI remains available while the receipt-only architecture is implemented:

```text
attest review [--base REF] [--alpha X] [--budget USD] [--k N]
attest verify <finding-id> --reproduced|--not-reproduced
attest feedback <finding-id> --fix|--good|--dismiss
attest stats [--since 7d|2026-09-01] [--drawer] [--json]
```

`attest verify --reproduced` currently updates local legacy gate bookkeeping. Do not treat
it as a trusted differential receipt or include it in autonomous-certification metrics.

BYOK model credentials are resolved through the provider SDK's standard credential chain.
Never expose them to generated tests or project code. Per-repository configuration currently
lives in `.attest.toml`; the evolution roadmap moves safety policy to a trusted base-owned
source. The local ledger under `.attest/` is gitignored.

## GitHub Action

The repository includes a self-installing composite Action and an
[example workflow](../examples/pull-request.yml). Read the
[current safety guide](github-action.md) before using it.

The Action is not yet approved for untrusted production deployment. Forks are skipped, and
same-repository head code still runs in a best-effort same-runner boundary. The roadmap
requires a privileged-controller/secretless-executor split and OS-level isolation before an
external pilot.

The historical 60-second acceptance criterion covered the initial status comment from job
start, not completion of differential verification; the current verification deadline can
be longer. No final-review-under-60-seconds claim is made.

## Development

Python 3.11 or newer is required. A typical local setup is:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src/attest
```

On Windows, use `.venv\Scripts\python` in place of `.venv/bin/python`. The supported
Gate toolchain is pinned in `requirements-toolchain.lock`; use the current branch's lock
and record exact interpreter/tool versions with every Gate result.

Coding agents start with [AGENTS.md](../AGENTS.md). The complete documentation map is
[docs/README.md](README.md). Design decisions are preserved in
[DECISIONS.md](../DECISIONS.md); dated reports remain evidence rather than current plans.

