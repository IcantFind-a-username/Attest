"""Strict generated-file transfer for free, revision-bound corpus diagnostics."""

import stat
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from runtime_contract_shadow import validate_source_links

from attest.benchmark.artifacts import canonical_json_bytes, sha256_bytes


def apply_wheel(
    tree: Path, wheel: Path, *, revision: str, expected_revision: str,
    expected_digest: str, packages: tuple[str, ...], version_path: str | None = None,
    allow_source_links: bool = False, source_prefix: str = "", source_only: bool = False,
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
    prefix = PurePosixPath(source_prefix)
    if source_prefix and (
        prefix.is_absolute() or ".." in prefix.parts or "\\" in source_prefix
        or ":" in source_prefix or prefix.as_posix() != source_prefix
        or not (tree / source_prefix).is_dir()
        or any((tree / part).is_symlink() for part in (prefix, *prefix.parents))
    ):
        raise ValueError("unsafe source prefix")
    paths = list(tree.rglob("*"))
    if tree.is_symlink() or (not allow_source_links and any(p.is_symlink() for p in paths)):
        raise ValueError("source symlink refused")
    links = validate_source_links(tree) if allow_source_links else {}
    original = {
        p.relative_to(tree).as_posix(): sha256_bytes(p.read_bytes())
        for p in paths if p.is_file()
    }
    additions: dict[str, bytes] = {}
    omitted: dict[str, str] = {}
    omitted_wheel: dict[str, dict[str, str]] = {}
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
            name = (prefix / relative).as_posix() if source_prefix else name
            if source_only and len(relative.parts) == 1 and name.endswith("-nspkg.pth"):
                omitted_wheel[name] = {
                    "reason": "namespace_hook_not_installed",
                    "wheel_sha256": sha256_bytes(archive.read(member)),
                }
                continue
            if relative.parts[0] not in packages and name not in original:
                raise ValueError("unknown package member: " + name)
            payload = archive.read(member)
            if name in original:
                if sha256_bytes(payload) != original[name]:
                    if not source_only:
                        raise ValueError("source overwrite refused: " + name)
                    omitted_wheel[name] = {
                        "reason": "original_source_kept", "source_sha256": original[name],
                        "wheel_sha256": sha256_bytes(payload),
                    }
            elif name.endswith(".so") or name == version_path:
                additions[name] = payload
            elif relative.suffix in {".h", ".hpp", ".c", ".cpp", ".pxd", ".pxi", ".pyx"}:
                # Build inputs are not Python import artifacts. Keep the source
                # export unchanged; a runtime that needs these still must pass.
                omitted[name] = sha256_bytes(payload)
            else:
                raise ValueError("unproven generated file: " + name)
    for name in additions:
        if (tree / name).is_dir() or (tree / name).is_symlink() or any(
            parent.as_posix() in original or parent.as_posix() in additions
            or parent.as_posix() in links or (tree / parent).is_symlink()
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
    if allow_source_links and validate_source_links(tree) != links:
        raise ValueError("source link drift during transfer")
    return {
        **({"source_links_digest": sha256_bytes(canonical_json_bytes(links))}
           if allow_source_links else {}),
        **({"source_prefix": source_prefix} if source_prefix else {}),
        "revision": revision, "wheel_sha256": expected_digest,
        "original_files_digest": sha256_bytes(canonical_json_bytes(original)),
        "added": {name: sha256_bytes(payload) for name, payload in additions.items()},
        "omitted_build_files": omitted,
        **({"omitted_wheel_files": omitted_wheel} if source_only else {}),
    }
