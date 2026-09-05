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
- **Yellow (a), the impact scope, is author-visible (D-143, D-145) and now has three
  conditions (D-150).** For each function the diff changed: its call sites, whether a test
  *names* each caller, whether the signature or return annotation moved, whether it raises a
  type the base did not, and whether any call site now passes fewer positional arguments than it
  takes. It speaks on **a1** signature ∧ untested caller, **a2** new raise or moved return
  annotation ∧ untested caller, or **a3** an added required parameter ∧ a statically broken
  call — a3 rests on no coverage proxy and a tested caller does not silence it. At most two
  notes per pull request, at `$0.00`: no model, no execution, no network. **Each condition was
  measured separately on the same 79 units and each fires on none of them**; the one time the
  level has spoken on real traffic (`corum`, 2026-09-06c) every clause was true and the author
  had already updated the caller.
- **Yellow (b), the null/Optional class (D-151).** The first level where a model proposes and a
  checker decides: the model names a parameter, a line and a caller; three premises are then read
  out of the head tree — the parameter admits None, the line dereferences it with no recognised
  guard above it, and some caller's argument comes from a function whose return annotation admits
  None. All three or nothing, and a void is written to the ledger with the premise that failed.
  **13 hypotheses over 79 units, 0 survived**, 11 of them dying because the corpus carries no
  type annotations. It costs **one extra model call per review**, found or not — the benchmark's
  product arm moved from $0.0108 to $0.0144 a case for exactly this reason.
- **The terminal report is the comment's four sentences (D-152, D-153).** `attest review` prints
  one contract line per level, red first, `[silent]` when nothing spoke, and one accounting line
  that always names units read, candidates, and the drawer's reason distribution. `--explain`
  prints one line per silent candidate. In the pull-request comment, red's evidence — command,
  test, six runs, logs — moved into a collapsed block, so the summary's first screen is what the
  four levels said.
- **The green channel reached a real pull request** (2026-09-05): one `structural` comment,
  coordinates and a measure, no defect claimed. On 2026-09-06c a single pull request carried
  **red, yellow and green at once** — two receipts, one impact note, one structural note
  ([as posted](docs/acceptance/evidence/2026-09-06c-pr11-comment.md)).
- **What the four levels say on ordinary traffic, measured** (2026-09-06c): over the 40 most
  recent commits of this repository and `us-stock-helper`, **green speaks 8 times and red,
  yellow (a) and yellow (b) speak 0**; every level is silent on 32 of 40, at `$0.051` a commit
  ([table](docs/acceptance/2026-09-06c-four-levels.md)).

### Evidence and certification

- **Reproductions are recorded rather than asserted (D-146).** The model chooses *what to
  call*; the merge base is executed to record what that call does; the assertion is written from
  the recording. `unfaithful generated test: fails on base as well` — 20 of 31 answered
  candidates on forward pairs before this — is structurally impossible on the new path. The
  legacy generator remains as `probe_generation = false`.
- **A delivery journal row is read under the shape it was written (D-149).** D-142's level
  marker had been made mandatory in the journal's integrity check, which retroactively
  invalidated every row written before it — and `attest review` **aborted at startup** on any
  repository holding one, because the alpha projection reconciles the journal before a candidate
  is read. Found when 14 of the first 19 held-out cases crashed on their own 2026-09-03 ledgers.
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
- **The 15 value-class drawers the probe generator produced, adjudicated by hand** (2026-09-06c):
  **0 real defects, 15 intended changes, 0 undecidable**, all fifteen on two `click` commits and
  every one of them documented in that commit's own changelog. `attest.intent.v4.1` is left
  alone, and this is explicitly *not* offered as evidence that clause (c) is well calibrated —
  n is two commits and both are unusually loud
  ([adjudication](docs/acceptance/2026-09-06c-value-class-adjudication.md)).
- **The gate level's shadow has its first observations at the publishing grade** (2026-09-06c):
  **9 `through_caller` of 314 new-code candidates cumulatively (2.9%), 0 `direct`**. The
  2026-09-05 "0 of 224" was a static result — no reproduction executed, so no grade could be
  taken ([report](docs/acceptance/2026-09-06c-gate-shadow.md)).

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
