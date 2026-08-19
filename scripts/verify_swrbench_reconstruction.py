#!/usr/bin/env python3
"""Audit SWR review-time candidates against local Git clones without sampling."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swrbench_reconstruction import SWRReconstructionError, run_verification  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidates",
        type=Path,
        default=ROOT / "data/private/external/swrbench/review-time-v0.1/candidate_inputs.jsonl",
    )
    parser.add_argument(
        "--review-time-manifest",
        type=Path,
        default=ROOT / "data/private/external/swrbench/review-time-v0.1/manifest.json",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=ROOT / "configs/swrbench_review_time_policy_v0.1.json",
    )
    parser.add_argument(
        "--repos-root",
        type=Path,
        default=ROOT / "data/private/external/swrbench/repos",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data/private/external/swrbench/reconstruction-v0.1",
    )
    args = parser.parse_args()
    try:
        manifest = run_verification(
            args.candidates,
            args.review_time_manifest,
            args.policy,
            args.repos_root,
            args.output,
        )
    except SWRReconstructionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(manifest["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
