# Decision log

Historical D-001 through D-037 use the original compact format. New decisions use dated,
structured entries with scope, consequences, reversal conditions, and affected invariant/
Gate IDs. Event/correction records use `Reverse: n/a`; they are evidence, not trade-offs to
reopen. Historical entries remain evidence; a new decision that changes a normative contract
is active only when the owning architecture/acceptance document changes with it.

- **D-001 toolchain**: hatchling + src layout, dist/import name `attest`, Python >=3.11 (dev machine 3.14), numpy as the only runtime dep for core (**amended by D-006**: the CLI adds the anthropic SDK, so numpy-only scopes to `attest.core`). Why: handoff spec; smallest surface. Reverse: anytime before publishing.
- **D-002 forbidden-token policy**: commit-msg hook rejects any case-insensitive AI-assistant name in commit messages; branch names and comments keep the same rule. Model identifiers (e.g. the default proposer model id) are product data mandated by the spec and live in config/data files, not in commit messages or branch names. Why: owner's git discipline + the spec itself fixes the default model id. Reverse: owner call.
- **D-003 exploration "relevant cells" (revised after independent review)**: the eps=0.10 -> 0.02 drop triggers when every MARGINAL cell (theta x verdict per judge) has >= 30 samples. Pairwise and triple cells are excluded: review verified empirically that under near-deterministic cloning (gamma=0.99) the rarest pair cell needs ~340k tasks to reach 30, pinning exploration hot forever and making the spec-mandated 0.02 phase unreachable; thin pair/triple cells are guarded by the tau=0.05 floor instead (RESULTS §5). Reverse: one predicate.
- **D-004 winner's-curse monitor defaults**: rolling window 200 purchases; alarm when a judge's mean(realized log-e minus estimated log-e) < -0.15 nats with n>=30 in window, or when any judge's spend share in the recent half-window drifts > 0.15 absolute vs the prior half. Alarms are appended to the ledger only; no automatic intervention (spec). Why: spec fixes the mechanism but not the constants; these are conservative first guesses. Reverse: constants are config; recalibrate after dogfood.
- **D-006 anthropic SDK is a runtime dep** (amends D-001's numpy-only, which now applies to `attest.core` only): the CLI needs the Messages API. Core still imports nothing beyond numpy. Reverse: split packages if core is ever published alone.
- **D-007 S-channel factory schedule**: vote m contributes LR1^((1-rho)^(m-1)) with LR1=2.0, rho=0.6, cumulative product capped at 3 -> schedule 2.00 / 2.64 / 2.95 / 3.00 / 3.00. Why: spec fixes rho~0.6, diminishing 2..K, cap 3, but not the curve; this one is monotone with shrinking marginal gain and hits the cap by vote 4. Reverse: constants in channels.py; recalibrate at >=500 labels (globally only).
- **D-008 gate reachability (red line 4)**: at factory caps S*T=9 < 10 = 1/alpha default, so the phase-1 gate is UNREACHABLE without verification — by design, not accident: MVP surfaces only reproduced findings ("宁可不说,不说错"). The CLI prints this note on every run, and refuses outright to run a gate that verification cannot reach either (e.g. alpha < 20/180... i.e. 1/alpha > 180). V channel in MVP = human-in-the-loop `attest verify` recording a reproduction attempt (LR 20 reproduced / 0.5 failed); the automated evidence executor stays post-MVP per handoff. Reverse: owner may loosen default alpha or raise caps after dogfood evidence.
- **D-009 alpha auto-tighten bookkeeping**: tightenings are recorded as ledger events (kind=alpha_tightened) in the reviewed repo, not by writing to that repo's files; `attest stats` and reports surface them. Requires >=10 labeled surfaced findings before acting. Why: a tool must not edit user documents; the ledger is the audit trail. Reverse: config auto_tighten_alpha=false.
- **D-010 per-finding spend attribution**: the K-sample proposal cost is shared; ledger review rows split it evenly across candidates (spend = total/n). Why: spec wants spend per row; even split is the only defensible cold-start allocation. Reverse: cost model later.
- **D-011 po_adaptive is experimental, with a known directional-pooling bias**: independent review confirmed the pooled pair table mixes both purchase directions while inclusion depends on the first verdict, so the reverse-direction conditional read is biased under heterogeneous purchase orders. Matches the seed prototype's engine_po semantics (RESULTS §6 documents its residual pathologies); documented rather than redesigned because the variant is a comparison flag, not the default. Reverse: split pair tables by direction if the variant is ever promoted.
- **D-012 monitor estimates are SIGNED expected log-e** (fix from independent review): the winner's-curse monitor originally compared the nonnegative allocation value (symmetric KL) to the signed realized log LR, which alarms permanently on healthy judges (expected gap -2(1-p)KL(q0||q1), several times the threshold). Now the recorded estimate is p*KL(q1||q0) - (1-p)*KL(q0||q1), the model expectation of the realized quantity: healthy gap ~0, real optimism goes negative. Allocation still uses the symmetric value (correct decision value). Reverse: n/a — correction/validation record.
- **D-013 dogfood sampling path**: no ANTHROPIC_API_KEY exists on this machine (checked process/user/machine env and the vendor CLI), so dogfood samples are generated by K parallel harness subagents running the EXACT system+user prompt and schema the product would send (same model family as the configured default), then replayed through `attest review --mock`. Everything downstream of sampling — validation, dedup, votes, channels, gate, ledger, verify, feedback — is the real product path. Consequences: p50 latency of the model call and live ApiProvider are NOT validated (deferred to owner with a key); token spend billed to the session, not the $10 API cap (recorded in DEVSPEND.md). Dedup thresholds were calibrated on the first dogfood run (graded by anchor agreement: exact line 0.15, near line 0.35, over claim+failure tokens). Reverse: rerun dogfood with ApiProvider once a key exists.
- **D-014 phase-1 independent review yielded 8 confirmed defects, all fixed**: path normalization ate dotfile prefixes (lstrip -> proper prefix strip); diff content could spoof file headers (header state machine added); `--mock` with zero files fell through to the real API (nargs='+' + MockProvider guard); sentence counter inflated on code spans/abbreviations/decimals (code-span strip + boundary regex + abbreviation list); tier-0 path match lacked component boundary (tests/utils.py corroborated utils.py); alpha auto-tighten re-halved on stale label windows (label-count watermark) and ignored the config-off flag for replay; cap-overflow findings were excluded from the precision loop (action renamed overflow_surface) and re-verification double-counted (dedupe by finding id); CLI overrides bypassed config validation (dataclasses.replace + error exit). Reverse: n/a — correction/validation record.
- **D-015 live-API validation supersedes D-013's deferral**: owner supplied ANTHROPIC_API_KEY (user-level env var; long-lived processes must re-read it from the User scope); live runs on 2026-08-29 validated the real ApiProvider path (schema 400 found+fixed @71db3f4, then 11.1s surfaced review + negative control, $0.1526 total, DEVSPEND.md). D-013's mock pipeline remains the keyless fallback. AGENTS.md added as the standing guide for coding agents. Reverse: n/a — validation event.
- **D-016 automated acceptance with private remotes (owner directive 2026-08-29)**: phases end with agent-run end-to-end acceptance, not owner handoff. Private GitHub repos (attest mirror + scratch) authorized for testing only; secret set via gh piped from env; public release still owner-gated. Precondition: gh auth or GH_TOKEN (the one allowed stop-and-ask). Reverse: owner call.
- **D-017 evidence-process containment**: POSIX reproduction pytest lowers `RLIMIT_NPROC` soft+hard to zero before exec, fails closed where the limit is absent or privilege can bypass it, and uses startup/audit markers so ordinary process attempts (plus Python thread attempts, because Linux counts threads) are DEFERRED; descendant polling and retained PIDs are forbidden, while Windows keeps its bounded process-tree fallback. Why: post-spawn ancestry sampling can miss exit-race children and reused PIDs can target unrelated processes. Reverse: replace with a scoped kernel container/job primitive that is available without runner privileges on every supported host.
- **D-018 Phase-3 acceptance boundary**: scratch-repository acceptance is a policy service over injected subprocess/filesystem adapters, with a separate opt-in live executor; local tests use fakes and the executor passes the model key only through command stdin. Acceptance preserves the executor's ternary verification semantics (reproduced / not-reproduced / deferred), treats its Python network guard as best-effort rather than global isolation, and requires the uploaded JSONL ledger artifact to persist and account for review, verification, and GitHub-comment events. Why: deterministic local policy tests must not need remote authority, secrets, or paid calls, while a retained artifact and URLs make the eventual live result independently inspectable. Reverse: replace the adapters if GitHub supplies a first-class test harness; replace best-effort isolation only with a cross-platform scoped kernel primitive; replace artifact persistence only when an equally durable auditable store accounts for every event.
- **D-019 benchmark corpus boundary**: the public manifest and validator are corpus-agnostic records over opaque pairs, prepared checkout paths, argv, provenance, source-license evidence, and explicit exclusions; BugsInPy remains a metadata-only adapter. Validation is offline by default, never runs upstream setup scripts, and requires three fixed passes plus three stable buggy failures. Project license evidence must be recognized from LICENSE/LICENCE/COPYING in both pinned upstream commits; an unspecified BugsInPy dataset license is recorded but does not authorize copying dataset artifacts (none are committed). Why: arbitrary local projects need the same evaluator contract, and missing/flaky/integrity evidence must not become silent negatives. Reverse: add adapters or container runners behind the generic interfaces without changing pair/scoring semantics.
- **D-020 differential evidence is regression-only, by construction**: VERIFIED now requires the same generated reproduction to fail deterministically on the reviewed head (N=3) and pass on its immutable base (N=3), in owned detached worktrees; fail/fail is an unfaithful test that DEFERS and never becomes V_FAILED, and any flaky side DEFERS. Consequence discovered during integration: a diff that ADDS code cannot be certified at all, because the symbol is absent on base and the base run's error is indistinguishable from an unfaithful test — so attest is structurally silent on new-code defects, and the BugsInPy corpus hides this because its replay cases reverse a developer fix (the function exists on both sides). Why: single-sided evidence let a fabricated finding and a real bug walk identical trajectories, and generated tests are measurably flakier than human ones; regression-only certification is the safe subset. Reverse: a four-way classification (regression-reproduced / new-code-candidate / unfaithful / not-reproduced) can price the new-code case once ledger data exists — it needs a new LR constant, so it is an owner decision under ground rule 8, never a silent addition.
- **D-021 differential evidence validated live (2026-08-30)**: three real-model runs against purpose-built git repositories confirmed the executor's three decisive behaviours. A genuine regression (an empty-input guard deleted from `parse_range`) produced two drawer candidates in 7.4s; both bought V through `head FAIL 3/3, base PASS 3/3`, lifting wealth 2.64 -> 52.78 and 2.95 -> 58.97 into surface. A semantics-preserving refactor produced zero candidates in 3.8s (silent negative control). A deliberately fabricated finding injected on that same clean refactor was refuted: the generated reproduction passed on head 3/3, so the run ended `not_reproduced`, wealth fell 2.95 -> 1.48, and it stayed in the drawer. Total $0.0509, logged in DEVSPEND.md. Why: single-sided evidence could not distinguish these three cases, which was the defect D-020 fixes; this is the first end-to-end evidence that the differential gate separates them on the real model path. Reverse: none needed - this is a validation record, not a design choice.
- **D-022 evidence classes are recorded, and the new-code class is deliberately unpriced**: every differential run now carries one of `regression_reproduced`, `new_code_candidate`, `unfaithful`, `not_reproduced`, or `indeterminate`, written to the verification ledger row. The new-code class is recognised by signature - no head run reports the symbol absent, so the code genuinely misbehaved, while the base run fails because the symbol is absent - and it buys nothing at all: the run stays DEFERRED and `verify_candidate` returns the identical gate result, so neither V nor V_FAILED is applied. A fabricated finding cannot masquerade as new code, because a reproduction naming a symbol that exists nowhere fails on HEAD with the same symbol-absent signature, which the rule excludes outright. **Amended after D-029**: that head-misbehaviour condition was originally applied only to this unpriced class and not to certification, which is precisely the gap the rename-refactor false positive exploited; it is now a precondition of buying any evidence at all. Live check on 2026-08-30: a genuine defect in a newly added helper (5/5 proposer votes, reproduction failing 3/3 on head) was classified `new_code_candidate` and left at wealth 3.00, unchanged. Why: this is the D-020 adoption ceiling made measurable without inventing a likelihood ratio for it. The head-side condition was widened after the first live acceptance run: it originally demanded assertion-class head output, which misclassified crash-shaped reproductions (a real ZeroDivisionError defect in new code was published as 'unfaithful generated test'), and now demands only that no head run reports the symbol absent. Reverse: pricing this class needs a new constant and >= 500 global labels of evidence, so it is an owner decision under ground rule 8.
- **D-023 correlated-panel ablation, restated after adversarial review: all four statistical objections were upheld and the headline claim is weaker than it was published as**: an offline, experiment-only harness (`src/attest/benchmark/experiments.py`, synthetic Bernoulli panels, no model calls, production constants imported never redefined) compares naive independent aggregation `LR1**votes` against the D-007 discounted schedule, k=5, 2000 tasks x 5 seeds. The original entry's headline numbers and both of its qualifying sentences were wrong; what replaces them is below, together with what changed and why. The four defects, each reproduced by a check that now pins it: (1) every rate used a per-TASK denominator that counts null tasks no sample ever proposed, but nominal alpha bounds the error rate over the findings the gate actually judges; (2) the two arms are nested and share every draw, so the 'overlapping intervals' reading applied an independent-sample test to paired data; (3) the gamma=0 fairness control ran only at the two factory alphas, which are precisely the gates S_CAP=3 makes unreachable for the discounted arm, so it never tested the discount at all; (4) the swept parameter is the generator's clone rate, not the pairwise correlation it produces. **Corrected axis (objection 4).** Only vote one is cloned, so the panel is not exchangeable: corr(v1,vj)=gamma while corr(vi,vj)=gamma^2 for later pairs, giving mean pairwise correlation ((k-1)gamma + C(k-1,2)gamma^2)/C(k,2), strictly below gamma everywhere in (0,1). The preregistered clone rates 0/0.3/0.6/0.9/0.99 generate measured correlations -0.001/0.174/0.463/0.845/0.985 against analytic 0/0.174/0.456/0.846/0.984. The grid was NOT re-chosen after the fact: the axis was relabelled, and every cell now carries the correlation it truly generates, measured from the drawn ballots. The clone rate that would actually deliver correlation RHO is 0.721, not RHO. The claim that gamma=RHO is 'the one correlation level at which D-007's assumption is literally true' is WITHDRAWN as indefensible: no clone rate makes the schedule the vote count's likelihood ratio - scanning the whole axis, the best fit is clone rate 0.597 and still misprices some vote count by 3.34x - and the exact ratio is non-monotone under correlation (a middling count is evidence AGAINST a clone panel, which is nearly unanimous either way) while the schedule is monotone by construction. D-007 is a heuristic discount and this ablation does not validate it as a likelihood ratio. **Corrected result (objection 1), per candidate - the null tasks that produced a candidate, which is the population alpha bounds.** At alpha 0.1 the naive arm runs 0.054 -> 0.161 -> 0.389 -> 0.780 -> 0.975 across the sweep, peaking at 9.8x nominal; at alpha 0.05 it runs 0.004 -> 0.035 -> 0.163 -> 0.608 -> 0.946, peaking at 18.9x. The published per-task series (0.047 -> 0.123 -> 0.239 -> 0.329 -> 0.336, '3.3x nominal') understated the error by up to 2.9x and understated it MOST where correlation is highest: the share of null tasks producing a candidate falls 0.872 -> 0.765 -> 0.613 -> 0.422 -> 0.345, so the wrong denominator diluted exactly the effect under study. The reported saturation between the top two sweep points was a denominator artifact - per candidate the rise is strictly monotone across the whole grid. Both denominators are now emitted under unambiguous names and neither may be quoted as 'the rate'. The breach of nominal alpha begins above realized correlation ~0.08 at alpha 0.1 and ~0.22 at alpha 0.05, replacing 'once gamma exceeds roughly 0.25', which was in clone-rate units on the diluted denominator. Unchanged and still true: the discounted arm wrong-certifies nowhere at either factory alpha at any correlation, and that is the D-008 cap arithmetic (S_CAP=3 < 10 = 1/alpha), not inference. **The paired comparison (objection 2) replaces the old qualification.** The arms are nested - the naive product dominates the capped discount at every vote count, so the discounted certification set is a subset and every discordant pair runs one way (discounted-only = 0 in all 15 cells). At the derived shared-speech gate alpha=0.356 (midpoint of the window where both arms can reach the gate), at clone rate 0.9 the arms' independent Wilson intervals DO overlap (0.810 vs 0.796 per candidate) - which is what the withdrawn sentence read as equivalence. The paired analysis says the opposite: 29 discordant pairs, all naive-only, exact McNemar p = 3.7e-9, paired difference 0.0137 with 95% bootstrap interval [0.0090, 0.0189] excluding zero. **The sentence 'at gamma 0.9 the two arms become statistically indistinguishable (0.342 vs 0.336, overlapping intervals)' is withdrawn: it was the wrong test on the wrong denominator, and its conclusion is false.** What is true is that the MAGNITUDE of the discount's advantage collapses with correlation - paired difference 0.382 / 0.262 / 0.113 / 0.0137 / 0.0006 across the sweep - and only at clone rate 0.99 does it become genuinely undetectable, on a single discordant pair (p = 1.0). The discount is the better aggregator in every cell of this grid; it just stops being worth anything. **The fairness control (objection 3), re-run where it can measure something.** At the factory alphas the discounted arm cannot certify at any vote count, so the old control established only that the naive arm is inside alpha there (0.07x and 0.54x per candidate). Run at the shared-speech gate under PERFECT INDEPENDENCE (clone rate 0, measured correlation -0.001), the naive product is already anti-conservative: 0.624 per candidate against alpha 0.356, 1.75x, Wilson lower bound above alpha - while the discounted arm sits at 0.242, 0.68x, and does not breach. **So the claim that 'the discount is priced against correlation itself rather than against the naive aggregator' does not survive**: at the only gates where the two can be compared at all, the discount is already worth 0.38 in wrong-certification rate with zero correlation present. A capped one-sided schedule is simply more conservative at a loose gate, and an unknown share of its advantage at high correlation is that generic conservatism rather than correlation pricing. This ablation cannot separate the two and no longer claims to. **Consequence for the external claim.** attest prices correlated votes so that it abstains correctly at shipped settings, and must NOT be sold as better inference on correlated panels - that conclusion is unchanged, but it now rests on evidence that is much stronger against the naive aggregator and much weaker about the discount's mechanism. Two limits stand alongside it: the vote channel prices only positive votes, so neither arm is a martingale-valid e-value and the cap rather than a Ville bound is what holds the discounted arm (D-026); and above realized correlation ~0.46 the discounted arm itself breaches alpha at the shared-speech gate, so its safety is a property of the shipped gates and not of the schedule. Reverse: none; recommendation_only under red line 5 (< 500 global labels), and no constant may move on synthetic evidence.
- **D-024 identifier resolution collects signal, it does not veto**: findings whose claim names code identifiers that resolve nowhere in the anchored file are recorded as an `identifier_check` ledger row and then proceed to the gate untouched. The check was built as a veto and deliberately demoted before merging, for two reasons. First, the V channel already stops hallucinated symbols at no extra cost: a reproduction naming a symbol that exists nowhere fails on HEAD with an absent-symbol signature, which D-022's classifier excludes from the new-code class outright, so it can never buy evidence. Second, resolution consults only the anchored file, so a correct reference to a helper defined elsewhere - or a dotted module path written in prose - is indistinguishable from an invented name, and a false veto silently destroys a true finding, which is this project's worst failure mode. The check therefore buys cost savings rather than safety, and that trade must not be taken blind. Reverse: promote it to a veto only with a measured false-veto rate from real ledger rows, and only by owner decision.
- **D-025 the evaluation layer wraps the product and never re-derives it**: the replay runner, generic project API, artifact store, and report modules drive the real `run_ci` against recorded proposer/generator cassettes and a loopback GitHub endpoint, so gate, executor, ledger, and pytest execution are the shipped code paths rather than reimplementations. Differential status comes from the product's own `EvidenceClass` through one total mapping in which only `regression_reproduced` can match truth; `new_code_candidate` carries its own status so it is never scored as an unfaithful or unreproduced failure, and every report states that class is unpriced by design. The product ledger and the benchmark oracle stay separately inspectable: the oracle re-runs under a distinct task identity with its own budget and writes no ledger rows, so scoring never rewrites a historical product decision. Artifacts are allowlisted, secret-redacted, bounded, and hashed into a manifest written last by atomic replace. `Prediction` gained an `evidence_class` field with a default, which the plan's Task 5 could not have anticipated because the class did not exist when it was written. Why: an evaluation harness that reimplements the thing it evaluates measures the harness. Reverse: none needed; the layer adds no production behaviour.
- **D-026 the wealth process is not an e-process, and the error control rests on reproduction**: an offline diagnostic (`experiment-evalue`) measured `E[LR | theta=0]` for each factory channel, after first validating its estimator against an oracle likelihood ratio built from the simulator's own densities, which measured 0.9966-1.0010 as it must. Results: the S channel measures 1.76-2.28 unconditioned and 2.48-2.80 conditioned on being proposed at all, with every interval far above 1; the T channel measures 1.10-1.51 under an assumed spurious-overlap rate, and its e-validity ceiling is 0.0 - no positive rate works. Both channels price only positive evidence and have no factor below one, so no null makes them e-values. V is the only channel that can be one, and only if the false-reproduction rate stays below 0.0128, a number nobody has measured. Selection makes this unfixable by reschedule: the product only ever prices findings some sample proposed, and the never-proposed outcome worth exactly 1 is never observed, so even a provably valid oracle likelihood ratio measures 1.46 once conditioned the same way. Against Ville's bound, the votes-only realized wrong-certification rate is exactly 0.0 at alpha 0.05/0.1 because the caps cannot reach the gate, and the full-channel rate equals the assumed false-reproduction rate and nothing else; loosen alpha past 1/S_CAP and the bound is breached at 1.55x-2.13x. Consequence: attest's type-I error control at shipped settings comes from D-008's cap arithmetic plus the reliability of differential reproduction, NOT from a martingale guarantee, and README says so. The practical reading is that differential V is not a feature on top of the guarantee - it IS the guarantee, which makes measuring its null rate the highest-value experiment this project has left. A two-sided counterfactual lives in the experiment harness only and is not a proposed patch; it is exact at gamma=0 and 4.5x-8.7x off under correlation, so it would not restore the property either. Reverse: none available by tuning a constant; restoring a genuine e-process would require pricing both correlation and non-proposal, which is a research question rather than a schedule change.
- **D-027 the reproduction channel's null rate measured 0 in 40 trials, and that is not yet enough**: D-026 established that differential reproduction is the only thing standing between a false finding and a certification at shipped settings, so its false-confirmation rate under the null is the number the whole error-control story depends on. Measured on 2026-08-30 against real model calls: 40 trials, each a semantics-preserving refactor (base and head behave identically) carrying a fabricated but plausible finding forced into the drawer, each verified by one real differential run at repeats=3. **Zero false confirmations.** Outcomes were 24 `not_reproduced` (the generated test passed on head, so wealth fell 2.95 -> 1.475), 15 `unfaithful` (the test failed on both trees and bought nothing), and 1 `indeterminate` infrastructure deferral. Cost $0.1956 across two batches. **The honest limit**: 0/40 gives a Wilson 95% interval of [0, 0.0876], whose upper bound is still well above the 0.0128 e-validity ceiling D-026 derived for this channel, so the measurement is consistent with the ceiling but does not establish it. Reaching an interval that clears the ceiling needs 296 trials, roughly $1.10 against the $10 development cap, and that is a paid expansion requiring owner authorization under ground rule 4. Why this matters more than a precision figure: every other accuracy number this project could report describes how well it finds real defects, while this one describes how often it would speak falsely, which is the property the product's entire promise rests on. Reverse: none; superseded only by a larger measurement, ideally on real diffs rather than constructed refactors. **Amended after D-029**: this measurement had a sampling gap - none of its trials renamed a public symbol, the one shape that reached the certification defect D-029(a) describes, so it never exercised that path.
- **D-028 a silent review on real code still costs most of the default budget**: dogfooding against an unrelated real project (617 added lines implementing a technical indicator, reviewed at K=5) produced zero candidates in 20.4s and spent $0.2352 of the $0.25 factory budget. The silence is correct - no high-severity defect was proposed, and attest said nothing - but the cost profile is worth recording before anyone reads the per-PR budget as a per-finding cost: proposal sampling is paid on every diff regardless of outcome, and a large diff at K=5 can consume most of the default budget while surfacing nothing. This is the first measurement on code neither written nor constructed for testing attest, so it also serves as evidence against the sampling bias in every other run tonight, all of which used repositories built for the purpose. Why: the honest framing of the product's economics is that you pay for the review, not for the findings. Reverse: none; a per-diff cost model or an adaptive K would change the profile and would need its own measurement.
- **D-029 adversarial review found two reproduced defects, one of them a false positive**: a seven-lens adversarial review of the whole differential-evidence change raised 17 claims; independent refuters killed 10 and could not kill 7, of which two share root causes worth recording. **(a) Certification ignored why the head runs failed.** `head_symbol_is_present` was computed but consulted only to gate the unpriced new-code class, so `head SYMBOL_ABSENT + base PASS` returned `regression_reproduced` and bought V=20. A pure rename refactor therefore certified: I reproduced it directly on shipped code - base defines `_validate`, head renames it to `_is_nonempty` with an identical body, a reproduction asserting on the old name fails 2/2 on head and passes 2/2 on base, and the run returns `reproduced` / `regression_reproduced`. A semantics-preserving change bought the strongest evidence in the system. **(b) The base worktree ran head's code.** The generated test is written inside `repo_root` and import order is steered only by PYTHONPATH, but pytest's prepend import mode inserts the rootdir ahead of it when a root `conftest.py` exists, and `PYTHONSAFEPATH` does not suppress that. For any project with a root `conftest.py` and a flat layout, the base run imported the head checkout, so genuine regressions failed on both sides and were dismissed as unfaithful - a silent false negative that would also have corrupted the benchmark oracle, which maps unfaithful to `buggy_fail_fixed_fail`. **What this says about D-027**: the 0-in-40 null-rate measurement had a sampling gap. Every trial changed an implementation internally; none renamed a public symbol, which is exactly the shape that reaches defect (a). Ten further trials built specifically to rename helpers also produced zero false confirmations, so real models rarely write the reproduction that triggers it, but that is a statement about model behaviour and not about the gate. Why this is recorded rather than quietly fixed: both defects were found by adversarial refutation rather than by 596 passing tests, and the false positive contradicts the product's central promise, so the record should show that the promise was broken and repaired rather than never broken. Reverse: none; both are defects, and the fixes are pinned by tests that observed the failure first.
- **D-030 the reproduction runs inside the revision under test, with conftest discovery bounded to it**: the generated test is now written to `<tree>/.attest-repro/test_repro.py` and pytest is pinned with `--rootdir=<tree> --confcutdir=<tree> -p no:cacheprovider`, so the base leg can no longer import the head checkout's code. Moving the file was necessary but not sufficient: without pinning, rootdir discovery still walks up to the reviewed project's root config, loads its `conftest.py`, and prepends `repo_root` to `sys.path` ahead of everything on PYTHONPATH, which is what produced the D-029(b) silent false negative. `--import-mode=importlib` was rejected because it would also stop the tree's own conftest being reached, and projects legitimately need their fixtures. The precise trigger is narrower than first reported and worth recording: with no config file anywhere, rootdir falls back to the common path of cwd and the test argument, which already sits below `repo_root`; any root-level config anchors rootdir at `repo_root`, and a bare `pyproject.toml` is enough, which every real project has. A second defect surfaced while validating the fix and was fixed with it: two runs against one tree write the same path, so a stale `__pycache__` entry could replay a previous test body when two bodies shared a length and a mtime second - `PYTHONDONTWRITEBYTECODE=1` now closes that and stops the run leaving bytecode inside the revision under test. Containment (D-017) is unchanged and marginally tighter, because `--confcutdir` strictly reduces the foreign conftest code that gets imported. The durable audit copy of the generated source still lives under `repo_root/.attest/repro/...`, outside the worktree that gets deleted. Reverse: none; the previous arrangement cannot distinguish the two revisions it exists to compare.
- **D-031 the reproduction channel's null rate clears its ceiling at 0 in 296 trials**: extending D-027's measurement to 296 trials produced zero false confirmations, giving a Wilson 95% interval of [0, 0.012812] against the 0.01282 e-validity ceiling D-026 derived for this channel. The interval clears the ceiling, so the V channel is - at this sample size, on this population - consistent with being the valid e-value the error-control story needs it to be, which no other channel can be. Outcome mix across 296 trials: 193 `not_reproduced` (the generated reproduction passed on head, pushing wealth 2.95 -> 1.475), 73 `unfaithful` (failed on both trees, bought nothing), 30 `indeterminate` (pytest collection or infrastructure failures, all safely deferred). Cost $1.1474, total development spend $2.05 of the $10 cap. **Three limits stated plainly.** First, the population is constructed semantics-preserving refactors, not real pull requests, so this measures the gate against a designed null rather than a natural one. Second, the trials ran against the code as it stood BEFORE the D-029 fixes landed; both fixes strictly tighten certification, so the measured rate cannot get worse, but the number is not a measurement of the current binary. Third, 30 of 296 runs deferred on infrastructure rather than deciding, and while deferral is the safe direction it means roughly one run in ten produced no evidence either way. Reverse: superseded by a measurement on real diffs. **Both directions confirmed against the fixed executor on 2026-08-30**: 45 further null trials including rename refactors produced zero false confirmations, so the fixes did not loosen the gate; and a real regression planted in a project shaped exactly like the one D-029(b) used to lose - root `conftest.py`, root `pyproject.toml`, flat package layout - now certifies correctly at `head FAIL 3/3, base PASS 3/3`, lifting wealth 2.95 -> 59.00 to surface, where before the fix it was dismissed as unfaithful and never spoken.
- **D-032 the benchmark refuses to score without authorisation, and never counts what it could not judge**: three honesty defects found by adversarial review are closed. A DEFERRED product run was scored as a true negative, so "I could not evaluate this" inflated specificity and silence precision with cases the tool never judged; deferrals are now abstentions, carried with their reason, excluded from both sides of every accuracy ratio, and reported separately. An inconclusive oracle receipt was charged against the product as a false positive AND a false negative at once; such a case now has no usable ground truth and is excluded with a recorded reason, while its operational facts - latency, silence, duplicates - are still measured, because those claim no correctness. And replay published precision and recall with no manifest-digest-bound validation receipt, which D-019 makes the thing that authorises scoring at all; scoring now defaults to refusal, publishes `metrics_withheld_reason`, and produces figures only when a receipt matching this manifest covers every scored pair. One existing test had encoded the wrong behaviour - it asserted true positives and true negatives on a receiptless run - and was changed rather than kept. Consequence for the shipped corpus: `benchmarks/attest-v1` still has no receipt, so replay against it now reports operational measurements only and says plainly that scoring was not authorised. Why: a benchmark that reports a number it has not earned is worse than one that reports nothing. Reverse: none; the refusal lifts by producing a receipt, which is the intended path.
- **D-033 two more reproduced defects closed: a stale label window could drive alpha to the floor, and real KeyError regressions were being silently blocked**: the D-014 watermark counted every feedback row, but ambiguous legacy `dismiss` labels are excluded from precision, so recording one advanced the watermark without moving the figure and re-opened the tightening gate - four such labels walked alpha 0.1 -> 0.05 -> 0.025 -> 0.0125 -> the 0.01 floor on a precision value that never changed. The watermark now counts only precision-bearing labels and compares with `<=` so rows written by the old code still block. Separately, `classify_failure_signature` read exception names, so an ordinary `KeyError` from a mapping lookup inside the code under test was called a missing symbol; once D-029's fix made head-symbol-absent a hard bar to buying anything, that silently blocked genuine regressions. The rule now discriminates: `NameError`/`ImportError`/`ModuleNotFoundError` are always unresolved names; `KeyError` never is, because CPython does not report an unresolved name that way; `AttributeError` is read from its message, with builtin value types treated as absent because no diff can remove an attribute from a namespace the interpreter owns. Both guards were verified to have teeth by mutation: dropping the instance-attribute case makes a method-rename refactor certify again, and the guard tests fail. Reverse: none; both are defects.
- **D-034 the Task 8 experiments land the decision packet's numbers**: three offline, deterministic (byte-identical reruns at full scale), experiment-only harnesses now back the owner decisions this branch has been accumulating. **Null grids on the real core engine** (20 preregistered seeds, 100k null tasks per alpha): realized wrong-certification stays inside alpha everywhere - pooled 0.24% at alpha 0.05, 1.24% at 0.1, 4.08% at 0.2 - but the external figures the status doc carried (0/3/544 per 80k) did NOT reproduce under this protocol and remain owner-provided, unmerged; and on null-only streams the optimism alarm fired in all 240 runs because theta=1 table rows never leave the Laplace prior, so the external "all alarms were drift" profile does not carry over. **Monitor policies**: a stale-tables canary with the true winner's-curse signature is caught by every policy in 5/5 runs - "the monitor cannot see unsafe runs" does not generalize; it depends on the failure having the optimism signature - but the alarm is also active on a third to half of healthy tasks, so braking is sensitive without being specific (false-brake 1.00 at run granularity), and the defensible harm-reduction arm is quarantine, which on canary streams halves wrong certifications while also cutting spend, paying only in abstention. **Two-ledger V-only speech**: at the factory alphas the two-ledger arm and the shipped gate agree record for record - zero discordant pairs - so V-only certification is a formalization of what the cap arithmetic already enforces, not a change; its value is robustness (loosen alpha to 0.25/0.4 and the factory arm wrong-certifies 18-70% of null candidates while V-only stays pinned at the assumed false-reproduction rate) and scheduling: using S/T wealth as the verification priority queue reaches any fixed recall with 11.5-33% less verification budget than first-come-first-served, the saving largest when the budget is tightest. Everything synthetic, insufficient_labels/recommendation_only; adopting any of it touches gate composition, CI verification ordering, or the S/T role, and stays an owner decision under ground rule 8. Reverse: none; the harness accepts real labeled ledger rows for the day they exist.
- **D-035 ten live repeats of one diff: the betting layer absorbs the sampling variance**: ten independent K=5 reviews of the same preregistered regression diff, fresh working copy and empty ledger each time, real provider. Every run proposed at least one candidate and every candidate anchored the deleted guard (calc.py:3-4, one location cluster, pairwise cluster Jaccard 1.0); every run made the identical decision - drawer, because no verification evidence had been purchased - so run-level outcome stability is 10/10 with zero decisions flipping across repeats. What varied underneath: candidate count (1 vs 2, the model sometimes splitting the two lines into separate findings), vote counts (wealth 2.64/2.95/3.0), and claim prose. Mean latency 6.9s, total cost $0.2841. This is the first direct measurement of the product's core mechanism - K-sample divergence entering, a stable decision leaving - and it is one diff, one model, one night: a distribution, not a proof. The Task 6 stability CLI measures the same thing reproducibly from cassettes; this run is the live sanity check that the number it will compute is not fiction. Reverse: superseded by preregistered Task 6 runs over more cases.
- **D-036 the corpus has its first validation receipt: 9 of 20 pairs scorable, with a structural caveat that must gate any accuracy claim**: the frozen BugsInPy pilot was materialized in full - all 20 pairs, all four projects, three exact interpreter pins (3.8.3/3.8.1/3.6.9) built as x86_64 under Rosetta, per-pair virtualenvs, and an interpreter-level network-deny wrapper that passed the validator's live socket probe in every run. The oracle validated 9 pairs (all black: 3x fixed-PASS + 3x buggy-FAIL, stable signatures), excluded 9 for dependency_or_setup_failure and 2 as flaky, and issued a manifest-bound receipt (manifest 8f9f90f1..., receipt e8cabb89...) that round-trips the fail-closed loader. **The caveat**: all nine validated buggy-FAIL signatures are unittest "has no attribute" errors, because BugsInPy introduces the regression test with the fix and its own harness transplants fixed-commit test files into the buggy tree - which our clean-checkout integrity rule forbids. So the oracle certifies "the fixed tree passes its tests and the buggy tree cannot run them", not "the bug demonstrably manifests"; the bug's existence rests on BugsInPy metadata, not on an independent reproduction. Product evaluation over these pairs is still meaningful - the product generates its own reproductions and never sees the corpus test - but any published accuracy number must carry this caveat, and the owner should decide whether to tighten the validator (treating unittest's no-attribute as a missing-test marker would exclude all nine, leaving zero validated pairs - honest but empty) or to permit declared test-file materialization as BugsInPy's own harness does. Reverse: rerun validation under whichever rule the owner picks; the receipt mechanism itself is agnostic.
- **D-037 first live evaluation on the validated corpus: precision held, recall was zero, and the failure list is the roadmap**: ten case-runs over two receipt-validated black pairs (both roles, three rounds as the harness was corrected). The developer-fix controls were silent in all four runs - zero candidates, zero false positives on real history. The bug-reintroduction replays surfaced nothing in five attempts, every one a safe DEFER, in three distinct modes: (a) on the large real diff the generator repeatedly returned output that failed the reproduction schema, so no test was ever executed - a model-side robustness gap that bigger anchors and real-world context expose and constructed repos never did; (b) the first round ran without the corpus project environment (ATTEST_PROJECT_PYTHON unset), which the orchestration now passes - an evaluation-harness lesson, not a product defect; (c) with the environment fixed, a generated reproduction attempted to spawn a child process - black's own test idiom - and the D-017 containment correctly refused it, exposing a real tension between containment and how mature projects write tests. Reading: on real historical bugs the product currently keeps its precision promise by staying entirely silent; the recall path is blocked by reproduction-generation robustness, not by the gate. That ranks the next engineering work: schema-tolerant repro parsing/retry, and a containment-compatible reproduction idiom for projects whose tests shell out. Cost $1.06, all safe-direction outcomes. Reverse: superseded by full Task 7 runs once the generation gaps close.
- **D-037 ERRATUM (D-041, 2026-08-30)**: the phrases “precision held” and “recall was zero”
  above are withdrawn. With no surfaced finding and all replay attempts DEFERred, finding
  precision and repository-scored recall were not estimated. The defensible result is
  surfaced delivery 0/5 with the recorded abstention modes. The observed upstream blockers
  do not prove that the gate would cease to block after they are fixed.
- **D-005 Corum ports deferred**: recon of Corum calibration.py/dependence.py found the hierarchical-shrinkage prior, pair-calibration tables with min-count gates, and correlation shrinkage + PSD projection all worth porting — but only at the >=500-label global recalibration milestone, which MVP explicitly excludes. Nothing ported now (no unverified code). Reverse: port when recalibration work starts.

## Evolution decisions

| ID | Status | Scope | Primary normative owner |
|---|---|---|---|
| D-038 | accepted | scheduler/certifier authority split | target architecture §3/§6/§8 |
| D-039 | accepted | receipt-only task/policy/publication contract | target architecture §4/§8 |
| D-040 | accepted, shadow first | Core and multi-model scheduling | target architecture §6; scheduler gates |
| D-041 | accepted | measurement units, DEFER, semantic truth | acceptance gates §2–§4 |
| D-042 | accepted target | secretless OS execution boundary | target architecture §7; security gates |
| D-043 | accepted abstention | new-code evidence class | target architecture §8.3 |
| D-044 | accepted | documentation and agent authority | `AGENTS.md`, `docs/README.md` |

### D-038 — Separate scheduling from certification

- **Date/status/scope:** 2026-08-30 · accepted target architecture · product-wide.
- **Decision:** candidate search and evidence scheduling may use adaptive, correlated,
  heuristic signals, but only an independent deterministic Certification Kernel may create
  a `CertifiedFinding`. Scheduler/S/T/Core/wealth are absent from certification authority.
- **Why:** D-026 established that current S/T wealth is not an e-process; current safety is
  carried by factory reachability and differential execution. Mixing ranking and truth
  authority makes configuration and calibration errors publication errors.
- **Consequences:** add `attest.certification`; presentation consumes certified types;
  scheduler failure can only fall back or abstain. Existing gate experiments remain
  historical/mechanism tests.
- **Supersedes/amends:** supersedes old agent/README language calling product wealth the
  final statistical authority; preserves D-008/D-026 as history of current factory math.
- **Reversal:** only an owner-approved replacement with a formal conditional-validity
  argument, adversarial implementation tests, and the full empirical gates; never by tuning
  a constant.
- **Trace:** `INV-CERT-001`, `INV-CERT-002`, `INV-SCHED-001`; `G-CERT-001`,
  `G-SCHED-001`, `G-SCHED-002`; work orders C-01/C-02/S-01 through S-04.

### D-039 — Receipt-only, task-bound publication is the target safety contract

- **Date/status/scope:** 2026-08-30 · accepted target contract · CI, CLI, GitHub,
  certification and publication policy.
- **Decision:** every author-visible finding requires an accepted receipt bound to the
  current repository, merge-base, head, diff, candidate/claim/hunk, exact test/execution,
  environment/executor, authenticated provenance, and base-owned policy. Receipt acceptance
  makes a finding eligible; PR-level family/dedup/hard-cap policy may still suppress it.
  Manual reproduction is `self_reported`, not automated V. Head configuration cannot relax
  safety.
- **Why:** current alpha can allow S/T direct surface; CI skips already-terminal candidates;
  manual `--reproduced` can buy legacy V; current top-three is layout-only; per-candidate
  alpha does not control PR-any-error exposure.
- **Consequences:** the alpha=.15 direct-surface test must be reversed as a security
  regression; merge-base/base policy, manual migration, receipt v2, and family policy are
  P0/P1 work. Compatibility never restores bypass.
- **Reversal:** only by replacing the receipt/family contract with an owner-approved policy
  that passes the same or stronger safety gates.
- **Trace:** `INV-TASK-001`, `INV-POLICY-001`, `INV-EVIDENCE-001`, `INV-RECEIPT-001`,
  `INV-FAMILY-001`, `INV-PRESENT-001`; `G-CERT-001` through `G-CERT-004`,
  `G-SEM-001` through `G-SEM-003`; work orders C-01 through C-05 and V-01 through V-03.

### D-040 — Core and multiple models are evidence schedulers, not voters

- **Date/status/scope:** 2026-08-30 · accepted direction, shadow first · scheduler/Core.
- **Decision:** evolve Core through a new arbitrary-action scheduler interface. Models/tools
  take heterogeneous roles and are treated as correlated actions. The objective is marginal
  probability of a decisive trusted receipt per cost/time under a PR-local budget. Core
  starts in shadow, cannot affect certification, and advances only through a real within-PR
  comparison with propensity/version logging and repo-clustered inference.
- **Why:** `attest.core.Engine` currently assumes two/three binary judges, immediate truth,
  fixed prior, and stationary plug-in cells; it is not in the review path. Agreement does
  not establish independent evidence. D-034 pooled synthetic candidates across tasks and
  assumed V outcomes/costs, while real CI can only reorder candidates inside one PR.
- **Consequences:** historical 11.5–33% savings remains simulation-only. First ship typed
  events and deterministic FCFS/S/T/feasibility shadow baselines, then a learned policy with
  cross-fitting, propensities, delayed labels, and version/drift handling.
- **Reversal:** Core may remain research-only or deterministic priority may win. Core may
  control order only after `G-SCHED-002`; it may never certify under this decision.
- **Trace:** `INV-SCHED-001`, `INV-SCHED-002`, `INV-ORDER-001`; `G-SCHED-001`, `G-SCHED-002`,
  `G-SCHED-003`, `G-MODEL-001`; work orders S-01 through S-04 and E-05.

### D-041 — Author harm and semantic opportunity define evaluation

- **Date/status/scope:** 2026-08-30 · accepted measurement contract · benchmark and claims.
- **Decision:** every author-visible finding is scored even in mixed surface+DEFER tasks;
  DEFER is abstention; no surfaces means precision undefined; eligible positives that
  abstain are deployment misses; repeats are operational and do not enlarge semantic n;
  location overlap is not semantic truth; primary inference clusters by PR/repository and
  follows a frozen sample/stop rule. Receipts must carry trial-level evidence and authority.
- **Why:** current live calibration can drop a whole case when any abstain reason exists,
  hiding published findings. Historical 0/5 all-DEFER, 10 repeats of one diff, 9 pairs from
  one project, and location-only matching cannot support broad precision/recall/stability.
- **Consequences:** M-01 through M-03 precede new quality claims. D-037 is interpreted as
  surfaced delivery 0 in the reported attempts with explicit blockers, not “precision held
  at zero recall.” D-035 is one-case operational consistency, not independent general
  stability.
- **Reversal:** only through a preregistered measurement amendment applied prospectively;
  never after observing outcomes.
- **Trace:** `INV-MEASURE-001`, `INV-TRUTH-001`, `INV-COST-001`; `G-MEASURE-001` through
  `G-MEASURE-004`,
  `G-NULL-001`, `G-CORPUS-001`, `G-STAB-001`, `G-SHADOW-001`; work orders M-01 through
  M-03 and E-01 through E-04.

### D-042 — Untrusted execution requires a secretless OS boundary

- **Date/status/scope:** 2026-08-30 · accepted security target · Action/executor.
- **Decision:** split the privileged controller from a credential-free content-addressed
  executor. Production execution requires default-deny kernel/OS network and filesystem
  isolation, bounded resources/processes, read-only source, authenticated results, and
  versioned profiles. Same-repository head is untrusted. Legitimate subprocess support is a
  digest/argv/profile allowlist inside the same boundary.
- **Why:** environment filtering, Python audit/socket hooks, and same-user worktrees cannot
  prevent native access to host files, parent secrets, checkout credentials, or network.
  D-017 is useful best-effort containment, not a production trust boundary.
- **Consequences:** current runner is labeled development/best-effort; missing platform
  capabilities DEFER. Backend selection remains an owner decision; security tests use
  canary secrets only.
- **Reversal:** another backend may replace the implementation if it passes equal/stronger
  `G-SEC-001` through `G-SEC-003`; production may not fall back to language-level guards.
- **Trace:** `INV-SEC-001`, `INV-RECEIPT-001`; `G-SEC-001`, `G-SEC-002`,
  `G-SEC-003`; work orders X-01 through X-03.

### D-043 — New-code findings remain a separate unpriced class

- **Date/status/scope:** 2026-08-30 · accepted abstention · evidence classes.
- **Decision:** do not “turn on” `new_code_candidate` by choosing one LR constant. Define a
  class-specific counterfactual/certificate (for example specification oracle, mutation or
  patch ablation) and calibrate it on hidden semantic data before publication.
- **Why:** base symbol absence makes the regression head-fail/base-pass contract
  inapplicable; one planted live example and a discriminator guard do not estimate semantic
  false-confirmation or PR harm.
- **Consequences:** ledger/ranking may retain new-code candidates; they remain abstentions
  in public paths. The roadmap may improve their discovery and collect shadow labels without
  pricing them.
- **Supersedes/amends:** amends D-020/D-022 language suggesting the remaining owner choice
  was merely a new LR after 500 labels.
- **Reversal:** owner approves a concrete evidence contract after its own semantic/null/
  prospective gates.
- **Trace:** `INV-CERT-001`, `INV-EVIDENCE-001`; `G-CERT-001`, `G-CORPUS-001`,
  `G-SHADOW-001`, `G-NEWCODE-001`; N-01 prepares the owner decision without pricing, and a
  separately scoped post-selection N-series work order (ID assigned only after the owner
  selects a contract) is required.

### D-044 — Normative construction scaffold replaces completed plans as agent authority

- **Date/status/scope:** 2026-08-30 · accepted repository process · documentation/agents.
- **Decision:** `AGENTS.md` owns durable work rules; target architecture owns invariants;
  acceptance gates own thresholds; roadmap owns status/dependencies; work orders own method;
  decisions own narrow trade-offs; dated reports and 2026-08-29 plans are historical
  evidence. One fact has one owner and other documents link to it.
- **Why:** the previous AGENTS file still named an old branch, D-014, 390 tests, missing
  receipt and unfinished Tasks 4–8 after all had changed, making it unsafe as a continuation
  guide.
- **Consequences:** old plans receive archive banners rather than rewritten checkboxes;
  dynamic head/test/spend facts do not live in AGENTS; a decision that changes a normative
  contract updates that document atomically.
- **Reversal:** document layout may split as it grows, but domain ownership, stable IDs, and
  no-silent-conflict rule remain unless an equally checkable replacement is approved.
- **Trace:** `G-DOC-001`; F-00 and every later work-order handoff.

### D-045 — Paid-call evidence is process-crash durable and reconciled bidirectionally

- **Date/status/scope:** 2026-08-30 · accepted measurement contract · M-03 paid studies.
- **Decision:** bind every paid subcall to one trial/call ID, one authoritative spend row,
  and one content-addressed artifact. Persist call transitions with same-directory atomic
  replacement; treat dispatched-without-response as `ambiguous_cost`; validate both from
  checkpoint to evidence and from evidence back to checkpoint. Enclosing observations and
  reports bind the verified joins rather than accepting a self-consistent empty directory.
- **Why:** case-level cost alone cannot prove which paid dispatch produced which artifact,
  and process interruption between dispatch, response, settlement, and report publication
  otherwise permits duplicate calls or erased cost.
- **Consequences:** missing, duplicate, mismatched, orphaned, or wholly absent call evidence
  withholds claims. The complete build/runtime/Gate closure is exactly pinned and accepted
  under both Python 3.11 and 3.12 before a measurement implementation is marked complete.
- **Boundary:** durability covers controller/process crashes on one local filesystem. It
  does not claim distributed transactions or power-loss persistence, and it never permits
  automatic replay of an uncertain dispatch.
- **Reversal:** retain all paid-call artifacts and use the last compatible reader; mark
  unresolved calls ambiguous and withhold metrics. A lock change must pass both declared
  interpreter Gates before replacing the accepted lock.
- **Trace:** `INV-COST-001`, `G-CODE-001`, `G-MEASURE-003`; work order M-03.

### D-046 — The composite Action consumes the audited primary environment

- **Date/status/scope:** 2026-08-30 · accepted measurement environment · M-03 Action
  bootstrap.
- **Decision:** the composite Action selects CPython 3.12.8, installs the complete exact
  `requirements-toolchain.lock`, installs Attest with dependency resolution and build
  isolation disabled, and runs `pip check` before execution.
- **Why:** M-03 explicitly owns the project lock and CI setup, while `G-CODE-001` requires
  the locked supported toolchain. Selecting a floating `uv` runtime and resolving ranged
  project metadata made the Action contradict the environment that the acceptance claim
  audited. Narrowing the claim would leave a shipped M-03 execution path outside the
  reproducibility contract.
- **Consequences:** Action bootstrap may download exact locked distributions on a fresh
  runner, but cannot select newer transitive versions. The minimum Python 3.11 environment
  remains a clean-install Gate; the Action itself uses the declared primary Python.
- **Reversal:** changing the primary interpreter or lock requires a reviewed lock update
  and fresh minimum/primary full Gates bound to the replacement implementation SHA.
- **Trace:** `G-CODE-001`; work order M-03; `action.yml`; `[tool.attest.toolchain]`.

### D-047 — Paid-call roles are immutable accounting authority

- **Date/status/scope:** 2026-08-30 · accepted measurement contract · M-03 paid studies.
- **Decision:** every paid dispatch is explicitly scoped as `product` or
  `benchmark_oracle` before the call. The role is bound through the request digest,
  predeclaration, checkpoint, artifact, spend row, reconciliation record, and report
  digest. Product, oracle, and total spend are derived only from these rows; the two role
  totals never overlap, and call order or separately populated result/report fields have
  no classification authority.
- **Why:** call identity and cost integrity alone still allowed oracle calls to be counted
  as product cost, settled cost to be erased after an evaluation exception, and a report
  to accept totals inconsistent with its paid-call rows.
- **Consequences:** paid-call checkpoint schema v5, artifact/cost schema v4, live schema
  v4, stability predeclaration/report schema v4 with observation schema v3, comparison
  checkpoint schema v5, and comparison reconciliation schema v2 and comparison report
  schema v3 fail explicitly on older state. Stability, live, and comparison use one
  role-aware reconciliation reducer; the local Ruff arm must carry zero provider calls,
  model tokens, and paid spend while retaining its separately measured tool time;
  legitimate zero-call trials carry an explicit empty row set, while missing evidence
  fails closed.
- **Reversal:** retain old artifacts with their compatible reader and start a new declared
  study; never invent roles for old state or migrate it into current scoring authority.
- **Trace:** `INV-COST-001`, `INV-VERSION-001`, `G-MEASURE-003`; work order M-03;
  `src/attest/benchmark/checkpoints.py` and its stability/live/comparison consumers.

#### 2026-08-31 amendment — integrated receipt, input, and execution authority

- **Status/scope:** active clarification for the M-02/M-03 integration. This amendment
  supersedes only D-047's current-version statements; the 2026-08-30 text and its accepted
  `bce13f0` observation remain immutable history.
- **Version contract:** the current comparison checkpoint is schema v6, the comparison
  report is schema v4, the calibration report is schema v4, and the project evaluation
  binding is schema v2. The live predeclaration and per-case checkpoint are schema v5;
  the stability predeclaration is schema v5 while the unchanged stability report remains
  schema v4 and its observation remains schema v3. The v6 comparison checkpoint combines
  receipt binding with exact manifest/truth/input-policy binding in the single migration
  from the externally accepted v5 format. Existing comparison checkpoint v5, live
  predeclaration/checkpoint v4, stability predeclaration v4, and comparison/calibration
  report v3 artifacts are retained only as history; they are not upgraded, replayed, or
  reinterpreted as current authority. Unknown versions fail closed. Paid-call checkpoint
  v5, artifact/cost v4, stability report v4, observation v3, and comparison reconciliation
  v2 are unchanged by this amendment.
- **Symmetric-authority boundary:** Phase 0 has no supported current-V2 production
  execution workflow. Public corpus validation executes project code only to create
  unsigned, content-addressed evidence and never accepts a signing key or emits current
  scoring authority. `verify-validation` is the sole production CLI path for V2 and is a
  pure offline verifier that never loads a checkout, runner, evaluator, or provider.
  Execution APIs and the `replay`, `compare`, and `live-local` commands accept only no
  receipt or an exact historical V1 receipt for exclusion inspection; V1 always remains
  `historical_integrity_only` and every execution report withholds accuracy. Raw V2 or a
  current `ValidationVerification` fails before runtime, state, output, checkpoint,
  provider, or evaluator effects. HMAC-backed current execution remains blocked pending
  X-01/V-03 or an approved public-key protocol that keeps signing authority unavailable to
  untrusted code.
- **Synthetic/reducer boundary:** a prebuilt evaluation binding is a trusted synthetic,
  non-authorizing seam. Pure report reducers may validate already-existing trusted
  evidence, but neither an opaque receipt digest nor an in-process V2 verifier capability
  authorizes execution. This amendment makes no comparison-accuracy quality claim: the
  inherited ability to coordinate-rewrite caller-supplied `ArmRun` outcomes while retaining
  paid-call evidence is owned by M-01/G-MEASURE-001 and must be closed with the versioned
  authoritative outcome artifact there, not with a partial Phase 0 adapter.
- **Compatibility/reversal:** preserve the original M-02 BLOCKED report, M-03 acceptance,
  INVALIDATED bundles, v1 receipt/results/protocol bytes, and every old state blob. Roll
  back by withholding current metrics and reading historical artifacts only; never coerce
  v1/v3/v4/v5 material into current scoring authority.
- **Trace:** `INV-SEC-001`, `INV-TRUTH-001`, `INV-VERSION-001`, `G-CODE-002`,
  `G-MEASURE-001`, `G-MEASURE-002`, `G-MEASURE-003`; work orders M-01, M-02, M-03,
  X-01, and V-03.

#### 2026-08-31 amendment — M-01 authoritative mixed outcomes

- **Status/scope:** active version/accounting clarification after M-01 Task 4; supersedes
  only D-047's earlier current-version and unresolved-M-01 statements.
- **Current versions:** comparison checkpoint v7; comparison report v4; calibration report
  v5; project evaluation binding v2; live predeclaration/case checkpoint v5; stability
  predeclaration/report/observation v5; paid-call checkpoint v5; paid-call artifact/cost v4;
  comparison reconciliation v2. `MeasurementRecord` remains v2 with
  `mixed_outcome_v3` reducer semantics; outcome predeclaration/seal/final-receipt schemas
  begin at v1. Unknown or older current-authority state fails closed and remains historical.
- **Authority closure:** product outcomes are persisted as exact adjudicated measurements,
  joined by finding ID, sealed into comparison/live/stability evidence, and included in
  final receipt/report digests. Caller-owned `ArmRun` rewrites and task-level DEFER can no
  longer erase already-published findings or rewrite product accuracy.
- **Evidence/reversal:** implementation `c680641` closes the code-level authority gap;
  probe hardening `b6caad7` plus the SHA-bound
  [`Task 4 acceptance`](docs/acceptance/2026-08-31-m01-mixed-outcome.md) closes the
  versioned before/after and 20-repeat offline contract. Final `G-MEASURE-001` acceptance
  remains pending Task 5 dual-Python full Gates. Retain old artifacts with compatible
  readers; never coerce them into current scoring authority.
- **Bounded closeout:** implementation `dd37a8e` closes reproduced strict-reader and
  delivery/decision authority gaps. Independent final review then reproduced one P1 in
  benchmark publication accounting; `5efe3d1` requires `action=surface` and reuses that
  authority in execution measurement. The same review pass confirmed the resolution with
  P0=0/P1=0. Fresh exact-SHA Python 3.11/3.12 environments each invoked full pytest once,
  but the host volume returned `ENOSPC` at 97% / about 99% (RC 120) before final counts or
  coverage existed. Static, provenance, clean-tree, and frozen-v1 checks passed; no retry
  occurred. D-049 therefore closes this task as `FAILED ENVIRONMENT`, not as a Gate pass;
  M-01 and `G-MEASURE-001` remain open. Raw evidence is under
  `docs/acceptance/evidence/2026-08-31-m01-task5-5efe3d1/`.
- **Trace:** `INV-MEASURE-001`, `INV-VERSION-001`; M-01 Tasks 3–4; Task 5 pending.

#### 2026-08-31 amendment — M-01 Task 5 recovery acceptance

- **Status/scope:** accepted supersession of only the current “Task 5 pending / M-01 open”
  conclusion above. The original `ENOSPC` observation and raw bundle remain immutable
  failed-environment history; neither invocation is relabelled as a pass.
- **Evidence:** final implementation `5efe3d1` (tree `a2909b5`) retains Task 4's
  versioned before/after and 20-process mixed-outcome result and closes independent review
  at P0=0/P1=0. Fresh detached exact-SHA Python 3.11.5 and 3.12.8 recovery environments
  each invoked full pytest once and passed 1543/1543 tests, total coverage 12373/13728
  (90.129662%), core coverage 428/429 (99.766900%), Ruff, Mypy, `pip check`, provenance,
  clean/diff, and frozen-v1 hashes. The superseding
  [`acceptance report`](docs/acceptance/2026-08-31-m01-task5-recovery.md) binds the raw
  dual-Python manifests; root manifest SHA-256 is
  `d98c510ba5ba8860a27bed57e3d08d86a90b2c4cb758ec1b252ae1ae2956e89b`.
- **Consequences:** M-01, `G-MEASURE-001`, and `G-CODE-001` pass. With M-02 and M-03
  already accepted, Phase 0 is complete and C-01 is unblocked but not started. This creates
  no natural/public-data quality claim and does not authorize C-02, Core, a release, or a
  factory-statistics/pricing change.
- **Reversal:** retain both recovery and failed-environment bundles. A later failure starts
  a new versioned observation; never rewrite either historical result.
- **Trace:** `INV-MEASURE-001`, `INV-VERSION-001`; `G-MEASURE-001`, `G-CODE-001`;
  M-01 Tasks 3–5.

### D-048 — Alpha auto-tighten constants are protected factory authority

- **Date/status/scope:** 2026-08-31 · accepted guard clarification · review ledger and
  factory statistical policy. Renumbered from main's colliding D-038 when merged after
  evolution decisions D-038 through D-047.
- **Decision:** `PRECISION_TARGET = 0.90`, `PRECISION_WINDOW = 50`, and
  `ALPHA_FLOOR = 0.01` are factory statistical constants. Changing any of them requires
  the same owner stop-and-ask as changing alpha, LR schedules, or channel caps.
- **Why:** these values let observed feedback move the gate itself. An unnamed constant
  cannot reliably receive the red-line protection already required for factory statistics.
- **Consequences:** `auto_tighten_alpha = false` remains the supported opt-out and changes
  none of the constants. Decision IDs are allocated by scanning the complete log; merge
  collisions are renumbered rather than overwriting accepted history.
- **Reversal:** owner call with preregistered calibration and downstream Gate evidence.
- **Trace:** `src/attest/review/ledger.py`; `AGENTS.md` §§14/16; factory-statistics
  stop-and-ask boundary.

### D-049 — Self-review and single-task effort are bounded

- **Date/status/scope:** 2026-08-31 · owner-merged process rule · all work orders.
  Renumbered from `origin/main`'s colliding D-039 because the evolution log already owns
  D-039.
- **Decision:** run one independent review pass per work-order branch. Fix only defects
  reproduced in that pass; unreproduced concerns and every later-round finding go to
  `docs/backlog.md`. End the task in a handoff report when any one condition holds: three
  consecutive commits to the same file have more additions than deletions; the task reaches
  eight commits or three hours; or its stated measurement is in hand.
- **Why:** an unbounded repair loop had produced more guards and code without a terminating
  product measurement. The same evidence threshold used for product findings now governs
  development findings.
- **Consequences:** a stop signal does not convert a missing Gate into PASS. It freezes the
  honest state, names the missing Gate, and returns prioritization to the owner or next
  explicitly scoped task. Plans and checklist exhaustion cannot override the bound.
- **Reversal:** owner call, supported by observed tasks that need a different bound.
- **Trace:** `AGENTS.md` §11; `docs/backlog.md`; all roadmap work orders.

### D-050 — Coverage authority follows the production package boundary

- **Date/status/scope:** 2026-09-01 · owner-approved Gate amendment · `G-CODE-001`.
- **Decision:** retain a hard 90% combined coverage threshold for `attest.review`,
  `attest.cli`, and `attest.github`. Report `attest.benchmark` and `attest.core` coverage
  separately without thresholds. Freeze both against feature growth; `attest.core` may not
  gain code without explicit owner approval. Run one supported Python at ordinary
  work-order/wave Gates and both locked Python versions at the final integration Gate.
- **Why:** benchmark source plus its tests are the majority of repository measurement
  apparatus and are not production authority. Requiring every product change to maintain
  line coverage for frozen benchmark and research-only Core conflated tool maintenance with
  product protection. Product coverage remains unchanged at 90%; known-input correctness
  and the feature freeze protect the measurement and research packages.
- **Evidence:** the pre-amendment Gate at `53f4641` passed 1543 tests with 90.13% total and
  99.77% Core coverage in 736.62 wall-clock seconds. The SHA-bound post-amendment timing and
  all three package reports are recorded in `docs/overnight-handoff.md`.
- **Consequences:** the default coverage report is the production Gate; benchmark and Core
  reports use `--fail-under=0`. This changes Gate scope, not the production threshold, test
  expectations, security standard, or any product behavior.
- **Reversal:** owner approval with a replacement package boundary and measured Gate-cost
  evidence; never by lowering the production threshold after a failure.
- **Trace:** `G-CODE-001`; `AGENTS.md` §13; `pyproject.toml` coverage configuration.

### D-051 — Measured proposal truncation gets bounded output headroom

- **Date/status/scope:** 2026-09-01 · accepted owner-authorized default adjustment ·
  proposal sampling only.
- **Decision:** increase `PROPOSER_MAX_OUTPUT_TOKENS` from 1,600 to 2,400. Keep the
  same value for both the provider hard cap and every up-front budget reservation;
  do not change the default review budget, sample count, gate, channel prices, or
  factory statistical constants.
- **Why/evidence:** the first stop-reason-instrumented operational run at `50055e2`
  observed 4/20 proposal calls ending at `max_tokens`, all four on one case; a valid
  response for that case consumed 1,539 output tokens. Adaptive reasoning consumes
  the same allowance even when its text is omitted. A 50% increase is the smallest
  round bound that provides material measured headroom.
- **Consequences:** the observed case's five-call preflight remains below its $0.25
  budget (about $0.135 at the new bound). The conservative default-budget diff-size
  boundary moves from about 50k to about 38k characters; larger inputs still DEFER
  before dispatch. This is a bounded generation default, not a lowered evidence bar.
- **Reversal:** replace only with another stop-reason-bound measurement; never recover
  budget by under-reserving the enforced provider cap.
- **Trace:** Wave 3 run `wave3-observe2-20260901`; `src/attest/review/proposer.py`;
  `DEVSPEND.md`.

### D-052 — Reproduction schema recovery stays bounded

- **Date/status/scope:** 2026-09-01 · accepted implementation constraint · V-channel
  reproduction generation.
- **Decision:** tolerate only an otherwise complete JSON response wrapped in one Markdown
  JSON fence, and retry a schema-invalid generation at most once. Reserve both possible
  calls before the first dispatch, settle only calls made, and cancel every unused
  reservation.
- **Why:** Wave 3 produced three schema-valid reproduction bodies out of four candidates;
  the fourth stopped at `max_tokens` with `{}`. One bounded recovery attempt addresses that
  observed D-037(a) failure without weakening the schema or execution boundary. D-037(c) is
  a separate runner-policy question and remains explicitly out of scope.
- **Consequences:** there is no unbounded paid retry and no under-reserved dispatch. Network,
  process, thread, capability, and secret isolation remain unchanged. Arbitrary prose around
  JSON is still rejected, and a second schema failure remains DEFER. No generation prompt or
  runner process/resource policy change is retained for D-037(c).
- **Reversal:** remove the retry only with measured V-channel evidence; never reverse by
  permitting process escape or accepting malformed schema.
- **Trace:** D-017; D-037; `src/attest/review/executor.py`; Wave 4.

### D-053 — Alpha relaxation remains an owner decision

- **Date/status/scope:** 2026-09-01 · pending owner decision · feedback policy only.
- **Question:** should any future design add a bounded alpha-relaxation path to complement
  the existing one-way `maybe_tighten_alpha` ratchet?
- **Current rule:** no relaxation path is implemented or authorized. Work on recall must
  add sparse evidence independent of model opinion; it must not uniformly lower the
  publication threshold or alter protected factory constants.
- **Why pending:** loosening alpha changes the error budget for every candidate, unlike a
  sparse signal that applies only when independently observed evidence exists. The current
  overnight measurements do not estimate the resulting precision/harm tradeoff.
- **Trace:** D-038; D-048; `src/attest/review/ledger.py`; owner overnight constraints.

### D-054 — Repair-history evidence is recorded unpriced

- **Date/status/scope:** 2026-09-01 · accepted shadow instrumentation · review candidate
  history and offline counterfactual measurement only.
- **Decision:** define the first F slice as true only when `git blame` maps the current
  anchor line to a commit within 50 commits of `HEAD` whose full commit message contains
  the word `revert` or `hotfix`. Persist that observation as
  `attest.history-signal.v1` with `priced=false`; it must not create a purchase, enter
  product wealth, write a surfaced ledger row, or affect publication. Call-graph
  reachability and test-blind-spot slices remain backlog items.
- **Counterfactual evidence:** the SHA-bound Wave 5 probe covered all nine historical-V1
  receipt pairs in both historical-bug and developer-fix-control roles (18 cases). Its one
  paid observation produced 26 candidates and F triggered for 0/26. Pure offline replay at
  hypothetical multipliers 1.25, 1.5, 2, and 3 produced no threshold crossings in either
  role; therefore no control candidate was falsely triggered. Actual spend was $1.576220
  against a $2.70 up-front bound.
- **Limits:** the receipt proves historical integrity only. Accuracy, precision, recall,
  and silence precision remain not estimated; the run is not evidence that the signal can
  improve recall. The zero trigger rate is a measurement of this exact sparse definition
  and sample, not authority to broaden or price it.
- **Reversal:** remove the shadow row without migrating wealth or publication state. Any
  change to the slice, lookback, or pricing requires a new owner-approved preregistration
  and control measurement.
- **Trace:** D-022; `src/attest/review/history.py`;
  `scripts/history_counterfactual.py`;
  `docs/acceptance/evidence/2026-09-01-wave5-history-counterfactual/result.json`.

### D-055 — C-01 owns a pure versioned regression-receipt domain

- **Date/status/scope:** 2026-09-01 · accepted C-01 boundary · pure certification types
  and validation only.
- **Decision:** establish task schema `attest.certification-task.v1`, base-policy schema
  `attest.certification-policy.v1`, and strict regression receipt schema
  `attest.certification-receipt.v2`. The pure validator compares current task, repository,
  revisions, diff, candidate, normalized claim, test node/digest, base policy,
  environment, interpreter, executor, exact run evidence, result/evidence class, and
  provenance. Ordinary invalid evidence returns exhaustive typed rejection codes; unknown
  versions/classes fail closed. Only the validator can construct `AcceptedReceipt`, and
  `CertifiedFinding` requires that accepted value.
- **Authority boundary:** the package imports no review, benchmark, Core, provider,
  subprocess, ledger, CLI, or GitHub code. It performs no JSON/file/network/process work,
  has no product caller, and contains no wealth/ranking input. The C-05 selection seam is
  a Protocol with no implementation. C-02, V-01, presentation, execution authority, PR
  family policy, and every factory statistic remain unchanged and unstarted.
- **Evidence:** implementation `e955f29`; 59 focused tests; executable certification logic
  at 100% informational line coverage (the four uncovered statements are the deliberately
  unimplemented selection Protocol); field-by-field mutation guards; adjacent gate/executor
  regressions; Wave 6 `G-CODE-001` at 1615 passed with product coverage 92.39%; one bounded
  self-review finished P0=0/P1=0.
- **Reversal:** leave the types readable but reject v2 receipts and return typed DEFER. Never
  fall back to raw wealth, legacy two-field validation, or a presentation-side constructor.
- **Trace:** `INV-CERT-001`, `INV-CERT-002`, `INV-VERSION-001`; C-01; C-02 not started;
  `G-CERT-001`, `G-CODE-001`, `G-CODE-002`.

### D-056 — Reproduction generation has independent bounded output headroom

- **Date/status/scope:** 2026-09-01 · accepted owner-authorized default adjustment ·
  V-channel reproduction generation only.
- **Decision:** rename the reproduction cap to `REPRO_MAX_OUTPUT_TOKENS` and increase it
  from 2,000 to 3,000. The provider hard cap and both bounded-retry budget reservations use
  that same reproduction-only value. The proposal cap remains independently fixed at 2,400.
- **Why/evidence:** the retained Wave 4 artifacts record 3/7 reproduction calls ending at
  `max_tokens` (42.9%), while writing complete executable test files. A 50% increase is the
  smallest round adjustment consistent with D-051's measured-headroom rule and leaves the
  reproduction allowance above the proposal allowance. This task made no paid evaluation;
  the post-change truncation rate is therefore not measured.
- **Consequences:** retry count, schema strictness, execution containment, gate, prices,
  factory statistics, and generator instructions do not change. Up-front budget checks
  remain conservative because they reserve the enforced 3,000-token cap twice.
- **Reversal:** replace only after a stop-reason-bound reproduction measurement; never
  recover budget by under-reserving the enforced provider cap.
- **Trace:** D-018; D-051; D-052; `src/attest/review/executor.py`;
  `docs/overnight-handoff.md`.

### D-057 — D-037(c) was runner-bootstrap attribution, not Black shelling evidence

- **Date/status/scope:** 2026-09-01 · evidence correction/owner decision required ·
  D-037(c), local-development process audit, and the next paid V-funnel replay.
- **Correction:** withdraw D-037's claim that the observed child-process DEFER came from
  “black's own test idiom” or shell-out-style generated tests. All four retained generated
  bodies were in-process. The old case artifacts individually bound the process reason to
  only two candidates. Exact zero-paid replays of those two (`01dd26db09`, direct
  `black.format_str`; `ffe9efc79f`, Click `CliRunner`) recorded the same first event:
  `subprocess.Popen`, target `uname`, from pytest importing `py -> uuid -> platform.uname`
  under the corpus Python 3.8 environment. The first DEFER stopped repeats at head 1/3 and
  prevented every base run.
- **Consequences:** the current process marker is interpreter-scoped, not attributable to
  reviewed code. This is still a real abstention/runner-compatibility defect, but it is not
  evidence that the two tested Black paths attempted a child process. No allowlist,
  guard-activation timing change, containment relaxation, or paid rerun is authorized here.
  Another paid V-funnel replay waits for owner direction on the runner/guard attribution
  boundary; independent C-02 or V-01 work remains unblocked.
- **Evidence:** `5a684fb` retains bounded event/target/stack diagnostics;
  `e0f2db0` is the final gated implementation/test SHA; the exact stacks and per-candidate
  outputs are in `docs/overnight-handoff.md`.
- **Reversal:** n/a — this corrects attribution. A future runner policy requires its own
  owner-approved decision and must preserve D-017/D-042 containment plus `G-SEC-002` and
  `G-SEC-003`; X-02/X-03 remain the owning work orders.
- **Trace:** D-017; D-037; D-041; D-042; D-049; `G-DOC-001`;
  `src/attest/review/executor.py`; `docs/roadmap.md`; `docs/backlog.md`.

### D-058 — the RED-test discipline is scoped to behavior changes, and ceremony tests are forbidden

- **Date/status/scope:** 2026-09-01 · owner-directed process amendment ·
  `docs/implementation/agent-work-orders.md` §1 and §3.1, the archived plans under
  `docs/superpowers/plans/`, and the removed `.superpowers/sdd/` leftovers.
- **Decision:** a named RED test is required only for orders that change behavior.
  Diagnostic, observational and reporting orders have none — their deliverable is the number
  or the finding — and §3.1 does not apply to them. Adjacent tests and the repository gates
  run once at the end of an order, not after every small change. §3.1 now forbids three
  kinds of test outright: one asserting an object can be constructed or a call does not
  raise, one written to move a coverage number, and one whose only failure mode is a typo
  the type checker already catches. A coverage number that falls because an order
  legitimately needed no test is reported, never papered over with a filler test.
- **Why:** 1615 tests at 92% coverage, about twelve minutes per gate, did not catch that the
  process marker rejected every candidate in the corpus environment — D-057 traced the first
  event to `uname -p`, spawned by `platform.uname()` during pytest's own bootstrap, before
  any reviewed code ran. No amount of unit coverage could have caught that; one end-to-end
  assertion would have. §3.1 therefore names the end-to-end shape as the highest-value test
  in this repository — given a real defect and a correct reproduction, the verification path
  produces a certified receipt — and asks for one of those over ten plumbing tests.
- **Consequences:** the archived plans still carried a live "REQUIRED SUB-SKILL … implement
  this plan task-by-task" line contradicting their own README; it is now a historical note.
  `.superpowers/sdd/m01-overnight-plan/` reports are deleted as spent workflow scratch. No
  gate threshold, factory statistical constant, containment behavior, or security invariant
  changes here; this amends how orders are worked, not what the product guarantees.
- **Evidence:** `docs/implementation/agent-work-orders.md` §1 steps 5 and 7, §3.1 "Scope and
  cost"; both files under `docs/superpowers/plans/`; D-057 for the traced root cause.
- **Reversal:** owner call — restore the per-order RED requirement if a defect is traced to
  an order that skipped one under this scope.
- **Trace:** D-039; D-057; `docs/implementation/agent-work-orders.md`;
  `docs/superpowers/plans/README.md`.

### D-059 — the process audit is scoped to the reviewed-code phase, and every repeat runs before classification

- **Date/status/scope:** 2026-09-01 · owner-approved implementation of the two items D-057
  left pending · `src/attest/review/executor.py`, the differential V funnel, and the
  receipt-validated corpus replay.
- **Decision:** two changes, both authorised by the owner against D-057's attribution
  finding.
  (a) The process-audit **adjudication window** opens when a test function starts executing
  and never closes again. Interpreter startup and pytest's own bootstrap no longer decide a
  candidate. Every event is still recorded in full — event, target, phase and bounded stack
  land in a durable per-run `process-observed` file — and a run that reaches a verdict
  without the window ever having opened is DEFERRED rather than trusted.
  (b) Every configured repeat now runs on **both** sides before anything is classified. A
  single indeterminate head run no longer returns immediately, and the base side is no
  longer skipped because of the head result. Classification then reads all runs: head
  failing every repeat with base passing every repeat is `REGRESSION_REPRODUCED`; head
  disagreeing with itself is unstable and uncertified; head uniformly indeterminate is named
  as such with the first run's reason; head passing every repeat is not reproduced; base
  failing too stays unfaithful.
- **Why:** D-057 established that the marker was interpreter-scoped — its first event in the
  corpus environment is `uname -p`, spawned by `platform.uname()` while pytest imports
  `py -> uuid`, before one line of reviewed code runs. It therefore fired for every candidate
  and distinguished nothing. Repeats exist to rule out a one-off; aborting on the first
  indeterminate run inverted that, so one hiccup denied a candidate and nothing was ever
  compared. A new end-to-end test — a receipt-validated corpus pair plus a known-correct
  reproduction, run through the real path — failed on the pre-change code with exactly the
  D-057 stack and passes after (a).
- **Consequences:** the first certified receipts this project has produced on real
  historical defects. On 9 receipt-validated `historical_bug_replay` cases: N = 23
  candidates, M = 6 reached differential execution, **K = 4 `regression_reproduced`**
  (head FAIL 3/3, base PASS 3/3), 4 surfaced findings each bound to one receipt, against
  K = 0 in all three prior rounds. Zero child-process DEFERs remained. The dominant
  remaining DEFER is the per-case product budget (15/23), not the guard. Base now always
  executes, so a differential costs up to twice the wall time it used to.
- **Explicitly unchanged:** the audited event set, `RLIMIT_NPROC`, timeouts and resource
  limits, adjudication strength while reviewed code runs, D-017/D-042 containment, and
  `G-SEC-002`/`G-SEC-003`. No allowlist exists. Certification still requires a deterministic
  head failure across every repeat. No factory statistical constant, alpha, LR, channel cap
  or coverage threshold was touched.
- **Known limit:** the window opens at the test call, so an event raised while the generated
  test module is imported is recorded but not adjudicated. That is an attribution boundary,
  not a containment hole — `RLIMIT_NPROC` still refuses the process either way. Widening the
  window to collection is in `docs/backlog.md` and needs its own owner decision.
- **Accuracy:** not estimated. The v1 receipt is `historical_integrity_only`, the run was
  executed without scoring authority, and the report withholds accuracy. K is an operational
  count of differential receipts; it is not precision, not recall, and no recall or precision
  statement may be derived from it.
- **Manual review of the four (2026-09-01, unpaid):** all four claims name the exact logic
  the reverted patch removes, one of them by the identifier the fix introduces (`no_commas`).
  The benchmark oracle independently corroborated three; its refutation of the fourth is a
  false negative caused by its own reproduction calling `black.Mode`/`format_str(line_length=)`,
  neither of which exists at that 2019-era revision, so it raised on both sides. Replayed
  locally at both SHAs: the product's reproduction separates the revisions correctly. The
  gap between K = 4 and the matcher's `matched = 1` is anchor tolerance (`line_slack = 0`,
  two misses off by one and two lines) plus single-hunk truth labelling, not a proposal or
  verification defect. Raising slack or relabelling truth after seeing these results is an
  outcome-dependent measurement change and needs its own owner decision (§16).
- **Erratum:** the first version of this entry and of the handoff report explained the
  harness's `regression_reproduced: 3` as an aggregate layer keeping one class per case.
  That was wrong. `runner.py` lets the oracle's per-finding class override the product's, so
  3 and 4 are two different measurements — product self-certification versus independent
  confirmation — and neither counter was truncating anything.
- **Evidence:** `docs/2026-09-01-d059-audit-window-and-repeat-semantics.md`;
  `docs/acceptance/evidence/2026-09-01-d059-wave4-replay/result.json`
  (SHA-256 `d0c09ac6a1338654809123a8cc45dd333ec2a95cf0a3f99d0499994a9744bd20`);
  `tests/test_corpus_certification_e2e.py`.
- **Reversal:** owner call. Restore interpreter-scoped adjudication only with evidence that
  a reviewed-code process attempt escaped attribution under the narrowed window; restore
  early repeat abort only with evidence that running all repeats costs more than it buys.
- **Trace:** D-017; D-020; D-037; D-042; D-049; D-057; D-058; `AGENTS.md` §4;
  `src/attest/review/executor.py`; `docs/roadmap.md`; `docs/backlog.md`; `DEVSPEND.md`.

### D-060 — every evidence class names its judge, and counts cover every candidate

- **Date/status/scope:** 2026-09-01 · owner-directed report-layer repair · implemented ·
  `src/attest/benchmark/{schema,runner,report,api,live,baselines}.py`, the calibration and
  comparison report payloads, and the benchmark report schema version.
- **Decision:** two report-layer defects are closed.
  (a) **Attribution.** The product certifies a finding from its own differential run and the
  benchmark oracle re-verifies it independently. `runner.py` let the oracle's class overwrite
  the product's, and every report then printed the survivor unlabelled. `Prediction` now
  carries `product_evidence_class` and `oracle_evidence_class` side by side, with
  `evidence_class_authority` naming which one `evidence_class` currently reports; the merge
  happens once, inside `extract_predictions_from_rows`, and keeps both. Reports emit counts
  per judge plus an explicit `oracle_overturned_product` count.
  (b) **Denominator.** `evidence_class_counts` was built from surfaced predictions only, so
  every candidate the gate did not surface disappeared. Counts are now built from the durable
  per-candidate verification records where they exist, and a `basis` field states which
  denominator was actually used, so a thin report never reads like a complete census.
- **Why:** D-059's erratum had to explain in prose that its `regression_reproduced: 3` and
  its K = 4 were two different measurements. A report should not need a prose erratum to say
  who judged what. Independently of any result, a count whose judge is unnamed and whose
  denominator is unstated cannot be audited.
- **Evidence (replayed on the committed D-059 artifact; no re-execution, no model call):**
  run total before `{regression_reproduced: 3, unfaithful: 1}`; after, product over 23
  candidates `{indeterminate: 17, regression_reproduced: 4, unfaithful: 2}`, oracle over its
  4 receipts `{regression_reproduced: 3, unfaithful: 1}`, `oracle_overturned_product: 1`.
  Per case, `case-81039ffa0c1e` moves from `{}` to `{indeterminate: 1, unfaithful: 1}` over
  its 2 candidates, and `case-c6f141a2be09` from a bare `{unfaithful: 1}` to a product
  `regression_reproduced` beside an oracle `unfaithful` with the disagreement counted.
- **Explicitly unchanged:** no factory statistical constant, alpha, LR, channel cap, gate
  threshold, coverage threshold, containment behaviour or product decision. This changes what
  the reports say about a run, never what the product does during one.
- **Consequences:** `REPORT_SCHEMA_VERSION` 4 -> 5. `evidence_class_counts` is now a mapping
  of judge -> class -> count plus `basis`, `counted`, `oracle_reviewed` and
  `oracle_overturned_product`; readers of the old flat map must be updated. Frozen artifacts
  written under schema 4 keep their original shape and are not rewritten.
- **Reversal:** owner call. Nothing here is load-bearing for product behaviour.
- **Trace:** D-019; D-022; D-059; `AGENTS.md` §14; `tests/benchmark/test_report.py`.

### D-061 — a reproduction that raises on both sides is not evidence, and the generator stops guessing APIs

- **Date/status/scope:** 2026-09-01 · owner-directed correction with an outcome-independent
  justification · implemented · `src/attest/review/executor.py` (`GENERATOR_SYSTEM`),
  `scripts/acceptance/d060_oracle_api_replay.py`, and D-059's `differential_v` figure.
- **Finding:** the single D-059 oracle receipt that refuted a product certificate did so with
  a test that raised on both revisions. Its body opened by probing
  `black.Mode(line_length=88)` and falling back to `format_str(src, line_length=88)`; at the
  pair's 2019-era revision neither name exists, so both branches raised `TypeError` on head
  and on base — exactly the `buggy_fail_fixed_fail` shape it reported as `unfaithful`.
- **Justification, stated independently of the outcome:** a test that raises identically on
  the defective and the fixed revision has zero discriminating power whichever side is right.
  It is therefore not evidence about the finding in either direction, and correcting it is
  warranted before knowing what the corrected test says. It does move a published number, so
  both numbers are reported and neither replaces the other in the record.
- **Both numbers.** Replayed through the product's own `execute_differential` at the pair's
  two SHAs, 3 repeats per side, corpus Python 3.8.3, **zero paid calls**:
  before (the probing body) head FAIL 3/3 and base FAIL 3/3 -> `buggy_fail_fixed_fail` ->
  `unfaithful`; after (`format_str(src, mode=...)`, the API that revision defines) head FAIL
  3/3 and base PASS 3/3 -> `buggy_fail_fixed_pass` -> `regression_reproduced`. D-059's
  `differential_v.confirmed` therefore reads 3 of 4 as recorded and 4 of 4 with the corrected
  reproduction; its `oracle_overturned_product` reads 1 as recorded and 0 corrected.
- **Decision:** `GENERATOR_SYSTEM` now requires the generated test to call only names the
  supplied source context shows the revision defining, and forbids guarding the call under
  test with a `try`/`except` around an alternative spelling.
- **Consequences:** this prompt is shared by the product proposer and the benchmark oracle,
  so generation changes on both arms and the next paid run is not generation-comparable to
  D-059's. No RED test is named: the change is a prompt string whose effect is model
  behaviour, and the only deterministic test of it would assert a substring, which D-058 §3.1
  forbids. The replay script is the durable check instead.
- **Explicitly unchanged:** classification contract, evidence-class pricing, repeat
  semantics, containment, timeouts and resource limits. A test that raises on both sides is
  still classified `unfaithful`; this decision does not reclassify it, it stops generating it.
- **Evidence:** `docs/acceptance/evidence/2026-09-01-d060-oracle-api-replay/result.json`
  (SHA-256 `a78ddabd88f04436dd1daf58dcca32fa284147d5e68765134da2b66973e66d1b`).
- **Reversal:** owner call; restore the previous prompt if the added constraint is shown to
  suppress otherwise-valid reproductions.
- **Trace:** D-022; D-059; D-058 §3.1; `AGENTS.md` §16.

### D-062 — matcher tolerance and hunk labelling, pre-registered before application

- **Date/status/scope:** 2026-09-01 · **pre-registration, written before the matcher is
  touched** · `src/attest/benchmark/matcher.py` and the benchmark scoring reports.
- **Why this is pre-registered.** D-059 reported K = 4 certified receipts against
  `matched = 1` and identified anchor tolerance and hunk labelling as the cause. Changing a
  matcher after seeing its results is the outcome-dependent measurement change `AGENTS.md`
  §16 reserves for an owner decision. The owner approved the change and required the rule and
  its justification to be recorded before it is applied, and the expected effect to be
  declared before it is measured. This section is that record.
- **Justification, established without reference to D-059's results.** Both grounds hold on
  the construction of the corpus alone and were true before any run existed.
  1. *A defect occupies a region, so line-exact anchoring was never a sound criterion.* An
     anchor names the statement a proposer is talking about; a labelled truth span names the
     lines a patch touched. A Python statement's header, its condition and its guarded call
     routinely sit on different physical lines, so a zero-line tolerance rejects anchors that
     name the right statement. `line_slack = 0` was a placeholder, not a measurement choice.
  2. *A defect can span several hunks, and the corpus cannot label all of them.* The
     manifest's truth spans are exactly the head-side (`side: "old"`) changed locations —
     verified across all 19 `historical_bug_replay` cases of `attest-v1`, zero mismatches.
     A fix hunk that is a pure insertion has no head-side line range at all, so the reverted
     head carries a real defect at a position the corpus never labels. Scoring such a case
     silently counts an unmatchable region as though it had been offered for matching.
- **The rule, as it will be applied.**
  1. `line_slack = 3` for benchmark scoring. Rationale: one Python statement's typical
     physical extent. The value is not tuned to observed distances, and to keep that
     auditable rather than merely asserted, every run reports a **sensitivity sweep** of the
     match count at `line_slack` in {0, 1, 2, 3, 4, 5, 10} beside the chosen value.
  2. **Truth spans are unchanged.** They already equal every head-side hunk, so no relabelling
     is performed and the frozen manifest and its digest are not touched.
  3. **Unlabelled hunks are named, never inferred.** Scoring reports per case the number of
     head-side labelled hunks and the number of fix-side hunks, and marks an unmatched
     finding `unlabelled_hunks_present` when its case has fix-side hunks with no head-side
     label. This is a statement about the corpus's labelling, never a claim that the finding
     is correct, and such a finding is never counted as matched.
- **Declared expectation, before application.** On D-059's four surfaced findings, at
  `line_slack = 3`:
  - with D-059's receipts exactly as recorded: **2 of 4** (up from 1 of 4). `fdbff9370c`
    (distance 0) and `b1e7f57dc2` (distance 1) match; `ed1d3ea89b` is excluded by its
    `buggy_fail_fixed_fail` receipt regardless of tolerance; `20d686ba82` is 16 lines from
    the only labelled span in its case.
  - with D-061's corrected receipt for `ed1d3ea89b`: **3 of 4**. Its distance is 2.
  - `20d686ba82` matches at no tolerance below 16. Its case, `case-c22190aa4fc9`, has 2
    fix-side hunks against 1 head-side label, so it is expected to be flagged
    `unlabelled_hunks_present`.
  - Sweep expectation: slack 0 -> 1/1, slack 1 -> 2/2, slack 2 and above -> 2/3, unchanged
    until slack 16 (recorded/corrected respectively).
- **Limits of this pre-registration, stated plainly.** The author had already read D-059's
  per-finding distances when choosing the value, so this is a recorded rule with a declared
  prediction, not a blind one. The protection that does not depend on the author is the
  sweep: any tolerance in [2, 15] yields the same counts, so the result is not sensitive to
  the specific value chosen.
- **What this cannot become.** `matched` remains an operational count. Precision and recall
  stay **not estimated** — no receipt with scoring authority exists, K and `matched` are
  counts of receipts and of location bindings, and per `INV-TRUTH-001` location overlap
  establishes neither correctness nor detection.
- **Explicitly unchanged:** no factory constant, alpha, LR, channel cap, gate threshold,
  coverage threshold, corpus manifest, validation receipt or product behaviour.
- **Reversal:** owner call; restore `line_slack = 0` if the tolerance is shown to bind
  distinct defects to one label.
- **Trace:** D-019; D-059; `AGENTS.md` §16; `INV-TRUTH-001`;
  `src/attest/benchmark/matcher.py`.

### D-062 amendment — applied, and the declared expectation held exactly

- **Date/status:** 2026-09-01 · the pre-registered rule above is now implemented and the
  D-059 records are re-scored. This amendment adds results; it does not edit the
  pre-registration, which was committed at `35ecaa5` before `matcher.py` was touched.
- **Implementation:** `matcher.DEFAULT_LINE_SLACK = 3`, used as the `scripts/benchmark.py`
  default for both scoring entry points; `matcher.line_slack_sweep` and
  `matcher.hunk_labelling`; `MatchResult.unlabelled_hunks_present`; and a `truth_matching`
  block in `BenchmarkRunReport` carrying the applied tolerance, the sweep, the per-case hunk
  labelling and the `INV-TRUTH-001` note. Truth spans were not relabelled and the frozen
  manifest and its digest are untouched.
- **Re-scored, no execution and no model call** (`scripts/acceptance/d062_rescore_d059.py`):

  | receipts | old rule (`line_slack = 0`) | new rule (`line_slack = 3`) | declared |
  |---|---:|---:|---:|
  | D-059 as recorded | 1 / 4 | **2 / 4** | 2 / 4 |
  | with D-061's corrected receipt | 1 / 4 | **3 / 4** | 3 / 4 |

- **Sweep, as recorded / D-061-corrected:** slack 0 -> 1 / 1; 1 -> 2 / 2; 2 -> 2 / 3;
  3, 4, 5, 10 -> 2 / 3; 16 -> 3 / 4. Every value in [2, 15] gives the same answer, so the
  count does not depend on the tolerance actually chosen.
- **Expectation versus observation: identical on every declared number.** `fdbff9370c`
  matched at distance 0 under both rules. `b1e7f57dc2` (distance 1) and `ed1d3ea89b`
  (distance 2, and only once D-061 corrected its `buggy_fail_fixed_fail` receipt) matched
  under the new rule. `20d686ba82` matched at no tolerance below 16, as declared, and its
  case `case-c22190aa4fc9` carries 1 head-side label against 2 fix-side hunks, so it is
  flagged `unlabelled_hunks_present` exactly as predicted.
- **One observation not declared in advance, recorded as such:** under the old rule
  `b1e7f57dc2` was also flagged `unlabelled_hunks_present`, because `case-99a012693940`
  likewise carries 1 head-side label against 2 fix-side hunks. The flag clears under the new
  rule because the finding matches. This is the flag behaving as specified on a case the
  pre-registration did not enumerate, not a rule change.
- **Still not estimated.** `matched` is a count of location bindings. No validation receipt
  with scoring authority exists for this corpus, and per `INV-TRUTH-001` an anchor
  overlapping a labelled span establishes neither correctness nor detection. Precision and
  recall remain **not estimated** and none may be derived from 1/4, 2/4 or 3/4.
- **Evidence:** `docs/acceptance/evidence/2026-09-01-d062-matcher-rescore/result.json`
  (SHA-256 `e2071ec565bea435c99b9d8457d1d68031742a06bf7f81de340e3f7bd6fe509b`);
  `tests/benchmark/test_matcher.py`.
- **Trace:** D-062; D-061; D-059; `AGENTS.md` §16.

### D-063 — the pricing layer carries an instrument that reports whether it is load-bearing

- **Date/status/scope:** 2026-09-01 · owner-directed instrumentation · implemented ·
  `src/attest/review/{gate,candidates,ledger,run}.py`, `src/attest/cli/main.py`,
  `src/attest/benchmark/{runner,api,live}.py`.
- **Decision:** every candidate now carries one recorded field,
  `pricing_changed_decision`: whether the decision taken on the full wealth differs from the
  decision the **strongest single purchased channel** would have taken against the same
  threshold. It is written to the durable per-candidate `review` ledger row and to the
  candidate store, and surfaced by `attest stats` and by the benchmark calibration report
  beside precision, abstention rate and silence precision.
- **This decides nothing.** The gate never reads the field. No threshold, alpha, cap, LR,
  purchase order or action changes. `GateResult.pricing_changed_decision` is computed after
  the decision and is ignored by `apply_gate`.
- **Why an instrument rather than a verdict.** Whether the wealth multiplication is
  load-bearing is a question about many rounds, not about one. The project already treats
  silence rate and abstention rate this way: measure continuously and let the number speak.
  A one-off judgement would go stale the moment a constant or an alpha moved; a field
  recorded on every candidate reports itself each round and will register the change.
- **Backfilled over every per-candidate record held, no model call and no execution**
  (`scripts/acceptance/d063_pricing_instrument_backfill.py`):

  | source | candidates | `pricing_changed_decision` |
  |---|---:|---:|
  | exhaustive reachable channel grid at alpha = 0.1 | 45 combinations | **0** |
  | 2026-09-01 history counterfactual (S, T, wealth recorded) | 26 | **0** |
  | D-059's four surfaced findings, over every reachable S | 4 (20 rows) | **0** |

  **So the wealth multiplication has changed a decision zero times to date.** The grid
  enumeration explains why, and it is structural rather than incidental: with the frozen
  factory tables `S * T` tops out at 9, below the surfacing threshold of 10, while the
  smallest reachable wealth is 0.5, above the discard threshold of 0.1. Only V reaches the
  threshold, and V = 20 alone already reaches it. Every certified receipt this project has
  produced was decided by V on its own, exactly as the owner suspected.
- **What this does not say.** It is not an argument to remove S, T or the multiplication, and
  it is not an accuracy statement. It says that at this alpha, with these caps, the product
  of the purchased channels has never crossed a threshold that its strongest single channel
  did not already cross. Raising a cap, lowering alpha, or pricing a new channel changes the
  enumeration and requires its own.
- **Migration:** the two fields are optional on `review` ledger rows and on candidate-store
  records, so every historical ledger stays valid and readable. Records written before the
  instrument existed report `None` and are counted as uninstrumented, never as `False`.
- **Evidence:** `docs/acceptance/evidence/2026-09-01-d063-pricing-instrument/result.json`;
  `tests/test_gate.py::test_pricing_instrument_records_without_deciding_anything` and
  `::test_pricing_instrument_reports_true_when_the_product_is_load_bearing`, the second of
  which pins that the instrument fires when the product really is load-bearing.
- **Reversal:** owner call; the field is inert and removing it changes no behaviour.
- **Trace:** D-007; D-008; D-022; D-059; `AGENTS.md` §16; `src/attest/review/gate.py`.

### D-064 — F is redefined once as graded change heat, measured once, and stays unpriced

- **Date/status/scope:** 2026-09-01 · owner-directed redefinition and single measurement ·
  `src/attest/review/history.py`, its ledger row, and
  `scripts/acceptance/d064_history_heat_discrimination.py`.
- **What changed.** The v1 observation asked one boolean question — is the anchor line owned
  by a recent revert or hotfix within the last 50 commits? — and fired on 0 of 26 candidates.
  That is a rare event, not a fair test of whether the line's history carries signal. F now
  records four raw values per candidate and applies no threshold to any of them: commits
  touching the anchor line in the trailing 12 months, the share of those whose subject
  matches a recorded repair vocabulary, the number of distinct authors, and the days since
  the line last changed. The window ends at **the reviewed revision's own commit date**, not
  at the wall clock, so a 2019 corpus revision is asked about its own twelve months.
- **F remains unpriced.** It buys no wealth, multiplies nothing, orders nothing, vetoes
  nothing, and reaches no publication path. `HISTORY_SIGNAL_SCHEMA_VERSION` moves to
  `attest.history-signal.v2` and the row still carries `priced: false`. The repair pattern is
  written into every row so the share is auditable rather than asserted.
- **The measure is discrimination, not trigger rate.** Two units are reported.

  *Per candidate* — the unit the product actually emits, all 26 candidates of the 2026-09-01
  history counterfactual, each with its four raw values in the artifact's `rows` table:

  | field | `historical_bug_replay` (n = 25) | `developer_fix_control` (n = 1) |
  |---|---|---|
  | commits | median 1, p25 1, p75 2 | 1 |
  | repair_share | median 0.00 (n = 21 defined) | 1.00 |
  | distinct_authors | median 1, p25 1, p75 2 | 1 |
  | days_since_last_change | median 90, p25 35, p75 122 (n = 21) | 0 |

  The control arm produced **one** candidate. There is no distribution to compare, and that
  is the honest result at this unit, not a formatting problem.

  *Per anchor line* — the unit that can carry a balanced comparison. Bug group: every
  head-side labelled defect line of the 9 replay cases. Control group: an equal number of
  fixed-stride lines from the same file at the same revision, at least 10 lines from every
  changed location, chosen without reference to what the signal says about them.

  | field | defect line (n = 72) | non-defect line (n = 72) |
  |---|---|---|
  | commits | median 1, p25 1, p75 2, mean 1.32, max 4 | median 1, p25 0, p75 2, mean 1.13, max 9 |
  | repair_share | median 0.00, p75 1.00, mean 0.30 (n = 54) | median 0.00, p75 0.00, mean 0.14 (n = 51) |
  | distinct_authors | median 1, p25 1, p75 1, mean 0.99 | median 1, p25 0, p75 1, mean 0.81 |
  | days_since_last_change | median 65, p25 11, p75 122, mean 86 (n = 54) | median 109, p25 74, p75 158, mean 126 (n = 51) |

- **No significance test was run and none should be read in.** The samples are small, they
  come from one project, and the distributions are printed side by side precisely so no
  statistical conclusion is smuggled in. The medians of commit count and distinct authors are
  identical between the groups and every field overlaps heavily.
- **Judgement, stated as judgement.** The redefinition did what it was meant to do: the v1
  signal was constant and therefore incapable of discriminating anything, and the v2 signal
  is not constant. Two of its four fields point in the direction one would expect. That is
  not enough to price it, and it is not a refutation either. The blocking gap is the
  candidate unit: the control arm emits almost no candidates, so on this corpus F cannot be
  evaluated where it would actually be used.
- **Stopping here, deliberately.** One redefinition, one measurement. No third or fourth cut
  of the same history was attempted. The result, the caveat below and the conditions for a
  future pricing argument are in `docs/backlog.md`.
- **Caveat that any future pricing argument must bound first:** a BugsInPy head sits at the
  bug-introducing commit, so the defect region was necessarily touched recently in that
  head's own history. Real pull requests also review recently changed code, so the analogy is
  not empty, but the size of that inflation is unmeasured.
- **Explicitly unchanged:** no factory constant, alpha, LR, channel cap, gate threshold,
  coverage threshold, pricing contract or product decision. F is not a channel.
- **Evidence:** `docs/acceptance/evidence/2026-09-01-d064-history-heat/result.json`
  (SHA-256 `e1f8658cf7fa7d84594141b361612e7f802d8f7bc16913cbb266dc1d941daa99`);
  `tests/test_history.py`.
- **Reversal:** owner call; F is inert and can be removed or re-scoped without touching any
  decision path.
- **Trace:** D-022; D-059; D-063; `docs/backlog.md`; `src/attest/review/history.py`.

### D-065 — F is measured at the candidate unit and does not discriminate there, and the pricing layer is blocked by S·T rather than by F

- **Date/status/scope:** 2026-09-01 · owner-directed measurement · offline, no paid call ·
  `scripts/acceptance/d065_candidate_unit_discrimination.py` and its artifact. No source
  file, constant, threshold or contract changed.
- **What was wrong with D-064's measurement, and what changed.** D-064 could not compare F
  at the unit the product emits because its control arm produced 1 candidate against 25.
  The blocker was the **measurement population**, not the signal definition, which is
  unchanged here: the same four graded fields, the same recorded values, regrouped. The
  population selected — and its reason, written before any number existed, in
  `docs/2026-09-01-d065-f-discrimination-population.md` — is the 26 candidates already on
  record, split by whether the anchor lands on the corpus's own head-side labelled defect
  region. It is the only available population whose non-defect label is product-blind, and
  the only one that places both groups **inside the same reviewed revision**, which is the
  unit at which a priced F would actually decide.
- **Why the wave-5 control arm was empty, established from the record rather than guessed.**
  The two arms of a wave-5 pair are the same diff run in opposite directions, so their
  manifest `changed_locations` are identical. Yield tracked direction alone: 1 candidate over
  the nine fix-applying heads against 25 over the nine fix-reverting heads, with the largest
  labelled diff silent in both directions and a one-line diff yielding two. The dogfood ledger
  agrees — 617 added lines produced 0 candidates, a semantics-preserving refactor produced 0.
  Any population built from clean, addition-shaped commits inherits that emptiness.
- **The split, at D-062's pre-registered `line_slack = 3`:** 20 on a labelled defect region,
  5 off it, 1 on a fix-applying head where no labelled defect exists. Stable from slack 3
  upward (20/5 at 3, 4, 5, 10) and moving below it (10/15 at 0, 18/7 at 2).
- **The result, at the candidate unit.**

  | field | on labelled defect | off labelled defect |
  |---|---|---|
  | commits | n = 20 · median 2 · mean 1.50 | n = 5 · median 1 · mean 1.00 |
  | repair_share | n = 16 · median 0.00 · mean **0.042** | n = 5 · median 0.00 · mean **0.200** |
  | distinct_authors | n = 20 · median 1 · mean 1.15 | n = 5 · median 1 · mean 1.00 |
  | days_since_last_change | n = 16 · median **97.5** · mean **89.6** | n = 5 · median **84** · mean **156.8** |

  The two fields D-064 called directionally suggestive at the anchor-line unit do **not**
  carry to this one: repair share inverts, and days-since-last-change disagrees with itself
  by median and mean on a five-element sample. The two fields D-064 found flat at the line
  unit are the two that separate here, weakly. Percentile bands against an in-repository
  ruler do not separate the groups: every off-label candidate sits at commits Q2 and authors
  Q3, while the on-label group straddles Q1/Q2/Q4. **No significance test was run and none
  may be read in.**
- **The finding that outranks the group means:** F is near-constant *inside* one review.
  Over the seven cases with more than one candidate, `repair_share` takes one distinct value
  in six (0.00 in four; undefined on both candidates in a fifth), `distinct_authors` spans ≤ 2 values, `commits` spreads ≤ 3. A priced
  F multiplies one candidate against another on the same head; a quantity that barely moves
  inside a head cannot re-order what one review shows.
- **The pricing counterfactual, and the number that actually blocks it.** At an F cap of 1.2,
  **zero** candidates cross the surfacing threshold, in every group. Crossing needs
  `S·T ≥ 10/1.2 = 8.334`; the observed maximum `S·T` over all 26 candidates is **3.0**, with
  `T = 1.0` on every one and `S ∈ {2.0, 2.639, 2.9485, 3.0}`. The owner's arithmetic is right
  where it was aimed — against D-063's *reachable* ceiling of 9, `9 × 1.2 = 10.8` clears 10 —
  but that ceiling has never been observed. Against the observed ceiling the required cap is
  `10 / 3.0 = 3.34`. Two structural consequences: a flat cap multiplies every candidate
  identically, so its crossing set is exactly `{S·T ≥ 10/c}`, a function of S and T that
  carries no F information at all (which is why cap 3.34 splits 5:1 and cap 5.0 surfaces
  everything including the candidate on a *fixed* revision); and at cap 1.2 the answer is
  invariant to how F is graded, since any multiplier bounded by 1.2 still needs `S·T ≥ 8.334`.
- **Judgement, stated as judgement.** The pricing layer is not activatable under foreseeable
  evidence, and F is not the reason — `S·T` is, by a factor of 2.8 against a threshold it has
  never approached. Separately and on its own terms, F did not discriminate at the candidate
  unit here. Neither statement is a refutation of F: n = 5 on the non-defect side, and four
  of those five anchor in `tests/test_black.py`, which BugsInPy cannot label at all because
  its `bug_patch.txt` carries only source hunks. That group is **unlabelable, not verified
  clean** — the fifth member, `black.py:610`, reads like a genuine second defect the corpus
  does not point at, on a case D-062 already flagged for unlabelled pure-insertion hunks.
- **Erratum (2026-09-02, unpaid).** This entry first read "0.00 in five". Four of the
  six single-valued cases hold `repair_share = 0.00`; the fifth, `case-1e2261dcc6e9`, has
  it **undefined on both candidates** because no commit touched either anchor line in the
  window. The artifact recorded that correctly as `defined: 0, distinct_values: 0`; only
  the prose collapsed undefined into zero. The finding is unchanged — six of seven cases
  still carry one distinct value or none. Related: the single candidate driving the
  repair-share inversion (`00afbee573`, share 1.00) is itself one of the four off-label
  candidates anchored in `tests/test_black.py`, the group this entry already names as
  unlabelable; the inversion is that one point.
- **Stopping here, as pre-registered.** One population, one measurement. No fifth slice of the
  same history, no graded-map simulation, and no cap, alpha or constant moved to force a
  crossing.
- **Explicitly unchanged:** F stays unpriced — it buys no wealth, multiplies nothing, orders
  nothing, vetoes nothing and reaches no publication path. No factory constant, alpha, LR,
  channel cap, gate threshold, coverage threshold, pricing contract or product decision moved.
  `INV-TRUTH-001` is respected: anchor overlap is used as a **grouping** variable and is never
  reported as detection. `matcher.match_findings` was deliberately not reused — it scores
  surfaced, differentially reproduced predictions, and none of these 26 ever purchased V, so
  passing them through it would have required forging a placement and a repro status.
- **Relation to D-063 and D-059:** this run makes no model call, so D-063's note that the
  changed generation prompt makes new runs incomparable with D-059 on generation quality does
  not apply — these are D-064's own 26 candidates, regrouped.
- **Evidence:** `docs/acceptance/evidence/2026-09-01-d065-candidate-unit-discrimination/result.json`
  (SHA-256 `245b35b45c564a69186c4c87a7c7ff087218d34a5acad4daa6dfe2985f68b7d9`);
  `docs/2026-09-01-d065-f-discrimination-population.md`.
- **Reversal:** owner call. Nothing is load-bearing; the artifact and script can be deleted
  without touching any decision path. The result would be superseded by a corpus whose control
  arm emits candidates, or by any change that lifts observed `S·T` toward its reachable ceiling.
- **Trace:** D-059; D-062; D-063; D-064; `AGENTS.md` §16; `INV-TRUTH-001`; `docs/backlog.md`.
