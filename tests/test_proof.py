import json
import tempfile
import unittest
from pathlib import Path

from pavo.proof import (
    accepted_stem_asr_recovery_report,
    conan_demo_video_report,
    conan_experience_comparison_report,
    conan_old_sitcom_report,
    nz_slang_comparison_report,
    plaud_anchor_quality_report,
    plaud_anchor_review_clip_packet,
    plaud_anchor_review_packet,
    plaud_decompose_recording_report,
    plaud_real_recording_report,
    proof_status_summary,
    real_media_accepted_stems_audit,
    real_media_decompose_search_report,
    stem_asr_improvement_search_report,
    stem_asr_improvement_report,
)


class ProofTests(unittest.TestCase):
    def test_committed_conan_experience_report_is_passing(self):
        report_path = Path(__file__).resolve().parents[1] / "docs" / "conan-experience-comparison-report.json"
        report = json.loads(report_path.read_text())

        self.assertTrue(report["passed"])
        self.assertTrue(report["youtube_has_phrase"])
        self.assertFalse(report["youtube_has_speaker_names"])
        self.assertTrue(report["pavo_preserves_speaker_evidence"])

    def test_committed_nz_slang_report_is_passing(self):
        report_path = Path(__file__).resolve().parents[1] / "docs" / "nz-slang-comparison-report.json"
        report = json.loads(report_path.read_text())

        self.assertTrue(report["passed"])
        self.assertFalse(report["youtube_has_speaker_names"])
        self.assertEqual(report["improved_terms"], ["box of birds", "sweet as", "bottle of milk"])
        self.assertGreaterEqual(report["speaker_count"], 2)

    def test_committed_conan_demo_video_report_is_passing(self):
        report_path = Path(__file__).resolve().parents[1] / "docs" / "conan-demo-video-report.json"
        report = json.loads(report_path.read_text())

        self.assertTrue(report["passed"])
        self.assertTrue(report["final_video_present"])
        self.assertTrue(report["comparison_valid"])
        self.assertTrue(report["narration_present"])
        self.assertEqual(report["missing_sections"], [])

    def test_committed_plaud_real_recording_report_is_partial_not_full_item_24(self):
        report_path = Path(__file__).resolve().parents[1] / "docs" / "plaud-real-recording-report.json"
        report = json.loads(report_path.read_text())

        self.assertFalse(report["passed"])
        self.assertTrue(report["partial"])
        self.assertTrue(report["stages"]["download"])
        self.assertTrue(report["stages"]["transcribe"])
        self.assertIn("decomposition", report["missing_stages"])
        self.assertIn("stem_asr", report["missing_stages"])

    def test_committed_plaud_decompose_report_proves_item_24_pipeline(self):
        report_path = Path(__file__).resolve().parents[1] / "docs" / "plaud-d535-decompose-report.json"
        report = json.loads(report_path.read_text())

        self.assertTrue(report["passed"])
        self.assertTrue(report["stages"]["download"])
        self.assertTrue(report["stages"]["voiceprints"])
        self.assertTrue(report["stages"]["speaker_change_detection"])
        self.assertTrue(report["stages"]["decomposition"])
        self.assertTrue(report["stages"]["stem_asr"])
        self.assertGreaterEqual(report["speaker_signature_count"], 2)
        self.assertGreaterEqual(report["separated_region_count"], 1)
        self.assertGreaterEqual(report["transcribed_stem_count"], 1)
        self.assertFalse(report["accepted_stems_passed"])

    def test_committed_plaud_c37_report_proves_second_real_plaud_attempt_without_accepted_stems(self):
        report_path = Path(__file__).resolve().parents[1] / "docs" / "plaud-c37-decompose-report.json"
        report = json.loads(report_path.read_text())

        self.assertTrue(report["passed"])
        self.assertEqual(report["accepted_region_count"], 0)
        self.assertFalse(report["accepted_stems_passed"])
        self.assertGreaterEqual(report["region_count"], 5)
        self.assertGreaterEqual(report["transcribed_stem_count"], 10)

    def test_committed_plaud_anchor_quality_report_records_remaining_blocker(self):
        report_path = Path(__file__).resolve().parents[1] / "docs" / "plaud-anchor-quality-report.json"
        report = json.loads(report_path.read_text())

        self.assertFalse(report["passed"])
        self.assertEqual(report["attempt_count"], 2)
        self.assertEqual(report["human_reviewed_attempt_count"], 0)
        self.assertEqual(report["accepted_stem_attempt_count"], 0)
        self.assertTrue(any("speaker anchors are not human-reviewed" in attempt["blockers"] for attempt in report["attempts"]))

    def test_committed_plaud_c37_anchor_review_packet_lists_speaker_1_candidates(self):
        report_path = Path(__file__).resolve().parents[1] / "docs" / "plaud-c37-speaker1-anchor-review-packet.json"
        report = json.loads(report_path.read_text())

        self.assertFalse(report["passed"])
        self.assertEqual(report["target_speaker_label"], "SPEAKER_01")
        self.assertGreaterEqual(report["existing_sample_count"], 5)
        self.assertGreater(report["review_candidate_count"], 0)
        self.assertGreater(len(report["suggested_speaker_corrections"]), 0)

    def test_committed_plaud_c37_anchor_review_clip_packet_is_ready_for_human_review(self):
        report_path = Path(__file__).resolve().parents[1] / "docs" / "plaud-c37-speaker1-anchor-review-clips.json"
        report = json.loads(report_path.read_text())

        self.assertTrue(report["passed"])
        self.assertFalse(report["human_reviewed"])
        self.assertEqual(report["target_speaker_label"], "SPEAKER_01")
        self.assertTrue(report["source_audio_present"])
        self.assertGreaterEqual(report["candidate_count"], 20)
        self.assertGreaterEqual(report["clip_count"], 20)
        self.assertEqual(report["missing_clips"], [])
        self.assertTrue(all(clip["present"] for clip in report["clips"]))

    def test_committed_conan_old_sitcom_report_has_accepted_stem_asr_proof(self):
        report_path = Path(__file__).resolve().parents[1] / "docs" / "conan-old-sitcom-report.json"
        report = json.loads(report_path.read_text())

        self.assertTrue(report["passed"])
        self.assertTrue(report["overlap_detected"])
        self.assertFalse(report["all_regions_rejected"])
        self.assertTrue(report["accepted_stem_asr_available"])
        self.assertFalse(report["stem_asr_improvement_passed"])
        self.assertGreater(report["trusted_segment_count"], 0)

    def test_committed_stem_asr_improvement_report_keeps_gap_open(self):
        report_path = Path(__file__).resolve().parents[1] / "docs" / "stem-asr-improvement-report.json"
        report = json.loads(report_path.read_text())

        self.assertFalse(report["passed"])
        self.assertTrue(report["reviewed"])
        self.assertGreater(report["trusted_stem_segment_count"], 0)
        self.assertEqual(report["recovered_terms"], [])
        self.assertIn("that old sitcom", report["mixed_text"].lower())

    def test_committed_accepted_stem_asr_recovery_report_closes_real_media_recovery_gap(self):
        report_path = Path(__file__).resolve().parents[1] / "docs" / "accepted-stem-asr-recovery-report.json"
        report = json.loads(report_path.read_text())

        self.assertTrue(report["passed"])
        self.assertFalse(report["reviewed"])
        self.assertGreaterEqual(report["comparison_count"], 2)
        self.assertGreaterEqual(report["recovered_item_count"], 3)
        self.assertTrue(any(item["term"] == "who" for item in report["recovered_items"]))

    def test_committed_stem_asr_improvement_search_report_records_broader_search(self):
        report_path = Path(__file__).resolve().parents[1] / "docs" / "stem-asr-improvement-search-report.json"
        report = json.loads(report_path.read_text())

        self.assertFalse(report["passed"])
        self.assertGreaterEqual(report["manifest_count"], 4)
        self.assertGreaterEqual(report["region_count"], 20)
        self.assertGreaterEqual(report["accepted_region_count"], 1)
        self.assertFalse(report["improvement_passed"])

    def test_committed_nz_decompose_search_report_records_generic_signature_search(self):
        report_path = Path(__file__).resolve().parents[1] / "docs" / "nz-decompose-proof-search-report.json"
        report = json.loads(report_path.read_text())

        self.assertFalse(report["passed"])
        self.assertTrue(report["speaker_signatures_present"])
        self.assertTrue(report["rolling_transcript_present"])
        self.assertEqual(report["accepted_region_count"], 0)
        self.assertGreaterEqual(report["separated_region_count"], 20)
        self.assertGreaterEqual(report["trusted_stem_region_count"], 11)
        self.assertGreaterEqual(report["transcribed_stem_count"], 40)
        self.assertTrue(report["include_rejected"])

    def test_committed_real_media_accepted_stems_audit_records_accepted_overlap(self):
        report_path = Path(__file__).resolve().parents[1] / "docs" / "real-media-accepted-stems-audit.json"
        report = json.loads(report_path.read_text())

        self.assertTrue(report["passed"])
        self.assertGreaterEqual(report["accepted_report_count"], 1)
        self.assertGreaterEqual(report["accepted_report_with_window_checks_count"], 1)
        self.assertGreaterEqual(report["separation_report_count"], 1)

    def test_committed_proof_status_summary_records_current_goal_gap(self):
        report_path = Path(__file__).resolve().parents[1] / "docs" / "proof-status-summary.json"
        report = json.loads(report_path.read_text())

        self.assertFalse(report["passed"])
        self.assertEqual(report["total_count"], 25)
        self.assertEqual(report["proved_count"], 25)
        self.assertTrue(report["accepted_real_media_stems"])
        self.assertTrue(report["accepted_real_media_stems_with_window_checks"])
        self.assertEqual(report["plaud_decompose_attempt_count"], 2)
        self.assertEqual(report["plaud_accepted_stem_attempt_count"], 0)
        self.assertTrue(report["plaud_anchor_review_clip_packet_ready"])
        self.assertGreaterEqual(report["plaud_anchor_review_clip_count"], 20)
        self.assertTrue(report["plaud_anchor_review_sheet_ready"])
        self.assertEqual(report["plaud_anchor_review_sheet_pending_count"], 20)
        self.assertEqual(report["plaud_anchor_review_sheet_approved_count"], 0)
        self.assertTrue(report["plaud_anchor_review_page_ready"])
        self.assertEqual(report["plaud_anchor_review_page_audio_count"], 20)
        self.assertEqual(report["plaud_anchor_review_page_approve_count"], 20)
        self.assertEqual(report["plaud_anchor_review_page_missing"], [])
        self.assertTrue(report["plaud_anchor_review_bundle_ready"])
        self.assertEqual(report["plaud_anchor_review_bundle_clip_count"], 20)
        self.assertEqual(report["plaud_anchor_review_bundle_url"], "http://127.0.0.1:9876/index.html")
        self.assertEqual(
            report["plaud_anchor_review_bundle_serve_command"],
            "pavo review anchors serve docs/plaud-c37-anchor-review-bundle --port 9876",
        )
        self.assertTrue(report["plaud_anchor_review_bundle_serve_command_verified"])
        self.assertTrue(report["plaud_anchor_review_browser_verified"])
        self.assertEqual(report["plaud_anchor_review_browser_audio_count"], 20)
        self.assertEqual(report["plaud_anchor_review_browser_approve_count"], 20)
        self.assertFalse(report["plaud_anchor_review_gate_passed"])
        self.assertIn("20 review rows are still pending", report["plaud_anchor_review_gate_blockers"])
        self.assertIn("no speaker-anchor clips are approved", report["plaud_anchor_review_gate_blockers"])
        self.assertFalse(report["plaud_anchor_rerun_command_ready"])
        self.assertEqual(report["plaud_anchor_rerun_command_approved_count"], 0)
        self.assertEqual(report["plaud_anchor_rerun_command_pending_count"], 20)
        self.assertIn("no approved speaker corrections", report["plaud_anchor_rerun_command_blocked_reason"])
        self.assertTrue(report["merge_policy_reviewed"])
        self.assertGreater(report["reviewable_real_media_stem_count"], 0)
        self.assertEqual(report["nz_decompose_search_region_count"], 20)
        self.assertEqual(report["nz_decompose_search_transcribed_stem_count"], 40)
        self.assertEqual(report["nz_decompose_search_accepted_region_count"], 0)
        self.assertEqual(report["nz_decompose_search_trusted_stem_region_count"], 11)
        self.assertNotIn("real accepted stems on a real overlap clip", report["remaining_gaps"])
        self.assertTrue(report["real_media_stem_asr_improvement"])
        self.assertGreaterEqual(report["real_media_stem_asr_recovery_item_count"], 3)
        self.assertNotIn("real-media comparison showing stem ASR recovers words missed by mixed-audio ASR", report["remaining_gaps"])
        self.assertNotIn("reviewed merge policy for when stem ASR can augment or override the canonical transcript", report["remaining_gaps"])

    def test_conan_experience_comparison_proves_pavo_adds_named_speaker_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            comparison = Path(tmp) / "comparison.json"
            comparison.write_text(
                json.dumps(
                    {
                        "youtube_has_speaker_names": False,
                        "pavo_named_speakers": ["Conan O'Brien", "Kaitlin Olson"],
                        "cases": [
                            {
                                "label": "Opening prompt",
                                "youtube": "do you remember the first time you met danny what was that experience",
                                "pavo": [
                                    {
                                        "start": 5.56,
                                        "end": 6.84,
                                        "speaker": "Kaitlin Olson",
                                        "text": "what was that experience like?",
                                        "rolling_fingerprint": {
                                            "status": "mixed",
                                            "runs": [
                                                {"best_slug": "conan-obrien"},
                                                {"best_slug": "kaitlin-olson"},
                                            ],
                                        },
                                    }
                                ],
                            }
                        ],
                    }
                )
            )

            report = conan_experience_comparison_report(comparison)

        self.assertTrue(report["passed"])
        self.assertFalse(report["youtube_has_speaker_names"])
        self.assertTrue(report["youtube_has_phrase"])
        self.assertEqual(report["phrase_speaker"], "Kaitlin Olson")
        self.assertTrue(report["pavo_preserves_speaker_evidence"])

    def test_conan_experience_comparison_fails_without_mixed_pavo_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            comparison = Path(tmp) / "comparison.json"
            comparison.write_text(
                json.dumps(
                    {
                        "youtube_has_speaker_names": False,
                        "pavo_named_speakers": ["Conan O'Brien", "Kaitlin Olson"],
                        "cases": [
                            {
                                "label": "Opening prompt",
                                "youtube": "what was that experience",
                                "pavo": [
                                    {
                                        "speaker": "Kaitlin Olson",
                                        "text": "what was that experience like?",
                                        "rolling_fingerprint": {
                                            "status": "single",
                                            "runs": [{"best_slug": "kaitlin-olson"}],
                                        },
                                    }
                                ],
                            }
                        ],
                    }
                )
            )

            report = conan_experience_comparison_report(comparison)

        self.assertFalse(report["passed"])
        self.assertFalse(report["pavo_preserves_speaker_evidence"])

    def test_nz_slang_comparison_proves_required_terms_improved_over_youtube(self):
        with tempfile.TemporaryDirectory() as tmp:
            comparison = Path(tmp) / "comparison.json"
            comparison.write_text(
                json.dumps(
                    {
                        "title": "New Zealand Accent/ Slang",
                        "channel": "King Country Kiwi",
                        "youtube_has_speaker_names": False,
                        "pavo_best_method": "resemblyzer-kmeans",
                        "speaker_count": 6,
                        "term_presence": {
                            "box of birds": {"youtube": False, "pavo": True},
                            "sweet as": {"youtube": False, "pavo": True},
                            "bottle of milk": {"youtube": False, "pavo": True},
                        },
                    }
                )
            )

            report = nz_slang_comparison_report(comparison)

        self.assertTrue(report["passed"])
        self.assertEqual(report["improved_term_count"], 3)
        self.assertEqual(report["missing_improvements"], [])

    def test_nz_slang_comparison_fails_when_required_term_is_not_improved(self):
        with tempfile.TemporaryDirectory() as tmp:
            comparison = Path(tmp) / "comparison.json"
            comparison.write_text(
                json.dumps(
                    {
                        "youtube_has_speaker_names": False,
                        "speaker_count": 6,
                        "term_presence": {
                            "box of birds": {"youtube": False, "pavo": True},
                            "sweet as": {"youtube": True, "pavo": True},
                            "bottle of milk": {"youtube": False, "pavo": True},
                        },
                    }
                )
            )

            report = nz_slang_comparison_report(comparison)

        self.assertFalse(report["passed"])
        self.assertEqual(report["missing_improvements"][0]["term"], "sweet as")

    def test_conan_demo_video_report_requires_expected_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            normalized = root / "normalized"
            normalized.mkdir()
            (root / "pavo-conan-demo.mp4").write_bytes(b"video")
            (root / "narration.txt").write_text("Pavo explains the overlap.\n")
            (root / "comparison.json").write_text(
                json.dumps({"youtube_has_speaker_names": False, "cases": [{"label": "Opening prompt"}]})
            )
            required = ["02-youtube.mp4", "03-pavo-captioned.mp4", "05-ai-explainer.mp4"]
            for name in required:
                (normalized / name).write_bytes(b"segment")

            report = conan_demo_video_report(root, required_sections=required)

        self.assertTrue(report["passed"])
        self.assertEqual(report["section_count"], 3)
        self.assertEqual(report["missing_sections"], [])

    def test_conan_demo_video_report_fails_when_section_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            normalized = root / "normalized"
            normalized.mkdir()
            (root / "pavo-conan-demo.mp4").write_bytes(b"video")
            (root / "narration.txt").write_text("Pavo explains the overlap.\n")
            (root / "comparison.json").write_text(
                json.dumps({"youtube_has_speaker_names": False, "cases": [{"label": "Opening prompt"}]})
            )

            report = conan_demo_video_report(root, required_sections=["02-youtube.mp4"])

        self.assertFalse(report["passed"])
        self.assertEqual(report["missing_sections"], ["02-youtube.mp4"])

    def test_plaud_real_recording_report_marks_transcribe_only_run_as_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.mp3"
            audio.write_bytes(b"audio")
            transcribe = root / "transcribe"
            raw_dir = transcribe / "faster-whisper"
            raw_dir.mkdir(parents=True)
            raw_json = raw_dir / "transcript.json"
            raw_json.write_text("{}\n")
            ensemble = transcribe / "ensembled-contextual-transcript.md"
            ensemble.write_text("# transcript\n")
            eidos_manifest = transcribe / "manifest.json"
            eidos_manifest.write_text(
                json.dumps(
                    {
                        "engines": ["faster-whisper"],
                        "raw_outputs": {"faster-whisper": str(raw_json)},
                        "ensemble": str(ensemble),
                        "method": "timed primary-spine ensemble",
                    }
                )
            )
            (root / "pavo-transcribe-manifest.json").write_text(
                json.dumps(
                    {
                        "recording_id": "rec_123",
                        "audio_path": str(audio),
                        "audio_sha256": "abc123",
                        "eidos_transcribe_manifest": str(eidos_manifest),
                        "engines": ["faster-whisper"],
                        "context_terms": ["Plaud", "Pavo"],
                    }
                )
            )

            report = plaud_real_recording_report(root)

        self.assertFalse(report["passed"])
        self.assertTrue(report["partial"])
        self.assertTrue(report["stages"]["download"])
        self.assertTrue(report["stages"]["transcribe"])
        self.assertFalse(report["stages"]["decomposition"])
        self.assertEqual(report["missing_transcribe_paths"], [])

    def test_plaud_real_recording_report_passes_when_all_item_24_manifests_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.mp3"
            audio.write_bytes(b"audio")
            transcribe = root / "transcribe"
            raw_dir = transcribe / "faster-whisper"
            raw_dir.mkdir(parents=True)
            raw_json = raw_dir / "transcript.json"
            raw_json.write_text("{}\n")
            ensemble = transcribe / "ensembled-contextual-transcript.md"
            ensemble.write_text("# transcript\n")
            eidos_manifest = transcribe / "manifest.json"
            eidos_manifest.write_text(
                json.dumps(
                    {
                        "engines": ["faster-whisper"],
                        "raw_outputs": {"faster-whisper": str(raw_json)},
                        "ensemble": str(ensemble),
                        "method": "timed primary-spine ensemble",
                    }
                )
            )
            (root / "pavo-transcribe-manifest.json").write_text(
                json.dumps(
                    {
                        "recording_id": "rec_123",
                        "audio_path": str(audio),
                        "audio_sha256": "abc123",
                        "eidos_transcribe_manifest": str(eidos_manifest),
                        "engines": ["faster-whisper"],
                        "context_terms": ["Plaud", "Pavo"],
                    }
                )
            )
            decompose = root / "decompose-transcribe"
            (decompose / "speaker-pipeline").mkdir(parents=True)
            (decompose / "stem-asr").mkdir()
            (root / "pavo-decompose-manifest.json").write_text("{}\n")
            (decompose / "decompose-transcribe.manifest.json").write_text("{}\n")
            (decompose / "speaker-pipeline" / "speaker-pipeline.manifest.json").write_text("{}\n")
            (decompose / "stem-asr" / "stem-asr.manifest.json").write_text("{}\n")

            report = plaud_real_recording_report(root)

        self.assertTrue(report["passed"])
        self.assertFalse(report["partial"])
        self.assertEqual(report["missing_stages"], [])

    def test_plaud_decompose_recording_report_passes_full_pipeline_with_rejected_stems(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.mp3"
            audio.write_bytes(b"audio")
            out = root / "decompose-transcribe"
            speaker_dir = out / "process-call" / "speaker-pipeline"
            signatures_dir = speaker_dir / "speaker-signatures"
            separated_dir = out / "separated-overlaps" / "region-01"
            stem_asr_dir = out / "stem-asr"
            for directory in [signatures_dir, separated_dir, stem_asr_dir]:
                directory.mkdir(parents=True)
            signatures_manifest = signatures_dir / "speaker-signatures.manifest.json"
            signatures_manifest.write_text(
                json.dumps(
                    {
                        "speakers": [
                            {"slug": "speaker-0", "sample_count": 2},
                            {"slug": "speaker-1", "sample_count": 3},
                        ]
                    }
                )
            )
            speaker_manifest = speaker_dir / "speaker-pipeline.manifest.json"
            speaker_manifest.write_text(
                json.dumps(
                    {
                        "num_speakers": 2,
                        "best_method": "mfcc-kmeans",
                        "speaker_immune_summary": {"segments": 4, "immune_counts": {"rolling_split_applied": 2}},
                    }
                )
            )
            region = separated_dir / "analysis.json"
            region.write_text(
                json.dumps(
                    {
                        "accepted": False,
                        "region": {"start": 0.0, "end": 5.0},
                        "stem_reports": {
                            "speaker-0": {"wrong_rate": 0.2, "whole_clip": {"margin": 0.03}},
                            "speaker-1": {"wrong_rate": 0.3, "whole_clip": {"margin": 0.04}},
                        },
                    }
                )
            )
            separation_manifest = out / "separated-overlaps" / "separate-overlaps.manifest.json"
            separation_manifest.write_text(json.dumps({"regions": [str(region)]}))
            decomposed = stem_asr_dir / "decomposed-transcript.json"
            decomposed.write_text(json.dumps({"segments": [{"trusted": False}, {"trusted": False}]}))
            stem_asr = stem_asr_dir / "stem-asr.manifest.json"
            stem_asr.write_text(json.dumps({"transcribed_stem_count": 2, "decomposed_transcript_json": str(decomposed)}))
            eidos_manifest = out / "decompose-transcribe.manifest.json"
            eidos_manifest.write_text(
                json.dumps(
                    {
                        "speaker_signatures_manifest": str(signatures_manifest),
                        "overlap_separation_manifest": str(separation_manifest),
                        "separated_region_count": 1,
                        "stem_asr_manifest": str(stem_asr),
                        "decomposed_transcript_json": str(decomposed),
                    }
                )
            )
            (root / "pavo-decompose-manifest.json").write_text(
                json.dumps(
                    {
                        "source_id": "plaud_rec",
                        "audio_path": str(audio),
                        "audio_sha256": "abc123",
                        "eidos_transcribe_manifest": str(eidos_manifest),
                    }
                )
            )

            report = plaud_decompose_recording_report(root)

        self.assertTrue(report["passed"])
        self.assertFalse(report["accepted_stems_passed"])
        self.assertEqual(report["trusted_segment_count"], 0)

    def test_plaud_decompose_recording_report_fails_without_voiceprints(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.mp3"
            audio.write_bytes(b"audio")
            out = root / "decompose-transcribe"
            out.mkdir()
            eidos_manifest = out / "decompose-transcribe.manifest.json"
            eidos_manifest.write_text(json.dumps({}))
            (root / "pavo-decompose-manifest.json").write_text(
                json.dumps({"source_id": "plaud_rec", "audio_path": str(audio), "eidos_transcribe_manifest": str(eidos_manifest)})
            )

            report = plaud_decompose_recording_report(root)

        self.assertFalse(report["passed"])
        self.assertFalse(report["stages"]["voiceprints"])

    def test_plaud_anchor_quality_report_requires_human_review_and_accepted_stems(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            signatures = root / "speaker-signatures.manifest.json"
            decompose = root / "decompose-report.json"
            signatures.write_text(
                json.dumps(
                    {
                        "speakers": [
                            {"speaker_label": "SPEAKER_00", "name": "Speaker 0", "slug": "speaker-0", "sample_count": 24},
                            {"speaker_label": "SPEAKER_01", "name": "Speaker 1", "slug": "speaker-1", "sample_count": 4},
                        ]
                    }
                )
            )
            decompose.write_text(json.dumps({"passed": True, "accepted_stems_passed": False}))

            report = plaud_anchor_quality_report(
                [
                    {
                        "label": "attempt",
                        "signatures_manifest": str(signatures),
                        "decompose_report": str(decompose),
                        "human_reviewed": False,
                    }
                ]
            )

        self.assertFalse(report["passed"])
        self.assertEqual(report["attempts"][0]["min_sample_count"], 4)
        self.assertIn("speaker anchors are not human-reviewed", report["attempts"][0]["blockers"])
        self.assertIn("no accepted Plaud separated stems", report["attempts"][0]["blockers"])
        self.assertIn("one or more speakers has fewer than 8 enrollment samples", report["attempts"][0]["blockers"])

    def test_plaud_anchor_review_packet_suggests_reviewable_speaker_corrections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            signatures = root / "speaker-signatures.manifest.json"
            attributed = root / "attributed.json"
            signatures.write_text(
                json.dumps(
                    {
                        "source_audio_wav": "/tmp/audio.wav",
                        "speakers": [
                            {
                                "speaker_label": "SPEAKER_01",
                                "name": "Speaker 1",
                                "sample_count": 1,
                                "sample_seconds": 4.0,
                                "sample_spans": [
                                    {"start": 10.0, "end": 14.0, "confidence": 0.96, "method": "audio_overlap", "text": "sample"}
                                ],
                            }
                        ],
                    }
                )
            )
            attributed.write_text(
                json.dumps(
                    [
                        {
                            "start": 20.0,
                            "end": 24.0,
                            "speaker_label": "SPEAKER_01",
                            "speaker": "Speaker 1",
                            "confidence": 0.92,
                            "method": "audio_overlap",
                            "text": "candidate span",
                        },
                        {
                            "start": 30.0,
                            "end": 31.0,
                            "speaker_label": "SPEAKER_01",
                            "speaker": "Speaker 1",
                            "confidence": 0.99,
                            "method": "audio_overlap",
                            "text": "too short",
                        },
                    ]
                )
            )

            report = plaud_anchor_review_packet(
                signatures_manifest=signatures,
                attributed_transcript=attributed,
                target_speaker_label="SPEAKER_01",
            )

        self.assertFalse(report["passed"])
        self.assertEqual(report["existing_sample_count"], 1)
        self.assertEqual(report["review_candidate_count"], 1)
        self.assertEqual(report["suggested_speaker_corrections"], ["00:20-00:24=SPEAKER_01"])

    def test_plaud_anchor_review_clip_packet_requires_all_candidate_clips(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            clips = root / "clips"
            clips.mkdir()
            audio.write_bytes(b"audio")
            packet = root / "review.json"
            packet.write_text(
                json.dumps(
                    {
                        "target_speaker_label": "SPEAKER_01",
                        "target_speaker_name": "Speaker 1",
                        "source_audio_wav": str(audio),
                        "review_candidates": [
                            {"start": 12.06, "end": 16.06, "text": "candidate one"},
                            {"start": 144.6, "end": 148.6, "text": "candidate two"},
                        ],
                    }
                )
            )
            (clips / "candidate-01-001206-001606.wav").write_bytes(b"clip")

            report = plaud_anchor_review_clip_packet(review_packet=packet, clips_dir=clips)

        self.assertFalse(report["passed"])
        self.assertEqual(report["candidate_count"], 2)
        self.assertEqual(report["clip_count"], 1)
        self.assertEqual(len(report["missing_clips"]), 1)
        self.assertEqual(report["clips"][0]["suggested_speaker_correction"], "00:12-00:16=SPEAKER_01")

    def test_plaud_anchor_review_clip_packet_passes_when_all_candidate_clips_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            clips = root / "clips"
            clips.mkdir()
            audio.write_bytes(b"audio")
            packet = root / "review.json"
            packet.write_text(
                json.dumps(
                    {
                        "target_speaker_label": "SPEAKER_01",
                        "source_audio_wav": str(audio),
                        "review_candidates": [
                            {"start": 12.06, "end": 16.06, "text": "candidate one"},
                            {"start": 144.6, "end": 148.6, "text": "candidate two"},
                        ],
                    }
                )
            )
            (clips / "candidate-01-001206-001606.wav").write_bytes(b"clip")
            (clips / "candidate-02-022460-022860.wav").write_bytes(b"clip")

            report = plaud_anchor_review_clip_packet(review_packet=packet, clips_dir=clips)

        self.assertTrue(report["passed"])
        self.assertFalse(report["human_reviewed"])
        self.assertEqual(report["clip_count"], 2)
        self.assertEqual(report["missing_clips"], [])

    def test_conan_old_sitcom_report_proves_rejected_diagnostic_stem_asr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            region_dir = root / "region-01"
            diag_dir = root / "stem-asr-diagnostic"
            region_dir.mkdir()
            diag_dir.mkdir()
            analysis = region_dir / "analysis.json"
            analysis.write_text(
                json.dumps(
                    {
                        "region": {"immune": "not_checked+rolling_mixed"},
                        "accepted": False,
                        "stem_reports": {
                            "conan-obrien": {
                                "target": "Conan O'Brien",
                                "whole_clip": {"best": "Conan O'Brien", "margin": 0.06},
                                "wrong_rate": 0.3333,
                                "path": str(region_dir / "conan-obrien.wav"),
                            },
                            "kaitlin-olson": {
                                "target": "Kaitlin Olson",
                                "whole_clip": {"best": "Kaitlin Olson", "margin": 0.05},
                                "wrong_rate": 0.3333,
                                "path": str(region_dir / "kaitlin-olson.wav"),
                            },
                        },
                    }
                )
            )
            separation_manifest = root / "separate-overlaps.manifest.json"
            separation_manifest.write_text(json.dumps({"candidate_count": 1, "regions": [str(analysis)]}))
            decomposed = diag_dir / "decomposed-transcript.json"
            decomposed.write_text(
                json.dumps(
                    {
                        "merge_policy": "evidence only; does not replace canonical transcript",
                        "segments": [
                            {"trusted": False, "source": "diagnostic_rejected_stem"},
                            {"trusted": False, "source": "diagnostic_rejected_stem"},
                        ],
                    }
                )
            )
            stem_asr_manifest = diag_dir / "stem-asr.manifest.json"
            stem_asr_manifest.write_text(
                json.dumps(
                    {
                        "include_rejected": True,
                        "transcribed_stem_count": 2,
                        "decomposed_transcript_json": str(decomposed),
                    }
                )
            )

            report = conan_old_sitcom_report(separation_manifest, stem_asr_manifest)

        self.assertTrue(report["passed"])
        self.assertEqual(report["accepted_region_count"], 0)
        self.assertEqual(report["transcribed_stem_count"], 2)
        self.assertEqual(report["rejected_segment_count"], 2)

    def test_conan_old_sitcom_report_fails_if_rejected_stems_become_trusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            region_dir = root / "region-01"
            diag_dir = root / "stem-asr-diagnostic"
            region_dir.mkdir()
            diag_dir.mkdir()
            analysis = region_dir / "analysis.json"
            analysis.write_text(
                json.dumps(
                    {
                        "region": {"immune": "not_checked+rolling_mixed"},
                        "accepted": False,
                        "stem_reports": {"conan-obrien": {"target": "Conan O'Brien", "whole_clip": {"best": "Conan O'Brien"}}},
                    }
                )
            )
            separation_manifest = root / "separate-overlaps.manifest.json"
            separation_manifest.write_text(json.dumps({"candidate_count": 1, "regions": [str(analysis)]}))
            decomposed = diag_dir / "decomposed-transcript.json"
            decomposed.write_text(json.dumps({"segments": [{"trusted": True}]}))
            stem_asr_manifest = diag_dir / "stem-asr.manifest.json"
            stem_asr_manifest.write_text(
                json.dumps(
                    {
                        "include_rejected": True,
                        "transcribed_stem_count": 1,
                        "decomposed_transcript_json": str(decomposed),
                    }
                )
            )

            report = conan_old_sitcom_report(separation_manifest, stem_asr_manifest)

        self.assertFalse(report["passed"])
        self.assertFalse(report["diagnostic_available"])

    def test_conan_old_sitcom_report_accepts_trusted_stem_asr_without_claiming_improvement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            region_dir = root / "region-01"
            stem_dir = root / "stem-asr-accepted"
            region_dir.mkdir()
            stem_dir.mkdir()
            analysis = region_dir / "analysis.json"
            analysis.write_text(
                json.dumps(
                    {
                        "region": {"immune": "not_checked+rolling_mixed"},
                        "accepted": True,
                        "stem_reports": {
                            "conan-obrien": {
                                "target": "Conan O'Brien",
                                "whole_clip": {"best": "Conan O'Brien", "margin": 0.12},
                                "wrong_rate": 0.0,
                                "rolling_windows": 1,
                                "path": str(region_dir / "conan-obrien.wav"),
                            },
                            "kaitlin-olson": {
                                "target": "Kaitlin Olson",
                                "whole_clip": {"best": "Kaitlin Olson", "margin": 0.06},
                                "wrong_rate": 0.0,
                                "rolling_windows": 1,
                                "path": str(region_dir / "kaitlin-olson.wav"),
                            },
                        },
                    }
                )
            )
            separation_manifest = root / "separate-overlaps.manifest.json"
            separation_manifest.write_text(json.dumps({"candidate_count": 1, "regions": [str(analysis)]}))
            decomposed = stem_dir / "decomposed-transcript.json"
            decomposed.write_text(
                json.dumps(
                    {
                        "merge_policy": "evidence only; does not replace canonical transcript",
                        "segments": [
                            {"trusted": True, "source": "separated_stem"},
                            {"trusted": True, "source": "separated_stem"},
                        ],
                    }
                )
            )
            stem_asr_manifest = stem_dir / "stem-asr.manifest.json"
            stem_asr_manifest.write_text(
                json.dumps(
                    {
                        "include_rejected": False,
                        "transcribed_stem_count": 2,
                        "decomposed_transcript_json": str(decomposed),
                    }
                )
            )

            report = conan_old_sitcom_report(separation_manifest, stem_asr_manifest)

        self.assertTrue(report["passed"])
        self.assertEqual(report["accepted_region_count"], 1)
        self.assertTrue(report["accepted_stem_asr_available"])
        self.assertFalse(report["stem_asr_improvement_passed"])

    def test_real_media_accepted_stems_audit_passes_when_any_report_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            region = root / "region-01"
            region.mkdir()
            (region / "analysis.json").write_text(
                json.dumps(
                    {
                        "accepted": True,
                        "region": {"start": 10.0, "end": 12.0},
                        "stem_reports": {
                            "speaker-a": {
                                "target": "Speaker A",
                                "wrong_rate": 0.0,
                                "rolling_windows": 1,
                                "whole_clip": {"best": "Speaker A", "margin": 0.2},
                            },
                            "speaker-b": {
                                "target": "Speaker B",
                                "wrong_rate": 0.0,
                                "rolling_windows": 1,
                                "whole_clip": {"best": "Speaker B", "margin": 0.3},
                            },
                        },
                    }
                )
            )

            report = real_media_accepted_stems_audit(root)

        self.assertTrue(report["passed"])
        self.assertEqual(report["accepted_report_count"], 1)
        self.assertEqual(report["accepted_report_with_window_checks_count"], 1)
        self.assertEqual(report["accepted_reports"][0]["stem_count"], 2)

    def test_real_media_accepted_stems_audit_fails_when_reports_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            region = root / "region-01"
            region.mkdir()
            (region / "analysis.json").write_text(
                json.dumps(
                    {
                        "accepted": False,
                        "region": {"start": 10.0, "end": 12.0},
                        "stem_reports": {"speaker-a": {"wrong_rate": 0.5, "whole_clip": {"margin": 0.01}}},
                    }
                )
            )

            report = real_media_accepted_stems_audit(root)

        self.assertFalse(report["passed"])
        self.assertEqual(report["accepted_report_count"], 0)
        self.assertEqual(report["rejected_report_count"], 1)

    def test_real_media_accepted_stems_audit_counts_reviewable_stems_without_passing_region(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            region = root / "region-01"
            region.mkdir()
            (region / "analysis.json").write_text(
                json.dumps(
                    {
                        "accepted": False,
                        "region": {"start": 10.0, "end": 12.0},
                        "stem_reports": {
                            "speaker-a": {
                                "target": "Speaker A",
                                "wrong_rate": 0.0,
                                "whole_clip": {"best": "Speaker A", "margin": 0.2},
                            },
                            "speaker-b": {
                                "target": "Speaker B",
                                "wrong_rate": 1.0,
                                "whole_clip": {"best": "Speaker A", "margin": 0.01},
                            },
                        },
                    }
                )
            )

            report = real_media_accepted_stems_audit(root)

        self.assertFalse(report["passed"])
        self.assertEqual(report["accepted_report_count"], 0)
        self.assertEqual(report["trusted_stem_count"], 1)
        self.assertEqual(report["trusted_stem_report_count"], 1)
        self.assertEqual(report["trusted_stem_reports"][0]["trusted_stems"], ["speaker-a"])

    def test_stem_asr_improvement_report_passes_only_for_reviewed_missing_mixed_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mixed = root / "mixed.json"
            stems = root / "stems.json"
            mixed.write_text(json.dumps({"segments": [{"text": "what was that like"}]}))
            stems.write_text(
                json.dumps(
                    {
                        "segments": [
                            {
                                "trusted": True,
                                "separation_accepted": True,
                                "text": "what was that experience like",
                            }
                        ]
                    }
                )
            )

            report = stem_asr_improvement_report(
                mixed_transcript_path=mixed,
                stem_evidence_path=stems,
                expected_recovered_terms=["experience"],
                reviewed=True,
            )

        self.assertTrue(report["passed"])
        self.assertEqual(report["recovered_terms"], ["experience"])

    def test_stem_asr_improvement_report_fails_when_mixed_asr_already_has_term(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mixed = root / "mixed.json"
            stems = root / "stems.json"
            mixed.write_text(json.dumps({"segments": [{"text": "that old sitcom"}]}))
            stems.write_text(
                json.dumps(
                    {
                        "segments": [
                            {
                                "trusted": True,
                                "separation_accepted": True,
                                "text": "that old sitcom",
                            }
                        ]
                    }
                )
            )

            report = stem_asr_improvement_report(
                mixed_transcript_path=mixed,
                stem_evidence_path=stems,
                expected_recovered_terms=["that old sitcom"],
                reviewed=True,
            )

        self.assertFalse(report["passed"])
        self.assertEqual(report["recovered_terms"], [])

    def test_accepted_stem_asr_recovery_report_passes_for_accepted_real_media_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mixed = root / "mixed.json"
            stem = root / "stem.json"
            mixed.write_text(json.dumps({"segments": [{"text": "Mike. He wrote this caption."}]}))
            stem.write_text(json.dumps({"segments": [{"text": "Mike, who are you? He wrote this caption."}]}))

            report = accepted_stem_asr_recovery_report(
                comparisons=[
                    {
                        "label": "fixture",
                        "mixed_transcript": str(mixed),
                        "stem_transcript": str(stem),
                        "separation_accepted": True,
                        "expected_recovered_terms": ["who"],
                    }
                ]
            )

        self.assertTrue(report["passed"])
        self.assertEqual(report["recovered_items"], [{"label": "fixture", "term": "who"}])

    def test_stem_asr_improvement_search_report_counts_accepted_regions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            accepted = root / "accepted.json"
            rejected = root / "rejected.json"
            manifest = root / "separate-overlaps.manifest.json"
            accepted.write_text(
                json.dumps(
                    {
                        "accepted": True,
                        "region": {"start": 1.0, "end": 2.0, "text": "accepted"},
                        "stem_reports": {
                            "a": {"target": "A", "whole_clip": {"best": "A", "margin": 0.2}, "wrong_rate": 0.0}
                        },
                    }
                )
            )
            rejected.write_text(json.dumps({"accepted": False, "region": {"start": 3.0, "end": 4.0}, "stem_reports": {}}))
            manifest.write_text(json.dumps({"candidate_count": 2, "regions": [str(accepted), str(rejected)]}))

            report = stem_asr_improvement_search_report([manifest], improvement_report={"passed": False})

        self.assertFalse(report["passed"])
        self.assertEqual(report["candidate_count"], 2)
        self.assertEqual(report["accepted_region_count"], 1)
        self.assertEqual(report["manifests"][0]["accepted_region_count"], 1)

    def test_real_media_decompose_search_report_counts_rejected_diagnostic_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            signatures = root / "speaker-signatures.manifest.json"
            rolling = root / "rolling.json"
            separated = root / "separated"
            stem_asr = root / "stem-asr"
            separated.mkdir()
            stem_asr.mkdir()
            signatures.write_text("{}")
            rolling.write_text("[]")
            analysis = separated / "analysis.json"
            analysis.write_text(
                json.dumps(
                    {
                        "accepted": False,
                        "region": {"start": 1.0, "end": 2.0, "text": "candidate"},
                        "stem_reports": {
                            "speaker-00": {
                                "target": "Speaker 0",
                                "wrong_rate": 0.0,
                                "whole_clip": {"best": "Speaker 0", "margin": 0.2},
                            },
                            "speaker-01": {
                                "target": "Speaker 1",
                                "wrong_rate": 1.0,
                                "whole_clip": {"best": "Speaker 0", "margin": 0.01},
                            },
                        },
                    }
                )
            )
            separation_manifest = separated / "separate-overlaps.manifest.json"
            separation_manifest.write_text(json.dumps({"regions": [str(analysis)]}))
            stem_manifest = stem_asr / "stem-asr.manifest.json"
            stem_manifest.write_text(json.dumps({"include_rejected": True, "transcribed_stem_count": 2}))
            manifest = root / "decompose-transcribe.manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "speaker_signatures_manifest": str(signatures),
                        "rolling_attributed_json": str(rolling),
                        "overlap_separation_manifest": str(separation_manifest),
                        "stem_asr_manifest": str(stem_manifest),
                    }
                )
            )

            report = real_media_decompose_search_report(manifest)

        self.assertFalse(report["passed"])
        self.assertTrue(report["speaker_signatures_present"])
        self.assertEqual(report["trusted_stem_region_count"], 1)
        self.assertEqual(report["accepted_region_count"], 0)

    def test_proof_status_summary_keeps_goal_open_without_real_accepted_stems(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp)
            for name in [
                "conan-experience-comparison-report.json",
                "conan-old-sitcom-report.json",
                "nz-slang-comparison-report.json",
                "conan-demo-video-report.json",
            ]:
                (docs / name).write_text(json.dumps({"passed": True}))
            (docs / "plaud-real-recording-report.json").write_text(json.dumps({"partial": True}))
            (docs / "plaud-d535-decompose-report.json").write_text(
                json.dumps({"passed": True, "accepted_stems_passed": False})
            )
            (docs / "real-media-accepted-stems-audit.json").write_text(
                json.dumps({"passed": False, "accepted_report_count": 0, "separation_report_count": 6})
            )

            report = proof_status_summary(docs)

        self.assertFalse(report["passed"])
        self.assertEqual(report["proved_count"], 25)
        self.assertFalse(report["accepted_real_media_stems"])
        self.assertIn("reviewed merge policy for when stem ASR can augment or override the canonical transcript", report["remaining_gaps"])

    def test_proof_status_summary_removes_merge_policy_gap_when_review_policy_is_proved(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp)
            for name in [
                "conan-experience-comparison-report.json",
                "conan-old-sitcom-report.json",
                "nz-slang-comparison-report.json",
                "conan-demo-video-report.json",
            ]:
                (docs / name).write_text(json.dumps({"passed": True}))
            (docs / "plaud-real-recording-report.json").write_text(json.dumps({"partial": True}))
            (docs / "plaud-d535-decompose-report.json").write_text(
                json.dumps({"passed": True, "accepted_stems_passed": False})
            )
            (docs / "real-media-accepted-stems-audit.json").write_text(
                json.dumps({"passed": False, "accepted_report_count": 0, "separation_report_count": 6})
            )
            (docs / "stem-merge-policy-report.json").write_text(json.dumps({"passed": True}))

            report = proof_status_summary(docs)

        self.assertTrue(report["merge_policy_reviewed"])
        self.assertNotIn("reviewed merge policy for when stem ASR can augment or override the canonical transcript", report["remaining_gaps"])


if __name__ == "__main__":
    unittest.main()
