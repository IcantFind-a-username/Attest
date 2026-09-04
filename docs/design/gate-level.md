# The gate level: the evidence form for new code

**Design only. Nothing here is implemented, and this document authorises no implementation.**
It answers the five questions mainline §1.1's gate row leaves open — what "reachable" means, how
it executes, how it verifies offline, how it is displayed apart from red, and how much of it may
be said — and ends with the one RED that would open the work.

Mainline §1.1: *gate claims "this new code fails on an input the change makes reachable", and
owes an executable failure of new code on a witnessed reachable input; there is no base revision
to compare against, so the failure itself is the evidence.*

## 0. The blocking question, before any of the rest

`G-NEWCODE-001` governs "N-01 and **any proposal to create a certifiable new-code evidence
class**", and it demands a hidden, product-blind pilot of ≥ 60 adjudicated new-code defects and
60 paired clean additions across ≥ 15 repositories **before** an owner may select a contract.
Mainline §1.3 puts gate third on the mainline, after green. **Those two documents do not agree
and one of them has to move.** The design below is written so the choice is cheap either way:

- **Read A — `G-NEWCODE-001` applies.** Gate is author-visible speech about new code, which is
  exactly what the gate exists to hold. Then this design is an *N-01 contract alternative*,
  submitted with at least two others and the always-abstain baseline, and nothing ships before
  the pilot. Cost: the gate level is not next; it is after a 120-case study.
- **Read B — it does not.** `G-NEWCODE-001`'s pass conditions are written about a **likelihood
  ratio and a certificate** ("it cannot name or tune an LR"). The design below names no LR,
  issues no certificate, and makes no semantic judgement: it reports that an uncaught exception
  was raised, on this line, through this call path, N times out of N. Then gate ships under its
  own new gate (`G-GATE-001`, to be written) and `new_code_candidate` stops being a blanket
  abstention. Cost: the product publishes about new code on evidence no 120-case study has
  measured.

**This is the owner's call and it is the first one.** My recommendation is **Read A with a
carve-out**: run this design as the *first* N-01 contract alternative, and let it ship early only
in **shadow** (`G-SHADOW-001`'s machinery already exists), so the pilot's 60 defects are collected
by the thing itself rather than before it. Everything below stands under either reading.

## 1. What "reachable" means

The claim is not "this code can crash". It is "this code crashes on an input **the change makes
reachable**". Three candidate witnesses, and the rule over them:

| witness | what it establishes | on its own? |
|---|---|---|
| **(a) call site** — a call to the new symbol exists in the head tree at a line the diff did **not** add | somebody actually calls it | no |
| **(b) type annotation** — the parameter's annotation admits the input's type | the input is inside the declared domain | **necessary** |
| **(c) documented support** — a docstring or documentation file states the parameter accepts it | the author promised this domain | no |

**The rule: (b) always, and at least one of (a) or (c).** Reasons, each one a thing that goes
wrong without it:

- **(b) is necessary** because an input outside the annotation is the caller's error, not the
  code's; a crash on it is a claim about a contract nobody offered. An **unannotated parameter is
  not reachable** and the candidate abstains. That is a large recall cost in untyped code and it
  is the decision, not an oversight.
- **(b) alone is never enough.** `def f(name: str)` admits every string in the language. A type is
  a permission, not a witness that anything produces the value.
- **(a) or (c)** is what turns permission into occurrence: either a real caller exists, or the
  author wrote down that the domain is supported and a claim against it is one they licensed.

**Two grades of witness, and only one of them may speak.**

- **through-caller (publishable).** The generated reproduction enters at the **call site**, not at
  the new symbol, and the new code executes underneath. Reachability is then not argued from
  annotations at all — it is in the trace. The recorded witness is `(path, line)` of the call site
  plus the raise-origin record proving the new code ran.
- **direct (drawer).** The reproduction calls the new symbol itself. Records `(b)` and `(a|c)` as
  metadata and states its own reason for staying in the drawer.

**The first measurement this design owes is what fraction of new-code candidates can produce a
through-caller witness at all.** If it is near zero the level is not worth building, and that is
a cheap thing to learn.

## 2. What kind of failure counts

Not every failure. **An uncaught exception, raised from a line the diff added, that is not a
deliberate refusal.** Three exclusions, and each mirrors a narrowing red already paid for:

1. **No value assertions.** A reproduction that asserts `f(x) == 7` invents a specification —
   `G-NEWCODE-001` names this as the adversarial case, and D-127/D-132 spent two versions
   learning it on the base-comparison side, where a *base tree* could at least witness the value.
   Here nothing can. **A crash is self-evidencing; an expected value is not.** Gate publishes
   crashes only.
2. **Changed-line binding, as red has it.** The raising frame must be on a line the diff added.
   An exception raised from untouched code that the new call merely reaches is a claim about the
   old code, and the old code has a base revision — that is red's job.
3. **Not a deliberate rejection (D-102, unchanged).** If the statement at the raising line is a
   `raise` or an `assert`, head is refusing on purpose and the intent observer already knows what
   to do with that: drawer, labelled.

## 3. How it executes

`linux-container-v1` exactly as red uses it (X-02: no network, read-only root, non-root, no
inherited environment, fresh tmpfs; V-03: fresh writable state per repeat). Three differences:

- **Head only.** There is no base run, so a gate finding costs roughly **half** a red receipt.
- **Repetition is unchanged and its agreement rule is stricter.** N runs, and all N must raise
  **the same exception type from the same line**; any disagreement DEFERs. Red compares two
  revisions; gate has only repetition to lean on.
- **One run red does not need: the environment control.** Before the failure means anything, the
  head tree must be shown to work at all in that container — at least one *pre-existing* test that
  exercises the same call site must pass in the same image. **No passing control, no claim**, and
  the drawer records "environment unproven". Without it "everything crashes" and "this input
  crashes" are the same observation.

## 4. How it verifies offline

The bundle is red's, plus a reachability record, and the verifier re-derives every check from
bytes with no network, no model and no re-execution:

| field | checked by re-reading |
|---|---|
| head revision, added-line set, test bytes, node id, per-run JUnit, interpreter and environment digests | as red (V-01/V-03), byte for byte |
| `reachability.kind` ∈ {`through_caller`} for a published finding | the enum |
| `reachability.call_site` = `(path, line)` | the head tree has a call to the symbol there, **and that line is not in the added-line set** |
| `reachability.annotation` | the parameter's annotation in the head source admits the input's type |
| `origin` = `(line, statement, exception_type, escaped)` | the line **is** in the added-line set, and the statement there is **not** `raise`/`assert` |
| `runs` | N ≥ the configured repeat count, all naming the same `(line, exception_type)` |
| `control_run` | present, `passed`, and naming a test the diff did not add |

Any missing or inconsistent field rejects the bundle. Fail closed, as everywhere else.

## 5. How it is displayed, and how much may be said

**A different claim needs a different shape, or the reader will hear "regression".**

- Its **own summary section**, under **`Gate — new code, nothing to compare against`**, never
  inside the red section and never counted in red's totals.
- Every inline comment opens `Gate (new code):` and carries the marker `<!-- attest:gate:… -->`,
  the way green carries its own (D-133).
- **The claim sentence names three coordinates and nothing else**: the exception type, the added
  line it was raised from, and the call site that reaches it. No severity, no "likely", no
  "regression", no fix advice in the claim. A model-written explanation, if any, is a separate
  labelled paragraph as green's is.
- **The sentence must say what it does not know.** "There is no base revision to compare against;
  this is not a claim that the change broke something that worked."

**Publication cap — the owner's number, and my proposal:**

1. **At most one gate finding per pull request.** Not per change unit: the level is new and its
   evidence is weaker than a receipt's.
2. **Zero when the same review publishes any red finding.** A receipt is strictly stronger and
   the author's attention is the scarce resource.
3. **A separate family from red (D-125 per change unit still applies within it).** A gate claim
   must never consume red's alpha and red must never consume gate's.
4. **Zero on any review whose red channel DEFERred for an environment reason.** If the container
   could not be trusted for red it cannot be trusted for a claim with no base run.

## 6. The one RED that opens the work

`tests/test_gate_level.py::test_a_crash_on_an_input_a_pre_existing_caller_produces_is_a_gate_finding`

> A head tree adds `def widen(name: str) -> str: return name.strip().casefold()[0]`. An
> **existing, not-added** line in `cli.py` calls `widen(argument)` where `argument: str` comes
> from `argparse`. The reproduction enters at the `cli.py` call site with `""`, which the
> annotation admits; `widen` raises `IndexError` from an added line; three runs agree; a
> pre-existing test of the same call site passes in the same image. **The finding publishes, in
> the gate section, naming `IndexError`, the added line, and the call site.**

and its false-positive control, in the same file:

> `::test_a_crash_reachable_only_from_a_caller_the_diff_added_is_not_a_gate_finding` — the same
> tree, except the only call site is a line the **diff itself added**. `reachability.call_site`
> fails its check, the witness is `direct`, and **nothing publishes**; the drawer records why.

Two more that must exist before it can be believed, and they are cheap:
`::test_an_expected_value_assertion_never_publishes` (§2.1) and
`::test_a_raise_on_an_added_line_stays_a_deliberate_rejection` (§2.3, D-102 unchanged).

## 7. What this design deliberately does not do

- **No likelihood ratio, no certificate, no severity, no calibration.** Gate reports an
  observation; it does not price it.
- **No untyped code.** (b) is necessary, so a parameter with no annotation abstains.
- **No value claims, ever** — the class that cost red two policy versions.
- **No cross-file reasoning about reachability.** One call site, in the head tree, read
  syntactically. A call reached through a registry, a decorator or a plugin table is not
  witnessed and abstains.
