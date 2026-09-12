# Install ref and release note (L-01)

An outside repository installs attest from an **immutable ref**, never from a branch. A
branch name is not an install ref: `main` moves, and a pilot cannot say afterwards which code
produced a receipt.

## The current pilot ref

| | |
|---|---|
| ref | **`v0.2.0`** (2026-09-13) · `v0.1.0`, `v0.1.0-rc.2`, `v0.1.0-rc.1`, `v0.1.0-pilot.1` (previous, never moved) |
| kind | annotated tag; immutable |
| commit | resolve with `git rev-parse v0.2.0^{commit}`. Every tag here is annotated and **none is ever moved** |
| package version | wheel metadata `0.2.0`, and `attest.__version__` reads the installed metadata rather than a second hand-written literal, so the `0.1.0rc1`/`0.1.0rc2` disagreement `v0.1.0-rc.2` shipped cannot recur. **`pyproject.toml` is the one hand-written place** |
| interpreter | CPython 3.11 minimum, 3.12 primary (the Action pins 3.12.8); the **reproduction** image is built on 3.10–3.13 and a project declaring outside that range is refused by name (D-186) |
| isolation backend | `linux-container-v1` (Docker/OCI); production never falls back to the host |
| evidence schemas | run record, receipt, seal and bundle are versioned; an unknown version is rejected, never misread |

Install it exactly as [`quickstart.md`](quickstart.md) §1 does:

```bash
git clone https://github.com/IcantFind-a-username/Attest.git
cd Attest
git checkout v0.2.0
```

and pin the workflow the same way:

```yaml
- uses: IcantFind-a-username/Attest@v0.2.0
```

### What `v0.2.0` changes over `v0.1.0`

**Three evidence-side rules and two more populations; no constant moved.** `alpha`, every
likelihood ratio, `k_samples`, the hard cap, `budget-usd` and the supported interpreter range are
unchanged.

- **A new rejection is a frame on the exception's path, not a statement (D-232,
  `attest.intent.v5`).** An escaped exception whose path through the anchored file crosses a line
  the change wrote is a behaviour change with unknown intent, whatever raised it; red keeps the
  merge-base-raised-head-does-not shape and a crash off every written line. Both `attrs#1603`
  receipts of the first batch moved to the drawer; both held-out receipts stayed.
- **A return-annotation-only change is not a yellow (a) claim (D-233); a container value on the
  yellow line names the first element that moved (D-234, `attest.value-note.v3`).**
- **Two more populations measured**: twenty merged pull requests of five libraries the free probe
  kept, and forty injected forward defects with the first non-reversed recall figure.
- **The README's adjudicated numbers are generated** from the reports' own columns
  (`docs/receipts.md`).

### What `v0.1.0` changes over `v0.1.0-rc.2`

**One constant-free behaviour change and a great deal of measurement.** `alpha`, every
likelihood ratio, `k_samples`, the hard cap, `budget-usd` and the supported interpreter range are
unchanged.

- **The `m_u/α` score bar is removed (D-199).** A finding whose certification is accepted and
  whose verification is reproduced publishes subject to same-defect clustering and the hard cap
  of three alone. Replayed over every recorded ledger that is **+25 published, −0 withdrawn**.
  **What it costs in trust:** the per-unit multiplicity cap goes with it — a row now records
  `pr_error_bound: 1.0` and `e_value_validity: "not-applied"`, because with no threshold there is
  no rejection rule for a union bound to be taken over. **The product offers the receipt and
  nothing statistical.**
- **Every author-visible line is adjudicated (D-201, D-204).** An ordinary deferral gets a
  contract line instead of bare `DEFER:` prose, and the **whole summary body** is checked rather
  than the lines inside it.
- **The red-team matrix dispatches all thirteen preregistered attack classes** (D-200), up from
  nine: `/proc`, home/git, native syscall and namespace were added.
- **`G-SHADOW-001` passes** under the bar of mainline condition 5 (D-205), on 28 pull requests
  with 13 reproductions that actually executed and 0 publications.

### What `v0.1.0-rc.2` changed over `v0.1.0-rc.1`

Copy and denominators, not capability. **No constant moved** — `alpha`, the likelihood ratios,
`k_samples`, the hard cap, `budget-usd` and the supported interpreter range are the same.

- **D-190** — seven refusals (`no docker`, `no pytest`, the interpreter range, an image that
  will not build, a truncated discovery, and the two decided from the tree) now reach the one
  line a pull-request author reads, as a contract line carrying the refusal's name, one sentence
  of fact and a link to the run whose artifact holds the ledger. Before this they reached the
  ledger and a collapsed block only. See [`failure-modes.md`](failure-modes.md).
- **D-186** — a project the reproduction interpreter cannot collect is refused by name instead
  of surfacing as `missing or malformed JUnit evidence`.
- **D-187** — a review whose discovery the budget ceiling actually cut off names the unit, the
  shortfall and the `budget-usd` that would have covered it.
- **D-189** — a note in the delivery journal no longer blocks the next review of that repository.

**The held-out number is worse at this ref than the one published beside rc.1, and the product
did not get worse**: D-186 removed nine unreviewable cases from a denominator of sixteen, so the
crash class reads **certified 2 of 7 eligible-and-supported** rather than 4 of 16, and two of
those four receipts came from a `pytest` tree this ref can no longer run
([report](../acceptance/2026-09-11-heldout-after-d186.md)).

## What this ref is and is not

- it **is** the first ref intended for a private pilot on one authorized outside repository;
- it is **not** a public release. Publishing, the Marketplace listing, and enabling the
  Action for anyone outside the pilot cohort are separate owner actions;
- new-code findings are not supported at this ref: a candidate with no merge-base definition
  is a typed abstention and is never priced or published;
- the full red-team matrix for `G-SEC-002` on the CI platform is open; see
  [`support-matrix.md`](support-matrix.md).

## Rollback targets

`v0.1.0` is the first ref intended for an outside repository to install. `v0.1.0-rc.2` and
`v0.1.0-rc.1` were **internal trial refs, not public releases**: each is tagged so a colleague can install the exact bytes a name points at, nothing is published to PyPI and nothing is listed on the GitHub Marketplace, and three of the seven `v0.1` conditions still fail ([read](../acceptance/2026-09-07-v01-tag-readiness.md)). `v0.1.0-rc.1` is the rollback target for `v0.1.0-rc.2`: it lowers no trust bar, because rc.2 adds refusals and moves no constant.

The oldest ref a production pilot may roll back to is `v0.1.0-pilot.1`: earlier commits
predate one or more of the container backend, the controller seal and the offline verifier,
and [`kill-switch-and-rollback.md`](kill-switch-and-rollback.md) forbids a rollback that
lowers the trust bar. Until a second pilot ref exists, the rollback for a bad review is the
kill switch (`enabled = false` on the base branch), not a ref change.

## Changing the ref

A new pilot ref is cut when, and only when, the repository gates pass on a clean checkout and
the change is described here in one row. The ref is never moved; a new tag is created.
