import json
import tempfile
import unittest
from pathlib import Path

from pavo.brief import build_meeting_brief
from pavo.review import (
    advance_cluster_review,
    build_anchor_review_rerun_command,
    build_anchor_review_serve_command,
    create_anchor_review_assistant,
    create_anchor_review_bundle,
    create_anchor_review_page,
    create_cluster_identity_audit,
    create_cluster_question_acoustic_report,
    create_cluster_question_impact_report,
    create_cluster_question_bundle,
    create_cluster_question_plan,
    create_cluster_review_forecast,
    compile_anchor_review_corrections,
    create_anchor_review_sheet,
    export_cluster_question_decisions,
    export_anchor_review_decisions,
    finalize_cluster_review,
    gate_anchor_review,
    import_anchor_review_sheet,
    materialize_anchor_review_decisions,
    materialize_cluster_question_decisions,
    parse_plain_english_review,
    prepare_cluster_review,
    save_anchor_review_sheet_payload,
    status_cluster_review,
    status_anchor_review,
    summarize_anchor_review_sheet,
    verify_anchor_review_page,
    _rank_next_review_plan_with_ensemble,
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

    def test_committed_plaud_c37_review_status_prints_next_action(self):
        docs = Path(__file__).resolve().parents[1] / "docs"

        result = status_anchor_review(
            docs / "plaud-c37-speaker1-anchor-review-sheet.json",
            gate_report_path=docs / "plaud-c37-anchor-review-gate-report.json",
            bundle_manifest_path=docs / "plaud-c37-anchor-review-bundle-manifest.json",
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.review_url, "http://127.0.0.1:9876/index.html")
        self.assertEqual(
            result.serve_command,
            "pavo review anchors serve docs/plaud-c37-anchor-review-bundle --port 9876",
        )
        self.assertEqual(result.pending_count, 20)
        self.assertIn("20 review rows are still pending", result.blockers)
        self.assertIn("review the bundled clips", result.next_action)

    def test_committed_conan_real_media_review_bundle_is_ready(self):
        docs = Path(__file__).resolve().parents[1] / "docs"
        sheet = docs / "conan-real-media-review-sheet.json"
        bundle_manifest = json.loads((docs / "conan-real-media-review-bundle-manifest.json").read_text())
        page_report = verify_anchor_review_page(sheet, docs / "conan-real-media-review.html")

        self.assertTrue(page_report.passed)
        self.assertEqual(page_report.candidate_count, 6)
        self.assertEqual(page_report.audio_count, 6)
        html = (docs / "conan-real-media-review.html").read_text()
        self.assertIn("Conan Listening Review", html)
        self.assertIn("Works", html)
        self.assertIn("Problem", html)
        self.assertIn("Unsure", html)
        self.assertIn("Save review", html)
        self.assertIn("/api/review-sheet", html)
        self.assertIn("Record note", html)
        self.assertIn("Parse note", html)
        self.assertIn("voice-waveform", html)
        self.assertIn("data-waveform", html)
        self.assertIn("/api/review-note", html)
        self.assertIn("/api/review-note-audio", html)
        self.assertIn("File mode: export review notes", html)
        self.assertIn("Opening handoff: mixed audio", html)
        self.assertIn("Technical details", html)
        self.assertNotIn("pavo review anchors import", html)
        self.assertNotIn("<dt>Target</dt>", html)
        self.assertTrue(bundle_manifest["passed"])
        self.assertEqual(bundle_manifest["copied_clip_count"], 6)
        self.assertEqual(bundle_manifest["missing_clip_count"], 0)
        self.assertEqual(
            bundle_manifest["serve_command"],
            "pavo review anchors serve docs/conan-real-media-review-bundle --port 9877",
        )

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

    def test_create_anchor_review_sheet_allows_row_level_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet = root / "cluster-clips.json"
            packet.write_text(
                json.dumps(
                    {
                        "target_speaker_label": "PAVO_REVIEW_CLUSTER",
                        "target_speaker_name": "Pavo review clusters",
                        "display_mode": "human_review",
                        "review_title": "Cluster Review",
                        "clips": [
                            {
                                "index": 1,
                                "target_speaker_label": "Daniel",
                                "target_speaker_name": "Daniel",
                                "start": 1.0,
                                "end": 2.0,
                                "text": "Daniel sample",
                                "clip_path": "/tmp/daniel.mp3",
                            },
                            {
                                "index": 2,
                                "target_speaker_label": "Alex",
                                "target_speaker_name": "Alex",
                                "start": 3.0,
                                "end": 4.0,
                                "text": "Alex sample",
                                "clip_path": "/tmp/alex.mp3",
                            },
                        ],
                    }
                )
            )

            result = create_anchor_review_sheet(packet)
            sheet = json.loads(result.review_sheet_path.read_text())

        self.assertEqual(sheet["display_mode"], "human_review")
        self.assertEqual(sheet["review_title"], "Cluster Review")
        self.assertEqual(sheet["rows"][0]["target_speaker_label"], "Daniel")
        self.assertEqual(sheet["rows"][1]["target_speaker_label"], "Alex")

    def test_cluster_human_review_does_not_export_fake_speaker_corrections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet = root / "pavo-review-cluster-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "requires_rerun_instruction": False,
                        "display_mode": "human_review",
                        "rows": [
                            {
                                "index": 1,
                                "status": "approved",
                                "approved": True,
                                "target_speaker_label": "Daniel",
                                "start": 1.0,
                                "end": 2.0,
                                "clip_path": "clips/daniel.mp3",
                                "suggested_speaker_correction": "",
                            }
                        ],
                    }
                )
            )

            corrections = compile_anchor_review_corrections(sheet)

        self.assertEqual(corrections.corrections, [])
        self.assertEqual(corrections.cli_args, [])

    def test_export_anchor_review_decisions_classifies_cluster_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet = root / "pavo-review-cluster-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "review_title": "Pavo Review Clusters",
                        "display_mode": "human_review",
                        "rows": [
                            {
                                "index": 1,
                                "status": "approved",
                                "approved": True,
                                "case": "Daniel / low_confidence_named_speaker",
                                "target_speaker_label": "Daniel",
                                "start": 1.0,
                                "end": 2.0,
                                "duration": 1.0,
                                "text": "Daniel sample",
                                "confidence": "low",
                                "method": "named_speaker_evidence",
                                "clip_path": "clips/daniel.mp3",
                                "recording_id": "rec-1",
                                "reviewer_note": "clear Daniel",
                                "review_parse": {"decision": "approved", "heard_speakers": ["Daniel"], "issues": []},
                            },
                            {
                                "index": 2,
                                "status": "rejected",
                                "approved": False,
                                "case": "Unknown office speaker / unattributed_speaker",
                                "target_speaker_label": "Unknown office speaker",
                                "start": 3.0,
                                "end": 4.0,
                                "duration": 1.0,
                                "text": "unknown sample",
                                "confidence": "low",
                                "method": "speaker_attribution",
                                "clip_path": "clips/unknown.mp3",
                                "reviewer_note": "mixed",
                                "review_parse": {"decision": "rejected", "issues": ["overlap"]},
                            },
                        ],
                    }
                )
            )

            result = export_anchor_review_decisions(sheet)
            report = json.loads(result.report_path.read_text())

        self.assertTrue(result.passed)
        self.assertTrue(result.human_reviewed)
        self.assertEqual(result.approved_count, 1)
        self.assertEqual(result.rejected_count, 1)
        self.assertEqual(result.pending_count, 0)
        self.assertEqual(result.routeable_count, 1)
        self.assertEqual(result.enrollment_candidate_count, 1)
        self.assertEqual(report["decisions"][0]["recording_id"], "rec-1")
        self.assertEqual(report["decisions"][0]["recommended_action"], "use_as_reviewed_speaker_hint_or_enrollment_candidate")
        self.assertEqual(report["decisions"][1]["recommended_action"], "do_not_use_for_speaker_truth")
        self.assertEqual(len(report["clusters"]), 2)

    def test_create_anchor_review_assistant_writes_recommendations_and_assisted_sheet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "_work"
            work.mkdir()
            (work / "speaker-attribution.json").write_text(
                json.dumps(
                    {
                        "segments": [
                            {
                                "recording_id": "rec-1",
                                "start": 1.0,
                                "end": 2.0,
                                "speaker": "Daniel",
                                "confidence": "medium",
                                "text": "Trusted context.",
                            },
                            {
                                "recording_id": "rec-1",
                                "start": 2.2,
                                "end": 3.0,
                                "speaker": "Daniel",
                                "confidence": "low",
                                "text": "Short weak segment.",
                            },
                        ]
                    }
                )
            )
            sheet = root / "review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "review_title": "Pavo Review Clusters",
                        "display_mode": "human_review",
                        "rows": [
                            {
                                "index": 1,
                                "status": "pending",
                                "approved": False,
                                "case": "Daniel / low_confidence_named_speaker",
                                "target_speaker_label": "Daniel",
                                "start": 2.2,
                                "end": 3.0,
                                "duration": 0.8,
                                "text": "Short weak segment.",
                                "confidence": "low",
                                "method": "speaker_attribution",
                                "clip_path": "clips/daniel.mp3",
                                "recording_id": "rec-1",
                            }
                        ],
                    }
                )
            )

            result = create_anchor_review_assistant(sheet, root)
            report = json.loads(result.json_path.read_text())
            assisted_sheet = json.loads(result.json_path.with_name("review-sheet-assisted.json").read_text())
            page = create_anchor_review_page(result.json_path.with_name("review-sheet-assisted.json"))
            verification = verify_anchor_review_page(result.json_path.with_name("review-sheet-assisted.json"), page.review_page_path)

            self.assertEqual(result.candidate_count, 1)
            self.assertEqual(result.recommendation_counts, {"likely_approve_existing_label": 1})
            self.assertEqual(report["recommendations"][0]["suggested_speaker"], "Daniel")
            self.assertIn("assistant_review", assisted_sheet["rows"][0])
            self.assertTrue(verification.passed)
            self.assertIn("Pavo assistant", page.review_page_path.read_text())

    def test_create_anchor_review_assistant_downgrades_cluster_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "_work"
            work.mkdir()
            (work / "voice-clusters.json").write_text(
                json.dumps(
                    {
                        "S1": {
                            "candidate_name": "Daniel",
                            "candidate_confidence": "high",
                            "candidate_reason": "operator-language cue",
                            "segment_count": 4,
                        }
                    }
                )
            )
            (work / "diarization-segments.json").write_text(
                json.dumps(
                    [
                        {
                            "recording_id": "rec-1",
                            "start": 2.2,
                            "end": 3.0,
                            "speaker": "S1",
                            "candidate_name": "Daniel",
                        }
                    ]
                )
            )
            (work / "speaker-attribution.json").write_text(
                json.dumps(
                    {
                        "segments": [
                            {
                                "recording_id": "rec-1",
                                "start": 1.0,
                                "end": 2.0,
                                "speaker": "Alex",
                                "confidence": "medium",
                                "text": "Trusted context.",
                            },
                            {
                                "recording_id": "rec-1",
                                "start": 2.2,
                                "end": 3.0,
                                "speaker": "Unknown office speaker",
                                "confidence": "low",
                                "text": "Unclear segment.",
                            },
                        ]
                    }
                )
            )
            sheet = root / "review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "review_title": "Pavo Review Clusters",
                        "display_mode": "human_review",
                        "rows": [
                            {
                                "index": 1,
                                "status": "pending",
                                "approved": False,
                                "case": "Unknown office speaker / unattributed_speaker",
                                "target_speaker_label": "Unknown office speaker",
                                "start": 2.2,
                                "end": 3.0,
                                "text": "Unclear segment.",
                                "clip_path": "clips/unknown.mp3",
                                "recording_id": "rec-1",
                            }
                        ],
                    }
                )
            )

            result = create_anchor_review_assistant(sheet, root)
            report = json.loads(result.json_path.read_text())

        row = report["recommendations"][0]
        self.assertEqual(result.recommendation_counts, {"listen_required_cluster_conflict": 1})
        self.assertEqual(row["suggested_speaker"], "Alex")
        self.assertEqual(row["cluster_context"]["candidate_name"], "Daniel")
        self.assertIn("Cluster candidate is Daniel", row["why"])

    def test_create_cluster_identity_audit_classifies_safe_and_conflict_clusters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "_work"
            work.mkdir()
            (work / "voice-clusters.json").write_text(
                json.dumps(
                    {
                        "S1": {"candidate_name": "Daniel", "candidate_confidence": "high", "segment_count": 4},
                        "S2": {"candidate_name": "Daniel", "candidate_confidence": "high", "segment_count": 4},
                    }
                )
            )
            diarization = []
            named = []
            for index in range(4):
                start = float(index)
                diarization.append({"recording_id": "rec-1", "start": start, "end": start + 0.5, "speaker": "S1"})
                named.append(
                    {
                        "recording_id": "rec-1",
                        "start": start,
                        "end": start + 0.5,
                        "speaker": "Daniel",
                        "confidence": "medium",
                        "text": f"Daniel {index}",
                    }
                )
            for index in range(4, 8):
                start = float(index)
                diarization.append({"recording_id": "rec-1", "start": start, "end": start + 0.5, "speaker": "S2"})
                named.append(
                    {
                        "recording_id": "rec-1",
                        "start": start,
                        "end": start + 0.5,
                        "speaker": "Alex",
                        "confidence": "medium",
                        "text": f"Alex {index}",
                    }
                )
            (work / "diarization-segments.json").write_text(json.dumps(diarization))
            (work / "named-speaker-evidence.json").write_text(json.dumps({"segments": named}))

            result = create_cluster_identity_audit(root)
            report = json.loads(result.json_path.read_text())

            by_id = {cluster["cluster_id"]: cluster for cluster in report["clusters"]}
            self.assertEqual(result.status_counts, {"candidate_conflict": 1, "safe_to_propagate": 1})
            self.assertEqual(by_id["S1"]["status"], "safe_to_propagate")
            self.assertEqual(by_id["S2"]["status"], "candidate_conflict")
            self.assertIn("Pavo Cluster Identity Audit", result.markdown_path.read_text())

    def test_create_cluster_question_plan_writes_targeted_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "_work"
            work.mkdir()
            (work / "voice-clusters.json").write_text(
                json.dumps({"S1": {"candidate_name": "Daniel", "candidate_confidence": "high", "segment_count": 2}})
            )
            (work / "diarization-segments.json").write_text(
                json.dumps(
                    [
                        {
                            "recording_id": "rec-1",
                            "start": 1.0,
                            "end": 5.0,
                            "speaker": "S1",
                            "candidate_name": "Daniel",
                            "text": "This is a useful representative sample.",
                        },
                        {
                            "recording_id": "rec-1",
                            "start": 6.0,
                            "end": 7.0,
                            "speaker": "S1",
                            "candidate_name": "Daniel",
                            "text": "Short.",
                        },
                    ]
                )
            )
            (work / "named-speaker-evidence.json").write_text(
                json.dumps(
                    {
                        "segments": [
                            {
                                "recording_id": "rec-1",
                                "start": 1.0,
                                "end": 5.0,
                                "speaker": "Daniel",
                                "confidence": "medium",
                                "text": "This is a useful representative sample.",
                            }
                        ]
                    }
                )
            )

            audit = create_cluster_identity_audit(root)
            result = create_cluster_question_plan(root, audit_path=audit.json_path)
            report = json.loads(result.json_path.read_text())

            self.assertEqual(result.question_count, 1)
            self.assertEqual(report["questions"][0]["cluster_id"], "S1")
            self.assertEqual(report["questions"][0]["samples"][0]["recording_id"], "rec-1")
            self.assertIn("Pavo Cluster Question Plan", result.markdown_path.read_text())

    def test_prepare_cluster_review_creates_verified_impact_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording = root / "rec-1"
            recording.mkdir()
            _write_test_wav(recording / "rec-1.wav")
            work = root / "_work"
            work.mkdir()
            (work / "diarization-segments.json").write_text(
                json.dumps(
                    [
                        {
                            "recording_id": "rec-1",
                            "start": 1.0,
                            "end": 5.0,
                            "speaker": "S-small",
                            "candidate_name": "Alex",
                            "text": "Small cluster sample.",
                        },
                        {
                            "recording_id": "rec-1",
                            "start": 6.0,
                            "end": 12.0,
                            "speaker": "S-big",
                            "candidate_name": "Daniel",
                            "text": "Large cluster sample with enough words to matter.",
                        },
                        {
                            "recording_id": "rec-1",
                            "start": 13.0,
                            "end": 19.0,
                            "speaker": "S-big",
                            "candidate_name": "Daniel",
                            "text": "Another large cluster sample with useful context.",
                        },
                    ]
                )
            )
            (work / "named-speaker-evidence.json").write_text(
                json.dumps(
                    {
                        "segments": [
                            {
                                "recording_id": "rec-1",
                                "start": 1.0,
                                "end": 5.0,
                                "speaker": "Alex",
                                "confidence": "medium",
                                "text": "Small cluster sample.",
                            },
                            {
                                "recording_id": "rec-1",
                                "start": 6.0,
                                "end": 12.0,
                                "speaker": "Daniel",
                                "confidence": "medium",
                                "text": "Large cluster sample with enough words to matter.",
                            },
                        ]
                    }
                )
            )

            result = prepare_cluster_review(root, min_strong_coverage=0.0, min_dominant_share=0.5)
            sheet = json.loads(result.review_sheet_path.read_text())
            impact_json_exists = result.impact_json_path.exists()
            impact_markdown_exists = result.impact_markdown_path.exists()
            acoustic_json_exists = result.acoustic_json_path.exists()
            acoustic_markdown_exists = result.acoustic_markdown_path.exists()
            forecast_json_exists = result.forecast_json_path.exists()
            forecast_markdown_exists = result.forecast_markdown_path.exists()
            page_html = result.review_page_path.read_text()

        self.assertTrue(result.page_verified)
        self.assertEqual(result.cluster_count, 2)
        self.assertEqual(result.question_count, 2)
        self.assertEqual(result.candidate_count, 3)
        self.assertEqual(result.missing_clip_count, 0)
        self.assertEqual(result.acoustic_analyzed_count, 3)
        self.assertGreaterEqual(result.acoustic_attention_cluster_count, 1)
        self.assertEqual(sheet["sort"]["mode"], "impact_desc")
        self.assertEqual(sheet["rows"][0]["cluster_question"]["cluster_id"], "S-big")
        self.assertTrue(impact_json_exists)
        self.assertTrue(impact_markdown_exists)
        self.assertTrue(acoustic_json_exists)
        self.assertTrue(acoustic_markdown_exists)
        self.assertTrue(forecast_json_exists)
        self.assertTrue(forecast_markdown_exists)
        self.assertIn("Acoustic evidence:", page_html)

    def test_cluster_review_status_reports_missing_prepare_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = status_cluster_review(root)

        self.assertEqual(result.state, "needs_prepare")
        self.assertEqual(result.candidate_count, 0)
        self.assertEqual(result.cluster_count, 0)
        self.assertEqual(result.ready_cluster_count, 0)
        self.assertEqual(result.conflicted_cluster_count, 0)
        self.assertEqual(result.unresolved_cluster_count, 0)
        self.assertEqual(result.next_review_count, 0)
        self.assertEqual(result.next_review_plan, [])
        self.assertEqual(result.review_effort["possible_reviews_saved"], 0)
        self.assertIn("prepare", result.next_command)
        self.assertIn("review sheet is missing", "; ".join(result.blockers))

    def test_cluster_review_status_reports_pending_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording = root / "rec-1"
            recording.mkdir()
            _write_test_wav(recording / "rec-1.wav")
            work = root / "_work"
            work.mkdir()
            (work / "diarization-segments.json").write_text(
                json.dumps(
                    [
                        {
                            "recording_id": "rec-1",
                            "start": 1.0,
                            "end": 5.0,
                            "speaker": "S1",
                            "candidate_name": "Daniel",
                            "text": "Review me.",
                        }
                    ]
                )
            )
            (work / "named-speaker-evidence.json").write_text(
                json.dumps(
                    {
                        "segments": [
                            {
                                "recording_id": "rec-1",
                                "start": 1.0,
                                "end": 5.0,
                                "speaker": "Daniel",
                                "confidence": "medium",
                                "text": "Review me.",
                            }
                        ]
                    }
                )
            )

            prepare_cluster_review(root, min_strong_coverage=0.0, min_dominant_share=0.5)
            result = status_cluster_review(root)
            markdown = result.as_markdown()

        self.assertEqual(result.state, "review_pending")
        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.pending_count, 1)
        self.assertEqual(result.cluster_count, 1)
        self.assertEqual(result.ready_cluster_count, 0)
        self.assertEqual(result.conflicted_cluster_count, 0)
        self.assertEqual(result.unresolved_cluster_count, 1)
        self.assertEqual(result.next_review_count, 1)
        self.assertEqual(len(result.next_review_plan), 1)
        self.assertIn("approve_effect", result.next_review_plan[0])
        self.assertIn("reject_effect", result.next_review_plan[0])
        self.assertIn("terminal_decision_rule", result.next_review_plan[0])
        self.assertIn("cannot-link", result.next_review_plan[0]["reject_effect"])
        self.assertIn("acoustic_verdict", result.next_review_plan[0])
        self.assertIn("acoustic_caution", result.next_review_plan[0])
        self.assertIn("review_priority_score", result.next_review_plan[0])
        self.assertIn("review_priority_reason", result.next_review_plan[0])
        self.assertEqual(result.review_effort["pending_reviews"], 1)
        self.assertEqual(result.review_effort["minimum_reviews"], 1)
        self.assertTrue(result.page_verified)
        self.assertIn("open", result.next_command)
        self.assertIn("### Cluster `S1` row `1`", markdown)
        self.assertIn("Approve effect:", markdown)
        self.assertIn("Reject effect:", markdown)
        self.assertIn("Terminal decision rule:", markdown)
        self.assertIn("Acoustic verdict:", markdown)
        self.assertIn("Acoustic caution:", markdown)
        self.assertIn("Review priority:", markdown)
        self.assertIn("Priority reason:", markdown)
        self.assertIn("Transcript excerpt: Review me.", markdown)
        self.assertIn("Clip:", markdown)

    def test_cluster_review_advance_stops_at_human_review_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "pavo-cluster-question-bundle"
            bundle.mkdir()
            sheet = bundle / "pavo-cluster-question-review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "index": 1,
                                "status": "pending",
                                "approved": False,
                                "target_speaker_label": "Daniel",
                                "cluster_question": {"cluster_id": "S1", "dominant_speaker": "Daniel"},
                            }
                        ]
                    }
                )
            )
            create_anchor_review_page(sheet, out_path=bundle / "index.html")

            result = advance_cluster_review(root)
            report = result.as_report()
            markdown = result.as_markdown()

        self.assertEqual(result.before_state, "review_pending")
        self.assertEqual(result.after_state, "review_pending")
        self.assertEqual(result.action, "await_human_review")
        self.assertFalse(result.advanced)
        self.assertIn("required human listening", report["safety_boundary"])
        self.assertIn("Pavo Cluster Review Advance", markdown)
        self.assertIn("await_human_review", markdown)

    def test_cli_cluster_review_advance_writes_reports(self):
        from pavo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "pavo-cluster-question-bundle"
            bundle.mkdir()
            sheet = bundle / "pavo-cluster-question-review-sheet.json"
            report = root / "advance.json"
            markdown_report = root / "advance.md"
            sheet.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "index": 1,
                                "status": "pending",
                                "approved": False,
                                "target_speaker_label": "Daniel",
                                "cluster_question": {"cluster_id": "S1", "dominant_speaker": "Daniel"},
                            }
                        ]
                    }
                )
            )
            create_anchor_review_page(sheet, out_path=bundle / "index.html")

            exit_code = main(
                [
                    "review",
                    "clusters",
                    "advance",
                    str(root),
                    "--report",
                    str(report),
                    "--markdown-report",
                    str(markdown_report),
                    "--json",
                ]
            )
            payload = json.loads(report.read_text())
            markdown = markdown_report.read_text()

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["action"], "await_human_review")
        self.assertFalse(payload["advanced"])
        self.assertEqual(payload["status"]["state"], "review_pending")
        self.assertIn("Pavo Cluster Review Advance", markdown)

    def test_cluster_review_status_reports_ready_to_finalize(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "pavo-cluster-question-bundle"
            bundle.mkdir()
            sheet = bundle / "pavo-cluster-question-review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "index": 1,
                                "status": "approved",
                                "approved": True,
                                "target_speaker_label": "Daniel",
                                "cluster_question": {"cluster_id": "S1", "dominant_speaker": "Daniel"},
                            }
                        ]
                    }
                )
            )
            create_anchor_review_page(sheet, out_path=bundle / "index.html")
            result = status_cluster_review(root)

        self.assertEqual(result.state, "ready_to_finalize")
        self.assertEqual(result.approved_count, 1)
        self.assertEqual(result.pending_count, 0)
        self.assertEqual(result.cluster_count, 1)
        self.assertEqual(result.ready_cluster_count, 1)
        self.assertEqual(result.conflicted_cluster_count, 0)
        self.assertEqual(result.unresolved_cluster_count, 0)
        self.assertEqual(result.next_review_count, 0)
        self.assertEqual(result.review_effort["minimum_reviews"], 0)
        self.assertTrue(result.page_verified)
        self.assertIn("finalize", result.next_command)
        self.assertIn("finalize", result.completion_commands)
        self.assertIn("decisions", result.completion_commands)

    def test_cluster_review_status_finds_bundle_local_materialized_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "pavo-cluster-question-bundle"
            artifacts = bundle / "pavo-cluster-question-artifacts"
            artifacts.mkdir(parents=True)
            sheet = bundle / "pavo-cluster-question-review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "index": 1,
                                "status": "approved",
                                "approved": True,
                                "target_speaker_label": "Daniel",
                                "cluster_question": {"cluster_id": "S1", "dominant_speaker": "Daniel"},
                            }
                        ]
                    }
                )
            )
            create_anchor_review_page(sheet, out_path=bundle / "index.html")
            (artifacts / "pavo-cluster-constraints.json").write_text(
                json.dumps({"passed": True, "constraint_count": 1, "constraints": [{"type": "must_link"}]})
            )
            (artifacts / "pavo-cluster-reviewed-hints.json").write_text(
                json.dumps({"passed": True, "hint_count": 1, "hints": [{"speaker": "Daniel"}]})
            )

            result = status_cluster_review(root)
            report = result.as_report()
            markdown = result.as_markdown()

        self.assertEqual(result.constraints_count, 1)
        self.assertEqual(result.hint_count, 1)
        self.assertEqual(result.materialized_artifact_dir, artifacts)
        self.assertEqual(report["materialized_artifact_dir"], str(artifacts))
        self.assertIn("completion_commands", report)
        self.assertIn("materialize_decisions", report["completion_commands"])
        self.assertIn("Completion Commands", markdown)

    def test_cluster_review_status_report_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = status_cluster_review(root)
            report = result.as_report()
            markdown = result.as_markdown()

        self.assertEqual(report["state"], "needs_prepare")
        self.assertIsNone(report["review_sheet"])
        self.assertEqual(report["candidate_count"], 0)
        self.assertEqual(report["cluster_count"], 0)
        self.assertEqual(report["ready_cluster_count"], 0)
        self.assertEqual(report["conflicted_cluster_count"], 0)
        self.assertEqual(report["unresolved_cluster_count"], 0)
        self.assertEqual(report["next_review_count"], 0)
        self.assertEqual(report["next_review_plan"], [])
        self.assertEqual(report["review_effort"]["possible_reviews_saved"], 0)
        self.assertIn("next_command", report)
        self.assertIn("completion_commands", report)
        self.assertIn("prepare", report["completion_commands"])
        self.assertIn("blockers", report)
        self.assertIn("Pavo Cluster Review Status", markdown)
        self.assertIn("needs_prepare", markdown)
        self.assertIn("Completion Commands", markdown)
        self.assertIn("Reviewer Guide", markdown)
        self.assertIn("Cluster consensus", markdown)
        self.assertIn("Listen to the audio", markdown)
        self.assertIn("Approve only", markdown)
        self.assertIn("terminal consensus", markdown)

    def test_cli_cluster_review_status_writes_report_json(self):
        from pavo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "status.json"
            markdown_report = root / "status.md"

            exit_code = main(
                [
                    "review",
                    "clusters",
                    "status",
                    str(root),
                    "--report",
                    str(report),
                    "--markdown-report",
                    str(markdown_report),
                    "--json",
                ]
            )
            payload = json.loads(report.read_text())
            markdown = markdown_report.read_text()

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["state"], "needs_prepare")
        self.assertEqual(payload["candidate_count"], 0)
        self.assertEqual(payload["cluster_count"], 0)
        self.assertIn("pavo review clusters prepare", payload["next_command"])
        self.assertIn("Pavo Cluster Review Status", markdown)
        self.assertIn("Reviewer Guide", markdown)
        self.assertIn("transcript text alone is not speaker truth", markdown)
        self.assertIn("pavo review clusters prepare", markdown)

    def test_create_cluster_question_bundle_writes_review_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording = root / "rec-1"
            recording.mkdir()
            audio = recording / "rec-1.wav"
            audio.write_bytes(b"RIFF")
            plan = root / "pavo-cluster-question-plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "batch_root": str(root),
                        "questions": [
                            {
                                "cluster_id": "S1",
                                "status": "low_coverage_targeted_review",
                                "question": "Can cluster S1 be confirmed as Daniel?",
                                "candidate_name": "Daniel",
                                "dominant_speaker": "Daniel",
                                "expected_impact": "2 segments / 8 seconds",
                                "suggested_decision": "Approve representative Daniel samples if the voice matches.",
                                "stop_condition": "Two representative samples confirm the same speaker.",
                                "samples": [
                                    {
                                        "recording_id": "rec-1",
                                        "start": 0.0,
                                        "end": 1.0,
                                        "text": "sample",
                                        "named_confidence": "medium",
                                    }
                                ],
                            }
                        ],
                    }
                )
            )

            result = create_cluster_question_bundle(plan)
            sheet = json.loads(result.review_sheet_path.read_text())
            verification = verify_anchor_review_page(result.review_sheet_path, result.review_page_path)
            html = result.review_page_path.read_text()

            self.assertEqual(result.candidate_count, 1)
            self.assertEqual(result.acoustic_analyzed_count, 0)
            self.assertTrue(result.review_page_path.exists())
            self.assertTrue(result.acoustic_json_path.exists())
            self.assertTrue(result.forecast_json_path.exists())
            self.assertEqual(sheet["rows"][0]["case"], "S1 / low_coverage_targeted_review")
            self.assertIn("Acoustic evidence:", html)
            self.assertTrue(verification.passed)

    def test_cluster_question_bundle_orders_review_rows_by_impact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording = root / "rec-1"
            recording.mkdir()
            audio = recording / "rec-1.wav"
            audio.write_bytes(b"RIFF")
            plan = root / "pavo-cluster-question-plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "batch_root": str(root),
                        "questions": [
                            {
                                "cluster_id": "S-small",
                                "status": "low_coverage_targeted_review",
                                "question": "Can cluster S-small be confirmed as Alex?",
                                "candidate_name": "Alex",
                                "dominant_speaker": "Alex",
                                "expected_impact": "3 segments / 8 seconds",
                                "suggested_decision": "Approve representative Alex samples if the voice matches.",
                                "stop_condition": "Two representative samples confirm the same speaker.",
                                "samples": [
                                    {
                                        "recording_id": "rec-1",
                                        "start": 0.0,
                                        "end": 1.0,
                                        "text": "small sample",
                                        "named_confidence": "medium",
                                    }
                                ],
                            },
                            {
                                "cluster_id": "S-big",
                                "status": "low_coverage_targeted_review",
                                "question": "Can cluster S-big be confirmed as Daniel?",
                                "candidate_name": "Daniel",
                                "dominant_speaker": "Daniel",
                                "expected_impact": "50 segments / 100 seconds",
                                "suggested_decision": "Approve representative Daniel samples if the voice matches.",
                                "stop_condition": "Two representative samples confirm the same speaker.",
                                "samples": [
                                    {
                                        "recording_id": "rec-1",
                                        "start": 2.0,
                                        "end": 3.0,
                                        "text": "big sample",
                                        "named_confidence": "medium",
                                    }
                                ],
                            },
                        ],
                    }
                )
            )

            result = create_cluster_question_bundle(plan)
            sheet = json.loads(result.review_sheet_path.read_text())
            html = result.review_page_path.read_text()

        self.assertEqual(sheet["sort"]["mode"], "impact_desc")
        self.assertEqual(sheet["rows"][0]["cluster_question"]["cluster_id"], "S-big")
        self.assertEqual(sheet["rows"][0]["impact_rank"], 1)
        self.assertGreater(sheet["rows"][0]["impact_score"], sheet["rows"][1]["impact_score"])
        self.assertIn("Impact rank", html)
        self.assertIn("Estimated unlock", html)

    def test_cluster_question_decisions_fail_closed_when_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet = root / "cluster-review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "index": 1,
                                "status": "pending",
                                "approved": False,
                                "target_speaker_label": "Daniel",
                                "recording_id": "rec-1",
                                "start": 1.0,
                                "end": 2.0,
                                "cluster_question": {"cluster_id": "S1", "dominant_speaker": "Daniel"},
                            }
                        ]
                    }
                )
            )

            result = export_cluster_question_decisions(sheet)
            materialized = materialize_cluster_question_decisions(result.report_path)

        self.assertFalse(result.passed)
        self.assertEqual(result.pending_count, 1)
        self.assertEqual(result.unresolved_cluster_count, 1)
        self.assertFalse(materialized.passed)
        self.assertIn("cluster questions still need review before terminal consensus", "; ".join(materialized.blockers))

    def test_finalize_cluster_review_fails_closed_when_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet = root / "cluster-review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "index": 1,
                                "status": "pending",
                                "approved": False,
                                "target_speaker_label": "Daniel",
                                "recording_id": "rec-1",
                                "start": 1.0,
                                "end": 2.0,
                                "cluster_question": {"cluster_id": "S1", "dominant_speaker": "Daniel"},
                            }
                        ]
                    }
                )
            )

            result = finalize_cluster_review(sheet, root)

        self.assertFalse(result.passed)
        self.assertEqual(result.pending_count, 1)
        self.assertIsNone(result.brief_json_path)
        self.assertIn("cluster questions still need review before terminal consensus", "; ".join(result.blockers))

    def test_cluster_question_decisions_allow_rejection_early_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet = root / "cluster-review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "index": 1,
                                "status": "rejected",
                                "approved": False,
                                "target_speaker_label": "Daniel",
                                "recording_id": "rec-1",
                                "start": 1.0,
                                "end": 2.0,
                                "clip_path": "clips/one.mp3",
                                "cluster_question": {"cluster_id": "S1", "dominant_speaker": "Daniel"},
                            },
                            {
                                "index": 2,
                                "status": "pending",
                                "approved": False,
                                "target_speaker_label": "Daniel",
                                "recording_id": "rec-2",
                                "start": 3.0,
                                "end": 4.0,
                                "clip_path": "clips/two.mp3",
                                "cluster_question": {"cluster_id": "S1", "dominant_speaker": "Daniel"},
                            },
                        ]
                    }
                )
            )

            result = export_cluster_question_decisions(sheet)
            report = json.loads(result.report_path.read_text())
            materialized = materialize_cluster_question_decisions(result.report_path)
            constraints = json.loads(materialized.constraints_path.read_text())

        self.assertTrue(result.passed)
        self.assertEqual(result.pending_count, 1)
        self.assertEqual(result.ready_cluster_count, 1)
        self.assertEqual(result.unresolved_cluster_count, 0)
        self.assertEqual(report["clusters"][0]["consensus_state"], "ready_for_cannot_link")
        self.assertTrue(materialized.passed)
        self.assertEqual(constraints["constraints"][0]["type"], "cannot_link")

    def test_cluster_question_decisions_emit_minimal_next_review_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet = root / "cluster-review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "index": 1,
                                "impact_rank": 2,
                                "impact_score": 10.0,
                                "status": "pending",
                                "approved": False,
                                "target_speaker_label": "Daniel",
                                "recording_id": "rec-1",
                                "start": 1.0,
                                "end": 2.0,
                                "text": "weaker sample",
                                "clip_path": "clips/one.mp3",
                                "cluster_question": {
                                    "cluster_id": "S1",
                                    "dominant_speaker": "Daniel",
                                    "question": "Can S1 be Daniel?",
                                    "expected_impact": "10 segments / 20 seconds",
                                },
                            },
                            {
                                "index": 2,
                                "impact_rank": 1,
                                "impact_score": 99.0,
                                "status": "pending",
                                "approved": False,
                                "target_speaker_label": "Daniel",
                                "recording_id": "rec-2",
                                "start": 3.0,
                                "end": 4.0,
                                "text": "best sample",
                                "clip_path": "clips/two.mp3",
                                "cluster_question": {
                                    "cluster_id": "S1",
                                    "dominant_speaker": "Daniel",
                                    "question": "Can S1 be Daniel?",
                                    "expected_impact": "10 segments / 20 seconds",
                                },
                            },
                            {
                                "index": 3,
                                "impact_rank": 3,
                                "impact_score": 80.0,
                                "status": "pending",
                                "approved": False,
                                "target_speaker_label": "Alex",
                                "recording_id": "rec-3",
                                "start": 5.0,
                                "end": 6.0,
                                "text": "other cluster",
                                "clip_path": "clips/three.mp3",
                                "cluster_question": {
                                    "cluster_id": "S2",
                                    "dominant_speaker": "Alex",
                                    "question": "Can S2 be Alex?",
                                    "expected_impact": "8 segments / 9 seconds",
                                },
                            },
                        ]
                    }
                )
            )

            result = export_cluster_question_decisions(sheet)
            report = json.loads(result.report_path.read_text())

        self.assertFalse(result.passed)
        self.assertEqual(result.next_review_count, 2)
        self.assertEqual(report["next_review_count"], 2)
        self.assertEqual(result.review_effort["pending_reviews"], 3)
        self.assertEqual(result.review_effort["minimum_reviews"], 2)
        self.assertEqual(result.review_effort["possible_reviews_saved"], 1)
        self.assertEqual(report["review_effort"]["reduction_percent"], 33.3)
        self.assertEqual(report["next_review_plan"][0]["cluster_id"], "S1")
        self.assertEqual(report["next_review_plan"][0]["row_index"], 2)
        self.assertEqual(report["next_review_plan"][0]["text"], "best sample")
        self.assertIn("early-stop", report["next_review_plan"][0]["closure_rule"])

    def test_cluster_status_reranks_next_reviews_by_ensemble_priority(self):
        plan = [
            {
                "cluster_id": "S1",
                "row_index": 1,
                "impact_rank": 1,
                "impact_score": 100.0,
                "question": "Can cluster S1 be confirmed as Daniel?",
                "acoustic_verdict": "consistent_acoustic_shape",
                "acoustic_min_pair_similarity": 0.95,
            },
            {
                "cluster_id": "S2",
                "row_index": 2,
                "impact_rank": 2,
                "impact_score": 90.0,
                "question": "Does cluster S2 belong to Daniel or Alex?",
                "acoustic_verdict": "listen_carefully_acoustic_drift",
                "acoustic_min_pair_similarity": 0.7,
            },
        ]

        ranked = _rank_next_review_plan_with_ensemble(plan)

        self.assertEqual(ranked[0]["cluster_id"], "S2")
        self.assertEqual(ranked[0]["review_priority_tier"], "urgent_listen")
        self.assertGreater(ranked[0]["review_priority_score"], ranked[1]["review_priority_score"])
        self.assertIn("acoustic drift", ranked[0]["review_priority_reason"])
        self.assertIn("ambiguous speaker question", ranked[0]["review_priority_reason"])

    def test_cluster_question_impact_report_ranks_pending_clusters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet = root / "cluster-review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "index": 1,
                                "status": "pending",
                                "approved": False,
                                "target_speaker_label": "Daniel",
                                "recording_id": "rec-1",
                                "start": 1.0,
                                "end": 2.0,
                                "text": "larger cluster sample",
                                "review_subtitle": "50 segments / 100 seconds",
                                "cluster_question": {
                                    "cluster_id": "S1",
                                    "dominant_speaker": "Daniel",
                                    "expected_impact": "50 segments / 100 seconds",
                                    "question": "Can S1 be Daniel?",
                                },
                            },
                            {
                                "index": 2,
                                "status": "pending",
                                "approved": False,
                                "target_speaker_label": "Alex",
                                "recording_id": "rec-2",
                                "start": 3.0,
                                "end": 4.0,
                                "text": "smaller cluster sample",
                                "review_subtitle": "3 segments / 8 seconds",
                                "cluster_question": {
                                    "cluster_id": "S2",
                                    "dominant_speaker": "Alex",
                                    "expected_impact": "3 segments / 8 seconds",
                                    "question": "Can S2 be Alex?",
                                },
                            },
                        ]
                    }
                )
            )

            result = create_cluster_question_impact_report(sheet)
            report = json.loads(result.json_path.read_text())
            markdown = result.markdown_path.read_text()

        self.assertEqual(result.top_cluster_id, "S1")
        self.assertEqual(result.estimated_unlockable_segments, 53)
        self.assertEqual(result.estimated_unlockable_seconds, 108.0)
        self.assertEqual(report["clusters"][0]["cluster_id"], "S1")
        self.assertIn("prioritization estimate only", report["safety_boundary"])
        self.assertIn("Pavo Cluster Question Impact Preview", markdown)

    def test_cluster_question_acoustic_report_scores_local_clip_consistency(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clip_a = root / "clip-a.wav"
            clip_b = root / "clip-b.wav"
            _write_test_wav(clip_a)
            _write_test_wav(clip_b)
            sheet = root / "cluster-review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "index": 1,
                                "status": "pending",
                                "approved": False,
                                "target_speaker_label": "Daniel",
                                "clip_path": str(clip_a),
                                "cluster_question": {"cluster_id": "S1", "dominant_speaker": "Daniel"},
                            },
                            {
                                "index": 2,
                                "status": "pending",
                                "approved": False,
                                "target_speaker_label": "Daniel",
                                "clip_path": str(clip_b),
                                "cluster_question": {"cluster_id": "S1", "dominant_speaker": "Daniel"},
                            },
                        ]
                    }
                )
            )

            result = create_cluster_question_acoustic_report(sheet)
            report = json.loads(result.json_path.read_text())
            markdown = result.markdown_path.read_text()
            status = status_cluster_review(root, review_sheet_path=sheet)

        self.assertEqual(result.candidate_count, 2)
        self.assertEqual(result.analyzed_count, 2)
        self.assertEqual(result.missing_count, 0)
        self.assertEqual(report["clusters"][0]["verdict"], "consistent_acoustic_shape")
        self.assertIn("not speaker identity", report["safety_boundary"])
        self.assertIn("Pavo Cluster Acoustic Evidence", markdown)
        self.assertEqual(status.acoustic_analyzed_count, 2)
        self.assertEqual(status.acoustic_attention_cluster_count, 0)

    def test_cluster_review_forecast_combines_impact_and_acoustic_risk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clip_a = root / "clip-a.wav"
            clip_b = root / "clip-b.wav"
            _write_test_wav(clip_a)
            _write_test_wav(clip_b)
            sheet = root / "cluster-review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "index": 1,
                                "status": "pending",
                                "approved": False,
                                "clip_path": str(clip_a),
                                "cluster_question": {
                                    "cluster_id": "S1",
                                    "dominant_speaker": "Daniel",
                                    "expected_impact": "40 segments / 80 seconds",
                                },
                            },
                            {
                                "index": 2,
                                "status": "pending",
                                "approved": False,
                                "clip_path": str(clip_b),
                                "cluster_question": {
                                    "cluster_id": "S1",
                                    "dominant_speaker": "Daniel",
                                    "expected_impact": "40 segments / 80 seconds",
                                },
                            },
                        ]
                    }
                )
            )
            create_cluster_question_impact_report(sheet)
            create_cluster_question_acoustic_report(sheet)

            result = create_cluster_review_forecast(sheet)
            report = json.loads(result.json_path.read_text())
            markdown = result.markdown_path.read_text()
            status = status_cluster_review(root, review_sheet_path=sheet)

        self.assertEqual(result.estimated_unlockable_segments, 40)
        self.assertEqual(result.risk_adjusted_segments, 30)
        self.assertEqual(report["clusters"][0]["success_probability"], 0.75)
        self.assertIn("Forecasts are planning estimates only", report["safety_boundary"])
        self.assertIn("Pavo Cluster Review Forecast", markdown)
        self.assertEqual(status.forecast_risk_adjusted_segments, 30)

    def test_cli_cluster_review_forecast_writes_reports(self):
        from pavo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet = root / "cluster-review-sheet.json"
            out = root / "forecast.json"
            sheet.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "index": 1,
                                "status": "pending",
                                "approved": False,
                                "cluster_question": {
                                    "cluster_id": "S1",
                                    "dominant_speaker": "Daniel",
                                    "expected_impact": "10 segments / 5 seconds",
                                },
                            }
                        ]
                    }
                )
            )

            exit_code = main(["review", "clusters", "forecast", str(sheet), "--out", str(out)])
            payload = json.loads(out.read_text())
            markdown = out.with_suffix(".md").read_text()

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["estimated_unlockable_segments"], 10)
        self.assertIn("Risk-adjusted segments", markdown)

    def test_anchor_review_page_embeds_cluster_acoustic_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clip_a = root / "clip-a.wav"
            clip_b = root / "clip-b.wav"
            _write_test_wav(clip_a)
            _write_test_wav(clip_b)
            sheet = root / "cluster-review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "display_mode": "human_review",
                        "rows": [
                            {
                                "index": 1,
                                "status": "pending",
                                "approved": False,
                                "clip_path": str(clip_a),
                                "cluster_question": {"cluster_id": "S1", "dominant_speaker": "Daniel"},
                            },
                            {
                                "index": 2,
                                "status": "pending",
                                "approved": False,
                                "clip_path": str(clip_b),
                                "cluster_question": {"cluster_id": "S1", "dominant_speaker": "Daniel"},
                            },
                        ],
                    }
                )
            )
            create_cluster_question_acoustic_report(sheet)

            page = create_anchor_review_page(sheet).review_page_path
            html = page.read_text()
            embedded = html.split('<script type="application/json" id="review-sheet-data">', 1)[1].split("</script>", 1)[0]
            payload = json.loads(embedded)

        self.assertIn("Acoustic evidence:", html)
        self.assertIn("consistent_acoustic_shape", html)
        self.assertIn("not speaker identity or auto-approval", html)
        self.assertEqual(payload["rows"][0]["acoustic_review"]["verdict"], "consistent_acoustic_shape")

    def test_cli_cluster_review_acoustics_writes_reports(self):
        from pavo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clip = root / "clip.wav"
            _write_test_wav(clip)
            sheet = root / "cluster-review-sheet.json"
            out = root / "acoustic.json"
            sheet.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "index": 1,
                                "status": "pending",
                                "approved": False,
                                "clip_path": str(clip),
                                "cluster_question": {"cluster_id": "S1", "dominant_speaker": "Daniel"},
                            }
                        ]
                    }
                )
            )

            exit_code = main(["review", "clusters", "acoustics", str(sheet), "--out", str(out)])
            payload = json.loads(out.read_text())
            markdown = out.with_suffix(".md").read_text()

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["analyzed_count"], 1)
        self.assertEqual(payload["clusters"][0]["verdict"], "insufficient_audio")
        self.assertIn("acoustic consistency is evidence", markdown)

    def test_finalize_cluster_review_applies_constraints_and_scores_improvement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording = root / "rec-1"
            recording.mkdir()
            _write_test_wav(recording / "rec-1.wav")
            (root / "rec-1.transcript.json").write_text('{"segments":[]}\n')
            work = root / "_work"
            work.mkdir()
            (work / "diarization-segments.json").write_text(
                json.dumps(
                    [
                        {
                            "recording_id": "rec-1",
                            "start": 1.0,
                            "end": 5.0,
                            "speaker": "S1",
                            "candidate_name": "Daniel",
                            "text": "This should become Daniel.",
                        }
                    ]
                )
            )
            (work / "speaker-attribution.json").write_text(
                json.dumps(
                    {
                        "segments": [
                            {
                                "recording_id": "rec-1",
                                "start": 1.0,
                                "end": 5.0,
                                "speaker": "Unknown office speaker",
                                "confidence": "low",
                                "text": "This should become Daniel.",
                            }
                        ]
                    }
                )
            )
            baseline_path = root / "baseline-brief.json"
            baseline_path.write_text(json.dumps(build_meeting_brief(root)))
            sheet = root / "cluster-review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "index": 1,
                                "status": "approved",
                                "approved": True,
                                "target_speaker_label": "Daniel",
                                "recording_id": "rec-1",
                                "start": 1.0,
                                "end": 5.0,
                                "duration": 4.0,
                                "text": "This should become Daniel.",
                                "clip_path": "clips/one.mp3",
                                "reviewer_note": "clear Daniel",
                                "cluster_question": {
                                    "cluster_id": "S1",
                                    "dominant_speaker": "Daniel",
                                    "question": "Can S1 be Daniel?",
                                },
                            }
                        ]
                    }
                )
            )

            result = finalize_cluster_review(sheet, root, baseline_brief_path=baseline_path)
            constraints_exists = result.constraints_path.exists()
            overlay_exists = bool(result.overlay_path and result.overlay_path.exists())
            brief_exists = bool(result.brief_json_path and result.brief_json_path.exists())
            improvement_exists = bool(result.improvement_json_path and result.improvement_json_path.exists())

        self.assertTrue(result.passed)
        self.assertEqual(result.approved_count, 1)
        self.assertEqual(result.pending_count, 0)
        self.assertEqual(result.constraints_count, 1)
        self.assertEqual(result.hint_count, 1)
        self.assertEqual(result.review_pressure_reduction, 1)
        self.assertEqual(result.routeable_named_span_gain, 1)
        self.assertTrue(constraints_exists)
        self.assertTrue(overlay_exists)
        self.assertTrue(brief_exists)
        self.assertTrue(improvement_exists)

    def test_materialize_cluster_question_decisions_writes_constraints_and_hints(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet = root / "cluster-review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "index": 1,
                                "status": "approved",
                                "approved": True,
                                "target_speaker_label": "Daniel",
                                "recording_id": "rec-1",
                                "start": 1.0,
                                "end": 2.0,
                                "duration": 1.0,
                                "text": "Daniel sample",
                                "clip_path": "clips/one.mp3",
                                "reviewer_note": "supports Daniel",
                                "cluster_question": {
                                    "cluster_id": "S1",
                                    "dominant_speaker": "Daniel",
                                    "question": "Can S1 be Daniel?",
                                },
                            },
                            {
                                "index": 2,
                                "status": "rejected",
                                "approved": False,
                                "target_speaker_label": "Alex",
                                "recording_id": "rec-2",
                                "start": 3.0,
                                "end": 4.0,
                                "clip_path": "clips/two.mp3",
                                "reviewer_note": "not Alex",
                                "cluster_question": {
                                    "cluster_id": "S2",
                                    "dominant_speaker": "Alex",
                                    "question": "Can S2 be Alex?",
                                },
                            },
                        ]
                    }
                )
            )

            result = export_cluster_question_decisions(sheet)
            report = json.loads(result.report_path.read_text())
            materialized = materialize_cluster_question_decisions(result.report_path)
            constraints = json.loads(materialized.constraints_path.read_text())
            hints = json.loads(materialized.reviewed_hints_path.read_text())

        self.assertTrue(result.passed)
        self.assertEqual(result.cluster_count, 2)
        self.assertEqual(result.ready_cluster_count, 2)
        self.assertEqual(result.conflicted_cluster_count, 0)
        self.assertEqual(result.unresolved_cluster_count, 0)
        self.assertEqual(report["clusters"][0]["consensus_state"], "ready_for_must_link")
        self.assertEqual(report["clusters"][1]["consensus_state"], "ready_for_cannot_link")
        self.assertTrue(materialized.passed)
        self.assertEqual(materialized.constraints_count, 2)
        self.assertEqual(materialized.hint_count, 1)
        self.assertEqual(constraints["constraints"][0]["type"], "must_link")
        self.assertEqual(constraints["constraints"][1]["type"], "cannot_link")
        self.assertEqual(hints["hints"][0]["speaker"], "Daniel")

    def test_cluster_question_decisions_block_conflicting_cluster_consensus(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet = root / "cluster-review-sheet.json"
            sheet.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "index": 1,
                                "status": "approved",
                                "approved": True,
                                "target_speaker_label": "Daniel",
                                "recording_id": "rec-1",
                                "start": 1.0,
                                "end": 2.0,
                                "clip_path": "clips/one.mp3",
                                "cluster_question": {
                                    "cluster_id": "S1",
                                    "dominant_speaker": "Daniel",
                                    "question": "Can S1 be Daniel?",
                                    "expected_impact": "10 segments / 20 seconds",
                                },
                            },
                            {
                                "index": 2,
                                "status": "rejected",
                                "approved": False,
                                "target_speaker_label": "Daniel",
                                "recording_id": "rec-2",
                                "start": 3.0,
                                "end": 4.0,
                                "clip_path": "clips/two.mp3",
                                "cluster_question": {
                                    "cluster_id": "S1",
                                    "dominant_speaker": "Daniel",
                                    "question": "Can S1 be Daniel?",
                                    "expected_impact": "10 segments / 20 seconds",
                                },
                            },
                        ]
                    }
                )
            )

            result = export_cluster_question_decisions(sheet)
            report = json.loads(result.report_path.read_text())
            materialized = materialize_cluster_question_decisions(result.report_path)

        self.assertFalse(result.passed)
        self.assertEqual(result.cluster_count, 1)
        self.assertEqual(result.ready_cluster_count, 0)
        self.assertEqual(result.conflicted_cluster_count, 1)
        self.assertEqual(result.unresolved_cluster_count, 0)
        self.assertIn("1 clusters have conflicting approved/rejected samples", result.blockers)
        self.assertEqual(report["clusters"][0]["consensus_state"], "conflicting_review")
        self.assertEqual(report["clusters"][0]["materialization_effect"], "do_not_materialize_broad_cluster_constraint")
        self.assertFalse(materialized.passed)
        self.assertIn("1 clusters have conflicting approved/rejected samples", materialized.blockers)

    def test_materialize_anchor_review_decisions_writes_hints_and_enrollment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            decision_report = root / "decisions.json"
            decision_report.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "human_reviewed": True,
                        "pending_count": 0,
                        "blockers": [],
                        "decisions": [
                            {
                                "index": 1,
                                "status": "approved",
                                "approved": True,
                                "speaker": "Daniel",
                                "recording_id": "rec-1",
                                "start": 1.0,
                                "end": 3.5,
                                "duration": 2.5,
                                "text": "Daniel sample",
                                "confidence": "low",
                                "clip_path": "clips/daniel.mp3",
                                "reviewer_note": "clear Daniel",
                                "routeable": True,
                                "enrollment_candidate": True,
                            },
                            {
                                "index": 2,
                                "status": "rejected",
                                "approved": False,
                                "speaker": "Unknown office speaker",
                                "routeable": False,
                                "enrollment_candidate": False,
                            },
                        ],
                    }
                )
            )

            result = materialize_anchor_review_decisions(decision_report)
            hints = json.loads(result.hint_path.read_text())
            enrollment = json.loads(result.enrollment_path.read_text())
            rerun = json.loads(result.rerun_plan_path.read_text())

        self.assertTrue(result.passed)
        self.assertEqual(result.routeable_count, 1)
        self.assertEqual(result.enrollment_speaker_count, 1)
        self.assertEqual(hints["hints"][0]["speaker"], "Daniel")
        self.assertEqual(hints["hints"][0]["recording_id"], "rec-1")
        self.assertEqual(enrollment["speakers"][0]["slug"], "daniel")
        self.assertEqual(enrollment["speakers"][0]["sample_count"], 1)
        self.assertEqual(enrollment["speakers"][0]["total_seconds"], 2.5)
        self.assertTrue(rerun["passed"])

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
        self.assertIn('id="save-review"', html)
        self.assertIn('id="export-json"', html)
        self.assertIn("/api/review-sheet", html)
        self.assertIn("Record note", html)
        self.assertIn("Parse note", html)
        self.assertIn("Keyboard shortcuts:", html)
        self.assertIn("handleReviewShortcut", html)
        self.assertIn("toggleCurrentAudio", html)
        self.assertIn("seekCurrentAudio", html)
        self.assertIn("restartCurrentAudio", html)
        self.assertIn("persistReviewDraft", html)
        self.assertIn("loadReviewDraft", html)
        self.assertIn("localStorage", html)
        self.assertIn('id="cluster-summary"', html)
        self.assertIn("renderClusterSummary", html)
        self.assertIn("clusterConsensusState", html)
        self.assertIn('id="next-review-plan"', html)
        self.assertIn("minimalNextReviewPlan", html)
        self.assertIn("focusNextRecommendedReview", html)
        self.assertIn("approveEffect", html)
        self.assertIn("rejectEffect", html)
        self.assertIn("terminalDecisionRule", html)
        self.assertIn("reviewPriorityScore", html)
        self.assertIn("reviewPriorityReason", html)
        self.assertIn("Priority:", html)
        self.assertIn('id="review-effort"', html)
        self.assertIn("renderReviewEffort", html)
        self.assertIn('id="completion-handoff"', html)
        self.assertIn("renderCompletionHandoff", html)
        self.assertIn("clusterFinalizeCommand", html)
        self.assertIn("pavo review clusters finalize", html)
        self.assertIn("<code>N</code> next recommended review", html)
        self.assertIn("<code>Space</code> play/pause", html)
        self.assertIn("<code>&larr;</code>/<code>&rarr;</code> seek 2s", html)
        self.assertIn('tabindex="0"', html)
        self.assertIn("data-waveform", html)
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
        self.assertTrue(result.shortcut_panel_present)
        self.assertTrue(result.keyboard_handler_present)
        self.assertTrue(result.audio_shortcuts_present)
        self.assertTrue(result.draft_autosave_present)
        self.assertTrue(result.cluster_summary_present)
        self.assertTrue(result.next_review_plan_present)
        self.assertTrue(result.review_effort_present)
        self.assertTrue(result.completion_handoff_present)
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

    def test_build_anchor_review_serve_command_points_at_bundle_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "bundle"
            bundle.mkdir()
            (bundle / "index.html").write_text("<html></html>")

            result = build_anchor_review_serve_command(bundle, host="127.0.0.1", port=9999, python="python3")

        self.assertEqual(result.url, "http://127.0.0.1:9999/index.html")
        self.assertEqual(
            result.command,
            ["pavo", "review", "anchors", "serve", str(bundle), "--host", "127.0.0.1", "--port", "9999"],
        )
        self.assertIn("pavo review anchors serve", result.shell_command)

    def test_build_anchor_review_serve_command_requires_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(FileNotFoundError, "Review bundle index not found"):
                build_anchor_review_serve_command(Path(tmp) / "missing")

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
        self.assertIn("shortcut panel", result.missing)
        self.assertIn("keyboard shortcuts", result.missing)
        self.assertIn("audio shortcuts", result.missing)
        self.assertIn("draft autosave", result.missing)
        self.assertIn("cluster summary", result.missing)
        self.assertIn("next review plan", result.missing)
        self.assertIn("review effort", result.missing)
        self.assertIn("completion handoff", result.missing)
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

    def test_save_anchor_review_sheet_payload_persists_validated_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "review-sheet.json"
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
                        "clip_path": "clips/candidate-1.wav",
                        "suggested_speaker_correction": "00:12-00:16=SPEAKER_01",
                        "reviewer_note": "",
                    }
                ],
            }
            reviewed = json.loads(json.dumps(sheet))
            reviewed["rows"][0]["status"] = "approved"
            reviewed["rows"][0]["approved"] = True
            reviewed["rows"][0]["reviewer_note"] = "clear voiceprint match"
            reviewed["rows"][0]["reviewer_note_transcript"] = "Conan is clear and it works"
            reviewed["rows"][0]["reviewer_note_audio_path"] = "review-notes/row-1.webm"
            reviewed["rows"][0]["review_parse"] = {"decision": "approved", "heard_speakers": ["Conan"]}
            original.write_text(json.dumps(sheet))

            result = save_anchor_review_sheet_payload(original, reviewed)
            saved = json.loads(original.read_text())

        self.assertTrue(result.human_reviewed)
        self.assertEqual(result.imported_sheet_path, original)
        self.assertEqual(saved["approved_count"], 1)
        self.assertEqual(saved["pending_count"], 0)
        self.assertEqual(saved["rows"][0]["reviewer_note"], "clear voiceprint match")
        self.assertEqual(saved["rows"][0]["reviewer_note_transcript"], "Conan is clear and it works")
        self.assertEqual(saved["rows"][0]["reviewer_note_audio_path"], "review-notes/row-1.webm")
        self.assertEqual(saved["rows"][0]["review_parse"]["heard_speakers"], ["Conan"])

    def test_parse_plain_english_review_extracts_decision_and_issues(self):
        result = parse_plain_english_review(
            "I hear Conan and Kaitlin talking over each other. Kaitlin is too quiet, so this is a problem.",
            row={"target_speaker_name": "Kaitlin Olson"},
        )

        self.assertEqual(result["decision"], "rejected")
        self.assertIn("Kaitlin Olson", result["heard_speakers"])
        self.assertTrue(result["overlap"])
        self.assertIn("overlap", result["issues"])
        self.assertIn("weak_voice", result["issues"])
        self.assertIn("retry", result["suggested_fix"])

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


def _write_test_wav(path: Path) -> None:
    import math
    import struct
    import wave

    sample_rate = 8000
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for index in range(sample_rate * 24):
            value = int(12000 * math.sin(2 * math.pi * 440 * index / sample_rate))
            wav.writeframes(struct.pack("<h", value))


if __name__ == "__main__":
    unittest.main()
