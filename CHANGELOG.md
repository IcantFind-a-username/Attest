# Changelog

Attest is a research prototype, and this file is written for someone deciding whether a given
ref is safe to point their repository at. Every entry says what changed **and what it costs in
recall or in trust**, because in this project those are the same currency.

The authority for *why* something changed is [`DECISIONS.md`](DECISIONS.md); dated measurements
live under [`docs/acceptance/`](docs/acceptance/). This file is the index, not the evidence.

Versions follow [semantic versioning](https://semver.org/) once `v0.1.0` exists. Until then the
only published ref is a pilot tag, and the sections below say plainly which is which.

## Unreleased — since `v0.1.0-rc.1`

### The release-readiness acceptance, 2026-09-09 ([report](docs/acceptance/2026-09-09-release-readiness.md))

- **A review with nothing left to say posted itself anyway** (D-180). Found by this repository's
  own workflow reviewing the pull request that merges this acceptance. The inline review is
  entered when a *note* exists, and every comment can be dropped after that — an unanchorable
  green note, a comment the new action clause refuses, a propagation note that is a shadow. The
  result was an author-visible `Attest review.` carrying **no comments**, and then an exit 2
  from the delivery journal refusing the empty member list it had just been handed — *after*
  everything was published. The review is now attempted only when a comment survives. **No
  receipt can be lost to this**: red is never dropped, so an empty list means nothing was
  certified.
- **An outside repository could not be reviewed at all, and now can** (D-176). `tenacity`, a
  public pytest project nobody here owns, was cloned, and the tagged wheel was installed into a
  clean virtualenv. The reproduction image build died: the tree is copied without `.git`, so a
  project that versions itself from the repository cannot build, and the detector for that
  recognised `setuptools_scm` but not **`hatch-vcs`** — the same library reached through
  `hatchling`. One tuple. **If your `pyproject.toml` says `[tool.hatch.version] source = "vcs"`,
  no ref before this one could review your repository.**
- **And the refusal named the wrong cause** (D-175). BuildKit echoes the whole Dockerfile around
  a failure, so a build that died installing *the project* carried the successful
  `RUN pip install pytest` in its log and reported *"pytest could not be provided"*. The refusal
  is now decided by the failing step the builder names.
- **Every author-visible comment now says what to do next** (D-178). Four real comments were
  audited element by element; three carried no action at all. `check_comment` refuses a comment
  without exactly one `Action:` line naming something to run, open or change. Red's is the
  receipt's own command and bundle, yellow's the untested caller and the two things that close
  it, green's the two coordinates and which copy to keep. **Assembled from coordinates, never
  from a model**, so wording cannot suppress a finding.
- **A silence over a host that could not run the executor said `nothing met an adjudicator's
  bar`** (D-177) — a clean bill of health for code nothing looked at. It now names the reason and
  how many candidates it stopped. In the same line: D-161's budget verdict had never been
  admitted by `output_contract.check`, so the product's own adjudicator refused a line the
  product emits.
- **Two failures had no copy of their own** (D-179): every proposal call answering HTTP 429, and
  a runner that cannot reach the API, both ended at `all provider samples failed or were
  malformed`. Each now has its own sentence, says *nothing was spent*, and says what to do.
  `budget-usd: "0.00"` now names the input and a value that works.
- **The vocabulary was downgraded, and no constant moved.** *e-value* → **priority score**,
  *family-wise error* → **per-unit family cap**, in the README, the mainline, `selection.py` and
  the base-policy document. `alpha` stays the name of a configuration constant. The only
  evidence this product publishes on is the differential reproduction; S/T rank candidates and
  spend a multiplicity budget, and D-174 proved they are not an e-value.
- **A budget below `$0.54` cannot review anything at the factory `samples: "5"`** — measured, not
  derived: five samples reserve $0.16 of output tokens alone against a 30% discovery share. At
  `$0.25` exactly one of five samples is bought.
- **New: [`SECURITY.md`](SECURITY.md)** — reporting channel, supported versions, disclosure, what
  is in scope, and what is *not claimed*.

### Behaviour a reader pointing a repository at `main` should know about

- **A call site is now the definition the name *resolves to*, not whatever wrote the name**
  (D-174, [report](docs/acceptance/2026-09-08-binding-and-bounds.md)). One shared layer,
  `attest.review.binding`, answers this for the impact level, the propagation level, the gate
  level's reachability witness and the intent discriminator. **Recall moves in both
  directions.** Gained: an aliased import (`from mathlib import sqrt as root; root(v)`) is a
  call site and was invisible before, and a second definition of one name in a file the caller
  does not import is no longer read as ambiguity — a refusal that took 43 of 198 changed
  functions on the last recorded population. Lost, and this is the point: `import math;
  math.sqrt(9)` is no longer a call site of *your* `sqrt`. Re-counting the recorded gate
  witnesses is what that costs — **all 26** `through_caller` observations across **445**
  new-code candidates were name collisions, so the gate level's measured reachability on real
  traffic is **0.0%** and not 5.8%. Anything the layer cannot resolve —
  inheritance, decorators, a call through a variable, any bare name in a file with a star
  import — is an abstention, so all four levels get quieter.
- **An exception a function catches itself is no longer reported as escaping to your callers**
  (`attest.propagation.unhandled-exception.v2`). `except LookupError` is now known to catch a
  `KeyError`, because `builtins` says so; two class names Python does not know are
  **undecidable** and never asserted to be unhandled. Recall cost: real propagations through a
  project's own exception hierarchy are now abstentions.
- **The green level no longer calls two different functions the same implementation.** A bare
  call keeps its callee name, so `charge(...)` and `refund(...)` stop measuring 1.000
  (`attest.structural.duplicate-implementation.v2`). Recall cost: a genuine copy in which one
  call was also renamed now measures below the threshold.
- **A base-tree specification must be about the symbol your change touched**
  (`attest.intent.v4.2`). An `assert` counts only when its own scope names an anchored symbol, a
  docstring only when it belongs to one or names it, a documentation paragraph only when that
  paragraph names it; a change touching no function or class at all can have no specification
  and is drawered saying so. Recall cost: a value-class receipt whose old value was pinned only
  by an unrelated assertion elsewhere in the tree no longer publishes. Receipts already written
  are replayed under the version they record.
- **What the published `alpha` means across a whole pull request was overstated, and the
  correction is on every row.** Per-unit Bonferroni controls `alpha` inside a change unit and
  nowhere else; the pull-request union bound is `min(1, U * alpha)` over the units searched, not
  `hard_cap * alpha` — the cap hides findings *after* the search. Measured on the real selector:
  10 units at `alpha = 0.1` publish something in **65%** of pull requests, not 30%. And the
  quantity being thresholded is **not a proven e-value**: over 475 candidates of 276 control
  reviews its mean is **2.27** and its *minimum* is **2.0**, so it cannot fall below 1 at all.
  Every `publication_policy` row now carries `units_searched`, `pr_error_bound` and
  `e_value_validity: assumed-calibrated`. **No threshold, `alpha`, likelihood ratio, `K` or cap
  changed**, and no published receipt is impeached — S·T tops out at 9 against a bar of 10 at
  the factory alpha, so every publication this product has made rests on the differential
  execution.
- **A review now spends 30% of its budget on discovery, not 60%, and the first change unit is
  no longer exempt.** With the ranking and the per-unit cap below, this halved the spend on both
  recorded populations and kept every receipt (D-168,
  [replay](docs/acceptance/2026-09-08-schedule-replay.md)). The consequence to weigh: a large
  first change unit can now exhaust the discovery share on its own, and that review defers with
  a stated budget reason instead of proposing. On 28 recorded reviews at K=4 that happened
  **0 times**; at K=5, the shipped default, it would happen **once**.
- **Reproductions are bought in a new order and there are fewer of them.** Cluster size first,
  then a static credibility score computed from the head tree, then the finding id — a total
  order — and at most **3 per changed file**. A candidate the cap held back says so:
  `ranked below verification cap`, in the ledger and under `--explain`, kept apart from a
  candidate the ranking never reached (D-168).
- **Yellow (b)'s null/Optional class is off.** It produced no sentence on 79 units under two
  rule versions and cost one model call on every review; that call is now not made at all
  (D-169). Its sibling, exception propagation, still runs and still costs nothing, and is now a
  **shadow**: it writes to the ledger and reaches no comment.
- **Yellow (a) gained a fourth condition and it is the only one that has ever spoken.** A
  changed function with ≥ 3 call sites across ≥ 2 files that **no test names at all**: 1 of 11
  forward pairs, **2 of 68 null controls (2.9%)** against the owner's 3% ceiling — inside it by
  one event, and the 95% upper bound on that rate is 9% (D-170).
- **`attest stats --since 7d`** prints a period report — what spoke on how many reviews, why the
  silent candidates were silent, spend, image reuse — instead of running totals (D-171).

### Fixed

- The offline M-01 measurement probe imports a **snapshot of the HEAD commit tree**, not the
  working tree, and no longer refuses to run when `src` is dirty. It had broken two full-suite
  runs in the previous window alone.
- Every paid corpus driver reserves a unit's **maximum** cost against its cumulative cap before
  starting it. The old rule gated on money already spent and let a run end $0.62 above its own
  cap (D-172).

## v0.1.0-rc.1 — 2026-09-07 · **internal trial, not a public release**

Tagged so a colleague can install the exact bytes a ref names. **Not published to PyPI**, and
not `v0.1.0`: that still needs three product conditions that do not hold
([readiness](docs/acceptance/2026-09-06b-v01-tag-readiness.md)). The release workflow builds a
wheel and an sdist on the tag, refuses a tag whose version disagrees with the wheel it produced,
and attaches both to the GitHub Release.

### What a reader deciding whether to point a repository at this ref should know

- **Four times the budget buys nothing measurable.** The 17 commits whose candidates died with
  the budget gone were re-reviewed at `--budget 1.00` against `0.25`: spend `$1.64 → $10.32`,
  candidates `105 → 331`, **and not one verdict moved**. Candidates refused *for budget* went
  **up**, 40 → 44 — raising the budget raises discovery, and discovery re-starves the budget
  (D-166, [report](docs/acceptance/2026-09-07-budget-rerun.md)). The `$1.00` default stands as a
  ceiling for large changes, not as a recommendation.
- **A repository that cannot be reviewed is told so in one line, and exits 0** — no Python
  source, an unparsable lock file, no docker, or an image that cannot provide pytest (D-159).
  A repository with **no test suite is supported**: attest installs pytest and writes the test.
- **Interpreters are 3.10–3.13**, primary 3.12, chosen from `requires-python`, classifiers **or
  a lock file**. 3.9 is no longer offered, so a project that only installs on 3.9 now fails to
  bootstrap — a real reduction in what the held-out corpus can measure, and the price of a
  declared range (D-162).
- **A killed review no longer makes a repository unreviewable.** A journal torn between its last
  settlement and its finalization is sealed by a signed abort record, with every binding the
  finalization had; nothing already written is edited (D-155, closing D-154).
- **Yellow (b) has a second class and still says nothing.** Exception propagation — a new call
  that raises, and no caller that handles it — is free, deterministic, and 0 of 79 (D-164). The
  null/Optional class was re-measured with annotation-independent premises and is **still 0 of
  79** under two rule versions; it is written into the README's limitations and shelved (D-165).
- **Green tells the same duplicated pair once**, not on every pull request that touches either
  file, while both spans are unchanged (D-160).
- **New knobs:** `daily_budget_usd` (per repository, rolling 24 h, default off) and
  `repro_concurrency` (default 2; the journal's byte order is unchanged either way). A silence
  bought out by a ceiling now says how many candidates it stopped (D-161, D-157).
- **New surfaces:** `attest review --json`, `attest stats --json`, and a cost column in
  `--explain` (D-163). `docs/faq.md` explains every drawer reason; `docs/examples/` carries one
  real red, yellow and green comment verbatim.
- **The red-team matrix covers nine attack classes** (D-166 window): the four already dispatched
  plus the controller's key file, a symlink escape, DNS egress, a tampered sealed bundle and
  bounded process exhaustion. **The external-observer item stays INSUFFICIENT** and the recorded
  matrix says so: every row is observed from inside the product, which is evidence the boundary
  held for this attempt and not evidence the kernel denied it.

## Unreleased

The work since `v0.1.0-pilot.1` that predates the tag above.

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
- **The held-out slice, re-run under the probe generator** (2026-09-06c): **certified 4 of 28,
  0 false publications on 40 controls, and 28 of 28 environments built** against 10 of 29 before.
  The environment stopped being the wall and `attest.intent.v4.1` became it: **all four cases the
  old generator published and this one does not were lost to the value-class clause**, which is
  the largest number this project has on that clause's recall cost
  ([report](docs/acceptance/2026-09-06c-heldout-probe.md)).
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
