# Handoff — 2026-09-13 · six phases to `v0.1.0`

Baseline `7483a54` (`main`). Budget for the whole task: **$12**, against a cumulative
$90.01 of the $110 cap. One section per phase, appended as each merges.

---

## Phase 1 — the publication rule

Branch `feature/suppression-sources` · report:
[the score bar is removed](acceptance/2026-09-13-publication-rule.md) ·
decision [D-199](../DECISIONS.md) · **$0.00 of $0.00 reserved**

### The one sentence

**The score bar is gone: a reproduction the kernel accepted now publishes under the cap alone,
which a replay of every recorded ledger turns into +25 findings and −0, with the control side
at +0 under the intent policy in force — and the per-unit multiplicity cap is given up with it,
so the product from here offers the receipt and nothing statistical.**

### 1. Step 1, and the two readings the owner was shown

The 35 bar-suppressed receipts, each resolved to its review's own `(head, merge_base)` and
matched on **both** shas against the committed plans:

| population | suppressions | reviews |
|---|---|---|
| defect | 13 | 7 |
| **control** | **2** | 2 |
| neither (E-04 shadow 14, four-levels 6) | 20 | 8 |

The two control rows are `c02` `1d0af73c3e` and `c04` `33aa333ec0`; their `m_u` of 10 and 5 are
exactly the `m` column the 2026-09-03 real-traffic report prints for those cases, so the
classification does not rest on a sha match. **That reading fails your precondition, and phase 1
stopped on it.** Re-judged under the intent policy the product runs today, both are
`behavior_change` — *"the change states its own intent"* — and never become receipts at all:
**control side 0.** You were shown both and chose to proceed. The zero's denominator is four
control receipts, and no designated control arm has ever run under v4.x code (D-196).

### 2. Step 3, the replay

129 ledgers, 609 `publication_policy` rows, 91 carrying a certified set, **90 of 91 reproducing
their own record and 0 disagreeing**. The one exclusion is the copied external-receipt ledger,
which published 1 of 1 and suppressed nothing, so the rule changes nothing for it.

| population | added | removed | added, restricted to today's intent policy |
|---|---|---|---|
| defect | **+11** | −0 | +1 |
| **control** | **+2** | **−0** | **+0** |
| neither | **+12** | −0 | +5 |
| total | **+25** | **−0** | +6 |

Twenty-five from thirty-five, because **the hard cap and the cluster rule absorb ten** — the
first time the cap has bound anything: the census found it had suppressed 0 of 574 rows. The 25
are **identical, id for id, to the baseline D-182 filed and declined**, computed by a different
script under a differently-worded rule: two implementations agreeing on the same set.

### 3. What moved in the code, and what did not

`PUBLICATION_POLICY_SCHEMA_VERSION` `v3` → `v4`; the bar is computed and recorded, not applied;
`score_bar_applied: false` on every row; `pr_error_bound: 1.0` and
`e_value_validity: "not-applied"`; historical rows replay under their own version's rule and an
unknown version fails closed. **Unchanged:** `alpha`, every likelihood ratio, `k_samples`, the
hard cap, the supported interpreter range, the isolation backend. D-125's and D-174's own
behavioural tests are kept, pinned at `schema_version="attest.publication-policy.v3"` — the
replay rule exercising itself rather than a weakened assertion.

### 4. Also in this phase

- `docs/mainline.md` §5 A now carries the **arithmetic ceiling** as its own paragraph, marked as
  the ceiling *before* the change, and the new rule under it (your default-yes item 1 of the
  2026-09-12b handoff).
- `docs/backlog.md`: **`T` has never fired in 2,589 recorded reviews** — one of three evidence
  channels is dead on every measured path, and nobody has established whether that is
  configuration, pricing or a design conclusion. Free to diagnose. Filed P1.
- `G-CERT-004` amended: this is the first amendment to that gate that *removes* an assertion
  rather than correcting one, and it says so.

### 5. Gates

| | |
|---|---|
| full local suite | see the pull request's `checks` run |
| `ruff` · `mypy` · `git diff --check` | clean |
| focused | `tests/certification` + `tests/test_ci_flow.py` green |
| paid | **$0.00** |
