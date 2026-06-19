import json
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from pavo.batch import (
    doctor_batch,
    enrich_operator_handoff_with_validation,
    format_operator_handoff,
    load_operator_handoff,
    operator_handoff_ready_to_finish,
    prove_batch,
    verify_batch_manifest,
)
from pavo.cli import main


class BatchDoctorTests(unittest.TestCase):
    def test_readme_documents_batch_handoff_operator_gate(self):
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()

        self.assertIn("pavo batch handoff /path/to/meeting-batch/pavo-batch-proof.json --check-validation", readme)
        self.assertIn("pavo batch handoff /path/to/meeting-batch/pavo-batch-proof.json --strict-ready", readme)
        self.assertIn("stale-validation detection", readme)
        self.assertIn("it exits `0` only when all", readme)
        self.assertIn("it exits `3` when the handoff exists", readme)

    def test_batch_doctor_reports_machine_ready_with_human_gate_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_processed_batch(root, recording_ids=["rec-a", "rec-b"])

            result = doctor_batch(root, refresh_cluster_gate=False)
            report = result.as_report()
            markdown = result.as_markdown()

        self.assertTrue(result.passed)
        self.assertFalse(result.complete)
        self.assertEqual(result.state, "machine_ready_human_review_pending")
        self.assertEqual(result.source_recording_count, 2)
        self.assertIn("human review", result.next_command)
        self.assertIn("Pavo Batch Doctor", markdown)
        self.assertIn("Source Recordings", markdown)
        self.assertEqual(report["source_recording_count"], 2)
        self.assertRegex(report["source_manifest_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(report["generated_manifest_sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("cluster_review_page", report["generated_artifacts"])
        first = report["source_recordings"][0]
        self.assertRegex(first["recording_manifest_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(first["artifacts"]["audio"]["bytes"], len(b"fake audio"))
        self.assertEqual(first["artifacts"]["audio"]["sha256"], "72401f193251f177a310936253acb57e91e29d2aa582093974351e65e267bb32")
        self.assertFalse(report["complete"])
        self.assertIn("required human listening", report["safety_boundary"])

    def test_batch_doctor_fails_when_source_recording_artifact_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_processed_batch(root, recording_ids=["rec-a"])
            (root / "rec-a" / "transcript-diarized.md").unlink()

            result = doctor_batch(root, refresh_cluster_gate=False)
            failed = {check["name"] for check in result.checks if not check["passed"]}

        self.assertFalse(result.passed)
        self.assertEqual(result.state, "needs_machine_repair")
        self.assertIn("source_diarized_markdown", failed)
        self.assertIn("source_fingerprints", {check["name"] for check in result.checks})
        self.assertIn("rec-a missing: diarized_markdown", result.blockers)

    def test_batch_doctor_cli_writes_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_processed_batch(root, recording_ids=["rec-a"])
            report_path = root / "batch-doctor.json"
            markdown_path = root / "batch-doctor.md"

            exit_code = main(
                [
                    "batch",
                    "doctor",
                    str(root),
                    "--json",
                    "--report",
                    str(report_path),
                    "--markdown-report",
                    str(markdown_path),
                    "--no-refresh-cluster-gate",
                ]
            )
            report = json.loads(report_path.read_text())
            markdown_exists = markdown_path.exists()

        self.assertEqual(exit_code, 0)
        self.assertTrue(report["passed"])
        self.assertTrue(markdown_exists)
        self.assertEqual(report["state"], "machine_ready_human_review_pending")

    def test_batch_manifest_verifier_passes_for_unchanged_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_processed_batch(root, recording_ids=["rec-a"])
            report_path = root / "batch-doctor.json"
            report_path.write_text(json.dumps(doctor_batch(root, refresh_cluster_gate=False).as_report()))

            result = verify_batch_manifest(report_path)

        self.assertTrue(result.passed)
        self.assertEqual(result.checked_artifact_count, 22)
        self.assertEqual(result.mismatches, [])

    def test_batch_manifest_verifier_fails_when_artifact_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_processed_batch(root, recording_ids=["rec-a"])
            report_path = root / "batch-doctor.json"
            report_path.write_text(json.dumps(doctor_batch(root, refresh_cluster_gate=False).as_report()))
            (root / "rec-a" / "rec-a.mp3").write_bytes(b"changed audio")

            result = verify_batch_manifest(report_path)
            reasons = {mismatch["reason"] for mismatch in result.mismatches}

        self.assertFalse(result.passed)
        self.assertIn("fingerprint_mismatch", reasons)
        self.assertIn("source_manifest_mismatch", reasons)

    def test_batch_manifest_verifier_fails_when_generated_artifact_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_processed_batch(root, recording_ids=["rec-a"])
            report_path = root / "batch-doctor.json"
            report_path.write_text(json.dumps(doctor_batch(root, refresh_cluster_gate=False).as_report()))
            (root / "pavo-meeting-brief.json").write_text(json.dumps({"state": "changed"}))

            result = verify_batch_manifest(report_path)
            reasons = {mismatch["reason"] for mismatch in result.mismatches}

        self.assertFalse(result.passed)
        self.assertIn("generated_fingerprint_mismatch", reasons)
        self.assertIn("generated_manifest_mismatch", reasons)

    def test_batch_manifest_verifier_cli_writes_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_processed_batch(root, recording_ids=["rec-a"])
            report_path = root / "batch-doctor.json"
            markdown_path = root / "verify.md"
            report_path.write_text(json.dumps(doctor_batch(root, refresh_cluster_gate=False).as_report()))

            exit_code = main(
                [
                    "batch",
                    "verify-manifest",
                    str(report_path),
                    "--json",
                    "--markdown-report",
                    str(markdown_path),
                ]
            )
            markdown_exists = markdown_path.exists()

        self.assertEqual(exit_code, 0)
        self.assertTrue(markdown_exists)

    def test_batch_proof_writes_doctor_verification_and_proof_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_processed_batch(root, recording_ids=["rec-a"])

            result = prove_batch(root, refresh_cluster_gate=False)
            proof_report = json.loads(result.proof_report_path.read_text())
            proof_markdown = result.proof_markdown_path.read_text()
            proof_review_slate = result.proof_review_slate_path.read_text()
            proof_review_checklist = result.proof_review_checklist_path.read_text()
            proof_markdown_exists = result.proof_markdown_path.exists()
            proof_review_slate_exists = result.proof_review_slate_path.exists()
            proof_review_checklist_exists = result.proof_review_checklist_path.exists()
            doctor_report_exists = result.doctor_report_path.exists()
            doctor_markdown_exists = result.doctor_markdown_path.exists()
            verification_markdown_exists = result.verification_markdown_path.exists()

        self.assertTrue(result.passed)
        self.assertFalse(result.complete)
        self.assertEqual(result.state, "machine_ready_human_review_pending")
        self.assertEqual(result.verification.checked_artifact_count, 22)
        self.assertTrue(doctor_report_exists)
        self.assertTrue(doctor_markdown_exists)
        self.assertTrue(verification_markdown_exists)
        self.assertEqual(proof_report["state"], "machine_ready_human_review_pending")
        self.assertEqual(proof_report["operator_handoff"]["state"], "machine_ready_human_review_pending")
        self.assertFalse(proof_report["operator_handoff"]["complete"])
        self.assertTrue(proof_report["operator_handoff"]["proof_review_slate_tsv"].endswith("pavo-batch-proof.review-slate.tsv"))
        self.assertEqual(proof_report["operator_handoff"]["proof_slate_item_count"], 2)
        self.assertIn("validate-slate", proof_report["operator_handoff"]["validate_command"])
        self.assertIn("finish-from-slate", proof_report["operator_handoff"]["finish_command"])
        self.assertIn("--strict-complete", proof_report["operator_handoff"]["strict_proof_command"])
        self.assertIn("Do not mark speaker identity complete", proof_report["operator_handoff"]["safety_boundary"])
        self.assertTrue(proof_report["proof_review_slate_path"].endswith("pavo-batch-proof.review-slate.tsv"))
        self.assertTrue(proof_report["proof_review_checklist_path"].endswith("pavo-batch-proof.review-checklist.md"))
        self.assertTrue(proof_report["review_packet"]["proof_review_slate_tsv"].endswith("pavo-batch-proof.review-slate.tsv"))
        self.assertTrue(
            proof_report["review_packet"]["proof_review_checklist_markdown"].endswith(
                "pavo-batch-proof.review-checklist.md"
            )
        )
        self.assertTrue(
            proof_report["operator_handoff"]["proof_review_checklist_markdown"].endswith(
                "pavo-batch-proof.review-checklist.md"
            )
        )
        self.assertEqual(proof_report["review_packet"]["proof_slate_item_count"], 2)
        self.assertIn("pavo-batch-proof.review-slate.tsv", proof_report["review_packet"]["validate_proof_slate_command"])
        self.assertIn("pavo-batch-proof.review-slate.validation.json", proof_report["review_packet"]["validate_proof_slate_command"])
        self.assertIn("pavo-batch-proof.review-slate.tsv", proof_report["review_packet"]["finish_proof_slate_command"])
        self.assertEqual(proof_report["review_packet"]["item_count"], 1)
        self.assertEqual(proof_report["review_packet"]["total_unlockable_segments"], 10)
        self.assertIn("pavo-cluster-review-decision-brief.html", proof_report["review_packet"]["decision_brief_html"])
        self.assertIn("Proof review slate TSV:", proof_markdown)
        self.assertIn("Proof review checklist:", proof_markdown)
        self.assertIn("Validate proof slate:", proof_markdown)
        self.assertIn("Finish from proof slate:", proof_markdown)
        self.assertIn("## Operator Handoff", proof_markdown)
        self.assertIn("Validate without mutation:", proof_markdown)
        self.assertIn("Finish only after validation passes:", proof_markdown)
        self.assertIn("Re-run strict proof:", proof_markdown)
        self.assertIn("Expected state before human review", proof_markdown)
        self.assertIn("## Speaker Review Queue", proof_markdown)
        self.assertIn("Cluster `S1` row `1`", proof_markdown)
        self.assertIn("Unlock: 10 segments / 42.5 seconds", proof_markdown)
        self.assertIn("Why: acoustic drift; high impact", proof_markdown)
        self.assertIn("Transcript: hello from the sample", proof_markdown)
        self.assertIn("Finish from proof slate:", proof_markdown)
        self.assertIn("## Fillable Review Slate", proof_markdown)
        self.assertIn("This TSV includes 2 review-sheet row(s)", proof_markdown)
        self.assertIn("Edit `", proof_markdown)
        self.assertIn("row_index\tcluster_id\tdecision\tspeaker\tnote", proof_markdown)
        self.assertIn("priority_tier\tpriority_score\tpriority_reason\tquestion", proof_markdown)
        self.assertIn("1\tS1\tpending\tDaniel", proof_markdown)
        self.assertIn("2\tS1\tpending\tDaniel", proof_markdown)
        self.assertIn("row_index\tcluster_id\tdecision\tspeaker\tnote", proof_review_slate)
        self.assertIn("priority_tier\tpriority_score\tpriority_reason\tquestion", proof_review_slate)
        self.assertIn("1\tS1\tpending\tDaniel", proof_review_slate)
        self.assertIn("urgent_listen\t99.0\tacoustic drift; high impact", proof_review_slate)
        self.assertIn("Can cluster S1 be confirmed as Daniel?", proof_review_slate)
        self.assertIn("listen_carefully_acoustic_drift", proof_review_slate)
        self.assertIn("hello from the sample", proof_review_slate)
        self.assertIn("2\tS1\tpending\tDaniel", proof_review_slate)
        self.assertIn("second supporting sample", proof_review_slate)
        self.assertIn("# Pavo Proof Review Checklist", proof_review_checklist)
        self.assertIn("Pending speaker decisions: 1", proof_review_checklist)
        self.assertIn("Supporting proof rows: 2", proof_review_checklist)
        self.assertIn("## 1. Cluster `S1` - Daniel", proof_review_checklist)
        self.assertIn("- Rows: 1, 2", proof_review_checklist)
        self.assertIn("- [ ] Listen to every supporting clip.", proof_review_checklist)
        self.assertIn("Transcript: hello from the sample", proof_review_checklist)
        self.assertIn("validate-slate <review-sheet>", proof_review_checklist)
        self.assertTrue(proof_markdown_exists)
        self.assertTrue(proof_review_slate_exists)
        self.assertTrue(proof_review_checklist_exists)

    def test_batch_handoff_cli_prints_existing_proof_operator_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_processed_batch(root, recording_ids=["rec-a"])
            result = prove_batch(root, refresh_cluster_gate=False)
            result.proof_review_slate_path.with_suffix(".validation.json").write_text(
                json.dumps(
                    {
                        "passed": False,
                        "ready_to_finalize": False,
                        "applied_count": 2,
                        "approved_count": 0,
                        "rejected_count": 0,
                        "pending_count": 2,
                        "blockers": ["2 cluster questions still need review"],
                    }
                )
            )

            text_stdout = io.StringIO()
            with redirect_stdout(text_stdout):
                text_exit = main(["batch", "handoff", str(result.proof_report_path)])

            json_stdout = io.StringIO()
            with redirect_stdout(json_stdout):
                json_exit = main(["batch", "handoff", str(result.proof_report_path), "--check-validation", "--json"])

            checked_stdout = io.StringIO()
            with redirect_stdout(checked_stdout):
                checked_exit = main(["batch", "handoff", str(result.proof_report_path), "--check-validation"])

            strict_stdout = io.StringIO()
            with redirect_stdout(strict_stdout):
                strict_exit = main(["batch", "handoff", str(result.proof_report_path), "--strict-ready"])

            loaded = load_operator_handoff(result.proof_report_path)
            formatted = format_operator_handoff(loaded)
            enriched = enrich_operator_handoff_with_validation(loaded)
            json_report = json.loads(json_stdout.getvalue())

        self.assertEqual(text_exit, 0)
        self.assertEqual(json_exit, 0)
        self.assertEqual(checked_exit, 0)
        self.assertEqual(strict_exit, 3)
        self.assertIn("Pavo Operator Handoff", text_stdout.getvalue())
        self.assertIn("validate_command:", text_stdout.getvalue())
        self.assertIn("strict_proof_command:", text_stdout.getvalue())
        self.assertEqual(text_stdout.getvalue(), formatted)
        self.assertEqual(checked_stdout.getvalue(), format_operator_handoff(enriched))
        self.assertIn("validation:", checked_stdout.getvalue())
        self.assertIn("status: pending_review", checked_stdout.getvalue())
        self.assertIn("fresh: true", checked_stdout.getvalue())
        self.assertIn("pending_count: 2", checked_stdout.getvalue())
        self.assertIn("progress_percent: 0.0", checked_stdout.getvalue())
        self.assertIn("pending_decision_count: 1", checked_stdout.getvalue())
        self.assertIn(
            "next_action: review 1 pending speaker decision(s) across 2 proof TSV row(s), then rerun validate_command",
            checked_stdout.getvalue(),
        )
        self.assertIn("pending_review_questions:", checked_stdout.getvalue())
        self.assertIn(
            "- cluster S1 speaker Daniel: Can cluster S1 be confirmed as Daniel? (2 clips; rows 1, 2;",
            checked_stdout.getvalue(),
        )
        self.assertIn("sample row 1: hello from the sample", checked_stdout.getvalue())
        self.assertIn("sample row 2: second supporting sample", checked_stdout.getvalue())
        self.assertIn("pending_rows:", checked_stdout.getvalue())
        self.assertIn("- row 1 cluster S1 speaker Daniel: Can cluster S1 be confirmed as Daniel?", checked_stdout.getvalue())
        self.assertIn("- row 2 cluster S1 speaker Daniel: Can cluster S1 be confirmed as Daniel?", checked_stdout.getvalue())
        self.assertIn("pending_count: 2", strict_stdout.getvalue())
        self.assertIn("artifact_checks:", checked_stdout.getvalue())
        self.assertIn("proof_review_checklist_markdown: exists=true", checked_stdout.getvalue())
        self.assertRegex(checked_stdout.getvalue(), r"proof_review_checklist_markdown: exists=true bytes=\d+ sha256=[0-9a-f]{64}")
        self.assertIn("proof_review_slate_tsv: exists=true", checked_stdout.getvalue())
        self.assertRegex(checked_stdout.getvalue(), r"proof_review_slate_tsv: exists=true bytes=\d+ sha256=[0-9a-f]{64}")
        self.assertIn("review_page: exists=true", checked_stdout.getvalue())
        self.assertIn("validation_report: exists=true", checked_stdout.getvalue())
        self.assertEqual(json_report["state"], "machine_ready_human_review_pending")
        self.assertEqual(json_report["proof_slate_item_count"], 2)
        self.assertTrue(json_report["artifact_checks"]["proof_review_slate_tsv"]["exists"])
        self.assertTrue(json_report["artifact_checks"]["proof_review_checklist_markdown"]["exists"])
        self.assertTrue(json_report["artifact_checks"]["review_page"]["exists"])
        self.assertTrue(json_report["artifact_checks"]["validation_report"]["exists"])
        self.assertRegex(json_report["artifact_checks"]["proof_review_slate_tsv"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(
            json_report["artifact_checks"]["proof_review_checklist_markdown"]["sha256"],
            r"^[0-9a-f]{64}$",
        )
        self.assertRegex(json_report["artifact_checks"]["review_page"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(json_report["artifact_checks"]["validation_report"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(json_report["validation"]["status"], "pending_review")
        self.assertTrue(json_report["validation"]["fresh"])
        self.assertEqual(json_report["validation"]["pending_count"], 2)
        self.assertEqual(json_report["validation"]["reviewed_count"], 0)
        self.assertEqual(json_report["validation"]["total_count"], 2)
        self.assertEqual(json_report["validation"]["progress_percent"], 0.0)
        self.assertEqual(json_report["validation"]["pending_decision_count"], 1)
        self.assertEqual(
            json_report["validation"]["next_action"],
            "review 1 pending speaker decision(s) across 2 proof TSV row(s), then rerun validate_command",
        )
        self.assertEqual(len(json_report["validation"]["pending_review_questions"]), 1)
        self.assertEqual(json_report["validation"]["pending_review_questions"][0]["cluster_id"], "S1")
        self.assertEqual(json_report["validation"]["pending_review_questions"][0]["clip_count"], 2)
        self.assertEqual(json_report["validation"]["pending_review_questions"][0]["row_indices"], ["1", "2"])
        self.assertEqual(
            json_report["validation"]["pending_review_questions"][0]["transcript_samples"],
            [
                {"row_index": "1", "excerpt": "hello from the sample"},
                {"row_index": "2", "excerpt": "second supporting sample"},
            ],
        )
        self.assertEqual(len(json_report["validation"]["pending_rows"]), 2)
        self.assertEqual(json_report["validation"]["pending_rows"][0]["row_index"], "1")
        self.assertEqual(json_report["validation"]["pending_rows"][0]["cluster_id"], "S1")
        self.assertEqual(json_report["validation"]["pending_rows"][0]["transcript"], "hello from the sample")
        self.assertEqual(json_report["validation"]["pending_rows"][0]["speaker"], "Daniel")
        self.assertFalse(operator_handoff_ready_to_finish(json_report))
        self.assertIn("finish-from-slate", json_report["finish_command"])

    def test_batch_handoff_strict_ready_exits_zero_when_validation_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_processed_batch(root, recording_ids=["rec-a"])
            result = prove_batch(root, refresh_cluster_gate=False)
            result.proof_review_slate_path.with_suffix(".validation.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "ready_to_finalize": True,
                        "applied_count": 2,
                        "approved_count": 2,
                        "rejected_count": 0,
                        "pending_count": 0,
                        "blockers": [],
                    }
                )
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["batch", "handoff", str(result.proof_report_path), "--strict-ready", "--json"])

            report = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["validation"]["status"], "ready_to_finish")
        self.assertTrue(report["validation"]["fresh"])
        self.assertEqual(report["validation"]["reviewed_count"], 2)
        self.assertEqual(report["validation"]["total_count"], 2)
        self.assertEqual(report["validation"]["progress_percent"], 100.0)
        self.assertEqual(report["validation"]["next_action"], "run finish_command, then strict_proof_command")
        self.assertTrue(operator_handoff_ready_to_finish(report))

    def test_batch_handoff_strict_ready_fails_when_checklist_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_processed_batch(root, recording_ids=["rec-a"])
            result = prove_batch(root, refresh_cluster_gate=False)
            result.proof_review_slate_path.with_suffix(".validation.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "ready_to_finalize": True,
                        "applied_count": 2,
                        "approved_count": 2,
                        "rejected_count": 0,
                        "pending_count": 0,
                        "blockers": [],
                    }
                )
            )
            result.proof_review_checklist_path.unlink()

            json_stdout = io.StringIO()
            with redirect_stdout(json_stdout):
                exit_code = main(["batch", "handoff", str(result.proof_report_path), "--strict-ready", "--json"])
            report = json.loads(json_stdout.getvalue())

        self.assertEqual(exit_code, 3)
        self.assertFalse(report["artifact_checks"]["proof_review_checklist_markdown"]["exists"])
        self.assertFalse(operator_handoff_ready_to_finish(report))

    def test_batch_handoff_validation_marks_stale_when_slate_is_newer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_processed_batch(root, recording_ids=["rec-a"])
            result = prove_batch(root, refresh_cluster_gate=False)
            validation_path = result.proof_review_slate_path.with_suffix(".validation.json")
            validation_path.write_text(
                json.dumps(
                    {
                        "passed": False,
                        "ready_to_finalize": False,
                        "applied_count": 2,
                        "approved_count": 0,
                        "rejected_count": 0,
                        "pending_count": 2,
                        "blockers": ["2 cluster questions still need review"],
                    }
                )
            )
            os.utime(validation_path, (1000, 1000))
            os.utime(result.proof_review_slate_path, (2000, 2000))

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["batch", "handoff", str(result.proof_report_path), "--check-validation", "--json"])

            report = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["validation"]["status"], "stale_validation")
        self.assertFalse(report["validation"]["fresh"])
        self.assertEqual(report["validation"]["next_action"], "rerun validate_command before trusting this handoff")
        self.assertLess(report["validation"]["validation_mtime"], report["validation"]["slate_mtime"])

    def test_batch_proof_cli_strict_complete_fails_when_human_gate_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_processed_batch(root, recording_ids=["rec-a"])

            exit_code = main(
                [
                    "batch",
                    "prove",
                    str(root),
                    "--json",
                    "--strict-complete",
                    "--no-refresh-cluster-gate",
                ]
            )
            proof_markdown_exists = (root / "pavo-batch-proof.md").exists()

        self.assertEqual(exit_code, 3)
        self.assertTrue(proof_markdown_exists)

    def test_batch_doctor_refreshes_cluster_gate_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_processed_batch(root, recording_ids=["rec-a"])
            stale_path = root / "pavo-cluster-review-gate.json"
            stale_path.write_text(json.dumps({"doctor": {"passed": False}, "blockers": ["stale"]}))

            with patch("pavo.batch.gate_cluster_review", return_value=_FakeClusterGate()):
                result = doctor_batch(root)
            refreshed = json.loads(stale_path.read_text())
            markdown = (root / "pavo-cluster-review-gate.md").read_text()

        self.assertTrue(result.passed)
        self.assertEqual(result.cluster_gate["next_command"], "open refreshed review")
        self.assertEqual(refreshed["next_command"], "open refreshed review")
        self.assertIn("Refreshed Gate", markdown)
        self.assertIn("cluster_gate_refresh", {check["name"] for check in result.checks})


def _write_processed_batch(root: Path, *, recording_ids: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for recording_id in recording_ids:
        directory = root / recording_id
        directory.mkdir()
        (directory / f"{recording_id}.mp3").write_bytes(b"fake audio")
        (directory / f"{recording_id}.transcript.json").write_text(json.dumps({"segments": []}))
        (directory / "transcript.md").write_text("# Transcript\n")
        (directory / "transcript-diarized.md").write_text("# Diarized\n")
        (directory / "transcript-speaker-attributed.md").write_text("# Attributed\n")
        (directory / "README.md").write_text("# Recording\n")
        (directory / "fetch.json").write_text(json.dumps({"recording_id": recording_id}))

    work = root / "_work"
    work.mkdir()
    (work / "diarization-segments.json").write_text(json.dumps([]))
    (work / "speaker-attribution.json").write_text(json.dumps({"segments": []}))
    (work / "named-speaker-evidence.json").write_text(json.dumps({"segments": []}))

    (root / "pavo-run-report.json").write_text(
        json.dumps({"counts": {"recordings_observed": len(recording_ids)}})
    )
    (root / "pavo-meeting-brief.json").write_text(json.dumps({"state": "needs_review"}))
    (root / "pavo-cluster-review-gate.json").write_text(
        json.dumps(
            {
                "complete": False,
                "next_command": "open human review",
                "blockers": ["1 cluster question still needs review before terminal consensus"],
                "doctor": {"passed": True},
                "state": "review_pending",
                "review_sheet": str(root / "pavo-cluster-question-bundle" / "pavo-cluster-question-review-sheet.json"),
                "review_queue": {
                    "summary": {
                        "minimum_reviews": 1,
                        "pending_reviews": 1,
                        "possible_reviews_saved": 9,
                        "reduction_percent": 90.0,
                        "total_unlockable_segments": 10,
                        "total_unlockable_seconds": 42.5,
                        "forecast_risk_adjusted_segments": 8,
                    },
                    "items": [
                        {
                            "rank": 1,
                            "row_index": 1,
                            "cluster_id": "S1",
                            "question": "Can cluster S1 be confirmed as Daniel?",
                            "target_speaker": "Daniel",
                            "priority_tier": "urgent_listen",
                            "priority_score": 99.0,
                            "priority_reason": "acoustic drift; high impact",
                            "unlockable_segments": 10,
                            "unlockable_seconds": 42.5,
                            "acoustic_verdict": "listen_carefully_acoustic_drift",
                            "clip_path": str(root / "clip.mp3"),
                            "transcript_excerpt": "hello from the sample",
                            "approve_effect": "approving unlocks the cluster",
                            "reject_effect": "rejecting prevents unsafe propagation",
                            "terminal_decision_rule": "one contradiction is enough",
                        }
                    ],
                    "validate_command": "pavo review clusters validate-slate ...",
                    "finish_command": "pavo review clusters finish-from-slate ...",
                },
                "finish_command": "pavo review clusters finish-from-slate ...",
            }
        )
    )
    (root / "pavo-cluster-review-gate.md").write_text("# Cluster Gate\n")
    bundle = root / "pavo-cluster-question-bundle"
    bundle.mkdir()
    (bundle / "index.html").write_text("<!doctype html><title>Review</title>\n")
    (bundle / "pavo-cluster-question-review-sheet.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "index": 1,
                        "status": "pending",
                        "target_speaker_label": "Daniel",
                        "target_speaker_name": "Daniel",
                        "text": "hello from the sample",
                        "cluster_question": {"cluster_id": "S1", "candidate_name": "Daniel"},
                    },
                    {
                        "index": 2,
                        "status": "pending",
                        "target_speaker_label": "Daniel",
                        "target_speaker_name": "Daniel",
                        "text": "second supporting sample",
                        "cluster_question": {"cluster_id": "S1", "candidate_name": "Daniel"},
                    },
                ]
            }
        )
    )
    (bundle / "pavo-cluster-question-acoustic-evidence.json").write_text(json.dumps({"clusters": []}))
    (bundle / "pavo-cluster-review-forecast.json").write_text(json.dumps({"risk_adjusted_segments": 0}))
    (bundle / "pavo-cluster-review-decision-slate.tsv").write_text("cluster_id\tdecision\n")
    (bundle / "pavo-cluster-review-decision-slate.md").write_text("# Decision Slate\n")
    (bundle / "pavo-cluster-review-validation.json").write_text(json.dumps({"passed": False, "fresh": True}))
    (bundle / "pavo-cluster-review-decision-brief.html").write_text("<!doctype html><title>Decision Brief</title>\n")


class _FakeClusterGate:
    def as_report(self) -> dict[str, object]:
        return {
            "complete": False,
            "next_command": "open refreshed review",
            "blockers": ["1 cluster question still needs review before terminal consensus"],
            "doctor": {"passed": True},
        }

    def as_markdown(self) -> str:
        return "# Refreshed Gate\n"


if __name__ == "__main__":
    unittest.main()
