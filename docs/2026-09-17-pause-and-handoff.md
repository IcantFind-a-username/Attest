# Attest is paused — 2026-09-17

**The owner is pausing this project for capacity reasons**, to work on the Latch security
foundation and two closed-source iOS applications. This is not an abandonment of the work and
not a verdict that the ideas were wrong. It is a stop with the books closed, so that whoever
opens this repository next — including the owner, later — can tell in ten minutes what was
proven, what was not, what is worth lifting out, and what should be left where it lies.

Nothing here is pushed to any remote. The last commit on [`fix/runtime-compatibility`](https://github.com/IcantFind-a-username/Attest/tree/fix/runtime-compatibility) is the
state of record: this branch on `main` carries only this notice, so that the landing page
says what happened without `main` absorbing a round of unfinished exploration.

## 1. Why it stops, in numbers rather than feeling

The product was a pull-request reviewer. Measured on the two populations the repository owns:

| population | claims | confirmed with a receipt | refuted with evidence | no verdict |
|---|---:|---:|---:|---:|
| 40 planted defects (arm C, paid) | 40 | **13** | 6 | **21** |
| 24 merged pull requests (batch 3, paid) | 55 | **0** | 8 | **47** |

On the corpus built to be favourable, the reviewer reaches a verdict on fewer than half its own
claims, and twenty of the twenty-one silences are the intent rule abstaining: the differential
held, the behaviour changed, and no rule could say whether that was a defect or an intended
change. On real merged traffic it confirmed nothing at all.

The open problem is not engineering. It is **telling a defect from a deliberate change**, and a
month of work on it (D-249 through D-282) netted zero: D-257 closed a real mis-attribution and
removed the capability with it; D-282 restored the capability with the mis-attribution closed.
Same place, a month later, better understood.

## 2. What was proven, and is worth taking to Latch

Three things survived every probe, are independent of the reviewer product, and total about
4,000 lines:

**Execution isolation and the request protocol** (`src/attest/execution/`, 2,213 lines).
Read-only tree mount, no network, process and memory bounds, an artifact allowlist, a minted
request that must survive a strict decoder, and a result envelope whose digests are recomputed
before anything is believed. P-01 ran a Go differential through it with six recorded Python
assumptions, all in the container adapter, none in the protocol
([report](https://github.com/IcantFind-a-username/Attest/blob/fix/runtime-compatibility/docs/acceptance/2026-09-16-language-probe.md)). For running untrusted code, this is the
part that already works.

**The certification kernel and its offline receipt** (`src/attest/certification/`, 1,737 lines,
standard library only). It decides whether a record of what happened may be believed, and a
bundle can be re-verified with no repository, no network and no model. P-02 had the unchanged
kernel accept a Go regression on evidence derived from a Go panic trace and Go coverage. P-03
adjudicated 63 claims with 42 false ones among them and confirmed none of the false
([report](https://github.com/IcantFind-a-username/Attest/blob/fix/runtime-compatibility/docs/acceptance/2026-09-16-claim-verification.md)).

**Non-perturbing observation** (`scripts/probe/contradiction_audit.py`, the `sys.monitoring`
plugin). Observing a program's returns without rebinding anything: seven libraries ran twice,
clean and observed, with identical pass, fail, skip and xfail counts. The earlier
attribute-wrapping version changed jinja's suite from 911 passed to 910 passed and 1 failed,
which is exactly the failure mode an agent monitor cannot afford
([report](https://github.com/IcantFind-a-username/Attest/blob/fix/runtime-compatibility/docs/acceptance/2026-09-17-contradiction-audit.md)).

One warning that belongs with them: **an empty observation still publishes**. P-02 found that a
record with nothing in it passes the intent rule, because a rule can only judge what was
recorded. Any new adapter or monitor built on this kernel needs its own test that an unobserved
failure cannot certify.

## 3. What should be left where it lies

- **The Python contract reader and the intent policy line** (`contracts.py`, `contract_context.py`,
  `intent.py`, about 3,800 lines, D-252 to D-282). It reads Python syntax, it is fragile, and its
  best measured yield was three cases of a forty-case diagnostic set.
- **The SWE-bench and natural-pair corpus work** (about 90 commits on 2026-09-16, D-260 to D-281).
  Zero qualified samples. The reports are honest and the failures are recorded; the effort is not
  worth resuming without a different repository selection.
- **The contradiction audit as a product.** Five findings across eight mature libraries is real
  but too thin to ask anyone to install a tool for. The instrument is worth keeping; the product
  is not.

## 4. If someone restarts this

Operational facts that cost days to rediscover:

- **The virtual environments break silently.** Every `.pth` file in this repository's `.venv` and
  in each corpus environment was flagged `hidden` on macOS, so `site` skipped them and imports
  failed with no useful message. `chflags nohidden <venv>/lib/python3.12/site-packages/*.pth`
  fixes it. Ten of twenty-one cases in P-03 were unusable until this was found, and any
  measurement taken while it was set was measuring a broken environment.
- **Docker needs a credential-free client config.** Point `DOCKER_CONFIG` at a directory whose
  `config.json` names no `credsStore`, or every build hangs on the macOS credential helper (D-253).
- **Thirteen branches are unmerged.** `fix/runtime-compatibility` is the mainline of record; the
  others are variations of the same 2026-09-16 work, and `feature/git-query-profile` carries
  unresolved security findings from an unfinished experiment.
- **The gate takes about forty minutes** under Docker and passed last on `ba91320`: 2,492 tests,
  93.42% kernel and execution coverage. The last product commit, `d57530e` (D-282), passed at
  93.35%.

The question to answer before writing any more code: **what evidence distinguishes a defect from
an intended change?** Until that has an answer, more reader rules will keep trading one silence
for another.

## 5. The books

Total paid model spend across the project's life: **$145.46** against an approved cap of $150.00.
Every round since 2026-09-15 — D-249 through D-282, and probes P-01 through P-05 — cost
**$0.00**: they ran on frozen ledgers, local corpora and containers. No remote was ever written
to; nothing was ever pushed.
