#!/usr/bin/env python3
"""Run an explicitly selected Stage-S engineering smoke; never emit annotations."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stage_s_tools import (
    StageSToolingError,
    align_verbatim_fragments,
    load_json,
    sha256_path,
    write_new_json,
)


SMOKE_STATUS = "engineering_smoke_not_annotation_not_gold"


def _align_output(comment: str, output: dict[str, Any]) -> dict[str, Any]:
    aligned = deepcopy(output)
    claims = aligned.get("claims")
    if not isinstance(claims, list):
        raise StageSToolingError("model output claims must be an array")
    for claim_index, claim in enumerate(claims):
        if not isinstance(claim, dict) or not isinstance(claim.get("source_fragments"), list):
            raise StageSToolingError(f"claim {claim_index} has malformed source_fragments")
        text_fragments = []
        for fragment_index, fragment in enumerate(claim["source_fragments"]):
            if isinstance(fragment, str):
                text_fragments.append({"text": fragment})
            elif isinstance(fragment, dict) and isinstance(fragment.get("text"), str):
                text_fragments.append({"text": fragment["text"]})
            else:
                raise StageSToolingError(
                    f"claim {claim_index} fragment {fragment_index} has no verbatim text"
                )
        claim["source_fragments"] = align_verbatim_fragments(comment, text_fragments)
    return aligned


def _http_request(endpoint: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
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
        raise StageSToolingError(f"model request failed: {exc}") from exc
    if not isinstance(value, dict):
        raise StageSToolingError("model response root must be an object")
    return value


def run_smoke(
    inputs_path: Path,
    protocol_path: Path,
    system_prompt_path: Path,
    sample_ids: list[str],
    endpoint: str,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
    requester: Callable[[str, dict[str, Any], float], dict[str, Any]] = _http_request,
) -> dict[str, Any]:
    inputs = load_json(inputs_path)
    protocol = load_json(protocol_path)
    try:
        system_prompt = system_prompt_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StageSToolingError(f"Cannot read system prompt: {exc}") from exc
    if not isinstance(inputs, dict) or inputs.get("evidence_visible") is not False:
        raise StageSToolingError("inputs must be a blinded Stage-S packet")
    if not isinstance(protocol, dict) or protocol.get("alignment_rule") is None:
        raise StageSToolingError("protocol must register an alignment rule")
    samples = inputs.get("samples")
    if not isinstance(samples, list):
        raise StageSToolingError("inputs samples must be an array")
    if not sample_ids or len(sample_ids) > 16 or len(set(sample_ids)) != len(sample_ids):
        raise StageSToolingError("select 1-16 unique sample IDs for an engineering smoke")
    by_id = {item.get("sample_id"): item for item in samples if isinstance(item, dict)}
    missing = [sample_id for sample_id in sample_ids if sample_id not in by_id]
    if missing:
        raise StageSToolingError(f"unknown sample IDs: {', '.join(missing)}")

    records = []
    for sample_id in sample_ids:
        comment = by_id[sample_id].get("comment_text")
        if not isinstance(comment, str):
            raise StageSToolingError(f"sample {sample_id} has no comment text")
        payload = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": comment},
            ],
        }
        record: dict[str, Any] = {
            "sample_id": sample_id,
            "request_succeeded": False,
            "json_parsed": False,
            "alignment_valid": False,
            "finish_reason": None,
            "raw_output": None,
            "aligned_output": None,
            "issues": [],
            "usage": None,
        }
        try:
            response = requester(endpoint, payload, timeout)
            record["request_succeeded"] = True
            choices = response.get("choices")
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                raise StageSToolingError("response has no first choice")
            choice = choices[0]
            message = choice.get("message")
            raw = message.get("content") if isinstance(message, dict) else None
            if not isinstance(raw, str):
                raise StageSToolingError("response choice has no string content")
            record["finish_reason"] = choice.get("finish_reason")
            record["raw_output"] = raw
            record["usage"] = response.get("usage")
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise StageSToolingError("parsed model output must be an object")
            record["json_parsed"] = True
            record["aligned_output"] = _align_output(comment, parsed)
            record["alignment_valid"] = True
        except (StageSToolingError, json.JSONDecodeError) as exc:
            record["issues"].append(str(exc))
        records.append(record)

    return {
        "schema_version": "eviscope.stage-s-model-smoke.v0.1",
        "status": SMOKE_STATUS,
        "selection_id": inputs.get("selection_id"),
        "input_sha256": sha256_path(inputs_path),
        "protocol_sha256": sha256_path(protocol_path),
        "system_prompt_sha256": sha256_path(system_prompt_path),
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--system-prompt", required=True, type=Path)
    parser.add_argument("--sample-id", action="append", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=3000)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    receipt_path = args.output.with_name(args.output.stem + ".receipt.json")
    if args.output.exists() or receipt_path.exists():
        print(f"ERROR: Refusing to overwrite existing output or receipt for: {args.output}", file=sys.stderr)
        return 1
    try:
        result = run_smoke(
            args.inputs,
            args.protocol,
            args.system_prompt,
            args.sample_id,
            args.endpoint,
            args.model,
            args.temperature,
            args.max_tokens,
            args.timeout,
        )
        write_new_json(args.output, result)
        receipt_path = args.output.with_name(args.output.stem + ".receipt.json")
        write_new_json(receipt_path, {
            "schema_version": "eviscope.model-smoke-receipt.v0.1",
            "status": SMOKE_STATUS,
            "inputs": {
                "stage_s_inputs_sha256": sha256_path(args.inputs),
                "protocol_sha256": sha256_path(args.protocol),
                "system_prompt_sha256": sha256_path(args.system_prompt),
            },
            "outputs": {"model_smoke_sha256": sha256_path(args.output)},
        })
    except StageSToolingError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    valid = sum(record["alignment_valid"] is True for record in result["records"])
    print(json.dumps({"records": len(result["records"]), "alignment_valid": valid, "output_sha256": sha256_path(args.output)}, indent=2))
    return 0 if valid == len(result["records"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
