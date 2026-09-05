# Changelog

Attest is a research prototype, and this file is written for someone deciding whether a given
ref is safe to point their repository at. Every entry says what changed **and what it costs in
recall or in trust**, because in this project those are the same currency.

The authority for *why* something changed is [`DECISIONS.md`](DECISIONS.md); dated measurements
live under [`docs/acceptance/`](docs/acceptance/). This file is the index, not the evidence.

Versions follow [semantic versioning](https://semver.org/) once `v0.1.0` exists. Until then the
only published ref is a pilot tag, and the sections below say plainly which is which.

## Unreleased

The work since `v0.1.0-pilot.1`. It is on `main` and it is **not tagged**: a `v0.1.0` needs
three product conditions that do not hold yet
([readiness](docs/acceptance/2026-09-06b-v01-tag-readiness.md)).

### Author-visible surface

- **The output contract (D-142).** Every author-visible line is *one line* carrying a level
  marker (`[red]`, `[gate]`, `[yellow]`, `[green]`), a `file:line` coordinate, one sentence of
  fact, and an evidence reference. Preamble, pull-request restatement, unlocated hedge,
  evaluation of the author and tool disclaimer are refused by a non-model adjudicator. A wholly
  silent review says exactly one line, and that line names how many change units it read.
- **Yellow (a), the impact scope, is author-visible (D-143, D-145).** For each function the
  diff changed: its call sites, whether a test *names* each caller, and whether the signature or
  return annotation moved. It speaks only when the interface moved **and** some caller is named
  by no test, at most two notes per pull request, at `$0.00` — no model, no execution, no
  network. On the 79 units it was measured over, that conjunction fires on none of them.
- **The green channel reached a real pull request** (2026-09-05): one `structural` comment,
  coordinates and a measure, no defect claimed.

### Evidence and certification

- **Reproductions are recorded rather than asserted (D-146).** The model chooses *what to
  call*; the merge base is executed to record what that call does; the assertion is written from
  the recording. `unfaithful generated test: fails on base as well` — 20 of 31 answered
  candidates on forward pairs before this — is structurally impossible on the new path. The
  legacy generator remains as `probe_generation = false`.
- **Bundle integrity is checked before publication (D-124)**, after four bundles were found
  carrying a `test_repro.py` that was not the test the runs executed.
- **The intent discriminator reached v4.1 (D-127 → D-134).** A changed return value publishes
  only against a base specification the change left standing. It costs the whole value class on
  the recorded corpus — 0 certified of 48 — and that cost is the decision.
- **The publication family is computed per change unit (D-125).**

### Measurement

- **`G-NULL-001a`'s independent 68-control population is finished and closed (D-141, D-144):**
  answered n = 7, **0 wrong publications**, 1 true positive found *on a control*. No bound is
  claimed from it; D-134's 5.2% at n = 58 remains the only bound the gate has.
- **Forward pairs, where time runs forwards (D-135, D-140):** 11 defect-introducing commits,
  3 certified and 3 published, value class 0 of 1.
- **A live defect in `more-itertools` was found as a null control** and adjudicated by an
  independent probe on four interpreters.

### Known limits at this ref

Head code still runs in a best-effort same-runner boundary, not an OS isolation boundary; the
new-code class abstains by design; and a silence is an abstention, never a true negative. The
[README's limits section](README.md#current-status) is the full list and it is longer than this
one.

## `v0.1.0-pilot.1` — 2026-09-03

The first published ref, cut for a private pilot. An outside repository installed the Action at
this tag, built the production image on a GitHub runner and received one author-visible comment
(a `DEFER`, 2026-09-04). It is a pilot tag: it is not a release, it makes no null-safety claim,
and it predates the output contract, the intent discriminator's v4 and v4.1, bundle-integrity
verification and probe-recorded reproductions.
