"""Progressive L0-L3 evidence escalation with a first-decisive stop rule.

This is the EviScope method object for engineering smoke: nested packages,
one judge call per level, stop at SUPPORTED or CONTRADICTED. It is not gold
and does not contact annotator working directories.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from eviscope_validation import LEVELS, VERDICTS
from oracle_judge import (
    OracleJudgeError,
    assemble_evidence,
    build_chat_payload,
    format_judge_user_message,
    parse_judge_response,
)
from stage_v_annotation import finalize_claim_verdict


DECISIVE = {"SUPPORTED", "CONTRADICTED"}
SMOKE_STATUS = "engineering_smoke_not_gold"


class EviScopeVerifierError(RuntimeError):
    pass


JudgeFn = Callable[[str, dict[str, Any]], dict[str, Any]]


def available_levels(
    snapshot_dir: Path,
    l1_dir: Path | None,
    l2_dir: Path | None,
    l3_dir: Path | None,
) -> tuple[str, ...]:
    levels: list[str] = ["L0"]
    if l1_dir is not None and (l1_dir / "manifest.json").is_file():
        levels.append("L1")
    if l2_dir is not None and (l2_dir / "manifest.json").is_file():
        levels.append("L2")
    if l3_dir is not None and (l3_dir / "manifest.json").is_file():
        levels.append("L3")
    expected = list(LEVELS[: len(levels)])
    if levels != expected:
        raise EviScopeVerifierError(f"evidence levels must be a prefix of L0-L3, got {levels}")
    return tuple(levels)


def escalate(
    comment_text: str,
    claim: dict[str, Any],
    packages: dict[str, dict[str, Any]],
    judge: JudgeFn,
) -> dict[str, Any]:
    order = [level for level in LEVELS if level in packages]
    if order != list(LEVELS[: len(order)]):
        raise EviScopeVerifierError(f"packages must be a prefix of L0-L3, got {order}")
    if not order:
        raise EviScopeVerifierError("escalate requires at least an L0 package")

    judgments: list[dict[str, Any]] = []
    called: list[str] = []
    for level in order:
        parsed = judge(level, packages[level])
        if parsed.get("verdict") not in VERDICTS:
            raise EviScopeVerifierError(f"{level} judge returned an unknown verdict")
        evidence_ids = parsed.get("evidence_ids")
        if not isinstance(evidence_ids, list) or any(not isinstance(item, str) for item in evidence_ids):
            raise EviScopeVerifierError(f"{level} judge evidence_ids must be a string array")
        known = {item["artifact_id"] for item in packages[level]["artifacts"]}
        unknown = [item for item in evidence_ids if item not in known]
        if unknown:
            raise EviScopeVerifierError(f"{level} cited unknown artifact IDs: {', '.join(unknown)}")
        judgment = {
            "level": level,
            "verdict": parsed["verdict"],
            "evidence_ids": evidence_ids,
            "rationale": parsed.get("rationale"),
            "confidence": parsed.get("confidence"),
            "artifact_count": packages[level]["artifact_count"],
            "total_bytes": packages[level]["total_bytes"],
        }
        judgments.append(judgment)
        called.append(level)
        if parsed["verdict"] in DECISIVE:
            break

    try:
        final_verdict, minimum_level = finalize_claim_verdict(judgments)
    except Exception as exc:
        raise EviScopeVerifierError(str(exc)) from exc
    return {
        "schema_version": "eviscope.escalation-trace.v0.1",
        "status": SMOKE_STATUS,
        "claim_id": claim.get("claim_id"),
        "normalized_text": claim.get("normalized_text"),
        "final_verdict": final_verdict,
        "minimum_evidence_level": minimum_level,
        "stopped_after": called[-1],
        "levels_called": called,
        "levels_skipped": [level for level in order if level not in called],
        "judgments": judgments,
        "future_artifacts_allowed": False,
    }


def load_nested_packages(
    snapshot_dir: Path,
    l1_dir: Path | None,
    l2_dir: Path | None,
    l3_dir: Path | None,
) -> dict[str, dict[str, Any]]:
    levels = available_levels(snapshot_dir, l1_dir, l2_dir, l3_dir)
    packages: dict[str, dict[str, Any]] = {}
    for level in levels:
        try:
            packages[level] = assemble_evidence(
                snapshot_dir,
                l1_dir if level in {"L1", "L2", "L3"} else None,
                level,
                l2_dir if level in {"L2", "L3"} else None,
                l3_dir if level == "L3" else None,
            )
        except OracleJudgeError as exc:
            raise EviScopeVerifierError(str(exc)) from exc
    return packages


def judge_from_requester(
    comment_text: str,
    claim: dict[str, Any],
    system_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
    requester: Callable[[str, dict[str, Any], float], dict[str, Any]],
) -> JudgeFn:
    def judge(level: str, evidence: dict[str, Any]) -> dict[str, Any]:
        user_message = format_judge_user_message(comment_text, claim, evidence)
        payload = build_chat_payload(system_prompt, user_message, model, temperature, max_tokens)
        response = requester(model, payload, timeout)
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise EviScopeVerifierError("model response has no first choice")
        message = choices[0].get("message")
        raw = message.get("content") if isinstance(message, dict) else None
        if not isinstance(raw, str):
            raise EviScopeVerifierError("model response choice has no string content")
        try:
            return parse_judge_response(raw)
        except OracleJudgeError as exc:
            raise EviScopeVerifierError(str(exc)) from exc

    return judge


def escalate_case(
    case: dict[str, Any],
    pr_candidates_root: Path,
    judge: JudgeFn,
) -> dict[str, Any]:
    repository_id = case.get("repository_id")
    review_head_sha = case.get("review_head_sha")
    comment_id = case.get("comment_id")
    comment_text = case.get("comment_text")
    claim = case.get("oracle_claim")
    if not isinstance(repository_id, str) or not isinstance(review_head_sha, str):
        raise EviScopeVerifierError("case requires repository_id and review_head_sha")
    if not isinstance(comment_id, int):
        raise EviScopeVerifierError("case requires integer comment_id")
    if not isinstance(comment_text, str) or not isinstance(claim, dict):
        raise EviScopeVerifierError("case requires comment_text and oracle_claim")
    base = pr_candidates_root / repository_id
    packages = load_nested_packages(
        base / "review-snapshots" / review_head_sha,
        base / "l1-evidence-v0.1" / f"comment-{comment_id}",
        base / "l2-evidence-v0.1" / f"comment-{comment_id}",
        base / "l3-evidence-v0.1" / f"comment-{comment_id}",
    )
    trace = escalate(comment_text, claim, packages, judge)
    trace["case_id"] = case.get("case_id")
    trace["sample_id"] = case.get("sample_id")
    trace["comment_id"] = comment_id
    trace["repository_id"] = repository_id
    return trace
