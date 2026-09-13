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


def test_a_generic_method_name_still_finds_its_caller_through_the_index(tmp_path: Path) -> None:
    """A changed method named `parse` used to get no callers at all: the name is
    in the generic list, so the regex path refused to search it. The tree index
    resolves the call through the import it was made with, so the caller in
    `app.py` is context, and the same-named call on an unrelated object is not.
    """
    repo = tmp_path / "repo"
    (repo / "src" / "pkg").mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "Fixture")
    (repo / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "pkg" / "reader.py").write_text(
        "class Reader:\n    def parse(self, text):\n        return text.strip()\n",
        encoding="utf-8",
    )
    (repo / "src" / "pkg" / "app.py").write_text(
        "from pkg.reader import Reader\n\n\n"
        "def load(text):\n    return Reader().parse(text)\n",
        encoding="utf-8",
    )
    (repo / "src" / "pkg" / "other.py").write_text(
        "import json\n\n\ndef decode(text):\n    return json.JSONDecoder().parse(text)\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "src" / "pkg" / "reader.py").write_text(
        "class Reader:\n    def parse(self, text):\n        return text.strip().lower()\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "head changes parse")

    provider = PromptRecorder()
    run_review(repo, base, ReviewConfig(k_samples=1, tier0_commands=[]), provider)

    assert len(provider.prompts) == 1
    prompt = provider.prompts[0]
    assert "caller of `parse` outside the diff: src/pkg/app.py" in prompt
    assert "Reader().parse(text)" in prompt
    assert "src/pkg/other.py" not in prompt
    assert "generic name parse not searched" not in prompt


def test_package_block_puts_the_files_nearest_on_the_import_graph_first(tmp_path: Path) -> None:
    """D-245: within the package, the file that imports the anchored module
    comes before an alphabetically earlier file that never touches it, so a
    block cut at its bound loses the far file, not the importer."""
    from attest.review.planner import package_block

    repo = tmp_path / "repo"
    pkg = repo / "src" / "pkg"
    pkg.mkdir(parents=True)
    (repo / "tests").mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "mod.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (pkg / "aaa_unrelated.py").write_text("Y = 2\n", encoding="utf-8")
    (pkg / "zzz_user.py").write_text("from pkg.mod import add\n\nZ = add(1, 2)\n", encoding="utf-8")
    (repo / "tests" / "test_aaa.py").write_text("def test_nothing():\n    pass\n", encoding="utf-8")
    (repo / "tests" / "test_mod.py").write_text(
        "from pkg.mod import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )

    block = package_block(repo, "src/pkg/mod.py")

    order = [
        block.index("### src/pkg/mod.py"),
        block.index("### src/pkg/zzz_user.py"),
        block.index("### src/pkg/aaa_unrelated.py"),
        block.index("### tests/test_mod.py"),
        block.index("### tests/test_aaa.py"),
    ]
    assert order == sorted(order)


def test_a_call_inside_the_defining_module_on_an_untyped_receiver_is_a_caller(
    tmp_path: Path,
) -> None:
    """D-246 (a) RED: `parser.py` calls `reader.read_regex(...)` from its own
    module-level functions on a parameter the index cannot type; the attribute
    rule counted such a call only from a file that *imports* the defining
    module, and the defining module never imports itself. Twelve callers of
    `python-dotenv-guard_raise-04` vanished that way. The defining module is
    always its own importer, so the caller snippet is context."""
    repo = tmp_path / "repo"
    (repo / "src" / "pkg").mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "Fixture")
    (repo / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "pkg" / "parser.py").write_text(
        "class Reader:\n"
        "    def read_regex(self, regex):\n"
        "        if regex is None:\n"
        "            raise ValueError('no regex')\n"
        "        return regex\n"
        "\n"
        "\n"
        "def parse_key(reader):\n"
        "    return reader.read_regex('key')\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "src" / "pkg" / "parser.py").write_text(
        "class Reader:\n"
        "    def read_regex(self, regex):\n"
        "        return regex\n"
        "\n"
        "\n"
        "def parse_key(reader):\n"
        "    return reader.read_regex('key')\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "head deletes the guard")

    provider = PromptRecorder()
    run_review(repo, base, ReviewConfig(k_samples=1, tier0_commands=[]), provider)

    assert len(provider.prompts) == 1
    prompt = provider.prompts[0]
    assert "caller of `read_regex` outside the diff: src/pkg/parser.py" in prompt
    assert "reader.read_regex('key')" in prompt


def _bigfile(chars: int) -> str:
    return "".join(f"X_{i} = {i}\n" for i in range(chars // 12))


def test_the_plan_row_says_which_files_the_package_block_bound_cut(tmp_path: Path) -> None:
    """D-246 RED (step 3b): the shared package block is cut at its bound and the
    ledger never said which files fell off it, so whether the bound binds on
    real traffic was a recomputation. The plan row carries the anchor, the
    characters kept and the files omitted, by name."""
    from attest.review.ledger import Ledger
    from attest.review.planner import MAX_PACKAGE_BLOCK_CHARS, MAX_PACKAGE_FILE_CHARS

    repo = tmp_path / "repo"
    pkg = repo / "src" / "pkg"
    pkg.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "Fixture")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "mod.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    for name in ("big_a", "big_b", "big_c"):
        (pkg / f"{name}.py").write_text(_bigfile(MAX_PACKAGE_FILE_CHARS + 5_000), encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (pkg / "mod.py").write_text("def add(a, b):\n    return a + b + 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "head")

    run_review(
        repo, base, ReviewConfig(k_samples=1, tier0_commands=[], context_strategy="package-cache"),
        PromptRecorder(),
    )

    row = next(r for r in Ledger(repo).entries() if r["kind"] == "review_plan")
    assert row["schema_version"] == "attest.review-plan.v2"
    block = row["package_block"]
    assert block["anchor"] == "src/pkg/mod.py"
    assert block["bound"] == MAX_PACKAGE_BLOCK_CHARS
    assert 0 < block["chars"] <= MAX_PACKAGE_BLOCK_CHARS
    assert block["files"][0] == "src/pkg/mod.py"
    assert "src/pkg/big_a.py" in block["files"] and "src/pkg/big_b.py" in block["files"]
    assert block["omitted"] == ["src/pkg/big_c.py"]


def test_the_plan_row_records_each_caller_snippet_with_its_resolution(tmp_path: Path) -> None:
    """D-246 RED (step 3c): the plan row counted caller snippets and never said
    how each was resolved, so *exact through an import* and *attribute on an
    untyped receiver* were one number. Each snippet travels with its level."""
    from attest.review.ledger import Ledger

    repo = tmp_path / "repo"
    (repo / "src" / "pkg").mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "Fixture")
    (repo / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    # the untyped caller sits beyond the hunk's three context lines, so the
    # changed symbol the planner reads is `parse` and not its neighbour
    tail = "\n\n# module helpers\n\n\ndef load_untyped(r):\n    return r.parse('x')\n"
    (repo / "src" / "pkg" / "reader.py").write_text(
        "class Reader:\n    def parse(self, text):\n        return text.strip()\n" + tail,
        encoding="utf-8",
    )
    (repo / "src" / "pkg" / "app.py").write_text(
        "from pkg.reader import Reader\n\n\ndef load(text):\n    return Reader().parse(text)\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "src" / "pkg" / "reader.py").write_text(
        "class Reader:\n    def parse(self, text):\n        return text.strip().lower()\n" + tail,
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "head changes parse")

    run_review(repo, base, ReviewConfig(k_samples=1, tier0_commands=[]), PromptRecorder())

    row = next(r for r in Ledger(repo).entries() if r["kind"] == "review_plan")
    (unit,) = row["units"]
    callers = {(c["path"], c["symbol"], c["resolution"]) for c in unit["callers"]}
    assert callers == {
        ("src/pkg/app.py", "parse", "exact"),
        ("src/pkg/reader.py", "parse", "attribute"),
    }
    assert all(c["start"] <= c["end"] for c in unit["callers"])
    assert unit["context"]["caller"] == 2
