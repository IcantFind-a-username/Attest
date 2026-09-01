# Independent evidence review

- Binding: baseline `0e58cd61a1a63c51a329d5c1a5509181be32adfa`; current
  `b6caad7249dd32100cd6d96ae038bcdbfdc636c6`.
- Result: P0/P1/P2 = 0/0/0.
- Inventory reviewed: 20 current JSON records, aggregate JSON, baseline JSON, and the
  exact baseline stderr marker; no symlink or special file.
- All JSON is canonical. Outer/nested repeats cover 0–19 exactly; every recorded output
  digest matches its file; source/probe/cassette/input/fixture/tree bindings recompute.
- Independent authoritative reduction returned semantic/operational = 1/20 and
  candidates/published/unresolved/partial = 5/4/1/1 with 20 unique isolation digests.
- A fresh aggregate run produced bytes identical to `aggregate.json`.
- Claim boundary: constructed-fixture accounting and operational consistency only; not
  public precision/recall, production reliability, or host-wide security evidence.
