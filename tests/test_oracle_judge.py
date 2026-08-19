from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oracle_judge import (  # noqa: E402
    OracleJudgeError,
    assemble_evidence,
    evaluate_case,
    format_judge_user_message,
    load_smoke_cases,
    parse_judge_response,
    run_smoke_suite,
)


class OracleJudgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cases_path = ROOT / "configs/oracle_judge_smoke_cases_v0.1.json"
        self.prompt_path = ROOT / "configs/oracle_judge_smoke_prompt_v0.1.txt"
        self.pr_root = ROOT / "data/private/pr-candidates"

    def test_load_smoke_cases(self) -> None:
        doc = load_smoke_cases(self.cases_path)
        self.assertEqual(3, len(doc["cases"]))

    def test_l1_is_richer_and_l0_omits_return_line(self) -> None:
        case = load_smoke_cases(self.cases_path)["cases"][0]
        base = self.pr_root / case["repository_id"]
        snapshot = base / "review-snapshots" / case["review_head_sha"]
        l1_dir = base / "l1-evidence-v0.1" / f"comment-{case['comment_id']}"
        l0 = assemble_evidence(snapshot, None, "L0")
        l1 = assemble_evidence(snapshot, l1_dir, "L1")
        self.assertGreater(l1["total_bytes"], l0["total_bytes"])
        self.assertEqual(1, l0["artifact_count"])
        self.assertGreater(l1["artifact_count"], 1)
        l0_text = l0["artifacts"][0]["content"]
        self.assertNotIn("return util.assertrepr_compare(", l0_text)
        l1_symbols = [
            item["content"]
            for item in l1["artifacts"]
            if item["kind"] == "enclosing_symbol"
        ]
        self.assertTrue(any("return util.assertrepr_compare(" in text for text in l1_symbols))

    def test_format_judge_user_message_includes_claim(self) -> None:
        case = load_smoke_cases(self.cases_path)["cases"][0]
        base = self.pr_root / case["repository_id"]
        snapshot = base / "review-snapshots" / case["review_head_sha"]
        evidence = assemble_evidence(snapshot, None, "L0")
        message = format_judge_user_message(case["comment_text"], case["oracle_claim"], evidence)
        self.assertIn(case["oracle_claim"]["normalized_text"], message)
        self.assertIn("L0:review-time-diff", message)

    def test_parse_judge_response(self) -> None:
        parsed = parse_judge_response(
            json.dumps(
                {
                    "verdict": "INSUFFICIENT",
                    "evidence_ids": [],
                    "rationale": "The diff does not show the return statement.",
                    "confidence": "high",
                }
            )
        )
        self.assertEqual("INSUFFICIENT", parsed["verdict"])

    def test_parse_rejects_decisive_without_evidence(self) -> None:
        with self.assertRaises(OracleJudgeError):
            parse_judge_response(
                json.dumps(
                    {
                        "verdict": "SUPPORTED",
                        "evidence_ids": [],
                        "rationale": "missing ids",
                        "confidence": "low",
                    }
                )
            )

    def test_dry_run_suite(self) -> None:
        result = run_smoke_suite(
            self.cases_path,
            self.pr_root,
            self.prompt_path,
            model="mock",
            temperature=0.0,
            max_tokens=100,
            timeout=1.0,
            dry_run=True,
        )
        self.assertEqual(3, result["case_count"])
        self.assertTrue(all(record["l1_richer_than_l0"] for record in result["records"]))

    def test_mock_requester_mechanism_signal(self) -> None:
        responses = {
            "pytest-s033-direct-generator-return": {
                "L0": "INSUFFICIENT",
                "L1": "SUPPORTED",
            },
            "django-s001-pop-race": {
                "L0": "SUPPORTED",
                "L1": "SUPPORTED",
            },
            "pytest-s033-hookspec-return-type": {
                "L0": "INSUFFICIENT",
                "L1": "INSUFFICIENT",
                "L2": "SUPPORTED",
            },
        }
        seen: list[str] = []

        def requester(_model: str, payload: dict, _timeout: float) -> dict:
            user = payload["messages"][1]["content"]
            if "return statement that passes through util.assertrepr_compare" in user:
                case_key = "pytest-s033-direct-generator-return"
            elif "CullHandler.check() calls self.elements.pop()" in user:
                case_key = "django-s001-pop-race"
            else:
                case_key = "pytest-s033-hookspec-return-type"
            if "definition:comment-mention:" in user or "kind=definition" in user:
                level = "L2"
            elif "enclosing_symbol" in user or "file_before:" in user:
                level = "L1"
            else:
                level = "L0"
            seen.append(f"{case_key}:{level}")
            verdict = responses[case_key][level]
            evidence_ids = ["L0:review-time-diff"] if verdict != "INSUFFICIENT" else []
            if level == "L1" and verdict == "SUPPORTED":
                evidence_ids.append("enclosing_symbol:3313441593")
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "verdict": verdict,
                                    "evidence_ids": evidence_ids,
                                    "rationale": "mock",
                                    "confidence": "high",
                                }
                            )
                        }
                    }
                ]
            }

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "smoke.json"
            result = run_smoke_suite(
                self.cases_path,
                self.pr_root,
                self.prompt_path,
                model="mock",
                temperature=0.0,
                max_tokens=100,
                timeout=1.0,
                requester=requester,
            )
            self.assertEqual(7, len(seen))
            self.assertEqual(1, result["mechanism_signals"])
            self.assertEqual(3, result["expectation_matches"])
            direct = next(
                record for record in result["records"] if record["case_id"] == "pytest-s033-direct-generator-return"
            )
            self.assertTrue(direct["mechanism_signal"])
            self.assertTrue(direct["both_match_expectation"])

    def test_evaluate_case_unknown_id(self) -> None:
        with self.assertRaises(OracleJudgeError):
            run_smoke_suite(
                self.cases_path,
                self.pr_root,
                self.prompt_path,
                model="mock",
                temperature=0.0,
                max_tokens=100,
                timeout=1.0,
                case_ids=["missing-case"],
                dry_run=True,
            )


if __name__ == "__main__":
    unittest.main()
