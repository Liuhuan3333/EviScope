#!/usr/bin/env python3
"""Build immutable L1 evidence from a frozen L0 review-time snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from l1_evidence import L1EvidenceError, build  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--snapshot-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--comments", type=Path, help="Inline comments JSON providing original_line and side")
    parser.add_argument("--comment-id", type=int, help="Build L1 only for one snapshot comment")
    parser.add_argument(
        "--all-changed-files",
        action="store_true",
        help="Include every changed file, not only comment-anchored paths",
    )
    args = parser.parse_args()
    try:
        package = build(
            args.repository,
            args.snapshot_dir,
            args.output,
            comments_path=args.comments,
            comment_id=args.comment_id,
            all_changed_files=args.all_changed_files,
        )
    except L1EvidenceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "artifact_count": package["artifact_count"],
                "file_count": package["file_count"],
                "comment_count": package["comment_count"],
                "available": sum(1 for item in package["artifacts"] if item["available"]),
                "status": package["status"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
