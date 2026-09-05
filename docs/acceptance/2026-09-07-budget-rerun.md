# The budget wall, re-measured: $0.25 against $1.00 on the commits it starved

**Owner instruction 1.1.** Data: [attest](evidence/2026-09-07-budget-attest.json) ·
[us-stock-helper](evidence/2026-09-07-budget-ush.json) · logs
`.attest/real-traffic/2026-09-07-budget-*.log` · product code pinned to a git worktree
at `42afd78`.

## The population, and why these 17

The 2026-09-06c four-level table over 40 real commits concluded: *"on this traffic the
binding constraint is the budget, not the adjudicators"* — 40 of 141 candidates died with
the budget gone. This run takes **exactly the commits that happened to**: the 17 of those
40 whose `--explain` log carries a budget refusal (11 of `attest`, 6 of
`us-stock-helper`), and re-reviews them at `--budget 1.00` instead of `0.25`. Same
clones, same plan file, same parents, shadow throughout — no GitHub client is
constructed, so no publication surface exists.

**17 of 17 ran.** Nothing was skipped and nothing was re-sampled.

## The two columns

| | **$0.25** (2026-09-06c) | **$1.00** (this run) |
|---|---|---|
| spend, 17 commits | **$1.6352** | **$10.3202** — 6.3× |
| candidates discovered | 105 | **331** — 3.2× |
| **red** spoke on | **0 of 17** | **0 of 17** |
| **yellow (a)** spoke on | 0 of 17 | 0 of 17 |
| **yellow (b)** spoke on | 0 of 17 | 0 of 17 |
| **green** spoke on | **8 of 17** | **8 of 17** — the same 8 |
| candidates refused for budget | 40 | **44** |
| median review elapsed | 29.6 s | **125.2 s** — 4.2× |
| total review elapsed | 554 s | 2,143 s |
| image cache lookups / hits | not recorded | **15 / 15** |

### Per commit

| commit | repo | $0.25 cand / spend / s | $1.00 cand / spend / s |
|---|---|---|---|
| `eede42194d` | attest | 13 / $0.1251 / 70.2 | 31 / $0.8919 / 161.7 |
| `9b1c9a8699` | attest | 4 / $0.1452 / 47.9 | 4 / $0.2642 / 35.1 |
| `8537f6a9d3` | attest | 0 / $0.0405 / 3.6 | 4 / $0.0636 / 20.8 |
| `150804a34b` | attest | 7 / $0.1454 / 42.2 | 21 / $0.9225 / 162.4 |
| `993ae171e7` | attest | 5 / $0.1210 / 31.6 | 5 / $0.4551 / 47.0 |
| `48b418c895` | attest | 11 / $0.1126 / 79.6 | 49 / $0.9236 / 306.4 |
| `c88f67e599` | attest | 13 / $0.1622 / 50.6 | 27 / $0.9061 / 194.3 |
| `820b973d09` | attest | 5 / $0.1242 / 29.6 | 9 / $0.1575 / 33.1 |
| `84c75985a0` | attest | 15 / $0.0998 / 28.6 | 56 / $0.8823 / 206.6 |
| `6579a8fec7` | attest | 5 / $0.0633 / 27.3 | 17 / $0.7213 / 125.2 |
| `4c3492065c` | attest | 3 / $0.0579 / 12.1 | 3 / $0.0158 / 4.4 |
| `3f6b67b0b6` | us-stock-helper | 10 / $0.1400 / 54.5 | 10 / $0.5127 / 106.6 |
| `ead0bd75d4` | us-stock-helper | 0 / $0.0271 / 5.4 | 9 / $0.5861 / 228.2 |
| `4ef2226bcf` | us-stock-helper | 7 / $0.0892 / 25.8 | 18 / $0.6641 / 98.8 |
| `801fb292ce` | us-stock-helper | 0 / $0.0241 / 5.7 | 20 / $0.8857 / 181.6 |
| `abefa25f7d` | us-stock-helper | 0 / $0.0255 / 5.6 | 18 / $0.6054 / 88.2 |
| `8cfab6c5a7` | us-stock-helper | 7 / $0.1321 / 33.3 | 30 / $0.8623 / 142.8 |

## The finding: **the budget was not the binding constraint**

Six times the money, three times the candidates, **and not one verdict moved.** Red is
still silent on all 17. Green speaks on the same 8 commits. Both yellows are still
silent. The 2026-09-06c sentence — *"the binding constraint is the budget, not the
adjudicators"* — **is retired by this measurement**, and the drawer's reason
distribution says why:

| drawer reason | $0.25 | $1.00 |
|---|---|---|
| **no reproduction bought** (the ranking never reached it) | — *(unrecorded, 53)* | **167** |
| **budget-exhausted** | 40 | **44** |
| intent stated in the diff | 5 | 33 |
| probe deferred on base | 3 | 28 |
| probe, other | 2 | 23 |
| probe reported no observation | — | 14 |
| not reproduced on head | 2 | 13 |
| generation failed | — | 6 |
| **value change, intent unknown** | — | **1** |
| unfaithful reproduction | — | 1 |

**Raising the budget raises discovery, and discovery re-starves the budget.** The
proposal stage's share of a larger budget produces more candidates, so the number
refused for budget goes *up* (40 → 44) even though four times as much was available;
the new dominant reason is that the ranking never got to them at all. A review with 56
candidates and $1.00 is not four times a review with 15 candidates and $0.25 — it is a
longer queue in front of the same door.

**One candidate reached an adjudicator at $1.00 that never reached one at $0.25**: a
`value change, intent unknown`. That is the whole of what four times the money bought in
adjudicated content, and it went to the drawer.

## What this costs, in time

Median review wall clock goes **29.6 s → 125.2 s** and the total for 17 commits goes
554 s → 2,143 s. Both columns run under `repro_concurrency = 2` (D-157) — the $0.25
column is the 2026-09-06c run, which was serial, so **this comparison does not isolate
the concurrency change** and no speed-up is claimed from it here. What it does show is
the shape of the cost: four times the budget is four times the latency, for the same
four verdicts.

## The image cache (D-156)

**15 image lookups across the 17 reviews, 15 reused, 0 built.** Two reviews bought no
reproduction and so looked up nothing. The reuse is across *commits of the same
repository* — the tag is keyed by the interpreter and the dependency manifests, and
neither repository moved a dependency across these commits.

**This run contains no cold build, so it does not time one.** What it establishes is the
denominator: on ordinary traffic, an image is built once per repository per dependency
change and reused by every commit in between — 15 of 15 here.

## Yellow (a)'s three conditions on this table (instruction 2.2)

All three of D-150's conditions are kept, and on the $1.00 column each fires **0 times**:

| condition | what it requires | fired on |
|---|---|---|
| **a1** | a changed signature ∧ a caller named by no test | **0 of 17** |
| **a2** | a new `raise` ∨ a moved return annotation ∧ an untested caller | **0 of 17** |
| **a3** | an added required parameter ∧ a statically broken call | **0 of 17** |

The same as at $0.25, and for the same reason: the level is free and deterministic, and
these 17 commits contain no changed function whose interface moved with an untested
caller. A budget cannot buy a condition that does not hold.
