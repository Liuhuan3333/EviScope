"""Build review-time L2 evidence on top of a frozen L1 package.

L2 adds repository-local definitions, imports, references, related tests, and
configuration reachable at the review head without checking out HEAD.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from l1_evidence import (
    L1EvidenceError,
    comment_index,
    git,
    git_show,
    load_json,
    load_snapshot_metadata,
    require_commit,
    sha256_bytes,
)


SCHEMA = "eviscope.l2-evidence-package.v0.1"
GENERATION_METHOD = "git-show-review-time-l2-no-checkout"
L2_KINDS = {"definition", "reference", "call_relation", "import", "test", "configuration"}
COMMENT_PATH = re.compile(r"\b(?:[\w.-]+/)*[\w.-]+\.py\b")
CONFIG_NAMES = {
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "tox.ini",
    "pytest.ini",
    "mypy.ini",
    "ruff.toml",
}


class L2EvidenceError(RuntimeError):
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
        "level": "L2",
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


def extract_python_imports(source: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    imports: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({"kind": "import", "module": alias.name, "name": alias.asname or alias.name})
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append(
                    {
                        "kind": "import_from",
                        "module": module,
                        "name": alias.name,
                        "alias": alias.asname,
                        "level": node.level,
                    }
                )
    return imports


def extract_comment_paths(comment_text: str) -> list[str]:
    seen: set[str] = set()
    paths: list[str] = []
    for match in COMMENT_PATH.finditer(comment_text):
        value = match.group(0)
        if value not in seen:
            seen.add(value)
            paths.append(value)
    return paths


def list_repo_paths(repository: Path, review_head: str) -> list[str]:
    cache_dir = repository / ".eviscope-cache"
    cache_file = cache_dir / f"repo-paths-{review_head}.json"
    if cache_file.is_file():
        cached = load_json(cache_file)
        if isinstance(cached, list) and all(isinstance(item, str) for item in cached):
            return cached
    output = git(repository, "ls-tree", "-r", "--name-only", review_head)
    assert isinstance(output, str)
    paths = [line for line in output.splitlines() if line]
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes((json.dumps(paths, ensure_ascii=False) + "\n").encode("utf-8"))
    return paths


def resolve_comment_path(
    bare_or_relative: str,
    anchor_path: str,
    repo_paths: list[str],
) -> str | None:
    if bare_or_relative in repo_paths:
        return bare_or_relative
    anchor_dir = str(Path(anchor_path).parent)
    candidate = str(Path(anchor_dir) / bare_or_relative)
    if candidate in repo_paths:
        return candidate
    basename = Path(bare_or_relative).name
    matches = [path for path in repo_paths if path.endswith(f"/{basename}") or path == basename]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    anchor_parts = Path(anchor_path).parts
    def score(path: str) -> tuple[int, int]:
        parts = Path(path).parts
        shared = sum(1 for left, right in zip(anchor_parts, parts) if left == right)
        return (-shared, len(path))
    return sorted(matches, key=score)[0]


def is_test_path(path: str) -> bool:
    name = Path(path).name
    parts = Path(path).parts
    return (name.startswith("test_") and name.endswith(".py")) or ("tests" in parts and name.endswith(".py"))


def grep_lines(content: str, needle: str, limit: int = 20) -> list[str]:
    hits: list[str] = []
    for line in content.splitlines():
        if needle in line:
            hits.append(line)
            if len(hits) >= limit:
                break
    return hits


def enclosing_symbol_name(l1_dir: Path, comment_id: int) -> str | None:
    rel = l1_dir / "artifacts" / f"enclosing_symbol__{comment_id}.json"
    if not rel.is_file():
        return None
    payload = load_json(rel)
    if not isinstance(payload, dict):
        return None
    name = payload.get("name")
    return name if isinstance(name, str) and name else None


def build(
    repository: Path,
    snapshot_dir: Path,
    l1_dir: Path,
    comments_path: Path,
    comment_id: int,
    output: Path,
) -> dict[str, Any]:
    if output.exists():
        raise L2EvidenceError(f"Refusing to overwrite existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if git(repository, "rev-parse", "--is-inside-work-tree").strip() != "true":
        raise L2EvidenceError("Repository is not a Git work tree")

    l1_manifest_path = l1_dir / "manifest.json"
    if not l1_manifest_path.is_file():
        raise L2EvidenceError(f"L1 package missing manifest.json: {l1_dir}")
    l1_manifest = load_json(l1_manifest_path)
    if l1_manifest.get("schema_version") != "eviscope.l1-evidence-package.v0.1":
        raise L2EvidenceError("L1 manifest must identify eviscope.l1-evidence-package.v0.1")

    metadata, _metadata_sha = load_snapshot_metadata(snapshot_dir)
    merge_base, review_head = metadata["merge_base_sha"], metadata["review_head_sha"]
    if l1_manifest.get("review_head_sha") != review_head or l1_manifest.get("merge_base_sha") != merge_base:
        raise L2EvidenceError("L1 manifest review SHAs do not match snapshot metadata")
    require_commit(repository, merge_base, "merge base")
    require_commit(repository, review_head, "review head")

    indexed = comment_index(comments_path)
    detail = indexed.get(comment_id)
    if not isinstance(detail, dict):
        raise L2EvidenceError(f"comment_id {comment_id} not found in comments JSON")
    anchor_path = detail.get("path")
    if not isinstance(anchor_path, str) or not anchor_path:
        raise L2EvidenceError(f"comment_id {comment_id} has no path")
    comment_body = detail.get("body")
    if not isinstance(comment_body, str):
        comment_body = ""

    changed_files = metadata.get("changed_files")
    if not isinstance(changed_files, list):
        raise L2EvidenceError("Snapshot metadata must list changed_files")

    tmp = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=str(output.parent)))
    artifacts: list[dict[str, Any]] = []
    repo_paths = list_repo_paths(repository, review_head)
    symbol_name = enclosing_symbol_name(l1_dir, comment_id)

    try:
        if anchor_path.endswith(".py"):
            source_bytes, absent = git_show(repository, review_head, anchor_path)
            if source_bytes is None:
                artifacts.append(
                    _artifact(
                        f"import:{comment_id}",
                        "import",
                        anchor_path,
                        review_head,
                        f"git:{review_head}:{anchor_path}",
                        None,
                        None,
                        absent or "path_absent_at_review_time_commit",
                        comment_id=comment_id,
                    )
                )
            else:
                try:
                    source_text = source_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    reason = "source_not_utf8"
                    payload_bytes = None
                else:
                    payload = {
                        "schema_version": "eviscope.l2-imports.v0.1",
                        "comment_id": comment_id,
                        "path": anchor_path,
                        "review_time_commit": review_head,
                        "imports": extract_python_imports(source_text),
                    }
                    payload_bytes = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                    reason = None
                relative = f"artifacts/import__{comment_id}.json"
                if payload_bytes is not None:
                    _write_bytes(tmp, relative, payload_bytes)
                artifacts.append(
                    _artifact(
                        f"import:{comment_id}",
                        "import",
                        anchor_path,
                        review_head,
                        f"git:{review_head}:{anchor_path}#imports",
                        payload_bytes,
                        relative if payload_bytes is not None else None,
                        reason,
                        comment_id=comment_id,
                    )
                )

        for mention in extract_comment_paths(comment_body):
            resolved = resolve_comment_path(mention, anchor_path, repo_paths)
            artifact_id = f"definition:comment-mention:{_safe_token(mention)}"
            if resolved is None:
                artifacts.append(
                    _artifact(
                        artifact_id,
                        "definition",
                        mention,
                        review_head,
                        f"comment:{comment_id}:mention:{mention}",
                        None,
                        None,
                        "comment_mention_not_found_at_review_time",
                        comment_id=comment_id,
                    )
                )
                continue
            content, absent = git_show(repository, review_head, resolved)
            relative = f"artifacts/definition__{_safe_token(resolved)}.bin"
            if content is not None:
                _write_bytes(tmp, relative, content)
            artifacts.append(
                _artifact(
                    artifact_id,
                    "definition",
                    resolved,
                    review_head,
                    f"git:{review_head}:{resolved}",
                    content,
                    relative if content is not None else None,
                    absent or "path_absent_at_review_time_commit",
                    comment_id=comment_id,
                )
            )

        if symbol_name:
            for path in sorted(changed_files):
                if not isinstance(path, str) or not path.endswith(".py"):
                    continue
                content, absent = git_show(repository, review_head, path)
                if content is None:
                    continue
                try:
                    text = content.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                hits = grep_lines(text, symbol_name)
                if not hits:
                    continue
                kind = "test" if is_test_path(path) else "reference"
                payload = {
                    "schema_version": "eviscope.l2-reference-snippet.v0.1",
                    "comment_id": comment_id,
                    "path": path,
                    "symbol": symbol_name,
                    "review_time_commit": review_head,
                    "lines": hits,
                }
                payload_bytes = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                relative = f"artifacts/{kind}__{_safe_token(path)}.json"
                _write_bytes(tmp, relative, payload_bytes)
                artifacts.append(
                    _artifact(
                        f"{kind}:{path}",
                        kind,
                        path,
                        review_head,
                        f"git:{review_head}:{path}#grep:{symbol_name}",
                        payload_bytes,
                        relative,
                        None,
                        comment_id=comment_id,
                    )
                )
                if kind == "test" and any(f"{symbol_name}(" in line for line in hits):
                    call_payload = {
                        "schema_version": "eviscope.l2-call-relation.v0.1",
                        "comment_id": comment_id,
                        "path": path,
                        "callee": symbol_name,
                        "review_time_commit": review_head,
                        "lines": [line for line in hits if f"{symbol_name}(" in line],
                    }
                    call_bytes = (json.dumps(call_payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                    call_rel = f"artifacts/call_relation__{_safe_token(path)}.json"
                    _write_bytes(tmp, call_rel, call_bytes)
                    artifacts.append(
                        _artifact(
                            f"call_relation:{path}",
                            "call_relation",
                            path,
                            review_head,
                            f"git:{review_head}:{path}#call:{symbol_name}",
                            call_bytes,
                            call_rel,
                            None,
                            comment_id=comment_id,
                        )
                    )

        for path in sorted(changed_files):
            if Path(path).name not in CONFIG_NAMES:
                continue
            content, absent = git_show(repository, review_head, path)
            relative = f"artifacts/configuration__{_safe_token(path)}.bin"
            if content is not None:
                _write_bytes(tmp, relative, content)
            artifacts.append(
                _artifact(
                    f"configuration:{path}",
                    "configuration",
                    path,
                    review_head,
                    f"git:{review_head}:{path}",
                    content,
                    relative if content is not None else None,
                    absent or "path_absent_at_review_time_commit",
                    comment_id=comment_id,
                )
            )

        if not artifacts:
            artifacts.append(
                _artifact(
                    f"reference:no-match:{comment_id}",
                    "reference",
                    "",
                    review_head,
                    f"comment:{comment_id}:no-l2-match",
                    None,
                    None,
                    "no_repository_local_l2_match",
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
            "l1_manifest_sha256": sha256_bytes(l1_manifest_path.read_bytes()),
            "generation_method": GENERATION_METHOD,
            "future_artifacts_allowed": False,
            "comment_count": 1,
            "l1_artifact_count": l1_manifest.get("artifact_count"),
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
