"""Oracle-claim progressive judge for engineering smoke and paired baselines.

Oracle claims are hand-segmented propositions supplied out-of-band. Evidence
packages are frozen review-time artifacts; this module never retrieves or
mutates repository state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from eviscope_validation import LEVELS, VERDICTS


class OracleJudgeError(RuntimeError):
    """Raised when oracle-judge inputs or outputs violate frozen rules."""


SMOKE_STATUS = "engineering_smoke_not_annotation_not_gold"
_L0_DIFF_ID = "L0:review-time-diff"


def _read_text(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise OracleJudgeError(f"Cannot read artifact {path}: {exc}") from exc
    if b"\x00" in raw:
        raise OracleJudgeError(f"Binary artifact cannot be embedded as text: {path}")
    return raw.decode("utf-8")


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OracleJudgeError(f"Cannot read JSON {path}: {exc}") from exc


def load_l0_diff(snapshot_dir: Path) -> tuple[bytes, str]:
    diff_path = snapshot_dir / "L0.diff"
    metadata_path = snapshot_dir / "metadata.json"
    if not diff_path.is_file() or not metadata_path.is_file():
        raise OracleJudgeError(f"Snapshot directory missing L0.diff or metadata.json: {snapshot_dir}")
    diff = diff_path.read_bytes()
    metadata = _load_json(metadata_path)
    expected = metadata.get("l0_sha256")
    if not isinstance(expected, str):
        raise OracleJudgeError("Snapshot metadata must include l0_sha256")
    import hashlib

    actual = hashlib.sha256(diff).hexdigest()
    if actual != expected:
        raise OracleJudgeError("L0.diff hash does not match snapshot metadata")
    return diff, expected


def _artifact_record(
    artifact_id: str,
    level: str,
    kind: str,
    path: str,
    source_locator: str,
    content: str,
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "level": level,
        "kind": kind,
        "path": path,
        "source_locator": source_locator,
        "content": content,
        "byte_length": len(content.encode("utf-8")),
    }


def assemble_evidence(
    snapshot_dir: Path,
    l1_package_dir: Path | None,
    max_level: str,
    l2_package_dir: Path | None = None,
    l3_package_dir: Path | None = None,
) -> dict[str, Any]:
    if max_level not in {"L0", "L1", "L2", "L3"}:
        raise OracleJudgeError("evidence assembly supports max_level L0, L1, L2, or L3")
    diff_bytes, l0_sha256 = load_l0_diff(snapshot_dir)
    try:
        diff_text = diff_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OracleJudgeError("L0.diff must decode as UTF-8 for judge smoke") from exc

    artifacts: list[dict[str, Any]] = [
        _artifact_record(
            _L0_DIFF_ID,
            "L0",
            "diff",
            "",
            f"snapshot:{snapshot_dir.name}:L0.diff",
            diff_text,
        )
    ]

    manifest: dict[str, Any] | None = None
    if max_level in {"L1", "L2", "L3"}:
        if l1_package_dir is None:
            raise OracleJudgeError("L1 evaluation requires an L1 evidence package directory")
        manifest_path = l1_package_dir / "manifest.json"
        if not manifest_path.is_file():
            raise OracleJudgeError(f"L1 package missing manifest.json: {l1_package_dir}")
        manifest = _load_json(manifest_path)
        if manifest.get("status") not in {
            "engineering_smoke_not_gold",
            "review_time_l1_not_gold",
            "synthetic_smoke_not_gold",
        }:
            raise OracleJudgeError("L1 manifest status is not an allowed engineering smoke status")
        for record in manifest.get("artifacts", []):
            if not isinstance(record, dict) or record.get("available") is not True:
                continue
            rel = record.get("relative_path")
            kind = record.get("kind")
            artifact_id = record.get("artifact_id")
            path = record.get("path")
            source_locator = record.get("source_locator")
            if not all(isinstance(item, str) and item for item in (rel, kind, artifact_id, source_locator)):
                raise OracleJudgeError("Available L1 artifact record is malformed")
            if kind == "enclosing_symbol":
                payload = _load_json(l1_package_dir / rel)
                text = payload.get("text")
                if not isinstance(text, str):
                    raise OracleJudgeError(f"Enclosing symbol artifact missing text: {rel}")
                content = text
            else:
                content = _read_text(l1_package_dir / rel)
            artifacts.append(
                _artifact_record(
                    artifact_id,
                    "L1",
                    kind,
                    path if isinstance(path, str) else "",
                    source_locator,
                    content,
                )
            )

    l2_manifest: dict[str, Any] | None = None
    if max_level in {"L2", "L3"}:
        if l2_package_dir is None:
            raise OracleJudgeError("L2 evaluation requires an L2 evidence package directory")
        l2_manifest_path = l2_package_dir / "manifest.json"
        if not l2_manifest_path.is_file():
            raise OracleJudgeError(f"L2 package missing manifest.json: {l2_package_dir}")
        l2_manifest = _load_json(l2_manifest_path)
        if l2_manifest.get("status") not in {
            "engineering_smoke_not_gold",
            "review_time_l2_not_gold",
            "synthetic_smoke_not_gold",
        }:
            raise OracleJudgeError("L2 manifest status is not an allowed engineering smoke status")
        for record in l2_manifest.get("artifacts", []):
            if not isinstance(record, dict) or record.get("available") is not True:
                continue
            rel = record.get("relative_path")
            kind = record.get("kind")
            artifact_id = record.get("artifact_id")
            path = record.get("path")
            source_locator = record.get("source_locator")
            if not all(isinstance(item, str) and item for item in (rel, kind, artifact_id, source_locator)):
                raise OracleJudgeError("Available L2 artifact record is malformed")
            if str(rel).endswith(".json"):
                payload = _load_json(l2_package_dir / rel)
                content = json.dumps(payload, ensure_ascii=False, indent=2)
            else:
                content = _read_text(l2_package_dir / rel)
            artifacts.append(
                _artifact_record(
                    artifact_id,
                    "L2",
                    kind if isinstance(kind, str) else "",
                    path if isinstance(path, str) else "",
                    source_locator,
                    content,
                )
            )

    l3_manifest: dict[str, Any] | None = None
    if max_level == "L3":
        if l3_package_dir is None:
            raise OracleJudgeError("L3 evaluation requires an L3 evidence package directory")
        l3_manifest_path = l3_package_dir / "manifest.json"
        if not l3_manifest_path.is_file():
            raise OracleJudgeError(f"L3 package missing manifest.json: {l3_package_dir}")
        l3_manifest = _load_json(l3_manifest_path)
        if l3_manifest.get("status") not in {
            "engineering_smoke_not_gold",
            "review_time_l3_not_gold",
            "synthetic_smoke_not_gold",
        }:
            raise OracleJudgeError("L3 manifest status is not an allowed engineering smoke status")
        for record in l3_manifest.get("artifacts", []):
            if not isinstance(record, dict) or record.get("available") is not True:
                continue
            rel = record.get("relative_path")
            kind = record.get("kind")
            artifact_id = record.get("artifact_id")
            path = record.get("path")
            source_locator = record.get("source_locator")
            if not all(isinstance(item, str) and item for item in (rel, kind, artifact_id, source_locator)):
                raise OracleJudgeError("Available L3 artifact record is malformed")
            if str(rel).endswith(".json"):
                payload = _load_json(l3_package_dir / rel)
                content = json.dumps(payload, ensure_ascii=False, indent=2)
            else:
                content = _read_text(l3_package_dir / rel)
            artifacts.append(
                _artifact_record(
                    artifact_id,
                    "L3",
                    kind if isinstance(kind, str) else "",
                    path if isinstance(path, str) else "",
                    source_locator,
                    content,
                )
            )

    return {
        "max_level": max_level,
        "l0_sha256": l0_sha256,
        "artifact_count": len(artifacts),
        "total_bytes": sum(item["byte_length"] for item in artifacts),
        "artifacts": artifacts,
        "l1_manifest_status": manifest.get("status") if manifest else None,
        "l2_manifest_status": l2_manifest.get("status") if l2_manifest else None,
        "l3_manifest_status": l3_manifest.get("status") if l3_manifest else None,
    }


def format_judge_user_message(
    comment_text: str,
    claim: dict[str, Any],
    evidence: dict[str, Any],
) -> str:
    claim_id = claim.get("claim_id")
    normalized = claim.get("normalized_text")
    if not isinstance(claim_id, str) or not claim_id:
        raise OracleJudgeError("oracle claim requires claim_id")
    if not isinstance(normalized, str) or not normalized:
        raise OracleJudgeError("oracle claim requires normalized_text")
    blocks = [
        "Review comment:",
        comment_text,
        "",
        f"Claim ({claim_id}):",
        normalized,
        "",
        f"Evidence package (max level {evidence['max_level']}):",
    ]
    if "hookspec.py" in normalized:
        blocks[6:6] = [
            "Reminder: this claim is only about hookspec.py. If that file is not "
            "in the package, return INSUFFICIENT. If hookspec.py contains the "
            "claimed annotation, return SUPPORTED. Do not CONTRADICT it because "
            "assertion/__init__.py uses Iterator[str] or another implementation type.",
            "",
        ]
    for artifact in evidence["artifacts"]:
        blocks.extend(
            [
                f"--- artifact_id={artifact['artifact_id']} level={artifact['level']} kind={artifact['kind']} ---",
                artifact["content"],
                "",
            ]
        )
    blocks.append(
        "Return one JSON object with keys verdict, evidence_ids, rationale, confidence."
    )
    return "\n".join(blocks)


def build_chat_payload(
    system_prompt: str,
    user_message: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    return {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    }


def parse_judge_response(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OracleJudgeError(f"judge output is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise OracleJudgeError("judge output root must be an object")
    verdict = parsed.get("verdict")
    evidence_ids = parsed.get("evidence_ids")
    rationale = parsed.get("rationale")
    confidence = parsed.get("confidence")
    if verdict not in VERDICTS:
        raise OracleJudgeError("judge output verdict must be SUPPORTED, CONTRADICTED, or INSUFFICIENT")
    if not isinstance(evidence_ids, list) or any(not isinstance(item, str) for item in evidence_ids):
        raise OracleJudgeError("judge output evidence_ids must be a string array")
    if not isinstance(rationale, str) or not rationale.strip():
        raise OracleJudgeError("judge output rationale must be a non-empty string")
    if confidence not in {"high", "medium", "low"}:
        raise OracleJudgeError("judge output confidence must be high, medium, or low")
    if verdict in {"SUPPORTED", "CONTRADICTED"} and not evidence_ids:
        raise OracleJudgeError("decisive verdict requires at least one evidence_id")
    return {
        "verdict": verdict,
        "evidence_ids": evidence_ids,
        "rationale": rationale,
        "confidence": confidence,
    }


def evaluate_case(
    case: dict[str, Any],
    pr_candidates_root: Path,
    system_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
    requester: Callable[[str, dict[str, Any], float], dict[str, Any]] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    case_id = case.get("case_id")
    repository_id = case.get("repository_id")
    review_head_sha = case.get("review_head_sha")
    comment_id = case.get("comment_id")
    comment_text = case.get("comment_text")
    oracle_claim = case.get("oracle_claim")
    expectation = case.get("smoke_expectation")
    if not all(isinstance(item, str) and item for item in (case_id, repository_id, review_head_sha, comment_text)):
        raise OracleJudgeError("case requires case_id, repository_id, review_head_sha, comment_text")
    if not isinstance(comment_id, int):
        raise OracleJudgeError(f"case {case_id} requires integer comment_id")
    if not isinstance(oracle_claim, dict):
        raise OracleJudgeError(f"case {case_id} requires oracle_claim")
    if not isinstance(expectation, dict):
        raise OracleJudgeError(f"case {case_id} requires smoke_expectation")

    base = pr_candidates_root / repository_id
    snapshot_dir = base / "review-snapshots" / review_head_sha
    l1_dir = base / "l1-evidence-v0.1" / f"comment-{comment_id}"
    l2_dir = base / "l2-evidence-v0.1" / f"comment-{comment_id}"

    evaluations: dict[str, Any] = {}
    levels = tuple(level for level in ("L0", "L1", "L2") if level in expectation)
    for level in levels:
        expected = expectation.get(level)
        if expected not in VERDICTS:
            raise OracleJudgeError(f"case {case_id} smoke_expectation.{level} must be a registered verdict")
        evidence = assemble_evidence(
            snapshot_dir,
            l1_dir if level in {"L1", "L2"} else None,
            level,
            l2_dir if level == "L2" else None,
        )
        user_message = format_judge_user_message(comment_text, oracle_claim, evidence)
        record: dict[str, Any] = {
            "max_level": level,
            "expected_verdict": expected,
            "artifact_count": evidence["artifact_count"],
            "total_bytes": evidence["total_bytes"],
            "request_succeeded": False,
            "parsed": False,
            "matches_expectation": False,
            "verdict": None,
            "raw_output": None,
            "parsed_output": None,
            "issues": [],
        }
        if dry_run or requester is None:
            record["dry_run"] = True
            evaluations[level] = record
            continue
        payload = build_chat_payload(system_prompt, user_message, model, temperature, max_tokens)
        try:
            response = requester(model, payload, timeout)
            record["request_succeeded"] = True
            choices = response.get("choices")
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                raise OracleJudgeError("model response has no first choice")
            message = choices[0].get("message")
            raw = message.get("content") if isinstance(message, dict) else None
            if not isinstance(raw, str):
                raise OracleJudgeError("model response choice has no string content")
            record["raw_output"] = raw
            parsed = parse_judge_response(raw)
            record["parsed"] = True
            record["parsed_output"] = parsed
            record["verdict"] = parsed["verdict"]
            record["matches_expectation"] = parsed["verdict"] == expected
            record["usage"] = response.get("usage")
        except OracleJudgeError as exc:
            record["issues"].append(str(exc))
        evaluations[level] = record

    l0 = evaluations.get("L0", {})
    l1 = evaluations.get("L1", {})
    mechanism_signal = (
        not dry_run
        and l0.get("parsed")
        and l1.get("parsed")
        and l0.get("verdict") == "INSUFFICIENT"
        and l1.get("verdict") == "SUPPORTED"
    )
    return {
        "case_id": case_id,
        "sample_id": case.get("sample_id"),
        "comment_id": comment_id,
        "evaluations": evaluations,
        "l1_richer_than_l0": (
            l1.get("total_bytes", 0) > l0.get("total_bytes", 0) if l0 and l1 else False
        ),
        "mechanism_signal": mechanism_signal,
        "both_match_expectation": (
            (dry_run or requester is None)
            or all(evaluations[level].get("matches_expectation") for level in levels)
        ),
    }


def load_smoke_cases(path: Path) -> dict[str, Any]:
    data = _load_json(path)
    if data.get("schema_version") != "eviscope.oracle-judge-smoke-cases.v0.1":
        raise OracleJudgeError("cases file must identify eviscope.oracle-judge-smoke-cases.v0.1")
    if data.get("status") != SMOKE_STATUS:
        raise OracleJudgeError("cases file status must be engineering_smoke_not_annotation_not_gold")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise OracleJudgeError("cases file must contain a non-empty cases array")
    return data


def run_smoke_suite(
    cases_path: Path,
    pr_candidates_root: Path,
    system_prompt_path: Path,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
    case_ids: list[str] | None = None,
    requester: Callable[[str, dict[str, Any], float], dict[str, Any]] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    cases_doc = load_smoke_cases(cases_path)
    try:
        system_prompt = system_prompt_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OracleJudgeError(f"Cannot read system prompt: {exc}") from exc
    selected = cases_doc["cases"]
    if case_ids:
        wanted = set(case_ids)
        selected = [case for case in selected if isinstance(case, dict) and case.get("case_id") in wanted]
        missing = wanted - {case.get("case_id") for case in selected}
        if missing:
            raise OracleJudgeError(f"unknown case IDs: {', '.join(sorted(missing))}")

    records = [
        evaluate_case(
            case,
            pr_candidates_root,
            system_prompt,
            model,
            temperature,
            max_tokens,
            timeout,
            requester=requester,
            dry_run=dry_run,
        )
        for case in selected
        if isinstance(case, dict)
    ]
    if not records:
        raise OracleJudgeError("no smoke cases selected")

    return {
        "schema_version": "eviscope.oracle-judge-smoke.v0.1",
        "status": SMOKE_STATUS,
        "guide_levels": list(LEVELS[:3]),
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "dry_run": dry_run,
        "case_count": len(records),
        "records": records,
        "mechanism_signals": sum(1 for record in records if record.get("mechanism_signal")),
        "expectation_matches": sum(1 for record in records if record.get("both_match_expectation")),
    }


def summarize_for_stdout(result: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for record in result.get("records", []):
        if not isinstance(record, dict):
            continue
        row = {"case_id": record.get("case_id"), "l1_richer_than_l0": record.get("l1_richer_than_l0")}
        evals = record.get("evaluations", {})
        for level in ("L0", "L1", "L2"):
            item = evals.get(level, {})
            if not item:
                continue
            row[f"{level}_bytes"] = item.get("total_bytes")
            row[f"{level}_expected"] = item.get("expected_verdict")
            row[f"{level}_verdict"] = item.get("verdict")
            row[f"{level}_match"] = item.get("matches_expectation")
        rows.append(row)
    return {
        "dry_run": result.get("dry_run"),
        "case_count": result.get("case_count"),
        "mechanism_signals": result.get("mechanism_signals"),
        "expectation_matches": result.get("expectation_matches"),
        "records": rows,
    }
