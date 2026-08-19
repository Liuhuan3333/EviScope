#!/usr/bin/env python3
"""Verify frozen files against explicit SHA-256 expectations without writing."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stage_s_tools import StageSToolingError, sha256_path


SHA256 = re.compile(r"^[0-9a-f]{64}$")


def parse_expectation(value: str) -> tuple[str, Path]:
    expected, separator, raw_path = value.partition("=")
    if not separator or SHA256.fullmatch(expected) is None or not raw_path:
        raise argparse.ArgumentTypeError("expected SHA256=PATH")
    return expected, Path(raw_path)


def verify(expectations: list[tuple[str, Path]]) -> list[dict[str, str | bool]]:
    results = []
    for expected, path in expectations:
        observed = sha256_path(path)
        results.append({
            "path": str(path),
            "expected_sha256": expected,
            "observed_sha256": observed,
            "match": observed == expected,
        })
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect", action="append", required=True, type=parse_expectation)
    args = parser.parse_args()
    try:
        results = verify(args.expect)
    except StageSToolingError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    for result in results:
        status = "OK" if result["match"] else "MISMATCH"
        print(f"{status} {result['observed_sha256']} {result['path']}")
    return 0 if all(item["match"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
