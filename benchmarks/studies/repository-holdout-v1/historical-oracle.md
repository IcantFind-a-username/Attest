# First development historical oracle — bounded E-02 preparation

Baseline `00b95f6bf3b51d76c6fd6650937366b949cbf9ae`; owner instruction: continue.
Use only the first already frozen development candidate, keras/8. The other four
development candidates are not attempted in this round; no held-out access or replacement.
This is a historical oracle feasibility experiment, not product recall or certification.

Commit `scripts/corpus/historical_oracle.py` before execution. Read the pinned candidate's
requirements and original oracle argv, fetch its two exact upstream revisions into the
existing in-repository Keras clone, and export both trees. Copy the fixed oracle file onto
both exports, hash it, and record this overlay separately. Neither exported tree goes to
the product. No project code runs on the host.

Use the existing Docker boundary and unchanged ContainerAdapter/Controller. The temporary
corpus image uses the recorded Python 3.7.3, linux/amd64 (the published historical wheel
architecture), and exact recorded dependency pins. Resolve the official Python base tag
once, record its image ID/repository digest, then build from that digest. Bootstrap tools
are explicitly pinned to pip 20.1.1, setuptools 46.4.0 and wheel 0.34.2; these are experiment
build tools, not a claim about the original environment. Dependency installation happens
inside the image builder with no host credential mounts/build secrets. Build network is
for package retrieval only; test execution has no network or inherited host environment.

Pull deadline 180 s; image build deadline 900 s. One attempt, no dependency substitution,
unpinned fallback or alternative interpreter. Persist a checkpoint and logs for every
external stage; failure stops execution and records the blocker. No failed build is a
defect result. Use a private Docker config for pull/build to avoid the known credential
helper hang; do not modify the user's Docker configuration.

If the image builds, invoke the unmodified original pytest node/configuration through
the existing adapter (non-root, read-only mounts, network none, NPROC=0, default pid cap),
with identical image and oracle bytes for fixed and buggy trees. Keep HOME/tmp fresh and
cap numerical library thread settings at one on both sides. Verify the Keras import path
belongs to the mounted tree before pytest. Three fixed/buggy repeats, 120 s and 2 GiB per
invocation. No xdist/config/skip repair after outcomes; if the first pair is not a valid
one-test PASS/FAIL pair, stop with the operational observation and do not call it qualified.
Even a three-repeat differential is only oracle feasibility: independent semantic truth,
controls, profile adequacy and product compatibility remain unqualified.

Do not relax process/thread restrictions, switch the production backend/interpreter
matrix, touch certification, call models, or publish. An unsupported CPU, dependency,
collection or process-policy requirement is a named blocker, not a reason to mutate the
experiment until it succeeds. One independent review; script lint and artifact checks.
No product behavior change, RED or full product gate. All original records stay immutable.
