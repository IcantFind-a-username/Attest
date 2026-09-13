# The A/B/C probe arms, 2026-09-14 — the shipped call, and two adaptive-thinking calls, on the same forty

**D-246 step 5, the owner instruction of 2026-09-14; dispatched on the owner's "跑" the same day.**
Three dispatches of `mutation-recall.yml` from `feat/probe-arms` (the repaired index of D-246 and the
ledger facts of step 3 in all three), over the same forty trials, **$1.00 per case, K=5,
`linux-container-v1`, the local review path, read-only clones, nothing written anywhere**, each
admitted at the D-244 p95 reservation ($0.1035 per case, from 209 trials of history) and capped by
the driver at $5.00, dispatched one at a time and settled in [DEVSPEND](../../DEVSPEND.md) before the
next so the preflight's headroom check was mechanical. **Only the probe's one call differs** between
the arms -- `generate_probe`'s provider, model and output bound (`ProbeCall`) -- and the proposals
and the reproduction generator are the shipped ones in all three. Runs
[34751464512](https://github.com/IcantFind-a-username/Attest/actions/runs/34751464512) (A),
[34753219949](https://github.com/IcantFind-a-username/Attest/actions/runs/34753219949) (B),
[34752320088](https://github.com/IcantFind-a-username/Attest/actions/runs/34752320088) (C);
**$7.722766 in all** of the $15.00 reserved; 40 of 40 cases ran in every arm and none was refused.
The tables are `scripts/acceptance/probe_arms_report.py`'s over the three artifacts, flattened under
[`evidence/2026-09-14-probe-arms/`](evidence/2026-09-14-probe-arms/).

## The arms

| arm | `arm` input | trials file | the probe's call |
|---|---|---|---|
| **A** | `A` | `trials-arm-A.jsonl` | the shipped call: the generation model, thinking disabled, the probe's own output bound (1,500 tokens) -- the same call as the 11 of 40 (D-245) and 12 of 40 (D-240) runs, so a third run of it is the jitter control the other two are read against |
| **B** | `B` | `trials-arm-B.jsonl` | the generation model, thinking adaptive at effort medium, 8,000 output tokens |
| **C** | `C` | `trials-arm-C.jsonl` | the proposal model, thinking adaptive at effort medium, 8,000 output tokens |

Every trial row carries `probe_call` (the arm, its model, thinking, effort and output bound), so an
arm is legible from its own file; the ledgers' `review_run.spend_breakdown` (D-243) carries the
probe stage's cost and tokens per case; `elapsed_s` is the case's wall clock.

## The default rule, pre-registered before the first call

1. The default probe call is the arm with the best **cost per certified case**.
2. A dearer arm becomes the default only if it certifies **at least three more cases** than the
   cheaper one **and** each gained case's mechanism can be named from its ledger -- the probe it
   chose, what the merge base recorded, the reason the receipt was accepted -- by a person, case
   by case.
3. An arm whose **median per-case wall clock is more than twice A's** is not the default,
   whatever it certifies.
4. AGENTS.md §9: one re-run of the forty moves about ±2 cases on its own; a difference of two
   cases or fewer decides nothing.
5. A case the cap or the budget refused is a miss for that arm and is named; the denominator is
   forty for every arm.

## 1. The three arms side by side

| arm | the probe's call | cases run | certified of 40 | Wilson 95% | boundary certified of 13 | spend | probe stage | cost per certified case | median wall clock per case | refused by the cap |
|---|---|---|---|---|---|---|---|---|---|---|
| **A** | `claude-opus-5`, thinking disabled, 1500 output tokens | 40 | **12** | [18.1%, 45.4%] | 1 | $2.7116 | $1.7141 | $0.2260 | 21 s | none |
| **B** | `claude-opus-5`, thinking adaptive at effort medium, 8000 output tokens | 40 | **14** | [22.1%, 50.5%] | 1 | $3.0174 | $2.0320 | $0.2155 | 23 s | none |
| **C** | `claude-sonnet-5`, thinking adaptive at effort medium, 8000 output tokens | 40 | **13** | [20.1%, 48.0%] | 2 | $1.9937 | $1.0017 | $0.1534 | 20 s | none |

|  | A | B | C |
|---|---|---|---|
| probe calls over the forty | 54 | 52 | 62 |
| probe-stage output tokens (thinking included) | 6,283 | 20,094 | 30,143 |
| probe-stage input tokens, cache reads included | 367k | 354k | 408k |
| cases that recorded a probe on the merge base | 32 | 36 | 33 |
| boundary thirteen: a probe made the revisions differ | 9 | 12 | 11 |
| wall clock per case: mean / largest | 24 s / 65 s | 27 s / 100 s | 28 s / 179 s |
| the run on the runner | 18 min | 22 min | 20 min |
| classes: certified / value class / no receipt / no reproduction attempted | 12 / 17 / 10 / 1 | 14 / 17 / 8 / 1 | 13 / 16 / 11 / 0 |

**The jitter control.** A is the shipped call run a third time on the same corpus: 12 of 40, against
11 (the D-245 run) and 12 (the D-240 run); it gains `urllib3-none_guard-15` against the D-245 run
(the case §4 of the [2026-09-14 report](2026-09-14-forty-with-index.md) called search variance)
and loses nothing; ten cases are certified in all three runs of this call. Eleven cases are
certified in all three arms; the union of the three arms is fifteen.

## 2. Gained and lost against A, case by case

| arm | certified cases |
|---|---|
| A | `attrs-none_guard-14--forward`, `attrs-none_guard-15--forward`, `attrs-none_guard-17--forward`, `itsdangerous-boundary-07--forward`, `itsdangerous-guard_raise-05--forward`, `itsdangerous-guard_raise-06--forward`, `jinja-none_guard-14--forward`, `more-itertools-none_guard-17--forward`, `packaging-guard_raise-01--forward`, `python-dotenv-guard_raise-01--forward`, `urllib3-guard_raise-04--forward`, `urllib3-none_guard-15--forward` |
| B | `attrs-none_guard-14--forward`, `attrs-none_guard-15--forward`, `attrs-none_guard-17--forward`, `itsdangerous-boundary-07--forward`, `itsdangerous-guard_raise-04--forward`, `itsdangerous-guard_raise-05--forward`, `itsdangerous-guard_raise-06--forward`, `jinja-none_guard-14--forward`, `more-itertools-none_guard-17--forward`, `packaging-guard_raise-01--forward`, `python-dotenv-guard_raise-01--forward`, `python-dotenv-guard_raise-04--forward`, `urllib3-guard_raise-04--forward`, `urllib3-none_guard-15--forward` |
| C | `attrs-none_guard-14--forward`, `attrs-none_guard-15--forward`, `attrs-none_guard-17--forward`, `itsdangerous-boundary-07--forward`, `itsdangerous-guard_raise-05--forward`, `itsdangerous-guard_raise-06--forward`, `jinja-boundary-09--forward`, `jinja-none_guard-14--forward`, `packaging-guard_raise-01--forward`, `python-dotenv-guard_raise-01--forward`, `python-dotenv-guard_raise-04--forward`, `urllib3-guard_raise-04--forward`, `urllib3-none_guard-15--forward` |

| arm | gained against A | lost against A | net |
|---|---|---|---|
| B | `itsdangerous-guard_raise-04--forward`, `python-dotenv-guard_raise-04--forward` | none | +2 |
| C | `jinja-boundary-09--forward`, `python-dotenv-guard_raise-04--forward` | `more-itertools-none_guard-17--forward` | +1 |

The mechanism of each gain, read from the ledgers (the probe, what the merge base recorded, why the
receipt was accepted):

- **B gains `itsdangerous-guard_raise-04`** (the deleted guard in `TimestampSigner.unsign`). A bought
  three probes that all reached the changed lines and saw no difference. B's **first** probe,
  `signer.unsign(signed, max_age=10)` after building a `TimestampSigner` and a stale signature in its
  setup, recorded `BadTimeSignature` on the merge base and `TypeError` on head -- the guard's
  rejection against the crash its removal exposes -- and the receipt is a regression (head FAIL
  3/3, base PASS 3/3). `max_age=10` is the first literal the D-245 hint offers for this case
  (§3 of the 2026-09-14 report); it is in the probe. **Mechanism named.**
- **B and C both gain `python-dotenv-guard_raise-04`** (the deleted guard in `Reader.read_regex`,
  the case D-245 lost and D-246 repaired the callers for). Under all three arms the discovery
  context carries the four `reader.read_regex(...)` caller snippets. A's first probe still took the
  direct path, `reader.read_regex(_single_quoted_key)` on a `Reader` it built itself: the merge base
  raised `Error` (the guard's own rejection), head `AttributeError`, and no base test asserts that --
  the value class, as in the D-245 run. B's first probe and C's first probe both went in through the
  caller, `list(parse_stream(io.StringIO(...)))`: the merge base returned a binding list, head raised
  `AttributeError`, a crash receipt -- the same route the D-240 run certified through. **Mechanism
  named**, and it is the same in both thinking arms: the first probe chose the entry point the
  context showed rather than the changed method itself.
- **C gains `jinja-boundary-09`** (`<` → `<=` on `cur_depth < depth` in `get_template_locals`). A
  **never attempted a reproduction** on it -- discovery produced no eligible candidate, $0.0083,
  3 seconds -- so the arm's probe never ran and this gain is discovery's variance, not the
  probe's. C's third probe, `get_template_locals({"l_1_name": 13, "l_01_name": 99})`, sits on the
  depth boundary: the merge base returns `{'name': 13}`, head `{'name': 99}`, and the base tree's
  own tests pin the value. **Mechanism named, but not attributable to the arm.**
- **C loses `more-itertools-none_guard-17`** (A: `list(islice(mi.repeatfunc(f), 6))`, a regression
  receipt). C's three probes each recorded nothing usable: the observation was not stable on the
  merge base. Search variance.

## 3. The rule applied

- **Cost per certified case**: C $0.1534, B $0.2155, A $0.2260. **Rule 1 names C.**
- **B against A**: net +2 (two gained, none lost) is inside the ±2 jitter and decides nothing
  (rule 4); B is dearer than A ($3.0174 against $2.7116) and gains two, short of the three rule 2
  asks of a dearer arm -- **not the default**, though both gains have a named mechanism.
- **C against A**: net +1 is inside the jitter and decides nothing (rule 4); C is cheaper, so rule
  2 does not apply to it; its median wall clock, 20 s against A's 21 s, is far under rule 3's
  ceiling. **C is the rule's default**: the cheapest certified case, at recall the forty cannot tell
  apart from A's.
- What C's price is made of: its probe stage bought 62 calls and 30,143 output tokens -- 4.8× A's
  6,283, thinking included -- for $1.0017 against A's $1.7141, because the proposal model's tokens
  cost two fifths of the generation model's. C is cheaper per token, not thriftier with them; B,
  on the generation model, spends 3.2× A's output tokens for $2.0320.

**The reading.** The rule was written to be applied and it names C. What the forty add beyond the
rule: the one case both thinking arms gain and A does not, `python-dotenv-guard_raise-04`, has the
same mechanism in both -- the first probe chose the caller's entry point that the D-246 context
showed -- and B's other gain used the literal the hint offered; those are two nameable effects of
letting the probe think, each one case, each inside the jitter on its own. Whether the default
probe call moves to C is a product configuration change (the probe's model, thinking and output
bound) and the owner's; this report is the measurement the rule asked for.

## 4. What is and is not claimed

- Retrieval is the same in all three arms (D-246's repaired index); what differs is how the probe
  is asked for. A gain here is a gain of the search, not of the context.
- **No arm is shown to certify more than another.** 12, 14 and 13 of 40 are one re-run apart
  (AGENTS.md §9), and the gained cases are attributed case by case rather than by the count.
- **The boundary class is unmoved**: 1, 1 and 2 of 13 certified; the probes hit the boundary in 9,
  12 and 11 of 13, and the value class holds most of them as before (D-127/D-174).
- Not natural traffic; the forty are planted mutations. The real-PR batches are unmeasured under
  any thinking arm.
- The p95 reservation admitted every case in every arm from the study's whole history, which is the
  shipped call's; no arm approached its $5.00 cap (largest arm $3.0174) and none overshot.
