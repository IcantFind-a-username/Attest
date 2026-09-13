# The index repair, 2026-09-14 — the two holes D-245 named, the callers the regex had, and the package block on real traffic

**0.3.0, the owner instruction of 2026-09-14 (after the forty under D-245).** Everything in this
report is free: `ast` and `git` over the forty case trees already rebuilt under
`.attest/corpora/mutations-v1-recall/` and over the clones of the three real-PR batches, no model
call, nothing bought. The two holes are the ones the [2026-09-14 report](2026-09-14-forty-with-index.md)
§4 and D-245 named on `python-dotenv-guard_raise-04`: the attribute rule counted a call on an
untyped receiver only from a file that *imports* the defining module, and the defining module never
imports itself; and a parameter annotated `reader: Reader` was a receiver the index could not type.
Both are repaired in D-246, with two more defects the free census below turned up. Sections 1 and 2
are the census over the forty; section 4 is the package block on the 68 real pull requests. Reproduce with `scripts/acceptance/index_repair_census.py`; the facts are
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

## 4. The package block's bound on real traffic: does it bind, and on what

**The first fact is that no measured run ever built the block.** `package_block` is called only
under `context_strategy = "package-cache"`, a comparison arm of owner instruction 4 (2026-09-03);
the shipped default is `r01`, and no `.attest.toml` in this repository or in any measured corpus
selects the other. So the forty under D-245, the three real-PR batches and every self-review ran
without a shared block, and D-245's ordering of it by import distance has run in no measured review.
Step 3's `package_block` field will read `null` until one does.

**The second is what the bound would do if the block were built.** For each of the 68 pull requests
of the three natural-traffic batches (`e05-external-v1` 24, `-v2` 20, `-v3` 24), on the clone at the
pull request's head, `package_block_report` was called on every file a review would have built the
block on -- the discovery anchor (the first planned unit's first file) and the anchored file of every
candidate that reached verification, read from the committed ledgers: 93 anchored files (48 pull
requests with one, 16 with two, 3 with three, 1 with four). *Bound hit* means at least one file the
order would have included did not fit under 120,000 characters (each file is itself cut at 40,000, so a
large package fits about three); *files cut* counts them; the last column names the cut files that
import the changed module, which are the ones the D-245 ordering exists to keep. Reproduce with
`scripts/acceptance/package_block_census.py`; the facts are in
[`evidence/2026-09-14-index-repair/package-block.json`](evidence/2026-09-14-index-repair/package-block.json).

| pull request | batch | anchored files (discovery, verified) | largest block, chars (bound 120,000) | bound hit | files cut | cut files that import the changed module |
|---|---|---|---|---|---|---|
| `more-itertools/more-itertools#1270` | v1 | `more_itertools/more.py`, `tests/test_more.py` | 80,319 | **yes** | 3 (0 source, 3 test) | — |
| `pallets/click#3861` | v1 | `src/click/core.py` | 111,702 | **yes** | 68 (8 source, 60 test) | `src/click/shell_completion.py`, `src/click/testing.py`, `src/click/types.py`, `tests/test_context.py`, `tests/test_defaults.py`, `tests/test_deprecations.py`, `tests/test_shell_completion.py` |
| `pallets/itsdangerous#406` | v1 | `src/itsdangerous/__init__.py` | 58,309 | no | — | — |
| `pallets/jinja#2099` | v1 | `scripts/generate_identifier_pattern.py`, `src/jinja2/_identifier.py` | 110,244 | **yes** | 44 (19 source, 25 test) | — |
| `pypa/packaging#611` | v1 | `tests/test_tags.py` | 113,387 | **yes** | 29 (0 source, 29 test) | — |
| `python-attrs/attrs#1606` | v1 | `tests/test_functional.py` | 109,975 | **yes** | 18 (0 source, 18 test) | — |
| `theskumar/python-dotenv#680` | v1 | `src/dotenv/main.py`, `src/dotenv/parser.py`, `tests/test_parser.py` | 96,680 | no | — | — |
| `urllib3/urllib3#5239` | v1 | `dummyserver/app.py` | 42,859 | no | — | — |
| `more-itertools/more-itertools#1266` | v1 | `more_itertools/more.py` | 80,319 | **yes** | 3 (0 source, 3 test) | — |
| `pallets/click#3858` | v1 | `src/click/types.py` | 115,180 | **yes** | 71 (11 source, 60 test) | `src/click/termui.py`, `tests/test_info_dict.py`, `tests/test_shell_completion.py` |
| `pallets/itsdangerous#405` | v1 | `src/itsdangerous/serializer.py` | 58,883 | no | — | — |
| `pallets/jinja#2098` | v1 | `src/jinja2/__init__.py` | 101,726 | **yes** | 44 (19 source, 25 test) | `src/jinja2/ext.py`, `src/jinja2/idtracking.py`, `src/jinja2/meta.py`, `src/jinja2/nativetypes.py`, `src/jinja2/optimizer.py`, `src/jinja2/parser.py`, `tests/conftest.py`, `tests/test_api.py`, `tests/test_async.py`, `tests/test_async_filters.py`, `tests/test_bytecode_cache.py`, `tests/test_compile.py`, `tests/test_core_tags.py`, `tests/test_debug.py`, `tests/test_ext.py`, `tests/test_filters.py`, `tests/test_idtracking.py`, `tests/test_inheritance.py`, `tests/test_lexnparse.py`, `tests/test_loader.py`, `tests/test_regression.py`, `tests/test_runtime.py`, `tests/test_security.py`, `tests/test_tests.py` |
| `pypa/packaging#1392` | v1 | `tests/test_ranges.py` | 111,634 | **yes** | 27 (0 source, 27 test) | — |
| `python-attrs/attrs#1603` | v1 | `src/attr/_make.py`, `tests/test_make.py` | 115,288 | **yes** | 32 (1 source, 31 test) | `src/attr/validators.py`, `tests/test_annotations.py`, `tests/test_dunders.py`, `tests/test_functional.py`, `tests/test_make.py`, `tests/test_next_gen.py`, `tests/utils.py` |
| `theskumar/python-dotenv#638` | v1 | `tests/test_main.py` | 61,090 | no | — | — |
| `urllib3/urllib3#5212` | v1 | `test/test_ssl.py` | 117,707 | **yes** | 31 (0 source, 31 test) | — |
| `more-itertools/more-itertools#1261` | v1 | `more_itertools/more.py` | 80,319 | **yes** | 3 (0 source, 3 test) | — |
| `pallets/click#3851` | v1 | `tests/test_types/test_Path.py` | 115,137 | **yes** | 50 (0 source, 50 test) | — |
| `pallets/itsdangerous#378` | v1 | `src/itsdangerous/signer.py`, `tests/test_itsdangerous/test_serializer.py` | 58,954 | no | — | — |
| `pallets/jinja#2096` | v1 | `src/jinja2/environment.py` | 108,281 | **yes** | 42 (17 source, 25 test) | `src/jinja2/ext.py`, `src/jinja2/filters.py`, `src/jinja2/lexer.py`, `src/jinja2/loaders.py`, `src/jinja2/meta.py`, `src/jinja2/nativetypes.py`, `src/jinja2/nodes.py`, `src/jinja2/optimizer.py`, `src/jinja2/parser.py`, `src/jinja2/runtime.py`, `src/jinja2/sandbox.py`, `src/jinja2/tests.py`, `src/jinja2/utils.py`, `tests/conftest.py`, `tests/test_compile.py`, `tests/test_imports.py` |
| `pypa/packaging#1384` | v1 | `src/packaging/specifiers.py` | 97,641 | **yes** | 52 (17 source, 35 test) | `src/packaging/metadata.py`, `src/packaging/pylock.py`, `src/packaging/ranges.py`, `src/packaging/requirements.py`, `tests/property/strategies.py`, `tests/property/test_ranges_cross_epoch.py`, `tests/property/test_ranges_pep440_extended.py`, `tests/property/test_ranges_pubgrub.py`, `tests/property/test_ranges_set_algebra.py`, `tests/property/test_ranges_set_relations.py`, `tests/property/test_ranges_to_specifier_set.py`, `tests/property/test_specifier_comparison.py`, `tests/property/test_specifier_extended.py`, `tests/property/test_specifier_implied.py`, `tests/property/test_specifier_matching.py`, `tests/property/test_version_releases.py`, `tests/test_metadata.py`, `tests/test_pylock.py`, `tests/test_pylock_select.py`, `tests/test_ranges.py`, `tests/test_requirements.py`, `tests/test_specifiers.py` |
| `python-attrs/attrs#1571` | v1 | `src/attr/validators.py` | 95,408 | **yes** | 35 (4 source, 31 test) | `tests/test_dunders.py`, `tests/test_funcs.py`, `tests/test_setattr.py`, `tests/test_validators.py` |
| `theskumar/python-dotenv#640` | v1 | `src/dotenv/parser.py`, `tests/test_parser.py` | 92,992 | no | — | — |
| `urllib3/urllib3#5221` | v1 | `src/urllib3/util/url.py`, `test/test_util.py` | 114,406 | **yes** | 63 (30 source, 33 test) | `src/urllib3/contrib/socks.py`, `src/urllib3/poolmanager.py`, `src/urllib3/util/__init__.py`, `src/urllib3/util/proxy.py`, `src/urllib3/util/ssl_.py` |
| `hukkin/tomli-w#79` | v2 | `tests/test_valid.py` | 10,674 | no | — | — |
| `pallets/markupsafe#499` | v2 | `src/markupsafe/__init__.py` | 24,139 | no | — | — |
| `pallets/werkzeug#3268` | v2 | `src/werkzeug/testapp.py` | 111,488 | **yes** | 78 (45 source, 33 test) | — |
| `psf/requests#7505` | v2 | `src/requests/models.py`, `tests/test_requests.py` | 105,896 | **yes** | 26 (11 source, 15 test) | `src/requests/cookies.py`, `src/requests/exceptions.py`, `src/requests/hooks.py`, `src/requests/sessions.py`, `src/requests/utils.py`, `tests/test_requests.py` |
| `python-jsonschema/jsonschema#1300` | v2 | `jsonschema/exceptions.py`, `jsonschema/tests/test_exceptions.py` | 108,055 | **yes** | 34 (20 source, 14 test) | `jsonschema/tests/test_cli.py`, `jsonschema/tests/test_deprecations.py`, `jsonschema/tests/test_exceptions.py`, `jsonschema/tests/test_format.py`, `jsonschema/tests/test_types.py`, `jsonschema/tests/test_validators.py`, `jsonschema/validators.py` |
| `hukkin/tomli-w#65` | v2 | `src/tomli_w/_writer.py` | 17,912 | no | — | — |
| `pallets/markupsafe#497` | v2 | `src/markupsafe/__init__.py` | 23,829 | no | — | — |
| `pallets/werkzeug#3267` | v2 | `src/werkzeug/datastructures/cache_control.py` | 118,454 | **yes** | 76 (42 source, 34 test) | — |
| `psf/requests#7502` | v2 | `src/requests/models.py`, `tests/test_requests.py` | 105,896 | **yes** | 26 (11 source, 15 test) | `src/requests/cookies.py`, `src/requests/exceptions.py`, `src/requests/hooks.py`, `src/requests/sessions.py`, `src/requests/utils.py`, `tests/test_requests.py` |
| `python-jsonschema/jsonschema#1482` | v2 | `jsonschema/_utils.py` | 109,122 | **yes** | 31 (17 source, 14 test) | `jsonschema/tests/test_utils.py` |
| `hukkin/tomli-w#70` | v2 | `src/tomli_w/__init__.py` | 17,912 | no | — | — |
| `pallets/markupsafe#496` | v2 | `setup.py` | 39,129 | no | — | — |
| `pallets/werkzeug#3266` | v2 | `src/werkzeug/wrappers/response.py`, `tests/middleware/test_proxy_fix.py`, `tests/test_test.py` | 108,380 | **yes** | 79 (45 source, 34 test) | `src/werkzeug/routing/exceptions.py`, `src/werkzeug/test.py`, `src/werkzeug/testapp.py`, `src/werkzeug/utils.py`, `src/werkzeug/wrappers/__init__.py` |
| `psf/requests#7497` | v2 | `src/requests/models.py` | 103,118 | **yes** | 26 (11 source, 15 test) | `src/requests/cookies.py`, `src/requests/exceptions.py`, `src/requests/hooks.py`, `src/requests/sessions.py`, `src/requests/utils.py`, `tests/test_requests.py` |
| `python-jsonschema/jsonschema#1444` | v2 | `jsonschema/exceptions.py` | 97,033 | **yes** | 28 (14 source, 14 test) | `jsonschema/tests/test_cli.py`, `jsonschema/tests/test_deprecations.py`, `jsonschema/tests/test_exceptions.py`, `jsonschema/tests/test_format.py`, `jsonschema/tests/test_types.py`, `jsonschema/tests/test_validators.py`, `jsonschema/validators.py` |
| `hukkin/tomli-w#69` | v2 | `src/tomli_w/_writer.py` | 17,912 | no | — | — |
| `pallets/markupsafe#469` | v2 | `src/markupsafe/__init__.py` | 22,849 | no | — | — |
| `pallets/werkzeug#3255` | v2 | `src/werkzeug/http.py` | 112,612 | **yes** | 73 (39 source, 34 test) | `src/werkzeug/datastructures/structures.py`, `src/werkzeug/debug/__init__.py`, `src/werkzeug/exceptions.py`, `src/werkzeug/formparser.py`, `src/werkzeug/middleware/http_proxy.py`, `src/werkzeug/middleware/lint.py`, `src/werkzeug/middleware/proxy_fix.py`, `src/werkzeug/middleware/shared_data.py`, `src/werkzeug/sansio/http.py`, `src/werkzeug/sansio/multipart.py`, `src/werkzeug/sansio/request.py`, `src/werkzeug/sansio/response.py`, `src/werkzeug/sansio/utils.py`, `src/werkzeug/serving.py`, `src/werkzeug/test.py`, `src/werkzeug/wrappers/response.py`, `tests/test_datastructures.py`, `tests/test_http.py`, `tests/test_send_file.py`, `tests/test_utils.py`, `tests/test_wrappers.py` |
| `psf/requests#7498` | v2 | `src/requests/models.py` | 103,451 | **yes** | 26 (11 source, 15 test) | `src/requests/cookies.py`, `src/requests/exceptions.py`, `src/requests/hooks.py`, `src/requests/sessions.py`, `src/requests/utils.py`, `tests/test_requests.py` |
| `python-jsonschema/jsonschema#1416` | v2 | `jsonschema/benchmarks/import_benchmark.py`, `jsonschema/tests/test_validators.py`, `jsonschema/validators.py` | 119,955 | **yes** | 36 (22 source, 14 test) | `jsonschema/protocols.py`, `jsonschema/tests/_suite.py`, `jsonschema/tests/test_cli.py`, `jsonschema/tests/test_deprecations.py`, `jsonschema/tests/test_exceptions.py`, `jsonschema/tests/test_format.py`, `jsonschema/tests/test_types.py`, `jsonschema/tests/test_validators.py`, `jsonschema/tests/typing/test_all_concrete_validators_match_protocol.py` |
| `Delgan/loguru#1510` | v3 | `loguru/_logger.py`, `tests/exceptions/source/modern/exception_formatting_async_generator_throw.py` | 117,751 | **yes** | 158 (6 source, 152 test) | — |
| `mahmoud/boltons#481` | v3 | `boltons/cacheutils.py`, `boltons/jsonutils.py`, `tests/test_cacheutils.py`, `tests/test_namedutils.py` | 116,951 | **yes** | 58 (27 source, 31 test) | `tests/test_cacheutils.py`, `tests/test_jsonutils.py` |
| `marshmallow-code/marshmallow#3034` | v3 | `src/marshmallow/fields.py` | 118,474 | **yes** | 24 (5 source, 19 test) | `tests/base.py`, `tests/foo_serializer.py`, `tests/mypy_test_cases/test_schema.py`, `tests/test_context.py`, `tests/test_decorators.py`, `tests/test_deserialization.py`, `tests/test_fields.py`, `tests/test_options.py`, `tests/test_registry.py`, `tests/test_schema.py`, `tests/test_serialization.py`, `tests/test_utils.py` |
| `pyparsing/pyparsing#653` | v3 | `pyparsing/helpers.py`, `tests/test_unit.py` | 117,636 | **yes** | 26 (12 source, 14 test) | `tests/test_pre_pep8_deprecation_warnings.py` |
| `python-babel/babel#1318` | v3 | `babel/messages/catalog.py`, `tests/messages/test_pofile_write.py` | 100,490 | **yes** | 91 (24 source, 67 test) | `babel/messages/__init__.py`, `babel/messages/checkers.py`, `babel/messages/frontend.py`, `babel/messages/mofile.py`, `babel/messages/pofile.py`, `tests/messages/test_catalog.py`, `tests/messages/test_checkers.py`, `tests/messages/test_pofile.py` |
| `tkem/cachetools#413` | v3 | `tests/__init__.py` | 104,078 | no | — | — |
| `Delgan/loguru#1504` | v3 | `loguru/_string_parsers.py`, `tests/test_filesink_rotation.py` | 119,359 | **yes** | 157 (6 source, 151 test) | — |
| `mahmoud/boltons#434` | v3 | `boltons/timeutils.py` | 106,556 | **yes** | 54 (23 source, 31 test) | `tests/test_timeutils.py` |
| `marshmallow-code/marshmallow#3004` | v3 | `src/marshmallow/fields.py` | 118,468 | **yes** | 24 (5 source, 19 test) | `tests/base.py`, `tests/foo_serializer.py`, `tests/mypy_test_cases/test_schema.py`, `tests/test_context.py`, `tests/test_decorators.py`, `tests/test_deserialization.py`, `tests/test_fields.py`, `tests/test_options.py`, `tests/test_registry.py`, `tests/test_schema.py`, `tests/test_serialization.py`, `tests/test_utils.py` |
| `pyparsing/pyparsing#645` | v3 | `pyparsing/results.py`, `tests/test_unit.py` | 117,636 | **yes** | 24 (10 source, 14 test) | `tests/test_pre_pep8_deprecation_warnings.py` |
| `python-babel/babel#1319` | v3 | `babel/messages/frontend.py` | 92,050 | **yes** | 89 (22 source, 67 test) | `babel/messages/setuptools_frontend.py`, `tests/interop/test_jinja2_interop.py`, `tests/messages/frontend/test_cli.py`, `tests/messages/frontend/test_compile.py`, `tests/messages/frontend/test_concat.py`, `tests/messages/frontend/test_extract.py`, `tests/messages/frontend/test_frontend.py`, `tests/messages/frontend/test_init.py`, `tests/messages/frontend/test_merge.py`, `tests/messages/test_setuptools_frontend.py`, `tests/messages/test_toml_config.py` |
| `tkem/cachetools#386` | v3 | `tests/test_tlru.py` | 93,969 | no | — | — |
| `Delgan/loguru#1508` | v3 | `loguru/_datetime.py`, `tests/test_datetime.py` | 119,546 | **yes** | 156 (5 source, 151 test) | — |
| `mahmoud/boltons#475` | v3 | `tests/test_strutils.py` | 117,035 | **yes** | 20 (0 source, 20 test) | — |
| `marshmallow-code/marshmallow#3024` | v3 | `src/marshmallow/utils.py` | 109,249 | **yes** | 22 (3 source, 19 test) | `tests/test_utils.py` |
| `pyparsing/pyparsing#649` | v3 | `tests/test_unit.py` | 119,559 | **yes** | 1 (0 source, 1 test) | — |
| `python-babel/babel#1161` | v3 | `tests/messages/frontend/test_concat.py` | 108,046 | **yes** | 54 (0 source, 54 test) | — |
| `tkem/cachetools#365` | v3 | `src/cachetools/func.py` | 107,637 | no | — | — |
| `Delgan/loguru#1507` | v3 | `tests/test_datetime.py` | 118,633 | **yes** | 40 (0 source, 40 test) | — |
| `mahmoud/boltons#467` | v3 | `boltons/statsutils.py`, `tests/test_statsutils.py` | 118,776 | **yes** | 54 (23 source, 31 test) | `tests/test_statsutils.py`, `tests/test_statsutils_histogram.py` |
| `marshmallow-code/marshmallow#3016` | v3 | `tests/test_validate.py` | 87,887 | **yes** | 11 (0 source, 11 test) | — |
| `pyparsing/pyparsing#648` | v3 | `tests/test_unit.py` | 119,559 | **yes** | 1 (0 source, 1 test) | — |
| `python-babel/babel#1291` | v3 | `babel/dates.py` | 92,729 | **yes** | 87 (22 source, 65 test) | `babel/messages/catalog.py`, `babel/support.py`, `babel/util.py`, `tests/benchmarks/benchmark_dates.py`, `tests/messages/frontend/test_cli.py`, `tests/messages/frontend/test_extract.py`, `tests/messages/frontend/test_init.py`, `tests/messages/test_catalog.py`, `tests/messages/test_checkers.py`, `tests/test_date_intervals.py`, `tests/test_dates.py`, `tests/test_day_periods.py`, `tests/test_smoke.py` |
| `tkem/cachetools#340` | v3 | `src/cachetools/__init__.py` | 99,473 | no | — | — |
| **68 pull requests** | | | | **49 hit the bound** | | **29 cut an importer** |

|  | v1 (24) | v2 (20) | v3 (24) | all (68) |
|---|---|---|---|---|
| bound hit | 17 | 12 | 20 | **49** |
| a cut file imports the changed module | 8 | 10 | 11 | **29** |
| never hit | 7 | 8 | 4 | 19 |

Block sizes over the 93 anchored files: smallest 10,674 characters, median 105,896, largest 119,955.
The 19 that never hit are the small packages -- `tomli-w` (4 of 4), `markupsafe` (4), `cachetools`
(4), `itsdangerous` (3), `python-dotenv` (3) and one `urllib3` pull request whose anchor sits in a
small subpackage; every pull request of the nine larger libraries hits it, `click` and `werkzeug`
cutting 68 to 79 files each.

**Reading.**

- **The lever has had no chance to act, and not because the bound is slack.** Under the shipped
  strategy the block is never built, so on every measured corpus the D-245 ordering cannot have
  produced a difference; that is the sentence the owner asked for, and it holds for a reason the
  instruction did not anticipate. Were the strategy switched on, the bound would bind on 49 of 68
  real pull requests and, even ordered by import distance, cut a file that imports the changed
  module on 29 of 68 -- on a large package the distance-one files alone exceed three files' worth
  -- so the ordering would then decide *which* importers survive rather than whether any does.
- **No paid measurement is scheduled for it.** Switching `package-cache` on is a cost decision (a
  block near 100k characters cached per review, on every sample and generation) and an owner item;
  under `r01` there is nothing to measure. If the owner ever turns it on, the `package_block` field
  of the plan row (step 3) says on each review what was cut, without this census.
- **One defect in the block itself, for the backlog, not fixed here:** when a project's tests live
  inside the package (`jsonschema/tests/`), `package_block` lists them twice -- once under the
  package walk and once under the tests walk -- and a file that fits is added twice, spending the
  bound on a copy; the cut lists above show the duplicates.
