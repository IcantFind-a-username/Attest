"""R-01: the proposer sees bounded repository context, not only the diff."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from attest.review.config import ReviewConfig
from attest.review.proposer import ProviderResult
from attest.review.run import run_review


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


class PromptRecorder:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, object],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        self.prompts.append(prompt)
        return ProviderResult(text=json.dumps({"findings": []}), input_tokens=10, output_tokens=5)


def test_cross_file_defect_context_contains_the_unchanged_caller(tmp_path: Path) -> None:
    """A callee's signature changes in lib.py; its caller in main.py does not.

    The diff never mentions main.py, so the proposer can only see the defect if
    the planner retrieves the caller. The existing test that pins the old
    behaviour is context too.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "Fixture")
    (repo / "lib.py").write_text("def area(w, h):\n    return w * h\n", encoding="utf-8")
    (repo / "main.py").write_text(
        "from lib import area\n\n\ndef report():\n    return area(2, 3)\n", encoding="utf-8"
    )
    (repo / "tests").mkdir()
    (repo / "tests" / "test_lib.py").write_text(
        "from lib import area\n\n\ndef test_area():\n    assert area(2, 3) == 6\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "lib.py").write_text(
        "def area(w, h, unit):\n    return w * h * unit\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "head changes the signature; the caller is untouched")

    provider = PromptRecorder()
    run_review(repo, base, ReviewConfig(k_samples=1, tier0_commands=[]), provider)

    assert len(provider.prompts) == 1
    prompt = provider.prompts[0]
    assert "main.py" in prompt
    assert "area(2, 3)" in prompt
    assert "tests/test_lib.py::test_area" in prompt
    # the old-side definition is visible even though only the head is checked out
    assert "def area(w, h):" in prompt


def test_generation_context_shows_signatures_and_the_nearest_test_module_helpers(
    tmp_path: Path,
) -> None:
    """Fix 4 (2026-09-03): the reproduction generator sees the anchored module's
    function and constructor signatures and the fixtures/helpers of the nearest
    existing test module, so it constructs objects the way the project does."""
    from attest.review.planner import generation_context

    repo = tmp_path / "repo"
    (repo / "services" / "svc" / "src" / "pkg").mkdir(parents=True)
    (repo / "services" / "svc" / "tests").mkdir(parents=True)
    module = repo / "services" / "svc" / "src" / "pkg" / "adapter.py"
    module.write_text(
        "class Adapter:\n"
        "    def __init__(self, config, transport):\n"
        "        self.config = config\n"
        "        self.transport = transport\n\n"
        "    def parse(self, payload):\n"
        "        return payload.upper()\n\n\n"
        "def compute(x, y=3):\n"
        "    return x - y\n",
        encoding="utf-8",
    )
    (repo / "services" / "svc" / "tests" / "test_adapter.py").write_text(
        "import pytest\n"
        "from pkg.adapter import Adapter, compute\n\n\n"
        "@pytest.fixture\n"
        "def adapter():\n"
        "    return Adapter(config={'a': 1}, transport=object())\n\n\n"
        "def _events():\n"
        "    return ['halt']\n\n\n"
        "def test_parse(adapter):\n"
        "    assert adapter.parse('x') == 'X'\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q", "--initial-branch=main"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@example.test",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "-m",
            "base",
        ],
        cwd=repo,
        check=True,
    )
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()

    context = generation_context(repo, base, "services/svc/src/pkg/adapter.py", 10)

    assert "def __init__(self, config, transport)" in context
    assert "def compute(x, y=3)" in context
    assert "@pytest.fixture" in context
    assert "return Adapter(config={'a': 1}, transport=object())" in context
    assert "def _events():" in context
    assert "from pkg.adapter import Adapter, compute" in context
    # helpers are ranked by use and a representative test shows the shape of
    # the inputs the project's tests build (fix 4 amendment, 2026-09-03)
    assert "def test_parse(adapter):" in context
    if "Existing tests naming" in context:
        assert context.index("Nearest existing test module") < context.index(
            "Existing tests naming"
        )


def test_package_block_is_the_anchored_package_and_its_tests_in_a_bounded_order(
    tmp_path: Path,
) -> None:
    """Owner instruction 4 (2026-09-03): the shared block is the anchored
    module first, then the rest of its package, then the project's tests
    directory, each file fenced and the whole bounded."""
    from attest.review.planner import package_block

    repo = tmp_path / "repo"
    pkg = repo / "services" / "svc" / "src" / "pkg"
    (pkg / "sub").mkdir(parents=True)
    (repo / "services" / "svc" / "tests").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "mod.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (pkg / "sub" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "sub" / "deep.py").write_text("X = 1\n", encoding="utf-8")
    (repo / "services" / "svc" / "tests" / "test_mod.py").write_text(
        "def test_add():\n    assert True\n", encoding="utf-8"
    )
    (repo / "unrelated.py").write_text("Y = 2\n", encoding="utf-8")

    block = package_block(repo, "services/svc/src/pkg/mod.py")

    order = [
        block.index("### services/svc/src/pkg/mod.py"),
        block.index("### services/svc/src/pkg/sub/deep.py"),
        block.index("### services/svc/tests/test_mod.py"),
    ]
    assert order == sorted(order)
    assert "unrelated.py" not in block
    assert block.startswith("Shared repository context")


def test_source_units_are_planned_before_documentation_units(tmp_path: Path) -> None:
    """E-04: the per-unit budget must reach code before prose.

    A commit that touches `docs/a.md` and `src/z.py` used to plan the Markdown
    unit first, because units were ordered by path alone; on a large commit the
    budget was spent on anchors eligibility rejects for not being Python.
    """
    from attest.review.diffs import parse_diff
    from attest.review.planner import plan_review

    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "docs" / "a.md").write_text("# a\nprose\n", encoding="utf-8")
    (repo / "src" / "z.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-qm", "base")

    diff = parse_diff(
        "diff --git a/docs/a.md b/docs/a.md\n"
        "--- a/docs/a.md\n+++ b/docs/a.md\n"
        "@@ -1,2 +1,3 @@\n # a\n prose\n+more\n"
        "diff --git a/src/z.py b/src/z.py\n"
        "--- a/src/z.py\n+++ b/src/z.py\n"
        "@@ -1,2 +1,3 @@\n def f():\n     return 1\n+    # tail\n"
    )
    plan = plan_review(repo, diff, "HEAD")
    ordered = [file for unit in plan.units for file in unit.files]
    assert ordered.index("src/z.py") < ordered.index("docs/a.md")


def test_within_a_rank_the_largest_change_is_planned_first(tmp_path: Path) -> None:
    """D-117: after source-before-prose, plan order is changed lines descending.

    Discovery reads the units it reaches in plan order, and the budget stops it
    somewhere in that list. On the real-traffic case the two files carrying the
    regression were the two the review never read: within the source rank the
    order was alphabetical and they sorted last. Size is the only cheap signal
    the plan has about where a defect might be, so the largest change is read
    first; the rank still puts every Python file ahead of every other file.
    """
    from attest.review.diffs import parse_diff
    from attest.review.planner import plan_review

    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    for name in ("a_small.py", "z_large.py"):
        (repo / "src" / name).write_text("x = 1\n", encoding="utf-8")
    (repo / "docs.md").write_text("# d\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-qm", "base")

    added = "".join(f"+line {n}\n" for n in range(1, 21))
    prose = "".join(f"+prose {n}\n" for n in range(1, 40))
    diff = parse_diff(
        "diff --git a/src/a_small.py b/src/a_small.py\n"
        "--- a/src/a_small.py\n+++ b/src/a_small.py\n"
        "@@ -1,1 +1,2 @@\n x = 1\n+y = 2\n"
        "diff --git a/src/z_large.py b/src/z_large.py\n"
        "--- a/src/z_large.py\n+++ b/src/z_large.py\n"
        f"@@ -1,1 +1,21 @@\n x = 1\n{added}"
        "diff --git a/docs.md b/docs.md\n"
        "--- a/docs.md\n+++ b/docs.md\n"
        f"@@ -1,1 +1,40 @@\n # d\n{prose}"
    )
    plan = plan_review(repo, diff, "HEAD")
    ordered = [file for unit in plan.units for file in unit.files]
    assert ordered == ["src/z_large.py", "src/a_small.py", "docs.md"]
