# Handoff — 2026-09-09 · release-readiness acceptance

`1bf4110` → `docs/release-readiness-acceptance` · **$0.00 spent** · full report:
[`docs/acceptance/2026-09-09-release-readiness.md`](acceptance/2026-09-09-release-readiness.md)

**One remote write, the one you authorised:** `fix/d-174-binding-and-bounds` pushed,
[PR #12](https://github.com/IcantFind-a-username/Attest/pull/12) opened, and you merged it.
Nothing else was pushed, nothing published, no protected parameter moved.

## Five sections, one sentence each

1. **Installable — after two fixes it did not have this morning.** A public pytest repository
   nobody here owns (`tenacity`) could not be reviewed *at all*: the image build died on
   `hatch-vcs`, and the refusal blamed pytest, which had installed fine. Both fixed; the tagged
   wheel now installs into an empty virtualenv and reviews that repository end to end from a
   scrubbed environment, producing a real green note.
2. **Useful — on the fixed sample, and only one number moved.** Yellow (a)'s control noise fell
   2.9% → 1.5%, and the note that disappeared is exactly one error class: call sites counted by
   name that do not resolve to the changed definition. Red's numbers are unchanged and are all
   K=4.
3. **The default configuration is usable, and its floor is higher than the docs said.** Below
   **$0.54** nothing can be reviewed at the factory `samples: "5"` — five samples reserve $0.16
   of output tokens against a 30% discovery share, measured on `tenacity` at $0.25, $0.50 and
   $1.00.
4. **Failure experience — three of five failures had no copy of their own.** All five now name
   their cause and a next step, and no failure can print *nothing met an adjudicator's bar* when
   nothing was judged.
5. **Maintainable — `SECURITY.md` exists, four document/implementation contradictions are gone,
   and six gates still do not pass.** No bar was lowered and the `rc` tag still says *internal
   trial*.

## FAIL, fixed (with the decision that records it)

| what was wrong | fix |
|---|---|
| a `hatch-vcs` project's image build fails; the whole repository is unreviewable | **D-176** — one tuple in `container_images.py` |
| the refusal blames pytest because BuildKit echoed a successful line | **D-175** — decide on the failing step the builder names |
| the silence line claims a clean bill of health when the executor never ran | **D-177** — a third verdict, and the shape now admits D-161's too |
| 429, and an unreachable API, both said *all provider samples failed or were malformed*; `budget-usd: "0.00"` named no input | **D-179** |
| three of four real comments told the reader nothing to do | **D-178** — an adjudicated `Action:` clause on every level |
| yellow (a)'s comment described the name-matching rule D-174 replaced | in D-178 |
| README pinned `@v0.1.0-pilot.1`; `github-action.md` used `@main` and claimed a `uv` venv; `failure-modes.md` quoted a credential message the product does not print | documents corrected, with errata visible |
| *e-value* / *family-wise error* stated as though proven | vocabulary downgraded in README, mainline, `selection.py`, `base-policy.md`; **no constant moved** — the reviewer verified this by comparing docstring-stripped ASTs |

## What the independent review found (AGENTS §11.7, `attest.certification` + `attest.execution`)

**APPROVE WITH FIXES.** Seven findings; six fixed here, one in the backlog.

| # | finding | resolution |
|---|---|---|
| **P0** | a `_version.py` **in the tree under review** could append its own `RUN` step to the generated Dockerfile — arbitrary code execution with network egress at build time. Pre-existing, and inside the function D-176 touches | fixed: the captured version is validated before interpolation |
| **P1** | a model paragraph containing `</details>` escapes the collapsed block: its text is scanned (so the note is dropped for a word the model chose) **and rendered as product copy** | fixed: `collapsed` neutralises the delimiters |
| **P1** | the 429 sentence could fire on a review of retry code — it read the model's own text — and claimed *nothing was spent* on a path where money **was** spent | fixed: only call-raised transport errors are classified |
| P2 ×3 | a swallowed ledger error reinstating the wrong sentence; a count of rows where its neighbours count findings; a reason bound that could exceed the line contract | all three fixed |
| P2 | a `check_comment` refusal leaves no trace | backlog |

Two claims of mine were too wide and are corrected in place: *"wording can never suppress a
finding"* (true of red, narrower for green and yellow) and *"a ledger this cannot read yields no
claim, never a wrong one"* (it yields a wrong one; what saves it is the unit count beside it).

## FAIL, not fixed

| what | why it is not fixed |
|---|---|
| **every empirical number in this repository is K=4; the factory setting is K=5** | measuring it costs money — §3.7 and owner item 1 |

## UNFINISHED, with what would finish it

| item | condition | cost |
|---|---|---|
| K=5 on the fixed sample | 27 reviews (the ones with a verdict) at `--budget 1.00`, `--code` pinned | **$27.00** at the cap · the full 153-review form is **$153.00** and does not fit the $29.67 remaining |
| `G-SEC-002` external observer | run the nine-class matrix **under** the kernel audit observer and publish the joint record | **$0.00**, one `workflow_dispatch` |
| `G-SEC-002` on this branch | D-176 touches `attest.execution`: one matrix dispatch on the branch + the independent review AGENTS §11.7 requires | **$0.00** |
| `G-NULL-001` | n ≥ 300 **answered** controls; the independent population answered 7 of 68 | ≈ **$53** — above the remaining cap, and it needs a corpus that answers rather than falls silent |
| `G-NEWCODE-001` 120-case pilot | progress is **0 of 445**: there is nothing to adjudicate until the reachability rule changes or owner item 2 is decided | unknown |
| `G-SHADOW-001` | one **prospective** run with an independent adjudicator; every shadow run so far is retrospective by construction | ≈ $0.02–0.19 a commit |
| **an outside real trial** | a repository **you do not own** installs the Action and runs it on a real pull request | ≈ $1 a pull request — **and nothing in this report substitutes for it** |

## What attest found in its own pull request

Reviewing PR #12, attest's yellow (a) level spoke unprompted on real traffic for the first time:
`calls_in` changed, 3 call sites resolve to it, no test names it. **Checked: true, and not a
defect** — `scripts/corpus/binding_recount.py` was rewritten for the new signature in the same
commit and runs. What it did get wrong was its own closing sentence, which still described the
name-matching rule; that is fixed. It is the fourth sample of the comment audit and the reason
the action clause exists.

## Owner items — three, each a yes/no with a default

1. **Reserve $27 to measure the factory K=5 on the 27 fixed-sample reviews that have a verdict?**
   *Default: yes.* It fits the $29.67 remaining. The full 153-review form needs a cap raise.
   Until this runs, every number the README quotes is K=4 and the shipped default is unmeasured.
2. **Does a caller that is itself a test count as a gate witness?**
   *Default: no — keep the exclusion.* Keeping it is why reachability is **0 of 445** rather
   than 3 of 445; the three surviving witnesses are all test callers. Keeping it risks silence
   on new code whose only pre-existing caller genuinely is a shared test helper; admitting them
   risks publishing a crash the change's own new test provokes. The gate stays in shadow either
   way until you answer.
3. **Change the publication rule to `V ∧ intent ∧ per-unit top 3`?**
   *Default: no.* The free replay (§0c) says it would publish **25 more** findings across 17 of
   82 recorded selections and retract none. All 25 reproduced under V and passed intent and were
   held back only by `m_u/α` — and **none was close**: their scores are 2.0–3.0 against bars of
   50–140, a factor of 17. So this is not a slightly lower bar; it removes the score threshold
   and leaves the reproduction and a display cap. Coherent, since the score was never an
   e-value — but it is the whole change, and the replay says how many, not whether any is right.
