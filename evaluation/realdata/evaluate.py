"""Run the real-data evaluation and emit JSON + a markdown summary.

Usage: python -m realdata.evaluate --repos DIR [DIR ...] --out DIR
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from realdata.corpus import Case, _git, build_cases
from realdata.measures import (
    classify_unparsed_files,
    measure_anchor_admissibility,
    measure_budget,
    measure_hunk_fidelity,
    measure_tier0,
    reachable_decisions,
    wealth_table,
)

from attest.review.channels import gate_feasibility, max_reachable_wealth
from attest.review.diffs import parse_diff

ALPHA = 0.1


def _pct(num: int, den: int) -> float:
    return round(100.0 * num / den, 1) if den else 0.0


def bootstrap_lr(tier0_rows: list[dict], iters: int = 4000, seed: int = 20260829) -> dict:
    """95% CI for the empirical T-channel likelihood ratio.

    Lines inside one case share a file and a single lint run, so they are not
    independent draws. Resampling is therefore done over CASES (a cluster
    bootstrap); a per-line bootstrap would report a spuriously tight interval.
    """
    rng = random.Random(seed)
    n = len(tier0_rows)
    if n == 0:
        return {}
    ratios = []
    for _ in range(iters):
        sample = [tier0_rows[rng.randrange(n)] for _ in range(n)]
        tl = sum(x["true_lines"] for x in sample)
        tlh = sum(x["true_lines_with_signal"] for x in sample)
        bg = sum(x["background_lines"] for x in sample)
        bgh = sum(x["background_lines_with_signal"] for x in sample)
        if tl and bg and bgh:
            ratios.append((tlh / tl) / (bgh / bg))
    if len(ratios) < iters // 2:
        return {"note": "too few resamples with usable background rate"}
    ratios.sort()
    return {
        "lr_ci95_low": round(ratios[int(0.025 * len(ratios))], 2),
        "lr_ci95_high": round(ratios[int(0.975 * len(ratios))], 2),
        "resamples": len(ratios),
    }


def sweep_real_commits(repo: Path, n: int = 120) -> list[dict]:
    """Whole-commit diffs (every file, every type) — the realistic PR shape."""
    shas = _git(repo, "log", "--no-merges", f"-n{n}", "--pretty=format:%H").split()
    rows = []
    for sha in shas:
        try:
            text = _git(repo, "diff", "--no-color", f"{sha}^", sha)
        except Exception:  # noqa: BLE001 - a repo-side git failure just skips the commit
            continue
        if not text.strip():
            continue
        info = parse_diff(text)
        named = _git(repo, "diff", "--no-color", "--name-only", f"{sha}^", sha).split("\n")
        named = [f for f in named if f.strip()]
        row = {"repo": repo.name, "sha": sha, "files_named": len(named),
               "files_parsed": len(info.files)}
        if len(named) != len(info.files):
            row["unparsed"] = classify_unparsed_files(repo, sha, set(info.files))
        row.update(measure_budget(text))
        rows.append(row)
    return rows


def run(repo_dirs: list[Path], out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(max_workers=len(repo_dirs)) as pool:
        per_repo = list(pool.map(lambda r: build_cases(r), repo_dirs))
    cases: list[tuple[Path, Case]] = [
        (repo, c) for repo, cs in zip(repo_dirs, per_repo, strict=True) for c in cs
    ]
    print(f"corpus: {len(cases)} cases from {len(repo_dirs)} repositories")

    records = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, (repo, case) in enumerate(cases):
            work = Path(tmp) / f"case{i}"
            work.mkdir()
            rec = {
                "repo": case.repo,
                "label": case.label,
                "sha": case.fix_sha,
                "path": case.path,
                "subject": case.subject,
                "omission": case.omission,
                "n_true_lines": len(case.true_lines),
                "fidelity": measure_hunk_fidelity(repo, case),
                "anchor": measure_anchor_admissibility(case),
                "tier0": measure_tier0(repo, case, work),
                "budget": measure_budget(case.diff_text),
            }
            records.append(rec)
            if (i + 1) % 25 == 0:
                print(f"  {i + 1}/{len(cases)} cases measured")

    with ThreadPoolExecutor(max_workers=len(repo_dirs)) as pool:
        sweeps = [row for rows in pool.map(sweep_real_commits, repo_dirs) for row in rows]
    print(f"pr-shape sweep: {len(sweeps)} whole-commit diffs")

    report = {
        "alpha": ALPHA,
        "n_cases": len(records),
        "records": records,
        "pr_sweep": sweeps,
        "wealth_table": wealth_table(ALPHA),
        "reachable_decisions": reachable_decisions(ALPHA),
        "gate_feasibility": gate_feasibility(ALPHA),
        "max_reachable": {
            "without_verification": max_reachable_wealth(False),
            "with_verification": max_reachable_wealth(True),
        },
    }
    (out_dir / "raw.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (out_dir / "summary.json").write_text(
        json.dumps(summarize(report), indent=1), encoding="utf-8"
    )
    return report


def summarize(report: dict) -> dict:
    recs = report["records"]
    pos = [r for r in recs if r["label"] == "positive"]
    neg = [r for r in recs if r["label"] == "negative"]

    fid_checked = sum(r["fidelity"].get("checked", 0) for r in recs)
    fid = {
        "hunks_checked": fid_checked,
        "range_mismatch": sum(r["fidelity"].get("range_mismatch", 0) for r in recs),
        "content_mismatch": sum(r["fidelity"].get("content_mismatch", 0) for r in recs),
        "past_eof": sum(r["fidelity"].get("past_eof", 0) for r in recs),
        "files_dropped": sum(r["fidelity"].get("files_dropped", 0) for r in recs),
        "blob_unavailable": sum(r["fidelity"].get("skipped", 0) for r in recs),
    }

    anchored = [r for r in pos if r["anchor"].get("has_true_line")]
    keys = ["exact_path", "basename_only", "b_prefixed", "a_prefixed", "backslashes",
            "dot_slash", "off_by_one_lo", "off_by_one_hi", "all_true_lines_in_hunk"]
    anchor = {
        "positives": len(pos),
        "omission_bugs": sum(1 for r in pos if r["omission"]),
        "with_true_line": len(anchored),
        **{k: _pct(sum(1 for r in anchored if r["anchor"].get(k)), len(anchored)) for k in keys},
    }

    def t_agg(rows: list[dict]) -> dict:
        all_t = [r["tier0"] for r in rows if "skipped" not in r["tier0"]]
        t = [x for x in all_t if x.get("ruff_ran")]
        tl = sum(x["true_lines"] for x in t)
        tlh = sum(x["true_lines_with_signal"] for x in t)
        bg = sum(x["background_lines"] for x in t)
        bgh = sum(x["background_lines_with_signal"] for x in t)
        secs = [x["tier0_seconds"] for x in t]
        return {
            "cases": len(t),
            "cases_ruff_failed": len(all_t) - len(t),
            "true_lines": tl,
            "true_lines_with_signal_pct": _pct(tlh, tl),
            "background_lines": bg,
            "background_lines_with_signal_pct": _pct(bgh, bg),
            "empirical_lr": round((tlh / tl) / (bgh / bg), 2) if tl and bg and bgh else None,
            "cases_with_any_in_hunk_signal_pct": _pct(
                sum(1 for x in t if x["any_in_hunk_signal"]), len(t)
            ),
            "tier0_p50_s": round(statistics.median(secs), 3) if secs else None,
            "tier0_max_s": round(max(secs), 3) if secs else None,
            **bootstrap_lr(t),
        }

    sweep = report["pr_sweep"]
    costs = sorted(r["est_cost_k"] for r in sweep)
    budget = {
        "commits": len(sweep),
        "deferred_pct": _pct(sum(1 for r in sweep if r["deferred"]), len(sweep)),
        "est_cost_k_p50": round(costs[len(costs) // 2], 4) if costs else None,
        "est_cost_k_p90": round(costs[int(len(costs) * 0.9)], 4) if costs else None,
        "est_cost_k_max": round(costs[-1], 4) if costs else None,
        "files_named_vs_parsed_mismatch": sum(
            1 for r in sweep if r["files_named"] != r["files_parsed"]
        ),
    }
    unparsed: dict[str, int] = {}
    for r in sweep:
        for kind, count in r.get("unparsed", {}).items():
            unparsed[kind] = unparsed.get(kind, 0) + count
    budget["unparsed_files_by_reason"] = unparsed

    return {
        "corpus": {"positive": len(pos), "negative": len(neg),
                   "repos": sorted({r["repo"] for r in recs})},
        "hunk_fidelity": fid,
        "anchor_admissibility_pct": anchor,
        "tier0_positive": t_agg(pos),
        "tier0_negative": t_agg(neg),
        "budget_pr_shape": budget,
        "gate": {
            "max_wealth_without_verification": report["max_reachable"]["without_verification"],
            "threshold": 1.0 / report["alpha"],
            "surfacing_rows_without_verification": sum(
                1 for r in report["wealth_table"] if r["surfaces"]
            ),
            **{k: v for k, v in report["reachable_decisions"].items() if k != "rows"},
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos", nargs="*", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument("--from-raw", action="store_true", help="re-summarize an existing raw.json")
    args = ap.parse_args()
    out = Path(args.out)
    if args.from_raw:
        report = json.loads((out / "raw.json").read_text(encoding="utf-8"))
    else:
        report = run([Path(r) for r in args.repos], out)
    summary = summarize(report)
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
