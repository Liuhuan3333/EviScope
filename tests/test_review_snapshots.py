from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_review_snapshots import SnapshotError, build


class ReviewSnapshotTest(unittest.TestCase):
    def make_repo(self, root: Path) -> tuple[Path, str, str]:
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "fixture@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Fixture"], check=True)
        path = repo / "sample.py"
        path.write_text("value = 1\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "sample.py"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
        base = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        path.write_text("value = 2\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "commit", "-qam", "review head"], check=True)
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        return repo, base, head

    def write_comments(self, path: Path, head: str) -> None:
        path.write_text(json.dumps([{
            "id": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "path": "sample.py",
            "original_commit_id": head,
            "commit_id": head,
        }]), encoding="utf-8")

    def test_builds_hashed_snapshot_from_original_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, base, head = self.make_repo(root)
            comments = root / "comments.json"
            self.write_comments(comments, head)
            output = root / "snapshots"
            manifest = build(repo, comments, base, output)
            self.assertEqual(1, manifest["snapshot_count"])
            self.assertEqual(1, manifest["comment_count"])
            metadata = json.loads((output / head / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(head, metadata["review_head_sha"])
            self.assertEqual(base, metadata["merge_base_sha"])
            self.assertEqual(64, len(metadata["l0_sha256"]))
            self.assertIn(b"value = 2", (output / head / "L0.diff").read_bytes())

    def test_refuses_to_overwrite_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, base, head = self.make_repo(root)
            comments = root / "comments.json"
            self.write_comments(comments, head)
            output = root / "snapshots"
            build(repo, comments, base, output)
            with self.assertRaisesRegex(SnapshotError, "Refusing to overwrite"):
                build(repo, comments, base, output)


if __name__ == "__main__":
    unittest.main()
