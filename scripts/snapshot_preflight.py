#!/usr/bin/env python3
"""Read-only preflight for review-time Git snapshots already present locally."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


SHA = re.compile(r"^[0-9a-f]{40}$")


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    argv = ["git", "-C", str(repo), *args]
    try:
        return subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", "git command timed out")
    except OSError as exc:
        return subprocess.CompletedProcess(argv, 127, "", str(exc))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that immutable base/head commits required for snapshot reconstruction exist."
    )
    parser.add_argument("repository", type=Path)
    parser.add_argument("base_sha")
    parser.add_argument("head_sha")
    args = parser.parse_args()

    result = {
        "base_sha": args.base_sha,
        "head_sha": args.head_sha,
        "is_git_repository": False,
        "base_commit_available": False,
        "head_commit_available": False,
        "diff_readable": False,
        "changed_file_count": None,
        "ready": False,
    }
    if (
        not args.repository.is_dir()
        or not SHA.fullmatch(args.base_sha)
        or not SHA.fullmatch(args.head_sha)
        or args.base_sha == args.head_sha
    ):
        print(json.dumps(result, indent=2))
        return 1

    result["is_git_repository"] = git(args.repository, "rev-parse", "--is-inside-work-tree").stdout.strip() == "true"
    if not result["is_git_repository"]:
        print(json.dumps(result, indent=2))
        return 1

    for label, sha in (("base", args.base_sha), ("head", args.head_sha)):
        check = git(args.repository, "cat-file", "-e", f"{sha}^{{commit}}")
        result[f"{label}_commit_available"] = check.returncode == 0

    if result["base_commit_available"] and result["head_commit_available"]:
        # Disable repository-configured external diff/textconv drivers so the
        # preflight remains a read-only Git object inspection even for an
        # untrusted clone.
        diff = git(
            args.repository,
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--name-only",
            args.base_sha,
            args.head_sha,
        )
        result["diff_readable"] = diff.returncode == 0
        if diff.returncode == 0:
            result["changed_file_count"] = len([line for line in diff.stdout.splitlines() if line])
    result["ready"] = all(
        result[key]
        for key in ("is_git_repository", "base_commit_available", "head_commit_available", "diff_readable")
    ) and bool(result["changed_file_count"])
    print(json.dumps(result, indent=2))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
