from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swrbench_reconstruction import (  # noqa: E402
    SWRReconstructionError,
    load_candidates,
    repo_slug,
    run_verification,
    verify_candidate,
)


class SWRBenchReconstructionTest(unittest.TestCase):
    def _init_repo(self, repo: Path) -> tuple[str, str]:
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "fixture@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Fixture"], check=True)
        (repo / "sample.py").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "sample.py"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
        base = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        (repo / "sample.py").write_text("base\nchanged\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "sample.py"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "head"], check=True)
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        return base, head

    def test_repo_slug(self) -> None:
        self.assertEqual("pytest-dev__pytest", repo_slug("pytest-dev/pytest"))

    def test_verify_candidate_passes_for_matching_clone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "org__repo"
            base, head = self._init_repo(repo)
            candidate = {
                "instance_id": "org__repo-1",
                "repo": "org/repo",
                "base_commit": base,
                "pr_commits": [
                    {
                        "sha": head,
                        "message": "head",
                        "diff": [{"file": "sample.py", "patch": "@@"}],
                    }
                ],
            }
            audit = verify_candidate(candidate, root)
            self.assertTrue(audit["verified"])
            self.assertIsNotNone(audit["reconstructed_l0_sha256"])
            self.assertEqual(["sample.py"], _swr_files_from_audit(audit, candidate))

    def test_verify_candidate_reports_missing_clone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = {
                "instance_id": "org__repo-1",
                "repo": "org/repo",
                "base_commit": "0" * 40,
                "pr_commits": [{"sha": "1" * 40, "message": "x", "diff": [{"file": "a.py", "patch": ""}]}],
            }
            audit = verify_candidate(candidate, root)
            self.assertFalse(audit["verified"])
            self.assertIn("CLONE_MISSING", audit["failures"])

    def test_verify_candidate_detects_changed_file_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "org__repo"
            base, head = self._init_repo(repo)
            candidate = {
                "instance_id": "org__repo-1",
                "repo": "org/repo",
                "base_commit": base,
                "pr_commits": [
                    {
                        "sha": head,
                        "message": "head",
                        "diff": [{"file": "missing.py", "patch": "@@"}],
                    }
                ],
            }
            audit = verify_candidate(candidate, root)
            self.assertFalse(audit["verified"])
            self.assertIn("CHANGED_FILE_SET_MISMATCH", audit["failures"])

    def test_run_verification_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "org__repo"
            base, head = self._init_repo(repo)
            candidate = {
                "schema_version": "eviscope.swrbench-review-time-candidates.v0.1",
                "status": "timestamp_consistent_requires_repository_verification_not_inference_not_gold",
                "instance_id": "org__repo-1",
                "repo": "org/repo",
                "base_commit": base,
                "review_time_cutoff": "2025-01-01T00:00:00+00:00",
                "pr_title": "t",
                "pr_statement": "s",
                "pr_commits": [
                    {
                        "sha": head,
                        "message": "head",
                        "diff": [{"file": "sample.py", "patch": "@@"}],
                    }
                ],
            }
            candidates = root / "candidates.jsonl"
            candidates.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
            review_manifest = root / "review-time-manifest.json"
            review_manifest.write_text(json.dumps({"controls": {}}) + "\n", encoding="utf-8")
            policy = ROOT / "configs/swrbench_review_time_policy_v0.1.json"
            output = root / "out"
            manifest = run_verification(candidates, review_manifest, policy, root, output)
            self.assertEqual(1, manifest["summary"]["verified_count"])
            self.assertTrue((output / "reconstruction_audit.jsonl").is_file())
            self.assertFalse(manifest["controls"]["model_inference_eligible"])

    def test_load_candidates_rejects_non_pending_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "status": "quarantined_not_gold",
                        "instance_id": "x",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(SWRReconstructionError):
                load_candidates(path)

    def test_run_verification_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "out"
            output.mkdir()
            with self.assertRaises(SWRReconstructionError):
                run_verification(
                    ROOT / "configs/swrbench_adaptation_protocol_v0.1.json",
                    ROOT / "configs/swrbench_review_time_policy_v0.1.json",
                    ROOT / "configs/swrbench_review_time_policy_v0.1.json",
                    root,
                    output,
                )


def _swr_files_from_audit(audit: dict, candidate: dict) -> list[str]:
    del audit
    from swrbench_reconstruction import _swr_changed_files

    return _swr_changed_files(candidate)


if __name__ == "__main__":
    unittest.main()
