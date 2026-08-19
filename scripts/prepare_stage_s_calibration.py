#!/usr/bin/env python3
"""Prepare a blinded, non-gold Stage-S calibration packet from one PR."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stage_s_annotation import load_blinded_packet  # noqa: E402
from stage_s_tools import (  # noqa: E402
    StageSToolingError,
    load_json,
    sha256_path,
    write_new_json,
)


RULE_ID = "all-nonauthor-human-inline-comments-by-id.v0.1"
RULE_TEXT = (
    "Include every inline comment whose actor differs from the pull-request "
    "author and whose GitHub actor type is not Bot; order by numeric comment ID."
)


def prepare(
    comments_path: Path,
    pull_path: Path,
    output: Path,
    selection_id: str,
    generated_at: str,
) -> dict[str, str]:
    if output.exists():
        raise StageSToolingError(f"Refusing to use pre-existing output directory: {output}")
    if not selection_id or not generated_at:
        raise StageSToolingError("selection_id and generated_at must be non-empty")

    comments = load_json(comments_path)
    pull = load_json(pull_path)
    if not isinstance(comments, list) or not isinstance(pull, dict):
        raise StageSToolingError("comments must be an array and pull must be an object")
    author = pull.get("user")
    if not isinstance(author, dict) or not isinstance(author.get("id"), int):
        raise StageSToolingError("pull author requires an integer id")

    eligible: list[dict[str, Any]] = []
    seen_comment_ids: set[int] = set()
    for index, comment in enumerate(comments):
        if not isinstance(comment, dict):
            raise StageSToolingError(f"comment {index} must be an object")
        user = comment.get("user")
        if not isinstance(user, dict) or not isinstance(user.get("id"), int):
            raise StageSToolingError(f"comment {index} requires an integer actor id")
        if user["id"] == author["id"] or user.get("type") == "Bot":
            continue
        comment_id, body = comment.get("id"), comment.get("body")
        if not isinstance(comment_id, int) or isinstance(comment_id, bool):
            raise StageSToolingError(f"eligible comment {index} requires an integer id")
        if comment_id in seen_comment_ids:
            raise StageSToolingError(f"duplicate eligible comment id: {comment_id}")
        if not isinstance(body, str) or not body:
            raise StageSToolingError(f"eligible comment {comment_id} has empty body")
        seen_comment_ids.add(comment_id)
        eligible.append(comment)
    eligible.sort(key=lambda item: item["id"])
    if not eligible:
        raise StageSToolingError("no eligible non-author human inline comments")

    samples = []
    private_samples = []
    for number, comment in enumerate(eligible, start=1):
        sample_id = f"M{number:03d}"
        samples.append({"sample_id": sample_id, "comment_text": comment["body"]})
        private_samples.append({"sample_id": sample_id, "comment_id": comment["id"]})

    packet = {
        "schema_version": "eviscope.stage-s-input-packet.v0.1",
        "selection_id": selection_id,
        "status": "training_not_gold",
        "guide_version": "v0.3",
        "evidence_visible": False,
        "sample_count": len(samples),
        "samples": samples,
    }
    private_map = {
        "schema_version": "eviscope.private-calibration-map.v0.1",
        "selection_id": selection_id,
        "status": "coordinator_only_not_annotation_not_gold",
        "sample_count": len(private_samples),
        "samples": private_samples,
    }
    manifest = {
        "schema_version": "eviscope.stage-s-calibration-manifest.v0.1",
        "selection_id": selection_id,
        "status": "training_not_gold",
        "generated_at": generated_at,
        "selection_rule_id": RULE_ID,
        "selection_rule": RULE_TEXT,
        "selection_rule_sha256": hashlib.sha256(RULE_TEXT.encode("utf-8")).hexdigest(),
        "sample_count": len(samples),
        "source_sha256": {
            "inline_comments.json": sha256_path(comments_path),
            "pull.json": sha256_path(pull_path),
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        write_new_json(temporary / "stage_s_inputs.json", packet)
        load_blinded_packet(temporary / "stage_s_inputs.json")
        write_new_json(temporary / "private_sample_map.json", private_map)
        write_new_json(temporary / "calibration_manifest.json", manifest)
        output_names = (
            "stage_s_inputs.json",
            "private_sample_map.json",
            "calibration_manifest.json",
        )
        hashes = {name: sha256_path(temporary / name) for name in output_names}
        write_new_json(temporary / "freeze_receipt.json", {
            "schema_version": "eviscope.freeze-receipt.v0.1",
            "status": "training_not_annotation_not_gold",
            "outputs": hashes,
        })
        temporary.rename(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comments", required=True, type=Path)
    parser.add_argument("--pull", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--selection-id", required=True)
    parser.add_argument("--generated-at", required=True)
    args = parser.parse_args()
    try:
        hashes = prepare(
            args.comments, args.pull, args.output, args.selection_id, args.generated_at
        )
    except StageSToolingError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(hashes, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
