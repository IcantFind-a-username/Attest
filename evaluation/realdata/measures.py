"""Measurements run against the real corpus. Each returns plain dicts."""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from realdata.corpus import Case, _git

from attest.review.budget import Budget, BudgetExceeded
from attest.review.channels import tier0_lr, verification_lr, votes_lr
from attest.review.config import ReviewConfig
from attest.review.diffs import parse_diff
from attest.review.proposer import MAX_OUTPUT_TOKENS, SYSTEM_PROMPT, build_prompt
from attest.review.tier0 import ANCHOR_SLACK, collect_signals, signals_near

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass
class HunkBody:
    path: str
    start: int
    lines: list[str]  # new-side content of the hunk, in order

    @property
    def end(self) -> int:
        return self.start + len(self.lines) - 1


def hunk_bodies(diff_text: str) -> list[HunkBody]:
    """New-side content of every hunk, walked independently of attest's parser."""
    out: list[HunkBody] = []
    path: str | None = None
    cur: HunkBody | None = None
    in_header = False
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            in_header, path, cur = True, None, None
            continue
        if in_header and line.startswith("+++ b/"):
            path = line[6:].strip()
            continue
        m = _HUNK_RE.match(line)
        if m and path is not None:
            in_header = False
            cur = HunkBody(path=path, start=int(m.group(1)), lines=[])
            if (int(m.group(2)) if m.group(2) is not None else 1) > 0:
                out.append(cur)
            continue
        if cur is None:
            continue
        if line.startswith("+") or line.startswith(" "):
            cur.lines.append(line[1:])
        elif line == "":
            cur.lines.append("")


    return out


def measure_hunk_fidelity(repo: Path, case: Case) -> dict:
    """Does attest's hunk map describe the real file on the diff's new side?"""
    info = parse_diff(case.diff_text)
    bodies = hunk_bodies(case.diff_text)
    try:
        blob = _git(repo, "show", f"{case.new_rev}:{case.path}").split("\n")
    except (RuntimeError, subprocess.TimeoutExpired):
        return {"checked": 0, "skipped": 1}
    res = {
        "checked": 0,
        "range_mismatch": 0,
        "content_mismatch": 0,
        "past_eof": 0,
        "files_dropped": 0,
    }
    parsed = {(f, r) for f, ranges in info.hunks.items() for r in ranges}
    if case.path not in info.hunks and bodies:
        res["files_dropped"] = 1
    for body in bodies:
        res["checked"] += 1
        if (body.path, (body.start, body.end)) not in parsed:
            res["range_mismatch"] += 1
        if body.end > len(blob):
            res["past_eof"] += 1
            continue
        actual = blob[body.start - 1 : body.end]
        if actual != body.lines:
            res["content_mismatch"] += 1
    return res


def measure_anchor_admissibility(case: Case) -> dict:
    """What a model has to emit for the anchor validator to accept a real bug line."""
    info = parse_diff(case.diff_text)
    p = case.path
    variants = {
        "exact_path": p,
        "basename_only": p.rsplit("/", 1)[-1],
        "b_prefixed": "b/" + p,
        "a_prefixed": "a/" + p,
        "backslashes": p.replace("/", "\\"),
        "dot_slash": "./" + p,
    }
    out: dict[str, object] = {"has_true_line": bool(case.true_lines)}
    if not case.true_lines:
        return out
    line = case.true_lines[0]
    for name, variant in variants.items():
        out[name] = info.anchor_in_hunk(variant, line)
    out["off_by_one_lo"] = info.anchor_in_hunk(p, line - 1)
    out["off_by_one_hi"] = info.anchor_in_hunk(p, line + 1)
    out["all_true_lines_in_hunk"] = all(info.anchor_in_hunk(p, ln) for ln in case.true_lines)
    return out


def _materialize(repo: Path, case: Case, workdir: Path) -> Path | None:
    """Write the diff's new-side blob into a throwaway tree that keeps the
    repository's own lint configuration, so ruff behaves as it would in CI."""
    try:
        content = _git(repo, "show", f"{case.new_rev}:{case.path}")
    except (RuntimeError, subprocess.TimeoutExpired):
        return None
    target = workdir / case.path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    for cfg in ("pyproject.toml", "ruff.toml", ".ruff.toml", "setup.cfg", "tox.ini"):
        src = repo / cfg
        if src.is_file():
            shutil.copy2(src, workdir / cfg)
    return workdir


def measure_tier0(repo: Path, case: Case, workdir: Path) -> dict:
    """T-channel evidence rate at real bug lines vs. at other in-hunk lines."""
    if _materialize(repo, case, workdir) is None:
        return {"skipped": 1}
    t0 = time.monotonic()
    signals = collect_signals(workdir, [case.path], ["ruff"])
    elapsed = time.monotonic() - t0
    # collect_signals swallows a ruff that refused to start (bad/partial config);
    # probe separately so "no signals" is never confused with "tool did not run"
    probe = subprocess.run(
        [shutil.which("ruff") or "ruff", "check", "--output-format", "json",
         "--exit-zero", case.path],
        capture_output=True, text=True, cwd=workdir, encoding="utf-8", errors="replace",
    )

    info = parse_diff(case.diff_text)
    in_hunk = [ln for a, b in info.hunks.get(case.path, []) for ln in range(a, b + 1)]
    true_set = set(case.true_lines)
    background = [
        ln for ln in in_hunk if all(abs(ln - t) > ANCHOR_SLACK for t in true_set)
    ]
    return {
        "ruff_ran": probe.returncode == 0,
        "ruff_error": probe.stderr.strip()[:200] if probe.returncode != 0 else "",
        "signals_total": len(signals),
        "tier0_seconds": elapsed,
        "true_lines": len(true_set),
        "true_lines_with_signal": sum(
            1 for ln in true_set if signals_near(signals, case.path, ln)
        ),
        "background_lines": len(background),
        "background_lines_with_signal": sum(
            1 for ln in background if signals_near(signals, case.path, ln)
        ),
        "any_in_hunk_signal": sum(
            1 for ln in in_hunk if signals_near(signals, case.path, ln)
        )
        > 0,
    }


def measure_budget(diff_text: str, k: int = 5, budget_usd: float = 0.25) -> dict:
    """Would the preflight let this review make its K calls, or DEFER?"""
    config = ReviewConfig(k_samples=k, budget_usd=budget_usd)
    budget = Budget(limit_usd=config.budget_usd, model=config.model)
    prompt = build_prompt(parse_diff(diff_text))
    chars = len(SYSTEM_PROMPT) + len(prompt)
    per_call = budget.estimate_cost(chars, MAX_OUTPUT_TOKENS)
    deferred_at = None
    for i in range(k):
        try:
            budget.reserve(f"sample-{i}", chars, MAX_OUTPUT_TOKENS)
        except BudgetExceeded:
            deferred_at = i
            break
    return {
        "diff_chars": len(diff_text),
        "prompt_chars": chars,
        "est_cost_per_call": per_call,
        "est_cost_k": per_call * k,
        "deferred": deferred_at is not None,
        "deferred_at_call": deferred_at,
    }


def wealth_table(alpha: float = 0.1) -> list[dict]:
    """Reachable pre-verification wealth per vote count, with and without T."""
    rows = []
    for votes in range(1, 6):
        s = votes_lr(votes)
        for t_signals, t_lr in ((0, 1.0), (1, 2.0), (2, 3.0)):
            rows.append(
                {
                    "votes": votes,
                    "t_signals": t_signals,
                    "wealth": s * t_lr,
                    "surfaces": s * t_lr >= 1.0 / alpha,
                }
            )
    return rows


def reachable_decisions(alpha: float = 0.1) -> dict:
    """Exhaustive enumeration of every wealth the factory tables can produce.

    The gate has three arms (surface / drawer / discard). Red line 4 asks that a
    threshold be shown achievable before adoption; this asks the same question
    of BOTH thresholds at once, over the full cross product of channel states
    the pipeline can actually reach.
    """
    from attest.core.betting import decide

    rows = []
    for votes in range(1, 6):
        for t_signals in (0, 1, 2):
            for v_state in (None, False, True):
                w = votes_lr(votes)
                # gate.py buys T only while the wager is still undecided
                if decide(w, alpha) is None and t_signals:
                    w *= tier0_lr(t_signals)
                if decide(w, alpha) is None and v_state is not None:
                    w *= verification_lr(v_state)
                rows.append(
                    {
                        "votes": votes,
                        "t_signals": t_signals,
                        "verification": v_state,
                        "wealth": round(w, 3),
                        "decision": {1: "surface", 0: "discard", None: "drawer"}[
                            decide(w, alpha)
                        ],
                    }
                )
    seen = {r["decision"] for r in rows}
    wealths = [r["wealth"] for r in rows]
    return {
        "states_enumerated": len(rows),
        "decisions_reachable": sorted(seen),
        "discard_reachable": "discard" in seen,
        "min_wealth": min(wealths),
        "max_wealth": max(wealths),
        "discard_threshold": alpha,
        "surface_threshold": 1.0 / alpha,
        "surface_without_verification": sum(
            1 for r in rows if r["verification"] is None and r["decision"] == "surface"
        ),
        "rows": rows,
    }


def classify_unparsed_files(repo: Path, sha: str, parsed: set[str]) -> dict[str, int]:
    """Why a file git names in a commit carries no hunk in attest's map.

    A file with no new-side line has nothing an anchor could point at, so its
    absence is correct behaviour rather than lost coverage — but only if that
    is in fact why it is missing. This names the reason from git's own status
    and numstat rather than guessing from the diff text.
    """
    out: dict[str, int] = {}
    status: dict[str, str] = {}
    for line in _git(repo, "diff", "--raw", f"{sha}^", sha).splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            status[parts[-1]] = parts[0].split()[-1]
    binary = set()
    for line in _git(repo, "diff", "--numstat", f"{sha}^", sha).splitlines():
        cols = line.split("\t")
        if len(cols) == 3 and cols[0] == "-" and cols[1] == "-":
            binary.add(cols[2])
    for path, st in status.items():
        if path in parsed:
            continue
        if path in binary:
            kind = "binary"
        elif st.startswith("D"):
            kind = "deleted"
        elif st.startswith("R"):
            kind = "pure_rename"
        elif st.startswith("A"):
            kind = "empty_file_added"
        elif st.startswith("T"):
            kind = "type_change"
        else:
            kind = f"other_{st}"
        out[kind] = out.get(kind, 0) + 1
    return out
