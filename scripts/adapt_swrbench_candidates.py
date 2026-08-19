#!/usr/bin/env python3
"""Build sanitized, non-gold SWR-Bench candidates and a private linkage audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stage_s_tools import StageSToolingError, load_json, sha256_path


SCHEMA_VERSION = "eviscope.swrbench-candidate-adapter.v0.1"
CANDIDATE_STATUS = "sanitized_candidate_not_sampled_not_inference_not_gold"
AUDIT_STATUS = "private_linkage_audit_not_annotation_not_gold"
SOURCE_FIELDS = {
    "repo", "instance_id", "pr_title", "pr_statement", "change_introduced",
    "base_commit", "created_at", "changes", "pr_commits", "pr_timeline", "all_commits",
}
FORBIDDEN_OUTPUT_KEYS = {
    "change_introduced", "changes", "pr_timeline", "all_commits", "author",
    "author_email", "committer", "committer_email", "author_raw_date", "author_date",
    "raw_date", "date", "change_discussion", "change_resolve_info",
}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
LINKABLE_EVENT_TYPES = {"comment", "review", "review_comment"}
LINKAGE_RULE_ID = "same-instant-unique-body-linkage.v0.1"
LINKAGE_RULE_TEXT = (
    "Match review/comment events at the same timezone-aware instant; accept only one raw-exact "
    "or whitespace-normalized-exact body; quarantine containment, ambiguity, absence, and mismatch."
)
EMAIL_LIKE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo is not None else None


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\r", "")).strip()


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _assert_no_forbidden_keys(value: Any, location: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}".strip(".")
            if key in FORBIDDEN_OUTPUT_KEYS:
                raise StageSToolingError(f"forbidden field leaked into candidate output: {child_location}")
            _assert_no_forbidden_keys(child, child_location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_forbidden_keys(child, f"{location}[{index}]")


def _event_link(original: str, timestamp: str, timeline: list[dict[str, Any]]) -> dict[str, Any]:
    target_time = _parse_time(timestamp)
    events = [
        event for event in timeline
        if isinstance(event, dict)
        and event.get("type") in LINKABLE_EVENT_TYPES
        and _parse_time(event.get("created_at")) == target_time
    ]
    candidates = [event for event in events if isinstance(event.get("body"), str)]
    raw_matches = [event for event in candidates if event["body"] == original]
    normalized_original = _normalize_whitespace(original)
    normalized_matches = [
        event for event in candidates
        if _normalize_whitespace(event["body"]) == normalized_original
    ]
    containment_matches = [
        event for event in candidates
        if normalized_original
        and _normalize_whitespace(event["body"])
        and (
            normalized_original in _normalize_whitespace(event["body"])
            or _normalize_whitespace(event["body"]) in normalized_original
        )
    ]

    if len(raw_matches) == 1:
        method, matched, deterministic = "EXACT_UNIQUE", raw_matches[0], True
    elif len(normalized_matches) == 1:
        method, matched, deterministic = "WHITESPACE_NORMALIZED_UNIQUE", normalized_matches[0], True
    elif len(containment_matches) == 1:
        method, matched, deterministic = "CONTAINMENT_UNIQUE_REVIEW_REQUIRED", containment_matches[0], False
    elif len(events) == 0:
        method, matched, deterministic = "NO_SAME_TIMESTAMP_EVENT", None, False
    elif len(containment_matches) > 1 or len(normalized_matches) > 1 or len(raw_matches) > 1:
        method, matched, deterministic = "AMBIGUOUS_SAME_TIMESTAMP_MATCH", None, False
    else:
        method, matched, deterministic = "NO_TEXT_MATCH_AT_TIMESTAMP", None, False

    result = {
        "method": method,
        "deterministic": deterministic,
        "same_timestamp_event_count": len(events),
        "source_comment_sha256": _digest_text(original),
    }
    if matched is not None:
        result.update({
            "matched_event_type": matched.get("type"),
            "matched_event_id": matched.get("id"),
            "matched_body_sha256": _digest_text(matched["body"]),
        })
    return result


def _sanitize_commit(commit: Any, location: str) -> dict[str, Any]:
    if not isinstance(commit, dict):
        raise StageSToolingError(f"{location} must be an object")
    sha = commit.get("sha")
    message = commit.get("message")
    diffs = commit.get("diff")
    if not isinstance(sha, str) or SHA40.fullmatch(sha) is None:
        raise StageSToolingError(f"{location}.sha must be a 40-character SHA")
    if not isinstance(message, str):
        raise StageSToolingError(f"{location}.message must be a string")
    if not isinstance(diffs, list) or not diffs:
        raise StageSToolingError(f"{location}.diff must be a non-empty array")
    sanitized_diffs = []
    for index, diff in enumerate(diffs):
        if not isinstance(diff, dict) or set(diff) != {"file", "patch"}:
            raise StageSToolingError(f"{location}.diff[{index}] has unexpected schema")
        if not isinstance(diff.get("file"), str) or not isinstance(diff.get("patch"), str):
            raise StageSToolingError(f"{location}.diff[{index}] requires string file and patch")
        sanitized_diffs.append({"file": diff["file"], "patch": diff["patch"]})
    return {"sha": sha, "message": message, "diff": sanitized_diffs}


def _jsonl_bytes(records: Iterable[dict[str, Any]]) -> bytes:
    return b"".join(
        (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        for record in records
    )


def _write_bytes(path: Path, value: bytes) -> str:
    path.write_bytes(value)
    return hashlib.sha256(value).hexdigest()


def _email_like_counts(candidate: dict[str, Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for field in ("pr_title", "pr_statement"):
        counts[field] += len(EMAIL_LIKE.findall(candidate[field]))
    for commit in candidate["pr_commits"]:
        counts["commit_message"] += len(EMAIL_LIKE.findall(commit["message"]))
        for diff in commit["diff"]:
            counts["diff_file"] += len(EMAIL_LIKE.findall(diff["file"]))
            counts["diff_patch"] += len(EMAIL_LIKE.findall(diff["patch"]))
    return counts


def build_candidates(dataset_path: Path, protocol_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    protocol = load_json(protocol_path)
    if protocol.get("schema_version") != "eviscope.swrbench-adaptation-protocol.v0.1":
        raise StageSToolingError("unsupported SWR-Bench adaptation protocol")
    if protocol.get("status") != "candidate_external_validation_source_not_gold":
        raise StageSToolingError("protocol does not preserve candidate/not-gold status")
    expected_hash = protocol.get("source", {}).get("dataset_sha256")
    observed_hash = sha256_path(dataset_path)
    if expected_hash != observed_hash:
        raise StageSToolingError("dataset SHA-256 does not match the adaptation protocol")

    candidates: list[dict[str, Any]] = []
    linkage: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    link_methods: Counter[str] = Counter()
    record_count = positive_count = clean_count = change_count = 0
    future_fix_overlap_count = 0
    email_like_occurrences: Counter[str] = Counter()
    records_with_email_like_text = 0

    try:
        source = dataset_path.open(encoding="utf-8")
    except OSError as exc:
        raise StageSToolingError(f"cannot read SWR-Bench dataset: {exc}") from exc
    with source:
        for line_number, line in enumerate(source, start=1):
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise StageSToolingError(f"invalid JSONL record at line {line_number}: {exc}") from exc
            if not isinstance(item, dict) or set(item) != SOURCE_FIELDS:
                raise StageSToolingError(f"line {line_number} has unexpected top-level schema")
            instance_id = item.get("instance_id")
            if not isinstance(instance_id, str) or not instance_id or instance_id in seen_ids:
                raise StageSToolingError(f"line {line_number} has missing or duplicate instance_id")
            seen_ids.add(instance_id)
            if not isinstance(item.get("repo"), str) or "/" not in item["repo"]:
                raise StageSToolingError(f"{instance_id}: repo must be owner/name")
            if not isinstance(item.get("base_commit"), str) or SHA40.fullmatch(item["base_commit"]) is None:
                raise StageSToolingError(f"{instance_id}: invalid base_commit")
            if _parse_time(item.get("created_at")) is None:
                raise StageSToolingError(f"{instance_id}: created_at must be timezone-aware")
            if not isinstance(item.get("pr_title"), str) or not isinstance(item.get("pr_statement"), str):
                raise StageSToolingError(f"{instance_id}: title and statement must be strings")
            if not isinstance(item.get("pr_commits"), list) or not item["pr_commits"]:
                raise StageSToolingError(f"{instance_id}: pr_commits must be non-empty")
            commits = [
                _sanitize_commit(commit, f"{instance_id}.pr_commits[{index}]")
                for index, commit in enumerate(item["pr_commits"])
            ]
            commit_shas = {commit["sha"] for commit in commits}
            if len(commit_shas) != len(commits):
                raise StageSToolingError(f"{instance_id}: duplicate PR commit SHA")
            if not isinstance(item.get("changes"), list) or not isinstance(item.get("pr_timeline"), list):
                raise StageSToolingError(f"{instance_id}: changes and timeline must be arrays")
            if any(not isinstance(event, dict) for event in item["pr_timeline"]):
                raise StageSToolingError(f"{instance_id}: every timeline event must be an object")
            positive = item.get("change_introduced")
            if not isinstance(positive, bool) or positive != bool(item["changes"]):
                raise StageSToolingError(f"{instance_id}: label/change-list inconsistency")

            candidate = {
                "schema_version": SCHEMA_VERSION,
                "status": CANDIDATE_STATUS,
                "instance_id": instance_id,
                "repo": item["repo"],
                "base_commit": item["base_commit"],
                "created_at": item["created_at"],
                "pr_title": item["pr_title"],
                "pr_statement": item["pr_statement"],
                "pr_commits": commits,
            }
            _assert_no_forbidden_keys(candidate)
            candidate_email_counts = _email_like_counts(candidate)
            email_like_occurrences.update(candidate_email_counts)
            records_with_email_like_text += int(sum(candidate_email_counts.values()) > 0)
            candidates.append(candidate)
            record_count += 1
            positive_count += int(positive)
            clean_count += int(not positive)

            for change_index, change in enumerate(item["changes"]):
                if not isinstance(change, dict):
                    raise StageSToolingError(f"{instance_id}.changes[{change_index}] must be an object")
                discussion = change.get("change_discussion")
                introducing = change.get("change_introducing")
                resolution = change.get("change_resolve_info")
                if not isinstance(discussion, dict) or not isinstance(introducing, dict):
                    raise StageSToolingError(f"{instance_id}.changes[{change_index}] lacks provenance")
                original = discussion.get("original_reviewer_comment")
                mention_time = discussion.get("first_mention_timestamp")
                intro_sha = introducing.get("commit_sha")
                if not isinstance(original, str) or not original or _parse_time(mention_time) is None:
                    raise StageSToolingError(f"{instance_id}.changes[{change_index}] has invalid discussion provenance")
                if not isinstance(intro_sha, str) or intro_sha not in commit_shas:
                    raise StageSToolingError(f"{instance_id}.changes[{change_index}] introducing SHA is outside pr_commits")
                resolution_sha = resolution.get("commit_sha") if isinstance(resolution, dict) else None
                future_overlap = isinstance(resolution_sha, str) and resolution_sha in commit_shas
                future_fix_overlap_count += int(future_overlap)
                link = _event_link(original, mention_time, item["pr_timeline"])
                link_methods[link["method"]] += 1
                change_count += 1
                linkage.append({
                    "schema_version": SCHEMA_VERSION,
                    "status": (
                        "linked_candidate_not_annotation_not_gold"
                        if link["deterministic"] and not future_overlap
                        else "quarantined_requires_manual_source_audit_not_gold"
                    ),
                    "instance_id": instance_id,
                    "change_index": change_index,
                    "change_ref": _digest_text(f"{instance_id}:{change_index}"),
                    "first_mention_timestamp": mention_time,
                    "introducing_commit_sha": intro_sha,
                    "resolution_commit_in_model_input": future_overlap,
                    "linkage": link,
                })

    summary = {
        "record_count": record_count,
        "positive_source_record_count_private_audit_only": positive_count,
        "clean_source_record_count_private_audit_only": clean_count,
        "change_count": change_count,
        "linkage_method_counts": dict(sorted(link_methods.items())),
        "deterministically_linked_change_count": sum(
            1 for record in linkage if record["linkage"]["deterministic"]
        ),
        "quarantined_change_count": sum(
            1 for record in linkage if record["status"].startswith("quarantined")
        ),
        "resolution_commit_in_model_input_count": future_fix_overlap_count,
        "email_like_occurrence_counts_in_visible_free_text": {
            field: email_like_occurrences[field]
            for field in ("pr_title", "pr_statement", "commit_message", "diff_file", "diff_patch")
        },
        "records_with_email_like_visible_free_text": records_with_email_like_text,
    }
    return candidates, linkage, summary


def adapt(dataset_path: Path, protocol_path: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise StageSToolingError(f"Refusing to overwrite existing output directory: {output_dir}")
    if not output_dir.parent.exists():
        raise StageSToolingError(f"output parent does not exist: {output_dir.parent}")
    candidates, linkage, summary = build_candidates(dataset_path, protocol_path)
    with tempfile.TemporaryDirectory(prefix=f".{output_dir.name}.", dir=output_dir.parent) as temporary:
        temp = Path(temporary)
        candidate_hash = _write_bytes(temp / "candidate_inputs.jsonl", _jsonl_bytes(candidates))
        linkage_hash = _write_bytes(temp / "private_linkage_audit.jsonl", _jsonl_bytes(linkage))
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "status": AUDIT_STATUS,
            "source": {
                "dataset_sha256": sha256_path(dataset_path),
                "protocol_sha256": sha256_path(protocol_path),
                "adapter_script_sha256": sha256_path(Path(__file__)),
            },
            "linkage_rule": {
                "rule_id": LINKAGE_RULE_ID,
                "rule_sha256": _digest_text(LINKAGE_RULE_TEXT),
            },
            "outputs": {
                "candidate_inputs.jsonl": candidate_hash,
                "private_linkage_audit.jsonl": linkage_hash,
            },
            "summary": summary,
            "controls": {
                "sampling_performed": False,
                "model_inference_eligible": False,
                "gold_analysis_eligible": False,
                "review_time_snapshot_verification_complete": False,
                "source_labels_absent_from_candidate_inputs": True,
                "structured_identity_fields_stripped": True,
                "free_text_email_like_occurrences_scanned_not_redacted": True,
                "raw_reviewer_comment_text_absent_from_linkage_audit": True,
                "unresolved_linkage_quarantined": True,
            },
        }
        manifest_hash = _write_bytes(
            temp / "manifest.json",
            (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
        os.rename(temp, output_dir)
    return {"manifest_sha256": manifest_hash, **summary}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = adapt(args.dataset, args.protocol, args.output)
    except StageSToolingError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
