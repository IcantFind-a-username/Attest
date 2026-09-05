# Handoff — 2026-09-06b (`1f4283b` → `8537f6a`, plus this document)

**Spend $4.249400 of $15; cumulative $60.310637 of $90.** Remote writes: pushes to `main`, and
one throwaway pull request ([#10](https://github.com/IcantFind-a-username/Attest/pull/10)),
**closed unmerged, branch deleted**. Four owner instructions, all four done; two of them found
defects that are fixed in the same window.

## 1. `G-NULL-001a`'s independent population is closed (D-144, free)

Reported everywhere the project quotes it — README's measured table, the
[report](acceptance/2026-09-06-g-null-001a-final.md) §5, `evolution-gates.md` — as
**answered n = 7, 0 wrong publications, 1 true positive on a control**, over 68 of 68 reviewed.
The rule-of-three 42.9% is written down only to be refused.

**No further control is added, and money is not the reason.** 68 controls cost $0.0184 each and
produced 7 answered ones, so an answered `n ≥ 300` needs ~2,900 more controls and ~$53 — but the
binding constraint is that **57 of 68 qualified null commits produce no candidate at all**, and a
population *selected* for producing candidates is no longer a null population, because the thing
under test makes the selection. D-134's 5.2% at n = 58 remains the only bound this gate has.

## 2. Yellow (a) speaks, and the owner's rule silences it (D-145, D-147)

Wired into the publication path on the owner's terms: the interface moved **and** some caller is
named by no test, ≤ 2 per pull request, one D-142 contract line, `$0.00`, its own section, red
untouched. [Report](acceptance/2026-09-06b-yellow-published.md).

**On the 79 units this level has ever been measured over, that conjunction fires on 0.** The
disjunction fired on 5. 56 of 257 changed functions moved an interface and not one had an
untested caller. That is a ceiling on noise (95% upper bound 3.8%), not evidence of value — and
it is why the demonstration had to be constructed.

**The yellow comment, as posted** ([permalink](https://github.com/IcantFind-a-username/Attest/pull/10#discussion_r3941395689)),
anchored on `report.py:1276`, the line the diff changed:

```
[yellow] src/attest/benchmark/report.py:1275 — `write_comparison_report` changed signature;
1 call site(s) name it, 1 of them named by no test — scripts/benchmark.py:1251
```

174 characters, inside the contract's 400. Rendered on the pull request it is one grey comment
box under the changed line, with the call-site list and the *"named by no test, never not
covered"* clause beneath it; the summary carries the same line under **Impact scope**, with
green's note in its own section above and red silent.

**The first attempt posted nothing — `HTTP 422` — and that is the useful part (D-147).** A green
note named `report.py:897`, a line the diff does not carry: the structural rule requires a
changed *file*, not a changed *line*. GitHub refuses a comment outside the diff and refuses the
**whole review** for it, so one unanchorable note took yellow down with it. Fixed: both
unanchored channels are handed the diff, an unanchorable green note is dropped from the inline
review and **keeps its place in the summary**, a yellow note is placed on the first changed line
*inside* the function, and journal members are read off the comments that will actually be
posted.

## 3. Reproductions are recorded, not asserted (D-146, D-148)

The model chooses **what to call**; the merge base is executed to record **what that call does**;
the kernel writes **the assertion**. Two structural guards refuse a recording before any head run
is bought — the probe must execute the anchored file on base, and three executions must agree.
`attest.intent.v4.1` unchanged. [Report](acceptance/2026-09-06b-forward-pairs-probe.md).

### The old and new columns, same 11 pairs

| | old (legacy generator) | **new (probe + record/replay)** |
|---|---|---|
| verification answers | 59 | 98 |
| — answered about the code | 31 | **47** |
| **unfaithful — `fails on base as well`** | **20** | **0** |
| probe refused (recording inadmissible) | — | 7 |
| **certified** | **3** | **3** |
| **published** | **3** | **3** |
| value class: certified / drawered | 0 / 1 | **0 / 15** |

**The wall is gone by construction** — the expectation is what base produced three times — **and
it bought no certifications.** The bottleneck moved: candidates that used to die in generation now
make genuine differentials and meet the *unchanged* value-class rule instead, so its drawers went
1 → 15. Composition changed both ways: `random_product` returns one of four tuples uniformly and
**cannot be recorded at all** (a real recall cost of recording, correctly refused), while
`click`'s `_unpack_args` certified where the legacy generator certified nothing. The bundle still
carries the generated test and still verifies offline — *accepted … seal verified*.

**The run was bought twice, and the first run is why.** At two recordings, `random_product` agreed
by chance one time in four and the replay then failed on base — the one outcome the design calls
structurally impossible, which the owner's instruction said would be a bug. It was. D-148 raises
recordings to **three** (the third disagreed at once) and stops the reason string from blaming the
generator: it is the *second* stability gate catching a value the first was fooled by. Nothing
finite closes that hole; what bounds it is that the replay's own three base runs must agree too —
**six identical observations** before a receipt.

## 4. The `v0.1` gap list: documentation done, code listed

[Re-read](acceptance/2026-09-06b-v01-tag-readiness.md). **Four of seven conditions hold**;
blocked on 3 (`G-SEC-002`), 4 (recall) and 5 (a prospective window), in that order of difficulty.

- **Done:** [`CHANGELOG.md`](../CHANGELOG.md) exists and says what a pilot tag is not; the
  "two silent levels" note is now one, because yellow speaks; **a `gates` run is green on a
  GitHub runner at this tip** (1915 passed, 10 skipped, coverage **93.12%** against the 90%
  floor) — that was gap item 4 and it cost nothing.
- **Deliberately not done:** the version string. A tree that says `0.1.0` while conditions 3, 4
  and 5 fail is a tree that lies about itself; those four mechanical edits belong to the commit
  that cuts the tag.
- **Listed, not started:** `G-SEC-002`'s 9 fixture classes and its external observer; the
  held-out recall slice under the current policy; a prospective shadow window; a receipt-backed
  comment to an outside repository; the gate level, still shadow; and **the probe generator's
  single measured population** — 11 forward pairs and nothing else.

## 5. For the owner — three items

1. **The value-class rule is now the whole wall, and it is unmeasured against a working
   generator.** Drawers went 1 → 15 on eleven pairs while certifications did not move. Every one
   of those 15 is a real head/base difference the product refuses to publish because the base tree
   does not *state* the value. **Default: adjudicate a sample of the 15 by hand before touching
   the rule** — it is free, the receipts are recorded, and D-135's lesson is that this clause is
   right on forward pairs and wrong on reversed ones. Changing the rule first would be changing
   two things at once.
2. **Yellow (a) is author-visible and silent on 79 of 79 units.** Keep it (it costs $0.00 and
   cannot fire on ordinary traffic), or restore D-143's disjunction (5 of 79, all six of whose
   forward notes were interface changes whose callers tests already name)? **Default: keep the
   conjunction and leave it silent** — a level nobody has complained about is not evidence it
   works, but a level that speaks 5 times to say nothing actionable is evidence it does not.
3. **Where does the probe generator get measured next?** The null population is closed (D-144),
   so the honest options are the **held-out slice** (~$10–15, and `G-RECALL-002` needs it anyway)
   or **E-04 shadow traffic** (~$10–20, and condition 5 needs a prospective one). **Default: the
   held-out slice**, because it is the only one that produces a recall number for condition 4 and
   the corpus already exists.

## 6. Gates at this tip

`ruff check .` clean; `mypy` clean over 87 source files. **On a GitHub runner at `150804a`:
1,915 passed, 10 skipped, coverage 93.12%** against the 90% floor — the 10 skips are the
container-backed cases the runner cannot execute. The same suite is **green on this host with no
skips**, including the three `m01_offline_measurement_probe` module fixtures that have failed
under a dirty tree since 2026-09-02: they pass whenever the tree is clean, and this window's
committed tips are. New tests: `test_probe_generation.py` (12),
plus 6 in `test_impact_scope.py`, 2 in `test_ci_flow.py` and 1 in `test_output_contract.py`.
All of them fail on the previous implementations. Two existing suites changed deliberately: every
test that supplies its own reproduction now pins `probe_generation=False` and says why, and the
M-01 measurement probe pins it too, because a cassette can only replay the generator it recorded.
