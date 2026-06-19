from __future__ import annotations

from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import shlex
import shutil
import time
from html.parser import HTMLParser
from html import escape
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .brief import (
    _apply_temporal_speaker_continuity,
    _ensemble_speaker_segments,
    _is_unknown_speaker,
    _load_diarization_segments,
    _load_named_evidence_segments,
    _load_speaker_attribution_segments,
    _rounded_time,
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


def create_anchor_review_page(
    review_sheet_path: Path | str,
    *,
    out_path: Path | str | None = None,
) -> AnchorReviewPageResult:
    sheet_path = Path(review_sheet_path)
    sheet = json.loads(sheet_path.read_text())
    page_path = Path(out_path) if out_path else sheet_path.with_suffix(".html")
    rows = sheet.get("rows", [])
    pending = [row for row in rows if row.get("status") == "pending"]
    labels = _review_labels(sheet)
    display_mode = sheet.get("display_mode") or "anchor_review"
    cards = "\n".join(_review_card(row, labels=labels, display_mode=display_mode) for row in rows)
    sheet_json = json.dumps(sheet).replace("</", "<\\/")
    download_name_json = json.dumps(sheet_path.name)
    title = sheet.get("review_title") or f"Pavo Anchor Review - {sheet.get('target_speaker_name') or sheet.get('target_speaker_label') or 'Speaker'}"
    instructions = _review_instructions(sheet, sheet_path)
    export_label = sheet.get("export_label") or "Export reviewed JSON"
    reset_label = sheet.get("reset_label") or "Reset page decisions"
    status_labels_json = json.dumps(labels["status"])
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
    .actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      margin: 18px 0;
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
    <section class="actions">
      <button type="button" id="save-review">Save review</button>
      <button type="button" id="export-json">{escape(str(export_label))}</button>
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

    function setSaveStatus(message) {{
      document.getElementById("save-status").textContent = message;
    }}

    function markDirty() {{
      dirty = true;
      setSaveStatus(backendAvailable ? "Unsaved changes" : "File mode: export review notes");
      if (backendAvailable) {{
        clearTimeout(saveTimer);
        saveTimer = setTimeout(() => saveReview(), 450);
      }}
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
      setSaveStatus(`Saved: ${{payload.approved_count}} works, ${{payload.rejected_count}} problems, ${{payload.pending_count}} unsure`);
    }}

    function exportReviewedSheet() {{
      const blob = new Blob([JSON.stringify(buildReviewedSheet(), null, 2) + "\\n"], {{ type: "application/json" }});
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = {download_name_json};
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
    }}

    function applyDecisionToCard(card, status) {{
      card.classList.remove("review-approved", "review-rejected", "review-pending");
      card.classList.add(`review-${{status}}`);
      card.querySelector("[data-status]").textContent = statusLabels[status] || status;
      card.querySelectorAll("[data-decision]").forEach((button) => {{
        button.classList.toggle("active", button.dataset.decision === status);
      }});
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
    checks = {
        "export button": parser.export_button_present,
        "reset button": parser.reset_button_present,
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
    expected = row.get("expected_behavior")
    correction_rows = (
        f"""    <dt>Expected behavior</dt><dd>{escape(str(expected))}</dd>"""
        if expected
        else f"""    <dt>Correction</dt><dd><code>{escape(str(correction or ''))}</code></dd>"""
    )
    return f"""<article data-review-index="{index}" class="review-{escape(status)}">
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
    title = row.get("review_heading") or f"Clip {row.get('index')}"
    prompt = row.get("review_prompt") or row.get("expected_behavior") or row.get("text") or "Listen to this clip and decide whether it matches the expected behavior."
    subtitle = row.get("review_subtitle") or row.get("case") or ""
    technical_rows = [
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
    return f"""<article data-review-index="{index}" class="review-{escape(status)}">
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
