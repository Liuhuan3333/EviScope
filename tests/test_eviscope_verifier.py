from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eviscope_verifier import (  # noqa: E402
    EviScopeVerifierError,
    available_levels,
    constrain_package,
    escalate,
    load_nested_packages,
)
from oracle_judge import load_smoke_cases  # noqa: E402


class EviScopeVerifierTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = load_smoke_cases(ROOT / "configs/oracle_judge_smoke_cases_v0.1.json")["cases"]
        self.pr_root = ROOT / "data/private/pr-candidates"

    def _packages(self, case_index: int = 1) -> dict:
        case = self.cases[case_index]
        base = self.pr_root / case["repository_id"]
        snapshot = base / "review-snapshots" / case["review_head_sha"]
        if not snapshot.is_dir():
            self.skipTest(f"private snapshot missing for {case['repository_id']}")
        return load_nested_packages(
            snapshot,
            base / "l1-evidence-v0.1" / f"comment-{case['comment_id']}",
            base / "l2-evidence-v0.1" / f"comment-{case['comment_id']}",
            base / "l3-evidence-v0.1" / f"comment-{case['comment_id']}",
        )

    def test_l3_package_nests_l2_artifacts(self) -> None:
        packages = self._packages(1)
        l2_ids = {item["artifact_id"] for item in packages["L2"]["artifacts"]}
        l3_ids = {item["artifact_id"] for item in packages["L3"]["artifacts"]}
        self.assertTrue(l2_ids.issubset(l3_ids))
        self.assertGreater(packages["L3"]["artifact_count"], packages["L2"]["artifact_count"])

    def test_available_levels_are_prefix(self) -> None:
        case = self.cases[1]
        base = self.pr_root / case["repository_id"]
        levels = available_levels(
            base / "review-snapshots" / case["review_head_sha"],
            base / "l1-evidence-v0.1" / f"comment-{case['comment_id']}",
            base / "l2-evidence-v0.1" / f"comment-{case['comment_id']}",
            base / "l3-evidence-v0.1" / f"comment-{case['comment_id']}",
        )
        self.assertEqual(("L0", "L1", "L2", "L3"), levels)

    def test_stops_at_l0_and_skips_later_levels(self) -> None:
        packages = self._packages(1)
        called: list[str] = []

        def judge(level: str, evidence: dict) -> dict:
            called.append(level)
            artifact_id = evidence["artifacts"][0]["artifact_id"]
            return {
                "verdict": "SUPPORTED",
                "evidence_ids": [artifact_id],
                "rationale": "mock decisive at L0",
                "confidence": "high",
            }

        trace = escalate("comment", {"claim_id": "c1", "normalized_text": "x"}, packages, judge)
        self.assertEqual(["L0"], called)
        self.assertEqual(["L0"], trace["levels_called"])
        self.assertEqual(["L1", "L2", "L3"], trace["levels_skipped"])
        self.assertEqual("L0", trace["stopped_after"])
        self.assertEqual("SUPPORTED", trace["final_verdict"])
        self.assertEqual("L0", trace["minimum_evidence_level"])

    def test_escalates_until_l1_then_stops(self) -> None:
        packages = self._packages(1)
        called: list[str] = []

        def judge(level: str, evidence: dict) -> dict:
            called.append(level)
            if level == "L0":
                return {"verdict": "INSUFFICIENT", "evidence_ids": [], "rationale": "need more", "confidence": "low"}
            artifact_id = evidence["artifacts"][0]["artifact_id"]
            return {
                "verdict": "SUPPORTED",
                "evidence_ids": [artifact_id],
                "rationale": "found at L1",
                "confidence": "high",
            }

        trace = escalate("comment", {"claim_id": "c1", "normalized_text": "x"}, packages, judge)
        self.assertEqual(["L0", "L1"], called)
        self.assertEqual("L1", trace["minimum_evidence_level"])
        self.assertEqual("SUPPORTED", trace["final_verdict"])
        self.assertEqual(["L2", "L3"], trace["levels_skipped"])

    def test_all_insufficient_yields_null_minimum_level(self) -> None:
        packages = self._packages(1)

        def judge(level: str, evidence: dict) -> dict:
            return {"verdict": "INSUFFICIENT", "evidence_ids": [], "rationale": "still missing", "confidence": "low"}

        trace = escalate("comment", {"claim_id": "c1", "normalized_text": "x"}, packages, judge)
        self.assertEqual(["L0", "L1", "L2", "L3"], trace["levels_called"])
        self.assertEqual("INSUFFICIENT", trace["final_verdict"])
        self.assertIsNone(trace["minimum_evidence_level"])

    def test_unknown_citation_is_rejected(self) -> None:
        packages = self._packages(1)

        def judge(level: str, evidence: dict) -> dict:
            return {
                "verdict": "SUPPORTED",
                "evidence_ids": ["not-a-real-id"],
                "rationale": "bad cite",
                "confidence": "high",
            }

        with self.assertRaises(EviScopeVerifierError):
            escalate("comment", {"claim_id": "c1", "normalized_text": "x"}, packages, judge)

    def test_unique_l0_prefix_is_remapped(self) -> None:
        packages = self._packages(1)

        def judge(level: str, evidence: dict) -> dict:
            return {
                "verdict": "SUPPORTED",
                "evidence_ids": ["L0"],
                "rationale": "prefix cite",
                "confidence": "high",
            }

        trace = escalate("comment", {"claim_id": "c1", "normalized_text": "x"}, packages, judge)
        self.assertEqual(["L0:review-time-diff"], trace["judgments"][0]["evidence_ids"])
        self.assertEqual(["L0"], trace["judgments"][0]["remapped_evidence_ids"])

    def test_hookspec_claim_drops_implementation_files(self) -> None:
        packages = self._packages(2)
        claim = self.cases[2]["oracle_claim"]
        l1 = constrain_package(packages["L1"], ["src/_pytest/hookspec.py"])
        l2 = constrain_package(packages["L2"], ["src/_pytest/hookspec.py"])
        l1_ids = {item["artifact_id"] for item in l1["artifacts"]}
        l2_hay = " ".join(item["artifact_id"] + (item.get("path") or "") for item in l2["artifacts"])
        self.assertNotIn("file_after:src/_pytest/assertion/__init__.py", l1_ids)
        self.assertIn("hookspec.py", l2_hay)
        self.assertGreater(l1["dropped_artifact_count"], 0)

    def test_off_path_l1_contradiction_does_not_stop_escalation(self) -> None:
        packages = self._packages(2)
        claim = self.cases[2]["oracle_claim"]
        called: list[str] = []

        def judge(level: str, evidence: dict) -> dict:
            called.append(level)
            hook = next(
                (
                    item["artifact_id"]
                    for item in evidence["artifacts"]
                    if "hookspec.py" in item["artifact_id"] or "hookspec.py" in (item.get("path") or "")
                ),
                None,
            )
            if hook:
                return {
                    "verdict": "SUPPORTED",
                    "evidence_ids": [hook],
                    "rationale": "spec file present",
                    "confidence": "high",
                }
            return {
                "verdict": "CONTRADICTED",
                "evidence_ids": ["L0:review-time-diff"],
                "rationale": "wrong file",
                "confidence": "high",
            }

        trace = escalate(self.cases[2]["comment_text"], claim, packages, judge)
        self.assertIn("L2", called)
        self.assertEqual("INSUFFICIENT", trace["judgments"][0]["verdict"])
        self.assertEqual("rejected_off_path_citation", trace["judgments"][0]["path_constraint"])
        self.assertEqual("SUPPORTED", trace["final_verdict"])
        self.assertEqual("L2", trace["minimum_evidence_level"])

    def test_artifact_id_prefix_is_stripped(self) -> None:
        packages = self._packages(1)

        def judge(level: str, evidence: dict) -> dict:
            return {
                "verdict": "SUPPORTED",
                "evidence_ids": ["artifact_id=L0:review-time-diff"],
                "rationale": "prefixed id",
                "confidence": "high",
            }

        trace = escalate("comment", {"claim_id": "c1", "normalized_text": "x"}, packages, judge)
        self.assertEqual(["L0:review-time-diff"], trace["judgments"][0]["evidence_ids"])


if __name__ == "__main__":
    unittest.main()
