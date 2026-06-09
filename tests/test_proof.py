import json
import tempfile
import unittest
from pathlib import Path

from pavo.proof import (
    conan_demo_video_report,
    conan_experience_comparison_report,
    conan_old_sitcom_report,
    nz_slang_comparison_report,
    plaud_real_recording_report,
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

    def test_committed_conan_old_sitcom_report_is_passing_rejected_diagnostic_proof(self):
        report_path = Path(__file__).resolve().parents[1] / "docs" / "conan-old-sitcom-report.json"
        report = json.loads(report_path.read_text())

        self.assertTrue(report["passed"])
        self.assertTrue(report["overlap_detected"])
        self.assertTrue(report["all_regions_rejected"])
        self.assertTrue(report["diagnostic_available"])
        self.assertEqual(report["trusted_segment_count"], 0)

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


if __name__ == "__main__":
    unittest.main()
