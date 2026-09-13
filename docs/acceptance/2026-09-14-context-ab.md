# The context A/B, 2026-09-14 — the same forty, old context against new: 12 and 12

**D-247's own experiment, dispatched on the owner's "跑" of 2026-09-14 after the cumulative cap was
raised to $160.** Two dispatches of `mutation-recall.yml` from `feat/call-path-to-the-first-probe`,
the same forty trials, **$1.00 per case, K=5, `linux-container-v1`, the local review path, read-only
clones, nothing written anywhere**, each admitted at the D-244 p95 reservation ($0.1035 per case)
and capped by the driver at $5.00, dispatched one at a time and settled in
[DEVSPEND](../../DEVSPEND.md) before the next. **Only the first probe's hint differs**
(`ProbeCall.include_routes`, recorded in every trial row); model, budget, K, verification count,
certification, intent and publication rules are the shipped ones in both. Runs
[34766961021](https://github.com/IcantFind-a-username/Attest/actions/runs/34766961021) (`old`) and
[34767960012](https://github.com/IcantFind-a-username/Attest/actions/runs/34767960012) (`new`);
**$5.738869** of the $10.00 reserved; 40 of 40 cases ran in both arms and none was refused.

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
