import json
import tempfile
import unittest
from pathlib import Path

from pavo.proof import conan_experience_comparison_report


class ProofTests(unittest.TestCase):
    def test_committed_conan_experience_report_is_passing(self):
        report_path = Path(__file__).resolve().parents[1] / "docs" / "conan-experience-comparison-report.json"
        report = json.loads(report_path.read_text())

        self.assertTrue(report["passed"])
        self.assertTrue(report["youtube_has_phrase"])
        self.assertFalse(report["youtube_has_speaker_names"])
        self.assertTrue(report["pavo_preserves_speaker_evidence"])

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


if __name__ == "__main__":
    unittest.main()
