# Repository-disjoint candidate pool, frozen before exploration

Owner approval: “做” following the proposal to explore a small development population and
freeze previously unused repositories for later independent evaluation. Baseline Attest:
`58b3a6ca9c7bbc965004c7e74d207bce448c1d82`. Local preparation only; API/model budget $0,
no remote writes, product changes, default changes, or evaluation dispatch.

## Permitted sources and access

Use the already approved BugsInPy corpus at
`https://github.com/reproducing-research-projects/BugsInPy.git`, pinned to the existing
recorded corpus revision `316b95e2353ecda832bad9b42f86fa7c2fcec8ac`.
Acquire it without checkout under `.attest/corpora/repository-holdout-v1-metadata/`.
Before freezing, read only project names, `project.info`, bug IDs and selected `bug.info`
revision metadata. Do not read gold patches, oracle scripts, test contents or bug reports.
No owner's other local project directory may be accessed.

Audit prior exposure against the baseline's tracked docs, benchmarks and scripts and the
existing corpus clone metadata. Repository aliases and prior instance splits count as
exposure. A mention is conservatively enough to exclude a project, even when it may only
be a dependency. An audit finding means recorded exposure; absence means no exposure found
in the declared scope, not proof of no prior human/model knowledge.

## Selection and immutable split

Take five eligible repositories, ordered by SHA-256 of
`attest-repository-holdout-v1|` plus the lower-case upstream repository slug. First is
development, remaining four are held out. Require at least five BugInPy IDs per repository;
freeze the first five IDs in the same hash order with project and ID appended to the seed.
This gives 20% development by repositories and candidate instances. If fewer than five
repositories survive the audit, retain the shortfall and do not silently replace the pool.
Record source URL, corpus commit, project ID, candidate bug IDs, metadata hashes and exact
buggy/fixed SHAs. Do not choose by defect type, product outcome or supported test shape.

Commit the split before any project-source exploration. Never move an explored repository
back into held-out; aliases/forks and all its instances follow repository-level assignment.
Keep the split append-only. Future mistakes use a visible invalidation/new version, never
an in-place edit that conceals exposure. Unexpected access or study outcomes are logged.

## Development exploration and future evaluation

After the split commit, clone only the development repository under this study's gitignored
corpus directory, at the first selected candidate's fixed SHA. Read package/test setup and
a small source sample; execute neither project code nor model calls. Report compatibility
observations only, not recall/precision or a product trial. Held-out project source is not
cloned/read/run in this round.

These are candidate historical defects, not qualified evaluation cases. Their oracles,
faithful base/head construction, semantic labels, independence and environments remain
unverified. No reasonable-change controls have been qualified by this selection. Before
the one held-out run: freeze an outcome-blind instance/control protocol with at least as
many qualified controls as defects, immutable product/version/budget, independent truth
adjudication, and full failure/abstention reporting. Paid dispatch requires separate opt-in.
Do not claim a zero-FPR guarantee from a finite control population.

## Deliverable

An immutable split plus exposure audit and a concise read-only exploration report, checked
for overlap, valid metadata, exact revisions and no held-out source access. No production
implementation or full product test rerun is required for this data/document preparation.
One bounded independent review verifies the split and claim limits before completion.
