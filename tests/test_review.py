import json
import tempfile
import unittest
from pathlib import Path

from pavo.review import (
    build_anchor_review_rerun_command,
    create_anchor_review_bundle,
    create_anchor_review_page,
    compile_anchor_review_corrections,
    create_anchor_review_sheet,
    gate_anchor_review,
    import_anchor_review_sheet,
    summarize_anchor_review_sheet,
    verify_anchor_review_page,
)


class ReviewTests(unittest.TestCase):
    def test_committed_plaud_c37_anchor_review_sheet_is_pending_human_review(self):
        sheet = Path(__file__).resolve().parents[1] / "docs" / "plaud-c37-speaker1-anchor-review-sheet.json"

        summary = summarize_anchor_review_sheet(sheet)
        corrections = compile_anchor_review_corrections(sheet)

        self.assertFalse(summary["human_reviewed"])
        self.assertEqual(summary["candidate_count"], 20)
        self.assertEqual(summary["pending_count"], 20)
        self.assertEqual(summary["approved_count"], 0)
        self.assertEqual(corrections.cli_args, [])

    def test_committed_plaud_c37_rerun_command_report_waits_for_approved_review(self):
        report = Path(__file__).resolve().parents[1] / "docs" / "plaud-c37-anchor-rerun-command-report.json"
        payload = json.loads(report.read_text())

        self.assertFalse(payload["passed"])
        self.assertFalse(payload["rerun_command_ready"])
        self.assertEqual(payload["approved_count"], 0)
        self.assertEqual(payload["pending_count"], 20)
        self.assertIn("no approved speaker corrections", payload["blocked_reason"])

    def test_committed_plaud_c37_review_gate_waits_for_human_review(self):
        docs = Path(__file__).resolve().parents[1] / "docs"

        result = gate_anchor_review(
            docs / "plaud-c37-speaker1-anchor-review-sheet.json",
            page_report_path=docs / "plaud-c37-anchor-review-page-report.json",
            bundle_manifest_path=docs / "plaud-c37-anchor-review-bundle-manifest.json",
            browser_report_path=docs / "plaud-c37-anchor-review-browser-report.json",
            rerun_report_path=docs / "plaud-c37-anchor-rerun-command-report.json",
        )

        self.assertFalse(result.passed)
        self.assertFalse(result.human_reviewed)
        self.assertTrue(result.page_ready)
        self.assertTrue(result.bundle_ready)
        self.assertTrue(result.browser_verified)
        self.assertEqual(result.approved_count, 0)
        self.assertEqual(result.pending_count, 20)
        self.assertIn("20 review rows are still pending", result.blockers)
        self.assertIn("no speaker-anchor clips are approved", result.blockers)

    def test_create_anchor_review_sheet_starts_pending_without_approved_corrections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet = root / "clips.json"
            packet.write_text(
                json.dumps(
                    {
                        "review_packet": "/tmp/review-packet.json",
                        "target_speaker_label": "SPEAKER_01",
                        "target_speaker_name": "Speaker 1",
                        "clips": [
                            {
                                "index": 1,
                                "start": 12.06,
                                "end": 16.06,
                                "duration": 4.0,
                                "text": "candidate",
                                "clip_path": "/tmp/candidate.wav",
                                "suggested_speaker_correction": "00:12-00:16=SPEAKER_01",
                            }
                        ],
                    }
                )
            )

            result = create_anchor_review_sheet(packet)
            summary = summarize_anchor_review_sheet(result.review_sheet_path)
            corrections = compile_anchor_review_corrections(result.review_sheet_path)

        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.pending_count, 1)
        self.assertFalse(summary["human_reviewed"])
        self.assertEqual(summary["approved_count"], 0)
        self.assertEqual(corrections.cli_args, [])

    def test_compile_anchor_review_corrections_exports_only_approved_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet = root / "review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "target_speaker_label": "SPEAKER_01",
                        "rows": [
                            {
                                "index": 1,
                                "status": "approved",
                                "approved": True,
                                "target_speaker_label": "SPEAKER_01",
                                "start": 12.06,
                                "end": 16.06,
                                "suggested_speaker_correction": "00:12-00:16=SPEAKER_01",
                            },
                            {
                                "index": 2,
                                "status": "rejected",
                                "approved": False,
                                "target_speaker_label": "SPEAKER_01",
                                "start": 144.6,
                                "end": 148.6,
                                "suggested_speaker_correction": "02:25-02:29=SPEAKER_01",
                            },
                        ],
                    }
                )
            )

            result = compile_anchor_review_corrections(sheet)
            summary = summarize_anchor_review_sheet(sheet)

        self.assertEqual(result.approved_count, 1)
        self.assertEqual(result.corrections, ["00:12-00:16=SPEAKER_01"])
        self.assertEqual(result.cli_args, ["--speaker-correction", "00:12-00:16=SPEAKER_01"])
        self.assertTrue(summary["human_reviewed"])
        self.assertTrue(summary["passed"])

    def test_create_anchor_review_page_embeds_clip_audio_and_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clip = root / "candidate.wav"
            clip.write_bytes(b"RIFF")
            sheet = root / "review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "target_speaker_label": "SPEAKER_01",
                        "target_speaker_name": "Speaker 1",
                        "rows": [
                            {
                                "index": 1,
                                "status": "pending",
                                "approved": False,
                                "target_speaker_label": "SPEAKER_01",
                                "target_speaker_name": "Speaker 1",
                                "start": 12.06,
                                "end": 16.06,
                                "text": "candidate",
                                "clip_path": str(clip),
                                "suggested_speaker_correction": "00:12-00:16=SPEAKER_01",
                            }
                        ],
                    }
                )
            )

            result = create_anchor_review_page(sheet)
            html = result.review_page_path.read_text()

        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.pending_count, 1)
        self.assertIn("<audio controls", html)
        self.assertIn(clip.as_uri(), html)
        self.assertIn("00:12-00:16=SPEAKER_01", html)
        self.assertIn('id="export-json"', html)
        self.assertIn('data-approve="1"', html)
        self.assertIn('data-reject="1"', html)
        embedded = html.split('<script type="application/json" id="review-sheet-data">', 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(embedded)["rows"][0]["index"], 1)

    def test_verify_anchor_review_page_checks_required_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clip = root / "candidate.wav"
            clip.write_bytes(b"RIFF")
            sheet = root / "review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "target_speaker_label": "SPEAKER_01",
                        "rows": [
                            {
                                "index": 1,
                                "status": "pending",
                                "approved": False,
                                "target_speaker_label": "SPEAKER_01",
                                "start": 12.06,
                                "end": 16.06,
                                "clip_path": str(clip),
                                "suggested_speaker_correction": "00:12-00:16=SPEAKER_01",
                            }
                        ],
                    }
                )
            )
            page = create_anchor_review_page(sheet).review_page_path

            result = verify_anchor_review_page(sheet, page)

        self.assertTrue(result.passed)
        self.assertEqual(result.audio_count, 1)
        self.assertEqual(result.approve_count, 1)
        self.assertEqual(result.reject_count, 1)
        self.assertEqual(result.pending_button_count, 1)
        self.assertEqual(result.note_count, 1)
        self.assertTrue(result.embedded_sheet_present)
        self.assertTrue(result.import_instruction_present)
        self.assertTrue(result.rerun_instruction_present)
        self.assertEqual(result.as_report()["missing"], [])

    def test_create_anchor_review_bundle_copies_clips_and_uses_relative_audio_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clip = root / "candidate.wav"
            clip.write_bytes(b"RIFF")
            sheet = root / "review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "target_speaker_label": "SPEAKER_01",
                        "rows": [
                            {
                                "index": 1,
                                "status": "pending",
                                "approved": False,
                                "target_speaker_label": "SPEAKER_01",
                                "start": 12.06,
                                "end": 16.06,
                                "clip_path": str(clip),
                                "suggested_speaker_correction": "00:12-00:16=SPEAKER_01",
                            }
                        ],
                    }
                )
            )
            bundle = root / "bundle"

            result = create_anchor_review_bundle(sheet, out_dir=bundle)
            bundled_sheet = json.loads(result.bundled_sheet_path.read_text())
            html = result.review_page_path.read_text()
            verification = verify_anchor_review_page(result.bundled_sheet_path, result.review_page_path)
            copied_clip_exists = (bundle / "clips" / "candidate-01.wav").exists()

        self.assertEqual(result.copied_clip_count, 1)
        self.assertEqual(result.missing_clip_count, 0)
        self.assertTrue(copied_clip_exists)
        self.assertEqual(bundled_sheet["rows"][0]["clip_path"], "clips/candidate-01.wav")
        self.assertIn('src="clips/candidate-01.wav"', html)
        self.assertTrue(verification.passed)

    def test_verify_anchor_review_page_fails_when_controls_are_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet = root / "review-sheet.json"
            page = root / "review.html"
            sheet.write_text(json.dumps({"rows": [{"index": 1}]}))
            page.write_text("<html><body><audio></audio></body></html>")

            result = verify_anchor_review_page(sheet, page)

        self.assertFalse(result.passed)
        self.assertIn("approve buttons: expected 1, found 0", result.missing)
        self.assertIn("embedded sheet JSON", result.missing)

    def test_summary_requires_all_rows_reviewed_before_human_reviewed_is_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet = root / "review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "target_speaker_label": "SPEAKER_01",
                        "rows": [
                            {"status": "approved", "approved": True, "start": 12.0, "end": 16.0},
                            {"status": "pending", "approved": False, "start": 20.0, "end": 24.0},
                        ],
                    }
                )
            )

            summary = summarize_anchor_review_sheet(sheet)

        self.assertFalse(summary["human_reviewed"])
        self.assertFalse(summary["passed"])
        self.assertEqual(summary["pending_count"], 1)

    def test_import_anchor_review_sheet_validates_and_normalizes_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "review-sheet.json"
            exported = root / "exported.json"
            imported = root / "imported.json"
            sheet = {
                "target_speaker_label": "SPEAKER_01",
                "rows": [
                    {
                        "index": 1,
                        "status": "pending",
                        "approved": False,
                        "target_speaker_label": "SPEAKER_01",
                        "start": 12.06,
                        "end": 16.06,
                        "clip_path": "/tmp/candidate-1.wav",
                        "suggested_speaker_correction": "00:12-00:16=SPEAKER_01",
                        "reviewer_note": "",
                    },
                    {
                        "index": 2,
                        "status": "pending",
                        "approved": False,
                        "target_speaker_label": "SPEAKER_01",
                        "start": 20.0,
                        "end": 24.0,
                        "clip_path": "/tmp/candidate-2.wav",
                        "suggested_speaker_correction": "00:20-00:24=SPEAKER_01",
                        "reviewer_note": "",
                    },
                ],
            }
            reviewed = json.loads(json.dumps(sheet))
            reviewed["rows"][0]["status"] = "approved"
            reviewed["rows"][0]["approved"] = True
            reviewed["rows"][0]["reviewer_note"] = "clean target speaker"
            reviewed["rows"][1]["status"] = "rejected"
            reviewed["rows"][1]["approved"] = False
            reviewed["rows"][1]["reviewer_note"] = "overlap"
            original.write_text(json.dumps(sheet))
            exported.write_text(json.dumps(reviewed))

            result = import_anchor_review_sheet(original, exported, out_path=imported)
            summary = summarize_anchor_review_sheet(imported)
            corrections = compile_anchor_review_corrections(imported)

        self.assertTrue(result.human_reviewed)
        self.assertEqual(result.approved_count, 1)
        self.assertEqual(result.rejected_count, 1)
        self.assertEqual(result.pending_count, 0)
        self.assertTrue(summary["passed"])
        self.assertEqual(corrections.cli_args, ["--speaker-correction", "00:12-00:16=SPEAKER_01"])

    def test_import_anchor_review_sheet_rejects_changed_clip_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "review-sheet.json"
            exported = root / "exported.json"
            sheet = {
                "rows": [
                    {
                        "index": 1,
                        "status": "pending",
                        "approved": False,
                        "target_speaker_label": "SPEAKER_01",
                        "start": 12.06,
                        "end": 16.06,
                        "clip_path": "/tmp/candidate-1.wav",
                        "suggested_speaker_correction": "00:12-00:16=SPEAKER_01",
                    },
                ],
            }
            reviewed = json.loads(json.dumps(sheet))
            reviewed["rows"][0]["clip_path"] = "/tmp/other.wav"
            original.write_text(json.dumps(sheet))
            exported.write_text(json.dumps(reviewed))

            with self.assertRaisesRegex(ValueError, "immutable field clip_path"):
                import_anchor_review_sheet(original, exported)

    def test_build_anchor_review_rerun_command_preserves_decompose_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet = root / "review-sheet.json"
            manifest = root / "pavo-decompose-manifest.json"
            sheet.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "index": 1,
                                "status": "approved",
                                "approved": True,
                                "target_speaker_label": "SPEAKER_01",
                                "start": 12.06,
                                "end": 16.06,
                                "suggested_speaker_correction": "00:12-00:16=SPEAKER_01",
                            }
                        ],
                    }
                )
            )
            manifest.write_text(
                json.dumps(
                    {
                        "source_id": "plaud_c37_original",
                        "audio_path": "/tmp/audio.mp3",
                        "engines": ["faster-whisper"],
                        "title": "Plaud c37",
                        "context_terms": ["Plaud", "Pavo"],
                        "num_speakers": 2,
                        "speakers": ["SPEAKER_00=Speaker 0=speaker-0", "SPEAKER_01=Speaker 1=speaker-1"],
                        "max_regions": 5,
                        "padding": 0.25,
                        "min_duration": 0.25,
                        "include_rejected_stems": True,
                    }
                )
            )

            result = build_anchor_review_rerun_command(sheet, manifest)

        self.assertEqual(result.approved_count, 1)
        self.assertEqual(result.command[:5], ["pavo", "audio", "decompose", "/tmp/audio.mp3", "--source-id"])
        self.assertIn("plaud_c37_original_reviewed", result.command)
        self.assertIn("--speaker-correction", result.command)
        self.assertIn("00:12-00:16=SPEAKER_01", result.command)
        self.assertIn("--include-rejected-stems", result.command)
        self.assertIn("'Plaud c37'", result.shell_command)

    def test_build_anchor_review_rerun_command_requires_approved_corrections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet = root / "review-sheet.json"
            manifest = root / "pavo-decompose-manifest.json"
            sheet.write_text(json.dumps({"rows": [{"status": "pending", "approved": False}]}))
            manifest.write_text(json.dumps({"source_id": "source", "audio_path": "/tmp/audio.mp3"}))

            with self.assertRaisesRegex(ValueError, "no approved speaker corrections"):
                build_anchor_review_rerun_command(sheet, manifest)

    def test_gate_anchor_review_passes_when_review_and_rerun_are_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet = root / "review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "rows": [
                            {"index": 1, "status": "approved", "approved": True},
                            {"index": 2, "status": "rejected", "approved": False},
                        ]
                    }
                )
            )
            page = root / "page.json"
            bundle = root / "bundle.json"
            browser = root / "browser.json"
            rerun = root / "rerun.json"
            page.write_text(json.dumps({"passed": True}))
            bundle.write_text(json.dumps({"passed": True}))
            browser.write_text(json.dumps({"passed": True}))
            rerun.write_text(json.dumps({"rerun_command_ready": True}))

            result = gate_anchor_review(
                sheet,
                page_report_path=page,
                bundle_manifest_path=bundle,
                browser_report_path=browser,
                rerun_report_path=rerun,
            )

        self.assertTrue(result.passed)
        self.assertTrue(result.human_reviewed)
        self.assertEqual(result.approved_count, 1)
        self.assertEqual(result.rejected_count, 1)
        self.assertEqual(result.pending_count, 0)
        self.assertEqual(result.blockers, [])
        self.assertEqual(result.next_action, "run the rerun command and regenerate Plaud decompose proof")


if __name__ == "__main__":
    unittest.main()
