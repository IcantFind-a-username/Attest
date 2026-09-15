# Source-mounted compatibility qualification

Baseline `e400ef2`, E-02 prerequisite under the existing owner authorization.
The previous turn produced six wheels, not runtime witnesses. No paid call,
product-source/default change, certification change or corpus replacement here.

Before execution, commit the driver and run its transfer boundary tests. Perform
one independent review. First build a tiny generic C extension returning 7, then
run it through the same transfer and guarded execution path. Do not proceed to
the six cases if this generic control fails.

Transfer only absent `.so` files and the project's declared generated version
file from the recorded wheel. Check wheel/revision identity, reject unsafe paths,
symlinks, duplicate names, unknown package roots and unexpected Python additions.
Check all original wheel/source overlaps for equal bytes, then check every
original source file after transfer. Record the original-tree digest and every
added-file digest. This is a trusted-controller diagnostic, not permission for
the generator to authenticate itself or issue a receipt.

Use a digest-pinned Python 3.10 slim Bookworm runtime with `libgomp1`; compilers
remain in the separate builder. Install the wheel plus its declared `test` and/or
`tests` extras, if any, and pytest. Extend the existing creation-date upper bounds
to active runtime/test dependencies read from wheel METADATA, with Python 3.10,
Linux aarch64 marker evaluation. Unresolved constraints or installation fails
closed. Retain resolved runtime versions; this is not a complete historical lock.

For each of the six frozen cases, in the existing order, export its recorded
revision afresh and apply only its own recorded wheel. One image build (600 s)
and one full guarded import test (60 s, 1024 MiB) per case, without behavioral
repair or retries. Imports must originate under `/attest/tree`, and at least one
native extension must have been transferred. Use existing `execute_repro` and
`ContainerAdapter`; retain their process/network, freshness and execution guards.
No fallback host execution, compiler allowance or thread-limit relaxation.

Count every row, distinguishing image refusal, transfer refusal and execution
failure. Success requires one executed, unskipped test, normal exit and active
network guard. This is runtime qualification only, not paired human-test truth,
forward-direction eligibility, a qualified defect/control, or a product review.
Those prerequisites and the paid minimum remain unchanged.
