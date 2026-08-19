from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from l1_evidence import L1EvidenceError, build, python_enclosing_symbol


class L1EvidenceTest(unittest.TestCase):
    def make_repo(self, root: Path) -> tuple[Path, str, str]:
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "fixture@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Fixture"], check=True)
        path = repo / "sample.py"
        path.write_text(
            "def keep():\n    return 1\n\ndef target():\n    value = 1\n    return value\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(repo), "add", "sample.py"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
        base = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        path.write_text(
            "def keep():\n    return 1\n\ndef target():\n    value = 2\n    return value\n",
            encoding="utf-8",
        )
        (repo / "added.py").write_text("def added():\n    return 3\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "sample.py", "added.py"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "review head"], check=True)
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        return repo, base, head

    def write_snapshot(self, root: Path, repo: Path, base: str, head: str, comments: list[dict]) -> Path:
        diff = subprocess.run(
            ["git", "-C", str(repo), "diff", "--binary", "--no-ext-diff", "--no-textconv", "--no-renames", base, head],
            check=True,
            capture_output=True,
        ).stdout
        names = subprocess.run(
            ["git", "-C", str(repo), "diff", "--name-only", "-z", "--no-ext-diff", "--no-textconv", "--no-renames", base, head],
            check=True,
            capture_output=True,
        ).stdout
        changed = [item.decode("utf-8") for item in names.split(b"\0") if item]
        snapshot = root / "snapshot" / head
        snapshot.mkdir(parents=True)
        (snapshot / "L0.diff").write_bytes(diff)
        metadata = {
            "schema_version": "eviscope.review-snapshot.v0.1",
            "final_base_sha": base,
            "merge_base_sha": base,
            "review_head_sha": head,
            "diff_mode": "git-diff-binary-no-renames-no-ext-diff-no-textconv",
            "changed_file_count": len(changed),
            "changed_files": changed,
            "l0_sha256": __import__("hashlib").sha256(diff).hexdigest(),
            "comments": comments,
        }
        (snapshot / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        return snapshot

    def test_extracts_file_sides_and_enclosing_function(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, base, head = self.make_repo(root)
            snapshot = self.write_snapshot(
                root,
                repo,
                base,
                head,
                [{"comment_id": 7, "created_at": "2026-01-01T00:00:00Z", "path": "sample.py"}],
            )
            comments = root / "comments.json"
            comments.write_text(
                json.dumps([{
                    "id": 7,
                    "path": "sample.py",
                    "original_line": 5,
                    "side": "RIGHT",
                    "original_commit_id": head,
                }]),
                encoding="utf-8",
            )
            output = root / "l1"
            package = build(repo, snapshot, output, comments_path=comments, comment_id=7)
            kinds = {item["kind"]: item for item in package["artifacts"]}
            self.assertTrue(kinds["file_before"]["available"])
            self.assertTrue(kinds["file_after"]["available"])
            self.assertTrue(kinds["enclosing_symbol"]["available"])
            before = (output / kinds["file_before"]["relative_path"]).read_text(encoding="utf-8")
            after = (output / kinds["file_after"]["relative_path"]).read_text(encoding="utf-8")
            self.assertIn("value = 1", before)
            self.assertIn("value = 2", after)
            symbol = json.loads((output / kinds["enclosing_symbol"]["relative_path"]).read_text(encoding="utf-8"))
            self.assertEqual("target", symbol["name"])
            self.assertEqual("function", symbol["kind"])
            self.assertIn("value = 2", symbol["text"])
            self.assertNotIn("def keep", symbol["text"])
            head_before = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
            ).stdout.strip()
            self.assertEqual(head, head_before)

    def test_records_missing_before_for_added_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, base, head = self.make_repo(root)
            snapshot = self.write_snapshot(
                root,
                repo,
                base,
                head,
                [{"comment_id": 8, "created_at": "2026-01-01T00:00:00Z", "path": "added.py"}],
            )
            comments = root / "comments.json"
            comments.write_text(
                json.dumps([{
                    "id": 8,
                    "path": "added.py",
                    "original_line": 1,
                    "side": "RIGHT",
                    "original_commit_id": head,
                }]),
                encoding="utf-8",
            )
            package = build(repo, snapshot, root / "l1", comments_path=comments)
            before = next(item for item in package["artifacts"] if item["kind"] == "file_before")
            after = next(item for item in package["artifacts"] if item["kind"] == "file_after")
            self.assertFalse(before["available"])
            self.assertEqual("path_absent_at_review_time_commit", before["unavailable_reason"])
            self.assertTrue(after["available"])

    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, base, head = self.make_repo(root)
            snapshot = self.write_snapshot(
                root,
                repo,
                base,
                head,
                [{"comment_id": 7, "created_at": "2026-01-01T00:00:00Z", "path": "sample.py"}],
            )
            output = root / "l1"
            build(repo, snapshot, output)
            with self.assertRaisesRegex(L1EvidenceError, "Refusing to overwrite"):
                build(repo, snapshot, output)

    def test_rejects_l0_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, base, head = self.make_repo(root)
            snapshot = self.write_snapshot(
                root,
                repo,
                base,
                head,
                [{"comment_id": 7, "created_at": "2026-01-01T00:00:00Z", "path": "sample.py"}],
            )
            (snapshot / "L0.diff").write_bytes(b"tampered")
            with self.assertRaisesRegex(L1EvidenceError, "l0_sha256"):
                build(repo, snapshot, root / "l1")

    def test_enclosing_symbol_prefers_innermost_function(self):
        source = (
            "class Outer:\n"
            "    def inner(self):\n"
            "        value = 1\n"
            "        return value\n"
        )
        symbol = python_enclosing_symbol(source, 3)
        assert symbol is not None
        self.assertEqual("inner", symbol["name"])
        self.assertEqual("function", symbol["kind"])


if __name__ == "__main__":
    unittest.main()
