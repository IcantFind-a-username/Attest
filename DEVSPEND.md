# Development spend ledger

Hard cap: $10 API spend for all development including dogfood (handoff guardrail 4).

## API spend (counts against the $10 cap)

| date | item | cost |
|---|---|---|
| 2026-08-29 | (none — no API key present on this machine; see D-013) | $0.00 |

**Total API spend: $0.00 of $10.00.**

## Session-subscription compute (does NOT count against the cap; recorded for transparency)

Dogfood proposer samples and verification workflows ran as harness subagents on
the operator's session (D-013). Itemized subagent tokens:

| item | tokens |
|---|---|
| Corum recon (calibration/dependence port survey) | 63,712 |
| Phase-0 verify workflow (9 agents) | 653,570 |
| Phase-1 verify workflow (21 agents) | 1,415,028 |
| Dogfood samples: pygments K=5 | 302,888 |
| Dogfood samples: corum-code K=5 | 426,471 |
| Dogfood samples: attest-self K=5 | 611,387 |

## What the dogfood reviews would have cost on the product path (estimates)

Per the in-repo ledgers (preflight-estimated, mock token counts for outputs):
pygments review ~$0.012; corum-code review ~$0.016; corum-docs review $0.000
(budget-deferred before any call); attest-self review ~$0.27 (run at
--budget 0.5). All within the $0.25 default per-PR budget except attest-self,
which used the budget knob explicitly.
