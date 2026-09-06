# Backlog

- **[P0] 2026-09-04 (D-127), the longest-standing open owner item.** An intended change of a returned *value* is invisible to every discriminator the product owns, and it published on a properly qualified null control (`jinja` `ac3ac6c9`: the commit takes `__name__` from the async function on purpose and says so in its own comment; the generated test asserts the sync name). D-102's intent rule covers a `raise`/`assert` in changed lines only, and the receipt records its silence verbatim — `new_rejection: false`, `exception_type: ""`, `witnesses: []`. Three shapes, none touching alpha, the LR, K or the cap: (a) extend the intent policy from new rejections to any changed-line-bound behavioural difference, requiring a base-tree witness exactly as D-102 does; (b) publish only when the head failure is a crash rather than a value mismatch; (c) require the claim's prose and the test's failing assertion to agree before publication. (c) also fixes the separate defect in the same receipt: the published sentence said `__wrapped__` pointed at the wrong function, the test asserted the opposite and *passed* that assertion, and nothing checks that the two agree. **§16 owner decision; `G-NULL-001a` cannot be resumed and mainline condition 4 cannot move until one lands.**

- **[P1 → DONE 2026-09-08] 2026-09-04, reproducing the 2026-09-02 item, hit twice again on 2026-09-07, and now fixed.** The probe imported `src` from the **working tree** and refused to run when `git status` showed that tree dirty, so any edit or concurrent write beside a full-suite run failed the probe rather than the edit — four consecutive windows, two whole-suite runs lost in the last one. It now materialises the **HEAD commit tree** with `git archive` (or a directory pinned with `--source-snapshot`) and imports that; the clean-tree guard is gone and `source_tree_sha256` is a digest of the snapshot actually imported. Two REDs in `tests/benchmark/test_m01_offline_measurement_probe.py`: a detached worktree whose `src` carries an uncommitted edit produces the same measurement and the same digest as the clean bundle, and an explicit snapshot is what gets measured. **The separate-worktree practice is no longer needed for this reason**, though it remains sound for others.

- **[P2] 2026-09-04.** `G-NULL-001a`'s control definition (D-122) is applied to *every* changed text file, so a commit that also edited a changelog is disqualified the moment that changelog is rewritten or deleted — which every one of the eight public clones has done. Measured qualification rate: **58 of 903 (6.4%)**, `click` 3 of 120. Restricting the untouched check to the files a review can anchor in (Python) would raise the yield sharply without loosening what "untouched" means for the reviewed code. A change to D-122, not to the study.

Findings that did not earn a fix, one line each: `file:line — what, and why it
was not fixed now`.

Per D-049, a self-review defect earns a commit only when it can be reproduced.
Everything else lands here: unreproduced "could in principle" hardening, and
every finding from a second review round. Nothing here is a promise to act —
this is the drawer, and items leave it only when a task is scoped to them or a
reproduction turns one into a real defect.

**Priorities**, added 2026-09-07 in a triage pass over every item: **[P0]** blocks a gate or a
release condition; **[P1]** has recurred and costs operator time every window; **[P2]** would
raise a measurement's yield; unlabelled items are records, not intentions. `DONE` items are kept
rather than deleted — a backlog whose closed items vanish cannot be audited.

<!-- entries below, newest first -->

- **[P2] 2026-09-08: `evaluate_project` reconstructs a `ReviewConfig` field by field, and will
  silently drop the next policy key too.** `src/attest/benchmark/api.py` lists eight of the
  fourteen fields; `context_strategy`, `generation_model`, `gate_shadow`, `repro_concurrency`
  and `daily_budget_usd` are reset to their defaults whatever the caller set, and
  `verification_cap_per_unit` was too until D-168 added a ninth line. A benchmark that resets a
  policy key reports a measurement of a policy nobody asked for, which is what the comment above
  `probe_generation` already says. `dataclasses.replace(request.config)` after
  `validate_review_config` would be exact and future-proof; it also carries `gate_shadow`, which
  is a behaviour change the reconstruction may have been deliberately preventing. Small, and
  worth doing on purpose rather than after the next key goes missing.

- **[P1] 2026-09-08 (D-168): at the shipped `k_samples = 5` the 30% discovery share can refuse
  a review its first change unit.** The ceiling is checked against the *preflight reservation*,
  which prices K samples at the 3,200-token output bound and overstates a real proposal by about
  **3×** ($3.1538 reserved against $1.0671 actually spent, over the 17 commits). At K=4, 0 of 28
  recorded reviews are refused. At K=5, **one is** — `click cd4674a6`, first unit 47,448 chars,
  reservation $0.3182 against a $0.30 ceiling — and it is one of the three reviews that has ever
  published a receipt. It would defer with a stated budget reason, which is a contract line, but
  it would publish nothing. `k_samples = 4` or `budget_usd >= 1.06` removes it; either is a
  policy change, so it is the owner's. A third shape, not costed: reserve at a measured
  percentile of real proposal output rather than at the token bound, which weakens the hard-budget
  guarantee and is therefore not proposed lightly.

- **[P2] 2026-09-08 (D-170): yellow (a)'s a4 meets the 3% control ceiling by one event.** 2 of 68
  is 2.9%; 3 of 68 would be 4.4% and would fail. The 95% Clopper-Pearson upper bound on the true
  rate is **9.0%**, so what n=68 establishes is that the rate is not large, not that it is under
  3%. Both firings are literally true statements about commits nobody had to fix. Either a larger
  control population or a tighter threshold (4 callers, 3 files) would settle it; neither is free
  of the other's cost, and a4 is currently the **only** condition of this level that has ever
  spoken.

- 2026-09-03 (real-traffic corpus, m/alpha): the family threshold is `m/alpha = 10m`, and on real traffic **m is not small**. Across 43 reviews the eligible-candidate counts were `0×19, 1×4, 2×2, 3×4, 4×2, 5×3, 7, 8×4, 9×2, 10, 14` — of the 24 reviews with any eligible candidate, **median m = 4.5, mean 5.2, max 14**, and 18 of 43 reviews had m ≥ 3, i.e. a publication bar of 30 or more. Six certified receipts were suppressed as "below family threshold" this window, against seven published; on `d05` all five certified receipts were suppressed at m = 7 (threshold 70) and on `d16` at m = 9 (threshold 90). The e-value a single reproduction can earn is bounded by the LR the kernel buys, so **a large PR is close to unpublishable by construction, and the product is silent exactly where a reviewer is most useful.** Three shapes worth pricing, none of them a change to alpha, the LR, K or the cap: (a) define the family per *change unit* rather than per pull request, so m is the count of eligible candidates competing inside one file/unit; (b) let a candidate that clears an absolute evidence bar publish regardless of m, with the multiplicity correction reported rather than enforced; (c) report suppressed-but-certified receipts to the author in a collapsed section that is explicitly not a finding. All three move the publication surface and are §16 owner decisions; (a) is the only one that keeps a family-wise guarantee.

- **DONE 2026-09-04.** 2026-09-03 (real-traffic corpus, `Corum`): **numpy cannot be imported inside `linux-container-v1`**, so every candidate in a numpy-dependent project DEFERs at the collection gate. `sitecustomize`'s thread cap makes OpenBLAS's `pthread_create` fail for 12 threads (`blas_thread_init: Resource temporarily unavailable`) and the import dies at 0.72 s — not a timeout, and not the generated test's fault. All four `Corum` defect pairs were lost this way. The cheap mitigation is `OPENBLAS_NUM_THREADS=1` (and the `OMP`/`MKL` equivalents) in the executor's environment template, which narrows nothing an attacker can use; it is an isolation-profile change and therefore a §16 owner decision, deliberately not made inside a measurement window. **Made on 2026-09-04**: `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` and the `MKL` equivalent are pinned to `1` in the executor's environment template (`executor.py:1305`), and `Corum` went 0 of 4 to 4 of 4.

- 2026-09-03 (D-120): bumping `INTENT_POLICY_VERSION` makes **every receipt issued before the bump stop verifying offline** — `attest verify` on the `d7be758` bundle now answers `rejected: … unknown intent policy`. The project has accepted this trade twice (receipt schema v3 → v4, INV-VERSION-001), but the product's headline claim is that an author-visible finding carries a *verifiable* receipt, and that claim decays with every policy bump. A verifier that keeps a registry of retired intent policies and re-judges a bundle under the policy it names — refusing only when the named policy is unknown to *any* version — would keep old receipts verifiable without letting a retired policy authorise a new publication. **Built on 2026-09-04 (D-121)** as an owner decision: `POLICY_FIELDS` is the registry, the digest is scoped to the recorded version's fields, D-120's constant rule is not applied to a v1 observation, and an unknown version still fails closed. All 17 v1 bundles on this host verify again.

- 2026-09-03 (D-113): the reproduction generator is shown the nearest test module's helpers (D-089) but is never told the generated file must be self-contained; opus-5 wrote `from test_matcher import _prediction, _truth`, which cannot resolve from `.attest-repro/`, and sonnet-5 wrote no imports at all. Both DEFERred. The fix is one sentence in the generation prompt plus a check that the file imports only from the project's own packages — a product change, deliberately not made in the measurement window.
- 2026-09-03 (window-end gate): `tests/benchmark/test_cli.py::test_replay_with_a_prepared_root_runs_the_real_product_path` reaches `ensure_image` and spawns a real `docker build`. On a host whose daemon cannot pull a base image it hangs indefinitely rather than failing, and under `--cov` it failed with the CLI subprocess exiting 1. A test named for the *replay* path should not depend on a registry; either it should pin the backend it wants, or the replay path should not select a container backend at all.

- **DONE 2026-09-03 (D-110).** `IMAGE_BUILD_TIMEOUT_S = 1800` in `src/attest/execution/container_images.py` is three times the deadline it runs under — `verification.py:86` sets `deadline = started + verification_timeout_s`, whose default is 600 s at every entry point, and `select_backend` is called at `:101`, *before* the first deadline check at `:163`. A build of 601–1800 s therefore "succeeds" and then every candidate DEFERs with `shared verification deadline exceeded after 600s`: 10–30 minutes of runner time bought nothing and the operator reads the wrong category. The fix is to pass the remaining verification budget into `ensure_image` and cap the build at `min(IMAGE_BUILD_TIMEOUT_S, remaining_s)`. Not done in this pass: the owner's instruction for this window was not to raise the 1800 s cap, and lowering it is a backend-policy change (§16).
- **DONE 2026-09-07.** 2026-09-03 (D-105 review of `9df938f`, finding 7): `status.py:123` bounds a reproduction reason to 200 characters and `verification.py:150` spends 87 of them on the fixed prefix `isolation backend unavailable: `, so the 1200-character build-log tail both bootstrap branches now attach renders as ~110 characters. `failure-modes.md:16` tells the operator to read the tail in the status; ~9 % of it arrives. Either raise the limit for this category or shorten the tail so the code stops implying more than is shown. **Fixed**: `BOOTSTRAP_REASON_LIMIT = 1400` for that one category, `REASON_LIMIT = 200` for every other, with a RED in `tests/test_status.py`.
- 2026-09-03 (D-105 review of `9df938f`, finding 8): the rendered bootstrap status says `environment bootstrap failed` twice — once as the category from `status.py:45` and once inside the reason — behind an `isolation backend unavailable: ` prefix that belongs to a different `failure-modes.md` row. Cosmetic; the documented literal is present, so the contract holds.
- 2026-09-03 (D-105 review of `9df938f`, finding 10): whether the daemon-side build continues after `subprocess.run` kills the docker client on timeout is builder-dependent (the classic builder continues, BuildKit cancels the session) and was not exercised. If it continues, a timed-out review leaves the daemon building against a context directory that has already been removed.
- 2026-09-03 (D-105 review of `9df938f`, finding 11): `tests/execution/test_linux_isolation.py` calls `ensure_image` directly (`:58`) and is the change-impact row (§12) for executor/reproduction changes; it was not run for `9df938f` in the window that made that change.
- **DONE 2026-09-03 (D-110).** on the operator's host `docker image inspect <name:tag>` failed for every existing `attest-repro:*` tag for several minutes while `docker images` listed them and inspect *by image id* resolved them, then began answering normally with no intervention. `image_digest` reads that as "image absent" and rebuilds — safe, but it is how a 30-minute rebuild of an image that already existed came to be started at all. There is no way for the probe to tell "docker says no" from "docker could not answer"; distinguishing them would need a second probe (e.g. `docker images -q`) and an owner decision about failing closed on an unreachable daemon.

- `src/attest/review/history.py:1` — call-graph reachability and test-blind-spot slices were
  intentionally excluded from the first F-channel scope; either slice needs an independently
  preregistered owner work order before implementation or measurement.
- `src/attest/review/executor.py:52` — the process audit spans trusted pytest bootstrap and
  reviewed code: exact replays for `01dd26db09` and `ffe9efc79f` first marked Python 3.8
  `platform.uname()` invoking `uname -p`, not Black behavior. Separating attribution without
  weakening containment requires an owner decision and likely the X-02/X-03 execution-profile
  boundary; no allowlist, activation-timing change, or runner-policy change was retained.
- `src/attest/review/ledger.py:80` — shared `ci_final` validation preserves `ValueError`
  behavior but changed several message strings; no repository caller depends on them, and
  the later-round compatibility concern is deferred under D-049 rather than opening another
  repair loop.
- 2026-09-02 (C-03 gate): `tests/benchmark/test_m01_offline_measurement_probe.py` — three module-fixture errors (`source import or clean-tree guard failed`) only when the whole suite runs from the repository root; the file passes alone, inside `tests/benchmark`, and with `--cov=src/attest`. The C-04 full run (`71b99aa`), executed with no other pytest process alive, passed all of them; the two earlier runs overlapped concurrent pytest invocations in the same checkout, so concurrent runs are the leading suspect. Keep full-suite gates exclusive.
- 2026-09-02 (R-01 trial): with planner context 3 of 20 proposal samples stopped at the 2,400-token output bound (2 of 20 without context); the truncated samples are voided whole. If the E-02 pilot table shows parse/truncation as the largest candidates→eligible loss, R-02 pulls forward per `mainline.md` §2; otherwise consider a per-unit bound that scales with context length under D-051.
- 2026-09-02 (E-02 pilot): pytest's own repository is runner-is-subject — the reviewed pytest becomes the test runner from the tree, so the interpreter must satisfy the *reviewed* pytest (no `imp` on 3.12) and generated files (`_pytest/_version.py`) must be committed; an executor profile that pins the runner separately (X-01/X-02) would remove this coupling.
- 2026-09-02 (E-02 pilot): on CPython 3.8 `platform.system()` shells out to `uname -p` and trips the process guard at collection for any project that reads `platform` at import (requests, pylint); 3.9+ computes it lazily. Same root as D-057; the controlled-subprocess profile (X-03) is the owner-gated fix, the pilot pins 3.9+ meanwhile.
- 2026-09-02 (E-02 pilot): with planner context 10/32 proposal samples stopped at 2,400 output tokens, two cases losing all four samples; the generator returned `{}` twice on two cases. Both are precommitted-recovery (R-02) shapes; measure them on the dev-slice re-run before touching D-051/D-056 bounds.

## 2026-09-05 (D-132/D-133 window)

- **`attest.intent.v4` clause (c) matches a symbol name as a word.** Common names —
  `readings`, `decision`, `snapshot`, `_reason`, `main` — match prose about something else, so
  an unknown fraction of the 42 intent-evidence hits in the corpus replay is false. Candidate
  narrowings: a minimum distinctiveness test on the symbol (as clause (b) applies to values), a
  dictionary-word exclusion, or requiring the mention to be in code-formatting/backticks. Moves
  what publishes, so it is the owner's.
- **Clause (b) is dead weight on the current corpus.** Once (a) restricts the pinned set to the
  failing assertion, the set is empty long before genericity is asked; (b) fires on 2 of 48
  receipts and on 0 of the ones v3 certified. Keep it (it is cheap and it is the rule that would
  have stopped `urllib3` under v3's set), but do not describe it as load-bearing.
- **The value class certifies 0 on the whole corpus under v4.** Nothing here says which of the
  12 v3 survivors were real defects. A recall study — adjudicating the 48 by hand — is the
  measurement that would tell whether v4 is right or merely silent.
- **`describe`'s coordinate rule has never fired.** 20 model calls, 0 refusals for it. It is a
  guard, not a measured fix, and should be re-measured on a different model or a harder prompt.
- **The wording adjudicator's denylist is a denylist**, English and Chinese. A hedge phrased
  outside the list passes.

## Forward-pair generation: observe the base before asserting — **DONE 2026-09-06 (D-146)**

*Recorded 2026-09-06 from the classification of D-140's 20 unfaithful reproductions
([report](acceptance/2026-09-06-forward-pair-generation-failures.md)); the owner's conditional
backlog item — "if the environment class dominates, match interpreter and dependency versions to
the commit's era" — **does not fire**: the environment class is **0 of 20**.*

What the data says instead: **18 of the 20** generated tests assert a behaviour the base
revision does not have either — 11 fail *identically* on both sides (the claim's premise about
base was simply false) and 7 encode a contract that postdates the base entirely. The proposer
sees a forward diff and head-side context; the base's actual behaviour is in neither.

The cheap experiment this suggested is **implemented as of 2026-09-06 (D-146)** and went
further than "quote its observed output": the model no longer writes an assertion at all. It
chooses one call; the merge base is executed twice to record what that call does; the kernel
writes the assertion from the recording. `fails on base as well` is structurally impossible on
that path. It was measured before and after on **the same 11 pairs**, as this item required
([report](acceptance/2026-09-06b-forward-pairs-probe.md)), and the legacy generator remains
available as `probe_generation = false`.

Era-matched interpreters and pinned dependencies remain worth doing for a different, smaller
population: the **4** candidates that DEFERred at `isolation backend unavailable` (the `attrs`
and `packaging` pairs, Python 3.13 and 3.9 image bootstraps) or `collection deferred`. That is
an image-build fix, not a generation fix, and it would have changed none of the 20.


## 2026-09-07 (this window's triage)

- **[P2] The propagation level's callee resolution is by bare name.** D-164 measured 0 of 79,
  and **43 of 198** changed functions voided because the callee's name is defined more than once
  in the tree. Resolving by import would make most of those decidable. 43 of 198 is a reason to
  consider it; it is **not** evidence that the answers would be right, and it is a real piece of
  work, so it is here rather than done.
- **[P2 → DONE 2026-09-08] Yellow (b)'s null/Optional class costs a model call on every review
  and has produced 0 sentences on 79 units under two rule versions** (D-151, D-165). Closed by
  owner decision 2 of 2026-09-07 (D-169): `NULLABILITY_ENABLED = False`, and the guard returns
  before the tree read and the model call, so the class costs $0.00 rather than a little less.
  The module, the premises and the REDs remain; one flag reopens it.
- **[DONE 2026-09-08] `us-stock-helper`'s half of the 1.1 re-run exceeded its cumulative cap by
  $0.62.** The driver's `--cap` gated *starting* a unit on money already spent, not on what the
  unit might cost, so a unit that began at $3.25 against a $3.50 cap ended the run at $4.12. Every
  driver now reserves the per-review `--budget` before a unit starts and settles it afterwards
  (`scripts/corpus/driver_budget.py`, D-172). Replayed on the recorded run: four units start
  instead of six, the run ends at $2.6486, and the two it refused are named in the log.
- **The `[gate]` level has never had an author-visible line**, by construction (D-137), and its
  cumulative shadow is now graded three ways (`through_caller`, `through_test_caller`, `direct`).
  Nothing to do until `G-NEWCODE-001` gets an owner decision on its LR.
- **A single-root project whose `pip install` fails for any reason fails the whole image**, where
  a nested project's failure is `|| echo "attest: optional project … failed to install"`. D-176
  fixed the one cause that was actually a defect on our side (`hatch-vcs`); the asymmetry itself
  is deliberate — the root's import roots are what the reproduction needs — but the operator
  meets it as *every candidate unreviewable* with only a build log tail to read. Worth measuring
  how often a public repository hits it before deciding whether the root should be best-effort
  too. Found by the 2026-09-09 release-readiness acceptance.
- **The `attest ci` DEFER for an unavailable executor names the reason but no next step.** The
  local CLI maps it to the fixed `[silent] unsupported: docker is not available here …` line;
  the pull-request comment says `DEFER: verification deferred: isolation backend unavailable:
  docker not found`, which is true and offers nothing to do. The three *silent* verdicts were
  fixed by D-177; this is the DEFER path beside them.
- **`_RATE_LIMIT_MARKERS` matches the bare substring `429`** (D-179). Guarded by requiring
  *every* sample error to match, so a stray line number cannot flip a whole review, but it is a
  substring test over model error text and it is the same class of defect D-174 spent a window
  removing from four other places. A structured provider error would decide it properly.
- **A `check_comment` refusal is discarded** (2026-09-09 review, finding 7). The verdict carries
  a reason and an `actionless` category and nothing records either, so a green or yellow note
  dropped for format leaves no trace an operator could find — unlike the structural notes, which
  get a ledger row each. One `ledger.append` at the four gated builders would close it.
