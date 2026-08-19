#!/usr/bin/env python3
"""Run progressive L0-L3 escalation smoke on frozen oracle claims."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eviscope_verifier import (  # noqa: E402
    EviScopeVerifierError,
    escalate_case,
    judge_from_requester,
)
from oracle_judge import load_smoke_cases  # noqa: E402
from stage_s_tools import StageSToolingError, sha256_path, write_new_json  # noqa: E402


def _http_request(_model: str, payload: dict, timeout: float) -> dict:
    endpoint = _http_request.endpoint  # type: ignore[attr-defined]
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise EviScopeVerifierError(f"model request failed: {exc}") from exc
    if not isinstance(value, dict):
        raise EviScopeVerifierError("model response root must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=ROOT / "configs/oracle_judge_smoke_cases_v0.1.json")
    parser.add_argument("--pr-candidates-root", type=Path, default=ROOT / "data/private/pr-candidates")
    parser.add_argument("--system-prompt", type=Path, default=ROOT / "configs/oracle_judge_smoke_prompt_v0.3.txt")
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--endpoint")
    parser.add_argument("--model", default="qwen3-coder-30b-a3b")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        cases_doc = load_smoke_cases(args.cases)
        selected = cases_doc["cases"]
        if args.case_id:
            wanted = set(args.case_id)
            selected = [case for case in selected if case.get("case_id") in wanted]
        if args.dry_run:
            traces = []
            for case in selected:
                from eviscope_verifier import load_nested_packages

                base = args.pr_candidates_root / case["repository_id"]
                packages = load_nested_packages(
                    base / "review-snapshots" / case["review_head_sha"],
                    base / "l1-evidence-v0.1" / f"comment-{case['comment_id']}",
                    base / "l2-evidence-v0.1" / f"comment-{case['comment_id']}",
                    base / "l3-evidence-v0.1" / f"comment-{case['comment_id']}",
                )
                traces.append(
                    {
                        "case_id": case["case_id"],
                        "available_levels": list(packages),
                        "artifact_counts": {level: packages[level]["artifact_count"] for level in packages},
                        "dry_run": True,
                    }
                )
            result = {
                "schema_version": "eviscope.escalation-smoke.v0.1",
                "status": "engineering_smoke_not_gold",
                "dry_run": True,
                "records": traces,
            }
        else:
            if not args.endpoint:
                print("ERROR: --endpoint is required unless --dry-run is set", file=sys.stderr)
                return 1
            _http_request.endpoint = args.endpoint  # type: ignore[attr-defined]
            system_prompt = args.system_prompt.read_text(encoding="utf-8")
            traces = []
            for case in selected:
                per_case = judge_from_requester(
                    case["comment_text"],
                    case["oracle_claim"],
                    system_prompt,
                    args.model,
                    args.temperature,
                    args.max_tokens,
                    args.timeout,
                    _http_request,
                )
                traces.append(escalate_case(case, args.pr_candidates_root, per_case))
            result = {
                "schema_version": "eviscope.escalation-smoke.v0.1",
                "status": "engineering_smoke_not_gold",
                "dry_run": False,
                "model": args.model,
                "records": traces,
            }
    except (EviScopeVerifierError, StageSToolingError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.output:
        write_new_json(args.output, result)
        write_new_json(
            args.output.with_name(args.output.stem + ".receipt.json"),
            {
                "schema_version": "eviscope.escalation-smoke-receipt.v0.1",
                "status": result["status"],
                "inputs": {"cases_sha256": sha256_path(args.cases)},
                "outputs": {"escalation_smoke_sha256": sha256_path(args.output)},
            },
        )
    summary = [
        {
            "case_id": record.get("case_id"),
            "levels_called": record.get("levels_called") or record.get("available_levels"),
            "stopped_after": record.get("stopped_after"),
            "final_verdict": record.get("final_verdict"),
            "minimum_evidence_level": record.get("minimum_evidence_level"),
        }
        for record in result["records"]
    ]
    print(json.dumps({"dry_run": result["dry_run"], "records": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
