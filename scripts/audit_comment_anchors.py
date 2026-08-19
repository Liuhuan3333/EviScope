#!/usr/bin/env python3
"""Audit inline-comment anchors against immutable review-time L0 snapshots."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stage_s_tools import StageSToolingError, load_json, sha256_bytes, sha256_path, write_new_json


HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
AUDIT_RULE_ID = "review-time-anchor-audit.v0.1"
AUDIT_RULE_TEXT = "EXACT_HUNK, BODY_EXACT, CHANGED_LINES_ORDERED, then locally verified API_LINE_COORDINATE; preserve distinct review heads even when L0 hashes match."


def _ordered_in(haystack: str, needles: list[str]) -> bool:
    cursor = 0
    for needle in needles:
        position = haystack.find(needle, cursor)
        if position < 0:
            return False
        cursor = position + len(needle)
    return True


def _changed_hunk_lines(hunk: str) -> list[str]:
    lines = []
    for line in hunk.splitlines():
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith(("+", "-")) and len(line) > 1:
            lines.append(line[1:])
    return lines


def _line_at_coordinate(diff: str, path: str, side: str, coordinate: int) -> str | None:
    current_path: str | None = None
    old_line: int | None = None
    new_line: int | None = None
    for raw_line in diff.splitlines():
        if raw_line.startswith("+++ "):
            marker = raw_line[4:]
            current_path = marker[2:] if marker.startswith("b/") else marker
            old_line = new_line = None
            continue
        match = HUNK_HEADER.match(raw_line)
        if match:
            old_line, new_line = int(match.group(1)), int(match.group(2))
            continue
        if current_path != path or old_line is None or new_line is None or not raw_line:
            continue
        prefix, text = raw_line[0], raw_line[1:]
        if prefix == " ":
            if side == "LEFT" and old_line == coordinate:
                return text
            if side == "RIGHT" and new_line == coordinate:
                return text
            old_line += 1
            new_line += 1
        elif prefix == "-":
            if side == "LEFT" and old_line == coordinate:
                return text
            old_line += 1
        elif prefix == "+":
            if side == "RIGHT" and new_line == coordinate:
                return text
            new_line += 1
    return None


def _repository_line(repository: Path, review_head: str, path: str, coordinate: int) -> str | None:
    environment = os.environ.copy()
    environment["GIT_NO_LAZY_FETCH"] = "1"
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), "show", f"{review_head}:{path}"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="surrogateescape",
            env=environment,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StageSToolingError(f"Cannot inspect review-time file: {exc}") from exc
    if result.returncode:
        raise StageSToolingError("Review-time file blob is unavailable locally")
    lines = result.stdout.splitlines()
    return lines[coordinate - 1] if coordinate <= len(lines) else None


def _anchor(
    comment: dict[str, Any],
    snapshot: dict[str, Any],
    diff: str,
    repository: Path | None,
) -> tuple[str, bool, str | None]:
    hunk = comment.get("diff_hunk")
    if isinstance(hunk, str) and hunk and hunk in diff:
        return "EXACT_HUNK", True, None
    if isinstance(hunk, str) and hunk:
        hunk_lines = hunk.splitlines()
        hunk_body = "\n".join(hunk_lines[1:]) if hunk_lines and hunk_lines[0].startswith("@@") else hunk
        if hunk_body and hunk_body in diff:
            return "BODY_EXACT", True, None
        changed = _changed_hunk_lines(hunk)
        if changed and _ordered_in(diff, changed):
            return "CHANGED_LINES_ORDERED", True, None
    coordinate = comment.get("original_line") or comment.get("line")
    changed_files = snapshot.get("changed_files", [])
    if (
        (not isinstance(hunk, str) or not hunk)
        and isinstance(coordinate, int)
        and not isinstance(coordinate, bool)
        and coordinate > 0
        and comment.get("path") in changed_files
    ):
        side = comment.get("side")
        line = _line_at_coordinate(diff, comment["path"], side, coordinate)
        if line is None and repository is not None and side == "RIGHT":
            line = _repository_line(repository, snapshot["review_head_sha"], comment["path"], coordinate)
        if line is not None:
            return "API_LINE_COORDINATE", True, sha256_bytes(line.encode("utf-8", "surrogateescape"))
    return "UNANCHORED", False, None

def build_audit(
    comments_path: Path,
    pull_path: Path,
    snapshot_manifest_path: Path,
    snapshots_root: Path,
    repository: Path | None = None,
) -> dict[str, Any]:
    comments = load_json(comments_path)
    pull = load_json(pull_path)
    manifest = load_json(snapshot_manifest_path)
    if not isinstance(comments, list) or not comments:
        raise StageSToolingError("comments must be a non-empty array")
    if not isinstance(pull, dict) or not isinstance(pull.get("user"), dict):
        raise StageSToolingError("pull must contain an author user object")
    author_id = pull["user"].get("id")
    if not isinstance(author_id, int):
        raise StageSToolingError("pull author must have an integer id")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("snapshots"), list):
        raise StageSToolingError("snapshot manifest is malformed")
    if manifest.get("comment_source_sha256") != sha256_path(comments_path):
        raise StageSToolingError("snapshot manifest comment source hash does not match")

    snapshots: dict[str, dict[str, Any]] = {}
    diffs: dict[str, str] = {}
    for snapshot in manifest["snapshots"]:
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("review_head_sha"), str):
            raise StageSToolingError("snapshot manifest contains a malformed record")
        review_head = snapshot["review_head_sha"]
        diff_path = snapshots_root / review_head / "L0.diff"
        if sha256_path(diff_path) != snapshot.get("l0_sha256"):
            raise StageSToolingError(f"L0 hash mismatch for review head {review_head}")
        try:
            diff = diff_path.read_text(encoding="utf-8", errors="surrogateescape")
        except OSError as exc:
            raise StageSToolingError(f"Cannot read L0 diff for {review_head}: {exc}") from exc
        if not diff:
            raise StageSToolingError(f"Empty L0 diff for review head {review_head}")
        snapshots[review_head] = snapshot
        diffs[review_head] = diff

    reviewer_users = {}
    for index, comment in enumerate(comments):
        user = comment.get("user") if isinstance(comment, dict) else None
        if not isinstance(user, dict) or not isinstance(user.get("id"), int):
            raise StageSToolingError(f"comment {index} has no integer user id")
        if user["id"] == author_id or user.get("type") == "Bot":
            continue
        if not isinstance(user.get("login"), str) or not user["login"]:
            raise StageSToolingError(f"comment {index} reviewer has no login for deterministic anonymization")
        reviewer_users[user["id"]] = user
    reviewer_ids = sorted(reviewer_users, key=lambda user_id: reviewer_users[user_id]["login"])
    actor_ids = {user_id: f"R{index:03d}" for index, user_id in enumerate(reviewer_ids, start=1)}

    records = []
    seen_comment_ids: set[int] = set()
    for index, comment in enumerate(comments):
        if not isinstance(comment, dict):
            raise StageSToolingError(f"comment {index} is not an object")
        comment_id = comment.get("id")
        review_head = comment.get("original_commit_id")
        user = comment.get("user")
        if not isinstance(comment_id, int) or comment_id in seen_comment_ids:
            raise StageSToolingError(f"comment {index} has a missing or duplicate integer id")
        if not isinstance(review_head, str) or review_head not in snapshots:
            raise StageSToolingError(f"comment {comment_id} has no matching review-time snapshot")
        if not isinstance(user, dict) or not isinstance(user.get("id"), int):
            raise StageSToolingError(f"comment {comment_id} has no integer user id")
        seen_comment_ids.add(comment_id)
        user_id = user["id"]
        if user_id == author_id:
            role = "AUTHOR_CONTEXT"
            actor_id = None
        elif user.get("type") == "Bot":
            role = "BOT_EXCLUDED"
            actor_id = None
        else:
            role = "HUMAN_REVIEWER"
            actor_id = actor_ids[user_id]
        method, valid, anchor_line_sha256 = _anchor(comment, snapshots[review_head], diffs[review_head], repository)
        record = {
            "comment_id": comment_id,
            "role": role,
            "reviewer_actor_id": actor_id,
            "review_head_sha": review_head,
            "merge_base_sha": snapshots[review_head].get("merge_base_sha"),
            "evidence_sha256": snapshots[review_head].get("l0_sha256"),
            "path": comment.get("path"),
            "side": comment.get("side"),
            "line": comment.get("line"),
            "original_line": comment.get("original_line"),
            "anchor_method": method,
            "anchor_valid": valid,
        }
        if anchor_line_sha256 is not None:
            record["anchor_line_sha256"] = anchor_line_sha256
        records.append(record)

    records.sort(key=lambda item: item["comment_id"])
    return {
        "schema_version": "eviscope.comment-anchor-audit.v0.1",
        "source_comment_sha256": sha256_path(comments_path),
        "snapshot_manifest_sha256": sha256_path(snapshot_manifest_path),
        "record_count": len(records),
        "reviewer_actor_count": len(actor_ids),
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comments", required=True, type=Path)
    parser.add_argument("--pull", required=True, type=Path)
    parser.add_argument("--snapshot-manifest", required=True, type=Path)
    parser.add_argument("--snapshots-root", required=True, type=Path)
    parser.add_argument("--repository", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    receipt_path = args.output.with_name(args.output.stem + ".receipt.json")
    if receipt_path.exists():
        print(f"ERROR: Refusing to overwrite existing file: {receipt_path}", file=sys.stderr)
        return 1
    try:
        result = build_audit(args.comments, args.pull, args.snapshot_manifest, args.snapshots_root, args.repository)
        write_new_json(args.output, result)
        write_new_json(receipt_path, {
            "schema_version": "eviscope.audit-receipt.v0.1",
            "status": "engineering_audit_not_annotation_not_gold",
            "rule_id": AUDIT_RULE_ID,
            "rule_sha256": sha256_bytes(AUDIT_RULE_TEXT.encode("utf-8")),
            "inputs": {
                "comments_sha256": sha256_path(args.comments),
                "pull_sha256": sha256_path(args.pull),
                "snapshot_manifest_sha256": sha256_path(args.snapshot_manifest),
            },
            "outputs": {"audit_sha256": sha256_path(args.output)},
        })
    except StageSToolingError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"record_count": result["record_count"], "output_sha256": sha256_path(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
