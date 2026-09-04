"""D-133 (a): the wording adjudicator, met by a real model for the first time.

D-130 shipped `attest.review.structural.describe` with the rule the green level
rests on -- *the LLM thinks; an algorithm decides whether it may speak* -- and
proved the adjudicator only against a stub that hedged on purpose. A denylist
that has never met a model is not evidence about a model.

This takes ten findings the offline measurement already produced, asks the real
default model to say each one in plain language and propose a fix, and records
per finding whether the adjudicator stopped coordinate-free wording. The model is
told nothing about the rule: the point is what it does unprompted.

    ANTHROPIC_API_KEY=... .venv/bin/python scripts/corpus/structural_wording_check.py \\
        --json report.json --limit 10

Two failure modes are counted separately, because they are different bugs:

  admitted  the prose names no coordinate and the adjudicator let it through
  refused   the prose names a coordinate and reads well, and it was dropped anyway
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.review.proposer import ApiProvider  # noqa: E402
from attest.review.structural import (  # noqa: E402
    STRUCTURAL_POLICY_VERSION,
    WORDING_MAX_TOKENS,
    WORDING_SCHEMA,
    WORDING_SYSTEM,
    DuplicateImplementation,
    describe,
    evidence_sentence,
    inadmissible_phrase,
)

OFFLINE = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-04-structural-offline.json"
PRICING = ROOT / "src" / "attest" / "data" / "pricing.toml"



def _pricing() -> tuple[dict[str, dict[str, float]], str]:
    data = tomllib.loads(PRICING.read_text(encoding="utf-8"))
    models = {
        name: {"in": float(m["input_per_mtok"]) / 1e6, "out": float(m["output_per_mtok"]) / 1e6}
        for name, m in data["models"].items()
    }
    return models, str(data["default_model"])


def findings(limit: int) -> list[DuplicateImplementation]:
    """The first `limit` distinct pairs of the offline measurement, in the order
    that file records them, so the sample is fixed rather than chosen."""
    payload = json.loads(OFFLINE.read_text(encoding="utf-8"))
    seen: set[tuple[str, int, str, int]] = set()
    picked: list[DuplicateImplementation] = []
    for row in payload["rows"]:
        for raw in row.get("findings", []):
            key = (raw["path_a"], raw["line_a"], raw["path_b"], raw["line_b"])
            if key in seen:
                continue
            seen.add(key)
            picked.append(
                DuplicateImplementation(
                    policy_version=str(raw["policy_version"]),
                    category=str(raw["category"]),
                    path_a=raw["path_a"],
                    name_a=raw["name_a"],
                    line_a=int(raw["line_a"]),
                    end_line_a=int(raw["end_line_a"]),
                    path_b=raw["path_b"],
                    name_b=raw["name_b"],
                    line_b=int(raw["line_b"]),
                    end_line_b=int(raw["end_line_b"]),
                    similarity=float(raw["similarity"]),
                    tokens_a=int(raw["tokens_a"]),
                    tokens_b=int(raw["tokens_b"]),
                    changed_side=str(raw["changed_side"]),
                )
            )
            if len(picked) >= limit:
                return picked
    return picked


def names_a_coordinate(text: str, finding: DuplicateImplementation) -> bool:
    """Does the prose name a place a reader could open? A path, or one of the two
    function names. This is the *measurement's* definition of "has a coordinate";
    the adjudicator's own rule is `inadmissible_phrase`, and the point of the run
    is whether the two agree."""
    return any(
        token in text
        for token in (
            finding.path_a,
            finding.path_b,
            Path(finding.path_a).name,
            Path(finding.path_b).name,
            finding.name_a,
            finding.name_b,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--model", default="")
    parser.add_argument("--max-usd", type=float, default=0.20)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)

    prices, default_model = _pricing()
    model = args.model or default_model
    provider = ApiProvider(model=model)
    price = prices[model]

    rows: list[dict] = []
    spend = 0.0
    for finding in findings(args.limit):
        usage: dict[str, int] = {}

        def say(evidence: str, _usage: dict[str, int] = usage) -> str:
            result = provider.sample(
                system=WORDING_SYSTEM,
                prompt=f"The finding, as the analysis states it:\n\n{evidence}",
                schema=WORDING_SCHEMA,  # type: ignore[arg-type]
                max_tokens=WORDING_MAX_TOKENS,
            )
            _usage["in"] = result.input_tokens
            _usage["out"] = result.output_tokens
            payload = json.loads(result.text or "{}")
            return f"{payload.get('sentence', '')}\n\n{payload.get('fix', '')}".strip()

        if spend >= args.max_usd:
            break
        published, refusal = describe(finding, say=say)
        spend += usage.get("in", 0) * price["in"] + usage.get("out", 0) * price["out"]
        # the model's own prose, recovered from what describe published or dropped
        evidence = evidence_sentence(finding)
        prose = published[len(evidence) :].strip() if refusal is None else ""
        rows.append(
            {
                "path_a": finding.path_a,
                "line_a": finding.line_a,
                "path_b": finding.path_b,
                "line_b": finding.line_b,
                "similarity": finding.similarity,
                "model_prose": prose,
                "refusal": refusal,
                "banned_phrase": inadmissible_phrase(prose) if prose else None,
                "prose_names_a_coordinate": names_a_coordinate(prose, finding) if prose else None,
                "published_is_evidence_only": refusal is not None,
                "input_tokens": usage.get("in", 0),
                "output_tokens": usage.get("out", 0),
            }
        )

    admitted = [r for r in rows if r["refusal"] is None and not r["prose_names_a_coordinate"]]
    payload = {
        "schema_version": "attest.structural-wording-check.v1",
        "policy_version": STRUCTURAL_POLICY_VERSION,
        "model": model,
        "findings_asked": len(rows),
        "model_sentence_published": sum(1 for r in rows if r["refusal"] is None),
        "model_sentence_dropped": sum(1 for r in rows if r["refusal"] is not None),
        "dropped_reasons": sorted({str(r["refusal"]) for r in rows if r["refusal"]}),
        "prose_naming_a_coordinate": sum(1 for r in rows if r["prose_names_a_coordinate"]),
        "coordinate_free_prose_admitted": len(admitted),
        "spend_usd": round(spend, 6),
        "rows": rows,
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + "\n", encoding="utf-8")
    print(
        f"model {model}: asked {payload['findings_asked']}, "
        f"published {payload['model_sentence_published']}, "
        f"dropped {payload['model_sentence_dropped']}; "
        f"prose naming a coordinate {payload['prose_naming_a_coordinate']}; "
        f"COORDINATE-FREE PROSE ADMITTED {payload['coordinate_free_prose_admitted']}; "
        f"${payload['spend_usd']:.6f}"
    )
    for reason in payload["dropped_reasons"]:
        print(f"  dropped: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
