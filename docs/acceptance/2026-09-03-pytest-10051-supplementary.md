# Supplementary rerun: `pytest-dev__pytest-10051` after the D-104 shadow fix

One case, reported apart. **It is not merged into the one-time held-out table**
and changes no number in `README.md` or the E-02 report.

## Why it exists

The one-time held-out run deferred this case with an environment bootstrap
failure. The supplementary rerun after the bootstrap fix (`5fc03fa`) deferred it
again, this time with a **false positive**: the shadow check compared every
loaded module's dotted name against the *tail* of the anchored path, so the
stdlib `logging` package was reported as a shadow of pytest's
`src/_pytest/logging.py` (D-104). The rerun the owner authorised asks what the
case does once that false positive is gone.

The first attempt at this rerun, in the 2026-09-03c window, spent **$0.00**: the
`docker build` for pytest's image hit the 1800 s cap and raised
`subprocess.TimeoutExpired` out of backend selection before any model call.

## The three runs of this one case

| run | product code | spend | outcome |
|---|---|---|---|
| one-time held-out | pre-fix | $0.022297 | DEFER — `isolation backend unavailable: environment bootstrap failed` |
| supplementary after the bootstrap fix | `5fc03fa` | $0.019252 | DEFER — `binding: the anchored module logging was imported from outside the head tree` (**false positive**, D-104) |
| **this run** | `e1b112f` | **$0.019502** | DEFER — `unfaithful generated test: fails on base as well` |

This run: 1 candidate, **1 eligible**, 1 reproduction attempted, 0 certified,
0 published; proposal prompt tokens 9,364 of which 7,017 were cache reads.

## What it says

The D-104 fix works on the case that motivated it: the candidate now clears
binding and reaches the faithfulness check, where it fails for an unrelated and
honest reason — the generated test fails on the base tree too, so it
discriminates nothing and buys nothing. **The case still does not certify.**
One case is not evidence about recall; it is evidence that one specific false
positive no longer blocks this one case.

## Why no image was built

The `docker build` that timed out in the previous window was never necessary:
the image for this exact tree, `attest-repro:523d6f3b150c6681`, had already been
built during the `5fc03fa` run and was still on the host. It was not reused
because `docker image inspect <name:tag>` was answering *No such image* for tags
the same daemon listed in `docker images` and resolved by image id — a daemon
condition observed directly again in this window. `image_digest` reads that
answer as "image absent" and rebuilds, and it has no way to tell "docker says
no" from "docker could not answer" (backlog).

The rerun therefore needed no build and never approached the 1800 s cap. **The
cap was not raised**, as instructed.

## Limits

The host's docker daemon would not complete *any* build for the rest of this
window — a one-line `FROM python:3.9-slim` context hung past three minutes with
the daemon still answering `image inspect` and `docker run` normally. This case
ran only because its image already existed. That is a host condition, not a
product defect, but it bounded what else could be measured in this window.
