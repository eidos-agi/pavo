from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .audio import run_audio_doctor
from .batch import doctor_batch, verify_batch_manifest
from .brief import (
    build_brief_improvement_report,
    build_meeting_brief,
    build_review_cluster_plan,
    write_brief_improvement_report,
    write_meeting_brief,
    write_reviewed_hints_named_evidence,
    write_review_cluster_clip_packet,
    write_review_cluster_plan,
)
from .config import DEFAULT_HOME, home_from_arg, init_home
from .download import save_audio
from .meetings import diarize as run_meeting_diarize
from .meetings import meetings_fetch, meetings_latest, meetings_process, meetings_today
from .overlap import SeparateOverlapsRequest, separate_overlaps
from .plaud import PlaudCli, PlaudCliError
from .review import (
    advance_cluster_review,
    build_anchor_review_rerun_command,
    build_anchor_review_serve_command,
    create_anchor_review_assistant,
    create_anchor_review_bundle,
    create_anchor_review_page,
    create_anchor_review_sheet,
    create_cluster_identity_audit,
    create_cluster_question_acoustic_report,
    create_cluster_question_impact_report,
    create_cluster_question_bundle,
    create_cluster_question_plan,
    create_cluster_review_forecast,
    compile_anchor_review_corrections,
    doctor_cluster_review,
    export_cluster_question_decisions,
    export_cluster_review_decision_brief,
    export_cluster_review_slate,
    export_anchor_review_decisions,
    finish_cluster_review_from_slate,
    finalize_cluster_review,
    gate_anchor_review,
    gate_cluster_review,
    import_anchor_review_sheet,
    import_cluster_review_slate,
    materialize_anchor_review_decisions,
    materialize_cluster_question_decisions,
    prepare_cluster_review,
    serve_anchor_review_bundle,
    status_cluster_review,
    status_anchor_review,
    summarize_anchor_review_sheet,
    validate_cluster_review_slate,
    verify_anchor_review_page,
)
from .render import RenderVideoRequest, render_video
from .transcribe import (
    DecomposeAudioRequest,
    ProcessAudioRequest,
    TranscribeRequest,
    decompose_audio,
    process_audio,
    transcribe_recording,
)


DEFAULT_SHIM_SCAN_ROOTS = [
    Path("/Volumes/GREENMARK/Clouds/repos-greenmark-waste-solutions/greenmark-cockpit/tools"),
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pavo")
    parser.add_argument("--home", help="Override Pavo home directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create local Pavo config and state")
    subparsers.add_parser("doctor", help="Check local Pavo and Plaud readiness")
    batch = subparsers.add_parser("batch", help="Batch-level source and artifact QA")
    batch_sub = batch.add_subparsers(dest="batch_command", required=True)
    batch_doctor = batch_sub.add_parser("doctor", help="Check one processed meeting batch for source and artifact coverage")
    batch_doctor.add_argument("batch_root", type=Path)
    batch_doctor.add_argument("--json", action="store_true", help="Print full machine-readable batch doctor JSON")
    batch_doctor.add_argument("--report", type=Path, help="Write machine-readable batch doctor JSON")
    batch_doctor.add_argument("--markdown-report", type=Path, help="Write human-readable batch doctor Markdown")
    batch_doctor.add_argument("--no-refresh-cluster-gate", action="store_true", help="Read the existing cluster gate report instead of refreshing it")
    batch_verify = batch_sub.add_parser("verify-manifest", help="Verify source artifact hashes from a batch doctor JSON report")
    batch_verify.add_argument("report", type=Path, help="Path to pavo-batch-doctor.json")
    batch_verify.add_argument("--json", action="store_true", help="Print full machine-readable verification JSON")
    batch_verify.add_argument("--markdown-report", type=Path, help="Write human-readable verification Markdown")

    brief = subparsers.add_parser("brief", help="Create a composed readiness and action brief for a meeting batch")
    brief.add_argument("root", type=Path)
    brief.add_argument("--out-dir", type=Path, help="Output directory; defaults to the batch root")
    brief.add_argument("--review-limit", type=int, default=200)
    brief.add_argument("--packet-limit", type=int, default=25)
    brief.add_argument("--review-plan", action="store_true", help="Also write a safe cluster-based human review plan")
    brief.add_argument("--review-plan-sample-limit", type=int, default=5, help="Sample rows per review cluster")
    brief.add_argument("--review-plan-clips", action="store_true", help="Extract sampled review clips and render a review page")
    brief.add_argument("--review-plan-clip-limit", type=int, default=25, help="Maximum review-plan clips to extract")
    brief.add_argument("--json", action="store_true", help="Print the full brief payload as JSON")

    brief_improvement = subparsers.add_parser("brief-improvement", help="Compare two Pavo meeting briefs and score improvement")
    brief_improvement.add_argument("baseline", type=Path, help="Baseline pavo-meeting-brief.json")
    brief_improvement.add_argument("current", type=Path, help="Current pavo-meeting-brief.json")
    brief_improvement.add_argument("--out-dir", type=Path, help="Output directory; defaults to the current brief directory")
    brief_improvement.add_argument("--label", help="Human label for the comparison")
    brief_improvement.add_argument("--json", action="store_true", help="Print the full improvement report as JSON")

    brief_apply_hints = subparsers.add_parser("brief-apply-hints", help="Convert reviewed speaker hints into named-speaker evidence for a batch")
    brief_apply_hints.add_argument("batch_root", type=Path)
    brief_apply_hints.add_argument("speaker_hints", type=Path)
    brief_apply_hints.add_argument("--out", type=Path, help="Overlay output path; defaults to batch _work")

    meetings = subparsers.add_parser("meetings", help="Plaud-backed meeting intake commands")
    meetings_sub = meetings.add_subparsers(dest="meetings_command", required=True)
    meetings_today_parser = meetings_sub.add_parser("today", help="List Plaud recordings created today")
    meetings_today_parser.add_argument("--json", action="store_true", help="Wrap Plaud output in JSON")
    meetings_latest_parser = meetings_sub.add_parser("latest", help="List recent Plaud recordings")
    meetings_latest_parser.add_argument("--days", type=int, default=7)
    meetings_latest_parser.add_argument("--source", default="plaud", choices=["plaud"])
    meetings_latest_parser.add_argument("--json", action="store_true", help="Wrap Plaud output in JSON")
    meetings_fetch_parser = meetings_sub.add_parser("fetch", help="Fetch Plaud transcript into a meeting folder")
    meetings_fetch_parser.add_argument("recording_id")
    meetings_fetch_parser.add_argument("--transcript", action="store_true", default=True)
    meetings_fetch_parser.add_argument("--audio", action="store_true", help="Download Plaud audio when available")
    meetings_fetch_parser.add_argument("--out", type=Path, help="Output folder")
    meetings_fetch_parser.add_argument("--slug", help="Meeting folder slug when --out is omitted")
    meetings_fetch_parser.add_argument("--json", action="store_true")
    meetings_process_parser = meetings_sub.add_parser(
        "process",
        help="Transcribe, diarize, attribute, and build speaker evidence for fetched Plaud MP3 folders",
    )
    meetings_process_parser.add_argument("recordings_root", type=Path)
    meetings_process_parser.add_argument("--model", default="mlx-community/whisper-tiny")
    meetings_process_parser.add_argument("--suffix", default="")
    meetings_process_parser.add_argument("--force", action="store_true")
    meetings_process_parser.add_argument("--speakers", type=int, default=7)
    meetings_process_parser.add_argument("--min-duration", type=float, default=1.2)
    meetings_process_parser.add_argument("--skip-transcribe", action="store_true")
    meetings_process_parser.add_argument("--skip-diarize", action="store_true")
    meetings_process_parser.add_argument("--skip-attribute", action="store_true")
    meetings_process_parser.add_argument("--skip-evidence", action="store_true")
    meetings_process_parser.add_argument("--keep-going", action="store_true")
    meetings_process_parser.add_argument("--json", action="store_true")

    diarize_parser = subparsers.add_parser("diarize", help="Prepare a fetched transcript for meeting diarization")
    diarize_parser.add_argument("transcript_path", type=Path)
    diarize_parser.add_argument("--project", default="greenmark")

    audio = subparsers.add_parser("audio", help="Audio intelligence checks")
    audio_sub = audio.add_subparsers(dest="audio_command", required=True)
    audio_sub.add_parser("doctor", help="Check eidos-transcribe readiness")
    audio_process = audio_sub.add_parser("process", help="Process imported audio with eidos-transcribe speaker analysis")
    audio_process.add_argument("audio_path", type=Path)
    audio_process.add_argument("--source-id", required=True, help="Stable source identifier for the imported audio")
    audio_process.add_argument("--title", help="Human-readable source title")
    audio_process.add_argument("--context-term", action="append", default=[], help="Known-good term to pass to eidos-transcribe")
    audio_process.add_argument("--context-file", type=Path, help="Context file to pass to eidos-transcribe")
    audio_process.add_argument("--engine", action="append", default=[], help="ASR engine to run; repeatable. Defaults to faster-whisper.")
    audio_process.add_argument("--num-speakers", type=int, help="Expected speaker count")
    audio_process.add_argument(
        "--speaker",
        action="append",
        default=[],
        help="Speaker mapping as SPEAKER_01=Full Name=slug; repeatable",
    )
    audio_process.add_argument(
        "--speaker-correction",
        action="append",
        default=[],
        help="Reviewed override as start-end=SPEAKER_00; repeatable",
    )
    audio_separate = audio_sub.add_parser("separate-overlaps", help="Separate and fingerprint mixed speaker regions")
    audio_separate.add_argument("source_id")
    audio_separate.add_argument("--out-dir", type=Path, help="Override overlap output directory")
    audio_separate.add_argument("--max-regions", type=int, default=3, help="Maximum mixed regions to analyze")
    audio_separate.add_argument("--padding", type=float, default=1.0, help="Seconds of context around each region")
    audio_separate.add_argument("--min-duration", type=float, default=1.0, help="Minimum mixed-region duration in seconds")
    audio_separate.add_argument("--start", type=float, help="Only consider regions after this timestamp in seconds")
    audio_separate.add_argument("--end", type=float, help="Only consider regions before this timestamp in seconds")
    audio_decompose = audio_sub.add_parser("decompose", help="Run voiceprint-first decomposition and separation-on-demand")
    audio_decompose.add_argument("audio_path", type=Path)
    audio_decompose.add_argument("--source-id", required=True, help="Stable source identifier for the imported audio")
    audio_decompose.add_argument("--title", help="Human-readable source title")
    audio_decompose.add_argument("--context-term", action="append", default=[], help="Known-good term to pass to eidos-transcribe")
    audio_decompose.add_argument("--context-file", type=Path, help="Context file to pass to eidos-transcribe")
    audio_decompose.add_argument("--engine", action="append", default=[], help="ASR engine to run; repeatable. Defaults to faster-whisper.")
    audio_decompose.add_argument("--num-speakers", type=int, help="Expected speaker count")
    audio_decompose.add_argument("--speaker", action="append", default=[], help="Speaker mapping as SPEAKER_01=Full Name=slug; repeatable")
    audio_decompose.add_argument("--speaker-correction", action="append", default=[], help="Reviewed override as start-end=SPEAKER_00; repeatable")
    audio_decompose.add_argument("--max-regions", type=int, default=3, help="Maximum disputed regions to separate")
    audio_decompose.add_argument("--padding", type=float, default=1.0, help="Seconds of context around each disputed region")
    audio_decompose.add_argument("--min-duration", type=float, default=1.0, help="Minimum disputed-region duration in seconds")
    audio_decompose.add_argument(
        "--include-rejected-stems",
        action="store_true",
        help="Transcribe rejected separated stems as untrusted diagnostic evidence",
    )

    transcribe = subparsers.add_parser("transcribe", help="Transcribe a Plaud recording with eidos-transcribe")
    transcribe.add_argument("recording_id")
    transcribe.add_argument("--context-term", action="append", default=[], help="Known-good term to pass to eidos-transcribe")
    transcribe.add_argument("--context-file", type=Path, help="Context file to pass to eidos-transcribe")
    transcribe.add_argument("--engine", action="append", default=[], help="ASR engine to run; repeatable. Defaults to faster-whisper.")

    video = subparsers.add_parser("video", help="Video rendering commands")
    video_sub = video.add_subparsers(dest="video_command", required=True)
    video_render = video_sub.add_parser("render", help="Burn captions into a video from a processed Pavo source")
    video_render.add_argument("source_id")
    video_render.add_argument("--audio-path", type=Path, help="Override source audio/video path")
    video_render.add_argument("--transcript-json", type=Path, help="Override transcript JSON to render")
    video_render.add_argument("--out", type=Path, help="Output video path")
    video_render.add_argument("--title", help="Rendered video title")
    video_render.add_argument("--portrait", action="append", default=[], help="Speaker portrait as 'Speaker Name=/path/to/image'")
    video_render.add_argument("--width", type=int, help="Output width")
    video_render.add_argument("--height", type=int, help="Output height")
    video_render.add_argument("--fps", type=int, help="Output frames per second")
    video_render.add_argument("--start", type=float, help="Start time in seconds")
    video_render.add_argument("--duration", type=float, help="Render only this many seconds")

    review = subparsers.add_parser("review", help="Human review helpers")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    review_anchors = review_sub.add_parser("anchors", help="Review speaker anchor clips")
    review_anchors_sub = review_anchors.add_subparsers(dest="review_anchors_command", required=True)
    review_clusters = review_sub.add_parser("clusters", help="Audit diarization cluster identity")
    review_clusters_sub = review_clusters.add_subparsers(dest="review_clusters_command", required=True)
    review_clusters_prepare = review_clusters_sub.add_parser("prepare", help="Prepare the full impact-ranked cluster review queue")
    review_clusters_prepare.add_argument("batch_root", type=Path)
    review_clusters_prepare.add_argument("--out-dir", type=Path, help="Bundle output directory; defaults to batch pavo-cluster-question-bundle")
    review_clusters_prepare.add_argument("--samples-per-cluster", type=int, default=2)
    review_clusters_prepare.add_argument("--clip-padding", type=float, default=0.25)
    review_clusters_prepare.add_argument("--min-strong-coverage", type=float, default=0.25)
    review_clusters_prepare.add_argument("--min-dominant-share", type=float, default=0.85)
    review_clusters_status = review_clusters_sub.add_parser("status", help="Inspect active cluster review loop state without mutating artifacts")
    review_clusters_status.add_argument("batch_root", type=Path)
    review_clusters_status.add_argument("--review-sheet", type=Path, help="Override cluster question review sheet")
    review_clusters_status.add_argument("--json", action="store_true", help="Print full machine-readable status JSON")
    review_clusters_status.add_argument("--report", type=Path, help="Write machine-readable status JSON report")
    review_clusters_status.add_argument("--markdown-report", type=Path, help="Write human-readable status Markdown report")
    review_clusters_doctor = review_clusters_sub.add_parser("doctor", help="Check cluster review artifact and gate readiness")
    review_clusters_doctor.add_argument("batch_root", type=Path)
    review_clusters_doctor.add_argument("--review-sheet", type=Path, help="Override cluster question review sheet")
    review_clusters_doctor.add_argument("--json", action="store_true", help="Print full machine-readable doctor JSON")
    review_clusters_doctor.add_argument("--report", type=Path, help="Write machine-readable doctor JSON report")
    review_clusters_doctor.add_argument("--markdown-report", type=Path, help="Write human-readable doctor Markdown report")
    review_clusters_gate = review_clusters_sub.add_parser("gate", help="Refresh validation and emit one cluster-review readiness gate")
    review_clusters_gate.add_argument("batch_root", type=Path)
    review_clusters_gate.add_argument("--review-sheet", type=Path, help="Override cluster question review sheet")
    review_clusters_gate.add_argument("--slate", type=Path, help="Override filled decision slate TSV")
    review_clusters_gate.add_argument("--no-refresh-validation", action="store_true", help="Use the existing validation report instead of refreshing it")
    review_clusters_gate.add_argument("--json", action="store_true", help="Print full machine-readable gate JSON")
    review_clusters_gate.add_argument("--report", type=Path, help="Write machine-readable gate JSON report")
    review_clusters_gate.add_argument("--markdown-report", type=Path, help="Write human-readable gate Markdown report")
    review_clusters_slate = review_clusters_sub.add_parser("slate", help="Export a compact human decision slate for the minimal cluster queue")
    review_clusters_slate.add_argument("batch_root", type=Path)
    review_clusters_slate.add_argument("--review-sheet", type=Path, help="Override cluster question review sheet")
    review_clusters_slate.add_argument("--out-dir", type=Path, help="Directory for Markdown and TSV slate outputs")
    review_clusters_decision_brief = review_clusters_sub.add_parser(
        "decision-brief",
        help="Export a ranked decision brief for the minimal cluster queue",
    )
    review_clusters_decision_brief.add_argument("batch_root", type=Path)
    review_clusters_decision_brief.add_argument("--review-sheet", type=Path, help="Override cluster question review sheet")
    review_clusters_decision_brief.add_argument("--out-dir", type=Path, help="Directory for JSON and Markdown brief outputs")
    review_clusters_decision_brief.add_argument("--json", action="store_true", help="Print machine-readable decision brief summary JSON")
    review_clusters_import_slate = review_clusters_sub.add_parser("import-slate", help="Validate and import a filled cluster decision slate TSV")
    review_clusters_import_slate.add_argument("review_sheet", type=Path)
    review_clusters_import_slate.add_argument("slate_tsv", type=Path)
    review_clusters_import_slate.add_argument("--out", type=Path, help="Imported review sheet path; defaults to replacing review_sheet")
    review_clusters_validate_slate = review_clusters_sub.add_parser("validate-slate", help="Dry-run a filled cluster decision slate TSV before finalizing")
    review_clusters_validate_slate.add_argument("review_sheet", type=Path)
    review_clusters_validate_slate.add_argument("slate_tsv", type=Path)
    review_clusters_validate_slate.add_argument("--json", action="store_true", help="Print machine-readable validation JSON")
    review_clusters_validate_slate.add_argument("--report", type=Path, help="Write machine-readable validation JSON report")
    review_clusters_finish_slate = review_clusters_sub.add_parser("finish-from-slate", help="Import a filled slate and finalize the cluster review when gates pass")
    review_clusters_finish_slate.add_argument("batch_root", type=Path)
    review_clusters_finish_slate.add_argument("review_sheet", type=Path)
    review_clusters_finish_slate.add_argument("slate_tsv", type=Path)
    review_clusters_finish_slate.add_argument("--imported-sheet", type=Path, help="Imported review sheet path; defaults to replacing review_sheet")
    review_clusters_finish_slate.add_argument("--baseline-brief", type=Path, help="Baseline pavo-meeting-brief.json before applying reviewed feedback")
    review_clusters_finish_slate.add_argument("--out-dir", type=Path, help="Output directory for materialized cluster artifacts and improvement report")
    review_clusters_advance = review_clusters_sub.add_parser("advance", help="Run the next safe cluster-review machine step")
    review_clusters_advance.add_argument("batch_root", type=Path)
    review_clusters_advance.add_argument("--review-sheet", type=Path, help="Override cluster question review sheet")
    review_clusters_advance.add_argument("--json", action="store_true", help="Print full machine-readable advance JSON")
    review_clusters_advance.add_argument("--report", type=Path, help="Write machine-readable advance JSON report")
    review_clusters_advance.add_argument("--markdown-report", type=Path, help="Write human-readable advance Markdown report")
    review_clusters_audit = review_clusters_sub.add_parser("audit", help="Write a cluster identity propagation audit")
    review_clusters_audit.add_argument("batch_root", type=Path)
    review_clusters_audit.add_argument("--out", type=Path, help="Cluster audit JSON path")
    review_clusters_audit.add_argument("--min-strong-coverage", type=float, default=0.25)
    review_clusters_audit.add_argument("--min-dominant-share", type=float, default=0.85)
    review_clusters_questions = review_clusters_sub.add_parser("questions", help="Write targeted cluster review questions from the audit")
    review_clusters_questions.add_argument("batch_root", type=Path)
    review_clusters_questions.add_argument("--audit", type=Path, help="Existing pavo-cluster-identity-audit.json")
    review_clusters_questions.add_argument("--out", type=Path, help="Cluster question plan JSON path")
    review_clusters_questions.add_argument("--samples-per-cluster", type=int, default=2)
    review_clusters_bundle = review_clusters_sub.add_parser("bundle", help="Create an audio review bundle from a cluster question plan")
    review_clusters_bundle.add_argument("question_plan", type=Path)
    review_clusters_bundle.add_argument("--batch-root", type=Path, help="Batch root for resolving source audio; defaults to question plan batch_root")
    review_clusters_bundle.add_argument("--out-dir", type=Path, help="Bundle output directory")
    review_clusters_bundle.add_argument("--clip-padding", type=float, default=0.25)
    review_clusters_impact = review_clusters_sub.add_parser("impact", help="Rank cluster-question review rows by expected impact")
    review_clusters_impact.add_argument("review_sheet", type=Path)
    review_clusters_impact.add_argument("--out", type=Path, help="Impact report JSON path")
    review_clusters_acoustics = review_clusters_sub.add_parser("acoustics", help="Score local acoustic consistency for cluster-question review clips")
    review_clusters_acoustics.add_argument("review_sheet", type=Path)
    review_clusters_acoustics.add_argument("--out", type=Path, help="Acoustic evidence JSON path")
    review_clusters_forecast = review_clusters_sub.add_parser("forecast", help="Estimate risk-adjusted payoff for pending cluster review")
    review_clusters_forecast.add_argument("review_sheet", type=Path)
    review_clusters_forecast.add_argument("--out", type=Path, help="Forecast JSON path")
    review_clusters_decisions = review_clusters_sub.add_parser("decisions", help="Export reviewed cluster-question decisions")
    review_clusters_decisions.add_argument("review_sheet", type=Path)
    review_clusters_decisions.add_argument("--out", type=Path, help="Decision report JSON path")
    review_clusters_materialize = review_clusters_sub.add_parser("materialize-decisions", help="Materialize cluster question decisions into constraints and hints")
    review_clusters_materialize.add_argument("decision_report", type=Path)
    review_clusters_materialize.add_argument("--out-dir", type=Path, help="Output artifact directory")
    review_clusters_finalize = review_clusters_sub.add_parser("finalize", help="Apply reviewed cluster decisions, rerun the brief, and score improvement")
    review_clusters_finalize.add_argument("review_sheet", type=Path)
    review_clusters_finalize.add_argument("batch_root", type=Path)
    review_clusters_finalize.add_argument("--baseline-brief", type=Path, help="Baseline pavo-meeting-brief.json before applying reviewed feedback")
    review_clusters_finalize.add_argument("--out-dir", type=Path, help="Output directory for materialized cluster artifacts and improvement report")
    review_anchors_init = review_anchors_sub.add_parser("init", help="Create a pending review sheet from a clip packet")
    review_anchors_init.add_argument("clip_packet", type=Path)
    review_anchors_init.add_argument("--out", type=Path, help="Review sheet JSON path")
    review_anchors_summary = review_anchors_sub.add_parser("summary", help="Summarize review progress")
    review_anchors_summary.add_argument("review_sheet", type=Path)
    review_anchors_page = review_anchors_sub.add_parser("page", help="Create an HTML page for listening to anchor clips")
    review_anchors_page.add_argument("review_sheet", type=Path)
    review_anchors_page.add_argument("--out", type=Path, help="Review page HTML path")
    review_anchors_bundle = review_anchors_sub.add_parser("bundle", help="Create a browser-safe review bundle with copied clips")
    review_anchors_bundle.add_argument("review_sheet", type=Path)
    review_anchors_bundle.add_argument("--out-dir", type=Path, required=True, help="Bundle directory")
    review_anchors_serve = review_anchors_sub.add_parser("serve", help="Serve a browser-safe review bundle over localhost")
    review_anchors_serve.add_argument("bundle_dir", type=Path)
    review_anchors_serve.add_argument("--host", default="127.0.0.1")
    review_anchors_serve.add_argument("--port", type=int, default=9876)
    review_anchors_verify_page = review_anchors_sub.add_parser("verify-page", help="Verify a generated anchor review HTML page")
    review_anchors_verify_page.add_argument("review_sheet", type=Path)
    review_anchors_verify_page.add_argument("review_page", type=Path)
    review_anchors_verify_page.add_argument("--report", type=Path, help="Write machine-readable verification report JSON")
    review_anchors_import = review_anchors_sub.add_parser("import", help="Validate and import an exported reviewed sheet")
    review_anchors_import.add_argument("review_sheet", type=Path)
    review_anchors_import.add_argument("reviewed_export", type=Path)
    review_anchors_import.add_argument("--out", type=Path, help="Imported review sheet path; defaults to replacing review_sheet")
    review_anchors_rerun = review_anchors_sub.add_parser("rerun-command", help="Print decompose rerun command with approved corrections")
    review_anchors_rerun.add_argument("review_sheet", type=Path)
    review_anchors_rerun.add_argument("pavo_decompose_manifest", type=Path)
    review_anchors_rerun.add_argument("--source-id", help="Override rerun source id; defaults to original source id plus _reviewed")
    review_anchors_gate = review_anchors_sub.add_parser("gate", help="Check whether anchor review is ready for corrected decompose rerun")
    review_anchors_gate.add_argument("review_sheet", type=Path)
    review_anchors_gate.add_argument("--page-report", type=Path)
    review_anchors_gate.add_argument("--bundle-manifest", type=Path)
    review_anchors_gate.add_argument("--browser-report", type=Path)
    review_anchors_gate.add_argument("--rerun-report", type=Path)
    review_anchors_gate.add_argument("--report", type=Path, help="Write machine-readable gate report JSON")
    review_anchors_status = review_anchors_sub.add_parser("status", help="Show review URL, blockers, and next action")
    review_anchors_status.add_argument("review_sheet", type=Path)
    review_anchors_status.add_argument("--gate-report", type=Path)
    review_anchors_status.add_argument("--bundle-manifest", type=Path)
    review_anchors_status.add_argument("--report", type=Path, help="Write machine-readable status report JSON")
    review_anchors_corrections = review_anchors_sub.add_parser("corrections", help="Print approved --speaker-correction flags")
    review_anchors_corrections.add_argument("review_sheet", type=Path)
    review_anchors_decisions = review_anchors_sub.add_parser("decisions", help="Export reviewed row decisions for cluster routing/enrollment")
    review_anchors_decisions.add_argument("review_sheet", type=Path)
    review_anchors_decisions.add_argument("--out", type=Path, help="Decision report JSON path")
    review_anchors_assistant = review_anchors_sub.add_parser("assistant", help="Create deterministic assistant recommendations for a review sheet")
    review_anchors_assistant.add_argument("review_sheet", type=Path)
    review_anchors_assistant.add_argument("batch_root", type=Path)
    review_anchors_assistant.add_argument("--out", type=Path, help="Assistant report JSON path")
    review_anchors_materialize = review_anchors_sub.add_parser("materialize-decisions", help="Turn a decision report into reviewed speaker hint/enrollment artifacts")
    review_anchors_materialize.add_argument("decision_report", type=Path)
    review_anchors_materialize.add_argument("--out-dir", type=Path, help="Output artifact directory")

    config = subparsers.add_parser("config", help="Inspect local Pavo config")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser("show", help="Print non-secret config")

    plaud = subparsers.add_parser("plaud", help="Plaud recording commands")
    plaud_sub = plaud.add_subparsers(dest="plaud_command", required=True)
    plaud_sub.add_parser("me", help="Show current Plaud account")
    plaud_sub.add_parser("files", help="List Plaud recordings")
    audio_url = plaud_sub.add_parser("audio-url", help="Print audio URL")
    audio_url.add_argument("recording_id")
    download = plaud_sub.add_parser("download", help="Download Plaud audio")
    download.add_argument("recording_id")
    download.add_argument("--out-dir", help="Override output directory")

    return parser


def find_pavo_shims(
    *,
    canonical_package_root: Path | None = None,
    scan_roots: list[Path] | None = None,
) -> list[Path]:
    package_root = (canonical_package_root or Path(__file__).resolve().parent).resolve()
    roots = scan_roots if scan_roots is not None else _configured_shim_scan_roots()
    shims: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for candidate in root.rglob("pavo.py"):
            resolved = candidate.resolve()
            if resolved == package_root / "cli.py":
                continue
            if package_root in resolved.parents:
                continue
            if _is_canonical_delegator(resolved):
                continue
            shims.append(resolved)
    return sorted(dict.fromkeys(shims))


def _is_canonical_delegator(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return "PAVO_CANONICAL_DELEGATOR = True" in text


def _configured_shim_scan_roots() -> list[Path]:
    configured = os.environ.get("PAVO_SHIM_SCAN_ROOTS")
    if configured:
        return [Path(item).expanduser() for item in configured.split(os.pathsep) if item.strip()]
    return DEFAULT_SHIM_SCAN_ROOTS


def run_doctor(home: Path) -> int:
    pavo_home = init_home(home)
    package_root = Path(__file__).resolve().parent
    cli_path = shutil.which("pavo")
    shims = find_pavo_shims(canonical_package_root=package_root)
    print(f"Pavo home: {pavo_home.root}")
    print(f"Config: {pavo_home.config_path}")
    print(f"State: {pavo_home.state_path}")
    print(f"Canonical package: {package_root}")
    print(f"Pavo CLI: {cli_path or 'missing from PATH'}")
    if shims:
        print("Pavo shim drift: found non-canonical pavo.py implementations")
        for shim in shims:
            print(f"- {shim}")
        print("Fix: replace each shim with a tiny delegator to canonical `pavo`.")
    else:
        print("Pavo shim drift: none found")

    plaud_path = shutil.which("plaud")
    if not plaud_path:
        print("Plaud CLI: missing")
        print("Install with: npm install -g @plaud-ai/cli")
        return 1

    print(f"Plaud CLI: {plaud_path}")
    try:
        output = subprocess.run(
            ["plaud", "version"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        print(f"Plaud CLI version check failed: {exc.stderr.strip()}")
        return 1
    print(f"Plaud version: {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    home = home_from_arg(args.home)

    if args.command == "init":
        pavo_home = init_home(home)
        print(f"Initialized Pavo home at {pavo_home.root}")
        return 0

    if args.command == "doctor":
        return run_doctor(home)

    if args.command == "batch":
        if args.batch_command == "doctor":
            result = doctor_batch(args.batch_root, refresh_cluster_gate=not args.no_refresh_cluster_gate)
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(result.as_report(), indent=2, sort_keys=True) + "\n")
            if args.markdown_report:
                args.markdown_report.parent.mkdir(parents=True, exist_ok=True)
                args.markdown_report.write_text(result.as_markdown())
            if args.json:
                print(json.dumps(result.as_report(), indent=2, sort_keys=True))
                return 0 if result.passed else 2
            print(f"passed: {str(result.passed).lower()}")
            print(f"complete: {str(result.complete).lower()}")
            print(f"state: {result.state}")
            print(f"source_recording_count: {result.source_recording_count}")
            print(f"next_command: {result.next_command}")
            for check in result.checks:
                print(f"check_{check['name']}: {'pass' if check['passed'] else 'fail'} - {check['detail']}")
            if result.blockers:
                print("blockers: " + "; ".join(result.blockers))
            return 0 if result.passed else 2
        if args.batch_command == "verify-manifest":
            result = verify_batch_manifest(args.report)
            if args.markdown_report:
                args.markdown_report.parent.mkdir(parents=True, exist_ok=True)
                args.markdown_report.write_text(result.as_markdown())
            if args.json:
                print(json.dumps(result.as_report(), indent=2, sort_keys=True))
                return 0 if result.passed else 2
            print(f"passed: {str(result.passed).lower()}")
            print(f"checked_artifact_count: {result.checked_artifact_count}")
            print(f"source_manifest_sha256: {result.source_manifest_sha256}")
            print(f"expected_source_manifest_sha256: {result.expected_source_manifest_sha256}")
            if result.mismatches:
                print("mismatches: " + "; ".join(f"{m.get('artifact')}:{m.get('reason')}" for m in result.mismatches))
            return 0 if result.passed else 2

    if args.command == "brief":
        if not args.root.exists():
            print(f"batch root not found: {args.root}", file=sys.stderr)
            return 2
        brief_payload = build_meeting_brief(args.root, review_limit=args.review_limit, packet_limit=args.packet_limit)
        outputs = write_meeting_brief(brief_payload, args.out_dir or args.root)
        out_dir = args.out_dir or args.root
        review_plan_outputs = None
        review_plan_payload = None
        review_clip_outputs = None
        review_sheet_path = None
        review_page_path = None
        review_bundle_path = None
        if args.review_plan or args.review_plan_clips:
            review_plan_payload = build_review_cluster_plan(
                brief_payload,
                sample_limit_per_cluster=args.review_plan_sample_limit,
            )
            review_plan_outputs = write_review_cluster_plan(review_plan_payload, out_dir)
        if args.review_plan_clips and review_plan_payload:
            review_clip_outputs = write_review_cluster_clip_packet(
                review_plan_payload,
                out_dir,
                max_clips=args.review_plan_clip_limit,
            )
            review_sheet = create_anchor_review_sheet(
                review_clip_outputs.packet_path,
                out_path=out_dir / "pavo-review-cluster-sheet.json",
            )
            review_page = create_anchor_review_page(
                review_sheet.review_sheet_path,
                out_path=out_dir / "pavo-review-cluster.html",
            )
            review_bundle = create_anchor_review_bundle(
                review_sheet.review_sheet_path,
                out_dir=out_dir / "pavo-review-cluster-bundle",
            )
            review_sheet_path = review_sheet.review_sheet_path
            review_page_path = review_page.review_page_path
            review_bundle_path = review_bundle.bundle_dir
        if args.json:
            print(
                __import__("json").dumps(
                    {
                        "brief_json": str(outputs.json_path),
                        "brief_markdown": str(outputs.markdown_path),
                        "review_plan_json": str(review_plan_outputs.json_path) if review_plan_outputs else None,
                        "review_plan_markdown": str(review_plan_outputs.markdown_path) if review_plan_outputs else None,
                        "review_clip_packet": str(review_clip_outputs.packet_path) if review_clip_outputs else None,
                        "review_clip_count": review_clip_outputs.extracted_clip_count if review_clip_outputs else None,
                        "review_missing_audio_count": review_clip_outputs.missing_audio_count if review_clip_outputs else None,
                        "review_sheet": str(review_sheet_path) if review_sheet_path else None,
                        "review_page": str(review_page_path) if review_page_path else None,
                        "review_bundle": str(review_bundle_path) if review_bundle_path else None,
                        "review_plan": review_plan_payload,
                        **brief_payload,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"state: {brief_payload['state']}")
            print(f"readiness_score: {brief_payload['readiness_score']['score']}")
            print(f"readiness_grade: {brief_payload['readiness_score']['grade']}")
            print(f"review_items: {brief_payload['review']['item_count']}")
            print(f"work_packets: {brief_payload['work_packets']['packet_count']}")
            print(f"brief_json: {outputs.json_path}")
            print(f"brief_markdown: {outputs.markdown_path}")
            if review_plan_outputs:
                print(f"review_plan_json: {review_plan_outputs.json_path}")
                print(f"review_plan_markdown: {review_plan_outputs.markdown_path}")
            if review_clip_outputs:
                print(f"review_clip_packet: {review_clip_outputs.packet_path}")
                print(f"review_clip_count: {review_clip_outputs.extracted_clip_count}")
                print(f"review_missing_audio_count: {review_clip_outputs.missing_audio_count}")
                print(f"review_sheet: {review_sheet_path}")
                print(f"review_page: {review_page_path}")
                print(f"review_bundle: {review_bundle_path}")
        return 0

    if args.command == "brief-improvement":
        if not args.baseline.exists():
            print(f"baseline brief not found: {args.baseline}", file=sys.stderr)
            return 2
        if not args.current.exists():
            print(f"current brief not found: {args.current}", file=sys.stderr)
            return 2
        baseline = __import__("json").loads(args.baseline.read_text())
        current = __import__("json").loads(args.current.read_text())
        report = build_brief_improvement_report(baseline, current, label=args.label)
        outputs = write_brief_improvement_report(report, args.out_dir or args.current.parent)
        if args.json:
            print(
                __import__("json").dumps(
                    {
                        "improvement_json": str(outputs.json_path),
                        "improvement_markdown": str(outputs.markdown_path),
                        **report,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"passed: {str(report['passed']).lower()}")
            print(f"review_pressure_reduction: {report['deltas']['review_pressure_reduction']}")
            print(f"routeable_named_span_gain: {report['deltas']['routeable_named_span_gain']}")
            if report["blockers"]:
                print("blockers: " + "; ".join(report["blockers"]))
            print(f"improvement_json: {outputs.json_path}")
            print(f"improvement_markdown: {outputs.markdown_path}")
        return 0 if report["passed"] else 2

    if args.command == "brief-apply-hints":
        if not args.batch_root.exists():
            print(f"batch root not found: {args.batch_root}", file=sys.stderr)
            return 2
        if not args.speaker_hints.exists():
            print(f"speaker hints not found: {args.speaker_hints}", file=sys.stderr)
            return 2
        result = write_reviewed_hints_named_evidence(args.speaker_hints, args.batch_root, out_path=args.out)
        print(f"overlay: {result.overlay_path}")
        print(f"segment_count: {result.segment_count}")
        print(f"speaker_count: {result.speaker_count}")
        return 0 if result.segment_count else 2

    if args.command == "meetings":
        if args.meetings_command == "today":
            return meetings_today(json_output=args.json)
        if args.meetings_command == "latest":
            return meetings_latest(days=args.days, json_output=args.json)
        if args.meetings_command == "fetch":
            return meetings_fetch(
                args.recording_id,
                audio=args.audio,
                out=args.out,
                slug=args.slug,
                json_output=args.json,
            )
        if args.meetings_command == "process":
            return meetings_process(
                args.recordings_root,
                model=args.model,
                suffix=args.suffix,
                force=args.force,
                speakers=args.speakers,
                min_duration=args.min_duration,
                skip_transcribe=args.skip_transcribe,
                skip_diarize=args.skip_diarize,
                skip_attribute=args.skip_attribute,
                skip_evidence=args.skip_evidence,
                keep_going=args.keep_going,
                json_output=args.json,
            )

    if args.command == "diarize":
        return run_meeting_diarize(args.transcript_path, project=args.project)

    if args.command == "audio":
        if args.audio_command == "doctor":
            result = run_audio_doctor(home)
            print(result.report, end="")
            return result.exit_code
        if args.audio_command == "process":
            try:
                result = process_audio(
                    ProcessAudioRequest(
                        audio_path=args.audio_path,
                        source_id=args.source_id,
                        home=home,
                        title=args.title,
                        context_terms=args.context_term,
                        context_file=args.context_file,
                        engines=args.engine or ["faster-whisper"],
                        num_speakers=args.num_speakers,
                        speakers=args.speaker,
                        speaker_corrections=args.speaker_correction,
                    )
                )
            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as exc:
                print(str(exc), file=sys.stderr)
                return 2
            print(f"source_id: {result.source_id}")
            print(f"audio_path: {result.audio_path}")
            print(f"audio_sha256: {result.audio_sha256}")
            print(f"process_output_dir: {result.output_dir}")
            print(f"manifest: {result.manifest_path}")
            return 0
        if args.audio_command == "separate-overlaps":
            try:
                result = separate_overlaps(
                    SeparateOverlapsRequest(
                        source_id=args.source_id,
                        home=home,
                        out_dir=args.out_dir,
                        max_regions=args.max_regions,
                        padding=args.padding,
                        min_duration=args.min_duration,
                        start=args.start,
                        end=args.end,
                    )
                )
            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as exc:
                print(str(exc), file=sys.stderr)
                return 2
            print(f"source_id: {result.source_id}")
            print(f"audio_wav: {result.audio_wav}")
            print(f"transcript_json: {result.transcript_json}")
            print(f"signatures_manifest: {result.signatures_manifest}")
            print(f"out_dir: {result.out_dir}")
            print(f"manifest: {result.manifest_path}")
            return 0
        if args.audio_command == "decompose":
            try:
                result = decompose_audio(
                    DecomposeAudioRequest(
                        audio_path=args.audio_path,
                        source_id=args.source_id,
                        home=home,
                        title=args.title,
                        context_terms=args.context_term,
                        context_file=args.context_file,
                        engines=args.engine or ["faster-whisper"],
                        num_speakers=args.num_speakers,
                        speakers=args.speaker,
                        speaker_corrections=args.speaker_correction,
                        max_regions=args.max_regions,
                        padding=args.padding,
                        min_duration=args.min_duration,
                        include_rejected_stems=args.include_rejected_stems,
                    )
                )
            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as exc:
                print(str(exc), file=sys.stderr)
                return 2
            print(f"source_id: {result.source_id}")
            print(f"audio_path: {result.audio_path}")
            print(f"audio_sha256: {result.audio_sha256}")
            print(f"decompose_output_dir: {result.output_dir}")
            print(f"manifest: {result.manifest_path}")
            return 0

    if args.command == "transcribe":
        try:
            result = transcribe_recording(
                TranscribeRequest(
                    recording_id=args.recording_id,
                    home=home,
                    context_terms=args.context_term,
                    context_file=args.context_file,
                    engines=args.engine or ["faster-whisper"],
                )
            )
        except (PlaudCliError, subprocess.CalledProcessError, RuntimeError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"audio_path: {result.audio_path}")
        print(f"audio_sha256: {result.audio_sha256}")
        print(f"transcribe_output_dir: {result.output_dir}")
        print(f"manifest: {result.manifest_path}")
        return 0

    if args.command == "video":
        if args.video_command == "render":
            try:
                result = render_video(
                    RenderVideoRequest(
                        source_id=args.source_id,
                        home=home,
                        audio_path=args.audio_path,
                        transcript_json=args.transcript_json,
                        out_path=args.out,
                        title=args.title,
                        portraits=args.portrait,
                        width=args.width,
                        height=args.height,
                        fps=args.fps,
                        start=args.start,
                        duration=args.duration,
                    )
                )
            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as exc:
                print(str(exc), file=sys.stderr)
                return 2
            print(f"source_id: {result.source_id}")
            print(f"audio_path: {result.audio_path}")
            print(f"transcript_json: {result.transcript_json}")
            print(f"output_video: {result.out_path}")
            print(f"manifest: {result.manifest_path}")
            return 0

    if args.command == "review":
        if args.review_command == "clusters":
            if args.review_clusters_command == "prepare":
                result = prepare_cluster_review(
                    args.batch_root,
                    out_dir=args.out_dir,
                    samples_per_cluster=args.samples_per_cluster,
                    clip_padding=args.clip_padding,
                    min_strong_coverage=args.min_strong_coverage,
                    min_dominant_share=args.min_dominant_share,
                )
                print(f"audit_json: {result.audit_json_path}")
                print(f"question_json: {result.question_json_path}")
                print(f"bundle_dir: {result.bundle_dir}")
                print(f"review_sheet: {result.review_sheet_path}")
                print(f"review_page: {result.review_page_path}")
                print(f"impact_json: {result.impact_json_path}")
                print(f"impact_markdown: {result.impact_markdown_path}")
                print(f"acoustic_json: {result.acoustic_json_path}")
                print(f"acoustic_markdown: {result.acoustic_markdown_path}")
                print(f"forecast_json: {result.forecast_json_path}")
                print(f"forecast_markdown: {result.forecast_markdown_path}")
                print(f"page_verified: {str(result.page_verified).lower()}")
                print(f"cluster_count: {result.cluster_count}")
                print(f"question_count: {result.question_count}")
                print(f"candidate_count: {result.candidate_count}")
                print(f"copied_clip_count: {result.copied_clip_count}")
                print(f"missing_clip_count: {result.missing_clip_count}")
                print(f"acoustic_analyzed_count: {result.acoustic_analyzed_count}")
                print(f"acoustic_attention_cluster_count: {result.acoustic_attention_cluster_count}")
                print(f"top_cluster_id: {result.top_cluster_id}")
                print(f"estimated_unlockable_segments: {result.estimated_unlockable_segments}")
                print(f"estimated_unlockable_seconds: {result.estimated_unlockable_seconds}")
                return 0 if result.page_verified and result.candidate_count and result.missing_clip_count == 0 else 2
            if args.review_clusters_command == "status":
                result = status_cluster_review(args.batch_root, review_sheet_path=args.review_sheet)
                if args.report:
                    args.report.parent.mkdir(parents=True, exist_ok=True)
                    args.report.write_text(__import__("json").dumps(result.as_report(), indent=2, sort_keys=True) + "\n")
                if args.markdown_report:
                    args.markdown_report.parent.mkdir(parents=True, exist_ok=True)
                    args.markdown_report.write_text(result.as_markdown())
                if args.json:
                    print(__import__("json").dumps(result.as_report(), indent=2, sort_keys=True))
                    return 0
                print(f"state: {result.state}")
                print(f"review_sheet: {result.review_sheet_path}")
                print(f"candidate_count: {result.candidate_count}")
                print(f"approved_count: {result.approved_count}")
                print(f"rejected_count: {result.rejected_count}")
                print(f"pending_count: {result.pending_count}")
                print(f"cluster_count: {result.cluster_count}")
                print(f"ready_cluster_count: {result.ready_cluster_count}")
                print(f"conflicted_cluster_count: {result.conflicted_cluster_count}")
                print(f"unresolved_cluster_count: {result.unresolved_cluster_count}")
                print(f"next_review_count: {result.next_review_count}")
                print(f"review_effort: {result.review_effort.get('summary')}")
                print(f"page_verified: {str(result.page_verified).lower()}")
                print(f"top_cluster_id: {result.top_cluster_id}")
                print(f"estimated_unlockable_segments: {result.estimated_unlockable_segments}")
                print(f"estimated_unlockable_seconds: {result.estimated_unlockable_seconds}")
                print(f"constraints_count: {result.constraints_count}")
                print(f"hint_count: {result.hint_count}")
                print(f"acoustic_analyzed_count: {result.acoustic_analyzed_count}")
                print(f"acoustic_attention_cluster_count: {result.acoustic_attention_cluster_count}")
                print(f"acoustic_report: {result.acoustic_report_path}")
                print(f"forecast_risk_adjusted_segments: {result.forecast_risk_adjusted_segments}")
                print(f"forecast_report: {result.forecast_report_path}")
                print(f"review_pressure_reduction: {result.review_pressure_reduction}")
                print(f"routeable_named_span_gain: {result.routeable_named_span_gain}")
                print(f"next_command: {result.next_command}")
                if result.blockers:
                    print("blockers: " + "; ".join(result.blockers))
                return 0
            if args.review_clusters_command == "doctor":
                result = doctor_cluster_review(args.batch_root, review_sheet_path=args.review_sheet)
                if args.report:
                    args.report.parent.mkdir(parents=True, exist_ok=True)
                    args.report.write_text(__import__("json").dumps(result.as_report(), indent=2, sort_keys=True) + "\n")
                if args.markdown_report:
                    args.markdown_report.parent.mkdir(parents=True, exist_ok=True)
                    args.markdown_report.write_text(result.as_markdown())
                if args.json:
                    print(__import__("json").dumps(result.as_report(), indent=2, sort_keys=True))
                    return 0 if result.passed else 2
                print(f"passed: {str(result.passed).lower()}")
                print(f"complete: {str(result.complete).lower()}")
                print(f"state: {result.state}")
                print(f"review_sheet: {result.review_sheet_path}")
                print(f"next_command: {result.next_command}")
                for check in result.checks:
                    print(f"check_{check['name']}: {'pass' if check['passed'] else 'fail'} - {check['detail']}")
                if result.blockers:
                    print("blockers: " + "; ".join(result.blockers))
                return 0 if result.passed else 2
            if args.review_clusters_command == "gate":
                result = gate_cluster_review(
                    args.batch_root,
                    review_sheet_path=args.review_sheet,
                    slate_path=args.slate,
                    refresh_validation=not args.no_refresh_validation,
                )
                if args.report:
                    args.report.parent.mkdir(parents=True, exist_ok=True)
                    args.report.write_text(json.dumps(result.as_report(), indent=2, sort_keys=True) + "\n")
                if args.markdown_report:
                    args.markdown_report.parent.mkdir(parents=True, exist_ok=True)
                    args.markdown_report.write_text(result.as_markdown())
                if args.json:
                    print(json.dumps(result.as_report(), indent=2, sort_keys=True))
                    return 0 if result.ready_to_finalize or result.complete else 2
                print(f"passed: {str(result.passed).lower()}")
                print(f"ready_to_finalize: {str(result.ready_to_finalize).lower()}")
                print(f"complete: {str(result.complete).lower()}")
                print(f"state: {result.state}")
                print(f"review_sheet: {result.review_sheet_path}")
                print(f"slate: {result.slate_path}")
                print(f"validation_report: {result.validation_report_path}")
                print(f"next_command: {result.next_command}")
                if result.finish_command:
                    print(f"finish_command: {result.finish_command}")
                if result.blockers:
                    print("blockers: " + "; ".join(result.blockers))
                return 0 if result.ready_to_finalize or result.complete else 2
            if args.review_clusters_command == "slate":
                result = export_cluster_review_slate(args.batch_root, review_sheet_path=args.review_sheet, out_dir=args.out_dir)
                print(f"state: {result.state}")
                print(f"review_sheet: {result.review_sheet_path}")
                print(f"item_count: {result.item_count}")
                print(f"markdown: {result.markdown_path}")
                print(f"tsv: {result.tsv_path}")
                if result.blockers:
                    print("blockers: " + "; ".join(result.blockers))
                return 0 if result.item_count or result.state in {"ready_to_finalize", "finalized_passed"} else 2
            if args.review_clusters_command == "decision-brief":
                result = export_cluster_review_decision_brief(
                    args.batch_root,
                    review_sheet_path=args.review_sheet,
                    out_dir=args.out_dir,
                )
                if args.json:
                    print(
                        __import__("json").dumps(
                            {
                                "state": result.state,
                                "review_sheet": str(result.review_sheet_path) if result.review_sheet_path else None,
                                "item_count": result.item_count,
                                "total_unlockable_segments": result.total_unlockable_segments,
                                "total_unlockable_seconds": result.total_unlockable_seconds,
                                "json": str(result.json_path),
                                "markdown": str(result.markdown_path),
                                "html": str(result.html_path),
                                "blockers": result.blockers,
                            },
                            indent=2,
                            sort_keys=True,
                        )
                    )
                else:
                    print(f"state: {result.state}")
                    print(f"review_sheet: {result.review_sheet_path}")
                    print(f"item_count: {result.item_count}")
                    print(f"total_unlockable_segments: {result.total_unlockable_segments}")
                    print(f"total_unlockable_seconds: {result.total_unlockable_seconds}")
                    print(f"json: {result.json_path}")
                    print(f"markdown: {result.markdown_path}")
                    print(f"html: {result.html_path}")
                    if result.blockers:
                        print("blockers: " + "; ".join(result.blockers))
                return 0 if result.item_count or result.state in {"ready_to_finalize", "finalized_passed"} else 2
            if args.review_clusters_command == "import-slate":
                result = import_cluster_review_slate(args.review_sheet, args.slate_tsv, out_path=args.out)
                print(f"review_sheet: {result.review_sheet_path}")
                print(f"slate: {result.slate_path}")
                print(f"imported_sheet: {result.imported_sheet_path}")
                print(f"applied_count: {result.applied_count}")
                print(f"approved_count: {result.approved_count}")
                print(f"rejected_count: {result.rejected_count}")
                print(f"pending_count: {result.pending_count}")
                return 0 if result.applied_count else 2
            if args.review_clusters_command == "validate-slate":
                result = validate_cluster_review_slate(args.review_sheet, args.slate_tsv)
                if args.report:
                    args.report.parent.mkdir(parents=True, exist_ok=True)
                    args.report.write_text(json.dumps(result.as_report(), indent=2, sort_keys=True) + "\n")
                if args.json:
                    print(json.dumps(result.as_report(), indent=2, sort_keys=True))
                    return 0 if result.passed else 2
                print(f"passed: {str(result.passed).lower()}")
                print(f"ready_to_finalize: {str(result.ready_to_finalize).lower()}")
                print(f"review_sheet: {result.review_sheet_path}")
                print(f"slate: {result.slate_path}")
                print(f"applied_count: {result.applied_count}")
                print(f"approved_count: {result.approved_count}")
                print(f"rejected_count: {result.rejected_count}")
                print(f"pending_count: {result.pending_count}")
                if result.blockers:
                    print("blockers: " + "; ".join(result.blockers))
                return 0 if result.passed else 2
            if args.review_clusters_command == "finish-from-slate":
                result = finish_cluster_review_from_slate(
                    args.batch_root,
                    args.review_sheet,
                    args.slate_tsv,
                    imported_sheet_path=args.imported_sheet,
                    baseline_brief_path=args.baseline_brief,
                    out_dir=args.out_dir,
                )
                print(f"passed: {str(result.passed).lower()}")
                print(f"review_sheet: {result.review_sheet_path}")
                print(f"slate: {result.slate_path}")
                print(f"imported_sheet: {result.imported_sheet_path}")
                print(f"decision_report: {result.decision_report_path}")
                print(f"applied_count: {result.applied_count}")
                print(f"approved_count: {result.approved_count}")
                print(f"rejected_count: {result.rejected_count}")
                print(f"pending_count: {result.pending_count}")
                if result.finalize_result:
                    print(f"constraints: {result.finalize_result.constraints_path}")
                    print(f"reviewed_hints: {result.finalize_result.reviewed_hints_path}")
                    print(f"brief_json: {result.finalize_result.brief_json_path}")
                    print(f"improvement_json: {result.finalize_result.improvement_json_path}")
                    print(f"review_pressure_reduction: {result.finalize_result.review_pressure_reduction}")
                    print(f"routeable_named_span_gain: {result.finalize_result.routeable_named_span_gain}")
                if result.blockers:
                    print("blockers: " + "; ".join(result.blockers))
                return 0 if result.passed else 2
            if args.review_clusters_command == "advance":
                result = advance_cluster_review(args.batch_root, review_sheet_path=args.review_sheet)
                if args.report:
                    args.report.parent.mkdir(parents=True, exist_ok=True)
                    args.report.write_text(__import__("json").dumps(result.as_report(), indent=2, sort_keys=True) + "\n")
                if args.markdown_report:
                    args.markdown_report.parent.mkdir(parents=True, exist_ok=True)
                    args.markdown_report.write_text(result.as_markdown())
                if args.json:
                    print(__import__("json").dumps(result.as_report(), indent=2, sort_keys=True))
                    return 0 if result.action in {"await_human_review", "await_conflict_resolution"} or result.advanced else 2
                print(f"before_state: {result.before_state}")
                print(f"after_state: {result.after_state}")
                print(f"action: {result.action}")
                print(f"advanced: {str(result.advanced).lower()}")
                print(f"next_command: {result.status.next_command}")
                if result.blockers:
                    print("blockers: " + "; ".join(result.blockers))
                return 0 if result.action in {"await_human_review", "await_conflict_resolution"} or result.advanced else 2
            if args.review_clusters_command == "audit":
                result = create_cluster_identity_audit(
                    args.batch_root,
                    out_path=args.out,
                    min_strong_coverage=args.min_strong_coverage,
                    min_dominant_share=args.min_dominant_share,
                )
                print(f"audit_json: {result.json_path}")
                print(f"audit_markdown: {result.markdown_path}")
                print(f"cluster_count: {result.cluster_count}")
                print(f"status_counts: {__import__('json').dumps(result.status_counts, sort_keys=True)}")
                return 0 if result.cluster_count else 2
            if args.review_clusters_command == "questions":
                result = create_cluster_question_plan(
                    args.batch_root,
                    audit_path=args.audit,
                    out_path=args.out,
                    samples_per_cluster=args.samples_per_cluster,
                )
                print(f"question_json: {result.json_path}")
                print(f"question_markdown: {result.markdown_path}")
                print(f"cluster_count: {result.cluster_count}")
                print(f"question_count: {result.question_count}")
                return 0 if result.question_count else 2
            if args.review_clusters_command == "bundle":
                result = create_cluster_question_bundle(
                    args.question_plan,
                    batch_root=args.batch_root,
                    out_dir=args.out_dir,
                    clip_padding=args.clip_padding,
                )
                print(f"bundle_dir: {result.bundle_dir}")
                print(f"review_sheet: {result.review_sheet_path}")
                print(f"review_page: {result.review_page_path}")
                print(f"candidate_count: {result.candidate_count}")
                print(f"copied_clip_count: {result.copied_clip_count}")
                print(f"missing_clip_count: {result.missing_clip_count}")
                print(f"acoustic_json: {result.acoustic_json_path}")
                print(f"acoustic_markdown: {result.acoustic_markdown_path}")
                print(f"acoustic_analyzed_count: {result.acoustic_analyzed_count}")
                print(f"acoustic_attention_cluster_count: {result.acoustic_attention_cluster_count}")
                print(f"forecast_json: {result.forecast_json_path}")
                print(f"forecast_markdown: {result.forecast_markdown_path}")
                return 0 if result.candidate_count and result.missing_clip_count == 0 else 2
            if args.review_clusters_command == "impact":
                result = create_cluster_question_impact_report(args.review_sheet, out_path=args.out)
                print(f"impact_json: {result.json_path}")
                print(f"impact_markdown: {result.markdown_path}")
                print(f"candidate_count: {result.candidate_count}")
                print(f"cluster_count: {result.cluster_count}")
                print(f"top_cluster_id: {result.top_cluster_id}")
                print(f"estimated_unlockable_segments: {result.estimated_unlockable_segments}")
                print(f"estimated_unlockable_seconds: {result.estimated_unlockable_seconds}")
                return 0 if result.cluster_count else 2
            if args.review_clusters_command == "acoustics":
                result = create_cluster_question_acoustic_report(args.review_sheet, out_path=args.out)
                print(f"acoustic_json: {result.json_path}")
                print(f"acoustic_markdown: {result.markdown_path}")
                print(f"candidate_count: {result.candidate_count}")
                print(f"analyzed_count: {result.analyzed_count}")
                print(f"missing_count: {result.missing_count}")
                print(f"cluster_count: {result.cluster_count}")
                print(f"consistent_cluster_count: {result.consistent_cluster_count}")
                print(f"attention_cluster_count: {result.attention_cluster_count}")
                return 0 if result.analyzed_count and result.missing_count == 0 else 2
            if args.review_clusters_command == "forecast":
                result = create_cluster_review_forecast(args.review_sheet, out_path=args.out)
                print(f"forecast_json: {result.json_path}")
                print(f"forecast_markdown: {result.markdown_path}")
                print(f"candidate_count: {result.candidate_count}")
                print(f"cluster_count: {result.cluster_count}")
                print(f"pending_cluster_count: {result.pending_cluster_count}")
                print(f"estimated_unlockable_segments: {result.estimated_unlockable_segments}")
                print(f"risk_adjusted_segments: {result.risk_adjusted_segments}")
                print(f"top_cluster_id: {result.top_cluster_id}")
                return 0 if result.cluster_count else 2
            if args.review_clusters_command == "decisions":
                result = export_cluster_question_decisions(args.review_sheet, out_path=args.out)
                print(f"passed: {str(result.passed).lower()}")
                print(f"candidate_count: {result.candidate_count}")
                print(f"approved_count: {result.approved_count}")
                print(f"rejected_count: {result.rejected_count}")
                print(f"pending_count: {result.pending_count}")
                print(f"cluster_count: {result.cluster_count}")
                print(f"ready_cluster_count: {result.ready_cluster_count}")
                print(f"conflicted_cluster_count: {result.conflicted_cluster_count}")
                print(f"unresolved_cluster_count: {result.unresolved_cluster_count}")
                print(f"next_review_count: {result.next_review_count}")
                print(f"review_effort: {result.review_effort.get('summary')}")
                if result.blockers:
                    print("blockers: " + "; ".join(result.blockers))
                print(f"report: {result.report_path}")
                return 0 if result.passed else 2
            if args.review_clusters_command == "materialize-decisions":
                result = materialize_cluster_question_decisions(args.decision_report, out_dir=args.out_dir)
                print(f"passed: {str(result.passed).lower()}")
                print(f"constraints_count: {result.constraints_count}")
                print(f"hint_count: {result.hint_count}")
                if result.blockers:
                    print("blockers: " + "; ".join(result.blockers))
                print(f"constraints: {result.constraints_path}")
                print(f"reviewed_hints: {result.reviewed_hints_path}")
                return 0 if result.passed else 2
            if args.review_clusters_command == "finalize":
                result = finalize_cluster_review(
                    args.review_sheet,
                    args.batch_root,
                    baseline_brief_path=args.baseline_brief,
                    out_dir=args.out_dir,
                )
                print(f"passed: {str(result.passed).lower()}")
                print(f"approved_count: {result.approved_count}")
                print(f"rejected_count: {result.rejected_count}")
                print(f"pending_count: {result.pending_count}")
                print(f"constraints_count: {result.constraints_count}")
                print(f"hint_count: {result.hint_count}")
                print(f"decision_report: {result.decision_report_path}")
                print(f"constraints: {result.constraints_path}")
                print(f"reviewed_hints: {result.reviewed_hints_path}")
                print(f"overlay: {result.overlay_path}")
                print(f"brief_json: {result.brief_json_path}")
                print(f"improvement_json: {result.improvement_json_path}")
                print(f"improvement_markdown: {result.improvement_markdown_path}")
                print(f"review_pressure_reduction: {result.review_pressure_reduction}")
                print(f"routeable_named_span_gain: {result.routeable_named_span_gain}")
                if result.blockers:
                    print("blockers: " + "; ".join(result.blockers))
                return 0 if result.passed else 2
        if args.review_command == "anchors":
            if args.review_anchors_command == "init":
                result = create_anchor_review_sheet(args.clip_packet, out_path=args.out)
                print(f"review_sheet: {result.review_sheet_path}")
                print(f"candidate_count: {result.candidate_count}")
                print(f"pending_count: {result.pending_count}")
                return 0
            if args.review_anchors_command == "summary":
                summary = summarize_anchor_review_sheet(args.review_sheet)
                print(f"review_sheet: {summary['review_sheet']}")
                print(f"human_reviewed: {str(summary['human_reviewed']).lower()}")
                print(f"candidate_count: {summary['candidate_count']}")
                print(f"approved_count: {summary['approved_count']}")
                print(f"rejected_count: {summary['rejected_count']}")
                print(f"pending_count: {summary['pending_count']}")
                return 0
            if args.review_anchors_command == "page":
                result = create_anchor_review_page(args.review_sheet, out_path=args.out)
                print(f"review_page: {result.review_page_path}")
                print(f"candidate_count: {result.candidate_count}")
                print(f"pending_count: {result.pending_count}")
                return 0
            if args.review_anchors_command == "bundle":
                result = create_anchor_review_bundle(args.review_sheet, out_dir=args.out_dir)
                print(f"bundle_dir: {result.bundle_dir}")
                print(f"review_sheet: {result.bundled_sheet_path}")
                print(f"review_page: {result.review_page_path}")
                print(f"copied_clip_count: {result.copied_clip_count}")
                print(f"missing_clip_count: {result.missing_clip_count}")
                return 0 if result.missing_clip_count == 0 else 2
            if args.review_anchors_command == "serve":
                try:
                    result = build_anchor_review_serve_command(
                        args.bundle_dir,
                        host=args.host,
                        port=args.port,
                        python=sys.executable,
                    )
                except FileNotFoundError as exc:
                    print(str(exc), file=sys.stderr)
                    return 2
                print(f"review_url: {result.url}")
                print(f"bundle_dir: {result.bundle_dir}")
                print("Press Ctrl-C to stop the review server.")
                try:
                    serve_anchor_review_bundle(args.bundle_dir, host=args.host, port=args.port)
                except KeyboardInterrupt:
                    return 0
                return 0
            if args.review_anchors_command == "verify-page":
                result = verify_anchor_review_page(args.review_sheet, args.review_page)
                if args.report:
                    args.report.parent.mkdir(parents=True, exist_ok=True)
                    args.report.write_text(__import__("json").dumps(result.as_report(), indent=2) + "\n")
                    print(f"report: {args.report}")
                print(f"passed: {str(result.passed).lower()}")
                print(f"candidate_count: {result.candidate_count}")
                print(f"audio_count: {result.audio_count}")
                print(f"approve_count: {result.approve_count}")
                print(f"reject_count: {result.reject_count}")
                print(f"pending_button_count: {result.pending_button_count}")
                print(f"note_count: {result.note_count}")
                if result.missing:
                    print("missing: " + "; ".join(result.missing))
                return 0 if result.passed else 2
            if args.review_anchors_command == "import":
                try:
                    result = import_anchor_review_sheet(args.review_sheet, args.reviewed_export, out_path=args.out)
                except ValueError as exc:
                    print(str(exc), file=sys.stderr)
                    return 2
                print(f"review_sheet: {result.review_sheet_path}")
                print(f"imported_sheet: {result.imported_sheet_path}")
                print(f"human_reviewed: {str(result.human_reviewed).lower()}")
                print(f"candidate_count: {result.candidate_count}")
                print(f"approved_count: {result.approved_count}")
                print(f"rejected_count: {result.rejected_count}")
                print(f"pending_count: {result.pending_count}")
                return 0
            if args.review_anchors_command == "rerun-command":
                try:
                    result = build_anchor_review_rerun_command(
                        args.review_sheet,
                        args.pavo_decompose_manifest,
                        source_id=args.source_id,
                    )
                except (KeyError, ValueError) as exc:
                    print(str(exc), file=sys.stderr)
                    return 2
                print(result.shell_command)
                return 0
            if args.review_anchors_command == "gate":
                result = gate_anchor_review(
                    args.review_sheet,
                    page_report_path=args.page_report,
                    bundle_manifest_path=args.bundle_manifest,
                    browser_report_path=args.browser_report,
                    rerun_report_path=args.rerun_report,
                )
                if args.report:
                    args.report.parent.mkdir(parents=True, exist_ok=True)
                    args.report.write_text(__import__("json").dumps(result.as_report(), indent=2) + "\n")
                    print(f"report: {args.report}")
                print(f"passed: {str(result.passed).lower()}")
                print(f"human_reviewed: {str(result.human_reviewed).lower()}")
                print(f"approved_count: {result.approved_count}")
                print(f"rejected_count: {result.rejected_count}")
                print(f"pending_count: {result.pending_count}")
                print(f"page_ready: {str(result.page_ready).lower()}")
                print(f"bundle_ready: {str(result.bundle_ready).lower()}")
                print(f"browser_verified: {str(result.browser_verified).lower()}")
                print(f"rerun_command_ready: {str(result.rerun_command_ready).lower()}")
                if result.blockers:
                    print("blockers: " + "; ".join(result.blockers))
                print(f"next_action: {result.next_action}")
                return 0 if result.passed else 2
            if args.review_anchors_command == "status":
                result = status_anchor_review(
                    args.review_sheet,
                    gate_report_path=args.gate_report,
                    bundle_manifest_path=args.bundle_manifest,
                )
                if args.report:
                    args.report.parent.mkdir(parents=True, exist_ok=True)
                    args.report.write_text(__import__("json").dumps(result.as_report(), indent=2) + "\n")
                    print(f"report: {args.report}")
                print(f"passed: {str(result.passed).lower()}")
                if result.serve_command:
                    print(f"serve_command: {result.serve_command}")
                if result.review_url:
                    print(f"review_url: {result.review_url}")
                print(f"approved_count: {result.approved_count}")
                print(f"rejected_count: {result.rejected_count}")
                print(f"pending_count: {result.pending_count}")
                if result.blockers:
                    print("blockers: " + "; ".join(result.blockers))
                print(f"next_action: {result.next_action}")
                return 0 if result.passed else 2
            if args.review_anchors_command == "corrections":
                result = compile_anchor_review_corrections(args.review_sheet)
                if result.cli_args:
                    print(" ".join(result.cli_args))
                return 0
            if args.review_anchors_command == "decisions":
                result = export_anchor_review_decisions(args.review_sheet, out_path=args.out)
                print(f"passed: {str(result.passed).lower()}")
                print(f"human_reviewed: {str(result.human_reviewed).lower()}")
                print(f"candidate_count: {result.candidate_count}")
                print(f"approved_count: {result.approved_count}")
                print(f"rejected_count: {result.rejected_count}")
                print(f"pending_count: {result.pending_count}")
                print(f"routeable_count: {result.routeable_count}")
                print(f"enrollment_candidate_count: {result.enrollment_candidate_count}")
                if result.blockers:
                    print("blockers: " + "; ".join(result.blockers))
                print(f"report: {result.report_path}")
                return 0 if result.passed else 2
            if args.review_anchors_command == "assistant":
                result = create_anchor_review_assistant(args.review_sheet, args.batch_root, out_path=args.out)
                print(f"assistant_json: {result.json_path}")
                print(f"assistant_markdown: {result.markdown_path}")
                print(f"candidate_count: {result.candidate_count}")
                print(f"recommendation_counts: {__import__('json').dumps(result.recommendation_counts, sort_keys=True)}")
                return 0 if result.candidate_count else 2
            if args.review_anchors_command == "materialize-decisions":
                result = materialize_anchor_review_decisions(args.decision_report, out_dir=args.out_dir)
                print(f"passed: {str(result.passed).lower()}")
                print(f"routeable_count: {result.routeable_count}")
                print(f"enrollment_speaker_count: {result.enrollment_speaker_count}")
                if result.blockers:
                    print("blockers: " + "; ".join(result.blockers))
                print(f"speaker_hints: {result.hint_path}")
                print(f"speaker_enrollment: {result.enrollment_path}")
                print(f"rerun_plan: {result.rerun_plan_path}")
                return 0 if result.passed else 2

    if args.command == "config":
        pavo_home = init_home(home)
        if args.config_command == "show":
            print(pavo_home.config_path.read_text(), end="")
            return 0

    if args.command == "plaud":
        cli = PlaudCli()
        try:
            if args.plaud_command == "me":
                print(cli.me(), end="")
                return 0
            if args.plaud_command == "files":
                print(cli.files(), end="")
                return 0
            if args.plaud_command == "audio-url":
                print(cli.audio_url(args.recording_id))
                return 0
            if args.plaud_command == "download":
                pavo_home = init_home(home)
                out_dir = (
                    Path(args.out_dir).expanduser()
                    if args.out_dir
                    else pavo_home.cache_dir / "plaud" / args.recording_id
                )
                url = cli.audio_url(args.recording_id)
                result = save_audio(url=url, out_dir=out_dir)
                print(f"path: {result.path}")
                print(f"sha256: {result.sha256}")
                print(f"size_bytes: {result.size_bytes}")
                return 0
        except PlaudCliError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    parser.error("Unhandled command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
