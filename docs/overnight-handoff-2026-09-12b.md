# Handoff — 2026-09-12b · the bar that hides receipts, and a corpus that can be measured

`c09f6f2` → `main` · **PR #18 merged** · reports:
[suppression census](acceptance/2026-09-12-suppression-census.md) ·
[rebuilt corpus](acceptance/2026-09-12-heldout-supported.md) ·
[readiness](acceptance/2026-09-12-v01-tag-readiness.md)

## The one sentence

**The score bar has hidden 35 reproductions the kernel accepted — 29 of them behind a bar no certified finding could ever have reached — and the rebuilt held-out corpus puts crash-class recall at 2 of 28 (7.1%, Wilson 95% [2.0%, 22.6%]) with both receipts coming from the seven cases the old denominator already held.**

## 0. The other window's five commits, merged

[PR #18](https://github.com/IcantFind-a-username/Attest/pull/18) is merged at `e8d3448`. That
window's container was root with no docker daemon, so its 163 failures were the same 163 on
`origin/main` — every one an executor refusing a privileged user. Re-run here on docker 27.5.1:

| | |
|---|---|
| full local suite | **2,208 passed, 0 failed, 0 skipped** |
| coverage | **93.33%** against the 90% kernel floor |
| ruff · mypy · `git diff --check` | clean |
| container isolation matrix | **ran for real**, 7 passed, `python:3.9-slim` pulled |
| fixes needed | **none**; the five commits are unchanged |

**The `checks` job's first run on a pull request:** success, **18m 15s** — of which pytest is
**17m 40s** (97%). Everything else is under a minute: checkout 2 s, toolchain 12 s, ruff <1 s,
mypy 14 s, `git diff --check` <1 s, wheel + sdist 4 s. `gates` correctly skipped on the
pull-request event, and the attest self-review passed beside it in 1m45s. The backlog called this
"a cheaper half" of a 45-minute job; it is cheaper, but the container matrix, the red-team matrix
and the release drills are not where those minutes go — the ordinary suite is. `timeout-minutes`
is 30, so there are 12 minutes of headroom.

**`gates` on `main` after the merge: success**, 22m 06s (`19:02:46Z → 19:24:52Z`, run
`34266640595`), with `checks` correctly skipped on the push event. Both halves of the new
arrangement have now run once and done what they were written to do.


## 1. The score bar has hidden 35 receipts, and the number that said otherwise read the wrong field

Free: 220 ledgers, 574 `publication_policy` rows, no model call, **$0.00**
([census](acceptance/2026-09-12-suppression-census.md), D-197).

| suppression reason | count |
|---|---|
| **`below family threshold`** | **35** — 33 candidates, 17 reviews |
| `same defect as a published finding` | 13 (the defect *was* published, under another id) |
| `beyond the hard author-visible cap` | **0 — the cap has never suppressed anything** |

All 48 carry a same-task `certification: accepted` and `verification: reproduced`.

**The correction.** D-182 read `wealth_final` from the `review` row — written *before*
verification, marked `authority: ranking`. The score the policy applies is that value **× 20**
(`verification_lr(True)`), pinned three ways: `mean_e_value` on every single-eligible row is
exactly review-wealth × 20 (35 of 35); the two suppressed candidates with a `ci_final` decision
read 40.0 and 60.0 where their review rows read 2.0 and 3.0; and 16 *published* entries have
review rows reading 2.0, which no bar — never below 10 — could have admitted. So the suppressed
scores are **40.0–60.0**, not 2.0–3.0, and the nearest miss is a factor of **1.017**, not 17.

**The structural finding underneath it.** In all **2,589** recorded `review` rows the channels
bought are `("S",)` — **`T` has never fired**, not in the corpus drivers and not on the shipped
external receipt with `tier0_commands = ["ruff"]`. So a certified finding's ceiling is
`S_CAP × V_CAP = 60`, the bar is `10·m_u`, and:

> **a change unit holding 7 or more eligible candidates cannot publish a receipt at all.**

**29 of the 35** were held back by a bar above 60. The closest miss is `f118070241` at 58.97
against 60.0. Nothing was changed: `alpha`, the LRs, `k_samples`, the cap and the publication rule
are untouched.

## 2. The corpus is rebuilt, and the number is worse and no longer disputable

39 evaluable cases over eight repositories, all eligibility decided **free** before any spend
(D-195); 35 run at the factory configuration for **$4.1384** of $5.00 (D-198,
[report](acceptance/2026-09-12-heldout-supported.md)).

| | old slice (`.d186`) | **this corpus** |
|---|---|---|
| crash-class denominator | 7 | **28** |
| certified | 2 | **2** |
| point estimate | 28.6% | **7.1%** |
| Wilson 95% | [8.2%, 64.1%] | **[2.0%, 22.6%]** |
| refused before any evidence | 9 of 16 | **0 of 35** |

`G-RECALL-002` asks ≥70% with a ≥50% lower bound. **Both fail, and the upper bound is 22.6%** —
not a sample-size problem. **All seven cases of the old denominator are in this corpus and both
receipts are theirs** (`520c57974d`, `e9223c7815`); of the **21 new crash-class cases, zero**.

**Where the receipts go**, over all 56 verification attempts:

| attempts | outcome |
|---|---|
| **17** | the generated probe does not collect on base |
| **17** | the process guard refuses the probe **on the merge base** (12 child process, 5 thread) |
| 13 | the whole intent clause (8 value class, 3 diff-states-intent, 2 D-102) |
| 3 | unfaithful generated test |
| 3 | probe observation absent or unstable |
| 1 | changed lines not executed |
| **2** | **reproduced** |

Two mechanical categories are **34 of 56**, and the second of them refuses code on the revision
that contains nothing untrusted.

## 3. Release readiness, re-read

[Full read](acceptance/2026-09-12-v01-tag-readiness.md). **Five of seven conditions hold; 3, 4 and
5 still FAIL** — the same three as the last four reads.

| condition | verdict | why |
|---|---|---|
| 3 — head code cannot read secrets, reach the network, or forge a result | **FAIL** | 9 of 13 fixture classes; the external observer now covers network and process creation, and nothing else |
| 4 — a stated non-trivial share of eligible defects certified | **FAIL** | 2 of 28 = 7.1%, Wilson [2.0%, 22.6%], against ≥70% |
| 5 — one prospective shadow run with no false publication | **FAIL** | E-04 has never run; a prospective window is calendar time |

Conditions 1 and 6 improved without changing verdict: 1 now holds by a **receipt** on an outside
repository rather than a `DEFER`, and 6's last open gap — a quickstart that kept the ledger and
not the bundle — is closed by the merge.

**Known untested, by your decision (D-196), for budget and not importance:** the red control arm
at K=5 (≈$126) and `G-NULL-001` (≈$53). Both are written into the readiness document in those
words, with their prices.

## 4. Money

| | |
|---|---|
| the corpus rebuild | **$4.138447** of $5.00 reserved; $0.861553 released |
| the PR #18 self-review (the merge you asked for) | $0.187612 |
| the previous window's named lag, settled here | $0.043662 |
| **window total** | **$4.369721** |
| everything else — the census, the readiness, every document | **$0.00** |
| **cumulative** | **$90.01 of the $110 cap**, leaving **$19.99** |

## 5. Three items for you, each with a default

1. **The publication bar's ceiling is arithmetic, not statistical: at `T = 1` a receipt tops out
   at 60 and the bar is `10·m_u`, so a change unit with ≥7 eligible candidates can never publish
   one.** Write that sentence into `mainline.md` §5 decision A so the rule's real shape is on the
   record? *(This changes no behaviour; D-182's decision stands either way.)*
   **Default: yes.** — $0.00, one paragraph.
2. **Two mechanical categories cost 34 of 56 verification attempts**, and the larger surprise is
   the process guard refusing a probe on the **merge base**, where nothing untrusted runs. Should
   the next window scope a base-side relaxation of that guard (a safety decision, hence yours)?
   **Default: yes, scope it — do not implement it.** — $0.00 to scope.
3. **`sympy__sympy-24443`, `pydata__xarray-7393`, `sympy__sympy-24539`, `sympy__sympy-24562`** were
   left unrun when the $5 cap refused them. Buy the remaining four (≈$0.45) to close the corpus at
   39 of 39? **Default: no** — the interval's upper bound is 22.6% and four cases cannot move it.
