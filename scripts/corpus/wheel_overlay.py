"""Strict generated-file transfer for free, revision-bound corpus diagnostics."""

import stat
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from attest.benchmark.artifacts import canonical_json_bytes, sha256_bytes


def apply_wheel(
    tree: Path, wheel: Path, *, revision: str, expected_revision: str,
    expected_digest: str, packages: tuple[str, ...], version_path: str | None = None,
) -> dict:
    """Check the entire archive before writing; never replace tracked source bytes.

    The caller owns the git export and trusted revision/wheel record. This helper
    binds that record and preserves its tree; it cannot authenticate a fabricated
    caller record or make a compiled module into a certification premise.
    """
    if not revision or revision != expected_revision:
        raise ValueError("revision mismatch")
    if sha256_bytes(wheel.read_bytes()) != expected_digest:
        raise ValueError("wheel digest mismatch")
    paths = list(tree.rglob("*"))
    if tree.is_symlink() or any(p.is_symlink() for p in paths):
        raise ValueError("source symlink refused")
    original = {
        p.relative_to(tree).as_posix(): sha256_bytes(p.read_bytes())
        for p in paths if p.is_file()
    }
    additions: dict[str, bytes] = {}
    with ZipFile(wheel) as archive:
        members = archive.infolist()
        if len(members) > 20000 or sum(m.file_size for m in members) > 512 * 1024 * 1024:
            raise ValueError("wheel resource bound exceeded")
        seen: set[str] = set()
        for member in members:
            name = member.filename
            relative = PurePosixPath(name)
            mode = member.external_attr >> 16
            if (
                relative.is_absolute() or ".." in relative.parts or "\\" in name
                or not relative.parts or name.rstrip("/") != relative.as_posix()
                or name in seen or stat.S_ISLNK(mode)
                or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)
            ):
                raise ValueError("unsafe wheel member: " + name)
            seen.add(name)
            if member.is_dir():
                continue
            if relative.parts[0].endswith(".dist-info"):
                continue
            if relative.parts[0] not in packages:
                raise ValueError("unknown package member: " + name)
            payload = archive.read(member)
            if name in original:
                if sha256_bytes(payload) != original[name]:
                    raise ValueError("source overwrite refused: " + name)
            elif name.endswith(".so") or name == version_path:
                additions[name] = payload
            else:
                raise ValueError("unproven generated file: " + name)
    for name in additions:
        if (tree / name).is_dir() or any(
            parent.as_posix() in original or parent.as_posix() in additions
            for parent in PurePosixPath(name).parents if parent.as_posix() != "."
        ):
            raise ValueError("file/directory collision: " + name)
    for name, payload in additions.items():
        target = tree / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(payload)
        target.chmod(0o644)
    if any(sha256_bytes((tree / name).read_bytes()) != digest for name, digest in original.items()):
        raise ValueError("source drift during transfer")
    return {
        "revision": revision, "wheel_sha256": expected_digest,
        "original_files_digest": sha256_bytes(canonical_json_bytes(original)),
        "added": {name: sha256_bytes(payload) for name, payload in additions.items()},
    }
