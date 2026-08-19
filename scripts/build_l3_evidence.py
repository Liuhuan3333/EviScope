#!/usr/bin/env python3
"""Build immutable L3 evidence from a frozen L2 package and raw PR dump."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from l3_evidence import L3EvidenceError, build  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--snapshot-dir", required=True, type=Path)
    parser.add_argument("--l2-dir", required=True, type=Path)
    parser.add_argument("--comments", required=True, type=Path)
    parser.add_argument("--comment-id", required=True, type=int)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        package = build(
            args.repository,
            args.snapshot_dir,
            args.l2_dir,
            args.comments,
            args.comment_id,
            args.raw_dir,
            args.output,
        )
    except L3EvidenceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "artifact_count": package["artifact_count"],
                "available": sum(1 for item in package["artifacts"] if item["available"]),
                "status": package["status"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
