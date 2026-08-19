#!/usr/bin/env python3
"""Prepare a blinded Stage-V packet from adjudicated Stage-S MATERIAL records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stage_s_tools import StageSToolingError, load_json, sha256_path, write_new_json  # noqa: E402
from stage_v_evidence import StageVEvidenceError, build_sample_evidence, dataset_record  # noqa: E402


def _load_screening(path: Path) -> dict[str, Any]:
    record = load_json(path)
    if not isinstance(record, dict):
        raise StageSToolingError(f"{path} must contain an object")
    if record.get("schema_version") != "eviscope.materiality-screening.v0.3":
        raise StageSToolingError(f"{path} is not a v0.3 screening record")
    if record.get("annotation_round") != "adjudication":
        raise StageSToolingError(f"{path} must be an adjudicated Stage-S record")
    if record.get("decision") != "MATERIAL":
        raise StageSToolingError(f"{path} must be MATERIAL")
    if not record.get("claims"):
        raise StageSToolingError(f"{path} must contain frozen claims")
    return record


def _comment_lookup(path: Path) -> dict[str, str]:
    packet = load_json(path)
    samples = packet.get("samples")
    if not isinstance(samples, list):
        raise StageSToolingError("comment packet must contain samples")
    return {
        sample["sample_id"]: sample["comment_text"]
        for sample in samples
        if isinstance(sample, dict) and isinstance(sample.get("sample_id"), str)
    }


def _map_lookup(path: Path) -> dict[str, dict[str, Any]]:
    payload = load_json(path)
    samples = payload.get("samples")
    if not isinstance(samples, list):
        raise StageSToolingError("sample map must contain samples")
    return {
        sample["sample_id"]: sample
        for sample in samples
        if isinstance(sample, dict) and isinstance(sample.get("sample_id"), str)
    }


def prepare(
    adjudicated_records_dir: Path,
    comment_texts_path: Path,
    sample_map_path: Path,
    pr_candidates_root: Path,
    output_dir: Path,
    selection_id: str,
    status: str,
    repository_id: str | None,
    review_head_sha: str | None,
    sample_kind: str,
    analysis_eligible: bool,
    exclusion_reason: str | None,
    sample_ids: set[str] | None,
) -> dict[str, str]:
    if output_dir.exists():
        raise StageSToolingError(f"refusing to overwrite existing output directory: {output_dir}")
    comments = _comment_lookup(comment_texts_path)
    mapping = _map_lookup(sample_map_path)
    screenings = sorted(adjudicated_records_dir.glob("*.json"))
    if not screenings:
        raise StageSToolingError(f"no adjudicated screening records in {adjudicated_records_dir}")

    dataset_records: list[dict[str, Any]] = []
    packet_samples: list[dict[str, Any]] = []
    for screening_path in screenings:
        screening = _load_screening(screening_path)
        sample_id = screening["sample_id"]
        if sample_ids is not None and sample_id not in sample_ids:
            continue
        if sample_id not in comments:
            raise StageSToolingError(f"no comment text for sample {sample_id}")
        if sample_id not in mapping:
            raise StageSToolingError(f"no private map row for sample {sample_id}")
        map_row = dict(mapping[sample_id])
        map_row.setdefault("repository_id", repository_id)
        map_row.setdefault("review_head_sha", review_head_sha)
        if not isinstance(map_row.get("comment_id"), int):
            raise StageSToolingError(f"sample map row for {sample_id} requires comment_id")
        if not isinstance(map_row.get("repository_id"), str) or not map_row["repository_id"]:
            raise StageSToolingError(f"sample map row for {sample_id} requires repository_id")
        if not isinstance(map_row.get("review_head_sha"), str) or not map_row["review_head_sha"]:
            raise StageSToolingError(f"sample map row for {sample_id} requires review_head_sha")

        comments_path = pr_candidates_root / map_row["repository_id"] / "raw" / "inline_comments.json"
        evidence = build_sample_evidence(
            pr_candidates_root,
            map_row["repository_id"],
            map_row["comment_id"],
            map_row["review_head_sha"],
            comments_path,
        )
        known_artifact_ids = {
            level: [block["artifact_id"] for block in blocks]
            for level, blocks in evidence["evidence_levels"].items()
        }
        packet_samples.append(
            {
                "sample_id": sample_id,
                "screening_id": screening["screening_id"],
                "screening_sha256": sha256_path(screening_path),
                "comment_text": comments[sample_id],
                "claims": screening["claims"],
                "evidence_levels": evidence["evidence_levels"],
                "known_artifact_ids": known_artifact_ids,
            }
        )
        dataset_records.append(
            dataset_record(
                sample_id,
                comments[sample_id],
                map_row,
                evidence,
                sample_kind,
                analysis_eligible,
                exclusion_reason,
            )
        )

    if not packet_samples:
        raise StageSToolingError("no samples selected for Stage-V packet")

    packet_samples.sort(key=lambda item: item["sample_id"])
    dataset_records.sort(key=lambda item: item["sample_id"])
    blinded = output_dir / "blinded"
    blinded.mkdir(parents=True)
    screenings_dir = blinded / "adjudicated_screenings"
    screenings_dir.mkdir()
    for screening_path in screenings:
        screening = _load_screening(screening_path)
        sample_id = screening["sample_id"]
        if sample_ids is not None and sample_id not in sample_ids:
            continue
        write_new_json(screenings_dir / f"{sample_id}.json", screening)
    dataset_manifest = {
        "schema_version": "eviscope.dataset-manifest.v0.1",
        "dataset_id": selection_id,
        "description": "Stage-V evidence catalog generated from adjudicated Stage-S claims.",
        "records": dataset_records,
    }
    dataset_path = blinded / "dataset_manifest.json"
    write_new_json(dataset_path, dataset_manifest)
    packet = {
        "schema_version": "eviscope.stage-v-input-packet.v0.1",
        "selection_id": selection_id,
        "status": status,
        "guide_version": "v0.3",
        "dataset_manifest_sha256": sha256_path(dataset_path),
        "sample_count": len(packet_samples),
        "samples": packet_samples,
    }
    packet_path = blinded / "stage_v_inputs.json"
    write_new_json(packet_path, packet)
    receipt = {
        "schema_version": "eviscope.stage-v-prepare-receipt.v0.1",
        "selection_id": selection_id,
        "sample_count": len(packet_samples),
        "dataset_manifest_sha256": sha256_path(dataset_path),
        "stage_v_inputs_sha256": sha256_path(packet_path),
    }
    write_new_json(output_dir / "prepare_receipt.json", receipt)
    return {
        "dataset_manifest": sha256_path(dataset_path),
        "stage_v_inputs": sha256_path(packet_path),
        "sample_count": str(len(packet_samples)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adjudicated-records-dir", required=True, type=Path)
    parser.add_argument("--comment-texts", required=True, type=Path)
    parser.add_argument("--sample-map", required=True, type=Path)
    parser.add_argument("--pr-candidates-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--selection-id", required=True)
    parser.add_argument("--status", default="training_not_gold")
    parser.add_argument("--repository-id", help="Default repository_id when absent from sample map")
    parser.add_argument("--review-head-sha", help="Default review_head_sha when absent from sample map")
    parser.add_argument("--sample-kind", default="stage_v_calibration")
    parser.add_argument("--sample-id", action="append", help="Include only these sample IDs")
    parser.add_argument("--analysis-eligible", action="store_true")
    parser.add_argument("--exclusion-reason", default="Stage-V calibration/training packet")
    args = parser.parse_args()
    try:
        result = prepare(
            args.adjudicated_records_dir,
            args.comment_texts,
            args.sample_map,
            args.pr_candidates_root,
            args.output_dir,
            args.selection_id,
            args.status,
            args.repository_id,
            args.review_head_sha,
            args.sample_kind,
            args.analysis_eligible,
            None if args.analysis_eligible else args.exclusion_reason,
            set(args.sample_id) if args.sample_id else None,
        )
    except (StageSToolingError, StageVEvidenceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
