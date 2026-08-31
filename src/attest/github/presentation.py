"""GitHub-safe renderers for verified review results."""

from __future__ import annotations

from attest.review.gate import GateResult

FINDING_ID_MARKER_PREFIX = "<!-- attest:finding-id:"


def render_running(candidate_count: int | None = None) -> str:
    """Render a status update without identifying any unverified candidate."""
    if candidate_count is None:
        return "Review running; candidates are under verification."
    return f"Review running; {candidate_count} candidates are under verification."


def render_deferred(reason: str) -> str:
    """Render the supplied deferral reason without review details."""
    return reason


def render_complete(results: list[GateResult], spend_usd: float, elapsed_s: float) -> str:
    """Render only results that have passed the wealth gate."""
    surfaced = _sorted_surfaced(results)
    lines = ["Review complete."]
    if surfaced:
        lines.append("Verified findings:")
        lines.extend(_summary_line(result) for result in surfaced)
    else:
        lines.append("No findings cleared the evidence bar.")
    lines.append(f"Spend ${spend_usd:.4f}; {elapsed_s:.1f}s.")
    return "\n".join(lines)


def inline_comments(results: list[GateResult]) -> list[dict[str, object]]:
    """Build the top-three, wealth-sorted GitHub review comments."""
    surfaced = _sorted_surfaced(results)
    if len(surfaced) != len(results):
        raise ValueError("inline comments require surfaced results")
    return [_inline_comment(result) for result in surfaced[:3]]


def _sorted_surfaced(results: list[GateResult]) -> list[GateResult]:
    return sorted(
        (result for result in results if result.decision == 1),
        key=lambda result: result.wealth,
        reverse=True,
    )


def _summary_line(result: GateResult) -> str:
    finding = result.finding
    return (
        f"- {_finding_id_marker(finding.finding_id)} Finding ID: {finding.finding_id}; "
        f"{finding.file}:{finding.line} — "
        f"{_one_line(finding.claim)} (wealth {result.wealth:.1f})"
    )


def _inline_comment(result: GateResult) -> dict[str, object]:
    finding = result.finding
    evidence = "; ".join(
        f"{purchase.channel} x{purchase.lr:.2f} ({purchase.detail})"
        for purchase in result.purchases
    )
    body = "\n".join(
        [
            _finding_id_marker(finding.finding_id),
            finding.claim,
            f"Finding ID: {finding.finding_id}",
            f"Failure scenario: {finding.failure_scenario}",
            f"Falsification plan: {finding.falsification_plan}",
            f"Wealth: wealth {result.wealth:.1f}",
            f"Evidence purchases: {evidence}",
        ]
    )
    return {"path": finding.file, "line": finding.line, "side": "RIGHT", "body": body}


def _finding_id_marker(finding_id: str) -> str:
    return f"{FINDING_ID_MARKER_PREFIX}{finding_id} -->"


def _one_line(value: str) -> str:
    return " ".join(value.splitlines())
