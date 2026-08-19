from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stage_v_annotation import (  # noqa: E402
    StageVAnnotationError,
    build_annotation_record,
    export_session,
    finalize_claim_verdict,
    load_stage_v_packet,
    open_session,
    store_record,
)


class StageVAnnotationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = ROOT / "tests/fixtures/stage_v_inputs.synthetic.json"

    def test_progressive_finalize(self) -> None:
        judgments = [
            {
                "level": "L0",
                "verdict": "INSUFFICIENT",
                "evidence_ids": [],
                "rationale": "Diff alone is not enough.",
                "confidence": "high",
            },
            {
                "level": "L1",
                "verdict": "SUPPORTED",
                "evidence_ids": ["synthetic-file"],
                "rationale": "File snapshot supports the claim.",
                "confidence": "high",
            },
        ]
        final, minimum = finalize_claim_verdict(judgments)
        self.assertEqual("SUPPORTED", final)
        self.assertEqual("L1", minimum)

    def test_session_export(self) -> None:
        packet = load_stage_v_packet(self.fixture)
        sample = packet["samples"][0]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "annotator"
            _, checkpoint = open_session(self.fixture, output, "synthetic-v-not-a-person", "independent_a")
            claim_results = [
                {
                    "claim_id": claim["claim_id"],
                    "judgments": [
                        {
                            "level": "L0",
                            "verdict": "INSUFFICIENT",
                            "evidence_ids": [],
                            "rationale": "Synthetic diff insufficient.",
                            "confidence": "high",
                        },
                        {
                            "level": "L1",
                            "verdict": "SUPPORTED",
                            "evidence_ids": ["synthetic-file"],
                            "rationale": "Synthetic file supports it.",
                            "confidence": "medium",
                        },
                    ],
                    "disagreement_codes": [],
                    "issue_type": None,
                    "adjudication_note": None,
                }
                for claim in sample["claims"]
            ]
            record = build_annotation_record(
                sample, "synthetic-v-not-a-person", "independent_a", claim_results
            )
            store_record(packet, checkpoint, output, sample["sample_id"], record)
            hashes = export_session(packet, checkpoint, output)
            self.assertEqual(1, len(hashes))
            manifest = json.loads((output / "frozen_export/manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("human_verdict_not_gold_until_adjudicated", manifest["status"])

    def test_calibration_packet_loads(self) -> None:
        path = ROOT / "data/private/annotations/stage-v-calibration-v0.1/blinded/stage_v_inputs.json"
        if not path.is_file():
            self.skipTest("calibration packet not prepared in this workspace")
        packet = load_stage_v_packet(path)
        self.assertEqual(1, packet["sample_count"])
        sample = packet["samples"][0]
        self.assertEqual("M003", sample["sample_id"])
        self.assertEqual(3, len(sample["claims"]))
        self.assertIn("L0", sample["evidence_levels"])

    def test_rejects_unknown_artifact(self) -> None:
        packet = load_stage_v_packet(self.fixture)
        sample = packet["samples"][0]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "annotator"
            _, checkpoint = open_session(self.fixture, output, "synthetic-v-not-a-person", "independent_a")
            with self.assertRaises(StageVAnnotationError):
                store_record(
                    packet,
                    checkpoint,
                    output,
                    sample["sample_id"],
                    build_annotation_record(
                        sample,
                        "synthetic-v-not-a-person",
                        "independent_a",
                        [
                            {
                                "claim_id": sample["claims"][0]["claim_id"],
                                "judgments": [
                                    {
                                        "level": "L0",
                                        "verdict": "SUPPORTED",
                                        "evidence_ids": ["missing-artifact"],
                                        "rationale": "bad id",
                                        "confidence": "low",
                                    }
                                ],
                                "disagreement_codes": [],
                            }
                        ],
                    ),
                )


if __name__ == "__main__":
    unittest.main()
