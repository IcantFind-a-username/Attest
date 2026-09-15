# Development environment preflight — continuation of E-02 preparation

Baseline `1bc7b680e2790e6ef83b5de410c2e4270a961f45`; owner instruction: continue.
Scope: the five already frozen Keras development candidates, in their frozen order.
No held-out project/source/oracle access, replacement cases, product/model evaluation,
paid calls, default changes, or new execution backend. The prior freeze stays immutable.

Read each selected development `bug.info`, `requirements.txt` and `run_test.sh` from
the pinned BugsInPy tree. These are development inputs and must never become held-out
truth. Before this protocol, keras/8 requirements and oracle command were inspected
to locate the prerequisite; no test was executed or behavioral outcome observed.

Measure the environment compatibility prerequisite using the committed
`scripts/corpus/development_preflight.py`: recorded Python version versus the existing
`AVAILABLE_PYTHONS`, exact TensorFlow pin versus official PyPI release distributions.
Inspect distribution filenames with the existing packaging wheel parser. Count a
CPython wheel as potentially usable on Linux only when its tags intersect the declared
interpreter/platform tag set; this does not establish dependency resolution or execution.
Source distributions are reported separately: their presence means buildability is unknown.
Missing/unparseable metadata or fetch errors remain errors, never a compatibility success.

This is a prerequisite census, not a benchmark or an estimator of recall. Its denominator
is all five frozen development candidates, with shared environments explicitly grouped.
If the recorded interpreter is unsupported, do not substitute today's Python or change
pins to obtain a behavioral result. Retain the blocker; no image build or project test
run is needed to establish that the existing product matrix does not cover the recorded
environment. No claim that a source port or a separate historical oracle environment
could never run the project follows from that blocker.

Deliver: per-candidate input hashes, oracle argv, environment groups, official distribution
metadata/digests, unsupported/unknown counts and the exact reason no paired execution was
attempted. Existing shared canonical JSON/digest and packaging parsers are reused.
No behavior change or RED test; perform artifact checks, script lint and one independent
review. Product gates and E-02 acceptance remain open (G-CORPUS-001 requires substantially
more repositories/cases plus semantic truth and paired controls).
