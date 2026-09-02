# Install ref and release note (L-01)

An outside repository installs attest from an **immutable ref**, never from a branch. A
branch name is not an install ref: `main` moves, and a pilot cannot say afterwards which code
produced a receipt.

## The current pilot ref

| | |
|---|---|
| ref | `v0.1.0-pilot.1` |
| kind | annotated tag; immutable |
| commit | resolve with `git rev-parse v0.1.0-pilot.1^{commit}`; the tag is annotated and never moved |
| package version | `attest 0.0.1` |
| interpreter | CPython 3.11 minimum, 3.12 primary (the Action pins 3.12.8) |
| isolation backend | `linux-container-v1` (Docker/OCI); production never falls back to the host |
| evidence schemas | run record, receipt, seal and bundle are versioned; an unknown version is rejected, never misread |

Install it exactly as [`quickstart.md`](quickstart.md) §1 does:

```bash
git clone https://github.com/IcantFind-a-username/Attest.git
cd Attest
git checkout v0.1.0-pilot.1
```

and pin the workflow the same way:

```yaml
- uses: IcantFind-a-username/Attest@v0.1.0-pilot.1
```

## What this ref is and is not

- it **is** the first ref intended for a private pilot on one authorized outside repository;
- it is **not** a public release. Publishing, the Marketplace listing, and enabling the
  Action for anyone outside the pilot cohort are separate owner actions;
- new-code findings are not supported at this ref: a candidate with no merge-base definition
  is a typed abstention and is never priced or published;
- the full red-team matrix for `G-SEC-002` on the CI platform is open; see
  [`support-matrix.md`](support-matrix.md).

## Rollback targets

The oldest ref a production pilot may roll back to is `v0.1.0-pilot.1`: earlier commits
predate one or more of the container backend, the controller seal and the offline verifier,
and [`kill-switch-and-rollback.md`](kill-switch-and-rollback.md) forbids a rollback that
lowers the trust bar. Until a second pilot ref exists, the rollback for a bad review is the
kill switch (`enabled = false` on the base branch), not a ref change.

## Changing the ref

A new pilot ref is cut when, and only when, the repository gates pass on a clean checkout and
the change is described here in one row. The ref is never moved; a new tag is created.
