"""One image per dependency set, reused across every commit that shares it (D-156).

The reproduction image is the slowest thing a review builds, and two commits of
one repository almost always declare the same dependencies. The tag is a digest
of the interpreter and of the tree's dependency manifests -- **the lock files
included** -- so a commit that changed only source code reuses the image, and a
commit that moved a pin does not.

Whether the reuse actually happens is recorded rather than hoped for: the image
carries `cached`, and the verification stage writes it to the ledger.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from attest.execution import container_adapter, container_images

IDENTIFIER = "sha256:" + "ab" * 32


@pytest.fixture
def daemon(monkeypatch: pytest.MonkeyPatch):
    """A docker whose cache holds exactly the tags it has been asked to build."""
    built: list[str] = []
    known: set[str] = set()

    def run(args: object, **kwargs: object) -> object:
        assert isinstance(args, list)
        if args[1:3] == ["image", "inspect"]:
            return subprocess.CompletedProcess(args, 1, "", "No such image")
        if args[1:2] == ["images"]:
            tag = args[-1]
            hit = any(tag == known_tag for known_tag in known)
            return subprocess.CompletedProcess(args, 0, (IDENTIFIER + "\n") if hit else "", "")
        if args[1:2] == ["build"]:
            tag = args[args.index("--tag") + 1]
            built.append(tag)
            known.add(tag)
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(f"unexpected docker call: {args}")

    monkeypatch.setattr(container_adapter.subprocess, "run", run)
    monkeypatch.setattr(container_images, "docker_executable", lambda: "/usr/bin/docker")
    return built


def _tree(path: Path, *, lock: str, source: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nrequires-python = ">=3.11"\n', encoding="utf-8"
    )
    (path / "poetry.lock").write_text(lock, encoding="utf-8")
    (path / "app.py").write_text(source, encoding="utf-8")
    return path


def test_the_same_lock_file_is_not_rebuilt_on_the_next_commit(
    tmp_path: Path, daemon: list[str]
) -> None:
    first = _tree(tmp_path / "c1", lock='name = "requests"\nversion = "2.31.0"\n', source="a = 1\n")
    second = _tree(tmp_path / "c2", lock='name = "requests"\nversion = "2.31.0"\n', source="a = 2\n")

    built = container_images.ensure_image(first)
    reused = container_images.ensure_image(second)

    assert built.cached is False and built.build_elapsed_s >= 0.0
    assert reused.cached is True
    assert reused.tag == built.tag
    assert daemon == [built.tag], "the second commit rebuilt an image it could have reused"


def test_a_moved_pin_is_a_different_image(tmp_path: Path, daemon: list[str]) -> None:
    first = _tree(tmp_path / "c1", lock='name = "requests"\nversion = "2.31.0"\n', source="a = 1\n")
    second = _tree(tmp_path / "c2", lock='name = "requests"\nversion = "2.32.0"\n', source="a = 1\n")

    one = container_images.ensure_image(first)
    two = container_images.ensure_image(second)

    assert one.tag != two.tag
    assert two.cached is False
    assert len(daemon) == 2


@pytest.mark.parametrize("name", sorted(container_images.LOCK_MANIFESTS))
def test_every_lock_file_the_product_names_is_part_of_the_key(
    tmp_path: Path, daemon: list[str], name: str
) -> None:
    first = tmp_path / f"{name}-1"
    second = tmp_path / f"{name}-2"
    for tree, body in ((first, "one"), (second, "two")):
        tree.mkdir(parents=True)
        (tree / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        (tree / name).write_text(body, encoding="utf-8")

    assert container_images.ensure_image(first).tag != container_images.ensure_image(second).tag
