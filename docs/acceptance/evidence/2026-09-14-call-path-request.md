# The first probe's request, before and after D-247 (redacted fixture)

Captured on a temporary repository built by the test fixture, with a provider that records the
request and answers a fixed probe. No model is called and nothing is bought. The fixture: a changed
`Reader.read_regex` in `src/pkg/reader.py` whose guard the head deletes; `src/pkg/parser.py`
reaches it from another module through `parse_stream`; `src/pkg/other.py` defines an unrelated
function of the same name; `src/pkg/loose.py` calls the name on a receiver the index cannot type;
`tests/test_parser.py` specifies the behaviour **at the merge base**.

## Before (`main` at the branch point)

````text
Claim: The guard is gone.
Failure scenario: read_regex no longer rejects None.
Falsification plan: Call read_regex with None.
Anchor: src/pkg/reader.py:5

Current (head) definition of `read_regex` (src/pkg/reader.py:5-6), which contains the claimed defect:
```python
    def read_regex(self, regex):
        return [self.stream]
```

Merge-base definition of `read_regex` (src/pkg/reader.py:5-8), the behaviour the test must assert:
```python
    def read_regex(self, regex):
        if regex is None:
            raise ValueError('regex required')
        return [self.stream]
```

Signatures in src/pkg/reader.py (call things exactly like this):
```python
class Reader:
    def __init__(self, stream)
    def read_regex(self, regex)
```

Nearest existing test module (tests/test_parser.py): its imports, fixtures and helpers, to construct objects the way the project's tests do:
```python
# imports
import pytest
from pkg.parser import parse_stream
```

Anchor window (head):
class Reader:
    def __init__(self, stream):
        self.stream = stream

    def read_regex(self, regex):
        return [self.stream]

Conditions this change removed or altered:
- in `read_regex`: the guard `regex is None` was removed (it raised ValueError)
An input that sits exactly on such a boundary, or one the removed guard used to catch, is where the two revisions are most likely to differ.

No test in the repository asserts a value about `Reader`, `read_regex`. A recorded value can then be certified only where a docstring or documentation states it; an input on which the merge base raises, or one whose result a docstring states, is what the certification rule can use.

Literal arguments the repository passes to `Reader`, `read_regex`, most frequent first: `'key'`. An input the tree already uses, or the value one step past it, is where a probe reaches the change with the least guessing.
````

## After (this branch)

````text
Claim: The guard is gone.
Failure scenario: read_regex no longer rejects None.
Falsification plan: Call read_regex with None.
Anchor: src/pkg/reader.py:5

Current (head) definition of `read_regex` (src/pkg/reader.py:5-6), which contains the claimed defect:
```python
    def read_regex(self, regex):
        return [self.stream]
```

Merge-base definition of `read_regex` (src/pkg/reader.py:5-8), the behaviour the test must assert:
```python
    def read_regex(self, regex):
        if regex is None:
            raise ValueError('regex required')
        return [self.stream]
```

Signatures in src/pkg/reader.py (call things exactly like this):
```python
class Reader:
    def __init__(self, stream)
    def read_regex(self, regex)
```

Nearest existing test module (tests/test_parser.py): its imports, fixtures and helpers, to construct objects the way the project's tests do:
```python
# imports
import pytest
from pkg.parser import parse_stream
```

Anchor window (head):
class Reader:
    def __init__(self, stream):
        self.stream = stream

    def read_regex(self, regex):
        return [self.stream]

Conditions this change removed or altered:
- in `read_regex`: the guard `regex is None` was removed (it raised ValueError)
An input that sits exactly on such a boundary, or one the removed guard used to catch, is where the two revisions are most likely to differ.

Routes into `Reader`, `read_regex` (head revision; the merge base decides what a call does):
1. `parse_stream` -> `return reader.read_regex('key')` (src/pkg/parser.py:6) -- a possible call: the index cannot type the receiver, so this route is unconfirmed
   the receiver is built there: `reader = Reader(stream)` (src/pkg/parser.py:5)
What the merge base specifies about these routes:
- tests/test_parser.py::test_parse_stream_rejects_a_missing_regex (merge base):
```python
def test_parse_stream_rejects_a_missing_regex():
    with pytest.raises(ValueError):
        parse_stream(None)
```
No test of the merge base names directly: `Reader`, `read_regex` (tests this change added or rewrote are not read here; one it deleted is not looked for).

No test of the head revision asserts a value about `Reader`, `read_regex`. A recorded value can then be certified only where a docstring or documentation states it; an input on which the merge base raises, or one whose result a docstring states, is what the certification rule can use.

Literal arguments the repository passes to `Reader`, `read_regex`, most frequent first: `'key'`. An input the tree already uses, or the value one step past it, is where a probe reaches the change with the least guessing.
````

## What is new, and where each piece comes from

| new material | source | revision |
|---|---|---|
| `parse_stream` -> `return reader.read_regex('key')` (`src/pkg/parser.py:6`) | `TreeIndex.callers_of` (D-245/D-246), rendered by `call_paths_into` | head |
| *a possible call: the index cannot type the receiver* | the index's own `attribute` resolution; a receiver assigned from a constructor is not typed (D-246's stated bound) | head |
| `the receiver is built there: reader = Reader(stream)` (`src/pkg/parser.py:5`) | the nearest assignment of the call's receiver, inside the enclosing definition | head |
| `tests/test_parser.py::test_parse_stream_rejects_a_missing_regex` and its body | `show_file_at(repo, base_ref, path)`, i.e. `git show <merge-base>:<file>` | **merge base** |
| *No test of the merge base names ...* | the names no merge-base test calls itself | merge base |
| *No test of the **head revision** asserts a value about ...* | the pre-existing D-238 block, now naming the revision it reads | head |

`src/pkg/other.py` appears in neither request: a same-named function in a file that never imports
the changed module is not a caller. `src/pkg/loose.py` is not shown as a certain route.
