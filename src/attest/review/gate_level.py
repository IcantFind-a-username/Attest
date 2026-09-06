"""The gate level, in shadow: an executable failure of new code on a witnessed
reachable input (`docs/design/gate-level.md`, D-137).

Everything here is **shadow-only**. A gate observation reaches the ledger and a
shadow record under ``.attest/shadow/gate/`` and reaches **no author-visible
surface at all**: no comment, no summary section, no `CertifiedFinding`, no
family selection, no calibration denominator. `would_publish` in a record is a
counterfactual and nothing more.

Two things are kept strictly apart, because only one of them costs money:

- **the witness** (`witness`, `classify_origin`, `adjudicate`) is pure: git and
  the `ast` module, no model, no execution, no network. It answers the design's
  first owed measurement -- *what fraction of new-code candidates can produce a
  through-caller witness at all* -- for nothing, before any reproduction is
  bought, and it is what stops a candidate before generation;
- **the execution** (`HeadOnlyExecution`) buys N head runs and, only for an
  observation that has already passed every other check, one environment
  control. There is no base run: a gate finding costs about half a red receipt.

The red path is not touched. `execute_differential` is not modified and not
called from here; the duplication of its head half is deliberate, so that no
defect in this module can change what a receipt says.
"""

from __future__ import annotations

import ast
import functools
import json
import re
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from attest.execution.controller import Controller, ExecutorAdapter
from attest.review.binding import BindingIndex, Reference, Target, dotted_name
from attest.review.candidates import StoredCandidate
from attest.review.executor import (
    ExecutionOutcome,
    ExecutionResult,
    ExecutorLimits,
    ReproSpec,
    execute_repro,
)
from attest.review.intent import RaiseOrigin, statement_kinds
from attest.review.workdir import gate_root

GATE_POLICY_VERSION = "attest.gate.v0-shadow"
GATE_SHADOW_SCHEMA_VERSION = "attest.gate-shadow.v1"

# §3: N runs, all naming the same (line, exception type). Red compares two
# revisions; gate has only repetition to lean on, so the agreement is exact.
GATE_REPEATS = 3
# Bounds on the free witness search. A call-site scan is `git grep` over the
# head tree, so these bound work, never truth: a symbol whose scan is truncated
# records that it was.
MAX_CALL_SITE_FILES = 40
MAX_SOURCE_BYTES = 400_000
TEST_PATH = re.compile(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$)")

THROUGH_CALLER = "through_caller"
# D-166: the through-caller rule exists so that *something the change did not
# add* depends on the new code. A call site inside the change's own new test
# satisfies the letter of that and not one word of its point, so it is graded
# apart and never publishes.
THROUGH_TEST_CALLER = "through_test_caller"
DIRECT = "direct"
NONE = "none"


@dataclass(frozen=True)
class CallSite:
    """A call to the symbol in the head tree at a line the diff did not add."""

    path: str
    line: int
    caller: str  # the definition the call sits inside, "" at module level


@dataclass(frozen=True)
class Reachability:
    kind: str  # through_caller | direct | none
    symbol: str
    parameters: tuple[str, ...] = ()
    annotations: tuple[str, ...] = ()  # positionally paired with `parameters`
    call_site: CallSite | None = None
    documented: bool = False
    admissible: bool = False  # (b) and at least one of (a) or (c)
    reason: str = ""


@dataclass(frozen=True)
class Origin:
    """§2: an uncaught exception raised from a line the diff added, which is not
    a deliberate refusal."""

    line: int
    statement: str  # "raise" | "assert" | "other"
    exception_type: str
    escaped: bool


@dataclass(frozen=True)
class ControlRun:
    """§3: the head tree works at all in this image -- a pre-existing test that
    names the caller passes there. No passing control, no claim."""

    target: str
    passed: bool
    reason: str


@dataclass(frozen=True)
class GateObservation:
    policy_version: str
    path: str
    symbol: str
    reachability: Reachability
    origin: Origin | None
    runs: tuple[tuple[int, str], ...]  # (line, exception type) per head run
    repeats: int
    control: ControlRun | None
    would_publish: bool
    reason: str
    source: str = "live"  # live | replay

    def to_ledger_row(self, task_id: str, finding_id: str) -> dict[str, object]:
        return {
            "kind": "gate_shadow",
            "schema_version": GATE_SHADOW_SCHEMA_VERSION,
            "task_id": task_id,
            "finding_id": finding_id,
            "policy_version": self.policy_version,
            "path": self.path,
            "symbol": self.symbol,
            "reachability": self.reachability.kind,
            "admissible": self.reachability.admissible,
            "call_site": (
                None
                if self.reachability.call_site is None
                else f"{self.reachability.call_site.path}:{self.reachability.call_site.line}"
            ),
            "exception_type": "" if self.origin is None else self.origin.exception_type,
            "origin_line": None if self.origin is None else self.origin.line,
            "runs_agreeing": len(set(self.runs)) == 1 and bool(self.runs),
            "control_passed": None if self.control is None else self.control.passed,
            "would_publish": self.would_publish,
            "reason": self.reason,
            "source": self.source,
            "author_visible": False,
        }

    def record(self) -> dict[str, object]:
        return {
            "schema_version": GATE_SHADOW_SCHEMA_VERSION,
            **{key: value for key, value in asdict(self).items()},
        }


# --------------------------------------------------------------------- the tree


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    return result.stdout if result.returncode == 0 else ""


@functools.lru_cache(maxsize=32)
def toplevel(repo: Path) -> Path:
    """The work tree's root. `git grep`'s pathspec is relative to the working
    directory, so a caller that hands in a subdirectory would silently search
    only that subtree -- which is a wrong answer, not a smaller one."""
    found = git(repo, "rev-parse", "--show-toplevel").strip()
    return Path(found) if found else repo


def show(repo: Path, ref: str, path: str) -> str:
    text = git(repo, "show", f"{ref}:{path}")
    return text if len(text.encode("utf-8", "replace")) <= MAX_SOURCE_BYTES else ""


# ------------------------------------------------------------------ the witness


def enclosing_definition(source: str, line: int) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """The innermost function the line sits inside. `None` at module level, and
    `None` when the source does not parse -- an unparseable head tree is never
    classified, it abstains."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    found: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        end = node.end_lineno or node.lineno
        if node.lineno <= line <= end and (
            found is None or node.lineno >= found.lineno  # innermost wins
        ):
            found = node
    return found


def parameter_annotations(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(names, annotations) of every parameter but `self`/`cls`; an unannotated
    parameter's annotation is the empty string."""
    arguments = node.args
    every = [
        *arguments.posonlyargs,
        *arguments.args,
        *([arguments.vararg] if arguments.vararg else []),
        *arguments.kwonlyargs,
        *([arguments.kwarg] if arguments.kwarg else []),
    ]
    names: list[str] = []
    annotations: list[str] = []
    for argument in every:
        if argument.arg in {"self", "cls"}:
            continue
        names.append(argument.arg)
        annotations.append("" if argument.annotation is None else ast.unparse(argument.annotation))
    return tuple(names), tuple(annotations)


def documents_parameter(
    node: ast.FunctionDef | ast.AsyncFunctionDef, names: tuple[str, ...]
) -> bool:
    """(c): the docstring states the domain, by naming a parameter."""
    doc = ast.get_docstring(node) or ""
    return any(name and name in doc for name in names)


@dataclass(frozen=True)
class WrittenCall:
    """One call of the searched name, with everything binding needs to judge it."""

    line: int
    caller: str  # innermost enclosing definition's plain name, "" at module level
    scope: str | None  # its qualname, which is what a receiver or a local needs
    dotted: str  # the call expression as written: `widen`, `lib.widen`, `self.widen`


def calls_in(source: str, symbol: str) -> list[WrittenCall]:
    """Every call whose **last written segment** is ``symbol``, with its scope.

    This is a text-shaped search and it stays one: it finds candidates, and
    `attest.review.binding` decides which of them actually reach the symbol."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    scopes: list[tuple[int, int, str, str]] = []

    def collect(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                qualname = f"{prefix}.{child.name}" if prefix else child.name
                scopes.append(
                    (child.lineno, child.end_lineno or child.lineno, child.name, qualname)
                )
                collect(child, qualname)
            else:
                collect(child, prefix)

    collect(tree, "")
    found: list[WrittenCall] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        written = dotted_name(node.func)
        if written is None or written.rsplit(".", 1)[-1] != symbol:
            continue
        enclosing = [
            (name, qualname)
            for start, end, name, qualname in scopes
            if start <= node.lineno <= end
        ]
        name, qualname = enclosing[-1] if enclosing else ("", "")
        found.append(
            WrittenCall(line=node.lineno, caller=name, scope=qualname or None, dotted=written)
        )
    return found


def enclosing_qualname(source: str, line: int) -> str:
    """The dotted scope chain the line sits in, "" at module level or on a
    source that does not parse. `enclosing_definition` answers with the node;
    binding needs the name that node is reached by."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return ""
    best = ""
    best_start = -1

    def walk(node: ast.AST, prefix: str) -> None:
        nonlocal best, best_start
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                qualname = f"{prefix}.{child.name}" if prefix else child.name
                end = child.end_lineno or child.lineno
                if child.lineno <= line <= end and child.lineno > best_start:
                    best, best_start = qualname, child.lineno
                walk(child, qualname)
            else:
                walk(child, prefix)

    walk(tree, "")
    return best


@functools.lru_cache(maxsize=8)
def _tree_paths(root: str, head_sha: str) -> tuple[str, ...]:
    """Every Python file of one revision, for the binding layer's module search."""
    listed = git(Path(root), "ls-tree", "-r", "--name-only", head_sha)
    return tuple(line for line in listed.splitlines() if line.endswith(".py"))


@functools.lru_cache(maxsize=8)
def binding_index(root: str, head_sha: str) -> BindingIndex:
    """One binding index per revision, reading blobs out of `git` on demand.

    Cached because a review asks the same revision about many candidates, and
    re-reading a package's `__init__` once per candidate is pure waste."""
    repo = Path(root)
    return BindingIndex(
        _tree_paths(root, head_sha), lambda path: show(repo, head_sha, path) or None
    )


def find_call_sites(
    repo: Path,
    head_sha: str,
    symbol: str,
    *,
    anchored_path: str,
    anchored_qualname: str = "",
    added: Mapping[str, set[int]],
) -> tuple[list[CallSite], bool]:
    """(a): calls that **resolve to** ``symbol`` in the head tree, at lines the
    diff did not add. Returns the sites and whether the search was truncated.

    `git grep` finds the candidates and `attest.review.binding` decides them.
    The distinction is the whole of this change: a second module that defines
    its own `widen` and calls it used to grade a candidate `through_caller` --
    the one grade allowed to publish -- on a call that never reaches the new
    code. A call site the binding layer cannot resolve is not a witness; the
    level abstains rather than counting a name."""
    # from the tree root, so the `*.py` pathspec means the whole tree and not
    # whatever subdirectory a caller happened to hand in
    root = toplevel(repo)
    listed = git(root, "grep", "-l", "-w", "-e", symbol, head_sha, "--", "*.py")
    paths = [line.split(":", 1)[1] for line in listed.splitlines() if ":" in line]
    truncated = len(paths) > MAX_CALL_SITE_FILES
    index = binding_index(str(root), head_sha)
    target = Target(anchored_path, anchored_qualname or symbol)
    sites: list[CallSite] = []
    for path in sorted(paths)[:MAX_CALL_SITE_FILES]:
        source = show(repo, head_sha, path)
        if not source:
            continue
        added_here = added.get(path, set())
        for call in calls_in(source, symbol):
            if call.line in added_here:
                continue  # §1: a call site the diff itself added is not a witness
            if path == anchored_path and call.caller == symbol:
                continue  # recursion is not a caller
            bound = index.resolve(
                Reference(path=path, dotted=call.dotted, scope=call.scope)
            )
            if bound != target:
                continue  # it is not this symbol that runs underneath
            sites.append(CallSite(path=path, line=call.line, caller=call.caller))
    return sites, truncated


def witness(
    repo: Path,
    head_sha: str,
    *,
    path: str,
    origin_line: int,
    added: Mapping[str, set[int]],
    head_source: str,
    test_source: str,
) -> Reachability:
    """§1: **(b) always, and at least one of (a) or (c)** -- plus the grade, which
    is decided by what the reproduction did rather than by what the tree allows."""
    definition = enclosing_definition(head_source, origin_line)
    if definition is None:
        return Reachability(
            kind=NONE,
            symbol="",
            reason="the failing line is not inside a definition, or the head source "
            "does not parse; nothing declares a domain",
        )
    symbol = definition.name
    qualname = enclosing_qualname(head_source, origin_line)
    names, annotations = parameter_annotations(definition)
    # (b) is necessary, and an unannotated parameter abstains. This is stricter
    # than the design's "the parameter's annotation admits the input's type":
    # which parameter carried the input is not decidable from the record, so
    # every parameter must declare its domain. The cost is recall in untyped
    # code, which is the decision the design already took, taken once more.
    unannotated = [
        name for name, annotation in zip(names, annotations, strict=True) if not annotation
    ]
    documented = documents_parameter(definition, names)
    sites, truncated = find_call_sites(
        repo,
        head_sha,
        symbol,
        anchored_path=path,
        anchored_qualname=qualname,
        added=added,
    )
    site = sites[0] if sites else None
    # The **grade** says how the reproduction got in and nothing else; the
    # **admissibility** says whether the tree licensed the domain at all. They
    # are separate on purpose: a reproduction that calls the symbol itself is
    # `direct` whether or not a caller exists, and its record then states which
    # of the two reasons keeps it in the drawer.
    called_directly = bool(calls_in(test_source, symbol))
    if called_directly:
        kind = DIRECT
    elif site is not None:
        # D-166: a caller that is itself a test is the change's own coverage,
        # not a dependency on the new code.
        kind = THROUGH_TEST_CALLER if TEST_PATH.search(site.path) else THROUGH_CALLER
    else:
        kind = NONE
    admissible = not unannotated and bool(names) and (site is not None or documented)
    if not names:
        reason = f"`{symbol}` takes no parameter: there is no domain to be inside"
    elif unannotated:
        reason = (
            f"unannotated parameter(s) {', '.join(unannotated)} of `{symbol}`: an input "
            "outside a declared domain is the caller's error, not the code's"
        )
    elif site is None and not documented:
        reason = f"no call site of `{symbol}` outside the added lines and no documented domain" + (
            f" (call-site search truncated at {MAX_CALL_SITE_FILES} files)" if truncated else ""
        )
    elif kind == NONE:
        reason = f"the reproduction neither calls `{symbol}` nor enters at a call site of it"
    elif kind == DIRECT:
        reason = (
            f"the reproduction calls `{symbol}` itself; reachability is argued from the "
            "annotation rather than witnessed in the trace"
        )
    elif kind == THROUGH_TEST_CALLER:
        reason = (
            f"the reproduction enters at {site.path}:{site.line}"  # type: ignore[union-attr]
            f", which is a test: `{symbol}` is covered by the change's own test rather "
            "than depended on by something the change did not add"
        )
    else:
        reason = (
            f"the reproduction enters at {site.path}:{site.line}"  # type: ignore[union-attr]
            f" and `{symbol}` runs underneath"
        )
    return Reachability(
        kind=kind,
        symbol=symbol,
        parameters=names,
        annotations=annotations,
        call_site=site,
        documented=documented,
        admissible=admissible,
        reason=reason,
    )


def classify_origin(
    head_source: str, added_lines: set[int], origins: tuple[RaiseOrigin, ...]
) -> tuple[Origin | None, str]:
    """§2: the first escaped exception raised from a line the diff added, whose
    statement is not a deliberate refusal."""
    kinds = statement_kinds(head_source)
    if kinds is None:
        return None, "the head source does not parse; the statement cannot be read"
    for origin in origins:
        if not origin.escaped:
            continue
        if origin.line not in added_lines:
            continue
        statement = kinds.get(origin.line, "other")
        if statement in {"raise", "assert"}:
            return None, (
                f"line {origin.line} is a deliberate {statement}: head refuses on purpose "
                "(D-102, unchanged)"
            )
        return Origin(
            line=origin.line,
            statement=statement,
            exception_type=origin.exception_type,
            escaped=True,
        ), ""
    if not origins:
        return None, "no exception was raised in a frame of the anchored file"
    return None, "every exception escaped from a line the diff did not add"


def adjudicate(
    *,
    path: str,
    reachability: Reachability,
    origin: Origin | None,
    origin_reason: str,
    runs: tuple[tuple[int, str], ...],
    repeats: int,
    control: ControlRun | None,
    source: str = "live",
) -> GateObservation:
    """The whole publication rule, in one place and with no model in it. A
    `would_publish` observation still publishes nothing: this level is shadow."""

    def observed(would_publish: bool, reason: str) -> GateObservation:
        return GateObservation(
            policy_version=GATE_POLICY_VERSION,
            path=path,
            symbol=reachability.symbol,
            reachability=reachability,
            origin=origin,
            runs=runs,
            repeats=repeats,
            control=control,
            would_publish=would_publish,
            reason=reason,
            source=source,
        )

    if origin is None:
        return observed(False, origin_reason or "no admissible failure")
    if not reachability.admissible:
        return observed(False, reachability.reason)
    if reachability.kind != THROUGH_CALLER:
        return observed(False, reachability.reason)
    if len(runs) < repeats:
        return observed(False, f"{len(runs)} of {repeats} runs recorded")
    if len(set(runs)) != 1:
        return observed(
            False, f"the {len(runs)} runs disagree on the failing line or the exception type"
        )
    if control is None:
        return observed(False, "environment unproven: no control run")
    if not control.passed:
        return observed(False, f"environment unproven: {control.reason}")
    return observed(
        True,
        f"{origin.exception_type} from the added line {path}:{origin.line}, reached from "
        f"{reachability.call_site.path}:{reachability.call_site.line}"  # type: ignore[union-attr]
        f" in {len(runs)}/{repeats} runs; there is no base revision to compare against",
    )


# ---------------------------------------------------------------- the execution


def control_target(repo: Path, head_sha: str, site: CallSite, added: Mapping[str, set[int]]) -> str:
    """A pre-existing test that names the caller of the call site. The design
    asks for a test *of the same call site*; naming the caller is the strongest
    syntactic form of that available without running a coverage pass, and the
    record says which test was chosen."""
    needle = site.caller or Path(site.path).stem
    listed = git(toplevel(repo), "grep", "-l", "-w", "-e", needle, head_sha, "--", "*.py")
    paths = [line.split(":", 1)[1] for line in listed.splitlines() if ":" in line]
    tests = [
        path
        for path in sorted(paths)
        if TEST_PATH.search(path) and not added.get(path) and path != site.path
    ]
    return tests[0] if tests else ""


@dataclass
class HeadOnlyExecution:
    """§3: one head worktree, a collection run, N behavioural runs, and -- only
    when everything else already holds -- one environment control. No base tree
    is ever created, so this cannot produce differential evidence by accident."""

    repo: Path
    candidate: StoredCandidate
    head_sha: str
    limits: ExecutorLimits
    adapter: ExecutorAdapter | None = None
    deadline: float | None = None
    clock: Callable[[], float] | None = None

    def __post_init__(self) -> None:
        self._tree: Path | None = None
        self._controller: Controller | None = None

    @property
    def _root(self) -> Path:
        # D-138: outside the repository tree, like every other execution path
        return gate_root(
            self.repo.resolve(), self.candidate.task_id, self.candidate.finding.finding_id
        )

    def __enter__(self) -> HeadOnlyExecution:
        tree = self._root / "head"
        tree.parent.mkdir(parents=True, exist_ok=True)
        added = subprocess.run(
            ["git", "-C", str(self.repo), "worktree", "add", "--detach", str(tree), self.head_sha],
            capture_output=True,
            text=True,
            check=False,
        )
        self._tree = tree if added.returncode == 0 else None
        self._controller = Controller(self._root)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._tree is not None:
            with suppress(OSError, subprocess.SubprocessError):
                subprocess.run(
                    ["git", "-C", str(self.repo), "worktree", "remove", "--force", str(self._tree)],
                    capture_output=True,
                    check=False,
                )
        with suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                ["git", "-C", str(self.repo), "worktree", "prune"], capture_output=True, check=False
            )

    @property
    def available(self) -> bool:
        return self._tree is not None

    def _run(
        self,
        spec: ReproSpec,
        label: str,
        *,
        node: str | None = None,
        collect_only: bool = False,
        tree_target: str | None = None,
    ) -> ExecutionResult:
        assert self._tree is not None
        effective = self.limits
        if self.deadline is not None and self.clock is not None:
            remaining = self.deadline - self.clock()
            if remaining <= 0:
                return ExecutionResult(
                    outcome=ExecutionOutcome.DEFERRED,
                    reason="shared deadline exceeded before the gate run",
                    exit_code=None,
                    stdout="",
                    stderr="",
                    elapsed_s=0.0,
                    network_blocked=False,
                )
            effective = replace(
                self.limits, wall_timeout_s=min(self.limits.wall_timeout_s, remaining)
            )
        return execute_repro(
            self.repo,
            self.candidate,
            spec,
            effective,
            tree=self._tree,
            run_label=label,
            node=node,
            collect_only=collect_only,
            revision_sha=self.head_sha,
            controller=self._controller,
            adapter=self.adapter,
            tree_target=tree_target,
        )

    def collect(self, spec: ReproSpec) -> ExecutionResult:
        return self._run(spec, "gate-collect", collect_only=True)

    def behavioural(self, spec: ReproSpec, node: str, index: int) -> ExecutionResult:
        return self._run(spec, f"gate-head-{index}", node=node)

    def control(self, target: str) -> ControlRun:
        placeholder = ReproSpec(test_body="# environment control: a pre-existing test\n")
        result = self._run(placeholder, "gate-control", tree_target=target)
        passed = result.outcome is ExecutionOutcome.NOT_REPRODUCED and result.exit_code == 0
        return ControlRun(
            target=target,
            passed=passed,
            reason=result.reason or ("passed" if passed else "did not pass"),
        )


# ------------------------------------------------------------------- the stage

# §5 caps a gate finding at one per pull request, so buying more than a couple
# of reproductions per review is waste: the stage stops at the first observation
# that would publish.
GATE_ATTEMPTS_PER_REVIEW = 2


@dataclass
class GateShadowStage:
    """What one review's shadow gate saw. It is returned so a driver can count
    it; nothing in it is author-visible and nothing in it is a finding."""

    observations: list[tuple[str, GateObservation]]  # (finding id, observation)
    considered: int = 0  # new-code candidates the stage looked at
    admissible: int = 0  # of those, the ones with a static witness
    attempted: int = 0  # of those, the ones a reproduction was bought for
    would_publish: int = 0
    notes: list[str] = field(default_factory=list)


def added_lines(repo: Path, base_sha: str, head_sha: str) -> dict[str, set[int]]:
    from attest.review.diffs import parse_diff

    text = git(repo, "diff", "-U0", f"{base_sha}..{head_sha}")
    return {path: set(lines) for path, lines in parse_diff(text).added_lines.items()}


def write_record(repo: Path, task_id: str, finding_id: str, observation: GateObservation) -> Path:
    """The shadow record. It lives under ``.attest/shadow/``, not under
    ``.attest/evidence/``: an evidence bundle is what a receipt is verified from,
    and nothing here is a receipt."""
    path = repo / ".attest" / "shadow" / "gate" / task_id / f"{finding_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(observation.record(), indent=1, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def run_gate_shadow_stage(
    repo: Path,
    *,
    task_id: str,
    base_sha: str,
    head_sha: str,
    candidates: Sequence[StoredCandidate],
    provider: object,
    budget: object,
    limits: ExecutorLimits | None = None,
    adapter: ExecutorAdapter | None = None,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
    attempts: int = GATE_ATTEMPTS_PER_REVIEW,
    generation_model: str = "",
    ledger: object | None = None,
) -> GateShadowStage:
    """The gate level over one review's **new-code** candidates -- the ones red
    never buys evidence for, because they have no base revision to compare
    against. Shadow: every observation is written to the ledger and to a shadow
    record, and to nothing else."""
    from attest.review.executor import generate_repro

    stage = GateShadowStage(observations=[])
    added = added_lines(repo, base_sha, head_sha)
    ranked = sorted(
        (c for c in candidates if c.eligibility == "new_code"),
        key=lambda c: (-c.wealth, c.finding.finding_id),
    )
    effective_limits = limits or ExecutorLimits()
    for candidate in ranked:
        stage.considered += 1
        path = candidate.finding.file
        head_source = show(repo, head_sha, path)
        # the free pre-check, at the candidate's own anchor: no generation is
        # bought for a symbol whose domain nothing declares, or that nothing
        # outside the diff calls
        static = witness(
            repo,
            head_sha,
            path=path,
            origin_line=candidate.finding.line,
            added=added,
            head_source=head_source,
            test_source="",
        )
        # A finding publishes only at the `through_caller` grade, and that grade
        # needs a call site; a candidate that has only a documented domain can
        # reach `direct` at best, which is the drawer. Buying a reproduction for
        # one would be buying a drawer entry, so the pre-filter demands both.
        if not (static.admissible and static.call_site is not None):
            stage.observations.append(
                (
                    candidate.finding.finding_id,
                    adjudicate(
                        path=path,
                        reachability=static,
                        origin=None,
                        origin_reason=static.reason,
                        runs=(),
                        repeats=GATE_REPEATS,
                        control=None,
                    ),
                )
            )
            continue
        stage.admissible += 1
        if stage.attempted >= attempts or stage.would_publish:
            stage.observations.append(
                (
                    candidate.finding.finding_id,
                    adjudicate(
                        path=path,
                        reachability=static,
                        origin=None,
                        origin_reason=(
                            "not attempted: the per-review attempt cap was reached "
                            "(§5 publishes at most one gate finding per pull request)"
                        ),
                        runs=(),
                        repeats=GATE_REPEATS,
                        control=None,
                    ),
                )
            )
            continue
        stage.attempted += 1
        observation = _attempt(
            repo,
            candidate=candidate,
            head_sha=head_sha,
            base_sha=base_sha,
            added=added,
            head_source=head_source,
            static=static,
            provider=provider,
            budget=budget,
            limits=effective_limits,
            adapter=adapter,
            deadline=deadline,
            clock=clock,
            generation_model=generation_model,
            generate_repro=generate_repro,
        )
        stage.observations.append((candidate.finding.finding_id, observation))
        if observation.would_publish:
            stage.would_publish += 1
    for finding_id, observation in stage.observations:
        write_record(repo, task_id, finding_id, observation)
        if ledger is not None:
            with suppress(OSError, RuntimeError):
                ledger.append(observation.to_ledger_row(task_id, finding_id))  # type: ignore[attr-defined]
    return stage


def _attempt(
    repo: Path,
    *,
    candidate: StoredCandidate,
    head_sha: str,
    base_sha: str,
    added: Mapping[str, set[int]],
    head_source: str,
    static: Reachability,
    provider: object,
    budget: object,
    limits: ExecutorLimits,
    adapter: ExecutorAdapter | None,
    deadline: float | None,
    clock: Callable[[], float],
    generation_model: str,
    generate_repro: Callable[..., ReproSpec],
) -> GateObservation:
    """One paid gate attempt: generate, collect, run N times head-only, and --
    only if everything else already holds -- one environment control."""
    path = candidate.finding.file

    def drawer(reason: str, reach: Reachability | None = None) -> GateObservation:
        return adjudicate(
            path=path,
            reachability=reach or static,
            origin=None,
            origin_reason=reason,
            runs=(),
            repeats=GATE_REPEATS,
            control=None,
        )

    try:
        spec = generate_repro(
            repo,
            candidate,
            provider,
            budget,
            timeout_s=None if deadline is None else max(0.0, deadline - clock()),
            base_ref=None,  # there is no base revision to compare against
            model=generation_model,
        )
    except Exception as exc:  # noqa: BLE001 - generation failures abstain, as red's do
        return drawer(f"generation failed: {type(exc).__name__}")
    with HeadOnlyExecution(
        repo=repo,
        candidate=candidate,
        head_sha=head_sha,
        limits=limits,
        adapter=adapter,
        deadline=deadline,
        clock=clock,
    ) as execution:
        if not execution.available:
            return drawer("head worktree unavailable")
        collected = execution.collect(spec)
        if collected.outcome is ExecutionOutcome.DEFERRED or collected.collected_count != 1:
            return drawer(
                f"collection produced {collected.collected_count} node(s): {collected.reason}"
            )
        node = collected.test_node.split("::", 1)[1] if "::" in collected.test_node else None
        if node is None:
            return drawer("collection reported no node id")
        runs: list[tuple[int, str]] = []
        origins: tuple[RaiseOrigin, ...] = ()
        for index in range(1, GATE_REPEATS + 1):
            result = execution.behavioural(spec, node, index)
            if result.outcome is not ExecutionOutcome.REPRODUCED:
                return drawer(f"head run {index}/{GATE_REPEATS}: {result.reason}")
            origin, reason = classify_origin(
                head_source, set(added.get(path, ())), result.raise_origins
            )
            if origin is None:
                return drawer(reason)
            runs.append((origin.line, origin.exception_type))
            origins = result.raise_origins
        origin, origin_reason = classify_origin(head_source, set(added.get(path, ())), origins)
        reach = witness(
            repo,
            head_sha,
            path=path,
            origin_line=origin.line if origin else candidate.finding.line,
            added=added,
            head_source=head_source,
            test_source=spec.test_body,
        )
        provisional = adjudicate(
            path=path,
            reachability=reach,
            origin=origin,
            origin_reason=origin_reason,
            runs=tuple(runs),
            repeats=GATE_REPEATS,
            control=ControlRun("", True, "pending"),
        )
        if not provisional.would_publish:
            return replace(provisional, control=None)
        site = reach.call_site
        target = "" if site is None else control_target(repo, head_sha, site, added)
        if not target:
            return adjudicate(
                path=path,
                reachability=reach,
                origin=origin,
                origin_reason=origin_reason,
                runs=tuple(runs),
                repeats=GATE_REPEATS,
                control=ControlRun("", False, "no pre-existing test names the caller"),
            )
        control = execution.control(target)
    return adjudicate(
        path=path,
        reachability=reach,
        origin=origin,
        origin_reason=origin_reason,
        runs=tuple(runs),
        repeats=GATE_REPEATS,
        control=control,
    )
