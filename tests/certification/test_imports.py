from __future__ import annotations

import ast
from pathlib import Path

import attest.certification

FORBIDDEN_PREFIXES = (
    "attest.benchmark",
    "attest.cli",
    "attest.core",
    "attest.github",
    "attest.review",
)


def test_certification_package_has_no_product_or_research_imports() -> None:
    package = Path(attest.certification.__file__).parent
    imported: list[str] = []
    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.append(node.module)

    assert not [
        name for name in imported if name.startswith(FORBIDDEN_PREFIXES)
    ]
