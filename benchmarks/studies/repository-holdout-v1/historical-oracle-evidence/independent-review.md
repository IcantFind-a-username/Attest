# Historical oracle — independent review

Single bounded pass of `95e5e45a3ec9a0f65575f8ce6997aa4401ec0d85` against
`00b95f6bf3b51d76c6fd6650937366b949cbf9ae`, branch `chore/keras-historical-oracle`.
Scope: the driver, preregistration and retained keras/8 attempt only. No experiment
rerun, additional corpus, held-out source/oracle/report, install, model call or remote
write was performed by the reviewer. The reviewer owns only this report.

## Findings and disposition

- **P2 — unsupported builder flag stops the sole attempt before image construction.**
  `scripts/corpus/historical_oracle.py:168` passes `--progress=plain`; retained
  `historical-oracle-keras8-r1/build.stderr` reports `unknown flag: --progress`,
  and `result.json` records build exit 125. The local legacy builder cannot accept
  this invocation. **Resolution status: confirmed; controller plans a committed
  collection repair removing only the progress flag and preserving r1.** The controller
  will append validation for its new attempt separately; this review does not inspect
  or qualify that attempt. Reporting must name this CLI failure, rather than infer package,
  interpreter, CPU, process-policy or oracle infeasibility from it. The protocol's
  initial attempt stopped; this is not a product defect or semantic result. Any second
  attempt must be visibly recorded as an amendment to the original one-attempt protocol.

No other concrete defect established in this pass. No receipt/publication path is
called. This statement does not qualify an unexecuted experiment or its security.

## Evidence checked

- `.venv/bin/python -m ruff check scripts/corpus/historical_oracle.py`: passed.
- All 18 retained external-stage stdout/stderr files match their recorded SHA-256;
  the script and protocol also match the recorded digests. Hash verification used
  the existing system `shasum` command, not a new measurement script.
- Both exported oracle files match `b32c4cf0e4b9c162478dadd6b3343466e6730fb5b3191a3190ff27b208be6ac0`.
  The driver overlays the fixed file on the buggy export and records it separately.
- Original requirement bytes and build-context bytes both match
  `bbacda7f742d0c5a2662b6efb98a5ecdb8ce11ba0c1acdad377c313b02601834`.
  Every listed dependency is version pinned. The recorded requirements/oracle reads
  use metadata revision `316b95e2353ecda832bad9b42f86fa7c2fcec8ac` and keras/8 paths.
- Recorded source revisions are fixed `d78c982b326adeed6ac25200dc6892ff8f518ca6`
  and buggy `87540a2a2f42e00c4a2ca7ca35d19f96e62e6cb0`; fetch/tree records use
  these same exact revisions. The official base image was resolved to an amd64
  digest and the generated Dockerfile uses that digest, with explicit bootstrap pins.
- Original node is `tests/keras/engine/test_topology.py::test_layer_sharing_at_heterogeneous_depth_order`.
  Both original pytest configurations still contain `-n 2`; the driver changes no
  configuration and adds JUnit output. Process-policy compatibility remains untested.
- The existing ContainerAdapter/Controller remain unchanged. Their command path uses
  network none, read-only/non-root execution, empty inherited environment, NPROC=0
  and the default pid cap. Driver-requested limits are 120 seconds and 2048 MiB.
  Pull/build use private empty Docker configuration and no credential mounts/secrets;
  no model API path exists. These execution properties were inspected in code, not
  demonstrated by this attempt, because no execution request was reached.
- Final record is `blocked`, `runs=[]`, product evaluations 0, model API spend 0,
  `receipt_eligible=false`. Thus there is no PASS/FAIL pair, semantic qualification,
  product recall estimate or receipt. No full pytest gate was run, as scoped.

## Change size and tool reuse

Implementation `git diff --stat`:

```text
 .../repository-holdout-v1/historical-oracle.md | 43 ++++
 scripts/corpus/historical_oracle.py           | 245 +++++++++++++++++++++
 2 files changed, 288 insertions(+)
```

Reused: `archive`, ContainerAdapter/Controller, ResourceLimits, `_atomic_write`,
`write_canonical_json`, `sha256_bytes`, `validation_junit_counts`, and `dataclasses.asdict`.
No replacement serialization, atomic-write, digest, metric or credential-filter helper
was added. No new tool declaration; this review creates only its assigned report.
