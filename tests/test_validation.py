from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from eviscope_validation import (
    validate_annotation,
    validate_annotation_v0_3,
    validate_dataset,
    validate_materiality_screening,
    validate_experiment_config,
    validate_file,
    validate_gate,
    validate_resources,
    validate_server_environment,
    validate_stage_s_synthetic_smoke_protocol,
    validate_swrbench_adaptation_protocol,
    validate_swrbench_review_time_policy,
)
from validate import cross_reference_issues


class ValidationTest(unittest.TestCase):
    def load(self, relative: str):
        return json.loads((ROOT / relative).read_text(encoding="utf-8"))

    def test_tracked_json_records_validate(self):
        paths = []
        for pattern in ("configs/*.json", "governance/*.json", "data/manifests/*.json"):
            paths.extend(ROOT.glob(pattern))
        failures = {str(path): [str(issue) for issue in validate_file(path)] for path in paths if validate_file(path)}
        self.assertEqual({}, failures)

    def test_future_artifact_is_rejected(self):
        data = self.load("data/manifests/dataset.synthetic-smoke.example.json")
        data["records"][0]["artifacts"][0]["available_at"] = "2026-08-14T00:00:00Z"
        issues = validate_dataset(Path("dataset.json"), data)
        self.assertTrue(any("future artifact" in issue.message for issue in issues))

    def test_synthetic_record_cannot_enter_analysis(self):
        data = self.load("data/manifests/dataset.synthetic-smoke.example.json")
        data["records"][0]["analysis_eligible"] = True
        issues = validate_dataset(Path("dataset.json"), data)
        self.assertTrue(any("analysis-ineligible" in issue.message for issue in issues))

    def test_synthetic_smoke_protocol_cannot_be_gold_or_use_natural_inputs(self):
        data = self.load("configs/stage_s_synthetic_smoke_protocol_v0.1.json")
        data["status"] = "gold"
        data["input_scope"] = "natural pilot comments"
        issues = validate_stage_s_synthetic_smoke_protocol(Path("smoke.json"), data)
        self.assertTrue(any("not gold" in issue.message for issue in issues))
        self.assertTrue(any("fabricated synthetic" in issue.message for issue in issues))

    def test_swrbench_protocol_cannot_inherit_labels_or_expose_future_fields(self):
        data = self.load("configs/swrbench_adaptation_protocol_v0.1.json")
        data["separation"]["inherit_swr_labels_as_eviscope_gold"] = True
        data["model_visible_allowlist"].append("changes")
        data["conversion_requirements"]["model_output_may_be_human_gold"] = True
        issues = validate_swrbench_adaptation_protocol(Path("swr.json"), data)
        self.assertTrue(any("label inheritance" in issue.message for issue in issues))
        self.assertTrue(any("pre-review field allowlist" in issue.message for issue in issues))
        self.assertTrue(any("human and leakage controls" in issue.message for issue in issues))

    def test_swr_review_time_policy_requires_reconstruction_and_quarantine(self):
        data = self.load("configs/swrbench_review_time_policy_v0.1.json")
        data["integrity_requirements"]["source_timestamps_alone_complete_verification"] = True
        data["review_time_cutoff"]["any_commit_after_cutoff_action"] = "drop_commit"
        data["output_controls"]["model_inference_eligible"] = True
        issues = validate_swrbench_review_time_policy(Path("policy.json"), data)
        self.assertTrue(any("repository reconstruction" in issue.message for issue in issues))
        self.assertTrue(any("quarantine rules" in issue.message for issue in issues))
        self.assertTrue(any("permissions" in issue.message for issue in issues))

    def test_dataset_requires_complete_provenance(self):
        data = self.load("data/manifests/dataset.synthetic-smoke.example.json")
        data["records"][0]["provenance"] = {}
        issues = validate_dataset(Path("dataset.json"), data)
        self.assertTrue(any("missing required field" in issue.message for issue in issues))
        self.assertTrue(any("base_sha" in issue.location for issue in issues))

    def test_decisive_annotation_requires_evidence(self):
        data = self.load("data/manifests/annotation.synthetic-smoke.example.json")
        data["claims"][0]["judgments"][1]["evidence_ids"] = []
        issues = validate_annotation(Path("annotation.json"), data)
        self.assertTrue(any("requires evidence" in issue.message for issue in issues))

    def test_annotation_requires_current_protocol_versions(self):
        data = self.load("data/manifests/annotation.synthetic-smoke.example.json")
        data["schema_version"] = "eviscope.annotation.v0.1"
        data["guide_version"] = "v0.1"
        issues = validate_annotation(Path("annotation.json"), data)
        self.assertTrue(any("schema v0.2" in issue.message for issue in issues))
        self.assertTrue(any("guide v0.2" in issue.message for issue in issues))

    def test_annotation_cannot_skip_an_evidence_level(self):
        data = self.load("data/manifests/annotation.synthetic-smoke.example.json")
        data["claims"][0]["judgments"][1]["level"] = "L2"
        issues = validate_annotation(Path("annotation.json"), data)
        self.assertTrue(any("progressive prefix" in issue.message for issue in issues))

    def test_annotation_stops_after_decisive_verdict(self):
        data = self.load("data/manifests/annotation.synthetic-smoke.example.json")
        extra = copy.deepcopy(data["claims"][0]["judgments"][1])
        extra["level"] = "L2"
        data["claims"][0]["judgments"].append(extra)
        issues = validate_annotation(Path("annotation.json"), data)
        self.assertTrue(any("stop after first decisive" in issue.message for issue in issues))

    def test_malformed_json_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("{", encoding="utf-8")
            issues = validate_file(path)
        self.assertTrue(any("invalid JSON" in issue.message for issue in issues))

    def test_gate_cannot_claim_completion_without_evidence(self):
        data = self.load("governance/gate0_status.json")
        data["overall_status"] = "passed"
        for criterion in data["criteria"]:
            criterion["status"] = "confirmed"
            criterion["evidence"] = None
        issues = validate_gate(Path("gate.json"), data)
        self.assertTrue(any("auditable evidence" in issue.message for issue in issues))

    def test_gate_cannot_complete_people_by_calling_them_implemented(self):
        data = self.load("governance/gate0_status.json")
        data["overall_status"] = "passed"
        for criterion in data["criteria"]:
            criterion["status"] = "implemented"
            criterion["evidence"] = "placeholder evidence"
        issues = validate_gate(Path("gate.json"), data)
        self.assertTrue(any("annotator-a can complete only as confirmed" in issue.message for issue in issues))
        self.assertTrue(any("cannot pass" in issue.message for issue in issues))

    def test_gate_requires_every_mandatory_criterion(self):
        data = self.load("governance/gate0_status.json")
        data["criteria"] = [item for item in data["criteria"] if item["id"] != "annotator-b"]
        issues = validate_gate(Path("gate.json"), data)
        self.assertTrue(any("annotator-b" in issue.message for issue in issues))

    def test_confirmed_resource_requires_commitment_and_coi_review(self):
        data = self.load("governance/resources.example.json")
        person = next(item for item in data["people"] if item["role_id"] == "annotator-a")
        person["status"] = "confirmed"
        issues = validate_resources(Path("resources.json"), data)
        self.assertTrue(any("committed hours" in issue.message for issue in issues))
        self.assertTrue(any("before confirmation" in issue.message for issue in issues))

    def test_empty_experiment_config_is_rejected(self):
        issues = validate_experiment_config(Path("config.json"), {})
        self.assertTrue(any("missing required field" in issue.message for issue in issues))

    def test_experiment_budget_and_release_rule_are_enforced(self):
        data = self.load("configs/experiment_defaults.json")
        data["retrieval_budget"]["max_actions"] = True
        data["release_rule"]["otherwise"] = "accept"
        issues = validate_experiment_config(Path("config.json"), data)
        self.assertTrue(any("positive integer" in issue.message for issue in issues))
        self.assertTrue(any("registered accept/reject/abstain" in issue.message for issue in issues))

    def test_empty_server_inventory_is_rejected(self):
        issues = validate_server_environment(Path("server.json"), {})
        self.assertTrue(any("missing required field" in issue.message for issue in issues))

    def test_server_collector_output_has_no_forbidden_identity_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "server.json"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "collect_server_env.py"), str(output)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual([], validate_server_environment(output, data))
            serialized = json.dumps(data).lower()
            for forbidden in ('"username"', '"hostname"', '"ip_address"', '"api_key"'):
                self.assertNotIn(forbidden, serialized)

    def test_snapshot_preflight_is_read_only_on_local_commits(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "fixture@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Fixture"], check=True)
            tracked = repo / "sample.py"
            tracked.write_text("x = 1\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "sample.py"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
            base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
            tracked.write_text("x = 2\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "commit", "-qam", "head"], check=True)
            head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
            before = subprocess.run(["git", "-C", str(repo), "status", "--porcelain=v1"], check=True, capture_output=True, text=True).stdout
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "snapshot_preflight.py"), str(repo), base, head],
                check=False,
                capture_output=True,
                text=True,
            )
            after = subprocess.run(["git", "-C", str(repo), "status", "--porcelain=v1"], check=True, capture_output=True, text=True).stdout
            self.assertEqual(0, result.returncode, result.stderr)
            preflight = json.loads(result.stdout)
            self.assertTrue(preflight["ready"])
            self.assertNotIn("repository_argument", preflight)
            self.assertNotIn(str(repo), result.stdout)
            self.assertEqual(before, after)

    def test_snapshot_preflight_rejects_identical_commits(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "fixture@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Fixture"], check=True)
            tracked = repo / "sample.py"
            tracked.write_text("x = 1\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "sample.py"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
            commit = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "snapshot_preflight.py"), str(repo), commit, commit],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(1, result.returncode)
            self.assertFalse(json.loads(result.stdout)["ready"])

    def test_cross_reference_rejects_unknown_evidence_id(self):
        dataset = self.load("data/manifests/dataset.synthetic-smoke.example.json")
        annotation = self.load("data/manifests/annotation.synthetic-smoke.example.json")
        annotation["claims"][0]["judgments"][1]["evidence_ids"] = ["missing-artifact"]
        with tempfile.TemporaryDirectory() as directory:
            dataset_path = Path(directory) / "dataset.json"
            annotation_path = Path(directory) / "annotation.json"
            dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
            annotation_path.write_text(json.dumps(annotation), encoding="utf-8")
            issues = cross_reference_issues([dataset_path, annotation_path])
        self.assertTrue(any("unknown artifact ID" in issue for issue in issues))

    def test_cross_reference_rejects_future_level_evidence(self):
        dataset = self.load("data/manifests/dataset.synthetic-smoke.example.json")
        annotation = self.load("data/manifests/annotation.synthetic-smoke.example.json")
        annotation["claims"][0]["judgments"][0]["evidence_ids"] = ["synthetic-file"]
        with tempfile.TemporaryDirectory() as directory:
            dataset_path = Path(directory) / "dataset.json"
            annotation_path = Path(directory) / "annotation.json"
            dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
            annotation_path.write_text(json.dumps(annotation), encoding="utf-8")
            issues = cross_reference_issues([dataset_path, annotation_path])
        self.assertTrue(any("future-level evidence" in issue for issue in issues))

    def test_cross_reference_checks_claim_source_span(self):
        dataset = self.load("data/manifests/dataset.synthetic-smoke.example.json")
        annotation = self.load("data/manifests/annotation.synthetic-smoke.example.json")
        annotation["claims"][0]["source_span"]["start"] = 1
        with tempfile.TemporaryDirectory() as directory:
            dataset_path = Path(directory) / "dataset.json"
            annotation_path = Path(directory) / "annotation.json"
            dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
            annotation_path.write_text(json.dumps(annotation), encoding="utf-8")
            issues = cross_reference_issues([dataset_path, annotation_path])
        self.assertTrue(any("exactly match" in issue for issue in issues))

    def test_boolean_values_are_not_accepted_as_integers(self):
        dataset = self.load("data/manifests/dataset.synthetic-smoke.example.json")
        dataset["records"][0]["provenance"]["pr_number"] = True
        self.assertTrue(any("positive integer" in issue.message for issue in validate_dataset(Path("dataset.json"), dataset)))

        annotation = self.load("data/manifests/annotation.synthetic-smoke.example.json")
        annotation["claims"][0]["source_span"]["start"] = False
        self.assertTrue(any("source_span" in issue.location for issue in validate_annotation(Path("annotation.json"), annotation)))

    def test_malformed_collection_types_are_reported_without_crashing(self):
        dataset = self.load("data/manifests/dataset.synthetic-smoke.example.json")
        dataset["records"][0]["sample_id"] = []
        self.assertTrue(validate_dataset(Path("dataset.json"), dataset))

        annotation = self.load("data/manifests/annotation.synthetic-smoke.example.json")
        annotation["claims"][0]["claim_id"] = []
        annotation["claims"][0]["disagreement_codes"] = [{}]
        self.assertTrue(validate_annotation(Path("annotation.json"), annotation))

        config = self.load("configs/experiment_defaults.json")
        config["verdicts"] = [{}]
        self.assertTrue(validate_experiment_config(Path("config.json"), config))

        resources = self.load("governance/resources.example.json")
        resources["people"][0]["role_id"] = []
        self.assertTrue(validate_resources(Path("resources.json"), resources))

    def test_cross_reference_tolerates_malformed_collection_types(self):
        dataset = self.load("data/manifests/dataset.synthetic-smoke.example.json")
        annotation = self.load("data/manifests/annotation.synthetic-smoke.example.json")
        pilot = self.load("data/manifests/pilot.example.json")
        dataset["records"] = None
        annotation["claims"] = None
        pilot["samples"] = None
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for name, document in (("dataset.json", dataset), ("annotation.json", annotation), ("pilot.json", pilot)):
                path = Path(directory) / name
                path.write_text(json.dumps(document), encoding="utf-8")
                paths.append(path)
            issues = cross_reference_issues(paths)
        self.assertTrue(any("no matching dataset record" in issue for issue in issues))


    def test_v03_uploaded_fixtures_validate(self):
        screening = self.load("data/manifests/screening.synthetic-smoke.example.json")
        annotation = self.load("data/manifests/annotation.v0.3.synthetic-smoke.example.json")
        self.assertEqual([], validate_materiality_screening(Path("screening.json"), screening))
        self.assertEqual([], validate_annotation_v0_3(Path("annotation-v03.json"), annotation))

    def test_v03_screening_enforces_decision_reason_and_claim_cardinality(self):
        screening = self.load("data/manifests/screening.synthetic-smoke.example.json")
        screening["decision"] = "NON_MATERIAL"
        screening["non_material_reason"] = "NOT_REGISTERED"
        issues = validate_materiality_screening(Path("screening.json"), screening)
        self.assertTrue(any("zero claims" in issue.message for issue in issues))
        self.assertTrue(any("registered non-material reason" in issue.message for issue in issues))

        screening = self.load("data/manifests/screening.synthetic-smoke.example.json")
        screening["non_material_reason"] = "PURE_PREFERENCE"
        issues = validate_materiality_screening(Path("screening.json"), screening)
        self.assertTrue(any("null reason" in issue.message for issue in issues))

    def test_v03_screening_rejects_overlap_and_boolean_offsets(self):
        overlap = self.load("data/manifests/screening.synthetic-smoke.example.json")
        overlap["claims"][0]["source_fragments"][1]["start"] = 10
        overlap_issues = validate_materiality_screening(Path("screening.json"), overlap)
        self.assertTrue(any("ordered and non-overlapping" in issue.message for issue in overlap_issues))

        boolean_offset = self.load("data/manifests/screening.synthetic-smoke.example.json")
        boolean_offset["claims"][0]["source_fragments"][0]["start"] = False
        offset_issues = validate_materiality_screening(Path("screening.json"), boolean_offset)
        self.assertTrue(any("integer offsets" in issue.message for issue in offset_issues))

    def test_v03_annotation_enforces_progression_and_decisive_evidence(self):
        annotation = self.load("data/manifests/annotation.v0.3.synthetic-smoke.example.json")
        annotation["claims"][0]["judgments"][1]["level"] = "L2"
        annotation["claims"][0]["judgments"][1]["evidence_ids"] = []
        extra = copy.deepcopy(annotation["claims"][0]["judgments"][1])
        extra["level"] = "L3"
        annotation["claims"][0]["judgments"].append(extra)
        issues = validate_annotation_v0_3(Path("annotation-v03.json"), annotation)
        self.assertTrue(any("progressive prefix" in issue.message for issue in issues))
        self.assertTrue(any("requires evidence" in issue.message for issue in issues))
        self.assertTrue(any("stop after first decisive" in issue.message for issue in issues))

    def test_v03_cross_reference_rejects_fragment_mismatch(self):
        dataset = self.load("data/manifests/dataset.synthetic-smoke.example.json")
        screening = self.load("data/manifests/screening.synthetic-smoke.example.json")
        screening["claims"][0]["source_fragments"][0]["start"] = 1
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_path = root / "dataset.json"
            screening_path = root / "screening.json"
            dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
            screening_path.write_text(json.dumps(screening), encoding="utf-8")
            issues = cross_reference_issues([dataset_path, screening_path])
        self.assertTrue(any("fragment text must exactly match" in issue for issue in issues))

    def test_v03_cross_reference_freezes_screening_hash_and_claim_ids(self):
        dataset = self.load("data/manifests/dataset.synthetic-smoke.example.json")
        screening = self.load("data/manifests/screening.synthetic-smoke.example.json")
        annotation = self.load("data/manifests/annotation.v0.3.synthetic-smoke.example.json")
        annotation["claims"][0]["claim_id"] = "changed-in-stage-v"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_path = root / "dataset.json"
            screening_path = root / "screening.json"
            annotation_path = root / "annotation.json"
            dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
            screening_path.write_text(json.dumps(screening), encoding="utf-8")
            annotation["screening_sha256"] = "0" * 64
            annotation_path.write_text(json.dumps(annotation), encoding="utf-8")
            issues = cross_reference_issues([dataset_path, screening_path, annotation_path])
        self.assertTrue(any("does not match the frozen Stage-S file" in issue for issue in issues))
        self.assertTrue(any("claim IDs and order" in issue for issue in issues))

    def test_v03_cross_reference_requires_adjudicated_material_screening(self):
        dataset = self.load("data/manifests/dataset.synthetic-smoke.example.json")
        screening = self.load("data/manifests/screening.synthetic-smoke.example.json")
        annotation = self.load("data/manifests/annotation.v0.3.synthetic-smoke.example.json")
        screening["annotation_round"] = "independent_a"
        screening["decision"] = "NON_MATERIAL"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_path = root / "dataset.json"
            screening_path = root / "screening.json"
            annotation_path = root / "annotation.json"
            dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
            screening_path.write_text(json.dumps(screening), encoding="utf-8")
            annotation["screening_sha256"] = hashlib.sha256(screening_path.read_bytes()).hexdigest()
            annotation_path.write_text(json.dumps(annotation), encoding="utf-8")
            issues = cross_reference_issues([dataset_path, screening_path, annotation_path])
        self.assertTrue(any("requires an adjudicated Stage-S" in issue for issue in issues))
        self.assertTrue(any("requires a MATERIAL Stage-S" in issue for issue in issues))

    def test_v03_cross_reference_rejects_future_level_evidence(self):
        dataset = self.load("data/manifests/dataset.synthetic-smoke.example.json")
        screening = self.load("data/manifests/screening.synthetic-smoke.example.json")
        annotation = self.load("data/manifests/annotation.v0.3.synthetic-smoke.example.json")
        annotation["claims"][0]["judgments"][0]["evidence_ids"] = ["synthetic-file"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_path = root / "dataset.json"
            screening_path = root / "screening.json"
            annotation_path = root / "annotation.json"
            dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
            screening_path.write_text(json.dumps(screening), encoding="utf-8")
            annotation["screening_sha256"] = hashlib.sha256(screening_path.read_bytes()).hexdigest()
            annotation_path.write_text(json.dumps(annotation), encoding="utf-8")
            issues = cross_reference_issues([dataset_path, screening_path, annotation_path])
        self.assertTrue(any("future-level evidence" in issue for issue in issues))


    def test_v03_screening_rejects_unregistered_context_and_prediction_fields(self):
        screening = self.load("data/manifests/screening.synthetic-smoke.example.json")
        screening["repository"] = "must-not-be-visible-in-stage-s"
        screening["claims"][0]["model_prediction"] = "must-not-be-visible"
        issues = validate_materiality_screening(Path("screening.json"), screening)
        self.assertTrue(any(issue.location == "repository" and issue.message == "unexpected field" for issue in issues))
        self.assertTrue(any("model_prediction" in issue.location and issue.message == "unexpected field" for issue in issues))

    def test_v03_validators_tolerate_malformed_collections(self):
        screening = self.load("data/manifests/screening.synthetic-smoke.example.json")
        screening["claims"] = {}
        self.assertTrue(validate_materiality_screening(Path("screening.json"), screening))
        annotation = self.load("data/manifests/annotation.v0.3.synthetic-smoke.example.json")
        annotation["claims"] = None
        self.assertTrue(validate_annotation_v0_3(Path("annotation.json"), annotation))


if __name__ == "__main__":
    unittest.main()
