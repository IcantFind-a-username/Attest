"""Pre-generation eligibility: which candidates may enter differential V at all.

Classification uses only diff, repository and executor facts — no model call,
no paid generation. It decides *whether* a reproduction is worth buying, never
what the reproduction shows; the executor's post-run evidence classes remain
the authority for what was seen (`INV-CERT-001`, D-020).

Classes:

- ``regression``: the anchor is Python that also exists at the merge-base, so a
  head-fail/base-pass receipt is possible;
- ``new_code``: the anchored file or its enclosing definition is new in this
  change; no base counterfactual exists and the class is unpriced (D-043);
- ``non_python``: the executor has no reproduction path for the anchored file;
- ``unsupported_executor``: this host cannot run the declared executor profile.

Only ``regression`` enters V. Parse failures fail open to ``regression``: a
candidate whose class cannot be determined is still allowed to buy evidence,
and the executor decides on what it actually observes.
"""

from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from attest.review.diffs import DiffInfo
from attest.review.executor import EvidenceClass, _process_containment_unavailable_reason
from attest.review.schema import Finding

ELIGIBILITY_SCHEMA_VERSION = "attest.eligibility.v1"


class EligibilityClass(StrEnum):
    REGRESSION = "regression"
    NEW_CODE = "new_code"
    NON_PYTHON = "non_python"
    UNSUPPORTED_EXECUTOR = "unsupported_executor"


@dataclass(frozen=True)
class Eligibility:
    finding_id: str
    eligibility: EligibilityClass
    reason: str
    required_evidence_class: str | None  # what V would have to show, if eligible

    @property
    def eligible(self) -> bool:
        return self.eligibility is EligibilityClass.REGRESSION

    def to_ledger_row(self, task_id: str) -> dict[str, object]:
        return {
            "kind": "eligibility",
            "schema_version": ELIGIBILITY_SCHEMA_VERSION,
            "task_id": task_id,
            "finding_id": self.finding_id,
            "eligibility": self.eligibility.value,
            "reason": self.reason,
            "required_evidence_class": self.required_evidence_class,
        }


def executor_unavailable_reason() -> str | None:
    """Host-level executor facts, computed once per review."""
    return _process_containment_unavailable_reason()


def show_file_at(repo: Path, ref: str, path: str) -> str | None:
    """File content at ``ref``; None when the path does not exist there."""
    listed = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", ref, "--", path], capture_output=True, text=True
    )
    if listed.returncode != 0 or not listed.stdout.strip():
        return None
    shown = subprocess.run(
        ["git", "-C", str(repo), "show", f"{ref}:{path}"], capture_output=True
    )
    if shown.returncode != 0:
        return None
    return shown.stdout.decode("utf-8", errors="replace")


def _definition_chain(tree: ast.Module, line: int) -> tuple[str, ...]:
    """Names of the nested def/class scopes enclosing ``line``, outermost first."""
    chain: list[str] = []

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = child.lineno
                end = child.end_lineno or child.lineno
                if start <= line <= end:
                    chain.append(child.name)
                    visit(child)
                    return
            visit(child)

    visit(tree)
    return tuple(chain)


def _defines_chain(tree: ast.Module, chain: tuple[str, ...]) -> bool:
    scope: ast.AST = tree
    for name in chain:
        match = next(
            (
                child
                for child in ast.iter_child_nodes(scope)
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and child.name == name
            ),
            None,
        )
        if match is None:
            return False
        scope = match
    return True


def classify_finding(
    repo: Path,
    diff: DiffInfo,
    base_ref: str,
    finding: Finding,
    *,
    executor_reason: str | None,
) -> Eligibility:
    finding_id = finding.finding_id
    required = EvidenceClass.REGRESSION_REPRODUCED.value

    def result(cls: EligibilityClass, reason: str) -> Eligibility:
        return Eligibility(
            finding_id=finding_id,
            eligibility=cls,
            reason=reason,
            required_evidence_class=required if cls is EligibilityClass.REGRESSION else None,
        )

    if executor_reason is not None:
        return result(EligibilityClass.UNSUPPORTED_EXECUTOR, executor_reason)
    if Path(finding.file).suffix.lower() != ".py":
        return result(
            EligibilityClass.NON_PYTHON,
            f"no reproduction executor for {Path(finding.file).suffix or '<no suffix>'} files",
        )
    if finding.file in diff.new_files:
        return result(EligibilityClass.NEW_CODE, "the anchored file is new in this change")
    if finding.line not in diff.added_lines.get(finding.file, set()):
        # context or deleted-side anchor: the code existed before this change
        return result(EligibilityClass.REGRESSION, "anchor is pre-existing code")
    try:
        head_source = (repo / finding.file).read_text(encoding="utf-8", errors="replace")
        head_tree = ast.parse(head_source)
    except (OSError, ValueError, SyntaxError, RecursionError):
        return result(EligibilityClass.REGRESSION, "head file unparsable; class undetermined")
    chain = _definition_chain(head_tree, finding.line)
    if not chain:
        return result(EligibilityClass.REGRESSION, "anchor is module-level code")
    base_source = show_file_at(repo, base_ref, finding.file)
    if base_source is None:
        return result(
            EligibilityClass.NEW_CODE, "the anchored file does not exist at the merge-base"
        )
    try:
        base_tree = ast.parse(base_source)
    except (ValueError, SyntaxError, RecursionError):
        return result(EligibilityClass.REGRESSION, "base file unparsable; class undetermined")
    qualified = ".".join(chain)
    if not _defines_chain(base_tree, chain):
        return result(
            EligibilityClass.NEW_CODE, f"definition {qualified} does not exist at the merge-base"
        )
    return result(EligibilityClass.REGRESSION, f"definition {qualified} exists at the merge-base")
