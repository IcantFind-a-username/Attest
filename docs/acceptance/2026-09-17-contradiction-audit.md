# P-05, 2026-09-17 — the contradiction audit, made real: observe without perturbing, and re-check what you found

**Owner instruction of 2026-09-17 ("先做一").** P-04 found that a repository's own statements are
clean enough to trust and that the instrument was not: wrapping module attributes changed what it
measured. This round replaces the instrument, scales the audit to eight libraries, and adds the
step that turns a finding into evidence: replaying only the tests that produced it.

No model, no paid spend, no product change, nothing pushed. Instruments:
`scripts/probe/contradiction_audit.py`, `contradiction_verify.py`. Records:
[`evidence/2026-09-17-contradiction-audit/`](evidence/2026-09-17-contradiction-audit/).

## 0. The answers

| asked | result |
|---|---|
| can the repository be observed without changing it | **yes**: `sys.monitoring` delivers return events for registered code objects and rebinds nothing. Seven libraries ran twice, clean and observed, and **every pass, fail, skip and xfail count is identical** |
| what does the audit yield | **630 checkpoints registered, 567 exercised, 5 contradictions** across 8 libraries: **0.9% of exercised checkpoints, about 1.8 per 1,000 functions** |
| can a finding be re-checked | **yes**: replaying only the recorded test nodes reproduced **4 of 5 exactly and the fifth in part** (the record keeps at most five nodes, and the sixth carried the missing type) |

## 1. The instrument, and the proof it did not interfere

P-04 wrapped module attributes. jinja's suite went from 911 passed to 910 passed and 1 failed,
because `pickle` notices that `jinja2.filters.do_capitalize` is no longer the object the module
holds. The audit now registers code objects with `sys.monitoring` (PEP 669) and receives a
`PY_RETURN` event for those alone; the repository's own function objects are untouched, and
nothing in the tree is written.

Each library ran twice. The counts are the proof:

| library | clean | observed | registered | exercised | return events |
|---|---|---|---:|---:|---:|
| click | 33,058 passed, 25 skipped, 1 xfailed | identical | 245 | 211 | 1,979,492 |
| packaging | 62,860 passed, 1 skipped | identical | 188 | 181 | 8,877,273 |
| jinja | 911 passed | identical | 144 | 127 | 94,124 |
| itsdangerous | 297 passed | identical | 22 | 21 | 12,324 |
| python-dotenv | 247 passed, 5 failed, 1 skipped | identical | 21 | 17 | 2,262 |
| attrs | 1,382 passed, 19 failed, 10 skipped, 1 xfailed | identical | 10 | 10 | 26,278 |
| more-itertools | 748 passed, 1 failed | identical | 0 | 0 | 0 |
| urllib3 | **timed out at 30 minutes, both runs** | — | — | — | — |

urllib3's suite starts its own servers and did not finish in either run, so its row proves
nothing either way; it is counted as unaudited, not as clean. The pre-existing failures in
attrs, python-dotenv and more-itertools are the libraries' own, identical on both sides.

## 2. The five contradictions

A contradiction is a function whose own signature declares a return type that the value it
returned is not, after three exemptions (§3).

| library | site | declares | returned | replay |
|---|---|---|---|---|
| attrs | `attr.__getattr__` | `str` | `module` ×1, `VersionInfo` ×2 | reproduced exactly |
| jinja | `jinja2.filters.do_join` | `str` | `list` ×28, `int` ×10 | reproduced in part (`list`) |
| jinja | `jinja2.runtime.Macro._invoke` | `str` | `list` ×1 | reproduced exactly |
| jinja | `jinja2.runtime.Macro.__call__` | `str` | `list` ×1 | reproduced exactly |
| jinja | `jinja2.runtime.BlockReference.__call__` | `str` | `int` ×1 | reproduced exactly |

Each is a statement the repository makes about itself, contradicted by the repository's own test
suite. None is a crash, and the audit does not claim any is a defect: what it claims is that the
signature and the behaviour disagree, and that a reader can see it again in one command.

## 3. Three exemptions, all properties of the language

Without them the count would be 26 rather than 5, and the difference is noise, not findings:

- **A generator or coroutine function is not observed.** Its return event carries the value
  handed to `StopIteration`, not the value the caller receives. 129 functions across the eight.
- **A returned coroutine or generator is deferred, not wrong.** A synchronous function returning
  an awaitable is how a library offers an async mode; jinja does this 182 times.
- **`NotImplemented` is the comparison protocol.** packaging's rich comparisons return it 298,457
  times, correctly, under signatures that read `-> bool`.

## 4. Re-checking a finding

`contradiction_verify.py` replays, for one finding, only the test nodes the audit recorded, with
the monitor narrowed to that one site, and compares what it sees with what was recorded. Each
record carries the library, the revision, the site, the declared type, the observed types, the
nodes and a digest, plus the command a reader can run:

```
cd <repo> && ATTEST_ONLY='jinja2.runtime.Macro.__call__' ATTEST_PACKAGE=jinja2 \
  ../.venv/bin/python -m pytest -q -p attest_audit tests/test_regression.py::...
```

Four reproduced exactly. `do_join` reproduced in part: the audit caps the recorded nodes at five,
and the `int` return came from a sixth test. That is a property of the record, not of the
finding, and raising the cap fixes it.

## 5. What this is, and what it is not

**It is** a repository-level audit that needs no pull request, no second revision and no model:
it reads what the repository declares, runs the repository's own workload, and reports the places
where the two disagree, with a replay for each. The noise floor is 0.9% of exercised checkpoints,
and after the three exemptions every survivor was a real disagreement.

**It is not** defect discovery. P-04 already measured that: checkpoints of this kind caught 1 of
25 planted defects and localised none, because the statements are type-shaped and the defects are
value-shaped. Nor is it language-general in the way the kernel is: a compiler for a typed
language rejects this class before it runs, so the yield here is a property of Python.

**Limits.** Eight libraries, one revision each, the workload being each library's own suite; a
function no test calls is registered and never exercised (63 of 630). The rule reads builtin
shapes and optionals of them, not generics, protocols or forward references. urllib3 did not
finish. Severity is not judged: `attr.__getattr__` returning a `VersionInfo` under a `-> str`
signature is a narrower annotation than the function's contract, while `do_join` returning a
`list` under `-> str` is closer to a real inconsistency, and this audit does not tell them apart.
