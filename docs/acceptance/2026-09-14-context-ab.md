# The context A/B, 2026-09-14 — the same forty, old context against new: 12 and 12

**D-247's own experiment, dispatched on the owner's "跑" of 2026-09-14 after the cumulative cap was
raised to $160.** Two dispatches of `mutation-recall.yml` from `feat/call-path-to-the-first-probe`,
the same forty trials, **$1.00 per case, K=5, `linux-container-v1`, the local review path, read-only
clones, nothing written anywhere**, each admitted at the D-244 p95 reservation ($0.1035 per case)
and capped by the driver at $5.00, dispatched one at a time and settled in
[DEVSPEND](../../DEVSPEND.md) before the next. **Only the first probe's hint differs**
(`ProbeCall.include_routes`, recorded in every trial row); the probe call itself is the **shipped**
one in both arms -- `claude-opus-5`, thinking disabled, 1,500 output tokens -- and so are the models,
budget, K, verification count, certification, intent and publication rules (§0). Arm `C` of the
probe-arms run was **not** adopted: switching the default probe call is an owner decision that has
not been taken. Runs
[34766961021](https://github.com/IcantFind-a-username/Attest/actions/runs/34766961021) (`old`) and
[34767960012](https://github.com/IcantFind-a-username/Attest/actions/runs/34767960012) (`new`);
**$5.738869** of the $10.00 reserved; 40 of 40 cases ran in both arms and none was refused.

## 0. The configuration both arms ran, and which earlier figures share it

An earlier draft of this report left this out, and it is what decides whether this 12 and the
earlier ones are the same yardstick. Read from the 40 trial rows of each arm (one distinct
`probe_call` per arm) and from the `review_run` rows of the eight ledgers:

| | both arms |
|---|---|
| probe call | **`claude-opus-5`, thinking disabled, 1,500 output tokens** — the shipped call, arm `A` of the D-246 step-5 vocabulary |
| proposal model | `claude-sonnet-5` (the shipped `default_model`) |
| reproduction generator | `claude-opus-5` (the shipped `generation_model`) |
| K, budget, alpha | 5, $1.00 per case, 0.1 |
| corpus | the frozen forty of `mutations-v1-recall`, rebuilt, not re-drawn |
| difference between the arms | `include_routes` only, recorded in every trial row |

**Arm `C` of the probe-arms run was not adopted.** The rule of that run named it on cost per
certified case, and switching the default probe call is an owner decision that has not been taken:
no pull request, no configuration change, and `ProbeCall`'s defaults are untouched. **These two arms
are therefore not comparable with that run's B (14) and C (13)**, which asked a different probe
call (adaptive thinking at effort medium, 8,000 output tokens, and for C a different model).

What *is* comparable is the series that holds the probe call fixed and varies the retrieval:

| run | probe call | retrieval / context | certified of 40 |
|---|---|---|---|
| D-240 run (2026-09-13) | shipped | callers by regex, before the tree index | 12 |
| D-245 run (2026-09-14) | shipped | the tree index as introduced | 11 |
| probe arms, arm `A` (2026-09-14) | shipped | the index repaired (D-246) | 12 |
| **context A/B, arm `old`** | shipped | the same, D-247's routes **off** | **12** |
| **context A/B, arm `new`** | shipped | the same, D-247's routes **on** | **12** |

The last two are the tightest pair in the table: one build of the code, one switch apart, and their
hints differ on 39 of 40 cases only in `_asserted_block`'s revision label. Arm `old` against arm `A`
of the probe-arms run is the next tightest — same probe call, same index, different day — and both
are 12. The D-240 and D-245 figures share the probe call but not the retrieval, so they belong in
this column and not in a claim about D-247.

## 1. The two arms

| | arm `old` (the hint before D-247) | arm `new` (with the routes and the merge-base specification) |
|---|---|---|
| certified of 40 | **12** | **12** |
| Wilson 95% | [18.1%, 45.4%] | [18.1%, 45.4%] |
| boundary certified of 13 | 1 | 1 |
| value class | 17 | 18 |
| no receipt | 10 | 10 |
| no reproduction attempted | 1 | 0 |
| probes that recorded on the merge base | 33 | 33 |
| probes that made the revisions differ | 33 | 33 |
| spend | $2.7407 | $2.9982 |
| probe stage (D-243) | $1.7422 | $1.9929 |
| median wall clock per case | 21 s | 22 s |

**Net 0**: one case gained, one lost. Under the pre-registered rule that is inside the ±2 a re-run
moves on its own (AGENTS.md §9) and decides nothing by itself, so both movements are read case by
case below. The old arm's 12 is also the third consecutive 12 for this call on this corpus (12, 12,
11 before it), which is the yardstick the new arm is read against.

## 2. The two cases that moved, and why

### `python-dotenv-guard_raise-04` — certified in `old`, value class in `new`

This is the case the routes block was built for, and the block lost it.

| | probe the arm chose | merge base | head | outcome |
|---|---|---|---|---|
| `old` | `list(parse_stream(io.StringIO('KEY="abc\n')))` | a binding list | `AttributeError` | **certified** (head FAIL 3/3, base PASS 3/3) |
| `new` | `reader.read_regex(_single_quoted_key)` on a `Reader` it built | `Error` | `AttributeError` | **value class** (no base test pins the value) |

What the new arm's hint offered:

```text
Routes into `Reader`, `read_regex` (head revision; the merge base decides what a call does):
1. `parse_key` -> `(key,) = reader.read_regex(_single_quoted_key)` (src/dotenv/parser.py:117)
2. `parse_key` -> `(key,) = reader.read_regex(_unquoted_key)` (src/dotenv/parser.py:119)
No test of the merge base names: `parse_key`, `Reader`, `read_regex` ...
```

The probe copied the first route almost verbatim. **The route is real and the block is truthful; it
is the wrong route.** `read_regex`'s nearest callers are `parse_key`'s two call sites, one hop up,
and nothing in the merge base specifies `parse_key`; the entry the merge base does specify,
`parse_stream`, is **two hops** up, which D-247 states it does not look for. The old arm, told
nothing, found `parse_stream` by itself. So the block did not fail to deliver — it delivered a
nearer route than the one the model would otherwise have found, and the nearer route is the one the
certification rule cannot use.

### `urllib3-none_guard-15` — value class in `old`, certified in `new`

| | probe the arm chose | merge base | head | outcome |
|---|---|---|---|---|
| `old` | `h.__ror__(5)` | `NotImplemented` (a value) | the merged dict | value class |
| `new` | `5 \| h` | `TypeError` | the merged dict | **certified** |

The difference is the call's *form*: the operator raises on the merge base where the dunder returns
`NotImplemented`, and a base test pins the `TypeError`. **This gain is not the block's.** What the
block offered for this case was:

```text
Routes into `HTTPHeaderDict`, `__ror__` (head revision; ...):
1. `request` -> `headers = HTTPHeaderDict(headers)` (src/urllib3/_request_methods.py:124)
2. `request_encode_body` -> `extra_kw: ... = {"headers": HTTPHeaderDict(headers)}` (...:254)
What the merge base specifies about these routes:
- test/contrib/emscripten/test_emscripten.py::test_pool_no_port (merge base): ...
```

Two constructor calls of the enclosing class and an emscripten test that calls
`HTTPConnectionPool`: nothing about `__ror__`, the changed method. The same case recorded the same
observation in both arms of the D-246 arms run under the same forms, so this is the search's own
variance, as the 2026-09-14 arms report §4 also found for it.

## 3. What this measures, and the two defects it found

**The evidence chain is repaired and the measurement says so**: in the new arm a route was resolved
in 34 of 40 cases and a merge-base specification quoted in 36, all of it reaching the request the
probe answers, at +4.1% of the request's size. **Recall did not move**: 12 and 12, and neither
movement is the block's doing.

The experiment's value is the two defects it exposes, both in *which* material the block selects,
not in whether it arrives:

1. **The nearest route is not the specified route, and the block prefers the nearest.** Selecting
   one hop is what put `parse_key` in front of the model instead of `parse_stream`. A route the
   merge base specifies is worth more than a route that is nearer, and the block currently cannot
   express that preference because it never looks past one hop.
2. **The specification is matched against the changed symbols *and* their enclosing class, so an
   unrelated test can be quoted as "what the merge base specifies about these routes".** A test that
   calls `HTTPHeaderDict(...)` says nothing about `__ror__`; quoting it puts a false lead where the
   hint promises a specification. The match should require the *changed definition* or the entry
   point of a route actually shown, not any name in the set.

Both are free to repair and free to re-measure offline for content; whether a repair moves a verdict
is another paid run of this same design, which is not authorised and not scheduled.

## 4. What is and is not claimed

- **No recall or precision claim.** 12 and 12 on a forty-case corpus of planted mutations, with the
  intervals overlapping entirely; the one gain and the one loss are attributed above and neither is
  the block's.
- **The chain is repaired**, and that is a claim about the request's contents, measured free on the
  forty: 34 routes resolved, 36 specifications quoted, +4.1% request size, `include_routes` in every
  trial row.
- The old arm is not byte-identical to the pre-D-247 hint: over the forty the two differ on 39 of 40
  cases **only** in `_asserted_block`'s revision label, and the `literals_hint` the ledger records is
  identical on 40 of 40.
- Not natural traffic. The three real-PR batches are unmeasured under D-246 and D-247 alike.
- Cost: $5.738869 of $10.00 reserved; no arm approached its $5.00 cap and none overshot.
