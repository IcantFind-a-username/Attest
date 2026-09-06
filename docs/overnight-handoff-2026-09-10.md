# Handoff — 2026-09-10 · the factory K, measured

`6c06d44` → `feature/k5-factory-sample` · **$3.13 spent of a $27.27 reservation** ·
full report: [`docs/acceptance/2026-09-10-factory-k5.md`](acceptance/2026-09-10-factory-k5.md)

**The two remote writes you authorised:** the release-readiness branch pushed,
[PR #13](https://github.com/IcantFind-a-username/Attest/pull/13) opened and merged green as
`6c06d44`. `feature/k5-factory-sample` is pushed and has **no pull request**. Nothing published,
no protected parameter moved.

## The one sentence

**At the factory `K=5` the forward-pair corpus still publishes three receipts, and one of the
three is a different review** — K costs the `click` receipt to the discovery ceiling, and
**D-162's interpreter range** gives the `packaging` one back. **The held-out half could not be
measured at all, because the same D-162 has made `pytest` unreviewable since 2026-09-07.**

## Step 0, and what CI found

`git merge origin/main` was a no-op: PR #12 was already the branch's base, so there were no
`DECISIONS.md`/`CHANGELOG.md` conflicts. CI then went **red on a real defect**, and it is the
kind this project exists to catch: reviewing its own pull request, attest posted an
author-visible **`Attest review.` with zero comments** and then exited **2**, refusing the empty
member list it had just written — after everything was already published. Every comment can be
dropped after the branch is entered (an unanchorable green note, D-178's action clause, a
shadow propagation note). **D-180**: the delivery is attempted only when a comment survives; red
is never dropped, so an empty list means nothing was certified. RED first, then green.

Gates at the fixed commit: **2,171 passed on the runner, 2,181 locally, exit 0, kernel +
execution coverage 93.33%** against the 90% floor. Free besides: the nine-class `G-SEC-002`
matrix **PASS** at `77da75d` under the kernel observer — 955 records, `socket` 0, `connect` 0.

## K=5 against K=4

| | K=4 | **K=5** | K's doing? |
|---|---|---|---|
| forward pairs certified / published | 3 / 3 | **3 / 3** | totals unchanged, **set changed** |
| — `click cd4674a6de` | 1 receipt | **0**, $0.0046 spent | **yes** — `projected total $0.3218 exceeds the discovery share $0.3000` |
| — `packaging 527be81862` | 0 | **1 receipt** | no — **D-162**, the same decision as D-185 |
| held-out certified | 4 of 16 | **not reportable** | no — **D-185**, 17 of 27 verdicts are `no JUnit artifact` |
| — the uncontaminated 9 | 2 of 9 | 1 of 9 | no — `attest.intent.v4.2` |
| yellow (a) / yellow (b) / green, 11 pairs | 0 / 0 / — | **0 / 0 / 4 notes** | no — none calls a model on discovery |
| yellow (a) control noise | 1 of 68 (1.5%) | **not re-measured** | the 126 controls are $126 at the cap |
| forward-pair spend | $2.0313 | **$1.0408** | — |

**Why the attribution is trustworthy.** D-168's free replay puts K=4 under *today's* schedule
and loses **no** receipt (`receipts_lost: []`), so a receipt K=5 loses is K's. And three control
reviews ($0.13) show the held-out fault at K=4 and at pre-D-174 code, so it is neither.

## The defect the run found — D-185, open

D-162 (2026-09-07) set the reproduction range to **3.10–3.13** because *"a project that cannot
install on 3.10 is a bootstrap failure"*. A 2019–2022 `pytest` **installs fine on 3.12** and then
cannot collect — `TypeError: required field "lineno" missing from alias` — so no refusal fires
and the review says `no JUnit artifact`, which reads as a broken host. **7 of the 9 `pytest`
cases of the held-out sample, unreviewable since the day after the K=4 column was bought, and
nothing said so.** `G-RECALL-002`'s only number cannot currently be re-taken. Not repaired: the
choice between widening the range, pinning per project, and a stated refusal is a design
decision on the execution path, and this window's instruction was a measurement.

## Release readiness

Five sections: 1 `PASS`, 2 half `PASS` / half `FAIL` (D-185), 3 **`FAIL` closed — and the
factory K costs a receipt**, 4 `FAIL (fixed)` again (D-180), 5 `PASS`. **Six unpassed gates → five**:
`G-SEC-002`'s two rows have their data and collapse into one; `G-NULL-001` (≈$53, needs a cap
raise and a corpus that answers), `G-NEWCODE-001` (decided by D-181, still 0 of 445),
`G-SHADOW-001` (calendar time) and the outside real trial (you name the repository) are unmoved.

## Owner items — three, each a yes/no with a default

1. **Repair D-185 next, before any further recall measurement?**
   *Default: yes.* Until it is repaired, `G-RECALL-002`'s 4-of-16 cannot be re-taken and every
   `pytest` case is a silent infrastructure failure. The narrow repair is to turn a
   collection-time interpreter incompatibility into a stated refusal (D-159's register); the
   wider one is to pin the interpreter per project. The narrow one is a day and does not move a
   supported range.
2. **Raise `budget-usd`'s shipped default from $1.00 to $1.06, or drop the factory `samples` to 4?**
   *Default: neither, and say so instead.* Both buy the `click` receipt back and both are
   factory constants, which is your call under §16. The third option is to leave the pair alone
   and have the product **name** the trade when discovery is cut off — it already prints the
   projected total and the ceiling, and nothing tells the operator that raising one number
   would have bought a finding.
3. **Re-run the same 27 at K=4 on today's code, to separate K from the code cleanly?**
   *Default: no.* $2.86 measured, $27 at the cap. D-168's free replay and this window's three
   control reviews already carry the attribution for every row that moved; a full control arm
   would confirm what those two already say and would spend a tenth of the remaining cap to do
   it.
