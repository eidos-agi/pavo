import json
import tempfile
import unittest
from pathlib import Path

from pavo.brief import build_meeting_brief, write_meeting_brief
from pavo.cli import main


class BriefTests(unittest.TestCase):
    def test_brief_scores_review_pressure_and_writes_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "call.mp3").write_bytes(b"audio")
            (root / "call.transcript.json").write_text('{"segments":[{"text":"We need to update routing."}]}\n')
            (root / "transcript.md").write_text("We need to update routing.\n")
            work = root / "_work"
            work.mkdir()
            (work / "diarization-segments.json").write_text('[{"recording_id":"call","speaker":"S1"}]\n')
            (work / "speaker-attribution.json").write_text(
                json.dumps(
                    {
                        "segments": [
                            {
                                "recording_id": "call",
                                "start": 0.0,
                                "end": 1.0,
                                "speaker": "Unknown office speaker",
                                "confidence": "low",
                                "text": "We need to update routing.",
                            }
                        ]
                    }
                )
            )
            (work / "named-speaker-evidence.json").write_text(
                json.dumps(
                    {
                        "segments": [
                            {
                                "recording_id": "call",
                                "start": 0.0,
                                "end": 1.0,
                                "speaker": "Daniel",
                                "confidence": "medium",
                                "reason": "Daniel/operator-language cue",
                                "text": "We need to update routing.",
                            }
                        ]
                    }
                )
            )
            (root / "named-speaker-evidence.md").write_text("# evidence\n")

            brief = build_meeting_brief(root)

            self.assertEqual(brief["state"], "ready_for_task_routing")
            self.assertEqual(brief["readiness_score"]["grade"], "ship_ready")
            self.assertGreaterEqual(brief["readiness_score"]["score"], 80)
            self.assertEqual(brief["review"]["item_count"], 0)
            self.assertEqual(brief["speaker_ensemble"]["routeable_named_segment_count"], 1)
            self.assertEqual(brief["speaker_ensemble"]["source_counts"], {"named_speaker_evidence": 1})
            self.assertEqual(brief["work_packets"]["packet_count"], 1)
            self.assertEqual(brief["next_actions"][0]["title"], "Turn candidate work packets into approved tasks")

            outputs = write_meeting_brief(brief, root)
            self.assertTrue(outputs.json_path.exists())
            self.assertIn("Pavo Meeting Brief", outputs.markdown_path.read_text())

    def test_cli_brief_command_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "call.mp3").write_bytes(b"audio")
            (root / "call.transcript.json").write_text('{"segments":[]}\n')

            self.assertEqual(main(["brief", str(root), "--json"]), 0)
            self.assertTrue((root / "pavo-meeting-brief.json").exists())
            self.assertTrue((root / "pavo-meeting-brief.md").exists())

    def test_brief_dedupes_generated_and_repeated_task_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "call.mp3").write_bytes(b"audio")
            (root / "call.transcript.json").write_text('{"segments":[]}\n')
            (root / "transcript-diarized.md").write_text("- `00:00:01`-`00:00:02` **S1 / Daniel**: Map that into NaviSoft\n")
            (root / "transcript-speaker-attributed.md").write_text("- `00:00:01`-`00:00:02` **Daniel (low)**: Map that into NaviSoft\n")
            (root / "pavo-meeting-brief.md").write_text("Review items: 200\n")

            brief = build_meeting_brief(root)

            self.assertEqual(brief["work_packets"]["packet_count"], 1)
            self.assertEqual(brief["work_packets"]["top_packets"][0]["title"], "Map that into NaviSoft")

    def test_brief_clusters_unattributed_review_pressure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "call.mp3").write_bytes(b"audio")
            (root / "call.transcript.json").write_text('{"segments":[]}\n')
            work = root / "_work"
            work.mkdir()
            (work / "diarization-segments.json").write_text('[{"recording_id":"call","speaker":"S1"}]\n')
            (work / "speaker-attribution.json").write_text(
                json.dumps(
                    {
                        "segments": [
                            {
                                "recording_id": "call",
                                "start": 0.0,
                                "end": 1.0,
                                "speaker": "Unknown office speaker",
                                "confidence": "low",
                                "text": "hello",
                            },
                            {
                                "recording_id": "call",
                                "start": 1.0,
                                "end": 2.5,
                                "speaker": "Unknown office speaker",
                                "confidence": "low",
                                "text": "there",
                            },
                        ]
                    }
                )
            )
            (root / "named-speaker-evidence.md").write_text("# evidence\n")

            brief = build_meeting_brief(root)

            self.assertEqual(brief["state"], "needs_human_review")
            self.assertEqual(brief["review"]["total_count"], 2)
            self.assertEqual(brief["review"]["clusters"][0]["speaker"], "Unknown office speaker")
            self.assertEqual(brief["review"]["clusters"][0]["segment_count"], 2)
            self.assertEqual(brief["review"]["clusters"][0]["duration_seconds"], 2.5)
