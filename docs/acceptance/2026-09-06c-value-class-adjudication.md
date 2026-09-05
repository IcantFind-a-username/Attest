# The 15 value-class drawers, adjudicated by hand — 2026-09-06c

Owner instruction 1 of this window, and the owner's default from the 2026-09-06b handoff §5.1:
**adjudicate a sample of the 15 by hand before touching the rule.** The sample is all fifteen.

D-146's probe generator removed the generation wall (unfaithful reproductions 20 → 0) and moved
the bottleneck onto `attest.intent.v4.1`, whose value-class drawers went **1 → 15** on the same
eleven forward pairs while certifications did not move. Every one of those fifteen is a *real*
head/base difference — three head runs failed and three base runs passed, and the expectation was
recorded from the base tree, not written by a model — that the product refuses to publish.

**Free: `$0.00`.** The receipts are recorded; this is reading, `git show` and `ast`.
[Data](evidence/2026-09-06b-forward-pairs-probe.json) ·
[the run](2026-09-06b-forward-pairs-probe.md) · ledger: `.attest/corpora/gnull/click/.attest/`.

## 0. The verdict, first

| | count |
|---|---|
| **真缺陷** — head introduced a defect the receipt would have caught | **0** |
| **有意变更** — head changed the behaviour on purpose, and says so | **15** |
| **无法判断** — the evidence does not settle it | **0** |

**x / y / z = 0 / 15 / 0.** The threshold for "write a page of analysis and candidate fixes"
was ≥ 8 真缺陷; it is not met, and no fix is proposed. §3 says what the number does and does not
license.

## 1. What the fifteen are

All fifteen sit on **two of the eleven pairs**, both `click`, and both were drawered by the same
clause: **`intent: intent stated in the change itself` — the same change also updates a test, a
docstring, documentation, a changelog entry or an inline comment about the symbol under test**
(D-132's clause (c), narrowed by D-134). No other clause fired on any of them; no other pair
produced a value-class candidate at all.

- `click cd4674a6de` (base `d5fbd32842`), **8 drawers** — a *"Merge Main into Stable (#3442)"*
  commit: 39 files, 3,418 insertions, 98 lines of `CHANGES.rst`.
- `click 19fd4d6e18` (base `c69643b60c`), **7 drawers** — *"Fix broken fish completion and
  multiline help string"*.

**Ten of the fifteen are the same function**, `FishComplete.format_completion`, which the second
commit rewrote and the first merged: the fish completion protocol moved from one line
(`type,value\thelp`) to three (`type\nvalue\nhelp`, with `_` for absent help). Ten different
probe inputs — a newline in the value, a tab in the help, a literal backslash-n, a newline in the
`type`, two items at once — all observe the same protocol change.

## 2. The fifteen, one row each

`base` is what the probe **recorded** by executing the expression on the merge base three times;
`head` is what the same expression produced on head, three times. Neither was written by a model.

| # | finding | anchor | the diff changed | probe recorded on base | head | clause | verdict | why |
|---|---|---|---|---|---|---|---|---|
| 1 | `8acfb19648` | `_textwrap.py` `_wrap_chunks` | width is measured in **visible** characters; ANSI escapes no longer count (`:pr:`3420``) | `['\x1b[31m…\x1b', '[32m…\x1b[', '33m…xxx', 'xxxxxxxxxx', 'xxxxxxx']` — base breaks the line **inside** an escape sequence | one chunk of escapes + 10 x's, then the rest | (c) | **有意变更** | `CHANGES.rst` documents it and `tests/test_formatting.py` names `_handle_long_word`; base's split mid-escape is the bug head fixes |
| 2 | `bc47e8bc29` | `shell_completion.py` `format_completion` | the fish protocol, 1 line → 3 | `'plain,line1\nline2\thelp line1\nhelp line2'` | `'plain\nline1\\nline2\nhelp line1\\nhelp line2'` | (c) | **有意变更** | the commit's own subject; `CHANGES.rst`: *"Fix Fish shell completion errors when option help text contains newlines"* |
| 3 | `d650c11347` | `_compat.py` `should_strip_ansi` | new `elif hasattr(stream, "color"): return False`, with an inline comment saying why | `True` | `False` | (c) | **有意变更** | the branch, the comment and `tests/test_compat.py::test_should_strip_ansi` are all in the diff. The duck-typing hazard the model named is real and is *the change*, not a regression |
| 4 | `f0c5f9607d` | `formatting.py` `write_usage` | early return when `args` is empty | `'\n'` — base emits **only a blank line** | `'Usage: prog\n'` | (c) | **有意变更** | `CHANGES.rst`: *"Fix `HelpFormatter.write_usage` emitting only a blank line when called without `args`"*. Base was wrong; head is the fix |
| 5 | `ad115e73f1` | `shell_completion.py` `_is_incomplete_argument` | `assert param.name is not None` deleted | raises `AssertionError` | returns normally | (c) | **有意变更** | a deliberate assert removal, visible in the diff. Note the probe reached it only by setting `param.name = None` *after* construction — a state `click` never builds (§4) |
| 6 | `492d6c7ed7` | `core.py` `Parameter.consume_value` | a `default_map` string is split for `nargs > 1` | `('hello world', DEFAULT_MAP)` | `(['hello', 'world'], DEFAULT_MAP)` | (c) | **有意变更** | `CHANGES.rst`: *"Split string values from `default_map` for parameters with `nargs > 1`"* — the change is the documented feature |
| 7 | `71ae755dea` | `exceptions.py` `NoSuchOption.format_message` | `"No such option: {name}"` → `"No such option {name!r}."` | `('No such option: --foo', '… (Possible options: --bar, --food)')` | `("No such option '--foo'.", …"Did you mean '--food'?")` | (c) | **有意变更** | a message reword plus a "did you mean"; `CHANGES.rst` names `NoSuchCommand` and the tests move with it |
| 8 | `0a4cebf482` | `format_completion` | as #2 | `'plain,foo'` | `'plain\nfoo\n_'` | (c) | **有意变更** | the `_` sentinel for absent help, mirroring `ZshComplete`, stated in the new docstring |
| 9 | `457771a1e8` | `format_completion` | as #2 (on the pair that made the change) | `'pl\nain,val\nue\tline1\nline2 and literal \\n token'` | three newline-separated fields with `\n` escaped | (c) | **有意变更** | same |
| 10 | `8397d3f1d5` | `format_completion` | as #2 | `'plain,a\nb\tline1\nline2'` | `'plain\na\\nb\nline1\\nline2'` | (c) | **有意变更** | same |
| 11 | `155ef5b6b8` | `format_completion` | as #2 | `'plain,C:\\path\\n\tline1\nline2 and literal \\n here'` | three fields, backslashes untouched | (c) | **有意变更** | same. The model's point — a literal `\n` in the text is now ambiguous with an escaped newline — is a *live design question about the new protocol*, not a regression from base |
| 12 | `50c92eacb6` | `format_completion` | as #2 | `'plain,val\tue\tline1\tline2\nline3'` | `'plain\nval\tue\nline1\tline2\\nline3'` | (c) | **有意变更** | same |
| 13 | `aaab2e272a` | `format_completion` | as #2, two items at once | `['plain,--at', 'plain,--other\tNormal help']` | `['plain\n--at\n_', 'plain\n--other\nNormal help']` | (c) | **有意变更** | same |
| 14 | `d9da8ab508` | `format_completion` | as #2 | `'plain,value\nwith-newline\tline one\nline two'` | three fields, newlines escaped | (c) | **有意变更** | same |
| 15 | `eae3dab7a5` | `format_completion` | as #2, newline in `type` | `'pl\nain,value\nwith newline\thelp\nline2'` | three fields; `type` is **not** escaped | (c) | **有意变更** | same. `type` staying unescaped is a real edge in the new protocol, and it is new-code behaviour, not a regression |

## 3. What the 0/15/0 licenses, and what it does not

**It licenses leaving the clause alone.** On these two commits the clause is right fifteen times
out of fifteen, and it is right for the reason the clause states: both diffs *say* what they are
doing, in `CHANGES.rst`, in a new docstring, in an inline comment, and in tests that move with the
code. A product that published these would be telling `click`'s maintainers that their own
changelog entries are defects.

**It does not license "clause (c) has high precision."** Three things bound the claim hard:

1. **n = 2 commits, not 15 rows.** Ten of the fifteen are one function under ten probe inputs;
   the fifteen rows are not fifteen independent observations, and treating them as such would be
   the same error D-139 already made once with a denominator.
2. **The two commits are unusually loud.** One is a 39-file *"Merge Main into Stable"* with 98
   changelog lines. A merge commit states the intent of everything it carries, so clause (c) has
   the easiest possible job on it. A quiet refactor that changes a value and touches no test, no
   docstring and no changelog is the case that would discriminate, and **the eleven forward pairs
   contain none.**
3. **The recall cost is still unmeasured where it matters.** D-135 established that this clause is
   right on forward pairs and wrong on all four reversed pairs it was tried on. Fifteen more
   forward rows do not touch that.

**So the recommendation to the owner is: do not change `attest.intent.v4.1`, and do not treat
this as evidence that it is well calibrated.** What would move the question is a population of
commits that change a value and *say nothing* — which is a corpus-construction task, not a rule
change.

## 4. One thing worth recording that is not about intent

Row 5 (`ad115e73f1`) is a differential over a state the program cannot reach. The probe's setup
constructs an `Argument`, then assigns `param.name = None` by hand; no `click` code path produces
that object. Base raises `AssertionError`, head does not, and the difference is real — **about an
input the program never receives.**

The intent rule drawered it for an unrelated reason (the assert removal is in the diff), so
nothing wrong was published. But the *reachability* of a probe's constructed state is not
something any current adjudicator checks, and on a pair where the diff said nothing this would
have been a value-class candidate with a genuine differential and no defect behind it.

**Recorded as an open question, not fixed**: it needs a definition of "a state the program can
construct" that a checker can decide, and inventing one inside an adjudication is how a rule ends
up with a clause nobody measured.
