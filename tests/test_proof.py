import json
import tempfile
import unittest
from pathlib import Path

from pavo.proof import conan_experience_comparison_report, nz_slang_comparison_report


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


if __name__ == "__main__":
    unittest.main()
