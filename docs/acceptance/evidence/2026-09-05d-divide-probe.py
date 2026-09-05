"""Independent adjudication of the `G-NULL-001a` stop on `more-itertools f4f2cfec9d`.

No product code. `base_divide` and `head_divide` are transcribed straight from
the two revisions of `more_itertools.divide`, and the question is only whether
the published claim is true: does head raise on inputs base handled, and how
ordinary are those inputs?

    python docs/acceptance/evidence/2026-09-05d-divide-probe.py

The answer on Python 3.12 is that a plain `dict` is enough, because `slice`
became hashable in 3.12 and `{}[:0]` stopped raising the `TypeError` the 2019
guard catches.
"""

from __future__ import annotations

import array
import collections
import io


def base_divide(n, iterable):
    seq = tuple(iterable)
    q, r = divmod(len(seq), n)
    ret = []
    stop = 0
    for i in range(1, n + 1):
        start = stop
        stop = (i * q) + (i if i < r else r)
        ret.append(iter(seq[start:stop]))
    return ret


def head_divide(n, iterable):
    try:
        iterable[:0]
    except TypeError:
        seq = tuple(iterable)
    else:
        seq = iterable
    q, r = divmod(len(seq), n)
    ret = []
    stop = 0
    for i in range(1, n + 1):
        start = stop
        stop += q + 1 if i <= r else q
        ret.append(iter(seq[start:stop]))
    return ret


class LegacyIterable:
    """The pre-``__iter__`` sequence protocol: ``__getitem__(int)`` until IndexError."""

    def __init__(self, data):
        self.d = list(data)

    def __getitem__(self, index):
        if isinstance(index, slice):
            raise IndexError("slicing not supported")
        if index >= len(self.d):
            raise IndexError
        return self.d[index]

    def __len__(self):
        return len(self.d)


class PairsMapping:
    """A mapping whose ``__getitem__`` raises KeyError for a key it lacks."""

    def __init__(self, pairs):
        self.p = list(pairs)

    def __iter__(self):
        return iter(key for key, _ in self.p)

    def __len__(self):
        return len(self.p)

    def __getitem__(self, key):
        for name, value in self.p:
            if name == key:
                return value
        raise KeyError(key)


def fresh(name):
    """A new instance per side: two of these are consumed by iterating them."""
    if name == "generator":
        return (x for x in range(7))
    if name == "StringIO":
        return io.StringIO("a\nb\nc\n")
    return CASES[name]


CASES = {
    "list": [1, 2, 3, 4, 5, 6, 7],
    "tuple": (1, 2, 3, 4, 5, 6, 7),
    "str": "abcdefg",
    "range": range(7),
    "generator": None,
    "deque": collections.deque([1, 2, 3, 4, 5, 6, 7]),
    "array": array.array("i", [1, 2, 3, 4, 5, 6, 7]),
    "dict": {k: k for k in range(7)},
    "OrderedDict": collections.OrderedDict((k, k) for k in range(7)),
    "set": set(range(7)),
    "StringIO": None,
    "LegacyIterable (__getitem__ raises IndexError on a slice)": LegacyIterable(range(1, 8)),
    "PairsMapping (__getitem__ raises KeyError)": PairsMapping((k, k) for k in range(7)),
}


def run(divide, value):
    try:
        return "ok " + repr([list(child) for child in divide(3, value)])[:44]
    except Exception as exc:  # noqa: BLE001 - the difference is what is being measured
        return f"{type(exc).__name__}: {exc}"[:44]


def main() -> int:
    for name in CASES:
        base = run(base_divide, fresh(name))
        head = run(head_divide, fresh(name))
        differs = "  <-- DIFFERS" if base != head else ""
        print(f"{name:<58} base={base:<48} head={head}{differs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
