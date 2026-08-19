from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from l1_evidence import build as build_l1
from l2_evidence import build as build_l2
from l3_evidence import L3EvidenceError, build, extract_issue_numbers


class L3EvidenceTest(unittest.TestCase):
    def make_repo(self, root: Path) -> tuple[Path, str, str]:
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "fixture@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Fixture"], check=True)
        (repo / "README.md").write_text("# fixture\n", encoding="utf-8")
        pkg = repo / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "target.py").write_text("def target():\n    return 1\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
        base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        (pkg / "target.py").write_text("def target():\n    return 2\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "pkg/target.py"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "head"], check=True)
        head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        return repo, base, head

    def write_snapshot(self, root: Path, repo: Path, base: str, head: str) -> Path:
        diff = subprocess.check_output(
            ["git", "-C", str(repo), "diff", "--binary", "--no-ext-diff", "--no-textconv", "--no-renames", base, head]
        )
        snapshot = root / "snapshot" / head
        snapshot.mkdir(parents=True)
        (snapshot / "L0.diff").write_bytes(diff)
        metadata = {
            "schema_version": "eviscope.review-snapshot.v0.1",
            "final_base_sha": base,
            "merge_base_sha": base,
            "review_head_sha": head,
            "diff_mode": "git-diff-binary-no-renames-no-ext-diff-no-textconv",
            "changed_file_count": 1,
            "changed_files": ["pkg/target.py"],
            "l0_sha256": __import__("hashlib").sha256(diff).hexdigest(),
            "comments": [{"comment_id": 1, "created_at": "2026-01-02T00:00:00Z", "path": "pkg/target.py"}],
        }
        (snapshot / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        return snapshot

    def packages(self, root: Path, repo: Path, snapshot: Path, comments_path: Path) -> tuple[Path, Path]:
        l1_out = root / "l1"
        build_l1(repo, snapshot, l1_out, comments_path=comments_path, comment_id=1)
        l2_out = root / "l2"
        build_l2(repo, snapshot, l1_out, comments_path, 1, l2_out)
        return l1_out, l2_out

    def test_review_time_docs_history_and_future_pr_body(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, base, head = self.make_repo(root)
            snapshot = self.write_snapshot(root, repo, base, head)
            comments = [
                {
                    "id": 1,
                    "body": "See also #99 for the original report.",
                    "path": "pkg/target.py",
                    "original_line": 2,
                    "side": "RIGHT",
                    "created_at": "2026-01-02T00:00:00Z",
                    "original_commit_id": head,
                }
            ]
            comments_path = root / "comments.json"
            comments_path.write_text(json.dumps(comments), encoding="utf-8")
            _l1, l2_out = self.packages(root, repo, snapshot, comments_path)
            raw = root / "raw"
            raw.mkdir()
            (raw / "pull.json").write_text(
                json.dumps(
                    {
                        "number": 12,
                        "title": "change target",
                        "body": "Fixes #99",
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-03T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            (raw / "issues").mkdir()
            (raw / "issues" / "99.json").write_text(
                json.dumps(
                    {
                        "number": 99,
                        "title": "bug",
                        "body": "broken",
                        "created_at": "2025-12-01T00:00:00Z",
                        "updated_at": "2026-01-01T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            out = root / "l3"
            package = build(repo, snapshot, l2_out, comments_path, 1, raw, out)
            kinds = {item["kind"]: item for item in package["artifacts"]}
            self.assertEqual(kinds["pr_description"]["available"], False)
            self.assertEqual(
                kinds["pr_description"]["unavailable_reason"],
                "frozen_pull_json_updated_after_review_time",
            )
            self.assertTrue(kinds["issue"]["available"])
            self.assertTrue(kinds["repository_documentation"]["available"])
            self.assertEqual(kinds["repository_documentation"]["path"], "README.md")
            self.assertTrue(kinds["history"]["available"])
            with self.assertRaises(L3EvidenceError):
                build(repo, snapshot, l2_out, comments_path, 1, raw, out)

    def test_available_pr_when_updated_before_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, base, head = self.make_repo(root)
            snapshot = self.write_snapshot(root, repo, base, head)
            comments = [
                {
                    "id": 1,
                    "body": "looks good",
                    "path": "pkg/target.py",
                    "original_line": 2,
                    "side": "RIGHT",
                    "created_at": "2026-01-02T00:00:00Z",
                    "original_commit_id": head,
                }
            ]
            comments_path = root / "comments.json"
            comments_path.write_text(json.dumps(comments), encoding="utf-8")
            _l1, l2_out = self.packages(root, repo, snapshot, comments_path)
            raw = root / "raw"
            raw.mkdir()
            (raw / "pull.json").write_text(
                json.dumps(
                    {
                        "number": 12,
                        "title": "change target",
                        "body": "safe body",
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-01T12:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            package = build(repo, snapshot, l2_out, comments_path, 1, raw, root / "l3")
            pr = next(item for item in package["artifacts"] if item["kind"] == "pr_description")
            self.assertTrue(pr["available"])

    def test_issue_helpers(self):
        self.assertEqual(extract_issue_numbers("see #12 and (#99)", exclude=12), [99])


if __name__ == "__main__":
    unittest.main()
