### Verified findings (each backed by a reproduction receipt): 3

- <!-- attest:finding-id:7b3c725e57 --> [red] Finding ID: 7b3c725e57; src/packaging/_musllinux.py:25 — frozen376af98bfd (receipt 9de0b91043e8)

<details>
<summary>Reproduce it yourself — command, test and the six runs</summary>

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


- <!-- attest:finding-id:d5eaa3e1b8 --> [red] Finding ID: d5eaa3e1b8; src/packaging/direct_url.py:179 — frozen5f9d98f2be (receipt 2906ed9127db)

<details>
<summary>Reproduce it yourself — command, test and the six runs</summary>

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


- <!-- attest:finding-id:04b7b202f3 --> [red] Finding ID: 04b7b202f3; src/urllib3/_collections.py:483 — frozenf939aa7b36 (receipt 3a08ea34a1bb)

<details>
<summary>Reproduce it yourself — command, test and the six runs</summary>

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

### Structural observations — measured, not reproduced; no defect is claimed: 1

- - [green] Structural (no defect claimed): scripts/corpus/impact_scan.py:62-68 `git` and scripts/corpus/qualify_controls.py:45-54 `git` normalise to token sequences of 50 and 50 tokens whose token-sequence similarity is 1.000 (threshold 0.92), not semantic equivalence; identifiers and literal values erased, attribute and callee names kept.

### Observed behaviour changes — the same call run on both revisions; no defect is claimed and nothing in the base tree pins either value: 1

- [yellow] loguru/_string_parsers.py:162 — for _string_parsers.parse_duration('1e400s'), the merge base raised OverflowError and head raises ValueError (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note 377e1f399cab

Spend $0.0000; 0.0s.
