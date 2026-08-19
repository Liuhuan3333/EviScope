from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from audit_comment_anchors import build_audit
from freeze_stage_s_selection import freeze
from run_stage_s_model_smoke import run_smoke
from stage_s_tools import (
    StageSToolingError,
    align_verbatim_fragments,
    sha256_path,
    validate_fragment_offsets,
)
from verify_frozen_hashes import verify


class FragmentAlignerTest(unittest.TestCase):
    def test_aligns_unique_unicode_fragment(self):
        comment = "前缀：返回值可能为空。"
        aligned = align_verbatim_fragments(comment, [{"text": "返回值可能为空"}])
        self.assertEqual("返回值可能为空", comment[aligned[0]["start"]:aligned[0]["end"]])

    def test_rejects_repeated_fragment(self):
        with self.assertRaisesRegex(StageSToolingError, "exactly once"):
            align_verbatim_fragments("same then same", [{"text": "same"}])

    def test_rejects_missing_fragment(self):
        with self.assertRaisesRegex(StageSToolingError, "observed 0"):
            align_verbatim_fragments("original", [{"text": "mutated"}])

    def test_rejects_wrong_offsets(self):
        with self.assertRaisesRegex(StageSToolingError, "do not reproduce"):
            validate_fragment_offsets("abcdef", [{"text": "bcd", "start": 2, "end": 5}])


class AnchorAuditTest(unittest.TestCase):
    def _write_fixture(self, root: Path) -> tuple[Path, Path, Path, Path]:
        snapshots = root / "snapshots"
        heads = ("1" * 40, "2" * 40)
        diff = b"diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n"
        diff_hash = __import__("hashlib").sha256(diff).hexdigest()
        for head in heads:
            directory = snapshots / head
            directory.mkdir(parents=True)
            (directory / "L0.diff").write_bytes(diff)
        comments = [
            {
                "id": 10,
                "body": "Please check this.",
                "diff_hunk": "",
                "original_commit_id": heads[0],
                "path": "a.py",
                "line": None,
                "original_line": 1,
                "side": "RIGHT",
                "user": {"id": 200, "login": "reviewer", "type": "User"},
            },
            {
                "id": 11,
                "body": "new",
                "diff_hunk": "@@ -1 +1 @@\n-old\n+new",
                "original_commit_id": heads[1],
                "path": "a.py",
                "line": 1,
                "original_line": 1,
                "side": "RIGHT",
                "user": {"id": 200, "login": "reviewer", "type": "User"},
            },
        ]
        comments_path = root / "comments.json"
        comments_path.write_text(json.dumps(comments), encoding="utf-8")
        pull_path = root / "pull.json"
        pull_path.write_text(json.dumps({"user": {"id": 100}}), encoding="utf-8")
        manifest = {
            "schema_version": "eviscope.review-snapshot-manifest.v0.1",
            "comment_source_sha256": sha256_path(comments_path),
            "snapshot_count": 2,
            "comment_count": 2,
            "snapshots": [
                {
                    "schema_version": "eviscope.review-snapshot.v0.1",
                    "review_head_sha": head,
                    "merge_base_sha": str(index + 3) * 40,
                    "l0_sha256": diff_hash,
                    "changed_files": ["a.py"],
                    "comments": [{"comment_id": 10 + index}],
                }
                for index, head in enumerate(heads)
            ],
        }
        manifest_path = snapshots / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return comments_path, pull_path, manifest_path, snapshots

    def test_empty_hunk_uses_api_coordinate_and_equivalent_snapshots_remain_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self._write_fixture(Path(directory))
            audit = build_audit(*paths)
        self.assertEqual(2, audit["record_count"])
        self.assertEqual("API_LINE_COORDINATE", audit["records"][0]["anchor_method"])
        self.assertNotEqual(audit["records"][0]["review_head_sha"], audit["records"][1]["review_head_sha"])
        self.assertEqual(audit["records"][0]["evidence_sha256"], audit["records"][1]["evidence_sha256"])


class FreezeSelectionTest(unittest.TestCase):
    def test_freezes_new_directory_with_receipt_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            comments_path = root / "comments.json"
            comments_path.write_text(json.dumps([{"id": 7, "body": "A material statement."}]), encoding="utf-8")
            audit_path = root / "audit.json"
            audit_path.write_text(json.dumps({
                "source_comment_sha256": sha256_path(comments_path),
                "records": [{
                    "comment_id": 7,
                    "role": "HUMAN_REVIEWER",
                    "anchor_valid": True,
                    "reviewer_actor_id": "R001",
                    "review_head_sha": "1" * 40,
                    "merge_base_sha": "2" * 40,
                    "evidence_sha256": "3" * 64,
                    "path": "a.py",
                    "anchor_method": "EXACT_HUNK",
                }],
            }), encoding="utf-8")
            config_path = root / "config.json"
            config_path.write_text(json.dumps({
                "selection_id": "fixture-selection",
                "seed": "registered-before-selection",
                "guide_version": "fixture-only",
                "generated_at": "2026-01-01T00:00:00+00:00",
                "per_repository": 1,
                "repositories": [{
                    "repository_id": "fixture-repo",
                    "audit_path": str(audit_path),
                    "comments_path": str(comments_path),
                }],
            }), encoding="utf-8")
            output = root / "frozen"
            hashes = freeze(config_path, output)
            stage = json.loads((output / "stage_s_inputs.json").read_text(encoding="utf-8"))
            receipt = json.loads((output / "freeze_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual("pre_gate_candidate_not_gold", stage["status"])
            self.assertFalse(stage["evidence_visible"])
            self.assertEqual(hashes, receipt["outputs"])
            with self.assertRaisesRegex(StageSToolingError, "pre-existing"):
                freeze(config_path, output)


class HashVerifierTest(unittest.TestCase):
    def test_reports_match_and_mismatch_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frozen.bin"
            path.write_bytes(b"frozen")
            correct = sha256_path(path)
            self.assertTrue(verify([(correct, path)])[0]["match"])
            self.assertFalse(verify([("0" * 64, path)])[0]["match"])


class ModelSmokeRunnerTest(unittest.TestCase):
    def test_preserves_raw_output_and_marks_result_not_gold(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = root / "inputs.json"
            protocol = root / "protocol.json"
            prompt = root / "prompt.txt"
            inputs.write_text(json.dumps({
                "selection_id": "fixture",
                "evidence_visible": False,
                "samples": [{"sample_id": "S001", "comment_text": "This returns null."}],
            }), encoding="utf-8")
            protocol.write_text(json.dumps({"alignment_rule": "exactly once"}), encoding="utf-8")
            prompt.write_text("Return JSON.", encoding="utf-8")
            raw = json.dumps({
                "decision": "MATERIAL",
                "non_material_reason": None,
                "claims": [{
                    "claim_id": "C1",
                    "normalized_text": "Return may be null.",
                    "source_fragments": [{"text": "returns null"}],
                }],
            })

            def requester(endpoint, payload, timeout):
                return {
                    "choices": [{"message": {"content": raw}, "finish_reason": "stop"}],
                    "usage": {"total_tokens": 10},
                }

            result = run_smoke(
                inputs, protocol, prompt, ["S001"], "http://127.0.0.1:1", "fixture-model", 0, 100, 1, requester
            )
        self.assertEqual("engineering_smoke_not_annotation_not_gold", result["status"])
        self.assertEqual(raw, result["records"][0]["raw_output"])
        self.assertTrue(result["records"][0]["alignment_valid"])


if __name__ == "__main__":
    unittest.main()
