# E-01 natural null (mainline §2 step 14): 20 real us-stock-helper commits with no known defect

Date: 2026-09-03. Corpus: `.attest/corpora/us-stock-helper/` (the owner's GitHub,
`feature/iphone-demo`). Population: 20 commits chosen by subject class before any run —
7 refactor/test-only, 6 docs-only, 7 feature additions — never a fix; plan
`benchmarks/attest-v2/runs/2026-09-03-e01-natural-null-plan.json`. Each commit is reviewed as
a pull request with head = the commit and base = its parent: `attest review --base <parent>
--k 4 --budget 0.25` through `linux-container-v1` (the local review selects the container
when Docker is present). Expected: zero publications; every publication is a RISK-CERT-01 root
cause. Evidence level: **natural-null study, n = 20 commits** (not `G-NULL-001`'s
preregistered n and interval; a first measurement of the mechanism on real changes).

First pass (code `a1624d2`): 0/20 published, $0.8076. Five commits with eligible regression
candidates (25 reproductions) DEFERred at the environment bootstrap: the corpus declares only
`requires-python = ">=3.11"` and the image rule fell back to 3.9. The rule now honours
`requires-python` (`8b93b75`) and those five were re-run from that checkout ($0.7204) so that
the null study exercises reproduction, not only ranking.

## Result: 1 publication on 20 commits — the stop rule fired

| class | commit | files | candidates | eligible | verifications | published | spend |
|---|---|---|---|---|---|---|---|
| refactor | `540b0a8` chore: add a one-shot evidence-gate measurement script | 2 | 9 | 0 | 0 | 0 | $0.0884 |
| refactor | `58bf763` test: pin agency positive attribution and 13g amendment form | 1 | 0 | 0 | 0 | 0 | $0.0136 |
| refactor | `facf699` test: pin a generated, byte-equal v2/v3 snapshot contract | 4 | 0 | 0 | 0 | 0 | $0.0129 |
| refactor | `d1fd50f` test: execute analysis_api's documented test command verbatim | 1 | 8 | 0 | 0 | 0 | $0.0545 |
| refactor | `e953086` test: pin gateway macd/rsi series to an independent reference | 1 | 0 | 0 | 0 | 0 | $0.0207 |
| refactor | `96487d9` test: pin the adviser cap across languages | 1 | 2 | 0 | 0 | 0 | $0.0181 |
| refactor | `034b650` test: guard live candle semantic validation (re-run) | 2 | 9 | 9 | 9 | 0 | $0.1774 |
| docs | `9a68477` docs: verify dual-entry fix in production and refresh Task 7 | 3 | 0 | 0 | 0 | 0 | $0.0213 |
| docs | `aa2a4cf` docs: log nasdaq halt-timestamp fix in adapters progress ledger | 1 | 0 | 0 | 0 | 0 | $0.0102 |
| docs | `fa85b21` docs: hand the branch over to a sonnet-tier agent | 1 | 0 | 0 | 0 | 0 | $0.0208 |
| docs | `44d396c` docs: record the dual-entry republication fix in the ledger | 1 | 0 | 0 | 0 | 0 | $0.0090 |
| docs | `07a6946` docs: record the follow-up round in the ledger | 1 | 0 | 0 | 0 | 0 | $0.0042 |
| docs | `9c023e6` docs: propose a fix plan for dual-entry filing re-announcements | 1 | 0 | 0 | 0 | 0 | $0.0146 |
| feature | `801fb29` feat: add verified regulatory and agency sources (re-run) | 13 | 17 | 12 | 12 | 0 | $0.1796 |
| feature | `abefa25` feat: register verified company ir feeds (re-run) | 12 | 7 | 2 | 2 | 0 | $0.1043 |
| feature | `8cfab6c` feat: widen sec current-filings coverage to 10-Q, 10-K and s (re-run) | 15 | 18 | 14 | 14 | 0 | $0.1824 |
| feature | `3a32c92` feat: guard pattern signal text against action verbs at construction (re-run) | 2 | 5 | 3 | 3 | **1** | $0.0767 |
| feature | `d6ceb70` feat(market_gateway): serve patternShapes in snapshot indicators | 2 | 5 | 0 | 0 | 0 | $0.0600 |
| feature | `e17c686` feat(analysis_core): add patterns-shapes-v1 detection engine | 4 | 0 | 0 | 0 | 0 | $0.0499 |
| feature | `b57092c` feat: add plain-language vocabulary for rvol, volatility, breadth | 3 | 0 | 0 | 0 | 0 | $0.0466 |

Publications: 1/20 commits (0/7 refactor, 0/6 docs, 1/7 feature). Money spent: $0.8076
(first pass) + $0.7204 (re-run of five) = **$1.5280** of the $1.90 reservation; the table's
per-commit figures use the re-run where one exists ($1.1652 summed).
Verification outcomes on the 40 verified candidates (ledger `verification` rows): 25 generation
failures at the $0.25 per-PR budget (`BudgetExceeded` before the second attempt on the three
large feature commits), 10 unfaithful generated tests (fail on base as well), 3 not
reproduced (pass on head), 1 collection DEFER, 1 new-code DEFER, 1 reproduced. The per-PR
budget, not the model, decided most of the feature-commit silence: at K = 4 with generation
the $0.25 default funds about five reproductions.

## The publication: `3a32c92`, candidate `7ecf2fb275`, task `20260903-021750-af3b3ea7`

The commit adds a guard to an existing `PatternShapeSignal.__post_init__`: every served text
field is swept against `plain_language.BANNED_VERBS` (`买入`, `卖出`, `加仓`, `抄底`, `梭哈`)
and a match raises `ValueError` ("a banned verb refuses to construct instead of shipping").
The certified claim: "the banned-verb guard uses substring containment and rejects
legitimate copy that merely contains a banned verb inside a longer word". The generated test
constructs a signal whose summary is `本次形态与买入价曾经历史新高相关…` and asserts construction
succeeds. Receipt (`.attest/corpora/us-stock-helper/.attest/evidence/20260903-021750-af3b3ea7/7ecf2fb275/`):
head FAIL 3/3, base PASS 3/3, `linux-container-v1`, fresh state, sealed, binding
`attest.binding.changed-line-coverage.v1` with changed lines 346-351 and 355 executed.

**The receipt is valid and the kernel did what it certifies**: on the changed lines head
rejects an input base accepted. **The claim is not what the receipt proves.** The phrase
contains the banned verb `买入` verbatim, which is the exact input the commit exists to
reject; the "legitimate word" was fabricated by the generator, not drawn from the
repository's reviewed copy table (the candidate's own falsification plan said to look there
and the generator did not). A validation-tightening commit on an existing definition is
regression-eligible under D-063's rule (the definition exists at the merge-base), and for
such a commit *every* newly rejected input yields `head_fail_base_pass`. This is the known
blind spot of the regression-only differential V (memory and D-078: intended behavior change
versus regression is not decidable from head/base outcomes alone), now observed on a natural
commit rather than argued.

Root cause under RISK-CERT-01: not a kernel bypass — the publication carried a current
accepted receipt — but a receipt whose evidence class (`regression_reproduced`) is wider than
the words published ("false positive on legitimate copy"). The register gains the row
`RISK-INTENT-01` for it. What stops it is a discriminator the owner has to choose (D-100):

- (a) a `new_rejection` result class: when the head failure is an exception raised from a
  changed line of the anchored file (innermost reviewed frame ∈ changed lines, the `raise`
  added by the diff), the evidence is "head rejects an input base accepted" and goes to
  the drawer unless the rejected input is a literal present in the reviewed tree at head
  (a fixture, a copy table, an existing test); the author sees it as a question, not a
  finding;
- (b) keep publishing such receipts but word them as what they prove ("this change rejects
  the following input, which the base accepted — intended?") under a distinct evidence
  class, so the published text never claims more than the receipt.

Neither is implemented in this window (no statistical constant or publication semantics
change without the owner). Per the owner's rule every paid run stopped when this
publication appeared: the held-out run at 68 of 69 results, the bootstrap re-run of the 18
pytest/pylint held-out cases not started, nothing re-run.

## Caveats

- The $0.25 per-PR budget bounded verification on the three large feature commits (25 of 40
  verified candidates never got a generated test); a null study at a higher per-PR budget
  would verify more and could publish more — the observed rate is a lower bound on what the
  present policy would publish on this corpus at higher budgets.
- The three re-run commits `034b650`, `801fb29`, `8cfab6c` had their run-status lines cut
  from the driver's 2,500-character log tail; their candidate, eligible and verification
  counts come from the corpus ledger.
- n = 20 on one repository by one author; this is the first natural-null measurement, not
  `G-NULL-001`.
