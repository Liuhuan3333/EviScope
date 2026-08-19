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

from prepare_swrbench_review_time_candidates import prepare
from stage_s_tools import StageSToolingError


class SWRBenchReviewTimeTest(unittest.TestCase):
    def _fixture(self, root: Path, late: bool = False) -> tuple[Path, Path, Path, Path]:
        sha = "1" * 40
        commit = {
            "sha": sha, "message": "Change\nCo-authored-by: Name <person@example.com>",
            "date": "2025-01-03T00:00:00Z" if late else "2025-01-01T00:00:00Z",
            "diff_text": "raw", "diff": [{"file": "a.py", "patch": "+x='test@example.com'"}],
        }
        item = {
            "instance_id": "org__repo-1", "repo": "org/repo", "base_commit": "0" * 40,
            "pr_title": "Title", "pr_statement": "Contact list@example.com",
            "change_introduced": False, "changes": [], "created_at": "2025-01-01T00:00:00Z",
            "pr_commits": [commit], "all_commits": [],
            "pr_timeline": [
                {"type": "commit", **commit},
                {"type": "review", "created_at": "2025-01-02T00:00:00Z", "body": "review"},
            ],
        }
        dataset = root / "source.jsonl"; dataset.write_text(json.dumps(item)+"\n", encoding="utf-8")
        adaptation = root / "adaptation.json"; adaptation.write_text("{}\n", encoding="utf-8")
        adapter = root / "adapter.json"; adapter.write_text(json.dumps({"controls":{"model_inference_eligible":False}})+"\n", encoding="utf-8")
        policy = root / "policy.json"
        policy.write_text(json.dumps({
            "schema_version":"eviscope.swrbench-review-time-policy.v0.1",
            "status":"candidate_reconstruction_policy_not_inference_not_gold",
            "inputs":{
                "dataset_sha256":hashlib.sha256(dataset.read_bytes()).hexdigest(),
                "adaptation_protocol_sha256":hashlib.sha256(adaptation.read_bytes()).hexdigest(),
                "candidate_adapter_manifest_sha256":hashlib.sha256(adapter.read_bytes()).hexdigest(),
            },
            "metadata_redaction":{
                "email_pattern":r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
                "email_replacement":"[EMAIL_REDACTED]",
                "identity_trailer_prefixes":["Co-authored-by"],
                "identity_trailer_replacement":"[IDENTITY_TRAILER_REMOVED]"
            },
            "output_controls":{
                "sampling_performed":False,"model_inference_eligible":False,
                "gold_analysis_eligible":False,"swr_labels_exported":False,
                "post_review_fields_exported":False
            }
        }),encoding="utf-8")
        return dataset, adaptation, adapter, policy

    def test_redacts_metadata_preserves_diff_and_remains_ineligible(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); inputs=self._fixture(root); output=root/"out"
            result=prepare(*inputs,output)
            candidate=(output/"candidate_inputs.jsonl").read_text(encoding="utf-8")
            manifest=json.loads((output/"manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(1,result["timestamp_consistent_candidate_count"])
        self.assertNotIn("person@example.com",candidate)
        self.assertNotIn("list@example.com",candidate)
        self.assertIn("test@example.com",candidate)
        self.assertIn("[IDENTITY_TRAILER_REMOVED]",candidate)
        self.assertFalse(manifest["controls"]["model_inference_eligible"])
        self.assertFalse(manifest["controls"]["repository_reconstruction_complete"])

    def test_quarantines_entire_pr_when_first_commit_is_late(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); inputs=self._fixture(root,late=True); output=root/"out"
            result=prepare(*inputs,output)
            audit=json.loads((output/"review_time_audit.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(0,result["timestamp_consistent_candidate_count"])
        self.assertEqual(1,result["quarantined_record_count"])
        self.assertEqual("COMMIT_AFTER_FIRST_HUMAN_INTERACTION",audit["reason"])

    def test_rejects_input_hash_mismatch_and_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); inputs=self._fixture(root); output=root/"out"; output.mkdir()
            with self.assertRaisesRegex(StageSToolingError,"overwrite"):
                prepare(*inputs,output)
            output.rmdir(); inputs[0].write_text("{}\n",encoding="utf-8")
            with self.assertRaisesRegex(StageSToolingError,"hashes"):
                prepare(*inputs,output)


if __name__ == "__main__":
    unittest.main()
