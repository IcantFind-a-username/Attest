| case | cand 4→5 | elig 4→5 | cert 4→5 | pub 4→5 | samples 4→5 | $ 4→5 | moved |
|---|---|---|---|---|---|---|---|
| psf__requests-5414 | 1 | 1 | 1 | 1 | **4→5** | 0.0409→0.0521 | 2 |
| pytest-dev__pytest-10051 | **1→2** | **1→2** | **1→0** | **1→0** | **4→5** | 0.0510→0.1149 | 2 |
| pytest-dev__pytest-6197 | 5 | 2 | **1→0** | **1→0** | **4→5** | 0.1122→0.1573 | 2 |
| pytest-dev__pytest-7324 | 2 | 2 | **1→0** | **1→0** | **4→5** | 0.0627→0.0852 | 3 |
| psf__requests-1724 | 1 | 1 | 0 | 0 | **4→5** | 0.0549→0.0137 | 1 |
| psf__requests-2317 | 1 | 1 | 0 | 0 | **4→5** | 0.0576→0.0139 | 1 |
| psf__requests-6028 | 1 | 1 | 0 | 0 | **4→5** | 0.0339→0.0409 | 0 |
| pylint-dev__pylint-4661 | 1 | 1 | 0 | 0 | **4→5** | 0.0248→0.0347 | 2 |
| pylint-dev__pylint-6528 | 1 | 1 | 0 | 0 | **4→5** | 0.0606→0.0748 | 1 |
| pytest-dev__pytest-5840 | 9 | 8 | 0 | 0 | **4→5** | 0.4659→0.2157 | 8 |
| pytest-dev__pytest-7205 | 1 | 1 | 0 | 0 | **4→5** | 0.0286→0.0476 | 2 |
| pylint-dev__pylint-6903 | 1 | 1 | 0 | 0 | **4→5** | 0.0435→0.0553 | 0 |
| pytest-dev__pytest-10356 | 3 | 3 | 0 | 0 | **4→5** | 0.1683→0.1839 | 2 |
| pytest-dev__pytest-5787 | **10→11** | 9 | 0 | 0 | **4→5** | 0.3678→0.2033 | 10 |
| pytest-dev__pytest-7490 | **4→5** | **4→5** | 0 | 0 | **4→5** | 0.1601→0.1727 | 4 |
| pytest-dev__pytest-7571 | **2→3** | **2→3** | 0 | 0 | **4→5** | 0.1020→0.2181 | 3 |

totals K=4 candidates 44 eligible 39 certified 4 published 4 $1.8347
totals K=5 candidates 48 eligible 42 certified 1 published 1 $1.6840

verdicts that moved:
- **psf__requests-5414 `520c57974d`**
  - K=4: (absent)
  - K=5: reproduced
- **psf__requests-5414 `b4a6e83afe`**
  - K=4: reproduced
  - K=5: (absent)
- **pytest-dev__pytest-10051 `4fed00716a`**
  - K=4: (absent)
  - K=5: unfaithful generated test: it references a symbol absent from head, so its head failure is a stale reference rather than a defect
- **pytest-dev__pytest-10051 `1af71a4893`**
  - K=4: reproduced
  - K=5: intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base test asserts it and no docstring or documentation writes it down (返回值变化已证实，意图未知)
- **pytest-dev__pytest-6197 `a10e094aac`**
  - K=4: unfaithful generated test: it references a symbol absent from head, so its head failure is a stale reference rather than a defect
  - K=5: probe deferred on base: missing or malformed JUnit evidence: ValueError: no JUnit artifact
- **pytest-dev__pytest-6197 `16694a06e5`**
  - K=4: reproduced
  - K=5: probe deferred on base: missing or malformed JUnit evidence: ValueError: no JUnit artifact
- **pytest-dev__pytest-7324 `bf18db4fea`**
  - K=4: (absent)
  - K=5: probe deferred on base: missing or malformed JUnit evidence: ValueError: no JUnit artifact
- **pytest-dev__pytest-7324 `ddc96effb9`**
  - K=4: pytest passed on head in 3/3 runs; base not executed
  - K=5: (absent)
- **pytest-dev__pytest-7324 `78e76aebd9`**
  - K=4: reproduced
  - K=5: probe deferred on base: missing or malformed JUnit evidence: ValueError: no JUnit artifact
- **psf__requests-1724 `da45e4aaa9`**
  - K=4: probe deferred on base: reproduction attempted a network connection
  - K=5: isolation backend unavailable: environment bootstrap failed (python 3.12, roots ['.']): Dockerfile:6
--------------------
   4 |     COPY tree /attest/build
   5 |     RUN pip install -r /attest/build/requirements.txt || echo "attest: optional requirements ./requirements.txt failed"
   6 | >>> RUN pip install /attest/build
   7 |     RUN rm -rf /attest/build
   8 |     
--------------------
ERROR: failed to solve: process "/bin/sh -c pip install /attest/build" did not complete successfully: exit code: 1

View build details: docker-desktop://dashboard/build/desktop-linux/desktop-linux/tn2of19y5dc29b40f8zluudga

- **psf__requests-2317 `1a8691529e`**
  - K=4: probe deferred on base: missing or malformed JUnit evidence: ValueError: no JUnit artifact
  - K=5: isolation backend unavailable: environment bootstrap failed (python 3.12, roots ['.', 'docs']): Dockerfile:6
--------------------
   4 |     COPY tree /attest/build
   5 |     RUN pip install -r /attest/build/requirements.txt || echo "attest: optional requirements ./requirements.txt failed"
   6 | >>> RUN pip install /attest/build
   7 |     RUN pip install -r /attest/build/docs/requirements.txt || echo "attest: optional requirements docs/requirements.txt failed"
   8 |     RUN rm -rf /attest/build
--------------------
ERROR: failed to solve: process "/bin/sh -c pip install /attest/build" did not complete successfully: exit code: 1

View build details: docker-desktop://dashboard/build/desktop-linux/desktop-linux/9gw572thz18lge7ze5uexjxwr

- **pylint-dev__pylint-4661 `af73ba1a44`**
  - K=4: probe deferred on base: pytest collection/import/syntax or infrastructure failure (exit code 2, 0 failure(s), 1 error(s))
  - K=5: (absent)
- **pylint-dev__pylint-4661 `fb1c309a74`**
  - K=4: (absent)
  - K=5: probe deferred on base: pytest collection/import/syntax or infrastructure failure (exit code 2, 0 failure(s), 1 error(s))
- **pylint-dev__pylint-6528 `e2c2de445f`**
  - K=4: probe observation is not stable on base: the merge base returned ['/attest/scratch/tmpy23fhk1k/keepme/good.py'], then the merge base returned ['/attest/scratch/tmp2nzzgcq9/keepme/good.py']
  - K=5: probe observation is not stable on base: the merge base returned ['/attest/scratch/tmp8cnkmvr1/pkg'], then the merge base returned ['/attest/scratch/tmp7r23iih6/pkg']
- **pytest-dev__pytest-5840 `d6afe20488`**
  - K=4: pytest passed on head in 3/3 runs; base not executed
  - K=5: (absent)
- **pytest-dev__pytest-5840 `545606c5d6`**
  - K=4: probe observation is not stable on base: the merge base returned ([<module 'conftest' from '/attest/scratch/tmp1ng6z9z1/real/conftest.py'>], [<module 'conftest' from '/attest/scratch/tmp1ng6z9z1/real/conftest.py'>], ['/attest/scratch/tmp1ng6z9z1/link/sub', '/attest/scratch/tmp1ng6z9z1/real/sub'],...
  - K=5: probe deferred on base: missing or malformed JUnit evidence: ValueError: no JUnit artifact
- **pytest-dev__pytest-5840 `1e7e3757a8`**
  - K=4: probe deferred on base: pytest collection/import/syntax or infrastructure failure (exit code 2, 0 failure(s), 1 error(s))
  - K=5: probe deferred on base: missing or malformed JUnit evidence: ValueError: no JUnit artifact
- **pytest-dev__pytest-5840 `5975a5e845`**
  - K=4: probe observation is not stable on base: the merge base returned ([<module 'conftest' from '/attest/scratch/tmpfyuge3vz/real/conftest.py'>, <module 'conftest' from '/attest/scratch/tmpfyuge3vz/real/sub/conftest.py'>], <module 'conftest' from '/attest/scratch/tmpfyuge3vz/real/sub/conftest.py'>, {l...
  - K=5: probe deferred on base: missing or malformed JUnit evidence: ValueError: no JUnit artifact
- **pytest-dev__pytest-5840 `e9c8fee0f3`**
  - K=4: pytest passed on head in 3/3 runs; base not executed
  - K=5: (absent)
- **pytest-dev__pytest-5840 `d7c5859ff9`**
  - K=4: pytest passed on head in 3/3 runs; base not executed
  - K=5: (absent)
- **pytest-dev__pytest-5840 `5ea813f1bb`**
  - K=4: probe deferred on base: pytest collection/import/syntax or infrastructure failure (exit code 2, 0 failure(s), 1 error(s))
  - K=5: (absent)
- **pytest-dev__pytest-5840 `81e24cbcff`**
  - K=4: probe observation is not stable on base: the merge base returned ['/attest/scratch/tmp8x119apj/linkdir/conftest.py'], then the merge base returned ['/attest/scratch/tmptdqskit0/linkdir/conftest.py']
  - K=5: (absent)
- **pytest-dev__pytest-7205 `91584844d0`**
  - K=4: pytest passed on head in 3/3 runs; base not executed
  - K=5: (absent)
- **pytest-dev__pytest-7205 `112415975d`**
  - K=4: (absent)
  - K=5: probe deferred on base: missing or malformed JUnit evidence: ValueError: no JUnit artifact
- **pytest-dev__pytest-10356 `d3b25d8328`**
  - K=4: (absent)
  - K=5: intent: intent stated in the change itself: the same change also updates a test, a docstring, documentation, a changelog entry or an inline comment about the symbol under test (改动自身已陈述意图)
- **pytest-dev__pytest-10356 `0c15bcf57a`**
  - K=4: intent: intent stated in the change itself: the same change also updates a test, a docstring, documentation, a changelog entry or an inline comment about the symbol under test (改动自身已陈述意图)
  - K=5: (absent)
- **pytest-dev__pytest-5787 `5e69418c42`**
  - K=4: pytest passed on head in 3/3 runs; base not executed
  - K=5: (absent)
- **pytest-dev__pytest-5787 `1417fbca8e`**
  - K=4: pytest passed on head in 3/3 runs; base not executed
  - K=5: (absent)
- **pytest-dev__pytest-5787 `2b5a663e7a`**
  - K=4: pytest passed on head in 3/3 runs; base not executed
  - K=5: (absent)
- **pytest-dev__pytest-5787 `a9b75f94df`**
  - K=4: probe observation did not survive re-execution: base produced it 3 times and then did not; the value is not deterministic
  - K=5: probe deferred on base: missing or malformed JUnit evidence: ValueError: no JUnit artifact
- **pytest-dev__pytest-5787 `b4823ad9a3`**
  - K=4: (absent)
  - K=5: probe deferred on base: missing or malformed JUnit evidence: ValueError: no JUnit artifact
- **pytest-dev__pytest-5787 `ea9d72ba11`**
  - K=4: pytest passed on head in 3/3 runs; base not executed
  - K=5: (absent)
- **pytest-dev__pytest-5787 `84ec472fc5`**
  - K=4: intent: intent stated in the change itself: the same change also updates a test, a docstring, documentation, a changelog entry or an inline comment about the symbol under test (改动自身已陈述意图)
  - K=5: (absent)
- **pytest-dev__pytest-5787 `45500daa3c`**
  - K=4: pytest passed on head in 3/3 runs; base not executed
  - K=5: probe deferred on base: missing or malformed JUnit evidence: ValueError: no JUnit artifact
- **pytest-dev__pytest-5787 `94b30cb49f`**
  - K=4: pytest passed on head in 3/3 runs; base not executed
  - K=5: (absent)
- **pytest-dev__pytest-5787 `fc73e2e9a0`**
  - K=4: unfaithful generated test: it references a symbol absent from head, so its head failure is a stale reference rather than a defect
  - K=5: (absent)
- **pytest-dev__pytest-7490 `b07d0535da`**
  - K=4: intent: intent stated in the change itself: the same change also updates a test, a docstring, documentation, a changelog entry or an inline comment about the symbol under test (改动自身已陈述意图)
  - K=5: probe deferred on base: missing or malformed JUnit evidence: ValueError: no JUnit artifact
- **pytest-dev__pytest-7490 `efc39813f7`**
  - K=4: pytest passed on head in 3/3 runs; base not executed
  - K=5: (absent)
- **pytest-dev__pytest-7490 `247eaebd40`**
  - K=4: intent: intent stated in the change itself: the same change also updates a test, a docstring, documentation, a changelog entry or an inline comment about the symbol under test (改动自身已陈述意图)
  - K=5: probe deferred on base: missing or malformed JUnit evidence: ValueError: no JUnit artifact
- **pytest-dev__pytest-7490 `9f1bd37dc6`**
  - K=4: intent: intent stated in the change itself: the same change also updates a test, a docstring, documentation, a changelog entry or an inline comment about the symbol under test (改动自身已陈述意图)
  - K=5: probe deferred on base: missing or malformed JUnit evidence: ValueError: no JUnit artifact
- **pytest-dev__pytest-7571 `e657c9c898`**
  - K=4: (absent)
  - K=5: probe deferred on base: missing or malformed JUnit evidence: ValueError: no JUnit artifact
- **pytest-dev__pytest-7571 `317dd21723`**
  - K=4: intent: intent stated in the change itself: the same change also updates a test, a docstring, documentation, a changelog entry or an inline comment about the symbol under test (改动自身已陈述意图)
  - K=5: probe deferred on base: missing or malformed JUnit evidence: ValueError: no JUnit artifact
- **pytest-dev__pytest-7571 `10374f7b39`**
  - K=4: intent: intent stated in the change itself: the same change also updates a test, a docstring, documentation, a changelog entry or an inline comment about the symbol under test (改动自身已陈述意图)
  - K=5: probe deferred on base: missing or malformed JUnit evidence: ValueError: no JUnit artifact
