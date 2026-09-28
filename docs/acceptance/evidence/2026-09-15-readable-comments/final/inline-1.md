<!-- attest:finding-id:7b3c725e57 -->
[red] src/packaging/_musllinux.py:25 — frozen376af98bfd (receipt 9de0b91043e8)

Verified: the generated test failed on head in 3/3 runs and passed on the merge base in 3/3 runs.

Action: reproduce it — `pytest -q test_repro.py::test_attest_replay` — then check the receipt offline with `attest verify --bundle .attest/corpora/mutations-v1-recall/packaging/repo/.attest/evidence/fe-b1-E61-packaging-boundary-08--forward/7b3c725e57 --require-seal`.

<details>
<summary>Reproduce it yourself — command, test and the six runs</summary>

Finding ID: 7b3c725e57

Test: test_repro.py::test_attest_replay

Receipt: 9de0b91043e87a30942577e16a21f30d7a3852c554cd02dbadaa4a6c46de9cc0

Run it yourself: save the test as `test_repro.py` in the repository root and run

```bash
pytest -q test_repro.py::test_attest_replay
```

```python
import re

from packaging._musllinux import _parse_musl_version


def test_attest_replay():
    MUSL_AMD64 = 'musl libc (x86_64)\nVersion 1.2.2\n'
    output = MUSL_AMD64
    _attest_value = _parse_musl_version(output)
    # recorded by executing the expression above on the merge base;
    # no model wrote this expectation
    assert re.sub(' at 0x[0-9a-f]+', '', repr(_attest_value)) == '_MuslVersion(major=1, minor=2)'
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
        MUSL_AMD64 = 'musl libc (x86_64)\nVersion 1.2.2\n'
        output = MUSL_AMD64
        _attest_value = _parse_musl_version(output)
        # recorded by executing the expression above on the merge base;
        # no model wrote this expectation
>       assert re.sub(' at 0x[0-9a-f]+', '', repr(_attest_value)) == '_MuslVersion(major=1, minor=2)'
E       AssertionError: assert 'None' == '_MuslVersion...r=1, minor=2)'
E         
E         - _MuslVersion(major=1, minor=2)
E         + None

MUSL_AMD64 = 'musl libc (x86_64)\nVersion 1.2.2\n'
_attest_value = None
output     = 'musl libc (x86_64)\nVersion 1.2.2\n'

.attest-repro/test_repro.py:12: AssertionError
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
        MUSL_AMD64 = 'musl libc (x86_64)\nVersion 1.2.2\n'
        output = MUSL_AMD64
        _attest_value = _parse_musl_version(output)
        # recorded by executing the expression above on the merge base;
        # no model wrote this expectation
>       assert re.sub(' at 0x[0-9a-f]+', '', repr(_attest_value)) == '_MuslVersion(major=1, minor=2)'
E       AssertionError: assert 'None' == '_MuslVersion...r=1, minor=2)'
E         
E         - _MuslVersion(major=1, minor=2)
E         + None

MUSL_AMD64 = 'musl libc (x86_64)\nVersion 1.2.2\n'
_attest_value = None
output     = 'musl libc (x86_64)\nVersion 1.2.2\n'

.attest-repro/test_repro.py:12: AssertionError
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
        MUSL_AMD64 = 'musl libc (x86_64)\nVersion 1.2.2\n'
        output = MUSL_AMD64
        _attest_value = _parse_musl_version(output)
        # recorded by executing the expression above on the merge base;
        # no model wrote this expectation
>       assert re.sub(' at 0x[0-9a-f]+', '', repr(_attest_value)) == '_MuslVersion(major=1, minor=2)'
E       AssertionError: assert 'None' == '_MuslVersion...r=1, minor=2)'
E         
E         - _MuslVersion(major=1, minor=2)
E         + None

MUSL_AMD64 = 'musl libc (x86_64)\nVersion 1.2.2\n'
_attest_value = None
output     = 'musl libc (x86_64)\nVersion 1.2.2\n'

.attest-repro/test_repro.py:12: AssertionError
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

Evidence bundle: `.attest/corpora/mutations-v1-recall/packaging/repo/.attest/evidence/fe-b1-E61-packaging-boundary-08--forward/7b3c725e57` — verify offline with `attest verify --bundle .attest/corpora/mutations-v1-recall/packaging/repo/.attest/evidence/fe-b1-E61-packaging-boundary-08--forward/7b3c725e57 --require-seal`.

</details>
