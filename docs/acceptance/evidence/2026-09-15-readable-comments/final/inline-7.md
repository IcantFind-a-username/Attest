<!-- attest:value:50c3eb6cef50 -->
[yellow] src/marshmallow/utils.py:97 — for utils.get_value(obj, 1), the merge base returned 2 and head raises TypeError (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note 50c3eb6cef50

<details>
<summary>The two observations, verbatim, and the drawer's reason</summary>

Expression: `utils.get_value(obj, 1)`

How the call was built (run it on either revision):

```python
from marshmallow import utils

obj = [1, 2, 3]

utils.get_value(obj, 1)
```

Merge base returned, 3/3 runs:

```
2
```

Head raises, 3/3 runs:

```
TypeError
```

What the intent clause found:
- nothing in the base tree pins either value

Why this is not a red finding: intent: behavior change confirmed, intent unknown: head raises TypeError from a call or expression on a changed line; no rejected input could be identified from the test's literals (行为变化已证实，意图未知)

</details>

Action: if the new value is intended, add a test that pins it at `src/marshmallow/utils.py:97`; otherwise restore what the merge base returned there.
