"""Run frozen, free runtime-contract shadow measurements. No receipt or model service.

The original repository node and an explicitly hashed instrumentation overlay execute
through the existing in-tree executor in the same production container image.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tomllib
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from runtime_contract_cases import NAMES, POSITIVES, build_case  # noqa: E402

from attest.benchmark.artifacts import sha256_bytes, write_canonical_json  # noqa: E402
from attest.execution.backends import select_backend  # noqa: E402
from attest.execution.controller import Controller, ExecutorAdapter  # noqa: E402
from attest.review.candidates import StoredCandidate  # noqa: E402
from attest.review.contract_runtime import (  # noqa: E402
    OBSERVER,
    RuntimeSite,
    discover_sites,
    instrument,
    interpret_pair,
)
from attest.review.executor import (  # noqa: E402
    ExecutionResult,
    ExecutorLimits,
    ReproSpec,
    _changed_files,
    _changed_lines,
    execute_repro,
)
from attest.review.intent import anchored_symbols  # noqa: E402
from attest.review.schema import Finding  # noqa: E402

GAIN_CASES = ("packaging-boundary-08", "packaging-guard_raise-06", "urllib3-none_guard-18")
OBSERVER_SOURCE = ROOT / "src/attest/review/_contract_observer.py"


def archive(repo: Path, sha: str, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    data = subprocess.check_output(["git", "-C", str(repo), "archive", sha])
    subprocess.run(["tar", "-x", "-C", str(destination)], input=data, check=True)


def run_site(
    repo: Path,
    trees: dict[str, Path],
    shas: dict[str, str],
    site: RuntimeSite,
    head: RuntimeSite | None,
    adapter: ExecutorAdapter,
    work: Path,
) -> dict[str, Any]:
    runs: dict[str, ExecutionResult] = {}
    overlays: dict[str, Any] = {}
    record: dict[str, Any] = {
        "base_site": asdict(site),
        "head_site": asdict(head) if head else None,
        "runs": {},
        "overlays": overlays,
        "protocol": {},
    }
    if head is None:
        record["verdict"] = interpret_pair(site, head, runs)
        return record
    for revision, selected in (("base", site), ("head", head)):
        source = (trees[revision] / selected.path).read_text()
        try:
            observed = instrument(source, selected)
        except ValueError as exc:
            record["verdict"] = {"status": "defer", "reason": str(exc), "receipt_eligible": False}
            return record
        overlays[revision] = {
            "original_test_digest": sha256_bytes(source.encode()),
            "observed_test_digest": sha256_bytes(observed.encode()),
            "observer_digest": sha256_bytes(OBSERVER_SOURCE.read_bytes()),
        }
        for mode in ("original", "observed"):
            label = revision + "-" + mode
            tree = work / label
            shutil.copytree(trees[revision], tree)
            if (tree / (OBSERVER + ".py")).exists():
                raise ValueError("observer module path already exists")
            if mode == "observed":
                (tree / selected.path).write_text(observed)
                shutil.copyfile(OBSERVER_SOURCE, tree / (OBSERVER + ".py"))
            body = observed if mode == "observed" else source
            candidate = StoredCandidate(
                "runtime-shadow-" + site.identity,
                Finding(
                    "Runtime contract shadow only", selected.anchor, selected.target_line, "", ""
                ),
                0.0,
                "verify",
                0.1,
            )
            controller = Controller(work / "protocol" / label)
            runs[label] = execute_repro(
                repo,
                candidate,
                ReproSpec(body),
                ExecutorLimits(wall_timeout_s=45, output_bytes=65_536),
                tree=tree,
                tree_target=selected.path,
                node=selected.node,
                run_label=label,
                revision_sha=shas[revision],
                adapter=adapter,
                controller=controller,
            )
            requests = list(controller.root.glob("*/request.json"))
            if len(requests) == 1:
                folder = requests[0].parent
                record["protocol"][label] = {
                    name: json.loads((folder / name).read_text())
                    for name in ("request.json", "result.json")
                    if (folder / name).is_file()
                }
    record["runs"] = {label: asdict(run) for label, run in runs.items()}
    digests = {
        rev + "-" + mode: data[mode + "_test_digest"]
        for rev, data in overlays.items()
        for mode in ("original", "observed")
    }
    record["verdict"] = interpret_pair(site, head, runs, digests=digests)
    return record


def measure(
    label: str,
    repo: Path,
    base_sha: str,
    head_sha: str,
    work: Path,
) -> dict[str, Any]:
    trees = {revision: work / revision for revision in ("base", "head")}
    shas = {"base": base_sha, "head": head_sha}
    for revision in trees:
        archive(repo, shas[revision], trees[revision])
    changed: dict[str, tuple[str, ...]] = {}
    for path in _changed_files(repo, base_sha, head_sha):
        if not path.endswith(".py") or not all((tree / path).is_file() for tree in trees.values()):
            continue
        changed[path] = anchored_symbols(
            base_source=(trees["base"] / path).read_text(),
            head_source=(trees["head"] / path).read_text(),
            changed_lines=_changed_lines(repo, base_sha, head_sha, path),
        )
    base = discover_sites(trees["base"], changed)
    head = discover_sites(trees["head"], changed)
    record: dict[str, Any] = {
        "label": label,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "changed": changed,
        "base_discovery": asdict(base),
        "head_discovery": asdict(head),
        "sites": [],
        "receipt_eligible": False,
    }
    # Preserve zero-site cases explicitly; never treat absent input as a successful test.
    if not base.sites:
        record["reason"] = "no supported assertion site discovered"
        return record
    image_tree = trees["base"]
    declaration = image_tree / "pyproject.toml"
    if declaration.is_file():
        metadata = tomllib.loads(declaration.read_text())
        group = metadata.get("dependency-groups", {}).get("test", [])
        if group:
            if (
                not isinstance(group, list)
                or not all(
                    isinstance(item, str)
                    and len(item) <= 256
                    and "\n" not in item
                    and "\r" not in item
                    and not item.startswith("-")
                    for item in group
                )
                or len(group) > 64
            ):
                record["reason"] = "unsupported base test dependency declaration"
                return record
            image_tree = work / "image-input"
            shutil.copytree(trees["base"], image_tree)
            requirements = image_tree / "requirements-dev.txt"
            old = requirements.read_text() if requirements.exists() else ""
            requirements.write_text(old + "\n" + "\n".join(group) + "\n")
            record["test_environment"] = {
                "source": "base pyproject.toml dependency-groups.test (flat strings only)",
                "declaration_digest": sha256_bytes(declaration.read_bytes()),
                "generated_requirements_digest": sha256_bytes(requirements.read_bytes()),
                "requirements": group,
            }
    backend = select_backend(image_tree, production=True, remaining_s=120)
    record["backend"] = {
        "profile": backend.profile,
        "available": backend.adapter is not None,
        "reason": backend.reason,
    }
    if backend.adapter is None:
        record["reason"] = backend.reason
        return record
    for i, site in enumerate(base.sites):
        matches = [
            s
            for s in head.sites
            if (s.path, s.node, s.assertion, s.anchor, s.symbol)
            == (site.path, site.node, site.assertion, site.anchor, site.symbol)
        ]
        head_site = matches[0] if len(matches) == 1 else None
        record["sites"].append(
            run_site(repo, trees, shas, site, head_site, backend.adapter, work / f"site-{i}")
        )
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--only", default=",".join(NAMES))
    parser.add_argument("--gains", action="store_true")
    args = parser.parse_args()
    for path in (args.work, args.out):
        if not path.resolve().is_relative_to(ROOT):
            raise ValueError("all experiment paths must be inside this repository")
    args.work, args.out = args.work.resolve(), args.out.resolve()
    args.work.mkdir(parents=True, exist_ok=False)
    labels = GAIN_CASES if args.gains else tuple(args.only.split(","))
    if not labels or (not args.gains and any(label not in NAMES for label in labels)):
        raise ValueError("unknown or empty frozen population")
    rows = []
    for label in labels:
        if args.gains:
            manifest = json.loads(
                (
                    ROOT
                    / ".attest/corpora/mutations-v1-recall/cases"
                    / (label + "--forward")
                    / "manifest.json"
                ).read_text()
            )
            repo = Path(manifest["repo_path"]).resolve()
            if not repo.is_relative_to(ROOT / ".attest/corpora"):
                raise ValueError("corpus is outside approved working tree")
            base_sha, head_sha = manifest["base_sha"], manifest["head_sha"]
        else:
            repo, base_sha, head_sha, _ = build_case(label, args.work / "fixtures")
        row = measure(label, repo, base_sha, head_sha, args.work / label)
        row["declared_truth"] = (
            "development_regression" if args.gains or label in POSITIVES else "control"
        )
        rows.append(row)
        write_canonical_json(args.out, rows)
        print(
            json.dumps(
                {
                    "label": label,
                    "sites": len(row["sites"]),
                    "results": [s["verdict"] for s in row["sites"]],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
