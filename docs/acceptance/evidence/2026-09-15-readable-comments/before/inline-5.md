<!-- attest:value:377e1f399cab -->
[yellow] loguru/_string_parsers.py:162 — for _string_parsers.parse_duration('1e400s'), the merge base raised OverflowError and head raises ValueError (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note 377e1f399cab

<details>
<summary>The two observations, verbatim, and the drawer's reason</summary>

Expression: `_string_parsers.parse_duration('1e400s')`

How the call was built (run it on either revision):

```python
from loguru import _string_parsers

_string_parsers.parse_duration('1e400s')
```

Merge base raised, 3/3 runs:

```
OverflowError
```

Head raises, 3/3 runs:

```
ValueError
```

What the intent clause found:
- nothing in the base tree pins either value

Why this is not a red finding: intent: behavior change confirmed, intent unknown: head raises ValueError from a raise statement on a changed line; the rejected input is not in the base tree's tests, fixtures or documentation (行为变化已证实，意图未知)

</details>

Action: if the new value is intended, add a test that pins it at `loguru/_string_parsers.py:162`; otherwise restore what the merge base raised there.
