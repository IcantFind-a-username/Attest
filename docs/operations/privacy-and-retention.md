# Privacy and retention

## What leaves the repository

### Every model call, one row each

Checked against the code on 2026-09-09, call by call, not from memory. There are **four**
paths that reach a model and **two** author-visible levels that reach none.

| call | when | what is sent | bound |
|---|---|---|---|
| **proposal** (`propose_plan` → `SYSTEM_PROMPT` + `build_prompt`) | `k_samples` times per change unit, on every review | the **unified diff of the change unit**, and — under `CONTEXT_PREAMBLE` — the retrieved context the planner packed: the head file's **module imports**, the **head definition** enclosing each hunk, the **merge-base definition** of the same symbol (the "old side"), **call sites outside the diff**, and **existing test functions naming the symbol** | one unit is packed to `MAX_UNIT_CHARS` = **30,000** characters of diff + context; a single file's block larger than that becomes its own unit and may exceed it |
| **probe generation** (`generate_probe` → `PROBE_SYSTEM` + `_generation_prompt`) | once per candidate that reaches verification, up to `MAX_PROBE_ATTEMPTS` | the candidate's own four fields (**claim, failure scenario, falsification plan, anchor**), then `generation_context`: the head file's imports, the **head and merge-base source of the enclosing definition**, **every signature in the anchored file**, the **nearest test module's imports, fixtures and helpers**, and the names of existing tests that reference the symbol — plus a **200-line window of head source** around the anchor | `generation_context` is truncated at `MAX_GENERATION_CONTEXT_CHARS` = **20,000** characters; the anchor window is `MAX_CONTEXT_LINES` = **200 lines** |
| **probe/schema repair** | only when the previous answer did not match the schema | the same prompt again, with the schema error | precommitted attempt count; never outcome-aware (`INV` 13) |
| **green wording** (`structural_notes` → `WORDING_SYSTEM`) | once per surviving green finding, **after** the measure already holds | **the deterministic evidence sentence only** — two `path:line-line` coordinates, the two function names, two token counts and a similarity number. **No source code of either span is sent.** The model's answer is advice, and dropping it changes no claim | `WORDING_MAX_TOKENS` = 200 |

**Two levels send nothing at all.**

- **yellow (a)**, the impact scope, is computed entirely from `ast` and the two git trees.
  No model is called, and `$0.00` is spent on the level.
- **gate** (shadow) reaches a model only through the probe path above, and publishes nothing.

**One level is off, and this is what it would send if it were on.** Yellow (b)'s
null/Optional class (`HYPOTHESIS_SYSTEM`) sends the **whole body of each changed function**,
head side. It is **off** by default since D-169. Yellow (b)'s exception-propagation class is
`ast`-only and sends nothing; it is in shadow.

### `context_strategy = "package-cache"` — what it adds

Not the default (`r01` is). When set, every proposal sample, the probe generation and its
repair are additionally given **one shared block containing the anchored module's whole
package and its `tests` directory**, bounded by `MAX_PACKAGE_BLOCK_CHARS` = **120,000**
characters. It is sent as one `cache_control` block, so it is transmitted once per cache
window rather than once per call — but it *is* transmitted, and it is a much larger slice of
the repository than the default strategy sends. Set it only where that is acceptable.

### GitHub

GitHub receives the status comment and inline comments: only verified findings (claim,
location, the generated test, run summaries, logs bounded to 6,000 characters, bundle path),
the green and yellow notes described above, and the collapsed run status (counts and failure
categories, **never** an unverified candidate's claim, file or line).

### Everything else

- Nothing else is sent anywhere. There is **no telemetry**, no hosted service, no proxy.
- **No credential is ever part of any prompt.** The API key is read from the runner's
  environment by the privileged controller and is never written to a prompt, a ledger, a
  bundle, a log line or an error message.
- What the model provider does with what it receives is governed by that provider's own API
  policy, not by `attest`. Retention on the provider's side — how long prompts and
  completions are stored, and under what terms — is outside this tool's control and outside
  the guarantees below; the operator should read their provider's API terms.

## What stays local

Under `.attest/` in the reviewed repository (gitignored): the ledger, candidates, attempt
cache (model responses, bounded), reproduction work directories, evidence bundles and the
controller key. These contain repository source excerpts and model outputs; treat the
directory as source-equivalent.

## Retention (defaults)

- evidence bundles of published findings: kept indefinitely (they are the certificate);
- reproduction work directories: removed after the run (worktrees) or safe to delete;
- attempt cache: safe to delete at any time; a deleted cache means a repeated run buys new
  samples;
- ledger: append-only; rotation is the operator's choice;
- controller key: rotate by deleting `.attest/controller.key`; earlier bundles then verify
  structurally but their seals report a different key id.

## Secrets

Model and GitHub credentials are read by the privileged controller only. Head code runs in a
container with `env -i` and exactly the request environment; the controller key is outside
every mount. `attest` never logs, commits or echoes credentials; ledger text is redacted for
known credential names.
