# The index repair, 2026-09-14 — the two holes D-245 named, the callers the regex had, and the package block on real traffic

**0.3.0, the owner instruction of 2026-09-14 (after the forty under D-245).** Everything in this
report is free: `ast` and `git` over the forty case trees already rebuilt under
`.attest/corpora/mutations-v1-recall/` and over the clones of the three real-PR batches, no model
call, nothing bought. The two holes are the ones the [2026-09-14 report](2026-09-14-forty-with-index.md)
§4 and D-245 named on `python-dotenv-guard_raise-04`: the attribute rule counted a call on an
untyped receiver only from a file that *imports* the defining module, and the defining module never
imports itself; and a parameter annotated `reader: Reader` was a receiver the index could not type.
Both are repaired in D-246, with two more defects the free census below turned up. Sections 1 and 2
are the census over the forty; section 4, the package block on the 68 real pull requests, is added by
the step that computes it. Reproduce with `scripts/acceptance/index_repair_census.py`; the facts are
in [`evidence/2026-09-14-index-repair/census.json`](evidence/2026-09-14-index-repair/census.json).

## 1. The two holes, and what the forty say before and after

### 1a. The repair (D-246)

- **(a) The defining module is its own importer.** `callers_of` adds the defining module's own
  file to the set of importers, so a call on an untyped receiver inside that file counts at the
  attribute level, as it would from any file that imports the module.
- **(b) A parameter annotated with an in-tree class is a typed receiver.** `def f(reader: Reader)`
  then `reader.x()` resolves to `module:Reader.x` at the exact level, whether `Reader` is defined in
  the same module or bound by a `from` import. Only a bare-name annotation is read; `Optional[Reader]`,
  a quoted forward reference, a dotted `mod.Reader`, the return annotation and a `self.attr`
  annotation are on the *still not found* list in D-246.
- **(c) A typed receiver whose class does not itself define the method falls back to the attribute
  rule.** Found by the census (§1c): `conn: HTTPSConnection` then `conn.set_tunnel(...)` resolved to
  `HTTPSConnection.set_tunnel`, which no class defines -- the method is `HTTPConnection`'s,
  inherited -- and the caller D-245 had counted at the attribute level vanished under (b). Such a call
  is treated as an untyped receiver from a file that imports (or is) the defining module. The same
  fallback catches a call through a package re-export (`dotenv.set_key(...)` for `dotenv.main:set_key`)
  from a file that imports the defining module, at the attribute level.
- **(d) A module's top-level names are known before its body is read.** Found by the census (§1c):
  `rewrite_traceback_stack` calls `get_template_locals`, defined further down `debug.py`, and D-245
  dropped the call because it had not yet seen the definition. A same-module call now resolves exact
  whichever way round the file is written.

Four REDs: `tests/test_planner.py::test_a_call_inside_the_defining_module_on_an_untyped_receiver_is_a_caller`
(a, through `run_review` -- the caller snippet reaches the prompt),
`tests/test_index.py::test_a_parameter_annotated_with_an_in_tree_class_is_a_typed_receiver` (b, both
bindings in one test), `::test_a_typed_receiver_whose_class_inherits_the_method_is_still_a_caller` (c),
`::test_a_same_module_call_made_before_the_definition_is_exact` (d). The index schema is
`attest.tree-index.v2`, so every cached index is rebuilt once.

### 1b. The census over the forty

For every case, on its rebuilt tree at the recorded head: the caller snippets `plan_review` puts in the
discovery context under the regex planner D-245 replaced, under D-245 as measured (`main` at
`a16312a`), and under the repair; and, per finding of the D-245 run, the call sites the index resolves
for the changed definitions by level. The regex and D-245 columns reproduce the two runs' ledgers to
the snippet (76 and 34), so the repaired column is the number the next run would carry, not an estimate.
A plan holds at most 4 caller snippets per symbol (`MAX_CALLERS_PER_SYMBOL`); the index count is
uncapped.

| case | stratum | regex plan | D-245 plan | repaired plan | index D-245 exact / attribute | index repaired exact / attribute | omissions D-245 → repaired |
|---|---|---|---|---|---|---|---|
| `attrs-boundary-09--forward` | boundary | 0 | 0 | 0 | 0 / 0 | 0 / 0 | none → none |
| `click-boundary-07--forward` | boundary | 1 | 1 | 1 | 2 / 1 | 2 / 1 | none → none |
| `itsdangerous-boundary-07--forward` | boundary | 4 | 1 | 3 | 1 / 8 | 1 / 10 | 8 further test reference(s) omitted → 8 further test reference(s) omitted |
| `jinja-boundary-09--forward` | boundary | 1 | 0 | 1 | 1 / 0 | 2 / 0 | none → none |
| `more-itertools-boundary-08--forward` | boundary | 1 | 1 | 1 | 1 / 0 | 1 / 0 | none → none |
| `packaging-boundary-08--forward` | boundary | 1 | 1 | 1 | 2 / 0 | 2 / 0 | none → none |
| `python-dotenv-boundary-06--forward` | boundary | 1 | 1 | 1 | 1 / 0 | 1 / 0 | none → none |
| `urllib3-boundary-07--forward` | boundary | 0 | 0 | 0 | 10 / 0 | 10 / 0 | none → none |
| `attrs-guard_raise-03--forward` | guard_raise | 1 | 1 | 1 | 9 / 0 | 9 / 0 | none → none |
| `click-boundary-10--forward` | boundary | 0 | 1 | 2 | 2 / 4 | 2 / 5 | none → none |
| `itsdangerous-guard_raise-01--forward` | guard_raise | 4 | 0 | 0 | 4 / 0 | 4 / 0 | none → none |
| `jinja-boundary-12--forward` | boundary | 1 | 1 | 1 | 1 / 0 | 2 / 0 | none → none |
| `more-itertools-boundary-10--forward` | boundary | 1 | 1 | 1 | 1 / 0 | 1 / 0 | none → none |
| `packaging-boundary-11--forward` | boundary | 1 | 0 | 0 | 11 / 0 | 11 / 0 | none → none |
| `python-dotenv-boundary-08--forward` | boundary | 1 | 1 | 1 | 2 / 0 | 2 / 0 | none → none |
| `urllib3-guard_raise-03--forward` | guard_raise | 1 | 1 | 1 | 1 / 0 | 1 / 0 | none → none |
| `attrs-none_guard-14--forward` | none_guard | 2 | 0 | 0 | 0 / 0 | 0 / 0 | 44 further test reference(s) omitted → 44 further test reference(s) omitted |
| `click-guard_raise-03--forward` | guard_raise | 4 | 4 | 4 | 4 / 0 | 4 / 0 | none → none |
| `itsdangerous-guard_raise-04--forward` | guard_raise | 4 | 1 | 3 | 2 / 16 | 2 / 20 | 8 further test reference(s) omitted → 8 further test reference(s) omitted |
| `jinja-guard_raise-01--forward` | guard_raise | 3 | 1 | 2 | 5 / 0 | 6 / 0 | none → none |
| `more-itertools-guard_raise-04--forward` | guard_raise | 3 | 0 | 0 | 0 / 0 | 0 / 0 | 2 further test reference(s) omitted → 2 further test reference(s) omitted |
| `packaging-guard_raise-01--forward` | guard_raise | 4 | 0 | 0 | 9 / 0 | 9 / 0 | none → none |
| `python-dotenv-guard_raise-01--forward` | guard_raise | 1 | 1 | 1 | 1 / 0 | 1 / 11 | 2 further test reference(s) omitted → 2 further test reference(s) omitted |
| `urllib3-guard_raise-04--forward` | guard_raise | 2 | 1 | 1 | 25 / 4 | 25 / 5 | none → none |
| `attrs-none_guard-15--forward` | none_guard | 0 | 0 | 0 | 7 / 0 | 7 / 0 | none → none |
| `click-guard_raise-05--forward` | guard_raise | 4 | 4 | 4 | 4 / 0 | 4 / 0 | none → none |
| `itsdangerous-guard_raise-05--forward` | guard_raise | 4 | 1 | 3 | 1 / 8 | 1 / 10 | 8 further test reference(s) omitted → 8 further test reference(s) omitted |
| `jinja-none_guard-13--forward` | none_guard | 2 | 1 | 1 | 1 / 0 | 1 / 0 | none → none |
| `more-itertools-guard_raise-05--forward` | guard_raise | 4 | 2 | 2 | 2 / 0 | 2 / 0 | 1 further test reference(s) omitted → 1 further test reference(s) omitted |
| `packaging-guard_raise-06--forward` | guard_raise | 4 | 0 | 2 | 3 / 0 | 3 / 2 | none → none |
| `python-dotenv-guard_raise-02--forward` | guard_raise | 1 | 1 | 1 | 2 / 0 | 2 / 0 | none → none |
| `urllib3-none_guard-15--forward` | none_guard | 0 | 0 | 0 | 37 / 0 | 37 / 0 | none → none |
| `attrs-none_guard-17--forward` | none_guard | 0 | 0 | 0 | 2 / 0 | 2 / 0 | none → none |
| `click-none_guard-15--forward` | none_guard | 1 | 1 | 1 | 1 / 0 | 1 / 0 | none → none |
| `itsdangerous-guard_raise-06--forward` | guard_raise | 4 | 1 | 3 | 1 / 8 | 1 / 10 | 8 further test reference(s) omitted → 8 further test reference(s) omitted |
| `jinja-none_guard-14--forward` | none_guard | 1 | 1 | 1 | 1 / 0 | 1 / 0 | none → none |
| `more-itertools-none_guard-17--forward` | none_guard | 2 | 0 | 0 | 0 / 0 | 0 / 0 | none → none |
| `packaging-none_guard-13--forward` | none_guard | 2 | 2 | 2 | 3 / 0 | 3 / 0 | none → none |
| `python-dotenv-guard_raise-04--forward` | guard_raise | 4 | 0 | 4 | 1 / 0 | 13 / 0 | none → 8 further caller(s) of read_regex omitted |
| `urllib3-none_guard-18--forward` | none_guard | 1 | 1 | 1 | 67 / 8 | 67 / 8 | none → none |
| **the forty** | | **76** | **34** | **51** | **228 / 57** | **243 / 82** | |

**Reading.**

- **34 → 51 caller snippets over the forty** (the regex had 76; §2 says what the other 25 were).
  Nine plans changed, all upward; no plan lost a snippet. The discovery context grew from 120,131 to
  125,472 characters over the forty (the regex era: 133,553). **Of the 17 snippets added, 11 are real
  callers and 6 are noise rule (a) admits** -- a same-named call on an untyped receiver anywhere in
  the defining module: `environ.update(self.env)` on a dict in the module that defines `ProgressBar`
  (`click-boundary-10`), `super().unsign(signed_value)` inside the changed override itself (the four
  `itsdangerous` cases; it reaches `Signer.unsign`, not the change), and `cls._from_dict(d)` in
  `DirectUrl.from_dict` (`packaging-guard_raise-06`). The eleven: the four `reader.read_regex(...)`
  snippets of `python-dotenv-guard_raise-04`; `signer.unsign(s, max_age=..., return_timestamp=True)` in
  `TimedSerializer.loads`, the entry point to the changed `TimestampSigner.unsign` (four cases, by
  rule (a)); `bucket.write_bytecode(f)` in `FileSystemBytecodeCache.dump_bytecode`, typed
  `bucket: Bucket` (rule (b)); `get_template_locals(...)` in `rewrite_traceback_stack` (rule (d));
  and `target_type._from_dict(value)` in `direct_url._get_object`, which `DirectUrl._from_dict`
  calls with `ArchiveInfo` (rule (a)). The 34 the D-245 run already carried are not re-judged here.
- **`python-dotenv-guard_raise-04`: 0 → 4**, the owner's acceptance condition for this step. The index
  resolves all thirteen `reader.read_regex(...)` calls of `parser.py` (twelve on the annotated
  parameter, one in `parse_stream`) at the exact level -- 1 / 0 → 13 / 0 -- and the plan carries four
  with *8 further caller(s) of read_regex omitted*, the same four snippets and the same omission the
  regex era had; the discovery context is 1,975 characters as it was under D-240 (837 under D-245).
- **Index-level, over the findings of the forty: 228 / 57 → 243 / 82 exact / attribute.** The
  attribute-level gain is mostly (a) and (c); `python-dotenv-guard_raise-01` (`set_key`) gains eleven
  attribute callers in `tests/test_main.py` through (c)'s re-export fallback, which the planner
  reports separately as test references and never as caller snippets.
- **Nothing here is recall.** These are retrieval counts on trees already on disk; whether a fuller
  context moves a verdict is the next paid run's question, and §9 of AGENTS.md says one re-run moves
  about ±2 on its own.

### 1c. What the census found and the repair took in

The first pass of the repair -- (a) and (b) alone -- left two of the regex era's snippets out that
the reading in §2 showed to be real callers:

- `src/urllib3/connectionpool.py:1068`, `conn.set_tunnel(...)` in `HTTPSConnectionPool._prepare_proxy`,
  `conn: HTTPSConnection`. `HTTPSConnection` inherits `set_tunnel` from `HTTPConnection`, the changed
  class (`urllib3-guard_raise-04`). D-245 counted it at the attribute level (the file imports
  `urllib3.connection`); rule (b) typed it as `HTTPSConnection.set_tunnel`, which nothing defines, and
  lost it. Rule (c) is the fix, and the case is back at 1 snippet, now 25 / 5 at the index level.
- `src/jinja2/debug.py:94`, `get_template_locals(tb.tb_frame.f_locals)` in `rewrite_traceback_stack`,
  defined at line 14 while the changed `get_template_locals` (`jinja-boundary-09`) is defined at line
  131. D-245's same-module rule saw definitions in file order and dropped the call. Rule (d) is the
  fix, and the case goes 0 → 1.

Both are in the repaired column above and in D-246 with their REDs. Nothing else in the 33-snippet
difference of the first pass was a caller (§2).

## 2. The regex-era snippets the repaired index does not give: noise or signal

The D-240 run's plans carried 76 caller snippets; the D-245 run's 34. The question is what the 42 were.
Read from the same trees: every snippet the regex planner puts in a plan whose call line the repaired
index does not report as a caller of the changed symbols -- **31 snippets** after the repair (33 before
1c's two fixes), each listed with the line the regex matched and what the repaired index makes of that
line. Not sampled; every one is read.

| # | case | site | symbol | the line | judgement | why |
|---|---|---|---|---|---|---|
| 1 | `attrs-none_guard-14--forward` | `src/attr/_make.py:2905` | `define` | `'define()' decorators.` | **noise** | prose in a docstring (`define()` in a sentence); no call |
| 2 | `attrs-none_guard-14--forward` | `src/attr/_next_gen.py:578` | `define` | `attribute -- regardless of the setting in 'define()'.` | **noise** | prose in a docstring; no call |
| 3 | `itsdangerous-boundary-07--forward` | `src/itsdangerous/serializer.py:339` | `unsign` | `return self.load_payload(signer.unsign(s))` | **cannot tell** | `signer` comes from `iter_unsigners`, built from `self.signer` / `default_signer`; `Serializer`'s default is `Signer`, not the changed `TimestampSigner`, and `TimedSerializer` (default `TimestampSigner`) overrides `loads`, so this line reaches the changed method only for a `Serializer` constructed with `signer=TimestampSigner` -- a construction-time fact no static index has |
| 4 | `itsdangerous-boundary-07--forward` | `src/itsdangerous/signer.py:263` | `unsign` | `self.unsign(signed_value)` | **noise** | `Signer.validate` calling its own `unsign`; `TimestampSigner` overrides `validate` (timed.py:160), so this line runs only on a plain `Signer` and reaches `Signer.unsign` |
| 5 | `itsdangerous-guard_raise-01--forward` | `src/itsdangerous/exc.py:15` | `__init__` | `super().__init__(message)` | **noise** | an exception class's `super().__init__`; the changed `__init__` is `Signer`'s |
| 6 | `itsdangerous-guard_raise-01--forward` | `src/itsdangerous/exc.py:26` | `__init__` | `super().__init__(message)` | **noise** | same |
| 7 | `itsdangerous-guard_raise-01--forward` | `src/itsdangerous/exc.py:47` | `__init__` | `super().__init__(message, payload)` | **noise** | same |
| 8 | `itsdangerous-guard_raise-01--forward` | `src/itsdangerous/exc.py:81` | `__init__` | `super().__init__(message, payload)` | **noise** | same |
| 9 | `itsdangerous-guard_raise-04--forward` | `src/itsdangerous/serializer.py:339` | `unsign` | `return self.load_payload(signer.unsign(s))` | **cannot tell** | `signer` comes from `iter_unsigners`, built from `self.signer` / `default_signer`; `Serializer`'s default is `Signer`, not the changed `TimestampSigner`, and `TimedSerializer` (default `TimestampSigner`) overrides `loads`, so this line reaches the changed method only for a `Serializer` constructed with `signer=TimestampSigner` -- a construction-time fact no static index has |
| 10 | `itsdangerous-guard_raise-04--forward` | `src/itsdangerous/signer.py:263` | `unsign` | `self.unsign(signed_value)` | **noise** | `Signer.validate` calling its own `unsign`; `TimestampSigner` overrides `validate` (timed.py:160), so this line runs only on a plain `Signer` and reaches `Signer.unsign` |
| 11 | `itsdangerous-guard_raise-05--forward` | `src/itsdangerous/serializer.py:339` | `unsign` | `return self.load_payload(signer.unsign(s))` | **cannot tell** | `signer` comes from `iter_unsigners`, built from `self.signer` / `default_signer`; `Serializer`'s default is `Signer`, not the changed `TimestampSigner`, and `TimedSerializer` (default `TimestampSigner`) overrides `loads`, so this line reaches the changed method only for a `Serializer` constructed with `signer=TimestampSigner` -- a construction-time fact no static index has |
| 12 | `itsdangerous-guard_raise-05--forward` | `src/itsdangerous/signer.py:263` | `unsign` | `self.unsign(signed_value)` | **noise** | `Signer.validate` calling its own `unsign`; `TimestampSigner` overrides `validate` (timed.py:160), so this line runs only on a plain `Signer` and reaches `Signer.unsign` |
| 13 | `itsdangerous-guard_raise-06--forward` | `src/itsdangerous/serializer.py:339` | `unsign` | `return self.load_payload(signer.unsign(s))` | **cannot tell** | `signer` comes from `iter_unsigners`, built from `self.signer` / `default_signer`; `Serializer`'s default is `Signer`, not the changed `TimestampSigner`, and `TimedSerializer` (default `TimestampSigner`) overrides `loads`, so this line reaches the changed method only for a `Serializer` constructed with `signer=TimestampSigner` -- a construction-time fact no static index has |
| 14 | `itsdangerous-guard_raise-06--forward` | `src/itsdangerous/signer.py:263` | `unsign` | `self.unsign(signed_value)` | **noise** | `Signer.validate` calling its own `unsign`; `TimestampSigner` overrides `validate` (timed.py:160), so this line runs only on a plain `Signer` and reaches `Signer.unsign` |
| 15 | `jinja-guard_raise-01--forward` | `src/jinja2/bccache.py:122` | `write_bytecode` | `bucket.write_bytecode(f)` | **noise** | inside the module docstring's example cache implementation -- a string, not code |
| 16 | `jinja-none_guard-13--forward` | `src/jinja2/environment.py:1321` | `generate` | `return TemplateStream(self.generate(*args, **kwargs))` | **noise** | `Template.generate`; the changed `generate` is the module-level function of compiler.py |
| 17 | `more-itertools-guard_raise-04--forward` | `more_itertools/more.py:257` | `first` | `>>> first([0, 1, 2, 3])` | **noise** | a doctest example inside the changed function's own docstring; not a call site in code |
| 18 | `more-itertools-guard_raise-04--forward` | `more_itertools/more.py:257` | `first` | `>>> first([0, 1, 2, 3])` | **noise** | a doctest example inside the changed function's own docstring; not a call site in code |
| 19 | `more-itertools-guard_raise-04--forward` | `more_itertools/recipes.py:566` | `first` | `yield first()` | **noise** | `first` is a parameter of `iter_except(func, exception, first=None)`, a local name |
| 20 | `more-itertools-guard_raise-05--forward` | `more_itertools/more.py:284` | `last` | `>>> last([0, 1, 2, 3])` | **noise** | a doctest example inside the changed function's own docstring |
| 21 | `more-itertools-guard_raise-05--forward` | `more_itertools/more.py:284` | `last` | `>>> last([0, 1, 2, 3])` | **noise** | a doctest example inside the changed function's own docstring |
| 22 | `more-itertools-none_guard-17--forward` | `more_itertools/recipes.py:324` | `repeatfunc` | `>>> list(repeatfunc(add, times, *args))` | **noise** | a doctest example inside the changed function's own docstring |
| 23 | `more-itertools-none_guard-17--forward` | `more_itertools/recipes.py:332` | `repeatfunc` | `>>> take(6, repeatfunc(randrange, times, *args))  # doctest:+SKIP` | **noise** | a doctest example inside the changed function's own docstring |
| 24 | `packaging-boundary-11--forward` | `src/packaging/version.py:629` | `__lt__` | `return super().__lt__(other)` | **noise** | `Version.__lt__` deferring to `_BaseVersion.__lt__`; the changed one is `BoundaryVersion.__lt__` in `_ranges.py` |
| 25 | `packaging-guard_raise-01--forward` | `src/packaging/_tokenizer.py:35` | `__init__` | `super().__init__()` | **noise** | an unrelated class's `super().__init__`; the changed `__init__` is `ELFFile`'s |
| 26 | `packaging-guard_raise-01--forward` | `src/packaging/dependency_groups.py:52` | `__init__` | `super().__init__(` | **noise** | same |
| 27 | `packaging-guard_raise-01--forward` | `src/packaging/direct_url.py:152` | `__init__` | `super().__init__("Missing required value", context=key)` | **noise** | same |
| 28 | `packaging-guard_raise-01--forward` | `src/packaging/metadata.py:58` | `__init__` | `super().__init__(message)` | **noise** | same |
| 29 | `packaging-guard_raise-06--forward` | `src/packaging/pylock.py:206` | `_from_dict` | `return target_type._from_dict(value)` | **noise** | a generic `type[_FromMappingProtocolT]` over pylock's own dataclasses; pylock.py never imports direct_url, whose `ArchiveInfo._from_dict` changed |
| 30 | `packaging-guard_raise-06--forward` | `src/packaging/pylock.py:220` | `_from_dict` | `typed_item = target_item_type._from_dict(item)` | **noise** | same |
| 31 | `urllib3-guard_raise-04--forward` | `src/urllib3/connectionpool.py:91` | `set_tunnel` | `# This value is sent to 'HTTPConnection.set_tunnel()' if called` | **noise** | a comment |

|  | snippets |
|---|---|
| noise -- a same-named call on an unrelated object, a docstring, a doctest, a comment, a local name | **27** |
| a real caller | **0** (the two the first pass had left out are repaired in 1c and are no longer in this list) |
| cannot tell statically | **4** (one site, `serializer.py:339`, under the four `itsdangerous` cases) |

**Reading.** The 42 is the net of two capped counts, 76 and 34, not a set of snippets. Set by set,
on the same trees: of the 76 snippets the regex planner put in the forty's plans, the D-245 index
reported **33** as callers of the changed symbols and did not report **43**. The repair reports **12**
of those 43 -- **7 real callers** (`get_template_locals` in `debug.py`, `bucket.write_bytecode` in
`bccache.py`, `_get_object`'s `target_type._from_dict` in `direct_url.py`, and four `reader.read_regex`
lines of `parser.py`) and **5 noise** it admits with them (`super().unsign` inside the override, four
cases; `cls._from_dict` in `DirectUrl.from_dict`) -- and the **31** above it still does not report are
**27 noise and 4 undecidable**. So of the 43 the D-245 index had dropped, 7 were signal and are back,
32 were noise, and 4 are one line no static index can decide. Six of the noise rows are doctest
examples in the changed function's own docstring: not callers, but inputs the tree documents, which
the D-245 literals hint does not read; that is an observation, not a proposal. Two more
(`bccache.py:122`, `_make.py:2905`) are code inside strings. The regex's 76 were 40 signal-or-plausible
(33 the index confirms and 7 it now restores) and 36 noise-or-undecidable, with the signal capped at
four per symbol and the rest named in an omission; the repaired plans' 51 carry those, eleven more
real callers the regex era never had in a plan, and six noise snippets named in §1b.
