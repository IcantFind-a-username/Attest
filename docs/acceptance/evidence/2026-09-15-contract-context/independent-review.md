# Contract-context independent review — one pass

Reviewed baseline `5dc801e` through the uncommitted implementation on
`fix/contract-context` (HEAD `75c6d69c24b024e3d4e0882a19a2add81fdc7a13`).
Read-only review of production source; no paid calls, remote actions, or whole-suite run.

## Finding: high — parametrize's local execution bypasses the context screen

Location: `src/attest/review/contract_context.py:41–46`.
The exemption for any decorator whose callee spells `pytest.mark.parametrize` does
not examine its arguments. The existing `flow_refusal` only rejects selected mark names
and indirect parameters; it does not screen arbitrary expressions in this decorator.

Reproduced in `.attest/context-work/reviewer/parametrize_effect/tests/test_geo.py`:

```python
import pytest
from geo import Point, parse

def install():
    globals()["parse"] = lambda text: Point(1, 2)
    return ["one"]

@pytest.mark.parametrize("unused", [0], ids=install())
def test_parse(unused):
    assert parse("1,2") == Point(1, 2)
```

The local `geo.parse` returns `Point(x=1, y=3)`. Direct execution of this fixture's
definition and `test_parse(0)` passes because the decorator's argument changed the
test module's callable to return `Point(x=1, y=2)`.

Actual source-reader results:

- `context_refusal(...) == ""`.
- `contract_probes(...)` emits `parse('1,2')`, with no refused sites.
- `find_contracts(base_tree=root, head_tree=root, ...)` records the same source as
  `admitted=True`, `flow_bound=True`, `standing_at_head=True`, `flow_reason=""`.
- `contract_admissible(record) == True` in the unchanged kernel.

Thus the observer still supplies affirmative authority for an assertion about a locally
substituted callable. The same test source can stand across a reasonable raw implementation
change. This is local decorator execution, not a transitive-import or ambient-plugin limit.
The end-to-end `attempt_certification` call was not rerun by this reviewer; the reproduction
establishes generator emission and erroneous observer/kernel contract admission.

Fix direction: restrict parametrize to the declarative subset the reader understands,
including its optional keywords, or refuse its unexamined executable argument expressions.
Callable `ids` also needs deliberate treatment because collection can invoke it later.

## Other inspection and limits

The added observer screen independently reads both trees. Clearing both `admitted` and
`flow_bound` on context refusal agrees with the kernel's derived-admissibility check.
An allowed base contract opposed by a refused head contract fails the standing check.
Function default/annotation calls, ordinary decorators, named hooks, class construction,
module executable statements, and nonempty ancestor conftests are conservatively screened.
No second concrete defect was reproduced in this pass.

Transitive imported code, ambient pytest plugins, and prior-test state are acknowledged
limits, not claims this patch establishes. The full suite and end-to-end empirical gate
remain the controller's responsibility.

## Diff and tooling

Initial `git diff --stat 5dc801e`:

```text
 scripts/corpus/binding_cases.py |   4 ++
 scripts/corpus/context_cases.py | 113 ++++++++++++++++++++++++++++++++++++++++
 src/attest/review/contracts.py  |  12 ++++-
 3 files changed, 128 insertions(+), 1 deletion(-)
```

This excludes the then-untracked `contract_context.py` (108 lines) and
`tests/test_contract_context.py` (72 lines), both inspected. Controller edits continued
during the pass; this report makes no second-pass claim about later edits.

Reused: production `context_refusal`, `contract_probes`, `find_contracts`, and kernel
`contract_admissible`; inspected the existing binding-case trace instead of introducing
another certification driver. No duplicate serialization/digest/statistics/credential
utility was needed from the supplied inventory. Newly added tools: none.
