#!/usr/bin/env python3
"""Apply frozen temporal and metadata rules to SWR candidates without sampling."""

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


SCHEMA_VERSION = "eviscope.swrbench-review-time-candidates.v0.1"
HUMAN_EVENT_TYPES = {"comment", "review", "review_comment"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _jsonl(records: Iterable[dict[str, Any]]) -> bytes:
    return b"".join(
        (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        for record in records
    )


def _write(path: Path, content: bytes) -> str:
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _redact_metadata(value: str, email: re.Pattern[str], replacement: str,
                     trailers: re.Pattern[str], trailer_replacement: str) -> tuple[str, int, int]:
    lines = []
    email_count = trailer_count = 0
    for line in value.splitlines(keepends=True):
        ending = "\n" if line.endswith("\n") else ""
        body = line[:-1] if ending else line
        if trailers.match(body):
            lines.append(trailer_replacement + ending)
            trailer_count += 1
        else:
            body, count = email.subn(replacement, body)
            email_count += count
            lines.append(body + ending)
    return "".join(lines), email_count, trailer_count


def _load_policy(policy_path: Path, dataset_path: Path, adaptation_protocol_path: Path,
                 adapter_manifest_path: Path) -> dict[str, Any]:
    policy = load_json(policy_path)
    if policy.get("schema_version") != "eviscope.swrbench-review-time-policy.v0.1":
        raise StageSToolingError("unsupported SWR review-time policy")
    if policy.get("status") != "candidate_reconstruction_policy_not_inference_not_gold":
        raise StageSToolingError("review-time policy does not preserve non-inference/not-gold status")
    expected = policy.get("inputs", {})
    observed = {
        "dataset_sha256": sha256_path(dataset_path),
        "adaptation_protocol_sha256": sha256_path(adaptation_protocol_path),
        "candidate_adapter_manifest_sha256": sha256_path(adapter_manifest_path),
    }
    if expected != observed:
        raise StageSToolingError("review-time policy input hashes do not match supplied artifacts")
    controls = policy.get("output_controls", {})
    if any(controls.get(field) is not False for field in (
        "sampling_performed", "model_inference_eligible", "gold_analysis_eligible",
        "swr_labels_exported", "post_review_fields_exported",
    )):
        raise StageSToolingError("review-time policy output controls are not safely disabled")
    return policy


def prepare(dataset_path: Path, adaptation_protocol_path: Path, adapter_manifest_path: Path,
            policy_path: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise StageSToolingError(f"Refusing to overwrite existing output directory: {output_dir}")
    if not output_dir.parent.exists():
        raise StageSToolingError(f"output parent does not exist: {output_dir.parent}")
    policy = _load_policy(policy_path, dataset_path, adaptation_protocol_path, adapter_manifest_path)
    adapter_manifest = load_json(adapter_manifest_path)
    if adapter_manifest.get("controls", {}).get("model_inference_eligible") is not False:
        raise StageSToolingError("input adapter manifest is not safely inference-disabled")

    redaction = policy["metadata_redaction"]
    email = re.compile(redaction["email_pattern"])
    prefixes = "|".join(re.escape(value) for value in redaction["identity_trailer_prefixes"])
    trailers = re.compile(rf"^(?:{prefixes}):", re.IGNORECASE)
    safe: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    seen: set[str] = set()
    summary: Counter[str] = Counter()

    try:
        source = dataset_path.open(encoding="utf-8")
    except OSError as exc:
        raise StageSToolingError(f"cannot read dataset: {exc}") from exc
    with source:
        for line_number, line in enumerate(source, start=1):
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise StageSToolingError(f"invalid JSONL at line {line_number}: {exc}") from exc
            instance_id = item.get("instance_id") if isinstance(item, dict) else None
            if not isinstance(instance_id, str) or not instance_id or instance_id in seen:
                raise StageSToolingError(f"line {line_number} has missing or duplicate instance_id")
            seen.add(instance_id)
            timeline = item.get("pr_timeline")
            commits = item.get("pr_commits")
            if not isinstance(timeline, list) or not isinstance(commits, list) or not commits:
                raise StageSToolingError(f"{instance_id}: timeline and non-empty commits are required")
            if any(not isinstance(event, dict) for event in timeline):
                raise StageSToolingError(f"{instance_id}: malformed timeline event")
            cutoffs = [
                parsed for event in timeline
                if event.get("type") in HUMAN_EVENT_TYPES
                for parsed in [_time(event.get("created_at"))]
                if parsed is not None
            ]
            cutoff = min(cutoffs) if cutoffs else None
            timeline_commits: dict[str, list[dict[str, Any]]] = {}
            for event in timeline:
                if event.get("type") == "commit":
                    timeline_commits.setdefault(event.get("sha"), []).append(event)

            late_shas = []
            integrity_failures = []
            sanitized_commits = []
            record_email_redactions = 0
            record_trailer_redactions = 0
            for index, commit in enumerate(commits):
                if not isinstance(commit, dict) or not isinstance(commit.get("sha"), str) or SHA40.fullmatch(commit["sha"]) is None:
                    raise StageSToolingError(f"{instance_id}.pr_commits[{index}] is malformed")
                commit_time = _time(commit.get("date"))
                if commit_time is None:
                    integrity_failures.append("INVALID_COMMIT_TIME")
                elif cutoff is not None and commit_time > cutoff:
                    late_shas.append(commit["sha"])
                matches = timeline_commits.get(commit["sha"], [])
                if len(matches) != 1:
                    integrity_failures.append("NON_UNIQUE_TIMELINE_COMMIT")
                elif any(commit.get(field) != matches[0].get(field) for field in ("message", "diff_text", "diff")):
                    integrity_failures.append("TIMELINE_COMMIT_CONTENT_MISMATCH")
                message, emails, trailers_removed = _redact_metadata(
                    commit.get("message", ""), email, redaction["email_replacement"],
                    trailers, redaction["identity_trailer_replacement"],
                )
                record_email_redactions += emails
                record_trailer_redactions += trailers_removed
                diffs = commit.get("diff")
                if not isinstance(diffs, list) or any(
                    not isinstance(diff, dict) or set(diff) != {"file", "patch"}
                    or not isinstance(diff.get("file"), str) or not isinstance(diff.get("patch"), str)
                    for diff in diffs
                ):
                    raise StageSToolingError(f"{instance_id}.pr_commits[{index}].diff is malformed")
                sanitized_commits.append({
                    "sha": commit["sha"], "message": message,
                    "diff": [{"file": diff["file"], "patch": diff["patch"]} for diff in diffs],
                })

            if cutoff is None:
                status, reason = "quarantined_not_gold", "MISSING_HUMAN_CUTOFF"
            elif late_shas:
                status, reason = "quarantined_not_gold", "COMMIT_AFTER_FIRST_HUMAN_INTERACTION"
            elif integrity_failures:
                status, reason = "quarantined_not_gold", sorted(set(integrity_failures))[0]
            else:
                status, reason = (
                    "timestamp_consistent_requires_repository_verification_not_inference_not_gold",
                    "REPOSITORY_RECONSTRUCTION_PENDING",
                )
                title, count, _ = _redact_metadata(
                    item["pr_title"], email, redaction["email_replacement"], trailers,
                    redaction["identity_trailer_replacement"],
                )
                summary["metadata_email_redactions"] += count
                statement, count, _ = _redact_metadata(
                    item["pr_statement"], email, redaction["email_replacement"], trailers,
                    redaction["identity_trailer_replacement"],
                )
                summary["metadata_email_redactions"] += count
                summary["metadata_email_redactions"] += record_email_redactions
                summary["identity_trailer_redactions"] += record_trailer_redactions
                safe.append({
                    "schema_version": SCHEMA_VERSION,
                    "status": status,
                    "instance_id": instance_id,
                    "repo": item["repo"],
                    "base_commit": item["base_commit"],
                    "review_time_cutoff": cutoff.isoformat(),
                    "pr_title": title,
                    "pr_statement": statement,
                    "pr_commits": sanitized_commits,
                })
            summary["source_record_count"] += 1
            summary["timestamp_consistent_candidate_count"] += int(status.startswith("timestamp_consistent"))
            summary["quarantined_record_count"] += int(status.startswith("quarantined"))
            summary["late_commit_count"] += len(late_shas)
            audits.append({
                "schema_version": SCHEMA_VERSION,
                "status": status,
                "instance_id": instance_id,
                "review_time_cutoff": cutoff.isoformat() if cutoff else None,
                "commit_count": len(commits),
                "late_commit_count": len(late_shas),
                "late_commit_sha256s": [hashlib.sha256(sha.encode()).hexdigest() for sha in late_shas],
                "integrity_failures": sorted(set(integrity_failures)),
                "reason": reason,
            })

    with tempfile.TemporaryDirectory(prefix=f".{output_dir.name}.", dir=output_dir.parent) as temporary:
        temp = Path(temporary)
        outputs = {
            "candidate_inputs.jsonl": _write(temp / "candidate_inputs.jsonl", _jsonl(safe)),
            "review_time_audit.jsonl": _write(temp / "review_time_audit.jsonl", _jsonl(audits)),
        }
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "status": "private_temporal_audit_not_sampled_not_inference_not_gold",
            "inputs": {
                "dataset_sha256": sha256_path(dataset_path),
                "adaptation_protocol_sha256": sha256_path(adaptation_protocol_path),
                "adapter_manifest_sha256": sha256_path(adapter_manifest_path),
                "review_time_policy_sha256": sha256_path(policy_path),
                "script_sha256": sha256_path(Path(__file__)),
            },
            "outputs": outputs,
            "summary": dict(sorted(summary.items())),
            "controls": {
                "sampling_performed": False,
                "model_inference_eligible": False,
                "gold_analysis_eligible": False,
                "repository_reconstruction_complete": False,
                "swr_labels_exported": False,
                "post_review_fields_exported": False,
                "diff_code_literals_preserved": True,
            },
        }
        manifest_hash = _write(
            temp / "manifest.json",
            (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
        os.rename(temp, output_dir)
    return {"manifest_sha256": manifest_hash, **dict(sorted(summary.items()))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--adaptation-protocol", required=True, type=Path)
    parser.add_argument("--adapter-manifest", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = prepare(
            args.dataset, args.adaptation_protocol, args.adapter_manifest, args.policy, args.output
        )
    except StageSToolingError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
