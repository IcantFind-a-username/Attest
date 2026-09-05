# Forward pairs: 11 of 2,005, and why that is the finding

**Owner instruction 3 of 2026-09-05c. D-135.** Free — git and pytest only, no model call, no
spend. Driver: [`scripts/corpus/forward_pairs.py`](../../scripts/corpus/forward_pairs.py). List:
[`2026-09-05-forward-pairs.json`](../../benchmarks/attest-v2/runs/2026-09-05-forward-pairs.json).

## 1. The policy

**A value-class recall number may be quoted only from forward pairs** — `base` an ancestor of
`head`, the defect appearing at `head`, time running the way it runs in a pull request. Reversed
pairs (D-116) keep the corpus for **crash and rejection classes and for controls**, where the
direction of time does not enter the rule.

The reason is measured, not assumed. On a reversed pair the diff *is* a repair run backwards, so
the fix's docstring, tests and changelog leave in the same diff and `attest.intent.v4.1` clause
(c) reads an author stating their intent — correctly, about that diff. The 2026-09-05b
adjudication: right on **7 of 8** forward receipts, wrong on **4 of 4** reversed ones.

## 2. How a pair is built

Given a repairing commit `F`:

1. **the oracle** — the node ids of `F`'s own test files that **fail on `F^`** and **pass on
   `F`**. No oracle, no pair.
2. **the boundary** — search the first-parent chain behind `F^` for the first commit that fails
   the oracle **whose own parent passes it**. That commit is `head`; its parent is `base`. Both
   ends are probed, so a tree in between that cannot run the oracle is skipped rather than fatal.
3. anything else is `unresolved`, with its reason recorded.

**The subject line is not read.** The first sweep only took `fix:`/`Fix …` subjects; it cost
pairs and bought nothing, because a commit that is not a repair produces no boundary anyway —
its new test fails on every ancestor, since the feature is *absent* there rather than broken,
and the search rejects it in two probes. The oracle already encodes what the subject was being
used to guess.

**The window is 32 first-parent commits**, and that is measured too: every boundary this corpus
produced sat 0, 1, 2, 3, 11, 13, 20 or 22 commits behind its fix, and no probe past 32 ever
found a passing ancestor.

## 3. The list

**13 resolutions over 11 distinct `(repo, head, base)` pairs** — rows 4, 5 and 6 are three fix
commits that converge on one boundary, and a review of that pair buys the same evidence three
times, so a review run is sized against 11.

| # | repo | head | base | distance | the repair whose tests are the oracle |
|---|---|---|---|---|---|
| 1 | `attrs` | `e048efcb39` | `75723b7720` | 11 | Cope with `field_transformer` being a generator (#1417) |
| 2 | `attrs` | `7c85d68de2` | `564fade925` | 1 | Allow single attributes to be excluded |
| 3 | `click` | `0585f456ba` | `cfa01eeb78` | 0 | Make `prompt`/`ParamType` typing work without runtime `typing_extensions` |
| 4 | `click` | `cd4674a6de` | `d5fbd32842` | 11 | Fix `get_parameter_source()` during type conversion and eager callbacks |
| 5 | `click` | `cd4674a6de` | `d5fbd32842` | 20 | Fix broken fish completion and multiline help string |
| 6 | `click` | `cd4674a6de` | `d5fbd32842` | 13 | pager doesn't close std streams |
| 7 | `click` | `19fd4d6e18` | `c69643b60c` | 22 | Fix broken fish completion and multiline help string |
| 8 | `itsdangerous` | `3703fbdedd` | `64048c1106` | 0 | datetimes are timezone-aware utc |
| 9 | `more-itertools` | `d63a26e56e` | `d0c20f5946` | 3 | Revert "first_true: pred -> predicate" |
| 10 | `more-itertools` | `2deea20ead` | `6235e945d9` | 2 | Fix `random_product()` as well |
| 11 | `more-itertools` | `71b76842d3` | `3331507287` | 1 | Fix `product_index()` with iterator input |
| 12 | `more-itertools` | `390a3db74c` | `935db916c7` | 1 | Reduce `groupby.__next__` calls in `all_equal` |
| 13 | `packaging` | `527be81862` | `e934f4896e` | 0 | Revert "Specifier.version now returns Version, not string" |

**The owner's target was ≥ 15 and it was not met.** The eleven repositories were scanned to
their limits — `urllib3` 417 commits, `jinja` 372, `attrs` 355, `packaging` 303,
`more-itertools` 233, `us-stock-helper` 101, `python-dotenv` 85, `click` 83, `attest` 36,
`itsdangerous` 20, `corum` 0 (a two-commit clone) — 2,005 in total, and the yield is **0.65%**.
More scanning of these repositories will not close the gap; another repository would.

## 4. Where the other 1,992 went

| why no pair | commits | share |
|---|---|---|
| the tree cannot run the oracle (a missing dependency, a `conftest` today's pytest rejects, a collection error) | 1,086 | 54.2% |
| **no passing ancestor in the 32-commit window** | 607 | 30.3% |
| `F^` already passes the fix's own tests — not a repair | 223 | 11.1% |
| `F^` does not carry the defect under the oracle | 40 | 2.0% |
| no node discriminates `F` from `F^` | 35 | 1.7% |
| the boundary is bracketed but no tree in between can be classified | 1 | 0.05% |

The second row is the one that matters, and it is not a defect of the method: **a fix's own test
usually does not discriminate its defect on a tree far enough back**, because by then the code
differs for unrelated reasons and the test fails for those instead. Only a genuine
regression — code that passed the test, then stopped — leaves a boundary.

**Zero pairs came from this account's three repositories.** Their `fix:` commits repair defects
that were *born with the code they fix*, which has no boundary at all. That is also why
differential V can never certify them (D-063), and it is worth saying beside any recall number
taken here.

## 5. What this costs the numbers already published

Every value-class figure taken on the injected-regression corpus **understates the class** and
must carry that sentence — the D-134 replay's `0 of 48` included.

## 6. What is owed

One full `attest review` per **distinct** pair (head = the commit that introduced the defect,
base = its parent), `attest.intent.v4.1`, K=4, `--budget 1.00`, containers, local only. It did
not run this window: the host's container backend stopped working mid-window
([the fault, isolated](../acceptance/2026-09-05-g-null-001a-independent.md#4-the-host-fault-isolated)),
and a review whose reproduction cannot execute yields no value-class row. At the corpus's
measured price, 11 reviews is about $3.
