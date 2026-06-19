from __future__ import annotations

from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import csv
import json
import math
import re
import subprocess
import shlex
import shutil
import tempfile
import time
import wave
from html.parser import HTMLParser
from html import escape
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .brief import (
    _apply_temporal_speaker_continuity,
    build_brief_improvement_report,
    build_meeting_brief,
    _ensemble_speaker_segments,
    _is_unknown_speaker,
    _load_diarization_segments,
    _load_named_evidence_segments,
    _load_speaker_attribution_segments,
    _rounded_time,
    write_brief_improvement_report,
    write_meeting_brief,
    write_reviewed_hints_named_evidence,
)


@dataclass(frozen=True)
class AnchorReviewSheetResult:
    review_sheet_path: Path
    candidate_count: int
    pending_count: int


@dataclass(frozen=True)
class AnchorReviewCorrectionsResult:
    review_sheet_path: Path
    approved_count: int
    corrections: list[str]
    cli_args: list[str]


@dataclass(frozen=True)
class AnchorReviewDecisionExportResult:
    review_sheet_path: Path
    report_path: Path
    passed: bool
    human_reviewed: bool
    candidate_count: int
    approved_count: int
    rejected_count: int
    pending_count: int
    routeable_count: int
    enrollment_candidate_count: int
    blockers: list[str]

    def as_report(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "review_sheet": str(self.review_sheet_path),
            "report_path": str(self.report_path),
            "human_reviewed": self.human_reviewed,
            "candidate_count": self.candidate_count,
            "approved_count": self.approved_count,
            "rejected_count": self.rejected_count,
            "pending_count": self.pending_count,
            "routeable_count": self.routeable_count,
            "enrollment_candidate_count": self.enrollment_candidate_count,
            "blockers": self.blockers,
        }

@dataclass(frozen=True)
class AnchorReviewMaterializeResult:
    decision_report_path: Path
    out_dir: Path
    passed: bool
    hint_path: Path
    enrollment_path: Path
    rerun_plan_path: Path
    routeable_count: int
    enrollment_speaker_count: int
    blockers: list[str]


@dataclass(frozen=True)
class AnchorReviewPageResult:
    review_sheet_path: Path
    review_page_path: Path
    candidate_count: int
    pending_count: int


@dataclass(frozen=True)
class AnchorReviewImportResult:
    review_sheet_path: Path
    imported_sheet_path: Path
    candidate_count: int
    approved_count: int
    rejected_count: int
    pending_count: int
    human_reviewed: bool


@dataclass(frozen=True)
class AnchorReviewRerunCommandResult:
    review_sheet_path: Path
    manifest_path: Path
    approved_count: int
    command: list[str]
    shell_command: str


@dataclass(frozen=True)
class AnchorReviewPageVerificationResult:
    review_sheet_path: Path
    review_page_path: Path
    passed: bool
    candidate_count: int
    audio_count: int
    approve_count: int
    reject_count: int
    pending_button_count: int
    note_count: int
    export_button_present: bool
    reset_button_present: bool
    shortcut_panel_present: bool
    keyboard_handler_present: bool
    audio_shortcuts_present: bool
    draft_autosave_present: bool
    cluster_summary_present: bool
    next_review_plan_present: bool
    review_effort_present: bool
    completion_handoff_present: bool
    embedded_sheet_present: bool
    import_instruction_present: bool
    rerun_instruction_present: bool
    missing: list[str]

    def as_report(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "review_sheet": str(self.review_sheet_path),
            "review_page": str(self.review_page_path),
            "candidate_count": self.candidate_count,
            "audio_count": self.audio_count,
            "approve_count": self.approve_count,
            "reject_count": self.reject_count,
            "pending_button_count": self.pending_button_count,
            "note_count": self.note_count,
            "export_button_present": self.export_button_present,
            "reset_button_present": self.reset_button_present,
            "shortcut_panel_present": self.shortcut_panel_present,
            "keyboard_handler_present": self.keyboard_handler_present,
            "audio_shortcuts_present": self.audio_shortcuts_present,
            "draft_autosave_present": self.draft_autosave_present,
            "cluster_summary_present": self.cluster_summary_present,
            "next_review_plan_present": self.next_review_plan_present,
            "review_effort_present": self.review_effort_present,
            "completion_handoff_present": self.completion_handoff_present,
            "embedded_sheet_present": self.embedded_sheet_present,
            "import_instruction_present": self.import_instruction_present,
            "rerun_instruction_present": self.rerun_instruction_present,
            "missing": self.missing,
            "next_required_proof": "human reviewer must approve or reject every clip, then import the reviewed sheet",
        }


@dataclass(frozen=True)
class AnchorReviewBundleResult:
    review_sheet_path: Path
    bundle_dir: Path
    bundled_sheet_path: Path
    review_page_path: Path
    copied_clip_count: int
    missing_clip_count: int


@dataclass(frozen=True)
class AnchorReviewAssistantResult:
    review_sheet_path: Path
    json_path: Path
    markdown_path: Path
    candidate_count: int
    recommendation_counts: dict[str, int]


@dataclass(frozen=True)
class ClusterIdentityAuditResult:
    batch_root: Path
    json_path: Path
    markdown_path: Path
    cluster_count: int
    status_counts: dict[str, int]


@dataclass(frozen=True)
class ClusterQuestionPlanResult:
    batch_root: Path
    json_path: Path
    markdown_path: Path
    question_count: int
    cluster_count: int


@dataclass(frozen=True)
class ClusterQuestionBundleResult:
    question_plan_path: Path
    review_sheet_path: Path
    review_page_path: Path
    bundle_dir: Path
    acoustic_json_path: Path
    acoustic_markdown_path: Path
    forecast_json_path: Path
    forecast_markdown_path: Path
    candidate_count: int
    copied_clip_count: int
    missing_clip_count: int
    acoustic_analyzed_count: int
    acoustic_attention_cluster_count: int


@dataclass(frozen=True)
class ClusterQuestionDecisionResult:
    review_sheet_path: Path
    report_path: Path
    passed: bool
    candidate_count: int
    approved_count: int
    rejected_count: int
    pending_count: int
    cluster_count: int
    ready_cluster_count: int
    conflicted_cluster_count: int
    unresolved_cluster_count: int
    next_review_count: int
    review_effort: dict[str, Any]
    blockers: list[str]


@dataclass(frozen=True)
class ClusterQuestionImpactResult:
    review_sheet_path: Path
    json_path: Path
    markdown_path: Path
    candidate_count: int
    cluster_count: int
    top_cluster_id: str | None
    estimated_unlockable_segments: int
    estimated_unlockable_seconds: float


@dataclass(frozen=True)
class ClusterQuestionAcousticReportResult:
    review_sheet_path: Path
    json_path: Path
    markdown_path: Path
    candidate_count: int
    analyzed_count: int
    missing_count: int
    cluster_count: int
    consistent_cluster_count: int
    attention_cluster_count: int


@dataclass(frozen=True)
class ClusterReviewForecastResult:
    review_sheet_path: Path
    json_path: Path
    markdown_path: Path
    candidate_count: int
    cluster_count: int
    pending_cluster_count: int
    estimated_unlockable_segments: int
    risk_adjusted_segments: int
    top_cluster_id: str | None


@dataclass(frozen=True)
class ClusterReviewPrepareResult:
    batch_root: Path
    audit_json_path: Path
    question_json_path: Path
    bundle_dir: Path
    review_sheet_path: Path
    review_page_path: Path
    impact_json_path: Path
    impact_markdown_path: Path
    acoustic_json_path: Path
    acoustic_markdown_path: Path
    forecast_json_path: Path
    forecast_markdown_path: Path
    page_verified: bool
    cluster_count: int
    question_count: int
    candidate_count: int
    copied_clip_count: int
    missing_clip_count: int
    acoustic_analyzed_count: int
    acoustic_attention_cluster_count: int
    top_cluster_id: str | None
    estimated_unlockable_segments: int
    estimated_unlockable_seconds: float


@dataclass(frozen=True)
class ClusterReviewSlateResult:
    batch_root: Path
    review_sheet_path: Path | None
    markdown_path: Path
    tsv_path: Path
    item_count: int
    state: str
    blockers: list[str]


@dataclass(frozen=True)
class ClusterReviewDecisionBriefResult:
    batch_root: Path
    review_sheet_path: Path | None
    json_path: Path
    markdown_path: Path
    html_path: Path
    item_count: int
    total_unlockable_segments: int
    total_unlockable_seconds: float
    state: str
    blockers: list[str]


@dataclass(frozen=True)
class ClusterReviewSlateImportResult:
    review_sheet_path: Path
    slate_path: Path
    imported_sheet_path: Path
    applied_count: int
    approved_count: int
    rejected_count: int
    pending_count: int


@dataclass(frozen=True)
class ClusterReviewFinishFromSlateResult:
    batch_root: Path
    review_sheet_path: Path
    slate_path: Path
    passed: bool
    imported_sheet_path: Path
    decision_report_path: Path
    finalize_result: ClusterReviewFinalizeResult | None
    applied_count: int
    approved_count: int
    rejected_count: int
    pending_count: int
    blockers: list[str]


@dataclass(frozen=True)
class ClusterReviewFinalizeResult:
    review_sheet_path: Path
    batch_root: Path
    passed: bool
    decision_report_path: Path
    constraints_path: Path
    reviewed_hints_path: Path
    overlay_path: Path | None
    brief_json_path: Path | None
    improvement_json_path: Path | None
    improvement_markdown_path: Path | None
    approved_count: int
    rejected_count: int
    pending_count: int
    constraints_count: int
    hint_count: int
    review_pressure_reduction: int | None
    routeable_named_span_gain: int | None
    blockers: list[str]


@dataclass(frozen=True)
class ClusterReviewStatusResult:
    batch_root: Path
    review_sheet_path: Path | None
    state: str
    candidate_count: int
    approved_count: int
    rejected_count: int
    pending_count: int
    cluster_count: int
    ready_cluster_count: int
    conflicted_cluster_count: int
    unresolved_cluster_count: int
    next_review_count: int
    review_effort: dict[str, Any]
    page_verified: bool
    top_cluster_id: str | None
    estimated_unlockable_segments: int | None
    estimated_unlockable_seconds: float | None
    constraints_count: int | None
    hint_count: int | None
    acoustic_analyzed_count: int | None
    acoustic_attention_cluster_count: int | None
    acoustic_report_path: Path | None
    forecast_risk_adjusted_segments: int | None
    forecast_report_path: Path | None
    materialized_artifact_dir: Path | None
    review_pressure_reduction: int | None
    routeable_named_span_gain: int | None
    next_review_plan: list[dict[str, Any]]
    next_command: str
    completion_commands: dict[str, str]
    blockers: list[str]

    def as_report(self) -> dict[str, Any]:
        return {
            "batch_root": str(self.batch_root),
            "review_sheet": str(self.review_sheet_path) if self.review_sheet_path else None,
            "state": self.state,
            "candidate_count": self.candidate_count,
            "approved_count": self.approved_count,
            "rejected_count": self.rejected_count,
            "pending_count": self.pending_count,
            "cluster_count": self.cluster_count,
            "ready_cluster_count": self.ready_cluster_count,
            "conflicted_cluster_count": self.conflicted_cluster_count,
            "unresolved_cluster_count": self.unresolved_cluster_count,
            "next_review_count": self.next_review_count,
            "review_effort": self.review_effort,
            "page_verified": self.page_verified,
            "top_cluster_id": self.top_cluster_id,
            "estimated_unlockable_segments": self.estimated_unlockable_segments,
            "estimated_unlockable_seconds": self.estimated_unlockable_seconds,
            "constraints_count": self.constraints_count,
            "hint_count": self.hint_count,
            "acoustic_analyzed_count": self.acoustic_analyzed_count,
            "acoustic_attention_cluster_count": self.acoustic_attention_cluster_count,
            "acoustic_report": str(self.acoustic_report_path) if self.acoustic_report_path else None,
            "forecast_risk_adjusted_segments": self.forecast_risk_adjusted_segments,
            "forecast_report": str(self.forecast_report_path) if self.forecast_report_path else None,
            "materialized_artifact_dir": str(self.materialized_artifact_dir) if self.materialized_artifact_dir else None,
            "review_pressure_reduction": self.review_pressure_reduction,
            "routeable_named_span_gain": self.routeable_named_span_gain,
            "next_review_plan": self.next_review_plan,
            "next_command": self.next_command,
            "completion_commands": self.completion_commands,
            "blockers": self.blockers,
        }

    def as_markdown(self) -> str:
        blockers = self.blockers or ["None"]
        lines = [
            "# Pavo Cluster Review Status",
            "",
            f"- Batch root: `{self.batch_root}`",
            f"- State: `{self.state}`",
            f"- Review sheet: `{self.review_sheet_path}`",
            f"- Candidate clips: {self.candidate_count}",
            f"- Approved / rejected / pending: {self.approved_count} / {self.rejected_count} / {self.pending_count}",
            f"- Cluster consensus: {self.ready_cluster_count} ready / {self.conflicted_cluster_count} conflicted / {self.unresolved_cluster_count} unresolved / {self.cluster_count} total",
            f"- Minimum next reviews: {self.next_review_count}",
            f"- Review effort: {self.review_effort.get('minimum_reviews')} minimum / {self.review_effort.get('pending_reviews')} pending / {self.review_effort.get('possible_reviews_saved')} skippable ({self.review_effort.get('reduction_percent')}% reduction)",
            f"- Page verified: `{str(self.page_verified).lower()}`",
            f"- Top cluster: `{self.top_cluster_id}`",
            f"- Estimated unlock: {self.estimated_unlockable_segments} segments / {self.estimated_unlockable_seconds} seconds",
            f"- Constraints / hints: {self.constraints_count} / {self.hint_count}",
            f"- Acoustic evidence: {self.acoustic_analyzed_count} analyzed / {self.acoustic_attention_cluster_count} attention clusters",
            f"- Forecast risk-adjusted unlock: {self.forecast_risk_adjusted_segments} segments",
            f"- Materialized artifact dir: `{self.materialized_artifact_dir}`",
            f"- Review pressure reduction: {self.review_pressure_reduction}",
            f"- Routeable named span gain: {self.routeable_named_span_gain}",
            "",
            "## Minimal Next Reviews",
            "",
        ]
        if self.next_review_plan:
            for item in self.next_review_plan:
                transcript = str(item.get("text") or "").strip()
                if len(transcript) > 220:
                    transcript = transcript[:217].rstrip() + "..."
                lines.extend(
                    [
                        f"### Cluster `{item.get('cluster_id')}` row `{item.get('row_index')}`",
                        "",
                        f"- Target speaker: `{item.get('target_speaker')}`",
                        f"- Question: {item.get('question')}",
                        f"- Expected impact: {item.get('expected_impact')}",
                        f"- Closure rule: {item.get('closure_rule')}",
                        f"- Approve effect: {item.get('approve_effect')}",
                        f"- Reject effect: {item.get('reject_effect')}",
                        f"- Terminal decision rule: {item.get('terminal_decision_rule')}",
                        f"- Acoustic verdict: `{item.get('acoustic_verdict') or 'unknown'}`",
                        f"- Acoustic min similarity: {item.get('acoustic_min_pair_similarity') if item.get('acoustic_min_pair_similarity') is not None else 'unknown'}",
                        f"- Acoustic caution: {item.get('acoustic_caution') or 'Use audio evidence as a caution only; listen before deciding.'}",
                        f"- Acoustic recommendation: {item.get('acoustic_recommended_action') or 'Use this as reviewer evidence only.'}",
                        f"- Review priority: `{item.get('review_priority_tier') or 'standard'}` / {item.get('review_priority_score') if item.get('review_priority_score') is not None else 'unknown'}",
                        f"- Priority reason: {item.get('review_priority_reason') or 'Impact-ranked representative sample.'}",
                        f"- Recommended action: {item.get('recommended_action')}",
                        f"- Clip: `{item.get('clip_path')}`",
                        f"- Transcript excerpt: {transcript or 'None'}",
                        "",
                    ]
                )
        else:
            lines.append("- None")
        lines.extend(
            [
                "",
                "## Next Action",
                "",
                f"`{self.next_command}`",
                "",
                "## Completion Commands",
                "",
            ]
        )
        if self.completion_commands:
            for label, command in self.completion_commands.items():
                lines.append(f"- {label}: `{command}`")
        else:
            lines.append("- None")
        lines.extend(
            [
                "",
                "## Reviewer Guide",
                "",
                "- Open the verified review page and work from the top-ranked clips first.",
                "- Listen to the audio before deciding; transcript text alone is not speaker truth.",
                "- Approve only when the voice supports the suggested cluster decision.",
                "- Reject clips that contradict the suggested identity, reveal a split cluster, or are too overlapped/noisy to trust.",
                "- A contradiction can early-stop a cluster as cannot-link; confirmation requires the support quorum.",
                "- Keep raw audio and voiceprint evidence inside Pavo review artifacts; do not publish them as task notes or public docs.",
                "- After every cluster has terminal consensus, run the finalize command shown above.",
                "",
                "## Blockers",
                "",
            ]
        )
        lines.extend(f"- {item}" for item in blockers)
        return "\n".join(lines).rstrip() + "\n"


@dataclass(frozen=True)
class ClusterReviewDoctorResult:
    batch_root: Path
    review_sheet_path: Path | None
    passed: bool
    complete: bool
    state: str
    checks: list[dict[str, Any]]
    blockers: list[str]
    next_command: str
    status: ClusterReviewStatusResult

    def as_report(self) -> dict[str, Any]:
        return {
            "batch_root": str(self.batch_root),
            "review_sheet": str(self.review_sheet_path) if self.review_sheet_path else None,
            "passed": self.passed,
            "complete": self.complete,
            "state": self.state,
            "checks": self.checks,
            "blockers": self.blockers,
            "next_command": self.next_command,
            "status": self.status.as_report(),
        }

    def as_markdown(self) -> str:
        lines = [
            "# Pavo Cluster Review Doctor",
            "",
            f"- Batch root: `{self.batch_root}`",
            f"- State: `{self.state}`",
            f"- Non-human plumbing passed: `{str(self.passed).lower()}`",
            f"- Complete: `{str(self.complete).lower()}`",
            f"- Next command: `{self.next_command}`",
            "",
            "## Checks",
            "",
        ]
        for check in self.checks:
            status = "pass" if check.get("passed") else "fail"
            lines.append(f"- `{status}` {check.get('name')}: {check.get('detail')}")
        lines.extend(["", "## Blockers", ""])
        if self.blockers:
            lines.extend(f"- {blocker}" for blocker in self.blockers)
        else:
            lines.append("- None")
        return "\n".join(lines).rstrip() + "\n"


@dataclass(frozen=True)
class ClusterReviewAdvanceResult:
    batch_root: Path
    before_state: str
    after_state: str
    action: str
    advanced: bool
    status: ClusterReviewStatusResult
    blockers: list[str]

    def as_report(self) -> dict[str, Any]:
        return {
            "batch_root": str(self.batch_root),
            "before_state": self.before_state,
            "after_state": self.after_state,
            "action": self.action,
            "advanced": self.advanced,
            "status": self.status.as_report(),
            "blockers": self.blockers,
            "safety_boundary": "Pavo advance only runs safe machine steps. It never approves speaker identity or bypasses required human listening.",
        }

    def as_markdown(self) -> str:
        blockers = self.blockers or ["None"]
        lines = [
            "# Pavo Cluster Review Advance",
            "",
            f"- Batch root: `{self.batch_root}`",
            f"- Before state: `{self.before_state}`",
            f"- After state: `{self.after_state}`",
            f"- Action: `{self.action}`",
            f"- Advanced: `{str(self.advanced).lower()}`",
            "",
            "## Safety Boundary",
            "",
            "Pavo advance only runs safe machine steps. It never approves speaker identity or bypasses required human listening.",
            "",
            "## Current Status",
            "",
            f"- Next command: `{self.status.next_command}`",
            f"- Candidate clips: {self.status.candidate_count}",
            f"- Cluster consensus: {self.status.ready_cluster_count} ready / {self.status.conflicted_cluster_count} conflicted / {self.status.unresolved_cluster_count} unresolved",
            f"- Review effort: {self.status.review_effort.get('summary')}",
            "",
            "## Blockers",
            "",
        ]
        lines.extend(f"- {item}" for item in blockers)
        return "\n".join(lines).rstrip() + "\n"


@dataclass(frozen=True)
class ClusterQuestionMaterializeResult:
    decision_report_path: Path
    out_dir: Path
    passed: bool
    constraints_path: Path
    reviewed_hints_path: Path
    constraints_count: int
    hint_count: int
    blockers: list[str]


@dataclass(frozen=True)
class AnchorReviewGateResult:
    review_sheet_path: Path
    passed: bool
    human_reviewed: bool
    approved_count: int
    rejected_count: int
    pending_count: int
    page_ready: bool
    bundle_ready: bool
    browser_verified: bool
    rerun_command_ready: bool
    blockers: list[str]
    next_action: str

    def as_report(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "review_sheet": str(self.review_sheet_path),
            "human_reviewed": self.human_reviewed,
            "approved_count": self.approved_count,
            "rejected_count": self.rejected_count,
            "pending_count": self.pending_count,
            "page_ready": self.page_ready,
            "bundle_ready": self.bundle_ready,
            "browser_verified": self.browser_verified,
            "rerun_command_ready": self.rerun_command_ready,
            "blockers": self.blockers,
            "next_action": self.next_action,
        }


@dataclass(frozen=True)
class AnchorReviewServeResult:
    bundle_dir: Path
    host: str
    port: int
    url: str
    command: list[str]
    shell_command: str


@dataclass(frozen=True)
class AnchorReviewStatusResult:
    review_sheet_path: Path
    passed: bool
    review_url: str | None
    serve_command: str | None
    approved_count: int
    rejected_count: int
    pending_count: int
    blockers: list[str]
    next_action: str

    def as_report(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "review_sheet": str(self.review_sheet_path),
            "review_url": self.review_url,
            "serve_command": self.serve_command,
            "approved_count": self.approved_count,
            "rejected_count": self.rejected_count,
            "pending_count": self.pending_count,
            "blockers": self.blockers,
            "next_action": self.next_action,
        }


def create_anchor_review_sheet(
    clip_packet_path: Path | str,
    *,
    out_path: Path | str | None = None,
) -> AnchorReviewSheetResult:
    packet_path = Path(clip_packet_path)
    packet = json.loads(packet_path.read_text())
    sheet_path = Path(out_path) if out_path else packet_path.with_name(packet_path.stem.replace("-clips", "-sheet") + ".json")
    rows = []
    for clip in packet.get("clips", []):
        rows.append(
            {
                "index": clip.get("index"),
                "status": "pending",
                "approved": False,
                "target_speaker_label": clip.get("target_speaker_label") or packet.get("target_speaker_label"),
                "target_speaker_name": clip.get("target_speaker_name") or packet.get("target_speaker_name"),
                "start": clip.get("start"),
                "end": clip.get("end"),
                "duration": clip.get("duration"),
                "text": clip.get("text"),
                "confidence": clip.get("confidence"),
                "method": clip.get("method"),
                "clip_path": clip.get("clip_path"),
                "recording_id": clip.get("recording_id"),
                "suggested_speaker_correction": clip.get("suggested_speaker_correction"),
                "reviewer_note": "",
                "case": clip.get("case"),
                "expected_behavior": clip.get("expected_behavior"),
                "review_heading": clip.get("review_heading"),
                "review_prompt": clip.get("review_prompt"),
                "review_subtitle": clip.get("review_subtitle"),
            }
        )
    sheet = {
        "passed": False,
        "human_reviewed": False,
        "review_packet": packet.get("review_packet"),
        "clip_packet": str(packet_path),
        "target_speaker_label": packet.get("target_speaker_label"),
        "target_speaker_name": packet.get("target_speaker_name"),
        "candidate_count": len(rows),
        "pending_count": len(rows),
        "approved_count": 0,
        "rejected_count": 0,
        "rows": rows,
        "review_title": packet.get("review_title"),
        "display_mode": packet.get("display_mode"),
        "review_labels": packet.get("review_labels"),
        "page_instructions": packet.get("page_instructions"),
        "requires_import_instruction": packet.get("requires_import_instruction", True),
        "requires_rerun_instruction": packet.get("requires_rerun_instruction", True),
        "instructions": [
            "Listen to each clip_path.",
            "Set approved true and status approved only for clean target-speaker clips.",
            "Set status rejected for wrong-speaker, overlap-heavy, noisy, or uncertain clips.",
            "Run pavo review anchors corrections <review-sheet> to export --speaker-correction flags.",
        ],
    }
    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    sheet_path.write_text(json.dumps(sheet, indent=2) + "\n")
    return AnchorReviewSheetResult(
        review_sheet_path=sheet_path,
        candidate_count=len(rows),
        pending_count=len(rows),
    )


def compile_anchor_review_corrections(review_sheet_path: Path | str) -> AnchorReviewCorrectionsResult:
    sheet_path = Path(review_sheet_path)
    sheet = json.loads(sheet_path.read_text())
    allow_correction_fallback = sheet.get("requires_rerun_instruction", True) is not False
    corrections = []
    for row in sheet.get("rows", []):
        if row.get("approved") is not True or row.get("status") != "approved":
            continue
        correction = row.get("suggested_speaker_correction")
        if not correction and allow_correction_fallback:
            correction = _speaker_correction(row.get("start"), row.get("end"), row.get("target_speaker_label"))
        if correction:
            corrections.append(correction)
    cli_args = [arg for correction in corrections for arg in ["--speaker-correction", correction]]
    return AnchorReviewCorrectionsResult(
        review_sheet_path=sheet_path,
        approved_count=len(corrections),
        corrections=corrections,
        cli_args=cli_args,
    )


def export_anchor_review_decisions(
    review_sheet_path: Path | str,
    *,
    out_path: Path | str | None = None,
) -> AnchorReviewDecisionExportResult:
    sheet_path = Path(review_sheet_path)
    sheet = json.loads(sheet_path.read_text())
    rows = sheet.get("rows", [])
    decisions = [_review_decision_row(row) for row in rows]
    approved = [decision for decision in decisions if decision["status"] == "approved"]
    rejected = [decision for decision in decisions if decision["status"] == "rejected"]
    pending = [decision for decision in decisions if decision["status"] == "pending"]
    routeable = [decision for decision in approved if decision["routeable"]]
    enrollment = [decision for decision in approved if decision["enrollment_candidate"]]
    cluster_summary = _decision_cluster_summary(decisions)
    blockers = []
    if pending:
        blockers.append(f"{len(pending)} review rows are still pending")
    if not approved:
        blockers.append("no reviewed rows were approved as usable")
    report = {
        "passed": bool(decisions and not pending and approved),
        "human_reviewed": bool(decisions and not pending),
        "review_sheet": str(sheet_path),
        "review_title": sheet.get("review_title"),
        "candidate_count": len(decisions),
        "approved_count": len(approved),
        "rejected_count": len(rejected),
        "pending_count": len(pending),
        "routeable_count": len(routeable),
        "enrollment_candidate_count": len(enrollment),
        "blockers": blockers,
        "clusters": cluster_summary,
        "decisions": decisions,
        "next_required_proof": (
            "Use approved routeable rows as reviewed speaker hints and enrollment candidates, "
            "then rerun attribution/decomposition; do not mass-approve unreviewed cluster spans."
        ),
    }
    report_path = Path(out_path) if out_path else sheet_path.with_name(sheet_path.stem.replace("-sheet", "-decisions") + ".json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return AnchorReviewDecisionExportResult(
        review_sheet_path=sheet_path,
        report_path=report_path,
        passed=bool(report["passed"]),
        human_reviewed=bool(report["human_reviewed"]),
        candidate_count=len(decisions),
        approved_count=len(approved),
        rejected_count=len(rejected),
        pending_count=len(pending),
        routeable_count=len(routeable),
        enrollment_candidate_count=len(enrollment),
        blockers=blockers,
    )


def materialize_anchor_review_decisions(
    decision_report_path: Path | str,
    *,
    out_dir: Path | str | None = None,
) -> AnchorReviewMaterializeResult:
    report_path = Path(decision_report_path)
    report = json.loads(report_path.read_text())
    target_dir = Path(out_dir) if out_dir else report_path.with_name("pavo-reviewed-speaker-artifacts")
    target_dir.mkdir(parents=True, exist_ok=True)
    decisions = report.get("decisions") or []
    routeable = [decision for decision in decisions if decision.get("routeable")]
    enrollment = [decision for decision in decisions if decision.get("enrollment_candidate")]
    grouped = _group_enrollment_samples(enrollment)
    blockers = list(report.get("blockers") or [])
    if report.get("pending_count"):
        blockers.append("decision report still has pending rows")
    if not routeable:
        blockers.append("no routeable reviewed speaker hints are available")
    hints = {
        "passed": bool(routeable),
        "source_decision_report": str(report_path),
        "created_at": _now_iso(),
        "routeable_count": len(routeable),
        "hints": [
            {
                "speaker": decision.get("speaker"),
                "recording_id": decision.get("recording_id"),
                "start": decision.get("start"),
                "end": decision.get("end"),
                "text": decision.get("text"),
                "confidence": decision.get("confidence"),
                "method": "human_reviewed_cluster_decision",
                "reviewer_note": decision.get("reviewer_note"),
                "clip_path": decision.get("clip_path"),
            }
            for decision in routeable
        ],
        "privacy": "Do not publish raw audio, voiceprints, or unreviewed speaker evidence outside Pavo.",
    }
    enrollment_payload = {
        "passed": bool(grouped),
        "source_decision_report": str(report_path),
        "created_at": _now_iso(),
        "speaker_count": len(grouped),
        "speakers": grouped,
        "next_required_proof": "Rerun attribution with these reviewed speaker hints, then regenerate the meeting brief and compare review-pressure reduction.",
    }
    rerun_plan = {
        "passed": bool(routeable and not report.get("pending_count")),
        "source_decision_report": str(report_path),
        "created_at": _now_iso(),
        "routeable_count": len(routeable),
        "enrollment_speaker_count": len(grouped),
        "blockers": list(dict.fromkeys(blockers)),
        "artifacts": {
            "speaker_hints": str(target_dir / "pavo-reviewed-speaker-hints.json"),
            "speaker_enrollment": str(target_dir / "pavo-reviewed-speaker-enrollment.json"),
        },
        "operator_next_steps": [
            "Feed pavo-reviewed-speaker-hints.json into the next attribution pass.",
            "Use pavo-reviewed-speaker-enrollment.json as the human-reviewed enrollment ledger.",
            "Regenerate pavo brief --review-plan-clips and compare routeable/review-pressure counts.",
        ],
    }
    hint_path = target_dir / "pavo-reviewed-speaker-hints.json"
    enrollment_path = target_dir / "pavo-reviewed-speaker-enrollment.json"
    rerun_plan_path = target_dir / "pavo-reviewed-speaker-rerun-plan.json"
    hint_path.write_text(json.dumps(hints, indent=2, sort_keys=True) + "\n")
    enrollment_path.write_text(json.dumps(enrollment_payload, indent=2, sort_keys=True) + "\n")
    rerun_plan_path.write_text(json.dumps(rerun_plan, indent=2, sort_keys=True) + "\n")
    return AnchorReviewMaterializeResult(
        decision_report_path=report_path,
        out_dir=target_dir,
        passed=bool(rerun_plan["passed"]),
        hint_path=hint_path,
        enrollment_path=enrollment_path,
        rerun_plan_path=rerun_plan_path,
        routeable_count=len(routeable),
        enrollment_speaker_count=len(grouped),
        blockers=list(dict.fromkeys(blockers)),
    )


def create_anchor_review_assistant(
    review_sheet_path: Path | str,
    batch_root: Path | str,
    *,
    out_path: Path | str | None = None,
) -> AnchorReviewAssistantResult:
    sheet_path = Path(review_sheet_path)
    root = Path(batch_root)
    sheet = json.loads(sheet_path.read_text())
    ensemble = _apply_temporal_speaker_continuity(
        _ensemble_speaker_segments(
            _load_speaker_attribution_segments(root),
            _load_named_evidence_segments(root),
        )
    )
    by_recording: dict[str, list[dict[str, Any]]] = {}
    by_key: dict[tuple[str, float | None, float | None], dict[str, Any]] = {}
    cluster_by_key = _diarization_cluster_by_key(root)
    for segment in ensemble:
        recording_id = str(segment.get("recording_id") or segment.get("source_id") or "")
        by_recording.setdefault(recording_id, []).append(segment)
        by_key[_review_segment_key(segment)] = segment
    for segments in by_recording.values():
        segments.sort(key=lambda item: (_rounded_time(item.get("start")) or 0.0, _rounded_time(item.get("end")) or 0.0))

    assisted_rows = []
    recommendations = []
    counts: dict[str, int] = {}
    for row in sheet.get("rows") or []:
        assistant = _review_assistant_row(
            row,
            by_key=by_key,
            by_recording=by_recording,
            cluster_by_key=cluster_by_key,
        )
        action = str(assistant["recommendation"])
        counts[action] = counts.get(action, 0) + 1
        assisted = dict(row)
        assisted["assistant_review"] = assistant
        assisted_rows.append(assisted)
        recommendations.append(
            {
                "index": row.get("index"),
                "case": row.get("case"),
                "recording_id": row.get("recording_id"),
                "start": row.get("start"),
                "end": row.get("end"),
                "target_speaker_label": row.get("target_speaker_label"),
                "text": row.get("text"),
                **assistant,
            }
        )

    report_path = Path(out_path) if out_path else sheet_path.with_name(f"{sheet_path.stem}-assistant.json")
    markdown_path = report_path.with_suffix(".md")
    assisted_sheet_path = report_path.with_name(f"{sheet_path.stem}-assisted.json")
    report = {
        "passed": bool(recommendations),
        "review_sheet": str(sheet_path),
        "batch_root": str(root),
        "candidate_count": len(recommendations),
        "recommendation_counts": counts,
        "recommendations": recommendations,
        "assisted_sheet": str(assisted_sheet_path),
        "safety_boundary": "Assistant recommendations are review accelerators only. They do not approve rows or create routeable speaker truth.",
    }
    assisted_sheet = {
        **sheet,
        "assistant_report": str(report_path),
        "rows": assisted_rows,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    markdown_path.write_text(render_anchor_review_assistant_markdown(report), encoding="utf-8")
    assisted_sheet_path.write_text(json.dumps(assisted_sheet, indent=2, sort_keys=True) + "\n")
    return AnchorReviewAssistantResult(
        review_sheet_path=sheet_path,
        json_path=report_path,
        markdown_path=markdown_path,
        candidate_count=len(recommendations),
        recommendation_counts=counts,
    )


def render_anchor_review_assistant_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Pavo Review Assistant",
        "",
        f"- Review sheet: `{report.get('review_sheet')}`",
        f"- Batch root: `{report.get('batch_root')}`",
        f"- Candidate clips: {report.get('candidate_count')}",
        f"- Recommendation counts: `{json.dumps(report.get('recommendation_counts') or {}, sort_keys=True)}`",
        "",
        "Safety boundary: assistant recommendations speed up review; they do not approve rows or create speaker truth.",
        "",
        "## Recommendations",
        "",
    ]
    for item in report.get("recommendations") or []:
        lines.extend(
            [
                f"### Row {item.get('index')} - {item.get('case')}",
                "",
                f"- Recommendation: `{item.get('recommendation')}`",
                f"- Confidence: `{item.get('assistant_confidence')}`",
                f"- Suggested speaker: `{item.get('suggested_speaker') or ''}`",
                f"- Why: {item.get('why')}",
                f"- Context: {item.get('context_summary')}",
                f"- Text: {item.get('text') or ''}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def create_cluster_identity_audit(
    batch_root: Path | str,
    *,
    out_path: Path | str | None = None,
    min_strong_coverage: float = 0.25,
    min_dominant_share: float = 0.85,
) -> ClusterIdentityAuditResult:
    root = Path(batch_root)
    clusters = _load_voice_clusters(root)
    named_by_key = {_review_segment_key(segment): segment for segment in _load_named_evidence_segments(root)}
    cluster_rows: dict[str, list[dict[str, Any]]] = {}
    for segment in _load_diarization_segments(root):
        cluster_rows.setdefault(str(segment.get("speaker") or "unknown"), []).append(segment)

    audits = []
    status_counts: dict[str, int] = {}
    for cluster_id, rows in sorted(cluster_rows.items()):
        audit = _cluster_identity_audit_row(
            cluster_id,
            rows,
            clusters.get(cluster_id) if isinstance(clusters.get(cluster_id), dict) else {},
            named_by_key,
            min_strong_coverage=min_strong_coverage,
            min_dominant_share=min_dominant_share,
        )
        audits.append(audit)
        status = str(audit["status"])
        status_counts[status] = status_counts.get(status, 0) + 1

    report_path = Path(out_path) if out_path else root / "pavo-cluster-identity-audit.json"
    markdown_path = report_path.with_suffix(".md")
    report = {
        "passed": bool(audits),
        "batch_root": str(root),
        "cluster_count": len(audits),
        "status_counts": status_counts,
        "thresholds": {
            "min_strong_coverage": min_strong_coverage,
            "min_dominant_share": min_dominant_share,
        },
        "clusters": audits,
        "safety_boundary": "Cluster identity can only be propagated when strong named evidence is sufficiently covered, dominant, and non-conflicting.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    markdown_path.write_text(render_cluster_identity_audit_markdown(report), encoding="utf-8")
    return ClusterIdentityAuditResult(
        batch_root=root,
        json_path=report_path,
        markdown_path=markdown_path,
        cluster_count=len(audits),
        status_counts=status_counts,
    )


def render_cluster_identity_audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Pavo Cluster Identity Audit",
        "",
        f"- Batch root: `{report.get('batch_root')}`",
        f"- Cluster count: {report.get('cluster_count')}",
        f"- Status counts: `{json.dumps(report.get('status_counts') or {}, sort_keys=True)}`",
        "",
        "Safety boundary: cluster labels are not speaker truth until evidence coverage, dominance, and conflict checks pass.",
        "",
        "## Clusters",
        "",
    ]
    for cluster in report.get("clusters") or []:
        lines.extend(
            [
                f"### {cluster.get('cluster_id')} - {cluster.get('status')}",
                "",
                f"- Candidate: `{cluster.get('candidate_name') or ''}` ({cluster.get('candidate_confidence') or 'unknown'})",
                f"- Dominant evidence: `{cluster.get('dominant_speaker') or ''}` ({cluster.get('dominant_share')})",
                f"- Strong coverage: {cluster.get('strong_coverage')}",
                f"- Segment count: {cluster.get('segment_count')}",
                f"- Recommended action: {cluster.get('recommended_action')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def create_cluster_question_plan(
    batch_root: Path | str,
    *,
    audit_path: Path | str | None = None,
    out_path: Path | str | None = None,
    samples_per_cluster: int = 2,
) -> ClusterQuestionPlanResult:
    root = Path(batch_root)
    audit_file = Path(audit_path) if audit_path else root / "pavo-cluster-identity-audit.json"
    if audit_file.exists():
        audit = json.loads(audit_file.read_text())
    else:
        audit_result = create_cluster_identity_audit(root)
        audit = json.loads(audit_result.json_path.read_text())
        audit_file = audit_result.json_path

    diarization_by_cluster: dict[str, list[dict[str, Any]]] = {}
    for segment in _load_diarization_segments(root):
        diarization_by_cluster.setdefault(str(segment.get("speaker") or "unknown"), []).append(segment)
    named_by_key = {_review_segment_key(segment): segment for segment in _load_named_evidence_segments(root)}

    questions = []
    for cluster in audit.get("clusters") or []:
        cluster_id = str(cluster.get("cluster_id") or "")
        samples = _cluster_question_samples(
            diarization_by_cluster.get(cluster_id, []),
            named_by_key=named_by_key,
            limit=samples_per_cluster,
        )
        if not samples:
            continue
        questions.append(_cluster_question(cluster, samples))

    report_path = Path(out_path) if out_path else root / "pavo-cluster-question-plan.json"
    markdown_path = report_path.with_suffix(".md")
    report = {
        "passed": bool(questions),
        "batch_root": str(root),
        "source_audit": str(audit_file),
        "cluster_count": len(audit.get("clusters") or []),
        "question_count": len(questions),
        "questions": questions,
        "safety_boundary": "Questions guide human review. They do not approve cluster identity or mutate speaker evidence.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    markdown_path.write_text(render_cluster_question_plan_markdown(report), encoding="utf-8")
    return ClusterQuestionPlanResult(
        batch_root=root,
        json_path=report_path,
        markdown_path=markdown_path,
        question_count=len(questions),
        cluster_count=len(audit.get("clusters") or []),
    )


def render_cluster_question_plan_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Pavo Cluster Question Plan",
        "",
        f"- Batch root: `{report.get('batch_root')}`",
        f"- Source audit: `{report.get('source_audit')}`",
        f"- Cluster count: {report.get('cluster_count')}",
        f"- Question count: {report.get('question_count')}",
        "",
        "Safety boundary: answer these questions in review before propagating cluster identity.",
        "",
        "## Questions",
        "",
    ]
    for item in report.get("questions") or []:
        lines.extend(
            [
                f"### {item.get('cluster_id')} - {item.get('question')}",
                "",
                f"- Status: `{item.get('status')}`",
                f"- Expected impact: {item.get('expected_impact')}",
                f"- Stop condition: {item.get('stop_condition')}",
                f"- Suggested decision: {item.get('suggested_decision')}",
                "",
                "Representative samples:",
            ]
        )
        for sample in item.get("samples") or []:
            lines.append(
                f"- `{sample.get('recording_id')}` {sample.get('start')}-{sample.get('end')}: {sample.get('text')}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def create_cluster_question_bundle(
    question_plan_path: Path | str,
    *,
    batch_root: Path | str | None = None,
    out_dir: Path | str | None = None,
    clip_padding: float = 0.25,
) -> ClusterQuestionBundleResult:
    plan_path = Path(question_plan_path)
    plan = json.loads(plan_path.read_text())
    root = Path(batch_root) if batch_root else Path(str(plan.get("batch_root") or plan_path.parent))
    target_dir = Path(out_dir) if out_dir else plan_path.with_name("pavo-cluster-question-bundle")
    clips_dir = target_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")

    rows = []
    copied = 0
    missing = 0
    for question_index, question in enumerate(plan.get("questions") or [], start=1):
        for sample_index, sample in enumerate(question.get("samples") or [], start=1):
            source_audio = _review_sample_audio_path(root, sample.get("recording_id"))
            clip_path = clips_dir / f"cluster-{question_index:02d}-sample-{sample_index:02d}.mp3"
            start, end = _question_sample_window(sample, padding=clip_padding)
            present = False
            actual_clip_path = clip_path
            if source_audio and ffmpeg and start is not None and end is not None:
                extracted = _extract_review_audio_clip(ffmpeg, source_audio, clip_path, start=start, end=end)
                if extracted:
                    actual_clip_path = extracted
                    present = True
            if present:
                copied += 1
            else:
                missing += 1
            rows.append(_cluster_question_review_row(question, sample, len(rows) + 1, actual_clip_path))

    rows = _rank_cluster_question_review_rows(rows)

    sheet_path = target_dir / "pavo-cluster-question-review-sheet.json"
    page_path = target_dir / "index.html"
    sheet = {
        "passed": False,
        "human_reviewed": False,
        "review_title": "Pavo Cluster Question Review",
        "display_mode": "human_review",
        "review_packet": str(plan_path),
        "clip_packet": str(plan_path),
        "candidate_count": len(rows),
        "pending_count": len(rows),
        "approved_count": 0,
        "rejected_count": 0,
        "target_speaker_label": "PAVO_CLUSTER_QUESTION",
        "target_speaker_name": "Pavo cluster question",
        "requires_import_instruction": False,
        "requires_rerun_instruction": False,
        "page_instructions": [
            "Listen to each representative sample.",
            "Approve only when the suggested cluster decision is supported by the audio.",
            "Reject when the sample contradicts the suggested decision or exposes a split cluster.",
            "Leave pending when the sample is too weak, overlapping, or noisy.",
        ],
        "review_labels": {
            "buttons": {
                "approved": "Supports decision",
                "rejected": "Contradicts decision",
                "pending": "Still uncertain",
            },
            "status": {
                "approved": "supports decision",
                "rejected": "contradicts decision",
                "pending": "uncertain",
            },
        },
        "sort": {
            "mode": "impact_desc",
            "description": "Rows are ordered by estimated speaker-routing impact so the reviewer can answer the highest-payoff questions first.",
        },
        "rows": rows,
    }
    sheet_path.write_text(json.dumps(sheet, indent=2, sort_keys=True) + "\n")
    acoustic = create_cluster_question_acoustic_report(sheet_path)
    page = create_anchor_review_page(sheet_path, out_path=page_path)
    impact = create_cluster_question_impact_report(sheet_path)
    forecast = create_cluster_review_forecast(sheet_path)
    return ClusterQuestionBundleResult(
        question_plan_path=plan_path,
        review_sheet_path=sheet_path,
        review_page_path=page.review_page_path,
        bundle_dir=target_dir,
        acoustic_json_path=acoustic.json_path,
        acoustic_markdown_path=acoustic.markdown_path,
        forecast_json_path=forecast.json_path,
        forecast_markdown_path=forecast.markdown_path,
        candidate_count=len(rows),
        copied_clip_count=copied,
        missing_clip_count=missing,
        acoustic_analyzed_count=acoustic.analyzed_count,
        acoustic_attention_cluster_count=acoustic.attention_cluster_count,
    )


def prepare_cluster_review(
    batch_root: Path | str,
    *,
    out_dir: Path | str | None = None,
    samples_per_cluster: int = 2,
    clip_padding: float = 0.25,
    min_strong_coverage: float = 0.25,
    min_dominant_share: float = 0.85,
) -> ClusterReviewPrepareResult:
    root = Path(batch_root)
    audit = create_cluster_identity_audit(
        root,
        min_strong_coverage=min_strong_coverage,
        min_dominant_share=min_dominant_share,
    )
    questions = create_cluster_question_plan(
        root,
        audit_path=audit.json_path,
        samples_per_cluster=samples_per_cluster,
    )
    bundle = create_cluster_question_bundle(
        questions.json_path,
        batch_root=root,
        out_dir=out_dir,
        clip_padding=clip_padding,
    )
    impact = create_cluster_question_impact_report(bundle.review_sheet_path)
    page = verify_anchor_review_page(bundle.review_sheet_path, bundle.review_page_path)
    return ClusterReviewPrepareResult(
        batch_root=root,
        audit_json_path=audit.json_path,
        question_json_path=questions.json_path,
        bundle_dir=bundle.bundle_dir,
        review_sheet_path=bundle.review_sheet_path,
        review_page_path=bundle.review_page_path,
        impact_json_path=impact.json_path,
        impact_markdown_path=impact.markdown_path,
        acoustic_json_path=bundle.acoustic_json_path,
        acoustic_markdown_path=bundle.acoustic_markdown_path,
        forecast_json_path=bundle.forecast_json_path,
        forecast_markdown_path=bundle.forecast_markdown_path,
        page_verified=page.passed,
        cluster_count=audit.cluster_count,
        question_count=questions.question_count,
        candidate_count=bundle.candidate_count,
        copied_clip_count=bundle.copied_clip_count,
        missing_clip_count=bundle.missing_clip_count,
        acoustic_analyzed_count=bundle.acoustic_analyzed_count,
        acoustic_attention_cluster_count=bundle.acoustic_attention_cluster_count,
        top_cluster_id=impact.top_cluster_id,
        estimated_unlockable_segments=impact.estimated_unlockable_segments,
        estimated_unlockable_seconds=impact.estimated_unlockable_seconds,
    )


def create_cluster_question_impact_report(
    review_sheet_path: Path | str,
    *,
    out_path: Path | str | None = None,
) -> ClusterQuestionImpactResult:
    sheet_path = Path(review_sheet_path)
    sheet = json.loads(sheet_path.read_text())
    rows = [row for row in sheet.get("rows") or [] if isinstance(row, dict)]
    clusters: dict[str, dict[str, Any]] = {}
    for row in rows:
        question = row.get("cluster_question") if isinstance(row.get("cluster_question"), dict) else {}
        cluster_id = str(question.get("cluster_id") or row.get("case") or "unknown")
        segments, seconds = _expected_impact_numbers(question.get("expected_impact") or row.get("review_subtitle"))
        item = clusters.setdefault(
            cluster_id,
            {
                "cluster_id": cluster_id,
                "question": question.get("question") or row.get("review_heading"),
                "status": question.get("status"),
                "target_speaker": question.get("dominant_speaker") or question.get("candidate_name") or row.get("target_speaker_label"),
                "candidate_name": question.get("candidate_name"),
                "dominant_speaker": question.get("dominant_speaker"),
                "expected_segments": segments,
                "expected_seconds": seconds,
                "candidate_rows": 0,
                "pending_rows": 0,
                "approved_rows": 0,
                "rejected_rows": 0,
                "sample_text": [],
                "review_clip_paths": [],
            },
        )
        item["expected_segments"] = max(int(item.get("expected_segments") or 0), segments)
        item["expected_seconds"] = max(float(item.get("expected_seconds") or 0.0), seconds)
        item["candidate_rows"] += 1
        status = str(row.get("status") or "pending")
        if status == "approved":
            item["approved_rows"] += 1
        elif status == "rejected":
            item["rejected_rows"] += 1
        else:
            item["pending_rows"] += 1
        text = str(row.get("text") or "").strip()
        if text and len(item["sample_text"]) < 2:
            item["sample_text"].append(text[:220])
        clip = row.get("clip_path")
        if clip and len(item["review_clip_paths"]) < 2:
            item["review_clip_paths"].append(str(clip))

    cluster_rows = []
    for item in clusters.values():
        pending_rows = int(item["pending_rows"])
        expected_segments = int(item["expected_segments"])
        expected_seconds = float(item["expected_seconds"])
        reviewed_rows = int(item["approved_rows"]) + int(item["rejected_rows"])
        impact_score = _cluster_question_impact_score(expected_segments, expected_seconds, pending_rows=pending_rows)
        if reviewed_rows:
            impact_score = round(impact_score * 0.5, 2)
        item["impact_score"] = impact_score
        item["review_state"] = "pending" if pending_rows else "reviewed"
        item["recommended_next_action"] = (
            "Review this cluster first; it has the largest estimated speaker-routing payoff."
            if pending_rows
            else "Already reviewed; materialize decisions before rerunning the brief."
        )
        cluster_rows.append(item)

    cluster_rows = sorted(
        cluster_rows,
        key=lambda item: (
            int(item.get("pending_rows") or 0) == 0,
            -float(item.get("impact_score") or 0.0),
            str(item.get("cluster_id") or ""),
        ),
    )
    pending_clusters = [item for item in cluster_rows if int(item.get("pending_rows") or 0)]
    estimated_segments = sum(int(item.get("expected_segments") or 0) for item in pending_clusters)
    estimated_seconds = round(sum(float(item.get("expected_seconds") or 0.0) for item in pending_clusters), 2)
    report = {
        "passed": bool(cluster_rows),
        "review_sheet": str(sheet_path),
        "candidate_count": len(rows),
        "cluster_count": len(cluster_rows),
        "pending_cluster_count": len(pending_clusters),
        "top_cluster_id": cluster_rows[0]["cluster_id"] if cluster_rows else None,
        "estimated_unlockable_segments": estimated_segments,
        "estimated_unlockable_seconds": estimated_seconds,
        "clusters": cluster_rows,
        "safety_boundary": "Impact is a prioritization estimate only. It does not approve identity, create constraints, or route speaker claims.",
        "next_required_proof": "Review the top pending cluster clips, export decisions, materialize constraints, rerun the brief, then compare review pressure.",
    }
    json_path = Path(out_path) if out_path else sheet_path.with_name(sheet_path.stem.replace("-sheet", "-impact") + ".json")
    markdown_path = json_path.with_suffix(".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    markdown_path.write_text(render_cluster_question_impact_markdown(report), encoding="utf-8")
    return ClusterQuestionImpactResult(
        review_sheet_path=sheet_path,
        json_path=json_path,
        markdown_path=markdown_path,
        candidate_count=len(rows),
        cluster_count=len(cluster_rows),
        top_cluster_id=report["top_cluster_id"],
        estimated_unlockable_segments=estimated_segments,
        estimated_unlockable_seconds=estimated_seconds,
    )


def render_cluster_question_impact_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Pavo Cluster Question Impact Preview",
        "",
        f"- Review sheet: `{report.get('review_sheet')}`",
        f"- Candidate rows: {report.get('candidate_count')}",
        f"- Cluster count: {report.get('cluster_count')}",
        f"- Pending clusters: {report.get('pending_cluster_count')}",
        f"- Estimated unlockable segments: {report.get('estimated_unlockable_segments')}",
        f"- Estimated unlockable seconds: {report.get('estimated_unlockable_seconds')}",
        "",
        "Safety boundary: this is prioritization only. Listen before approving any cluster identity.",
        "",
        "## Ranked Cluster Decisions",
        "",
    ]
    for item in report.get("clusters") or []:
        lines.extend(
            [
                f"### {item.get('cluster_id')} - {item.get('target_speaker') or 'unknown'}",
                "",
                f"- Review state: `{item.get('review_state')}`",
                f"- Impact score: {item.get('impact_score')}",
                f"- Expected impact: {item.get('expected_segments')} segments / {item.get('expected_seconds')} seconds",
                f"- Pending rows: {item.get('pending_rows')}",
                f"- Question: {item.get('question')}",
                f"- Recommended next action: {item.get('recommended_next_action')}",
                "",
            ]
        )
        for text in item.get("sample_text") or []:
            lines.append(f"- Sample: {text}")
        if item.get("sample_text"):
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def create_cluster_question_acoustic_report(
    review_sheet_path: Path | str,
    *,
    out_path: Path | str | None = None,
) -> ClusterQuestionAcousticReportResult:
    sheet_path = Path(review_sheet_path)
    sheet = json.loads(sheet_path.read_text())
    rows = [row for row in sheet.get("rows") or [] if isinstance(row, dict)]
    analyzed_rows = []
    cluster_groups: dict[str, list[dict[str, Any]]] = {}
    missing_count = 0
    for row in rows:
        cluster = row.get("cluster_question") if isinstance(row.get("cluster_question"), dict) else {}
        cluster_id = str(cluster.get("cluster_id") or row.get("case") or "unknown")
        clip_path = _resolve_review_clip_path(sheet_path, row.get("clip_path"))
        signature = _acoustic_signature_for_clip(clip_path)
        if not signature.get("analyzed"):
            missing_count += 1
        item = {
            "index": row.get("index"),
            "cluster_id": cluster_id,
            "target_speaker": row.get("target_speaker_label") or cluster.get("dominant_speaker") or cluster.get("candidate_name"),
            "status": row.get("status") or "pending",
            "clip_path": str(clip_path) if clip_path else None,
            "text": row.get("text"),
            "signature": signature,
        }
        analyzed_rows.append(item)
        cluster_groups.setdefault(cluster_id, []).append(item)

    cluster_reports = [_cluster_acoustic_summary(cluster_id, items) for cluster_id, items in sorted(cluster_groups.items())]
    consistent_count = sum(1 for item in cluster_reports if item["verdict"] == "consistent_acoustic_shape")
    attention_count = sum(1 for item in cluster_reports if item["verdict"] in {"mixed_acoustic_shape", "listen_carefully_acoustic_drift", "insufficient_audio"})
    report = {
        "passed": bool(rows and missing_count == 0),
        "review_sheet": str(sheet_path),
        "candidate_count": len(rows),
        "analyzed_count": sum(1 for item in analyzed_rows if item["signature"].get("analyzed")),
        "missing_count": missing_count,
        "cluster_count": len(cluster_reports),
        "consistent_cluster_count": consistent_count,
        "attention_cluster_count": attention_count,
        "clusters": cluster_reports,
        "rows": analyzed_rows,
        "safety_boundary": "Acoustic consistency is reviewer evidence only. It is not speaker identity, approval, a voiceprint, or a routing constraint.",
        "next_required_proof": "Listen to pending clips, make human decisions, finalize reviewed constraints, then prove review-pressure reduction.",
    }
    json_path = Path(out_path) if out_path else sheet_path.with_name("pavo-cluster-question-acoustic-evidence.json")
    markdown_path = json_path.with_suffix(".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    markdown_path.write_text(render_cluster_question_acoustic_markdown(report), encoding="utf-8")
    return ClusterQuestionAcousticReportResult(
        review_sheet_path=sheet_path,
        json_path=json_path,
        markdown_path=markdown_path,
        candidate_count=len(rows),
        analyzed_count=int(report["analyzed_count"]),
        missing_count=missing_count,
        cluster_count=len(cluster_reports),
        consistent_cluster_count=consistent_count,
        attention_cluster_count=attention_count,
    )


def render_cluster_question_acoustic_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Pavo Cluster Acoustic Evidence",
        "",
        f"- Review sheet: `{report.get('review_sheet')}`",
        f"- Candidate rows: {report.get('candidate_count')}",
        f"- Analyzed clips: {report.get('analyzed_count')}",
        f"- Missing clips: {report.get('missing_count')}",
        f"- Cluster count: {report.get('cluster_count')}",
        f"- Consistent clusters: {report.get('consistent_cluster_count')}",
        f"- Attention clusters: {report.get('attention_cluster_count')}",
        "",
        "Safety boundary: acoustic consistency is evidence for the reviewer, not speaker identity.",
        "",
        "## Cluster Evidence",
        "",
    ]
    for item in report.get("clusters") or []:
        lines.extend(
            [
                f"### {item.get('cluster_id')}",
                "",
                f"- Verdict: `{item.get('verdict')}`",
                f"- Sample count: {item.get('sample_count')}",
                f"- Analyzed count: {item.get('analyzed_count')}",
                f"- Pair similarity min / average: {item.get('min_pair_similarity')} / {item.get('average_pair_similarity')}",
                f"- Recommended next action: {item.get('recommended_next_action')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def create_cluster_review_forecast(
    review_sheet_path: Path | str,
    *,
    out_path: Path | str | None = None,
) -> ClusterReviewForecastResult:
    sheet_path = Path(review_sheet_path)
    impact_path = sheet_path.with_name(sheet_path.stem.replace("-sheet", "-impact") + ".json")
    acoustic_path = sheet_path.with_name("pavo-cluster-question-acoustic-evidence.json")
    impact = _load_optional_json(impact_path)
    if not impact:
        create_cluster_question_impact_report(sheet_path)
        impact = _load_optional_json(impact_path)
    acoustic = _load_optional_json(acoustic_path)
    if not acoustic:
        create_cluster_question_acoustic_report(sheet_path)
        acoustic = _load_optional_json(acoustic_path)
    acoustic_by_cluster = {
        str(item.get("cluster_id") or ""): item
        for item in (acoustic.get("clusters") if isinstance(acoustic, dict) else []) or []
        if isinstance(item, dict)
    }
    clusters = []
    for item in (impact.get("clusters") if isinstance(impact, dict) else []) or []:
        if not isinstance(item, dict):
            continue
        cluster_id = str(item.get("cluster_id") or "")
        acoustic_item = acoustic_by_cluster.get(cluster_id, {})
        probability = _forecast_success_probability(str(acoustic_item.get("verdict") or "unknown"))
        expected_segments = int(item.get("expected_segments") or 0)
        risk_adjusted = int(round(expected_segments * probability))
        clusters.append(
            {
                "cluster_id": cluster_id,
                "target_speaker": item.get("target_speaker"),
                "review_state": item.get("review_state"),
                "pending_rows": int(item.get("pending_rows") or 0),
                "expected_segments": expected_segments,
                "expected_seconds": float(item.get("expected_seconds") or 0.0),
                "impact_score": item.get("impact_score"),
                "acoustic_verdict": acoustic_item.get("verdict"),
                "acoustic_min_pair_similarity": acoustic_item.get("min_pair_similarity"),
                "success_probability": probability,
                "risk_adjusted_segments": risk_adjusted,
                "recommended_next_action": _forecast_next_action(item, acoustic_item, probability),
            }
        )
    clusters.sort(key=lambda row: (-int(row.get("risk_adjusted_segments") or 0), -float(row.get("impact_score") or 0.0), str(row.get("cluster_id") or "")))
    pending_clusters = [row for row in clusters if int(row.get("pending_rows") or 0)]
    estimated_segments = sum(int(row.get("expected_segments") or 0) for row in pending_clusters)
    risk_adjusted_segments = sum(int(row.get("risk_adjusted_segments") or 0) for row in pending_clusters)
    report = {
        "passed": bool(clusters),
        "review_sheet": str(sheet_path),
        "candidate_count": int(impact.get("candidate_count") or 0) if isinstance(impact, dict) else 0,
        "cluster_count": len(clusters),
        "pending_cluster_count": len(pending_clusters),
        "estimated_unlockable_segments": estimated_segments,
        "risk_adjusted_segments": risk_adjusted_segments,
        "top_cluster_id": clusters[0]["cluster_id"] if clusters else None,
        "clusters": clusters,
        "safety_boundary": "Forecasts are planning estimates only. They do not approve identity, create constraints, or prove improvement.",
        "next_required_proof": "Human decisions, materialized constraints, rerun brief, and measured review-pressure reduction.",
    }
    json_path = Path(out_path) if out_path else sheet_path.with_name("pavo-cluster-review-forecast.json")
    markdown_path = json_path.with_suffix(".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    markdown_path.write_text(render_cluster_review_forecast_markdown(report), encoding="utf-8")
    return ClusterReviewForecastResult(
        review_sheet_path=sheet_path,
        json_path=json_path,
        markdown_path=markdown_path,
        candidate_count=int(report["candidate_count"]),
        cluster_count=len(clusters),
        pending_cluster_count=len(pending_clusters),
        estimated_unlockable_segments=estimated_segments,
        risk_adjusted_segments=risk_adjusted_segments,
        top_cluster_id=report["top_cluster_id"],
    )


def render_cluster_review_forecast_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Pavo Cluster Review Forecast",
        "",
        f"- Review sheet: `{report.get('review_sheet')}`",
        f"- Candidate rows: {report.get('candidate_count')}",
        f"- Pending clusters: {report.get('pending_cluster_count')}",
        f"- Estimated unlockable segments: {report.get('estimated_unlockable_segments')}",
        f"- Risk-adjusted segments: {report.get('risk_adjusted_segments')}",
        f"- Top cluster: `{report.get('top_cluster_id')}`",
        "",
        "Safety boundary: this is a forecast only. It is not speaker identity or measured improvement.",
        "",
        "## Forecasted Clusters",
        "",
    ]
    for item in report.get("clusters") or []:
        lines.extend(
            [
                f"### {item.get('cluster_id')} - {item.get('target_speaker') or 'unknown'}",
                "",
                f"- Acoustic verdict: `{item.get('acoustic_verdict')}`",
                f"- Success probability: {item.get('success_probability')}",
                f"- Expected / risk-adjusted segments: {item.get('expected_segments')} / {item.get('risk_adjusted_segments')}",
                f"- Recommended next action: {item.get('recommended_next_action')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _forecast_success_probability(acoustic_verdict: str) -> float:
    if acoustic_verdict == "consistent_acoustic_shape":
        return 0.75
    if acoustic_verdict == "mixed_acoustic_shape":
        return 0.5
    if acoustic_verdict == "listen_carefully_acoustic_drift":
        return 0.25
    if acoustic_verdict == "insufficient_audio":
        return 0.2
    return 0.35


def _forecast_next_action(impact_item: dict[str, Any], acoustic_item: dict[str, Any], probability: float) -> str:
    if int(impact_item.get("pending_rows") or 0) <= 0:
        return "Already reviewed; materialize decisions and measure actual improvement."
    verdict = str(acoustic_item.get("verdict") or "unknown")
    if verdict == "listen_carefully_acoustic_drift":
        return "Review first with extra caution; acoustic drift may expose a split cluster or overlap."
    if verdict == "insufficient_audio":
        return "Repair or replace samples before trusting this forecast."
    if probability >= 0.7:
        return "High-value review candidate; samples look acoustically consistent but still require listening."
    return "Review carefully; expected payoff is real but acoustic evidence is mixed."


def export_cluster_question_decisions(
    review_sheet_path: Path | str,
    *,
    out_path: Path | str | None = None,
) -> ClusterQuestionDecisionResult:
    sheet_path = Path(review_sheet_path)
    sheet = json.loads(sheet_path.read_text())
    rows = sheet.get("rows") or []
    decisions = [_cluster_question_decision_row(row) for row in rows]
    approved = [row for row in decisions if row["status"] == "approved"]
    rejected = [row for row in decisions if row["status"] == "rejected"]
    pending = [row for row in decisions if row["status"] == "pending"]
    cluster_summaries = _cluster_question_consensus_summaries(decisions)
    next_review_plan = _cluster_question_next_review_plan(decisions, cluster_summaries)
    review_effort = _cluster_question_review_effort(pending_count=len(pending), next_review_count=len(next_review_plan))
    ready_clusters = [row for row in cluster_summaries if str(row.get("consensus_state") or "").startswith("ready_for_")]
    conflicted_clusters = [row for row in cluster_summaries if row.get("consensus_state") == "conflicting_review"]
    unresolved_clusters = [
        row
        for row in cluster_summaries
        if row.get("consensus_state") not in {"ready_for_must_link", "ready_for_cannot_link", "conflicting_review"}
    ]
    blockers = []
    if conflicted_clusters:
        blockers.append(f"{len(conflicted_clusters)} clusters have conflicting approved/rejected samples")
    if unresolved_clusters:
        blockers.append(f"{len(unresolved_clusters)} cluster questions still need review before terminal consensus")
    if not approved and not rejected:
        blockers.append("no cluster question rows have been reviewed")
    passed = bool(decisions and not blockers and (approved or rejected))
    report = {
        "passed": passed,
        "human_reviewed": bool(decisions and not pending),
        "review_sheet": str(sheet_path),
        "review_title": sheet.get("review_title"),
        "candidate_count": len(decisions),
        "approved_count": len(approved),
        "rejected_count": len(rejected),
        "pending_count": len(pending),
        "cluster_count": len(cluster_summaries),
        "ready_cluster_count": len(ready_clusters),
        "conflicted_cluster_count": len(conflicted_clusters),
        "unresolved_cluster_count": len(unresolved_clusters),
        "next_review_count": len(next_review_plan),
        "review_effort": review_effort,
        "next_review_plan": next_review_plan,
        "cluster_reviewed": bool(cluster_summaries and not unresolved_clusters and not conflicted_clusters),
        "clusters": cluster_summaries,
        "blockers": blockers,
        "decisions": decisions,
        "next_required_proof": "Materialize reviewed cluster decisions into constraints, rerun Pavo brief, and compare review pressure.",
    }
    report_path = Path(out_path) if out_path else sheet_path.with_name(sheet_path.stem.replace("-sheet", "-decisions") + ".json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return ClusterQuestionDecisionResult(
        review_sheet_path=sheet_path,
        report_path=report_path,
        passed=passed,
        candidate_count=len(decisions),
        approved_count=len(approved),
        rejected_count=len(rejected),
        pending_count=len(pending),
        cluster_count=len(cluster_summaries),
        ready_cluster_count=len(ready_clusters),
        conflicted_cluster_count=len(conflicted_clusters),
        unresolved_cluster_count=len(unresolved_clusters),
        next_review_count=len(next_review_plan),
        review_effort=review_effort,
        blockers=blockers,
    )


def materialize_cluster_question_decisions(
    decision_report_path: Path | str,
    *,
    out_dir: Path | str | None = None,
) -> ClusterQuestionMaterializeResult:
    report_path = Path(decision_report_path)
    report = json.loads(report_path.read_text())
    target_dir = Path(out_dir) if out_dir else report_path.with_name("pavo-cluster-question-artifacts")
    target_dir.mkdir(parents=True, exist_ok=True)
    blockers = list(report.get("blockers") or [])
    decisions = report.get("decisions") or []
    approved = [row for row in decisions if row.get("status") == "approved"]
    rejected = [row for row in decisions if row.get("status") == "rejected"]
    constraints = [_cluster_constraint_from_decision(row, kind="must_link") for row in approved]
    constraints.extend(_cluster_constraint_from_decision(row, kind="cannot_link") for row in rejected)
    constraints = [row for row in constraints if row]
    hints = [_cluster_hint_from_decision(row) for row in approved]
    hints = [row for row in hints if row]
    if not constraints:
        blockers.append("no reviewed cluster constraints were materialized")
    constraints_path = target_dir / "pavo-cluster-constraints.json"
    hints_path = target_dir / "pavo-cluster-reviewed-hints.json"
    constraints_payload = {
        "passed": bool(constraints and not blockers),
        "source_decision_report": str(report_path),
        "created_at": _now_iso(),
        "constraint_count": len(constraints),
        "constraints": constraints,
        "blockers": list(dict.fromkeys(blockers)),
        "privacy": "Reviewed constraints are routing evidence; do not publish raw audio or voiceprints outside Pavo.",
    }
    hints_payload = {
        "passed": bool(hints and not blockers),
        "source_decision_report": str(report_path),
        "created_at": _now_iso(),
        "hint_count": len(hints),
        "hints": hints,
        "privacy": "Reviewed cluster hints are routing evidence; do not publish raw audio or voiceprints outside Pavo.",
    }
    constraints_path.write_text(json.dumps(constraints_payload, indent=2, sort_keys=True) + "\n")
    hints_path.write_text(json.dumps(hints_payload, indent=2, sort_keys=True) + "\n")
    return ClusterQuestionMaterializeResult(
        decision_report_path=report_path,
        out_dir=target_dir,
        passed=bool(constraints and not blockers),
        constraints_path=constraints_path,
        reviewed_hints_path=hints_path,
        constraints_count=len(constraints),
        hint_count=len(hints),
        blockers=list(dict.fromkeys(blockers)),
    )


def finalize_cluster_review(
    review_sheet_path: Path | str,
    batch_root: Path | str,
    *,
    baseline_brief_path: Path | str | None = None,
    out_dir: Path | str | None = None,
) -> ClusterReviewFinalizeResult:
    sheet_path = Path(review_sheet_path)
    root = Path(batch_root)
    target_dir = Path(out_dir) if out_dir else root / "pavo-cluster-question-artifacts"
    target_dir.mkdir(parents=True, exist_ok=True)
    baseline = _load_baseline_brief(root, baseline_brief_path)
    decisions = export_cluster_question_decisions(sheet_path)
    materialized = materialize_cluster_question_decisions(decisions.report_path, out_dir=target_dir)
    blockers = list(dict.fromkeys([*decisions.blockers, *materialized.blockers]))
    overlay_path = None
    brief_json_path = None
    improvement_json_path = None
    improvement_markdown_path = None
    review_pressure_reduction = None
    routeable_named_span_gain = None

    if not blockers and materialized.passed:
        if materialized.hint_count:
            overlay = write_reviewed_hints_named_evidence(materialized.reviewed_hints_path, root)
            overlay_path = overlay.overlay_path
        current = build_meeting_brief(root)
        brief_outputs = write_meeting_brief(current, root)
        brief_json_path = brief_outputs.json_path
        improvement = build_brief_improvement_report(baseline, current, label="Pavo cluster review finalize")
        improvement_outputs = write_brief_improvement_report(improvement, target_dir)
        improvement_json_path = improvement_outputs.json_path
        improvement_markdown_path = improvement_outputs.markdown_path
        review_pressure_reduction = int(improvement.get("deltas", {}).get("review_pressure_reduction") or 0)
        routeable_named_span_gain = int(improvement.get("deltas", {}).get("routeable_named_span_gain") or 0)
        blockers.extend(improvement.get("blockers") or [])

    return ClusterReviewFinalizeResult(
        review_sheet_path=sheet_path,
        batch_root=root,
        passed=bool(not blockers and materialized.passed),
        decision_report_path=decisions.report_path,
        constraints_path=materialized.constraints_path,
        reviewed_hints_path=materialized.reviewed_hints_path,
        overlay_path=overlay_path,
        brief_json_path=brief_json_path,
        improvement_json_path=improvement_json_path,
        improvement_markdown_path=improvement_markdown_path,
        approved_count=decisions.approved_count,
        rejected_count=decisions.rejected_count,
        pending_count=decisions.pending_count,
        constraints_count=materialized.constraints_count,
        hint_count=materialized.hint_count,
        review_pressure_reduction=review_pressure_reduction,
        routeable_named_span_gain=routeable_named_span_gain,
        blockers=list(dict.fromkeys(blockers)),
    )


def status_cluster_review(
    batch_root: Path | str,
    *,
    review_sheet_path: Path | str | None = None,
) -> ClusterReviewStatusResult:
    root = Path(batch_root)
    sheet_path = Path(review_sheet_path) if review_sheet_path else root / "pavo-cluster-question-bundle" / "pavo-cluster-question-review-sheet.json"
    if not sheet_path.exists():
        prepare_command = shlex.join(["pavo", "review", "clusters", "prepare", str(root)])
        return ClusterReviewStatusResult(
            batch_root=root,
            review_sheet_path=None,
            state="needs_prepare",
            candidate_count=0,
            approved_count=0,
            rejected_count=0,
            pending_count=0,
            cluster_count=0,
            ready_cluster_count=0,
            conflicted_cluster_count=0,
            unresolved_cluster_count=0,
            next_review_count=0,
            review_effort=_cluster_question_review_effort(pending_count=0, next_review_count=0),
            page_verified=False,
            top_cluster_id=None,
            estimated_unlockable_segments=None,
            estimated_unlockable_seconds=None,
            constraints_count=None,
            hint_count=None,
            acoustic_analyzed_count=None,
            acoustic_attention_cluster_count=None,
            acoustic_report_path=None,
            forecast_risk_adjusted_segments=None,
            forecast_report_path=None,
            materialized_artifact_dir=None,
            review_pressure_reduction=None,
            routeable_named_span_gain=None,
            next_review_plan=[],
            next_command=prepare_command,
            completion_commands={"prepare": prepare_command},
            blockers=["cluster question review sheet is missing"],
        )

    sheet = json.loads(sheet_path.read_text())
    rows = [row for row in sheet.get("rows") or [] if isinstance(row, dict)]
    approved = [row for row in rows if row.get("status") == "approved" and row.get("approved") is True]
    rejected = [row for row in rows if row.get("status") == "rejected"]
    pending = [row for row in rows if row.get("status") == "pending"]
    decision_rows = [_cluster_question_decision_row(row) for row in rows]
    consensus = _cluster_question_consensus_summaries(decision_rows)
    next_review_plan = _cluster_question_next_review_plan(decision_rows, consensus)
    review_effort = _cluster_question_review_effort(pending_count=len(pending), next_review_count=len(next_review_plan))
    ready_cluster_count = sum(1 for row in consensus if str(row.get("consensus_state") or "").startswith("ready_for_"))
    conflicted_cluster_count = sum(1 for row in consensus if row.get("consensus_state") == "conflicting_review")
    unresolved_cluster_count = sum(
        1
        for row in consensus
        if row.get("consensus_state") not in {"ready_for_must_link", "ready_for_cannot_link", "conflicting_review"}
    )
    page_path = sheet_path.with_name("index.html")
    page_verified = False
    if page_path.exists():
        try:
            page_verified = verify_anchor_review_page(sheet_path, page_path).passed
        except Exception:
            page_verified = False

    impact_path = sheet_path.with_name(sheet_path.stem.replace("-sheet", "-impact") + ".json")
    impact = _load_optional_json(impact_path)
    root_artifact_dir = root / "pavo-cluster-question-artifacts"
    bundle_artifact_dir = sheet_path.with_name("pavo-cluster-question-artifacts")
    constraints, constraints_path = _load_first_optional_json(
        [
            root_artifact_dir / "pavo-cluster-constraints.json",
            bundle_artifact_dir / "pavo-cluster-constraints.json",
        ]
    )
    hints, hints_path = _load_first_optional_json(
        [
            root_artifact_dir / "pavo-cluster-reviewed-hints.json",
            bundle_artifact_dir / "pavo-cluster-reviewed-hints.json",
        ]
    )
    improvement, improvement_path = _load_first_optional_json(
        [
            root_artifact_dir / "pavo-brief-improvement-report.json",
            bundle_artifact_dir / "pavo-brief-improvement-report.json",
        ]
    )
    materialized_artifact_dir = None
    for path in [constraints_path, hints_path, improvement_path]:
        if path is not None:
            materialized_artifact_dir = path.parent
            break
    acoustic_path = sheet_path.with_name("pavo-cluster-question-acoustic-evidence.json")
    acoustic = _load_optional_json(acoustic_path)
    next_review_plan = _attach_acoustic_evidence_to_next_review_plan(next_review_plan, acoustic)
    next_review_plan = _rank_next_review_plan_with_ensemble(next_review_plan)
    forecast_path = sheet_path.with_name("pavo-cluster-review-forecast.json")
    forecast = _load_optional_json(forecast_path)
    decision_report_path = sheet_path.with_name(sheet_path.stem.replace("-sheet", "-decisions") + ".json")
    slate_tsv_path = sheet_path.with_name("pavo-cluster-review-decision-slate.tsv")
    status_json_path = root / "pavo-cluster-review-status.json"
    status_markdown_path = root / "pavo-cluster-review-status.md"
    completion_commands = {
        "open_review_page": shlex.join(["open", str(page_path)]),
        "finish_from_slate": shlex.join(
            ["pavo", "review", "clusters", "finish-from-slate", str(root), str(sheet_path), str(slate_tsv_path)]
        ),
        "decisions": shlex.join(["pavo", "review", "clusters", "decisions", str(sheet_path), "--out", str(decision_report_path)]),
        "materialize_decisions": shlex.join(["pavo", "review", "clusters", "materialize-decisions", str(decision_report_path)]),
        "finalize": shlex.join(["pavo", "review", "clusters", "finalize", str(sheet_path), str(root)]),
        "refresh_status": shlex.join(
            [
                "pavo",
                "review",
                "clusters",
                "status",
                str(root),
                "--json",
                "--report",
                str(status_json_path),
                "--markdown-report",
                str(status_markdown_path),
            ]
        ),
    }

    blockers: list[str] = []
    if not page_verified:
        blockers.append("cluster review page is not verified")
    if conflicted_cluster_count:
        blockers.append(f"{conflicted_cluster_count} clusters have conflicting approved/rejected samples")
    if unresolved_cluster_count:
        blockers.append(f"{unresolved_cluster_count} cluster questions still need review before terminal consensus")

    constraints_count = constraints.get("constraint_count") if constraints else None
    hint_count = hints.get("hint_count") if hints else None
    deltas = improvement.get("deltas") if isinstance(improvement.get("deltas"), dict) else {}
    review_delta = deltas.get("review_pressure_reduction") if deltas else None
    routeable_delta = deltas.get("routeable_named_span_gain") if deltas else None

    if conflicted_cluster_count:
        state = "review_conflicted"
        next_command = completion_commands["open_review_page"]
    elif unresolved_cluster_count:
        state = "review_pending"
        next_command = completion_commands["open_review_page"]
    elif not rows:
        state = "needs_prepare"
        blockers.append("cluster review sheet has no rows")
        next_command = shlex.join(["pavo", "review", "clusters", "prepare", str(root)])
    elif not constraints.get("passed") or not improvement:
        state = "ready_to_finalize"
        next_command = completion_commands["finalize"]
    elif improvement.get("passed"):
        state = "finalized_passed"
        next_command = shlex.join(["pavo", "brief", str(root)])
    else:
        state = "finalized_attention"
        blockers.extend(improvement.get("blockers") or [])
        next_command = shlex.join(["pavo", "review", "clusters", "impact", str(sheet_path)])

    top_cluster = impact.get("top_cluster_id")
    if not top_cluster and rows:
        question = rows[0].get("cluster_question") if isinstance(rows[0].get("cluster_question"), dict) else {}
        top_cluster = question.get("cluster_id")

    return ClusterReviewStatusResult(
        batch_root=root,
        review_sheet_path=sheet_path,
        state=state,
        candidate_count=len(rows),
        approved_count=len(approved),
        rejected_count=len(rejected),
        pending_count=len(pending),
        cluster_count=len(consensus),
        ready_cluster_count=ready_cluster_count,
        conflicted_cluster_count=conflicted_cluster_count,
        unresolved_cluster_count=unresolved_cluster_count,
        next_review_count=len(next_review_plan),
        review_effort=review_effort,
        page_verified=page_verified,
        top_cluster_id=top_cluster,
        estimated_unlockable_segments=impact.get("estimated_unlockable_segments") if impact else None,
        estimated_unlockable_seconds=impact.get("estimated_unlockable_seconds") if impact else None,
        constraints_count=int(constraints_count) if constraints_count is not None else None,
        hint_count=int(hint_count) if hint_count is not None else None,
        acoustic_analyzed_count=int(acoustic.get("analyzed_count")) if acoustic and acoustic.get("analyzed_count") is not None else None,
        acoustic_attention_cluster_count=int(acoustic.get("attention_cluster_count")) if acoustic and acoustic.get("attention_cluster_count") is not None else None,
        acoustic_report_path=acoustic_path if acoustic else None,
        forecast_risk_adjusted_segments=int(forecast.get("risk_adjusted_segments")) if forecast and forecast.get("risk_adjusted_segments") is not None else None,
        forecast_report_path=forecast_path if forecast else None,
        materialized_artifact_dir=materialized_artifact_dir,
        review_pressure_reduction=int(review_delta) if review_delta is not None else None,
        routeable_named_span_gain=int(routeable_delta) if routeable_delta is not None else None,
        next_review_plan=next_review_plan,
        next_command=next_command,
        completion_commands=completion_commands,
        blockers=list(dict.fromkeys(blockers)),
    )


def doctor_cluster_review(
    batch_root: Path | str,
    *,
    review_sheet_path: Path | str | None = None,
) -> ClusterReviewDoctorResult:
    root = Path(batch_root)
    status = status_cluster_review(root, review_sheet_path=review_sheet_path)
    sheet_path = status.review_sheet_path
    bundle_dir = sheet_path.parent if sheet_path else root / "pavo-cluster-question-bundle"
    clip_count = len(list((bundle_dir / "clips").glob("*"))) if (bundle_dir / "clips").exists() else 0
    slate_tsv = bundle_dir / "pavo-cluster-review-decision-slate.tsv"
    slate_md = bundle_dir / "pavo-cluster-review-decision-slate.md"
    page_path = bundle_dir / "index.html"
    finish_command = status.completion_commands.get("finish_from_slate")
    checks = [
        _doctor_check(
            "review_sheet",
            bool(sheet_path and sheet_path.exists()),
            str(sheet_path) if sheet_path else "missing",
        ),
        _doctor_check("review_page_verified", status.page_verified, str(page_path)),
        _doctor_check("candidate_clips", status.candidate_count > 0, f"{status.candidate_count} candidate rows"),
        _doctor_check(
            "clip_files",
            clip_count >= status.candidate_count > 0,
            f"{clip_count} clip files for {status.candidate_count} candidates",
        ),
        _doctor_check(
            "acoustic_evidence",
            bool(status.acoustic_report_path and status.acoustic_analyzed_count == status.candidate_count),
            f"{status.acoustic_analyzed_count} analyzed; report={status.acoustic_report_path}",
        ),
        _doctor_check(
            "forecast",
            bool(status.forecast_report_path and status.forecast_risk_adjusted_segments is not None),
            f"risk_adjusted_segments={status.forecast_risk_adjusted_segments}; report={status.forecast_report_path}",
        ),
        _doctor_check("static_slate_tsv", slate_tsv.exists(), str(slate_tsv)),
        _doctor_check("static_slate_markdown", slate_md.exists(), str(slate_md)),
        _doctor_check("finish_from_slate_command", bool(finish_command), finish_command or "missing"),
    ]
    plumbing_passed = all(check["passed"] for check in checks)
    complete = status.state.startswith("finalized_") and not status.blockers
    blockers = [] if plumbing_passed else [f"{check['name']} failed" for check in checks if not check["passed"]]
    blockers.extend(status.blockers)
    return ClusterReviewDoctorResult(
        batch_root=root,
        review_sheet_path=sheet_path,
        passed=plumbing_passed,
        complete=complete,
        state=status.state,
        checks=checks,
        blockers=list(dict.fromkeys(blockers)),
        next_command=status.next_command,
        status=status,
    )


def export_cluster_review_slate(
    batch_root: Path | str,
    *,
    review_sheet_path: Path | str | None = None,
    out_dir: Path | str | None = None,
) -> ClusterReviewSlateResult:
    status = status_cluster_review(batch_root, review_sheet_path=review_sheet_path)
    target_dir = Path(out_dir) if out_dir else Path(batch_root) / "pavo-cluster-question-bundle"
    target_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = target_dir / "pavo-cluster-review-decision-slate.md"
    tsv_path = target_dir / "pavo-cluster-review-decision-slate.tsv"

    markdown_path.write_text(_render_cluster_review_slate_markdown(status), encoding="utf-8")
    tsv_path.write_text(_render_cluster_review_slate_tsv(status), encoding="utf-8")
    return ClusterReviewSlateResult(
        batch_root=Path(batch_root),
        review_sheet_path=status.review_sheet_path,
        markdown_path=markdown_path,
        tsv_path=tsv_path,
        item_count=len(status.next_review_plan),
        state=status.state,
        blockers=list(status.blockers),
    )


def export_cluster_review_decision_brief(
    batch_root: Path | str,
    *,
    review_sheet_path: Path | str | None = None,
    out_dir: Path | str | None = None,
) -> ClusterReviewDecisionBriefResult:
    status = status_cluster_review(batch_root, review_sheet_path=review_sheet_path)
    target_dir = Path(out_dir) if out_dir else Path(batch_root) / "pavo-cluster-question-bundle"
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "pavo-cluster-review-decision-brief.json"
    markdown_path = target_dir / "pavo-cluster-review-decision-brief.md"
    html_path = target_dir / "pavo-cluster-review-decision-brief.html"
    payload = _cluster_review_decision_brief_payload(status)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_cluster_review_decision_brief_markdown(payload), encoding="utf-8")
    html_path.write_text(_render_cluster_review_decision_brief_html(payload), encoding="utf-8")
    summary = payload["summary"]
    return ClusterReviewDecisionBriefResult(
        batch_root=Path(batch_root),
        review_sheet_path=status.review_sheet_path,
        json_path=json_path,
        markdown_path=markdown_path,
        html_path=html_path,
        item_count=int(summary["item_count"]),
        total_unlockable_segments=int(summary["total_unlockable_segments"]),
        total_unlockable_seconds=float(summary["total_unlockable_seconds"]),
        state=status.state,
        blockers=list(status.blockers),
    )


def import_cluster_review_slate(
    review_sheet_path: Path | str,
    slate_tsv_path: Path | str,
    *,
    out_path: Path | str | None = None,
) -> ClusterReviewSlateImportResult:
    sheet_path = Path(review_sheet_path)
    slate_path = Path(slate_tsv_path)
    sheet = json.loads(sheet_path.read_text())
    rows = sheet.get("rows") or []
    row_by_index = {str(row.get("index")): row for row in rows}
    slate_rows = _read_cluster_review_slate_tsv(slate_path)
    seen: set[str] = set()
    applied = 0

    for slate_row in slate_rows:
        row_index = str(slate_row.get("row_index") or "").strip()
        if not row_index:
            raise ValueError("slate row missing row_index")
        if row_index in seen:
            raise ValueError(f"duplicate slate row_index {row_index}")
        seen.add(row_index)
        original = row_by_index.get(row_index)
        if original is None:
            raise ValueError(f"slate row_index {row_index} does not exist in review sheet")
        question = original.get("cluster_question") if isinstance(original.get("cluster_question"), dict) else {}
        cluster_id = str(question.get("cluster_id") or original.get("case") or "")
        slate_cluster = str(slate_row.get("cluster_id") or "").strip()
        if slate_cluster and slate_cluster != cluster_id:
            raise ValueError(f"slate row_index {row_index} changed cluster_id from {cluster_id} to {slate_cluster}")

        decision = str(slate_row.get("decision") or "pending").strip().lower()
        if decision not in {"approved", "rejected", "pending"}:
            raise ValueError(f"slate row_index {row_index} has invalid decision {decision!r}")
        speaker = str(slate_row.get("speaker") or "").strip()
        note = str(slate_row.get("note") or "").strip()
        original["status"] = decision
        original["approved"] = decision == "approved"
        if note:
            original["reviewer_note"] = note
        if decision == "approved" and speaker:
            original["target_speaker_label"] = speaker
            original["target_speaker_name"] = speaker
            question["dominant_speaker"] = speaker
            question["candidate_name"] = speaker
            original["cluster_question"] = question
        applied += 1

    target_path = Path(out_path) if out_path else sheet_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(sheet, indent=2, sort_keys=True) + "\n")
    updated_rows = sheet.get("rows") or []
    approved = [row for row in updated_rows if row.get("status") == "approved" and row.get("approved") is True]
    rejected = [row for row in updated_rows if row.get("status") == "rejected"]
    pending = [row for row in updated_rows if row.get("status") not in {"approved", "rejected"}]
    return ClusterReviewSlateImportResult(
        review_sheet_path=sheet_path,
        slate_path=slate_path,
        imported_sheet_path=target_path,
        applied_count=applied,
        approved_count=len(approved),
        rejected_count=len(rejected),
        pending_count=len(pending),
    )


def finish_cluster_review_from_slate(
    batch_root: Path | str,
    review_sheet_path: Path | str,
    slate_tsv_path: Path | str,
    *,
    imported_sheet_path: Path | str | None = None,
    baseline_brief_path: Path | str | None = None,
    out_dir: Path | str | None = None,
) -> ClusterReviewFinishFromSlateResult:
    root = Path(batch_root)
    imported = import_cluster_review_slate(review_sheet_path, slate_tsv_path, out_path=imported_sheet_path)
    decisions = export_cluster_question_decisions(imported.imported_sheet_path)
    blockers = list(decisions.blockers)
    finalize_result = None
    if decisions.passed:
        finalize_result = finalize_cluster_review(
            imported.imported_sheet_path,
            root,
            baseline_brief_path=baseline_brief_path,
            out_dir=out_dir,
        )
        blockers.extend(finalize_result.blockers)
    else:
        blockers.append("decision gate did not pass; fill every required cluster decision before finalizing")
    blockers = list(dict.fromkeys(blockers))
    return ClusterReviewFinishFromSlateResult(
        batch_root=root,
        review_sheet_path=Path(review_sheet_path),
        slate_path=Path(slate_tsv_path),
        passed=bool(finalize_result and finalize_result.passed and not blockers),
        imported_sheet_path=imported.imported_sheet_path,
        decision_report_path=decisions.report_path,
        finalize_result=finalize_result,
        applied_count=imported.applied_count,
        approved_count=decisions.approved_count,
        rejected_count=decisions.rejected_count,
        pending_count=decisions.pending_count,
        blockers=blockers,
    )


def advance_cluster_review(
    batch_root: Path | str,
    *,
    review_sheet_path: Path | str | None = None,
) -> ClusterReviewAdvanceResult:
    root = Path(batch_root)
    before = status_cluster_review(root, review_sheet_path=review_sheet_path)
    action = "status_only"
    advanced = False
    blockers: list[str] = []

    if before.state == "needs_prepare":
        prepare_cluster_review(root)
        action = "prepared_review_queue"
        advanced = True
    elif before.state == "ready_to_finalize" and before.review_sheet_path is not None:
        finalized = finalize_cluster_review(before.review_sheet_path, root)
        action = "finalized_review"
        advanced = bool(finalized.passed)
        blockers.extend(finalized.blockers)
    elif before.state == "review_pending":
        action = "await_human_review"
        blockers.extend(before.blockers)
    elif before.state == "review_conflicted":
        action = "await_conflict_resolution"
        blockers.extend(before.blockers)
    elif before.state in {"finalized_passed", "finalized_attention"}:
        action = "already_finalized"
        blockers.extend(before.blockers)
    else:
        blockers.extend(before.blockers)

    after = status_cluster_review(root, review_sheet_path=review_sheet_path)
    if after.blockers and action not in {"await_human_review", "await_conflict_resolution"}:
        blockers.extend(after.blockers)
    return ClusterReviewAdvanceResult(
        batch_root=root,
        before_state=before.state,
        after_state=after.state,
        action=action,
        advanced=advanced,
        status=after,
        blockers=list(dict.fromkeys(blockers)),
    )


def _load_baseline_brief(root: Path, baseline_brief_path: Path | str | None) -> dict[str, Any]:
    if baseline_brief_path:
        return json.loads(Path(baseline_brief_path).read_text())
    existing = root / "pavo-meeting-brief.json"
    if existing.exists():
        payload = _load_optional_json(existing)
        if payload:
            return payload
    return build_meeting_brief(root)


def create_anchor_review_page(
    review_sheet_path: Path | str,
    *,
    out_path: Path | str | None = None,
) -> AnchorReviewPageResult:
    sheet_path = Path(review_sheet_path)
    sheet = json.loads(sheet_path.read_text())
    page_path = Path(out_path) if out_path else sheet_path.with_suffix(".html")
    acoustic_rows = _load_acoustic_review_rows(sheet_path)
    rows = [_with_acoustic_review(row, acoustic_rows) for row in sheet.get("rows", [])]
    sheet = {**sheet, "rows": rows}
    pending = [row for row in rows if row.get("status") == "pending"]
    labels = _review_labels(sheet)
    display_mode = sheet.get("display_mode") or "anchor_review"
    cards = "\n".join(_review_card(row, labels=labels, display_mode=display_mode) for row in rows)
    sheet_json = json.dumps(sheet).replace("</", "<\\/")
    download_name_json = json.dumps(sheet_path.name)
    slate_download_name_json = json.dumps(sheet_path.with_name("pavo-cluster-review-decision-slate.tsv").name)
    draft_key_json = json.dumps(f"pavo-review-draft:{sheet_path.resolve()}:{len(rows)}")
    title = sheet.get("review_title") or f"Pavo Anchor Review - {sheet.get('target_speaker_name') or sheet.get('target_speaker_label') or 'Speaker'}"
    instructions = _review_instructions(sheet, sheet_path)
    export_label = sheet.get("export_label") or "Export reviewed JSON"
    reset_label = sheet.get("reset_label") or "Reset page decisions"
    status_labels_json = json.dumps(labels["status"])
    cluster_batch_root = sheet_path.parent.parent if sheet_path.parent.name == "pavo-cluster-question-bundle" else sheet_path.parent
    decision_report_path = sheet_path.with_name(sheet_path.stem.replace("-sheet", "-decisions") + ".json")
    cluster_decision_command_json = json.dumps(
        f"pavo review clusters decisions {shlex.quote(str(sheet_path))} --out {shlex.quote(str(decision_report_path))}"
    )
    cluster_finalize_command_json = json.dumps(
        f"pavo review clusters finalize {shlex.quote(str(sheet_path))} {shlex.quote(str(cluster_batch_root))}"
    )
    cluster_finish_from_slate_command_json = json.dumps(
        "pavo review clusters finish-from-slate "
        f"{shlex.quote(str(cluster_batch_root))} "
        f"{shlex.quote(str(sheet_path))} "
        f"{shlex.quote(str(sheet_path.with_name('pavo-cluster-review-decision-slate.tsv')))}"
    )
    cluster_status_command_json = json.dumps(
        "pavo review clusters status "
        f"{shlex.quote(str(cluster_batch_root))} --json "
        f"--report {shlex.quote(str(cluster_batch_root / 'pavo-cluster-review-status.json'))} "
        f"--markdown-report {shlex.quote(str(cluster_batch_root / 'pavo-cluster-review-status.md'))}"
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #17211c;
      background: #f7faf4;
    }}
    header {{
      padding: 28px 32px;
      background: #0d3b2e;
      color: #f9fff7;
    }}
    main {{
      max-width: 1040px;
      margin: 0 auto;
      padding: 24px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      letter-spacing: 0;
    }}
    .meta {{
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      color: #d7f5dd;
    }}
    .instructions {{
      margin: 0 0 18px;
      padding: 16px;
      border: 1px solid #bfd7c5;
      background: #ffffff;
    }}
    .assistant-review {{
      margin: 12px 0;
      padding: 12px;
      border-left: 4px solid #3f8f64;
      background: #edf8ef;
    }}
    .assistant-review span {{
      display: inline-block;
      margin-left: 8px;
      color: #315044;
      font-weight: 700;
    }}
    .assistant-review p {{
      margin: 6px 0 0;
    }}
    .assistant-review .context {{
      color: #496458;
      font-size: 13px;
    }}
    .acoustic-review {{
      margin: 12px 0;
      padding: 12px;
      border-left: 4px solid #d2b35f;
      background: #fff8df;
    }}
    .acoustic-review strong {{
      color: #5c4300;
    }}
    .acoustic-review span {{
      display: inline-block;
      margin-left: 8px;
      color: #5c4300;
      font-weight: 700;
    }}
    .acoustic-review p {{
      margin: 6px 0 0;
      color: #544a2d;
    }}
    .acoustic-review.acoustic-drift {{
      border-left-color: #b86b5f;
      background: #fff0ea;
    }}
    .acoustic-review.acoustic-consistent {{
      border-left-color: #4c9560;
      background: #edf8ef;
    }}
    .actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      margin: 18px 0;
    }}
    .shortcut-panel {{
      margin: 0 0 18px;
      padding: 12px 16px;
      border: 1px solid #d9e5db;
      background: #fbfdf9;
      color: #315044;
    }}
    .shortcut-panel strong {{
      color: #17211c;
    }}
    .shortcut-panel code {{
      margin: 0 4px;
      font-weight: 700;
    }}
    .cluster-summary {{
      display: grid;
      gap: 8px;
      margin: 0 0 18px;
      padding: 12px 16px;
      border: 1px solid #c7d9cc;
      background: #ffffff;
    }}
    .cluster-summary h2 {{
      margin: 0;
      font-size: 16px;
    }}
    .cluster-summary-row {{
      display: grid;
      gap: 4px;
      padding: 8px 10px;
      border-radius: 6px;
      background: #f4f9f2;
    }}
    .cluster-summary-row strong {{
      color: #17211c;
    }}
    .cluster-summary-row.ready {{
      background: #edf8ef;
      border-left: 4px solid #4c9560;
    }}
    .cluster-summary-row.conflict {{
      background: #fff0ea;
      border-left: 4px solid #b86b5f;
    }}
    .cluster-summary-row.pending {{
      background: #fff8df;
      border-left: 4px solid #d2b35f;
    }}
    .cluster-summary-row span {{
      color: #4f665b;
      font-size: 14px;
    }}
    .next-review-plan {{
      display: grid;
      gap: 8px;
      margin: 0 0 18px;
      padding: 12px 16px;
      border: 1px solid #c7d9cc;
      background: #ffffff;
    }}
    .next-review-plan h2 {{
      margin: 0;
      font-size: 16px;
    }}
    .next-review-row {{
      display: grid;
      gap: 4px;
      padding: 8px 10px;
      border-radius: 6px;
      border-left: 4px solid #174835;
      background: #edf8ef;
    }}
    .next-review-row strong {{
      color: #17211c;
    }}
    .next-review-row span {{
      color: #4f665b;
      font-size: 14px;
    }}
    .review-effort {{
      margin: 0 0 18px;
      padding: 12px 16px;
      border: 1px solid #c7d9cc;
      background: #f4f9f2;
      color: #315044;
      font-weight: 700;
    }}
    .completion-handoff {{
      display: grid;
      gap: 10px;
      margin: 0 0 18px;
      padding: 12px 16px;
      border: 1px solid #c7d9cc;
      background: #ffffff;
      color: #315044;
    }}
    .completion-handoff.ready {{
      border-left: 4px solid #4c9560;
      background: #edf8ef;
    }}
    .completion-handoff.blocked {{
      border-left: 4px solid #d2b35f;
      background: #fff8df;
    }}
    .completion-handoff h2 {{
      margin: 0;
      font-size: 16px;
      color: #17211c;
    }}
    .completion-handoff ol {{
      margin: 0;
      padding-left: 20px;
    }}
    .completion-handoff pre {{
      margin: 6px 0 10px;
      padding: 10px;
      overflow-x: auto;
      border-radius: 6px;
      background: #10251b;
      color: #f9fff7;
      white-space: pre-wrap;
    }}
    .save-status {{
      color: #315044;
      font-weight: 700;
    }}
    button {{
      border: 1px solid #174835;
      border-radius: 6px;
      background: #174835;
      color: #ffffff;
      padding: 8px 12px;
      font: inherit;
      cursor: pointer;
    }}
    button.secondary {{
      background: #ffffff;
      color: #174835;
    }}
    button:focus-visible,
    textarea:focus-visible {{
      outline: 3px solid #8ed39a;
      outline-offset: 2px;
    }}
    article {{
      margin: 16px 0;
      padding: 18px;
      border: 1px solid #cfdfd1;
      border-radius: 8px;
      background: #ffffff;
    }}
    article:focus {{
      outline: 3px solid #8ed39a;
      outline-offset: 2px;
    }}
    .row-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: baseline;
      margin-bottom: 10px;
    }}
    h2 {{
      margin: 0;
      font-size: 18px;
      letter-spacing: 0;
    }}
    code {{
      background: #eef4ee;
      padding: 2px 5px;
      border-radius: 4px;
    }}
    audio {{
      width: 100%;
      margin: 10px 0;
    }}
    dl {{
      display: grid;
      grid-template-columns: 160px 1fr;
      gap: 8px 12px;
      margin: 12px 0 0;
    }}
    dt {{
      font-weight: 700;
      color: #315044;
    }}
    dd {{
      margin: 0;
      overflow-wrap: anywhere;
    }}
    .status {{
      font-weight: 700;
      color: #7a4e00;
    }}
    .review-controls {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin: 12px 0;
    }}
    .review-controls button.active {{
      background: #8ed39a;
      border-color: #174835;
      color: #10251b;
      font-weight: 700;
    }}
    .voice-review {{
      display: grid;
      gap: 8px;
      margin: 12px 0 6px;
      padding: 10px;
      border: 1px solid #d9e5db;
      border-radius: 6px;
      background: #fbfdf9;
    }}
    .voice-review-actions {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .voice-review button.active {{
      background: #b86b5f;
      border-color: #8d3f35;
    }}
    .voice-waveform {{
      display: grid;
      align-items: center;
      height: 54px;
      overflow: hidden;
      border: 1px solid #c7d9cc;
      border-radius: 999px;
      background: #10251b;
      padding: 0 14px;
    }}
    .voice-waveform canvas {{
      display: block;
      width: 100%;
      height: 38px;
    }}
    .voice-review.recording .voice-waveform {{
      border-color: #8ed39a;
      box-shadow: 0 0 0 3px rgba(142, 211, 154, 0.25);
    }}
    .voice-status,
    .parsed-review {{
      color: #4f665b;
      font-size: 14px;
      line-height: 1.4;
    }}
    article.review-approved {{
      border-color: #4c9560;
      box-shadow: inset 4px 0 0 #4c9560;
    }}
    article.review-rejected {{
      border-color: #b86b5f;
      box-shadow: inset 4px 0 0 #b86b5f;
    }}
    article.review-pending {{
      box-shadow: inset 4px 0 0 #d2b35f;
    }}
    .review-prompt {{
      margin: 8px 0 10px;
      font-size: 17px;
      line-height: 1.45;
    }}
    .clip-subtitle {{
      margin: 4px 0 0;
      color: #4f665b;
    }}
    details {{
      margin-top: 12px;
    }}
    summary {{
      cursor: pointer;
      color: #315044;
      font-weight: 700;
    }}
    textarea {{
      width: 100%;
      box-sizing: border-box;
      min-height: 70px;
      margin-top: 8px;
      padding: 8px;
      border: 1px solid #bfd7c5;
      border-radius: 6px;
      font: inherit;
    }}
    @media (max-width: 700px) {{
      header {{ padding: 22px 18px; }}
      main {{ padding: 16px; }}
      dl {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(title)}</h1>
    <div class="meta">
      <span>{len(rows)} candidate clips</span>
      <span>{len(pending)} pending</span>
      <span>sheet: {escape(str(sheet_path))}</span>
    </div>
  </header>
  <main>
    {instructions}
    <section class="shortcut-panel" id="shortcut-panel">
      <strong>Keyboard shortcuts:</strong>
      <code>A</code> approve/supports decision,
      <code>R</code> reject/contradicts decision,
      <code>U</code> uncertain,
      <code>J</code>/<code>K</code> next/previous clip,
      <code>N</code> next recommended review,
      <code>Space</code> play/pause,
      <code>&larr;</code>/<code>&rarr;</code> seek 2s,
      <code>0</code> restart clip,
      <code>/</code> note,
      <code>S</code> save/export.
    </section>
    <section class="cluster-summary" id="cluster-summary" aria-live="polite">
      <h2>Cluster consensus</h2>
      <div id="cluster-summary-rows">Loading cluster consensus...</div>
    </section>
    <section class="next-review-plan" id="next-review-plan" aria-live="polite">
      <h2>Minimal next reviews</h2>
      <div id="next-review-plan-rows">Loading next review queue...</div>
    </section>
    <section class="review-effort" id="review-effort" aria-live="polite">
      Calculating review effort...
    </section>
    <section class="completion-handoff" id="completion-handoff" aria-live="polite">
      <h2>Completion handoff</h2>
      <div id="completion-handoff-body">Waiting for cluster consensus...</div>
    </section>
    <section class="actions">
      <button type="button" id="save-review">Save review</button>
      <button type="button" id="export-json">{escape(str(export_label))}</button>
      <button type="button" id="export-slate-tsv">Export slate TSV</button>
      <button type="button" class="secondary" id="reset-review">{escape(str(reset_label))}</button>
      <span id="review-count">{len(pending)} pending</span>
      <span class="save-status" id="save-status">Checking save backend...</span>
    </section>
    {cards}
  </main>
  <script type="application/json" id="review-sheet-data">{sheet_json}</script>
  <script>
    let originalSheet = JSON.parse(document.getElementById("review-sheet-data").textContent);
    const statusLabels = {status_labels_json};
    const decisions = new Map();
    let backendAvailable = false;
    let dirty = false;
    let saveTimer = null;
    let activeRecording = null;
    const reviewDraftKey = {draft_key_json};
    const clusterDecisionCommand = {cluster_decision_command_json};
    const clusterFinalizeCommand = {cluster_finalize_command_json};
    const clusterFinishFromSlateCommand = {cluster_finish_from_slate_command_json};
    const clusterStatusCommand = {cluster_status_command_json};

    function initializeDecisionsFromSheet(sheet) {{
      originalSheet = sheet;
      decisions.clear();
      originalSheet.rows.forEach((row) => decisions.set(String(row.index), {{
        status: row.status || "pending",
        approved: row.approved === true,
        reviewer_note: row.reviewer_note || "",
        reviewer_note_transcript: row.reviewer_note_transcript || "",
        reviewer_note_audio_path: row.reviewer_note_audio_path || "",
        review_parse: row.review_parse || {{}}
      }}));
    }}

    function setDecision(index, status) {{
      const key = String(index);
      const current = decisions.get(key) || {{}};
      current.status = status;
      current.approved = status === "approved";
      decisions.set(key, current);
      const card = document.querySelector(`[data-review-index="${{key}}"]`);
      if (card) {{
        applyDecisionToCard(card, status);
      }}
      updateCount();
      markDirty();
    }}

    function setNote(index, note) {{
      const key = String(index);
      const current = decisions.get(key) || {{}};
      current.reviewer_note = note;
      decisions.set(key, current);
      markDirty();
    }}

    function setDecisionField(index, field, value) {{
      const key = String(index);
      const current = decisions.get(key) || {{}};
      current[field] = value;
      decisions.set(key, current);
      markDirty();
    }}

    function noteTextFor(index) {{
      const note = document.querySelector(`[data-note="${{index}}"]`);
      return note ? note.value : "";
    }}

    async function parseNote(index) {{
      const text = noteTextFor(index);
      if (!text.trim()) {{
        setCardMessage(index, "Add or record a plain-English note first.");
        return;
      }}
      if (!backendAvailable) {{
        setCardMessage(index, "Serve this bundle with Pavo to parse notes.");
        return;
      }}
      const response = await fetch("/api/review-note", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ row_index: index, text }})
      }});
      const payload = await response.json();
      if (!response.ok || payload.parsed !== true) {{
        throw new Error(payload.error || `Parse failed with HTTP ${{response.status}}`);
      }}
      applyParsedReview(index, payload.review_parse);
    }}

    function applyParsedReview(index, reviewParse) {{
      const key = String(index);
      const current = decisions.get(key) || {{}};
      current.review_parse = reviewParse || {{}};
      if (reviewParse && ["approved", "rejected", "pending"].includes(reviewParse.decision)) {{
        current.status = reviewParse.decision;
        current.approved = reviewParse.decision === "approved";
      }}
      decisions.set(key, current);
      const card = document.querySelector(`[data-review-index="${{key}}"]`);
      if (card) {{
        applyDecisionToCard(card, current.status || "pending");
        renderParsedReview(card, current.review_parse);
      }}
      updateCount();
      markDirty();
    }}

    function renderParsedReview(card, reviewParse) {{
      const target = card.querySelector("[data-parsed-review]");
      if (!target) return;
      if (!reviewParse || Object.keys(reviewParse).length === 0) {{
        target.textContent = "No parsed note yet.";
        return;
      }}
      const parts = [
        `Decision: ${{reviewParse.decision || "pending"}}`,
        `Speakers: ${{(reviewParse.heard_speakers || []).join(", ") || "unknown"}}`,
        `Overlap: ${{reviewParse.overlap === true ? "yes" : reviewParse.overlap === false ? "no" : "unknown"}}`,
        `Issues: ${{(reviewParse.issues || []).join(", ") || "none"}}`
      ];
      if (reviewParse.suggested_fix) parts.push(`Fix: ${{reviewParse.suggested_fix}}`);
      target.textContent = parts.join(" | ");
    }}

    function setCardMessage(index, message) {{
      const card = document.querySelector(`[data-review-index="${{index}}"]`);
      const target = card ? card.querySelector("[data-voice-status]") : null;
      if (target) target.textContent = message;
    }}

    function setVoiceRecordingState(index, isRecording) {{
      const card = document.querySelector(`[data-review-index="${{index}}"]`);
      const panel = card ? card.querySelector(".voice-review") : null;
      if (panel) panel.classList.toggle("recording", isRecording);
    }}

    function drawIdleWaveform(canvas) {{
      if (!canvas) return;
      const context = canvas.getContext("2d");
      const width = canvas.width = canvas.offsetWidth || 600;
      const height = canvas.height = canvas.offsetHeight || 38;
      context.clearRect(0, 0, width, height);
      const barCount = 42;
      const gap = 3;
      const barWidth = Math.max(2, (width - gap * (barCount - 1)) / barCount);
      for (let index = 0; index < barCount; index += 1) {{
        const phase = index / barCount;
        const amplitude = 0.18 + Math.abs(Math.sin(phase * Math.PI * 3)) * 0.28;
        const barHeight = Math.max(4, amplitude * height);
        const x = index * (barWidth + gap);
        const y = (height - barHeight) / 2;
        context.fillStyle = "rgba(215, 245, 221, 0.58)";
        context.fillRect(x, y, barWidth, barHeight);
      }}
    }}

    function startWaveform(index, stream) {{
      const card = document.querySelector(`[data-review-index="${{index}}"]`);
      const canvas = card ? card.querySelector("[data-waveform]") : null;
      if (!canvas || !window.AudioContext && !window.webkitAudioContext) {{
        return {{}};
      }}
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      const audioContext = new AudioContextClass();
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 128;
      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const context = canvas.getContext("2d");
      const draw = () => {{
        const width = canvas.width = canvas.offsetWidth || 600;
        const height = canvas.height = canvas.offsetHeight || 38;
        analyser.getByteFrequencyData(data);
        context.clearRect(0, 0, width, height);
        const barCount = Math.min(48, data.length);
        const gap = 3;
        const barWidth = Math.max(2, (width - gap * (barCount - 1)) / barCount);
        for (let index = 0; index < barCount; index += 1) {{
          const value = data[index] / 255;
          const eased = Math.max(0.08, value * 0.95);
          const barHeight = Math.max(4, eased * height);
          const x = index * (barWidth + gap);
          const y = (height - barHeight) / 2;
          const green = 150 + Math.round(value * 85);
          context.fillStyle = `rgb(142, ${{green}}, 154)`;
          context.fillRect(x, y, barWidth, barHeight);
        }}
        activeRecording.waveformFrame = requestAnimationFrame(draw);
      }};
      draw();
      return {{ audioContext, canvas }};
    }}

    function stopWaveform(recording) {{
      if (!recording) return;
      if (recording.waveformFrame) cancelAnimationFrame(recording.waveformFrame);
      if (recording.audioContext) {{
        try {{ recording.audioContext.close(); }} catch (error) {{}}
      }}
      drawIdleWaveform(recording.canvas);
      setVoiceRecordingState(recording.index, false);
    }}

    function buildReviewedSheet() {{
      const rows = originalSheet.rows.map((row) => {{
        const decision = decisions.get(String(row.index)) || {{}};
        return {{
          ...row,
          status: decision.status || "pending",
          approved: decision.approved === true,
          reviewer_note: decision.reviewer_note || "",
          reviewer_note_transcript: decision.reviewer_note_transcript || "",
          reviewer_note_audio_path: decision.reviewer_note_audio_path || "",
          review_parse: decision.review_parse || {{}}
        }};
      }});
      const approvedCount = rows.filter((row) => row.status === "approved" && row.approved === true).length;
      const rejectedCount = rows.filter((row) => row.status === "rejected").length;
      const pendingCount = rows.filter((row) => row.status === "pending").length;
      return {{
        ...originalSheet,
        passed: rows.length > 0 && approvedCount > 0 && pendingCount === 0,
        human_reviewed: rows.length > 0 && pendingCount === 0,
        approved_count: approvedCount,
        rejected_count: rejectedCount,
        pending_count: pendingCount,
        rows
      }};
    }}

    function escapeHtml(value) {{
      return String(value == null ? "" : value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }}

    function clusterConsensusState(cluster) {{
      if (cluster.approvedRows > 0 && cluster.rejectedRows > 0) return ["conflicting_review", "conflict", "Do not materialize; re-listen or add samples."];
      if (cluster.rejectedRows > 0) return ["ready_for_cannot_link", "ready", "Ready to reject this proposed speaker after export/import."];
      const quorum = Math.min(2, Math.max(1, cluster.totalRows));
      if (cluster.approvedRows >= quorum) return ["ready_for_must_link", "ready", "Ready to confirm this cluster after export/import."];
      if (cluster.approvedRows > 0) return ["pending_review", "pending", `Need ${{quorum - cluster.approvedRows}} more supporting sample(s), or one contradiction to early-stop.`];
      if (cluster.pendingRows > 0) return ["pending_review", "pending", "Review one representative sample. A contradiction can early-stop; confirmation needs quorum."];
      return ["unresolved_no_decision", "pending", "Review at least one sample."];
    }}

    function renderClusterSummary() {{
      const target = document.getElementById("cluster-summary-rows");
      if (!target) return;
      const clusters = new Map();
      buildReviewedSheet().rows.forEach((row) => {{
        const question = row.cluster_question || {{}};
        const clusterId = String(question.cluster_id || row.case || "unknown");
        const cluster = clusters.get(clusterId) || {{
          clusterId,
          targetSpeaker: question.dominant_speaker || row.target_speaker_label || question.candidate_name || "unknown",
          question: question.question || "",
          expectedImpact: question.expected_impact || "",
          approvedRows: 0,
          rejectedRows: 0,
          pendingRows: 0,
          totalRows: 0
        }};
        cluster.totalRows += 1;
        if (row.status === "approved" && row.approved === true) {{
          cluster.approvedRows += 1;
        }} else if (row.status === "rejected") {{
          cluster.rejectedRows += 1;
        }} else {{
          cluster.pendingRows += 1;
        }}
        clusters.set(clusterId, cluster);
      }});
      if (!clusters.size) {{
        target.textContent = "No cluster questions in this review sheet.";
        return;
      }}
      target.innerHTML = Array.from(clusters.values()).map((cluster) => {{
        const [state, css, action] = clusterConsensusState(cluster);
        const question = cluster.question ? `<span>${{escapeHtml(cluster.question)}}</span>` : "";
        const impact = cluster.expectedImpact ? ` • ${{escapeHtml(cluster.expectedImpact)}}` : "";
        return `<div class="cluster-summary-row ${{css}}">
          <strong>${{escapeHtml(cluster.clusterId)}} - ${{escapeHtml(cluster.targetSpeaker)}}: ${{state}}</strong>
          <span>${{cluster.approvedRows}} approved / ${{cluster.rejectedRows}} rejected / ${{cluster.pendingRows}} pending / ${{cluster.totalRows}} total${{impact}}</span>
          ${{question}}
          <span>${{escapeHtml(action)}}</span>
        </div>`;
      }}).join("");
    }}

    function minimalNextReviewPlan() {{
      const clusters = new Map();
      buildReviewedSheet().rows.forEach((row) => {{
        const question = row.cluster_question || {{}};
        const clusterId = String(question.cluster_id || row.case || "unknown");
        const cluster = clusters.get(clusterId) || {{
          clusterId,
          targetSpeaker: question.dominant_speaker || row.target_speaker_label || question.candidate_name || "unknown",
          question: question.question || "",
          expectedImpact: question.expected_impact || "",
          approvedRows: 0,
          rejectedRows: 0,
          pendingRows: 0,
          totalRows: 0,
          pending: []
        }};
        cluster.totalRows += 1;
        if (row.status === "approved" && row.approved === true) {{
          cluster.approvedRows += 1;
        }} else if (row.status === "rejected") {{
          cluster.rejectedRows += 1;
        }} else {{
          cluster.pendingRows += 1;
          cluster.pending.push(row);
        }}
        clusters.set(clusterId, cluster);
      }});
      const plan = [];
      clusters.forEach((cluster) => {{
        const [state] = clusterConsensusState(cluster);
        if (["ready_for_must_link", "ready_for_cannot_link", "conflicting_review"].includes(state)) return;
        if (!cluster.pending.length) return;
        cluster.pending.sort((left, right) => {{
          const scoreDelta = Number(right.impact_score || 0) - Number(left.impact_score || 0);
          if (scoreDelta !== 0) return scoreDelta;
          return Number(left.impact_rank || left.index || 0) - Number(right.impact_rank || right.index || 0);
        }});
        const row = cluster.pending[0];
        const quorum = Math.min(2, Math.max(1, cluster.totalRows));
        const approvalsNeeded = Math.max(0, quorum - cluster.approvedRows);
        const closureRule = cluster.approvedRows
          ? `Approve ${{approvalsNeeded}} more matching sample(s), or reject this sample to early-stop.`
          : "Reject to early-stop as cannot-link; approve only if the voice supports the proposed speaker.";
        const approveEffect = approvalsNeeded <= 1
          ? "Approve: reaches must-link quorum for this cluster."
          : `Approve: adds support; ${{approvalsNeeded - 1}} more matching sample(s) still needed.`;
        const rejectEffect = "Reject: early-stops this cluster as cannot-link and prevents unsafe identity propagation.";
        const terminalDecisionRule = "One contradiction is enough for cannot-link; confirmation requires approval quorum.";
        const questionText = String(cluster.question || "").toLowerCase();
        let riskPoints = 0;
        const priorityReasons = [];
        if (questionText.includes(" or ") || questionText.includes("what speaker")) {{
          riskPoints += 15;
          priorityReasons.push("ambiguous speaker question");
        }}
        const impactScore = Number(row.impact_score || 0);
        const reviewPriorityScore = Math.round(impactScore * (1 + riskPoints / 100) * 10) / 10;
        const reviewPriorityTier = riskPoints >= 25 ? "careful_listen" : riskPoints >= 10 ? "normal_listen" : "straightforward";
        const reviewPriorityReason = `${{priorityReasons.length ? priorityReasons.join(", ") : "impact-ranked representative sample"}}; impact score ${{impactScore}}; risk boost ${{riskPoints}}%.`;
        plan.push({{
          clusterId: cluster.clusterId,
          targetSpeaker: cluster.targetSpeaker,
          rowIndex: row.index,
          impactRank: row.impact_rank || row.index,
          impactScore,
          expectedImpact: cluster.expectedImpact,
          text: row.text || "",
          question: cluster.question,
          closureRule,
          approveEffect,
          rejectEffect,
          terminalDecisionRule,
          reviewPriorityScore,
          reviewPriorityTier,
          reviewPriorityReason
        }});
      }});
      return plan.sort((left, right) => {{
        const scoreDelta = Number(right.reviewPriorityScore || right.impactScore || 0) - Number(left.reviewPriorityScore || left.impactScore || 0);
        if (scoreDelta !== 0) return scoreDelta;
        return Number(left.impactRank || left.rowIndex || 0) - Number(right.impactRank || right.rowIndex || 0);
      }});
    }}

    function renderNextReviewPlan() {{
      const target = document.getElementById("next-review-plan-rows");
      if (!target) return;
      const plan = minimalNextReviewPlan();
      if (!plan.length) {{
        target.textContent = "No minimal reviews remain. Export/import decisions, then finalize.";
        return;
      }}
      target.innerHTML = plan.map((item) => {{
        const text = item.text ? `<span>${{escapeHtml(item.text.slice(0, 180))}}</span>` : "";
        const impact = item.expectedImpact ? ` • ${{escapeHtml(item.expectedImpact)}}` : "";
        return `<div class="next-review-row" data-next-review-target="${{escapeHtml(item.rowIndex)}}">
          <strong>${{escapeHtml(item.clusterId)}} row ${{escapeHtml(item.rowIndex)}} - ${{escapeHtml(item.targetSpeaker)}}${{impact}}</strong>
          <span>${{escapeHtml(item.closureRule)}}</span>
          <span>${{escapeHtml(item.approveEffect)}}</span>
          <span>${{escapeHtml(item.rejectEffect)}}</span>
          <span>${{escapeHtml(item.terminalDecisionRule)}}</span>
          <span>Priority: ${{escapeHtml(item.reviewPriorityTier)}} / ${{escapeHtml(item.reviewPriorityScore)}} - ${{escapeHtml(item.reviewPriorityReason)}}</span>
          ${{text}}
        </div>`;
      }}).join("");
    }}

    function renderReviewEffort() {{
      const target = document.getElementById("review-effort");
      if (!target) return;
      const reviewed = buildReviewedSheet();
      const plan = minimalNextReviewPlan();
      const pending = Number(reviewed.pending_count || 0);
      const minimum = Number(plan.length || 0);
      const saved = Math.max(0, pending - minimum);
      const reduction = pending ? ((saved / pending) * 100).toFixed(1) : "0.0";
      target.textContent = `Review effort: ${{minimum}} minimum reviews vs ${{pending}} pending clips; up to ${{saved}} clips can be skipped by terminal cluster consensus (${{reduction}}% reduction).`;
    }}

    function clusterConsensusSnapshot() {{
      const clusters = new Map();
      buildReviewedSheet().rows.forEach((row) => {{
        const question = row.cluster_question || {{}};
        const clusterId = String(question.cluster_id || row.case || "unknown");
        const cluster = clusters.get(clusterId) || {{
          clusterId,
          approvedRows: 0,
          rejectedRows: 0,
          pendingRows: 0,
          totalRows: 0
        }};
        cluster.totalRows += 1;
        if (row.status === "approved" && row.approved === true) {{
          cluster.approvedRows += 1;
        }} else if (row.status === "rejected") {{
          cluster.rejectedRows += 1;
        }} else {{
          cluster.pendingRows += 1;
        }}
        clusters.set(clusterId, cluster);
      }});
      const items = Array.from(clusters.values()).map((cluster) => {{
        const [state] = clusterConsensusState(cluster);
        return {{ ...cluster, state }};
      }});
      return {{
        clusters: items,
        ready: items.filter((cluster) => ["ready_for_must_link", "ready_for_cannot_link"].includes(cluster.state)).length,
        conflict: items.filter((cluster) => cluster.state === "conflicting_review").length,
        unresolved: items.filter((cluster) => !["ready_for_must_link", "ready_for_cannot_link", "conflicting_review"].includes(cluster.state)).length
      }};
    }}

    function renderCompletionHandoff() {{
      const panel = document.getElementById("completion-handoff");
      const body = document.getElementById("completion-handoff-body");
      if (!panel || !body) return;
      const plan = minimalNextReviewPlan();
      const snapshot = clusterConsensusSnapshot();
      panel.classList.toggle("ready", snapshot.unresolved === 0 && snapshot.conflict === 0);
      panel.classList.toggle("blocked", snapshot.unresolved > 0 || snapshot.conflict > 0);
      if (snapshot.conflict > 0) {{
        body.innerHTML = `<p><strong>${{snapshot.conflict}} cluster(s) conflict.</strong> Re-listen, add samples, or reject the contradicted cluster before materializing constraints.</p>`;
        return;
      }}
      if (plan.length > 0) {{
        body.innerHTML = `<p><strong>${{plan.length}} minimal review(s) remain.</strong> Press <code>N</code> to jump to the next highest-impact clip. When this count reaches zero, Pavo will show the finish commands here.</p>`;
        return;
      }}
      body.innerHTML = `
        <p><strong>Cluster consensus is ready.</strong> Export the slate TSV, then run the one-command finish gate:</p>
        <ol>
          <li>Export the filled TSV with <strong>Export slate TSV</strong>.</li>
          <li>Finish from slate:<pre>${{escapeHtml(clusterFinishFromSlateCommand)}}</pre></li>
          <li>Refresh the status proof:<pre>${{escapeHtml(clusterStatusCommand)}}</pre></li>
        </ol>
        <p>Fallback commands remain available if you need to debug: <code>${{escapeHtml(clusterDecisionCommand)}}</code> then <code>${{escapeHtml(clusterFinalizeCommand)}}</code>.</p>
      `;
    }}

    function focusNextRecommendedReview() {{
      const plan = minimalNextReviewPlan();
      if (!plan.length) return;
      const card = document.querySelector(`[data-review-index="${{plan[0].rowIndex}}"]`);
      focusReviewCard(card);
    }}

    function setSaveStatus(message) {{
      document.getElementById("save-status").textContent = message;
    }}

    function markDirty() {{
      dirty = true;
      persistReviewDraft();
      setSaveStatus(backendAvailable ? "Unsaved changes" : "File mode: export review notes");
      if (backendAvailable) {{
        clearTimeout(saveTimer);
        saveTimer = setTimeout(() => saveReview(), 450);
      }}
    }}

    function persistReviewDraft() {{
      try {{
        localStorage.setItem(reviewDraftKey, JSON.stringify(buildReviewedSheet()));
      }} catch (error) {{}}
    }}

    function loadReviewDraft() {{
      try {{
        const raw = localStorage.getItem(reviewDraftKey);
        if (!raw) return null;
        const draft = JSON.parse(raw);
        if (!draft || !Array.isArray(draft.rows) || draft.rows.length !== originalSheet.rows.length) return null;
        return draft;
      }} catch (error) {{
        return null;
      }}
    }}

    function clearReviewDraft() {{
      try {{
        localStorage.removeItem(reviewDraftKey);
      }} catch (error) {{}}
    }}

    async function saveReview() {{
      if (!backendAvailable) {{
        exportReviewedSheet();
        return;
      }}
      setSaveStatus("Saving...");
      const response = await fetch("/api/review-sheet", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify(buildReviewedSheet())
      }});
      const payload = await response.json();
      if (!response.ok || payload.saved !== true) {{
        throw new Error(payload.error || `Save failed with HTTP ${{response.status}}`);
      }}
      dirty = false;
      clearReviewDraft();
      setSaveStatus(`Saved: ${{payload.approved_count}} works, ${{payload.rejected_count}} problems, ${{payload.pending_count}} unsure`);
    }}

    function exportReviewedSheet() {{
      persistReviewDraft();
      const blob = new Blob([JSON.stringify(buildReviewedSheet(), null, 2) + "\\n"], {{ type: "application/json" }});
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = {download_name_json};
      link.click();
      URL.revokeObjectURL(link.href);
    }}

    function slateTsvCell(value) {{
      return String(value == null ? "" : value)
        .replaceAll("\\t", " ")
        .replaceAll("\\r", " ")
        .replaceAll("\\n", " ")
        .trim();
    }}

    function buildReviewedSlateTsv() {{
      const headers = ["row_index", "cluster_id", "decision", "speaker", "note", "priority_tier", "priority_score", "priority_reason", "question", "expected_impact", "acoustic_verdict", "clip_path", "transcript"];
      const priorityByRow = new Map(minimalNextReviewPlan().map((item) => [String(item.rowIndex), item]));
      const lines = [headers.join("\\t")];
      buildReviewedSheet().rows.forEach((row) => {{
        const question = row.cluster_question || {{}};
        const priority = priorityByRow.get(String(row.index)) || {{}};
        const speaker = question.dominant_speaker || row.target_speaker_label || row.target_speaker_name || question.candidate_name || "";
        const values = [
          row.index,
          question.cluster_id || row.case || "unknown",
          row.status || "pending",
          speaker,
          row.reviewer_note || "",
          priority.reviewPriorityTier || "",
          priority.reviewPriorityScore || "",
          priority.reviewPriorityReason || "",
          question.question || "",
          question.expected_impact || "",
          priority.acousticVerdict || "",
          row.clip_path || "",
          row.text || ""
        ];
        lines.push(values.map(slateTsvCell).join("\\t"));
      }});
      return lines.join("\\n") + "\\n";
    }}

    function exportReviewedSlateTsv() {{
      persistReviewDraft();
      const blob = new Blob([buildReviewedSlateTsv()], {{ type: "text/tab-separated-values" }});
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = {slate_download_name_json};
      link.click();
      URL.revokeObjectURL(link.href);
    }}

    async function toggleRecording(index, button) {{
      if (activeRecording && activeRecording.index === String(index)) {{
        activeRecording.recorder.stop();
        return;
      }}
      if (activeRecording) {{
        setCardMessage(index, "Finish the active recording first.");
        return;
      }}
      if (!backendAvailable) {{
        setCardMessage(index, "Serve this bundle with Pavo before recording notes.");
        return;
      }}
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {{
        setCardMessage(index, "This browser cannot record audio notes.");
        return;
      }}
      const chunks = [];
      const stream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
      const recorder = new MediaRecorder(stream);
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      let recognition = null;
      let transcript = "";
      if (SpeechRecognition) {{
        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = "en-US";
        recognition.onresult = (event) => {{
          transcript = Array.from(event.results).map((result) => result[0].transcript).join(" ").trim();
          if (transcript) {{
            const note = document.querySelector(`[data-note="${{index}}"]`);
            if (note) note.value = transcript;
            setNote(index, transcript);
          }}
        }};
        try {{ recognition.start(); }} catch (error) {{}}
      }}
      recorder.ondataavailable = (event) => {{
        if (event.data && event.data.size) chunks.push(event.data);
      }};
      recorder.onstop = async () => {{
        button.textContent = "Record note";
        button.classList.remove("active");
        const stoppedRecording = activeRecording;
        stopWaveform(stoppedRecording);
        stream.getTracks().forEach((track) => track.stop());
        if (recognition) {{
          try {{ recognition.stop(); }} catch (error) {{}}
        }}
        activeRecording = null;
        try {{
          const blob = new Blob(chunks, {{ type: recorder.mimeType || "audio/webm" }});
          const response = await fetch(`/api/review-note-audio?row=${{encodeURIComponent(index)}}`, {{
            method: "POST",
            headers: {{ "Content-Type": blob.type || "audio/webm" }},
            body: blob
          }});
          const payload = await response.json();
          if (!response.ok || payload.saved !== true) {{
            throw new Error(payload.error || `Audio save failed with HTTP ${{response.status}}`);
          }}
          setDecisionField(index, "reviewer_note_audio_path", payload.audio_path);
          if (transcript) {{
            setDecisionField(index, "reviewer_note_transcript", transcript);
            await parseNote(index);
          }}
          setCardMessage(index, `Saved spoken note: ${{payload.audio_path}}`);
        }} catch (error) {{
          setCardMessage(index, error.message);
        }}
      }};
      activeRecording = {{ index: String(index), recorder, recognition }};
      Object.assign(activeRecording, startWaveform(index, stream));
      setVoiceRecordingState(index, true);
      recorder.start();
      button.textContent = "Stop recording";
      button.classList.add("active");
      setCardMessage(index, SpeechRecognition ? "Recording. Speak in plain English." : "Recording audio note. Type a short note if dictation is unavailable.");
    }}

    function updateCount() {{
      const reviewed = buildReviewedSheet();
      document.getElementById("review-count").textContent =
        `${{reviewed.approved_count}} ${{statusLabels.approved.toLowerCase()}}, ${{reviewed.rejected_count}} ${{statusLabels.rejected.toLowerCase()}}, ${{reviewed.pending_count}} ${{statusLabels.pending.toLowerCase()}}`;
      renderClusterSummary();
      renderNextReviewPlan();
      renderReviewEffort();
      renderCompletionHandoff();
    }}

    function applyDecisionToCard(card, status) {{
      card.classList.remove("review-approved", "review-rejected", "review-pending");
      card.classList.add(`review-${{status}}`);
      card.querySelector("[data-status]").textContent = statusLabels[status] || status;
      card.querySelectorAll("[data-decision]").forEach((button) => {{
        button.classList.toggle("active", button.dataset.decision === status);
      }});
    }}

    function reviewCards() {{
      return Array.from(document.querySelectorAll("[data-review-index]"));
    }}

    function currentReviewCard() {{
      const focused = document.activeElement ? document.activeElement.closest("[data-review-index]") : null;
      if (focused) return focused;
      return reviewCards().find((card) => card.classList.contains("review-pending")) || reviewCards()[0] || null;
    }}

    function focusReviewCard(card) {{
      if (!card) return;
      card.focus({{ preventScroll: true }});
      card.scrollIntoView({{ block: "center", behavior: "smooth" }});
    }}

    function moveReviewFocus(delta) {{
      const cards = reviewCards();
      if (!cards.length) return;
      const current = currentReviewCard();
      const currentIndex = Math.max(0, cards.indexOf(current));
      const nextIndex = Math.min(cards.length - 1, Math.max(0, currentIndex + delta));
      focusReviewCard(cards[nextIndex]);
    }}

    function currentAudio() {{
      const card = currentReviewCard();
      return card ? card.querySelector("audio") : null;
    }}

    function pauseOtherAudio(except) {{
      document.querySelectorAll("audio").forEach((audio) => {{
        if (audio !== except) audio.pause();
      }});
    }}

    function toggleCurrentAudio() {{
      const audio = currentAudio();
      if (!audio) return;
      pauseOtherAudio(audio);
      if (audio.paused) {{
        audio.play().catch(() => {{}});
      }} else {{
        audio.pause();
      }}
    }}

    function seekCurrentAudio(seconds) {{
      const audio = currentAudio();
      if (!audio) return;
      const duration = Number.isFinite(audio.duration) ? audio.duration : Number.POSITIVE_INFINITY;
      audio.currentTime = Math.max(0, Math.min(duration, audio.currentTime + seconds));
    }}

    function restartCurrentAudio() {{
      const audio = currentAudio();
      if (!audio) return;
      pauseOtherAudio(audio);
      audio.currentTime = 0;
      audio.play().catch(() => {{}});
    }}

    function shortcutTargetIsTyping(event) {{
      const target = event.target;
      if (!target) return false;
      const tag = (target.tagName || "").toLowerCase();
      return tag === "textarea" || tag === "input" || tag === "select" || target.isContentEditable === true;
    }}

    function handleReviewShortcut(event) {{
      if (event.metaKey || event.ctrlKey || event.altKey || shortcutTargetIsTyping(event)) return;
      const key = event.key.toLowerCase();
      const code = event.code || "";
      const card = currentReviewCard();
      if (!card && !["j", "k", "n", "arrowleft", "arrowright", "0"].includes(key) && code !== "Space") return;
      if (key === "a") {{
        event.preventDefault();
        setDecision(card.dataset.reviewIndex, "approved");
        moveReviewFocus(1);
      }} else if (key === "r") {{
        event.preventDefault();
        setDecision(card.dataset.reviewIndex, "rejected");
        moveReviewFocus(1);
      }} else if (key === "u") {{
        event.preventDefault();
        setDecision(card.dataset.reviewIndex, "pending");
        moveReviewFocus(1);
      }} else if (key === "j") {{
        event.preventDefault();
        moveReviewFocus(1);
      }} else if (key === "k") {{
        event.preventDefault();
        moveReviewFocus(-1);
      }} else if (key === "n") {{
        event.preventDefault();
        focusNextRecommendedReview();
      }} else if (code === "Space") {{
        event.preventDefault();
        toggleCurrentAudio();
      }} else if (key === "arrowleft") {{
        event.preventDefault();
        seekCurrentAudio(-2);
      }} else if (key === "arrowright") {{
        event.preventDefault();
        seekCurrentAudio(2);
      }} else if (key === "0") {{
        event.preventDefault();
        restartCurrentAudio();
      }} else if (key === "/") {{
        event.preventDefault();
        const note = card.querySelector("[data-note]");
        if (note) note.focus();
      }} else if (key === "s") {{
        event.preventDefault();
        saveReview().catch((error) => setSaveStatus(error.message));
      }}
    }}

    document.querySelectorAll("[data-approve]").forEach((button) => {{
      button.addEventListener("click", () => setDecision(button.dataset.approve, "approved"));
    }});
    document.querySelectorAll("[data-reject]").forEach((button) => {{
      button.addEventListener("click", () => setDecision(button.dataset.reject, "rejected"));
    }});
    document.querySelectorAll("[data-pending]").forEach((button) => {{
      button.addEventListener("click", () => setDecision(button.dataset.pending, "pending"));
    }});
    document.addEventListener("keydown", handleReviewShortcut);
    document.querySelectorAll("[data-note]").forEach((note) => {{
      note.addEventListener("input", () => setNote(note.dataset.note, note.value));
    }});
    document.querySelectorAll("[data-record-note]").forEach((button) => {{
      button.addEventListener("click", () => {{
        toggleRecording(button.dataset.recordNote, button).catch((error) => setCardMessage(button.dataset.recordNote, error.message));
      }});
    }});
    document.querySelectorAll("[data-parse-note]").forEach((button) => {{
      button.addEventListener("click", () => {{
        parseNote(button.dataset.parseNote).catch((error) => setCardMessage(button.dataset.parseNote, error.message));
      }});
    }});
    document.getElementById("save-review").addEventListener("click", () => {{
      saveReview().catch((error) => setSaveStatus(error.message));
    }});
    document.getElementById("export-json").addEventListener("click", exportReviewedSheet);
    document.getElementById("export-slate-tsv").addEventListener("click", exportReviewedSlateTsv);
    document.getElementById("reset-review").addEventListener("click", () => {{
      initializeDecisionsFromSheet(originalSheet);
      document.querySelectorAll("[data-review-index]").forEach((card) => {{
        const index = card.dataset.reviewIndex;
        const decision = decisions.get(index);
        applyDecisionToCard(card, decision.status);
        const note = card.querySelector("[data-note]");
        if (note) note.value = decision.reviewer_note;
        renderParsedReview(card, decision.review_parse);
        drawIdleWaveform(card.querySelector("[data-waveform]"));
      }});
      updateCount();
      markDirty();
    }});
    async function loadBackendSheet() {{
      if (!location.protocol.startsWith("http")) {{
        const draft = loadReviewDraft();
        if (draft) {{
          initializeDecisionsFromSheet(draft);
          setSaveStatus("Restored browser draft. Export review notes when done.");
          return;
        }}
        setSaveStatus("File mode: export review notes");
        return;
      }}
      try {{
        const response = await fetch("/api/review-sheet");
        if (!response.ok) throw new Error(`HTTP ${{response.status}}`);
        initializeDecisionsFromSheet(await response.json());
        backendAvailable = true;
        setSaveStatus("Ready to save");
      }} catch (error) {{
        backendAvailable = false;
        const draft = loadReviewDraft();
        if (draft) {{
          initializeDecisionsFromSheet(draft);
          setSaveStatus("Restored browser draft. Export review notes when done.");
          return;
        }}
        setSaveStatus("File mode: export review notes");
      }}
    }}

    function renderCurrentDecisions() {{
      document.querySelectorAll("[data-review-index]").forEach((card) => {{
        const decision = decisions.get(card.dataset.reviewIndex);
        applyDecisionToCard(card, (decision && decision.status) || "pending");
        const note = card.querySelector("[data-note]");
        if (note && decision) note.value = decision.reviewer_note;
        if (decision) renderParsedReview(card, decision.review_parse);
        drawIdleWaveform(card.querySelector("[data-waveform]"));
      }});
      updateCount();
    }}

    initializeDecisionsFromSheet(originalSheet);
    loadBackendSheet().finally(renderCurrentDecisions);
  </script>
</body>
</html>
"""
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(html)
    return AnchorReviewPageResult(
        review_sheet_path=sheet_path,
        review_page_path=page_path,
        candidate_count=len(rows),
        pending_count=len(pending),
    )


def create_anchor_review_bundle(
    review_sheet_path: Path | str,
    *,
    out_dir: Path | str,
) -> AnchorReviewBundleResult:
    sheet_path = Path(review_sheet_path)
    sheet = json.loads(sheet_path.read_text())
    bundle_dir = Path(out_dir)
    clips_dir = bundle_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    missing = 0
    bundled_rows = []
    for row in sheet.get("rows", []):
        bundled = dict(row)
        source = Path(str(row.get("clip_path", ""))).expanduser()
        if source.exists():
            clip_name = _bundle_clip_name(row, source)
            target = clips_dir / clip_name
            shutil.copy2(source, target)
            bundled["source_clip_path"] = str(source)
            bundled["clip_path"] = f"clips/{clip_name}"
            copied += 1
        else:
            missing += 1
        bundled_rows.append(bundled)
    bundled_sheet = {
        **sheet,
        "source_review_sheet": str(sheet_path),
        "bundle_dir": str(bundle_dir),
        "copied_clip_count": copied,
        "missing_clip_count": missing,
        "rows": bundled_rows,
    }
    bundled_sheet_path = bundle_dir / sheet_path.name
    bundled_sheet_path.write_text(json.dumps(bundled_sheet, indent=2) + "\n")
    page_result = create_anchor_review_page(bundled_sheet_path, out_path=bundle_dir / "index.html")
    return AnchorReviewBundleResult(
        review_sheet_path=sheet_path,
        bundle_dir=bundle_dir,
        bundled_sheet_path=bundled_sheet_path,
        review_page_path=page_result.review_page_path,
        copied_clip_count=copied,
        missing_clip_count=missing,
    )


def build_anchor_review_serve_command(
    bundle_dir: Path | str,
    *,
    host: str = "127.0.0.1",
    port: int = 9876,
    python: str = "python3",
) -> AnchorReviewServeResult:
    root = Path(bundle_dir)
    index = root / "index.html"
    if not index.exists():
        raise FileNotFoundError(f"Review bundle index not found: {index}")
    command = [
        "pavo",
        "review",
        "anchors",
        "serve",
        str(root),
        "--host",
        host,
        "--port",
        str(port),
    ]
    return AnchorReviewServeResult(
        bundle_dir=root,
        host=host,
        port=port,
        url=f"http://{host}:{port}/index.html",
        command=command,
        shell_command=shlex.join(command),
    )


def serve_anchor_review_bundle(
    bundle_dir: Path | str,
    *,
    host: str = "127.0.0.1",
    port: int = 9876,
) -> AnchorReviewServeResult:
    result = build_anchor_review_serve_command(bundle_dir, host=host, port=port)
    root = result.bundle_dir.resolve()
    sheet_path = _find_bundle_review_sheet(root)

    class ReviewHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

        def do_GET(self) -> None:
            if urlparse(self.path).path == "/api/review-sheet":
                self._send_json(json.loads(sheet_path.read_text()))
                return
            super().do_GET()

        def do_POST(self) -> None:
            parsed_path = urlparse(self.path)
            if parsed_path.path == "/api/review-note":
                self._handle_review_note_parse()
                return
            if parsed_path.path == "/api/review-note-audio":
                self._handle_review_note_audio(parsed_path)
                return
            if parsed_path.path != "/api/review-sheet":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("content-length", "0"))
            except ValueError:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "invalid content length")
                return
            if length <= 0:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "empty review payload")
                return
            if length > 2_000_000:
                self._send_error_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "review payload is too large")
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                saved = save_anchor_review_sheet_payload(sheet_path, payload)
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send_error_json(HTTPStatus.BAD_REQUEST, "review payload is not valid JSON")
                return
            except ValueError as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._send_json(
                {
                    "saved": True,
                    "review_sheet": str(saved.imported_sheet_path),
                    "candidate_count": saved.candidate_count,
                    "approved_count": saved.approved_count,
                    "rejected_count": saved.rejected_count,
                    "pending_count": saved.pending_count,
                    "human_reviewed": saved.human_reviewed,
                }
            )

        def _handle_review_note_parse(self) -> None:
            try:
                length = int(self.headers.get("content-length", "0"))
            except ValueError:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "invalid content length")
                return
            if length <= 0:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "empty review note payload")
                return
            if length > 100_000:
                self._send_error_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "review note payload is too large")
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send_error_json(HTTPStatus.BAD_REQUEST, "review note payload is not valid JSON")
                return
            row_index = str(payload.get("row_index") or "")
            sheet = json.loads(sheet_path.read_text())
            row = next((candidate for candidate in sheet.get("rows", []) if str(candidate.get("index")) == row_index), None)
            self._send_json(
                {
                    "parsed": True,
                    "row_index": row_index,
                    "review_parse": parse_plain_english_review(str(payload.get("text") or ""), row=row),
                }
            )

        def _handle_review_note_audio(self, parsed_path: Any) -> None:
            query = parse_qs(parsed_path.query)
            row_index = str((query.get("row") or [""])[0])
            if not row_index:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "missing row query parameter")
                return
            if not _row_exists(sheet_path, row_index):
                self._send_error_json(HTTPStatus.BAD_REQUEST, f"unknown review row {row_index}")
                return
            try:
                length = int(self.headers.get("content-length", "0"))
            except ValueError:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "invalid content length")
                return
            if length <= 0:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "empty audio payload")
                return
            if length > 25_000_000:
                self._send_error_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "audio note payload is too large")
                return
            content_type = self.headers.get("content-type") or "application/octet-stream"
            extension = _audio_note_extension(content_type)
            notes_dir = root / "review-notes"
            notes_dir.mkdir(parents=True, exist_ok=True)
            safe_row = re.sub(r"[^0-9A-Za-z_.-]+", "-", row_index).strip("-") or "row"
            note_path = notes_dir / f"row-{safe_row}-{int(time.time())}{extension}"
            note_path.write_bytes(self.rfile.read(length))
            self._send_json(
                {
                    "saved": True,
                    "row_index": row_index,
                    "audio_path": note_path.relative_to(root).as_posix(),
                    "content_type": content_type,
                }
            )

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
            body = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_error_json(self, status: int, message: str) -> None:
            self._send_json({"saved": False, "error": message}, status=status)

    server = ThreadingHTTPServer((host, port), ReviewHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return result


def import_anchor_review_sheet(
    original_sheet_path: Path | str,
    reviewed_export_path: Path | str,
    *,
    out_path: Path | str | None = None,
) -> AnchorReviewImportResult:
    original_path = Path(original_sheet_path)
    export_path = Path(reviewed_export_path)
    reviewed = json.loads(export_path.read_text())
    return save_anchor_review_sheet_payload(original_path, reviewed, out_path=out_path)


def save_anchor_review_sheet_payload(
    original_sheet_path: Path | str,
    reviewed: dict[str, Any],
    *,
    out_path: Path | str | None = None,
) -> AnchorReviewImportResult:
    original_path = Path(original_sheet_path)
    original = json.loads(original_path.read_text())
    original_rows = original.get("rows", [])
    reviewed_rows = reviewed.get("rows", [])
    if len(original_rows) != len(reviewed_rows):
        raise ValueError("reviewed export row count does not match original sheet")

    reviewed_by_index = {_row_key(row): row for row in reviewed_rows}
    imported_rows = []
    for original_row in original_rows:
        key = _row_key(original_row)
        if key not in reviewed_by_index:
            raise ValueError(f"reviewed export is missing row {key}")
        reviewed_row = reviewed_by_index[key]
        _validate_same_review_row(original_row, reviewed_row)
        imported_rows.append(_imported_review_row(original_row, reviewed_row))

    approved_count = sum(1 for row in imported_rows if row.get("status") == "approved" and row.get("approved") is True)
    rejected_count = sum(1 for row in imported_rows if row.get("status") == "rejected")
    pending_count = sum(1 for row in imported_rows if row.get("status") == "pending")
    imported = {
        **original,
        "passed": bool(imported_rows and approved_count and not pending_count),
        "human_reviewed": bool(imported_rows and not pending_count),
        "candidate_count": len(imported_rows),
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "pending_count": pending_count,
        "rows": imported_rows,
    }
    target_path = Path(out_path) if out_path else original_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(imported, indent=2) + "\n")
    return AnchorReviewImportResult(
        review_sheet_path=original_path,
        imported_sheet_path=target_path,
        candidate_count=len(imported_rows),
        approved_count=approved_count,
        rejected_count=rejected_count,
        pending_count=pending_count,
        human_reviewed=bool(imported_rows and not pending_count),
    )


def build_anchor_review_rerun_command(
    review_sheet_path: Path | str,
    pavo_decompose_manifest_path: Path | str,
    *,
    source_id: str | None = None,
) -> AnchorReviewRerunCommandResult:
    sheet_path = Path(review_sheet_path)
    manifest_path = Path(pavo_decompose_manifest_path)
    corrections = compile_anchor_review_corrections(sheet_path)
    if not corrections.corrections:
        raise ValueError("review sheet has no approved speaker corrections")
    manifest = json.loads(manifest_path.read_text())
    rerun_source_id = source_id or f"{manifest.get('source_id')}_reviewed"
    command = [
        "pavo",
        "audio",
        "decompose",
        str(manifest["audio_path"]),
        "--source-id",
        rerun_source_id,
    ]
    for engine in manifest.get("engines") or ["faster-whisper"]:
        command.extend(["--engine", str(engine)])
    if manifest.get("title"):
        command.extend(["--title", str(manifest["title"])])
    for term in manifest.get("context_terms") or []:
        command.extend(["--context-term", str(term)])
    if manifest.get("context_file"):
        command.extend(["--context-file", str(manifest["context_file"])])
    if manifest.get("num_speakers"):
        command.extend(["--num-speakers", str(manifest["num_speakers"])])
    for speaker in manifest.get("speakers") or []:
        command.extend(["--speaker", str(speaker)])
    command.extend(corrections.cli_args)
    command.extend(["--max-regions", str(manifest.get("max_regions", 3))])
    command.extend(["--padding", str(manifest.get("padding", 1.0))])
    command.extend(["--min-duration", str(manifest.get("min_duration", 1.0))])
    if manifest.get("include_rejected_stems"):
        command.append("--include-rejected-stems")
    return AnchorReviewRerunCommandResult(
        review_sheet_path=sheet_path,
        manifest_path=manifest_path,
        approved_count=corrections.approved_count,
        command=command,
        shell_command=shlex.join(command),
    )


def verify_anchor_review_page(
    review_sheet_path: Path | str,
    review_page_path: Path | str,
) -> AnchorReviewPageVerificationResult:
    sheet_path = Path(review_sheet_path)
    page_path = Path(review_page_path)
    sheet = json.loads(sheet_path.read_text())
    html = page_path.read_text()
    parser = _ReviewPageParser()
    parser.feed(html)
    candidate_count = len(sheet.get("rows", []))
    missing = []
    expected_counts = {
        "audio controls": parser.audio_count,
        "approve buttons": parser.approve_count,
        "reject buttons": parser.reject_count,
        "pending buttons": parser.pending_button_count,
        "reviewer note fields": parser.note_count,
    }
    for label, count in expected_counts.items():
        if count != candidate_count:
            missing.append(f"{label}: expected {candidate_count}, found {count}")
    embedded_sheet_present = False
    if parser.review_sheet_json:
        try:
            embedded = json.loads(parser.review_sheet_json)
            embedded_sheet_present = len(embedded.get("rows", [])) == candidate_count
        except json.JSONDecodeError:
            embedded_sheet_present = False
    requires_import = sheet.get("requires_import_instruction", True)
    requires_rerun = sheet.get("requires_rerun_instruction", True)
    requires_slate_export = any(isinstance(row.get("cluster_question"), dict) for row in sheet.get("rows", []))
    checks = {
        "export button": parser.export_button_present,
        "reset button": parser.reset_button_present,
        "shortcut panel": parser.shortcut_panel_present,
        "keyboard shortcuts": "handleReviewShortcut" in html and 'addEventListener("keydown", handleReviewShortcut)' in html,
        "audio shortcuts": "toggleCurrentAudio" in html and "seekCurrentAudio" in html and "restartCurrentAudio" in html,
        "draft autosave": "localStorage" in html and "persistReviewDraft" in html and "loadReviewDraft" in html,
        "cluster summary": 'id="cluster-summary"' in html and "renderClusterSummary" in html and "clusterConsensusState" in html,
        "next review plan": 'id="next-review-plan"' in html and "minimalNextReviewPlan" in html and "focusNextRecommendedReview" in html,
        "review effort": 'id="review-effort"' in html and "renderReviewEffort" in html,
        "completion handoff": 'id="completion-handoff"' in html and "renderCompletionHandoff" in html and "clusterFinalizeCommand" in html,
        "slate TSV export": (not requires_slate_export)
        or ('id="export-slate-tsv"' in html and "buildReviewedSlateTsv" in html and "exportReviewedSlateTsv" in html),
        "embedded sheet JSON": embedded_sheet_present,
        "import instruction": (not requires_import) or "pavo review anchors import" in html,
        "rerun instruction": (not requires_rerun) or "pavo review anchors rerun-command" in html,
    }
    for label, present in checks.items():
        if not present:
            missing.append(label)
    return AnchorReviewPageVerificationResult(
        review_sheet_path=sheet_path,
        review_page_path=page_path,
        passed=not missing,
        candidate_count=candidate_count,
        audio_count=parser.audio_count,
        approve_count=parser.approve_count,
        reject_count=parser.reject_count,
        pending_button_count=parser.pending_button_count,
        note_count=parser.note_count,
        export_button_present=parser.export_button_present,
        reset_button_present=parser.reset_button_present,
        shortcut_panel_present=checks["shortcut panel"],
        keyboard_handler_present=checks["keyboard shortcuts"],
        audio_shortcuts_present=checks["audio shortcuts"],
        draft_autosave_present=checks["draft autosave"],
        cluster_summary_present=checks["cluster summary"],
        next_review_plan_present=checks["next review plan"],
        review_effort_present=checks["review effort"],
        completion_handoff_present=checks["completion handoff"],
        embedded_sheet_present=embedded_sheet_present,
        import_instruction_present=checks["import instruction"],
        rerun_instruction_present=checks["rerun instruction"],
        missing=missing,
    )


def gate_anchor_review(
    review_sheet_path: Path | str,
    *,
    page_report_path: Path | str | None = None,
    bundle_manifest_path: Path | str | None = None,
    browser_report_path: Path | str | None = None,
    rerun_report_path: Path | str | None = None,
) -> AnchorReviewGateResult:
    sheet_path = Path(review_sheet_path)
    summary = summarize_anchor_review_sheet(sheet_path)
    page_report = _load_optional_json(page_report_path)
    bundle_manifest = _load_optional_json(bundle_manifest_path)
    browser_report = _load_optional_json(browser_report_path)
    rerun_report = _load_optional_json(rerun_report_path)
    page_ready = bool(page_report.get("passed"))
    bundle_ready = bool(bundle_manifest.get("passed"))
    browser_verified = bool(browser_report.get("passed"))
    rerun_command_ready = bool(rerun_report.get("rerun_command_ready"))
    blockers = []
    if not page_ready:
        blockers.append("anchor review page is not verified")
    if not bundle_ready:
        blockers.append("browser-safe anchor review bundle is not ready")
    if not browser_verified:
        blockers.append("anchor review bundle has not been browser-verified")
    if not summary["human_reviewed"]:
        blockers.append(f"{summary['pending_count']} review rows are still pending")
    if not summary["approved_count"]:
        blockers.append("no speaker-anchor clips are approved")
    if summary["human_reviewed"] and summary["approved_count"] and not rerun_command_ready:
        blockers.append("rerun command is not ready")
    passed = bool(
        page_ready
        and bundle_ready
        and browser_verified
        and summary["human_reviewed"]
        and summary["approved_count"]
        and rerun_command_ready
    )
    next_action = (
        "run the rerun command and regenerate Plaud decompose proof"
        if passed
        else "review the bundled clips, export JSON, import it, then run pavo review anchors rerun-command"
    )
    return AnchorReviewGateResult(
        review_sheet_path=sheet_path,
        passed=passed,
        human_reviewed=summary["human_reviewed"],
        approved_count=summary["approved_count"],
        rejected_count=summary["rejected_count"],
        pending_count=summary["pending_count"],
        page_ready=page_ready,
        bundle_ready=bundle_ready,
        browser_verified=browser_verified,
        rerun_command_ready=rerun_command_ready,
        blockers=blockers,
        next_action=next_action,
    )


def status_anchor_review(
    review_sheet_path: Path | str,
    *,
    gate_report_path: Path | str | None = None,
    bundle_manifest_path: Path | str | None = None,
) -> AnchorReviewStatusResult:
    sheet_path = Path(review_sheet_path)
    summary = summarize_anchor_review_sheet(sheet_path)
    gate_report = _load_optional_json(gate_report_path)
    bundle_manifest = _load_optional_json(bundle_manifest_path)
    blockers = gate_report.get("blockers") or []
    next_action = gate_report.get("next_action") or (
        "run the rerun command and regenerate Plaud decompose proof"
        if summary["human_reviewed"] and summary["approved_count"]
        else "review the bundled clips, export JSON, import it, then run pavo review anchors rerun-command"
    )
    return AnchorReviewStatusResult(
        review_sheet_path=sheet_path,
        passed=bool(gate_report.get("passed")),
        review_url=bundle_manifest.get("review_url"),
        serve_command=bundle_manifest.get("serve_command"),
        approved_count=summary["approved_count"],
        rejected_count=summary["rejected_count"],
        pending_count=summary["pending_count"],
        blockers=blockers,
        next_action=next_action,
    )


def summarize_anchor_review_sheet(review_sheet_path: Path | str) -> dict[str, Any]:
    sheet_path = Path(review_sheet_path)
    sheet = json.loads(sheet_path.read_text())
    rows = sheet.get("rows", [])
    approved = [row for row in rows if row.get("approved") is True and row.get("status") == "approved"]
    rejected = [row for row in rows if row.get("status") == "rejected"]
    pending = [row for row in rows if row.get("status") == "pending"]
    return {
        "passed": bool(rows and approved and not pending),
        "human_reviewed": bool(rows and not pending),
        "review_sheet": str(sheet_path),
        "target_speaker_label": sheet.get("target_speaker_label"),
        "candidate_count": len(rows),
        "approved_count": len(approved),
        "rejected_count": len(rejected),
        "pending_count": len(pending),
        "corrections": compile_anchor_review_corrections(sheet_path).corrections,
        "next_required_proof": "rerun Plaud decompose with exported --speaker-correction flags and produce accepted stems",
    }


def parse_plain_english_review(text: str, *, row: dict[str, Any] | None = None) -> dict[str, Any]:
    note = " ".join(str(text or "").split())
    lowered = note.lower()
    issues = []
    suggested_fix = []
    if any(term in lowered for term in ["wrong speaker", "wrong person", "not conan", "not kaitlin", "misidentified"]):
        issues.append("wrong_speaker")
        suggested_fix.append("rename speaker or reject this stem")
    if any(term in lowered for term in ["overlap", "talk over", "talking over", "at the same time", "both talking", "mixed"]):
        issues.append("overlap")
        suggested_fix.append("retry split with overlap-aware boundaries")
    if any(term in lowered for term in ["too quiet", "quiet", "faint", "weak", "barely hear", "buried"]):
        issues.append("weak_voice")
        suggested_fix.append("retry separation or mark the stem diagnostic only")
    if any(term in lowered for term in ["noisy", "noise", "garbled", "muddy", "distorted"]):
        issues.append("noise")
        suggested_fix.append("rerun cleanup before transcription")
    if any(term in lowered for term in ["timing", "starts late", "starts early", "cuts off", "boundary", "too short"]):
        issues.append("timing")
        suggested_fix.append("adjust the clip boundary")
    if any(term in lowered for term in ["transcript", "caption", "word", "phrase", "said"]):
        issues.append("transcript_hint")
    if any(term in lowered for term in ["works", "correct", "right", "good", "clear", "clean", "useful", "got it"]):
        decision = "approved"
    elif any(term in lowered for term in ["wrong", "bad", "problem", "reject", "doesn't work", "does not work", "failed", "misleading"]):
        decision = "rejected"
    elif note:
        decision = "pending"
    else:
        decision = str((row or {}).get("status") or "pending")
    if issues and decision == "approved" and any(issue in issues for issue in ["wrong_speaker", "weak_voice", "noise"]):
        decision = "rejected"
    speaker_names = _known_speaker_names(row)
    heard_speakers = []
    for name in speaker_names:
        name_lower = name.lower()
        first_name = name_lower.split()[0] if name_lower.split() else name_lower
        if name_lower in lowered or first_name in lowered:
            heard_speakers.append(name)
    if not heard_speakers:
        for common_name in ["conan", "kaitlin", "danny", "charlie", "rob", "glenn"]:
            if common_name in lowered:
                heard_speakers.append(common_name.title())
    overlap = True if "overlap" in issues else None
    if any(term in lowered for term in ["no overlap", "not overlapping", "only one speaker", "single speaker"]):
        overlap = False
    confidence = 0.25
    if note:
        confidence += 0.25
    if heard_speakers:
        confidence += 0.2
    if issues:
        confidence += 0.2
    if decision in {"approved", "rejected"}:
        confidence += 0.1
    return {
        "raw_note": note,
        "decision": decision,
        "heard_speakers": heard_speakers,
        "overlap": overlap,
        "issues": sorted(set(issues)),
        "suggested_fix": "; ".join(dict.fromkeys(suggested_fix)),
        "confidence": round(min(confidence, 0.95), 2),
    }


def _find_bundle_review_sheet(bundle_dir: Path) -> Path:
    if not (bundle_dir / "index.html").exists():
        raise FileNotFoundError(f"Review bundle index not found: {bundle_dir / 'index.html'}")
    candidates = sorted(bundle_dir.glob("*-sheet.json"))
    if not candidates:
        candidates = sorted(path for path in bundle_dir.glob("*.json") if "manifest" not in path.name)
    if not candidates:
        raise FileNotFoundError(f"Review bundle sheet JSON not found: {bundle_dir}")
    if len(candidates) > 1:
        raise ValueError(f"Review bundle has multiple sheet JSON files: {', '.join(path.name for path in candidates)}")
    return candidates[0]


def _row_exists(sheet_path: Path, row_index: str) -> bool:
    sheet = json.loads(sheet_path.read_text())
    return any(str(row.get("index")) == str(row_index) for row in sheet.get("rows", []))


def _audio_note_extension(content_type: str) -> str:
    normalized = content_type.lower()
    if "mp4" in normalized:
        return ".m4a"
    if "ogg" in normalized:
        return ".ogg"
    if "wav" in normalized:
        return ".wav"
    return ".webm"


def _known_speaker_names(row: dict[str, Any] | None) -> list[str]:
    names = []
    if not row:
        return names
    for key in ["target_speaker_name", "target_speaker_label"]:
        value = str(row.get(key) or "").strip()
        if value and value.upper() != "MIXED":
            names.append(value)
    return list(dict.fromkeys(names))


def _parsed_review_text(review_parse: dict[str, Any]) -> str:
    if not review_parse:
        return "No parsed note yet."
    speakers = ", ".join(str(name) for name in review_parse.get("heard_speakers") or []) or "unknown"
    issues = ", ".join(str(issue) for issue in review_parse.get("issues") or []) or "none"
    overlap = review_parse.get("overlap")
    overlap_text = "yes" if overlap is True else "no" if overlap is False else "unknown"
    parts = [
        f"Decision: {review_parse.get('decision') or 'pending'}",
        f"Speakers: {speakers}",
        f"Overlap: {overlap_text}",
        f"Issues: {issues}",
    ]
    if review_parse.get("suggested_fix"):
        parts.append(f"Fix: {review_parse.get('suggested_fix')}")
    return " | ".join(parts)


def _speaker_correction(start: Any, end: Any, speaker_label: Any) -> str | None:
    if start is None or end is None or not speaker_label:
        return None
    return f"{_format_seconds(start)}-{_format_seconds(end)}={speaker_label}"


def _row_key(row: dict[str, Any]) -> str:
    return str(row.get("index"))


def _validate_same_review_row(original: dict[str, Any], reviewed: dict[str, Any]) -> None:
    immutable_keys = [
        "index",
        "target_speaker_label",
        "start",
        "end",
        "clip_path",
        "suggested_speaker_correction",
    ]
    for key in immutable_keys:
        if str(original.get(key)) != str(reviewed.get(key)):
            raise ValueError(f"reviewed export row {original.get('index')} changed immutable field {key}")


def _imported_review_row(original: dict[str, Any], reviewed: dict[str, Any]) -> dict[str, Any]:
    status = reviewed.get("status") or "pending"
    if status not in {"pending", "approved", "rejected"}:
        raise ValueError(f"reviewed export row {original.get('index')} has invalid status {status}")
    approved = status == "approved"
    if reviewed.get("approved") is True and status != "approved":
        raise ValueError(f"reviewed export row {original.get('index')} has approved true without approved status")
    row = dict(original)
    row["status"] = status
    row["approved"] = approved
    row["reviewer_note"] = str(reviewed.get("reviewer_note") or "")
    row["reviewer_note_transcript"] = str(reviewed.get("reviewer_note_transcript") or "")
    row["reviewer_note_audio_path"] = str(reviewed.get("reviewer_note_audio_path") or "")
    review_parse = reviewed.get("review_parse") if isinstance(reviewed.get("review_parse"), dict) else {}
    row["review_parse"] = review_parse
    return row


def _review_decision_row(row: dict[str, Any]) -> dict[str, Any]:
    status = str(row.get("status") or "pending")
    speaker = str(row.get("target_speaker_label") or row.get("target_speaker_name") or "")
    review_parse = row.get("review_parse") if isinstance(row.get("review_parse"), dict) else {}
    issues = [str(issue) for issue in review_parse.get("issues") or []]
    approved = status == "approved" and row.get("approved") is True
    unknown = _is_unknown_review_speaker(speaker)
    routeable = bool(approved and speaker and not unknown and "wrong_speaker" not in issues)
    enrollment_candidate = bool(approved and speaker and not unknown)
    return {
        "index": row.get("index"),
        "status": status,
        "approved": bool(row.get("approved") is True),
        "case": row.get("case"),
        "speaker": speaker,
        "start": row.get("start"),
        "end": row.get("end"),
        "duration": row.get("duration"),
        "text": row.get("text"),
        "confidence": row.get("confidence"),
        "method": row.get("method"),
        "clip_path": row.get("clip_path"),
        "recording_id": row.get("recording_id"),
        "reviewer_note": row.get("reviewer_note"),
        "review_parse": review_parse,
        "routeable": routeable,
        "enrollment_candidate": enrollment_candidate,
        "safe_external_task_claim": routeable,
        "recommended_action": _decision_recommended_action(status, speaker, issues),
    }


def _decision_cluster_summary(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        key = str(decision.get("case") or decision.get("speaker") or "uncategorized")
        cluster = clusters.setdefault(
            key,
            {
                "case": key,
                "candidate_count": 0,
                "approved_count": 0,
                "rejected_count": 0,
                "pending_count": 0,
                "routeable_count": 0,
                "enrollment_candidate_count": 0,
            },
        )
        cluster["candidate_count"] += 1
        status = str(decision.get("status") or "pending")
        if status == "approved":
            cluster["approved_count"] += 1
        elif status == "rejected":
            cluster["rejected_count"] += 1
        else:
            cluster["pending_count"] += 1
        if decision.get("routeable"):
            cluster["routeable_count"] += 1
        if decision.get("enrollment_candidate"):
            cluster["enrollment_candidate_count"] += 1
    return sorted(clusters.values(), key=lambda item: (-item["candidate_count"], item["case"]))


def _group_enrollment_samples(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    speakers: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        speaker = str(decision.get("speaker") or "").strip()
        if not speaker:
            continue
        entry = speakers.setdefault(
            speaker,
            {
                "speaker": speaker,
                "slug": _speaker_slug(speaker),
                "sample_count": 0,
                "total_seconds": 0.0,
                "samples": [],
            },
        )
        duration = _safe_float(decision.get("duration"))
        if duration is None:
            start = _safe_float(decision.get("start")) or 0.0
            end = _safe_float(decision.get("end")) or start
            duration = max(0.0, end - start)
        entry["sample_count"] += 1
        entry["total_seconds"] = round(float(entry["total_seconds"]) + duration, 2)
        entry["samples"].append(
            {
                "recording_id": decision.get("recording_id"),
                "start": decision.get("start"),
                "end": decision.get("end"),
                "duration": round(duration, 2),
                "clip_path": decision.get("clip_path"),
                "text": decision.get("text"),
                "reviewer_note": decision.get("reviewer_note"),
            }
        )
    return sorted(speakers.values(), key=lambda item: (-item["sample_count"], item["speaker"]))


def _speaker_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "speaker"


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _review_assistant_row(
    row: dict[str, Any],
    *,
    by_key: dict[tuple[str, float | None, float | None], dict[str, Any]],
    by_recording: dict[str, list[dict[str, Any]]],
    cluster_by_key: dict[tuple[str, float | None, float | None], dict[str, Any]],
) -> dict[str, Any]:
    segment = by_key.get(_review_segment_key(row))
    recording_id = str(row.get("recording_id") or "")
    neighbors = _review_context_neighbors(by_recording.get(recording_id, []), row)
    target = str(row.get("target_speaker_label") or row.get("target_speaker_name") or "")
    suggested = None
    recommendation = "listen_required"
    assistant_confidence = "low"
    why = "No deterministic speaker decision is strong enough to pre-fill this row."
    cluster = _review_cluster_context(row, by_key=by_key, cluster_by_key=cluster_by_key)

    if segment and not _is_unknown_review_speaker(segment.get("speaker")) and str(segment.get("confidence")) in {"medium", "high", "manual_confirmed"}:
        suggested = str(segment.get("speaker"))
        recommendation = "likely_approve_existing_label" if suggested == target else "consider_relabel_to_context_speaker"
        assistant_confidence = "medium" if str(segment.get("confidence")) == "medium" else "high"
        why = f"Current ensemble already has {suggested} at {segment.get('confidence')} confidence via {segment.get('ensemble_source') or 'speaker evidence'}."
    elif not _is_unknown_review_speaker(target):
        trusted_same = [
            item
            for item in neighbors
            if item.get("speaker") == target and item.get("confidence") in {"medium", "high", "manual_confirmed"}
        ]
        if trusted_same:
            suggested = target
            recommendation = "likely_approve_if_voice_matches"
            assistant_confidence = "medium"
            why = f"Nearby trusted context is also {target}; use the clip to confirm the short/weak span."
    else:
        trusted = [item for item in neighbors if not _is_unknown_review_speaker(item.get("speaker")) and item.get("confidence") in {"medium", "high", "manual_confirmed"}]
        speakers = [str(item.get("speaker")) for item in trusted]
        if speakers and len(set(speakers)) == 1:
            suggested = speakers[0]
            recommendation = "consider_assign_to_context_speaker"
            assistant_confidence = "medium"
            why = f"All nearby trusted context points to {suggested}; listen before assigning because this row is currently unknown."

    conflict = _cluster_conflicts_with_suggestion(cluster, suggested)
    if conflict:
        recommendation = "listen_required_cluster_conflict"
        assistant_confidence = "low"
        why = f"{why} Cluster candidate is {cluster.get('candidate_name')}, so this needs explicit listening before assignment."

    return {
        "recommendation": recommendation,
        "assistant_confidence": assistant_confidence,
        "suggested_speaker": suggested,
        "why": why,
        "cluster_context": cluster,
        "context_summary": _review_context_summary(neighbors),
        "matched_segment": _assistant_segment_summary(segment) if segment else None,
        "neighbor_segments": [_assistant_segment_summary(item) for item in neighbors],
    }


def _review_segment_key(segment: dict[str, Any]) -> tuple[str, float | None, float | None]:
    return (
        str(segment.get("recording_id") or segment.get("source_id") or ""),
        _rounded_time(segment.get("start")),
        _rounded_time(segment.get("end")),
    )


def _review_context_neighbors(segments: list[dict[str, Any]], row: dict[str, Any], *, window_seconds: float = 12.0) -> list[dict[str, Any]]:
    start = _rounded_time(row.get("start"))
    end = _rounded_time(row.get("end"))
    if start is None or end is None:
        return []
    context = []
    for segment in segments:
        if _review_segment_key(segment) == _review_segment_key(row):
            continue
        segment_start = _rounded_time(segment.get("start"))
        segment_end = _rounded_time(segment.get("end"))
        if segment_start is None or segment_end is None:
            continue
        gap = min(abs(start - segment_end), abs(segment_start - end))
        if gap <= window_seconds:
            context.append({**segment, "_pavo_context_gap": round(gap, 2)})
    return sorted(context, key=lambda item: float(item.get("_pavo_context_gap") or 0.0))[:6]


def _diarization_cluster_by_key(root: Path) -> dict[tuple[str, float | None, float | None], dict[str, Any]]:
    clusters = _load_voice_clusters(root)
    by_key: dict[tuple[str, float | None, float | None], dict[str, Any]] = {}
    for segment in _load_diarization_segments(root):
        cluster_id = str(segment.get("speaker") or "")
        cluster = clusters.get(cluster_id) if isinstance(clusters.get(cluster_id), dict) else {}
        by_key[_review_segment_key(segment)] = {
            "cluster_id": cluster_id,
            "candidate_name": segment.get("candidate_name") or cluster.get("candidate_name"),
            "candidate_confidence": cluster.get("candidate_confidence"),
            "candidate_reason": cluster.get("candidate_reason"),
            "segment_count": cluster.get("segment_count"),
            "duration_seconds": cluster.get("duration_seconds"),
        }
    return by_key


def _load_voice_clusters(root: Path) -> dict[str, Any]:
    for path in root.rglob("voice-clusters.json"):
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {}
            return payload if isinstance(payload, dict) else {}
    return {}


def _review_cluster_context(
    row: dict[str, Any],
    *,
    by_key: dict[tuple[str, float | None, float | None], dict[str, Any]],
    cluster_by_key: dict[tuple[str, float | None, float | None], dict[str, Any]],
) -> dict[str, Any] | None:
    cluster = cluster_by_key.get(_review_segment_key(row))
    if not cluster:
        return None
    matched = by_key.get(_review_segment_key(row))
    return {
        **cluster,
        "matched_speaker": matched.get("speaker") if matched else None,
        "matched_confidence": matched.get("confidence") if matched else None,
        "matched_source": matched.get("ensemble_source") if matched else None,
    }


def _cluster_conflicts_with_suggestion(cluster: dict[str, Any] | None, suggested: str | None) -> bool:
    if not cluster or not suggested:
        return False
    candidate = str(cluster.get("candidate_name") or "")
    if _is_unknown_review_speaker(candidate) or _is_unknown_review_speaker(suggested):
        return False
    return candidate != suggested


def _cluster_identity_audit_row(
    cluster_id: str,
    rows: list[dict[str, Any]],
    cluster: dict[str, Any],
    named_by_key: dict[tuple[str, float | None, float | None], dict[str, Any]],
    *,
    min_strong_coverage: float,
    min_dominant_share: float,
) -> dict[str, Any]:
    strong_counts: dict[str, int] = {}
    all_counts: dict[str, int] = {}
    examples: dict[str, list[str]] = {}
    for row in rows:
        named = named_by_key.get(_review_segment_key(row))
        if not named:
            continue
        speaker = str(named.get("speaker") or "")
        confidence = str(named.get("confidence") or "unknown")
        key = f"{speaker}/{confidence}"
        all_counts[key] = all_counts.get(key, 0) + 1
        if confidence in {"medium", "high", "manual_confirmed"} and not _is_unknown_review_speaker(speaker):
            strong_counts[speaker] = strong_counts.get(speaker, 0) + 1
            examples.setdefault(speaker, [])
            if len(examples[speaker]) < 3 and named.get("text"):
                examples[speaker].append(str(named.get("text")))

    segment_count = len(rows)
    strong_total = sum(strong_counts.values())
    dominant_speaker = None
    dominant_count = 0
    if strong_counts:
        dominant_speaker, dominant_count = sorted(strong_counts.items(), key=lambda item: (-item[1], item[0]))[0]
    strong_coverage = round(strong_total / segment_count, 4) if segment_count else 0.0
    dominant_share = round(dominant_count / strong_total, 4) if strong_total else 0.0
    candidate = str(cluster.get("candidate_name") or "")
    candidate_confidence = str(cluster.get("candidate_confidence") or "unknown")
    candidate_conflicts = bool(
        dominant_speaker
        and not _is_unknown_review_speaker(candidate)
        and candidate != dominant_speaker
    )

    status = "needs_targeted_review"
    recommended_action = "Ask a human to identify representative clips before propagating this cluster."
    if strong_total == 0:
        status = "no_strong_named_evidence"
        recommended_action = "Collect at least one reviewed/named speaker sample for this cluster."
    elif candidate_conflicts:
        status = "candidate_conflict"
        recommended_action = "Do not propagate; review conflict clips and create must-link/cannot-link constraints."
    elif strong_coverage >= min_strong_coverage and dominant_share >= min_dominant_share:
        status = "safe_to_propagate"
        recommended_action = f"Propagate {dominant_speaker} only with provenance and keep sampled review checks."
    elif dominant_share >= min_dominant_share:
        status = "low_coverage_targeted_review"
        recommended_action = f"Ask targeted questions for {dominant_speaker}; evidence is dominant but sparse."

    return {
        "cluster_id": cluster_id,
        "status": status,
        "candidate_name": cluster.get("candidate_name"),
        "candidate_confidence": cluster.get("candidate_confidence"),
        "candidate_reason": cluster.get("candidate_reason"),
        "segment_count": segment_count,
        "duration_seconds": cluster.get("duration_seconds"),
        "strong_named_count": strong_total,
        "strong_coverage": strong_coverage,
        "dominant_speaker": dominant_speaker,
        "dominant_count": dominant_count,
        "dominant_share": dominant_share,
        "strong_counts": strong_counts,
        "all_named_counts": all_counts,
        "sample_quotes_by_speaker": examples,
        "recommended_action": recommended_action,
    }


def _cluster_question(
    cluster: dict[str, Any],
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    status = str(cluster.get("status") or "needs_targeted_review")
    cluster_id = str(cluster.get("cluster_id") or "")
    dominant = cluster.get("dominant_speaker")
    candidate = cluster.get("candidate_name")
    if status == "candidate_conflict":
        question = f"Does cluster {cluster_id} belong to {candidate} or {dominant}?"
        suggested = "Create cannot-link/must-link constraints before propagation."
        stop = "At least one conflict sample is explicitly assigned or rejected."
    elif status == "low_coverage_targeted_review":
        question = f"Can cluster {cluster_id} be confirmed as {dominant}?"
        suggested = f"Approve representative {dominant} samples if the voice matches."
        stop = "Two representative samples confirm the same speaker, or one sample contradicts it."
    elif status == "no_strong_named_evidence":
        question = f"Who is the representative speaker for cluster {cluster_id}?"
        suggested = "Identify or mark unassigned before any propagation."
        stop = "One clean representative sample has a reviewed speaker label."
    else:
        question = f"What speaker identity should constrain cluster {cluster_id}?"
        suggested = "Review representative clips before propagating."
        stop = "Representative samples either agree on one speaker or expose a split cluster."

    return {
        "cluster_id": cluster_id,
        "status": status,
        "question": question,
        "candidate_name": candidate,
        "dominant_speaker": dominant,
        "strong_coverage": cluster.get("strong_coverage"),
        "dominant_share": cluster.get("dominant_share"),
        "expected_impact": f"{cluster.get('segment_count')} segments / {cluster.get('duration_seconds') or 'unknown'} seconds",
        "suggested_decision": suggested,
        "stop_condition": stop,
        "samples": samples,
    }


def _cluster_question_samples(
    rows: list[dict[str, Any]],
    *,
    named_by_key: dict[tuple[str, float | None, float | None], dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    scored = []
    for row in rows:
        text = str(row.get("text") or "").strip()
        named = named_by_key.get(_review_segment_key(row))
        confidence = str(named.get("confidence") if named else "")
        speaker = str(named.get("speaker") if named else row.get("candidate_name") or "")
        score = _question_sample_score(row, named)
        scored.append((score, row, named, speaker, confidence, text))
    results = []
    for _, row, named, speaker, confidence, text in sorted(scored, key=lambda item: (-item[0], str(item[1].get("recording_id") or ""), _safe_float(item[1].get("start")) or 0.0)):
        if len(results) >= limit:
            break
        results.append(
            {
                "recording_id": row.get("recording_id"),
                "start": row.get("start"),
                "end": row.get("end"),
                "cluster_speaker": row.get("speaker"),
                "candidate_name": row.get("candidate_name"),
                "named_speaker": speaker,
                "named_confidence": confidence,
                "text": text[:500],
                "selection_reason": "longer informative sample with available text/evidence",
            }
        )
    return results


def _question_sample_score(row: dict[str, Any], named: dict[str, Any] | None) -> float:
    duration = max(0.0, (_safe_float(row.get("end")) or 0.0) - (_safe_float(row.get("start")) or 0.0))
    text = str(row.get("text") or "")
    score = min(duration, 20.0)
    if 20 <= len(text) <= 240:
        score += 5.0
    if named and str(named.get("confidence")) in {"medium", "high", "manual_confirmed"}:
        score += 4.0
    if named and not _is_unknown_review_speaker(named.get("speaker")):
        score += 2.0
    return score


def _cluster_question_review_row(question: dict[str, Any], sample: dict[str, Any], index: int, clip_path: Path) -> dict[str, Any]:
    prompt = (
        f"{question.get('question')} "
        f"Suggested decision: {question.get('suggested_decision')} "
        f"Stop condition: {question.get('stop_condition')}"
    )
    expected_segments, expected_seconds = _expected_impact_numbers(question.get("expected_impact"))
    impact_score = _cluster_question_impact_score(expected_segments, expected_seconds, pending_rows=1)
    return {
        "index": index,
        "impact_rank": index,
        "impact_score": impact_score,
        "expected_unlock_segments": expected_segments,
        "expected_unlock_seconds": expected_seconds,
        "status": "pending",
        "approved": False,
        "target_speaker_label": question.get("dominant_speaker") or question.get("candidate_name") or question.get("cluster_id"),
        "target_speaker_name": question.get("dominant_speaker") or question.get("candidate_name") or question.get("cluster_id"),
        "start": sample.get("start"),
        "end": sample.get("end"),
        "duration": round(max(0.0, (_safe_float(sample.get("end")) or 0.0) - (_safe_float(sample.get("start")) or 0.0)), 2),
        "text": sample.get("text"),
        "confidence": sample.get("named_confidence") or "review_required",
        "method": "cluster_question_plan",
        "clip_path": str(clip_path),
        "recording_id": sample.get("recording_id"),
        "case": f"{question.get('cluster_id')} / {question.get('status')}",
        "expected_behavior": question.get("stop_condition"),
        "review_heading": question.get("question"),
        "review_prompt": prompt,
        "review_subtitle": question.get("expected_impact"),
        "cluster_question": question,
        "cluster_sample": sample,
    }


def _rank_cluster_question_review_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        rows,
        key=lambda row: (
            -float(row.get("impact_score") or 0.0),
            str((row.get("cluster_question") or {}).get("cluster_id") or ""),
            int(row.get("index") or 0),
        ),
    )
    output = []
    for index, row in enumerate(ranked, start=1):
        enriched = dict(row)
        enriched["index"] = index
        enriched["impact_rank"] = index
        output.append(enriched)
    return output


def _cluster_question_impact_score(expected_segments: int, expected_seconds: float, *, pending_rows: int) -> float:
    return round((expected_segments * 10.0) + expected_seconds + (pending_rows * 2.0), 2)


def _expected_impact_numbers(value: Any) -> tuple[int, float]:
    text = str(value or "")
    segment_match = re.search(r"(\d+)\s+segments?", text)
    seconds_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s+seconds?", text)
    segments = int(segment_match.group(1)) if segment_match else 0
    seconds = float(seconds_match.group(1)) if seconds_match else 0.0
    return segments, seconds


def _resolve_review_clip_path(sheet_path: Path, value: Any) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    if path.is_absolute():
        return path
    candidate = sheet_path.parent / path
    if candidate.exists():
        return candidate
    return path


def _load_acoustic_review_rows(sheet_path: Path) -> dict[int, dict[str, Any]]:
    report_path = sheet_path.with_name("pavo-cluster-question-acoustic-evidence.json")
    report = _load_optional_json(report_path)
    if not report:
        return {}
    clusters = {
        str(item.get("cluster_id") or ""): item
        for item in report.get("clusters") or []
        if isinstance(item, dict)
    }
    by_index: dict[int, dict[str, Any]] = {}
    for row in report.get("rows") or []:
        if not isinstance(row, dict) or row.get("index") is None:
            continue
        try:
            index = int(row.get("index"))
        except (TypeError, ValueError):
            continue
        cluster_id = str(row.get("cluster_id") or "")
        cluster = clusters.get(cluster_id, {})
        by_index[index] = {
            "cluster_id": cluster_id,
            "verdict": cluster.get("verdict"),
            "min_pair_similarity": cluster.get("min_pair_similarity"),
            "average_pair_similarity": cluster.get("average_pair_similarity"),
            "recommended_next_action": cluster.get("recommended_next_action"),
            "signature": row.get("signature"),
            "source_report": str(report_path),
        }
    return by_index


def _with_acoustic_review(row: dict[str, Any], acoustic_rows: dict[int, dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(row, dict) or row.get("index") is None:
        return row
    try:
        index = int(row.get("index"))
    except (TypeError, ValueError):
        return row
    acoustic = acoustic_rows.get(index)
    if not acoustic:
        return row
    return {**row, "acoustic_review": acoustic}


def _acoustic_signature_for_clip(clip_path: Path | None) -> dict[str, Any]:
    if not clip_path or not clip_path.exists():
        return {"analyzed": False, "reason": "clip_missing"}
    try:
        samples, sample_rate = _load_clip_samples(clip_path)
    except Exception as exc:
        return {"analyzed": False, "reason": f"decode_failed: {exc}"}
    if not samples or sample_rate <= 0:
        return {"analyzed": False, "reason": "no_pcm_samples"}
    duration = len(samples) / float(sample_rate)
    if duration <= 0:
        return {"analyzed": False, "reason": "zero_duration"}
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    peak = max(abs(sample) for sample in samples)
    zero_crossings = sum(1 for left, right in zip(samples, samples[1:]) if (left < 0 <= right) or (right < 0 <= left))
    zcr = zero_crossings / max(1, len(samples) - 1)
    window_size = max(1, int(sample_rate * 0.1))
    energies = []
    for start in range(0, len(samples), window_size):
        window = samples[start : start + window_size]
        if window:
            energies.append(math.sqrt(sum(sample * sample for sample in window) / len(window)))
    mean_energy = sum(energies) / len(energies) if energies else 0.0
    energy_variance = sum((item - mean_energy) ** 2 for item in energies) / len(energies) if energies else 0.0
    dynamic_range = (max(energies) - min(energies)) if energies else 0.0
    silence_ratio = sum(1 for item in energies if item < 0.02) / len(energies) if energies else 0.0
    feature_vector = [
        round(min(rms * 4.0, 1.0), 5),
        round(min(peak * 2.0, 1.0), 5),
        round(min(zcr * 20.0, 1.0), 5),
        round(min(math.sqrt(energy_variance) * 8.0, 1.0), 5),
        round(min(dynamic_range * 5.0, 1.0), 5),
        round(min(silence_ratio, 1.0), 5),
    ]
    return {
        "analyzed": True,
        "duration_seconds": round(duration, 3),
        "sample_rate": sample_rate,
        "rms": round(rms, 6),
        "peak": round(peak, 6),
        "zero_crossing_rate": round(zcr, 6),
        "silence_ratio": round(silence_ratio, 6),
        "energy_dynamic_range": round(dynamic_range, 6),
        "feature_vector": feature_vector,
    }


def _load_clip_samples(clip_path: Path) -> tuple[list[float], int]:
    if clip_path.suffix.lower() == ".wav":
        try:
            return _read_wav_samples(clip_path)
        except wave.Error:
            pass
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg missing for non-wav acoustic analysis")
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "clip.wav"
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(clip_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-acodec",
            "pcm_s16le",
            str(wav_path),
        ]
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return _read_wav_samples(wav_path)


def _read_wav_samples(path: Path) -> tuple[list[float], int]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    if sample_width != 2:
        raise RuntimeError(f"unsupported wav sample width {sample_width}")
    samples = []
    frame_width = sample_width * channels
    for offset in range(0, len(frames), frame_width):
        channel_values = []
        for channel in range(channels):
            start = offset + (channel * sample_width)
            if start + sample_width <= len(frames):
                channel_values.append(int.from_bytes(frames[start : start + sample_width], byteorder="little", signed=True) / 32768.0)
        if channel_values:
            samples.append(sum(channel_values) / len(channel_values))
    return samples, sample_rate


def _cluster_acoustic_summary(cluster_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    analyzed = [item for item in items if item.get("signature", {}).get("analyzed")]
    pair_scores = []
    for left_index, left in enumerate(analyzed):
        for right in analyzed[left_index + 1 :]:
            pair_scores.append(_acoustic_similarity(left["signature"].get("feature_vector") or [], right["signature"].get("feature_vector") or []))
    if len(analyzed) < 2:
        verdict = "insufficient_audio"
        action = "Collect or repair at least two playable samples before using acoustic consistency."
    else:
        min_score = min(pair_scores) if pair_scores else 0.0
        if min_score >= 0.88:
            verdict = "consistent_acoustic_shape"
            action = "Review normally; the sampled clips have similar acoustic shape, but still listen before approving identity."
        elif min_score >= 0.72:
            verdict = "mixed_acoustic_shape"
            action = "Listen carefully; samples are not obviously split but should not be rushed."
        else:
            verdict = "listen_carefully_acoustic_drift"
            action = "Prioritize this cluster for careful listening; acoustic drift may mean noise, overlap, or a split cluster."
    return {
        "cluster_id": cluster_id,
        "sample_count": len(items),
        "analyzed_count": len(analyzed),
        "min_pair_similarity": round(min(pair_scores), 4) if pair_scores else None,
        "average_pair_similarity": round(sum(pair_scores) / len(pair_scores), 4) if pair_scores else None,
        "verdict": verdict,
        "recommended_next_action": action,
        "rows": [item.get("index") for item in items],
    }


def _acoustic_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)) / len(left))
    return round(max(0.0, min(1.0, 1.0 - distance)), 4)


def _review_sample_audio_path(root: Path, recording_id: Any) -> Path | None:
    if not recording_id:
        return None
    candidates = sorted(root.rglob(f"{recording_id}.*"))
    for path in candidates:
        if path.suffix.lower() in {".aac", ".m4a", ".mp3", ".wav"} and path.is_file():
            return path
    return None


def _question_sample_window(sample: dict[str, Any], *, padding: float) -> tuple[float | None, float | None]:
    start = _safe_float(sample.get("start"))
    end = _safe_float(sample.get("end"))
    if start is None or end is None:
        return None, None
    return max(0.0, start - padding), max(start, end + padding)


def _extract_review_audio_clip(ffmpeg: str, source_audio: Path, clip_path: Path, *, start: float, end: float) -> Path | None:
    duration = max(0.1, end - start)
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    mp3_command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(source_audio),
        "-vn",
        "-acodec",
        "libmp3lame",
        str(clip_path),
    ]
    try:
        subprocess.run(mp3_command, check=True, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        wav_path = clip_path.with_suffix(".wav")
        wav_command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(source_audio),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-acodec",
            "pcm_s16le",
            str(wav_path),
        ]
        try:
            subprocess.run(wav_command, check=True, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.CalledProcessError):
            return None
        if wav_path.exists() and wav_path.stat().st_size > 0:
            if clip_path.exists() and clip_path.stat().st_size == 0:
                clip_path.unlink()
            return wav_path
        return None
    return clip_path if clip_path.exists() and clip_path.stat().st_size > 0 else None


def _cluster_question_decision_row(row: dict[str, Any]) -> dict[str, Any]:
    status = str(row.get("status") or "pending")
    question = row.get("cluster_question") if isinstance(row.get("cluster_question"), dict) else {}
    sample = row.get("cluster_sample") if isinstance(row.get("cluster_sample"), dict) else {}
    approved = status == "approved" and row.get("approved") is True
    return {
        "index": row.get("index"),
        "status": status,
        "approved": approved,
        "case": row.get("case"),
        "impact_rank": row.get("impact_rank"),
        "impact_score": row.get("impact_score"),
        "cluster_id": question.get("cluster_id"),
        "cluster_status": question.get("status"),
        "question": question.get("question"),
        "suggested_decision": question.get("suggested_decision"),
        "stop_condition": question.get("stop_condition"),
        "expected_impact": question.get("expected_impact"),
        "strong_coverage": question.get("strong_coverage"),
        "dominant_share": question.get("dominant_share"),
        "target_speaker_label": row.get("target_speaker_label"),
        "target_speaker_name": row.get("target_speaker_name"),
        "dominant_speaker": question.get("dominant_speaker"),
        "candidate_name": question.get("candidate_name"),
        "recording_id": row.get("recording_id"),
        "start": row.get("start"),
        "end": row.get("end"),
        "duration": row.get("duration"),
        "text": row.get("text"),
        "clip_path": row.get("clip_path"),
        "reviewer_note": row.get("reviewer_note"),
        "review_parse": row.get("review_parse") if isinstance(row.get("review_parse"), dict) else {},
        "sample": sample,
        "safe_to_materialize": status in {"approved", "rejected"},
    }


def _cluster_question_consensus_summaries(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        cluster_id = str(decision.get("cluster_id") or decision.get("case") or "unknown")
        cluster = grouped.setdefault(
            cluster_id,
            {
                "cluster_id": cluster_id,
                "target_speaker": decision.get("dominant_speaker") or decision.get("target_speaker_label") or decision.get("candidate_name"),
                "question": decision.get("question"),
                "expected_impact": decision.get("expected_impact"),
                "strong_coverage": decision.get("strong_coverage"),
                "dominant_share": decision.get("dominant_share"),
                "sample_count": 0,
                "approved_rows": 0,
                "rejected_rows": 0,
                "pending_rows": 0,
                "reviewed_indices": [],
                "pending_indices": [],
                "sample_text": [],
            },
        )
        cluster["sample_count"] += 1
        status = str(decision.get("status") or "pending")
        if status == "approved":
            cluster["approved_rows"] += 1
            cluster["reviewed_indices"].append(decision.get("index"))
        elif status == "rejected":
            cluster["rejected_rows"] += 1
            cluster["reviewed_indices"].append(decision.get("index"))
        else:
            cluster["pending_rows"] += 1
            cluster["pending_indices"].append(decision.get("index"))
        text = str(decision.get("text") or "").strip()
        if text and len(cluster["sample_text"]) < 2:
            cluster["sample_text"].append(text[:220])

    summaries = []
    for cluster in grouped.values():
        approved_rows = int(cluster["approved_rows"])
        rejected_rows = int(cluster["rejected_rows"])
        pending_rows = int(cluster["pending_rows"])
        sample_count = int(cluster["sample_count"])
        approval_quorum = min(2, sample_count)
        cluster["approval_quorum"] = approval_quorum
        if approved_rows and rejected_rows:
            consensus_state = "conflicting_review"
            materialization_effect = "do_not_materialize_broad_cluster_constraint"
            recommended_next_action = "Add or re-listen to samples; the cluster may be mixed or the proposed speaker may be wrong."
        elif rejected_rows:
            consensus_state = "ready_for_cannot_link"
            materialization_effect = "cluster_can_be_rejected_for_target_speaker"
            recommended_next_action = "Early stop: a representative sample contradicted the proposed speaker. Materialize cannot-link or add samples if unsure."
        elif approved_rows >= approval_quorum:
            consensus_state = "ready_for_must_link"
            materialization_effect = "cluster_can_be_confirmed_for_target_speaker"
            recommended_next_action = "Materialize as a must-link cluster constraint, then rerun the brief and measure review-pressure reduction."
        elif approved_rows:
            consensus_state = "pending_review"
            materialization_effect = "needs_more_support_before_must_link"
            recommended_next_action = f"Need {approval_quorum - approved_rows} more supporting sample(s), or one contradiction to early-stop as cannot-link."
        elif pending_rows:
            consensus_state = "pending_review"
            materialization_effect = "no_cluster_constraint_until_terminal_consensus"
            recommended_next_action = "Review one representative sample. A contradiction can early-stop; confirmation needs the quorum."
        else:
            consensus_state = "unresolved_no_decision"
            materialization_effect = "no_cluster_constraint"
            recommended_next_action = "Review at least one sample or replace weak samples."
        cluster["consensus_state"] = consensus_state
        cluster["materialization_effect"] = materialization_effect
        cluster["recommended_next_action"] = recommended_next_action
        summaries.append(cluster)
    return sorted(
        summaries,
        key=lambda item: (
            item.get("consensus_state") != "conflicting_review",
            item.get("consensus_state") != "pending_review",
            str(item.get("cluster_id") or ""),
        ),
    )


def _cluster_question_next_review_plan(
    decisions: list[dict[str, Any]],
    cluster_summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    summary_by_cluster = {str(item.get("cluster_id") or "unknown"): item for item in cluster_summaries}
    pending_by_cluster: dict[str, list[dict[str, Any]]] = {}
    for decision in decisions:
        if str(decision.get("status") or "pending") != "pending":
            continue
        cluster_id = str(decision.get("cluster_id") or decision.get("case") or "unknown")
        pending_by_cluster.setdefault(cluster_id, []).append(decision)

    plan: list[dict[str, Any]] = []
    for cluster_id, summary in summary_by_cluster.items():
        state = str(summary.get("consensus_state") or "")
        if state in {"ready_for_must_link", "ready_for_cannot_link", "conflicting_review"}:
            continue
        candidates = pending_by_cluster.get(cluster_id) or []
        if not candidates:
            continue
        candidates.sort(
            key=lambda row: (
                -float(row.get("impact_score") or 0.0),
                int(row.get("impact_rank") or row.get("index") or 0),
                int(row.get("index") or 0),
            )
        )
        row = candidates[0]
        approved_rows = int(summary.get("approved_rows") or 0)
        approval_quorum = int(summary.get("approval_quorum") or 1)
        approvals_needed = max(0, approval_quorum - approved_rows)
        if approved_rows:
            closure_rule = f"Approve {approvals_needed} more matching sample(s), or reject this sample to early-stop as cannot-link."
        else:
            closure_rule = "Reject this sample to early-stop as cannot-link; approve it only if the voice supports the proposed speaker."
        approve_effect = (
            "Approving this sample reaches must-link quorum for the cluster."
            if approvals_needed <= 1
            else f"Approving this sample adds support; {approvals_needed - 1} more matching sample(s) still needed for must-link quorum."
        )
        reject_effect = "Rejecting this sample early-stops this cluster as cannot-link and prevents unsafe identity propagation."
        terminal_decision_rule = "One contradiction is enough for cannot-link; confirming a speaker requires the approval quorum."
        plan.append(
            {
                "cluster_id": cluster_id,
                "target_speaker": summary.get("target_speaker"),
                "consensus_state": state,
                "row_index": row.get("index"),
                "impact_rank": row.get("impact_rank"),
                "impact_score": row.get("impact_score"),
                "expected_impact": summary.get("expected_impact"),
                "recording_id": row.get("recording_id"),
                "start": row.get("start"),
                "end": row.get("end"),
                "clip_path": row.get("clip_path"),
                "text": row.get("text"),
                "question": summary.get("question"),
                "closure_rule": closure_rule,
                "approve_effect": approve_effect,
                "reject_effect": reject_effect,
                "terminal_decision_rule": terminal_decision_rule,
                "recommended_action": "Listen to this representative pending sample before any lower-impact sample in the same cluster.",
            }
        )
    return sorted(
        plan,
        key=lambda item: (
            -float(item.get("impact_score") or 0.0),
            int(item.get("impact_rank") or item.get("row_index") or 0),
            str(item.get("cluster_id") or ""),
        ),
    )


def _cluster_question_review_effort(*, pending_count: int, next_review_count: int) -> dict[str, Any]:
    pending = max(0, int(pending_count or 0))
    minimum = max(0, int(next_review_count or 0))
    saved = max(0, pending - minimum)
    reduction = round((saved / pending) * 100.0, 1) if pending else 0.0
    return {
        "pending_reviews": pending,
        "minimum_reviews": minimum,
        "possible_reviews_saved": saved,
        "reduction_percent": reduction,
        "summary": f"{minimum} minimum reviews vs {pending} pending clips; up to {saved} clips can be skipped by terminal cluster consensus.",
    }


def _cluster_constraint_from_decision(decision: dict[str, Any], *, kind: str) -> dict[str, Any] | None:
    cluster_id = decision.get("cluster_id")
    speaker = decision.get("dominant_speaker") or decision.get("target_speaker_label") or decision.get("candidate_name")
    if not cluster_id or not speaker:
        return None
    return {
        "type": kind,
        "cluster_id": cluster_id,
        "speaker": speaker,
        "recording_id": decision.get("recording_id"),
        "start": decision.get("start"),
        "end": decision.get("end"),
        "clip_path": decision.get("clip_path"),
        "reviewer_note": decision.get("reviewer_note"),
        "question": decision.get("question"),
        "source_decision_index": decision.get("index"),
    }


def _cluster_hint_from_decision(decision: dict[str, Any]) -> dict[str, Any] | None:
    speaker = decision.get("dominant_speaker") or decision.get("target_speaker_label") or decision.get("candidate_name")
    if not speaker or _is_unknown_review_speaker(speaker):
        return None
    return {
        "speaker": speaker,
        "cluster_id": decision.get("cluster_id"),
        "recording_id": decision.get("recording_id"),
        "start": decision.get("start"),
        "end": decision.get("end"),
        "duration": decision.get("duration"),
        "text": decision.get("text"),
        "clip_path": decision.get("clip_path"),
        "reviewer_note": decision.get("reviewer_note"),
        "confidence": "manual_confirmed_cluster_question",
    }


def _review_context_summary(neighbors: list[dict[str, Any]]) -> str:
    if not neighbors:
        return "No nearby trusted context was found."
    parts = []
    for item in neighbors[:4]:
        parts.append(
            f"{item.get('speaker') or 'unknown'}:{item.get('confidence') or 'unknown'}"
            f"@{item.get('start')}-{item.get('end')}"
        )
    return "; ".join(parts)


def _assistant_segment_summary(segment: dict[str, Any] | None) -> dict[str, Any] | None:
    if not segment:
        return None
    return {
        "recording_id": segment.get("recording_id") or segment.get("source_id"),
        "start": segment.get("start"),
        "end": segment.get("end"),
        "speaker": segment.get("speaker"),
        "confidence": segment.get("confidence"),
        "ensemble_source": segment.get("ensemble_source"),
        "reason": segment.get("reason"),
        "gap_seconds": segment.get("_pavo_context_gap"),
        "text": segment.get("text"),
    }


def _assistant_review_block(row: dict[str, Any]) -> str:
    assistant = row.get("assistant_review") if isinstance(row.get("assistant_review"), dict) else None
    if not assistant:
        return ""
    cluster = assistant.get("cluster_context") if isinstance(assistant.get("cluster_context"), dict) else {}
    cluster_text = ""
    if cluster:
        cluster_text = (
            f"<p class=\"context\">Cluster {escape(str(cluster.get('cluster_id') or ''))}: "
            f"candidate {escape(str(cluster.get('candidate_name') or 'unknown'))} "
            f"({escape(str(cluster.get('candidate_confidence') or 'unknown'))})</p>"
        )
    return f"""  <section class="assistant-review">
    <strong>Pavo assistant:</strong>
    <span>{escape(str(assistant.get('recommendation') or 'listen_required'))}</span>
    <span>confidence {escape(str(assistant.get('assistant_confidence') or 'low'))}</span>
    <p>{escape(str(assistant.get('why') or ''))}</p>
    <p class="context">{escape(str(assistant.get('context_summary') or ''))}</p>
    {cluster_text}
  </section>"""


def _acoustic_review_block(row: dict[str, Any]) -> str:
    acoustic = row.get("acoustic_review") if isinstance(row.get("acoustic_review"), dict) else None
    if not acoustic:
        return ""
    verdict = str(acoustic.get("verdict") or "unknown")
    css = "acoustic-review"
    if verdict == "listen_carefully_acoustic_drift":
        css += " acoustic-drift"
    elif verdict == "consistent_acoustic_shape":
        css += " acoustic-consistent"
    similarity = acoustic.get("min_pair_similarity")
    similarity_text = "unknown" if similarity is None else str(similarity)
    action = acoustic.get("recommended_next_action") or "Use this as reviewer evidence only."
    return f"""  <section class="{css}">
    <strong>Acoustic evidence:</strong>
    <span>{escape(verdict)}</span>
    <span>cluster min similarity {escape(similarity_text)}</span>
    <p>{escape(str(action))}</p>
    <p>Safety boundary: this is not speaker identity or auto-approval. Listen before deciding.</p>
  </section>"""


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _decision_recommended_action(status: str, speaker: str, issues: list[str]) -> str:
    if status == "pending":
        return "human_review_required"
    if status == "rejected":
        return "do_not_use_for_speaker_truth"
    if _is_unknown_review_speaker(speaker):
        return "identify_or_keep_unassigned_before_rerun"
    if "wrong_speaker" in issues:
        return "fix_speaker_label_before_rerun"
    return "use_as_reviewed_speaker_hint_or_enrollment_candidate"


def _is_unknown_review_speaker(value: Any) -> bool:
    lowered = str(value or "").lower()
    return not lowered or lowered.startswith("unknown") or lowered.startswith("unattributed") or lowered.endswith("-mentioned")


def _review_card(row: dict[str, Any], *, labels: dict[str, Any], display_mode: str = "anchor_review") -> str:
    if display_mode == "human_review":
        return _human_review_card(row, labels=labels)
    return _anchor_review_card(row, labels=labels)


def _spoken_review_controls(row: dict[str, Any]) -> str:
    index = escape(str(row.get("index")))
    parse = row.get("review_parse") if isinstance(row.get("review_parse"), dict) else {}
    parse_text = _parsed_review_text(parse)
    audio_path = str(row.get("reviewer_note_audio_path") or "")
    status = f"Saved spoken note: {audio_path}" if audio_path else "Record a plain-English note, or type one below and parse it."
    return f"""<div class="voice-review">
    <div class="voice-review-actions">
      <button type="button" class="secondary" data-record-note="{index}">Record note</button>
      <button type="button" class="secondary" data-parse-note="{index}">Parse note</button>
      <span class="voice-status" data-voice-status>{escape(status)}</span>
    </div>
    <div class="voice-waveform" aria-hidden="true"><canvas data-waveform="{index}"></canvas></div>
    <div class="parsed-review" data-parsed-review>{escape(parse_text)}</div>
  </div>"""


def _anchor_review_card(row: dict[str, Any], *, labels: dict[str, Any]) -> str:
    clip_path = row.get("clip_path")
    audio_src = _audio_src(clip_path)
    correction = row.get("suggested_speaker_correction") or _speaker_correction(
        row.get("start"), row.get("end"), row.get("target_speaker_label")
    )
    index = escape(str(row.get("index")))
    note = escape(str(row.get("reviewer_note") or ""))
    status = str(row.get("status") or "pending")
    status_label = labels["status"].get(status, status)
    approve_label = labels["buttons"]["approved"]
    reject_label = labels["buttons"]["rejected"]
    pending_label = labels["buttons"]["pending"]
    spoken_review = _spoken_review_controls(row)
    assistant_review = _assistant_review_block(row)
    acoustic_review = _acoustic_review_block(row)
    expected = row.get("expected_behavior")
    correction_rows = (
        f"""    <dt>Expected behavior</dt><dd>{escape(str(expected))}</dd>"""
        if expected
        else f"""    <dt>Correction</dt><dd><code>{escape(str(correction or ''))}</code></dd>"""
    )
    return f"""<article data-review-index="{index}" class="review-{escape(status)}" tabindex="0">
  <div class="row-head">
    <h2>Clip {index}</h2>
    <span class="status" data-status>{escape(str(status_label))}</span>
  </div>
  <audio controls preload="metadata" src="{escape(audio_src)}"></audio>
  <div class="review-controls">
    <button type="button" data-decision="approved" data-approve="{index}">{escape(str(approve_label))}</button>
    <button type="button" data-decision="rejected" class="secondary" data-reject="{index}">{escape(str(reject_label))}</button>
    <button type="button" data-decision="pending" class="secondary" data-pending="{index}">{escape(str(pending_label))}</button>
  </div>
  {assistant_review}
  {acoustic_review}
  {spoken_review}
  <textarea data-note="{index}" placeholder="Reviewer note">{note}</textarea>
  <dl>
    <dt>Time</dt><dd>{escape(str(row.get('start')))} - {escape(str(row.get('end')))} seconds</dd>
    <dt>Text</dt><dd>{escape(str(row.get('text') or ''))}</dd>
    <dt>Target</dt><dd>{escape(str(row.get('target_speaker_label') or ''))} / {escape(str(row.get('target_speaker_name') or ''))}</dd>
{correction_rows}
    <dt>Clip path</dt><dd>{escape(str(clip_path or ''))}</dd>
  </dl>
</article>"""


def _human_review_card(row: dict[str, Any], *, labels: dict[str, Any]) -> str:
    clip_path = row.get("clip_path")
    audio_src = _audio_src(clip_path)
    index = escape(str(row.get("index")))
    note = escape(str(row.get("reviewer_note") or ""))
    status = str(row.get("status") or "pending")
    status_label = labels["status"].get(status, status)
    approve_label = labels["buttons"]["approved"]
    reject_label = labels["buttons"]["rejected"]
    pending_label = labels["buttons"]["pending"]
    spoken_review = _spoken_review_controls(row)
    assistant_review = _assistant_review_block(row)
    acoustic_review = _acoustic_review_block(row)
    title = row.get("review_heading") or f"Clip {row.get('index')}"
    prompt = row.get("review_prompt") or row.get("expected_behavior") or row.get("text") or "Listen to this clip and decide whether it matches the expected behavior."
    subtitle = row.get("review_subtitle") or row.get("case") or ""
    technical_rows = [
        ("Impact rank", row.get("impact_rank") or ""),
        ("Impact score", row.get("impact_score") or ""),
        (
            "Estimated unlock",
            f"{row.get('expected_unlock_segments')} segments / {row.get('expected_unlock_seconds')} seconds"
            if row.get("expected_unlock_segments") or row.get("expected_unlock_seconds")
            else "",
        ),
        ("Time", f"{row.get('start')} - {row.get('end')} seconds"),
        ("Transcript hint", row.get("text") or ""),
        ("System label", f"{row.get('target_speaker_label') or ''} / {row.get('target_speaker_name') or ''}"),
        ("Expected behavior", row.get("expected_behavior") or ""),
        ("Clip path", clip_path or ""),
    ]
    technical = "\n".join(
        f"      <dt>{escape(str(label))}</dt><dd>{escape(str(value))}</dd>"
        for label, value in technical_rows
        if value
    )
    return f"""<article data-review-index="{index}" class="review-{escape(status)}" tabindex="0">
  <div class="row-head">
    <div>
      <h2>{escape(str(title))}</h2>
      <p class="clip-subtitle">{escape(str(subtitle))}</p>
    </div>
    <span class="status" data-status>{escape(str(status_label))}</span>
  </div>
  <p class="review-prompt">{escape(str(prompt))}</p>
  <audio controls preload="metadata" src="{escape(audio_src)}"></audio>
  <div class="review-controls" aria-label="Review decision">
    <button type="button" data-decision="approved" data-approve="{index}">{escape(str(approve_label))}</button>
    <button type="button" data-decision="rejected" class="secondary" data-reject="{index}">{escape(str(reject_label))}</button>
    <button type="button" data-decision="pending" class="secondary" data-pending="{index}">{escape(str(pending_label))}</button>
  </div>
  {assistant_review}
  {acoustic_review}
  {spoken_review}
  <textarea data-note="{index}" placeholder="Optional note">{note}</textarea>
  <details>
    <summary>Technical details</summary>
    <dl>
{technical}
    </dl>
  </details>
</article>"""


def _review_labels(sheet: dict[str, Any]) -> dict[str, Any]:
    labels = sheet.get("review_labels") or {}
    button_labels = labels.get("buttons") or {}
    status_labels = labels.get("status") or {}
    return {
        "buttons": {
            "approved": button_labels.get("approved") or "Approve",
            "rejected": button_labels.get("rejected") or "Reject",
            "pending": button_labels.get("pending") or "Pending",
        },
        "status": {
            "approved": status_labels.get("approved") or "approved",
            "rejected": status_labels.get("rejected") or "rejected",
            "pending": status_labels.get("pending") or "pending",
        },
    }


def _review_instructions(sheet: dict[str, Any], sheet_path: Path) -> str:
    lines = sheet.get("page_instructions")
    if lines:
        items = "\n".join(f"      <li>{escape(str(line))}</li>" for line in lines)
        return f"""<section class="instructions">
      <ul>
{items}
      </ul>
    </section>"""
    return f"""<section class="instructions">
      Listen for clean {escape(str(sheet.get('target_speaker_label') or 'target speaker'))} anchor clips.
      Approve only clean target-speaker clips. Reject uncertain, overlapping, noisy, or wrong-speaker clips.
      Export the reviewed JSON sheet, import it with
      <code>pavo review anchors import {escape(str(sheet_path))} ~/Downloads/{escape(sheet_path.name)}</code>,
      print the corrected decompose command with
      <code>pavo review anchors rerun-command {escape(str(sheet_path))} /path/to/pavo-decompose-manifest.json</code>,
      then rerun decomposition and regenerate the Plaud proof report.
    </section>"""


def _audio_src(clip_path: Any) -> str:
    if not clip_path:
        return ""
    path = Path(str(clip_path)).expanduser()
    if path.is_absolute():
        return path.as_uri()
    return str(path)


def _load_optional_json(path: Path | str | None) -> dict[str, Any]:
    if path is None:
        return {}
    json_path = Path(path)
    return json.loads(json_path.read_text()) if json_path.exists() else {}


def _load_first_optional_json(paths: list[Path]) -> tuple[dict[str, Any], Path | None]:
    for path in paths:
        if path.exists():
            return json.loads(path.read_text()), path
    return {}, None


def _attach_acoustic_evidence_to_next_review_plan(
    plan: list[dict[str, Any]],
    acoustic: dict[str, Any],
) -> list[dict[str, Any]]:
    if not plan:
        return plan
    clusters = {
        str(item.get("cluster_id") or ""): item
        for item in acoustic.get("clusters") or []
        if isinstance(item, dict)
    }
    rows: dict[int, dict[str, Any]] = {}
    for item in acoustic.get("rows") or []:
        if not isinstance(item, dict) or item.get("index") is None:
            continue
        try:
            rows[int(item.get("index"))] = item
        except (TypeError, ValueError):
            continue
    enriched = []
    for item in plan:
        row_index = item.get("row_index")
        try:
            row = rows.get(int(row_index))
        except (TypeError, ValueError):
            row = None
        cluster = clusters.get(str(item.get("cluster_id") or ""))
        verdict = cluster.get("verdict") if cluster else None
        if verdict == "consistent_acoustic_shape":
            caution = "Acoustic shape is consistent, but this is not identity proof."
        elif verdict in {"mixed_acoustic_shape", "listen_carefully_acoustic_drift"}:
            caution = "Listen carefully for overlap, noise, or a split cluster before approving."
        elif verdict == "insufficient_audio":
            caution = "Acoustic evidence is insufficient; rely on listening and consider replacing the sample."
        else:
            caution = "No acoustic cluster evidence is available; rely on listening."
        enriched.append(
            {
                **item,
                "acoustic_verdict": verdict,
                "acoustic_min_pair_similarity": cluster.get("min_pair_similarity") if cluster else None,
                "acoustic_average_pair_similarity": cluster.get("average_pair_similarity") if cluster else None,
                "acoustic_recommended_action": cluster.get("recommended_next_action") if cluster else None,
                "acoustic_caution": caution,
                "acoustic_signature_analyzed": bool((row or {}).get("signature", {}).get("analyzed")),
            }
        )
    return enriched


def _rank_next_review_plan_with_ensemble(plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    for item in plan:
        impact = float(item.get("impact_score") or 0.0)
        risk_points = 0
        reasons: list[str] = []
        verdict = str(item.get("acoustic_verdict") or "")
        if verdict == "listen_carefully_acoustic_drift":
            risk_points += 30
            reasons.append("acoustic drift")
        elif verdict == "mixed_acoustic_shape":
            risk_points += 15
            reasons.append("mixed acoustic shape")
        elif verdict == "insufficient_audio":
            risk_points += 20
            reasons.append("insufficient acoustic evidence")
        elif verdict == "consistent_acoustic_shape":
            reasons.append("consistent acoustic shape")
        else:
            risk_points += 10
            reasons.append("missing acoustic evidence")

        question = str(item.get("question") or "").lower()
        if " or " in question or "what speaker" in question:
            risk_points += 15
            reasons.append("ambiguous speaker question")

        min_similarity = item.get("acoustic_min_pair_similarity")
        try:
            min_similarity_value = float(min_similarity)
        except (TypeError, ValueError):
            min_similarity_value = None
        if min_similarity_value is not None and min_similarity_value < 0.75:
            risk_points += 20
            reasons.append("low pair similarity")

        priority_score = round(impact * (1.0 + (risk_points / 100.0)), 1)
        if risk_points >= 45:
            tier = "urgent_listen"
        elif risk_points >= 25:
            tier = "careful_listen"
        elif risk_points >= 10:
            tier = "normal_listen"
        else:
            tier = "straightforward"
        reason = f"{', '.join(reasons)}; impact score {impact:g}; risk boost {risk_points}%."
        enriched.append(
            {
                **item,
                "review_priority_score": priority_score,
                "review_priority_tier": tier,
                "review_priority_risk_points": risk_points,
                "review_priority_reason": reason,
            }
        )
    return sorted(
        enriched,
        key=lambda item: (
            -float(item.get("review_priority_score") or 0.0),
            int(item.get("impact_rank") or item.get("row_index") or 0),
            str(item.get("cluster_id") or ""),
        ),
    )


def _doctor_check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def _cluster_review_decision_brief_payload(status: ClusterReviewStatusResult) -> dict[str, Any]:
    items = []
    total_segments = 0
    total_seconds = 0.0
    tier_counts: dict[str, int] = {}
    for rank, item in enumerate(status.next_review_plan, start=1):
        segments, seconds = _parse_expected_impact(item.get("expected_impact"))
        if segments == 0 and seconds == 0.0 and item.get("start") is not None and item.get("end") is not None:
            segments = 1
            seconds = max(0.0, round(float(item["end"]) - float(item["start"]), 2))
        total_segments += segments
        total_seconds += seconds
        tier = str(item.get("review_priority_tier") or "standard")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        transcript = str(item.get("text") or "").strip()
        cumulative_instruction = (
            f"After this decision, the ordered review will have addressed "
            f"{total_segments} segments / {round(total_seconds, 1)} seconds if all prior decisions are resolved."
        )
        items.append(
            {
                "rank": rank,
                "row_index": item.get("row_index"),
                "cluster_id": item.get("cluster_id"),
                "target_speaker": item.get("target_speaker"),
                "question": item.get("question"),
                "expected_impact": item.get("expected_impact"),
                "unlockable_segments": segments,
                "unlockable_seconds": seconds,
                "cumulative_unlockable_segments": total_segments,
                "cumulative_unlockable_seconds": round(total_seconds, 1),
                "cumulative_review_instruction": cumulative_instruction,
                "priority_tier": tier,
                "priority_score": item.get("review_priority_score"),
                "priority_reason": item.get("review_priority_reason"),
                "acoustic_verdict": item.get("acoustic_verdict") or "unknown",
                "acoustic_min_pair_similarity": item.get("acoustic_min_pair_similarity"),
                "acoustic_caution": item.get("acoustic_caution"),
                "recommended_action": item.get("recommended_action"),
                "closure_rule": item.get("closure_rule"),
                "approve_effect": item.get("approve_effect"),
                "reject_effect": item.get("reject_effect"),
                "terminal_decision_rule": item.get("terminal_decision_rule"),
                "clip_path": item.get("clip_path"),
                "transcript_excerpt": transcript,
                "review_instruction": _cluster_review_decision_instruction(item),
            }
        )
    return {
        "batch_root": str(status.batch_root),
        "review_sheet": str(status.review_sheet_path) if status.review_sheet_path else None,
        "state": status.state,
        "summary": {
            "item_count": len(items),
            "minimum_reviews": status.review_effort.get("minimum_reviews"),
            "pending_reviews": status.review_effort.get("pending_reviews"),
            "possible_reviews_saved": status.review_effort.get("possible_reviews_saved"),
            "reduction_percent": status.review_effort.get("reduction_percent"),
            "total_unlockable_segments": total_segments,
            "total_unlockable_seconds": round(total_seconds, 1),
            "tier_counts": tier_counts,
            "top_cluster_id": status.top_cluster_id,
            "forecast_risk_adjusted_segments": status.forecast_risk_adjusted_segments,
            "estimated_unlockable_segments": status.estimated_unlockable_segments,
            "estimated_unlockable_seconds": status.estimated_unlockable_seconds,
        },
        "finish_command": status.completion_commands.get("finish_from_slate"),
        "open_review_page_command": status.completion_commands.get("open_review_page") or status.next_command,
        "safety_boundary": "Human listening is required. Pavo ranks and explains the next decisions but does not approve speaker identity automatically.",
        "blockers": status.blockers,
        "items": items,
    }


def _parse_expected_impact(value: Any) -> tuple[int, float]:
    text = str(value or "")
    match = re.search(r"(\d+)\s+segments?\s*/\s*([0-9.]+)\s+seconds?", text)
    if not match:
        return 0, 0.0
    return int(match.group(1)), float(match.group(2))


def _cluster_review_decision_instruction(item: dict[str, Any]) -> str:
    tier = str(item.get("review_priority_tier") or "")
    acoustic = str(item.get("acoustic_verdict") or "unknown")
    speaker = item.get("target_speaker") or "the proposed speaker"
    if tier == "urgent_listen" or "drift" in acoustic:
        return f"Listen carefully before approving {speaker}; reject on any contradiction or split-cluster evidence."
    if "mixed" in acoustic:
        return f"Listen for overlap/noise first, then approve {speaker} only if the voice is clearly consistent."
    return f"Approve {speaker} only after listening; reject if the sample contradicts the proposed identity."


def _render_cluster_review_decision_brief_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Pavo Cluster Review Decision Brief",
        "",
        f"- Batch root: `{payload['batch_root']}`",
        f"- State: `{payload['state']}`",
        f"- Review sheet: `{payload['review_sheet']}`",
        f"- Items needing human decisions: {summary['item_count']}",
        f"- Minimum reviews / pending clips: {summary['minimum_reviews']} / {summary['pending_reviews']}",
        f"- Review reduction: {summary['possible_reviews_saved']} clips saved ({summary['reduction_percent']}%)",
        f"- Total visible unlock if these clusters resolve: {summary['total_unlockable_segments']} segments / {summary['total_unlockable_seconds']} seconds",
        f"- Forecast risk-adjusted unlock: {summary['forecast_risk_adjusted_segments']} segments",
        f"- Safety boundary: {payload['safety_boundary']}",
        "",
        "## Ordered Review Script",
        "",
        "Work top to bottom. Each decision is chosen to unlock the most transcript coverage per human listen while still respecting acoustic risk.",
        "",
        "## Commands",
        "",
        f"- Open review page: `{payload['open_review_page_command']}`",
        f"- Finish from reviewed TSV: `{payload['finish_command']}`",
        "",
        "## Priority Mix",
        "",
    ]
    tier_counts = summary.get("tier_counts") or {}
    if tier_counts:
        for tier, count in sorted(tier_counts.items()):
            lines.append(f"- `{tier}`: {count}")
    else:
        lines.append("- None")
    if payload.get("blockers"):
        lines.extend(["", "## Current Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in payload["blockers"])
    lines.extend(["", "## Ranked Decisions", ""])
    if not payload["items"]:
        lines.append("- No review items remain.")
        return "\n".join(lines).rstrip() + "\n"
    for item in payload["items"]:
        transcript = str(item.get("transcript_excerpt") or "")
        if len(transcript) > 260:
            transcript = transcript[:257].rstrip() + "..."
        lines.extend(
            [
                f"### {item['rank']}. Cluster `{item['cluster_id']}` row `{item['row_index']}`",
                "",
                f"- Question: {item['question']}",
                f"- Target speaker: `{item['target_speaker']}`",
                f"- Expected unlock: {item['unlockable_segments']} segments / {item['unlockable_seconds']} seconds",
                f"- Cumulative unlock after this step: {item['cumulative_unlockable_segments']} segments / {item['cumulative_unlockable_seconds']} seconds",
                f"- Priority: `{item['priority_tier']}` / {item['priority_score']}",
                f"- Why: {item['priority_reason']}",
                f"- Step guidance: {item['cumulative_review_instruction']}",
                f"- Acoustic verdict: `{item['acoustic_verdict']}`; min similarity: {item['acoustic_min_pair_similarity']}",
                f"- Reviewer instruction: {item['review_instruction']}",
                f"- Closure rule: {item['closure_rule']}",
                f"- Approve effect: {item['approve_effect']}",
                f"- Reject effect: {item['reject_effect']}",
                f"- Clip: `{item['clip_path']}`",
                f"- Transcript: {transcript or 'None'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_cluster_review_decision_brief_html(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    review_key = json.dumps(f"pavo-cluster-decision-brief:{payload.get('review_sheet')}")
    tier_counts = summary.get("tier_counts") or {}
    tier_bits = "".join(
        f'<span class="pill">{escape(str(tier))}: {count}</span>'
        for tier, count in sorted(tier_counts.items())
    ) or '<span class="pill">none</span>'
    blockers = payload.get("blockers") or []
    blocker_bits = "".join(f"<li>{escape(str(blocker))}</li>" for blocker in blockers) or "<li>None</li>"
    item_cards = []
    for item in payload.get("items") or []:
        transcript = str(item.get("transcript_excerpt") or "")
        if len(transcript) > 360:
            transcript = transcript[:357].rstrip() + "..."
        audio_src = _audio_src(item.get("clip_path"))
        row_index = escape(str(item.get("row_index") or ""))
        cluster_id = escape(str(item.get("cluster_id") or ""))
        target_speaker = escape(str(item.get("target_speaker") or ""))
        metadata = {
            "priority_tier": item.get("priority_tier"),
            "priority_score": item.get("priority_score"),
            "priority_reason": item.get("priority_reason"),
            "question": item.get("question"),
            "expected_impact": item.get("expected_impact"),
            "unlockable_segments": item.get("unlockable_segments"),
            "unlockable_seconds": item.get("unlockable_seconds"),
            "cumulative_unlockable_segments": item.get("cumulative_unlockable_segments"),
            "cumulative_unlockable_seconds": item.get("cumulative_unlockable_seconds"),
            "acoustic_verdict": item.get("acoustic_verdict"),
            "clip_path": item.get("clip_path"),
            "transcript": item.get("transcript_excerpt"),
        }
        metadata_json = escape(json.dumps(metadata, sort_keys=True))
        item_cards.append(
            f"""
      <article class="card {escape(str(item.get('priority_tier') or 'standard'))}" data-review-card data-row-index="{row_index}" data-cluster-id="{cluster_id}" data-metadata="{metadata_json}">
        <div class="card-top">
          <div>
            <p class="eyebrow">Decision {item.get('rank')} · cluster {escape(str(item.get('cluster_id')))}</p>
            <h2>{escape(str(item.get('question') or 'Review cluster'))}</h2>
          </div>
          <span class="badge">{escape(str(item.get('priority_tier') or 'standard'))}</span>
        </div>
        <div class="metrics">
          <div><strong>{item.get('unlockable_segments')}</strong><span>segments</span></div>
          <div><strong>{item.get('unlockable_seconds')}</strong><span>seconds</span></div>
          <div><strong>{escape(str(item.get('priority_score')))}</strong><span>priority</span></div>
        </div>
        <p class="step-guidance">{escape(str(item.get('cumulative_review_instruction') or ''))}</p>
        <audio controls preload="metadata" src="{escape(audio_src)}"></audio>
        <div class="decision-controls">
          <label><input type="radio" name="decision-{row_index}" value="approved"> Approve</label>
          <label><input type="radio" name="decision-{row_index}" value="rejected"> Reject</label>
          <label><input type="radio" name="decision-{row_index}" value="pending" checked> Pending</label>
          <label class="speaker-field">Speaker <input data-speaker value="{target_speaker}" aria-label="Speaker for row {row_index}"></label>
        </div>
        <textarea data-note placeholder="Reviewer note, especially if rejecting or changing speaker"></textarea>
        <dl>
          <dt>Target</dt><dd>{escape(str(item.get('target_speaker') or 'unknown'))}</dd>
          <dt>Acoustic</dt><dd>{escape(str(item.get('acoustic_verdict')))} · min similarity {escape(str(item.get('acoustic_min_pair_similarity')))}</dd>
          <dt>Instruction</dt><dd>{escape(str(item.get('review_instruction') or 'Listen before deciding.'))}</dd>
          <dt>Approve</dt><dd>{escape(str(item.get('approve_effect') or ''))}</dd>
          <dt>Reject</dt><dd>{escape(str(item.get('reject_effect') or ''))}</dd>
        </dl>
        <blockquote>{escape(transcript or 'No transcript excerpt')}</blockquote>
        <p class="clip">{escape(str(item.get('clip_path') or ''))}</p>
      </article>"""
        )
    cards = "\n".join(item_cards) or "<p>No review items remain.</p>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pavo Cluster Review Decision Brief</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #172033;
      --muted: #667085;
      --line: #d9e0ea;
      --soft: #f6f8fb;
      --blue: #2563eb;
      --amber: #b45309;
      --red: #b42318;
      --green: #047857;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #eef3f8; color: var(--ink); font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
    header {{ background: white; border: 1px solid var(--line); border-radius: 22px; padding: 26px; box-shadow: 0 18px 50px rgba(15, 23, 42, 0.08); }}
    h1 {{ margin: 0 0 8px; font-size: 34px; letter-spacing: -0.04em; }}
    h2 {{ margin: 0; font-size: 20px; letter-spacing: -0.02em; }}
    .subtle {{ color: var(--muted); margin: 0; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 22px 0; }}
    .stat {{ background: var(--soft); border: 1px solid var(--line); border-radius: 16px; padding: 15px; }}
    .stat strong {{ display: block; font-size: 25px; }}
    .stat span {{ color: var(--muted); }}
    .commands, .blockers {{ background: white; border: 1px solid var(--line); border-radius: 18px; padding: 18px; margin: 18px 0; }}
    .export-panel {{ background: #fffdf5; border: 1px solid #f2d79b; border-radius: 18px; padding: 18px; margin: 18px 0; }}
    .completion-summary {{ display: inline-block; border-radius: 999px; padding: 8px 12px; font-weight: 850; background: #fff7ed; color: #9a3412; }}
    .completion-summary.ready {{ background: #ecfdf3; color: #027a48; }}
    .completion-summary.incomplete {{ background: #fff7ed; color: #9a3412; }}
    .impact-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 12px 0 14px; }}
    .impact-cell {{ border: 1px solid #fed7aa; background: #fffbeb; border-radius: 14px; padding: 10px; }}
    .impact-cell strong {{ display: block; font-size: 19px; }}
    .impact-cell span {{ color: var(--muted); font-size: 12px; }}
    code {{ background: #f1f5f9; border: 1px solid #dbe3ee; border-radius: 8px; padding: 2px 5px; overflow-wrap: anywhere; }}
    button {{ border: 0; border-radius: 12px; background: var(--blue); color: white; padding: 10px 14px; font-weight: 800; cursor: pointer; margin-right: 8px; }}
    button.secondary {{ background: #475467; }}
    textarea {{ width: 100%; min-height: 74px; border: 1px solid var(--line); border-radius: 12px; padding: 10px; font: inherit; margin: 10px 0 12px; }}
    input[type="text"], .speaker-field input {{ border: 1px solid var(--line); border-radius: 10px; padding: 7px 9px; font: inherit; min-width: 140px; }}
    .pill, .badge {{ display: inline-flex; align-items: center; border-radius: 999px; padding: 5px 10px; margin: 4px 6px 4px 0; font-weight: 700; background: #e8f0ff; color: #1d4ed8; }}
    .cards {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin-top: 20px; }}
    .card {{ background: white; border: 1px solid var(--line); border-left: 7px solid var(--blue); border-radius: 22px; padding: 20px; box-shadow: 0 12px 35px rgba(15, 23, 42, 0.07); }}
    .card.active {{ outline: 4px solid rgba(37, 99, 235, 0.22); box-shadow: 0 18px 45px rgba(37, 99, 235, 0.16); }}
    .card.urgent_listen {{ border-left-color: var(--red); }}
    .card.careful_listen {{ border-left-color: var(--amber); }}
    .card.normal_listen {{ border-left-color: var(--green); }}
    .card-top {{ display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }}
    .eyebrow {{ margin: 0 0 4px; color: var(--muted); text-transform: uppercase; font-size: 11px; font-weight: 800; letter-spacing: 0.08em; }}
    .metrics {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 16px 0; }}
    .metrics div {{ background: var(--soft); border-radius: 14px; padding: 11px; }}
    .metrics strong {{ display: block; font-size: 20px; }}
    .metrics span {{ color: var(--muted); font-size: 12px; }}
    .step-guidance {{ background: #eff6ff; border: 1px solid #bfdbfe; color: #1e3a8a; border-radius: 14px; padding: 10px 12px; font-weight: 750; }}
    audio {{ width: 100%; margin: 8px 0 14px; }}
    .decision-controls {{ display: flex; flex-wrap: wrap; gap: 10px 14px; align-items: center; padding: 12px; background: #f8fafc; border: 1px solid var(--line); border-radius: 14px; margin-bottom: 10px; }}
    .decision-controls label {{ font-weight: 750; }}
    .speaker-field {{ margin-left: auto; }}
    dl {{ display: grid; grid-template-columns: 88px 1fr; gap: 8px 12px; margin: 0; }}
    dt {{ color: var(--muted); font-weight: 800; }}
    dd {{ margin: 0; }}
    blockquote {{ margin: 16px 0 0; padding: 12px 14px; background: #f8fafc; border-left: 4px solid #cbd5e1; border-radius: 10px; }}
    .clip {{ color: var(--muted); font-size: 11px; overflow-wrap: anywhere; }}
    .shortcut-grid {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
    .shortcut-grid span {{ background: #eef2ff; color: #3730a3; border-radius: 999px; padding: 5px 9px; font-weight: 800; }}
    @media print {{
      body {{ background: white; }}
      main {{ max-width: none; padding: 0; }}
      header, .commands, .blockers, .card {{ box-shadow: none; break-inside: avoid; }}
      .export-panel {{ display: none; }}
      .cards {{ grid-template-columns: 1fr; }}
      audio {{ display: none; }}
    }}
    @media (max-width: 900px) {{
      .grid, .cards {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <p class="eyebrow">Pavo Active Speaker Correction</p>
      <h1>Cluster Review Decision Brief</h1>
      <p class="subtle">{escape(str(payload.get('safety_boundary')))}</p>
      <div class="grid">
        <div class="stat"><strong>{summary.get('item_count')}</strong><span>human decisions</span></div>
        <div class="stat"><strong>{summary.get('total_unlockable_segments')}</strong><span>visible segments</span></div>
        <div class="stat"><strong>{summary.get('total_unlockable_seconds')}</strong><span>visible seconds</span></div>
        <div class="stat"><strong>{summary.get('forecast_risk_adjusted_segments')}</strong><span>risk-adjusted segments</span></div>
      </div>
      <div>{tier_bits}</div>
    </header>
    <section class="commands">
      <h2>Commands</h2>
      <p>Open full review page: <code>{escape(str(payload.get('open_review_page_command') or ''))}</code></p>
      <p>Finish after TSV review: <code>{escape(str(payload.get('finish_command') or ''))}</code></p>
    </section>
    <section class="export-panel">
      <h2>Decision Export</h2>
      <p>Mark each card, adjust speaker if needed, add notes, then export the TSV. The output is compatible with <code>pavo review clusters finish-from-slate</code>.</p>
      <p id="completion-summary" class="completion-summary">Pending review...</p>
      <div class="impact-grid" aria-label="Live decision impact">
        <div class="impact-cell"><strong id="approved-impact">0 / 0.0s</strong><span>approved unlock</span></div>
        <div class="impact-cell"><strong id="rejected-impact">0 / 0.0s</strong><span>rejected/blocked</span></div>
        <div class="impact-cell"><strong id="pending-impact">0 / 0.0s</strong><span>still undecided</span></div>
        <div class="impact-cell"><strong id="review-impact">0%</strong><span>impact reviewed</span></div>
      </div>
      <button type="button" id="export-tsv">Export reviewed TSV</button>
      <button type="button" class="secondary" id="copy-tsv">Copy TSV</button>
      <button type="button" class="secondary" id="reset-decisions">Reset to pending</button>
      <button type="button" class="secondary" id="clear-saved">Clear saved local decisions</button>
      <div class="shortcut-grid" aria-label="Keyboard shortcuts">
        <span>A approve</span><span>R reject</span><span>P pending</span><span>J next</span><span>K previous</span><span>Space play/pause</span>
      </div>
      <textarea id="tsv-output" aria-label="Generated decision TSV" placeholder="Generated TSV appears here"></textarea>
    </section>
    <section class="blockers">
      <h2>Current Blockers</h2>
      <ul>{blocker_bits}</ul>
    </section>
    <section class="cards">
      {cards}
    </section>
  </main>
  <script>
    const STORAGE_KEY = {review_key};
    const HEADERS = ["row_index", "cluster_id", "decision", "speaker", "note", "priority_tier", "priority_score", "priority_reason", "question", "expected_impact", "acoustic_verdict", "clip_path", "transcript"];
    function cell(value) {{
      return String(value ?? "").replace(/\\t/g, " ").replace(/\\r?\\n/g, " ").trim();
    }}
    function selectedDecision(card) {{
      const selected = card.querySelector("input[type=radio]:checked");
      return selected ? selected.value : "pending";
    }}
    function rowFromCard(card) {{
      const metadata = JSON.parse(card.dataset.metadata || "{{}}");
      return {{
        row_index: card.dataset.rowIndex || "",
        cluster_id: card.dataset.clusterId || "",
        decision: selectedDecision(card),
        speaker: (card.querySelector("[data-speaker]") || {{ value: "" }}).value,
        note: (card.querySelector("[data-note]") || {{ value: "" }}).value,
        priority_tier: metadata.priority_tier,
        priority_score: metadata.priority_score,
        priority_reason: metadata.priority_reason,
        question: metadata.question,
        expected_impact: metadata.expected_impact,
        unlockable_segments: Number(metadata.unlockable_segments || 0),
        unlockable_seconds: Number(metadata.unlockable_seconds || 0),
        acoustic_verdict: metadata.acoustic_verdict,
        clip_path: metadata.clip_path,
        transcript: metadata.transcript
      }};
    }}
    function currentRows() {{
      return Array.from(document.querySelectorAll("[data-review-card]")).map(rowFromCard);
    }}
    function cards() {{
      return Array.from(document.querySelectorAll("[data-review-card]"));
    }}
    function activeCard() {{
      return document.querySelector("[data-review-card].active") || cards()[0] || null;
    }}
    function setActiveCard(card, scroll = true) {{
      if (!card) return;
      cards().forEach(item => item.classList.toggle("active", item === card));
      if (scroll) card.scrollIntoView({{ behavior: "smooth", block: "center" }});
    }}
    function moveActive(delta) {{
      const all = cards();
      if (!all.length) return;
      const current = activeCard();
      const index = Math.max(0, all.indexOf(current));
      const next = all[Math.max(0, Math.min(all.length - 1, index + delta))];
      setActiveCard(next);
    }}
    function setDecision(card, decision) {{
      if (!card) return;
      const radio = card.querySelector(`input[type=radio][value="${{decision}}"]`);
      if (radio) {{
        radio.checked = true;
        writeTsv();
      }}
    }}
    function toggleAudio(card) {{
      const audio = card ? card.querySelector("audio") : null;
      if (!audio) return;
      document.querySelectorAll("audio").forEach(item => {{ if (item !== audio) item.pause(); }});
      if (audio.paused) audio.play().catch(() => {{}});
      else audio.pause();
    }}
    function buildTsv() {{
      const rows = currentRows();
      return [HEADERS.join("\\t"), ...rows.map(row => HEADERS.map(key => cell(row[key])).join("\\t"))].join("\\n") + "\\n";
    }}
    function completion(rows = currentRows()) {{
      return rows.reduce((acc, row) => {{
        acc.total += 1;
        acc[row.decision] = (acc[row.decision] || 0) + 1;
        if (row.decision !== "pending") acc.reviewed += 1;
        return acc;
      }}, {{ total: 0, reviewed: 0, approved: 0, rejected: 0, pending: 0 }});
    }}
    function writeCompletion(rows = currentRows()) {{
      const stats = completion(rows);
      const summary = document.getElementById("completion-summary");
      const done = stats.pending === 0 && stats.total > 0;
      summary.textContent = `${{stats.reviewed}}/${{stats.total}} reviewed · ${{stats.approved}} approved · ${{stats.rejected}} rejected · ${{stats.pending}} pending${{done ? " · ready to export" : " · incomplete"}}`;
      summary.classList.toggle("ready", done);
      summary.classList.toggle("incomplete", !done);
      writeImpact(rows);
      return stats;
    }}
    function formatImpact(segments, seconds) {{
      return `${{Math.round(segments)}} / ${{Number(seconds || 0).toFixed(1)}}s`;
    }}
    function writeImpact(rows = currentRows()) {{
      const totals = rows.reduce((acc, row) => {{
        const bucket = row.decision === "approved" ? "approved" : row.decision === "rejected" ? "rejected" : "pending";
        acc[bucket].segments += Number(row.unlockable_segments || 0);
        acc[bucket].seconds += Number(row.unlockable_seconds || 0);
        acc.total.segments += Number(row.unlockable_segments || 0);
        acc.total.seconds += Number(row.unlockable_seconds || 0);
        return acc;
      }}, {{
        approved: {{ segments: 0, seconds: 0 }},
        rejected: {{ segments: 0, seconds: 0 }},
        pending: {{ segments: 0, seconds: 0 }},
        total: {{ segments: 0, seconds: 0 }}
      }});
      const reviewedSegments = totals.approved.segments + totals.rejected.segments;
      const reviewedPercent = totals.total.segments ? Math.round((reviewedSegments / totals.total.segments) * 100) : 0;
      document.getElementById("approved-impact").textContent = formatImpact(totals.approved.segments, totals.approved.seconds);
      document.getElementById("rejected-impact").textContent = formatImpact(totals.rejected.segments, totals.rejected.seconds);
      document.getElementById("pending-impact").textContent = formatImpact(totals.pending.segments, totals.pending.seconds);
      document.getElementById("review-impact").textContent = `${{reviewedPercent}}%`;
    }}
    function saveLocal() {{
      const decisions = currentRows().map(row => ({{
        row_index: row.row_index,
        decision: row.decision,
        speaker: row.speaker,
        note: row.note
      }}));
      localStorage.setItem(STORAGE_KEY, JSON.stringify({{ saved_at: new Date().toISOString(), decisions }}));
    }}
    function restoreLocal() {{
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      let saved;
      try {{ saved = JSON.parse(raw); }} catch (error) {{ return; }}
      const byRow = new Map((saved.decisions || []).map(item => [String(item.row_index), item]));
      document.querySelectorAll("[data-review-card]").forEach(card => {{
        const savedRow = byRow.get(String(card.dataset.rowIndex || ""));
        if (!savedRow) return;
        const radio = card.querySelector(`input[type=radio][value="${{savedRow.decision || "pending"}}"]`);
        if (radio) radio.checked = true;
        const speaker = card.querySelector("[data-speaker]");
        if (speaker && savedRow.speaker !== undefined) speaker.value = savedRow.speaker;
        const note = card.querySelector("[data-note]");
        if (note && savedRow.note !== undefined) note.value = savedRow.note;
      }});
    }}
    function writeTsv() {{
      const output = document.getElementById("tsv-output");
      output.value = buildTsv();
      writeCompletion();
      saveLocal();
      return output.value;
    }}
    document.getElementById("export-tsv").addEventListener("click", () => {{
      const stats = writeCompletion();
      if (stats.pending > 0 && !confirm(`${{stats.pending}} decisions are still pending. Export anyway?`)) return;
      const text = writeTsv();
      const blob = new Blob([text], {{ type: "text/tab-separated-values" }});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "pavo-cluster-review-decision-slate.reviewed.tsv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    }});
    document.getElementById("copy-tsv").addEventListener("click", async () => {{
      const text = writeTsv();
      if (navigator.clipboard) await navigator.clipboard.writeText(text);
    }});
    document.getElementById("reset-decisions").addEventListener("click", () => {{
      document.querySelectorAll("[data-review-card]").forEach(card => {{
        const pending = card.querySelector("input[value=pending]");
        if (pending) pending.checked = true;
        const note = card.querySelector("[data-note]");
        if (note) note.value = "";
      }});
      writeTsv();
    }});
    document.getElementById("clear-saved").addEventListener("click", () => {{
      localStorage.removeItem(STORAGE_KEY);
      alert("Saved local decisions cleared for this review sheet.");
    }});
    document.querySelectorAll("[data-review-card] input, [data-review-card] textarea").forEach(element => {{
      element.addEventListener("change", writeTsv);
      element.addEventListener("input", writeTsv);
    }});
    cards().forEach(card => {{
      card.addEventListener("click", event => {{
        if (event.target && ["TEXTAREA", "INPUT", "BUTTON"].includes(event.target.tagName)) return;
        setActiveCard(card, false);
      }});
    }});
    document.addEventListener("keydown", event => {{
      if (event.target && ["TEXTAREA", "INPUT"].includes(event.target.tagName)) return;
      const key = event.key.toLowerCase();
      if (key === "a") {{ event.preventDefault(); setDecision(activeCard(), "approved"); }}
      if (key === "r") {{ event.preventDefault(); setDecision(activeCard(), "rejected"); }}
      if (key === "p") {{ event.preventDefault(); setDecision(activeCard(), "pending"); }}
      if (key === "j") {{ event.preventDefault(); moveActive(1); }}
      if (key === "k") {{ event.preventDefault(); moveActive(-1); }}
      if (event.key === " ") {{ event.preventDefault(); toggleAudio(activeCard()); }}
    }});
    restoreLocal();
    setActiveCard(cards()[0], false);
    writeTsv();
  </script>
</body>
</html>
"""


def _render_cluster_review_slate_markdown(status: ClusterReviewStatusResult) -> str:
    lines = [
        "# Pavo Cluster Review Decision Slate",
        "",
        f"- Batch root: `{status.batch_root}`",
        f"- Review sheet: `{status.review_sheet_path}`",
        f"- State: `{status.state}`",
        f"- Minimum reviews: {status.next_review_count}",
        f"- Review effort: {status.review_effort.get('summary')}",
        f"- Safety boundary: this slate asks for human decisions. It does not approve identity or mutate evidence.",
        "",
        "Decision values for TSV: `approved`, `rejected`, or `pending`.",
        "",
    ]
    if status.blockers:
        lines.extend(["## Current Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in status.blockers)
        lines.append("")
    lines.extend(["## Review Items", ""])
    if not status.next_review_plan:
        lines.append("- No review items remain.")
        return "\n".join(lines).rstrip() + "\n"
    for item in status.next_review_plan:
        transcript = str(item.get("text") or "").strip()
        if len(transcript) > 260:
            transcript = transcript[:257].rstrip() + "..."
        lines.extend(
            [
                f"### {item.get('cluster_id')} row {item.get('row_index')} - {item.get('target_speaker')}",
                "",
                f"- Priority: `{item.get('review_priority_tier')}` / {item.get('review_priority_score')}",
                f"- Why this is next: {item.get('review_priority_reason')}",
                f"- Question: {item.get('question')}",
                f"- Expected impact: {item.get('expected_impact')}",
                f"- Acoustic verdict: `{item.get('acoustic_verdict') or 'unknown'}`",
                f"- Acoustic caution: {item.get('acoustic_caution')}",
                f"- Closure rule: {item.get('closure_rule')}",
                f"- Approve effect: {item.get('approve_effect')}",
                f"- Reject effect: {item.get('reject_effect')}",
                f"- Clip: `{item.get('clip_path')}`",
                f"- Transcript: {transcript or 'None'}",
                "",
                "Fill in TSV row with:",
                "- `decision`: approved/rejected/pending",
                "- `speaker`: the correct speaker name/label if known",
                "- `note`: short reason, especially if rejecting",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_cluster_review_slate_tsv(status: ClusterReviewStatusResult) -> str:
    headers = [
        "row_index",
        "cluster_id",
        "decision",
        "speaker",
        "note",
        "priority_tier",
        "priority_score",
        "priority_reason",
        "question",
        "expected_impact",
        "acoustic_verdict",
        "clip_path",
        "transcript",
    ]
    rows = ["\t".join(headers)]
    for item in status.next_review_plan:
        values = [
            item.get("row_index"),
            item.get("cluster_id"),
            "pending",
            item.get("target_speaker"),
            "",
            item.get("review_priority_tier"),
            item.get("review_priority_score"),
            item.get("review_priority_reason"),
            item.get("question"),
            item.get("expected_impact"),
            item.get("acoustic_verdict"),
            item.get("clip_path"),
            item.get("text"),
        ]
        rows.append("\t".join(_tsv_cell(value) for value in values))
    return "\n".join(rows).rstrip() + "\n"


def _read_cluster_review_slate_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"row_index", "cluster_id", "decision", "speaker", "note"}
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(required - fieldnames)
        if missing:
            raise ValueError(f"slate TSV missing required column(s): {', '.join(missing)}")
        return [dict(row) for row in reader]


def _tsv_cell(value: Any) -> str:
    return str(value or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def _bundle_clip_name(row: dict[str, Any], source: Path) -> str:
    index = row.get("index")
    prefix = f"candidate-{int(index):02d}" if isinstance(index, int) else f"candidate-{index or 'unknown'}"
    return f"{prefix}{source.suffix or '.wav'}"


class _ReviewPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.audio_count = 0
        self.approve_count = 0
        self.reject_count = 0
        self.pending_button_count = 0
        self.note_count = 0
        self.export_button_present = False
        self.reset_button_present = False
        self.shortcut_panel_present = False
        self._in_review_sheet_script = False
        self._review_sheet_chunks: list[str] = []

    @property
    def review_sheet_json(self) -> str:
        return "".join(self._review_sheet_chunks).strip()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "audio":
            self.audio_count += 1
        if "data-approve" in attr:
            self.approve_count += 1
        if "data-reject" in attr:
            self.reject_count += 1
        if "data-pending" in attr:
            self.pending_button_count += 1
        if "data-note" in attr:
            self.note_count += 1
        if attr.get("id") == "export-json":
            self.export_button_present = True
        if attr.get("id") == "reset-review":
            self.reset_button_present = True
        if attr.get("id") == "shortcut-panel":
            self.shortcut_panel_present = True
        if tag == "script" and attr.get("id") == "review-sheet-data":
            self._in_review_sheet_script = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_review_sheet_script = False

    def handle_data(self, data: str) -> None:
        if self._in_review_sheet_script:
            self._review_sheet_chunks.append(data)


def _format_seconds(value: Any) -> str:
    seconds = max(0, int(round(float(value))))
    minutes, second = divmod(seconds, 60)
    hour, minute = divmod(minutes, 60)
    if hour:
        return f"{hour:02d}:{minute:02d}:{second:02d}"
    return f"{minute:02d}:{second:02d}"
