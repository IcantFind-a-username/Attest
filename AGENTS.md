# AGENTS.md — development guide for coding agents

This file is the standing instruction set for any coding agent working in this
repository. It is self-contained: everything needed to continue development is
here or in files referenced by relative path. Follow it exactly; do not re-open
settled decisions (they live in DECISIONS.md with reversal conditions).

## What this project is

**attest** — fast, precise, evidence-first AI code review
(超快、超准、有证据). It says at most 3 things per PR, in under 60 seconds,
each with evidence you can click and re-run — and says nothing rather than
something wrong. True positives outrank everything; we do not compete on
coverage, style advice, or comment volume.

The statistical core is a sequential betting engine (e-process): each candidate
finding is a wager, evidence purchases multiply a wealth process, and **only the
wealth threshold decides who speaks** — surface at wealth ≥ 1/alpha, discard at
≤ alpha, drawer otherwise. No vote counting, no self-reported confidence scores.

## Current state (2026-08-29)

- `main` @ `71db3f4` (tracked files clean). Phases 0–2 complete, including
  live-API validation (real review in 11.1s wall clock, $0.04; negative control
  silent; V-channel refutation path exercised on real data). An
  `ANTHROPIC_API_KEY` exists as a user-level environment variable on this
  machine (new terminals inherit it; long-running processes may need
  `[Environment]::GetEnvironmentVariable('ANTHROPIC_API_KEY','User')`).
- 128 tests green, coverage 98% (core 100%), ruff + mypy clean.
- Owner has approved continuing. Current work: **Phase 3** (see Roadmap).

## Ground rules (non-negotiable)

1. **Git discipline**: conventional commits (`feat:`/`fix:`/`chore:`/`docs:`/`test:`);
   feature/fix work goes through `feature/*` / `fix/*` branches merged after
   self-review (small docs/chore commits directly on main are acceptable —
   existing history has both). **The rule: no AI-assistant or vendor-agent
   names — including your own — in commit messages, branch names, code, or
   comments.** A `commit-msg` hook backstops part of this (it greps a couple of
   name patterns); the hook is a backstop, not the definition — the rule covers
   every assistant name whether or not the hook catches it. Never bypass the
   hook (`--no-verify` forbidden), never weaken it. Model identifiers needed as
   product data live only in `src/attest/data/pricing.toml` (D-002); when a
   commit touches them, phrase the message as "default model id", never the
   name itself.
2. **Read-only paths**: `C:\Users\user\Desktop\Corum` and
   `C:\Users\user\Desktop\attest-seed` are research archives. Never modify,
   never commit there, never "fix" anything in them. (They may be absent in a
   sandboxed environment; they are not needed to build.)
3. **No remotes, no publishing**: do not create or push to any remote, do not
   publish to PyPI or any marketplace, until the owner explicitly says so.
   Local git only.
4. **Spend**: development API budget is **$10 total**; log every call in
   `DEVSPEND.md` (failed $0 calls noted as such). Never print or echo API keys;
   verify presence by length/prefix only. The product's per-PR budget knob is
   not your development budget.
5. **Third-party repos**: dogfood targets are local clones for read-only
   analysis. **Never** post comments, PRs, or issues to repositories you do not
   own.
6. **Green gate per phase**: `pytest`, `ruff check`, `mypy` all clean;
   coverage gate is on the TOTAL for `src/attest`: ≥ 90% overall and ≥ 99% for
   `attest.core` (current: 98% total, core 99–100% per file). First chore of
   Phase 3: add `fail_under = 90` to `[tool.coverage.report]` so the gate is
   enforced, not honor-system.
7. **Decision log**: every non-trivial tradeoff gets one line in `DECISIONS.md`
   (what / why / when reversible). Highest existing number is **D-014** (note:
   file order is not numeric — D-005 appears last); continue from D-015. The
   independent-review-before-merge pattern (D-014 caught 8 real defects) is
   expected for every phase.
8. **Stop and ask the owner** before: changing any factory statistical constant
   (default alpha, channel caps, LR schedules), anything that touches a red
   line below, any remote/publish action, or exceeding the spend cap.

## Architecture red lines (audit-derived; violating one = rework)

1. **No quorum or vote-count gates, ever.** Only the continuous wealth
   threshold decides speech. The 3-findings cap governs *placement* (top-3 by
   wealth surface; the rest stay visible in the drawer), never suppression.
2. **Repeated samples from one model are a correlated panel.** Independence
   assumptions fabricate confidence. The S-channel diminishing schedule
   (D-007: 2.00/2.64/2.95/3.00/3.00, cap 3) exists for this — do not
   "simplify" it into independent multiplication.
3. **VERIFIED is a strong feature and a surface-brake, never an unconditional
   pass.** Generated repro tests can encode the model's misreading; treat them
   skeptically.
4. **Any new threshold must be shown achievable before adoption**
   (oracle-feasibility; D-008 is the worked example: with factory caps
   S·T = 9 < 10 = 1/alpha, so the gate is *intentionally* unreachable without
   verification, and the CLI discloses this every run).
5. **No recalibration below 500 ledger labels; at ≥500, global only, never
   per-repo.** (Corum ports for the recalibration milestone are scoped in
   D-005 — do not port earlier.)
6. **Fork PRs: never execute head code in a privileged context** (secrets or a
   write token present). See Phase 3 notes.

## Code map

```
src/attest/core    betting engine library (numpy-only): tables, betting,
                   allocation, exploration, monitor, engine, stream;
                   demo_compat pins the seed experiment record
src/attest/review  product pipeline: diffs → proposer → schema → dedup →
                   channels (S/T/V) → gate → report; plus budget, ledger,
                   config, tier0
src/attest/cli     entry points: review / verify / feedback / stats
src/attest/data    pricing.toml (model pricing + default model id)
tests/             128 tests incl. regression pins to the seed experiment —
                   never weaken a pin to make a change pass
```

Key invariants already implemented (do not regress):

- **Finding schema, four mandatory parts**: `claim`, `anchor` (file+line, must
  fall inside the diff hunks — validated), `failure_scenario`,
  `falsification_plan`. Missing any ⇒ candidate discarded.
- **Budget pre-charge** before every call; exceed ⇒ explicit DEFER with reason.
- **Ledger** `.attest/ledger.jsonl` (gitignored) records reviews, spend,
  verify/feedback labels, alpha_tightened events. Alpha auto-tighten needs ≥10
  labeled surfaced findings and a label-count watermark (D-009, D-014).
- Factory channels: S ≤ 3 (schedule), T ≤ 3, V = 20 reproduced / 0.5 failed.
  Default alpha 0.1.

## Roadmap (owner-approved order; finish a phase → green gate → stop-check → next)

### Phase 3 — GitHub Action shell + CI auto-verify (built together)

Rationale: D-008 means the bot cannot autonomously surface anything without a
V channel; in CI the repo is checked out, so the `falsification_plan` can
actually run. Shipping the Action without the executor would ship a bot that
can never speak.

Settled design points (do not re-derive):

- **Layout**: `action.yml` (composite) at the repo root, so the repo itself is
  consumable as `uses: <owner>/attest@<ref>` once a remote exists. Workflow
  templates go in `examples/`.
- **Install path**: the action installs the package **from its own checkout**
  (`uv pip install "${{ github.action_path }}"` into a uv-managed venv via
  `astral-sh/setup-uv`). No PyPI involved — this resolves the no-publishing
  rule; `uvx`-from-PyPI is a post-publish optimization, not Phase 3.
- **Two-stage comment, red-line-1-safe semantics**: the fast (<60s) post is a
  **status-only sticky summary** ("review running, N candidates under
  verification") — it names NO findings. Findings appear only after the gate
  passes (wealth ≥ 1/alpha, i.e. after verification), as batched inline
  comments + summary update-in-place. If verification exceeds its time box
  (default 10 min), the summary reports DEFER with reason. Only the wealth
  threshold ever decides speech.
- Permissions `contents: read`, `pull-requests: write`; one `concurrency`
  group per PR with cancel-in-progress to stop duplicate spend.
- **Evidence executor lite**: generate a focused repro test from
  `falsification_plan` (Python targets first), run time-boxed and
  resource-limited in the runner; block network for the test process where the
  platform allows (document the limitation on hosted runners — there is no
  global network-off switch). VERIFIED only on a genuine failing run (red
  line 3 applies to generated tests).
- **CI credentials/spend**: model key = `ANTHROPIC_API_KEY` repo secret;
  default model comes from `pricing.toml`. During development and acceptance,
  CI spend counts against the $10 dev cap and gets logged in DEVSPEND.md.
- Fork PRs in v1: skip with a clear note (no secrets, no execution of head
  code); document the unprivileged-job + `workflow_run` two-workflow pattern
  for later.
- **Build vs acceptance are separate gates**: everything above is built and
  tested locally (unit + integration with a mocked GitHub API + `act` if
  useful) with **no remote created**. The live acceptance run — scratch repo,
  real PRs — happens only after the owner creates the remote and approves the
  push (ground rules 3/8). Acceptance criteria, run by the owner: first status
  comment < 60s; a planted-bug PR gets its finding verified and posted; a
  negative-control PR gets zero finding comments; all spend within budget;
  ledger rows written for every event.

### Phase 4 — feedback flywheel

- Read emoji reactions on our own past comments on the next run; `/attest`
  slash commands (`dismiss`, `verify`) gated to OWNER/MEMBER/COLLABORATOR.
- Ledger on an orphan branch `attest/ledger` (append-only JSONL;
  fetch → append → push with bounded jittered retry; `GITHUB_TOKEN` pushes do
  not retrigger workflows).
- `attest stats` merges local + branch ledgers; precision SLA (≥90% on
  surfaced findings) computed and reported from real labels.

### Phase 5 — hardening for first external users

- `.attest.toml` reference docs, README quickstart ≤ 5 lines, error-message
  pass, cross-platform sanity (Linux CI runner is the Action's reality).
- **STOP before any publish** — owner decision.

## Working style

- Continuous small increments; run an independent self-review pass before
  merging each phase branch (list concrete defects with file:line, fix the
  confirmed ones, log the pattern in DECISIONS.md).
- MVP-first bias: build the smallest thing that can be tested for real, test
  it against reality, then decide the next step from evidence.
- Windows dev box: `.venv\Scripts\python -m pytest` / `ruff check` / `mypy`;
  Python 3.14 works. The Action targets Linux runners — keep code
  cross-platform (pathlib, no shell-isms).

## External references (context, not required to build)

- `C:\Users\user\Desktop\ATTEST-HANDOFF.md` — original owner handoff (v2)
- `C:\Users\user\Desktop\attest-seed\bettingdemo\RESULTS.md` — seed experiment
  record the regression pins trace to (read-only)
- The Corum repository — the research ancestor; its preregistered negative
  result is why the red lines above exist
