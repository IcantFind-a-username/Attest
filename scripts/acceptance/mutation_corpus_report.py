"""The mutations-v1 corpus report (work order PR 3 e of 2026-09-12): per library,
how many lines its own tests reach, how many mutation sites of each class sat on
those lines, how many were injected, and why a library was skipped. Free: reads
`report.json` and `manifest.jsonl` already on disk.

    python scripts/acceptance/mutation_corpus_report.py \\
        --corpus .attest/corpora/mutations-v1 \\
        --out docs/acceptance/2026-09-12-mutation-corpus.md
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

CLASSES = ("guard_raise", "boundary", "none_guard")
CLASS_TEXT = {
    "guard_raise": "an `if …: raise …` validation deleted",
    "boundary": "a `<=`/`<` (or `>=`/`>`) boundary swapped",
    "none_guard": "an `if x is None: return …` guard deleted",
}


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def build(corpus: Path) -> str:
    report = json.loads((corpus / "report.json").read_text(encoding="utf-8"))
    manifests = [
        json.loads(line)
        for line in (corpus / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    libraries = sorted(report["libraries"], key=lambda row: str(row["library"]))
    built = [row for row in libraries if "skipped" not in row]
    skipped = [row for row in libraries if "skipped" in row]
    by_direction = Counter(m["shape"].split(":")[0] for m in manifests)
    by_class = Counter(m["mutation"]["kind"] for m in manifests)
    out: list[str] = []
    out.append("# mutations-v1 — a crash-mutation corpus over eight public clones, built for $0")
    out.append("")
    out.append(
        "**Work order PR 3 e of the 2026-09-12 overnight window.** For each of the eight "
        "`G-NULL-001a` clones at its default-branch tip, the library's **own** test suite ran "
        "under `coverage` on this host to find the lines its tests reach; three classes of crash "
        "mutation were then injected on covered lines of the package's own source, each as its "
        "own commit off the tip, and every mutation yields two cases in the `swebench_pilot` "
        "manifest shape — **forward** (base = the original, head = the mutation: the pull "
        "request that introduces the defect) and **fix** (base = the mutation, head = the "
        "original). **No review was bought and nothing here was reviewed.** The corpus lives "
        "under `.attest/corpora/mutations-v1/` and is not committed."
    )
    out.append("")
    out.append("| | |")
    out.append("|---|---|")
    out.append(f"| libraries with cases | **{len(built)}** of 8 |")
    out.append(f"| libraries skipped | **{len(skipped)}** |")
    out.append(
        f"| mutations injected | **{sum(int(r['mutations_applied']) for r in built)}** "
        f"({', '.join(f'{k} {by_class.get(k, 0) // 2}' for k in CLASSES)}) |"
    )
    out.append(
        f"| cases | **{len(manifests)}** ({by_direction.get('forward', 0)} forward, "
        f"{by_direction.get('fix', 0)} fix) |"
    )
    out.append(
        f"| covered lines, all built libraries | "
        f"{sum(int(r['covered_lines']) for r in built)} in "
        f"{sum(int(r['covered_files']) for r in built)} package files |"
    )
    out.append("")
    out.append("## 1. Per library")
    out.append("")
    out.append(
        "| library | tip | covered files | covered lines | sites found (raise / boundary / None) "
        "| injected (raise / boundary / None) | cases | suite wall time |"
    )
    out.append("|---|---|---|---|---|---|---|---|")
    for row in built:
        found = row["sites_found"]
        applied = row["applied_by_class"]
        out.append(
            f"| `{row['library']}` | `{str(row['tip'])[:12]}` | {row['covered_files']} | "
            f"{row['covered_lines']} | {found['guard_raise']} / {found['boundary']} / "
            f"{found['none_guard']} | {applied['guard_raise']} / {applied['boundary']} / "
            f"{applied['none_guard']} | {row['cases']} | {row.get('elapsed_s', '')}s |"
        )
    out.append("")
    if skipped:
        out.append("## 2. Skipped, by name and reason")
        out.append("")
        out.append("| library | tip | reason |")
        out.append("|---|---|---|")
        for row in skipped:
            out.append(
                f"| `{row['library']}` | `{str(row.get('tip', ''))[:12]}` | "
                f"{_cell(str(row['skipped'])[:300])} |"
            )
        out.append("")
    out.append("## 3. The three classes, and the cap")
    out.append("")
    for kind in CLASSES:
        out.append(f"- **{kind}** — {CLASS_TEXT[kind]}.")
    out.append(
        "- At most **6 per class per library**, taken in `(file, line)` order among the sites "
        "the library's own tests reach; a site whose mutation does not parse is skipped. "
        "The cap is what makes the corpus a sample rather than an exhaustive walk, and the "
        "`sites found` column says how much was left."
    )
    out.append("")
    out.append("## 4. What the corpus is for, and what it is not")
    out.append("")
    out.append(
        "- A **fix-direction** case is the shape the held-out slice already measures (a repairing "
        "commit's parent against the commit); a **forward** case is the shape E-04 reviews (a "
        "pull request introducing a change). Both directions of the same mutation let one "
        "defect be asked from both sides."
    )
    out.append(
        "- **Not a recall figure.** Nothing here has been reviewed; a library's own tests may or "
        "may not catch each mutation (that was not measured — running every suite once per "
        "mutation is hours), so the corpus does not yet say which defects are *silent* in the "
        "library. That column is the first thing to add before any paid run over it."
    )
    out.append(
        "- **A known limit of the boundary class.** The rule takes any `<`/`<=`/`>`/`>=` on a "
        "covered line, so compatibility modules contribute comparisons on `sys.version_info` "
        "(`attrs` `src/attr/_compat.py:11` is one), which are not the class the corpus is "
        "named for and whose mutation changes nothing on the interpreter that runs the "
        "tests. A later version should exclude comparisons whose operands are version "
        "tuples; the cases are listed rather than removed so the count is honest."
    )
    out.append(
        "- **Not committed.** Manifests carry absolute host paths and real commit shas of "
        "worktrees under `.attest/`; the corpus is rebuilt by "
        "`scripts/corpus/mutate.py` from the same tips."
    )
    out.append("")
    out.append("## 5. Every case")
    out.append("")
    out.append("| case | library | class | site | base | head |")
    out.append("|---|---|---|---|---|---|")
    for m in sorted(manifests, key=lambda m: str(m["instance_id"])):
        site = m["mutation"]
        out.append(
            f"| `{m['instance_id']}` | `{m['repo']}` | {site['kind']} | "
            f"`{site['path']}:{site['line']}` | `{str(m['base_sha'])[:8]}` | "
            f"`{str(m['head_sha'])[:8]}` |"
        )
    out.append("")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=".attest/corpora/mutations-v1")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    Path(args.out).write_text(build(Path(args.corpus)), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
