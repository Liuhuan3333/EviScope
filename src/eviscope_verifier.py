"""Progressive L0-L3 evidence escalation with a first-decisive stop rule.

This is the EviScope method object for engineering smoke: nested packages,
one judge call per level, stop at SUPPORTED or CONTRADICTED. It is not gold
and does not contact annotator working directories.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from eviscope_validation import LEVELS, VERDICTS
from l2_evidence import extract_comment_paths
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


def resolve_evidence_ids(cited: list[str], known: set[str]) -> tuple[list[str], list[str]]:
    """Map judge citations onto package artifact IDs.

    Exact IDs pass through. A unique prefix such as ``L0`` may resolve to
    ``L0:review-time-diff``. Ambiguous or unknown citations are rejected.
    """
    resolved: list[str] = []
    remapped: list[str] = []
    unknown: list[str] = []
    for item in cited:
        if item.startswith("artifact_id="):
            item = item[len("artifact_id=") :]
        if item in known:
            resolved.append(item)
            continue
        matches = sorted(candidate for candidate in known if candidate.startswith(item + ":"))
        if len(matches) == 1:
            resolved.append(matches[0])
            remapped.append(item)
        else:
            unknown.append(item)
    if unknown:
        raise EviScopeVerifierError(f"cited unknown artifact IDs: {', '.join(unknown)}")
    return resolved, remapped


def _is_l0_artifact(artifact: dict[str, Any]) -> bool:
    return artifact.get("level") == "L0" or artifact.get("artifact_id") == "L0:review-time-diff"


def artifact_mentions_named_path(artifact: dict[str, Any], named_paths: list[str]) -> bool:
    haystack = " ".join(
        str(artifact.get(key) or "")
        for key in ("artifact_id", "path", "source_locator", "kind")
    ).replace("\\", "/")
    return any(named.replace("\\", "/") in haystack for named in named_paths)


def l0_diff_contains_named_path(artifact: dict[str, Any], named_paths: list[str]) -> bool:
    content = str(artifact.get("content") or "").replace("\\", "/")
    return any(named.replace("\\", "/") in content for named in named_paths)


def constrain_package(package: dict[str, Any], named_paths: list[str]) -> dict[str, Any]:
    """Keep L0 plus artifacts whose locator matches a path named by the claim."""
    if not named_paths:
        return package
    kept: list[dict[str, Any]] = []
    for artifact in package["artifacts"]:
        if _is_l0_artifact(artifact) or artifact_mentions_named_path(artifact, named_paths):
            kept.append(artifact)
    constrained = dict(package)
    constrained["artifacts"] = kept
    constrained["artifact_count"] = len(kept)
    constrained["total_bytes"] = sum(item["byte_length"] for item in kept)
    constrained["path_constrained"] = True
    constrained["named_paths"] = named_paths
    constrained["dropped_artifact_count"] = package["artifact_count"] - len(kept)
    return constrained


def apply_path_constraint(
    verdict: str,
    evidence_ids: list[str],
    package: dict[str, Any],
    named_paths: list[str],
) -> tuple[str, str | None]:
    if not named_paths or verdict not in DECISIVE:
        return verdict, None
    by_id = {item["artifact_id"]: item for item in package["artifacts"]}
    for evidence_id in evidence_ids:
        artifact = by_id.get(evidence_id)
        if artifact is None:
            continue
        if _is_l0_artifact(artifact):
            if l0_diff_contains_named_path(artifact, named_paths):
                return verdict, None
            continue
        if artifact_mentions_named_path(artifact, named_paths):
            return verdict, None
    return "INSUFFICIENT", "rejected_off_path_citation"


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

    named_paths = extract_comment_paths(str(claim.get("normalized_text") or ""))
    judgments: list[dict[str, Any]] = []
    called: list[str] = []
    for level in order:
        package = constrain_package(packages[level], named_paths)
        parsed = judge(level, package)
        if parsed.get("verdict") not in VERDICTS:
            raise EviScopeVerifierError(f"{level} judge returned an unknown verdict")
        evidence_ids = parsed.get("evidence_ids")
        if not isinstance(evidence_ids, list) or any(not isinstance(item, str) for item in evidence_ids):
            raise EviScopeVerifierError(f"{level} judge evidence_ids must be a string array")
        known = {item["artifact_id"] for item in package["artifacts"]}
        try:
            evidence_ids, remapped = resolve_evidence_ids(evidence_ids, known)
        except EviScopeVerifierError as exc:
            raise EviScopeVerifierError(f"{level} {exc}") from exc
        raw_verdict = parsed["verdict"]
        verdict, constraint = apply_path_constraint(raw_verdict, evidence_ids, package, named_paths)
        judgment = {
            "level": level,
            "verdict": verdict,
            "raw_verdict": raw_verdict,
            "path_constraint": constraint,
            "evidence_ids": evidence_ids,
            "remapped_evidence_ids": remapped,
            "rationale": parsed.get("rationale"),
            "confidence": parsed.get("confidence"),
            "artifact_count": package["artifact_count"],
            "total_bytes": package["total_bytes"],
            "dropped_artifact_count": package.get("dropped_artifact_count", 0),
        }
        judgments.append(judgment)
        called.append(level)
        if verdict in DECISIVE:
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
        "named_paths": named_paths,
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
