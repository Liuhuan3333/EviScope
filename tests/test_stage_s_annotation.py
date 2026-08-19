from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from eviscope_validation import validate_materiality_screening
from prepare_stage_s_calibration import prepare
from stage_s_annotation import (
    StageSAnnotationError,
    export_session,
    load_blinded_packet,
    make_material_record,
    make_non_material_record,
    open_session,
    store_record,
)
from stage_s_tools import StageSToolingError, sha256_path


class StageSAnnotationTest(unittest.TestCase):
    def write_packet(self, root: Path) -> Path:
        path = root / "stage_s_inputs.json"
        path.write_text(json.dumps({
            "schema_version": "eviscope.stage-s-input-packet.v0.1",
            "selection_id": "synthetic-stage-s-tool-test",
            "status": "synthetic_fixture_not_gold",
            "guide_version": "v0.3",
            "evidence_visible": False,
            "sample_count": 2,
            "samples": [
                {"sample_id": "T001", "comment_text": "This can return null, so the caller can fail."},
                {"sample_id": "T002", "comment_text": "Thanks for the update."},
            ],
        }), encoding="utf-8")
        return path

    def test_packet_rejects_context_or_prediction_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_packet(Path(directory))
            packet = json.loads(path.read_text(encoding="utf-8"))
            packet["samples"][0]["repository"] = "forbidden/repository"
            path.write_text(json.dumps(packet), encoding="utf-8")
            with self.assertRaisesRegex(StageSAnnotationError, "only sample_id and comment_text"):
                load_blinded_packet(path)

    def test_checkpoint_resume_freeze_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self.write_packet(root)
            output = root / "annotator-a"
            packet, checkpoint = open_session(inputs, output, "annotator-A-private", "independent_a")
            material = make_material_record(packet, checkpoint, "T001", packet["samples"][0]["comment_text"], [
                {"normalized_text": "The function can return null.", "source_fragments": [{"text": "This can return null"}]},
                {"normalized_text": "The caller can fail.", "source_fragments": [{"text": "the caller can fail"}]},
            ])
            store_record(packet, checkpoint, output, "T001", material)
            non_material = make_non_material_record(
                packet, checkpoint, "T002", "GREETING_OR_ACKNOWLEDGEMENT"
            )
            store_record(packet, checkpoint, output, "T002", non_material)

            resumed_packet, resumed = open_session(
                inputs, output, "annotator-A-private", "independent_a"
            )
            self.assertEqual(2, len(resumed["records"]))
            hashes = export_session(resumed_packet, resumed, output)
            manifest_path = output / "frozen_export" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("human_annotation_not_gold_until_adjudicated", manifest["status"])
            self.assertEqual(hashes, manifest["records"])
            for relative, digest in hashes.items():
                record_path = output / "frozen_export" / relative
                self.assertEqual(digest, sha256_path(record_path))
                record = json.loads(record_path.read_text(encoding="utf-8"))
                self.assertEqual([], validate_materiality_screening(record_path, record))
            with self.assertRaisesRegex(StageSAnnotationError, "frozen"):
                export_session(resumed_packet, resumed, output)

    def test_resume_rejects_different_annotator_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self.write_packet(root)
            output = root / "annotator-a"
            open_session(inputs, output, "annotator-A-private", "independent_a")
            with self.assertRaisesRegex(StageSAnnotationError, "does not match session"):
                open_session(inputs, output, "annotator-B-private", "independent_b")

    def test_rejects_ambiguous_fragment_and_incomplete_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self.write_packet(root)
            output = root / "annotator-a"
            packet, checkpoint = open_session(inputs, output, "annotator-A-private", "independent_a")
            with self.assertRaisesRegex(StageSAnnotationError, "exactly once"):
                make_material_record(
                    packet, checkpoint, "T001", "same same", [
                        {"normalized_text": "Repeated.", "source_fragments": [{"text": "same"}]}
                    ]
                )
            with self.assertRaisesRegex(StageSAnnotationError, "incomplete"):
                export_session(packet, checkpoint, output)

    @unittest.skipUnless(
        (ROOT / "data/private/pr-candidates/maven-11639/raw/inline_comments.json").exists(),
        "private Maven non-Pilot fixture is unavailable",
    )
    def test_maven_nonpilot_packet_is_blinded_and_loadable(self):
        comments = json.loads(
            (ROOT / "data/private/pr-candidates/maven-11639/raw/inline_comments.json").read_text(encoding="utf-8")
        )
        pull = json.loads(
            (ROOT / "data/private/pr-candidates/maven-11639/raw/pull.json").read_text(encoding="utf-8")
        )
        reviewer_comments = [
            comment for comment in comments
            if comment["user"]["id"] != pull["user"]["id"] and comment["user"].get("type") != "Bot"
        ]
        self.assertEqual(3, len(reviewer_comments))
        packet = {
            "schema_version": "eviscope.stage-s-input-packet.v0.1",
            "selection_id": "maven-11639-nonpilot-tool-check",
            "status": "training_not_gold",
            "guide_version": "v0.3",
            "evidence_visible": False,
            "sample_count": len(reviewer_comments),
            "samples": [
                {"sample_id": f"M{index:03d}", "comment_text": comment["body"]}
                for index, comment in enumerate(reviewer_comments, start=1)
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = root / "stage_s_inputs.json"
            inputs.write_text(json.dumps(packet), encoding="utf-8")
            loaded, checkpoint = open_session(
                inputs, root / "maven-session", "tool-check-only", "independent_a"
            )
        self.assertEqual(3, loaded["sample_count"])
        self.assertEqual({}, checkpoint["records"])
        self.assertTrue(all(set(sample) == {"sample_id", "comment_text"} for sample in loaded["samples"]))

    def test_calibration_packet_filters_blinds_sorts_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            comments = root / "inline_comments.json"
            comments.write_text(json.dumps([
                {"id": 30, "body": "Reviewer two.", "user": {"id": 3, "type": "User"}},
                {"id": 10, "body": "Author reply.", "user": {"id": 1, "type": "User"}},
                {"id": 20, "body": "Reviewer one.", "user": {"id": 2, "type": "User"}},
                {"id": 40, "body": "Bot note.", "user": {"id": 4, "type": "Bot"}},
            ]), encoding="utf-8")
            pull = root / "pull.json"
            pull.write_text(json.dumps({"user": {"id": 1}}), encoding="utf-8")
            output = root / "calibration"
            hashes = prepare(
                comments, pull, output, "fixture-calibration", "2026-08-18T00:00:00+00:00"
            )
            packet = load_blinded_packet(output / "stage_s_inputs.json")
            self.assertEqual(["Reviewer one.", "Reviewer two."], [
                sample["comment_text"] for sample in packet["samples"]
            ])
            self.assertEqual({"sample_id", "comment_text"}, set(packet["samples"][0]))
            self.assertEqual(sha256_path(output / "stage_s_inputs.json"), hashes["stage_s_inputs.json"])
            with self.assertRaisesRegex(StageSToolingError, "pre-existing"):
                prepare(comments, pull, output, "fixture-calibration", "later")


if __name__ == "__main__":
    unittest.main()
