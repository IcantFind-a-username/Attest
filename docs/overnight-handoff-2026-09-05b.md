# Handoff — 2026-09-05b (`e8d5f16` → `b4b3206`, plus this line): v4.1, n = 58, and the value class read by hand

**Window spend $1.073500 of $6; cumulative $50.563241 of $90.** Remote writes: **push to `main`
only**. Gates at the tip: `ruff` clean, `mypy` clean over 82 source files, `git diff --check`
clean, **`pytest` exit 0 with zero failures** over the whole suite minus
`tests/execution/test_isolation.py`, run on a clean tree; and the **GitHub-runner `gates`
workflow passed on the tip this handoff names** — run 33930801526, `success`, no deselection, so
the isolation tests ran there.

## 1. `attest.intent.v4.1` (D-134) — clause (c) narrowed, and it changes nothing

[Report](acceptance/2026-09-05-intent-v41-replay.md), [data](acceptance/evidence/2026-09-05-intent-v41-replay.json),
**$0.00.** A symbol is intent evidence only where the diff names it in a **recognisable form**:
backticked, dot-qualified, or a bare name ≥ 8 characters that is not ordinary English. Position —
prose the change moved *inside a touched symbol's body* — is untouched, and that is what stops
`urllib3 c7b9adcb`.

| | v2 | v3 | v4 | **v4.1** |
|---|---|---|---|---|
| certifying receipts (57) | 57 | 21 | 9 | **9** |
| — the value class (48) | 48 | 12 | 0 | **0** |
| publications over 138 reviews | 28 | 15 | 6 | **6** |
| **control publications** | 2 | 1 | 0 | **0** |

**No receipt's verdict moves either way**; clause (c) fires on the same 42 of 48. What moves is
underneath: **15 of 87 evidence sites dropped** — `render`, `summary`, `readings`×2,
`snapshot`×4, `decision`×10 — across 4 receipts that each kept another site. D-132 said an
unknown fraction of (c)'s hits was vocabulary; at receipt level **the fraction is zero**.

## 2. `G-NULL-001a`: n = 58 under one version, 0 wrong publications, bound 5.2%

[Report](acceptance/2026-09-05-g-null-001a-v41.md), [data](acceptance/evidence/2026-09-05-g-null-001a-v41.json),
**$1.073500 of a $4.00 reservation ($2.9265 released).** The instruction named the other 51; **all
58 ran**, because that is the only way `n = 58` names one policy version — the deviation cost
~$0.5 and is on the record in `DEVSPEND.md`. Population, cutoff, seed, quota untouched.

31 candidates, 24 eligible, **4 differentials reproduced (head 3/3 fail, base 3/3 pass, network
blocked), all four drawered by clause (c)**, 0 certified, **0 publications**. **The four are
exactly the `jinja ac3ac6c9` and `urllib3 c7b9adcb` receipts that published under v2 and v3 —
both stopped live, at the moment of decision, not in a replay.** Rule of three: **95% upper bound
3/58 ≈ 5.2%**, against ~43% at n = 7.

**I do not claim the gate passes.** The arithmetic pass condition is met (n reached, 0 wrong
publications, controls qualified, cluster analysis reported at 8 < 10). But the population now
contains the two commits D-127 and D-132 were written against, so **it is a regression test as
much as a null study and 5.2% is optimistic.** Owner item 1.

## 3. The 48 drawered value receipts: 12 adjudicated, and v4.1 is right on 7

[Report](acceptance/2026-09-05-value-class-adjudication.md), **$0.00.** Stratified 6 (c)-alone /
3 (a) / 3 v3-too, drawn by a fixed hash before any diff was read; 12 receipts on 8 pairs.
**`pair` is the column that decided everything**: five receipts sit on pairs where `head` is
`base`'s *parent* — a `fix:` commit run backwards, which is how an injected regression is made.

| # | receipt | pair | verdict | right? |
|---|---|---|---|---|
| 1 | `us-stock-helper 75ce7a3425` nasdaq halt timestamps | **rev** | real defect | **no** |
| 2 | `attest 0ab1e8313a` typed bootstrap timeout | fwd | intended | yes |
| 3 | `us-stock-helper 240836f2e0` pattern replay invariant | fwd | intended | yes |
| 4 | `attest 0e910940fa` same pair as #2 | fwd | intended | yes |
| 5 | `us-stock-helper 1d0af73c3e` smoke redaction contract | fwd | intended | yes |
| 6 | `us-stock-helper 67dae52f8e` same pair as #3 | fwd | intended | yes |
| 7 | `attest 2878d4012e` unguarded `json.loads` in new code | fwd | real defect (new code) | **no** |
| 8 | `corum c25c7fbb4c` overflowing `Fraction` validation | **rev** | real defect | **no** |
| 9 | `corum 7c88ff3d94` same pair as #8 | **rev** | real defect | **no** |
| 10 | `us-stock-helper 16cab71ac4` messages translated to Chinese | fwd | intended | yes |
| 11 | `us-stock-helper c5b90ad887` coordinator state deleted | **rev** | real defect | **no** |
| 12 | `us-stock-helper 2a2e79e265` same pair as #10 | fwd | intended | yes |

**Forward pairs: 8 receipts, 7 right. Reversed pairs: 4 receipts, 0 right.** Undoing a `fix:`
commit takes that fix's docstring, tests and changelog out in the same diff, so clause (c) reads
it as an author stating their intent. **It is not wrong about the diff; it is wrong about which
direction time runs, and no narrowing of (c) can fix it.** Consequence: any value-class number
taken on an injected-regression corpus understates the class. #7 costs nothing the differential
could have certified anyway. And (c) has a false negative too — #8/#9 moved 44 lines of their own
tests and (c) never fired, because the anchored symbol is a private helper the tests never name.

## 4. `docs/design/gate-level.md` — designed, not implemented

Two pages. **Reachable** = the annotation admits the input (**necessary**; an unannotated
parameter abstains) **plus** a call site the diff did not add, **or** a documented domain. Two
grades: **through-caller publishes** (the reproduction enters at the call site and reachability is
in the trace), **direct goes to the drawer**. Only an **uncaught, non-deliberate exception raised
from an added line** counts — no value assertions, ever, and D-102's rejection rule is unchanged.
Execution: `linux-container-v1`, **head only** (~half a red receipt), N runs agreeing on line and
exception type, **plus an environment control** — a pre-existing test of the same call site must
pass in the same image. Offline verification re-derives every field from bytes, including that
the call-site line is *not* in the added set. Display: its own section, `Gate (new code):`, three
coordinates and the sentence "there is no base revision to compare against". Cap: **1 per pull
request, 0 when red publishes, a separate family from red, 0 when red DEFERred on environment.**
RED named. **It opens with the conflict it cannot resolve alone: `G-NEWCODE-001` governs any
new-code evidence class and demands a 120-case blind pilot first; mainline §1.3 puts gate next.**

## 5. Not done, and why

- **No second, independent null population.** 5.2% rests on controls the rule was tuned against.
  ~$1.10 buys a disjoint seed-shifted sample; it is owner item 1, not a thing to do unasked.
- **The wordlist is curated, not a dictionary** (`src/attest/review/vocabulary.py`). A word wrongly
  *in* it makes the rule publish more. Its whole measured effect today is 15 sites, 0 receipts.
- **The adjudication is not blind and n = 12.** I read the commit subject and the pair direction.
  No rate is claimed from it.
- **Nothing implemented for the gate level**, by instruction. No yellow, no `G-SEC-002`, no
  new-code pricing, no scheduler. `G-SHADOW-001` still unsatisfied. L-01 still open.
- **Four v2 receipts whose observer inputs are not on this host** were skipped by the replay, as
  before.

## 6. For the owner — three items

1. **Does `G-NULL-001a` pass?** The condition as written is met at n = 58 with 0 wrong
   publications. It is met on a population that now contains the two commits the last two rule
   revisions were written against. **Default: no — buy the independent sample first, ~$1.10**, a
   disjoint seed-shifted draw from the same eight repositories under the same cutoff. That is the
   cheapest independent evidence this gate has ever had available, and it is the difference
   between a bound and a regression test.
2. **Gate level: Read A or Read B?** `G-NEWCODE-001` applies (120-case blind pilot first, and the
   gate design becomes one of its contract alternatives), or it does not (gate ships under a new
   `G-GATE-001`). **Default: Read A with a carve-out** — run the design as N-01's first
   alternative, shipping early only in *shadow*, so the pilot's 60 defects are collected by the
   thing itself. Either way one normative document has to move, and that is a documentation
   repair the next window can do in an hour.
3. **Should clause (c) learn the direction of time?** Today it cannot, and on reversed pairs it
   misses every real defect. The only signal available is that `base` is an ancestor of `head`,
   which the review already knows. **Default: no.** A rule that behaves differently on reversed
   pairs would be a rule tuned to the corpus, and production pull requests are never reversed —
   but the *measurement* consequence must be written into the corpus policy so no future number is
   quoted without it.
