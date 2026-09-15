<!-- attest:finding-id:d5eaa3e1b8 -->
[red] src/packaging/direct_url.py:179 — frozen5f9d98f2be (receipt 2906ed9127db)

Verified: the generated test failed on head in 3/3 runs and passed on the merge base in 3/3 runs.

Action: reproduce it — `pytest -q test_repro.py::test_attest_replay` — then check the receipt offline with `attest verify --bundle .attest/corpora/mutations-v1-recall/packaging/repo/.attest/evidence/fe-b1-E61-packaging-guard_raise-06--forward/d5eaa3e1b8 --require-seal`.

<details>
<summary>Reproduce it yourself — command, test and the six runs</summary>

Finding ID: d5eaa3e1b8

Test: test_repro.py::test_attest_replay

Receipt: 2906ed9127db5fe27bb145d47379cbda0190c1e6f8a9699f7da226ba2c1c15c3

Run it yourself: save the test as `test_repro.py` in the repository root and run

```bash
pytest -q test_repro.py::test_attest_replay
```

```python
import re

from packaging.direct_url import DirectUrl


def test_attest_replay():
    try:
        _attest_value = DirectUrl.from_dict({'url': 'https://example.com/archive.zip', 'archive_info': {'hashes': {'md5': 12345}}})
    except BaseException as _attest_error:  # noqa: BLE001 - the type is the record
        _attest_raised = type(_attest_error).__name__
    else:
        _attest_raised = None
    # recorded by executing the expression above on the merge base;
    # no model wrote this expectation
    assert _attest_raised == 'DirectUrlValidationError'
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
        try:
            _attest_value = DirectUrl.from_dict({'url': 'https://example.com/archive.zip', 'archive_info': {'hashes': {'md5': 12345}}})
        except BaseException as _attest_error:  # noqa: BLE001 - the type is the record
            _attest_raised = type(_attest_error).__name__
        else:
            _attest_raised = None
        # recorded by executing the expression above on the merge base;
        # no model wrote this expectation
>       assert _attest_raised == 'DirectUrlValidationError'
E       AssertionError: assert None == 'DirectUrlValidationError'

_attest_raised = None
_attest_value = DirectUrl(url='https://example.com/archive.zip', archive_info=ArchiveInfo(hashes={'md5': 12345}), vcs_info=None, dir_info=None, subdirectory=None)

.attest-repro/test_repro.py:15: AssertionError
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
        try:
            _attest_value = DirectUrl.from_dict({'url': 'https://example.com/archive.zip', 'archive_info': {'hashes': {'md5': 12345}}})
        except BaseException as _attest_error:  # noqa: BLE001 - the type is the record
            _attest_raised = type(_attest_error).__name__
        else:
            _attest_raised = None
        # recorded by executing the expression above on the merge base;
        # no model wrote this expectation
>       assert _attest_raised == 'DirectUrlValidationError'
E       AssertionError: assert None == 'DirectUrlValidationError'

_attest_raised = None
_attest_value = DirectUrl(url='https://example.com/archive.zip', archive_info=ArchiveInfo(hashes={'md5': 12345}), vcs_info=None, dir_info=None, subdirectory=None)

.attest-repro/test_repro.py:15: AssertionError
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
        try:
            _attest_value = DirectUrl.from_dict({'url': 'https://example.com/archive.zip', 'archive_info': {'hashes': {'md5': 12345}}})
        except BaseException as _attest_error:  # noqa: BLE001 - the type is the record
            _attest_raised = type(_attest_error).__name__
        else:
            _attest_raised = None
        # recorded by executing the expression above on the merge base;
        # no model wrote this expectation
>       assert _attest_raised == 'DirectUrlValidationError'
E       AssertionError: assert None == 'DirectUrlValidationError'

_attest_raised = None
_attest_value = DirectUrl(url='https://example.com/archive.zip', archive_info=ArchiveInfo(hashes={'md5': 12345}), vcs_info=None, dir_info=None, subdirectory=None)

.attest-repro/test_repro.py:15: AssertionError
=========================== short test summary info ============================
FAILED .attest-repro/test_repro.py::test_attest_replay - AssertionError: asse...
1 failed in 0.02s

```

**base-1**

```text
.                                                                        [100%]
1 passed in 0.02s

```

**base-2**

```text
.                                                                        [100%]
1 passed in 0.02s

```

**base-3**

```text
.                                                                        [100%]
1 passed in 0.02s

```

</details>

Evidence bundle: `.attest/corpora/mutations-v1-recall/packaging/repo/.attest/evidence/fe-b1-E61-packaging-guard_raise-06--forward/d5eaa3e1b8` — verify offline with `attest verify --bundle .attest/corpora/mutations-v1-recall/packaging/repo/.attest/evidence/fe-b1-E61-packaging-guard_raise-06--forward/d5eaa3e1b8 --require-seal`.

</details>
