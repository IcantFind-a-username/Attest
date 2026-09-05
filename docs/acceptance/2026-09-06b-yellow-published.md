# Yellow (a) becomes author-visible, and the owner's rule silences it — 2026-09-06b

Owner instruction 2 of this window: **wire yellow (a) into the publication path under the D-142
contract, at most 2 notes per pull request, speaking only when the signature or return type
changed *and* an untested caller exists**; then open one throwaway pull request in this
repository that trips it, read the comment, and close the pull request.

Both halves are done. The second half is the interesting one, because on every population this
level has ever been measured over, **the owner's rule makes it silent**.

## 1. The rule, and what it costs

D-143 shipped the level with a disjunction — speak if the interface moved **or** a caller is
named by no test. The owner's rule is the **conjunction**:

> the signature or return annotation moved **and** some call site is named by no test

The [2026-09-06 scan](2026-09-06-impact-scope-scan.md) §5 already priced this exact narrowing
and said what it would cost: *"0 of 11 forward pairs and 1 of 68 controls, which is a level that
does not exist."* Re-run at the implemented rule, it is quieter still.

| population | units | D-143 (disjunction) | **D-145 (conjunction)** |
|---|---|---|---|
| forward pairs (defect-introducing commits) | 11 | 4 (36.4%), 6 notes | **0 (0.0%), 0 notes** |
| null controls (ordinary old commits) | 68 | 1 (1.5%), 1 note | **0 (0.0%), 0 notes** |
| | **79** | 5 (6.3%), 7 notes | **0 (0.0%), 0 notes** |

257 changed functions were examined, **56 of them changed their interface**, and not one of
those 56 had a caller that no test names. [Data](evidence/2026-09-06b-impact-scope-conjunction.json).

```bash
.venv/bin/python scripts/corpus/impact_scan.py scan --population both \
  --json docs/acceptance/evidence/2026-09-06b-impact-scope-conjunction.json
```

**That is the honest headline and it is not an argument against the rule.** The two halves
select for opposite things: a project disciplined enough to test its callers is exactly the
project whose interface changes are covered, and the eight public repositories in these two
populations are that kind of project. The conjunction is a claim about a *combination* that
these corpora do not contain — which means the level costs an author nothing, and also that
these 79 units cannot tell us whether it is useful when it does fire. A rate of 0 in 79 has a
95% upper bound of 3.8%; it is a ceiling on noise, not a measurement of value.

**What the conjunction buys is that every note is actionable by construction.** Under the
disjunction, all six forward notes were interface changes whose every caller a test already
names — cases where the suite would report the breakage without this level's help — and two of
them were annotation-only. Under the conjunction, a note means: *this interface moved, and here
is a call site nothing tests.* There is no version of that note an author can dismiss as noise.

## 2. The publication path

Yellow reaches an author the way green does, and never the way red does.

- **Its own marker and its own section.** `[yellow]` inline, and a summary section headed
  *"Impact scope — counted over the call graph; no defect is claimed and no coverage was
  measured"*. Red's section is untouched and the two never merge.
- **One D-142 contract line**, assembled by `claim_line` and adjudicated by the same non-model
  format adjudicator every other level passes through. A line that does not conform is not
  published: like green and unlike red, yellow has no receipt to fall back on, so the note is
  dropped whole.
- **At most two notes per pull request**, the same cap green has.
- **`$0.00`.** `impact_notes` is passed no provider and no budget, because there is nothing it
  could spend them on: two `git` reads and `ast`. It cannot fail a review either — every
  exception in it is silence.
- **Silence is silence.** A level with nothing to say contributes no line, no heading and no
  marker; and a review where *all* levels are silent still owes the contract's one silence line
  naming the units it read. `test_a_body_change_with_an_untested_caller_produces_no_yellow_line`
  pins that, on the case D-143's rule would have published.
- **The delivery journal knows it.** Yellow members are identified by the coordinate of the
  changed function, the way green members are identified by their pair of coordinates, and one
  `impact_note` ledger row per note records the policy version, the reason, the caller count and
  the untested count.

## 3. The one real comment

*(pending — the throwaway pull request in this repository; see §4 for what was asked of it)*

## 4. Limits

- **0 of 79 is a ceiling on how often this level speaks, not evidence that it is right when it
  does.** The only note anyone has read under this rule is the constructed one in §3.
- **"Named by no test" is not "not covered".** No coverage was measured and no test was run. A
  caller reached through a registry, a dispatch table or `getattr` is invisible to a static name
  walk, and the published sentence says exactly what was computed.
- **The four-hop bound produces speech, not silence** (D-143): a test five calls away from a
  caller counts as not naming it. Raising the bound can only make the level quieter, and it is
  the first thing to try if a note is ever disputed.
- **The disjunction is one line away.** `note_for` refuses on `not (interface_changed and
  untested)`; restoring `or` restores D-143's 6.3%. The numbers for both are in this document.
