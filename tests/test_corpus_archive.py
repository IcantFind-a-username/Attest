"""Corpus export preserves internal links and refuses unsafe archive graphs."""

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/corpus"))
from runtime_contract_shadow import archive  # noqa: E402


@pytest.fixture
def archive_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "assets").mkdir()
    (repo / "assets/icon.svg").write_bytes(b"<svg/>\n")
    return repo


@pytest.fixture
def snapshot(archive_repo: Path) -> Callable[[], str]:
    def capture() -> str:
        subprocess.run(["git", "-C", str(archive_repo), "add", "."], check=True)
        return subprocess.check_output(
            ["git", "-C", str(archive_repo), "write-tree"],
            text=True,
        ).strip()

    return capture


@pytest.mark.parametrize("target", ["../../outside", "/etc/passwd", "missing", "link"])
def test_unsafe_links_refused_before_export(
    archive_repo: Path,
    target: str,
    snapshot: Callable[[], str],
) -> None:
    (archive_repo / "link").symlink_to(target)
    tree = snapshot()
    destination = archive_repo.parent / "export"
    with pytest.raises(ValueError):
        archive(archive_repo, tree, destination)
    assert not destination.exists()


@pytest.mark.parametrize("target", ["assets/icon.svg", "./assets/icon.svg", "assets"])
def test_internal_links_preserve_target_and_bytes(
    archive_repo: Path,
    target: str,
    snapshot: Callable[[], str],
) -> None:
    (archive_repo / "link").symlink_to(target)
    tree = snapshot()
    destination = archive_repo.parent / "export"
    archive(archive_repo, tree, destination)
    assert (destination / "link").is_symlink()
    assert os.readlink(destination / "link") == target
    assert (destination / "assets/icon.svg").read_bytes() == b"<svg/>\n"


@pytest.mark.parametrize(
    ("links", "accepted"),
    [
        ({"first": "assets", "link": "first/icon.svg"}, True),
        ({"first": "assets/icon.svg", "link": "first"}, True),
        ({"first": "second", "second": "first"}, False),
        ({"first": "assets", "link": "first/../../escape"}, False),
        ({"first": "assets/icon.svg", "link": "first/.."}, False),
        ({"first": "assets", "link": "first/../missing"}, False),
    ],
)
def test_link_graph_resolves_in_component_order(
    archive_repo: Path,
    links: dict[str, str],
    accepted: bool,
    snapshot: Callable[[], str],
) -> None:
    for name, target in links.items():
        (archive_repo / name).symlink_to(target)
    tree = snapshot()
    destination = archive_repo.parent / "export"
    if accepted:
        archive(archive_repo, tree, destination)
        assert (destination / "link").read_bytes() == b"<svg/>\n"
        assert {name: os.readlink(destination / name) for name in links} == links
    else:
        with pytest.raises(ValueError):
            archive(archive_repo, tree, destination)
        assert not destination.exists()
