# The `v0.1` conditions, re-read — 2026-09-12

Previous read: [2026-09-07](2026-09-07-v01-tag-readiness.md). Mainline §1 states **seven**
conditions. All seven are read below against what is on disk today, not against what the last
read said about them.

**The same three conditions fail, and none of them closed.** What moved is what is known about
them: condition 3 gained an external observer for two of its claims, and condition 4 gained a
real denominator — its number is now worse and no longer disputable. Condition 5 has not moved at
all. Separately, condition 1 — which already held — now holds by a receipt rather than by a
`DEFER`.

## The seven conditions

| # | condition (mainline §1) | 2026-09-07 | **now** | what moved |
|---|---|---|---|---|
| 1 | an outside repository installs from a stable ref, adds the Action, receives PR comments | holds, by a `DEFER` | **holds, by a receipt** | `us-stock-helper` #5 installed `@v0.1.0-rc.2` with the quickstart's defaults and received a `[red]` comment backed by head FAIL 3/3, base PASS 3/3, receipt `37e8cbfcabe1` ([report](2026-09-12-external-receipt.md)). The defect was **owner-placed**, so it measures the install path and **no recall** |
| 2 | every author-visible finding carries its level's evidence form and was admitted by that level's non-model adjudicator | holds, five classes | **holds, five classes** | unchanged in substance; D-190 added a fourth silence verdict, and it is a contract line like the others |
| 3 | head code cannot read secrets, reach the network, or forge a result | **FAILS** — 9 of 13 fixture classes, external observer INSUFFICIENT | **FAILS** — 9 of 13, external observer sufficient *for two claims* | the kernel's own audit log recorded **945 records at the container's uid with 0 `socket`, 0 `connect`, 0 `clone`** ([report](2026-09-08-external-observer.md)), so network and process-creation are now attested from outside the product. The four remaining fixture classes and every claim outside that rule set are untouched |
| 4 | held-out corpus: silent on every control, a stated non-trivial share of eligible defects certified | **FAILS**, denominator unstated | **FAILS**, and the denominator is now a real one | D-186 cut the old slice's eligible-and-supported denominator to **7** (2 certified). A corpus built for the question — held-out instances whose projects declare an interpreter the product supports — replaces it; the number is in §2 and it does not reach 70% |
| 5 | one prospective shadow run with no false publication | **FAILS** | **FAILS** | unchanged. E-04 is unchecked in the roadmap and nothing prospective has run. A prospective window cannot be assembled from history, and nothing in this window tried |
| 6 | the L-01 exit list is done | holds | **holds** | the item the 2026-09-09 amendment called *"the one nothing local can substitute for"* — a receipt on a repository this project does not develop in — is taken; and the gap it exposed, a quickstart that retained the ledger and not the bundle, is closed (D-194) |
| 7 | every author-visible line obeys the output contract | holds | **holds** | D-190 put the seven refusals on the one line an author reads, in the contract's own shape |

**Five of seven hold. The tag is blocked on 3, 4 and 5** — the same three as the last four reads.

## 1. Condition 3, at its real width

Nine of thirteen attack fixture classes are dispatched for real on the production backend and
marked, never certified, with a positive control certifying in the same run. The external
observer now exists and works: an audit rule on the host kernel, `attest` not imported by the
reader, the container's uid written in as a literal, a marker process and an unfiltered control
rule to separate *"the boundary held"* from *"the observer is broken"*.

What it establishes is **narrow and real**: the kernel says no network syscall was made and no
process was cloned, which agrees with what the harness said about three fixtures. What it does
not establish is everything else: the four missing classes (`/proc`, home/git, native syscall,
namespace), any claim outside the seven watched syscalls, and any run on any other kernel.

**This condition is a safety claim, not a measurement, and it is the only one of the three that
cannot be closed by buying data.**

## 2. Condition 4, on a corpus built for it

D-191 said the old held-out slice was too small once the unsupported cases were removed: seven
eligible-and-supported cases cannot test a ≥70% bar. The rebuild (D-195) is done and the number
is taken — 39 evaluable cases over eight repositories, 35 of them run at the factory
configuration for $4.1384. Full table, per-case verdicts and candidate ids:
[corpus report](2026-09-12-heldout-supported.md).

| | old slice (`.d186`) | **this corpus** |
|---|---|---|
| crash-class denominator | 7 | **28** |
| certified | 2 | **2** |
| point estimate | 28.6% | **7.1%** |
| Wilson 95% | [8.2%, 64.1%] | **[2.0%, 22.6%]** |
| refused before any evidence | 9 of 16 | **0 of 35** |

The gate asks for **≥70% point detection with a ≥50% clustered lower bound**. **Neither is met,
and the interval's upper bound is 22.6%** — this is not a sample-size problem. All seven cases of
the old denominator are inside this corpus and **both receipts are theirs**; the 21 new
crash-class cases certified nothing. What has changed is that the number is now over a population
that was **pre-specified, screened for supportability before anything was bought, and built from
the same held-out slice**, and that the report says *where* the receipts go: 34 of 56 verification
attempts end in two mechanical categories — the generated probe failing to collect (17) and the
process guard refusing a probe **on the merge base** (17) — against 13 for the whole intent
clause.

**Controls.** The last measured control arm is at **K=4** (0 false publications on 40 held-out
controls, 2026-09-03; 0 on 68 independent nulls, 2026-09-05d). By **D-196** the K=5 red control
arm (126 controls, ≈$126) is **not** bought before `v0.1.0` and is recorded here as **known
untested — for budget, not because it does not matter**. Any sentence of the form *"silent on
every control"* is therefore about a K=4 population and must say so.

## 3. Condition 5, unmoved and honest about why

E-04 is unchecked. The 2026-09-07 window's 17 + 13 shadow reviews and this window's corpus run
are all of commits that existed before the protocol; a prospective window is calendar time, and
no amount of replay substitutes for it. `G-NULL-001` (≈$53) is likewise **not** bought before
`v0.1.0` by D-196, and is recorded here as **known untested — for budget**.

## 4. What would move each remaining condition

1. **Condition 3** — the four remaining fixture classes, plus observation of the claims the
   current audit rule set does not watch. Days of work; the observer itself now exists, which is
   the part that used to be missing.
2. **Condition 4** — product work, not corpus work. The corpus is no longer the blocker: the
   verdicts in §2's report say where the receipts are lost, and none of the largest categories is
   a measurement problem.
3. **Condition 5** — calendar time and ≈$10–20 for 100 units, on live traffic, prospectively.

## 5. The `FAIL` list, in one place

| condition | verdict | why, in one line |
|---|---|---|
| 3 — head code cannot read secrets, reach the network, or forge a result | **FAIL** | 9 of 13 fixture classes; external observation covers network and process creation only |
| 4 — a stated non-trivial share of eligible defects certified | **FAIL** | rebuilt crash-class recall **2 of 28 = 7.1%**, Wilson 95% [2.0%, 22.6%], against a ≥70% bar (§2) |
| 5 — one prospective shadow run with no false publication | **FAIL** | E-04 has never run; a prospective window is calendar time |

**Known untested, by owner decision D-196, and for budget rather than importance:**

| item | price | what it would settle |
|---|---|---|
| the red control arm at K=5 | ≈$126 (126 controls at the per-review cap) | whether the shipped K changes the control false-publication rate; the last measured arm is K=4 |
| `G-NULL-001` | ≈$53 | the natural-null rate on the full preregistered population |
