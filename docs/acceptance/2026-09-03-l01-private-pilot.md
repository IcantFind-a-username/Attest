# L-01 private pilot — the quickstart, verbatim, on an outside repository

**Date:** 2026-09-03 · **install ref:** `v0.1.0-pilot.1` (`eedb656`) · **pilot repository:**
`IcantFind-a-username/us-stock-helper` (owner decision D) · **no GitHub write of any kind:**
every review ran through the local `attest review` path and its output was captured to a file.

## Protocol

[`docs/operations/quickstart.md`](../operations/quickstart.md) §1 and §2 were executed
literally, from a **fresh clone** of Attest at the tag and a **fresh clone** of the pilot
repository:

```
git clone https://github.com/IcantFind-a-username/Attest.git && cd Attest
git checkout v0.1.0-pilot.1
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-toolchain.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/attest --help
```

then, per commit, `head = commit`, `base = parent`:

```
<fresh Attest>/.venv/bin/attest review --base <parent> --k 4 --budget 0.25 \
    --verification-timeout 900
```

The quickstart's `--base main` was replaced by the reviewed commit's parent so that three
individual commits could be reviewed; nothing else deviated. The reviewed clone had no
`.attest/` state before the second set.

**Two commit sets, because the repository's default branch is not `main`.** The clone's
default branch is `feature/iphone-demo`; `main`'s tip (`00549e4`, 2026-08-15) is not the
newest work in the repository. Set 1 is the three most recent commits of `main`; set 2 is the
three most recent non-merge commits by date (on `claude/token-quota-check-4lvpkl`), one of
which changes existing Python and can therefore reach the reproduction stage. Both are
reported.

## Results

| set | commit | what it changes | units read | candidates | eligible | reproductions | certified | published | outcome | spend |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `00549e4` docs: adopt the apache 2.0 license | `LICENSE` | 1 of 1 | 0 | 0 | 0 | 0 | 0 | documented silence | $0.0146 |
| 1 | `4170859` feat: traceable no-lookahead indicator prototype | 12 files, all-new Python package | **1 of 2, budget-limited** | 9 | 0 | 0 | 0 | 0 | documented silence (new code) | $0.0852 |
| 1 | `dd75a7e` chore: ignore local worktrees | `.gitignore` | 1 of 1 | 0 | 0 | 0 | 0 | 0 | documented silence | $0.0072 |
| 2 | `8687625` docs: log the commit-authorship lesson | `CLAUDE.md` | 1 of 1 | 0 | 0 | 0 | 0 | 0 | documented silence | $0.0053 |
| 2 | `f57fc39` backlog entry | `docs/backlog.md` | 1 of 1 | 0 | 0 | 0 | 0 | 0 | documented silence | $0.0137 |
| 2 | `f58bf64` feat(market_gateway): read-only options-flow slice | 7 files, changed + new Python | **2 of 3, budget-limited** | 15 | **1** | **1** | 0 | 0 | documented silence (unfaithful test) | $0.1512 |

**Total $0.2772 across six reviews. Publications: 0 of 6. Every silence carries a stated
reason in the run status.**

The one reproduction attempt ran the full production path: the executor recorded
`profile linux-container-v1, available true, image attest-repro:55ef0e3569cdbbe3`, built the
project's image from its own manifests and ran the generated test in the container. It
DEFERred with `unfaithful generated test: it references a symbol absent from head, so its
head failure is a stale reference rather than a defect` — the candidate claimed
`MarketGatewayService` has no `options_flow` method, and the generated test asserted against
a name that does not exist on head, which the faithfulness check refuses rather than
publishes.

## The exit criterion

Mainline §2 step 16's RED — *the quickstart executed verbatim on a fresh clone of an outside
repository yields a receipt-backed comment or a documented silence* — is met by six documented
silences. **The receipt-backed branch was not exercised on this repository:** none of the six
commits contained a regression against its own parent, so nothing could be certified. The
receipt path's evidence remains the held-out corpus (`G-RECALL-002`) and E-01/E-04; the pilot
proves the wiring end to end — install, plan, propose, classify, generate, containerised
differential reproduction, faithfulness refusal, status, ledger — not the product's recall.

## Wiring problems the pilot exposed, and the fixes

| # | problem | fix | RED |
|---|---|---|---|
| 1 | `examples/pull-request.yml` pinned `uses: …/Attest@main`: an operator copying the example installed a moving branch while `install-ref.md` promised an immutable ref | pinned to `v0.1.0-pilot.1` | `test_example_workflow_pins_the_action_to_an_immutable_ref` (rejects `main`/`master`/`HEAD` and anything not a version tag or full SHA) |
| 2 | `attest --help` described `verify` only as a self-report recorder, so nothing pointed at the offline bundle verifier the quickstart tells the operator to run | subcommand help names the offline bundle check first | `test_top_level_help_says_verify_checks_a_bundle_offline` |
| 3 | quickstart §1 ran `python -m venv`; `python` is absent on a stock macOS, so step 1 failed on the pilot machine | `python3 -m venv` | doc |
| 4 | quickstart §2 promised exactly two local outcomes; local review also prints an `unverified candidates (…)` drawer list, and the run status can now say `read N of M units, budget-limited` | quickstart and `failure-modes.md` describe both | doc |

Checked and found correct, no change: the example workflow's `permissions:` block
(`contents: read` + `pull-requests: write` covers both endpoints the client uses —
`POST/PATCH /repos/…/issues/…/comments` and `POST /repos/…/pulls/…/reviews`); `fetch-depth: 0`
for merge-base resolution; the `pull_request` event payload shape
(`load_pull_request_context` parses a full synchronize payload and marks it non-fork);
the Action's interpreter pin (3.12.8, within `requires-python >= 3.11`).

## What the pilot did not test

- no GitHub write path was exercised (by instruction): no comment was posted, so
  `upsert_issue_comment` and `create_review` were not run against the API;
- no certification, therefore no receipt, no offline verification and no publication policy
  on real pilot traffic;
- the kill switch (`enabled = false`) and rollback were not exercised on the pilot repository;
  their tests remain the suite's;
- one repository, six commits: this is a wiring pilot, not a measurement.
