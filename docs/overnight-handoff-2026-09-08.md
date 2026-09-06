# Handoff — 2026-09-08 (`62241f4` → TIP)

**Spend $0.00 of the $8 window cap; cumulative $80.33 of $110 — unchanged, because nothing was
bought.** Every item was free: two offline replays over ledgers already on disk, one free `ast`
scan, two P1 fixes, one CLI flag, one runner dispatch of a matrix that makes no model call. **No
provider is constructed anywhere in this window.** Remote writes: pushes to `main`, one pull
request to `Corum`, one `workflow_dispatch`. Eight items instructed; **seven complete, one
partial** (§6).

## 1. Discovery scheduling (D-168), replayed on two populations

Discovery ≤ **30%** of one review's budget with the first change unit no longer exempt;
candidates ranked by **cluster size**, then **static credibility** (anchor inside a definition in
a non-test file; that definition called somewhere in the tree), then finding id; at most **3**
reproductions per **changed file**, the rest recorded as `ranked below verification cap`.

| at `--budget 1.00`, `--cap 3`, K=4 | 17 commits (D-166) | 11 forward pairs |
|---|---|---|
| units read | 76 → **46** | 31 → **31** |
| regression-eligible candidates | 168 → **142** | 98 → **98** |
| reproductions bought | 168 → **79** | 98 → **51** |
| spend | $10.27 → **$5.24** | $2.03 → **$1.08** |
| **receipts published** | 0 → **0** | **3 → 3** |
| candidates verified that were not before | 0 | 0 |
| first unit refused by the ceiling | 0 of 17 | 0 of 11 |

**Half the money, every receipt.** The forward pairs are the only population where red has ever
published; all three receipts survive. [Report](acceptance/2026-09-08-schedule-replay.md).

**A correction to D-166 the replay forced.** D-166 read the drawer's 167 `no-reproduction-bought`
as *"never ranked high enough to buy a reproduction"*. Of the 331 candidates, **168 were
regression-eligible and every one of them bought a reproduction attempt**; the 167 are the
**ineligible** ones — 128 `new_code`, 35 `non_python` — which have no verification reason to
record. Discovery was not starving verification of eligible candidates; it was buying candidates
that can never be certified. That is what the share stops.

**The modelling detail that decides the answer, and got it wrong first.** A reservation is
*transient*: `propose` reserves K samples at the 3,200-token bound, then `settle` replaces each
with the call's actual cost, which is about **3× smaller**. The first version of this replay
accumulated reservations across units, read the ceiling as three times tighter than it is, and
reported that the rule would lose two of the three receipts. It does not. The corrected model is
in `units_under_the_share`, with the reason written beside it.

## 2. Yellow (b): one class closed, one made a shadow (D-169)

| | class 1 — null/Optional | class 2 — exception propagation |
|---|---|---|
| measured | 0 of 79 under **two** rule versions, 28 hypotheses, 0 surviving | 0 of 79, control noise **0%** vs the 3% ceiling |
| cost | **one model call per review** | $0.00 |
| now | **off** — the guard returns before the tree read and before the provider, so it costs $0.00, not a little less | **shadow** — runs, writes `propagation_note` rows, reaches no author-visible surface (the arrangement D-137 gave the gate) |

Written into the README's limitations, including the one argument for reopening that has never
been tested: the corpus that defeated class 1 carries no type annotations.

## 3. Yellow (a)'s fourth condition (D-170) — and it is the only one that has ever spoken

≥ 3 call sites across ≥ 2 files, and **no test names the function at all**.

| condition | forward pairs | null controls |
|---|---|---|
| a1 signature + untested caller | 0 of 11 | 0 of 68 |
| a2 new raise / return + untested caller | 0 of 11 | 0 of 68 |
| a3 added parameter, arity break | 0 of 11 | 0 of 68 |
| **a4 fan-out, no test names it** | **1 of 11 (9.1%)** | **2 of 68 (2.9%)** |

**2.9% is inside the owner's 3% ceiling by one event** — 3 of 68 would be 4.4% and would fail,
and the 95% upper bound on the true rate is **9.0%**. Enabled under the rule as stated. Both
control firings are *literally true*: `git grep` finds no test naming `click.version_option` or
`jinja2.make_attrgetter` at those revisions. The forward-pair firing is on the
defect-introducing commit.

## 4. The two P1 fixes, and their REDs

- **M-01 offline probe (recurred in four consecutive windows; cost two full-suite runs in the
  last one).** It imported `src` from the **working tree** and refused to run when that tree was
  dirty. It now materialises the **HEAD commit tree** with `git archive` — or a directory pinned
  with `--source-snapshot` — imports that, and digests what it imported. **RED:** a detached
  worktree whose `src` carries an uncommitted edit produces the same `source_tree_sha256` and the
  same `semantic_digest` as the clean twenty-repeat bundle; and an explicit snapshot is what gets
  measured, so a byte added to it moves the digest.
- **The paid drivers' cumulative cap (D-172).** `if spent >= args.cap` gated *starting* on money
  already spent, which is how the 2026-09-07 run ended **$0.62 above its own $3.50 cap**. Every
  driver now reserves the per-review `--budget` before a unit starts and settles it afterwards.
  **RED:** the recorded six units replayed both ways — the old rule starts all six and ends at
  $4.1163; this one starts **four**, ends at **$2.6486**, and names the two it refused. An
  unreadable cost is charged the reservation, never treated as free.

## 5. Stable-period preparation

- **`attest stats --since 7d`** (or a date, or `24h`, `2w`) slices the ledger before anything is
  counted and prints a period report: what spoke on how many reviews with every silence named,
  why the silent candidates were silent, spend, image reuse, median review. An unreadable spec is
  exit 2 with the spellings that work (D-171).
- **Installs at `v0.1.0-rc.1`.** `Attest` reviews itself with the code under review (`uses: ./`),
  which is deliberate and unchanged. `Corum` has no workflow at all → **one pull request**, the
  documented install plus a fork guard. **`Corum` has no `ANTHROPIC_API_KEY` secret**, so the
  workflow will report one line and exit 0 until you add one; that is yours to do.
  **`us-stock-helper` was not touched** — it is pinned at `v0.1.0-pilot.1` with `budget-usd 0.60`
  and `samples 4`, and updating it is a remote write this window was not authorised to make. The
  exact file is at `docs/operations/us-stock-helper-attest-review.yml`; the diff is three lines.

## 6. `G-SEC-002`'s external observer — OBSERVER_RESULT

## 7. Gates

GATES_LINE

## 8. For the owner — three items

1. **The 30% discovery share has a cliff at the shipped `k_samples = 5`, and it lands on the one
   review that published.** The ceiling is checked against the preflight reservation, which
   overstates a real proposal by ~3× ($3.15 reserved against $1.07 spent, over the 17). At K=4,
   **0 of 28** recorded reviews are refused their first unit. At K=5, **one is** — `click
   cd4674a6`, first unit 47,448 chars, reservation $0.3182 against a $0.30 ceiling — and it is
   one of the three reviews that has ever published a receipt. It would defer with a stated
   budget reason, which is a contract line, but it would publish nothing. **Default:
   `k_samples = 4`**, which is what both measured runs already used and what removes the cliff
   without touching the budget. `budget_usd >= 1.06` does the same and costs more.
2. **a4 meets your 3% ceiling by one event, and it is the only condition of yellow (a) that has
   ever spoken.** 2 of 68 is 2.9%; 3 would be 4.4%. The 95% upper bound is 9.0%, so n=68
   establishes that the rate is not large, not that it is under 3%. **Default: leave it on and
   widen the control population before tightening the thresholds** — a4 is currently the whole of
   this level's voice, and both of its control firings are true statements rather than false
   ones.
3. **OWNER_ITEM_3**
