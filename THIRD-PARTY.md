# Third-party licences

Attest is Apache-2.0 (see `LICENSE`, `NOTICE`). This file is the standing manifest required
by the licence iron rule in `AGENTS.md` §8 and D-068.

## The rule, in one line

Survey open source before building; integrate what may lawfully be integrated; **never adopt
anything whose licence forbids the use.** Copyleft triggers on **distribution, not profit** —
publishing publicly is distribution.

## Allowlist

`MIT` · `BSD-2-Clause` · `BSD-3-Clause` · `Apache-2.0` · `ISC` · `PSF-2.0` ·
`MPL-2.0` (library use only)

## Denylist

Any `*GPL*` (GPL, LGPL, AGPL) · `BSL` · `SSPL` · any non-commercial or field-of-use
restriction · any proprietary licence · **any unknown licence**.

Unknown **fails closed**. A person resolves it and the resolution is recorded in the table
below with its evidence.

## Current dependencies

Measured 2026-09-02. Runtime dependencies are declared in `pyproject.toml`.

| Package | Role | Licence | Note |
|---|---|---|---|
| `numpy` | runtime | BSD-3-Clause | Metadata carries a licence *file* rather than an SPDX identifier, so a mechanical gate reports it as unknown. Resolved by inspection; the gate must keep flagging it rather than guess. |
| `anthropic` | runtime | MIT | |
| `pytest` | runtime | MIT | |
| `pytest-cov` | dev | MIT | |
| `ruff` | dev | MIT | |
| `mypy` | dev | MIT | |
| `pathspec` | transitive (dev) | MPL-2.0 | File-level weak copyleft. Library use imposes nothing on an Apache-2.0 work; only modifications to its own files would carry MPL terms. |

Across the installed environment as measured: 20 MIT, 3 BSD-3-Clause, 2 Apache-2.0,
1 BSD-2-Clause, 1 MPL-2.0, 1 PSF-2.0, **0 GPL/AGPL**.

## Rejected, with reasons

Recorded so the same evaluation is not repeated.

| Candidate | Purpose | Licence | Decision |
|---|---|---|---|
| **METIS** | graph partitioning | University of Minnesota, **non-commercial restriction** | **Rejected.** A field-of-use restriction is incompatible with Apache-2.0 and would make the project not open source by OSI definition. |
| **igraph** | graph partitioning / community detection | GPL-2.0 | **Rejected.** Infectious under distribution. |
| **leidenalg** | community detection | GPL-3.0 | **Rejected.** Infectious under distribution. |

Permissive replacements covering the same ground with no capability loss: `networkx`
(BSD-3-Clause), `scipy` and `scikit-learn` (BSD-3-Clause).

## Taking from open source without taking the licence

| What is taken | Copyright applies | Obligation |
|---|---|---|
| Algorithm or idea | No — not copyrightable | Read it, learn it, reimplement it freely |
| Expression (code copied in) | Yes | Attribution, `NOTICE` entry, change notice (Apache-2.0 terms) |
| Calling a library | Governed by that library | Attribution for permissive licences |

Reading a design and reimplementing it is safe. Copy-paste is the risk.

## Limits of the mechanical gate

The CI gate checks licence identifiers against the lists above. It does **not** detect
vendored third-party code inside a package, patent or trademark terms, dual-licensing
subtleties, or where the idea/expression line falls in a specific case. **It is not legal
clearance.** Anything shipping commercially remains a human decision.
