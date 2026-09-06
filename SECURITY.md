# Security policy

`attest` runs **code from a pull request** — code its operator has not read yet — and it runs
it on a machine that holds an API key. That is the whole security question, and everything
below is scoped to it.

## Reporting a vulnerability

Open a [GitHub Security Advisory](https://github.com/IcantFind-a-username/Attest/security/advisories/new)
on this repository. That is the only channel; it is private until the advisory is published.

Please include the version or commit, the platform, and a reproduction — a diff, a generated
test, or the fixture that demonstrates it. If a proof of concept would execute against a
third party, describe it instead of running it.

**Do not** open a public issue for a vulnerability, and do not post one as a pull-request
comment.

**What to expect.** This is a research prototype maintained by one person; there is no
on-call rotation and no service-level commitment. An acknowledgement is the intent within
7 days and a first assessment within 30. If you have heard nothing in 30 days, assume the
report has not been seen and say so publicly — that is a better outcome than silence.

## Supported versions

| version | supported |
|---|---|
| `main` | yes — fixes land here first |
| `v0.1.0-rc.1` | yes, as an **internal trial ref**. It is not a public release and nothing is published to PyPI |
| `v0.1.0-pilot.1` | no. Kept only as the oldest ref a pilot may roll back to |
| anything else | no |

There is no long-term-support branch and no backporting. A fix is a new commit on `main` and,
where it matters, a new tag.

## Disclosure

Coordinated. A fix lands on `main`, the advisory is published with the commit that fixes it,
and the reporter is credited unless they ask not to be. No embargo is requested beyond the
time it takes to fix — this is a prototype with no installed base to protect.

## What is in scope

The trust boundary is: **head code is untrusted; the controller is trusted; nothing crosses.**
A report that breaks any of these is in scope.

- **Head code reading a credential.** The API key and the GitHub token are held by the
  privileged controller. Head code runs in `linux-container-v1` with an empty environment,
  and the controller key file is outside every mount.
- **Head code reaching the network.** `--network none`, plus language-level guards.
- **Head code escaping its work directory**, including through a symlink.
- **Head code forging a result** — a result bound to another request's nonce, an artifact
  whose digest does not match, an evidence bundle edited after it was sealed.
- **A pull request relaxing the policy it is judged under.** Policy is read from the
  merge-base; a head `.attest.toml` cannot loosen it.
- **A fork pull request reaching a credential or a runner step that holds one.**
- **A credential appearing in a log line, a ledger row, a receipt, a bundle, an error
  message or a pull-request comment.**
- **A published claim with no accepted receipt behind it** (`INV-CERT-001`). A false
  publication is a correctness bug, not a security bug — but a publication with *no receipt
  at all* is a break of the certification boundary and belongs here.

Where these are exercised today:

| boundary | test |
|---|---|
| fork pull request is skipped before any credential | `tests/test_action_entrypoint.py::test_cross_repository_event_skips_before_the_attest_executable_runs`, `::test_credential_free_gate_marks_cross_repository_event_untrusted`, `::test_this_repository_workflow_runs_only_for_same_repository_branches` |
| the gate step holds no credential; only the trusted path receives them | `tests/test_action_entrypoint.py::test_action_gate_has_no_credentials_and_only_trusted_execution_receives_them` |
| head code cannot read the controller's secret or key file | `tests/execution/test_linux_isolation.py::test_head_code_cannot_read_the_controllers_secret`; red-team fixtures `secret`, `keyfile` |
| the container runs unprivileged, without capabilities | `tests/execution/test_linux_isolation.py::test_the_container_runs_as_an_unprivileged_user_without_capabilities` |
| a privileged host **refuses to run** rather than running unprotected | `tests/test_executor.py::test_execute_privileged_posix_user_defers_before_running_generated_code`, `::test_execute_linux_privilege_state_fails_closed_before_generated_code` |
| credentials are dropped from the verification subprocess and redacted from the ledger | `tests/test_executor.py::test_verification_subprocess_drops_credentials_and_redacts_ledger` |
| a provider error carrying a key is redacted before it reaches a comment | `tests/test_proposer.py::test_response_fragment_is_bounded_and_redacts_known_credentials` |
| network, filesystem escape, symlink escape, process exhaustion, result forgery, bundle tampering | `scripts/release/redteam.py` — nine classes plus a positive control, run on a GitHub-hosted runner ([latest result](docs/acceptance/2026-09-07-redteam-nine.md)) |

## What is out of scope

- **Anything that requires write access to this repository, or to the runner, to begin with.**
- **The model provider.** What Anthropic does with a prompt is governed by their API terms.
  What `attest` sends is enumerated in
  [`docs/operations/privacy-and-retention.md`](docs/operations/privacy-and-retention.md).
- **Local `attest review` without Docker.** It falls back to a host adapter with *language
  guards only and no OS boundary*, and it says so in the ledger and in the run status.
  Running untrusted code that way is the operator's decision, not a defect.
- **Unsupported runners.** `macos-*`, `windows-*` and self-hosted runners are outside the
  declared platform ([support matrix](docs/operations/support-matrix.md)).
- **A false or missing finding.** Precision and recall are correctness questions; open an
  issue. A silence is an abstention and is never a claim that code is safe.
- **Denial of service by making a review expensive.** Spend is bounded by `budget-usd` per
  review; a pull request that makes a review cost more than it is worth is a cost problem,
  and the ceiling is the answer to it.

## What is *not* claimed

Read this before relying on the boundary.

- **The isolation evidence is observed from inside the product.** Every red-team row records
  the fixture's own return value, the reason the run recorded, and whether a file appeared on
  the host. `G-SEC-002` also asks for a **sandbox-external** observer proving the kernel
  denied the attempt. One such observation exists, on one run
  ([report](docs/acceptance/2026-09-08-external-observer.md)); the matrix has not been run
  under it. **That condition of the gate is open**, and no number of internal passes closes it.
- **Language-level process and network guards are best-effort containment, not a boundary.**
  The OS boundary is the container. Without it there is no boundary.
- **The process audit covers the whole reproduction interpreter**, so trusted bootstrap can
  set the same child-process marker reviewed code would.
- **No penetration test by a third party has been performed.**
