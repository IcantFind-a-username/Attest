<!-- attest:structural:scripts/corpus/impact_scan.py:62|scripts/corpus/qualify_controls.py:45 -->
[green] Structural (no defect claimed): scripts/corpus/impact_scan.py:62-68 `git` and scripts/corpus/qualify_controls.py:45-54 `git` normalise to token sequences of 50 and 50 tokens whose token-sequence similarity is 1.000 (threshold 0.92), not semantic equivalence; identifiers and literal values erased, attribute and callee names kept.

Category: structural. This is a measurement over the two coordinates above, not a reproduction: no test was generated and no receipt backs it.

Action: keep one of `scripts/corpus/impact_scan.py:62` and `scripts/corpus/qualify_controls.py:45`, and call it from the other.
