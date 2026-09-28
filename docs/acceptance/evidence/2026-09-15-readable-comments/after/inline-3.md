<!-- attest:finding-id:04b7b202f3 -->
[red] src/urllib3/_collections.py:483 — frozenf939aa7b36 (receipt 3a08ea34a1bb)

Verified: the generated test failed on head in 3/3 runs and passed on the merge base in 3/3 runs.

Action: reproduce it — `pytest -q test_repro.py::test_attest_replay` — then check the receipt offline with `attest verify --bundle .attest/corpora/mutations-v1-recall/urllib3/repo/.attest/evidence/fe-b1-E61-urllib3-none_guard-15--forward/04b7b202f3 --require-seal`.

<details>
<summary>Reproduce it yourself — command, test and the six runs</summary>

Finding ID: 04b7b202f3

Test: test_repro.py::test_attest_replay

Receipt: 3a08ea34a1bbcbf9af67f5ece047d32d5ed5de75fe428cfb96124d8087f6353b

Run it yourself: save the test as `test_repro.py` in the repository root and run

```bash
pytest -q test_repro.py::test_attest_replay
```

```python
import re

from urllib3._collections import HTTPHeaderDict


def test_attest_replay():
    h = HTTPHeaderDict(a='1')
    try:
        _attest_value = 5 | h
    except BaseException as _attest_error:  # noqa: BLE001 - the type is the record
        _attest_raised = type(_attest_error).__name__
    else:
        _attest_raised = None
    # recorded by executing the expression above on the merge base;
    # no model wrote this expectation
    assert _attest_raised == 'TypeError'
```

Runs: head FAIL 3/3, base PASS 3/3

head:
- head-1: failed (exit 1)
- head-2: failed (exit 1)
- head-3: failed (exit 1)

base (merge-base):
- base-1: passed (exit 0)
- base-2: passed (exit 0)
- base-3: passed (exit 0)

<details>
<summary>Full logs</summary>

**head-1**

```text
F                                                                        [100%]
=================================== FAILURES ===================================
______________________________ test_attest_replay ______________________________

    def test_attest_replay():
        h = HTTPHeaderDict(a='1')
        try:
            _attest_value = 5 | h
        except BaseException as _attest_error:  # noqa: BLE001 - the type is the record
            _attest_raised = type(_attest_error).__name__
        else:
            _attest_raised = None
        # recorded by executing the expression above on the merge base;
        # no model wrote this expectation
>       assert _attest_raised == 'TypeError'
E       AssertionError: assert None == 'TypeError'

.attest-repro/test_repro.py:16: AssertionError
=========================== short test summary info ============================
FAILED .attest-repro/test_repro.py::test_attest_replay - AssertionError: asse...
1 failed in 0.02s

```

**head-2**

```text
F                                                                        [100%]
=================================== FAILURES ===================================
______________________________ test_attest_replay ______________________________

    def test_attest_replay():
        h = HTTPHeaderDict(a='1')
        try:
            _attest_value = 5 | h
        except BaseException as _attest_error:  # noqa: BLE001 - the type is the record
            _attest_raised = type(_attest_error).__name__
        else:
            _attest_raised = None
        # recorded by executing the expression above on the merge base;
        # no model wrote this expectation
>       assert _attest_raised == 'TypeError'
E       AssertionError: assert None == 'TypeError'

.attest-repro/test_repro.py:16: AssertionError
=========================== short test summary info ============================
FAILED .attest-repro/test_repro.py::test_attest_replay - AssertionError: asse...
1 failed in 0.02s

```

**head-3**

```text
F                                                                        [100%]
=================================== FAILURES ===================================
______________________________ test_attest_replay ______________________________

    def test_attest_replay():
        h = HTTPHeaderDict(a='1')
        try:
            _attest_value = 5 | h
        except BaseException as _attest_error:  # noqa: BLE001 - the type is the record
            _attest_raised = type(_attest_error).__name__
        else:
            _attest_raised = None
        # recorded by executing the expression above on the merge base;
        # no model wrote this expectation
>       assert _attest_raised == 'TypeError'
E       AssertionError: assert None == 'TypeError'

.attest-repro/test_repro.py:16: AssertionError
=========================== short test summary info ============================
FAILED .attest-repro/test_repro.py::test_attest_replay - AssertionError: asse...
1 failed in 0.02s

```

**base-1**

```text
.                                                                        [100%]
1 passed in 0.01s

```

**base-2**

```text
.                                                                        [100%]
1 passed in 0.01s

```

**base-3**

```text
.                                                                        [100%]
1 passed in 0.01s

```

</details>

Evidence bundle: `.attest/corpora/mutations-v1-recall/urllib3/repo/.attest/evidence/fe-b1-E61-urllib3-none_guard-15--forward/04b7b202f3` — verify offline with `attest verify --bundle .attest/corpora/mutations-v1-recall/urllib3/repo/.attest/evidence/fe-b1-E61-urllib3-none_guard-15--forward/04b7b202f3 --require-seal`.

</details>
