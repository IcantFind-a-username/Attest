# The value-class note in shadow: 4 on 780 control rows, 29 on 391 defect rows

**Owner authorisation of 2026-09-11**, §16 item 2: implement the yellow line for a
value-class observation, **shadow only** — write the ledger row, render the line, post it
nowhere. Recorded as D-218. Whether an author ever sees it is tomorrow's decision, and this
document is the evidence it rests on.

**Free by construction.** No model, no container, no network, no spend. The census reads the
ledgers already on this machine and replays the rule over the rows in them
([`scripts/corpus/value_note_census.py`](../../scripts/corpus/value_note_census.py),
[data](evidence/2026-09-11-value-note-census.json)).

## 1. The one sentence

On populations with **no defect in them** the rule fires **4 times in 780 verification rows**,
all four on one arm and three distinct units; on the held-out defect corpus it fires **29 times
in 391 rows** across **19 of 62** cases. The noise floor is not zero and it is not large.

## 2. The census

| arm | what it is | case ledgers | verification rows | **notes** | renderable | units with ≥1 |
|---|---|---|---|---|---|---|
| **held-out control** | SWE-bench cases with no defect (docs-only, test-only) | 48 | 17 | **0** | 0 | 0 |
| **null control** | `G-NULL-001a`'s populations, public clones, no known defect | 8 | 399 | **4** | 3 | 3 |
| **us-stock-helper** | the owner's own repository, real history | 1 | 342 | **0** | 0 | 0 |
| **corum** | a third-party clone, real history | 1 | 22 | **0** | 0 | 0 |
| **control total** | | 58 | **780** | **4** | 3 | 3 |
| held-out defect | SWE-bench cases carrying a reverted gold patch | 62 | 391 | **29** | 14 | **19** |
| this repository | Attest reviewing its own pull requests | 1 | 305 | **2** | 1 | 1 |

**Read the denominators.** A ledger accumulates over every run ever made against that case,
under several policy versions — 22 of the 35 notes were written under
`attest.intent.v4.1`, 12 under v4.2 and 1 under v2. **A rate per run cannot be read out of
this table**, and none is quoted. What can be read is that the rule is not silent on defects
and is nearly silent on controls.

**"Renderable" is smaller than "notes" and that is the point.** A line needs *what head
produced*, and until D-216 the head observation was never recorded: for the rows already on
disk the census recovers it from the failing assertion's left-hand side, and where the run
carried neither the row is counted and marked unrenderable rather than dropped (D-177). Under
D-216 the head observation is recorded on every probe, so **new** rows are renderable by
construction, and `note_from` refuses to build a note without it.

## 3. Every control-arm line, rendered

Four notes, three units. These are the lines an author would have seen, verbatim.

| unit | coordinate | expression | base → head |
|---|---|---|---|
| `click` | `src/click/core.py` | `group.resolve_command(ctx, ["instal", "--flag"])` | raised `UsageError` → raises `NoSuchCommand` |
| `click` (a second run of the same case) | `src/click/core.py` | the same call | the same pair |
| `itsdangerous` | `tests/test_itsdangerous/test_serializer.py:16` | `mod.coerce_str("str", b"abc")` | raised `AttributeError` → returns `None` |
| `more-itertools` | `more_itertools/more.py:15` | *(the probe row predates `probe_observation`; unrenderable)* | — |

Two observations that matter for the decision.

- **The `click` pair is one fact counted twice.** The same case was reviewed twice and both
  ledgers hold it. Counted as rows it is 2 of 4; counted as units it is 1 of 3. A
  deduplication rule on `(path, expression)` is not in this implementation and would be worth
  one if the level ever ships.
- **`itsdangerous` anchors inside `tests/`.** The changed file is a test module, so the note
  would point an author at their own test. That is a real limitation of the anchor and not of
  the rule; it is the same anchor the red channel would use.

## 4. The other two arms, from their own frozen evidence

Neither has ledgers on this machine, so both are read from the committed run records rather
than recomputed.

| population | n | notes the rule would write |
|---|---|---|
| **forward pairs**, `K=5`, 2026-09-10 ([evidence](evidence/2026-09-10-forward-pairs-k5.json)) | 11 pairs, 26 attempted reproductions | **3** (`value_class_drawered`) |
| **E-04 stratum v3, the runner arm** — 28 real pull requests of the owner's own repositories ([report](2026-09-13-e04-shadow-v3.md)) | 28 units, 13 reproductions that executed | **3** (`behavior_changes_intent_unknown`) |

The E-04 number is the one that answers *what would a real week of traffic look like*: **3
notes over 28 pull requests**, on a population with no planted defect. The rendered lines are
not recoverable — that run's ledgers were runner artifacts and are not on this machine — so
this row is a count and is not quoted as anything else.

## 5. What is claimed, and what is not

**Claimed.** The rule fires 4 times over 780 control verification rows here, 3 times over 11
forward pairs, and 3 times over 28 real pull requests. Every line it renders is admitted by
the output contract (`tests/test_value_note.py::test_the_line_is_one_admissible_contract_line`).

**Not claimed.**

- **Not a precision figure.** A control-arm note is not necessarily wrong: `click`'s
  `UsageError` → `NoSuchCommand` is a real behaviour change that a reviewer might want to
  know about. Nothing here adjudicates whether these four are worth an author's attention —
  that is exactly the question the owner is being asked.
- **Not a rate.** See §2: the ledgers are cumulative over runs and policy versions.
- **Not that the red channel changes.** D-127, D-132, D-134 and D-174 are untouched; every
  one of these differentials is still drawered and still publishes nothing.
- **Not shipped.** `ci.py` does not import the module, and
  `tests/test_value_note.py::test_nothing_in_the_publication_path_imports_this_module`
  checks the import graph rather than trusting the sentence above.

## 6. The decision this supports

Three shapes the owner could take, in the order of how much they claim:

1. **Leave it in shadow.** Costs nothing, buys nothing, keeps the rows accumulating so the
   next window has a larger census.
2. **Author-visible on forward traffic only**, i.e. a real pull request rather than a
   reversed corpus. On the numbers here that is ~3 lines per 28 pull requests.
3. **Author-visible everywhere.** Not recommended without a deduplication rule for the
   `click` shape and a decision about notes anchored inside `tests/`.

**Cost: $0.00.**
