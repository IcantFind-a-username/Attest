# Repository-disjoint candidate freeze and development exploration

Date: 2026-09-16 (Asia/Singapore). Owner-directed preparation, D-260.
Baseline: `58b3a6ca9c7bbc965004c7e74d207bce448c1d82`.
Branch: `chore/freeze-repository-holdout`; split frozen at
`a3e62f9206629d0656ece192e16307c568d4a41a`, before project-source exploration.

## Result and limits

Frozen **25 candidate historical defects across five repositories**: five development
candidates and 20 held-out candidates. Qualified defects: **0**. Qualified controls: **0**.
Product evaluations: **0**. This is evaluation preparation, with no new recall, precision,
FPR, or release-readiness result. The old forty remains development evidence.

| Role | Repository | BugsInPy IDs |
|---|---|---|
| Development | keras-team/keras | 8, 40, 30, 34, 11 |
| Held out | explosion/spaCy | 9, 2, 8, 1, 7 |
| Held out | ansible/ansible | 13, 6, 4, 14, 16 |
| Held out | jakubroztocil/httpie, now httpie/cli | 2, 1, 5, 4, 3 |
| Held out | nvbn/thefuck | 20, 21, 3, 10, 6 |

Selection follows the committed hash rule, not defect shape or Attest outcomes. Development
is 20% by both repositories and candidates. Exact buggy/fixed SHAs, metadata byte digests,
repository aliases and the pinned BugsInPy revision are in the
[immutable split](../../benchmarks/studies/repository-holdout-v1/frozen-candidates.json).
The 20 held-out candidates come from four repositories; they are not 20 independent
repositories or yet 20 independently qualified defects. Correlated fixes must be grouped
during later outcome-blind qualification.

## Exposure audit and visible corrections

The [protocol](../../benchmarks/studies/repository-holdout-v1/protocol.md) was committed
at `511b2d0`. Its first, mention-only audit excluded all 17 projects because the historical
manifest lists administrative exclusions for every project. That
[initial audit](../../benchmarks/studies/repository-holdout-v1/exposure-audit-initial.json)
is preserved. Amendment `3068cc1`, committed before selection/source access, distinguishes
pre-patch metadata/licensing exclusions from substantive development exposure. Unknown
exposure still excludes a repository.

**Erratum to the classified audit:** its original interpretation says, “Historical
_import_candidate performs listed metadata/licensing checks before opening patch/oracle
files.” This is too broad for `missing_regression_test`, which the historical importer
also raises after reading patch/test bytes. The original classification of unselected
`tqdm` as `administrative-only-in-declared-audit` is therefore unsupported. It is now
unknown/excluded in the [append-only correction](../../benchmarks/studies/repository-holdout-v1/audit-erratum.json).
The original audit is preserved. Recomputing selection after this correction leaves all
five repositories, roles and 25 IDs unchanged. The selected five have no such ambiguous
exclusion reason. This finding was reproduced from the pinned historical importer.

The audit covers declared baseline documents, benchmark/script records and clone origins;
no substantive development exposure was found for the selected repositories in that scope.
It cannot establish absence of undocumented human/model exposure or pretraining. Old
licensing metadata may have been inspected. Renamed repositories share an assignment.

## Small development exploration

After the freeze, only Keras was cloned for project-source access, without checkout, and
the fixed revision of `keras/8`, `d78c982b326adeed6ac25200dc6892ff8f518ca6`, was fetched.
Read-only `git show` inspected package setup, pytest configuration, the first 150 lines of
the declared test file and the package initializer. Exact paths/digests and visible ranges
are in [development-access.json](../../benchmarks/studies/repository-holdout-v1/development-access.json).
No project code was installed, imported or executed. No held-out project source, gold
patch, oracle script or bug report was read in this task.

Observed compatibility questions, not measured Attest failures:

- The revision identifies Keras 2.2.4 and numerical/backend dependencies. BugsInPy records
  Python 3.7.3; setup metadata describes older supported Python versions. Reproducible
  backend and interpreter qualification remains necessary.
- `pytest.ini` requests `-n 2` via pytest-xdist. Runtime observation needs explicit
  qualification of worker identity and collection; single-process assumptions cannot be
  inferred from this configuration. No runner settings were changed or tested.
- The sampled tests construct layers/models, mutate their state and compare collections
  or backend-dependent values. They expose useful development questions about receiver
  state and structured expectations. Static inspection does not establish whether an
  individual defect is discoverable or certifiable by Attest.

Only one selected development revision was explored. All Keras candidates stay development;
none may later be presented as held-out. Freeze-time `source_read:false` fields remain
historical facts, with subsequent access recorded separately.

## Verification and next boundary

One [independent review](../../benchmarks/studies/repository-holdout-v1/independent-review.md)
verified protocol/canonical hashes, all 25 candidate metadata hashes and revision strings,
17 project metadata hashes, 783 normalized baseline document digests, aliases and selection.
Its single P2 is corrected above. Upstream existence/ancestry of held-out revision objects
was not verified; exact metadata identifiers do not establish executability.

Final data checks verify immutable files, corrected selection, role/alias separation,
unique candidate revision pairs, local evidence links and absence of changes to product
code/tests/scripts. Commands and artifact hashes are in
[validation.json](../../benchmarks/studies/repository-holdout-v1/validation.json).
Full pytest, Ruff and Mypy were not rerun for this data/document-only preparation, as
specified by its protocol. No prior product gate is presented as a current gate.

Next, qualify development environments and freeze a product-blind defect/control protocol
before independent evaluation. Faithful oracles, semantic labels, license/adapter support,
at least as many qualified reasonable-change controls as defects, version/budget and
failure/abstention denominators must be fixed before held-out dispatch. Do not replace
unsuccessful cases after observing product outcomes. Paid dispatch requires separate opt-in.

Attest model/API spend **$0**. Remote activity was read-only Git/GitHub metadata retrieval;
no push, PR, publication or third-party write. Product code, intent defaults, certification
authority and release gates are unchanged. Finite silent controls would not establish a
universal zero-false-positive guarantee.
