"""Dependency-free structural and semantic validation for Gate 0 artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


LEVELS = ("L0", "L1", "L2", "L3")
VERDICTS = {"SUPPORTED", "CONTRADICTED", "INSUFFICIENT"}
PLACEHOLDERS = {"UNCONFIRMED", "TBD", "TODO"}
NON_MATERIAL_REASONS = {
    "GREETING_OR_ACKNOWLEDGEMENT",
    "PURE_PREFERENCE",
    "PURE_CODE_SUGGESTION",
    "PROCESS_UPDATE",
    "QUESTION_NO_FACTUAL_PREMISE",
    "DUPLICATE_POINTER",
    "CONTEXT_ONLY_PR_AUTHOR",
    "OVERSIZED_COMPOSITE",
    "OTHER",
}
DISAGREEMENT_CODES_V03 = {
    "SEGMENTATION_BOUNDARY",
    "NORMALIZATION",
    "MATERIALITY",
    "VERDICT",
    "MINIMUM_LEVEL",
    "EVIDENCE_SCOPE",
    "REVIEW_TIME_LEAKAGE",
    "OTHER",
}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAMPLE_ID = re.compile(r"^[a-zA-Z0-9._-]+$")
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]+$")

LEVEL_KINDS = {
    "L0": {"diff"},
    "L1": {"file_before", "file_after", "enclosing_symbol"},
    "L2": {"definition", "reference", "call_relation", "import", "test", "configuration"},
    "L3": {"pr_description", "issue", "repository_documentation", "history"},
}


@dataclass(frozen=True)
class Issue:
    path: Path
    location: str
    message: str

    def __str__(self) -> str:
        suffix = f" [{self.location}]" if self.location else ""
        return f"{self.path}{suffix}: {self.message}"


def _issue(path: Path, location: str, message: str) -> Issue:
    return Issue(path, location, message)


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def _required(path: Path, obj: Any, fields: tuple[str, ...], location: str) -> list[Issue]:
    if not isinstance(obj, dict):
        return [_issue(path, location, "must be an object")]
    return [
        _issue(path, f"{location}.{field}".strip("."), "missing required field")
        for field in fields
        if field not in obj
    ]


def _unexpected(path: Path, obj: Any, allowed: set[str], location: str) -> list[Issue]:
    if not isinstance(obj, dict):
        return []
    return [
        _issue(path, f"{location}.{field}".strip("."), "unexpected field")
        for field in obj
        if field not in allowed
    ]


def validate_dataset(path: Path, data: dict[str, Any]) -> list[Issue]:
    issues = _required(path, data, ("dataset_id", "records"), "")
    if not isinstance(data.get("dataset_id"), str) or not data.get("dataset_id"):
        issues.append(_issue(path, "dataset_id", "must be a non-empty string"))
    records = data.get("records")
    if not isinstance(records, list):
        return issues + [_issue(path, "records", "must be an array")]
    sample_ids: set[str] = set()
    for index, record in enumerate(records):
        loc = f"records[{index}]"
        issues += _required(path, record, ("sample_id", "sample_kind", "provenance", "review", "artifacts", "analysis_eligible"), loc)
        if not isinstance(record, dict):
            continue
        sample_id = record.get("sample_id")
        if isinstance(sample_id, str):
            if sample_id in sample_ids:
                issues.append(_issue(path, f"{loc}.sample_id", "duplicate sample_id"))
            sample_ids.add(sample_id)
            if SAMPLE_ID.fullmatch(sample_id) is None:
                issues.append(_issue(path, f"{loc}.sample_id", "contains unsupported characters"))
        else:
            issues.append(_issue(path, f"{loc}.sample_id", "must be a string"))
        kind = record.get("sample_kind")
        if kind not in {"natural", "challenge", "synthetic_smoke"}:
            issues.append(_issue(path, f"{loc}.sample_kind", "must be natural, challenge, or synthetic_smoke"))
        if kind == "synthetic_smoke" and record.get("analysis_eligible") is not False:
            issues.append(_issue(path, f"{loc}.analysis_eligible", "synthetic smoke records must be analysis-ineligible"))
        provenance = record.get("provenance", {})
        issues += _required(
            path,
            provenance,
            ("forge", "repository", "repository_url", "license_spdx", "pr_number", "base_sha", "head_sha", "retrieved_at"),
            f"{loc}.provenance",
        )
        if isinstance(provenance, dict):
            if provenance.get("forge") not in {"github", "gitlab", "other"}:
                issues.append(_issue(path, f"{loc}.provenance.forge", "must be github, gitlab, or other"))
            repository = provenance.get("repository")
            if not isinstance(repository, str) or repository.count("/") != 1 or repository.startswith("/") or repository.endswith("/"):
                issues.append(_issue(path, f"{loc}.provenance.repository", "must be owner/repository"))
            url = provenance.get("repository_url")
            if not isinstance(url, str) or not url.startswith("https://"):
                issues.append(_issue(path, f"{loc}.provenance.repository_url", "must be an HTTPS URL"))
            if not isinstance(provenance.get("license_spdx"), str) or provenance.get("license_spdx") in PLACEHOLDERS:
                issues.append(_issue(path, f"{loc}.provenance.license_spdx", "requires a non-placeholder SPDX expression"))
            if (
                not isinstance(provenance.get("pr_number"), int)
                or isinstance(provenance.get("pr_number"), bool)
                or provenance.get("pr_number", 0) < 1
            ):
                issues.append(_issue(path, f"{loc}.provenance.pr_number", "must be a positive integer"))
            for field in ("base_sha", "head_sha"):
                value = provenance.get(field)
                if not isinstance(value, str) or SHA40.fullmatch(value) is None:
                    issues.append(_issue(path, f"{loc}.provenance.{field}", "must be a lowercase 40-character commit SHA"))
            if provenance.get("base_sha") == provenance.get("head_sha"):
                issues.append(_issue(path, f"{loc}.provenance", "base_sha and head_sha must differ"))
            if _parse_time(provenance.get("retrieved_at")) is None:
                issues.append(_issue(path, f"{loc}.provenance.retrieved_at", "must be a timezone-aware ISO-8601 timestamp"))

        review = record.get("review", {})
        issues += _required(
            path,
            review,
            ("comment_id", "comment_author_type", "comment_text", "review_timestamp", "path"),
            f"{loc}.review",
        )
        review_time = _parse_time(review.get("review_timestamp")) if isinstance(review, dict) else None
        if review_time is None:
            issues.append(_issue(path, f"{loc}.review.review_timestamp", "must be a timezone-aware ISO-8601 timestamp"))
        if isinstance(review, dict):
            author_type = review.get("comment_author_type")
            generator_id = review.get("generator_registry_id")
            if author_type not in {"human", "model"}:
                issues.append(_issue(path, f"{loc}.review.comment_author_type", "must be human or model"))
            elif author_type == "model" and not generator_id:
                issues.append(_issue(path, f"{loc}.review.generator_registry_id", "model comments require a generator registry ID"))
            elif author_type == "human" and generator_id is not None:
                issues.append(_issue(path, f"{loc}.review.generator_registry_id", "human comments cannot name a generator model"))
            for field in ("comment_id", "comment_text", "path"):
                if not isinstance(review.get(field), str) or not review.get(field):
                    issues.append(_issue(path, f"{loc}.review.{field}", "must be a non-empty string"))
            review_path = review.get("path")
            if isinstance(review_path, str) and (review_path.startswith("/") or ".." in Path(review_path).parts):
                issues.append(_issue(path, f"{loc}.review.path", "must be a repository-relative path"))
        artifacts = record.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            issues.append(_issue(path, f"{loc}.artifacts", "must contain at least one artifact"))
            continue
        artifact_ids: set[str] = set()
        has_l0_diff = False
        for artifact_index, artifact in enumerate(artifacts):
            aloc = f"{loc}.artifacts[{artifact_index}]"
            issues += _required(path, artifact, ("artifact_id", "level", "kind", "source_locator", "sha256", "available_at"), aloc)
            if not isinstance(artifact, dict):
                continue
            aid = artifact.get("artifact_id")
            if isinstance(aid, str) and aid:
                if aid in artifact_ids:
                    issues.append(_issue(path, f"{aloc}.artifact_id", "duplicate artifact_id within sample"))
                artifact_ids.add(aid)
            else:
                issues.append(_issue(path, f"{aloc}.artifact_id", "must be a non-empty string"))
            level = artifact.get("level")
            if level not in LEVELS:
                issues.append(_issue(path, f"{aloc}.level", "must be L0-L3"))
            has_l0_diff |= level == "L0" and artifact.get("kind") == "diff"
            if level in LEVEL_KINDS and artifact.get("kind") not in LEVEL_KINDS[level]:
                issues.append(_issue(path, f"{aloc}.kind", f"is not valid evidence kind for {level}"))
            digest = artifact.get("sha256")
            if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
                issues.append(_issue(path, f"{aloc}.sha256", "must be a lowercase 64-character SHA-256"))
            if not isinstance(artifact.get("source_locator"), str) or not artifact.get("source_locator"):
                issues.append(_issue(path, f"{aloc}.source_locator", "must be a non-empty string"))
            available = _parse_time(artifact.get("available_at"))
            if available is None:
                issues.append(_issue(path, f"{aloc}.available_at", "must be an ISO-8601 timestamp"))
            elif review_time is not None and available > review_time:
                issues.append(_issue(path, f"{aloc}.available_at", "future artifact: available after review_timestamp"))
        if not has_l0_diff:
            issues.append(_issue(path, f"{loc}.artifacts", "must include an L0 diff artifact"))
        eligible = record.get("analysis_eligible")
        exclusion = record.get("exclusion_reason")
        if not isinstance(eligible, bool):
            issues.append(_issue(path, f"{loc}.analysis_eligible", "must be boolean"))
        elif eligible and exclusion is not None:
            issues.append(_issue(path, f"{loc}.exclusion_reason", "eligible records cannot have an exclusion reason"))
        elif not eligible and not isinstance(exclusion, str):
            issues.append(_issue(path, f"{loc}.exclusion_reason", "ineligible records require an exclusion reason"))
    return issues


def validate_annotation(path: Path, data: dict[str, Any]) -> list[Issue]:
    issues = _required(path, data, ("schema_version", "sample_id", "annotator_private_id", "annotation_round", "claims", "completed_at", "guide_version"), "")
    if data.get("annotation_round") not in {"independent_a", "independent_b", "reverse_audit", "adjudication"}:
        issues.append(_issue(path, "annotation_round", "unknown annotation round"))
    if data.get("schema_version") != "eviscope.annotation.v0.2":
        issues.append(_issue(path, "schema_version", "must identify annotation schema v0.2"))
    if data.get("guide_version") != "v0.2":
        issues.append(_issue(path, "guide_version", "must identify annotation guide v0.2"))
    if _parse_time(data.get("completed_at")) is None:
        issues.append(_issue(path, "completed_at", "must be a timezone-aware ISO-8601 timestamp"))
    claims = data.get("claims")
    if not isinstance(claims, list) or not claims:
        return issues + [_issue(path, "claims", "must be a non-empty array")]
    claim_ids: set[str] = set()
    for index, claim in enumerate(claims):
        loc = f"claims[{index}]"
        issues += _required(path, claim, ("claim_id", "text", "source_span", "materiality", "judgments", "final_verdict", "minimum_evidence_level"), loc)
        if not isinstance(claim, dict):
            continue
        claim_id = claim.get("claim_id")
        if isinstance(claim_id, str) and claim_id:
            if claim_id in claim_ids:
                issues.append(_issue(path, f"{loc}.claim_id", "duplicate claim_id"))
            claim_ids.add(claim_id)
        else:
            issues.append(_issue(path, f"{loc}.claim_id", "must be a non-empty string"))
        if not isinstance(claim.get("text"), str) or not claim.get("text"):
            issues.append(_issue(path, f"{loc}.text", "must be a non-empty string"))
        span = claim.get("source_span", {})
        if (
            not isinstance(span, dict)
            or not isinstance(span.get("start"), int)
            or isinstance(span.get("start"), bool)
            or not isinstance(span.get("end"), int)
            or isinstance(span.get("end"), bool)
            or span.get("start", -1) < 0
            or span.get("end", 0) <= span.get("start", 0)
        ):
            issues.append(_issue(path, f"{loc}.source_span", "end must be greater than start"))
        materiality = claim.get("materiality")
        final = claim.get("final_verdict")
        minimum = claim.get("minimum_evidence_level")
        judgments = claim.get("judgments")
        codes = claim.get("disagreement_codes")
        allowed_codes = {"SEGMENTATION_BOUNDARY", "MATERIALITY", "VERDICT", "MINIMUM_LEVEL", "EVIDENCE_SCOPE", "REVIEW_TIME_LEAKAGE", "OTHER"}
        if not isinstance(codes, list) or any(not isinstance(code, str) for code in codes) or len(codes) != len(set(codes)) or any(code not in allowed_codes for code in codes):
            issues.append(_issue(path, f"{loc}.disagreement_codes", "must contain unique registered disagreement codes"))
        if materiality == "non_material":
            if final != "NOT_APPLICABLE" or minimum is not None or judgments not in ([], None):
                issues.append(_issue(path, loc, "non-material claims require NOT_APPLICABLE, null minimum level, and no judgments"))
            if not claim.get("non_material_reason"):
                issues.append(_issue(path, f"{loc}.non_material_reason", "required for non-material claim"))
            continue
        if materiality != "material":
            issues.append(_issue(path, f"{loc}.materiality", "must be material or non_material"))
        if not isinstance(judgments, list) or not judgments:
            issues.append(_issue(path, f"{loc}.judgments", "material claim requires progressive judgments"))
            continue
        seen_levels: list[str] = []
        decisive: tuple[str, str] | None = None
        for ji, judgment in enumerate(judgments):
            jloc = f"{loc}.judgments[{ji}]"
            issues += _required(path, judgment, ("level", "verdict", "evidence_ids", "rationale", "confidence"), jloc)
            if not isinstance(judgment, dict):
                continue
            level, verdict = judgment.get("level"), judgment.get("verdict")
            seen_levels.append(level)
            if verdict not in VERDICTS:
                issues.append(_issue(path, f"{jloc}.verdict", "unknown verdict"))
            if not isinstance(judgment.get("rationale"), str) or not judgment.get("rationale"):
                issues.append(_issue(path, f"{jloc}.rationale", "must be a non-empty string"))
            if judgment.get("confidence") not in {"high", "medium", "low"}:
                issues.append(_issue(path, f"{jloc}.confidence", "must be high, medium, or low"))
            evidence_ids = judgment.get("evidence_ids")
            if not isinstance(evidence_ids, list) or any(not isinstance(item, str) for item in evidence_ids) or len(evidence_ids) != len(set(evidence_ids)) or any(not item for item in evidence_ids):
                issues.append(_issue(path, f"{jloc}.evidence_ids", "must contain unique non-empty artifact IDs"))
            if verdict in {"SUPPORTED", "CONTRADICTED"}:
                if not judgment.get("evidence_ids"):
                    issues.append(_issue(path, f"{jloc}.evidence_ids", "decisive verdict requires evidence"))
                if decisive is None and level in LEVELS:
                    decisive = (level, verdict)
                elif decisive is not None:
                    issues.append(_issue(path, jloc, "judgments must stop after first decisive verdict"))
        expected_prefix = list(LEVELS[: len(seen_levels)])
        if seen_levels != expected_prefix:
            issues.append(_issue(path, f"{loc}.judgments", "levels must be unique progressive prefix L0 through L3"))
        if decisive is None:
            if seen_levels != list(LEVELS) or final != "INSUFFICIENT" or minimum is not None:
                issues.append(_issue(path, loc, "unresolved claim requires L0-L3 INSUFFICIENT judgments, final INSUFFICIENT, and null minimum level"))
        elif final != decisive[1] or minimum != decisive[0]:
            issues.append(_issue(path, loc, "final verdict and minimum level must match first decisive judgment"))
    return issues


def validate_materiality_screening(path: Path, data: dict[str, Any]) -> list[Issue]:
    required = (
        "schema_version",
        "screening_id",
        "sample_id",
        "annotator_private_id",
        "annotation_round",
        "decision",
        "non_material_reason",
        "claims",
        "completed_at",
        "guide_version",
    )
    issues = _required(path, data, required, "")
    issues += _unexpected(path, data, set(required), "")
    if data.get("schema_version") != "eviscope.materiality-screening.v0.3":
        issues.append(_issue(path, "schema_version", "must identify materiality-screening schema v0.3"))
    if data.get("guide_version") != "v0.3":
        issues.append(_issue(path, "guide_version", "must identify annotation guide v0.3"))
    for field in ("screening_id", "sample_id", "annotator_private_id"):
        if not isinstance(data.get(field), str) or not data.get(field):
            issues.append(_issue(path, field, "must be a non-empty string"))
    if data.get("annotation_round") not in {"independent_a", "independent_b", "adjudication"}:
        issues.append(_issue(path, "annotation_round", "unknown Stage-S annotation round"))
    if _parse_time(data.get("completed_at")) is None:
        issues.append(_issue(path, "completed_at", "must be a timezone-aware ISO-8601 timestamp"))

    decision = data.get("decision")
    reason = data.get("non_material_reason")
    claims = data.get("claims")
    if not isinstance(claims, list):
        return issues + [_issue(path, "claims", "must be an array")]
    if decision == "NON_MATERIAL":
        if claims:
            issues.append(_issue(path, "claims", "NON_MATERIAL screening must contain zero claims"))
        if reason not in NON_MATERIAL_REASONS:
            issues.append(_issue(path, "non_material_reason", "must be a registered non-material reason"))
    elif decision == "MATERIAL":
        if not claims:
            issues.append(_issue(path, "claims", "MATERIAL screening requires at least one claim"))
        if reason is not None:
            issues.append(_issue(path, "non_material_reason", "MATERIAL screening requires a null reason"))
    else:
        issues.append(_issue(path, "decision", "must be MATERIAL or NON_MATERIAL"))

    claim_ids: set[str] = set()
    for claim_index, claim in enumerate(claims):
        loc = f"claims[{claim_index}]"
        claim_fields = ("claim_id", "normalized_text", "source_fragments")
        issues += _required(path, claim, claim_fields, loc)
        issues += _unexpected(path, claim, set(claim_fields), loc)
        if not isinstance(claim, dict):
            continue
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id:
            issues.append(_issue(path, f"{loc}.claim_id", "must be a non-empty string"))
        elif claim_id in claim_ids:
            issues.append(_issue(path, f"{loc}.claim_id", "duplicate claim_id"))
        else:
            claim_ids.add(claim_id)
        if not isinstance(claim.get("normalized_text"), str) or not claim.get("normalized_text"):
            issues.append(_issue(path, f"{loc}.normalized_text", "must be a non-empty string"))
        fragments = claim.get("source_fragments")
        if not isinstance(fragments, list) or not fragments:
            issues.append(_issue(path, f"{loc}.source_fragments", "must be a non-empty array"))
            continue
        previous_end = -1
        for fragment_index, fragment in enumerate(fragments):
            floc = f"{loc}.source_fragments[{fragment_index}]"
            fragment_fields = ("start", "end", "text")
            issues += _required(path, fragment, fragment_fields, floc)
            issues += _unexpected(path, fragment, set(fragment_fields), floc)
            if not isinstance(fragment, dict):
                continue
            start, end, text = fragment.get("start"), fragment.get("end"), fragment.get("text")
            if (
                not isinstance(start, int)
                or isinstance(start, bool)
                or not isinstance(end, int)
                or isinstance(end, bool)
                or start < 0
                or end <= start
            ):
                issues.append(_issue(path, floc, "requires integer offsets with 0 <= start < end"))
                continue
            if start < previous_end:
                issues.append(_issue(path, floc, "fragments must be ordered and non-overlapping"))
            previous_end = end
            if not isinstance(text, str) or not text:
                issues.append(_issue(path, f"{floc}.text", "must be a non-empty string"))
    return issues


def _validate_v03_verdict_claim(path: Path, claim: dict[str, Any], loc: str) -> list[Issue]:
    required_claim_fields = (
        "claim_id",
        "judgments",
        "final_verdict",
        "minimum_evidence_level",
        "disagreement_codes",
    )
    issues = _required(path, claim, required_claim_fields, loc)
    issues += _unexpected(
        path,
        claim,
        set(required_claim_fields) | {"issue_type", "adjudication_note"},
        loc,
    )
    codes = claim.get("disagreement_codes")
    if (
        not isinstance(codes, list)
        or any(not isinstance(code, str) for code in codes)
        or len(codes) != len(set(codes))
        or any(code not in DISAGREEMENT_CODES_V03 for code in codes)
    ):
        issues.append(_issue(path, f"{loc}.disagreement_codes", "must contain unique registered v0.3 disagreement codes"))
    issue_type = claim.get("issue_type")
    if issue_type is not None and (not isinstance(issue_type, str) or not issue_type):
        issues.append(_issue(path, f"{loc}.issue_type", "must be null or a non-empty string"))

    final = claim.get("final_verdict")
    minimum = claim.get("minimum_evidence_level")
    if final not in VERDICTS:
        issues.append(_issue(path, f"{loc}.final_verdict", "unknown final verdict"))
    if minimum is not None and minimum not in LEVELS:
        issues.append(_issue(path, f"{loc}.minimum_evidence_level", "must be L0-L3 or null"))

    judgments = claim.get("judgments")
    if not isinstance(judgments, list) or not judgments:
        return issues + [_issue(path, f"{loc}.judgments", "must be a non-empty progressive array")]
    seen_levels: list[Any] = []
    seen_verdicts: list[Any] = []
    decisive: tuple[str, str] | None = None
    for judgment_index, judgment in enumerate(judgments):
        jloc = f"{loc}.judgments[{judgment_index}]"
        judgment_fields = ("level", "verdict", "evidence_ids", "rationale", "confidence")
        issues += _required(path, judgment, judgment_fields, jloc)
        issues += _unexpected(path, judgment, set(judgment_fields), jloc)
        if not isinstance(judgment, dict):
            continue
        level, verdict = judgment.get("level"), judgment.get("verdict")
        seen_levels.append(level)
        seen_verdicts.append(verdict)
        if level not in LEVELS:
            issues.append(_issue(path, f"{jloc}.level", "unknown evidence level"))
        if verdict not in VERDICTS:
            issues.append(_issue(path, f"{jloc}.verdict", "unknown verdict"))
        evidence_ids = judgment.get("evidence_ids")
        if (
            not isinstance(evidence_ids, list)
            or any(not isinstance(item, str) or not item for item in evidence_ids)
            or len(evidence_ids) != len(set(evidence_ids))
        ):
            issues.append(_issue(path, f"{jloc}.evidence_ids", "must contain unique non-empty artifact IDs"))
        if not isinstance(judgment.get("rationale"), str) or not judgment.get("rationale"):
            issues.append(_issue(path, f"{jloc}.rationale", "must be a non-empty string"))
        if judgment.get("confidence") not in {"high", "medium", "low"}:
            issues.append(_issue(path, f"{jloc}.confidence", "must be high, medium, or low"))
        if decisive is not None:
            issues.append(_issue(path, jloc, "judgments must stop after first decisive verdict"))
        elif verdict in {"SUPPORTED", "CONTRADICTED"}:
            if not evidence_ids:
                issues.append(_issue(path, f"{jloc}.evidence_ids", "decisive verdict requires evidence"))
            if level in LEVELS:
                decisive = (level, verdict)

    if seen_levels != list(LEVELS[: len(seen_levels)]):
        issues.append(_issue(path, f"{loc}.judgments", "levels must be unique progressive prefix L0 through L3"))
    if decisive is None:
        if (
            seen_levels != list(LEVELS)
            or any(verdict != "INSUFFICIENT" for verdict in seen_verdicts)
            or final != "INSUFFICIENT"
            or minimum is not None
        ):
            issues.append(_issue(path, loc, "unresolved claim requires L0-L3 INSUFFICIENT judgments, final INSUFFICIENT, and null minimum level"))
    elif final != decisive[1] or minimum != decisive[0]:
        issues.append(_issue(path, loc, "final verdict and minimum level must match first decisive judgment"))
    return issues


def validate_annotation_v0_3(path: Path, data: dict[str, Any]) -> list[Issue]:
    required = (
        "schema_version",
        "sample_id",
        "screening_id",
        "screening_sha256",
        "annotator_private_id",
        "annotation_round",
        "claims",
        "completed_at",
        "guide_version",
    )
    issues = _required(path, data, required, "")
    issues += _unexpected(path, data, set(required), "")
    if data.get("schema_version") != "eviscope.annotation.v0.3":
        issues.append(_issue(path, "schema_version", "must identify annotation schema v0.3"))
    if data.get("guide_version") != "v0.3":
        issues.append(_issue(path, "guide_version", "must identify annotation guide v0.3"))
    for field in ("sample_id", "screening_id", "annotator_private_id"):
        if not isinstance(data.get(field), str) or not data.get(field):
            issues.append(_issue(path, field, "must be a non-empty string"))
    digest = data.get("screening_sha256")
    if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
        issues.append(_issue(path, "screening_sha256", "must be a lowercase 64-character SHA-256"))
    if data.get("annotation_round") not in {"independent_a", "independent_b", "reverse_audit", "adjudication"}:
        issues.append(_issue(path, "annotation_round", "unknown Stage-V annotation round"))
    if _parse_time(data.get("completed_at")) is None:
        issues.append(_issue(path, "completed_at", "must be a timezone-aware ISO-8601 timestamp"))
    claims = data.get("claims")
    if not isinstance(claims, list) or not claims:
        return issues + [_issue(path, "claims", "must be a non-empty array")]
    claim_ids: set[str] = set()
    for claim_index, claim in enumerate(claims):
        loc = f"claims[{claim_index}]"
        if not isinstance(claim, dict):
            issues.append(_issue(path, loc, "must be an object"))
            continue
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id:
            issues.append(_issue(path, f"{loc}.claim_id", "must be a non-empty string"))
        elif claim_id in claim_ids:
            issues.append(_issue(path, f"{loc}.claim_id", "duplicate claim_id"))
        else:
            claim_ids.add(claim_id)
        issues += _validate_v03_verdict_claim(path, claim, loc)
    return issues


def validate_pilot(path: Path, data: dict[str, Any]) -> list[Issue]:
    issues = _required(path, data, ("pilot_id", "status", "selection", "targets", "samples"), "")
    if data.get("status") not in {"template", "collecting", "frozen", "complete"}:
        issues.append(_issue(path, "status", "unknown pilot status"))
    selection = data.get("selection", {})
    issues += _required(path, selection, ("languages", "repository_count", "selection_rule"), "selection")
    if isinstance(selection, dict):
        languages = selection.get("languages")
        if not isinstance(languages, list) or not languages or any(not isinstance(item, str) for item in languages) or len(languages) != len(set(languages)) or any(item not in {"Python", "Java"} for item in languages):
            issues.append(_issue(path, "selection.languages", "requires unique Python/Java entries"))
        if (
            not isinstance(selection.get("repository_count"), int)
            or isinstance(selection.get("repository_count"), bool)
            or selection.get("repository_count", 0) < 1
        ):
            issues.append(_issue(path, "selection.repository_count", "must be positive"))
        if not isinstance(selection.get("selection_rule"), str) or not selection.get("selection_rule"):
            issues.append(_issue(path, "selection.selection_rule", "must be non-empty"))
    targets = data.get("targets", {})
    issues += _required(path, targets, ("comments_min", "comments_max", "claims_min"), "targets")
    if isinstance(targets, dict):
        values = [targets.get(key) for key in ("comments_min", "comments_max", "claims_min")]
        if not all(isinstance(value, int) and not isinstance(value, bool) for value in values):
            issues.append(_issue(path, "targets", "target counts must be integers"))
        elif targets.get("comments_min", 0) < 30 or targets.get("comments_max", 0) > 50 or targets.get("comments_max", 0) < targets.get("comments_min", 0):
            issues.append(_issue(path, "targets", "pilot requires 30-50 comments with max >= min"))
        if targets.get("claims_min", 0) < 60:
            issues.append(_issue(path, "targets.claims_min", "Gate 1 requires at least 60 claims"))
    if data.get("status") in {"frozen", "complete"} and not data.get("samples"):
        issues.append(_issue(path, "samples", "frozen/complete pilot cannot be empty"))
    samples = data.get("samples")
    if not isinstance(samples, list) or any(not isinstance(item, str) for item in samples) or len(samples) != len(set(samples)) or any(not item for item in samples):
        issues.append(_issue(path, "samples", "must contain unique non-empty sample IDs"))
    return issues


def validate_model_registry(path: Path, data: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    models = data.get("models")
    if not isinstance(models, list) or not models:
        return [_issue(path, "models", "must be a non-empty array")]
    ids: set[str] = set()
    for index, model in enumerate(models):
        loc = f"models[{index}]"
        issues += _required(path, model, ("registry_id", "role", "exact_model_id", "status", "temperature"), loc)
        if not isinstance(model, dict):
            continue
        registry_id = model.get("registry_id")
        if isinstance(registry_id, str):
            if registry_id in ids:
                issues.append(_issue(path, f"{loc}.registry_id", "duplicate registry ID"))
            ids.add(registry_id)
        else:
            issues.append(_issue(path, f"{loc}.registry_id", "must be a string"))
        if model.get("status") == "confirmed" and model.get("exact_model_id") in PLACEHOLDERS:
            issues.append(_issue(path, f"{loc}.exact_model_id", "confirmed model requires exact non-placeholder ID"))
        if model.get("status") not in {"unconfirmed", "confirmed", "disabled"}:
            issues.append(_issue(path, f"{loc}.status", "must be unconfirmed, confirmed, or disabled"))
        if model.get("role") not in {"judge", "generator", "retriever", "embedder"}:
            issues.append(_issue(path, f"{loc}.role", "unknown model role"))
        if not isinstance(model.get("temperature"), (int, float)) or isinstance(model.get("temperature"), bool) or model.get("temperature", -1) < 0:
            issues.append(_issue(path, f"{loc}.temperature", "must be a non-negative number"))
        credential_name = model.get("credential_env_var")
        if credential_name is not None and (not isinstance(credential_name, str) or ENV_NAME.fullmatch(credential_name) is None):
            issues.append(_issue(path, f"{loc}.credential_env_var", "must be an environment-variable name, never a value"))
        forbidden = {key for key in model if any(token in key.lower() for token in ("api_key_value", "password", "secret_value"))}
        if forbidden:
            issues.append(_issue(path, loc, f"forbidden secret-bearing keys: {sorted(forbidden)}"))
    return issues


def validate_gate(path: Path, data: dict[str, Any]) -> list[Issue]:
    issues = _required(path, data, ("gate", "overall_status", "criteria", "decision_rule"), "")
    criteria = data.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        return issues + [_issue(path, "criteria", "must be non-empty")]
    required_ids = {"annotator-a", "annotator-b", "adjudicator", "compute", "model-budget", "snapshot-tooling", "protocol"}
    ids = [item.get("id") for item in criteria if isinstance(item, dict)]
    if len(ids) != len(set(ids)):
        issues.append(_issue(path, "criteria", "criterion IDs must be unique"))
    for missing in sorted(required_ids - set(ids)):
        issues.append(_issue(path, "criteria", f"missing mandatory criterion {missing}"))
    complete_statuses = {"confirmed", "implemented"}
    allowed_statuses = complete_statuses | {"unconfirmed", "reported_available_not_profiled", "implemented_pending_real_pr_smoke"}
    # Completion words are criterion-specific. Personnel, compute, budget/model
    # access, and the real-PR smoke test require external confirmation; only the
    # protocol artifact itself is completed by implementation.
    required_completion = {
        "annotator-a": "confirmed",
        "annotator-b": "confirmed",
        "adjudicator": "confirmed",
        "compute": "confirmed",
        "model-budget": "confirmed",
        "snapshot-tooling": "confirmed",
        "protocol": "implemented",
    }
    for index, item in enumerate(criteria):
        loc = f"criteria[{index}]"
        issues += _required(path, item, ("id", "requirement", "status", "evidence"), loc)
        if not isinstance(item, dict):
            continue
        if item.get("status") not in allowed_statuses:
            issues.append(_issue(path, f"{loc}.status", "unknown criterion status"))
        if item.get("status") in complete_statuses and (not isinstance(item.get("evidence"), str) or not item.get("evidence", "").strip()):
            issues.append(_issue(path, f"{loc}.evidence", "completed criterion requires auditable evidence"))
        criterion_id = item.get("id")
        expected = required_completion.get(criterion_id)
        if expected is not None and item.get("status") in complete_statuses and item.get("status") != expected:
            issues.append(_issue(path, f"{loc}.status", f"criterion {criterion_id} can complete only as {expected}"))
    by_id = {item.get("id"): item for item in criteria if isinstance(item, dict)}
    incomplete = any(
        not isinstance(by_id.get(criterion_id), dict)
        or by_id[criterion_id].get("status") != expected
        for criterion_id, expected in required_completion.items()
    )
    if data.get("overall_status") == "passed" and incomplete:
        issues.append(_issue(path, "overall_status", "cannot pass while a mandatory criterion is incomplete"))
    if data.get("overall_status") not in {"passed", "blocked_pending_confirmation", "failed"}:
        issues.append(_issue(path, "overall_status", "unknown overall gate status"))
    return issues


def validate_resources(path: Path, data: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    people = data.get("people")
    if not isinstance(people, list):
        return [_issue(path, "people", "must be an array")]
    required_roles = {"annotator-a", "annotator-b", "adjudicator"}
    found = {person.get("role_id") for person in people if isinstance(person, dict) and isinstance(person.get("role_id"), str)}
    for role in sorted(required_roles - found):
        issues.append(_issue(path, "people", f"missing required role {role}"))
    if len(found) != len(people):
        issues.append(_issue(path, "people", "role IDs must be present and unique"))
    for index, person in enumerate(people):
        if not isinstance(person, dict):
            continue
        loc = f"people[{index}]"
        issues += _required(path, person, ("role_id", "role", "name_or_private_id", "languages", "commitment_hours", "conflict_of_interest_reviewed", "status"), loc)
        if person.get("status") not in {"unconfirmed", "confirmed", "declined"}:
            issues.append(_issue(path, f"{loc}.status", "unknown person status"))
        if person.get("status") == "confirmed":
            if person.get("name_or_private_id") in PLACEHOLDERS or not person.get("name_or_private_id"):
                issues.append(_issue(path, f"{loc}.name_or_private_id", "confirmed person requires a private identifier"))
            if not isinstance(person.get("commitment_hours"), (int, float)) or person.get("commitment_hours", 0) <= 0:
                issues.append(_issue(path, f"{loc}.commitment_hours", "confirmed person requires positive committed hours"))
            if person.get("conflict_of_interest_reviewed") is not True:
                issues.append(_issue(path, f"{loc}.conflict_of_interest_reviewed", "must be true before confirmation"))
    for section in ("compute", "budget", "data_governance"):
        if not isinstance(data.get(section), dict):
            issues.append(_issue(path, section, "must be an object"))
    return issues


def validate_experiment_config(path: Path, data: dict[str, Any]) -> list[Issue]:
    issues = _required(
        path,
        data,
        ("evidence_levels", "verdicts", "retrieval_budget", "primary_temperature", "repeat_subset_fraction", "splitting_unit", "external_web_evidence_allowed", "future_artifacts_allowed", "release_rule"),
        "",
    )
    if data.get("evidence_levels") != list(LEVELS):
        issues.append(_issue(path, "evidence_levels", "must be exactly L0-L3 in order"))
    verdicts = data.get("verdicts")
    if not isinstance(verdicts, list) or any(not isinstance(item, str) for item in verdicts) or set(verdicts) != VERDICTS:
        issues.append(_issue(path, "verdicts", "must contain the three registered verdicts"))
    if data.get("external_web_evidence_allowed") is not False or data.get("future_artifacts_allowed") is not False:
        issues.append(_issue(path, "", "Gate 0 protocol forbids external web and future artifacts"))
    budget = data.get("retrieval_budget")
    issues += _required(path, budget, ("max_actions", "max_chunks", "max_input_tokens", "status"), "retrieval_budget")
    if isinstance(budget, dict):
        for field in ("max_actions", "max_chunks", "max_input_tokens"):
            value = budget.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                issues.append(_issue(path, f"retrieval_budget.{field}", "must be a positive integer"))
        if budget.get("status") not in {"provisional_until_pilot_freeze", "frozen"}:
            issues.append(_issue(path, "retrieval_budget.status", "must be provisional_until_pilot_freeze or frozen"))
    temperature = data.get("primary_temperature")
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool) or temperature < 0:
        issues.append(_issue(path, "primary_temperature", "must be a non-negative number"))
    fraction = data.get("repeat_subset_fraction")
    if not isinstance(fraction, (int, float)) or isinstance(fraction, bool) or not 0 < fraction <= 1:
        issues.append(_issue(path, "repeat_subset_fraction", "must be in (0, 1]"))
    if data.get("splitting_unit") != "repository":
        issues.append(_issue(path, "splitting_unit", "must be repository to prevent cross-repository split leakage"))
    expected_release_rule = {
        "all_material_supported": "accept",
        "any_material_contradicted": "reject",
        "otherwise": "abstain",
    }
    if data.get("release_rule") != expected_release_rule:
        issues.append(_issue(path, "release_rule", "must match the registered accept/reject/abstain rule"))
    return issues


def validate_server_environment(path: Path, data: dict[str, Any]) -> list[Issue]:
    required = ("collected_at_utc", "os", "cpu", "memory", "gpus", "tools", "scheduler", "secret_policy")
    issues = _required(path, data, required, "")
    if _parse_time(data.get("collected_at_utc")) is None:
        issues.append(_issue(path, "collected_at_utc", "must be a timezone-aware ISO-8601 timestamp"))
    for field in ("os", "cpu", "memory", "tools", "scheduler"):
        if not isinstance(data.get(field), dict):
            issues.append(_issue(path, field, "must be an object"))
    if not isinstance(data.get("gpus"), list):
        issues.append(_issue(path, "gpus", "must be an array"))
    expected_policy = "no environment values, credentials, usernames, hostnames, IPs, SSH config, or process command lines collected"
    if data.get("secret_policy") != expected_policy:
        issues.append(_issue(path, "secret_policy", "unexpected secret collection policy"))
    forbidden_keys = re.compile(r"(user|host|ip|address|credential|password|secret|token|key_value)", re.I)
    def walk(value: Any, location: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key != "secret_policy" and forbidden_keys.search(str(key)):
                    issues.append(_issue(path, f"{location}.{key}".strip("."), "forbidden identifying or secret-bearing field"))
                walk(child, f"{location}.{key}".strip("."))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{location}[{index}]")
    walk(data, "")
    return issues


def validate_stage_s_synthetic_smoke_protocol(
    path: Path, data: dict[str, Any]
) -> list[Issue]:
    required = (
        "schema_version", "status", "guide_version", "input_scope",
        "selected_sample_ids", "alignment_rule", "temperature", "max_tokens", "purpose",
    )
    issues = _required(path, data, required, "")
    issues += _unexpected(path, data, set(required), "")
    if data.get("status") != "engineering_only_not_annotation_not_gold":
        issues.append(_issue(path, "status", "must remain engineering-only and not gold"))
    if data.get("guide_version") != "v0.3":
        issues.append(_issue(path, "guide_version", "must identify guide v0.3"))
    if data.get("input_scope") != "fabricated synthetic fixture only":
        issues.append(_issue(path, "input_scope", "must be restricted to fabricated synthetic fixtures"))
    sample_ids = data.get("selected_sample_ids")
    if not isinstance(sample_ids, list) or not 1 <= len(sample_ids) <= 16:
        issues.append(_issue(path, "selected_sample_ids", "must contain 1-16 sample IDs"))
    elif (
        len(set(sample_ids)) != len(sample_ids)
        or any(not isinstance(value, str) or SAMPLE_ID.fullmatch(value) is None for value in sample_ids)
    ):
        issues.append(_issue(path, "selected_sample_ids", "must contain unique valid sample IDs"))
    if not isinstance(data.get("alignment_rule"), str) or not data.get("alignment_rule"):
        issues.append(_issue(path, "alignment_rule", "must be a non-empty string"))
    temperature = data.get("temperature")
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool) or temperature != 0:
        issues.append(_issue(path, "temperature", "engineering smoke temperature must be zero"))
    max_tokens = data.get("max_tokens")
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens < 1:
        issues.append(_issue(path, "max_tokens", "must be a positive integer"))
    if not isinstance(data.get("purpose"), str) or not data.get("purpose"):
        issues.append(_issue(path, "purpose", "must be a non-empty string"))
    return issues


def validate_swrbench_adaptation_protocol(
    path: Path, data: dict[str, Any]
) -> list[Issue]:
    required = (
        "schema_version", "status", "source", "separation",
        "model_visible_allowlist", "model_hidden_fields",
        "conversion_requirements", "split_and_deduplication", "readiness",
    )
    issues = _required(path, data, required, "")
    issues += _unexpected(path, data, set(required), "")
    if data.get("status") != "candidate_external_validation_source_not_gold":
        issues.append(_issue(path, "status", "must remain an external candidate and not gold"))

    source = data.get("source")
    source_fields = {
        "repository_url", "commit_sha", "dataset_path", "dataset_sha256",
        "source_code_license", "license_sha256",
    }
    issues += _required(path, source, tuple(sorted(source_fields)), "source")
    issues += _unexpected(path, source, source_fields, "source")
    if isinstance(source, dict):
        if SHA40.fullmatch(str(source.get("commit_sha", ""))) is None:
            issues.append(_issue(path, "source.commit_sha", "must be a 40-character SHA"))
        for field in ("dataset_sha256", "license_sha256"):
            if SHA256.fullmatch(str(source.get(field, ""))) is None:
                issues.append(_issue(path, f"source.{field}", "must be a SHA-256 digest"))
        if source.get("repository_url") != "https://github.com/ZZR0/SWRench.git":
            issues.append(_issue(path, "source.repository_url", "must identify the audited official source"))

    separation = data.get("separation")
    separation_fields = {
        "dataset_layer", "merge_with_eviscope_core",
        "inherit_swr_labels_as_eviscope_gold",
        "estimate_natural_prevalence_from_balanced_swr", "report_results_separately",
    }
    issues += _required(path, separation, tuple(sorted(separation_fields)), "separation")
    issues += _unexpected(path, separation, separation_fields, "separation")
    if isinstance(separation, dict) and (
        separation.get("merge_with_eviscope_core") is not False
        or separation.get("inherit_swr_labels_as_eviscope_gold") is not False
        or separation.get("estimate_natural_prevalence_from_balanced_swr") is not False
        or separation.get("report_results_separately") is not True
    ):
        issues.append(_issue(path, "separation", "must preserve Core/SWR separation and prohibit label inheritance"))

    expected_visible = {
        "instance_id", "repo", "base_commit", "created_at", "pr_title",
        "pr_statement", "pr_commits[].sha", "pr_commits[].message", "pr_commits[].diff",
    }
    visible = data.get("model_visible_allowlist")
    if not isinstance(visible, list) or set(visible) != expected_visible or len(visible) != len(expected_visible):
        issues.append(_issue(path, "model_visible_allowlist", "must equal the registered pre-review field allowlist"))

    hidden = data.get("model_hidden_fields")
    mandatory_hidden = {
        "change_introduced", "changes", "pr_timeline", "all_commits",
        "pr_commits[].author_email", "pr_commits[].committer_email",
        "change_discussion", "change_resolve_info", "post_review_commits_and_fixes",
    }
    if not isinstance(hidden, list) or not mandatory_hidden.issubset(set(hidden)):
        issues.append(_issue(path, "model_hidden_fields", "must hide labels, discussion, timeline, identities, and future fixes"))

    conversion = data.get("conversion_requirements")
    required_true = {
        "deterministic_comment_event_linkage_required",
        "review_time_snapshot_verification_required",
        "identity_and_email_stripping_required",
        "atomic_claim_resegmentation_required",
        "eviscope_materiality_rescreening_required",
        "independent_a_b_annotation_required",
        "third_human_c_for_all_disagreements_required",
    }
    required_false = {"model_output_may_be_human_gold"}
    conversion_fields = required_true | required_false
    issues += _required(path, conversion, tuple(sorted(conversion_fields)), "conversion_requirements")
    issues += _unexpected(path, conversion, conversion_fields, "conversion_requirements")
    if isinstance(conversion, dict) and (
        any(conversion.get(field) is not True for field in required_true)
        or any(conversion.get(field) is not False for field in required_false)
    ):
        issues.append(_issue(path, "conversion_requirements", "must require EviScope human and leakage controls"))

    split = data.get("split_and_deduplication")
    split_fields = {
        "split_unit", "exact_pr_overlap_check_required",
        "near_duplicate_check_required", "cross_layer_overlap_report_required",
    }
    issues += _required(path, split, tuple(sorted(split_fields)), "split_and_deduplication")
    issues += _unexpected(path, split, split_fields, "split_and_deduplication")
    if isinstance(split, dict) and (
        split.get("split_unit") != "repository"
        or any(split.get(field) is not True for field in split_fields - {"split_unit"})
    ):
        issues.append(_issue(path, "split_and_deduplication", "must use repository splits and all overlap checks"))

    readiness = data.get("readiness")
    readiness_fields = {
        "source_integrity_verified", "schema_audited", "formal_sample_selection_frozen",
        "converted_annotations_exist", "eligible_for_model_inference", "eligible_for_gold_analysis",
    }
    issues += _required(path, readiness, tuple(sorted(readiness_fields)), "readiness")
    issues += _unexpected(path, readiness, readiness_fields, "readiness")
    if isinstance(readiness, dict) and (
        readiness.get("source_integrity_verified") is not True
        or readiness.get("schema_audited") is not True
        or any(readiness.get(field) is not False for field in readiness_fields - {"source_integrity_verified", "schema_audited"})
    ):
        issues.append(_issue(path, "readiness", "source is audited but must remain unselected, unconverted, and ineligible"))
    return issues


def validate_swrbench_review_time_policy(path: Path, data: dict[str, Any]) -> list[Issue]:
    required = (
        "schema_version", "status", "inputs", "review_time_cutoff",
        "integrity_requirements", "metadata_redaction", "output_controls",
    )
    issues = _required(path, data, required, "")
    issues += _unexpected(path, data, set(required), "")
    if data.get("status") != "candidate_reconstruction_policy_not_inference_not_gold":
        issues.append(_issue(path, "status", "must remain reconstruction-only, non-inference, and not gold"))
    inputs = data.get("inputs")
    input_fields = {"dataset_sha256", "adaptation_protocol_sha256", "candidate_adapter_manifest_sha256"}
    issues += _required(path, inputs, tuple(sorted(input_fields)), "inputs")
    issues += _unexpected(path, inputs, input_fields, "inputs")
    if isinstance(inputs, dict):
        for field in input_fields:
            if SHA256.fullmatch(str(inputs.get(field, ""))) is None:
                issues.append(_issue(path, f"inputs.{field}", "must be a SHA-256 digest"))
    cutoff = data.get("review_time_cutoff")
    cutoff_fields = {
        "rule", "event_types", "commit_time_field", "commit_time_interpretation",
        "missing_cutoff_action", "any_commit_after_cutoff_action", "non_contiguous_safe_prefix_action",
    }
    issues += _required(path, cutoff, tuple(sorted(cutoff_fields)), "review_time_cutoff")
    issues += _unexpected(path, cutoff, cutoff_fields, "review_time_cutoff")
    if isinstance(cutoff, dict) and (
        cutoff.get("event_types") != ["comment", "review", "review_comment"]
        or cutoff.get("commit_time_interpretation") != "necessary_not_sufficient_for_pr_visibility"
        or any(cutoff.get(field) != "quarantine_entire_pr" for field in (
            "missing_cutoff_action", "any_commit_after_cutoff_action", "non_contiguous_safe_prefix_action"
        ))
    ):
        issues.append(_issue(path, "review_time_cutoff", "must use the registered first-human cutoff and quarantine rules"))
    integrity = data.get("integrity_requirements")
    true_fields = {
        "unique_timeline_commit_match_required", "message_diff_text_and_diff_equality_required",
        "repository_commit_object_verification_required", "base_and_ancestry_verification_required",
        "independent_diff_reconstruction_required",
    }
    integrity_fields = true_fields | {"source_timestamps_alone_complete_verification"}
    issues += _required(path, integrity, tuple(sorted(integrity_fields)), "integrity_requirements")
    issues += _unexpected(path, integrity, integrity_fields, "integrity_requirements")
    if isinstance(integrity, dict) and (
        any(integrity.get(field) is not True for field in true_fields)
        or integrity.get("source_timestamps_alone_complete_verification") is not False
    ):
        issues.append(_issue(path, "integrity_requirements", "must require independent repository reconstruction"))
    redaction = data.get("metadata_redaction")
    redaction_fields = {
        "email_pattern", "email_replacement", "redacted_fields", "identity_trailer_prefixes",
        "identity_trailer_replacement", "diff_patch_policy",
    }
    issues += _required(path, redaction, tuple(sorted(redaction_fields)), "metadata_redaction")
    issues += _unexpected(path, redaction, redaction_fields, "metadata_redaction")
    if isinstance(redaction, dict) and (
        redaction.get("redacted_fields") != ["pr_title", "pr_statement", "pr_commits[].message"]
        or redaction.get("diff_patch_policy") != "preserve_code_literals_and_keep_inference_ineligible"
    ):
        issues.append(_issue(path, "metadata_redaction", "must redact metadata without silently changing code diffs"))
    controls = data.get("output_controls")
    control_fields = {
        "sampling_performed", "model_inference_eligible", "gold_analysis_eligible",
        "swr_labels_exported", "post_review_fields_exported",
    }
    issues += _required(path, controls, tuple(sorted(control_fields)), "output_controls")
    issues += _unexpected(path, controls, control_fields, "output_controls")
    if isinstance(controls, dict) and any(controls.get(field) is not False for field in control_fields):
        issues.append(_issue(path, "output_controls", "all candidate output permissions must remain false"))
    return issues


def validate_l1_evidence_package(path: Path, data: dict[str, Any]) -> list[Issue]:
    required = (
        "schema_version",
        "status",
        "review_head_sha",
        "merge_base_sha",
        "l0_sha256",
        "snapshot_metadata_sha256",
        "generation_method",
        "future_artifacts_allowed",
        "comment_count",
        "file_count",
        "artifact_count",
        "artifacts",
    )
    issues = _required(path, data, required, "")
    issues += _unexpected(path, data, set(required), "")
    if data.get("status") not in {"engineering_smoke_not_gold", "synthetic_smoke_not_gold", "review_time_l1_not_gold"}:
        issues.append(_issue(path, "status", "must remain non-gold L1 evidence"))
    if data.get("future_artifacts_allowed") is not False:
        issues.append(_issue(path, "future_artifacts_allowed", "must be false"))
    if data.get("status") == "synthetic_smoke_not_gold":
        if data.get("generation_method") != "synthetic-not-reconstructed":
            issues.append(_issue(path, "generation_method", "synthetic smoke must identify synthetic-not-reconstructed"))
    elif data.get("generation_method") != "git-show-review-time-no-checkout":
        issues.append(_issue(path, "generation_method", "must be git-show-review-time-no-checkout"))
    for field in ("review_head_sha", "merge_base_sha"):
        if SHA40.fullmatch(str(data.get(field, ""))) is None:
            issues.append(_issue(path, field, "must be a lowercase 40-character SHA"))
    if data.get("review_head_sha") == data.get("merge_base_sha"):
        issues.append(_issue(path, "review_head_sha", "must differ from merge_base_sha"))
    for field in ("l0_sha256", "snapshot_metadata_sha256"):
        if SHA256.fullmatch(str(data.get(field, ""))) is None:
            issues.append(_issue(path, field, "must be a SHA-256 digest"))
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return issues + [_issue(path, "artifacts", "must contain at least one artifact")]
    if data.get("artifact_count") != len(artifacts):
        issues.append(_issue(path, "artifact_count", "must equal artifacts length"))
    ids: set[str] = set()
    artifact_fields = {
        "artifact_id",
        "level",
        "kind",
        "path",
        "comment_id",
        "source_locator",
        "sha256",
        "available",
        "unavailable_reason",
        "review_time_commit",
        "relative_path",
        "byte_length",
        "binary",
    }
    for index, artifact in enumerate(artifacts):
        loc = f"artifacts[{index}]"
        issues += _required(path, artifact, tuple(sorted(artifact_fields)), loc)
        issues += _unexpected(path, artifact, artifact_fields, loc)
        if not isinstance(artifact, dict):
            continue
        aid = artifact.get("artifact_id")
        if isinstance(aid, str) and aid:
            if aid in ids:
                issues.append(_issue(path, f"{loc}.artifact_id", "duplicate artifact_id"))
            ids.add(aid)
        else:
            issues.append(_issue(path, f"{loc}.artifact_id", "must be a non-empty string"))
        if artifact.get("level") != "L1":
            issues.append(_issue(path, f"{loc}.level", "must be L1"))
        if artifact.get("kind") not in LEVEL_KINDS["L1"]:
            issues.append(_issue(path, f"{loc}.kind", "must be a registered L1 kind"))
        commit = artifact.get("review_time_commit")
        if commit not in {data.get("merge_base_sha"), data.get("review_head_sha")}:
            issues.append(_issue(path, f"{loc}.review_time_commit", "must be the snapshot merge base or review head"))
        available = artifact.get("available")
        if available is True:
            if SHA256.fullmatch(str(artifact.get("sha256", ""))) is None:
                issues.append(_issue(path, f"{loc}.sha256", "available artifact requires SHA-256"))
            if artifact.get("unavailable_reason") is not None:
                issues.append(_issue(path, f"{loc}.unavailable_reason", "must be null when available"))
            if data.get("status") != "synthetic_smoke_not_gold" and (
                not isinstance(artifact.get("relative_path"), str) or not artifact.get("relative_path")
            ):
                issues.append(_issue(path, f"{loc}.relative_path", "available reconstructed artifact requires a relative path"))
        elif available is False:
            if artifact.get("sha256") is not None or artifact.get("relative_path") is not None:
                issues.append(_issue(path, loc, "unavailable artifact cannot carry content hash or path"))
            if not isinstance(artifact.get("unavailable_reason"), str) or not artifact.get("unavailable_reason"):
                issues.append(_issue(path, f"{loc}.unavailable_reason", "required when unavailable"))
        else:
            issues.append(_issue(path, f"{loc}.available", "must be true or false"))
    return issues


VALIDATORS: dict[str, Callable[[Path, dict[str, Any]], list[Issue]]] = {
    "eviscope.dataset-manifest.v0.1": validate_dataset,
    "eviscope.annotation.v0.2": validate_annotation,
    "eviscope.materiality-screening.v0.3": validate_materiality_screening,
    "eviscope.annotation.v0.3": validate_annotation_v0_3,
    "eviscope.pilot-manifest.v0.1": validate_pilot,
    "eviscope.model-registry.v0.1": validate_model_registry,
    "eviscope.gate-status.v0.1": validate_gate,
    "eviscope.resources.v0.1": validate_resources,
    "eviscope.experiment-config.v0.1": validate_experiment_config,
    "eviscope.server-environment.v0.1": validate_server_environment,
    "eviscope.stage-s-synthetic-smoke-protocol.v0.1": validate_stage_s_synthetic_smoke_protocol,
    "eviscope.swrbench-adaptation-protocol.v0.1": validate_swrbench_adaptation_protocol,
    "eviscope.swrbench-review-time-policy.v0.1": validate_swrbench_review_time_policy,
    "eviscope.l1-evidence-package.v0.1": validate_l1_evidence_package,
}


def validate_file(path: Path) -> list[Issue]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return [_issue(path, "", f"cannot read: {exc}")]
    except json.JSONDecodeError as exc:
        return [_issue(path, "", f"invalid JSON at {exc.lineno}:{exc.colno}: {exc.msg}")]
    if not isinstance(data, dict):
        return [_issue(path, "", "root must be an object")]
    version = data.get("schema_version")
    if not isinstance(version, str):
        return [_issue(path, "schema_version", "missing schema version")]
    validator = VALIDATORS.get(version)
    if validator is None:
        return [_issue(path, "schema_version", f"unsupported schema version {version!r}")]
    return validator(path, data)
