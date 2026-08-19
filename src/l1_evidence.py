"""Build review-time L1 evidence from a frozen L0 snapshot.

L1 is changed-file before/after plus enclosing symbols. The builder only
reads Git objects named in the snapshot metadata (merge base and review
head). It never checks out HEAD, never uses the current GitHub tree, and
refuses to overwrite an existing output directory.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SCHEMA = "eviscope.l1-evidence-package.v0.1"
GENERATION_METHOD = "git-show-review-time-no-checkout"
L1_KINDS = {"file_before", "file_after", "enclosing_symbol"}


class L1EvidenceError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise L1EvidenceError(f"Cannot read JSON {path}: {exc}") from exc


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
        raise L1EvidenceError(f"Git command failed: {args[0]}: {exc}") from exc
    if result.returncode:
        stderr = result.stderr.decode("utf-8", "replace") if binary else result.stderr
        raise L1EvidenceError(f"Git command failed: {args[0]}: {stderr.strip()}")
    return result.stdout


def require_commit(repo: Path, sha: str, label: str) -> None:
    if not SHA40.fullmatch(sha):
        raise L1EvidenceError(f"{label} is not a lowercase 40-character SHA: {sha!r}")
    git(repo, "cat-file", "-e", f"{sha}^{{commit}}")


def git_show(repo: Path, sha: str, path: str) -> tuple[bytes | None, str | None]:
    """Return (bytes, None) or (None, unavailable_reason). Other Git failures raise."""
    command = [
        "git",
        "-c",
        "core.pager=cat",
        "-C",
        str(repo),
        "show",
        f"{sha}:{path}",
    ]
    try:
        result = subprocess.run(command, check=False, capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise L1EvidenceError(f"Git show failed for {path} at {sha}: {exc}") from exc
    if result.returncode == 0:
        return result.stdout, None
    stderr = result.stderr.decode("utf-8", "replace")
    lowered = stderr.lower()
    if "does not exist" in lowered or "exists on disk, but not in" in lowered or "not in" in lowered:
        return None, "path_absent_at_review_time_commit"
    raise L1EvidenceError(f"Git show failed for {path} at {sha}: {stderr.strip()}")


def load_snapshot_metadata(snapshot_dir: Path) -> tuple[dict[str, Any], str]:
    metadata_path = snapshot_dir / "metadata.json"
    diff_path = snapshot_dir / "L0.diff"
    if not metadata_path.is_file() or not diff_path.is_file():
        raise L1EvidenceError(f"Snapshot directory must contain metadata.json and L0.diff: {snapshot_dir}")
    metadata = load_json(metadata_path)
    if not isinstance(metadata, dict):
        raise L1EvidenceError("Snapshot metadata must be an object")
    if metadata.get("schema_version") != "eviscope.review-snapshot.v0.1":
        raise L1EvidenceError("Snapshot metadata must identify eviscope.review-snapshot.v0.1")
    digest = sha256_bytes(diff_path.read_bytes())
    recorded = metadata.get("l0_sha256")
    if recorded != digest:
        raise L1EvidenceError("L0.diff hash does not match snapshot metadata l0_sha256")
    return metadata, sha256_bytes(metadata_path.read_bytes())


def allowed_commits(metadata: dict[str, Any]) -> tuple[str, str]:
    merge_base = metadata.get("merge_base_sha")
    review_head = metadata.get("review_head_sha")
    if not isinstance(merge_base, str) or not isinstance(review_head, str):
        raise L1EvidenceError("Snapshot metadata must contain merge_base_sha and review_head_sha")
    if merge_base == review_head:
        raise L1EvidenceError("merge_base_sha and review_head_sha must differ")
    return merge_base, review_head


def comment_index(comments_path: Path | None) -> dict[int, dict[str, Any]]:
    if comments_path is None:
        return {}
    payload = load_json(comments_path)
    if not isinstance(payload, list):
        raise L1EvidenceError("Comments JSON must be a list")
    indexed: dict[int, dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("id"), int):
            continue
        indexed[item["id"]] = item
    return indexed


def python_enclosing_symbol(source: str, line: int) -> dict[str, Any] | None:
    if line < 1:
        raise L1EvidenceError("original_line must be a positive 1-based line number")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    matches: list[tuple[int, int, int, ast.AST]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        start = getattr(node, "lineno", None)
        end = getattr(node, "end_lineno", None)
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if start <= line <= end:
            matches.append((end - start, -start, end, node))
    if not matches:
        return None
    matches.sort()
    _span, _neg_start, end, node = matches[0]
    start = node.lineno
    lines = source.splitlines(keepends=True)
    text = "".join(lines[start - 1 : end])
    kind = "class" if isinstance(node, ast.ClassDef) else "function"
    return {
        "kind": kind,
        "name": node.name,
        "start_line": start,
        "end_line": end,
        "text": text,
    }


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
        "level": "L1",
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


def _write_bytes(root: Path, relative: str, data: bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _safe_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "unnamed"


def build(
    repository: Path,
    snapshot_dir: Path,
    output: Path,
    comments_path: Path | None = None,
    comment_id: int | None = None,
    all_changed_files: bool = False,
) -> dict[str, Any]:
    if output.exists():
        raise L1EvidenceError(f"Refusing to overwrite existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if git(repository, "rev-parse", "--is-inside-work-tree").strip() != "true":
        raise L1EvidenceError("Repository is not a Git work tree")

    metadata, metadata_sha256 = load_snapshot_metadata(snapshot_dir)
    merge_base, review_head = allowed_commits(metadata)
    require_commit(repository, merge_base, "merge base")
    require_commit(repository, review_head, "review head")

    snapshot_comments = metadata.get("comments")
    if not isinstance(snapshot_comments, list) or not snapshot_comments:
        raise L1EvidenceError("Snapshot metadata must list comments")
    changed_files = metadata.get("changed_files")
    if not isinstance(changed_files, list) or any(not isinstance(item, str) or not item for item in changed_files):
        raise L1EvidenceError("Snapshot metadata must list changed_files")
    for path in changed_files:
        if path.startswith("/") or ".." in Path(path).parts:
            raise L1EvidenceError(f"changed file path must be repository-relative: {path}")

    indexed = comment_index(comments_path)
    selected: list[dict[str, Any]] = []
    for record in snapshot_comments:
        if not isinstance(record, dict) or not isinstance(record.get("comment_id"), int):
            raise L1EvidenceError("Snapshot comment records require integer comment_id")
        if comment_id is not None and record["comment_id"] != comment_id:
            continue
        selected.append(record)
    if comment_id is not None and not selected:
        raise L1EvidenceError(f"comment_id {comment_id} is not in this snapshot")

    paths: set[str] = set()
    if all_changed_files:
        paths.update(changed_files)
    for record in selected:
        path = record.get("path")
        if isinstance(path, str) and path:
            if path.startswith("/") or ".." in Path(path).parts:
                raise L1EvidenceError(f"comment path must be repository-relative: {path}")
            paths.add(path)
    if not paths:
        raise L1EvidenceError("No files selected for L1 reconstruction")

    tmp = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=str(output.parent)))
    artifacts_dir = tmp / "artifacts"
    artifacts_dir.mkdir()
    artifacts: list[dict[str, Any]] = []

    try:
        for path in sorted(paths):
            before, before_reason = git_show(repository, merge_base, path)
            after, after_reason = git_show(repository, review_head, path)
            before_rel = None
            after_rel = None
            token = _safe_token(path)
            if before is not None:
                before_rel = f"artifacts/file_before__{token}.bin"
                _write_bytes(tmp, before_rel, before)
            if after is not None:
                after_rel = f"artifacts/file_after__{token}.bin"
                _write_bytes(tmp, after_rel, after)
            artifacts.append(
                _artifact(
                    f"file_before:{path}",
                    "file_before",
                    path,
                    merge_base,
                    f"git:{merge_base}:{path}",
                    before,
                    before_rel,
                    before_reason or "path_absent_at_review_time_commit",
                )
            )
            artifacts.append(
                _artifact(
                    f"file_after:{path}",
                    "file_after",
                    path,
                    review_head,
                    f"git:{review_head}:{path}",
                    after,
                    after_rel,
                    after_reason or "path_absent_at_review_time_commit",
                )
            )

        for record in selected:
            cid = record["comment_id"]
            path = record.get("path")
            if not isinstance(path, str) or not path:
                artifacts.append(
                    _artifact(
                        f"enclosing_symbol:{cid}",
                        "enclosing_symbol",
                        "",
                        review_head,
                        f"comment:{cid}",
                        None,
                        None,
                        "missing_comment_path",
                        comment_id=cid,
                    )
                )
                continue
            detail = indexed.get(cid)
            line = detail.get("original_line") if isinstance(detail, dict) else None
            side = detail.get("side") if isinstance(detail, dict) else "RIGHT"
            if not isinstance(line, int) or isinstance(line, bool) or line < 1:
                artifacts.append(
                    _artifact(
                        f"enclosing_symbol:{cid}",
                        "enclosing_symbol",
                        path,
                        review_head,
                        f"git:{review_head}:{path}",
                        None,
                        None,
                        "missing_original_line",
                        comment_id=cid,
                    )
                )
                continue
            commit = merge_base if side == "LEFT" else review_head
            if commit not in {merge_base, review_head}:
                raise L1EvidenceError("enclosing-symbol commit is not a review-time snapshot SHA")
            source_bytes, absent = git_show(repository, commit, path)
            if source_bytes is None:
                artifacts.append(
                    _artifact(
                        f"enclosing_symbol:{cid}",
                        "enclosing_symbol",
                        path,
                        commit,
                        f"git:{commit}:{path}#L{line}",
                        None,
                        None,
                        absent or "path_absent_at_review_time_commit",
                        comment_id=cid,
                    )
                )
                continue
            if path.endswith(".py"):
                try:
                    source_text = source_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    symbol = None
                    reason = "source_not_utf8"
                else:
                    symbol = python_enclosing_symbol(source_text, line)
                    reason = "no_enclosing_function_or_class"
            else:
                symbol = None
                reason = "language_not_supported_for_symbol_parse"
            if symbol is None:
                artifacts.append(
                    _artifact(
                        f"enclosing_symbol:{cid}",
                        "enclosing_symbol",
                        path,
                        commit,
                        f"git:{commit}:{path}#L{line}",
                        None,
                        None,
                        reason,
                        comment_id=cid,
                    )
                )
                continue
            payload = {
                "schema_version": "eviscope.l1-enclosing-symbol.v0.1",
                "comment_id": cid,
                "path": path,
                "original_line": line,
                "side": side or "RIGHT",
                "review_time_commit": commit,
                **symbol,
            }
            encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            relative = f"artifacts/enclosing_symbol__{cid}.json"
            _write_bytes(tmp, relative, encoded)
            artifacts.append(
                _artifact(
                    f"enclosing_symbol:{cid}",
                    "enclosing_symbol",
                    path,
                    commit,
                    f"git:{commit}:{path}#L{symbol['start_line']}-L{symbol['end_line']}",
                    encoded,
                    relative,
                    None,
                    comment_id=cid,
                )
            )

        package = {
            "schema_version": SCHEMA,
            "status": "engineering_smoke_not_gold",
            "review_head_sha": review_head,
            "merge_base_sha": merge_base,
            "l0_sha256": metadata["l0_sha256"],
            "snapshot_metadata_sha256": metadata_sha256,
            "generation_method": GENERATION_METHOD,
            "future_artifacts_allowed": False,
            "comment_count": len(selected),
            "file_count": len(paths),
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
