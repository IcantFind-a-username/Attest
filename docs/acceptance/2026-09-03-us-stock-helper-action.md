# The Action on an outside repository — installed, opened, and blocked on a missing secret

**Owner decision 3 of 2026-09-03g.** Three remote writes were authorized against
`IcantFind-a-username/us-stock-helper` and exactly three were made. The Action reached a
GitHub runner on that repository for the first time and **could not review anything**: the
repository has no `ANTHROPIC_API_KEY`, so the entrypoint refused before any model call.

## 1. What was written

| # | write | result |
|---|---|---|
| a | branch `attest/enable-review`, [pull request #3](https://github.com/IcantFind-a-username/us-stock-helper/pull/3) adding `.github/workflows/attest-review.yml` at `IcantFind-a-username/Attest@v0.1.0-pilot.1`, same-repository branches only | **open, for the owner to merge** |
| b | branch `attest/known-regression-drill-2026-09-03`, [pull request #4](https://github.com/IcantFind-a-username/us-stock-helper/pull/4) carrying one planted known regression | **open** — the drill did not complete, see §3 |
| c | close #4 and delete its branch after the Action commented | **not done**: the condition ("after the Action commented") never arrived |

Nothing else was written. No secret was created, read or changed — creating one is the
owner's to do.

## 2. The planted regression, and why it is *known*

One line of `services/analysis_core/us_stock_helper_core/indicators.py`:

```
-    result[index] = fsum(checked[index - period + 1 : index + 1]) / period
+    result[index] = fsum(checked[index - period + 2 : index + 1]) / period
```

Every SMA is now the sum of a window one bar short, still divided by `period`. It is a
*known* regression rather than a guess because the repository's own
`tests/test_indicator_series.py` catches it before anything is pushed —
`AssertionError: 80.84 != 101.9` — and that check was run locally first. The commit message
calls the change a performance tweak on purpose: the product is supposed to read the code.

## 3. What the runner did

| run | branch | workflow | conclusion |
|---|---|---|---|
| [33749058731](https://github.com/IcantFind-a-username/us-stock-helper/actions/runs/33749058731) | `attest/enable-review` | attest pull request review | **failure** |
| [33749092145](https://github.com/IcantFind-a-username/us-stock-helper/actions/runs/33749092145) | `attest/known-regression-drill-2026-09-03` | attest pull request review | **failure** |

Both failed identically, and the gate step's own log names the cause:

```
INPUT_MODEL_API_KEY:
error: trusted pull requests require both action credentials
```

The action installed cleanly from the pinned tag (`Successfully installed attest-0.0.1`,
18.8 s) and refused **before** any model call, which is the behaviour the credential gate is
for. The secret is simply absent:

```
$ gh api repos/IcantFind-a-username/us-stock-helper/actions/secrets
{"total_count":0,"secrets":[]}
$ gh api repos/IcantFind-a-username/Attest/actions/secrets
{"total_count":1,"secrets":[{"name":"ANTHROPIC_API_KEY", ...}]}
```

The owner's instruction said the secret had been added to `us-stock-helper`. It is present on
`Attest` and absent on `us-stock-helper` — most likely added to the wrong repository, or added
as a Dependabot or Codespaces secret rather than an Actions secret. There are no environment
secrets on the repository either (`environments: total_count 0`). **API spend on this item:
$0.00.**

## 4. What this does and does not establish for mainline §1 condition 1

It establishes that an outside repository can install the Action from the immutable pilot tag
and that a runner will fetch, install and start it — the first time that has happened outside
this repository. It does **not** establish the condition, which asks for a *comment*. No
comment was posted, so **condition 1 still does not hold.**

## 5. The one step that finishes it

Add `ANTHROPIC_API_KEY` to `IcantFind-a-username/us-stock-helper` → Settings → Secrets and
variables → **Actions**, then re-run the failed check on pull request #4:

```
gh run rerun 33749092145 --repo IcantFind-a-username/us-stock-helper
```

Pull request #4 was deliberately left open so that this is one command rather than a new
branch. It is labelled `[THROWAWAY — do not merge]`, only the owner can merge it, and its CI
is red by construction. Close it and delete its branch once the comment is on the record.
