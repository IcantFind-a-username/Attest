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

### D-070 — Working-tree boundary and a cap on agent-created work orders

- **Date/status/scope:** 2026-09-02 · owner-directed process amendment · `AGENTS.md` §7,
  §10, §16. Numbers D-059 through D-069 are reserved for the owner's local branch of
  2026-09-01/02 (K=4 live receipts, the five-wave pricing task and its follow-ups), which
  had not been pushed when this entry was written; this entry deliberately skips them so
  that branch can merge without renumbering.
- **Decision:** the repository working tree is the only directory an agent may read as
  input, execute against, or write to; any external corpus must be named in the work order
  or an owner-approved fixture list before the first read and enters as a clone of its
  remote under `.attest/corpora/<name>/` at a recorded commit, never as the owner's local
  checkout. One task may propose at most one
  new work order, only as a decision package, and may not implement it, chain orders behind
  it, or open a new prefix series. A new CLI subcommand, a new product surface, or an owner
  queue longer than three items is a §16 stop-and-ask item.
- **Why:** an overnight run asked to find a non-defect population where the product
  produces candidates (so the F facet could be scored) instead invented a whole-repository
  `scan` surface, created an `A-`/`F-`/`L-00` order series absent from `docs/roadmap.md`,
  produced 49 commits and 23 owner-queue items, and ran the scanner against the owner's
  local checkout of another project. The owner had said that project could be used to
  exercise the algorithm, and meant a clone from its remote; the agent opened the sibling
  directory instead. The repository documents at the baseline did not cause it (§1 ranked
  the owner instruction first; roadmap NOW was C-02/V-01; `scan` existed nowhere), but §10
  step 5 read as permission to author unlimited orders and nothing said how an authorized
  external corpus enters the working tree. A local checkout may carry uncommitted work and
  is not a reproducible input; a clone at a recorded commit is.
- **Consequences:** the divergent chain is not merged; only its git-history predicate fixes
  are candidates for cherry-pick under their own order. Overnight tasks start from a fresh
  session whose only context is the prompt and this repository. No factory constant, gate,
  containment or security invariant changes here.
- **Evidence:** `AGENTS.md` §7 last bullet, §10 closing paragraph, §16 new bullet; the
  overnight report of 2026-09-02 held by the owner.
- **Reversal:** owner call — relax the one-order cap if a documented measurement was blocked
  by it rather than by a missing corpus.
- **Trace:** D-039; D-049; D-058; `AGENTS.md` §1, §7, §10, §16.

### D-071 — Mainline to the product and the owner's attention budget

- **Date/status/scope:** 2026-09-02 · owner-directed · new `docs/mainline.md`;
  `docs/roadmap.md` NOW row; `AGENTS.md` §10; `docs/README.md` authority table.
- **Decision:** the remaining roadmap orders are worked in the fixed sequence of
  `docs/mainline.md` §2 (C-02, C-03, C-04, R-03, R-01, V-01, E-02 pilot, C-05, V-02, X-01,
  X-02, V-03, E-02 held-out, E-01, E-04, L-01); "product" is defined by its §1; the pilot
  fork in its §4 chooses the next task from numbers; owner repositories, BugsInPy and
  SWE-bench Verified are the corpora, with a committed dev/held-out split. Only §16 items
  and the four decisions in mainline §5 reach the owner; everything else is the agent's,
  logged in at most six lines; a handoff carries at most three owner items.
- **Why:** the owner directs direction and does not read code; the last overnight produced
  23 owner questions, which is a failed handoff. The roadmap's eight phases are correct as
  dependencies but did not say what to do next without an owner round-trip, and no document
  said which corpora could be used without asking.
- **Consequences:** V-01 moves after R-03/R-01 (candidates before richer receipts); S-*,
  N-01, X-03, R-04, pricing/F research and any scan surface are off the mainline until
  after L-01. No gate threshold or factory constant changes.
- **Reversal:** owner call — reorder if the step-7 pilot shows receipts, not candidates,
  are the binding loss.
- **Trace:** D-049; D-058; D-070; `docs/mainline.md`; `docs/roadmap.md` §3.

### D-072 — C-02: only a validator-accepted receipt can speak

- **Date/status/scope:** 2026-09-02 · active · `review/ci.py`, `review/certify.py`, `review/report.py`, `github/presentation.py`, `review/executor.py`.
- **Decision:** CI verifies every non-discarded candidate (S/T rank, never publish) and builds one `CertificationReceipt` per regression-reproduced run through the new `review.certify` adapter; presentation and the CLI report accept only `CertifiedFinding`. `ci_final.action == "surface"` now means "receipt accepted"; the S/T/V wealth stays beside it for analysis. A `certification` ledger row records accepted/rejected/not-attempted with the receipt digest.
- **Why:** at alpha ≥ 0.15 an S·T-terminal candidate was published with no verification (`RISK-CERT-01`); `G-CERT-001` demands zero speech without a current accepted receipt.
- **Limits:** environment/interpreter/executor digests bind declared inputs (limits, guard source, interpreter path, executor module bytes); V-01 deepens them to test bytes, commands and per-run artifacts. Policy source is the event base SHA until C-03 resolves the merge-base.
- **Reversal:** none foreseen; removing the adapter reopens the bypass.


### D-073 — C-03: the counterfactual is the merge-base and policy is base-owned

- **Date/status/scope:** 2026-09-02 · active · `review/ci.py`, `review/config.py`, `review/diffs.py`, `cli/main.py`.
- **Decision:** CI resolves `git merge-base <event base> <head>` and DEFERs when it is unavailable (no two-dot fallback); discovery diffs and differential execution both use it. Policy comes from the committed `.attest.toml` at the merge-base (factory defaults when absent) with only protected Action inputs on top; the model is Action-owned so provider and pricing agree; a caller-supplied config (benchmark harness) is its own protected layer, and the harness declares the counterfactual of its reverse historical pairs via `merge_base_sha` (`248adfb`) because a head that is an ancestor of its base has no merge-base diff; the Action path never passes it. Source and digest are recorded in a `certification_task` row and bound into every receipt's task; the workspace HEAD is re-checked before the first author-visible write.
- **Why:** the head could relax alpha/caps/budget by editing its own file, and base-tip two-dot diffs reviewed the base's progress as if the PR had made it (`G-CERT-002`).
- **Limits:** local `attest review` still reads the working tree's file (developer-owned, no trust boundary); the Action does no explicit fetch, so the example workflow's `fetch-depth: 0` is required and a shallow checkout DEFERs with a stated reason.
- **Reversal:** none foreseen.


### D-074 — C-04: self-reported evidence lives in its own namespace

- **Date/status/scope:** 2026-09-02 · active · `cli/main.py`, `review/ledger.py`, `review/run.py`.
- **Decision:** `attest verify` writes a `self_report` row (actor, reproduced, evidence) and buys no channel; it prints a note, never a verdict. Review rows from `run_review` carry `authority: "ranking"`, and the surfaced projection counts neither ranking rows nor legacy `verified_*` rows (namespace `legacy_self_reported_unknown`, readable unchanged) as author-visible, so manual notes and S/T ranks never enter precision, the alpha window, or publication. `attest stats` reports self-reports separately.
- **Why:** `G-CERT-003`: a manual `--reproduced` moved wealth 2.6 → 52.8 and counted as a surfaced, labelable finding, contaminating the calibration denominator (`INV-EVIDENCE-001`).
- **Limits:** no certification JSON import boundary exists yet, so "reject self-reported IDs at the boundary" waits for V-03's offline verifier; legacy rows without the authority marker written by the pre-C-02 terminal report keep their old surfaced semantics because that report did assert them.
- **Reversal:** none foreseen.


### D-075 — R-03: clusters are components of the candidate multiset; eligibility precedes generation

- **Date/status/scope:** 2026-09-02 · active · `review/dedup.py`, new `review/eligibility.py`, `review/diffs.py`, `review/schema.py`, `review/candidates.py`, `review/run.py`, `review/ci.py`.
- **Decision:** discovery clusters (`attest.discovery-cluster.v1`) are connected components of the pairwise anchor/lexical similarity graph (thresholds unchanged from D-013), represented by the medoid with canonical tie-break, sorted provenance retained, and a cluster id digested from the member anchor/claim set without sample ids. Before any paid reproduction each candidate is classified from facts only — non-Python suffix, executor host unavailable, anchored file new in the diff, or enclosing def/class absent at the merge-base → `new_code` — and only `regression` enters V; the rest are `not_attempted` certification rows outside the eligible denominator. Parse failures fail open to `regression` because V still decides.
- **Why:** the greedy first-match merge let sample completion order pick the public claim and its anchor (`G-RECALL-001`), and new-code/non-Python candidates bought generation they could never certify (D-043).
- **Limits:** components can chain distinct defects through intermediate wordings; C-05 owns publication clusters and may version the schema. Candidate counts on real PRs are unchanged by construction (clustering merges exactly what the old predicate merged); the eligible share is measured in the E-02 pilot table.
- **Reversal:** a C-05 publication-cluster schema that needs different discovery identities.


### D-076 — R-01: the proposer sees planned units with bounded repository context

- **Date/status/scope:** 2026-09-02 · active · new `review/planner.py`, `review/proposer.py`, `review/run.py`; trial harness under `scripts/corpus/`.
- **Decision:** the merge-base diff is split into stable file units (id = digest of paths and hunk headers) packed under 30k chars; each unit carries ≤10k chars of read-only context — the head file's imports, the head and merge-base source of every definition enclosing a hunk, up to four call sites outside the diff (test paths and generic names such as `run`/`append` excluded), and up to eight test functions naming those symbols — with every omission recorded in a `review_plan` ledger row. Units are proposed in plan order with K samples each; the first unit the budget cannot cover stops the run and the rest are reported as omitted, never silently truncated. Findings are clustered task-wide (R-03).
- **Why:** with only the diff the proposer could not see a caller whose callee changed (the RED), invented a missing `import sys` on a real pytest change, and had no view of the old behaviour. Real-corpus trial on five SWE-bench Verified dev regression PRs at K=4 (`.attest/corpora/swebench/trials/`): diff-only 7 candidates/$0.2575, a no-context repeat 7/$0.2581, planner context 6/$0.3566; every arm found each true defect, the context arm dropped the `import sys` garbage claim and sharpened the rest, cost rose 38%, and truncated samples went 2→3 of 20.
- **Limits:** candidate count is set by K and clustering, not by context; the context arm's extra truncation is R-02's structured-output concern and is logged in the backlog; retrieval is textual (call-site grep, AST enclosing scopes), not a resolver.
- **Reversal:** if the E-02 pilot table shows candidates→eligible or generation losses dominated by context length, cap `MAX_CONTEXT_CHARS` lower or drop the definition excerpt first.


### D-077 — V-01: a receipt is a content-addressed bundle that verifies offline

- **Date/status/scope:** 2026-09-02 · active · `review/executor.py`, `review/certify.py`, new `review/evidence.py`, `review/ci.py`.
- **Decision:** differential execution collects first (same guards) and requires exactly one node, then selects it explicitly on every repeat; each run records command template, interpreter path+version (probed once per process), guard-relevant environment digest, exact test-bytes digest, JUnit text and structured counts, and the receipt's per-run `artifact_digest` is the digest of that run record. Accepted certifications are written as `attest.evidence-bundle.v1` under `.attest/evidence/<task>/<candidate>/` with a manifest; `verify_bundle` recomputes every file digest, run record, cross-run agreement (test bytes, node, environment, interpreter, command) and the provenance digest before calling the pure validator. Subject identity fields come from the runs themselves; disagreement collapses to "" and rejects.
- **Why:** `G-SEM-001`: the C-02 receipt digested declared inputs and its provenance was never recomputed, so a flipped byte could pass; the exact node and collection count were inferred from JUnit rather than enforced before repeats.
- **Limits:** the bundle is written by the same process that ran the tests (V-03 adds fresh-state and authenticated provenance and ships the verifier as a CLI); environment identity covers the guard-relevant variables, not the full dependency set.
- **Reversal:** a V-03/X-01 protocol that moves run records to the executor side supersedes the writer, not the verifier.


### D-078 — E-02 pilot: next task is the generator's context, then proposal truncation

- **Date/status/scope:** 2026-09-02 · active · `docs/acceptance/2026-09-02-e02-pilot.md`, `certification/validate.py` (`4561686`), `scripts/corpus/`.
- **Decision:** the dev-slice pilot (8 regressions, 8 controls, K=4) certified 2 with 0 control false publications and no candidates→eligible loss, so per `mainline.md` §4 the next task is the R-01 revisit applied to reproduction generation (planner context and the reproduction prompt, within existing caps) and then the proposal-truncation loss (10/32 samples at the 2,400-token bound) via R-02's precommitted recovery; the dev slice is re-run after each. A claim is bounded as prose (≤ 2,000 chars) rather than as a 256-char identifier, a kernel defect the pilot exposed.
- **Why:** the largest named loss is eligible→certified (unfaithful, `{}`, non-failing generated tests), and two of the three silent cases were silent only because every proposal sample truncated.
- **Limits:** three repositories, feasibility-selected; the interpreter had to match each project's era (3.9 for requests/pylint, 3.11 for pytest); pytest's own repository is runner-is-subject.
- **Reversal:** a re-run that certifies ≥ 5 on the dev slice with 0 control publications moves the mainline to C-05.


### D-079 — Step a: the reproduction generator sees both sides of the anchored definition

- **Date/status/scope:** 2026-09-02 · active · `review/planner.py` (`generation_context`), `review/executor.py` (prompt, `generate_repro`, `verify_candidate`); `scripts/corpus/regen_trial.py`.
- **Decision:** reproduction generation receives the head definition enclosing the anchor, the same definition at the merge-base, the module's imports and the existing tests naming the symbol (≤ 8,000 chars), and the system prompt demands one module-level test that fails on head because of the claim and asserts the merge-base behaviour concretely, imported the way the project's tests import. One generation per candidate; the schema-only retry of D-052 is unchanged.
- **Why:** the six eligible-but-uncertified dev-slice candidates failed on guessed base behaviour, non-distinguishing inputs, or `{}`; the generator had only a 200-line head window.
- **Measurement (owner RED: ≥ 3 of 6 faithful):** 5 of 6 faithful (head FAIL 3/3, base PASS 3/3): requests-2931 first candidate, pylint-4970 second, pytest-10081, pytest-6202 both; the remaining requests-2931 candidate still guesses the base URL encoding. Two earlier passes at 2/6 and 0/3 were interpreter-blocked (pytest 5.x cannot compile on 3.11's AST; a 0.0.0 version failed pytest's minversion), which set the executor-side interpreter rule: the highest available interpreter within the project's declared `Programming Language :: Python :: 3.X` classifiers, else the oldest available (3.9); CPython 3.8 is excluded because its eager `platform.uname()` trips the process guard (owner item 3, 2026-09-02).
- **Limits:** the executor's interpreter and each project's own runner still bound what can run; pytest's repository is runner-is-subject (backlog).
- **Reversal:** none foreseen; the context is bounded and read-only.


### D-080 — R-02 (step b): truncated proposals are salvaged, unusable ones get one cached repair

- **Date/status/scope:** 2026-09-02 · active · new `review/recovery.py`, `review/proposer.py`, `review/run.py`.
- **Decision:** a proposal sample that stops at the output bound keeps the complete finding objects before the cut (deterministic, no model call, marked `salvaged:<n>`); a sample with nothing salvageable gets exactly `MODEL_REPAIR_ATTEMPTS = 1` further sample of the same prompt under the same bound, reserved before dispatch; every attempt is cached under a digest of inputs, slot and attempt index in `.attest/cache/attempts`, so a repeated run replays instead of buying and cannot pick among attempts; replayed attempts cancel their reservation. All of this precedes any behavioural execution.
- **Why:** 10 of 32 pilot proposal samples truncated at 2,400 tokens, silencing two cases outright; recovery must be precommitted, never outcome-aware (`G-RECALL-001`, AGENTS §6.13).
- **Limits:** the reproduction generator keeps D-052's single schema retry; a `{}` text block (no content returned) is not salvageable and is recorded as such; the cache is per repository.
- **Reversal:** set `MODEL_REPAIR_ATTEMPTS` to 0 and keep salvage only; attempts stay on disk.


### D-081 — C-05: e-value Bonferroni family policy with a hard author-visible cap

- **Date/status/scope:** 2026-09-02 · owner-selected (mainline §5 A, answered 2026-09-02) · new `certification/clustering.py`, `certification/selection.py`, `review/ci.py`.
- **Decision:** certified findings are clustered for publication (same reproduction digest, or anchors within three lines of one file; connected components over a canonically sorted input) and a cluster counts once through its highest-e-value member (ties on candidate id); with m eligible candidates in the PR a finding publishes only when its e-value (S/T/V wealth) ≥ m/α; at most three findings are author-visible anywhere, inline or summary, so nothing is "overflow" any more; suppressed certified findings stay private with a reason (`below family threshold`, `same defect as a published finding`, `beyond the hard author-visible cap`) in a `publication_policy` ledger row that also reports the arithmetic mean of the eligible candidates' e-values as the PR-level global null. Factory LR, α, K unchanged.
- **Why:** `G-CERT-004` / `INV-FAMILY-001`: the dev-slice re-run certified the same pylint defect twice and the old cap was layout-only.
- **Limits:** the cluster relation is anchor/digest based, not semantic; V-02 binding will sharpen it; benchmark PR-any-wrong exposure now counts published findings only.
- **Reversal:** a different family method needs a new policy schema version and re-runs `G-CERT-004`.


### D-082 — Empty proposal samples classified; proposal output bound raised to 3,200

- **Date/status/scope:** 2026-09-02 · owner-directed · `review/proposer.py` (`PROPOSER_MAX_OUTPUT_TOKENS`), `tests/test_proposer.py`.
- **Decision:** of the 43 empty proposal samples in the dev-slice re-run, 30 were correct silences on controls; on the eight regression PRs 9 of 13 empty samples had stopped at the 2,400 bound with the allowance consumed by reasoning and 4 were deliberate empties, so exhaustion dominates where it costs recall and the bound is raised to 3,200 (a runtime output parameter, not a statistical constant; D-051's arithmetic and the documented ~26,000-char default-budget diff boundary move with it). K stays at 4 for the pilot.
- **Why:** owner answer 3 of 2026-09-02; verified together with C-05 on the next dev-slice re-run rather than alone.
- **Limits:** the classification is by stop reason and output size, not by reading the samples; a repair sample under R-02 already recovers some of these.
- **Reversal:** if the re-run shows no fewer exhausted samples, the bound returns to 2,400.


### D-083 — V-02: differential evidence must execute a changed line

- **Date/status/scope:** 2026-09-02 · active · new `certification/binding.py`, `review/executor.py` (tracer, binding), `certification/types.py` (receipt v3: `binding_policy_version`, `binding_digest`; policy `binding_policy_version`), `certification/validate.py`, `review/evidence.py`, benchmark status map.
- **Decision:** the guard preamble traces the anchored file with `sys.settrace` and every run records the lines it executed; the binding observation is the set of the anchored file's changed lines (its diff hunks between base and head) executed on every head run. Policy `attest.binding.changed-line-coverage.v1` accepts only when that set is non-empty; otherwise the differential result is a typed `UNBOUND` abstention that buys no evidence. The receipt binds the policy version and the observation digest, the bundle stores the observation and the offline verifier recomputes it.
- **Why:** `G-SEM-002`: a test that fails on head and passes on base without running the changed code (reading the source text, an unrelated known failure) proved the diff changed *something*, not the claim; the mainline RED demands its rejection.
- **Comparison (mainline §2 step 9):** changed-line coverage costs no extra run and is deterministic; the base run already is the whole-diff ablation; mutation of the alleged cause and dependency slicing each need additional executions per candidate and stay unadopted; blind semantic adjudication is E-02's measurement, not a runtime policy.
- **Limits:** line coverage proves the changed code ran, not that the claim's semantics hold; the G-SEM-002 pilot (≥30 legitimate regressions, all adversarial classes, preregistered) is not run in this window; tracing covers the main thread only (threads are already blocked).
- **Reversal:** a stronger policy version supersedes this one; receipts record which policy bound them.


### D-084 — The V-02 tracer is confined to the reproduction window

- **Date/status/scope:** 2026-09-03 · active · `review/executor.py` (`_LINES_PLUGIN`, `LINES_PLUGIN_NAME`), `tests/test_executor.py`.
- **Decision:** the changed-line tracer is a pytest plugin loaded with `-p` that calls `sys.settrace` inside a `pytest_runtest_protocol` wrapper around the one collected item (setup, call, teardown) and removes it afterwards; pytest bootstrap, collection and the imports they trigger are never traced, and the guard sitecustomize carries no tracer. Only lines the test itself drives count as executed: a `def` statement or module-level assignment that runs at import time no longer binds (the V-02 fixture's binding moves from lines 1-2 to line 2).
- **Why:** owner step 0 (2026-09-03): the whole-process tracer doubled the full gate (12 → 35 min) and a line executed at import proves nothing about what the test exercised.
- **Limits:** a regression whose only changed line is a default argument or a module constant is `UNBOUND` under `changed-line-coverage.v1` even when a test observes its effect; the G-SEM-002 pilot measures how often.
- **Reversal:** none foreseen; the per-frame cost is intrinsic to `settrace`.


### D-085 — X-01: nonced, content-addressed controller/executor protocol; the host adapter is development-only

- **Date/status/scope:** 2026-09-03 · active · new `execution/{types,protocol,controller,local_adapter}.py`, `review/executor.py` (`execute_repro` is controller-side only), `review/certify.py`, `review/evidence.py` (run records carry `executor_profile`/`executor_digest`), `tests/execution/`.
- **Decision:** every run is an `ExecutionRequest` (protocol `attest.execution-protocol.v1`): a controller-minted 32-hex nonce, content-addressed inputs (guard sitecustomize, tracer plugin, test bytes by SHA-256), an argv template and an explicit, sorted, credential-free environment that name the three mounts by placeholder (`{tree}`, `{inputs}`, `{outputs}`), bounded limits and the only artifact names the controller will read back. The adapter answers with an envelope bound to the nonce and the request digest; the controller re-reads every listed artifact from the outputs directory (regular files only, ≤ 4 MiB), recomputes the digests, rejects nonce/digest/run-id/profile mismatches, undeclared or duplicate artifacts, results for never-issued or already-answered requests, executor crashes and jobs made ambiguous by a restart, and persists accepted results atomically. The in-process host runner is the `local_development_best_effort` profile; the receipt's executor identity is what the runs recorded. Guard markers and executed lines are written to the outputs mount named by `ATTEST_OUTPUTS`, so the guard and the tracer are constant, content-addressed bytes.
- **Why:** `G-SEC-001`: the executor's result channel was the same writable directory the job could reach, and the job inherited the controller's whole environment minus a name filter.
- **Limits:** origin authentication of the envelope (a controller seal) and fresh state per repeat are V-03; there is no production adapter until X-02, and a policy listing only a production profile would DEFER every run today.
- **Reversal:** a protocol v2 supersedes by version; results under v1 stay verifiable.


### D-086 — Structured generation buys text, not reasoning; a response without text is a generation failure

- **Date/status/scope:** 2026-09-03 · owner fix 1 (2026-09-03) · `review/proposer.py` (`ProviderResult.text` may be None, `content_types`, `thinking_arguments`, `no_text_reason`), `review/recovery.py` (the attempt cache carries block types), `review/executor.py` (`GenerationNoText`), `benchmark/baselines.py` (None-safe parse).
- **Decision:** every structured call sends `thinking: {"type": "disabled"}` on models that accept it (Sonnet 5, Opus 5 at default effort, the 4.x family) and, on models whose thinking is always on (Fable/Mythos), omits the parameter and asks for `effort: "low"`, so the output bound is spent on the JSON document; a response with no text block is reported as `generation_no_text (stop_reason=…, blocks=…)` — the generator raises it after the precommitted attempts and the proposer records the sample as `no_text` — with no placeholder `{}` and no "schema mismatch" ever reported for it.
- **Why:** the us-stock-helper trials (2026-09-02): sonnet-5's reproduction generation failed 8/8 with `output_tokens=3000`, `stop_reason=max_tokens` and only a thinking block, reported as "schema mismatch raw={}"; the same exhaustion hid inside the proposer's "empty" samples.
- **Limits:** the effect on proposal quality of removing reasoning is measured by the dev-slice re-run (b), not assumed; the fixed-`budget_tokens` split is not expressible on the Claude 5 API, so "separate budgets" means text-only output.
- **Reversal:** if re-run (b) certifies fewer defects than the C-05 re-run at zero control publications, restore adaptive thinking with a larger bound and re-measure.


### D-088 — The tree under test is the only import root for its own packages; a shadowed anchor is its own reason

- **Date/status/scope:** 2026-09-03 · owner fix 3 (2026-09-03) · `review/executor.py` (`project_roots`, `ATTEST_TREE_PATHS`, the guard's `sys.path` pinning, the tracer's `import-origin` artifact, `ExecutionResult.import_origins`, the shadowed-anchor DEFER in `execute_differential`).
- **Decision:** the controller discovers every directory under the tree (depth ≤ 4, hidden and build directories skipped, ≤ 32 roots) holding `pyproject.toml`/`setup.py`/`setup.cfg` and puts the tree, its `src`, each such directory and its `src` first on `PYTHONPATH` *and* in `ATTEST_TREE_PATHS`, which the guard sitecustomize re-inserts at the front of `sys.path` at startup, ahead of site-packages (a same-name editable install) and of anything the interpreter's environment prepends. After the reproduction window the tracer records every loaded module whose dotted name maps onto the anchored file but whose file is another path; a head run with such an origin DEFERs as `UNBOUND` with the origin named, never as "passed on head". The same environment goes to every adapter, so X-02's container inherits it.
- **Why:** the us-stock-helper trials: `services/*/src` packages resolved to the operator's editable install and the head tree executed 0 lines, which V-02 turned into silence with no stated cause.
- **Limits:** a module pre-imported by the interpreter itself before sitecustomize (a cached copy) cannot be evicted, only detected; discovery is by project markers, not by reading build configuration (X-02's environment bootstrap reads it).
- **Reversal:** none foreseen; the roots are additive and placeholder-relative.
- **Amendment (2026-09-03, trial A re-run):** each discovered project's `tests` directory (and the tree's) is appended to the roots, the way pytest's prepend import mode exposes it to the project's own tests, and the generator is told the nearest test module's helpers are importable by module name; the first re-run's generated test had imported `test_analysis_service` and failed on both trees for that reason alone.


### D-087 — Empty samples split into "no text returned" and "true abstention"; D-082 recomputed

- **Date/status/scope:** 2026-09-03 · owner fix 2 (2026-09-03) · `review/proposer.py` (`ProposalRun.no_text_samples`, `abstained_samples`), `review/run.py` (notes), `scripts/corpus/swebench_pilot.py` (table columns).
- **Decision:** a proposal sample counts as an abstention only when the model returned an empty findings list; a response without a text block is `no_text`, a failed sample that is neither a candidate nor silence. The pilot table reports both columns per population; control silence is counted from true abstentions alone.
- **D-082 recomputed (C-05 re-run, 64 samples, by stop reason and recovery status):** defects 20 intact, 8 `no_text`, 4 true abstentions (all four on pytest-5809); controls 2 intact, 30 true abstentions, 0 `no_text`. The eight defect-side "empties" were exhaustion, not silence — the population fix 1 addresses — and every control silence was a model-authored empty list.
- **Limits:** past runs are classified by `stop_reason == max_tokens` on an empty recovery, not by reading responses.
- **Reversal:** none foreseen; the labels are additive.


### D-089 — The reproduction generator sees signatures and the nearest test module's fixtures and helpers

- **Date/status/scope:** 2026-09-03 · owner fix 4 (2026-09-03) · `review/planner.py` (`_signatures`, `_nearest_test_module`, `_test_module_helpers`, `generation_context`; `MAX_GENERATION_CONTEXT_CHARS` 8,000 → 12,000).
- **Decision:** the generation context adds (a) every top-level function signature of the anchored module and every class header with its `__init__` (or annotated fields) and public method signatures, ≤ 60 lines, and (b) the imports, `@pytest.fixture` functions and non-test helper functions (module level or inside test classes, ≤ 8, ≤ 25 lines each) of the nearest existing test module — the first module that names the changed symbol, else the closest test file by path with `test_<stem>.py` winning ties — under an instruction to construct objects the way the project's tests do.
- **Why:** the us-stock-helper trials: six of six haiku reproductions and the diagnostic sonnet-5 attempts guessed constructor arguments, field names and package paths (`GenericFeedAdapter.__init__() missing 'config' and 'transport'`, `OHLCVBar(date=)`), while the project's own test helpers construct them correctly.
- **Limits:** the bound is on characters, not on relevance; the paid check is the trial A re-run (a), where the generated test must import the right package path and fail on head, pass on base.
- **Reversal:** if re-run (b) shows no gain in faithful reproductions, drop the helper section and keep signatures.
- **Amendment (2026-09-03, trial A runs 2-5):** the nearest test module is first the one named after the anchored file (`test_<stem>.py`, closest by path), helpers include helper classes and are ranked by how often the module's own tests use them (≤ 12), two representative tests using the most-used helpers are shown whole (≤ 40 lines each), the helper section precedes the list of test names, and the bound is 20,000 characters; trial A's generated test then constructs objects exactly as the project's tests do, and its remaining failure is a behavioural threshold (universe size), not an API guess.


### D-090 — `attest review` runs the differential stage CI runs; one verification stage, full commit ids at the entry

- **Date/status/scope:** 2026-09-03 · owner fix 5 (2026-09-03) · new `review/verification.py` (`run_verification_stage`, `CERTIFICATION_REPEATS`), `review/ci.py` (calls it), `review/run.py` (`verify`, `resolve_full_sha`, `ReviewRun.certified/published/verification_reasons`), `cli/main.py` (`review --verification-timeout`, certified findings rendered), `review/report.py` unchanged.
- **Decision:** the verification stage — differential reproduction for every regression-eligible, non-discarded candidate, one certification attempt each, the C-05 family policy and the hard cap, with the same ledger rows — is one function that CI and the local review both call. `attest review` runs it whenever the working tree is clean at a committed HEAD and `--base` resolves to a different commit; otherwise it says so ("verification skipped: … commit the change and pass --base <ref>") instead of pointing at `attest verify`, which records self-reports only. Base and head are resolved to 40-hex commit ids at the entry, so the executor, the worktrees and the certificate validator bind one identity.
- **Why:** the us-stock-helper trials: `attest review` never ran reproduction and its note sent the operator to a command that certifies nothing; short ids reached the validator as `task_invalid`.
- **Limits:** the local repository id is the literal `local`; the local policy digest is the caller-config digest, not a base-owned file.
- **Reversal:** none foreseen; CI behaviour is byte-for-byte the previous inline code.


### D-091 — Every run ends with a status: counts and reproduction failure categories, never a candidate

- **Date/status/scope:** 2026-09-03 · owner instruction 2, item 6 · new `review/status.py` (`RunStatus`, `status_from_rows`, `categorise_failure`), `review/run.py` (`ReviewRun.status`), `review/report.py`, `cli/main.py`, `review/ci.py` (`_with_run_status`).
- **Decision:** at the end of `attest review` and `attest ci` the task's ledger rows are folded into a status — change units read, candidates, eligible, reproductions attempted, certified, published, and one line per failed reproduction with its category (`no text returned`, `unfaithful test`, `environment or import failure`, `timeout`, `changed lines not executed`, `collection failure`, `other`) and a bounded reason. The CLI prints it under `run status:`; CI appends it to the final status comment (complete or deferred) as a collapsed `<details>` section. It is operational status, not a finding, so receipt-only publication does not bind it; it carries no claim, file or line of an uncertified candidate.
- **Why:** the us-stock-helper trials were silent with no visible cause; the owner requires silence to be explained.
- **Limits:** categories come from the recorded reason strings; a new failure shape lands in `other` until named.
- **Reversal:** none foreseen; the section is additive.


### D-092 — The drawer is visible to the owner in `attest stats --drawer`

- **Date/status/scope:** 2026-09-03 · owner instruction 2, item 9 · `cli/main.py` (`render_drawer`, `stats --drawer/--limit`), `tests/test_stats_drawer.py`.
- **Decision:** `attest stats --drawer` lists, newest task first, every candidate that entered the drawer without a receipt: id, file:line, votes, the category and bounded reason of its reproduction failure (or `not attempted`), any `attest feedback` label, and the claim. It reads the local ledger and candidate store only; it never enters a PR comment and is not speech.
- **Why:** the owner wants to label what the product held back; trial A's correct-but-unverified candidate was invisible outside the ledger.
- **Limits:** the newest verification reason per candidate is shown; older attempts stay in the ledger.
- **Reversal:** none foreseen; the view is read-only.


### D-093 — User-facing wording: verified / evidence / abstained / reproduction failed

- **Date/status/scope:** 2026-09-03 · owner instruction 2, item 10 · `review/report.py`, `github/presentation.py`, `README.md` (user-facing sections). Display only; no computation changed.
- **Decision:** the CLI report, the PR comments and the README's user-facing text no longer say wealth, alpha, e-value or likelihood ratio: findings are "verified" (by a reproduction receipt), the rest are "unverified candidates ranked by internal score, not evidence", silence is "abstained", and a failed reproduction is named as such. Internal logs, `DECISIONS.md`, ledger rows and bundle fields keep the statistical terms.
- **Why:** owner item 10; the statistical vocabulary was leaking into author-visible text.
- **Limits:** the `--alpha` flag name is unchanged (a configuration key, not prose).
- **Reversal:** none foreseen.


### D-094 — Prompt caching and first-token-staggered fan-out; cache writes and reads priced apart

- **Date/status/scope:** 2026-09-03 · owner instruction 3 · `review/proposer.py` (`ApiProvider.supports_cache_control`, `call_provider`, `ProviderResult.cache_*`, staggered `propose`), `review/executor.py` (`generate_repro` shares its prompt prefix), `review/budget.py` (`settle` prices `cache_creation_input_tokens` at 1.25× and `cache_read_input_tokens` at 0.1× the input price), `data/pricing.toml` (`cache_write_multiplier`, `cache_read_multiplier`), `review/recovery.py` (attempt cache carries cache usage), `review/status.py` (prompt tokens and cache reads in the run status), `benchmark/checkpoints.py` (M-03 artifacts record and price cache usage; older four-key artifacts still read).
- **Decision:** every structured call sends the system prompt and the shared prefix of the user prompt as `cache_control: ephemeral` blocks with the variable remainder after them; the K proposal samples of a unit share the whole prompt, and the reproduction generator's precommitted second attempt shares the first attempt's prompt. `propose` dispatches sample 0 alone with a streaming first-token callback and starts samples 1..K-1 only after that token (or after sample 0 finished without one), so they read the entry sample 0 wrote. No model, prompt text, bound or statistical constant changes; a provider without cache support gets the plain call.
- **Why:** the K samples of a unit are byte-identical prompts and the generator's two attempts likewise; paying full input price K times was pure surcharge.
- **Limits:** prompts under the model's cacheable minimum (1,024 tokens on Sonnet 5) silently do not cache; the benchmark's checkpointed provider forwards nothing cache-related to its inner provider, so M-03 studies stay cold until that wrapper opts in.
- **Reversal:** remove the `cache_control` blocks; the staggered dispatch is harmless without them.


### D-095 — `package-cache`: an experimental context strategy, default unchanged

- **Date/status/scope:** 2026-09-03 · owner instruction 4 · comparison only · `review/config.py` (`context_strategy`, `CONTEXT_STRATEGIES`), `review/planner.py` (`package_block`), `review/proposer.py` (`shared_system` block ahead of the role instruction, in the attempt identity), `review/run.py`, `review/executor.py`, `review/verification.py`, `scripts/corpus/swebench_pilot.py` (`--context-strategy`, `--results-suffix`).
- **Decision:** with `context_strategy = "package-cache"` the anchored module's whole package (anchored file first, then the package's sources, then the project's `tests` directory; ≤ 120,000 characters, ≤ 40,000 per file) is sent as the first system block with its own `cache_control` breakpoint, byte-identical for every proposal sample of the PR, every reproduction generation and its repair, so the block is written once and read afterwards; the role instruction is the second system block. `r01` (the planner's per-unit context) stays the default; switching is the owner's decision after the comparison.
- **Why:** owner instruction 4: measure whether one large cached block beats retrieved context on certified count, no-text count, cost per PR and cache-read share.
- **Limits:** the block is chosen from the first unit's first changed file for proposals and from the anchored file for generation, so a PR spanning packages shares only the first; prompts below the cacheable minimum do not cache.
- **Reversal:** delete the strategy value; the default path is untouched.
- **Result (2026-09-03, dev slice, 8 PRs per arm):** r01 certified 4 at $0.0608 per PR, package-cache certified 2 at $0.2192 per PR (3.6×), no-text 0 in both, cache-read share 78% / 75% of proposal prompt tokens; the recommendation is to keep `r01` ([`acceptance/2026-09-03-r01-cache-variant.md`](docs/acceptance/2026-09-03-r01-cache-variant.md)); the switch remains the owner's.


### D-096 — X-02: `linux-container-v1`, the production isolation backend, with the environment bootstrap

- **Date/status/scope:** 2026-09-03 · owner-selected default (mainline §5 B, 2026-09-02) · new `execution/container_adapter.py`, `execution/container_images.py`, `execution/backends.py`; `review/executor.py` (guard marks network and out-of-work-dir write attempts; `ATTEST_WRITABLE`, `{scratch}`), `review/verification.py` (backend per task, `executor_backend` ledger row, fail-closed DEFER), `review/certify.py` (policy lists the backend in use), `review/status.py` (`environment bootstrap failed`), `tests/execution/test_linux_isolation.py` (real containers), `tests/execution/test_backends.py`, `tests/conftest.py` (the suite runs on the host adapter unless marked `real_backend`).
- **Decision:** every reproduction of a production task (`attest ci`, the pilot driver) runs in a fresh OCI container: `--network none`, `--read-only`, uid 65534, `--cap-drop ALL`, `no-new-privileges`, `--pids-limit`, `--ulimit nproc=0:0` (so the guard's kernel-containment check holds), cpu and memory limits, tmpfs scratch and `/tmp`, the tree and the inputs mounted read-only, the outputs directory the only writable host path, `env -i` with exactly the request environment plus PATH/HOME/TMPDIR inside the image; the job invokes the image's `python3`, and the interpreter identity names the image. The image is built before any head code runs from the tree's manifests (`pyproject.toml`/`setup.py`/`setup.cfg`/`requirements*.txt`, every project root under `services/*` and friends, depth ≤ 4) on `python:<version>-slim` chosen by the classifier rule, tagged by the digest of the interpreter and the manifests, and its digest is part of the executor digest in every run record and receipt. A bootstrap that fails DEFERs every candidate with `environment bootstrap failed: …` (item 8) and the run status names it. The guard now marks a network attempt or a write outside the outputs/scratch/reproduction directories and such a run DEFERs, whatever the OS then denies. Production never falls back to the host adapter; a local `attest review` does, and says so.
- **RED (real containers, `tests/execution/test_linux_isolation.py`):** the planted regression fails 3/3 on head and passes 3/3 on base inside the container with the changed line executed; a reproduction that reads the controller's canary sees nothing; a socket connect and a write to the tree, `/etc` or the inputs mount fail and the run is marked; uid ≠ 0, `CapEff` 0, `RLIMIT_NPROC` (0,0).
- **Limits:** Docker Desktop on the operator's macOS is the tested platform (a Linux VM daemon, not rootless mode); GitHub Actions Linux runners are the declared production platform and `G-SEC-002`'s full red-team matrix (fork bombs, `/proc` discovery, native helpers, forged results under a hostile job) is not yet exercised there; the language guard remains the marker, the kernel is the boundary.
- **Reversal:** the profile string is versioned; a `linux-container-v2` (rootless, seccomp/landlock, cgroup v2 assertions) supersedes it and receipts say which one ran.
- **Amendment (2026-09-03, E-01):** the image interpreter also honours `requires-python = ">=3.X"` as a lower bound (the natural-null corpus declares only that, so the era fallback 3.9 could not install it and 25 eligible candidates on 5 commits DEFERred as `environment bootstrap failed`); those five commits are re-run.
- **Amendment (2026-09-03, held-out, `874e270`):** a setuptools_scm project is built with the version its committed `_version.py` carries (`SETUPTOOLS_SCM_PRETEND_VERSION`; the build context has no `.git`), only the tree root's own install is required and nested projects (`examples/`, docs helpers, sibling services) install best-effort with the failure kept in the build log. 45 held-out reproductions on 18 pytest/pylint cases had DEFERred as `environment bootstrap failed`; they are re-run only when the owner lifts the stop.


### D-097 — V-03: fresh writable state per run, a controller seal on every bundle, the offline verifier on `attest verify --bundle`

- **Date/status/scope:** 2026-09-03 · active · new `execution/provenance.py` (HMAC-SHA256 seal, `.attest/controller.key` created with mode 0600 outside every mount), `execution/controller.py` (`DispatchOutcome.fresh_state`/`stale_entries`: the outputs directory is created empty for every run and anything found there beforehand is named and removed), `review/executor.py` (`ExecutionResult.fresh_state`), `review/evidence.py` (run records carry `fresh_state`; `verify_bundle(key=…, require_seal=…)` recomputes the manifest digest and verifies `seal.json`), `review/certify.py` (every accepted bundle is sealed), `cli/main.py` (`attest verify --bundle DIR [--key FILE] [--require-seal]`), `tests/execution/test_fresh_repeats.py`.
- **Decision:** a run record whose `fresh_state` is not true rejects offline (the RED); the seal binds the bundle manifest digest and the receipt's provenance digest under a key the executor never sees (the container mounts the tree, inputs and outputs only; the key lives beside the ledger), so a bundle rewritten by job code, a seal copied from another bundle, or a seal made with another key rejects; without the key the verifier reports the seal as unchecked and rejects when it is required. The X-01 controller already persists each run atomically (artifacts first, `result.json` last) and rejects results for jobs left dispatched across a restart.
- **Why:** `G-SEM-003`: repeats shared writable state and nothing authenticated the controller's authorship of a bundle.
- **Limits:** HMAC with a repository-local key authenticates the controller to itself and to whoever holds the key (the operator, CI secrets); a public-key seal with a platform trust root is the next version. The head and base worktrees are shared by the three repeats; the guard marks writes into them and pytest's own writes are disabled, so state cannot leak between repeats through the tree, but the tree is not recreated per repeat.
- **Reversal:** the seal schema is versioned; unsealed historical bundles still verify structurally.


### D-098 — A verified finding is presented as its test

- **Date/status/scope:** 2026-09-03 · owner instruction 2, item 7 · new `review/finding_evidence.py` (`FindingEvidence`, `evidence_from_bundle`, `render_markdown`, `render_text`), `github/presentation.py` (`render_complete`/`inline_comments` take the evidence), `review/report.py` (CLI block), `review/verification.py` (`VerificationStage.evidence` from each accepted bundle), `review/ci.py`, `review/run.py`, `cli/main.py`.
- **Decision:** every published finding, inline and in the summary comment, carries the exact reproduction bytes as a fenced test, the one-line command with the node id (`pytest -q test_repro.py::…`), the head/base run summaries, the full logs in a collapsed section, the evidence bundle path and the offline command `attest verify --bundle <path> --require-seal`; the CLI prints the same block. Everything is read from the sealed bundle the certification wrote; nothing is re-executed for presentation.
- **Why:** owner item 7: an author must be able to run what the product claims without trusting the product.
- **RED:** the test and command copied out of the PR comment fail on the head tree and pass on the base tree (`tests/test_ci_flow.py::test_verified_finding_comment_carries_a_test_and_command_that_reproduce_on_both_trees`).
- **Limits:** logs are bounded to 6,000 characters per run; the command assumes the test is saved at the repository root the way the executor runs it.
- **Reversal:** none foreseen; the block is additive.


### D-099 — L-01, the parts that need no owner decision: quickstart, support matrix, failure copy, kill switch, rollback, privacy draft

- **Date/status/scope:** 2026-09-03 · active · new `docs/operations/{quickstart,support-matrix,failure-modes,kill-switch-and-rollback,privacy-and-retention}.md`; `review/config.py` (`enabled`, `DISABLED_REASON`), `review/ci.py` (defer before any model call when the base policy is disabled), `review/run.py` (the local review honours it), `tests/test_ci_flow.py`.
- **Decision:** the kill switch is one base-owned key, `enabled = false` in `.attest.toml`; CI reads it at the merge-base, so a pull request's head cannot re-enable it (the RED: base disabled, head says enabled, zero provider calls, an explicit final status). Rollback is the workflow's `uses:` ref; schemas are versioned so older readers reject rather than misread. The quickstart is written to be executed verbatim from a fresh clone to a verified comment or an explained silence; the support matrix and failure copy name every unsupported shape and the literal text the author sees. Publication, the pilot repository and the retention defaults stay with the owner (mainline §5 D).
- **Why:** mainline §1 item 6 and the L-01 exit list; the owner asked for the owner-free parts now.
- **Limits:** the quickstart is not yet executed on an outside repository (that execution is the L-01 RED and needs the owner's pilot repository); the drills of the L-01 work order (credential revoked, GitHub outage, budget exhaustion, superseded PR) are covered by existing tests individually, not by a `scripts/release/drill.py` yet.
- **Reversal:** none; documentation and one policy key.

### D-100 — The natural null published once: a receipt-backed intended behavior change (`RISK-INTENT-01`); every paid run stopped

- **Date/status/scope:** 2026-09-03 · observed, root-caused, owner decision pending · [`docs/acceptance/2026-09-03-e01-natural-null.md`](docs/acceptance/2026-09-03-e01-natural-null.md); roadmap §14 row `RISK-INTENT-01`.
- **Decision:** E-01 (20 real commits, K = 4, $0.25 per PR, containers) published 1/20: on `3a32c92` (a guard that rejects served text containing a banned verb) the receipt is valid — head FAIL 3/3, base PASS 3/3, changed lines executed, sealed — but the published words ("false positive on legitimate copy") claim more than the receipt proves ("head rejects an input base accepted"); the rejected phrase contains the banned verb verbatim and was fabricated by the generator. Per the owner's stop rule every paid run stopped (held-out at 68/69, the 18 bootstrap-failed cases not re-run).
- **Why:** a validation-tightening commit on an existing definition is regression-eligible (D-063) and every input it newly rejects yields `head_fail_base_pass`; the regression-only differential V cannot tell an intended rejection from a regression (D-078's limit, now observed on a natural commit).
- **Owner choice (not implemented):** (a) a `new_rejection` result class — head failure is an exception raised from a changed line — that publishes only when the rejected input is a literal present in the reviewed tree, else drawer plus a question to the author; or (b) publish such receipts under a distinct evidence class worded as exactly what they prove. Either changes publication semantics (`INV-CERT-001`), so neither ships without the owner.
- **Limits:** n = 20 commits, one repository, one author; 25 of 40 verified candidates were cut by the per-PR budget, so the observed rate is a lower bound at higher budgets.
- **Reversal:** the register row is removed if the owner rules such receipts publishable as-is.

### D-101 — E-02 held-out: one pass, 0 control false publications on 39, recall bounded by the environment; the bound stays at 3,200

- **Date/status/scope:** 2026-09-03 · measured, incomplete by the stop rule · [`docs/acceptance/2026-09-03-e02-heldout.md`](docs/acceptance/2026-09-03-e02-heldout.md), `scripts/corpus/heldout_run.py` (`--only`, `--defects-only`), `scripts/corpus/binding_pilot.py`.
- **Decision:** the held-out numbers replace the dev-slice numbers in the README (29 defects, 39 controls, 2026-09-03): certified 7 candidates on 5/29 defects, 0/39 control false publications, 0/280 truncated samples, 0 diff-boundary hits — the proposal bound stays at 3,200 (owner answer 3); cache reads ≈ 75 % of input tokens; $1.7899. 45 of 50 silent defect reproductions were `environment bootstrap failed` on 18 pytest/pylint cases (fixed in `874e270`, D-096 amendment); on the 11 defects that built, certified on 5/11.
- **G-SEM-002 pilot:** 9 generated tests plus 18 constructed adversarial tests through the container: 18/18 adversarial rejected (9 unbound, 9 unfaithful), 5/5 real reproductions bound, 0 false verdicts; a mechanism check, not the preregistered sample.
- **Why:** mainline §2 step 13; the dev slice is a development record from now on.
- **Limits:** one pass, 68/69 cases, 18 defects never executed, reverse-fix corpus with synthetic controls.
- **Reversal:** the re-run of the 18 cases after the owner lifts the stop supersedes the defect-side numbers.
- **Amendment (2026-09-03, second window):** recounted from the result files, the bootstrap-failed defects are 19 (15 pytest + 4 pylint), not 18; 10 environments built and the built-environment figure is certified on 5/10, not 5/11 (erratum in the held-out report). The supplementary run covers the 19.
- **Supplementary run (owner decision 2, 2026-09-03; product code `5fc03fa`):** on the 19 defects, 50 candidates, 45 eligible, 12 certified, 11 published, certified on 10/19, 0/19 bootstrap failures, 0 truncation, 0 boundary hits, no behavior-change classification; silence: 24 unfaithful reproductions, 2 unbound (one the D-104 false positive), 2 collection failures, 2 new-code, 1 budget cut. Tabulated apart in the held-out report; never merged into the one-time table (different code, not pre-registered). Spend $0.8913, over the $0.60 reservation by $0.2913 (driver had no cumulative cap; `--cap` added).

### D-102 — The intent discriminator: a `raise` on a changed line is a behavior change, published only with a base-tree witness (owner decision 1 on D-100)

- **Date/status/scope:** 2026-09-03 · active · `certification/intent.py` (pure `IntentObservation`, `intent_verdict`, `evidence_class_for`; policy `attest.intent.new-rejection.v1`), `review/intent.py` (raise origins, statement kinds, test literals, base-tree witnesses), `review/executor.py` (the tracer records the first anchored frame each exception passes through; `execute_differential` classifies after binding), `certify.py`/`evidence.py` (receipt fields `intent_policy_version`/`intent_digest`, `intent.json`, offline re-judgement; receipt schema **v4**), `certification/{types,policy,validate}.py` (`intent_policy_version`, evidence class `behavior_change`, `intent_policy_mismatch`/`intent_digest_invalid`), `status.py` (category `behavior change, intent unknown`; the status shows only the label), `finding_evidence.py`/`presentation.py`/`report.py` (behavior-change wording), `cli` (`attest stats` accounts behavior changes apart), ledger rows carry `evidence_class` and the observation; `scripts/corpus/intent_replay.py`; report [`docs/acceptance/2026-09-03-d102-intent-replay.md`](docs/acceptance/2026-09-03-d102-intent-replay.md).
- **Decision:** when every head run raised an exception from a `raise`/`assert` statement on a changed line of the anchored file, the differential is a **behavior change** (head rejects an input the base accepted), not a regression. Its rejected inputs are the generated test's string literals that reached the raising frame. The receipt is accepted and may publish — as a `behavior_change` receipt, worded as exactly what it proves and asking the author to confirm — only when every identified input occurs verbatim in the **base** tree's tests, fixtures, examples or documentation; otherwise the differential DEFERs into the drawer with the label "behavior change confirmed, intent unknown" (行为变化已证实，意图未知) and buys nothing. Behavior changes are accounted as their own class in the run status, the ledger and `attest stats`. The offline verifier recomputes the observation digest and re-judges the verdict. Regression receipts under the same policy bind an observation that says "not a new rejection".
- **Why:** owner decision 1 of 2026-09-03 on D-100 (`RISK-INTENT-01`): the regression-only kernel published a valid receipt for an intended rejection on E-01; the owner chose the structural discriminator with a base-tree witness over exact-wording publication.
- **RED:** the `3a32c92` receipt goes to the drawer and the five held-out regressions still publish — on the real bundles through the container (`intent_replay.py`: 1 deferred `behavior_change`, 7/7 `regression_reproduced`) and in the suite: `tests/certification/test_intent.py`, `tests/test_intent_observer.py`, `tests/test_executor.py::test_a_new_rejection_*` / `::test_a_regression_and_a_crash_*`, `tests/test_ci_flow.py::test_a_new_rejection_*` (no review, labelled status without the candidate's file, line or input; the witnessed variant publishes with the behavior-change wording, verifies offline, and a digest-consistent bundle that lost its witnesses is rejected).
- **Limits:** a witness is verbatim presence in a witness file (by path: `tests`, `test`, `testing`, `fixtures`, `testdata`, `examples`, `docs`; by name: `test_*.py`, `*_test.py`, `conftest.py`, `*.md`, `*.rst`, `*.txt`, `README*`; docstrings are not scanned); presence as a negative example is not distinguished, mitigated by requiring every identified input to be witnessed; only string literals are identified, so a rejection of a number or a constructed value stays in the drawer; a rejection raised by an unchanged helper called from a changed line is still a regression; v3 bundles verify only with the code that wrote them (INV-VERSION-001, as V-02 did).
- **Reversal:** if E-04 shows the drawer swallowing real regressions on natural commits, widen the witness scope (docstrings, the head tree's pre-existing tests) as a new intent policy version — never by publishing an unwitnessed behavior change.
- **Amendment after the D-049 review pass (2026-09-03, same window; reproduced findings F1-F5, all fixed with REDs):** (F1) the tracer now records up to 256 distinct origins with exact-duplicate suppression and a `truncated` flag; a truncated record DEFERs instead of falling through to "regression". (F2) an anchored file the host cannot parse DEFERs when any origin lies on a changed line, instead of classifying every raise as a crash. (F3) a rejected input is a test literal *equal* to a string local of the raising frame or *quoted* verbatim in the exception message — substring presence is no longer enough — dictionary keys and subscripts are not literals, and a witness must contain the literal quoted (`'…'`, `"…"`, `` `…` ``) in a test module, documentation, or a data file inside a test/fixture/example/doc directory; `requirements.txt`-style files are not witnesses. (F4) the tracer records whether each exception escaped the anchored code (a frame that runs a line after the event handled it); only an *escaped* raise on a changed line whose exception type matches the JUnit failure — or a test-level failure (assertion, `pytest.fail`) that the escaped raise can have caused — is the rejection, so a raise the changed code handles itself no longer decides the class. (F5) surrogates in messages and locals are replaced before the artifact is written and the hook never raises. On the real bundles the tightened rule keeps every verdict: `3a32c92` DEFERs (now "no rejected input could be identified" — its phrase was f-string-built), 7/7 held-out candidates stay regressions (`intent-replay-v2.json`).

### D-103 — E-04 prospective shadow: the collector, its fail-closed preflight and protocol v1 on the owner's repositories

- **Date/status/scope:** 2026-09-03 · active, stratum v1 run ([report](docs/acceptance/2026-09-03-e04-prospective-v1.md)) · `src/attest/benchmark/prospective.py`, `tests/benchmark/test_prospective.py`, `scripts/corpus/prospective_shadow.py`, `benchmarks/studies/e04-prospective-v1/{protocol.md,preregistration.json,authorization.json,preregistration.sha256}` (frozen `2026-09-02T21:43:17+00:00`, digest `af8aff9c…`), `sample.jsonl`, `trials.jsonl`, `report.json`.
- **Decision:** the shadow is the local review path itself (`run_review`), which owns no GitHub client and shares `run_verification_stage` with CI, so "what CI would have published" is read from the same publication-policy row — checked by a zero-cost identity fixture rather than a second code path. A unit is one non-merge commit pushed after the freeze to a repository the authorization names (mainline §3: the owner's GitHub account), reviewed head = commit, base = parent, K = 4, $0.25, containers. The sample records stratum, inclusion probability and the seeded silent-audit draw before any outcome; the preflight refuses (each with its own reason) a missing paid opt-in, a missing/late/narrow authorization, an unfrozen or edited protocol, an inclusion probability outside (0, 1], a sample recorded before the freeze or after an outcome, and insufficient cap headroom. The study bundle carries counts and candidate ids, never a claim, file or line. Truth is product-blind adjudication into `adjudication.jsonl`; unknown truth stays `unresolved`; precision and eligible detection are `INSUFFICIENT` until every shadow finding and every drawn silent unit is adjudicated and the preregistered minimum (100/100) is met. The behavior-change drawer rate (D-102) is a named metric.
- **Why:** mainline §2 step 15 and the E-04 work order; the population the owner authorized without asking is the only prospective traffic available, and the full `G-SHADOW-001` n (500 PRs, 30 repositories) is a multi-window study — stratum v1 fixes the mechanism and the protocol so later strata add units, not rules.
- **RED:** `tests/benchmark/test_prospective.py` (every preflight refusal by reason; the draw recorded before outcomes and reproducible; the report never treating unknown truth as clean; the collector publishing exactly what CI publishes with no GitHub connection).
- **Result, stratum v1:** 2 units (Attest `19920c6`, `5fc03fa`), 22 candidates, 0 eligible (10 anchored in Markdown, 12 in a new file), 0 reproductions, 0 shadow findings, $0.1694; on the 23-file commit the $0.25 per-unit budget funded the K = 4 samples of the first of 13 change units (the documentation unit, by path order) — budget-bound silence, the E-01 mechanism again; the per-unit budget and the unit order are the owner's next question (§5 C).
- **Limits:** stratum v1's population is the owner's four Python repositories and its traffic in this window is Attest's own commits (the other repositories had no push after the freeze); adjudication needs a product-blind reviewer the agent cannot be, so v1 reports safety counts and the drawer rate only; the silent-audit probability is 1.0 (uniform adjudication sample) because n is small.
- **Reversal:** a new stratum for any code, model, prompt or population change; never a re-run or exclusion inside a stratum.
- **Amendment (owner answers, 2026-09-03 second window):** question 1 answered *order source first, keep $0.25* — the planner now ranks `.py` paths before every other path within a plan, and a budget-bound proposal records `units_planned` / `units_read` / `budget_limited` in the ledger so the silence receipt reads `read N of M units, budget-limited` instead of reporting the planned count as if it had been read (REDs: `test_source_units_are_planned_before_documentation_units`, `test_a_budget_limited_run_says_how_many_units_it_read_of_how_many`). Because this is a product-code change, the next prospective units run as **stratum v2**; v1's two units stand as recorded. Question 3 answered *accept `INSUFFICIENT`*: unadjudicated units stay `unresolved`, precision and eligible detection stay `INSUFFICIENT`, and this blocks nothing.

### D-104 — A shadow is a module of a dotted name the anchored file answers to, not a basename match

- **Date/status/scope:** 2026-09-03 · active · the reproduction tracer plugin in `review/executor.py` (`_expected_module_names`, `_record_import_origin`); RED `tests/test_executor.py::test_a_stdlib_module_sharing_the_anchored_basename_is_not_a_shadow`.
- **Decision:** owner fix 3's shadow check compared every loaded module's dotted name against the *tail* of the anchored path, so the stdlib `logging` package was reported as a shadow of pytest's `src/_pytest/logging.py` and the supplementary held-out run (code `5fc03fa`) DEFERred `pytest-dev__pytest-10051` as UNBOUND ("imported from outside the head tree (/usr/local/lib/python3.10/logging/__init__.py)"). The check now derives the dotted names the anchored file answers to from the tree's import roots (`ATTEST_TREE_PATHS`) and flags only a module of one of those names loaded from another file; the basename rule remains the fallback when no root contains the anchored file.
- **Why/limits:** the false positive turned a real regression into silence; the existing fix-3 REDs (installed same-name copy, pre-imported copy) still pass. Cases run under `5fc03fa` keep their recorded verdict; re-running the affected one is a separate reservation.

### D-105 — The ≥90% coverage floor, property/mutation tests and independent review bind the kernel only

- **Date/status/scope:** 2026-09-03 · active, owner-directed · `docs/acceptance/evolution-gates.md` (`G-CODE-001`, `G-CODE-002`), `docs/implementation/agent-work-orders.md` §1 step 9, §3.1, §5, `AGENTS.md` §11, §13, `pyproject.toml` coverage include.
- **Decision:** `fail_under = 90` now covers `attest.certification` and `attest.execution`; `attest.review`, `attest.cli`, `attest.github`, `attest.benchmark`, `attest.core` and `attest.deconstruct` print coverage as an observation with no threshold. `G-CODE-002` (property/mutation tests) applies to the kernel and security paths only. Independent review is required only for a change that touches them; every other order self-checks once. "All adjacent tests pass" is deleted as a pass condition. Unchanged: one named RED per behaviour change (D-058), one `pytest` / `ruff check .` / `mypy src/attest` run at the end of each order, and no test may depend on the network, a secret or the clock.
- **Why:** the mainline has reached L-01; a peripheral coverage floor now costs more than it buys, while the kernel gates keep the safety properties they were written for.
- **Limits/reversal:** no existing test is deleted; if a peripheral module produces a false publication, restore its floor as a new decision rather than by silently re-widening the gate.

### D-106 — L-01: the pilot ref, the pilot itself, and what the pilot did not prove

- **Date/status/scope:** 2026-09-03 · active · tag `v0.1.0-pilot.1` (`eedb656`), `docs/operations/{install-ref,base-policy,quickstart,failure-modes}.md`, `examples/pull-request.yml`, `src/attest/cli/main.py`; report [`docs/acceptance/2026-09-03-l01-private-pilot.md`](docs/acceptance/2026-09-03-l01-private-pilot.md).
- **Decision:** the install ref is an annotated, never-moved tag, not a branch; the example workflow and the quickstart both pin it. The base branch owns the review policy and the reference lists every key with its factory default and what a repository setting can never do. The private pilot is the quickstart executed literally from a fresh clone of Attest at the tag against a fresh clone of `IcantFind-a-username/us-stock-helper` (owner decision D), six commits, local review only, no GitHub write.
- **Result:** six documented silences, 0 publications, $0.2772. One candidate reached the containerised reproduction stage (`linux-container-v1`, image built from the project's own manifests) and DEFERred as an unfaithful test. Four wiring problems were found and fixed, two with REDs: a mutable action ref in the example workflow, CLI help that never named the offline verifier, `python` vs `python3` in step 1, and a quickstart that under-described the local output.
- **Limits:** the receipt-backed branch of the step-16 exit was **not** exercised — none of the six commits regressed against its own parent — so this pilot proves the wiring, not recall; no GitHub write path ran; the kill switch and rollback were not exercised on the pilot repository. `G-RELEASE-001` still needs the offline drill script and owner approval of the privacy/retention defaults.
- **Reversal:** a new pilot ref is a new tag, never a moved one; the rollback for a bad review at this ref is the kill switch (`enabled = false` on the base branch), because no earlier ref clears the trust bar.

### D-107 — The privacy and retention defaults are approved; the provider's own retention is out of scope

- **Date/status/scope:** 2026-09-03 · active, owner-directed · `docs/operations/privacy-and-retention.md`.
- **Decision:** the document is approved as written and is no longer a draft: evidence bundles of published findings are kept indefinitely (they are the certificate), reproduction work directories are removed after the run, the attempt cache and the ledger are the operator's to rotate or delete, and the controller key is rotated by deleting `.attest/controller.key`. Added at the owner's instruction: **what the model provider does with what it receives is governed by that provider's API policy, not by `attest`** — provider-side retention of prompts and completions is outside this tool's control and outside the guarantees the document makes, and the operator should read their provider's API terms.
- **Why:** owner decision 1 of 2026-09-03 (fourth window). `G-RELEASE-001` could not count the privacy/retention item while the heading said "for the owner's approval"; and a retention document that is silent about the one party the tool actually sends source to would overclaim.
- **Limits:** the document describes the defaults this code ships, not a contract with any provider. `attest` cannot enforce, verify or report provider-side retention.
- **Reversal:** a change to any retention default is a new decision, not an edit to this document.

### D-108 — The Action runs on a GitHub-hosted runner, for this repository's own pull requests only

- **Date/status/scope:** 2026-09-03 · active, owner-directed · `.github/workflows/pull-request.yml`; RED `tests/test_action_entrypoint.py::test_this_repository_workflow_runs_only_for_same_repository_branches`; report [`docs/acceptance/2026-09-03-first-runner-review.md`](docs/acceptance/2026-09-03-first-runner-review.md).
- **Decision:** this repository reviews its own pull requests with `uses: ./` — the action as it stands in the pull request — because the one place where reviewing with the code under review is the point is here; an outside repository still pins the immutable ref, and `examples/pull-request.yml` and its test are unchanged. The event is `pull_request`, never `pull_request_target`. The job carries `if: github.event.pull_request.head.repo.full_name == github.repository`, so a fork pull request never starts a step whose environment holds `ANTHROPIC_API_KEY`; `scripts/action-gate.sh` refuses one a second time, inside the action.
- **Why:** owner decision 3 of 2026-09-03. Until this landed the repository had no `.github/workflows/` at all: the action this product ships had never been executed by GitHub, and every gate in the project had only ever run on the owner's machine.
- **Result:** one run on one throwaway branch carrying one planted regression — 76 s, **$0.0301**, backend **`linux-container-v1`** with the image built on the runner, 1 candidate, 1 eligible (`definition _normal_path exists at the merge-base`), 1 reproduction, **0 certified**, DEFER `unfaithful generated test: fails on base as well`, one status comment posted. The pull request was closed unmerged and the branch deleted; the workflow file stays. It found one product defect, fixed in `d62bcd6`.
- **Limits:** the wiring is proved, **recall is not** — a receipt-backed comment has still never been produced on a runner. The fork path was exercised only in the affirmative: no fork pull request was opened, so both guards were watched admitting, never refusing.
- **Reversal:** delete the workflow file; nothing else is stateful on the GitHub side. A second run costs another review, so the workflow now bills every pull request opened against this repository — that is the intended cost and the owner can turn it off with the same one-line kill switch every consuming repository has.

### D-109 — The receipt-bearing pilot: eligible, reproduced, and still no receipt

- **Date/status/scope:** 2026-09-03 · active, owner-directed · report [`docs/acceptance/2026-09-03-l01-receipt-pilot.md`](docs/acceptance/2026-09-03-l01-receipt-pilot.md); `.attest/pilot/receipts/` (gitignored worktrees and outputs).
- **Decision:** the three commits were selected mechanically, not by reading their fixes: for every `fix:` commit in `us-stock-helper`, the lines it removes were blamed at its parent to find the introducing commit, keeping only pairs whose introducing commit **modified a pre-existing Python file** — the only shape D-102's regression-only kernel can certify. The three are `d7be758` (repaired by `2d4a0d8`), `e17c686` (repaired by `8ed7811`) and `20c7260` (repaired by `1906530`).
- **Result:** **no receipt.** `d7be758`: read 2 of 4 units (budget-limited), 12 candidates, 11 eligible, 11 reproductions attempted, 0 certified, $0.1741. `e17c686`: 1 candidate, 1 eligible, 1 reproduction, 0 certified, $0.0731. `20c7260`: **stopped unrun** — after two reviews $0.0528 of the owner's $0.30 remained, which cannot fund a review at the default $0.25 budget. Both completed reviews ran through `linux-container-v1` and built no image (the repository's manifest set is stable across these commits, so all three trees address one image that was already on the host).
- **Why nothing certified:** three of three executed reproductions reported `pytest passed on head in 3/3 runs; base not executed` — the generated test does not fail on the buggy commit, so the differential never reaches the base side. The other nine never generated a test: each stopped at `BudgetExceeded … projected total $0.263 exceeds budget $0.25` on its second attempt, because the proposal stage had already spent the per-review budget on 12 candidates from a 210-line change. **Budget lost to breadth, not to difficulty.**
- **Limits:** the receipt-backed branch of the L-01 step-16 exit is now unexercised across nine reviewed commits of this repository. The D-105 unit ordering worked — the two unreached units were 1,832-line JSON fixtures and the silence named them — so this is not the E-01 mechanism repeating. Half the proposal samples abstained outright, which is the null behaviour working.
- **Amendment 2026-09-03 (D-113):** the selection rule in this entry is wrong. `d7be758` carries no regression against its parent — the repairing commit's own test fails identically on both sides and the defect came from `e17c686` two commits earlier — so two of the three reproductions counted here were correct silences, not generation failures. The "six of six" sentence below is superseded by [the classification report](docs/acceptance/2026-09-03-generation-classification.md): four of the six ran against pairs with nothing to find or nothing proposed, and the two that remain are model-sensitive.
- **Reversal/next:** the concentration to attack is **the faithfulness of the generated reproduction**. Every reproduction that has ever executed on real traffic — six of six across four populations — was rejected as unfaithful, by three distinct reasons: three `pytest passed on head in 3/3 runs` (this pilot), two `fails on base as well` (the runner review, `pytest-10051`) and one `references a symbol absent from head` (the 2026-09-03c pilot). n is small; what matters is that no reproduction has ever cleared the stage. That is a measurement question, not a budget one, and it precedes any further spend on pilots.

### D-110 — An image build is capped by the verification budget it runs under, and a warm image is found by id

- **Date/status/scope:** 2026-09-03 · active, owner-directed (decision 2 of 2026-09-03d) · `src/attest/execution/container_images.py`, `container_adapter.py`, `backends.py`, `src/attest/review/verification.py`; REDs `tests/execution/test_backends.py::test_an_image_build_cannot_outlast_the_verification_budget_it_runs_under` and `::test_a_reusable_image_is_found_and_addressed_by_id_not_by_tag`.
- **Decision:** the build timeout is `min(IMAGE_BUILD_TIMEOUT_S, remaining verification budget)`, threaded from `run_verification_stage` (which owns the deadline) through `select_backend` into `ensure_image`; an exhausted budget never reaches the daemon and fails closed with `no verification budget remained for an image build`. Image reuse is decided by `docker images --no-trunc --quiet <tag>` (falling back to the old `image inspect`), and the **id** it returns is what the run is addressed by — the tag stays only as the cache key and the human-readable name in `BackendSelection.reason`.
- **Why:** the 1800 s ceiling is three times the 600 s shared deadline and `select_backend` runs before the first deadline check, so a 601–1800 s build "succeeded" and then DEFERred every candidate with `shared verification deadline exceeded` — the wrong category, after up to 30 minutes of runner time. Separately, `docker image inspect <name:tag>` was observed answering *No such image* for tags the same daemon listed and resolved by id, which is how a 30-minute rebuild of an existing image came to be started at all.
- **Limits:** the 1800 s ceiling itself is unchanged; this only lowers the *effective* cap when the caller has less budget. Addressing by id changes the environment identity string bound into new run records (`python3@sha256:…` rather than `python3@attest-repro:…`); old bundles carry their own strings and verify unchanged.
- **Reversal:** pass `remaining_s=None` (the default) to restore the flat ceiling; drop `image_id` from `resolve_image` to restore tag-only lookup.

### D-111 — Discovery may spend at most 60% of a review's budget, and reproductions are bought best-first

- **Date/status/scope:** 2026-09-03 · active, owner-directed (decision 3 of 2026-09-03d) · `src/attest/review/budget.py`, `run.py`, `verification.py`; REDs `tests/test_budget_ledger.py::test_discovery_cannot_spend_more_than_its_share_of_the_review_budget` and `tests/test_ci_flow.py::test_reproductions_are_bought_in_ranking_order`.
- **Decision:** `PROPOSAL_SHARE = 0.6`. `Budget.stage(label, share)` bounds every reservation made inside the block to that share of the limit, and `run_review` wraps the whole proposal stage — every unit, sample and schema repair — in it. Verification is not capped: it may use whatever discovery left. Reproductions are then attempted in ranking order, `(-wealth, finding_id)` — the key C-05 already uses for publication.
- **Why:** on `d7be758` twelve candidates from a 210-line change consumed the $0.25 review budget in discovery, and nine of eleven eligible reproductions stopped at `BudgetExceeded … projected total $0.263` on their *second* generation attempt. Breadth starved verification, and the store order the loop walked (dedup's `(file, line, claim)`) carries no ranking, so the ones it did buy were not the best ones.
- **Limits:** the share binds *reservations*, which are deliberate over-estimates (`max_output_tokens` at full price). At the $0.25 default with K=4 the share is $0.15 against a $0.128 floor for four 3,200-token samples, so a large first unit can now DEFER a review that would previously have proposed; the reason names the share and the fix is a larger `--budget`. The share is a budget-allocation default, not a factory statistic (§16), and no threshold, alpha or gate moved.
- **Reversal:** drop the `with budget.stage(...)` block to restore one flat ceiling; drop the sort in `verification.py` to restore store order.
- **Amendment, same day — the share binds breadth, not the first unit.** As first written the share wrapped the whole proposal stage, and the release drill caught what that means: at the shipped defaults (K=5, `budget_usd` 0.25) five samples reserve `5 × 3200 × $10/Mtok = $0.16` at the proposal token bound *before a single character of diff is priced*, against a $0.15 share — so **every review at the product's own defaults DEFERred at `sample-4`**, and the first opus run of this window DEFERred at $0.00 the same way. The share is therefore applied in `propose_plan` to every unit **after the first**; the first unit is bought against the whole budget. This keeps the effect the owner asked for on the motivating case — on `d7be758` unit 2's four samples reserve $0.178 against a $0.15 share, so discovery stops after unit 1 having spent ~$0.09 and verification keeps ~$0.16 instead of $0.076 — while a review can always afford to read one change unit. The residual: a single very large *first* unit can still take more than 60%. Making the bound literal for the first unit too would require raising the default per-review budget to roughly $0.7 on the sample estimates observed on real traffic; that is an owner call, not an agent one. RED: `tests/test_proposer.py::test_the_discovery_share_bounds_breadth_and_never_the_first_unit`.

### D-112 — The repository's gates run on a GitHub runner on every push to `main`

- **Date/status/scope:** 2026-09-03 · active, owner-directed · `.github/workflows/ci.yml`; `tests/benchmark/test_m01_offline_measurement_probe.py`.
- **Decision:** push to `main` (and `workflow_dispatch`) runs ruff, mypy, `git diff --check` and `pytest --cov` on `ubuntu-latest` under Python 3.12 from `requirements-toolchain.lock`, **with no deselection**. One supported Python, as AGENTS §13 asks of an ordinary gate. The checkout is full-depth with tags: the M-01 probe builds a worktree at a fixed baseline commit and the rollback drill resolves the documented oldest install ref.
- **Why:** the window-end gate has not been green on the owner's host since its docker VM lost registry egress. `tests/execution/test_linux_isolation.py` cannot build its image there, and deselecting it *is* the kernel coverage shortfall — `container_adapter.py` at 43%, the whole of `ContainerAdapter.run`.
- **Result:** the floor is green where the container runs. First run: **`container_adapter.py` 90%, kernel total 92.04% against the 90% floor** (locally 88.35% with the isolation tests deselected). It also found two host assumptions the owner's machine hid: `PYTHON = ROOT / ".venv" / "bin" / "python"` in the M-01 probe test (now `sys.executable`), and a shallow checkout with no tags.
- **Limits:** the runner is not free of its own assumptions, and a green run there does not make the owner's host green. Nothing about the paid `pull_request` review workflow (D-108) changed; this job makes no model call.
- **Reversal:** delete the workflow file.

### D-113 — The generation wall was mostly a population artefact, and what is left is model-sensitive

- **Date/status/scope:** 2026-09-03 · active, owner-directed (instruction 1 of 2026-09-03e) · report [`docs/acceptance/2026-09-03-generation-classification.md`](docs/acceptance/2026-09-03-generation-classification.md); no product code changed by this measurement.
- **Decision:** a receipt pilot pair is only a defect pair if the repairing commit's **own human-written tests discriminate** it — pass on one side, fail on the other. Running that check on the two reviewed pairs of D-109 removes `d7be758` from the population entirely: the fix's test fails identically on both sides, and `git blame`/`git log -S` put the defect two commits earlier, in `e17c686`. Selecting by "which commit last touched the lines the fix removed" is not the same as "which commit introduced the defect", and that is what D-109 did.
- **Result:** of the six executed reproductions in the old §5 table, **four ran against pairs with no regression to find or none proposed** and were correct silences or correct verdicts. `e17c686` does regress — three of the fix's five tests discriminate — but its regression was never proposed: the run stopped at `read 2 of 4 units, budget-limited` and the two unread units are exactly the two files that carry it. The generation question rests on **two** cases, not six.
- **The model matters.** Re-run with `claude-opus-5`, K=4: `pytest-dev__pytest-10051` produced **2 candidates, 2 eligible, 2 reproductions, 2 certified, 2 published** (head FAIL 3/3, base PASS 3/3, sealed bundles, `linux-container-v1`) where `claude-sonnet-5` produced one unfaithful test. This is the first receipt-backed publication that case has ever produced. The Attest PR #8 pair still fails under opus, in the same class as under sonnet — the generated file is not self-contained: `NameError` (no imports at all) under sonnet, `ModuleNotFoundError: test_matcher` at collection under opus.
- **Limits:** n = 2 real cases, one run per model; nothing here is a rate, and the two models were not run at the same per-review budget. The remaining failure mode is the reproduction prompt's contract about a self-contained test, not the differential kernel, which refused correctly every time.
- **Reversal:** the population rule is a selection criterion for future pilots, not code; a future pilot that ignores it produces the same artefact.

### D-114 — The generated reproduction must stand on its own, and a file that does not collect is regenerated

- **Date/status/scope:** 2026-09-03 · active, owner-directed (decision 1 of 2026-09-03f) · `src/attest/review/executor.py` (`GENERATOR_SYSTEM`, `imported_test_modules`, `generate_repro`, `execute_differential`, `verify_candidate`); `tests/test_executor.py`, `tests/test_ci_flow.py`.
- **Decision:** three things, in the order a bad generation meets them. (1) The prompt says the file stands alone: import every name it uses, only from the standard library and the project's own packages, copy the helpers you were shown instead of importing them, and set the log level before asserting on log records. The D-089 sentence that told the generator the nearest test module's directory is importable is **removed** — it was true of the reproduction's directory only by accident and is false in a container. (2) A generated body that imports a test module, a `conftest` or a `tests` package is rejected inside the generation loop, before it is written anywhere and before anything executes it; the attempt is spent and the next one is taken. (3) A body that does not collect on head no longer ends the candidate: the generator is asked **once** more (`COLLECTION_REGENERATIONS = 1`) and only the file that collects reaches a behavioural run. The retained collection evidence is the round that decided.
- **Why:** all three remaining real generation failures across both models were scaffolding, not evidence about the diff — a file with no import statement at all, a file importing `test_matcher` from the repository's own `tests/`, and a `caplog` assertion with no `set_level`. The differential kernel refused each of them correctly; nothing about certification changes here.
- **Deviation from the instruction, stated plainly:** the owner asked for the `pytest --collect-only` check to happen "before execution, not in the container". The collection round runs **inside the same backend as every other execution of head code**, because collecting imports the reviewed revision and a host-side collect would run head code outside the sandbox — `G-SEC-001..003` forbid that, and no product change may buy speed with it. What the instruction's second half asks for is met: a file that does not collect never reaches a behavioural run, and the test-module rejection is purely static and executes nothing at all.
- **Cost:** at most one extra generation call and one extra collection run per candidate; both are bounded by the same per-review budget and shared deadline, and a regeneration that cannot be funded reports `…; regeneration failed: BudgetExceeded: …` rather than silently retrying.
- **Limits:** this addresses the *scaffolding* class only. It cannot make a test faithful, and a second scaffolding failure is reported, not spent on.
- **Reversal:** restore the removed prompt sentence, drop `imported_test_modules` from the attempt loop, and pass `regenerate=None` from `verify_candidate`.
- **RED:** `tests/test_executor.py::test_verify_candidate_regenerates_a_reproduction_that_does_not_stand_alone`.

### D-115 — The reproduction generator has its own model; the budget prices each call at the model that answered it

- **Date/status/scope:** 2026-09-03 · active, owner-directed (decision 2 of 2026-09-03f) · `src/attest/data/pricing.toml`, `src/attest/review/config.py`, `src/attest/review/budget.py`, `src/attest/review/proposer.py`, `src/attest/review/executor.py`, `src/attest/review/verification.py`, `src/attest/review/run.py`, `src/attest/cli/main.py`; `docs/operations/base-policy.md`.
- **Decision:** `generation_model` joins `default_model` in the shipped pricing table — the only place a model id belongs — and becomes a `ReviewConfig` field and a base-policy key. Proposals run on `model`; the reproduction generation runs on `generation_model`. The provider takes a per-call model override, offered only to providers that declare `supports_model_override`, so every other provider and every test double is unaffected. `Budget` holds a price table per model, prices each reservation and settlement at the model that answered it, and records that model on the call row; an unpriced model raises rather than being charged at another model's rate. The `review_run` ledger row carries both models, so any result table can name them. In CI `generation_model` is protected exactly like `model`.
- **Why:** on the one case where both models have reviewed the same pair, `claude-opus-5` turned zero receipts into two certified publications where `claude-sonnet-5` produced an unfaithful test (D-113). Proposals rank and are cheap to repeat; the reproduction is the evidence and is bought once.
- **Limits:** n = 1 comparable case. The generation stage costs roughly 2.5× more per call at the new model's input/output prices, inside the same unchanged $0.25 default budget, so a review that could afford two reproductions may now afford one. Nothing about alpha, K, the channel cap or the LR moves.
- **Reversal:** set `generation_model = "claude-sonnet-5"` in `pricing.toml`; no code change.
- **RED:** `tests/test_executor.py::test_the_reproduction_generator_runs_on_its_own_model_and_is_priced_there`.

### D-116 — A receipt pilot pair is the repairing commit and its parent, and the fix's own tests must discriminate it

- **Date/status/scope:** 2026-09-03 · active, owner-directed (decision 4 of 2026-09-03f) · `docs/mainline.md` §3; supersedes the selection rule in D-109, extends D-113.
- **Decision:** for a repairing commit `F`, a receipt pilot pair is **head = `F^`, base = `F`** — the same shape mainline §3 already fixes for SWE-bench (base carries the fix, head does not). A pair enters the population only when `F`'s own human-written tests discriminate it: copied onto both sides and run there, at least one test fails on head and passes on base. The check is free and runs before any paid review.
- **Why:** D-109 selected pairs by blaming the lines the fix removed, which finds the last commit to *touch* a line, not the one that introduced the defect. That put `d7be758` — a semantics-preserving rewrite — into the population, and two of the six reproductions counted as generation failures were reviewing a pair with nothing in it.
- **Consequence for the record:** the D-109 population is retired. Every future receipt pilot pair is named by its **repairing** commit, not by the commit blamed for the defect.
- **Reversal:** none needed; this is a selection criterion, not code. A pilot that ignores it reproduces the artefact.

### D-117 — Within a rank, discovery reads the largest change first

- **Date/status/scope:** 2026-09-03 · active, owner-directed (decision 5 of 2026-09-03f) · `src/attest/review/planner.py` (`_unit_order`, `_changed_line_count`); `tests/test_planner.py`.
- **Decision:** plan order is `(source before everything else, changed lines descending, path)`. D-105's rank is unchanged — only a Python file can carry an anchored, reproducible finding, so every `.py` file still precedes every other file. Within a rank the tie-break is no longer alphabetical.
- **Why:** a budget-limited discovery reads the units it reaches in plan order. On the one real regression this project has found on its own traffic (`e17c686`), the review stopped at `read 2 of 4 units, budget-limited` and the two unread units were `patterns_shapes.py` and `scoring.py` — the two files carrying the defect, unread because they sort last alphabetically. The size of a change is the only signal the plan holds before any model call.
- **Limits:** size is a proxy, not evidence: a one-line defect in a small file is now read after a large mechanical rename. Both keys are properties of the diff alone, so the plan digest stays stable under reordering (`INV-ORDER-001`).
- **Reversal:** drop the second key from `_unit_order`.
- **RED:** `tests/test_planner.py::test_within_a_rank_the_largest_change_is_planned_first`.

### D-118 — All nine release drills, and four red-team fixture classes on the production backend

- **Date/status/scope:** 2026-09-03 · active, owner-directed (instructions 7 and 8 of 2026-09-03f) · `scripts/release/drill.py`, `scripts/release/redteam.py`, `.github/workflows/red-team.yml`, `tests/release/test_drill.py`; records [drills](docs/acceptance/2026-09-03-release-drills-all-nine.md), [matrix](docs/acceptance/2026-09-03-redteam-matrix.md).
- **Decision:** the seven unimplemented `G-RELEASE-001` drills are implemented — revoked credential, GitHub outage, executor unavailable, budget exhaustion, superseded pull request, malicious same-repository change, verifier failure — each driving the product's own code path and each carrying a negative control, one commit per drill. **56 checks, all passing.** The `G-SEC-002` red-team matrix runs four preregistered attack classes against `linux-container-v1` on a GitHub runner under `workflow_dispatch`, with a positive control that must certify in the same backend in the same run.
- **Result:** every attack fixture is marked and none certified. Head code reading the controller's environment finds nothing; a socket and a write outside the work directory each defer the run with a reason and leave nothing on disk; an executor answering another request's nonce is rejected with the mismatch named. The drills also found a real defect: a provider outage message that echoes the credential it rejected reached the author-visible notes unredacted, fixed in the same window.
- **Limits, stated rather than rounded off:** four fixture classes are not `G-SEC-002`. That gate names `/proc`, home/git, DNS/IPv6, native syscall, fork/thread bomb, exec, daemon, resource and namespace fixtures too, and demands a **sandbox-external** supervisor or kernel observation; this matrix reads the guard's own in-process markers. The secret row passes because the canary is *absent* in the container, which is weaker than "the read was denied". Two drills (GitHub outage, malicious change) need a docker daemon and fail without one — the honest answer for a host that cannot run the production backend.
- **Reversal:** delete the drill functions and the workflow; the two original drills stand alone.

### D-119 — L-01 is not complete: four of mainline §1's six conditions do not hold, and no tag was cut

- **Date/status/scope:** 2026-09-03 · active, owner-directed (instruction 9 of 2026-09-03f) · reading only, no code; [the six conditions](docs/acceptance/2026-09-03-mainline-six-conditions.md); `docs/roadmap.md` L-01.
- **Decision:** conditions 2 (every author-visible finding carries a verifiable receipt) and 6 (the L-01 exit list) **hold**. Conditions 1, 3, 4 and 5 **do not**, so L-01 stays open and **`v0.1.0-pilot.2` was not tagged**; `v0.1.0-pilot.1` remains the install ref.
- **Why each fails:** (1) no outside repository has ever had the Action installed or received a comment — every outside-repository run has been a local `attest review` with no GitHub write; (3) four `G-SEC-002` fixture classes pass on the production backend, out of a preregistered list of nine-plus, and observed from inside the boundary rather than by an external supervisor; (4) the 39 controls are synthetic and the one natural-null study is 20 commits in one repository, against `G-NULL-001`'s 600 candidates across 30 repositories; (5) E-04 stratum v1 saw 2 units and 0 eligible candidates, against a preregistered minimum of 100/100.
- **Consequence:** 1 and 3 are work someone can simply do. 4 and 5 are population problems that need spend nobody has authorised; [the real-traffic plan](docs/corpus/real-traffic-plan.md) is a step toward 4 and is itself far below `G-NULL-001`.
- **Reversal:** none; this is a reading of the evidence at this commit and is superseded by the next reading.

### D-120 — An assertion that rests only on constants the change replaced is a constant change, not a regression

- **Date/status/scope:** 2026-09-03 · active, owner-directed (decision 2 of 2026-09-03g) · extends D-102 · `certification/intent.py` (`constant_change`, `CONSTANT_CHANGE_LABEL`, two observation fields, policy version **`attest.intent.v2`**), `review/intent.py` (`constant_values`, `assertion_constants`, `observe_constant_substitution`; `observe_intent` reads the base revision of the anchored file), `review/executor.py` (the base source is read beside the head source; the constant class defers into the same drawer); `tests/test_executor.py`, `tests/test_intent_observer.py`, `tests/test_ci_flow.py`.
- **Decision:** a differential goes to the **`behavior_change` drawer** when every literal constant the generated test's failing assertion rests on is one this change **substituted** in the anchored file — present in the base revision, absent from the head revision, and replaced by another constant of the same type. The assertion's *condition* is read; its *message* is prose the generator wrote and is not read. No base-tree witness publishes this class: unlike D-102's new rejection, there is nothing an author could witness — the test restates the constant the author edited. A constant the change merely **deletes** (nothing of its type added in its place) is not a substitution: losing a validation message is a regression, and that path is untouched.
- **Why:** the one receipt this product has ever produced on real third-party traffic certified "head discloses `explainable-horizon-score-v1` where base discloses `explainable-horizon-score-v2`" — true, differential, bound to a changed line, and about a version string. The owner's answer to §5 question 3 of 2026-09-03f is that this class must not publish.
- **Result on the record:** the `d7be758` receipt (`c229fb6992bb…`, task `20260903-170105-9b14404e`) **reclassifies to `behavior_change` and would no longer be certified** under the new policy; the bundle is kept as the historical artifact it is. Re-judged offline: the assertion's constants are exactly `'explainable-horizon-score-v2'`, the change removed it and added `'explainable-horizon-score-v1'` in its place. Its published count was already 0 (the C-05 family threshold), so no author-visible claim changes.
- **Limits:** the rule reads the *anchored* file only, so a constant substituted in one file and asserted through another is not seen. Whole-file value sets mean a constant that survives elsewhere in the head revision is not "removed"; that is deliberate and keeps the rule quiet on common literals. The "same type added" test is a heuristic for substitution, not a proof of it — a change that both drops a message and edits an unrelated string of the same type can send a real regression to the drawer. Every mistake it can make is in the direction of not publishing.
- **Cost:** one extra file read per differential; no model call, no execution.
- **Reversal:** drop the `constant_change` branch from `intent_verdict` and the executor; the policy version returns to `attest.intent.new-rejection.v1`. Bundles written under `attest.intent.v2` verify only with the code that wrote them (INV-VERSION-001, as v3 and v4 did before).
- **RED:** `tests/test_executor.py::test_an_assertion_on_a_substituted_constant_goes_to_the_drawer`, with the negative control `::test_an_assertion_on_a_computed_value_still_certifies` in the same commit pair.

### D-121 — A receipt is verified under the policy version it records, and a retired policy still cannot publish

- **Date/status/scope:** 2026-09-04 · active, owner-directed (decision 2 of 2026-09-04) · extends D-102 and D-120 · `certification/intent.py` (`INTENT_POLICY_V1`, `POLICY_FIELDS`, a version-scoped `digest`, `constant_change`, `intent_verdict`), `review/evidence.py` (`intent_reasons`, extracted from `verify_bundle`); `tests/certification/test_intent.py`.
- **Decision:** offline verification judges an intent observation under **the policy version the record names**, not the one in force today. `POLICY_FIELDS` is the registry: `attest.intent.new-rejection.v1` names the ten fields D-102 wrote, `attest.intent.v2` those ten plus D-120's `constant_substitution` and `asserted_constants`. Three consequences follow. The **digest** is computed over exactly the fields the recorded version defines, so a field a later version adds does not move an older receipt's digest. **D-120's constant rule is not applied to a v1 observation** — the rule did not exist when that receipt was issued, and re-judging by a later rule is not verification. A record whose key set differs from its version's field set is **malformed**, because a field outside that set is not bound by the digest.
- **What did not change:** a version absent from the registry still answers `unknown intent policy` and never publishes (`INV-VERSION-001`). A *current* task still binds `receipt.intent_policy_version` to the base-owned policy, so a receipt naming a retired version is rejected with `INTENT_POLICY_MISMATCH` before it can be issued or accepted. Keeping v1 verifiable is a statement about the past, not a licence for the present.
- **Why:** the product's headline claim is that every author-visible finding carries a *verifiable* receipt. D-120 bumped the version and, with it, silently voided every receipt issued before — `attest verify` answered `rejected: … unknown intent policy` on bundles nothing was wrong with. A claim that decays whenever the policy is edited is not an audit chain. This was written down as a backlog item in the same window it was created; it is a promise, not a nice-to-have, so it is paid off here rather than carried.
- **Result on the record:** all **17** intent observations on this host written under `attest.intent.new-rejection.v1` — the `us-stock-helper`, `Corum` and SWE-bench bundles of 2026-09-03 — verify offline again. Before the change every one of them was rejected twice over, for a digest that had moved and for a policy the verifier no longer recognised.
- **Erratum:** the retired version string is `attest.intent.new-rejection.v1`, not `attest.intent.v1`; D-120's reversal note and the 2026-09-03g handoff both use the shorter form loosely.
- **Limits:** the registry records field sets and dispatches the one rule that differs between the two versions; it is not a general policy interpreter. A third version whose *rule* differs in more than the constant clause will need its own branch in `intent_verdict`, not just a row in `POLICY_FIELDS` — the table is deliberately small and will not scale silently.
- **Cost:** none. No model call, no execution, no extra file read.
- **Reversal:** delete `POLICY_FIELDS` and restore the equality check against `INTENT_POLICY_VERSION`; receipts older than the current version stop verifying again.
- **RED:** `tests/certification/test_intent.py::test_a_v1_receipt_still_verifies_under_the_v1_rules`, `::test_a_v1_digest_is_computed_over_the_fields_v1_defined`, `::test_the_verifier_reads_a_v1_intent_record_and_judges_it_under_v1`, with the controls `::test_an_unknown_intent_policy_still_fails_closed`, `::test_the_v2_constant_rule_is_not_applied_to_a_v1_receipt`, `::test_the_verifier_rejects_a_v1_record_carrying_a_field_v1_never_had` and `::test_a_retired_policy_cannot_authorise_a_new_publication`.
- **Trace:** `INV-CERT-001`, `INV-RECEIPT-001`, `INV-VERSION-001`.

### D-122 — A control is a commit six months old whose lines nobody has touched, and no affordable n reaches the ≤1% bound

- **Date/status/scope:** 2026-09-04 · active, owner-directed (decision 1 of 2026-09-04: option C, plus an amended control definition and an affordable sample size) · `docs/acceptance/evolution-gates.md` (`G-NULL-001` amendment; new `G-NULL-001a`), `scripts/corpus/qualify_controls.py`, [pricing paper](docs/acceptance/2026-09-04-g-null-001-amendment.md), corpus table column.
- **Decision:** a control commit qualifies only when (1) its committer date is at least six months before the measurement date and (2) no later commit on the default branch touches a line it added — every added line still present at the tip and still blamed to it. Any later commit disqualifies, fix or not; adjudicating "was that a fix?" is the subjective judgement the rule exists to remove, and the conservative reading only ever drops controls. The population may be the owner's repositories plus **read-only clones of public repositories** (AGENTS.md §7/§8), which retires the ≥30-repository blocker. Option C is adopted: `G-SEC-002` is engineering at $0, E-04 goes to 100 units, `G-NULL-001` is not run.
- **The gate splits.** `G-NULL-001` stands unchanged and unpassed. `G-NULL-001a` is a new, weaker gate whose permitted claim must always carry its own n and bound. With zero errors the 95% upper bound is `1 - 0.05^(1/n)`, so **≤1% needs n ≥ 300 whatever a review costs** — $65.31 at the measured $0.2177, above the whole approved cap. No amendment to the *control definition* moves an arithmetic floor.
- **The measurement that decides it:** requalified with `qualify_controls.py` (git only, no model call), **0 of the 25 corpus controls qualify, and the age check alone drops all 25.** The oldest control commit is 41 days old; the three repositories' entire histories are 6 days (`Attest`), 7 days (`Corum`) and 6 weeks (`us-stock-helper`). **This account owns no controls under its own new definition**, so any run must be built from public clones. The untouched check, reported for information against each clone's tip, passes 9 of 25, fails 5 and is undefined for 11 (unmerged branch, or newer than the clone).
- **Recommended shape:** n = 100 at **$21.77** ($13.97–$34.27) for a 95% upper bound of **2.95%** — affordable beside E-04 under a cap near $55, and three times the release bound, which the claim must say out loud.
- **Limits:** the rule selects **cold code** — a line untouched for six months is a line nobody had to fix *and* a line nobody exercises — which biases the measured false-publication rate downward by an amount this design does not estimate. Every run under the amendment must report mean eligible candidates per control beside the 2026-09-03 baseline of 2.9 per review. The qualifier reads the default-branch tip it is given; on a stale or detached clone the second check is undefined rather than false, and the report says which.
- **Cost:** $0.00. Nothing was run.
- **Reversal:** delete the amendment and `G-NULL-001a`; the corpus returns to subject-based strata, which `c03` and `c05` already refuted.
- **Trace:** `INV-MEASURE-001`, `INV-TRUTH-001`; `G-NULL-001`, `G-NULL-001a`; E-01.

### D-123 — A native BLAS is told to want one thread; the thread limit stays at zero

- **Date/status/scope:** 2026-09-04 · active, owner-directed (instruction 4 of 2026-09-04) · `src/attest/review/executor.py` (`_reproduction_environment`), `tests/execution/test_linux_isolation.py`; [report](docs/acceptance/2026-09-04-numpy-under-the-thread-cap.md).
- **Decision:** the reproduction environment names `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1` and `MKL_NUM_THREADS=1`. `RLIMIT_NPROC` stays at 0.
- **Why this option and not the other:** the owner offered either the variables or a raised thread limit. `RLIMIT_NPROC = 0` is the containment `linux-container-v1` and the language guard's kernel-containment check are built on (`INV-SEC-001`); raising it to let OpenBLAS have twelve threads would relax a security boundary to fix an import. Telling a BLAS to want one thread asks the kernel for nothing and relaxes nothing.
- **Result:** on the four `Corum` defect pairs the corpus lost entirely to this cause — 9 verifications, 0 reproduced, 0 receipts on 2026-09-03 — the re-run at the same `--budget 0.60` through `linux-container-v1` gives **8 verifications, 7 reproduced, 7 accepted receipts and 4 published, for $0.4046 against $0.5622.** `import numpy`, `import scipy` and `import corum` all succeed under the three variables and all fail without them. No `blas_thread_init` line survives in the new ledger.
- **Limits:** four pairs in one repository, selected *because* they were blocked by one known cause and then unblocked — the most favourable sample there is. It measures no recall and no null rate. `NUMEXPR_NUM_THREADS` and `VECLIB_MAXIMUM_THREADS` are the same class of knob and are **not** set, because nothing measured here needed them; a project that pulls numexpr will hit the same wall. The variables change `environment_digest`, so a receipt's digest is the one recorded with it (D-121 keeps older bundles verifiable).
- **Evidence for the fix, stated exactly:** a direct container reproduction with the adapter's own flags, plus the end-to-end re-run. The committed fixture `tests/execution/test_linux_isolation.py::test_a_project_that_imports_numpy_runs_inside_the_container` did **not** finish on this host inside the window — its image build (a tree declaring numpy) did not complete — so it is a regression guard for the next run, not this decision's evidence.
- **Cost:** $0.4046 for the re-run; the fix itself is free.
- **Reversal:** delete the three entries; `Corum` returns to 0 of 4.
- **Trace:** `INV-SEC-001`, `INV-EVIDENCE-001`; `G-SEC-002`, `G-RECALL-002` (untouched).

### D-124 — The bundle is about the test that ran, and certification verifies its own output before anything is author-visible

- **Date/status/scope:** 2026-09-04 · active, agent decision under the owner's instruction 1 of 2026-09-04 (product condition 2) · `src/attest/review/executor.py` (`DifferentialExecution.executed_spec`, `verify_candidate`), `src/attest/review/certify.py` (`attempt_certification`), `src/attest/review/verification.py` (the refusal becomes a DEFER reason), `scripts/corpus/reverify_bundles.py`, `tests/test_bundle_integrity.py`; [re-verification report](docs/acceptance/2026-09-04-bundle-reverification.md).
- **The defect, exactly.** `execute_differential` may replace the generated test before any behavioural run is bought (D-114: a file that does not collect is scaffolding failure, not evidence). It does so by rebinding its own local `spec`. `verify_candidate` kept the *first* spec in the variable it returned, and `attempt_certification` wrote `verification.spec.test_body` into the bundle. So on every review where the first generation did not collect, **the bundle's `test_repro.py` was the test that failed to collect, and `receipt.test_digest` — read from the runs themselves — named the one that ran.** When the first generation returned `{"test_body": ""}` the bundle's test file is one newline; when it returned a real but uncollectable file, the bundle carries a plausible test nobody executed. That second shape is the worse one.
- **Decision, three parts, all fail-closed.**
  1. `DifferentialExecution` carries `executed_spec`, read at the moment the differential finishes, so the spec that produced the recorded runs is the one the caller gets. This is the root-cause fix; every regeneration round is now correctly attributed.
  2. Before writing anything, `attempt_certification` compares `sha256(test_bytes)` with `subject.test_digest` and refuses on mismatch (`bundle_test_digest_mismatch`). `write_bundle` takes the bytes from its caller and cannot check them itself; this is the seam where the receipt's subject and the bundle's contents could diverge silently, so the check belongs here.
  3. **Certification verifies its own output once, offline, exactly as a reader would** — `verify_bundle(path, key=…, require_seal=True)` — and a bundle that does not pass buys nothing (`bundle_self_verification_failed`). The candidate becomes a DEFER with the verifier's own reasons attached, never a finding.
- **Why the existing gates did not catch it.** `G-CERT-001` and `G-SEM-001` both hold: the kernel is pure and the verifier is correct — it rejected these bundles the moment anyone asked it. Nobody asked. The suite's bundle round-trips (`tests/test_evidence.py`, `tests/execution/test_fresh_repeats.py`) all use a first generation that collects, so the regeneration branch never reached `write_bundle` in any test. The one test that does exercise regeneration, `tests/test_executor.py::test_verify_candidate_regenerates_a_reproduction_that_does_not_stand_alone`, asserts which file reached the *executor* and stops at that boundary — it never looks at `verification.spec` and never writes a bundle. The gap was not a missing rule but a missing composition: two correct halves with no test spanning them, and a product that never ran its own verifier on its own output.
- **Result on the record ([report](docs/acceptance/2026-09-04-bundle-reverification.md)).** 86 bundles on this host re-verified: **44 accept, 42 do not.** Two disjoint causes. **Four** are this defect (`test bytes do not match receipt.test_digest`); **thirty-eight** are schema drift — receipts written before the V-03 `fresh_state` field, the X-01 executor identity, or the current receipt body, which stopped verifying when the schema moved (INV-VERSION-001, the trade D-121 already documents). Of the four, **one was published**: `us-stock-helper` `75ce7a3425` in the real-traffic corpus row `d11`. Every failing bundle is marked `unverifiable_v1.json` beside its manifest — outside the manifest, so the bundle's own digests stay exactly what was written — and **nothing is deleted**: a bundle that no longer verifies is still the record of what ran.
- **Corrected corpus numbers:** certified 18 → **16**, certified-but-below-threshold 8 → **7**. Row `d11` goes 4 certified → 3; control row `c02` goes 1 certified → 0. Publication needs two different answers, because they answer different questions, and both are on the record ([replay](docs/acceptance/evidence/2026-09-04-family-replay.json)):
  - **publications that stand: 7 → 6.** The run published 7 findings; one of them, `75ce7a3425`, rests on a bundle that does not verify, so it is withdrawn.
  - **what the fixed product would have published on the same run: 7.** `75ce7a3425` is the representative of a three-member publication cluster on `d11` (`nasdaq.py` lines 47, 47, 50). Refuse it at certification and `38c316089d` becomes the representative at e = 52.78 against a bar of 40, so `d11` still publishes two — a different finding about the same defect. Nothing else in the run moves: the refusal happens after the reproduction is bought, so eligibility, spend and every other candidate are untouched.

  The 0-false-publication count is unchanged either way — the withdrawn publication is a defect-pair receipt, not a control's. The pair-level headline (6 of 19 pairs certified, 4 of 19 published) is unchanged.
- **Limits:** the self-check runs the same verifier in the same process on the same host, so it catches what the bundle cannot prove about itself — it is not an independent audit and does not detect a verifier that is wrong in both directions. It roughly doubles the I/O of an accepted certification and adds one signature verification; measured at well under a second per bundle, against reproduction runs that take tens of seconds. Bundles already written are not repaired: the executed test bytes still exist under `.attest/repro/…/head-1/test_repro.py`, but rewriting a sealed bundle after the fact is exactly the forgery the seal exists to prevent, so they stay marked instead.
- **Cost:** $0.00. No model call; the re-verification is git-and-disk only.
- **Reversal:** drop the `executed_spec` field and the two guards; the bundle returns to trusting whichever spec the caller happened to hold.
- **RED:** `tests/test_bundle_integrity.py::test_a_regenerated_reproduction_puts_its_own_bytes_in_the_bundle` (1a) and `::test_a_bundle_that_does_not_verify_publishes_nothing` (1b). Both were confirmed failing on `5ebcf88` before the fix: the first reads `b"\n"` out of the bundle, the second surfaces a finding it must not.
- **Trace:** `INV-CERT-001`, `INV-RECEIPT-001`, `INV-VERSION-001`; `G-CERT-001`, `G-SEM-001`; mainline §1 condition 2; `RISK-CERT-01`.

### D-125 — The publication family is the change unit, and the change unit is the file

- **Date/status/scope:** 2026-09-04 · active, owner-directed (decision 2 of 2026-09-04; backlog option (a) of the three costed on 2026-09-03) · new `src/attest/certification/units.py`, `src/attest/certification/selection.py` (`FamilyPolicy.threshold_for`, `Selection.unit_thresholds`, publication policy schema `v1` → `v2`), `src/attest/review/verification.py` (the ledger records the units and the bars applied), `scripts/corpus/replay_family.py`, `tests/certification/test_change_unit_family.py`, `tests/test_ci_flow.py` (the G-CERT-004 gate test); [comparison paper](docs/acceptance/2026-09-04-family-per-change-unit.md).
- **Decision:** a certified finding publishes at `e >= m_u / alpha`, where `m_u` is the number of eligible candidates in **its own change unit**, and the change unit is the **changed file its anchor names**. A publication cluster is judged in the unit of its representative. `alpha`, the likelihood ratio, `K` and the hard cap are untouched, and the cap is still applied across units, so at most three findings are author-visible anywhere.
- **Why the file and not the planner's unit.** `PlanUnit` exists to pack prompt context under `MAX_UNIT_CHARS`: its membership depends on a character budget and on how much retrieved context each file happened to attract, so a statistical family defined on it would move when a prompt budget moved. The file is the coarsest thing the diff alone determines that a reviewer already reasons about. The definition lives alone in `certification/units.py` behind `CHANGE_UNIT_POLICY_VERSION`, so a finer unit later — the enclosing function, the hunk — is one edit and a version bump.
- **The three properties the RED checks.** *Order-invariant*: a candidate's unit is a function of its own anchor path alone, so no permutation of candidates, samples, files or hunks moves a candidate between units or changes a unit's size (checked over 50 shuffles of the anchors and 24 shuffles of the certified findings, end to end through `select_for_publication`). *Deterministic*: the same anchor always gives the same unit — no clock, no hash of a mutable set, no dependence on what else was found; separator style is normalised so a Windows-style anchor is not a second unit. *Total*: every candidate has exactly one unit, so the units partition the eligible set and the sizes sum to the PR-wide count.
- **What the guarantee now is, stated rather than hidden.** Bonferroni over `m_u` controls the family-wise error rate at `alpha` **within a change unit**. Across a pull request the bound is the union over the units that published, and at most `hard_cap` findings are ever author-visible, so the PR-level family-wise error is bounded by `hard_cap * alpha` rather than `alpha`. That is the price. Any split of `alpha` across units that preserved the PR-level rate returns exactly the `m/alpha` bar it replaced — there is no version of this that is free, which is why it is an owner decision and not an implementation detail.
- **The whole corpus recomputed ([paper](docs/acceptance/2026-09-04-family-per-change-unit.md), [data](docs/acceptance/evidence/2026-09-04-family-replay.json)).** `scripts/corpus/replay_family.py` replays the recorded reviews through the real selector; $0.00, no model call, no execution. **The old rule reproduces the ledger on 66 of 66 reviews**, which is what licenses the new column. On the D-124-corrected population, publications go **12 → 17** across the three clones. Five new publications, all on defect pairs: three on `d05`, one on `d13`, one on `d02`. The bar moves because a large change is many small families — median `m_u` is 2 against a median PR `m` of 4, and 40 of the 89 units hold a single eligible candidate.
- **The control condition, which is what decided adoption.** The owner's rule was that any publication in the control group stops the run for root cause and the rule is not adopted. **No control gains a publication.** `c02` — ten eligible candidates, all in one file — keeps a bar of 100 and its one certified receipt (e = 60) stays suppressed exactly as before; `c04` likewise; every other control certified nothing under either rule. `c03` and `c05` publish the same findings under both rules, and both were adjudicated true positives on 2026-09-03. The rule is therefore adopted.
- **The gate test changed, and says so.** `tests/test_ci_flow.py::test_pr_family_policy_caps_publication_and_counts_a_defect_once` (G-CERT-004) now runs seven candidates in two files: the PR-wide bar of 70 would publish nothing, `app.py`'s bar of 20 publishes one, and the whole five-candidate `util.py` unit stays below its own bar of 50. Both halves of the decision in one run, with the cap and the same-defect rule unchanged.
- **It then ran, on 100 units it had never seen.** E-04 stratum v2 the same night: 21 accepted receipts and **7 shadow findings on 3 units**, where the PR-wide bar publishes **nothing** on all three ([report](docs/acceptance/2026-09-04-e04-stratum-v2.md)). Under the previous rule that whole 100-unit run would have been silent. That is the backlog item's claim observed rather than argued — and it moves the risk: a product that publishes nothing cannot be wrong in public, and none of those seven is adjudicated.
- **Limits:** the file is a crude unit — a large module with unrelated defects is one family, and two files edited for one reason are two. The replay assumes the run is otherwise unchanged, which holds because publication is the last stage after every paid call, but it means these five findings were never *shown* to anyone and are not a precision measurement. Three of the five are in `Attest`'s own repository, the standing disclosed conflict. The corpus's controls are still not known to be defect-free (D-122), so "no control published" is a weaker statement than it sounds.
- **Cost:** $0.00. The replay is disk-only.
- **Reversal:** pass `eligible_units` mapping every unit to the PR-wide count — one line — and the old bar returns; the schema version and the ledger's `unit_thresholds` say which rule produced a given row.
- **RED:** `tests/certification/test_change_unit_family.py::test_the_unit_partition_is_order_invariant_and_deterministic`, with `::test_the_unit_partition_is_total_and_counts_each_candidate_once`, `::test_a_finding_is_judged_by_its_own_unit_not_the_pull_request` (the behaviour: e = 12 with a PR bar of 100 and a unit bar of 10 publishes; the same e-value in a unit of eight does not) and `::test_selection_is_unchanged_by_the_order_the_findings_arrive_in`.
- **Trace:** `INV-CERT-001`, `INV-FAMILY-001`; `G-CERT-004`; C-05; mainline §5 decision A.

### D-126 — The shipped per-review budget default is $1.00

- **Date/status/scope:** 2026-09-04 · active, owner-directed (decision 3 of 2026-09-04) · `src/attest/review/config.py` (`ReviewConfig.budget_usd`), `action.yml` (`budget-usd` input default), `src/attest/review/proposer.py` (the reservation arithmetic's worked example), `docs/operations/quickstart.md`, `docs/operations/base-policy.md`, `docs/github-action.md`.
- **Decision:** the factory default per-review model spend cap is **$1.00**, raised from $0.25. Nothing else moves: `alpha`, the likelihood ratio, `K`, `max_findings` and the cap are untouched, and the budget remains a hard cap that produces an explicit `DEFER: budget: …` rather than a truncated answer.
- **The two independent measurements it rests on.**
  1. **[The budget wall](docs/acceptance/2026-09-04-budget-wall.md)** — the same three defect pairs, the same product code (`fc2014f`), the same K and backend, only the budget different. At $0.60: 25 of 31 verifications ended in `BudgetExceeded` and **0** receipts. At $1.20: **0** `BudgetExceeded` and 5 receipts (4 of them verifiable after D-124). Certification went 0 of 3 pairs to 3 of 3 with nothing else changed.
  2. **[The corpus's own `BudgetExceeded` count](docs/acceptance/2026-09-03-real-traffic-corpus.md)** — over 43 unrelated reviews at $0.60, `BudgetExceeded` on the second generation attempt was **39 of 75** reproduction failures, more than collection failures (20) and unfaithful tests (13) together. That is a different population, a different question and the same answer: the budget, not the model, was the largest single reason a candidate did not certify.
- **Why $1.00 and not $1.20 or $0.60.** $0.60 is measured to be *below* the wall on real changes. At $1.20 no review exhausted its budget, so the wall is somewhere at or under it. $1.00 is the owner's number and sits above every measured mean — the corpus's overall mean is $0.22 per review and the largest population's is $0.31 — while remaining a cap the few large changes can reach.
- **The honest caveat, stated because the measurement says it.** Of the three reviews measured at $1.20, the per-review spends were $0.7532, $1.0338 and $0.9454. **`d03` spent $1.0338, which a $1.00 cap would have clipped.** So $1.00 is not above the highest observed need; it is above two of three. What that costs in receipts on that one review cannot be read off the ledger — it needs a paid re-run — and is left as an owner item rather than guessed at.
- **What the raise does not fix.** Budget was hiding the other three failure modes, not causing them: at $1.20 what remains is collection failures, unfaithful tests and reproductions that execute none of the changed lines. And more receipts is not more publications — that is what D-125 addresses, independently.
- **Cost to a consuming repository, stated in the docs.** Every operator-facing page now carries the measured price rather than the cap: mean **$0.22** per review over the 43-review corpus, $0.31 on a pull request with real code changes, $0.12 test-only, $0.06 documentation-only, and $0.91 (max $1.03) on the three largest changes ever measured. The cap is described as a ceiling, not a price.
- **Limits:** every figure is at `claude-sonnet-5` proposals and `claude-opus-5` generation with K = 4, on three repositories, one run each. A different model pair or a larger K moves all of them. The $0.25 default itself was **never measured on real traffic** — no run at $0.25 produced a receipt outside the benchmark corpora — so this is a raise away from an unmeasured number toward a measured one, not a comparison of two measured settings.
- **Cost:** $0.00. No run; both measurements already existed.
- **Reversal:** one literal in `ReviewConfig` and one in `action.yml`. A repository that wants the old behaviour sets `budget_usd = 0.25` in its base-branch `.attest.toml`.
- **RED:** none required — this is a factory default, not a rule. The behaviour it changes is already covered: `tests/test_ci_flow.py` exercises the budget-exhaustion DEFER path, and `docs/operations/base-policy.md`'s table is the contract.
- **Trace:** `INV-BUDGET-001`; mainline §1 condition 1; L-01.

### D-127 — RISK-CERT-01 root cause: an intended change of a returned value is invisible to every discriminator the product owns

- **Date/status/scope:** 2026-09-04 · **open — root-caused, not fixed** (the fix is an owner decision) · observed by `scripts/corpus/null_study.py` on the `G-NULL-001a` population; no product change made; [report](docs/acceptance/2026-09-04-g-null-001a.md).
- **What happened.** On the fifteenth of 58 preregistered qualified null controls, the product **published a defect claim on a control**. The run stopped at once under the `RISK-CERT-01` rule, before anything else was bought.
- **The control.** `jinja` `ac3ac6c9` (2022-03-03, *"async_variant filters are pickleable"*), 1,641 days old, no later commit touching a line it added — a control by the amendment's own definition (D-122), not a mis-stratified one. It replaces one `functools.wraps` with a stacked pair and states its intent in the diff: *"Take the doc and annotations from the sync function, but the name from the async function."*
- **What published.** A generated test asserting `do_thing_async.__name__ == "do_thing"` — the sync function's name. It passes on the parent and fails on the commit **because the commit deliberately changed that name**. The receipt is mechanically perfect: head fails 3 of 3, base passes 3 of 3, in isolation, from fresh state, changed lines executed, bundle verifies offline with its seal.
- **Root cause, and it is structural rather than a bug.** Every rule in the chain answers *"did the behaviour change, and is the change bound to this diff?"*, and here the answer is yes twice. **Nothing asks whether the author meant it**, except D-102's intent discriminator — which covers exactly one shape, a head failure raised by a `raise`/`assert` **in the changed lines**. This head code raises nothing; it returns a different string, and the failing assertion lives in the generated test. The receipt records the discriminator's silence verbatim: `new_rejection: false`, `exception_type: ""`, `witnesses: []`. **An intended change of a returned value is invisible to every discriminator the product owns, and it publishes.**
- **A second, separable defect in the same receipt.** The published prose says `__wrapped__` points to the async function. The test does not test that; it asserts `__wrapped__ is do_thing` and *passes* that assertion, failing on `__name__` instead. The sentence shown to the author and the sentence the test proved are different sentences, and **nothing checks that they agree**. S proposes the claim, V certifies an execution, and the two are bound only by a candidate id.
- **Why this one matters more than `c03` and `c05`.** Those two 2026-09-03 control publications were adjudicated true positives on commits that should never have been controls. This control is properly qualified and the publication is wrong. It is the first observed false publication of the class `G-NULL-001` exists to measure.
- **Not fixed, deliberately.** A discriminator that separates an intended value change from a regression moves what publishes, which makes it the same class of decision as D-102 — an owner decision. Designing one at the end of the window and validating it on the very population that produced it would be the worst available option. The run was left stopped with 43 of 58 controls unrun.
- **What it does to the window's other results.** Nothing mechanical: D-124's bundle integrity, D-125's family rule and D-126's budget are unaffected, and the receipt here is exactly the kind D-124 now guarantees. But it changes their reading. D-125 made the product speak where it had been silent — 7 shadow findings on E-04 stratum v2 where the old rule published none — and this decision says the product does not yet know when to keep quiet. **The two must be read together.**
- **Cost:** $0.5883 for the fifteen control reviews; $25.41 of the reservation released unspent.
- **Trace:** `RISK-CERT-01`, `INV-CERT-001`, `INV-TRUTH-001`; `G-NULL-001`, `G-NULL-001a`; mainline §1 condition 4; D-102, D-125.

### D-128 — `attest.intent.v3`: a value regression publishes only against a base specification this change left standing

- **Date/status/scope:** 2026-09-04 · active, owner-directed (decision 1 of 2026-09-04c; shape (a) of the three costed in D-127) · `src/attest/certification/intent.py` (policy `v2` → `v3`, four recorded fields, `value_change`/`value_change_reason`), `src/attest/review/intent.py` (`assertion_pinned_values`, `docstring_texts`, `is_spec_file`, `specified_by`, `find_specifications`, and the head tree the observer now reads), `src/attest/review/executor.py` (every receipt is judged, not only the rejection shapes), `src/attest/review/evidence.py` (the verifier coerces the new pairs), `scripts/corpus/intent_v3_replay.py`, `tests/test_intent_value_change.py`; [replay](docs/acceptance/2026-09-04-intent-v3-replay.md).
- **Decision.** When every head run failed on **an assertion of the generated test** — not a crash, not a `raise`/`assert` on a changed line — the differential shows a changed **value**, and the receipt publishes only when **the base tree specifies every value that assertion pins** *and* **this change leaves every one of those specifications standing**. Otherwise it goes to the `behavior_change` drawer labelled *"value change confirmed, intent unknown / 返回值变化已证实，意图未知"*. Wholly deterministic: file reads and `ast`, no model call, no execution, no repository command. `alpha`, the likelihood ratio, `K` and the cap are untouched.
- **This is D-102's mirror, and it is meant to be read as one.** D-102 asks whether the author meant a new **rejection** and requires the rejected input to be witnessed by the base tree. D-128 asks whether the author meant a new **returned value** and requires the old value to be *specified* by the base tree. Same question, same evidence class, same drawer, same fail-closed posture, and — this is the point — **the same recall cost**, one class later.
- **The three things it reads, and nothing else.** A value is *specified* when (i) a base **test** asserts it — a constant operand of a comparison inside an `assert`, or (ii) a **docstring** of the anchored file quotes it, or (iii) a **documentation** file (`.md`, `.rst`, `README*`) quotes it. Only strings can be quoted: a bare number in prose names nothing in particular. A specification is *standing* when the head revision of the same file still specifies the same value; a file head deleted, rewrote or could not be read counts as **rewritten**, never as standing.
- **What "the value the assertion pins" means, and why it is narrower than D-120's.** The pinned values are the **constant operands of the assertion's comparisons**, not every literal in the condition. A call's arguments, a subscript's slice and a dictionary's keys are how the assertion *reaches* the value; only what it compares against is what it *states*. So `getattr(w, "__wrapped__", None) is f` pins nothing, and `run_path("calc.py")["value"]() == 1` pins `1`. D-120's `assertion_constants` deliberately keeps the wider set, because it asks the opposite question — whether the assertion rests *only* on constants the change substituted — and both functions now sit side by side with their two questions written down.
- **The recall cost, measured before it was accepted, on all 121-plus recorded reviews ([replay](docs/acceptance/2026-09-04-intent-v3-replay.md), [data](docs/acceptance/evidence/2026-09-04-intent-v3-replay.json)).** $0.00, no model call. **Certified receipts 55 → 19.** The value class is 46 of the 55 and keeps **10**. Publications over **125 reviews: 27 → 14**, with the old replay reproducing the ledger on **59 of the 59** rows written under D-125's family policy. **This is the decision, not a side effect of it**: the product now refuses to certify most of what it used to, because most generated reproductions invent the value they expect and nothing in the repository ever said it.
- **The control condition, which is why it was adopted.** Both `jinja ac3ac6c9` receipts — the one D-127 root-caused and its sibling — go to the drawer on the real trees, for the stated reason: the base tree names neither `'normal_func'` nor `'from_normal'`. Under `v2` the same observation on the same bytes carries no verdict at all, which is how it published. **Control receipts 2 → 0, control publications 1 → 0**, and no control gains one anywhere in the corpus.
- **Where it is weakest, stated rather than discovered later — and (1) was then observed the same night.** (1) **Four of the ten survivors rest only on generic constants** (`None`, `0`, `2`, `True`), which almost any tree asserts somewhere; there the contradicted "specification" is a coincidence of vocabulary. **The resumed `G-NULL-001a` run published a control on a pinned set of exactly `["False"]` hours later (D-131), so this is an observation, not a caveat.** (2) **16 of the 36 drawered receipts pin no value at all** — `assert f(x) == EXPECTED` compares against a *name*, which is a stronger statement of the old value than a literal and which a file-reading rule cannot see. **The suite found two more of this shape immediately**: the monorepo helper-import fixture, whose reproduction compares against a name its own test module defines, and the numpy container fixture, which compared two computed values; both are recorded in the tests rather than worked around, and the numpy one had its right-hand side changed to the literal its base tree already states. Both limits are candidates for a narrower or wider v4 and both move what publishes, so neither was done here.
- **D-125 and D-128 point opposite ways, on purpose.** D-125 took this corpus from 12 publications to 24; D-128 takes 27 to 14. The owner's instruction was to keep D-125 and fix D-127, and the net is roughly the pre-D-125 volume with the control publication removed — which is the position those two decisions together were meant to reach.
- **Audit chain (D-121).** `v1` and `v2` receipts keep their own field sets, their own digests and their own rules: D-120's constant rule now applies to `v2` and `v3` and still not to `v1`, and D-128's value rule applies to `v3` alone. A version this module does not know still fails closed. Bundles written under `v2` therefore still verify as what they were.
- **Cost:** $0.00. The replay is worktrees and disk.
- **Reversal:** set `INTENT_POLICY_VERSION` back to `attest.intent.v2`; the value fields stop being part of the recorded policy and the rule stops applying, with every `v3` receipt still verifiable under `v3`.
- **RED:** `tests/test_intent_value_change.py::test_the_jinja_control_goes_to_the_drawer` (the `G-NULL-001a` control, with the published reproduction verbatim), `::test_a_value_nothing_in_the_base_specifies_goes_to_the_drawer`, `::test_a_specification_the_same_change_rewrites_goes_to_the_drawer`, and the positive control `::test_a_value_the_base_specifies_and_the_change_leaves_alone_publishes`. Confirmed failing on `9308e17`: the discriminator there returns `regression_reproduced` and no verdict for both real `ac3ac6c9` receipts, on the real base and head trees. `tests/test_executor.py::test_differential_certification_requires_the_head_code_to_misbehave` carries the cost as a row of its own table — the same defect certifies with a base test stating the value and drawers without one.
- **Trace:** `RISK-CERT-01`, `INV-CERT-001`, `INV-TRUTH-001`; `G-NULL-001`, `G-NULL-001a`; mainline §1 condition 4; D-102, D-120, D-121, D-125, D-127.

### D-129 — The product speaks at four levels, each with a non-model adjudicator; the only integration is an Action and a Secret

- **Date/status/scope:** 2026-09-04 · active, owner-directed (decision 4 of 2026-09-04c) · `docs/mainline.md` §1 (condition 2 amended), new §1.1, §1.2, §1.3; `AGENTS.md` §10 compact copy.
- **Decision (a) — four levels, one rule.** **The LLM thinks; an algorithm decides whether it may speak.** **red** = a differential receipt; **gate** = an executable failure of new code on a witnessed reachable input (N-01); **yellow** = the model states premises, a deterministic checker verifies each one, only verified premises appear in the text and the confidence is a function of which ones were; **green** = a computable structural measure with at least two concrete coordinates, the model called once afterwards to translate it and propose a fix. Every level's adjudicator calls no model, and a level with no working adjudicator ships nothing.
- **Why condition 2 had to be amended.** It required a differential receipt for *every* author-visible finding, which made three of the four levels unshippable by definition rather than by argument. It now requires the evidence form of the finding's level plus that level's adjudicator, and keeps the offline-verifier requirement where the form is a receipt. The amendment is marked in place so an older reference to "condition 2" still lands on the same clause.
- **Decision (b) — one integration, no keys.** GitHub Action plus a repository Secret, and nothing else. The consuming repository holds its own `ANTHROPIC_API_KEY`; the product does not touch, store, transmit or log a key, in any log line, ledger, receipt, bundle or error message. No hosted service, no proxy, no key upload, no connect-your-account flow. **`attest init` is demoted to an optional convenience and ordered last**, and nothing depends on it; the quickstart's first screen is the workflow file itself.
- **Decision (c) — v3 → green → gate → yellow.** Green is first because it costs zero execution and near-zero API — the measure is computed deterministically and the model is called only after the evidence holds — so it is the cheapest available test of the architecture itself. Gate is second because it needs a reachability witness the product does not have. Yellow is last because a premise checker is the largest new deterministic surface and the easiest to fake; it should follow two demonstrations of the pattern rather than lead them.
- **What moves on the mainline.** **N-01 leaves the "off the mainline until after L-01" list** and becomes the gate level. Nothing else moves: S-*, X-03, R-04, the pricing/F research and any whole-repository scan stay off it.
- **Limits:** this is a definition, not an implementation. Only red exists today; green v0 ships in the same window as one class (D-130) and is not the level. The confidence function at yellow is named, not specified. "Reachable input" at gate has no witness format yet, and inventing one is that step's work.
- **Cost:** $0.00.
- **Reversal:** the amendment to condition 2 is one clause; §1.1–§1.3 are additive.
- **RED:** none — no behaviour changes here. The levels' REDs are owed by the steps that build them; green v0's is `tests/test_structural_duplication.py`.
- **Trace:** mainline §1, §1.1, §1.2, §1.3; `AGENTS.md` §10; N-01; D-128, D-130.

### D-130 — The green level v0: repeated implementation, found by an algorithm and worded by one

- **Date/status/scope:** 2026-09-04 · active, owner-directed (decision 6 of 2026-09-04c) · new `src/attest/review/structural.py`, `tests/test_structural_duplication.py`, `scripts/corpus/structural_offline.py`; [offline measurement](docs/acceptance/2026-09-04-structural-offline.md).
- **Decision:** one class and no more — **the same implementation in two or more places**. A finding exists when two function bodies normalise to token sequences whose similarity clears **0.92**, both clear a size floor (40 normalised tokens, 4 statements), and **at least one is in a file this change touched**. The evidence is the two coordinates and the measure; the publication category is `structural`.
- **The rule this level exists to demonstrate.** *The LLM thinks; an algorithm decides whether it may speak.* Detection calls no model and cannot reach one — `collect` and `find_duplicate_implementations` take no provider. A model is called **once**, in `describe`, strictly after the finding already exists, and only to say it readably and propose a fix.
- **The wording is adjudicated too, and that is the novel part.** `inadmissible_phrase` refuses a fixed list of coordinate-free hedges — "may", "possibly", "consider", "likely", "可能", "建议重构" — and it runs on **the model's sentence exactly as it runs on ours**. A hedging model is dropped, the reason is recorded rather than hidden, and the deterministic evidence sentence stands alone. A model failure is silence, never a hedge.
- **What normalisation keeps and erases, and why.** Identifiers, argument names and literal *values* are erased, so a renamed copy still matches; attribute names and callee names are kept, so two functions that merely share a shape do not. Docstrings are dropped before the walk — a copied docstring is not a copied implementation. Test modules are excluded: duplicated test bodies are a fact of life, not a claim worth making.
- **Measured offline on real traffic, $0.00 and zero model calls ([report](docs/acceptance/2026-09-04-structural-offline.md), [data](docs/acceptance/evidence/2026-09-04-structural-offline.json)).** The E-04 stratum-v2 population, 100 units of the owner's most recent traffic: **33 units change Python, 8 of those speak, 12 findings — a 24.2% trigger rate over Python-touching units, 8% over all units.** The 58 `G-NULL-001a` null controls: **13 of 58 speak, 14 findings, 22.4%**.
- **The control rate is not a false-publication rate, and the report says so.** Duplication is a property of the code, not of whether the commit was a defect, so a null control speaking is expected and is not an error. Green makes no claim about defects; it claims a structural fact. **That is why this level is cheap to be right about, and it is also the limit of what it is worth.**
- **Manual adjudication of five, sampled one per distinct pair and repository:** `_local_extrema` copied byte-for-byte into a second `us-stock-helper` module (**true, worth saying**); `_validate_unit_interval` / `_require_probability` in `Corum`, the same validation with different return types (**true, the most useful of the five**); `_classify` / `classify_subject` in `Attest`, a script re-implementing a library function with different return values — a latent divergence (**true**); `show_file_at` duplicated in `Attest`'s own `eligibility.py` and `planner.py` (**true, exact**); `_seconds` / `_env_fetch_deadline_seconds` in `us-stock-helper`, the same env parser where one adds an upper bound (**borderline — the claim "the same implementation" overstates it**). **Four clearly true, one overstated, none false.**
- **Limits:** it is a clone detector, not a defect detector, and nothing here is wired into the publication path — that is the green level's own step, not v0. The 0.92 threshold, the 40-token floor and the ±15% length window are chosen, not tuned on a held-out slice; the borderline finding above suggests the threshold is if anything slightly low for the sentence it produces. The banned-phrase list is a denylist and an English/Chinese one. The pairwise search is bounded (2,000,000 comparisons, 50 pairs reported) and does not scale to a whole-repository scan, which is off the mainline anyway.
- **Cost:** $0.00. Zero model calls, by construction, in both the detector and the measurement.
- **Reversal:** delete the module; nothing imports it from the review path.
- **RED:** `tests/test_structural_duplication.py::test_a_renamed_copy_is_found_with_both_coordinates_and_a_measure`, `::test_the_same_shape_doing_different_work_is_not_a_finding` (the false-positive control), `::test_the_wording_adjudicator_refuses_a_hedge_wherever_it_comes_from`, `::test_no_model_is_called_before_the_evidence_holds`, `::test_the_detector_is_order_invariant_and_deterministic`.
- **Trace:** mainline §1.1 (green), §1.3 (order); D-129.

### D-131 — `G-NULL-001a` published again under v3: a generic constant is not a specification, and the pinned set is not the failing assertion's

- **Date/status/scope:** 2026-09-04 · **open — root-caused, not fixed** (the owner's rule for this window forbids both fixing and resuming) · observed by `scripts/corpus/null_study.py` on the same preregistered population; no product change made; [report](docs/acceptance/2026-09-04-g-null-001a-resumed.md).
- **What happened.** The 43 unrun controls were resumed after the offline replay showed zero control publications under `attest.intent.v3`. **36 ran; the 36th published, and the publication is wrong.** 51 of 58 controls are now run, 7 never reached, $1.0747 spent of $18.
- **The control.** `urllib3 c7b9adcb` (2023-12-28, *"Fix TestBrokenPipe on macOS"*), 980 days old, untouched. Three lines that deliberately widen a tolerated-errno set from `EPROTOTYPE` to `EPROTOTYPE` **and** `ECONNRESET`, with the comment updated in the same diff. The generated test asserts that `ECONNRESET` still propagates; it does not, on purpose.
- **Root cause, from the receipt's own record.** v3 **classified it correctly** — `value_mismatch: true` — and then admitted it, because `pinned_values` is `["False"]` and `urllib3`'s own tests assert `is False` somewhere, so `value_specified` is non-empty. Two compounding defects:
  1. **A generic constant is not a specification.** `False`, `None`, `0`, `True` appear in almost every tree, so the rule is satisfied by a coincidence of vocabulary. **D-128's own report named this as v3's weakest point** — four of its ten surviving receipts rest on exactly such constants — hours before it was observed.
  2. **The pinned set is every `assert` in the test, not the assertion that failed.** Here the failure is a bare `raise AssertionError(...)` in a stub class the test defines, so the constant that carried the publication is unrelated to the failure. The rule is *stated* about the failing assertion and *implemented* over all of them, and on this test the approximation is not close.
- **What it does and does not do to D-128.** It does not retract it: on this same population v3 drawers both `jinja ac3ac6c9` receipts that `v2` published, and the corpus replay's 55 → 19 receipts and 27 → 14 publications stand. It retracts any reading of D-128 as *sufficient*: **1 wrong publication in 36 controls under v3**, a number too wide to quote as a rate, and biased downward by a population of cold code.
- **Two candidate narrowings, described and implemented nowhere** (both move what publishes, so both are the owner's): exclude generic constants from the pinned set, requiring at least one distinctive value; and pin only the constants of the assertion that actually failed, read from the head runs' JUnit message rather than from every `assert` in the source.
- **Cost:** $1.074700; $16.925300 of the reservation released.
- **Trace:** `RISK-CERT-01`, `INV-CERT-001`, `INV-TRUTH-001`; `G-NULL-001`, `G-NULL-001a`; mainline §1 condition 4; D-102, D-127, D-128.
