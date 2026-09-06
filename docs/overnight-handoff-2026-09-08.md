# Handoff — 2026-09-08 (`62241f4` → TIP)

**Spend $0.00 of the $8 cap; cumulative $80.33 of $110, unchanged, because nothing was bought.**
No provider is constructed anywhere in this window. Remote writes: pushes to `main`,
[Corum#1](https://github.com/IcantFind-a-username/Corum/pull/1), four `workflow_dispatch` runs.
Eight items instructed, eight done, with one omission named below. Detail is in D-168…D-173 and
the reports linked here.

## 1. The discovery schedule, replayed offline (D-168 · [report](acceptance/2026-09-08-schedule-replay.md))

Discovery ≤ 30% of a review's budget (first unit no longer exempt); rank by cluster size, then
static credibility, then id; ≤ 3 reproductions per changed file, the rest `ranked below
verification cap`.

| `--budget 1.00`, `--cap 3`, K=4 | 17 commits (D-166) | 11 forward pairs |
|---|---|---|
| units read | 76 → **46** | 31 → **31** |
| regression-eligible candidates | 168 → **142** | 98 → **98** |
| reproductions bought | 168 → **79** | 98 → **51** |
| spend | $10.27 → **$5.24** | $2.03 → **$1.08** |
| **receipts published** | 0 → **0** | **3 → 3** |
| verified that were not before | 0 | 0 |
| first unit refused by the ceiling | 0 of 17 | 0 of 11 |

**Half the money, every receipt.** Two corrections the replay forced, both written down:
D-166's 167 `no-reproduction-bought` were **163 ineligible candidates**, not candidates the
ranking failed to reach — every one of the 168 eligible ones did buy an attempt. And a
reservation is *transient*, so modelling the ceiling against a sum of reservations reads it 3×
tighter than it is; the first version of this replay did, and reported the opposite result.

## 2. Yellow (a)'s fourth condition (D-170 · [scan](acceptance/evidence/2026-09-08-impact-a4.json))

≥ 3 call sites across ≥ 2 files, and no test names the function at all.

| condition | forward pairs | null controls |
|---|---|---|
| a1 signature + untested caller | 0 of 11 | 0 of 68 |
| a2 new raise / return + untested caller | 0 of 11 | 0 of 68 |
| a3 added parameter, arity break | 0 of 11 | 0 of 68 |
| **a4 fan-out, no test names it** | **1 of 11 (9.1%)** | **2 of 68 (2.9%)** |

Inside your 3% ceiling **by one event** (3 of 68 = 4.4%); the 95% upper bound is **9.0%**.
Enabled. Both control firings are literally true — `git grep` finds no test naming
`click.version_option` or `jinja2.make_attrgetter` at those revisions — and the forward firing is
on the defect-introducing commit. It is the only condition of this level that has ever spoken.

## 3. The external observer works (D-173 · [report](acceptance/2026-09-08-external-observer.md))

Kernel audit rules beside the container; `attest` is not imported by the reader. On a GitHub
runner (`6.17.0-1022-azure`, run `34014635971`), across a `PASS` matrix with all nine fixtures
dispatched: **945 records at the container's uid — 939 `openat`, 4 `execve`, 2 `unlink`, and 0
`socket`, 0 `connect`, 0 `clone`.** The harness said the network, DNS and process-exhaustion
fixtures were refused; the kernel says those syscalls were never made.

Four runs and three real failures to get there: the matrix run under `sudo` was refused by the
product's own containment guard; `ausearch` reported `<no matches>` for a key the raw log carried
1,060 times, so it is out of the path; and the control key is a prefix of the rule key. Zero
records now means something, because `arm` carries a marker at the container's uid and an
unfiltered control rule. **Condition 3:** classes unchanged at 9 of 13; the external-observer
item is no longer `INSUFFICIENT` **for the network and process-creation claims** — the rest of it
is, and the report says what this cannot show.

## 4. The two P1s, and their REDs

- **M-01** imported `src` from the working tree and refused to run when it was dirty — four
  windows, two full-suite runs lost in the last. It now imports the **HEAD commit tree**
  (`git archive`) or a `--source-snapshot`, and digests what it imported. **RED:** a detached
  worktree with an uncommitted edit in `src` yields the same `source_tree_sha256` and
  `semantic_digest` as the clean twenty-repeat bundle; and a byte added to an explicit snapshot
  moves that digest.
- **The drivers' cap (D-172)** gated *starting* on money already spent, which is how the
  2026-09-07 run ended **$0.62 above its own $3.50 cap**. Each unit's maximum is now reserved
  first. **RED:** the six recorded units replayed both ways — the old rule starts all six and
  ends at $4.1163, this one starts **four**, ends at **$2.6486**, and names the two it refused;
  an unreadable cost is charged the reservation.

## 5. The rest, one line each

`attest stats --since 7d` prints a period report and exits 2 on a spec it cannot read (D-171) ·
yellow (b)'s null class is **off**, its propagation class a **shadow** (D-169) · `Corum` has the
install at `v0.1.0-rc.1`, and its own check is **red for a missing `ANTHROPIC_API_KEY`**, loudly
and by design · **`us-stock-helper` was not touched** (still `v0.1.0-pilot.1`, `budget-usd 0.60`)
— the file is `docs/operations/us-stock-helper-attest-review.yml`, a three-line diff, and
updating it is a remote write this window was not authorised to make · the `more-itertools` issue
is **still not filed** (checked twice upstream); the draft is
`docs/acceptance/2026-09-06-more-itertools-issue.md`.

## 6. Gates

GATES_LINE

## 7. For the owner — three items

1. **The 30% share has a cliff at the shipped `k_samples = 5`, and it lands on the one review
   that published.** The ceiling is checked against the preflight reservation, which overstates a
   real proposal ~3× ($3.15 reserved against $1.07 spent, over the 17). At K=4, **0 of 28**
   recorded reviews are refused their first unit; at K=5, **one is** — `click cd4674a6`, 47,448
   chars, $0.3182 against $0.30 — and it is one of the three that ever published. It would defer
   with a stated reason and publish nothing. **Default: `k_samples = 4`**, which both measured
   runs already used; `budget_usd ≥ 1.06` does the same and costs more.
2. **a4 meets the 3% ceiling by one event and is the whole of yellow (a)'s voice.** n=68
   establishes that the rate is not large, not that it is under 3%. **Default: leave it on and
   widen the control population** rather than tighten thresholds on 68 units.
3. **The observer costs $0.00 and is off by default.** (a) leave it opt-in; (b) run it on every
   red-team dispatch; (c) widen the watched set — reading the controller's key file is an
   `openat`, and 939 were recorded without anyone asking *which paths*. **Default: (b) now, (c)
   as a scoped item** — (b) is a one-line change to the input's default; (c) is where the
   remaining `INSUFFICIENT` actually is.
