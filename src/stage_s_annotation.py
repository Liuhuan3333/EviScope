"""Dependency-free support for blinded, offline Stage-S annotation."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eviscope_validation import NON_MATERIAL_REASONS, validate_materiality_screening
from stage_s_tools import (
    StageSToolingError,
    align_verbatim_fragments,
    load_json,
    sha256_path,
    write_new_json,
)


class StageSAnnotationError(StageSToolingError):
    pass


PRIVATE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
ROUNDS = {"independent_a", "independent_b", "adjudication"}
PACKET_FIELDS = {
    "schema_version", "selection_id", "status", "guide_version",
    "evidence_visible", "sample_count", "samples",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_blinded_packet(path: Path) -> dict[str, Any]:
    packet = load_json(path)
    if not isinstance(packet, dict):
        raise StageSAnnotationError("Stage-S packet must be an object")
    extras = set(packet) - PACKET_FIELDS
    if extras:
        raise StageSAnnotationError(f"packet contains forbidden fields: {', '.join(sorted(extras))}")
    if packet.get("schema_version") != "eviscope.stage-s-input-packet.v0.1":
        raise StageSAnnotationError("unsupported Stage-S packet schema")
    if packet.get("guide_version") != "v0.3":
        raise StageSAnnotationError("packet must identify guide v0.3")
    if packet.get("evidence_visible") is not False:
        raise StageSAnnotationError("packet must explicitly hide evidence")
    status = packet.get("status")
    if not isinstance(status, str) or not status.endswith("not_gold"):
        raise StageSAnnotationError("packet status must explicitly end in not_gold")
    if not isinstance(packet.get("selection_id"), str) or not packet["selection_id"]:
        raise StageSAnnotationError("selection_id must be non-empty")
    samples = packet.get("samples")
    if not isinstance(samples, list) or not samples:
        raise StageSAnnotationError("packet must contain samples")
    if packet.get("sample_count") != len(samples):
        raise StageSAnnotationError("sample_count does not match samples")
    seen: set[str] = set()
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict) or set(sample) != {"sample_id", "comment_text"}:
            raise StageSAnnotationError(
                f"sample {index} must contain only sample_id and comment_text"
            )
        sample_id, comment = sample["sample_id"], sample["comment_text"]
        if not isinstance(sample_id, str) or not PRIVATE_ID.fullmatch(sample_id):
            raise StageSAnnotationError(f"sample {index} has invalid sample_id")
        if sample_id in seen:
            raise StageSAnnotationError(f"duplicate sample_id: {sample_id}")
        if not isinstance(comment, str) or not comment:
            raise StageSAnnotationError(f"sample {sample_id} has empty comment_text")
        seen.add(sample_id)
    return packet


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if temporary.exists():
        raise StageSAnnotationError(f"temporary path exists: {temporary}")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        temporary.replace(path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise StageSAnnotationError(f"cannot save checkpoint: {exc}") from exc


def open_session(
    inputs_path: Path,
    output_dir: Path,
    annotator_private_id: str,
    annotation_round: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not PRIVATE_ID.fullmatch(annotator_private_id):
        raise StageSAnnotationError("annotator_private_id contains unsupported characters")
    if annotation_round not in ROUNDS:
        raise StageSAnnotationError("unknown Stage-S annotation round")
    packet = load_blinded_packet(inputs_path)
    checkpoint_path = output_dir / "checkpoint.json"
    input_hash = sha256_path(inputs_path)
    expected = {
        "input_sha256": input_hash,
        "selection_id": packet["selection_id"],
        "annotator_private_id": annotator_private_id,
        "annotation_round": annotation_round,
    }
    if checkpoint_path.exists():
        checkpoint = load_json(checkpoint_path)
        if not isinstance(checkpoint, dict):
            raise StageSAnnotationError("checkpoint must be an object")
        for field, value in expected.items():
            if checkpoint.get(field) != value:
                raise StageSAnnotationError(f"checkpoint {field} does not match session")
        if checkpoint.get("status") not in {"in_progress", "frozen"}:
            raise StageSAnnotationError("checkpoint has unknown status")
        if not isinstance(checkpoint.get("records"), dict):
            raise StageSAnnotationError("checkpoint records must be an object")
    else:
        if output_dir.exists() and any(output_dir.iterdir()):
            raise StageSAnnotationError("new output directory must be empty")
        checkpoint = {
            "schema_version": "eviscope.stage-s-checkpoint.v0.1",
            "status": "in_progress",
            **expected,
            "records": {},
            "updated_at": _now(),
        }
        save_checkpoint(output_dir, checkpoint)
    sample_ids = {sample["sample_id"] for sample in packet["samples"]}
    if any(sample_id not in sample_ids for sample_id in checkpoint["records"]):
        raise StageSAnnotationError("checkpoint contains sample outside input packet")
    return packet, checkpoint


def save_checkpoint(output_dir: Path, checkpoint: dict[str, Any]) -> None:
    checkpoint["updated_at"] = _now()
    _atomic_json(output_dir / "checkpoint.json", checkpoint)


def _base_record(
    packet: dict[str, Any], checkpoint: dict[str, Any], sample_id: str
) -> dict[str, Any]:
    return {
        "schema_version": "eviscope.materiality-screening.v0.3",
        "screening_id": (
            f"{packet['selection_id']}:{sample_id}:{checkpoint['annotation_round']}"
        ),
        "sample_id": sample_id,
        "annotator_private_id": checkpoint["annotator_private_id"],
        "annotation_round": checkpoint["annotation_round"],
        "completed_at": _now(),
        "guide_version": "v0.3",
    }


def make_non_material_record(
    packet: dict[str, Any], checkpoint: dict[str, Any], sample_id: str, reason: str
) -> dict[str, Any]:
    if reason not in NON_MATERIAL_REASONS:
        raise StageSAnnotationError("reason is not registered in guide v0.3")
    record = _base_record(packet, checkpoint, sample_id)
    record.update({"decision": "NON_MATERIAL", "non_material_reason": reason, "claims": []})
    return record


def make_material_record(
    packet: dict[str, Any],
    checkpoint: dict[str, Any],
    sample_id: str,
    comment: str,
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    if not claims:
        raise StageSAnnotationError("MATERIAL record requires at least one claim")
    aligned = []
    for index, claim in enumerate(claims, start=1):
        normalized = claim.get("normalized_text") if isinstance(claim, dict) else None
        fragments = claim.get("source_fragments") if isinstance(claim, dict) else None
        if not isinstance(normalized, str) or not normalized:
            raise StageSAnnotationError(f"claim {index} requires normalized_text")
        if not isinstance(fragments, list):
            raise StageSAnnotationError(f"claim {index} requires source_fragments")
        try:
            aligned_fragments = align_verbatim_fragments(comment, fragments)
        except StageSToolingError as exc:
            raise StageSAnnotationError(
                f"claim {index} fragment alignment failed: {exc}"
            ) from exc
        aligned.append({
            "claim_id": f"claim-{index}",
            "normalized_text": normalized,
            "source_fragments": aligned_fragments,
        })
    record = _base_record(packet, checkpoint, sample_id)
    record.update({"decision": "MATERIAL", "non_material_reason": None, "claims": aligned})
    return record


def validate_record(record: dict[str, Any], comment: str) -> None:
    issues: list[Any] = list(
        validate_materiality_screening(Path(f"{record.get('sample_id', 'unknown')}.json"), record)
    )
    for claim_index, claim in enumerate(record.get("claims", [])):
        for fragment_index, fragment in enumerate(claim.get("source_fragments", [])):
            start, end, text = fragment["start"], fragment["end"], fragment["text"]
            if end > len(comment) or comment[start:end] != text:
                issues.append(
                    f"claims[{claim_index}].source_fragments[{fragment_index}] does not match comment"
                )
    if issues:
        raise StageSAnnotationError("invalid Stage-S record: " + "; ".join(map(str, issues)))


def store_record(
    packet: dict[str, Any], checkpoint: dict[str, Any], output_dir: Path,
    sample_id: str, record: dict[str, Any]
) -> None:
    if checkpoint.get("status") != "in_progress" or (output_dir / "frozen_export").exists():
        raise StageSAnnotationError("session is frozen")
    comments = {sample["sample_id"]: sample["comment_text"] for sample in packet["samples"]}
    if sample_id not in comments or record.get("sample_id") != sample_id:
        raise StageSAnnotationError("record sample does not match input packet")
    validate_record(record, comments[sample_id])
    checkpoint["records"][sample_id] = record
    save_checkpoint(output_dir, checkpoint)


def export_session(
    packet: dict[str, Any], checkpoint: dict[str, Any], output_dir: Path
) -> dict[str, str]:
    export_dir = output_dir / "frozen_export"
    if checkpoint.get("status") != "in_progress" or export_dir.exists():
        raise StageSAnnotationError("export already exists or session is frozen")
    comments = {sample["sample_id"]: sample["comment_text"] for sample in packet["samples"]}
    order = [sample["sample_id"] for sample in packet["samples"]]
    missing = [sample_id for sample_id in order if sample_id not in checkpoint["records"]]
    if missing:
        raise StageSAnnotationError(f"cannot export; {len(missing)} samples are incomplete")
    for sample_id in order:
        validate_record(checkpoint["records"][sample_id], comments[sample_id])
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".stage-s-export.", dir=output_dir))
    try:
        records_dir = temporary / "records"
        records_dir.mkdir()
        hashes = {}
        for sample_id in order:
            record_path = records_dir / f"{sample_id}.json"
            write_new_json(record_path, checkpoint["records"][sample_id])
            hashes[f"records/{sample_id}.json"] = sha256_path(record_path)
        write_new_json(temporary / "manifest.json", {
            "schema_version": "eviscope.stage-s-export-manifest.v0.1",
            "status": "human_annotation_not_gold_until_adjudicated",
            "selection_id": packet["selection_id"],
            "input_sha256": checkpoint["input_sha256"],
            "annotator_private_id": checkpoint["annotator_private_id"],
            "annotation_round": checkpoint["annotation_round"],
            "record_count": len(hashes),
            "records": hashes,
            "frozen_at": _now(),
        })
        temporary.rename(export_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    checkpoint["status"] = "frozen"
    checkpoint["export_manifest_sha256"] = sha256_path(export_dir / "manifest.json")
    save_checkpoint(output_dir, checkpoint)
    return hashes
