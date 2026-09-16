# Reading the test context, 2026-09-16 — a conftest is read, not refused for existing

**Owner instruction of 2026-09-16 (step by step after the gate; scope set to pure-Python
repositories).** No model call, no paid run, nothing pushed; the factory configuration is
unchanged (`contract_probes = False`, `intent_policy = attest.intent.v5.1`). Product change:
D-282, commit `d57530e`. Evidence:
[`evidence/2026-09-16-contract-conftest/`](evidence/2026-09-16-contract-conftest/).

**Status: capability repair of an experimental rule.** The full gate under Docker passes on
`d57530e`: exit 0, kernel and execution coverage 93.35%
([log](evidence/2026-09-16-contract-conftest/full-gate-d57530e.log)).

## 0. What was wrong

D-257 refused a contract whenever the test file's ancestor `conftest.py` was anything but
empty, because an unread conftest can install a fixture that replaces the callable under
test. Real repositories always have a conftest. Rebuilt over the 74 recorded contract
searches, **98 of 98 refusals were `conftest execution is unexamined`**, contract probes fell
to **0 on every population**, and the three D-254 gains were withdrawn. The capability existed
only where no repository lives.

## 1. The rule now

Everything that runs before the assertion is read: the conftest chain from the repository root
down, its hooks, the setup half of autouse fixtures, the fixtures the test asks for, and the
test module's own body. Such code is refused when it can **reach the module under review** --
the anchored module, or a module that file imports -- or when the rule **cannot tell what it
reaches**. Concretely:

- A call is followed to the module its name resolves to. Into this repository's own modules the
  rule follows one level deeper, so an import-time `helper.install()` that patches the symbol is
  still refused. Into the standard library or a third-party package it does not follow, and says so.
- A constructor of a class the module under review defines **builds a value**, so a
  `parametrize` row of `Point(1, 2)` is read. A function call in the same place is still refused.
- Teardown after a fixture's `yield` runs after the assertion and is not read.
- `monkeypatch`-style replacement (`setattr`, `setitem`, `setenv`, `chdir`, …) is refused
  wherever it is reached through, and so are the namespace builtins (`setattr`, `globals`,
  `vars`, `exec`, …).
- A fixture a test asks for must be defined on the path and provably unable to reach the module;
  one no conftest defines -- a plugin's, or a pytest builtin -- is refused by name.
- A decorator is screened on the test that states the contract, not on every function of the
  file: `pytest.mark.*` is metadata, `usefixtures` and indirect parametrization are refused, and
  any other decorator is refused.

Stated limits, unchanged: nothing is executed; a call into a third-party module is not followed;
a constructor with side effects, a plugin installed by configuration, and state left by earlier
tests are not read.

## 2. What it costs and what it recovers

Rebuilt over the same 74 recorded contract searches, on the same base trees:

| population | D-255 | D-257 | now |
|---|---:|---:|---:|
| the forty | 25 | 0 | 24 |
| counterexample variants | 25 | 0 | 25 |
| batch 3 controls | 0 | 0 | 0 |

The three contracts D-254 gained are built again: `test_musllinux.py:57`,
`test_direct_url.py:95` and `test_poolmanager.py:423`.

**Product replay** of the affected cases (`frozen_e2e.py`, arm `E61`, run `b2`, ledger-frozen
proposals and probes, no model call):

| population | result |
|---|---|
| the ten affected forty cases | **4 published on the planted hunk**, the same four as D-255: the three contract gains and `urllib3-none_guard-15` through its model probe |
| counterexamples, 3 cases / 6 variants | **0 red publications**; the search chose the contract probe in 6 of 6 |
| the two affected controls | **0 red publications**, unchanged |

The seven reasonable-change miscertifications D-257 blocked stay blocked: the autouse fixture,
module and class setup, the import-time call, the declared plugin, and both parametrize callback
variants are each refused, now with the line that caused it.

## 3. What is not claimed

This is not a recall figure and not a real-repository measurement. The forty is a diagnostic set
of injected defects, the proposals and model probes are ledger-frozen, and the default rule is
untouched. The context screen reads one repository's own source; a fixture installed by a plugin,
or a third-party import with side effects, is outside it and is stated rather than closed.
