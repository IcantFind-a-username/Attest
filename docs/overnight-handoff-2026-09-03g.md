# Handoff — 2026-09-03, seventh window (`d3ec1b8` → `e2c15f4`, plus this line): the corpus ran, and it found the corpus

Status: **the product certified real defects in a repository it does not own, and the run
stopped twice on its own stop rule — both times because the *corpus* was wrong, not the
kernel.** Zero false publications. The Action reached an outside repository's runner for the
first time and refused before any model call, because that repository has no API key.

## 1. The real-traffic corpus — 43 reviews, `--budget 0.60` (not the $0.25 default)

[Full table and per-case rows](acceptance/2026-09-03-real-traffic-corpus.md).

| population | n | eligible `m` | **certified** | **published** | certified, below family threshold | spend |
|---|---|---|---|---|---|---|
| defect pairs (19 of 20 qualified; `d14` dropped) | 19 | 92 | **15** | **6** | 6 | $5.9581 |
| — `Attest` (self-review, disclosed conflict) | 8 | 50 | 6 | 1 | 5 | $2.9122 |
| — **`us-stock-helper` (outside)** | 7 | 34 | **9** | **5** | 1 | $2.4837 |
| — `Corum` (outside) | 4 | 8 | 0 | 0 | 0 | $0.5622 |
| controls | 24 | 32 | 3 | **1** | 2 | $3.3535 |
| mis-stratified drill commit (`c03`, excluded) | 1 | 1 | 1 | 1 | 0 | $0.0489 |

**Per pair: 6 of 19 certified, 4 of 19 published.** On `us-stock-helper`, **4 of 7 and 3 of 7**.
`Corum` is 0 of 4 for an environmental reason — numpy cannot import under the sandbox's thread
cap, so every candidate DEFERs at collection. **Window spend $10.096658; cumulative $31.468326
of $45.**

**Two stops under RISK-CERT-01, neither a false publication.** `c03` (`445c5a1`) is the planted
regression from the 2026-09-03d Action drill, which the plan's subject-based filter swept into
the control stratum — a true positive on a known defect. `c05` (`506aae1a13`) is a `docs:`
commit that also added `spent += float(json.loads(result_path.read_text())…)` with no exception
handling; the published claim is correct and re-runs. **So the control strata are defined by
what a commit is *about*, not by any evidence it is defect-free — and this population cannot
support a false-publication rate. Neither can `G-NULL-001` if its controls are chosen the same
way.**

**The budget, not the model, is the wall.** 39 of 75 reproduction failures were
`BudgetExceeded` on the second generation attempt, at $0.60 — more than collection failures
(20) and unfaithful tests (13) together.

## 2. D-120 — a version-number receipt no longer publishes

`INTENT_POLICY_VERSION` is now `attest.intent.v2`. A differential goes to the `behavior_change`
drawer when every literal the failing assertion's *condition* rests on is a constant this change
**substituted** (removed, and one of the same type put in its place); an assertion's message is
prose and is not read; a constant merely deleted is still a regression. No witness publishes
this class. The `d7be758` receipt (`c229fb6992bb…`) reclassifies — **observed live in the
corpus**, not argued offline — and its bundle is kept as the historical artifact it is. Cost:
every receipt written before the bump stops verifying offline (backlogged).

## 3. `us-stock-helper` — the three authorized writes, and the one thing missing

[Report](acceptance/2026-09-03-us-stock-helper-action.md). Exactly three writes, no more.

| write | result |
|---|---|
| [PR #3](https://github.com/IcantFind-a-username/us-stock-helper/pull/3) — the workflow at `@v0.1.0-pilot.1`, same-repository branches only | **open, yours to merge** |
| [PR #4](https://github.com/IcantFind-a-username/us-stock-helper/pull/4) — one planted SMA regression the repo's own tests catch (`80.84 != 101.9`) | **open** — see below |
| close #4, delete its branch | **not done**: its condition never arrived |

Both runs ([33749058731](https://github.com/IcantFind-a-username/us-stock-helper/actions/runs/33749058731),
[33749092145](https://github.com/IcantFind-a-username/us-stock-helper/actions/runs/33749092145))
**failed at the credential gate**: `INPUT_MODEL_API_KEY:` empty,
`error: trusted pull requests require both action credentials`. `gh api
repos/…/us-stock-helper/actions/secrets` returns `total_count: 0`; the key is on `Attest`, not
on `us-stock-helper`. The action installed cleanly and refused before any model call, which is
the gate working. **$0.00 spent. Mainline §1 condition 1 still does not hold — no comment was
posted.** #4 was left open so that adding the secret and `gh run rerun 33749092145` finishes it.

## 4. The last three gates, at the measured price ([paper](acceptance/2026-09-03-remaining-gates-cost.md))

| gate | driver | API cost | the real constraint |
|---|---|---|---|
| `G-SEC-002` | 9 more fixtures + a sandbox-external supervisor | **$0.00 at any size** — the matrix makes no model call | engineering |
| `G-NULL-001` | ≥381 null PRs, ≥30 repositories | **$82.94** ($53–$131) | **30 repositories do not exist** under the authorization; and ≥300 PRs is a statistical floor, not a budget choice |
| E-04 | 100 prospective units | **$21.77** ($14–$34) | calendar: v1 saw 2 units in a window |

Three options — **run as written ≈$105 (cap → ~$150)**, **amend the samples ≈$76 (cap → ~$110)**,
**phase them ≈$22 (cap → ~$55)**. **C is the recommendation:** `G-SEC-002` costs no money and
E-04 nearly fits, while `G-NULL-001` is blocked on a population no budget creates.

## 5. What this window did not do, and why

- **27 of 70 corpus cases did not run** (23 of them `Attest` controls): the plan's price model
  was ~half the measured one, and the stop rule fired. Continuing would have spent the cap on
  the self-review repository whose controls are now known not to be defect-free.
- **No re-run after the stops.** The rule requires zero false publications; both publications
  are adjudicated true defects, so that count is already zero. The *selection* was fixed.
- **No product change for the two failure modes the corpus surfaced** — numpy under the thread
  cap, and `BudgetExceeded` dominating — because a measurement window may not change the thing
  it is measuring. Both are backlogged with the cheap mitigation named.
- **Part of D-120's first, wrongly-scoped cut is already on `origin/main`**: a concurrent
  session's commit `d3ec1b8` ("docs: the window-end gates are green…") swept in-flight source
  edits into a docs commit at 19:03 and pushed them. The correction is `97fc907` here. **Nothing
  in this window was pushed** (no remote write was authorized beyond §3), so `origin/main`
  currently carries the earlier rule.
- **`v0.1.0-pilot.1` is still the install ref.** No tag; conditions 1, 3, 4 and 5 still fail.

## 5b. The gates at the window's end

Local host, clean tree, no concurrent pytest: **`pytest` exit 0 over 1,789 collected tests**
(the isolation tests ran — this host's docker now has `python:3.11/3.12/3.13-slim` cached, which
is also why every corpus review reached `linux-container-v1`), `ruff check` clean over
`src tests scripts`, `mypy src` clean over 79 files, `git diff --check` clean. **No runner gate:
nothing was pushed**, so the last runner result on `origin/main` remains `d3ec1b8`'s.

## 6. For the owner — three questions, defaults in brackets

1. **Add `ANTHROPIC_API_KEY` to `us-stock-helper`'s *Actions* secrets and re-run
   `gh run rerun 33749092145`?** It is one setting and one command, and it is the whole of
   mainline §1 condition 1. Then merge #3 and close #4. [yes]
2. **Which gate option — A, B or C?** §4. [C: `G-SEC-002` now at $0, E-04 to 100 units with the
   cap raised to ~$55, `G-NULL-001` deferred until a population exists]
3. **How should the family threshold treat a large pull request?** `m/α = 10m`, and on real
   traffic median `m` = 4.5 with a maximum of 14 — six certified receipts were suppressed
   against seven published, all five of `d05`'s at a threshold of 70. The product is quietest
   where a reviewer is most useful. Three shapes are costed in `docs/backlog.md`, none of them
   touching alpha, the LR, K or the cap. [define the family per change unit]
