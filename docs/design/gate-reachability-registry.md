# The registry witness: a second class of reachability for the gate level

**Design only. Nothing here is implemented, and this document does not ask for it to be.**
It answers item 2 of the 2026-09-05c handoff — the owner kept
[the gate level's](gate-level.md) §7 exclusion (*"a call reached through a registry, a decorator
or a plugin table is not witnessed and abstains"*) and asked what the second class would look
like if it were ever lifted. §5 measures what lifting it would buy, and the number is the
argument.

## 1. What §7 excludes, and why it was right to

Gate's publishable grade is **through-caller**: the reproduction enters at a call site the diff
did not add, the new code executes underneath, and reachability is in the trace rather than in an
argument. §7 refuses the case where the only thing naming the new symbol is a *registration* —
`set_defaults(func=cmd_run)`, `@app.route("/x")`, `@click.command()`, `@pytest.fixture`. The
reason stands: **a reference in a dispatch table is not a witness that anything calls the code.**
A parser that never sees `run` on its command line never calls `cmd_run`.

But the reason is narrower than the rule. What the registration establishes is not "this is
called"; it is **"there is a documented, author-built path from an external input to this code,
and the author built it on purpose."** That is weaker than a call site and much stronger than an
annotation. It deserves a grade of its own rather than silence.

## 2. The proposed grade: **through-registry**

A third grade between `through_caller` (publishes) and `direct` (drawer). Its witness has three
parts, and all three are required:

1. **the registration** — a syntactic site in the head tree, outside the added lines, that binds
   the new symbol into a named registry (§3 lists the four adapters and their shapes);
2. **the entry point** — the registrar's own public entry, also outside the added lines, that a
   reproduction can call: `main(argv)`, `app.test_client()`, `CliRunner().invoke(cli, …)`, a
   `pytest` collection of one node id. **The reproduction is written against the entry point and
   never names the new symbol.** This is what makes the grade honest: if the registry does not in
   fact route to the new code, the reproduction fails to reproduce and nothing is claimed.
3. **the traversal proof** — the executed-lines record (the same `_LINES_PLUGIN` trace red
   already collects) must contain **the registration line or the registrar's dispatch line**, and
   the raise origin must be on a line the diff added. Reachability is then in the trace exactly
   as it is for `through_caller`; the registry is not argued about, it is *observed being used*.

Everything else in [gate-level.md](gate-level.md) is unchanged: (b) the annotation is still
necessary, §2's three exclusions still hold (no value assertions, changed-line binding, no
deliberate rejections), §3's two agreeing runs and environment control still hold, and §5's
per-PR cap still holds.

## 3. The four adapters

Each adapter answers three questions: how a reproduction reaches the registered symbol
deterministically, what proves the registry was traversed, and where it will produce a false
positive.

| adapter | registration shape | entry the reproduction calls | traversal proof | false-positive risk |
|---|---|---|---|---|
| **argparse** | `sub.add_parser("run").set_defaults(func=SYM)`; `type=SYM`; `action=SYM` | `main(["run", …])`, or the module's `__main__` argv path | the `set_defaults` line **and** the `args.func(args)` dispatch line both in the executed set | the reproduction must *invent the command line*. A required argument given a value no user would give makes the crash a claim about the author's own CLI contract, not about reachable input. **Mitigation: every argv token must come from the parser's own declared defaults, choices or metavar; an invented free-form value abstains.** |
| **click** | `@click.command()` / `@group.command()` on `SYM`; `group.add_command(SYM)` | `CliRunner().invoke(cli, [...])` | the decorator line and `SYM`'s first body line in the executed set | click's decorator **replaces** the symbol with a `Command` object, so "the new symbol" in the trace is the wrapped callback. The witness must anchor on the callback's own code object, not the name. Same argv discipline as argparse. |
| **Flask / FastAPI** | `@app.route(path, methods=…)`, `@app.get/post/…`, `@router.get`, `app.add_url_rule(...)` | the framework's own test client: `app.test_client().get(path)`, `TestClient(app).post(path, json=…)` | the route decorator line and the handler's first body line in the executed set | the **request body is invented** the same way an argv is, and FastAPI's own validation layer usually rejects a body outside the annotation *before* the handler runs — which is the correct outcome and must be recorded as `not reproduced`, not as an abstention. A crash reached only by *disabling* validation is not a reachable input. |
| **pytest fixture** | `@pytest.fixture` on `SYM`; a test function whose parameter is `SYM`'s name | `pytest` collecting and running **one pre-existing** test node that requests the fixture | the fixture's `def` line and the requesting test's line both in the executed set | the sharpest one. **A crash inside a test tree is not a product defect.** A fixture is reachable only from tests, so a `through_registry` finding here says "your test suite is broken", which is true, in scope for nobody, and would be author-visible noise. **Recommendation: the pytest adapter is specified and then disabled** — and the same argument bars pytest's own collection of `test_*` functions from ever counting as a registry (§5 shows why this matters: 4 of the 13 unwitnessed `attest` candidates are test functions). |

## 4. Worked example: the case the owner named

`attest 2878d4012e` — head `506aae1a13`, `scripts/corpus/heldout_run.py:128`, `JSONDecodeError`,
symbol `cmd_run`. Under §7 today: `reachability = direct`, reason *"no call site of `cmd_run`
outside the added lines and no documented domain"*, **drawer** — and the 2026-09-05b adjudication
read it by hand as a real unguarded `json.loads` on an added line.

Under the argparse adapter it would run like this:

1. **registration** — `scripts/corpus/heldout_run.py:300`, `run.set_defaults(func=cmd_run)`.
   Outside the added lines (the diff added the body of `cmd_run`, not the parser wiring). ✔
2. **entry point** — `main(argv)` in the same module, also outside the added lines. The
   reproduction calls `main(["run", "--log", <a path it wrote>, …])`, and **never names
   `cmd_run`**; every token comes from the parser's own declared arguments. ✔
3. **traversal proof** — the executed-lines record must contain line 300 (the registration) and
   the `args.func(args)` dispatch, plus `heldout_run.py:128` as the raise origin, which is a line
   the diff added. ✔
4. §2's exclusions — an uncaught `JSONDecodeError`, not a `raise`/`assert`, no value assertion. ✔
5. §3 — two agreeing head runs and a pre-existing test naming the entry point as the environment
   control. This one is where it would most likely stop: this module has no test that calls
   `main`, so the environment control would have to fall back to some other pre-existing test in
   the tree, and §3 as written wants one that *names the caller*. **That is a real gap and this
   design does not paper over it.**

So the grade is reachable in principle for the owner's case, and the ceiling on the argv
discipline in step 2 is the thing that would decide whether it is reachable in practice.

## 5. The ceiling, measured

[`scripts/corpus/registry_ceiling.py`](../../scripts/corpus/registry_ceiling.py), free —
`git show` and `git grep`, no model call. Name-based and therefore an **over**-count by
construction (a same-named symbol in another module would count). It refuses to report a ceiling
unless it first finds the positive control, `attest 2878d4012e`; it does. Data:
[`2026-09-05-registry-ceiling.json`](../acceptance/evidence/2026-09-05-registry-ceiling.json).

| population | rows | no call site (a) today | scanned | **a registry witness would newly admit** |
|---|---|---|---|---|
| E-04 stratum v2 new-code candidates | 224 | 200 | 194 | **0** |
| the 53 recorded receipt bundles (D-137 replay) | 53 | 25 | 1 | **1** — `attest 2878d4012e` |

*Scanned* is smaller than *no call site* because a row with no resolved symbol has nothing to
look up: 6 of the 224 candidates and **24 of the 25** unwitnessed replay rows never got past §2's
changed-line binding (`line 0 is not a line the diff added`), so exactly one replay row ever
reached the question this design is about — and a registry witness admits it.

**Zero of 224, and the reason is structural rather than a threshold.** 176 of the 224 candidates
are `us-stock-helper` and 26 are `corum`, and the head trees of *all* those units contain **no
registration site of any of the four shapes** — no `set_defaults(func=…)`, no click command, no
route, no fixture. Their decorators are `@dataclass` and `@property`. The 22 `attest` candidates
sit in the only tree that registers anything (19 `set_defaults` sites, 25 `@pytest.fixture`
sites), and **none of the 13 unwitnessed `attest` symbols is one of the registered ones** — they
are private helpers (`_log_tail`, `_unit_order`, `_as_int`), drill entry points called directly,
and four `test_*` functions that §3's pytest recommendation would bar anyway.

So the gate level's **10.7% ceiling does not move** in this traffic. The registry witness buys
exactly one finding in everything this project has recorded, and that finding is the one the
owner already knows about.

**Note added 2026-09-08 (D-174, [report](../acceptance/2026-09-08-binding-and-bounds.md)):** the
10.7% this section compares against was a count of call sites matched by **name**. Under name
binding it is **0.0%** — all 26 recorded `through_caller` witnesses across 445 candidates were
collisions. The comparison in this section is therefore between a registry witness that buys one
finding and a `through_caller` witness that has so far bought **none**, which strengthens the
argument for §7 rather than weakening it, but the numbers above should be read as the name-match
figures they are. The recommendation is unchanged.

## 6. Recommendation

**Keep §7 as it is.** Not because the second class is unsound — §2's three-part witness is as
strong as `through_caller` where the traversal is actually in the trace — but because it is
**four adapters, an argv-synthesis discipline, an environment-control gap (§4 step 5) and a
disabled-by-design fifth adapter, for one recorded case.** The right time to revisit is when a
CLI-shaped or web-shaped repository enters the traffic and the 0-of-224 row above becomes
something else; the scan that produced it is cheap enough to re-run on every stratum.

If it is ever built, build **argparse only, first**, with the argv discipline enforced, and
measure it before writing the other three.
