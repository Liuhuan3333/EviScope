"""Shared, dependency-free helpers for Stage-S engineering tools."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class StageSToolingError(RuntimeError):
    """Raised when an input violates a frozen Stage-S tooling rule."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    try:
        return sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise StageSToolingError(f"Cannot read {path}: {exc}") from exc


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageSToolingError(f"Cannot read JSON {path}: {exc}") from exc


def write_new_json(path: Path, value: Any) -> None:
    if path.exists():
        raise StageSToolingError(f"Refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_bytes(canonical_json_bytes(value))
    except OSError as exc:
        raise StageSToolingError(f"Cannot write {path}: {exc}") from exc


def align_verbatim_fragments(comment: str, fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive offsets only for quotations occurring exactly once in comment."""
    if not isinstance(comment, str):
        raise StageSToolingError("comment must be a string")
    if not isinstance(fragments, list) or not fragments:
        raise StageSToolingError("fragments must be a non-empty list")

    aligned: list[dict[str, Any]] = []
    for index, fragment in enumerate(fragments):
        if not isinstance(fragment, dict) or not isinstance(fragment.get("text"), str):
            raise StageSToolingError(f"fragment {index} must contain string text")
        text = fragment["text"]
        if not text:
            raise StageSToolingError(f"fragment {index} text must not be empty")
        occurrences = comment.count(text)
        if occurrences != 1:
            raise StageSToolingError(
                f"fragment {index} must occur exactly once; observed {occurrences} occurrences"
            )
        start = comment.index(text)
        aligned.append({"text": text, "start": start, "end": start + len(text)})

    validate_fragment_offsets(comment, aligned)
    return aligned


def validate_fragment_offsets(comment: str, fragments: list[dict[str, Any]]) -> None:
    previous_end = -1
    for index, fragment in enumerate(fragments):
        if not isinstance(fragment, dict):
            raise StageSToolingError(f"fragment {index} must be an object")
        text = fragment.get("text")
        start = fragment.get("start")
        end = fragment.get("end")
        if not isinstance(text, str) or not isinstance(start, int) or not isinstance(end, int):
            raise StageSToolingError(f"fragment {index} requires text and integer start/end")
        if isinstance(start, bool) or isinstance(end, bool) or start < 0 or end <= start:
            raise StageSToolingError(f"fragment {index} has invalid offsets")
        if start < previous_end:
            raise StageSToolingError("fragments must be ordered and non-overlapping")
        if comment[start:end] != text:
            raise StageSToolingError(f"fragment {index} offsets do not reproduce text")
        previous_end = end
