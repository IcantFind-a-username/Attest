"""Generated artifacts cannot overwrite source or cross revision identities."""

import json
import sys
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest

from attest.benchmark.artifacts import sha256_bytes

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/corpus"))
import swebench_source_runtime as source_runtime  # noqa: E402
from wheel_overlay import apply_wheel  # noqa: E402


@pytest.fixture
def wheel_tree(tmp_path: Path) -> tuple[Path, Path]:
    tree = tmp_path / "tree"
    (tree / "pkg").mkdir(parents=True)
    (tree / "pkg/__init__.py").write_bytes(b"VALUE = 1\n")
    return tree, tmp_path / "fixture.whl"


@pytest.mark.parametrize(
    "kind", ["revision", "digest", "overwrite", "traversal", "symlink", "python", "collision"]
)
def test_refuses_before_any_transfer(wheel_tree: tuple[Path, Path], kind: str) -> None:
    tree, wheel = wheel_tree
    with ZipFile(wheel, "w") as z:
        z.writestr("pkg/native.so", b"fixture native bytes")
        if kind == "overwrite":
            z.writestr("pkg/__init__.py", b"VALUE = 2\n")
        elif kind == "traversal":
            z.writestr("../escape.so", b"escape")
        elif kind == "symlink":
            info = ZipInfo("pkg/link.so")
            info.external_attr = 0o120777 << 16
            z.writestr(info, "../escape")
        elif kind == "python":
            z.writestr("pkg/injected.py", b"VALUE = 2\n")
        elif kind == "collision":
            z.writestr("pkg/native.so/other.so", b"nested native bytes")
    with pytest.raises(ValueError):
        apply_wheel(
            tree, wheel, revision="a" * 40,
            expected_revision=("b" if kind == "revision" else "a") * 40,
            expected_digest="wrong" if kind == "digest" else sha256_bytes(wheel.read_bytes()),
            packages=("pkg",),
        )
    assert not (tree / "pkg/native.so").exists()
    assert (tree / "pkg/__init__.py").read_bytes() == b"VALUE = 1\n"


def test_generated_additions_preserve_source(wheel_tree: tuple[Path, Path]) -> None:
    tree, wheel = wheel_tree
    with ZipFile(wheel, "w") as z:
        z.writestr("pkg/__init__.py", b"VALUE = 1\n")
        z.writestr("pkg/native.so", b"fixture native bytes")
        z.writestr("pkg/_version.py", b"version = '0.1'\n")
        z.writestr("pkg/generated.h", b"/* build header */\n")
        z.writestr("fixture-0.1.dist-info/METADATA", b"Name: fixture\n")
    result = apply_wheel(
        tree, wheel, revision="a" * 40, expected_revision="a" * 40,
        expected_digest=sha256_bytes(wheel.read_bytes()), packages=("pkg",),
        version_path="pkg/_version.py",
    )
    assert set(result["added"]) == {"pkg/native.so", "pkg/_version.py"}
    assert set(result["omitted_build_files"]) == {"pkg/generated.h"}
    assert not (tree / "pkg/generated.h").exists()
    assert (tree / "pkg/__init__.py").read_bytes() == b"VALUE = 1\n"


@pytest.mark.parametrize("link_target", ["data.txt", "../pkg/data.txt"])
def test_safe_source_link_survives_wheel_transfer(
    wheel_tree: tuple[Path, Path], link_target: str,
) -> None:
    tree, wheel = wheel_tree
    (tree / "pkg/data.txt").write_bytes(b"data")
    (tree / "pkg/link.txt").symlink_to(link_target)
    with ZipFile(wheel, "w") as z:
        z.writestr("pkg/link.txt", b"data")
        z.writestr("pkg/native.so", b"native")
    apply_wheel(
        tree, wheel, revision="a", expected_revision="a",
        expected_digest=sha256_bytes(wheel.read_bytes()), packages=("pkg",),
        allow_source_links=True,
    )
    assert (tree / "pkg/link.txt").is_symlink()
    assert (tree / "pkg/link.txt").read_bytes() == b"data"
    assert (tree / "pkg/native.so").read_bytes() == b"native"


@pytest.mark.parametrize("target", ["../../outside", "/etc/passwd", "missing", "link.txt"])
def test_unsafe_source_link_still_refused(wheel_tree: tuple[Path, Path], target: str) -> None:
    tree, wheel = wheel_tree
    (tree / "pkg/link.txt").symlink_to(target)
    with ZipFile(wheel, "w") as z:
        z.writestr("pkg/native.so", b"native")
    with pytest.raises(ValueError):
        apply_wheel(
            tree, wheel, revision="a", expected_revision="a",
            expected_digest=sha256_bytes(wheel.read_bytes()), packages=("pkg",),
            allow_source_links=True,
        )
    assert not (tree / "pkg/native.so").exists()


@pytest.mark.parametrize("alias", ["alias", "ALIAS"])
def test_wheel_cannot_add_below_source_directory_link(
    wheel_tree: tuple[Path, Path], alias: str,
) -> None:
    tree, wheel = wheel_tree
    (tree / "pkg/real").mkdir()
    (tree / "pkg/alias").symlink_to("real")
    with ZipFile(wheel, "w") as z:
        z.writestr(f"pkg/{alias}/native.so", b"native")
    if (tree / "pkg" / alias).is_symlink():
        with pytest.raises(ValueError):
            apply_wheel(
                tree, wheel, revision="a", expected_revision="a",
                expected_digest=sha256_bytes(wheel.read_bytes()), packages=("pkg",),
                allow_source_links=True,
            )
    else:
        # On a case-sensitive filesystem ALIAS is a distinct, safe new directory.
        apply_wheel(
            tree, wheel, revision="a", expected_revision="a",
            expected_digest=sha256_bytes(wheel.read_bytes()), packages=("pkg",),
            allow_source_links=True,
        )
        assert (tree / "pkg" / alias / "native.so").read_bytes() == b"native"
    assert not (tree / "pkg/real/native.so").exists()


@pytest.mark.parametrize("pure", [True, False])
def test_source_runtime_requires_pure_metadata_without_native_artifact(
    wheel_tree: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, pure: bool,
) -> None:
    tree, wheel = wheel_tree
    with ZipFile(wheel, "w") as z:
        z.writestr("fixture.dist-info/WHEEL", f"Root-Is-Purelib: {str(pure).lower()}\n")
    monkeypatch.setattr(source_runtime, "constraints", lambda *_: ("", ""))

    def stop_at_image_build(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("image build boundary reached")

    monkeypatch.setattr(source_runtime, "build", stop_at_image_build)
    directory = tree.parent / "runtime"
    directory.mkdir()
    state: dict = {}
    expected = RuntimeError if pure else ValueError
    with pytest.raises(expected, match="image build boundary|non-pure wheel"):
        source_runtime.check_runtime(
            directory, tree, wheel, "a", sha256_bytes(wheel.read_bytes()), "a",
            "2023-01-01T00:00:00Z", "unused", {}, state,
            builder="unused", allow_source_links=True,
        )
    assert state["stage"] == ("runtime_image" if pure else "transfer")
    if pure:
        transfer = json.loads((directory / "transfer.json").read_bytes())
        assert transfer["pure_python_source"] is True
        assert transfer["added"] == {}
    assert (tree / "pkg/__init__.py").read_bytes() == b"VALUE = 1\n"
