# Failure-mode copy (L-01)

What the author sees, in the order they are likely to meet it. Every line below is the
literal text or its stable prefix; the statistical vocabulary never appears.

Two rules this table is checked against, and was re-checked against on 2026-09-09 by
constructing each failure and recording what came out:

1. **every failure has copy of its own and a next step.** A generic sentence for a cause the
   product can name is a defect, not a safe default;
2. **no failure ever reads as "reviewed, nothing found".** A silence that means *nobody
   looked* and a silence that means *nothing met a bar* are different claims, and the line
   says which.

| situation | what is shown | what to do |
|---|---|---|
| review finished, something verified | `Verified findings (each backed by a reproduction receipt):` then per finding the claim, `Finding ID`, `Verified: the generated test failed on head in 3/3 runs and passed on the merge base in 3/3 runs.`, the test, the command, the logs, the bundle path | run the command yourself; `attest verify --bundle … --require-seal` |
| review finished, nothing verified | `No finding was verified by a reproduction; abstained.` plus a collapsed `Run status` | read the status: candidates, eligible, attempts, and each failure category |
| fork pull request | `fork pull requests are skipped before model or head-code execution` | expected; open the pull request from a branch of the repository |
| model credential missing or revoked | the Action exits **2** before any head code runs, with a message that names the secret and the page to create it: `error: attest did not run -- the model API key secret is empty or missing.` then `Nothing was sent anywhere. No model was called, no code left this runner, and no key was read, stored or logged.`, the repository's own `settings/secrets/actions/new` URL, and `Name: ANTHROPIC_API_KEY`. A missing `github-token` gets its own message saying Actions supplies it and nothing needs creating | create the secret; nothing was executed. *(Corrected 2026-09-09: this row quoted a sentence the product does not print.)* |
| budget exhausted | `DEFER: budget: …` | raise `budget-usd` on the Action or wait for the next push |
| the budget ran out part-way through a large change | `read N of M units, budget-limited` in the run status, with the omitted units and the call that would have exceeded the budget | raise `budget-usd`; the M − N unread units were **not** reviewed, and the silence covers only what was read. Source files are read before documentation, so the budget reaches code first |
| merge-base unavailable | `merge-base unavailable: fetch the base branch history (fetch-depth 0)` | set `fetch-depth: 0` in the checkout step |
| isolation backend unavailable (CI) | `isolation backend unavailable: …` in every reproduction's status line | the runner has no Docker; production never falls back |
| environment bootstrap failed | `environment bootstrap failed (python 3.x, roots […]): …` | the project's manifests do not install on a slim image; see the build log tail in the status |
| the generated test was unfaithful | `unfaithful test` in the run status | nothing to do: the product declined to speak |
| the change rejects an input the merge base accepted, and the base tree does not use that input | `behavior change, intent unknown` in the run status; locally `attest stats --drawer` shows `behavior change confirmed, intent unknown (行为变化已证实，意图未知)` | nothing to do if the rejection is intended; if it is a defect, add the rejected input to a test or fixture on the base branch and the next review can verify it |
| the change rejects an input the merge base accepted, and the base tree's own tests, fixtures or docs use that input | `Behavior change (intent to confirm):` before the claim; `Verified behavior change: …` and `Behavior change: head raises … on '<input>', an input the merge base accepts and the base tree uses in <path>` | confirm or dismiss: `attest feedback <id> --dismiss` if the rejection is intended |
| no text returned by the model | `no text returned` | a provider-side failure the product records honestly; rerun later |
| head code tried to reach the network, spawn, thread, or write outside its directory | `reproduction attempted …` | the reproduction is refused and marked; the product stays silent on that candidate |
| head moved before publication | `workspace HEAD drifted from the reviewed head before publication` | push again; the review is bound to one head |
| repository disabled | `disabled by the base policy (.attest.toml enabled = false)` | intended; see the kill switch |

## The refusals that end a review in one line

Each of these is printed as a single `[silent]` line and the process exits **0** — an
unsupported project is not a failed run (D-159).

| situation | what is shown | what to do |
|---|---|---|
| the repository has no Python | `[silent] unsupported: this repository has no Python source, and Attest reviews Python; nothing was read and nothing was spent.` | nothing; attest reviews Python |
| a lock file will not parse | `[silent] unsupported: this repository's dependency lock file cannot be parsed, so the reproduction environment cannot be built; nothing was read and nothing was spent.` | fix or remove the lock file (`poetry.lock`, `uv.lock`, `pdm.lock`, `Pipfile`) |
| no docker on the runner | `[silent] unsupported: docker is not available here, and Attest runs head code only inside a container; nothing was verified.` | use a GitHub-hosted `ubuntu-*` runner; see the [support matrix](support-matrix.md) |
| pytest could not be installed into the image | `[silent] unsupported: pytest could not be provided in the reproduction image, and every claim Attest makes is a pytest run on two revisions; nothing was verified.` | check the build log tail in the run status. **This line is now decided by the step that actually failed** — a project that will not install gets *environment bootstrap failed* instead (D-175) |
| the project cannot run under a supported interpreter | `[silent] unsupported: this project declares Python outside 3.10-3.13 and pytest collected no test at all under the 3.12 Attest fell back to, so the reproduction never ran; nothing was verified -- Attest can review this repository once it runs on Python 3.10 or newer.` | the reproduction image is built on the newest supported interpreter no older than the project's own declaration; a project declaring less than 3.10 gets 3.12, and one whose code cannot *run* there installs and then fails to collect. Nothing to do until the project supports 3.10 or newer; see the [support matrix](support-matrix.md) (D-186, repairing D-185) |

## The silences, and which is which

A wholly silent review prints exactly one line in a fixed shape, and the middle clause says
why it was silent. All three are admitted by `output_contract.check`; before 2026-09-09 the
second was not, so the product's own adjudicator refused a line the product emits.

| verdict | line | what to do |
|---|---|---|
| everything was judged | `[silent] read 13 of 13 units; nothing met an adjudicator's bar; $0.0184, 2.5s.` | nothing. **This is an abstention, never a true negative** |
| the budget stopped it | `[silent] read 1 of 13 units; the budget ceiling was reached; 4 candidate(s) were not verified; $1.0000, 61.2s.` | raise `budget-usd`; the 12 unread units were **not** reviewed |
| the host could not run the executor | `[silent] read 3 of 3 units; executor unavailable: process containment unavailable for privileged POSIX user; 4 candidate(s) not verified; $0.0184, 2.5s.` | **nothing was judged.** Run the job unprivileged, or on a GitHub-hosted runner (D-177) |

## The provider

| situation | what is shown | what to do |
|---|---|---|
| every proposal call was rate-limited or refused for capacity | `DEFER: the model API refused every proposal for rate or capacity (HTTP 429/529); nothing was spent and nothing was reviewed -- re-run this job, or lower \`samples\` if it happens on every run` | re-run; nothing was charged (D-179) |
| the runner cannot reach the model API | `DEFER: the model API could not be reached from this runner (network or DNS); nothing was spent and nothing was reviewed -- check the runner's egress, then re-run this job` | check egress from the runner (D-179) |
| every call failed for some other reason | `DEFER: all provider samples failed or were malformed` | read the per-sample notes in the run status; the cause is not one the product can name |
| `budget-usd` is zero or not a number | `error: budget must be a finite positive number of US dollars: set the Action's \`budget-usd\` (or \`--budget\` locally) above 0, for example 1.00`, exit 2 | set a positive `budget-usd` (D-179) |
