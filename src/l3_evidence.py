"""Build review-time L3 evidence on top of a frozen L2 package.

L3 adds the PR description, linked issues, repository documentation, and
commit history that can be shown to exist at the review-time commit.
The builder never checks out HEAD and never fetches live GitHub pages.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from l1_evidence import (
    comment_index,
    git,
    git_show,
    load_json,
    load_snapshot_metadata,
    require_commit,
    sha256_bytes,
)


SCHEMA = "eviscope.l3-evidence-package.v0.1"
GENERATION_METHOD = "frozen-raw-and-git-show-review-time-l3-no-checkout"
L3_KINDS = {"pr_description", "issue", "repository_documentation", "history"}
ISSUE_REF = re.compile(r"(?:(?<=\s)|^|[(\[])#(\d+)\b")
DOC_CANDIDATES = (
    "README.md",
    "README.rst",
    "README.txt",
    "CONTRIBUTING.md",
    "CONTRIBUTING.rst",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "docs/index.md",
    "docs/index.rst",
)
HISTORY_LIMIT = 50


class L3EvidenceError(RuntimeError):
    pass


def _safe_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "unnamed"


def _write_bytes(root: Path, relative: str, data: bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _artifact(
    artifact_id: str,
    kind: str,
    path: str,
    commit: str,
    locator: str,
    content: bytes | None,
    relative_path: str | None,
    unavailable_reason: str | None,
    comment_id: int | None = None,
) -> dict[str, Any]:
    available = content is not None
    return {
        "artifact_id": artifact_id,
        "level": "L3",
        "kind": kind,
        "path": path,
        "comment_id": comment_id,
        "source_locator": locator,
        "sha256": sha256_bytes(content) if available else None,
        "available": available,
        "unavailable_reason": None if available else unavailable_reason,
        "review_time_commit": commit,
        "relative_path": relative_path if available else None,
        "byte_length": len(content) if available else 0,
        "binary": (b"\x00" in content) if available else False,
    }


def parse_review_time(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def extract_issue_numbers(text: str, exclude: int | None = None) -> list[int]:
    seen: set[int] = set()
    numbers: list[int] = []
    for match in ISSUE_REF.finditer(text):
        number = int(match.group(1))
        if exclude is not None and number == exclude:
            continue
        if number not in seen:
            seen.add(number)
            numbers.append(number)
    return numbers


def load_frozen_issue(raw_dir: Path, number: int) -> dict[str, Any] | None:
    candidates = [
        raw_dir / "issues" / f"{number}.json",
        raw_dir / f"issue-{number}.json",
        raw_dir / "issue.json",
        raw_dir / "issues.json",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        payload = load_json(path)
        if isinstance(payload, dict) and payload.get("number") == number:
            return payload
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and item.get("number") == number:
                    return item
    return None


def commit_history(repository: Path, merge_base: str, review_head: str) -> list[dict[str, str]]:
    output = git(
        repository,
        "log",
        "--no-decorate",
        "--format=%H\t%cI\t%s",
        f"{merge_base}..{review_head}",
    )
    assert isinstance(output, str)
    rows: list[dict[str, str]] = []
    for line in output.splitlines():
        if not line:
            continue
        sha, when, subject = line.split("\t", 2)
        rows.append({"sha": sha, "committed_at": when, "subject": subject})
        if len(rows) >= HISTORY_LIMIT:
            break
    return rows


def build(
    repository: Path,
    snapshot_dir: Path,
    l2_dir: Path,
    comments_path: Path,
    comment_id: int,
    raw_dir: Path,
    output: Path,
) -> dict[str, Any]:
    if output.exists():
        raise L3EvidenceError(f"Refusing to overwrite existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if git(repository, "rev-parse", "--is-inside-work-tree").strip() != "true":
        raise L3EvidenceError("Repository is not a Git work tree")

    l2_manifest_path = l2_dir / "manifest.json"
    if not l2_manifest_path.is_file():
        raise L3EvidenceError(f"L2 package missing manifest.json: {l2_dir}")
    l2_manifest = load_json(l2_manifest_path)
    if l2_manifest.get("schema_version") != "eviscope.l2-evidence-package.v0.1":
        raise L3EvidenceError("L2 manifest must identify eviscope.l2-evidence-package.v0.1")

    metadata, _metadata_sha = load_snapshot_metadata(snapshot_dir)
    merge_base, review_head = metadata["merge_base_sha"], metadata["review_head_sha"]
    if l2_manifest.get("review_head_sha") != review_head or l2_manifest.get("merge_base_sha") != merge_base:
        raise L3EvidenceError("L2 manifest review SHAs do not match snapshot metadata")
    require_commit(repository, merge_base, "merge base")
    require_commit(repository, review_head, "review head")

    indexed = comment_index(comments_path)
    detail = indexed.get(comment_id)
    if not isinstance(detail, dict):
        raise L3EvidenceError(f"comment_id {comment_id} not found in comments JSON")
    created_at = detail.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        raise L3EvidenceError(f"comment_id {comment_id} has no created_at")
    review_time = parse_review_time(created_at)
    comment_body = detail.get("body")
    if not isinstance(comment_body, str):
        comment_body = ""

    tmp = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=str(output.parent)))
    artifacts: list[dict[str, Any]] = []
    try:
        pull_path = raw_dir / "pull.json"
        pull: dict[str, Any] | None = None
        pr_number: int | None = None
        if not pull_path.is_file():
            artifacts.append(
                _artifact(
                    f"pr_description:{comment_id}",
                    "pr_description",
                    "pull.json",
                    review_head,
                    "raw:pull.json",
                    None,
                    None,
                    "frozen_pull_json_absent",
                    comment_id=comment_id,
                )
            )
        else:
            loaded = load_json(pull_path)
            if not isinstance(loaded, dict):
                raise L3EvidenceError("pull.json must be an object")
            pull = loaded
            number = pull.get("number")
            pr_number = number if isinstance(number, int) else None
            created = pull.get("created_at")
            updated = pull.get("updated_at")
            reason = None
            payload_bytes = None
            if not isinstance(created, str) or parse_review_time(created) > review_time:
                reason = "pr_created_after_review_time"
            elif isinstance(updated, str) and parse_review_time(updated) > review_time:
                reason = "frozen_pull_json_updated_after_review_time"
            else:
                payload = {
                    "schema_version": "eviscope.l3-pr-description.v0.1",
                    "comment_id": comment_id,
                    "number": pr_number,
                    "title": pull.get("title") if isinstance(pull.get("title"), str) else "",
                    "body": pull.get("body") if isinstance(pull.get("body"), str) else "",
                    "created_at": created,
                    "updated_at": updated,
                    "review_time_commit": review_head,
                }
                payload_bytes = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            relative = f"artifacts/pr_description__{comment_id}.json"
            if payload_bytes is not None:
                _write_bytes(tmp, relative, payload_bytes)
            artifacts.append(
                _artifact(
                    f"pr_description:{comment_id}",
                    "pr_description",
                    "pull.json",
                    review_head,
                    "raw:pull.json",
                    payload_bytes,
                    relative if payload_bytes is not None else None,
                    reason,
                    comment_id=comment_id,
                )
            )

        search_text = comment_body
        if pull and isinstance(pull.get("body"), str) and isinstance(pull.get("created_at"), str):
            if parse_review_time(pull["created_at"]) <= review_time:
                search_text = f"{comment_body}\n{pull['body']}"
        for number in extract_issue_numbers(search_text, exclude=pr_number):
            frozen = load_frozen_issue(raw_dir, number)
            artifact_id = f"issue:{number}"
            if frozen is None:
                artifacts.append(
                    _artifact(
                        artifact_id,
                        "issue",
                        f"issues/{number}.json",
                        review_head,
                        f"raw:issue:{number}",
                        None,
                        None,
                        "linked_issue_not_in_frozen_raw",
                        comment_id=comment_id,
                    )
                )
                continue
            issue_created = frozen.get("created_at")
            issue_updated = frozen.get("updated_at")
            reason = None
            payload_bytes = None
            if not isinstance(issue_created, str) or parse_review_time(issue_created) > review_time:
                reason = "issue_created_after_review_time"
            elif isinstance(issue_updated, str) and parse_review_time(issue_updated) > review_time:
                reason = "frozen_issue_json_updated_after_review_time"
            else:
                payload = {
                    "schema_version": "eviscope.l3-issue.v0.1",
                    "comment_id": comment_id,
                    "number": number,
                    "title": frozen.get("title") if isinstance(frozen.get("title"), str) else "",
                    "body": frozen.get("body") if isinstance(frozen.get("body"), str) else "",
                    "created_at": issue_created,
                    "updated_at": issue_updated,
                    "review_time_commit": review_head,
                }
                payload_bytes = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            relative = f"artifacts/issue__{number}.json"
            if payload_bytes is not None:
                _write_bytes(tmp, relative, payload_bytes)
            artifacts.append(
                _artifact(
                    artifact_id,
                    "issue",
                    f"issues/{number}.json",
                    review_head,
                    f"raw:issue:{number}",
                    payload_bytes,
                    relative if payload_bytes is not None else None,
                    reason,
                    comment_id=comment_id,
                )
            )

        for doc_path in DOC_CANDIDATES:
            content, absent = git_show(repository, review_head, doc_path)
            if content is None:
                continue
            relative = f"artifacts/repository_documentation__{_safe_token(doc_path)}.bin"
            _write_bytes(tmp, relative, content)
            artifacts.append(
                _artifact(
                    f"repository_documentation:{doc_path}",
                    "repository_documentation",
                    doc_path,
                    review_head,
                    f"git:{review_head}:{doc_path}",
                    content,
                    relative,
                    absent,
                    comment_id=comment_id,
                )
            )
            break

        history = commit_history(repository, merge_base, review_head)
        history_payload = {
            "schema_version": "eviscope.l3-history.v0.1",
            "comment_id": comment_id,
            "merge_base_sha": merge_base,
            "review_head_sha": review_head,
            "commit_count": len(history),
            "commits": history,
        }
        history_bytes = (json.dumps(history_payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        history_rel = "artifacts/history.json"
        _write_bytes(tmp, history_rel, history_bytes)
        artifacts.append(
            _artifact(
                f"history:{comment_id}",
                "history",
                "git-log",
                review_head,
                f"git-log:{merge_base}..{review_head}",
                history_bytes,
                history_rel,
                None,
                comment_id=comment_id,
            )
        )

        package = {
            "schema_version": SCHEMA,
            "status": "engineering_smoke_not_gold",
            "comment_id": comment_id,
            "review_head_sha": review_head,
            "merge_base_sha": merge_base,
            "l0_sha256": metadata["l0_sha256"],
            "l2_manifest_sha256": sha256_bytes(l2_manifest_path.read_bytes()),
            "generation_method": GENERATION_METHOD,
            "future_artifacts_allowed": False,
            "comment_count": 1,
            "l2_artifact_count": l2_manifest.get("artifact_count"),
            "artifact_count": len(artifacts),
            "artifacts": artifacts,
        }
        (tmp / "manifest.json").write_bytes(
            (json.dumps(package, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        )
        os.replace(tmp, output)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return package
