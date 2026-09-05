# The gate level in shadow: 10.7% can ever speak, 0 executed, and the one case §7 stops

**Owner instruction 2 of 2026-09-05c. D-137.** Reservation $12.00, **spent $0.588196**,
$11.4118 released. [Witness data](evidence/2026-09-05-gate-witness.json),
[replay data](evidence/2026-09-05-gate-replay.json), [live-run data](evidence/2026-09-05-gate-live.json).
Design: [`docs/design/gate-level.md`](../design/gate-level.md).

**Nothing on any path in this report is author-visible.** The output is `gate_shadow` ledger
rows and records under `.attest/shadow/gate/`. `ReviewConfig.gate_shadow` is off in the product.

## 1. The document conflict is closed

`G-NEWCODE-001` now carries a paragraph of its own: **the pilot precondition governs
author-visible speech, not observation**, and shadow records count toward its 120 adjudicated
cases. Mainline §1.3's gate row says the same and names the flag. Read **A with the carve-out**:
the design is N-01's first contract alternative, it ships early only in shadow, and the pilot's
defects are collected by the thing itself. `new_code_candidate` stays a typed abstention on
every author-visible path.

## 2. Free, and it is the number the design said it owed

The static witness over the **224 recorded new-code candidates** of E-04 stratum v2's 100 units.
No model call, no execution, no spend — it is read off the head trees with `git` and `ast`.

| | candidates | share |
|---|---|---|
| new-code candidates | 224 | |
| **(b)** every parameter annotated | 160 | 71.4% |
| **(a)** a call site outside the added lines | **24** | **10.7%** |
| admissible — (b) and ((a) or (c)) | 80 | 35.7% |

**10.7% is the ceiling on what this level can ever publish about new code in this traffic**,
because only the `through_caller` grade publishes and that grade needs a call site. The design
asked for this measurement first and said it would be cheap to learn if the level was not worth
building; it cost $0.00. The other 56 admissible candidates have a documented domain but no
caller, so they can reach `direct` at best — the drawer — and the stage buys them no
reproduction at all.

The reasons behind the 200 that fail are worth reading as a group: **`no call site outside the
added lines`** dominates, then **`takes no parameter: there is no domain to be inside`** (the
candidate is anchored on a test function), then **`unannotated parameter(s)`**.

## 3. The paid live run bought 13 attempts and executed none

10 units reached an attempt, 13 reproductions were generated, **every one DEFERred at
collection** — `reproduction timed out after 60s`, and again after the wall clock was raised to
300 s. **Executed gate observations: 0.**

This is the host fault documented in
[the independent null report §4](2026-09-05-g-null-001a-independent.md#4-the-host-fault-isolated):
every Docker bind mount of a path under `/Users/franz` hangs, while the same mount from
`/private/tmp` returns in 1.3 s and collects the very reproduction that timed out in 0.23 s.
Red's own path DEFERs identically. **The gate level's execution is implemented and unmeasured**,
and the static numbers above are not a substitute for it.

## 4. The replay carries the result, and it is free

The same adjudicator over the **53 recorded receipt bundles** in the corpora. A bundle's
`intent.json` already holds the three coordinates the gate needs — path, origin line, exception
type — and its `test_repro.py` holds the reproduction, so the question can be asked of evidence
already paid for.

| | receipts |
|---|---|
| replayed | 53 |
| admissible | 28 |
| `through_caller` | 20 |
| **would publish** | **4** (one finding under §5's cap) |

| clone | receipt | added line | exception | call site | verdict |
|---|---|---|---|---|---|
| `corum` | `38e5da0a9f` | `src/corum/models.py:47` | `OverflowError` | `src/corum/models.py:87` | **would publish** |
| `corum` | `7c88ff3d94` | `src/corum/models.py:47` | `OverflowError` | `src/corum/models.py:87` | **would publish** |
| `corum` | `a8a27ddfd7` | `src/corum/models.py:47` | `OverflowError` | `src/corum/models.py:87` | **would publish** |
| `corum` | `c25c7fbb4c` | `src/corum/models.py:47` | `OverflowError` | `src/corum/models.py:87` | **would publish** |
| `attest` | `2878d4012e` | `scripts/corpus/heldout_run.py:128` | `JSONDecodeError` | — | drawer |

The four publishers are one defect on one pair — `models.py:47`, all four candidates — and §5
caps a review at one gate finding, so this is **one** finding, not four. They are rows 8 and 9
of the [2026-09-05b adjudication](2026-09-05-value-class-adjudication.md), which read them by
hand as **real defects that clause (c) drawered**. The gate level recovers them without
consulting the direction of time, which is the whole reason it does not need a base revision.

**Two caveats the replay cannot remove.** It executes nothing, so the §3 environment control was
not run — the record says `replayed from a recorded bundle; no §3 control was executed` in the
control field rather than claiming one. And its origin comes from the recorded intent
observation rather than from fresh head runs.

## 5. `attest 2878d4012e` — the named case, and the clause that stops it

Its three coordinates: **`JSONDecodeError`**, the added line
**`scripts/corpus/heldout_run.py:128`**, and **no call site**. The added line is
`spent += float(json.loads(result_path.read_text()).get("spend_usd", 0.0))`, inside the
pre-existing `cmd_run(args: argparse.Namespace)`. (b) holds — the one parameter is annotated.
(a) does not: `cmd_run` is reached only through `argparse`'s `set_defaults(func=cmd_run)`
dispatch table, and the design's §7 excludes *"a call reached through a registry, a decorator or
a plugin table"*. The exclusion is doing exactly what it was written to do, and it costs this
level its first real new-code defect. **Pricing that trade is the owner's, and it is handoff
item 2.**

Two corrections to the instruction, both on the record:

- **Its pair is not in E-04 stratum v2.** That stratum is the 40 newest `Attest` commits at its
  2026-09-03T19:24Z freeze; `506aae1` is `2026-09-03 06:13 +0800`, about an hour older than the
  oldest of them. It ran as a **named supplementary unit**, reported apart from the 100.
- **It is a `regression` candidate, not a `new_code` one**, so the live stage — which exists for
  the candidates red never buys evidence for — would not have reached it in any case. The replay
  is the path that can ask the gate question of a receipt red drawered, and that is where it is.

## 6. What holds the level in shadow

Two structural tests, in `tests/test_gate_level.py`:

- `::test_no_author_visible_module_can_reach_the_gate_level` — none of `presentation.py`,
  `client.py`, `report.py`, `structural.py`, `ci.py`, `selection.py`, `types.py` may contain the
  string `gate_level`. If that test ever has to be edited, the level is no longer in shadow and
  `G-NEWCODE-001` applies in full.
- `::test_the_status_line_does_not_read_gate_rows` — `status_from_rows` dispatches on `kind`, and
  `gate_shadow` is not one of the kinds it reads, so a shadow row cannot move a number the author
  is shown.

Plus the design's own RED and its false-positive control, the two exclusions (§2.1 value
assertions, §2.3 deliberate `raise`), §1(b)'s abstention on an unannotated parameter, and §3's
run-agreement and environment-control rules — nine tests, all passing.
