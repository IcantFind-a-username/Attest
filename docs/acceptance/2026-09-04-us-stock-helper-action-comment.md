# The Action commented on an outside repository — and the comment says DEFER

Continues [2026-09-03](2026-09-03-us-stock-helper-action.md), which ended one setting short.
The owner added `ANTHROPIC_API_KEY` to `us-stock-helper`'s **Actions** secrets, merged
[#3](https://github.com/IcantFind-a-username/us-stock-helper/pull/3), and authorised the
re-run. **`gh run rerun 33749092145` now succeeds and the Action posts a comment on a
repository this project does not develop in.** The comment is an abstention.

Screenshot: [`assets/2026-09-04-us-stock-helper-pr4-comment.png`](assets/2026-09-04-us-stock-helper-pr4-comment.png).

## 1. The run

| field | value |
|---|---|
| run | [33749092145](https://github.com/IcantFind-a-username/us-stock-helper/actions/runs/33749092145), job `attest`, **success in 1m37s** |
| pull request | [#4](https://github.com/IcantFind-a-username/us-stock-helper/pull/4), head `4d9b805`, merge-base `9fc9408` |
| task | `20260903-162134-ff5e0472`; policy `factory-defaults`, review policy digest `5137e2b5…` |
| Action inputs | `budget-usd` 0.60, `samples` 4, ref `@v0.1.0-pilot.1` |
| **executor backend** | **`linux-container-v1`, available** — image `attest-repro:55ef0e3569cdbbe3`, built on the GitHub runner |
| **API spend** | **$0.044403** (`ci_final`); the review itself $0.028702, `claude-sonnet-5`, 4 samples, 3,618 cache-creation then 3×3,618 cache-read tokens |

## 2. What the Action did, step by step

| stage | result |
|---|---|
| change units read | 1 of 1 planned; not budget-limited |
| candidates | 1 (`b7a7916a96`) |
| eligibility | **regression** — "definition `moving_average_series` exists at the merge-base" |
| review decision | drawer, wealth 3.0, authority `ranking` (S only; T and V unbought) |
| reproduction | **1 attempted, deferred at collection in 1.05 s**: "pytest collection/import/syntax or infrastructure failure during collection (exit code 2)" |
| certification | `not_attempted` — "execution outcome deferred (indeterminate) buys no receipt" |
| publication policy | e-value Bonferroni, α 0.1, eligible 1, family threshold 10.0, hard cap 3, mean e-value 3.0, **published 0, suppressed 0** |
| comments posted | **3 edits of one status comment** — `running`, `candidate_count`, `defer` |

The comment's whole visible text:

> DEFER: verification deferred: collection deferred: pytest collection/import/syntax or
> infrastructure failure during collection (exit code 2)

…with a collapsed **Run status**: *change units read: 1; candidates: 1; eligible: 1;
reproductions attempted: 1; certified: 0; published: 0*.

## 3. What this establishes, and what it does not

**Mainline §1 condition 1 now holds.** An outside repository has the Action installed from
the immutable pilot tag, its runner reached the model, built the production container image,
ran a reproduction inside it, and posted an author-visible comment. That had never happened.

**The planted regression was not caught.** The candidate was found and correctly ruled
eligible — Attest read the code, not the commit message, and named the right function — and
then the *generated reproduction did not collect*. This is the D-114 generation failure mode,
now observed on a GitHub runner rather than on this host. The drill's own success criterion
("the Action comments once") is met; its implied criterion ("on a known regression, the
comment is a finding") is not.

**Nothing false was published.** A silence on a known defect is an abstention, not a true
negative (`INV-MEASURE-001`, `INV-CERT-001` §8): one run, one candidate, one collection
failure. It measures no recall.

## 4. The four remote writes, and the end state

| write | result |
|---|---|
| `gh run rerun 33749092145` | success; comment posted |
| the Action's own comment (3 edits, by `github-actions[bot]`) | on the record |
| `gh pr close 4` | **closed** 2026-09-03T16:27:22Z |
| delete `attest/known-regression-drill-2026-09-03` | **deleted**; `GET /branches/…` answers 404 |

`us-stock-helper` now carries the workflow on its default branch (#3, merged by the owner)
and nothing else of this project's. No issue, no review, no reaction, no further comment.
