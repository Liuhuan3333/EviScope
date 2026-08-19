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
from l2_evidence import (
    L2EvidenceError,
    build,
    extract_comment_paths,
    is_test_path,
    resolve_comment_path,
)


class L2EvidenceTest(unittest.TestCase):
    def make_repo(self, root: Path) -> tuple[Path, str, str]:
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "fixture@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Fixture"], check=True)
        pkg = repo / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "target.py").write_text(
            "import helper\n\ndef target():\n    return helper.run()\n",
            encoding="utf-8",
        )
        (pkg / "helper.py").write_text("def run():\n    return 1\n", encoding="utf-8")
        (repo / "tests").mkdir()
        (repo / "tests" / "test_target.py").write_text(
            "from pkg.target import target\n\ndef test_target():\n    assert target() == 1\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
        base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        (pkg / "target.py").write_text(
            "import helper\n\ndef target():\n    return helper.run() + 1\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(repo), "add", "pkg/target.py"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "head"], check=True)
        head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        return repo, base, head

    def write_snapshot(self, root: Path, repo: Path, base: str, head: str) -> Path:
        diff = subprocess.check_output(
            ["git", "-C", str(repo), "diff", "--binary", "--no-ext-diff", "--no-textconv", "--no-renames", base, head]
        )
        names = subprocess.check_output(
            ["git", "-C", str(repo), "diff", "--name-only", "-z", "--no-ext-diff", "--no-textconv", "--no-renames", base, head]
        )
        changed = [item.decode("utf-8") for item in names.split(b"\0") if item]
        if "tests/test_target.py" not in changed:
            changed.append("tests/test_target.py")
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
            "comments": [{"comment_id": 1, "created_at": "2026-01-01T00:00:00Z", "path": "pkg/target.py"}],
        }
        (snapshot / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        return snapshot

    def test_resolves_comment_mentions_and_builds_l2(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, base, head = self.make_repo(root)
            snapshot = self.write_snapshot(root, repo, base, head)
            comments = [
                {
                    "id": 1,
                    "body": "Please check helper.py for the callee contract.",
                    "path": "pkg/target.py",
                    "original_line": 4,
                    "side": "RIGHT",
                    "created_at": "2026-01-01T00:00:00Z",
                    "original_commit_id": head,
                }
            ]
            comments_path = root / "comments.json"
            comments_path.write_text(json.dumps(comments), encoding="utf-8")
            l1_out = root / "l1"
            build_l1(repo, snapshot, l1_out, comments_path=comments_path, comment_id=1)
            l2_out = root / "l2"
            package = build(repo, snapshot, l1_out, comments_path, 1, l2_out)
            self.assertEqual(package["schema_version"], "eviscope.l2-evidence-package.v0.1")
            kinds = {item["kind"] for item in package["artifacts"] if item["available"]}
            self.assertIn("import", kinds)
            self.assertIn("definition", kinds)
            self.assertIn("test", kinds)
            definition = next(
                item for item in package["artifacts"] if item["kind"] == "definition" and item["available"]
            )
            self.assertEqual(definition["path"], "pkg/helper.py")
            with self.assertRaises(L2EvidenceError):
                build(repo, snapshot, l1_out, comments_path, 1, l2_out)

    def test_helpers(self):
        self.assertEqual(extract_comment_paths("see helper.py and pkg/foo.py"), ["helper.py", "pkg/foo.py"])
        paths = ["pkg/target.py", "pkg/helper.py", "tests/test_target.py"]
        self.assertEqual(resolve_comment_path("helper.py", "pkg/target.py", paths), "pkg/helper.py")
        self.assertTrue(is_test_path("tests/test_target.py"))
        self.assertFalse(is_test_path("pkg/target.py"))


if __name__ == "__main__":
    unittest.main()
