#!/usr/bin/env python3
"""Run paired oracle-claim judge smoke at L0 vs L1."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oracle_judge import OracleJudgeError, run_smoke_suite, summarize_for_stdout  # noqa: E402
from stage_s_tools import sha256_path, write_new_json  # noqa: E402


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
        raise OracleJudgeError(f"model request failed: {exc}") from exc
    if not isinstance(value, dict):
        raise OracleJudgeError("model response root must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases",
        type=Path,
        default=ROOT / "configs/oracle_judge_smoke_cases_v0.1.json",
    )
    parser.add_argument(
        "--pr-candidates-root",
        type=Path,
        default=ROOT / "data/private/pr-candidates",
    )
    parser.add_argument(
        "--system-prompt",
        type=Path,
        default=ROOT / "configs/oracle_judge_smoke_prompt_v0.3.txt",
    )
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--endpoint")
    parser.add_argument("--model", default="Qwen/Qwen3-Coder-30B-A3B-Instruct")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    requester = None
    if not args.dry_run:
        if not args.endpoint:
            print("ERROR: --endpoint is required unless --dry-run is set", file=sys.stderr)
            return 1
        _http_request.endpoint = args.endpoint  # type: ignore[attr-defined]
        requester = _http_request

    try:
        result = run_smoke_suite(
            args.cases,
            args.pr_candidates_root,
            args.system_prompt,
            args.model,
            args.temperature,
            args.max_tokens,
            args.timeout,
            case_ids=args.case_id,
            requester=requester,
            dry_run=args.dry_run,
        )
    except OracleJudgeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.output:
        receipt_path = args.output.with_name(args.output.stem + ".receipt.json")
        if args.output.exists() or receipt_path.exists():
            print(f"ERROR: Refusing to overwrite existing output or receipt: {args.output}", file=sys.stderr)
            return 1
        write_new_json(args.output, result)
        write_new_json(
            receipt_path,
            {
                "schema_version": "eviscope.oracle-judge-smoke-receipt.v0.1",
                "status": result["status"],
                "inputs": {
                    "cases_sha256": sha256_path(args.cases),
                    "system_prompt_sha256": sha256_path(args.system_prompt),
                },
                "outputs": {"oracle_judge_smoke_sha256": sha256_path(args.output)},
            },
        )

    summary = summarize_for_stdout(result)
    print(json.dumps(summary, indent=2))

    if args.dry_run:
        return 0
    if result["mechanism_signals"] < 1:
        return 2
    if result["expectation_matches"] != result["case_count"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
