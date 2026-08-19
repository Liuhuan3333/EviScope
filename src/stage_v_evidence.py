"""Assemble review-time evidence catalogs for Stage-V annotation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from oracle_judge import OracleJudgeError, assemble_evidence, load_l0_diff
from stage_s_tools import StageSToolingError, load_json, sha256_bytes


class StageVEvidenceError(StageSToolingError):
    pass


L0_ARTIFACT_ID = "L0:review-time-diff"


def _review_timestamp(comments_path: Path, comment_id: int) -> str:
    comments = load_json(comments_path)
    if not isinstance(comments, list):
        raise StageVEvidenceError("comments JSON must be a list")
    for comment in comments:
        if isinstance(comment, dict) and comment.get("id") == comment_id:
            created = comment.get("created_at")
            if isinstance(created, str) and created:
                return created
    raise StageVEvidenceError(f"comment_id {comment_id} not found in {comments_path}")


def _repository_root(pr_candidates_root: Path, repository_id: str) -> Path:
    candidate = pr_candidates_root / repository_id
    nested = candidate / "repo"
    if nested.is_dir() and (nested / ".git").exists():
        return nested
    if candidate.is_dir() and (candidate / ".git").exists():
        return candidate
    raise StageVEvidenceError(f"no Git repository found for {repository_id}")


def _manifest_artifacts(manifest_path: Path, level: str) -> list[dict[str, Any]]:
    if not manifest_path.is_file():
        return []
    manifest = load_json(manifest_path)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    rows: list[dict[str, Any]] = []
    for record in artifacts:
        if not isinstance(record, dict) or record.get("available") is not True:
            continue
        artifact_id = record.get("artifact_id")
        kind = record.get("kind")
        source_locator = record.get("source_locator")
        sha = record.get("sha256")
        if not all(isinstance(item, str) and item for item in (artifact_id, kind, source_locator)):
            continue
        rows.append(
            {
                "artifact_id": artifact_id,
                "level": level,
                "kind": kind,
                "source_locator": source_locator,
                "sha256": sha if isinstance(sha, str) else hashlib.sha256(b"").hexdigest(),
            }
        )
    return rows


def build_sample_evidence(
    pr_candidates_root: Path,
    repository_id: str,
    comment_id: int,
    review_head_sha: str,
    comments_path: Path,
) -> dict[str, Any]:
    repo_root = _repository_root(pr_candidates_root, repository_id)
    repo_dir = pr_candidates_root / repository_id
    snapshot_dir = repo_dir / "review-snapshots" / review_head_sha
    l1_dir = repo_dir / "l1-evidence-v0.1" / f"comment-{comment_id}"
    l2_dir = repo_dir / "l2-evidence-v0.1" / f"comment-{comment_id}"

    review_timestamp = _review_timestamp(comments_path, comment_id)
    diff_bytes, l0_sha256 = load_l0_diff(snapshot_dir)

    catalog: list[dict[str, Any]] = [
        {
            "artifact_id": L0_ARTIFACT_ID,
            "level": "L0",
            "kind": "diff",
            "source_locator": f"snapshot:{review_head_sha}:L0.diff",
            "sha256": l0_sha256,
            "available_at": review_timestamp,
        }
    ]
    levels: dict[str, list[dict[str, str]]] = {}
    if l1_dir.is_dir() and (l1_dir / "manifest.json").is_file():
        catalog.extend(_manifest_artifacts(l1_dir / "manifest.json", "L1"))
    if l2_dir.is_dir() and (l2_dir / "manifest.json").is_file():
        catalog.extend(_manifest_artifacts(l2_dir / "manifest.json", "L2"))

    level_plan: list[tuple[str, Path | None, Path | None]] = [("L0", None, None)]
    if l1_dir.is_dir() and (l1_dir / "manifest.json").is_file():
        level_plan.append(("L1", l1_dir, None))
    if l2_dir.is_dir() and (l2_dir / "manifest.json").is_file():
        level_plan.append(("L2", l1_dir, l2_dir))

    for level, l1_path, l2_path in level_plan:
        try:
            bundle = assemble_evidence(snapshot_dir, l1_path, level, l2_path)
        except OracleJudgeError as exc:
            raise StageVEvidenceError(str(exc)) from exc
        levels[level] = [
            {
                "artifact_id": artifact["artifact_id"],
                "level": artifact["level"],
                "kind": artifact["kind"],
                "header": (
                    f"--- artifact_id={artifact['artifact_id']} "
                    f"level={artifact['level']} kind={artifact['kind']} ---"
                ),
                "content": artifact["content"],
            }
            for artifact in bundle["artifacts"]
        ]

    return {
        "repository_id": repository_id,
        "comment_id": comment_id,
        "review_head_sha": review_head_sha,
        "review_timestamp": review_timestamp,
        "l0_sha256": l0_sha256,
        "l0_byte_length": len(diff_bytes),
        "artifact_catalog": catalog,
        "evidence_levels": levels,
        "available_levels": [level for level, blocks in levels.items() if blocks],
    }


def dataset_record(
    sample_id: str,
    comment_text: str,
    map_row: dict[str, Any],
    evidence: dict[str, Any],
    sample_kind: str,
    analysis_eligible: bool,
    exclusion_reason: str | None,
) -> dict[str, Any]:
    path = map_row.get("path")
    if not isinstance(path, str):
        path = "unknown"
    return {
        "sample_id": sample_id,
        "sample_kind": sample_kind,
        "provenance": {
            "forge": "github",
            "repository": map_row.get("repository_id", "unknown"),
            "repository_url": None,
            "license_spdx": None,
            "pr_number": None,
            "base_sha": map_row.get("merge_base_sha"),
            "head_sha": map_row.get("review_head_sha"),
            "retrieved_at": evidence["review_timestamp"],
        },
        "review": {
            "comment_id": str(map_row.get("comment_id")),
            "comment_author_type": "human",
            "generator_registry_id": None,
            "comment_text": comment_text,
            "review_timestamp": evidence["review_timestamp"],
            "path": path,
            "original_line": None,
        },
        "artifacts": evidence["artifact_catalog"],
        "analysis_eligible": analysis_eligible,
        "exclusion_reason": exclusion_reason,
    }
