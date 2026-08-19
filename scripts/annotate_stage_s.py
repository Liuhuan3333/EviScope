#!/usr/bin/env python3
"""Offline CLI for blinded Stage-S human annotation under guide v0.3."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eviscope_validation import NON_MATERIAL_REASONS  # noqa: E402
from stage_s_annotation import (  # noqa: E402
    StageSAnnotationError,
    export_session,
    make_material_record,
    make_non_material_record,
    open_session,
    store_record,
)


def _positive_integer(prompt: str) -> int:
    while True:
        value = input(prompt).strip()
        if value.isdigit() and int(value) > 0:
            return int(value)
        print("Enter a positive integer.")


def _exact_fragment() -> str:
    print("Paste one exact source fragment. Finish with a line containing only <<<END>>>.")
    lines = []
    while True:
        line = input()
        if line == "<<<END>>>":
            break
        lines.append(line)
    return "\n".join(lines)


def _material_claims() -> list[dict[str, object]]:
    claims = []
    for claim_number in range(1, _positive_integer("Number of atomic claims: ") + 1):
        normalized = input(f"Claim {claim_number} normalized text: ").strip()
        fragments = []
        for _ in range(_positive_integer(f"Claim {claim_number} fragment count: ")):
            fragments.append({"text": _exact_fragment()})
        claims.append({"normalized_text": normalized, "source_fragments": fragments})
    return claims


def _non_material_reason() -> str:
    reasons = sorted(NON_MATERIAL_REASONS)
    for index, reason in enumerate(reasons, start=1):
        print(f"  {index}. {reason}")
    while True:
        value = input("Reason number: ").strip()
        if value.isdigit() and 1 <= int(value) <= len(reasons):
            return reasons[int(value) - 1]
        print("Choose one registered reason number.")


def _annotate_one(packet, checkpoint, output_dir: Path, sample_id: str) -> bool:
    comments = {sample["sample_id"]: sample["comment_text"] for sample in packet["samples"]}
    print("\n" + "=" * 72)
    print(sample_id)
    print("-" * 72)
    print(comments[sample_id])
    print("=" * 72)
    while True:
        decision = input("Decision [M]ATERIAL/[N]ON_MATERIAL/[Q]uit: ").strip().upper()
        if decision == "Q":
            return False
        try:
            if decision == "M":
                record = make_material_record(
                    packet, checkpoint, sample_id, comments[sample_id], _material_claims()
                )
            elif decision == "N":
                record = make_non_material_record(
                    packet, checkpoint, sample_id, _non_material_reason()
                )
            else:
                print("Enter M, N, or Q.")
                continue
            store_record(packet, checkpoint, output_dir, sample_id, record)
            return True
        except StageSAnnotationError as exc:
            print(f"Record rejected: {exc}")
            print("Re-enter this sample; no invalid record was saved.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--annotator-private-id", required=True)
    parser.add_argument(
        "--round", required=True, choices=("independent_a", "independent_b", "adjudication")
    )
    parser.add_argument("--redo", help="Re-enter one sample before export")
    parser.add_argument("--export-only", action="store_true")
    args = parser.parse_args()
    try:
        packet, checkpoint = open_session(
            args.inputs, args.output_dir, args.annotator_private_id, args.round
        )
        sample_order = [sample["sample_id"] for sample in packet["samples"]]
        if args.export_only:
            hashes = export_session(packet, checkpoint, args.output_dir)
            print(json.dumps({"record_count": len(hashes), "status": "frozen"}, indent=2))
            return 0
        if args.redo:
            if args.redo not in sample_order:
                raise StageSAnnotationError(f"unknown --redo sample: {args.redo}")
            targets = [args.redo]
        else:
            targets = [sample_id for sample_id in sample_order if sample_id not in checkpoint["records"]]
        for sample_id in targets:
            completed = len(checkpoint["records"])
            print(f"\nProgress: {completed}/{len(sample_order)}")
            if not _annotate_one(packet, checkpoint, args.output_dir, sample_id):
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
    except StageSAnnotationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
