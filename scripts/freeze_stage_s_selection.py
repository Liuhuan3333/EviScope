#!/usr/bin/env python3
"""Freeze a blinded Stage-S selection using content-independent SHA-256 rank."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stage_s_tools import StageSToolingError, canonical_json_bytes, load_json, sha256_path, write_new_json


RULE_ID = "actor-review-state-coverage-then-seeded-sha256-rank.v0.1"
RULE_TEXT = (
    "Select anchored HUMAN_REVIEWER comments per repository; first maximize "
    "reviewer-actor by review-state coverage, then fill by seeded SHA-256 rank; "
    "do not use comment content, materiality, claims, verdicts, or later artifacts."
)


def _rank(seed: str, repository_id: str, comment_id: int) -> str:
    payload = f"{seed}\0{repository_id}\0{comment_id}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_repository(source: dict[str, Any], seed: str, quota: int) -> tuple[list[dict[str, Any]], dict[str, str]]:
    repository_id = source.get("repository_id")
    audit_path = Path(source.get("audit_path", ""))
    comments_path = Path(source.get("comments_path", ""))
    if not isinstance(repository_id, str) or not repository_id:
        raise StageSToolingError("each repository requires repository_id")
    audit = load_json(audit_path)
    comments = load_json(comments_path)
    if not isinstance(audit, dict) or not isinstance(audit.get("records"), list):
        raise StageSToolingError(f"{repository_id}: malformed audit")
    if not isinstance(comments, list):
        raise StageSToolingError(f"{repository_id}: comments must be an array")
    comments_sha = sha256_path(comments_path)
    if audit.get("source_comment_sha256") != comments_sha:
        raise StageSToolingError(f"{repository_id}: audit/comment hash mismatch")
    by_id = {
        item.get("id"): item
        for item in comments
        if isinstance(item, dict) and isinstance(item.get("id"), int)
    }
    candidates = []
    for record in audit["records"]:
        if not isinstance(record, dict):
            raise StageSToolingError(f"{repository_id}: malformed audit record")
        if record.get("role") != "HUMAN_REVIEWER" or record.get("anchor_valid") is not True:
            continue
        comment_id = record.get("comment_id")
        comment = by_id.get(comment_id)
        if not isinstance(comment, dict) or not isinstance(comment.get("body"), str):
            raise StageSToolingError(f"{repository_id}: selected audit record lacks source comment")
        actor = record.get("reviewer_actor_id")
        state = record.get("review_head_sha")
        if not isinstance(actor, str) or not isinstance(state, str):
            raise StageSToolingError(f"{repository_id}: candidate lacks actor or review state")
        candidates.append({
            "rank": _rank(seed, repository_id, comment_id),
            "stratum": (actor, state),
            "record": record,
            "comment_text": comment["body"],
        })
    if len(candidates) < quota:
        raise StageSToolingError(f"{repository_id}: only {len(candidates)} eligible comments for quota {quota}")

    by_stratum: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for candidate in candidates:
        by_stratum.setdefault(candidate["stratum"], []).append(candidate)
    coverage = [min(items, key=lambda item: item["rank"]) for items in by_stratum.values()]
    coverage.sort(key=lambda item: item["rank"])
    selected = coverage[:quota]
    selected_ids = {item["record"]["comment_id"] for item in selected}
    if len(selected) < quota:
        remaining = sorted(
            (item for item in candidates if item["record"]["comment_id"] not in selected_ids),
            key=lambda item: item["rank"],
        )
        selected.extend(remaining[: quota - len(selected)])
    selected.sort(key=lambda item: item["rank"])
    return selected, {"audit_sha256": sha256_path(audit_path), "comments_sha256": comments_sha}


def freeze(config_path: Path, output: Path) -> dict[str, str]:
    if output.exists():
        raise StageSToolingError(f"Refusing to use pre-existing output directory: {output}")
    config = load_json(config_path)
    if not isinstance(config, dict):
        raise StageSToolingError("selection config must be an object")
    required = ("selection_id", "seed", "guide_version", "generated_at", "per_repository", "repositories")
    missing = [field for field in required if field not in config]
    if missing:
        raise StageSToolingError(f"selection config missing fields: {', '.join(missing)}")
    selection_id = config["selection_id"]
    seed = config["seed"]
    guide_version = config["guide_version"]
    quota = config["per_repository"]
    sources = config["repositories"]
    if not all(isinstance(value, str) and value for value in (selection_id, seed, guide_version, config["generated_at"])):
        raise StageSToolingError("selection metadata strings must be non-empty")
    if not isinstance(quota, int) or isinstance(quota, bool) or quota < 1:
        raise StageSToolingError("per_repository must be a positive integer")
    if not isinstance(sources, list) or not sources:
        raise StageSToolingError("repositories must be a non-empty array")
    repository_ids = [source.get("repository_id") for source in sources if isinstance(source, dict)]
    if len(repository_ids) != len(sources) or len(set(repository_ids)) != len(repository_ids):
        raise StageSToolingError("repository IDs must be present and unique")

    chosen: list[tuple[str, dict[str, Any]]] = []
    source_hashes = {}
    for source in sources:
        selected, hashes = _load_repository(source, seed, quota)
        repository_id = source["repository_id"]
        source_hashes[repository_id] = hashes
        chosen.extend((repository_id, item) for item in selected)

    stage_samples = []
    private_samples = []
    for number, (repository_id, item) in enumerate(chosen, start=1):
        sample_id = f"S{number:03d}"
        record = item["record"]
        stage_samples.append({"sample_id": sample_id, "comment_text": item["comment_text"]})
        private_samples.append({
            "sample_id": sample_id,
            "repository_id": repository_id,
            "comment_id": record["comment_id"],
            "reviewer_actor_id": record["reviewer_actor_id"],
            "review_head_sha": record["review_head_sha"],
            "merge_base_sha": record["merge_base_sha"],
            "evidence_sha256": record["evidence_sha256"],
            "path": record["path"],
            "anchor_method": record["anchor_method"],
        })

    stage_packet = {
        "schema_version": "eviscope.stage-s-input-packet.v0.1",
        "selection_id": selection_id,
        "status": "pre_gate_candidate_not_gold",
        "guide_version": guide_version,
        "evidence_visible": False,
        "sample_count": len(stage_samples),
        "samples": stage_samples,
    }
    private_map = {
        "schema_version": "eviscope.private-sample-map.v0.1",
        "selection_id": selection_id,
        "sample_count": len(private_samples),
        "samples": private_samples,
    }
    manifest = {
        "schema_version": "eviscope.pilot-selection-candidate.v0.2",
        "selection_id": selection_id,
        "status": "pre_gate_candidate",
        "generated_at": config["generated_at"],
        "selection_seed_sha256": hashlib.sha256(seed.encode("utf-8")).hexdigest(),
        "selection_rule_id": RULE_ID,
        "selection_rule": RULE_TEXT,
        "selection_rule_sha256": hashlib.sha256(RULE_TEXT.encode("utf-8")).hexdigest(),
        "config_sha256": sha256_path(config_path),
        "repository_count": len(sources),
        "sample_count": len(stage_samples),
        "source_audits": source_hashes,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        write_new_json(temporary / "stage_s_inputs.json", stage_packet)
        write_new_json(temporary / "private_sample_map.json", private_map)
        write_new_json(temporary / "selection_manifest.json", manifest)
        receipt = {
            "schema_version": "eviscope.freeze-receipt.v0.1",
            "status": "not_annotation_not_gold",
            "outputs": {
                name: sha256_path(temporary / name)
                for name in ("stage_s_inputs.json", "private_sample_map.json", "selection_manifest.json")
            },
        }
        write_new_json(temporary / "freeze_receipt.json", receipt)
        temporary.rename(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {name: sha256_path(output / name) for name in receipt["outputs"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        hashes = freeze(args.config, args.output)
    except StageSToolingError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(hashes, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
