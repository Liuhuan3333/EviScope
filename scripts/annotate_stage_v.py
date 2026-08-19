#!/usr/bin/env python3
"""Offline CLI for Stage-V progressive verdict annotation under guide v0.3."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eviscope_validation import VERDICTS  # noqa: E402
from stage_v_annotation import (  # noqa: E402
    StageVAnnotationError,
    build_annotation_record,
    export_session,
    finalize_claim_verdict,
    open_session,
    store_record,
)


def _choice(prompt: str, options: list[str]) -> str:
    lookup = {str(index): value for index, value in enumerate(options, start=1)}
    for index, value in lookup.items():
        print(f"  {index}. {value}")
    while True:
        value = input(prompt).strip()
        if value in lookup:
            return lookup[value]
        if value in options:
            return value
        print("Choose a listed option.")


def _comma_list(prompt: str) -> list[str]:
    raw = input(prompt).strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _judgment(level: str, known_ids: list[str]) -> dict[str, object]:
    print(f"\n--- {level} judgment ---")
    verdict = _choice("Verdict: ", list(VERDICTS))
    evidence_ids: list[str] = []
    if verdict in {"SUPPORTED", "CONTRADICTED"}:
        if known_ids:
            print("Known artifact IDs at this level:")
            for artifact_id in known_ids:
                print(f"  - {artifact_id}")
        evidence_ids = _comma_list("Evidence IDs (comma-separated): ")
    rationale = input("Rationale: ").strip()
    confidence = _choice("Confidence [1=high/2=medium/3=low]: ", ["high", "medium", "low"])
    return {
        "level": level,
        "verdict": verdict,
        "evidence_ids": evidence_ids,
        "rationale": rationale,
        "confidence": confidence,
    }


def _show_evidence(sample: dict[str, object], level: str) -> None:
    blocks = sample["evidence_levels"].get(level, [])
    print(f"\nEvidence package up to {level}:")
    print("-" * 72)
    if not blocks:
        print("(no artifacts at this level)")
        return
    for block in blocks:
        print(block["header"])
        print(block["content"])
        print()


def _annotate_claim(sample: dict[str, object], claim: dict[str, object]) -> dict[str, object]:
    print("\n" + "=" * 72)
    print(f"Claim {claim['claim_id']}")
    print("-" * 72)
    print("Normalized text:")
    print(claim["normalized_text"])
    print("\nSource fragments:")
    for fragment in claim["source_fragments"]:
        print(f"  [{fragment['start']}:{fragment['end']}] {fragment['text']!r}")
    judgments: list[dict[str, object]] = []
    for level in ("L0", "L1", "L2", "L3"):
        if level not in sample["evidence_levels"]:
            break
        _show_evidence(sample, level)
        judgment = _judgment(level, sample["known_artifact_ids"].get(level, []))
        judgments.append(judgment)
        if judgment["verdict"] in {"SUPPORTED", "CONTRADICTED"}:
            break
        if level == "L3":
            break
        next_level = {"L0": "L1", "L1": "L2", "L2": "L3"}[level]
        if next_level not in sample["evidence_levels"]:
            break
        if input(f"Continue to {next_level}? [Y/n]: ").strip().lower() == "n":
            break
    final_verdict, minimum_level = finalize_claim_verdict(judgments)
    print(f"Derived final verdict: {final_verdict}; minimum level: {minimum_level}")
    return {
        "claim_id": claim["claim_id"],
        "judgments": judgments,
        "disagreement_codes": [],
        "issue_type": None,
        "adjudication_note": None,
    }


def _annotate_sample(
    packet,
    checkpoint,
    output_dir: Path,
    sample: dict[str, object],
) -> bool:
    print("\n" + "#" * 72)
    print(f"Sample {sample['sample_id']}")
    print("#" * 72)
    print("Review comment:")
    print(sample["comment_text"])
    if input("Begin this sample? [Y/n/q=quit]: ").strip().lower() == "q":
        return False
    claim_results = [_annotate_claim(sample, claim) for claim in sample["claims"]]
    record = build_annotation_record(
        sample,
        checkpoint["annotator_private_id"],
        checkpoint["annotation_round"],
        claim_results,
    )
    store_record(packet, checkpoint, output_dir, sample["sample_id"], record)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--annotator-private-id", required=True)
    parser.add_argument(
        "--round",
        required=True,
        choices=("independent_a", "independent_b", "reverse_audit", "adjudication"),
    )
    parser.add_argument("--redo", help="Re-enter one sample before export")
    parser.add_argument("--export-only", action="store_true")
    args = parser.parse_args()
    try:
        packet, checkpoint = open_session(
            args.inputs, args.output_dir, args.annotator_private_id, args.round
        )
        sample_order = [sample["sample_id"] for sample in packet["samples"]]
        samples = {sample["sample_id"]: sample for sample in packet["samples"]}
        if args.export_only:
            hashes = export_session(packet, checkpoint, args.output_dir)
            print(json.dumps({"record_count": len(hashes), "status": "frozen"}, indent=2))
            return 0
        if args.redo:
            if args.redo not in sample_order:
                raise StageVAnnotationError(f"unknown --redo sample: {args.redo}")
            targets = [args.redo]
        else:
            targets = [sample_id for sample_id in sample_order if sample_id not in checkpoint["records"]]
        for sample_id in targets:
            completed = len(checkpoint["records"])
            print(f"\nProgress: {completed}/{len(sample_order)}")
            if not _annotate_sample(packet, checkpoint, args.output_dir, samples[sample_id]):
                print("Checkpoint saved. No export was created.")
                return 0
        remaining = [sample_id for sample_id in sample_order if sample_id not in checkpoint["records"]]
        if remaining:
            print(f"Checkpoint saved; {len(remaining)} samples remain.")
            return 0
        if input("All samples complete. Freeze export now? [y/N]: ").strip().lower() == "y":
            hashes = export_session(packet, checkpoint, args.output_dir)
            print(json.dumps({"record_count": len(hashes), "status": "frozen"}, indent=2))
        else:
            print("Complete checkpoint saved; run again with --export-only to freeze.")
        return 0
    except StageVAnnotationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
