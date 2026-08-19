"""Dependency-free support for offline Stage-V verdict annotation."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eviscope_validation import VERDICTS, validate_annotation_v0_3
from stage_s_tools import StageSToolingError, load_json, sha256_path, write_new_json


class StageVAnnotationError(StageSToolingError):
    pass


PRIVATE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
ROUNDS = {"independent_a", "independent_b", "reverse_audit", "adjudication"}
LEVELS = ("L0", "L1", "L2", "L3")
CONFIDENCE = {"high", "medium", "low"}
PACKET_FIELDS = {
    "schema_version",
    "selection_id",
    "status",
    "guide_version",
    "dataset_manifest_sha256",
    "sample_count",
    "samples",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_stage_v_packet(path: Path) -> dict[str, Any]:
    packet = load_json(path)
    if not isinstance(packet, dict):
        raise StageVAnnotationError("Stage-V packet must be an object")
    extras = set(packet) - PACKET_FIELDS
    if extras:
        raise StageVAnnotationError(f"packet contains forbidden fields: {', '.join(sorted(extras))}")
    if packet.get("schema_version") != "eviscope.stage-v-input-packet.v0.1":
        raise StageVAnnotationError("unsupported Stage-V packet schema")
    if packet.get("guide_version") != "v0.3":
        raise StageVAnnotationError("packet must identify guide v0.3")
    status = packet.get("status")
    if not isinstance(status, str) or not status.endswith("not_gold"):
        raise StageVAnnotationError("packet status must explicitly end in not_gold")
    digest = packet.get("dataset_manifest_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise StageVAnnotationError("dataset_manifest_sha256 must be a SHA-256 digest")
    samples = packet.get("samples")
    if not isinstance(samples, list) or not samples:
        raise StageVAnnotationError("packet must contain samples")
    if packet.get("sample_count") != len(samples):
        raise StageVAnnotationError("sample_count does not match samples")
    seen: set[str] = set()
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise StageVAnnotationError(f"sample {index} must be an object")
        required = {
            "sample_id",
            "screening_id",
            "screening_sha256",
            "comment_text",
            "claims",
            "evidence_levels",
            "known_artifact_ids",
        }
        missing = required - set(sample)
        if missing:
            raise StageVAnnotationError(f"sample {index} missing fields: {', '.join(sorted(missing))}")
        sample_id = sample["sample_id"]
        if not isinstance(sample_id, str) or not PRIVATE_ID.fullmatch(sample_id):
            raise StageVAnnotationError(f"sample {index} has invalid sample_id")
        if sample_id in seen:
            raise StageVAnnotationError(f"duplicate sample_id: {sample_id}")
        seen.add(sample_id)
        claims = sample.get("claims")
        if not isinstance(claims, list) or not claims:
            raise StageVAnnotationError(f"sample {sample_id} must contain claims")
        claim_ids: list[str] = []
        for claim_index, claim in enumerate(claims):
            if not isinstance(claim, dict):
                raise StageVAnnotationError(f"sample {sample_id} claim {claim_index} must be an object")
            for field in ("claim_id", "normalized_text", "source_fragments"):
                if field not in claim:
                    raise StageVAnnotationError(f"sample {sample_id} claim {claim_index} missing {field}")
            claim_ids.append(claim["claim_id"])
        if len(claim_ids) != len(set(claim_ids)):
            raise StageVAnnotationError(f"sample {sample_id} has duplicate claim_id values")
        evidence_levels = sample.get("evidence_levels")
        if not isinstance(evidence_levels, dict) or "L0" not in evidence_levels:
            raise StageVAnnotationError(f"sample {sample_id} must expose L0 evidence")
        known = sample.get("known_artifact_ids")
        if not isinstance(known, dict):
            raise StageVAnnotationError(f"sample {sample_id} known_artifact_ids must be an object")
        for level, artifact_ids in known.items():
            if level not in LEVELS or not isinstance(artifact_ids, list):
                raise StageVAnnotationError(f"sample {sample_id} has invalid known_artifact_ids")
    return packet


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if temporary.exists():
        raise StageVAnnotationError(f"temporary path exists: {temporary}")
    try:
        temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise StageVAnnotationError(f"cannot save checkpoint: {exc}") from exc


def open_session(
    inputs_path: Path,
    output_dir: Path,
    annotator_private_id: str,
    annotation_round: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not PRIVATE_ID.fullmatch(annotator_private_id):
        raise StageVAnnotationError("annotator_private_id contains unsupported characters")
    if annotation_round not in ROUNDS:
        raise StageVAnnotationError("unknown Stage-V annotation round")
    packet = load_stage_v_packet(inputs_path)
    checkpoint_path = output_dir / "checkpoint.json"
    input_hash = sha256_path(inputs_path)
    expected = {
        "input_sha256": input_hash,
        "selection_id": packet["selection_id"],
        "dataset_manifest_sha256": packet["dataset_manifest_sha256"],
        "annotator_private_id": annotator_private_id,
        "annotation_round": annotation_round,
    }
    if checkpoint_path.exists():
        checkpoint = load_json(checkpoint_path)
        if not isinstance(checkpoint, dict):
            raise StageVAnnotationError("checkpoint must be an object")
        for field, value in expected.items():
            if checkpoint.get(field) != value:
                raise StageVAnnotationError(f"checkpoint {field} does not match session")
        if checkpoint.get("status") not in {"in_progress", "frozen"}:
            raise StageVAnnotationError("checkpoint has unknown status")
        if not isinstance(checkpoint.get("records"), dict):
            raise StageVAnnotationError("checkpoint records must be an object")
    else:
        if output_dir.exists() and any(output_dir.iterdir()):
            raise StageVAnnotationError("new output directory must be empty")
        checkpoint = {
            "schema_version": "eviscope.stage-v-checkpoint.v0.1",
            "status": "in_progress",
            **expected,
            "records": {},
            "updated_at": _now(),
        }
        save_checkpoint(output_dir, checkpoint)
    sample_ids = {sample["sample_id"] for sample in packet["samples"]}
    if any(sample_id not in sample_ids for sample_id in checkpoint["records"]):
        raise StageVAnnotationError("checkpoint contains sample outside input packet")
    return packet, checkpoint


def save_checkpoint(output_dir: Path, checkpoint: dict[str, Any]) -> None:
    checkpoint["updated_at"] = _now()
    _atomic_json(output_dir / "checkpoint.json", checkpoint)


def finalize_claim_verdict(judgments: list[dict[str, Any]]) -> tuple[str, str | None]:
    if not judgments:
        raise StageVAnnotationError("claim requires at least one judgment")
    expected_levels = list(LEVELS[: len(judgments)])
    seen_levels = [item.get("level") for item in judgments]
    if seen_levels != expected_levels:
        raise StageVAnnotationError("judgments must follow progressive L0-L3 prefix")
    for judgment in judgments:
        if judgment.get("verdict") not in VERDICTS:
            raise StageVAnnotationError("unknown verdict")
    for judgment in judgments:
        verdict = judgment["verdict"]
        if verdict in {"SUPPORTED", "CONTRADICTED"}:
            if not judgment.get("evidence_ids"):
                raise StageVAnnotationError("decisive verdict requires evidence_ids")
            return verdict, judgment["level"]
    if len(judgments) == len(LEVELS) and all(item["verdict"] == "INSUFFICIENT" for item in judgments):
        return "INSUFFICIENT", None
    if judgments[-1]["verdict"] != "INSUFFICIENT":
        raise StageVAnnotationError("must stop after first decisive verdict")
    return "INSUFFICIENT", None


def build_annotation_record(
    sample: dict[str, Any],
    annotator_private_id: str,
    annotation_round: str,
    claim_results: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(claim_results) != len(sample["claims"]):
        raise StageVAnnotationError("claim result count does not match frozen claims")
    claims_out: list[dict[str, Any]] = []
    for frozen, result in zip(sample["claims"], claim_results, strict=True):
        if frozen["claim_id"] != result["claim_id"]:
            raise StageVAnnotationError("claim_id order must match frozen Stage-S claims")
        final_verdict, minimum_level = finalize_claim_verdict(result["judgments"])
        claims_out.append(
            {
                "claim_id": frozen["claim_id"],
                "judgments": result["judgments"],
                "final_verdict": final_verdict,
                "minimum_evidence_level": minimum_level,
                "issue_type": result.get("issue_type"),
                "disagreement_codes": result.get("disagreement_codes") or [],
                "adjudication_note": result.get("adjudication_note"),
            }
        )
    return {
        "schema_version": "eviscope.annotation.v0.3",
        "sample_id": sample["sample_id"],
        "screening_id": sample["screening_id"],
        "screening_sha256": sample["screening_sha256"],
        "annotator_private_id": annotator_private_id,
        "annotation_round": annotation_round,
        "claims": claims_out,
        "completed_at": _now(),
        "guide_version": "v0.3",
    }


def validate_annotation_record(record: dict[str, Any], sample: dict[str, Any]) -> None:
    known_by_level = sample.get("known_artifact_ids", {})
    for claim in record.get("claims", []):
        if not isinstance(claim, dict):
            continue
        for judgment in claim.get("judgments", []):
            if not isinstance(judgment, dict):
                continue
            level = judgment.get("level")
            allowed = set(known_by_level.get(level, []))
            for artifact_id in judgment.get("evidence_ids", []):
                if artifact_id not in allowed:
                    raise StageVAnnotationError(
                        f"unknown or future-level artifact_id {artifact_id!r} at {level}"
                    )
    issues = validate_annotation_v0_3(Path(f"{record.get('sample_id', 'unknown')}.json"), record)
    if issues:
        raise StageVAnnotationError("invalid Stage-V record: " + "; ".join(map(str, issues)))


def store_record(
    packet: dict[str, Any],
    checkpoint: dict[str, Any],
    output_dir: Path,
    sample_id: str,
    record: dict[str, Any],
) -> None:
    if checkpoint.get("status") != "in_progress" or (output_dir / "frozen_export").exists():
        raise StageVAnnotationError("session is frozen")
    sample = next(item for item in packet["samples"] if item["sample_id"] == sample_id)
    if record.get("sample_id") != sample_id:
        raise StageVAnnotationError("record sample does not match packet")
    validate_annotation_record(record, sample)
    checkpoint["records"][sample_id] = record
    save_checkpoint(output_dir, checkpoint)


def export_session(
    packet: dict[str, Any], checkpoint: dict[str, Any], output_dir: Path
) -> dict[str, str]:
    export_dir = output_dir / "frozen_export"
    if checkpoint.get("status") != "in_progress" or export_dir.exists():
        raise StageVAnnotationError("export already exists or session is frozen")
    order = [sample["sample_id"] for sample in packet["samples"]]
    missing = [sample_id for sample_id in order if sample_id not in checkpoint["records"]]
    if missing:
        raise StageVAnnotationError(f"cannot export; {len(missing)} samples are incomplete")
    samples = {sample["sample_id"]: sample for sample in packet["samples"]}
    output_dir.mkdir(parents=True, exist_ok=True)
    import shutil
    import tempfile

    temporary = Path(tempfile.mkdtemp(prefix=".stage-v-export.", dir=output_dir))
    try:
        records_dir = temporary / "records"
        records_dir.mkdir()
        hashes: dict[str, str] = {}
        for sample_id in order:
            record = checkpoint["records"][sample_id]
            validate_annotation_record(record, samples[sample_id])
            record_path = records_dir / f"{sample_id}.json"
            write_new_json(record_path, record)
            hashes[f"records/{sample_id}.json"] = sha256_path(record_path)
        write_new_json(
            temporary / "manifest.json",
            {
                "schema_version": "eviscope.stage-v-export-manifest.v0.1",
                "status": "human_verdict_not_gold_until_adjudicated",
                "selection_id": packet["selection_id"],
                "input_sha256": checkpoint["input_sha256"],
                "dataset_manifest_sha256": checkpoint["dataset_manifest_sha256"],
                "annotator_private_id": checkpoint["annotator_private_id"],
                "annotation_round": checkpoint["annotation_round"],
                "record_count": len(hashes),
                "records": hashes,
                "frozen_at": _now(),
            },
        )
        temporary.rename(export_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    checkpoint["status"] = "frozen"
    checkpoint["export_manifest_sha256"] = sha256_path(export_dir / "manifest.json")
    save_checkpoint(output_dir, checkpoint)
    return hashes
