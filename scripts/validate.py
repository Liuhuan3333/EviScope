#!/usr/bin/env python3
"""Validate EviScope manifests and governance records."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eviscope_validation import validate_file  # noqa: E402


def all_files() -> list[Path]:
    patterns = (
        "configs/*.json",
        "governance/*.json",
        "data/manifests/*.json",
    )
    return sorted({path for pattern in patterns for path in ROOT.glob(pattern)})


def cross_reference_issues(paths: list[Path]) -> list[str]:
    """Check links that cannot be validated from one JSON document alone."""
    documents: list[tuple[Path, dict]] = []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            documents.append((path, data))

    sample_artifacts: dict[str, dict[str, str]] = {}
    sample_comments: dict[str, str] = {}
    issues: list[str] = []
    for path, data in documents:
        if data.get("schema_version") != "eviscope.dataset-manifest.v0.1":
            continue
        records = data.get("records")
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("sample_id"), str):
                continue
            sample_id = record["sample_id"]
            if sample_id in sample_artifacts:
                issues.append(f"{path} [records]: duplicate sample_id across dataset manifests: {sample_id}")
                continue
            artifacts = record.get("artifacts")
            if not isinstance(artifacts, list):
                artifacts = []
            sample_artifacts[sample_id] = {
                artifact["artifact_id"]: artifact["level"]
                for artifact in artifacts
                if (
                    isinstance(artifact, dict)
                    and isinstance(artifact.get("artifact_id"), str)
                    and isinstance(artifact.get("level"), str)
                )
            }
            review = record.get("review")
            if isinstance(review, dict) and isinstance(review.get("comment_text"), str):
                sample_comments[sample_id] = review["comment_text"]

    screenings: dict[str, tuple[Path, dict, str]] = {}
    for path, data in documents:
        if data.get("schema_version") != "eviscope.materiality-screening.v0.3":
            continue
        screening_id = data.get("screening_id")
        if not isinstance(screening_id, str):
            continue
        if screening_id in screenings:
            issues.append(f"{path} [screening_id]: duplicate screening_id: {screening_id}")
            continue
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
        screenings[screening_id] = (path, data, digest)
        sample_id = data.get("sample_id")
        if sample_id not in sample_artifacts:
            issues.append(f"{path} [sample_id]: no matching dataset record: {sample_id}")
            continue
        comment_text = sample_comments.get(sample_id)
        claims = data.get("claims")
        if comment_text is None or not isinstance(claims, list):
            continue
        for claim_index, claim in enumerate(claims):
            if not isinstance(claim, dict) or not isinstance(claim.get("source_fragments"), list):
                continue
            for fragment_index, fragment in enumerate(claim["source_fragments"]):
                if not isinstance(fragment, dict):
                    continue
                start, end, text = fragment.get("start"), fragment.get("end"), fragment.get("text")
                if (
                    isinstance(start, int)
                    and not isinstance(start, bool)
                    and isinstance(end, int)
                    and not isinstance(end, bool)
                    and isinstance(text, str)
                    and (start < 0 or end > len(comment_text) or comment_text[start:end] != text)
                ):
                    issues.append(
                        f"{path} [claims[{claim_index}].source_fragments[{fragment_index}]]: "
                        "fragment text must exactly match its character span in the source comment"
                    )

    levels = ("L0", "L1", "L2", "L3")
    for path, data in documents:
        version = data.get("schema_version")
        if version in {"eviscope.annotation.v0.2", "eviscope.annotation.v0.3"}:
            sample_id = data.get("sample_id")
            if sample_id not in sample_artifacts:
                issues.append(f"{path} [sample_id]: no matching dataset record: {sample_id}")
                continue
            known = sample_artifacts[sample_id]
            comment_text = sample_comments.get(sample_id)
            claims = data.get("claims")
            if not isinstance(claims, list):
                continue

            if version == "eviscope.annotation.v0.2":
                for claim_index, claim in enumerate(claims):
                    if not isinstance(claim, dict):
                        continue
                    span = claim.get("source_span")
                    claim_text = claim.get("text")
                    if (
                        comment_text is not None
                        and isinstance(span, dict)
                        and isinstance(span.get("start"), int)
                        and not isinstance(span.get("start"), bool)
                        and isinstance(span.get("end"), int)
                        and not isinstance(span.get("end"), bool)
                        and isinstance(claim_text, str)
                    ):
                        start_offset, end_offset = span["start"], span["end"]
                        if (
                            start_offset < 0
                            or end_offset > len(comment_text)
                            or comment_text[start_offset:end_offset] != claim_text
                        ):
                            issues.append(
                                f"{path} [claims[{claim_index}].source_span]: "
                                "claim text must exactly match its character span in the source comment"
                            )
            else:
                screening_id = data.get("screening_id")
                screening = screenings.get(screening_id)
                if screening is None:
                    issues.append(f"{path} [screening_id]: no matching Stage-S screening: {screening_id}")
                else:
                    _, screening_data, screening_digest = screening
                    if data.get("screening_sha256") != screening_digest:
                        issues.append(f"{path} [screening_sha256]: does not match the frozen Stage-S file")
                    if screening_data.get("sample_id") != sample_id:
                        issues.append(f"{path} [sample_id]: does not match the Stage-S screening sample")
                    if screening_data.get("annotation_round") != "adjudication":
                        issues.append(f"{path} [screening_id]: Stage V requires an adjudicated Stage-S record")
                    if screening_data.get("decision") != "MATERIAL":
                        issues.append(f"{path} [screening_id]: Stage V requires a MATERIAL Stage-S record")
                    screening_claims = screening_data.get("claims")
                    screening_claim_ids = (
                        [claim.get("claim_id") for claim in screening_claims if isinstance(claim, dict)]
                        if isinstance(screening_claims, list)
                        else []
                    )
                    verdict_claim_ids = [claim.get("claim_id") for claim in claims if isinstance(claim, dict)]
                    if verdict_claim_ids != screening_claim_ids:
                        issues.append(
                            f"{path} [claims]: Stage-V claim IDs and order must exactly match frozen Stage-S claims"
                        )

            for claim_index, claim in enumerate(claims):
                if not isinstance(claim, dict):
                    continue
                judgments = claim.get("judgments")
                if not isinstance(judgments, list):
                    continue
                for judgment_index, judgment in enumerate(judgments):
                    if not isinstance(judgment, dict):
                        continue
                    evidence_ids = judgment.get("evidence_ids")
                    if not isinstance(evidence_ids, list):
                        continue
                    for evidence_id in evidence_ids:
                        if not isinstance(evidence_id, str):
                            continue
                        if evidence_id not in known:
                            issues.append(
                                f"{path} [claims[{claim_index}].judgments[{judgment_index}].evidence_ids]: "
                                f"unknown artifact ID for {sample_id}: {evidence_id}"
                            )
                            continue
                        judgment_level = judgment.get("level")
                        evidence_level = known[evidence_id]
                        if (
                            judgment_level in levels
                            and evidence_level in levels
                            and levels.index(evidence_level) > levels.index(judgment_level)
                        ):
                            issues.append(
                                f"{path} [claims[{claim_index}].judgments[{judgment_index}].evidence_ids]: "
                                f"future-level evidence {evidence_id} ({evidence_level}) cited at {judgment_level}"
                            )
        elif version == "eviscope.pilot-manifest.v0.1":
            samples = data.get("samples")
            if not isinstance(samples, list):
                continue
            for sample_id in samples:
                if sample_id not in sample_artifacts:
                    issues.append(f"{path} [samples]: no matching dataset record: {sample_id}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--all", action="store_true", help="validate all tracked Gate 0 records")
    args = parser.parse_args()
    if args.all == bool(args.paths):
        parser.error("provide either --all or one or more JSON paths")
    paths = all_files() if args.all else args.paths
    issue_count = 0
    for path in paths:
        issues = validate_file(path)
        if issues:
            issue_count += len(issues)
            for issue in issues:
                print(issue, file=sys.stderr)
        else:
            print(f"OK {path}")
    if args.all:
        cross_issues = cross_reference_issues(paths)
        issue_count += len(cross_issues)
        for issue in cross_issues:
            print(issue, file=sys.stderr)
    print(json.dumps({"files": len(paths), "issues": issue_count}))
    return 1 if issue_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
