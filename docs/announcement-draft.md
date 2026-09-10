# Announcement draft — `v0.1.0`

**Not published.** This is a draft for the owner to edit, cut or discard. Nothing here has been
posted anywhere.

---

## attest v0.1.0 — a pull-request reviewer that only says things it can prove

**One sentence.** attest reviews a pull request and publishes a defect claim only when a
generated test **fails on your head commit and passes on the merge base** — three runs each way,
inside a network-free container, with a receipt you can verify offline. Everything else is a
stated silence.

An LLM proposes; an algorithm that calls no model decides whether it may speak.

### What a real comment looks like

This is the whole of what an outside repository received, on a pull request in a repository this
project does not develop in, from an Action installed at a tagged ref:

```
[red] services/analysis_core/us_stock_helper_core/indicators.py:60 — Removing the empty-check
causes `checked[0]` to raise IndexError when `_validated` returns an empty sequence (e.g., input
list shorter than period, or empty), instead of gracefully returning an empty tuple as before.
(receipt 37e8cbfcabe1)
```

One line. A level marker, a coordinate, one sentence of fact, and a receipt id. Behind it: the
generated test failed on head in **3 of 3** runs and passed on the merge base in **3 of 3**,
inside `linux-container-v1` with the network blocked, and the image was built on the runner from
the project's own manifests in 27.9 s. Below the line, in a collapsed block, the command to
reproduce it, the test, and the six run outcomes.

**Read the caveat with it**: that defect was **placed on purpose** by the person who wrote the
reviewer, and the pull request said so. It demonstrates the install and publication path. **It
measures no recall and no precision.**

### Four levels, and each owes different evidence

| level | what it claims | who decides |
|---|---|---|
| **red** | this change broke something that worked | a differential receipt — the certification kernel, the binding policy, the intent discriminator |
| **gate** | this new code fails on a reachable input | reachability plus the same execution and isolation red demands — **in shadow; nothing reaches an author** |
| **yellow** | this looks wrong, and here is exactly what I checked | a deterministic premise checker; an unverified premise is **deleted from the text**, not softened |
| **green** | this is structurally so, here and here | a computable measure with two concrete coordinates; the model is called only after the evidence holds |

A level with nothing to say contributes no line. When every level is silent the product still
owes exactly one, and it names how many change units the silence covers.

### The numbers, with intervals

| | |
|---|---|
| crash-class recall, held-out corpus of 28 | **2 of 28 — 7.1%**, Wilson 95% [2.0%, 22.6%] |
| false publications, 28 real pull requests, 13 reproductions executed | **0** |
| false publications, 68 independent null controls + 40 held-out controls, K=4 | **0** |
| yellow (a) noise floor, 68 controls | **1 of 68 — 1.47%**, Wilson 95% [0.26%, 7.87%] |
| red-team attack classes dispatched on the production backend, all marked | **13 of 13** |
| cost of a review | mean **$0.22**, hard cap `budget-usd` (default $1.00) |

### What it cannot do, and I would rather you heard it from me

- **Recall is 7.1%.** The interval's *upper* bound is 22.6%. **It will miss most defects.**
  Three measured loss sources over 56 verification attempts: 17 probes that do not collect,
  **17 refused by the process guard on the merge base** where nothing untrusted runs, 13 lost to
  the intent clause.
- **Utility is unproven.** The prospective run over 28 real pull requests published **nothing**.
  A review that says nothing cannot be wrong, and it cannot be useful either.
- **Python and pytest only**, interpreters 3.10–3.13, Linux containers. Anything else gets one
  line naming the reason and exit 0.
- **The gate level is in shadow** — 0 of 445 recorded candidates has produced a publishing-grade
  witness.
- **Every control number is a K=4 number.** The shipped `samples` is 5 and that control arm has
  never been bought (≈$126), nor has the full natural-null population (≈$53).
- **A silence is never a true negative.** Nothing licenses *"attest found nothing, so it is
  fine."*

### Install it, in three steps

1. Save the workflow file — copy it whole from the
   [README](https://github.com/IcantFind-a-username/Attest#install-it-in-one-file) — as
   `.github/workflows/attest.yml`. It pins `IcantFind-a-username/Attest@v0.1.0`.
2. Add one repository secret: **Settings → Secrets and variables → Actions → New repository
   secret**, Name exactly `ANTHROPIC_API_KEY`. `GITHUB_TOKEN` needs nothing.
3. Open a pull request.

**attest never touches, stores, transmits or logs your key.** It is read from your own runner's
environment and goes nowhere else; a missing key stops the run before any model call and the
error says where to put it. **Fork pull requests are never reviewed and never commented on.**

### Why publish something with 7.1% recall

Because the thing being tested is not the recall. It is whether *"the model proposes and an
algorithm decides"* survives contact with a real repository — and the answer so far is that it
does: 0 false publications across every population measured, 13 of 13 attack classes refused,
and every author-visible line adjudicated by something that calls no model. **The recall is the
next problem, and it is a product problem, not a corpus problem.**

---

*Not on the GitHub Marketplace. Not on PyPI. Install from the tagged ref.*
