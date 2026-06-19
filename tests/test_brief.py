import json
import tempfile
import unittest
from pathlib import Path

from pavo.brief import (
    build_meeting_brief,
    build_review_cluster_plan,
    write_meeting_brief,
    write_review_cluster_clip_packet,
    write_review_cluster_plan,
)
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
            self.assertEqual(brief["review"]["clusters"][0]["samples"][0]["text"], "hello")

    def test_review_cluster_plan_keeps_human_approval_boundary(self):
        brief = {
            "generated_at": "2026-06-18T00:00:00+00:00",
            "root": "/tmp/batch",
            "state": "needs_human_review",
            "readiness_score": {"score": 90, "grade": "usable_with_review"},
            "review": {
                "clusters": [
                    {
                        "speaker": "Unknown office speaker",
                        "reason": "unattributed_speaker",
                        "segment_count": 3,
                        "duration_seconds": 12.5,
                        "recording_count": 2,
                        "sample_text": ["unknown sample"],
                    },
                    {
                        "speaker": "Daniel",
                        "reason": "low_confidence_named_speaker",
                        "segment_count": 2,
                        "duration_seconds": 4.0,
                        "recording_count": 1,
                        "sample_text": ["daniel sample"],
                    },
                ],
                "top_items": [
                    {
                        "speaker": "Unknown office speaker",
                        "reason": "unattributed_speaker",
                        "recording_id": "r1",
                        "start": 0.0,
                        "end": 3.0,
                        "confidence": "low",
                        "ensemble_source": "speaker_attribution",
                        "text": "Who owns this?",
                    },
                    {
                        "speaker": "Daniel",
                        "reason": "low_confidence_named_speaker",
                        "recording_id": "r2",
                        "start": 4.0,
                        "end": 6.0,
                        "confidence": "low",
                        "ensemble_source": "named_speaker_evidence",
                        "text": "Let's fix it.",
                    },
                ],
            },
        }

        plan = build_review_cluster_plan(brief)

        self.assertFalse(plan["approval_boundary"]["mass_approval_allowed"])
        self.assertTrue(plan["approval_boundary"]["human_required"])
        self.assertEqual(plan["summary"]["cluster_count"], 2)
        self.assertEqual(plan["clusters"][0]["approval_state"], "human_required")
        self.assertEqual(plan["clusters"][0]["review_mode"], "identify_or_enroll_speaker")
        self.assertIn("mass_approve_cluster", plan["clusters"][0]["forbidden_actions"])
        self.assertEqual(plan["clusters"][1]["review_mode"], "confirm_named_speaker_confidence")
        self.assertEqual(plan["clusters"][1]["samples"][0]["recording_id"], "r2")

    def test_review_cluster_plan_writes_outputs(self):
        brief = {
            "root": "/tmp/batch",
            "state": "needs_human_review",
            "readiness_score": {"score": 80, "grade": "usable_with_review"},
            "review": {
                "clusters": [
                    {
                        "speaker": "Unknown office speaker",
                        "reason": "unattributed_speaker",
                        "segment_count": 1,
                        "duration_seconds": 1.0,
                        "recording_count": 1,
                        "sample_text": ["hello"],
                    }
                ],
                "top_items": [],
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_review_cluster_plan(build_review_cluster_plan(brief), Path(tmp))

            self.assertTrue(outputs.json_path.exists())
            self.assertTrue(outputs.markdown_path.exists())
            self.assertIn("Pavo Review Cluster Plan", outputs.markdown_path.read_text())

    def test_cli_brief_command_writes_review_plan_when_requested(self):
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
                                "text": "Need a decision.",
                            }
                        ]
                    }
                )
            )
            (root / "named-speaker-evidence.md").write_text("# evidence\n")

            self.assertEqual(main(["brief", str(root), "--review-plan"]), 0)
            self.assertTrue((root / "pavo-review-cluster-plan.json").exists())
            self.assertTrue((root / "pavo-review-cluster-plan.md").exists())

    def test_review_cluster_clip_packet_extracts_sample_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording = root / "rec-1"
            recording.mkdir()
            audio = recording / "rec-1.wav"
            _write_test_wav(audio)
            plan = {
                "root": str(root),
                "clusters": [
                    {
                        "cluster_key": "Daniel / low_confidence_named_speaker",
                        "speaker": "Daniel",
                        "review_mode": "confirm_named_speaker_confidence",
                        "recommended_next_action": "Confirm Daniel sample.",
                        "stop_condition": "Human reviewed.",
                        "samples": [
                            {
                                "recording_id": "rec-1",
                                "start": 0.1,
                                "end": 0.8,
                                "confidence": "low",
                                "ensemble_source": "named_speaker_evidence",
                                "text": "sample text",
                            }
                        ],
                    }
                ],
            }

            result = write_review_cluster_clip_packet(plan, root)
            packet = json.loads(result.packet_path.read_text())

            self.assertEqual(result.extracted_clip_count, 1)
            self.assertEqual(result.missing_audio_count, 0)
            self.assertEqual(packet["candidate_count"], 1)
            self.assertEqual(packet["clips"][0]["target_speaker_label"], "Daniel")
            self.assertEqual(packet["clips"][0]["recording_id"], "rec-1")
            self.assertTrue(Path(packet["clips"][0]["clip_path"]).exists())


def _write_test_wav(path: Path) -> None:
    import math
    import struct
    import wave

    sample_rate = 8000
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for index in range(sample_rate):
            value = int(12000 * math.sin(2 * math.pi * 440 * index / sample_rate))
            wav.writeframes(struct.pack("<h", value))
