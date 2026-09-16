# Original tests with the existing font seed and complete original module context

After font-cache-runtime completes, archive and bind its raw result and dependency
freeze digests. Run natural_pair_original_tests.py --study remainder-font-cache
once into fresh remainder-prewarmed-original-tests. Preserve the earlier attempt;
its executions collected no tests and provide no behavioral outcome to select on.
All six frozen pairs remain in order, including runtime-unqualified pairs.

Inherit original-tests.md unchanged except two declared preparation changes:
1. Use the recorded font-cache runtime image, still under the process/thread guard.
2. The identical upstream original test module may be created when its historical
   path is absent. Its bytes still come only from the frozen original base blob plus
   original test_patch, and its exact node is unchanged. Record file creation for
   each side. Do not copy conftest, rewrite assertions/imports, apply the production
   repair, or permit a missing production anchor. Require a safe canonical path,
   no linked target/ancestor, and no file/directory collision before the write.

Apply the same context to both sides, regardless of behavior. Preserve three paired
repeats, exact JUnit identity, trace/provenance checks, and stop-on-mismatch with no
repair or retry after a behavioral outcome. Unsupported context/fixtures stay
unqualified. Record raw oracles privately and report independent case counts.
No product evaluation, API/model spend, default-policy change or remote mutation.
