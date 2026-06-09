import json
import tempfile
import unittest
from pathlib import Path

from pavo.review import (
    compile_anchor_review_corrections,
    create_anchor_review_sheet,
    summarize_anchor_review_sheet,
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


if __name__ == "__main__":
    unittest.main()
