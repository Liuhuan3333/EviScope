from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from adapt_swrbench_candidates import adapt
from stage_s_tools import StageSToolingError


class SWRBenchAdapterTest(unittest.TestCase):
    def _write_fixture(self, root: Path, future_fix_overlap: bool = False) -> tuple[Path, Path]:
        intro = "1" * 40
        resolution = intro if future_fix_overlap else "2" * 40
        change = {
            "change_type": "F.2",
            "change_introducing": {"commit_sha": intro, "code_snippet": "private"},
            "change_discussion": {
                "discussion_summary": "private",
                "first_mention_timestamp": "2025-01-02T00:00:00Z",
                "original_reviewer_comment": "This can fail.\nPlease guard it.",
            },
            "change_resolve_info": {
                "commit_sha": resolution,
                "code_snippet": "future private",
                "resolution_explanation": "future private",
            },
        }
        item = {
            "repo": "org/repo",
            "instance_id": "org__repo-1",
            "pr_title": "Title",
            "pr_statement": "Statement",
            "change_introduced": True,
            "base_commit": "0" * 40,
            "created_at": "2025-01-01T00:00:00Z",
            "changes": [change],
            "pr_commits": [{
                "type": "commit",
                "sha": intro,
                "message": "change",
                "author": "identity",
                "author_email": "private@example.com",
                "author_raw_date": "private",
                "author_date": "2025-01-01T00:00:00Z",
                "committer": "identity",
                "committer_email": "private@example.com",
                "raw_date": "private",
                "date": "2025-01-01T00:00:00Z",
                "diff_text": "private duplicate",
                "diff": [{"file": "a.py", "patch": "@@ -1 +1 @@\n-old\n+new"}],
            }],
            "pr_timeline": [{
                "type": "review_comment",
                "id": 7,
                "user": "identity",
                "body": "This can fail.  Please guard it.",
                "created_at": "2025-01-02T00:00:00Z",
            }],
            "all_commits": [{"sha": resolution, "message": "future"}],
        }
        dataset = root / "source.jsonl"
        dataset.write_text(json.dumps(item) + "\n", encoding="utf-8")
        digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
        protocol = root / "protocol.json"
        protocol.write_text(json.dumps({
            "schema_version": "eviscope.swrbench-adaptation-protocol.v0.1",
            "status": "candidate_external_validation_source_not_gold",
            "source": {"dataset_sha256": digest},
        }), encoding="utf-8")
        return dataset, protocol

    def test_sanitizes_and_links_without_labels_or_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset, protocol = self._write_fixture(root)
            output = root / "converted"
            result = adapt(dataset, protocol, output)
            candidate_text = (output / "candidate_inputs.jsonl").read_text(encoding="utf-8")
            audit = json.loads((output / "private_linkage_audit.jsonl").read_text(encoding="utf-8"))
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(1, result["deterministically_linked_change_count"])
        for forbidden in ("change_introduced", "changes", "author_email", "committer_email", "private@example.com"):
            self.assertNotIn(forbidden, candidate_text)
        self.assertEqual("WHITESPACE_NORMALIZED_UNIQUE", audit["linkage"]["method"])
        self.assertFalse(manifest["controls"]["sampling_performed"])
        self.assertFalse(manifest["controls"]["model_inference_eligible"])
        self.assertFalse(manifest["controls"]["gold_analysis_eligible"])

    def test_quarantines_future_fix_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset, protocol = self._write_fixture(root, future_fix_overlap=True)
            output = root / "converted"
            result = adapt(dataset, protocol, output)
            audit = json.loads((output / "private_linkage_audit.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(1, result["resolution_commit_in_model_input_count"])
        self.assertTrue(audit["resolution_commit_in_model_input"])
        self.assertTrue(audit["status"].startswith("quarantined"))

    def test_matches_semantically_equal_timezone_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset, protocol = self._write_fixture(root)
            item = json.loads(dataset.read_text(encoding="utf-8"))
            item["pr_timeline"][0]["created_at"] = "2025-01-02T08:00:00+08:00"
            dataset.write_text(json.dumps(item) + "\n", encoding="utf-8")
            data = json.loads(protocol.read_text(encoding="utf-8"))
            data["source"]["dataset_sha256"] = hashlib.sha256(dataset.read_bytes()).hexdigest()
            protocol.write_text(json.dumps(data), encoding="utf-8")
            output = root / "converted"
            result = adapt(dataset, protocol, output)
        self.assertEqual(1, result["deterministically_linked_change_count"])

    def test_reports_but_does_not_mutate_code_email_literals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset, protocol = self._write_fixture(root)
            item = json.loads(dataset.read_text(encoding="utf-8"))
            item["pr_commits"][0]["diff"][0]["patch"] += "\n+address = 'test@example.com'"
            dataset.write_text(json.dumps(item) + "\n", encoding="utf-8")
            data = json.loads(protocol.read_text(encoding="utf-8"))
            data["source"]["dataset_sha256"] = hashlib.sha256(dataset.read_bytes()).hexdigest()
            protocol.write_text(json.dumps(data), encoding="utf-8")
            output = root / "converted"
            result = adapt(dataset, protocol, output)
            candidate = (output / "candidate_inputs.jsonl").read_text(encoding="utf-8")
        self.assertEqual(1, result["email_like_occurrence_counts_in_visible_free_text"]["diff_patch"])
        self.assertIn("test@example.com", candidate)

    def test_rejects_hash_mismatch_and_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset, protocol = self._write_fixture(root)
            output = root / "converted"
            output.mkdir()
            with self.assertRaisesRegex(StageSToolingError, "overwrite"):
                adapt(dataset, protocol, output)
            output.rmdir()
            data = json.loads(protocol.read_text(encoding="utf-8"))
            data["source"]["dataset_sha256"] = "0" * 64
            protocol.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(StageSToolingError, "SHA-256"):
                adapt(dataset, protocol, output)


if __name__ == "__main__":
    unittest.main()
