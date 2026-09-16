# Pre-execution review resolution

One independent review at dc2d0ad reproduced a P2 omission: the admission predicate
checked identity tuples but accepted a changed cutoff, output path and ordering.
No build had started. The driver now derives complete ordered entries from the
qualification record and its digest-bound freeze, including the original case
timestamp and safe previously frozen identity. The supplied entries must equal
that list exactly. No source, dependency or outcome informed this correction.

Direct checks of the actual natural_cases function admit the exact four frozen
entries and refuse five mutations: future cutoff, path traversal, reversed order,
changed revision and duplicate entry. Ruff and git diff --check pass. Existing
six-case study inputs/results are untouched. No second review pass or extra scope.
