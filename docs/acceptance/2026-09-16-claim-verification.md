# P-03, 2026-09-16 — Attest as a verification layer: 63 adjudications, zero false confirmations

**Owner instruction of 2026-09-16 ("做").** The question is not how many defects Attest finds.
It is: given a defect claim about a change, can Attest adjudicate it? No model call, no paid
spend, no product change, nothing pushed. Instrument:
`scripts/probe/claim_verification_probe.py`. Record:
[`evidence/2026-09-16-claim-verification/p03.json`](evidence/2026-09-16-claim-verification/p03.json).

## 0. The result

Twenty-one cases of `mutations-v1-recall`, each adjudicated three ways, three repeats per side:

| population | the claim | what it should be | result |
|---|---|---|---|
| **true** | the recorded change breaks behaviour | confirmed | **21 of 21 confirmed** |
| **null** | a head that adds one comment line breaks behaviour | refused | **21 of 21 refused** |
| **reversed** | the same two revisions the other way round, so the change under review is the repair | refused | **21 of 21 refused** |

**63 adjudications, 42 of which are false claims, and not one was confirmed.** The oracle is the
repository's own test that D-251 recorded as detecting the change; the verdict rule is the
product's own: the oracle passes on the parent in every repeat and fails on the head in every
repeat, or the claim is refused.

## 1. What this supports

The adjudication half of Attest does what it says on a population it did not produce. A claim
arrives with a change and a symbol; the answer is a reproducible differential or a refusal. The
reversed population is the interesting one: the behaviour does change there, and a tool that
merely looked for "a difference between the revisions" would have confirmed all 21. The
direction rule refuses every one of them.

This is the capability the two Go probes showed to be language-neutral (P-01, P-02): run a test
on two revisions under isolation, and judge the result by a fixed rule.

## 2. What this does not support

- **The oracle is given.** D-251 recorded which of each repository's tests detects each change.
  Choosing that test for an arbitrary claim is the hard part, and this probe does not do it.
  When no existing test covers the claimed behaviour, a probe has to be written, which is where
  the model, the cost and the unmeasured part of the product live.
- **The location is not adjudicated.** A true claim naming the wrong file or line would still be
  confirmed here: the probe runs no tracer, so it shows the change causes the failure, not that
  the claimed line is the one that runs. The product's binding observation does that, and P-02
  showed it can be filled from a Go panic trace as well as a Python tracer.
- **The claims are planted changes**, not a third party's prose. A real claim from another tool
  arrives as text about code, and mapping it to a change and an oracle is unmeasured.
- **The population is 21 cases of 8 libraries**, all Python, all from a corpus this project has
  used before. Wilson 95% for 0 false confirmations in 42 false claims is [0.0%, 8.4%].

## 3. An operational finding, worth naming

Ten of the twenty-one cases were **unusable on the first run**: every corpus virtual environment
had its `.pth` files flagged `hidden` on this macOS host, so `site` skipped them and the library
under test could not be imported at all. The same flag had disabled the repository's own
development environment. One `chflags nohidden` over the corpus restored all ten, and the
result above is the repaired run; the first run's tallies (4 confirmed, 7 refused, 10 unusable)
are kept in the record.

Anything measured on these environments while the flag was set was measuring a broken
environment. That is worth remembering when reading the 2026-09-16 qualification studies.

## 4. What would turn this into a product claim

Two things, in order:

1. **Oracle selection**: given a claim and a change, choose or write the test that adjudicates it.
   Today that is the model's probe, whose real-traffic yield is still zero certified on 28 pull
   requests.
2. **Third-party claims**: run the same adjudication over claims another tool or agent produced,
   with their own wording and their own locations, and report confirmed, refused and
   undecidable. That needs a claim source, which this probe deliberately did not invent.

Until (2) exists, the honest summary is narrow and real: **on claims about a change, with an
oracle in hand, this adjudicates correctly and refuses everything false it was given.**
