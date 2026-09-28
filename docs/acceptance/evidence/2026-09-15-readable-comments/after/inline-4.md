<!-- attest:finding-id:78f74c1a04 -->
[red] src/urllib3/poolmanager.py:415 — frozencf268fdb9c (receipt b7729d6818ef)

Verified: the generated test failed on head in 3/3 runs and passed on the merge base in 3/3 runs.

Action: reproduce it — `pytest -q test_repro.py::test_attest_replay` — then check the receipt offline with `attest verify --bundle .attest/corpora/mutations-v1-recall/urllib3/repo/.attest/evidence/fe-b1-E61-urllib3-none_guard-18--forward/78f74c1a04 --require-seal`.

<details>
<summary>Reproduce it yourself — command, test and the six runs</summary>

Finding ID: 78f74c1a04

Test: test_repro.py::test_attest_replay

Receipt: b7729d6818ef96b56c53a374fb6e35b9ad195f9922a7f49e4e5e784326f2f06d

Run it yourself: save the test as `test_repro.py` in the repository root and run

```bash
pytest -q test_repro.py::test_attest_replay
```

```python
import re

from urllib3.poolmanager import PoolManager
from urllib3.util.url import Url


def test_attest_replay():
    p = PoolManager()
    _attest_value = p._proxy_requires_url_absolute_form(Url('http://example.com'))
    # recorded by executing the expression above on the merge base;
    # no model wrote this expectation
    assert _attest_value == False
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
        p = PoolManager()
        _attest_value = p._proxy_requires_url_absolute_form(Url('http://example.com'))
        # recorded by executing the expression above on the merge base;
        # no model wrote this expectation
>       assert _attest_value == False
E       assert True == False

.attest-repro/test_repro.py:12: AssertionError
=========================== short test summary info ============================
FAILED .attest-repro/test_repro.py::test_attest_replay - assert True == False
1 failed in 0.02s

```

**head-2**

```text
F                                                                        [100%]
=================================== FAILURES ===================================
______________________________ test_attest_replay ______________________________

    def test_attest_replay():
        p = PoolManager()
        _attest_value = p._proxy_requires_url_absolute_form(Url('http://example.com'))
        # recorded by executing the expression above on the merge base;
        # no model wrote this expectation
>       assert _attest_value == False
E       assert True == False

.attest-repro/test_repro.py:12: AssertionError
=========================== short test summary info ============================
FAILED .attest-repro/test_repro.py::test_attest_replay - assert True == False
1 failed in 0.02s

```

**head-3**

```text
F                                                                        [100%]
=================================== FAILURES ===================================
______________________________ test_attest_replay ______________________________

    def test_attest_replay():
        p = PoolManager()
        _attest_value = p._proxy_requires_url_absolute_form(Url('http://example.com'))
        # recorded by executing the expression above on the merge base;
        # no model wrote this expectation
>       assert _attest_value == False
E       assert True == False

.attest-repro/test_repro.py:12: AssertionError
=========================== short test summary info ============================
FAILED .attest-repro/test_repro.py::test_attest_replay - assert True == False
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

Evidence bundle: `.attest/corpora/mutations-v1-recall/urllib3/repo/.attest/evidence/fe-b1-E61-urllib3-none_guard-18--forward/78f74c1a04` — verify offline with `attest verify --bundle .attest/corpora/mutations-v1-recall/urllib3/repo/.attest/evidence/fe-b1-E61-urllib3-none_guard-18--forward/78f74c1a04 --require-seal`.

</details>
