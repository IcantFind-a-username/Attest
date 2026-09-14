"""Phase 0 of the contract-evidence plan: the evidence-supply audit over the forty.

For each of the 40 mutation cases (`benchmarks/studies/mutations-v1-recall/sample.jsonl`),
from the trees rebuilt under `.attest/corpora/mutations-v1-recall` (`mutation_recall.py
build`) and arm C's ledgers (`docs/acceptance/evidence/2026-09-14-probe-arms/arm-C`), record
with **no model call and no container**:

    static    the touched symbols under the rule before D-249 (a file of more than
              MAX_SYMBOLS definitions anchored nothing) and under it; what the base tree
              holds *about* those symbols -- literal assertions, object-valued comparators,
              parametrize rows, `raises`, docstring Raises sections, changelog paragraphs;
              and whether the values arm C's probe pinned are specified by the shipped
              rule (`find_specifications`) on the rebuilt base tree with the repaired symbols
    dynamic   the library's own tests that name a touched symbol, run on head and on base
              in the library's own venv: a test that fails on head and passes on base is the
              library catching its own mutant
    report    the markdown table and the numbers the plan's Phase 0 exit condition asks for

Usage:
    .venv/bin/python scripts/corpus/evidence_supply.py static
    .venv/bin/python scripts/corpus/evidence_supply.py dynamic [--only a,b] [--timeout 900]
    .venv/bin/python scripts/corpus/evidence_supply.py report
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import difflib
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))

from mutation_recall import STUDY, WORK, classify  # noqa: E402

from attest.certification.intent import GENERIC_VALUE_REPRS  # noqa: E402
from attest.review.intent import (  # noqa: E402
    DOC_SUFFIXES,
    SKIPPED_DIRS,
    anchored_symbols,
    assertion_pinned_values,
    associated_assertions,
    associated_raises,
    find_specifications,
    is_spec_file,
    names_symbol,
    owned_docstrings,
    symbol_ranges,
)

ARM_C = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-14-probe-arms" / "arm-C"
OUT = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-15-evidence-supply"
REPORT = ROOT / "docs" / "acceptance" / "2026-09-15-evidence-supply.md"
OLD_MAX_SYMBOLS = 200  # the bound `symbol_ranges` refused whole files over, before D-249
CONTEXT_LINES = 3  # V-02's binding reads the hunk with this much context each side
CHANGELOG_RE = re.compile(r"^(change|history|news|release)", re.IGNORECASE)
_PARAGRAPH = re.compile(r"\n[ \t]*\n")
_RAISES_FIELD = re.compile(r":raises?\s+([A-Za-z_][\w.]*)\s*:")
_EXCEPTION_NAME = re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:Error|Exception|Warning))\b")
_RAISES_SECTION = re.compile(
    r"(?:^|\n)[ \t]*Raises[ \t]*:?[ \t]*\n(?:[ \t]*-+[ \t]*\n)?((?:[ \t]+.*\n?)+)"
)
MAX_LISTED = 8


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip()[:300]}")
    return done.stdout


def _checkout(repo: Path, sha: str) -> None:
    _git(repo, "checkout", "-q", "--", ".")
    _git(repo, "checkout", "-q", "--detach", sha)


def head_changed_lines(base: str, head: str) -> tuple[int, ...]:
    """Head-side lines of the hunk, with the binding's context: a replaced or
    inserted range as it stands, a deletion as the head line it left behind."""
    base_lines, head_lines = base.splitlines(), head.splitlines()
    matcher = difflib.SequenceMatcher(None, base_lines, head_lines, autojunk=False)
    lines: set[int] = set()
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            j2 = j1 + 1
        for line in range(j1 + 1 - CONTEXT_LINES, j2 + 1 + CONTEXT_LINES):
            if 1 <= line <= len(head_lines):
                lines.add(line)
    return tuple(sorted(lines))


def symbols_before_d249(base: str, head: str, changed: tuple[int, ...]) -> tuple[str, ...]:
    """What `anchored_symbols` returned before D-249: nothing at all when either
    file held more than OLD_MAX_SYMBOLS definitions."""
    for source in (head, base):
        ranges = symbol_ranges(source)
        if ranges is not None and len(ranges) > OLD_MAX_SYMBOLS:
            return ()
    return anchored_symbols(base_source=base, head_source=head, changed_lines=changed)


# --- what the base tree holds about the symbols ------------------------------------


def _capitalised_calls(node: ast.AST) -> list[str]:
    """Calls whose callee is a capitalised name -- an object being constructed as
    the expected side of a comparison, which `_operand_constants` cannot see."""
    found = []
    for inner in ast.walk(node):
        if isinstance(inner, ast.Call):
            callee = inner.func
            name = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", "")
            if name.lstrip("_")[:1].isupper():
                found.append(ast.unparse(inner)[:80])
    return found


def _object_comparators(associated: str) -> list[str]:
    try:
        tree = ast.parse(associated)
    except SyntaxError:
        return []
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for operand in (node.left, *node.comparators):
                found.extend(_capitalised_calls(operand))
    return found


def _parametrize_rows(text: str, symbols: tuple[str, ...]) -> tuple[int, int]:
    """(rows of parametrize tables on tests naming a symbol, rows holding an object)."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return 0, 0
    patterns = [re.compile(rf"\b{re.escape(s)}\b") for s in symbols]
    rows = objects = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not node.name.startswith("test"):
            continue
        body = ast.get_source_segment(text, node) or ""
        if not any(p.search(body) for p in patterns):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            callee = decorator.func
            name = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", "")
            if name != "parametrize" or len(decorator.args) < 2:
                continue
            table = decorator.args[1]
            if isinstance(table, ast.List | ast.Tuple):
                rows += len(table.elts)
                objects += sum(1 for elt in table.elts if _capitalised_calls(elt))
    return rows, objects


def _tests_naming(text: str, symbols: tuple[str, ...]) -> int:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return 0
    patterns = [re.compile(rf"\b{re.escape(s)}\b") for s in symbols]
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
            "test"
        ):
            body = ast.get_source_segment(text, node) or ""
            if any(p.search(body) for p in patterns):
                count += 1
    return count


def _docstring_raises(source: str, symbols: tuple[str, ...]) -> list[str]:
    """Exception names a touched symbol's own docstring says it raises: Sphinx
    `:raises X:` fields, or a `Raises` section (Google / numpy style)."""
    found: list[str] = []
    for owner, body in owned_docstrings(source):
        if owner not in symbols:
            continue
        found.extend(_RAISES_FIELD.findall(body))
        for section in _RAISES_SECTION.findall(body):
            found.extend(_EXCEPTION_NAME.findall(section))
    return sorted(set(found))


def _walk_tree(repo: Path):
    for current, dirnames, filenames in os.walk(repo):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIPPED_DIRS)
        for filename in sorted(filenames):
            path = Path(current) / filename
            yield path.relative_to(repo), path


def base_supply(repo: Path, anchored: str, symbols: tuple[str, ...]) -> dict:
    """What the tree at its checked-out revision holds about ``symbols``."""
    out: dict = {
        "test_files_naming": [],
        "tests_naming": 0,
        "literal_values": [],
        "object_comparators": [],
        "parametrize_rows": 0,
        "parametrize_object_rows": 0,
        "raises": [],
        "docstring_raises": [],
        "changelog_paragraphs_naming": 0,
        "changelog_files": [],
    }
    if not symbols:
        return out
    literal: dict[str, None] = {}
    objects: list[str] = []
    raises: list[str] = []
    for relative, path in _walk_tree(repo):
        name = relative.name
        if relative.suffix == ".py" and is_spec_file(relative):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            naming = _tests_naming(text, symbols)
            if naming:
                out["tests_naming"] += naming
                out["test_files_naming"].append(relative.as_posix())
            associated = associated_assertions(text, symbols)
            if associated:
                for _kind, value in assertion_pinned_values(associated) or ():
                    shown = repr(value)[:80]
                    if shown not in GENERIC_VALUE_REPRS:
                        literal.setdefault(shown, None)
                objects.extend(_object_comparators(associated))
            rows, object_rows = _parametrize_rows(text, symbols)
            out["parametrize_rows"] += rows
            out["parametrize_object_rows"] += object_rows
            for exc in associated_raises(text, symbols):
                if exc not in raises:
                    raises.append(exc)
        elif CHANGELOG_RE.match(name) and (name.endswith(DOC_SUFFIXES) or name.endswith(".txt")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            naming = sum(1 for block in _PARAGRAPH.split(text) if names_symbol(block, symbols))
            if naming:
                out["changelog_paragraphs_naming"] += naming
                out["changelog_files"].append(relative.as_posix())
    out["literal_values"] = list(literal)[:MAX_LISTED]
    out["object_comparators"] = sorted(set(objects))[:MAX_LISTED]
    out["raises"] = raises
    with contextlib.suppress(OSError):
        out["docstring_raises"] = _docstring_raises(
            (repo / anchored).read_text(encoding="utf-8", errors="replace"), symbols
        )
    return out


class _Repr:
    """A stand-in whose repr is the recorded one, for a pinned value that is not a
    literal (an object's repr): it can match nothing, which is the finding."""

    def __init__(self, text: str) -> None:
        self.text = text

    def __repr__(self) -> str:
        return self.text


def pinned_tuples(reprs: list[str]) -> tuple[tuple[str, object], ...]:
    out: list[tuple[str, object]] = []
    for text in reprs:
        try:
            value = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            out.append(("object", _Repr(text)))
        else:
            out.append((type(value).__name__, value))
    return tuple(out)


# --- arm C, per case -----------------------------------------------------------------


def arm_c_facts(unit_id: str, library: str, site: tuple[str, int]) -> dict:
    trials = {r["unit_id"]: r for r in _read_jsonl(ARM_C / "trials-arm-C.jsonl")}
    trial = trials.get(unit_id)
    if trial is None:
        return {"class": "not run"}
    rows = [r for r in _read_jsonl(ARM_C / f"{library}-ledger.jsonl")
            if r.get("task_id") == trial["task_id"]]
    klass, why = classify(rows, str(trial.get("deferred_reason") or ""), site=site)
    verifications = [r for r in rows if r.get("kind") == "verification"]
    probes = [r for r in rows if r.get("kind") == "probe_observation"]
    notes = [r for r in rows if r.get("kind") == "value_observation_note"]
    intent = {}
    for v in verifications:
        if isinstance(v.get("intent"), dict) and v["intent"].get("policy_version"):
            intent = v["intent"]
            if v.get("outcome") == "reproduced":
                break
    note = notes[0] if notes else {}
    return {
        "class": klass,
        "why": why[:200],
        "pinned_values": list(intent.get("pinned_values") or ()),
        "value_specified": list(intent.get("value_specified") or ()),
        "anchored_symbols_recorded": list(intent.get("anchored_symbols") or ()),
        "exception_type": intent.get("exception_type", ""),
        "value_mismatch": intent.get("value_mismatch"),
        "probes": [p.get("expression", "")[:100] for p in probes],
        "expression": note.get("expression", ""),
        "base": f"{note.get('base_kind', '')}:{str(note.get('base_detail', ''))[:60]}"
        if note else "",
        "head": f"{note.get('head_kind', '')}:{str(note.get('head_detail', ''))[:60]}"
        if note else "",
        "spend_usd": trial.get("spend_usd"),
    }


# --- static -----------------------------------------------------------------------


def _reading(record: dict) -> str:
    """One mechanical sentence per case: which link is missing, from the facts."""
    arm = record["arm_c"]
    klass = arm["class"]
    before, after = record["symbols_before_d249"], record["symbols_after_d249"]
    supply = record["supply"]
    if klass == "certified":
        return "certified"
    if klass in ("not run",):
        return klass
    if not arm["pinned_values"]:
        return "search: no probe made the revisions differ, or the recording was refused"
    distinctive = [v for v in arm["pinned_values"] if v not in GENERIC_VALUE_REPRS]
    specified = {v for v, _site in record["pinned_now_specified"]}
    parts = []
    if not before and after:
        parts.append("symbol bound (D-249)")
    if not after:
        return "no symbol under D-249 either: the changed line sits in no def or class"
    if distinctive and all(v in specified for v in distinctive):
        parts.append("the shipped rule now specifies every pinned value -> certifies")
        return "; ".join(parts)
    if not distinctive:
        parts.append("only generic constants pinned; a (symbol, input, relation) contract "
                     "would not exclude them by value")
    exc = arm.get("exception_type") or ""
    bare = [v.strip("'\"") for v in distinctive]
    pinned_exc = [v for v in bare if v.endswith(("Error", "Exception"))]
    if pinned_exc and any(e in supply["docstring_raises"] for e in pinned_exc):
        parts.append("docstring Raises names the exception (a source the rule does not read)")
    elif pinned_exc and supply["raises"]:
        parts.append(f"base tests expect {supply['raises']} about the symbol, not {pinned_exc}")
    elif pinned_exc:
        parts.append("deleted guard: no test, docstring or changelog names its exception")
    if supply["object_comparators"] or supply["parametrize_object_rows"]:
        parts.append("object-valued expected sides exist (a form the rule cannot read; whether "
                     "one covers a discriminating input is the own-tests column)")
    if supply["changelog_paragraphs_naming"] and not specified:
        parts.append("changelog names the symbol but does not quote the value")
    if not parts:
        parts.append("nothing in the tree specifies this input's outcome")
    if exc and not pinned_exc:
        parts.append(f"head raised {exc}")
    return "; ".join(parts)


def cmd_static(_args: argparse.Namespace) -> int:
    sample = _read_jsonl(STUDY / "sample.jsonl")
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    checked_out: dict[str, str] = {}
    for row in sample:
        unit_id = str(row["unit_id"])
        library = str(row["library"])
        mutation = row["mutation"]
        manifest_path = WORK / "cases" / unit_id / "manifest.json"
        if not manifest_path.is_file():
            records.append({"unit_id": unit_id, "library": library, "error": "case not built"})
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        repo = Path(manifest["repo_path"])
        base_sha, head_sha = manifest["base_sha"], manifest["head_sha"]
        path = str(mutation["path"])
        base_src = _git(repo, "show", f"{base_sha}:{path}")
        head_src = _git(repo, "show", f"{head_sha}:{path}")
        changed = head_changed_lines(base_src, head_src)
        before = symbols_before_d249(base_src, head_src, changed)
        after = anchored_symbols(base_source=base_src, head_source=head_src, changed_lines=changed)
        if checked_out.get(library) != base_sha:
            _checkout(repo, base_sha)
            checked_out[library] = base_sha
        supply = base_supply(repo, path, after)
        site = (path, int(mutation["line"]))
        arm = arm_c_facts(unit_id, library, site)
        pinned = pinned_tuples(arm.get("pinned_values") or [])
        specified, _respecified = (
            find_specifications(base_tree=repo, head_tree=None, pinned=pinned, anchored=path,
                                symbols=after)
            if pinned and after
            else ((), ())
        )
        record = {
            "unit_id": unit_id,
            "library": library,
            "stratum": row["stratum"],
            "site": f"{path}:{mutation['line']}",
            "mutation": str(mutation.get("description", ""))[:120],
            "base_sha": base_sha,
            "head_sha": head_sha,
            "changed_head_lines": list(changed),
            "definitions_in_file": len(symbol_ranges(head_src) or ()),
            "symbols_before_d249": list(before),
            "symbols_after_d249": list(after),
            "supply": supply,
            "arm_c": arm,
            "pinned_now_specified": [list(s) for s in specified],
        }
        record["reading"] = _reading(record)
        records.append(record)
        print(json.dumps({"unit_id": unit_id, "class": arm.get("class"),
                          "symbols": f"{list(before)} -> {list(after)}",
                          "reading": record["reading"]}, ensure_ascii=False), flush=True)
    (OUT / "static.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUT / 'static.json'} ({len(records)} cases)")
    return 0


# --- dynamic ----------------------------------------------------------------------


def _pytest(python: Path, repo: Path, files: list[str], junit: Path, timeout: float) -> dict:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "CI": "1"}
    env.pop("PYTHONPATH", None)
    junit.unlink(missing_ok=True)
    started = time.monotonic()
    try:
        done = subprocess.run(
            [str(python), "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider",
             "-o", "addopts=", "-W", "ignore", f"--junitxml={junit}", *files],
            cwd=repo, env=env, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"exit": None, "timed_out": True, "elapsed_s": round(time.monotonic() - started, 1),
                "failed": [], "collected": 0}
    failed: list[str] = []
    collected = 0
    if junit.is_file():
        for case in ET.parse(junit).getroot().iter("testcase"):
            collected += 1
            if any(child.tag in ("failure", "error") for child in case):
                failed.append(f"{case.get('classname')}::{case.get('name')}")
    return {"exit": done.returncode, "timed_out": False,
            "elapsed_s": round(time.monotonic() - started, 1), "failed": sorted(failed),
            "collected": collected, "tail": done.stdout[-300:]}


def cmd_dynamic(args: argparse.Namespace) -> int:
    static = json.loads((OUT / "static.json").read_text(encoding="utf-8"))
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    results = []
    junit_dir = OUT / "junit"
    junit_dir.mkdir(parents=True, exist_ok=True)
    for record in static:
        unit_id = record["unit_id"]
        if only and unit_id not in only:
            continue
        if "error" in record:
            continue
        library = record["library"]
        repo = WORK / library / "repo"
        python = WORK / library / ".venv" / "bin" / "python"
        files = record["supply"]["test_files_naming"]
        entry = {"unit_id": unit_id, "library": library, "files": files}
        if not files:
            entry["outcome"] = "no test names a touched symbol"
            results.append(entry)
            print(json.dumps(entry), flush=True)
            continue
        _checkout(repo, record["head_sha"])
        head = _pytest(python, repo, files, junit_dir / f"{unit_id}-head.xml", args.timeout)
        _checkout(repo, record["base_sha"])
        base = _pytest(python, repo, files, junit_dir / f"{unit_id}-base.xml", args.timeout)
        detecting = sorted(set(head["failed"]) - set(base["failed"]))
        entry.update({"head": head, "base": base, "detecting": detecting[:MAX_LISTED],
                      "detecting_count": len(detecting)})
        if head["timed_out"] or base["timed_out"]:
            entry["outcome"] = "timed out"
        elif head["collected"] == 0:
            entry["outcome"] = "nothing collected"
        elif detecting:
            entry["outcome"] = "own tests catch the mutant"
        else:
            entry["outcome"] = "own tests pass on the mutant"
        results.append(entry)
        print(json.dumps({"unit_id": unit_id, "outcome": entry["outcome"],
                          "detecting": len(detecting), "head_failed": len(head["failed"]),
                          "base_failed": len(base["failed"]), "collected": head["collected"],
                          "elapsed_s": [head["elapsed_s"], base["elapsed_s"]]}), flush=True)
    path = OUT / "dynamic.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.is_file() and only else []
    merged = {r["unit_id"]: r for r in previous}
    merged.update({r["unit_id"]: r for r in results})
    path.write_text(json.dumps(list(merged.values()), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(merged)} cases)")
    return 0


# --- report -----------------------------------------------------------------------


def _bucket(record: dict, dynamic: dict | None) -> str:
    reading = record["reading"]
    if reading == "certified":
        return "certified (arm C)"
    if reading.startswith("search"):
        return "search: no differential"
    if reading.startswith("no symbol"):
        return "no symbol under D-249 either"
    if "-> certifies" in reading:
        return "specified once the symbol is anchored (D-249)"
    if "docstring Raises" in reading:
        return "docstring Raises names it (unread source)"
    if "object-valued" in reading:
        return "object-valued expected side (unread form)"
    if "only generic" in reading:
        return "generic constant only"
    if "deleted guard" in reading or "base tests expect" in reading:
        return "deleted guard: exception unnamed about the symbol"
    return "nothing in the tree about this input"


def _own_tests_outcome(d: dict | None) -> str:
    """The own-tests column, re-read from the recorded runs: a file that fails to
    collect on both revisions decides nothing, and says so."""
    if d is None:
        return "not run"
    if "head" not in d:
        return d["outcome"]
    head, base = d["head"], d["base"]
    if head["timed_out"] or base["timed_out"]:
        return "timed out"
    if head["collected"] == 0:
        return "nothing collected"
    if d.get("detecting_count"):
        return f"own tests catch the mutant ({d['detecting_count']})"
    if len(base["failed"]) == base["collected"] and len(head["failed"]) == head["collected"]:
        return "inconclusive (the naming files fail on both revisions)"
    return "own tests pass on the mutant"


def cmd_report(_args: argparse.Namespace) -> int:
    static = json.loads((OUT / "static.json").read_text(encoding="utf-8"))
    dynamic_path = OUT / "dynamic.json"
    dynamic = {r["unit_id"]: r for r in json.loads(dynamic_path.read_text())} \
        if dynamic_path.is_file() else {}
    lines = []
    lines.append("| case | stratum | arm C | defs | symbols before → after (D-249) | "
                 "tests naming | literal | object | param rows (obj) | raises | "
                 "docstring Raises | changelog ¶ | pinned | specified now | "
                 "own tests on the mutant | reading |")
    lines.append("|---|---|---|---:|---|---:|---|---|---|---|---|---:|---|---|---|---|")
    buckets: Counter[str] = Counter()
    dynamic_counts: Counter[str] = Counter()
    cross: Counter[tuple[str, str]] = Counter()
    for r in static:
        if "error" in r:
            lines.append(f"| `{r['unit_id']}` | | | | | | | | | | | | | | | {r['error']} |")
            continue
        s, a = r["supply"], r["arm_c"]
        d = dynamic.get(r["unit_id"])
        own = _own_tests_outcome(d)
        dynamic_counts[own.split(" (")[0]] += 1
        bucket = _bucket(r, d)
        buckets[bucket] += 1
        cross[(bucket, own.split(" (")[0])] += 1
        lines.append(
            f"| `{r['unit_id']}` | {r['stratum']} | {a.get('class', '')} | "
            f"{r['definitions_in_file']} | "
            f"{r['symbols_before_d249']} → {r['symbols_after_d249']} | {s['tests_naming']} | "
            f"{', '.join(f'`{v}`' for v in s['literal_values'][:4]) or '—'} | "
            f"{', '.join(f'`{v}`' for v in s['object_comparators'][:3]) or '—'} | "
            f"{s['parametrize_rows']} ({s['parametrize_object_rows']}) | "
            f"{', '.join(s['raises']) or '—'} | {', '.join(s['docstring_raises']) or '—'} | "
            f"{s['changelog_paragraphs_naming']} | "
            f"{', '.join(f'`{v}`' for v in a.get('pinned_values', [])[:3]) or '—'} | "
            f"{', '.join(f'`{v}` ← {p}' for v, p in r['pinned_now_specified'][:2]) or '—'} | "
            f"{own} | {r['reading']} |"
        )
    summary = {
        "cases": len(static),
        "buckets": dict(buckets),
        "own_tests": dict(dynamic_counts),
        "bucket_by_own_tests": {f"{b} | {o}": n for (b, o), n in sorted(cross.items())},
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    (OUT / "table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT / 'table.md'} and {OUT / 'summary.json'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("static").set_defaults(func=cmd_static)
    d = sub.add_parser("dynamic")
    d.add_argument("--only", default="")
    d.add_argument("--timeout", type=float, default=900.0)
    d.set_defaults(func=cmd_dynamic)
    sub.add_parser("report").set_defaults(func=cmd_report)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
