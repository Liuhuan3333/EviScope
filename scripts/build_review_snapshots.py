#!/usr/bin/env python3
"""Build immutable L0 snapshots at each inline comment's original commit."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


SHA = re.compile(r"^[0-9a-f]{40}$")


class SnapshotError(RuntimeError):
    pass


def git(repo: Path, *args: str, binary: bool = False) -> bytes | str:
    command = [
        "git",
        "-c",
        "core.pager=cat",
        "-c",
        "pager.diff=false",
        "-C",
        str(repo),
        *args,
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=not binary,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SnapshotError(f"Git command failed: {args[0]}: {exc}") from exc
    if result.returncode:
        stderr = result.stderr.decode("utf-8", "replace") if binary else result.stderr
        raise SnapshotError(f"Git command failed: {args[0]}: {stderr.strip()}")
    return result.stdout


def require_commit(repo: Path, sha: str, label: str) -> None:
    if not SHA.fullmatch(sha):
        raise SnapshotError(f"{label} is not a lowercase 40-character SHA: {sha!r}")
    git(repo, "cat-file", "-e", f"{sha}^{{commit}}")


def load_comment_groups(path: Path) -> dict[str, list[dict[str, object]]]:
    try:
        comments = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"Cannot read comments JSON: {exc}") from exc
    if not isinstance(comments, list) or not comments:
        raise SnapshotError("Comments JSON must be a non-empty list")

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for index, comment in enumerate(comments):
        if not isinstance(comment, dict):
            raise SnapshotError(f"Comment {index} is not an object")
        sha = comment.get("original_commit_id")
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            raise SnapshotError(f"Comment {index} has no valid original_commit_id")
        if not isinstance(comment.get("id"), int):
            raise SnapshotError(f"Comment {index} has no integer id")
        if not isinstance(comment.get("created_at"), str) or not comment["created_at"]:
            raise SnapshotError(f"Comment {index} has no created_at timestamp")
        grouped[sha].append(comment)
    return dict(sorted(grouped.items()))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(repository: Path, comments_path: Path, final_base: str, output: Path) -> dict[str, object]:
    if git(repository, "rev-parse", "--is-inside-work-tree").strip() != "true":
        raise SnapshotError("Repository is not a Git work tree")
    require_commit(repository, final_base, "final base")
    groups = load_comment_groups(comments_path)

    records: list[dict[str, object]] = []
    for review_head, comments in groups.items():
        require_commit(repository, review_head, "review head")
        merge_base = git(repository, "merge-base", final_base, review_head).strip()
        require_commit(repository, merge_base, "merge base")

        diff = git(
            repository,
            "diff",
            "--binary",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            merge_base,
            review_head,
            binary=True,
        )
        assert isinstance(diff, bytes)
        names = git(
            repository,
            "diff",
            "--name-only",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            "-z",
            merge_base,
            review_head,
            binary=True,
        )
        assert isinstance(names, bytes)
        changed_files = [item.decode("utf-8", "surrogateescape") for item in names.split(b"\0") if item]
        if not diff or not changed_files:
            raise SnapshotError(f"Empty L0 snapshot for review head {review_head}")

        snapshot_dir = output / review_head
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        diff_path = snapshot_dir / "L0.diff"
        metadata_path = snapshot_dir / "metadata.json"
        if diff_path.exists() or metadata_path.exists():
            raise SnapshotError(f"Refusing to overwrite existing snapshot: {snapshot_dir}")
        diff_path.write_bytes(diff)

        metadata = {
            "schema_version": "eviscope.review-snapshot.v0.1",
            "final_base_sha": final_base,
            "merge_base_sha": merge_base,
            "review_head_sha": review_head,
            "diff_mode": "git-diff-binary-no-renames-no-ext-diff-no-textconv",
            "changed_file_count": len(changed_files),
            "changed_files": changed_files,
            "l0_sha256": sha256(diff),
            "comments": [
                {
                    "comment_id": comment["id"],
                    "created_at": comment["created_at"],
                    "path": comment.get("path"),
                }
                for comment in sorted(comments, key=lambda item: (str(item["created_at"]), int(item["id"])))
            ],
        }
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        records.append(metadata)

    manifest = {
        "schema_version": "eviscope.review-snapshot-manifest.v0.1",
        "comment_source_sha256": sha256(comments_path.read_bytes()),
        "snapshot_count": len(records),
        "comment_count": sum(len(record["comments"]) for record in records),
        "snapshots": records,
    }
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        raise SnapshotError(f"Refusing to overwrite existing manifest: {manifest_path}")
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--comments", required=True, type=Path)
    parser.add_argument("--final-base", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = build(args.repository, args.comments, args.final_base, args.output)
    except SnapshotError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "snapshot_count": manifest["snapshot_count"],
        "comment_count": manifest["comment_count"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
