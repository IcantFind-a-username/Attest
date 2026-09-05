# Upstream report, prepared and **not** filed — `more-itertools`: `divide()` raises `KeyError` on a mapping from Python 3.12

**Status: draft for the owner to file.** Nothing in this document has been sent anywhere, and
this repository has posted nothing to `more-itertools`. Third-party repositories are read-only
inputs here (AGENTS §8); the clone under `.attest/corpora/gnull/more-itertools/` was fetched
read-only and its default-branch tip at the time of writing is `d92f081a08` (2026-09-03).

Provenance: the defect was surfaced by this project's own null study as a **publication on a
commit filed as a control**, and adjudicated by an independent probe with no product code in it
(D-139, D-141). The finding is about `more-itertools`; it is not about Attest.

---

## Title

> `divide()` raises `KeyError: slice(None, 0, None)` for dict/mapping input on Python ≥ 3.12

## Minimal reproduction

```python
import more_itertools as mi

mi.divide(3, {1: "a", 2: "b", 3: "c"})
# Python 3.11: [<tuple_iterator>, <tuple_iterator>, <tuple_iterator>]  -> [[1], [2], [3]]
# Python 3.12: KeyError: slice(None, 0, None)
# Python 3.13: KeyError: slice(None, 0, None)
```

One line, no third-party dependency:

```bash
python -c "import more_itertools as mi; print([list(c) for c in mi.divide(3, {1:'a',2:'b',3:'c'})])"
```

The same happens for `collections.OrderedDict` and for any mapping type; more generally for any
object whose `__getitem__` raises something other than `TypeError` when handed a slice. A
`dict` is only the ordinary instance of that class, and it became one at Python 3.12.

## Affected version range

| axis | affected from | notes |
|---|---|---|
| library | **`more-itertools` 8.1.0** and every release since, up to and including the current `main` (`d92f081a08`, tag `v11.1.0` in the clone) | introduced by `f4f2cfec9d1af6780012a5021e46c191d14148e0` (2019-12-29, *“In `divide`: avoid tuple conversion if possible”*); `git tag --contains` first lists `8.1.0` |
| interpreter, mapping input | **Python 3.12** and later (3.12, 3.13 confirmed) | `slice` objects became hashable in 3.12, so `{}[:0]` raises `KeyError` instead of `TypeError` and escapes the guard |
| interpreter, non-mapping input | **every** version (3.9, 3.11, 3.12, 3.13 confirmed) | any `__getitem__` that raises a non-`TypeError` for a slice — e.g. the legacy sequence protocol raising `IndexError` — has always escaped the guard |

Measured, not inferred: the two revisions of `divide` were transcribed into a standalone probe
with no library or product import
([`evidence/2026-09-05d-divide-probe.py`](evidence/2026-09-05d-divide-probe.py)) and run on
**four** interpreters; the release library itself was then run from the clone's tip on 3.11,
3.12 and 3.13. Thirteen input types, of which nine (list, tuple, str, range, generator, deque,
array, set, StringIO) behave identically on every version.

```text
python 3.9.25   dict: no difference   legacy-__getitem__: DIFFERS   KeyError-mapping: DIFFERS
python 3.11.5   dict: no difference   legacy-__getitem__: DIFFERS   KeyError-mapping: DIFFERS
python 3.12.2   dict: DIFFERS         legacy-__getitem__: DIFFERS   KeyError-mapping: DIFFERS
python 3.13.1   dict: DIFFERS         legacy-__getitem__: DIFFERS   KeyError-mapping: DIFFERS
```

## Root cause, in one sentence

`divide()` decides whether its argument is sliceable with `try: iterable[:0] / except TypeError`,
and that guard catches `TypeError` only — so any object whose `__getitem__` raises a different
exception for a slice escapes the fallback and reaches `len(seq)`/`seq[start:stop]` as if it
were a sequence, which for a mapping on Python ≥ 3.12 is a `KeyError`.

Current source (`more_itertools/more.py`, `divide`):

```python
    try:
        iterable[:0]
    except TypeError:
        seq = tuple(iterable)
    else:
        seq = iterable
```

## Suggested fix

```python
    try:
        iterable[:0]
    except (TypeError, KeyError):
        seq = tuple(iterable)
    else:
        seq = iterable
```

That is the minimal change and it fixes the reported case. Two things worth deciding upstream,
stated here rather than assumed:

- a `__getitem__` raising `IndexError` (the pre-`__iter__` sequence protocol) still escapes; a
  broader `except Exception` or an `isinstance(iterable, Sequence)` test covers that too;
- the probe is a *behavioural* check on the guard, so whichever form is chosen, a regression
  test with a `dict` argument pins the 3.12 case that no existing test covers.

## The receipt

The reproduction the automated run certified is the non-`TypeError` `__getitem__` case rather
than the `dict` case; both are the same root cause. Its evidence bundle is sealed and verifies
offline (head FAIL 3/3, base PASS 3/3, `linux-container-v1`):

```text
.attest/corpora/gnull/more-itertools/.attest/evidence/20260905-192011-03c695ce/79f0b29318
```

```bash
.venv/bin/attest --repo .attest/corpora/gnull/more-itertools verify --require-seal --bundle "$PWD/.attest/corpora/gnull/more-itertools/.attest/evidence/20260905-192011-03c695ce/79f0b29318"
```

```text
accepted: receipt a665516a077c7ff5ae0128cd31429e34e4fa18dd8af7d536f06f8ed49940c195
for 79f0b29318 (linux-container-v1); seal verified
```

The bundle path must be absolute or relative to the current directory — `--repo` does not rebase
it. The certified test:

```python
import more_itertools as mi


def test_divide_with_side_effecting_getitem():
    class LazySequence:
        """Iterable whose __getitem__ raises a non-TypeError on slicing."""

        def __init__(self, data):
            self._data = list(data)
            self.getitem_calls = 0

        def __iter__(self):
            return iter(self._data)

        def __getitem__(self, index):
            self.getitem_calls += 1
            raise IndexError('slicing not supported')

    obj = LazySequence([1, 2, 3, 4, 5, 6, 7])
    children = mi.divide(3, obj)
    assert [list(c) for c in children] == [[1, 2, 3], [4, 5], [6, 7]]
    assert obj.getitem_calls == 0
```

## Before filing

- The upstream issue tracker was **not** searched for an existing report of this; a duplicate
  check is one search and belongs to whoever files it.
- If a maintainer asks how it was found, the honest answer is the one above: an automated
  regression-certification run treated the 2019 commit as a null control, published against it,
  and a hand-written probe confirmed the publication was right.
