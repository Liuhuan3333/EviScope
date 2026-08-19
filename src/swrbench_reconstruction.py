"""Verify SWR-Bench review-time candidates against local Git repositories.

Read-only: no checkout, no fetch, no sampling, no model inference.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

SHA40 = re.compile(r"^[0-9a-f]{40}$")
DIFF_MODE = "git-diff-binary-no-renames-no-ext-diff-no-textconv"
SCHEMA = "eviscope.swrbench-reconstruction-audit.v0.1"
STATUS_PASS = "repository_verified_not_inference_not_gold"
STATUS_FAIL = "repository_verification_failed_not_gold"
STATUS_SKIP = "repository_verification_skipped_not_gold"


class SWRReconstructionError(RuntimeError):
    """Raised when reconstruction tooling inputs violate frozen rules."""


def repo_slug(repo: str) -> str:
    if not isinstance(repo, str) or "/" not in repo or repo.count("/") != 1:
        raise SWRReconstructionError(f"repo must look like owner/name: {repo!r}")
    owner, name = repo.split("/", 1)
    if not owner or not name:
        raise SWRReconstructionError(f"repo must look like owner/name: {repo!r}")
    return f"{owner}__{name}"


def resolve_clone(repos_root: Path, repo: str) -> Path:
    return repos_root / repo_slug(repo)


def _git(repo: Path, *args: str, binary: bool = False) -> bytes | str:
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
        raise SWRReconstructionError(f"git {args[0]} failed: {exc}") from exc
    if result.returncode:
        stderr = result.stderr.decode("utf-8", "replace") if binary else result.stderr
        raise SWRReconstructionError(f"git {args[0]} failed: {stderr.strip()}")
    return result.stdout


def _object_exists(repo: Path, sha: str) -> bool:
    if SHA40.fullmatch(sha) is None:
        return False
    result = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"],
        capture_output=True,
        timeout=30,
    )
    return result.returncode == 0


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True,
        timeout=30,
    )
    return result.returncode == 0


def _changed_files(repo: Path, base: str, head: str) -> list[str]:
    output = _git(
        repo,
        "diff",
        "--name-only",
        "-z",
        "--no-ext-diff",
        "--no-textconv",
        "--no-renames",
        base,
        head,
        binary=True,
    )
    if not isinstance(output, bytes):
        raise SWRReconstructionError("git diff returned unexpected text mode output")
    return sorted(item.decode("utf-8") for item in output.split(b"\0") if item)


def _reconstructed_diff(repo: Path, base: str, head: str) -> bytes:
    output = _git(
        repo,
        "diff",
        "--binary",
        "--no-ext-diff",
        "--no-textconv",
        "--no-renames",
        base,
        head,
        binary=True,
    )
    if not isinstance(output, bytes):
        raise SWRReconstructionError("git diff --binary returned unexpected text mode output")
    return output


def _swr_changed_files(candidate: dict[str, Any]) -> list[str]:
    files: set[str] = set()
    commits = candidate.get("pr_commits")
    if not isinstance(commits, list):
        return []
    for commit in commits:
        if not isinstance(commit, dict):
            continue
        diffs = commit.get("diff")
        if not isinstance(diffs, list):
            continue
        for diff in diffs:
            if isinstance(diff, dict) and isinstance(diff.get("file"), str) and diff["file"]:
                files.add(diff["file"])
    return sorted(files)


def _candidate_head(candidate: dict[str, Any]) -> str | None:
    commits = candidate.get("pr_commits")
    if not isinstance(commits, list) or not commits:
        return None
    last = commits[-1]
    if not isinstance(last, dict):
        return None
    sha = last.get("sha")
    return sha if isinstance(sha, str) and SHA40.fullmatch(sha) else None


def verify_candidate(candidate: dict[str, Any], repos_root: Path) -> dict[str, Any]:
    instance_id = candidate.get("instance_id")
    repo = candidate.get("repo")
    base = candidate.get("base_commit")
    head = _candidate_head(candidate)
    failures: list[str] = []

    if not isinstance(instance_id, str) or not instance_id:
        raise SWRReconstructionError("candidate missing instance_id")
    if not isinstance(repo, str) or not repo:
        failures.append("MALFORMED_REPO")
    if not isinstance(base, str) or SHA40.fullmatch(base) is None:
        failures.append("MALFORMED_BASE_SHA")
    if head is None:
        failures.append("MALFORMED_HEAD_SHA")

    clone = resolve_clone(repos_root, repo) if isinstance(repo, str) and repo else Path()
    inside = subprocess.run(
        ["git", "-C", str(clone), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    clone_present = clone.is_dir() and inside.returncode == 0 and inside.stdout.strip() == "true"
    if not clone_present:
        return {
            "schema_version": SCHEMA,
            "instance_id": instance_id,
            "repo": repo,
            "base_commit": base,
            "review_head_sha": head,
            "clone_path": str(clone),
            "verified": False,
            "status": STATUS_SKIP,
            "failures": ["CLONE_MISSING"],
            "changed_file_count": None,
            "swr_changed_file_count": len(_swr_changed_files(candidate)),
            "reconstructed_l0_sha256": None,
            "diff_mode": DIFF_MODE,
        }

    if "MALFORMED_BASE_SHA" not in failures and base is not None and not _object_exists(clone, base):
        failures.append("BASE_COMMIT_MISSING")
    if "MALFORMED_HEAD_SHA" not in failures and head is not None and not _object_exists(clone, head):
        failures.append("HEAD_COMMIT_MISSING")

    commits = candidate.get("pr_commits")
    if isinstance(commits, list):
        for index, commit in enumerate(commits):
            if not isinstance(commit, dict):
                failures.append(f"MALFORMED_COMMIT_{index}")
                continue
            sha = commit.get("sha")
            if not isinstance(sha, str) or SHA40.fullmatch(sha) is None:
                failures.append(f"MALFORMED_COMMIT_SHA_{index}")
            elif not _object_exists(clone, sha):
                failures.append(f"COMMIT_MISSING_{sha[:8]}")

    if (
        base is not None
        and head is not None
        and "BASE_COMMIT_MISSING" not in failures
        and "HEAD_COMMIT_MISSING" not in failures
    ):
        if base == head:
            failures.append("BASE_EQUALS_HEAD")
        elif not _is_ancestor(clone, base, head):
            failures.append("BASE_NOT_ANCESTOR_OF_HEAD")
        else:
            if isinstance(commits, list):
                for commit in commits:
                    if not isinstance(commit, dict):
                        continue
                    sha = commit.get("sha")
                    if isinstance(sha, str) and SHA40.fullmatch(sha) and not _is_ancestor(clone, base, sha):
                        failures.append(f"COMMIT_NOT_DESCENDANT_OF_BASE_{sha[:8]}")
                        break

    swr_files = _swr_changed_files(candidate)
    reconstructed_l0_sha256 = None
    changed_file_count = None
    if (
        not failures
        and base is not None
        and head is not None
        and base != head
    ):
        try:
            git_files = _changed_files(clone, base, head)
            changed_file_count = len(git_files)
            if git_files != swr_files:
                failures.append("CHANGED_FILE_SET_MISMATCH")
            diff_bytes = _reconstructed_diff(clone, base, head)
            if not diff_bytes:
                failures.append("EMPTY_RECONSTRUCTED_DIFF")
            else:
                reconstructed_l0_sha256 = hashlib.sha256(diff_bytes).hexdigest()
        except SWRReconstructionError as exc:
            failures.append(f"DIFF_RECONSTRUCTION_ERROR:{exc}")

    verified = not failures
    if verified:
        status = STATUS_PASS
    elif "CLONE_MISSING" in failures:
        status = STATUS_SKIP
    else:
        status = STATUS_FAIL
    return {
        "schema_version": SCHEMA,
        "instance_id": instance_id,
        "repo": repo,
        "base_commit": base,
        "review_head_sha": head,
        "clone_path": str(clone),
        "verified": verified,
        "status": status,
        "failures": sorted(set(failures)),
        "changed_file_count": changed_file_count,
        "swr_changed_file_count": len(swr_files),
        "reconstructed_l0_sha256": reconstructed_l0_sha256,
        "diff_mode": DIFF_MODE,
    }


def load_candidates(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise SWRReconstructionError(f"cannot read candidates: {exc}") from exc
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SWRReconstructionError(f"invalid JSONL at line {line_number}: {exc}") from exc
        if not isinstance(item, dict):
            raise SWRReconstructionError(f"line {line_number} is not an object")
        if item.get("status") != "timestamp_consistent_requires_repository_verification_not_inference_not_gold":
            raise SWRReconstructionError(
                f"{item.get('instance_id')}: candidate status is not pending repository verification"
            )
        records.append(item)
    if not records:
        raise SWRReconstructionError("candidate file is empty")
    return records


def _jsonl(records: list[dict[str, Any]]) -> bytes:
    return b"".join(
        (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        for record in records
    )


def run_verification(
    candidates_path: Path,
    review_time_manifest_path: Path,
    policy_path: Path,
    repos_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        raise SWRReconstructionError(f"refusing to overwrite existing output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)

    try:
        manifest = json.loads(review_time_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SWRReconstructionError(f"cannot read review-time manifest: {exc}") from exc
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SWRReconstructionError(f"cannot read policy: {exc}") from exc
    if policy.get("schema_version") != "eviscope.swrbench-review-time-policy.v0.1":
        raise SWRReconstructionError("unsupported review-time policy")

    candidates = load_candidates(candidates_path)
    audits = [verify_candidate(candidate, repos_root) for candidate in candidates]

    verified = sum(1 for item in audits if item["verified"])
    skipped = sum(1 for item in audits if item["status"] == STATUS_SKIP)
    failed = sum(1 for item in audits if item["status"] == STATUS_FAIL)
    clone_missing = sum(1 for item in audits if "CLONE_MISSING" in item.get("failures", []))

    audit_bytes = _jsonl(audits)
    audit_path = output_dir / "reconstruction_audit.jsonl"
    audit_path.write_bytes(audit_bytes)
    audit_sha256 = hashlib.sha256(audit_bytes).hexdigest()

    summary = {
        "candidate_count": len(candidates),
        "verified_count": verified,
        "failed_count": failed,
        "skipped_count": skipped,
        "clone_missing_count": clone_missing,
        "unique_repos": len({item.get("repo") for item in candidates if isinstance(item.get("repo"), str)}),
    }

    result_manifest = {
        "schema_version": "eviscope.swrbench-reconstruction-manifest.v0.1",
        "status": "private_repository_audit_not_sampled_not_inference_not_gold",
        "inputs": {
            "candidate_inputs_sha256": hashlib.sha256(candidates_path.read_bytes()).hexdigest(),
            "review_time_manifest_sha256": hashlib.sha256(review_time_manifest_path.read_bytes()).hexdigest(),
            "review_time_policy_sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest(),
            "repos_root": str(repos_root),
        },
        "outputs": {
            "reconstruction_audit.jsonl": audit_sha256,
        },
        "summary": summary,
        "controls": {
            "sampling_performed": False,
            "model_inference_eligible": False,
            "gold_analysis_eligible": False,
            "repository_reconstruction_complete": verified == len(candidates) and verified > 0,
            "swr_labels_exported": False,
            "post_review_fields_exported": False,
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(result_manifest, indent=2) + "\n", encoding="utf-8")
    return result_manifest
