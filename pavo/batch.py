from __future__ import annotations

import csv
import hashlib
import json
import shlex
import shutil
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

from .review import finish_cluster_review_from_slate, gate_cluster_review, validate_cluster_review_slate


SOURCE_REQUIRED_FILES = [
    "audio",
    "transcript_json",
    "transcript_markdown",
    "diarized_markdown",
    "speaker_attributed_markdown",
    "readme",
    "fetch_manifest",
]

GENERATED_ARTIFACT_PATHS = {
    "run_report": "pavo-run-report.json",
    "meeting_brief": "pavo-meeting-brief.json",
    "diarization_segments": "_work/diarization-segments.json",
    "speaker_attribution": "_work/speaker-attribution.json",
    "named_speaker_evidence": "_work/named-speaker-evidence.json",
    "cluster_gate_json": "pavo-cluster-review-gate.json",
    "cluster_gate_markdown": "pavo-cluster-review-gate.md",
    "cluster_review_page": "pavo-cluster-question-bundle/index.html",
    "cluster_review_sheet": "pavo-cluster-question-bundle/pavo-cluster-question-review-sheet.json",
    "cluster_acoustic_evidence": "pavo-cluster-question-bundle/pavo-cluster-question-acoustic-evidence.json",
    "cluster_forecast": "pavo-cluster-question-bundle/pavo-cluster-review-forecast.json",
    "cluster_slate_tsv": "pavo-cluster-question-bundle/pavo-cluster-review-decision-slate.tsv",
    "cluster_slate_markdown": "pavo-cluster-question-bundle/pavo-cluster-review-decision-slate.md",
    "cluster_validation": "pavo-cluster-question-bundle/pavo-cluster-review-validation.json",
    "cluster_decision_brief": "pavo-cluster-question-bundle/pavo-cluster-review-decision-brief.html",
}

BATCH_SPEAKER_DECISION_RUBRIC = [
    "Approve only when every supporting clip sounds like the named speaker and the transcript context does not contradict that identity.",
    "Reject when any supporting clip is the wrong speaker, too overlapped, too noisy, or clearly contradicts the proposed identity.",
    "Keep pending when the clips disagree, the speaker is uncertain, or another listener should make the call.",
]

BATCH_SPEAKER_REVIEW_REASONS = {
    "approved_clean_match": "approved: every clip matches the named speaker",
    "approved_speaker_corrected": "approved: speaker label corrected by reviewer",
    "rejected_wrong_speaker": "rejected: one or more clips are the wrong speaker",
    "rejected_overlap_or_noise": "rejected: overlap, noise, or low quality makes identity unsafe",
    "rejected_context_contradiction": "rejected: transcript context contradicts the proposed identity",
    "pending_uncertain": "pending: reviewer is uncertain",
    "pending_clips_disagree": "pending: supporting clips disagree",
    "pending_second_listener": "pending: needs another listener",
}


@dataclass(frozen=True)
class BatchDoctorResult:
    batch_root: Path
    passed: bool
    complete: bool
    state: str
    source_recording_count: int
    source_recordings: list[dict[str, Any]]
    source_manifest_sha256: str | None
    generated_artifacts: dict[str, dict[str, Any]]
    generated_manifest_sha256: str | None
    checks: list[dict[str, Any]]
    blockers: list[str]
    next_command: str
    cluster_gate: dict[str, Any] | None

    def as_report(self) -> dict[str, Any]:
        return {
            "batch_root": str(self.batch_root),
            "passed": self.passed,
            "complete": self.complete,
            "state": self.state,
            "source_recording_count": self.source_recording_count,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_recordings": self.source_recordings,
            "generated_artifacts": self.generated_artifacts,
            "generated_manifest_sha256": self.generated_manifest_sha256,
            "checks": self.checks,
            "blockers": self.blockers,
            "next_command": self.next_command,
            "cluster_gate": self.cluster_gate,
            "safety_boundary": "Batch doctor proves source and machine artifact coverage. It does not approve speaker identity or replace required human listening gates.",
        }

    def as_markdown(self) -> str:
        lines = [
            "# Pavo Batch Doctor",
            "",
            f"- Batch root: `{self.batch_root}`",
            f"- State: `{self.state}`",
            f"- Machine plumbing passed: `{str(self.passed).lower()}`",
            f"- Complete: `{str(self.complete).lower()}`",
            f"- Source recordings: {self.source_recording_count}",
            f"- Source manifest SHA-256: `{self.source_manifest_sha256}`",
            f"- Generated manifest SHA-256: `{self.generated_manifest_sha256}`",
            f"- Next command: `{self.next_command}`",
            "",
            "## Checks",
            "",
        ]
        for check in self.checks:
            status = "pass" if check.get("passed") else "fail"
            lines.append(f"- `{status}` {check.get('name')}: {check.get('detail')}")
        lines.extend(["", "## Source Recordings", ""])
        if self.source_recordings:
            for item in self.source_recordings:
                missing = ", ".join(item.get("missing") or []) or "none"
                lines.append(
                    f"- `{item.get('recording_id')}`: audio `{item.get('audio_present')}`, "
                    f"transcript `{item.get('transcript_json_present')}`, diarized `{item.get('diarized_markdown_present')}`, "
                    f"attributed `{item.get('speaker_attributed_markdown_present')}`, missing `{missing}`, "
                    f"manifest `{item.get('recording_manifest_sha256')}`"
                )
        else:
            lines.append("- None")
        lines.extend(["", "## Generated Artifacts", ""])
        if self.generated_artifacts:
            for name, payload in sorted(self.generated_artifacts.items()):
                lines.append(
                    f"- `{name}`: {payload.get('bytes')} bytes, SHA-256 `{payload.get('sha256')}`"
                )
        else:
            lines.append("- None")
        lines.extend(["", "## Blockers", ""])
        if self.blockers:
            lines.extend(f"- {blocker}" for blocker in self.blockers)
        else:
            lines.append("- None")
        lines.extend(
            [
                "",
                "## Safety Boundary",
                "",
                "Pavo can prove source coverage, generated artifacts, and gate state. It cannot mark the batch complete until required human speaker decisions have been represented in the review slate.",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"


@dataclass(frozen=True)
class BatchManifestVerificationResult:
    report_path: Path
    passed: bool
    source_manifest_sha256: str | None
    expected_source_manifest_sha256: str | None
    generated_manifest_sha256: str | None
    expected_generated_manifest_sha256: str | None
    checked_artifact_count: int
    mismatches: list[dict[str, Any]]

    def as_report(self) -> dict[str, Any]:
        return {
            "report_path": str(self.report_path),
            "passed": self.passed,
            "source_manifest_sha256": self.source_manifest_sha256,
            "expected_source_manifest_sha256": self.expected_source_manifest_sha256,
            "generated_manifest_sha256": self.generated_manifest_sha256,
            "expected_generated_manifest_sha256": self.expected_generated_manifest_sha256,
            "checked_artifact_count": self.checked_artifact_count,
            "mismatches": self.mismatches,
        }

    def as_markdown(self) -> str:
        lines = [
            "# Pavo Batch Manifest Verification",
            "",
            f"- Report path: `{self.report_path}`",
            f"- Passed: `{str(self.passed).lower()}`",
            f"- Source manifest SHA-256: `{self.source_manifest_sha256}`",
            f"- Expected source manifest SHA-256: `{self.expected_source_manifest_sha256}`",
            f"- Generated manifest SHA-256: `{self.generated_manifest_sha256}`",
            f"- Expected generated manifest SHA-256: `{self.expected_generated_manifest_sha256}`",
            f"- Checked artifacts: {self.checked_artifact_count}",
            "",
            "## Mismatches",
            "",
        ]
        if self.mismatches:
            for mismatch in self.mismatches:
                lines.append(
                    f"- `{mismatch.get('recording_id')}` `{mismatch.get('artifact')}`: "
                    f"{mismatch.get('reason')} ({mismatch.get('path')})"
                )
        else:
            lines.append("- None")
        return "\n".join(lines).rstrip() + "\n"


@dataclass(frozen=True)
class BatchProofResult:
    batch_root: Path
    passed: bool
    complete: bool
    state: str
    doctor: BatchDoctorResult
    verification: BatchManifestVerificationResult
    proof_report_path: Path
    proof_markdown_path: Path
    proof_review_slate_path: Path
    proof_decision_slate_path: Path
    proof_decision_board_path: Path
    proof_review_checklist_path: Path
    doctor_report_path: Path
    doctor_markdown_path: Path
    verification_markdown_path: Path
    review_packet: dict[str, Any]

    def as_report(self) -> dict[str, Any]:
        return {
            "batch_root": str(self.batch_root),
            "passed": self.passed,
            "complete": self.complete,
            "state": self.state,
            "proof_report_path": str(self.proof_report_path),
            "proof_markdown_path": str(self.proof_markdown_path),
            "proof_review_slate_path": str(self.proof_review_slate_path),
            "proof_decision_slate_path": str(self.proof_decision_slate_path),
            "proof_decision_board_path": str(self.proof_decision_board_path),
            "proof_review_checklist_path": str(self.proof_review_checklist_path),
            "doctor_report_path": str(self.doctor_report_path),
            "doctor_markdown_path": str(self.doctor_markdown_path),
            "verification_markdown_path": str(self.verification_markdown_path),
            "source_manifest_sha256": self.doctor.source_manifest_sha256,
            "generated_manifest_sha256": self.doctor.generated_manifest_sha256,
            "checked_artifact_count": self.verification.checked_artifact_count,
            "mismatches": self.verification.mismatches,
            "checks": self.doctor.checks,
            "blockers": self.doctor.blockers,
            "next_command": self.doctor.next_command,
            "review_packet": self.review_packet,
            "operator_handoff": _operator_handoff(self),
            "doctor": self.doctor.as_report(),
            "verification": self.verification.as_report(),
            "safety_boundary": "Batch proof verifies machine plumbing and artifact integrity. It does not mark speaker identity complete until human review gates pass.",
        }

    def as_markdown(self) -> str:
        validate_proof_slate_command = self.review_packet.get("validate_proof_slate_command")
        finish_proof_slate_command = self.review_packet.get("finish_proof_slate_command")
        lines = [
            "# Pavo Batch Proof",
            "",
            f"- Batch root: `{self.batch_root}`",
            f"- Passed: `{str(self.passed).lower()}`",
            f"- Complete: `{str(self.complete).lower()}`",
            f"- State: `{self.state}`",
            f"- Source manifest SHA-256: `{self.doctor.source_manifest_sha256}`",
            f"- Generated manifest SHA-256: `{self.doctor.generated_manifest_sha256}`",
            f"- Checked artifacts: {self.verification.checked_artifact_count}",
            f"- Mismatches: {len(self.verification.mismatches)}",
            f"- Next command: `{self.doctor.next_command}`",
            f"- Review packet state: `{self.review_packet.get('state')}`",
            f"- Review packet items: {self.review_packet.get('item_count')}",
            f"- Review unlock: {self.review_packet.get('total_unlockable_segments')} segments / {self.review_packet.get('total_unlockable_seconds')} seconds",
            "",
            "## Reports",
            "",
            f"- Proof JSON: `{self.proof_report_path}`",
            f"- Proof Markdown: `{self.proof_markdown_path}`",
            f"- Proof review slate TSV: `{self.proof_review_slate_path}`",
            f"- Proof decision slate TSV: `{self.proof_decision_slate_path}`",
            f"- Proof decision board HTML: `{self.proof_decision_board_path}`",
            f"- Proof review checklist: `{self.proof_review_checklist_path}`",
            f"- Doctor JSON: `{self.doctor_report_path}`",
            f"- Doctor Markdown: `{self.doctor_markdown_path}`",
            f"- Manifest verification Markdown: `{self.verification_markdown_path}`",
            f"- Review decision brief: `{self.review_packet.get('decision_brief_html')}`",
            f"- Review slate TSV: `{self.review_packet.get('slate_tsv')}`",
            f"- Review page: `{self.review_packet.get('review_page')}`",
            f"- Validate slate: `{self.review_packet.get('validate_command')}`",
            f"- Finish from slate: `{self.review_packet.get('finish_command')}`",
            f"- Validate proof slate: `{validate_proof_slate_command}`",
            f"- Finish from proof slate: `{finish_proof_slate_command}`",
            "",
            "## Operator Handoff",
            "",
            "1. Open the review page or proof TSV listed above.",
            f"2. Fill `{self.proof_review_slate_path}` by changing `decision` to `approved` or `rejected`, correcting `speaker` when needed, and leaving a short `note` for ambiguous rows.",
            f"3. Validate without mutation: `{validate_proof_slate_command}`",
            f"4. Finish only after validation passes: `{finish_proof_slate_command}`",
            f"5. Re-run strict proof: `pavo batch prove {shlex.quote(str(self.batch_root))} --strict-complete`",
            "",
            "Expected state before human review: validation fails closed with pending rows. Expected final state after human review: strict proof exits zero with `complete: true`.",
            "",
            "## Speaker Review Queue",
            "",
        ]
        top_items = self.review_packet.get("top_items") or []
        proof_slate_items = self.review_packet.get("proof_slate_items") or top_items
        if top_items:
            for item in top_items:
                lines.extend(
                    [
                        f"### {item.get('rank')}. Cluster `{item.get('cluster_id')}` row `{item.get('row_index')}`",
                        "",
                        f"- Question: {item.get('question')}",
                        f"- Target speaker: `{item.get('target_speaker')}`",
                        f"- Priority: `{item.get('priority_tier')}` / {item.get('priority_score')}",
                        f"- Why: {item.get('priority_reason')}",
                        f"- Unlock: {item.get('unlockable_segments')} segments / {item.get('unlockable_seconds')} seconds",
                        f"- Acoustic verdict: `{item.get('acoustic_verdict')}`",
                        f"- Clip: `{item.get('clip_path')}`",
                        f"- Transcript: {item.get('transcript_excerpt')}",
                        f"- Approve effect: {item.get('approve_effect')}",
                        f"- Reject effect: {item.get('reject_effect')}",
                        f"- Rule: {item.get('terminal_decision_rule')}",
                        "",
                    ]
                )
        else:
            lines.append("- None")
        lines.extend(
            [
                "",
                "## Fillable Review Slate",
                "",
                f"Edit `{self.proof_review_slate_path}`, change `decision` from `pending` to `approved` or `rejected`, adjust `speaker` if needed, then run the proof-slate validate and finish commands above. This TSV includes {len(proof_slate_items)} review-sheet row(s), not just the ranked summary cards.",
                "",
                "```tsv",
            ]
        )
        lines.extend(_review_packet_slate_tsv_lines(proof_slate_items))
        lines.extend(
            [
                "```",
                "",
                "## Checks",
                "",
            ]
        )
        for check in self.doctor.checks:
            status = "pass" if check.get("passed") else "fail"
            lines.append(f"- `{status}` {check.get('name')}: {check.get('detail')}")
        lines.extend(["", "## Blockers", ""])
        if self.doctor.blockers:
            lines.extend(f"- {blocker}" for blocker in self.doctor.blockers)
        else:
            lines.append("- None")
        lines.extend(
            [
                "",
                "## Safety Boundary",
                "",
                "Pavo can prove machine coverage and artifact integrity. Speaker identity remains incomplete until the review slate decisions are filled and the cluster gate passes.",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"


@dataclass(frozen=True)
class BatchDecisionSlateApplyResult:
    proof_report_path: Path
    proof_review_slate_path: Path
    decision_slate_path: Path
    out_path: Path
    row_count: int
    decision_count: int
    applied_row_count: int
    approved_row_count: int
    rejected_row_count: int
    pending_row_count: int
    skipped_row_count: int
    missing_decision_groups: list[str]

    def as_report(self) -> dict[str, Any]:
        return {
            "proof_report_path": str(self.proof_report_path),
            "proof_review_slate_path": str(self.proof_review_slate_path),
            "decision_slate_path": str(self.decision_slate_path),
            "out_path": str(self.out_path),
            "row_count": self.row_count,
            "decision_count": self.decision_count,
            "applied_row_count": self.applied_row_count,
            "approved_row_count": self.approved_row_count,
            "rejected_row_count": self.rejected_row_count,
            "pending_row_count": self.pending_row_count,
            "skipped_row_count": self.skipped_row_count,
            "missing_decision_groups": self.missing_decision_groups,
        }


VALID_REVIEW_DECISIONS = {"pending", "approved", "rejected"}


@dataclass(frozen=True)
class BatchSpeakerMemoryCandidateResult:
    proof_report_path: Path
    proof_review_slate_path: Path
    out_path: Path
    candidate_count: int
    speaker_count: int
    approved_row_count: int
    rejected_row_count: int
    pending_row_count: int
    candidates: list[dict[str, Any]]

    def as_report(self) -> dict[str, Any]:
        return {
            "proof_report_path": str(self.proof_report_path),
            "proof_review_slate_path": str(self.proof_review_slate_path),
            "out_path": str(self.out_path),
            "candidate_count": self.candidate_count,
            "speaker_count": self.speaker_count,
            "approved_row_count": self.approved_row_count,
            "rejected_row_count": self.rejected_row_count,
            "pending_row_count": self.pending_row_count,
            "candidates": self.candidates,
            "safety_boundary": "Speaker memory candidates are reviewed samples for later enrollment or verification. They are not voiceprints and do not prove identity by themselves.",
        }


@dataclass(frozen=True)
class BatchReviewedProofFinalizeResult:
    proof_report_path: Path
    batch_root: Path
    review_sheet_path: Path
    proof_review_slate_path: Path
    validation_report_path: Path
    passed: bool
    finalized: bool
    validation_ready: bool
    finish_passed: bool
    strict_proof_complete: bool
    speaker_memory_candidates_path: Path | None
    speaker_memory_candidate_count: int
    speaker_memory_speaker_count: int
    blockers: list[str]
    validation: dict[str, Any]
    finish: dict[str, Any] | None
    strict_proof: dict[str, Any] | None

    def as_report(self) -> dict[str, Any]:
        return {
            "proof_report_path": str(self.proof_report_path),
            "batch_root": str(self.batch_root),
            "review_sheet_path": str(self.review_sheet_path),
            "proof_review_slate_path": str(self.proof_review_slate_path),
            "validation_report_path": str(self.validation_report_path),
            "passed": self.passed,
            "finalized": self.finalized,
            "validation_ready": self.validation_ready,
            "finish_passed": self.finish_passed,
            "strict_proof_complete": self.strict_proof_complete,
            "speaker_memory_candidates_path": str(self.speaker_memory_candidates_path) if self.speaker_memory_candidates_path else None,
            "speaker_memory_candidate_count": self.speaker_memory_candidate_count,
            "speaker_memory_speaker_count": self.speaker_memory_speaker_count,
            "blockers": self.blockers,
            "validation": self.validation,
            "finish": self.finish,
            "strict_proof": self.strict_proof,
            "safety_boundary": "Finalizing a reviewed proof requires human-filled slate decisions. Pavo validates and materializes them, but it does not approve speaker identity from machine inference alone.",
        }


@dataclass(frozen=True)
class BatchDecisionBoardResult:
    proof_report_path: Path
    decision_slate_path: Path
    out_path: Path
    decision_count: int
    pending_decision_count: int
    supporting_row_count: int

    def as_report(self) -> dict[str, Any]:
        return {
            "proof_report_path": str(self.proof_report_path),
            "decision_slate_path": str(self.decision_slate_path),
            "out_path": str(self.out_path),
            "decision_count": self.decision_count,
            "pending_decision_count": self.pending_decision_count,
            "supporting_row_count": self.supporting_row_count,
            "safety_boundary": "Decision board helps a human fill the review slate. It does not approve speaker identity or write reviewed decisions by itself.",
        }


@dataclass(frozen=True)
class BatchDecisionBoardVerifyResult:
    proof_report_path: Path
    decision_board_path: Path
    passed: bool
    decision_count: int
    expected_decision_count: int
    pending_decision_count: int
    supporting_row_count: int
    expected_supporting_row_count: int
    checks: list[dict[str, Any]]
    blockers: list[str]
    board_fingerprint: dict[str, Any]

    def as_report(self) -> dict[str, Any]:
        return {
            "proof_report_path": str(self.proof_report_path),
            "decision_board_path": str(self.decision_board_path),
            "passed": self.passed,
            "decision_count": self.decision_count,
            "expected_decision_count": self.expected_decision_count,
            "pending_decision_count": self.pending_decision_count,
            "supporting_row_count": self.supporting_row_count,
            "expected_supporting_row_count": self.expected_supporting_row_count,
            "checks": self.checks,
            "blockers": self.blockers,
            "board_fingerprint": self.board_fingerprint,
            "safety_boundary": "Decision-board verification proves the review surface is present and wired. It does not approve speaker identity or replace human listening review.",
        }


@dataclass(frozen=True)
class BatchReviewPackResult:
    proof_report_path: Path
    batch_root: Path
    out_dir: Path
    manifest_path: Path
    readme_path: Path
    zip_path: Path | None
    copied_artifact_count: int
    missing_artifact_count: int
    artifact_manifest_sha256: str
    raw_audio_copied: bool
    artifacts: dict[str, dict[str, Any]]
    missing_artifacts: list[dict[str, Any]]

    def as_report(self) -> dict[str, Any]:
        return {
            "proof_report_path": str(self.proof_report_path),
            "batch_root": str(self.batch_root),
            "out_dir": str(self.out_dir),
            "manifest_path": str(self.manifest_path),
            "readme_path": str(self.readme_path),
            "zip_path": str(self.zip_path) if self.zip_path else None,
            "copied_artifact_count": self.copied_artifact_count,
            "missing_artifact_count": self.missing_artifact_count,
            "artifact_manifest_sha256": self.artifact_manifest_sha256,
            "raw_audio_copied": self.raw_audio_copied,
            "artifacts": self.artifacts,
            "missing_artifacts": self.missing_artifacts,
            "safety_boundary": "Review packs copy proof and review artifacts only. They do not copy raw audio, create voiceprints, or approve speaker identity.",
        }


@dataclass(frozen=True)
class BatchReviewPackVerifyResult:
    proof_report_path: Path
    pack_dir: Path
    manifest_path: Path
    readme_path: Path
    zip_path: Path | None
    passed: bool
    artifact_count: int
    missing_artifact_count: int
    checks: list[dict[str, Any]]
    blockers: list[str]
    artifact_manifest_sha256: str | None
    board_verification: dict[str, Any] | None
    sprint_verification: dict[str, Any] | None

    def as_report(self) -> dict[str, Any]:
        return {
            "proof_report_path": str(self.proof_report_path),
            "pack_dir": str(self.pack_dir),
            "manifest_path": str(self.manifest_path),
            "readme_path": str(self.readme_path),
            "zip_path": str(self.zip_path) if self.zip_path else None,
            "passed": self.passed,
            "artifact_count": self.artifact_count,
            "missing_artifact_count": self.missing_artifact_count,
            "checks": self.checks,
            "blockers": self.blockers,
            "artifact_manifest_sha256": self.artifact_manifest_sha256,
            "board_verification": self.board_verification,
            "sprint_verification": self.sprint_verification,
            "safety_boundary": "Review-pack verification proves the handoff package is complete and integrity-checked. It does not copy raw audio or approve speaker identity.",
        }


@dataclass(frozen=True)
class BatchReviewSprintResult:
    proof_report_path: Path
    out_dir: Path
    json_path: Path
    markdown_path: Path
    state: str
    complete: bool
    pending_decision_count: int
    pending_clip_count: int
    estimated_minutes: float
    payload: dict[str, Any]

    def as_report(self) -> dict[str, Any]:
        return {
            "proof_report_path": str(self.proof_report_path),
            "out_dir": str(self.out_dir),
            "json_path": str(self.json_path),
            "markdown_path": str(self.markdown_path),
            "state": self.state,
            "complete": self.complete,
            "pending_decision_count": self.pending_decision_count,
            "pending_clip_count": self.pending_clip_count,
            "estimated_minutes": self.estimated_minutes,
            "payload": self.payload,
            "safety_boundary": "Review sprint packets guide human speaker review. They do not approve identity or copy raw audio.",
        }


@dataclass(frozen=True)
class BatchReviewSprintVerifyResult:
    proof_report_path: Path
    json_path: Path
    markdown_path: Path
    passed: bool
    pending_decision_count: int
    pending_clip_count: int
    checks: list[dict[str, Any]]
    blockers: list[str]

    def as_report(self) -> dict[str, Any]:
        return {
            "proof_report_path": str(self.proof_report_path),
            "json_path": str(self.json_path),
            "markdown_path": str(self.markdown_path),
            "passed": self.passed,
            "pending_decision_count": self.pending_decision_count,
            "pending_clip_count": self.pending_clip_count,
            "checks": self.checks,
            "blockers": self.blockers,
            "safety_boundary": "Review-sprint verification proves the reviewer packet is complete and evidence-linked. It does not approve speaker identity.",
        }


@dataclass(frozen=True)
class BatchSpeakerAnswerSheetResult:
    proof_report_path: Path
    out_dir: Path
    markdown_path: Path
    tsv_path: Path
    pending_decision_count: int
    pending_clip_count: int
    estimated_minutes: float
    payload: dict[str, Any]

    def as_report(self) -> dict[str, Any]:
        return {
            "proof_report_path": str(self.proof_report_path),
            "out_dir": str(self.out_dir),
            "markdown_path": str(self.markdown_path),
            "tsv_path": str(self.tsv_path),
            "pending_decision_count": self.pending_decision_count,
            "pending_clip_count": self.pending_clip_count,
            "estimated_minutes": self.estimated_minutes,
            "payload": self.payload,
            "safety_boundary": "Speaker answer sheets guide human listening decisions. They do not approve identity, create voiceprints, or copy raw audio.",
        }


@dataclass(frozen=True)
class BatchSpeakerAnswerSheetVerifyResult:
    proof_report_path: Path
    markdown_path: Path
    tsv_path: Path
    passed: bool
    pending_decision_count: int
    pending_clip_count: int
    checks: list[dict[str, Any]]
    blockers: list[str]

    def as_report(self) -> dict[str, Any]:
        return {
            "proof_report_path": str(self.proof_report_path),
            "markdown_path": str(self.markdown_path),
            "tsv_path": str(self.tsv_path),
            "passed": self.passed,
            "pending_decision_count": self.pending_decision_count,
            "pending_clip_count": self.pending_clip_count,
            "checks": self.checks,
            "blockers": self.blockers,
            "safety_boundary": "Answer-sheet verification proves the human decision sheet is present, ordered, and clip-linked. It does not approve speaker identity.",
        }


@dataclass(frozen=True)
class BatchReviewRehearsalResult:
    proof_report_path: Path
    out_dir: Path
    json_path: Path
    markdown_path: Path
    passed: bool
    state: str
    pending_decision_count: int
    pending_clip_count: int
    estimated_minutes: float
    first_decision: dict[str, Any] | None
    checks: list[dict[str, Any]]
    blockers: list[str]
    payload: dict[str, Any]

    def as_report(self) -> dict[str, Any]:
        return {
            "proof_report_path": str(self.proof_report_path),
            "out_dir": str(self.out_dir),
            "json_path": str(self.json_path),
            "markdown_path": str(self.markdown_path),
            "passed": self.passed,
            "state": self.state,
            "pending_decision_count": self.pending_decision_count,
            "pending_clip_count": self.pending_clip_count,
            "estimated_minutes": self.estimated_minutes,
            "first_decision": self.first_decision,
            "checks": self.checks,
            "blockers": self.blockers,
            "payload": self.payload,
            "safety_boundary": "Review rehearsal proves the human review path is coherent and ready. It does not approve speaker identity or replace listening review.",
        }


@dataclass(frozen=True)
class BatchReadinessResult:
    proof_report_path: Path
    state: str
    passed: bool
    complete: bool
    machine_ready: bool
    board_ready: bool
    review_pack_ready: bool
    validation_status: str | None
    validation_ready: bool
    pending_decision_count: int | None
    pending_row_count: int | None
    review_sprint: dict[str, Any]
    review_completion: dict[str, Any]
    next_action: str
    blockers: list[str]
    proof: dict[str, Any]
    handoff: dict[str, Any]
    board: dict[str, Any] | None
    review_pack: dict[str, Any] | None

    def as_report(self) -> dict[str, Any]:
        return {
            "proof_report_path": str(self.proof_report_path),
            "state": self.state,
            "passed": self.passed,
            "complete": self.complete,
            "machine_ready": self.machine_ready,
            "board_ready": self.board_ready,
            "review_pack_ready": self.review_pack_ready,
            "validation_status": self.validation_status,
            "validation_ready": self.validation_ready,
            "pending_decision_count": self.pending_decision_count,
            "pending_row_count": self.pending_row_count,
            "review_sprint": self.review_sprint,
            "review_completion": self.review_completion,
            "next_action": self.next_action,
            "blockers": self.blockers,
            "proof": self.proof,
            "handoff": self.handoff,
            "board": self.board,
            "review_pack": self.review_pack,
            "safety_boundary": "Readiness summarizes proof, pack, board, and human-review gates. It does not approve speaker identity.",
        }


@dataclass(frozen=True)
class BatchDecisionBoardAuditApplyResult:
    proof_report_path: Path
    audit_path: Path
    decision_slate_out_path: Path
    proof_review_slate_out_path: Path
    decision_count: int
    approved_decision_count: int
    rejected_decision_count: int
    pending_decision_count: int
    applied_row_count: int
    approved_row_count: int
    rejected_row_count: int
    pending_row_count: int
    missing_decision_groups: list[str]

    def as_report(self) -> dict[str, Any]:
        return {
            "proof_report_path": str(self.proof_report_path),
            "audit_path": str(self.audit_path),
            "decision_slate_out_path": str(self.decision_slate_out_path),
            "proof_review_slate_out_path": str(self.proof_review_slate_out_path),
            "decision_count": self.decision_count,
            "approved_decision_count": self.approved_decision_count,
            "rejected_decision_count": self.rejected_decision_count,
            "pending_decision_count": self.pending_decision_count,
            "applied_row_count": self.applied_row_count,
            "approved_row_count": self.approved_row_count,
            "rejected_row_count": self.rejected_row_count,
            "pending_row_count": self.pending_row_count,
            "missing_decision_groups": self.missing_decision_groups,
            "safety_boundary": "Decision-board audit import turns reviewed board state into TSV artifacts. It does not validate or finalize speaker identity by itself.",
        }


@dataclass(frozen=True)
class BatchDecisionBoardAuditFinalizeResult:
    proof_report_path: Path
    audit_path: Path
    decision_slate_out_path: Path
    proof_review_slate_out_path: Path
    passed: bool
    finalized: bool
    validation_ready: bool
    finish_passed: bool
    strict_proof_complete: bool
    import_report: dict[str, Any]
    finalization_report: dict[str, Any]
    blockers: list[str]

    def as_report(self) -> dict[str, Any]:
        return {
            "proof_report_path": str(self.proof_report_path),
            "audit_path": str(self.audit_path),
            "decision_slate_out_path": str(self.decision_slate_out_path),
            "proof_review_slate_out_path": str(self.proof_review_slate_out_path),
            "passed": self.passed,
            "finalized": self.finalized,
            "validation_ready": self.validation_ready,
            "finish_passed": self.finish_passed,
            "strict_proof_complete": self.strict_proof_complete,
            "import": self.import_report,
            "finalization": self.finalization_report,
            "blockers": self.blockers,
            "safety_boundary": "Finalize-from-board-audit imports reviewed board state and runs the existing validation/finalization gates. It still fails closed while decisions are pending.",
        }


def doctor_batch(batch_root: Path | str, *, refresh_cluster_gate: bool = True) -> BatchDoctorResult:
    root = Path(batch_root)
    recordings = _source_recordings(root)
    cluster_gate_path = root / "pavo-cluster-review-gate.json"
    cluster_gate_markdown_path = root / "pavo-cluster-review-gate.md"
    cluster_gate_refresh_error = None
    if refresh_cluster_gate and root.exists():
        try:
            cluster_gate_result = gate_cluster_review(root)
            cluster_gate = cluster_gate_result.as_report()
            cluster_gate_path.write_text(json.dumps(cluster_gate, indent=2, sort_keys=True) + "\n")
            cluster_gate_markdown_path.write_text(cluster_gate_result.as_markdown())
        except (OSError, ValueError) as exc:
            cluster_gate = _load_optional_json(cluster_gate_path)
            cluster_gate_refresh_error = str(exc)
    else:
        cluster_gate = _load_optional_json(cluster_gate_path)
    run_report = _load_optional_json(root / "pavo-run-report.json")
    meeting_brief = _load_optional_json(root / "pavo-meeting-brief.json")
    generated_artifacts = _generated_artifacts(root)

    source_count = len(recordings)
    source_missing = {
        item["recording_id"]: item["missing"]
        for item in recordings
        if item["missing"]
    }
    source_manifest_sha256 = _source_manifest_sha256(recordings)
    generated_manifest_sha256 = _artifact_manifest_sha256(generated_artifacts)
    work_dir = root / "_work"
    checks = [
        _check("batch_root", root.exists(), str(root)),
        _check("source_recordings", source_count > 0, f"{source_count} source recording directories"),
        _check("source_audio", all(item["audio_present"] for item in recordings) and source_count > 0, _coverage_detail(recordings, "audio_present")),
        _check(
            "source_transcript_json",
            all(item["transcript_json_present"] for item in recordings) and source_count > 0,
            _coverage_detail(recordings, "transcript_json_present"),
        ),
        _check(
            "source_transcript_markdown",
            all(item["transcript_markdown_present"] for item in recordings) and source_count > 0,
            _coverage_detail(recordings, "transcript_markdown_present"),
        ),
        _check(
            "source_diarized_markdown",
            all(item["diarized_markdown_present"] for item in recordings) and source_count > 0,
            _coverage_detail(recordings, "diarized_markdown_present"),
        ),
        _check(
            "source_speaker_attributed_markdown",
            all(item["speaker_attributed_markdown_present"] for item in recordings) and source_count > 0,
            _coverage_detail(recordings, "speaker_attributed_markdown_present"),
        ),
        _check(
            "source_fingerprints",
            all(item.get("recording_manifest_sha256") for item in recordings) and source_count > 0,
            f"{sum(1 for item in recordings if item.get('recording_manifest_sha256'))}/{source_count}",
        ),
        _check("run_report", bool(run_report), str(root / "pavo-run-report.json")),
        _check("meeting_brief", bool(meeting_brief), str(root / "pavo-meeting-brief.json")),
        _check("diarization_segments", (work_dir / "diarization-segments.json").exists(), str(work_dir / "diarization-segments.json")),
        _check("speaker_attribution", (work_dir / "speaker-attribution.json").exists(), str(work_dir / "speaker-attribution.json")),
        _check("named_speaker_evidence", (work_dir / "named-speaker-evidence.json").exists(), str(work_dir / "named-speaker-evidence.json")),
        _check("cluster_gate_report", bool(cluster_gate), str(root / "pavo-cluster-review-gate.json")),
        _check(
            "generated_fingerprints",
            _required_generated_artifacts_present(generated_artifacts),
            f"{len(generated_artifacts)}/{len(GENERATED_ARTIFACT_PATHS)}",
        ),
        _check(
            "cluster_gate_refresh",
            not cluster_gate_refresh_error,
            "refreshed" if refresh_cluster_gate and not cluster_gate_refresh_error else (cluster_gate_refresh_error or "not requested"),
        ),
        _check(
            "cluster_gate_machine_plumbing",
            bool(cluster_gate and (cluster_gate.get("doctor") or {}).get("passed")),
            f"doctor_passed={bool(cluster_gate and (cluster_gate.get('doctor') or {}).get('passed'))}",
        ),
    ]
    if run_report:
        observed = (run_report.get("counts") or {}).get("recordings_observed")
        checks.append(
            _check(
                "run_report_recording_parity",
                observed == source_count,
                f"run_report={observed}; source_directories={source_count}",
            )
        )

    passed = all(check["passed"] for check in checks)
    complete = bool(passed and cluster_gate and cluster_gate.get("complete"))
    if complete:
        state = "complete"
        next_command = "pavo brief " + str(root)
    elif passed:
        state = "machine_ready_human_review_pending"
        next_command = str(cluster_gate.get("next_command") if cluster_gate else f"pavo review clusters gate {root}")
    else:
        state = "needs_machine_repair"
        next_command = f"pavo meetings process {root}"

    blockers = [f"{check['name']} failed" for check in checks if not check["passed"]]
    for recording_id, missing in source_missing.items():
        blockers.append(f"{recording_id} missing: {', '.join(missing)}")
    if cluster_gate and cluster_gate.get("blockers"):
        blockers.extend(cluster_gate.get("blockers") or [])
    return BatchDoctorResult(
        batch_root=root,
        passed=passed,
        complete=complete,
        state=state,
        source_recording_count=source_count,
        source_recordings=recordings,
        source_manifest_sha256=source_manifest_sha256,
        generated_artifacts=generated_artifacts,
        generated_manifest_sha256=generated_manifest_sha256,
        checks=checks,
        blockers=list(dict.fromkeys(blockers)),
        next_command=next_command,
        cluster_gate=cluster_gate,
    )


def prove_batch(
    batch_root: Path | str,
    *,
    out_dir: Path | str | None = None,
    refresh_cluster_gate: bool = True,
) -> BatchProofResult:
    root = Path(batch_root)
    target_dir = Path(out_dir) if out_dir else root
    target_dir.mkdir(parents=True, exist_ok=True)
    doctor_report_path = target_dir / "pavo-batch-doctor.json"
    doctor_markdown_path = target_dir / "pavo-batch-doctor.md"
    verification_markdown_path = target_dir / "pavo-batch-manifest-verification.md"
    proof_report_path = target_dir / "pavo-batch-proof.json"
    proof_markdown_path = target_dir / "pavo-batch-proof.md"
    proof_review_slate_path = target_dir / "pavo-batch-proof.review-slate.tsv"
    proof_decision_slate_path = target_dir / "pavo-batch-proof.decision-slate.tsv"
    proof_decision_board_path = target_dir / "pavo-batch-proof.decision-board.html"
    proof_review_checklist_path = target_dir / "pavo-batch-proof.review-checklist.md"

    doctor = doctor_batch(root, refresh_cluster_gate=refresh_cluster_gate)
    doctor_report_path.write_text(json.dumps(doctor.as_report(), indent=2, sort_keys=True) + "\n")
    doctor_markdown_path.write_text(doctor.as_markdown())
    verification = verify_batch_manifest(doctor_report_path)
    verification_markdown_path.write_text(verification.as_markdown())

    passed = bool(doctor.passed and verification.passed)
    complete = bool(passed and doctor.complete)
    if complete:
        state = "complete"
    elif passed:
        state = "machine_ready_human_review_pending"
    else:
        state = "needs_machine_repair"

    review_packet = _review_packet_summary(root, doctor.cluster_gate)
    proof_review_slate_path.write_text(
        "\n".join(
            _review_packet_slate_tsv_lines(
                review_packet.get("proof_slate_items") or review_packet.get("top_items") or []
            )
        )
        + "\n"
    )
    proof_decision_slate_path.write_text(
        "\n".join(
            _review_packet_decision_slate_tsv_lines(
                review_packet.get("proof_slate_items") or review_packet.get("top_items") or []
            )
        )
        + "\n"
    )
    _add_proof_slate_commands(
        review_packet,
        batch_root=root,
        proof_review_slate_path=proof_review_slate_path,
    )
    strict_proof_command = f"pavo batch prove {shlex.quote(str(root))} --strict-complete"
    handoff_command = f"pavo batch handoff {shlex.quote(str(proof_report_path))} --check-validation"
    proof_review_checklist_path.write_text(
        _render_proof_review_checklist(
            batch_root=root,
            proof_slate_items=review_packet.get("proof_slate_items") or review_packet.get("top_items") or [],
            proof_review_slate_path=proof_review_slate_path,
            validate_command=review_packet.get("validate_proof_slate_command"),
            finish_command=review_packet.get("finish_proof_slate_command"),
            strict_proof_command=strict_proof_command,
            handoff_command=handoff_command,
        )
    )
    review_packet["proof_review_checklist_markdown"] = str(proof_review_checklist_path)
    review_packet["proof_decision_slate_tsv"] = str(proof_decision_slate_path)
    review_packet["proof_decision_board_html"] = str(proof_decision_board_path)

    result = BatchProofResult(
        batch_root=root,
        passed=passed,
        complete=complete,
        state=state,
        doctor=doctor,
        verification=verification,
        proof_report_path=proof_report_path,
        proof_markdown_path=proof_markdown_path,
        proof_review_slate_path=proof_review_slate_path,
        proof_decision_slate_path=proof_decision_slate_path,
        proof_decision_board_path=proof_decision_board_path,
        proof_review_checklist_path=proof_review_checklist_path,
        doctor_report_path=doctor_report_path,
        doctor_markdown_path=doctor_markdown_path,
        verification_markdown_path=verification_markdown_path,
        review_packet=review_packet,
    )
    proof_report_path.write_text(json.dumps(result.as_report(), indent=2, sort_keys=True) + "\n")
    proof_markdown_path.write_text(result.as_markdown())
    write_batch_decision_board(proof_report_path, out_path=proof_decision_board_path)
    proof_report_path.write_text(json.dumps(result.as_report(), indent=2, sort_keys=True) + "\n")
    return result


def _operator_handoff(result: BatchProofResult) -> dict[str, Any]:
    proof_slate = result.review_packet.get("proof_review_slate_tsv") or str(result.proof_review_slate_path)
    validate_command = result.review_packet.get("validate_proof_slate_command")
    finish_command = result.review_packet.get("finish_proof_slate_command")
    strict_proof_command = f"pavo batch prove {shlex.quote(str(result.batch_root))} --strict-complete"
    return {
        "state": result.state,
        "complete": result.complete,
        "review_page": result.review_packet.get("review_page"),
        "proof_review_slate_tsv": proof_slate,
        "proof_decision_slate_tsv": result.review_packet.get("proof_decision_slate_tsv")
        or str(result.proof_decision_slate_path),
        "proof_decision_board_html": result.review_packet.get("proof_decision_board_html")
        or str(result.proof_decision_board_path),
        "proof_review_checklist_markdown": result.review_packet.get("proof_review_checklist_markdown")
        or str(result.proof_review_checklist_path),
        "proof_slate_item_count": result.review_packet.get("proof_slate_item_count"),
        "validate_command": validate_command,
        "finish_command": finish_command,
        "strict_proof_command": strict_proof_command,
        "steps": [
            "Open the review page or proof TSV.",
            "Approve or reject every proof TSV row, correct speaker labels when needed, and leave notes for ambiguity.",
            "Run validate_command; it must pass before finishing.",
            "Run finish_command to materialize reviewed speaker decisions.",
            "Run strict_proof_command and require complete true.",
        ],
        "expected_pending_state": "validation fails closed while any review row remains pending",
        "expected_complete_state": "strict proof exits zero with complete true",
        "safety_boundary": "Do not mark speaker identity complete from machine inference alone.",
    }


def load_operator_handoff(proof_report_path: Path | str) -> dict[str, Any]:
    path = Path(proof_report_path)
    report = json.loads(path.read_text())
    handoff = report.get("operator_handoff")
    if not isinstance(handoff, dict):
        raise ValueError(f"proof report missing operator_handoff: {path}")
    return handoff


def enrich_operator_handoff_with_validation(handoff: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(handoff)
    review_page = str(enriched.get("review_page") or "").strip()
    slate = str(enriched.get("proof_review_slate_tsv") or "").strip()
    decision_slate = str(enriched.get("proof_decision_slate_tsv") or "").strip()
    decision_board = str(enriched.get("proof_decision_board_html") or "").strip()
    checklist = str(enriched.get("proof_review_checklist_markdown") or "").strip()
    artifact_checks = {
        "review_page": _handoff_artifact_check(review_page),
        "proof_review_slate_tsv": _handoff_artifact_check(slate),
        "proof_decision_slate_tsv": _handoff_artifact_check(decision_slate),
        "proof_decision_board_html": _handoff_artifact_check(decision_board),
        "proof_review_checklist_markdown": _handoff_artifact_check(checklist),
    }
    validation_path = Path(slate).with_suffix(".validation.json") if slate else None
    artifact_checks["validation_report"] = _handoff_artifact_check(str(validation_path) if validation_path else "")
    validation: dict[str, Any] = {
        "path": str(validation_path) if validation_path else None,
        "exists": bool(validation_path and validation_path.exists()),
        "status": "missing",
        "next_action": _handoff_validation_next_action("missing", 0),
    }
    if validation_path and validation_path.exists():
        try:
            payload = json.loads(validation_path.read_text())
            passed = bool(payload.get("passed"))
            ready = bool(payload.get("ready_to_finalize"))
            pending = int(payload.get("pending_count") or 0)
            approved = int(payload.get("approved_count") or 0)
            rejected = int(payload.get("rejected_count") or 0)
            reviewed = approved + rejected
            total = reviewed + pending
            progress_percent = round((reviewed / total) * 100, 1) if total else 100.0
            pending_rows = _handoff_pending_rows(slate)
            pending_review_questions = _handoff_pending_review_questions(pending_rows)
            pending_decision_count = len(pending_review_questions)
            decision_progress = _handoff_decision_progress(slate)
            decision_ready = bool(
                decision_progress.get("total_decision_count")
                and decision_progress.get("pending_decision_count") == 0
                and decision_progress.get("inconsistent_decision_count") == 0
                and decision_progress.get("reviewed_decision_count")
                == decision_progress.get("total_decision_count")
            )
            slate_mtime = Path(slate).stat().st_mtime if slate and Path(slate).exists() else None
            validation_mtime = validation_path.stat().st_mtime
            fresh = slate_mtime is None or validation_mtime >= slate_mtime
            status = "stale_validation" if not fresh else ("ready_to_finish" if ready and decision_ready else "pending_review")
            validation.update(
                {
                    "status": status,
                    "fresh": fresh,
                    "slate_mtime": slate_mtime,
                    "validation_mtime": validation_mtime,
                    "reviewed_count": reviewed,
                    "total_count": total,
                    "progress_percent": progress_percent,
                    "pending_rows": pending_rows,
                    "pending_decision_count": pending_decision_count,
                    "decision_progress": decision_progress,
                    "decision_ready": decision_ready,
                    "pending_review_questions": pending_review_questions,
                    "next_action": _handoff_validation_next_action(status, pending, pending_decision_count),
                    "passed": passed,
                    "ready_to_finalize": ready,
                    "applied_count": payload.get("applied_count"),
                    "approved_count": approved,
                    "rejected_count": rejected,
                    "pending_count": pending,
                    "blockers": payload.get("blockers") or [],
                }
            )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            validation.update(
                {
                    "status": "unreadable",
                    "error": str(exc),
                    "next_action": _handoff_validation_next_action("unreadable", 0),
                }
            )
    enriched["artifact_checks"] = artifact_checks
    enriched["artifact_manifest_sha256"] = _handoff_artifact_manifest_sha256(artifact_checks)
    enriched["validation"] = validation
    return enriched


def _handoff_validation_next_action(
    status: str, pending_count: int, pending_decision_count: int | None = None
) -> str:
    if status == "ready_to_finish":
        return "run finish_command, then strict_proof_command"
    if status == "stale_validation":
        return "rerun validate_command before trusting this handoff"
    if status == "pending_review":
        if pending_decision_count is not None and pending_decision_count != pending_count:
            return (
                f"review {pending_decision_count} pending speaker decision(s) across "
                f"{pending_count} proof TSV row(s), then rerun validate_command"
            )
        return f"review {pending_count} pending proof TSV row(s), then rerun validate_command"
    if status == "missing":
        return "run validate_command to create a validation report"
    if status == "unreadable":
        return "repair or delete the unreadable validation report, then rerun validate_command"
    return "inspect validation status"


def _handoff_pending_rows(slate: str, *, limit: int = 20) -> list[dict[str, Any]]:
    path = Path(slate) if slate else None
    if not path or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            for row in reader:
                if str(row.get("decision") or "").strip().lower() != "pending":
                    continue
                rows.append(
                    {
                        "row_index": row.get("row_index"),
                        "cluster_id": row.get("cluster_id"),
                        "speaker": row.get("speaker"),
                        "question": row.get("question"),
                        "clip_path": row.get("clip_path"),
                        "priority_tier": row.get("priority_tier"),
                        "priority_score": row.get("priority_score"),
                        "acoustic_verdict": row.get("acoustic_verdict"),
                        "transcript": row.get("transcript"),
                    }
                )
                if len(rows) >= limit:
                    break
    except (OSError, csv.Error):
        return []
    return rows


def _handoff_decision_progress(slate: str) -> dict[str, Any]:
    path = Path(slate) if slate else None
    if not path or not path.exists():
        return {
            "total_decision_count": 0,
            "reviewed_decision_count": 0,
            "pending_decision_count": 0,
            "progress_percent": 100.0,
        }
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            for row in reader:
                key = (
                    str(row.get("cluster_id") or ""),
                    str(row.get("speaker") or ""),
                    str(row.get("question") or ""),
                )
                group = grouped.setdefault(
                    key,
                    {
                        "cluster_id": row.get("cluster_id"),
                        "speaker": row.get("speaker"),
                        "question": row.get("question"),
                        "row_indices": [],
                        "decisions": set(),
                    },
                )
                group["row_indices"].append(row.get("row_index"))
                group["decisions"].add(str(row.get("decision") or "").strip().lower() or "pending")
    except (OSError, csv.Error):
        return {
            "total_decision_count": 0,
            "reviewed_decision_count": 0,
            "pending_decision_count": 0,
            "progress_percent": 0.0,
            "error": "unable to read proof TSV decision progress",
        }
    total = len(grouped)
    pending = sum(1 for group in grouped.values() if "pending" in group["decisions"])
    inconsistent_groups = [
        {
            "cluster_id": group.get("cluster_id"),
            "speaker": group.get("speaker"),
            "question": group.get("question"),
            "row_indices": group.get("row_indices") or [],
            "decisions": sorted(group["decisions"]),
        }
        for group in grouped.values()
        if "pending" not in group["decisions"] and len(group["decisions"]) > 1
    ]
    reviewed = total - pending
    progress = round((reviewed / total) * 100, 1) if total else 100.0
    return {
        "total_decision_count": total,
        "reviewed_decision_count": reviewed,
        "pending_decision_count": pending,
        "inconsistent_decision_count": len(inconsistent_groups),
        "inconsistent_decisions": inconsistent_groups,
        "progress_percent": progress,
    }


def _decision_slate_review_completion(path_value: str | None) -> dict[str, Any]:
    path = Path(path_value) if path_value else None
    if not path or not path.exists():
        return {
            "path": str(path) if path else None,
            "total_decision_count": 0,
            "approved_decision_count": 0,
            "rejected_decision_count": 0,
            "pending_decision_count": 0,
            "reviewed_decision_count": 0,
            "missing_reason_decision_count": 0,
            "missing_reason_decision_groups": [],
            "progress_percent": 100.0,
            "export_ready": True,
        }
    rows, _fieldnames = _read_tsv(path)
    approved = 0
    rejected = 0
    pending = 0
    missing_reason_groups: list[str] = []
    for row in rows:
        decision = str(row.get("decision") or "").strip().lower() or "pending"
        group = str(row.get("decision_group") or "").strip()
        reason = str(row.get("review_reason") or "").strip()
        if decision == "approved":
            approved += 1
        elif decision == "rejected":
            rejected += 1
        else:
            pending += 1
        if decision in {"approved", "rejected"} and reason not in BATCH_SPEAKER_REVIEW_REASONS:
            missing_reason_groups.append(group or f"row-{len(missing_reason_groups) + 1}")
    total = len(rows)
    reviewed = approved + rejected
    progress = round((reviewed / total) * 100, 1) if total else 100.0
    return {
        "path": str(path),
        "total_decision_count": total,
        "approved_decision_count": approved,
        "rejected_decision_count": rejected,
        "pending_decision_count": pending,
        "reviewed_decision_count": reviewed,
        "missing_reason_decision_count": len(missing_reason_groups),
        "missing_reason_decision_groups": missing_reason_groups,
        "progress_percent": progress,
        "export_ready": pending == 0 and not missing_reason_groups,
    }


def _handoff_pending_review_questions(pending_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []
    for row in pending_rows:
        key = (
            str(row.get("cluster_id") or ""),
            str(row.get("speaker") or ""),
            str(row.get("question") or ""),
        )
        if key not in grouped:
            grouped[key] = {
                "cluster_id": row.get("cluster_id"),
                "speaker": row.get("speaker"),
                "question": row.get("question"),
                "row_indices": [],
                "clip_paths": [],
                "clip_count": 0,
                "priority_tier": row.get("priority_tier"),
                "priority_score": row.get("priority_score"),
                "acoustic_verdict": row.get("acoustic_verdict"),
                "transcript_samples": [],
            }
            order.append(key)
        group = grouped[key]
        group["clip_count"] += 1
        if row.get("row_index"):
            group["row_indices"].append(row.get("row_index"))
        if row.get("clip_path"):
            group["clip_paths"].append(row.get("clip_path"))
        transcript = _handoff_transcript_excerpt(row.get("transcript"))
        if transcript:
            group["transcript_samples"].append(
                {
                    "row_index": row.get("row_index"),
                    "excerpt": transcript,
                }
            )
    return [grouped[key] for key in order]


def _handoff_transcript_excerpt(value: Any, *, limit: int = 140) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def operator_handoff_ready_to_finish(handoff: dict[str, Any]) -> bool:
    validation = handoff.get("validation") if isinstance(handoff.get("validation"), dict) else {}
    artifacts = handoff.get("artifact_checks") if isinstance(handoff.get("artifact_checks"), dict) else {}
    artifacts_exist = bool(artifacts) and all(bool((check or {}).get("exists")) for check in artifacts.values())
    return bool(
        artifacts_exist
        and validation.get("exists")
        and validation.get("fresh")
        and validation.get("ready_to_finalize")
        and validation.get("decision_ready")
        and validation.get("status") == "ready_to_finish"
    )


def _handoff_artifact_check(path_value: str) -> dict[str, Any]:
    path = Path(path_value) if path_value else None
    exists = bool(path and path.exists())
    fingerprint = _file_fingerprint(path) if path and exists and path.is_file() else {}
    return {
        "path": str(path) if path else None,
        "exists": exists,
        "bytes": fingerprint.get("bytes"),
        "sha256": fingerprint.get("sha256"),
    }


def _handoff_artifact_manifest_sha256(artifact_checks: dict[str, dict[str, Any]]) -> str:
    entries = {
        name: {
            "path": payload.get("path"),
            "exists": bool(payload.get("exists")),
            "bytes": payload.get("bytes"),
            "sha256": payload.get("sha256"),
        }
        for name, payload in sorted(artifact_checks.items())
    }
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def format_operator_handoff(handoff: dict[str, Any]) -> str:
    lines = [
        "Pavo Operator Handoff",
        f"state: {handoff.get('state')}",
        f"complete: {str(bool(handoff.get('complete'))).lower()}",
        f"review_page: {handoff.get('review_page')}",
        f"proof_review_slate_tsv: {handoff.get('proof_review_slate_tsv')}",
        f"proof_decision_slate_tsv: {handoff.get('proof_decision_slate_tsv')}",
        f"proof_decision_board_html: {handoff.get('proof_decision_board_html')}",
        f"proof_review_checklist_markdown: {handoff.get('proof_review_checklist_markdown')}",
        f"proof_slate_item_count: {handoff.get('proof_slate_item_count')}",
        f"validate_command: {handoff.get('validate_command')}",
        f"finish_command: {handoff.get('finish_command')}",
        f"strict_proof_command: {handoff.get('strict_proof_command')}",
        "",
        "steps:",
    ]
    for index, step in enumerate(handoff.get("steps") or [], start=1):
        lines.append(f"{index}. {step}")
    lines.extend(
        [
            "",
            f"expected_pending_state: {handoff.get('expected_pending_state')}",
            f"expected_complete_state: {handoff.get('expected_complete_state')}",
            f"safety_boundary: {handoff.get('safety_boundary')}",
        ]
    )
    validation = handoff.get("validation") if isinstance(handoff.get("validation"), dict) else None
    if validation:
        lines.extend(
            [
                "",
                "validation:",
                f"path: {validation.get('path')}",
                f"exists: {str(bool(validation.get('exists'))).lower()}",
                f"status: {validation.get('status')}",
                f"fresh: {str(bool(validation.get('fresh'))).lower() if validation.get('fresh') is not None else None}",
            ]
        )
        if validation.get("exists"):
            lines.extend(
                [
                    f"passed: {str(bool(validation.get('passed'))).lower()}",
                    f"ready_to_finalize: {str(bool(validation.get('ready_to_finalize'))).lower()}",
                    f"applied_count: {validation.get('applied_count')}",
                    f"approved_count: {validation.get('approved_count')}",
                    f"rejected_count: {validation.get('rejected_count')}",
                    f"pending_count: {validation.get('pending_count')}",
                    f"pending_decision_count: {validation.get('pending_decision_count')}",
                    f"decision_ready: {str(bool(validation.get('decision_ready'))).lower()}",
                    f"reviewed_count: {validation.get('reviewed_count')}",
                    f"total_count: {validation.get('total_count')}",
                    f"progress_percent: {validation.get('progress_percent')}",
                    f"next_action: {validation.get('next_action')}",
                ]
            )
            decision_progress = validation.get("decision_progress") or {}
            if decision_progress:
                lines.extend(
                    [
                        "decision_progress:",
                        f"total_decision_count: {decision_progress.get('total_decision_count')}",
                        f"reviewed_decision_count: {decision_progress.get('reviewed_decision_count')}",
                        f"pending_decision_count: {decision_progress.get('pending_decision_count')}",
                        f"inconsistent_decision_count: {decision_progress.get('inconsistent_decision_count')}",
                        f"decision_progress_percent: {decision_progress.get('progress_percent')}",
                    ]
                )
            pending_rows = validation.get("pending_rows") or []
            pending_review_questions = validation.get("pending_review_questions") or []
            if pending_review_questions:
                lines.append("pending_review_questions:")
                for item in pending_review_questions:
                    row_indices = ", ".join(str(value) for value in item.get("row_indices") or [])
                    lines.append(
                        "- cluster {cluster_id} speaker {speaker}: {question} ({clip_count} clips; rows {row_indices}; acoustic {acoustic_verdict})".format(
                            cluster_id=item.get("cluster_id"),
                            speaker=item.get("speaker"),
                            question=item.get("question"),
                            clip_count=item.get("clip_count"),
                            row_indices=row_indices,
                            acoustic_verdict=item.get("acoustic_verdict"),
                        )
                    )
                    for sample in item.get("transcript_samples") or []:
                        lines.append(
                            "  sample row {row_index}: {excerpt}".format(
                                row_index=sample.get("row_index"),
                                excerpt=sample.get("excerpt"),
                            )
                        )
            if pending_rows:
                lines.append("pending_rows:")
                for row in pending_rows:
                    lines.append(
                        "- row {row_index} cluster {cluster_id} speaker {speaker}: {question} ({clip_path})".format(
                            row_index=row.get("row_index"),
                            cluster_id=row.get("cluster_id"),
                            speaker=row.get("speaker"),
                            question=row.get("question"),
                            clip_path=row.get("clip_path"),
                        )
                    )
            blockers = validation.get("blockers") or []
            if blockers:
                lines.append("blockers: " + "; ".join(str(blocker) for blocker in blockers))
        if validation.get("error"):
            lines.append(f"error: {validation.get('error')}")
    artifact_checks = handoff.get("artifact_checks") if isinstance(handoff.get("artifact_checks"), dict) else None
    if artifact_checks:
        lines.extend(["", "artifact_checks:"])
        if handoff.get("artifact_manifest_sha256"):
            lines.append(f"artifact_manifest_sha256: {handoff.get('artifact_manifest_sha256')}")
        for name in sorted(artifact_checks):
            check = artifact_checks.get(name) or {}
            lines.append(
                f"{name}: exists={str(bool(check.get('exists'))).lower()} bytes={check.get('bytes')} sha256={check.get('sha256')} path={check.get('path')}"
            )
    return "\n".join(lines).rstrip() + "\n"


def _review_packet_summary(batch_root: Path, cluster_gate: dict[str, Any] | None) -> dict[str, Any]:
    bundle = batch_root / "pavo-cluster-question-bundle"
    gate = cluster_gate or {}
    review_queue = gate.get("review_queue") or {}
    summary = review_queue.get("summary") or {}
    items = review_queue.get("items") or []
    top_items = [
        {
            "rank": item.get("rank"),
            "row_index": item.get("row_index"),
            "cluster_id": item.get("cluster_id"),
            "question": item.get("question"),
            "target_speaker": item.get("target_speaker"),
            "priority_tier": item.get("priority_tier"),
            "priority_score": item.get("priority_score"),
            "priority_reason": item.get("priority_reason"),
            "unlockable_segments": item.get("unlockable_segments"),
            "unlockable_seconds": item.get("unlockable_seconds"),
            "acoustic_verdict": item.get("acoustic_verdict"),
            "clip_path": item.get("clip_path"),
            "transcript_excerpt": item.get("transcript_excerpt"),
            "approve_effect": item.get("approve_effect"),
            "reject_effect": item.get("reject_effect"),
            "terminal_decision_rule": item.get("terminal_decision_rule"),
        }
        for item in items[:7]
    ]
    proof_slate_items = _proof_review_slate_items(gate.get("review_sheet"), top_items)
    return {
        "state": gate.get("state"),
        "item_count": len(items),
        "proof_slate_item_count": len(proof_slate_items),
        "minimum_reviews": summary.get("minimum_reviews"),
        "pending_reviews": summary.get("pending_reviews"),
        "possible_reviews_saved": summary.get("possible_reviews_saved"),
        "reduction_percent": summary.get("reduction_percent"),
        "total_unlockable_segments": summary.get("total_unlockable_segments"),
        "total_unlockable_seconds": summary.get("total_unlockable_seconds"),
        "forecast_risk_adjusted_segments": summary.get("forecast_risk_adjusted_segments"),
        "review_sheet": gate.get("review_sheet"),
        "slate_tsv": str(bundle / "pavo-cluster-review-decision-slate.tsv"),
        "slate_markdown": str(bundle / "pavo-cluster-review-decision-slate.md"),
        "decision_brief_json": str(bundle / "pavo-cluster-review-decision-brief.json"),
        "decision_brief_markdown": str(bundle / "pavo-cluster-review-decision-brief.md"),
        "decision_brief_html": str(bundle / "pavo-cluster-review-decision-brief.html"),
        "review_page": str(bundle / "index.html"),
        "validate_command": review_queue.get("validate_command"),
        "finish_command": gate.get("finish_command") or review_queue.get("finish_command"),
        "top_items": top_items,
        "proof_slate_items": proof_slate_items,
        "safety_boundary": "Review packet lists required human speaker decisions; it does not approve identity.",
    }


def _add_proof_slate_commands(
    review_packet: dict[str, Any],
    *,
    batch_root: Path,
    proof_review_slate_path: Path,
) -> None:
    review_sheet = str(review_packet.get("review_sheet") or "").strip()
    if not review_sheet:
        review_packet["proof_review_slate_tsv"] = str(proof_review_slate_path)
        review_packet["validate_proof_slate_command"] = None
        review_packet["finish_proof_slate_command"] = None
        return
    validation_report = proof_review_slate_path.with_suffix(".validation.json")
    review_packet["proof_review_slate_tsv"] = str(proof_review_slate_path)
    review_packet["validate_proof_slate_command"] = (
        "pavo review clusters validate-slate "
        f"{shlex.quote(review_sheet)} "
        f"{shlex.quote(str(proof_review_slate_path))} "
        f"--report {shlex.quote(str(validation_report))}"
    )
    review_packet["finish_proof_slate_command"] = (
        "pavo review clusters finish-from-slate "
        f"{shlex.quote(str(batch_root))} "
        f"{shlex.quote(review_sheet)} "
        f"{shlex.quote(str(proof_review_slate_path))}"
    )


def _proof_review_slate_items(review_sheet: Any, top_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sheet_path = Path(str(review_sheet)) if review_sheet else None
    if not sheet_path or not sheet_path.exists():
        return top_items
    try:
        sheet = json.loads(sheet_path.read_text())
    except (OSError, json.JSONDecodeError):
        return top_items
    rows = sheet.get("rows") or []
    if not rows:
        return top_items
    top_by_cluster = {str(item.get("cluster_id") or ""): item for item in top_items}
    top_by_row = {str(item.get("row_index") or ""): item for item in top_items}
    proof_items: list[dict[str, Any]] = []
    for row in rows:
        question = row.get("cluster_question") if isinstance(row.get("cluster_question"), dict) else {}
        row_index = row.get("index")
        cluster_id = str(question.get("cluster_id") or row.get("case") or "")
        top = top_by_row.get(str(row_index)) or top_by_cluster.get(cluster_id) or {}
        target_speaker = (
            top.get("target_speaker")
            or question.get("candidate_name")
            or question.get("dominant_speaker")
            or row.get("target_speaker_name")
            or row.get("target_speaker_label")
            or ""
        )
        transcript = str(row.get("text") or "").strip()
        if len(transcript) > 120:
            transcript = transcript[:117].rstrip() + "..."
        proof_items.append(
            {
                "rank": top.get("rank") or len(proof_items) + 1,
                "row_index": row_index,
                "cluster_id": cluster_id,
                "question": top.get("question") or question.get("question") or f"Review cluster {cluster_id}",
                "target_speaker": target_speaker,
                "priority_tier": top.get("priority_tier"),
                "priority_score": top.get("priority_score"),
                "priority_reason": top.get("priority_reason"),
                "acoustic_verdict": top.get("acoustic_verdict"),
                "clip_path": row.get("clip_path") or top.get("clip_path"),
                "transcript_excerpt": transcript or top.get("transcript_excerpt"),
            }
        )
    return proof_items


def _render_proof_review_checklist(
    *,
    batch_root: Path,
    proof_slate_items: list[dict[str, Any]],
    proof_review_slate_path: Path,
    validate_command: str | None = None,
    finish_command: str | None = None,
    strict_proof_command: str | None = None,
    handoff_command: str | None = None,
) -> str:
    grouped = _handoff_pending_review_questions(
        [
            {
                "row_index": str(item.get("row_index") or ""),
                "cluster_id": str(item.get("cluster_id") or ""),
                "speaker": str(item.get("target_speaker") or ""),
                "question": str(item.get("question") or ""),
                "clip_path": str(item.get("clip_path") or ""),
                "priority_tier": item.get("priority_tier"),
                "priority_score": item.get("priority_score"),
                "acoustic_verdict": item.get("acoustic_verdict"),
                "transcript": item.get("transcript_excerpt"),
            }
            for item in proof_slate_items
        ]
    )
    lines = [
        "# Pavo Proof Review Checklist",
        "",
        f"- Batch root: `{batch_root}`",
        f"- Proof TSV to edit: `{proof_review_slate_path}`",
        f"- Pending speaker decisions: {len(grouped)}",
        f"- Supporting proof rows: {len(proof_slate_items)}",
        "",
        "Work top to bottom. Listen before approving identity; reject or correct the speaker when the clip contradicts the proposal.",
        "",
    ]
    if not grouped:
        lines.append("- No pending review questions were generated.")
    for index, item in enumerate(grouped, start=1):
        row_indices = ", ".join(str(value) for value in item.get("row_indices") or [])
        lines.extend(
            [
                f"## {index}. Cluster `{item.get('cluster_id')}` - {item.get('speaker')}",
                "",
                f"- Question: {item.get('question')}",
                f"- Rows: {row_indices}",
                f"- Clips: {item.get('clip_count')}",
                f"- Priority: `{item.get('priority_tier')}` / {item.get('priority_score')}",
                f"- Acoustic verdict: `{item.get('acoustic_verdict')}`",
                "",
                "- [ ] Listen to every supporting clip.",
                "- [ ] Decide `approved` / `rejected` for each row in the TSV.",
                "- [ ] Correct the `speaker` value if needed.",
                "- [ ] Add a short note for any rejection, correction, overlap, or uncertainty.",
                "",
                "Evidence:",
            ]
        )
        clip_paths = item.get("clip_paths") or []
        samples = item.get("transcript_samples") or []
        for sample_index, sample in enumerate(samples, start=1):
            clip_path = clip_paths[sample_index - 1] if sample_index - 1 < len(clip_paths) else ""
            lines.append(f"- Row {sample.get('row_index')}: `{clip_path}`")
            lines.append(f"  - Transcript: {sample.get('excerpt')}")
        lines.append("")
    lines.extend(
        [
            "## Finish Commands",
            "",
            "After editing the TSV, validate before mutation:",
            "",
            "```bash",
            str(validate_command or ""),
            "```",
            "",
            "If validation passes, materialize the reviewed speaker decisions:",
            "",
            "```bash",
            str(finish_command or ""),
            "```",
            "",
            "Then re-check the handoff and require strict proof:",
            "",
            "```bash",
            str(handoff_command or ""),
            str(strict_proof_command or ""),
            "```",
            "",
            "Do not run the finish command until validation passes.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _review_packet_slate_tsv_lines(items: list[dict[str, Any]]) -> list[str]:
    decision_keys = [
        (
            str(item.get("cluster_id") or ""),
            str(item.get("target_speaker") or ""),
            str(item.get("question") or ""),
        )
        for item in items
    ]
    decision_order: list[tuple[str, str, str]] = []
    for key in decision_keys:
        if key not in decision_order:
            decision_order.append(key)
    decision_meta: dict[tuple[str, str, str], dict[str, int]] = {}
    for index, key in enumerate(decision_order, start=1):
        row_count = sum(1 for candidate in decision_keys if candidate == key)
        decision_meta[key] = {"index": index, "row_count": row_count}
    lines = [
        "\t".join(
            [
                "row_index",
                "cluster_id",
                "decision",
                "speaker",
                "note",
                "rank",
                "priority_tier",
                "priority_score",
                "priority_reason",
                "question",
                "acoustic_verdict",
                "clip_path",
                "transcript",
                "decision_group",
                "decision_row_count",
                "decision_clip_count",
            ]
        )
    ]
    for item in items:
        key = (
            str(item.get("cluster_id") or ""),
            str(item.get("target_speaker") or ""),
            str(item.get("question") or ""),
        )
        meta = decision_meta.get(key, {"index": 0, "row_count": 1})
        note = f"reviewed via pavo-batch-proof rank {item.get('rank')}; {item.get('question') or ''}"
        lines.append(
            "\t".join(
                [
                    str(item.get("row_index") or ""),
                    str(item.get("cluster_id") or ""),
                    "pending",
                    str(item.get("target_speaker") or ""),
                    _tsv_safe(note),
                    str(item.get("rank") or ""),
                    _tsv_safe(str(item.get("priority_tier") or "")),
                    _tsv_safe(str(item.get("priority_score") or "")),
                    _tsv_safe(str(item.get("priority_reason") or "")),
                    _tsv_safe(str(item.get("question") or "")),
                    _tsv_safe(str(item.get("acoustic_verdict") or "")),
                    _tsv_safe(str(item.get("clip_path") or "")),
                    _tsv_safe(str(item.get("transcript_excerpt") or "")),
                    f"D{meta['index']:02d}",
                    str(meta["row_count"]),
                    str(meta["row_count"]),
                ]
            )
        )
    return lines


def _review_packet_decision_slate_tsv_lines(items: list[dict[str, Any]]) -> list[str]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []
    for item in items:
        key = (
            str(item.get("cluster_id") or ""),
            str(item.get("target_speaker") or ""),
            str(item.get("question") or ""),
        )
        if key not in grouped:
            grouped[key] = {
                "cluster_id": item.get("cluster_id"),
                "speaker": item.get("target_speaker"),
                "question": item.get("question"),
                "row_indices": [],
                "clip_paths": [],
                "transcript_samples": [],
                "priority_tier": item.get("priority_tier"),
                "priority_score": item.get("priority_score"),
                "priority_reason": item.get("priority_reason"),
                "acoustic_verdict": item.get("acoustic_verdict"),
            }
            order.append(key)
        group = grouped[key]
        if item.get("row_index") is not None:
            group["row_indices"].append(str(item.get("row_index")))
        if item.get("clip_path"):
            group["clip_paths"].append(str(item.get("clip_path")))
        if item.get("transcript_excerpt"):
            group["transcript_samples"].append(str(item.get("transcript_excerpt")))
    lines = [
        "\t".join(
            [
                "decision_group",
                "decision",
                "speaker",
                "review_reason",
                "cluster_id",
                "question",
                "row_indices",
                "clip_count",
                "priority_tier",
                "priority_score",
                "priority_reason",
                "acoustic_verdict",
                "clip_paths",
                "transcript_samples",
            ]
        )
    ]
    for index, key in enumerate(order, start=1):
        group = grouped[key]
        lines.append(
            "\t".join(
                [
                    f"D{index:02d}",
                    "pending",
                    _tsv_safe(str(group.get("speaker") or "")),
                    "",
                    _tsv_safe(str(group.get("cluster_id") or "")),
                    _tsv_safe(str(group.get("question") or "")),
                    _tsv_safe(",".join(group.get("row_indices") or [])),
                    str(len(group.get("clip_paths") or [])),
                    _tsv_safe(str(group.get("priority_tier") or "")),
                    _tsv_safe(str(group.get("priority_score") or "")),
                    _tsv_safe(str(group.get("priority_reason") or "")),
                    _tsv_safe(str(group.get("acoustic_verdict") or "")),
                    _tsv_safe(" | ".join(group.get("clip_paths") or [])),
                    _tsv_safe(" | ".join(group.get("transcript_samples") or [])),
                ]
            )
        )
    return lines


def apply_batch_decision_slate(
    proof_report_path: Path | str,
    decision_slate_path: Path | str,
    *,
    out_path: Path | str,
) -> BatchDecisionSlateApplyResult:
    proof_path = Path(proof_report_path)
    proof_report = json.loads(proof_path.read_text())
    review_slate_value = (
        proof_report.get("proof_review_slate_path")
        or (proof_report.get("review_packet") or {}).get("proof_review_slate_tsv")
        or (proof_report.get("operator_handoff") or {}).get("proof_review_slate_tsv")
    )
    if not review_slate_value:
        raise ValueError(f"proof report does not name a proof review slate: {proof_path}")
    review_slate_path = Path(str(review_slate_value))
    if not review_slate_path.exists():
        raise FileNotFoundError(f"proof review slate not found: {review_slate_path}")

    decision_path = Path(decision_slate_path)
    decisions = _read_decision_slate_tsv(decision_path)
    review_rows, fieldnames = _read_tsv(review_slate_path)
    if "review_reason" not in fieldnames:
        fieldnames.append("review_reason")
    missing_decision_groups: list[str] = []
    applied_row_count = 0
    approved_row_count = 0
    rejected_row_count = 0
    pending_row_count = 0
    skipped_row_count = 0

    for row in review_rows:
        decision_group = str(row.get("decision_group") or "").strip()
        if not decision_group:
            skipped_row_count += 1
            continue
        decision = decisions.get(decision_group)
        if decision is None:
            if decision_group not in missing_decision_groups:
                missing_decision_groups.append(decision_group)
            skipped_row_count += 1
            continue
        applied_row_count += 1
        row["decision"] = decision["decision"]
        if decision.get("speaker"):
            row["speaker"] = decision["speaker"]
        row["review_reason"] = decision.get("review_reason", "")
        if decision["decision"] == "approved":
            approved_row_count += 1
        elif decision["decision"] == "rejected":
            rejected_row_count += 1
        else:
            pending_row_count += 1

    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_tsv(target, review_rows, fieldnames)
    return BatchDecisionSlateApplyResult(
        proof_report_path=proof_path,
        proof_review_slate_path=review_slate_path,
        decision_slate_path=decision_path,
        out_path=target,
        row_count=len(review_rows),
        decision_count=len(decisions),
        applied_row_count=applied_row_count,
        approved_row_count=approved_row_count,
        rejected_row_count=rejected_row_count,
        pending_row_count=pending_row_count,
        skipped_row_count=skipped_row_count,
        missing_decision_groups=missing_decision_groups,
    )


def apply_batch_decision_board_audit(
    proof_report_path: Path | str,
    audit_path: Path | str,
    *,
    proof_review_slate_out_path: Path | str,
    decision_slate_out_path: Path | str | None = None,
) -> BatchDecisionBoardAuditApplyResult:
    proof_path = Path(proof_report_path)
    audit = Path(audit_path)
    payload = json.loads(audit.read_text())
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    source_proof = str(source.get("proofReport") or "").strip()
    if source_proof and Path(source_proof) != proof_path:
        raise ValueError(
            f"decision-board audit was exported for {source_proof}, not {proof_path}; "
            "use the matching proof report"
        )
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"decision-board audit has no rows: {audit}")
    decision_slate_out = (
        Path(decision_slate_out_path)
        if decision_slate_out_path
        else audit.with_name("pavo-batch-proof.decision-slate.reviewed.tsv")
    )
    fieldnames = [
        "decision_group",
        "decision",
        "speaker",
        "review_reason",
        "cluster_id",
        "question",
        "row_indices",
        "clip_count",
        "priority_tier",
        "priority_score",
        "priority_reason",
        "acoustic_verdict",
        "clip_paths",
        "transcript_samples",
    ]
    decision_rows: list[dict[str, str]] = []
    approved_decision_count = 0
    rejected_decision_count = 0
    pending_decision_count = 0
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"decision-board audit row {index} is not an object")
        decision_group = str(row.get("decision_group") or "").strip()
        if not decision_group:
            raise ValueError(f"decision-board audit row {index} is missing decision_group")
        decision = str(row.get("decision") or "").strip().lower()
        if decision not in VALID_REVIEW_DECISIONS:
            raise ValueError(
                f"decision-board audit row {index} has invalid decision {decision!r}; "
                f"expected one of {sorted(VALID_REVIEW_DECISIONS)}"
            )
        if decision == "approved":
            approved_decision_count += 1
        elif decision == "rejected":
            rejected_decision_count += 1
        else:
            pending_decision_count += 1
        review_reason = str(row.get("review_reason") or "").strip()
        if decision in {"approved", "rejected"}:
            if review_reason not in BATCH_SPEAKER_REVIEW_REASONS:
                raise ValueError(
                    f"decision-board audit row {index} has invalid or missing review_reason {review_reason!r}; "
                    f"expected one of {sorted(BATCH_SPEAKER_REVIEW_REASONS)}"
                )
        decision_rows.append({field: _tsv_safe(str(row.get(field) or "")) for field in fieldnames})
    _write_tsv(decision_slate_out, decision_rows, fieldnames)
    applied = apply_batch_decision_slate(
        proof_path,
        decision_slate_out,
        out_path=proof_review_slate_out_path,
    )
    return BatchDecisionBoardAuditApplyResult(
        proof_report_path=proof_path,
        audit_path=audit,
        decision_slate_out_path=decision_slate_out,
        proof_review_slate_out_path=Path(proof_review_slate_out_path),
        decision_count=len(decision_rows),
        approved_decision_count=approved_decision_count,
        rejected_decision_count=rejected_decision_count,
        pending_decision_count=pending_decision_count,
        applied_row_count=applied.applied_row_count,
        approved_row_count=applied.approved_row_count,
        rejected_row_count=applied.rejected_row_count,
        pending_row_count=applied.pending_row_count,
        missing_decision_groups=applied.missing_decision_groups,
    )


def build_batch_speaker_memory_candidates(
    proof_report_path: Path | str,
    *,
    proof_review_slate_path: Path | str | None = None,
    out_path: Path | str,
) -> BatchSpeakerMemoryCandidateResult:
    proof_path = Path(proof_report_path)
    resolved_slate = Path(proof_review_slate_path) if proof_review_slate_path else _proof_review_slate_path_from_report(proof_path)
    review_rows, _fieldnames = _read_tsv(resolved_slate)
    approved_rows = [row for row in review_rows if str(row.get("decision") or "").strip().lower() == "approved"]
    rejected_rows = [row for row in review_rows if str(row.get("decision") or "").strip().lower() == "rejected"]
    pending_rows = [
        row
        for row in review_rows
        if str(row.get("decision") or "").strip().lower() not in {"approved", "rejected"}
    ]
    by_speaker: dict[str, dict[str, Any]] = {}
    for row in approved_rows:
        speaker = str(row.get("speaker") or "").strip()
        if not speaker or _unknown_speaker_label(speaker):
            continue
        entry = by_speaker.setdefault(
            speaker,
            {
                "speaker": speaker,
                "speaker_slug": _speaker_slug(speaker),
                "sample_count": 0,
                "clusters": [],
                "samples": [],
            },
        )
        cluster_id = str(row.get("cluster_id") or "").strip()
        if cluster_id and cluster_id not in entry["clusters"]:
            entry["clusters"].append(cluster_id)
        entry["sample_count"] += 1
        entry["samples"].append(
            {
                "row_index": row.get("row_index"),
                "cluster_id": row.get("cluster_id"),
                "decision_group": row.get("decision_group"),
                "clip_path": row.get("clip_path"),
                "transcript": row.get("transcript"),
                "question": row.get("question"),
                "note": row.get("note"),
                "review_reason": row.get("review_reason"),
                "acoustic_verdict": row.get("acoustic_verdict"),
                "priority_tier": row.get("priority_tier"),
                "priority_score": row.get("priority_score"),
                "source_proof_review_slate_tsv": str(resolved_slate),
            }
        )
    candidates = sorted(by_speaker.values(), key=lambda item: (-int(item["sample_count"]), item["speaker"]))
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    result = BatchSpeakerMemoryCandidateResult(
        proof_report_path=proof_path,
        proof_review_slate_path=resolved_slate,
        out_path=target,
        candidate_count=sum(int(item["sample_count"]) for item in candidates),
        speaker_count=len(candidates),
        approved_row_count=len(approved_rows),
        rejected_row_count=len(rejected_rows),
        pending_row_count=len(pending_rows),
        candidates=candidates,
    )
    target.write_text(json.dumps(result.as_report(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def finalize_batch_reviewed_proof(
    proof_report_path: Path | str,
    *,
    proof_review_slate_path: Path | str | None = None,
    baseline_brief_path: Path | str | None = None,
    out_dir: Path | str | None = None,
) -> BatchReviewedProofFinalizeResult:
    proof_path = Path(proof_report_path)
    proof_report = json.loads(proof_path.read_text())
    batch_root_value = str(proof_report.get("batch_root") or "").strip()
    if not batch_root_value:
        raise ValueError(f"proof report does not name a batch root: {proof_path}")
    batch_root = Path(batch_root_value)
    review_packet = proof_report.get("review_packet") if isinstance(proof_report.get("review_packet"), dict) else {}
    review_sheet_value = review_packet.get("review_sheet")
    if not review_sheet_value:
        raise ValueError(f"proof report does not name a review sheet: {proof_path}")
    review_sheet_path = Path(str(review_sheet_value))
    proof_slate_path = Path(proof_review_slate_path) if proof_review_slate_path else _proof_review_slate_path_from_report(proof_path)
    target_dir = Path(out_dir) if out_dir else batch_root
    target_dir.mkdir(parents=True, exist_ok=True)
    validation_report_path = proof_slate_path.with_suffix(".validation.json")
    validation = validate_cluster_review_slate(review_sheet_path, proof_slate_path)
    validation_report_path.write_text(json.dumps(validation.as_report(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    blockers = list(validation.blockers)
    finish_report = None
    strict_proof_report = None
    memory_result = None

    if validation.ready_to_finalize:
        finish = finish_cluster_review_from_slate(
            batch_root,
            review_sheet_path,
            proof_slate_path,
            baseline_brief_path=baseline_brief_path,
            out_dir=target_dir,
        )
        finish_report = finish.as_report()
        blockers.extend(finish.blockers)
        if finish.passed:
            memory_result = build_batch_speaker_memory_candidates(
                proof_path,
                proof_review_slate_path=proof_slate_path,
                out_path=target_dir / "pavo-speaker-memory-candidates.json",
            )
            strict_proof = prove_batch(batch_root, out_dir=target_dir)
            strict_proof_report = strict_proof.as_report()
            if not strict_proof_report.get("complete"):
                blockers.append("strict proof did not complete after finalization")
    else:
        blockers.append("proof slate is not ready to finalize")

    blockers = list(dict.fromkeys(blockers))
    finish_passed = bool(finish_report and finish_report.get("passed"))
    strict_complete = bool(strict_proof_report and strict_proof_report.get("complete"))
    passed = bool(validation.ready_to_finalize and finish_passed and strict_complete and not blockers)
    return BatchReviewedProofFinalizeResult(
        proof_report_path=proof_path,
        batch_root=batch_root,
        review_sheet_path=review_sheet_path,
        proof_review_slate_path=proof_slate_path,
        validation_report_path=validation_report_path,
        passed=passed,
        finalized=finish_passed,
        validation_ready=validation.ready_to_finalize,
        finish_passed=finish_passed,
        strict_proof_complete=strict_complete,
        speaker_memory_candidates_path=memory_result.out_path if memory_result else None,
        speaker_memory_candidate_count=memory_result.candidate_count if memory_result else 0,
        speaker_memory_speaker_count=memory_result.speaker_count if memory_result else 0,
        blockers=blockers,
        validation=validation.as_report(),
        finish=finish_report,
        strict_proof=strict_proof_report,
    )


def finalize_batch_decision_board_audit(
    proof_report_path: Path | str,
    audit_path: Path | str,
    *,
    proof_review_slate_out_path: Path | str | None = None,
    decision_slate_out_path: Path | str | None = None,
    baseline_brief_path: Path | str | None = None,
    out_dir: Path | str | None = None,
) -> BatchDecisionBoardAuditFinalizeResult:
    proof_path = Path(proof_report_path)
    proof_report = json.loads(proof_path.read_text())
    batch_root_value = str(proof_report.get("batch_root") or "").strip()
    if not batch_root_value:
        raise ValueError(f"proof report does not name a batch root: {proof_path}")
    batch_root = Path(batch_root_value)
    proof_review_slate_out = (
        Path(proof_review_slate_out_path)
        if proof_review_slate_out_path
        else batch_root / "pavo-batch-proof.review-slate.tsv"
    )
    decision_slate_out = (
        Path(decision_slate_out_path)
        if decision_slate_out_path
        else batch_root / "pavo-batch-proof.decision-slate.reviewed.tsv"
    )
    imported = apply_batch_decision_board_audit(
        proof_path,
        audit_path,
        proof_review_slate_out_path=proof_review_slate_out,
        decision_slate_out_path=decision_slate_out,
    )
    finalized = finalize_batch_reviewed_proof(
        proof_path,
        proof_review_slate_path=proof_review_slate_out,
        baseline_brief_path=baseline_brief_path,
        out_dir=out_dir,
    )
    blockers = list(dict.fromkeys((finalized.blockers or []) + (imported.missing_decision_groups or [])))
    return BatchDecisionBoardAuditFinalizeResult(
        proof_report_path=proof_path,
        audit_path=Path(audit_path),
        decision_slate_out_path=decision_slate_out,
        proof_review_slate_out_path=proof_review_slate_out,
        passed=bool(finalized.passed and not imported.missing_decision_groups),
        finalized=finalized.finalized,
        validation_ready=finalized.validation_ready,
        finish_passed=finalized.finish_passed,
        strict_proof_complete=finalized.strict_proof_complete,
        import_report=imported.as_report(),
        finalization_report=finalized.as_report(),
        blockers=blockers,
    )


def write_batch_decision_board(
    proof_report_path: Path | str,
    *,
    out_path: Path | str | None = None,
) -> BatchDecisionBoardResult:
    proof_path = Path(proof_report_path)
    proof_report = json.loads(proof_path.read_text())
    operator = proof_report.get("operator_handoff") if isinstance(proof_report.get("operator_handoff"), dict) else {}
    decision_slate_value = (
        proof_report.get("proof_decision_slate_path")
        or (proof_report.get("review_packet") or {}).get("proof_decision_slate_tsv")
        or operator.get("proof_decision_slate_tsv")
    )
    if not decision_slate_value:
        raise ValueError(f"proof report does not name a decision slate: {proof_path}")
    decision_slate_path = Path(str(decision_slate_value))
    if not decision_slate_path.exists():
        raise FileNotFoundError(f"proof decision slate not found: {decision_slate_path}")
    decisions, _decision_fields = _read_tsv(decision_slate_path)
    proof_slate_path = _proof_review_slate_path_from_report(proof_path)
    proof_rows, _proof_fields = _read_tsv(proof_slate_path)
    rows_by_group: dict[str, list[dict[str, str]]] = {}
    for row in proof_rows:
        rows_by_group.setdefault(str(row.get("decision_group") or ""), []).append(row)
    target = Path(out_path) if out_path else proof_path.with_name("pavo-batch-proof.decision-board.html")
    target.parent.mkdir(parents=True, exist_ok=True)
    html = _render_batch_decision_board_html(
        proof_report=proof_report,
        proof_report_path=proof_path,
        proof_slate_path=proof_slate_path,
        decision_slate_path=decision_slate_path,
        decisions=decisions,
        rows_by_group=rows_by_group,
    )
    target.write_text(html, encoding="utf-8")
    pending_count = sum(1 for row in decisions if str(row.get("decision") or "").strip().lower() == "pending")
    return BatchDecisionBoardResult(
        proof_report_path=proof_path,
        decision_slate_path=decision_slate_path,
        out_path=target,
        decision_count=len(decisions),
        pending_decision_count=pending_count,
        supporting_row_count=len(proof_rows),
    )


def verify_batch_decision_board(
    proof_report_path: Path | str,
    *,
    decision_board_path: Path | str | None = None,
) -> BatchDecisionBoardVerifyResult:
    proof_path = Path(proof_report_path)
    proof_report = json.loads(proof_path.read_text())
    board_value = decision_board_path or proof_report.get("proof_decision_board_path")
    if not board_value:
        board_value = (proof_report.get("review_packet") or {}).get("proof_decision_board_html")
    if not board_value:
        board_value = (proof_report.get("operator_handoff") or {}).get("proof_decision_board_html")
    if not board_value:
        raise ValueError(f"proof report does not name a decision board: {proof_path}")
    board_path = Path(str(board_value))
    decision_slate_value = (
        proof_report.get("proof_decision_slate_path")
        or (proof_report.get("review_packet") or {}).get("proof_decision_slate_tsv")
        or (proof_report.get("operator_handoff") or {}).get("proof_decision_slate_tsv")
    )
    if not decision_slate_value:
        raise ValueError(f"proof report does not name a decision slate: {proof_path}")
    decision_slate_path = Path(str(decision_slate_value))
    decisions, _decision_fields = _read_tsv(decision_slate_path)
    proof_slate_path = _proof_review_slate_path_from_report(proof_path)
    proof_rows, _proof_fields = _read_tsv(proof_slate_path)
    html = board_path.read_text(encoding="utf-8") if board_path.exists() else ""
    pending_count = sum(1 for row in decisions if str(row.get("decision") or "").strip().lower() == "pending")
    expected_decision_count = _proof_report_decision_count(proof_report, default=len(decisions))
    expected_supporting_count = _proof_report_supporting_row_count(proof_report, default=len(proof_rows))
    card_count = html.count('class="card"')
    checks = [
        _check("decision_board_exists", board_path.exists() and board_path.is_file(), str(board_path)),
        _check("decision_slate_exists", decision_slate_path.exists() and decision_slate_path.is_file(), str(decision_slate_path)),
        _check("proof_review_slate_exists", proof_slate_path.exists() and proof_slate_path.is_file(), str(proof_slate_path)),
        _check("decision_count_matches", len(decisions) == expected_decision_count, f"{len(decisions)}/{expected_decision_count}"),
        _check("supporting_row_count_matches", len(proof_rows) == expected_supporting_count, f"{len(proof_rows)}/{expected_supporting_count}"),
        _check("has_decision_cards", card_count >= len(decisions), f"{card_count}/{len(decisions)}"),
        _check("has_download_tsv", "Download TSV" in html and "downloadTsv" in html, "Download TSV control"),
        _check("has_download_audit_json", "Download Audit JSON" in html and "downloadAudit" in html, "Download Audit JSON control"),
        _check("has_review_sprint", "Review Sprint" in html and "focusNextPending" in html, "guided review sprint"),
        _check(
            "has_decision_rubric",
            "Decision Rubric" in html and all(rule in html for rule in BATCH_SPEAKER_DECISION_RUBRIC),
            "approve/reject/pending rubric",
        ),
        _check(
            "has_review_reason_controls",
            "Review reason" in html and "approved_clean_match" in html and "updateReviewReason" in html,
            "structured reason controls",
        ),
        _check(
            "has_reasoned_decision_shortcuts",
            "setDecisionWithReason" in html and "Approve clean" in html and "Reject wrong speaker" in html,
            "one-click reasoned decision shortcuts",
        ),
        _check(
            "has_inline_evidence_hints",
            "Review guidance" in html
            and "Decision shape" in html
            and "Decision risk" in html
            and "Suggested action" in html
            and "Evidence hints" in html,
            "inline speaker evidence guidance",
        ),
        _check(
            "has_risk_aware_focus",
            "Focus high risk" in html
            and "focusNextHighRisk" in html
            and "high-risk-count" in html
            and "data-risk" in html,
            "risk-aware review navigation",
        ),
        _check(
            "has_review_reason_export_gate",
            "validateAuditReady" in html and "Missing review reason" in html,
            "client-side reason gate before audit export",
        ),
        _check(
            "has_live_review_completion",
            "missing-reason-count" in html and "export-ready-status" in html and "review-progress-percent" in html,
            "live review completion scorecards",
        ),
        _check(
            "has_audit_completion_summary",
            "reviewCompletion" in html and "progressPercent" in html and "missingReasonCount" in html,
            "audit JSON includes review completion summary",
        ),
        _check(
            "has_audit_review_context",
            "reviewContext" in html
            and "decision_risk" in html
            and "suggested_review_action" in html
            and "evidence_hints" in html,
            "audit JSON includes speaker review context",
        ),
        _check("has_autosave", "localStorage" in html and "Autosaved locally" in html, "localStorage autosave"),
        _check("has_audit_events", "auditEvents" in html and "auditPayload" in html, "audit event export"),
        _check("has_finalize_board_audit_command", "pavo batch finalize-board-audit" in html, "finalize-board-audit command"),
        _check("has_apply_board_audit_command", "pavo batch apply-decision-board-audit" in html, "apply-decision-board-audit command"),
        _check("has_finalize_reviewed_proof_command", "pavo batch finalize-reviewed-proof" in html, "finalize-reviewed-proof command"),
        _check("has_safety_boundary", "does not write files or approve identity by itself" in html, "identity safety boundary"),
    ]
    blockers = [f"{check['name']}: {check['detail']}" for check in checks if not check.get("passed")]
    board_fingerprint = _file_fingerprint(board_path) if board_path.exists() and board_path.is_file() else {}
    return BatchDecisionBoardVerifyResult(
        proof_report_path=proof_path,
        decision_board_path=board_path,
        passed=not blockers,
        decision_count=len(decisions),
        expected_decision_count=expected_decision_count,
        pending_decision_count=pending_count,
        supporting_row_count=len(proof_rows),
        expected_supporting_row_count=expected_supporting_count,
        checks=checks,
        blockers=blockers,
        board_fingerprint=board_fingerprint,
    )


def _proof_report_decision_count(proof_report: dict[str, Any], *, default: int) -> int:
    review_packet = proof_report.get("review_packet") if isinstance(proof_report.get("review_packet"), dict) else {}
    value = review_packet.get("proof_decision_count") or review_packet.get("decision_count")
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _proof_report_supporting_row_count(proof_report: dict[str, Any], *, default: int) -> int:
    review_packet = proof_report.get("review_packet") if isinstance(proof_report.get("review_packet"), dict) else {}
    value = review_packet.get("proof_slate_item_count") or proof_report.get("proof_slate_item_count")
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def write_batch_review_pack(
    proof_report_path: Path | str,
    *,
    out_dir: Path | str | None = None,
    zip_output: bool = True,
    zip_path: Path | str | None = None,
) -> BatchReviewPackResult:
    proof_path = Path(proof_report_path)
    proof_report = json.loads(proof_path.read_text())
    batch_root_value = str(proof_report.get("batch_root") or "").strip()
    if not batch_root_value:
        raise ValueError(f"proof report does not name a batch root: {proof_path}")
    batch_root = Path(batch_root_value)
    target_dir = Path(out_dir) if out_dir else proof_path.with_name("pavo-batch-review-pack")
    artifact_dir = target_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    handoff = proof_report.get("operator_handoff") if isinstance(proof_report.get("operator_handoff"), dict) else {}
    review_packet = proof_report.get("review_packet") if isinstance(proof_report.get("review_packet"), dict) else {}
    write_batch_decision_board(proof_path)
    write_batch_review_sprint(proof_path, out_dir=proof_path.parent)
    answer_sheet_result = write_batch_speaker_answer_sheet(proof_path, out_dir=proof_path.parent)
    calibration_result = write_batch_speaker_calibration(proof_path, out_dir=proof_path.parent)
    _write_batch_review_pack_cockpit(
        proof_path,
        proof_report=proof_report,
        handoff=handoff,
        target_dir=target_dir,
        answer_sheet_result=answer_sheet_result,
        calibration_result=calibration_result,
    )
    artifacts_to_copy = _batch_review_pack_artifacts(proof_path, proof_report, handoff, review_packet)
    copied: dict[str, dict[str, Any]] = {}
    missing: list[dict[str, Any]] = []
    for name, source in artifacts_to_copy.items():
        if not source or not source.exists() or not source.is_file():
            missing.append({"name": name, "path": str(source) if source else None})
            continue
        destination = artifact_dir / _review_pack_artifact_filename(name, source)
        shutil.copy2(source, destination)
        copied[name] = {
            "source": _file_fingerprint(source),
            "packed": _file_fingerprint(destination),
            "packed_relative_path": str(destination.relative_to(target_dir)),
        }

    validation = enrich_operator_handoff_with_validation(handoff).get("validation") if handoff else {}
    manifest_path = target_dir / "manifest.json"
    readme_path = target_dir / "README.md"
    zip_target = Path(zip_path) if zip_path else target_dir.with_suffix(".zip")
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "proof_report_path": str(proof_path),
        "batch_root": str(batch_root),
        "out_dir": str(target_dir),
        "raw_audio_copied": False,
        "copied_artifact_count": len(copied),
        "missing_artifact_count": len(missing),
        "artifacts": copied,
        "missing_artifacts": missing,
        "operator_handoff": handoff,
        "validation": validation,
        "zip_path": str(zip_target) if zip_output else None,
        "safety_boundary": "This pack intentionally excludes raw audio, signed URLs, credentials, voiceprints, and identity approvals.",
    }
    manifest["artifact_manifest_sha256"] = _review_pack_artifact_manifest_sha256(copied)
    readme_path.write_text(_render_batch_review_pack_readme(manifest), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    copied["review_pack_readme"] = {
        "source": None,
        "packed": _file_fingerprint(readme_path),
        "packed_relative_path": str(readme_path.relative_to(target_dir)),
    }
    copied["review_pack_manifest"] = {
        "source": None,
        "packed": _file_fingerprint(manifest_path),
        "packed_relative_path": str(manifest_path.relative_to(target_dir)),
    }
    manifest["artifacts"] = copied
    manifest["copied_artifact_count"] = len(copied)
    manifest["artifact_manifest_sha256"] = _review_pack_artifact_manifest_sha256(copied)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if zip_output:
        zip_target.parent.mkdir(parents=True, exist_ok=True)
        if zip_target.exists():
            zip_target.unlink()
        with zipfile.ZipFile(zip_target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(target_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(target_dir.parent))
    else:
        zip_target = None

    return BatchReviewPackResult(
        proof_report_path=proof_path,
        batch_root=batch_root,
        out_dir=target_dir,
        manifest_path=manifest_path,
        readme_path=readme_path,
        zip_path=zip_target,
        copied_artifact_count=len(copied),
        missing_artifact_count=len(missing),
        artifact_manifest_sha256=str(manifest["artifact_manifest_sha256"]),
        raw_audio_copied=False,
        artifacts=copied,
        missing_artifacts=missing,
    )


def _review_pack_artifact_manifest_sha256(copied: dict[str, dict[str, Any]]) -> str:
    entries = {
        name: {
            "path": payload.get("packed_relative_path"),
            "exists": True,
            "bytes": (payload.get("packed") or {}).get("bytes"),
            "sha256": (payload.get("packed") or {}).get("sha256"),
        }
        for name, payload in copied.items()
        if name != "review_pack_manifest"
    }
    return _handoff_artifact_manifest_sha256(entries)


def _write_batch_review_pack_cockpit(
    proof_path: Path,
    *,
    proof_report: dict[str, Any],
    handoff: dict[str, Any],
    target_dir: Path,
    answer_sheet_result: BatchSpeakerAnswerSheetResult,
    calibration_result: dict[str, Any],
) -> Path:
    enriched_handoff = enrich_operator_handoff_with_validation(handoff) if handoff else {}
    validation = enriched_handoff.get("validation") if isinstance(enriched_handoff.get("validation"), dict) else {}
    answer_rows, _fields = _read_tsv(answer_sheet_result.tsv_path)
    first_decision = dict(answer_rows[0]) if answer_rows else None
    pending_decision_count = _optional_int(validation.get("pending_decision_count"))
    if pending_decision_count is None:
        pending_decision_count = len(answer_rows)
    pending_clip_count = _optional_int(validation.get("pending_count"))
    if pending_clip_count is None:
        pending_clip_count = sum(len(str(row.get("clip_paths") or "").split(";")) for row in answer_rows)
    target = proof_path.with_name("pavo-batch-review-cockpit.html")
    checks = [
        _check("machine_ready", bool(proof_report.get("passed")), str(proof_report.get("passed"))),
        _check("speaker_answer_sheet_exists", answer_sheet_result.tsv_path.exists(), str(answer_sheet_result.tsv_path)),
        _check("speaker_calibration_exists", Path(str(calibration_result.get("tsv_path") or "")).exists(), str(calibration_result.get("tsv_path") or "")),
        _check("review_pack_target_named", target_dir.name != "", str(target_dir)),
        _check("human_gate_is_explicit", True, "complete" if proof_report.get("complete") else "pending"),
    ]
    blockers = [f"{check['name']}: {check['detail']}" for check in checks if not check.get("passed")]
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "proof_report_path": str(proof_path),
        "state": "complete" if proof_report.get("complete") else "machine_ready_human_review_pending",
        "passed": not blockers,
        "complete": bool(proof_report.get("complete")),
        "machine_ready": bool(proof_report.get("passed")),
        "human_gate": "complete" if proof_report.get("complete") else "pending",
        "pending_decision_count": pending_decision_count,
        "pending_clip_count": pending_clip_count,
        "estimated_minutes": None,
        "first_decision": first_decision,
        "artifacts": {
            "decision_board": str(proof_path.with_name("pavo-batch-proof.decision-board.html")),
            "review_sprint_markdown": str(proof_path.with_name("pavo-batch-review-sprint.md")),
            "speaker_answer_sheet_markdown": str(answer_sheet_result.markdown_path),
            "speaker_answer_sheet_tsv": str(answer_sheet_result.tsv_path),
            "speaker_calibration_markdown": str(calibration_result.get("markdown_path") or ""),
            "speaker_calibration_tsv": str(calibration_result.get("tsv_path") or ""),
            "review_pack": str(target_dir),
            "review_pack_zip": str(target_dir.with_suffix(".zip")),
        },
        "commands": {
            "review_now": f"pavo batch review-now {shlex.quote(str(proof_path))}",
            "review_cockpit": f"pavo batch review-cockpit {shlex.quote(str(proof_path))}",
            "finalize_board_audit": _batch_finalize_board_audit_command(proof_path, enriched_handoff),
        },
        "checks": checks,
        "blockers": blockers,
        "safety_boundary": "This cockpit proves the operator page is present and wired. It does not approve speaker identity.",
    }
    target.write_text(_render_batch_review_cockpit_html(payload), encoding="utf-8")
    return target


def verify_batch_review_pack(
    proof_report_path: Path | str,
    *,
    pack_dir: Path | str | None = None,
) -> BatchReviewPackVerifyResult:
    proof_path = Path(proof_report_path)
    resolved_pack_dir = Path(pack_dir) if pack_dir else proof_path.with_name("pavo-batch-review-pack")
    manifest_path = resolved_pack_dir / "manifest.json"
    readme_path = resolved_pack_dir / "README.md"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    missing_artifacts = manifest.get("missing_artifacts") if isinstance(manifest.get("missing_artifacts"), list) else []
    readme_text = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    zip_value = manifest.get("zip_path")
    zip_path = Path(str(zip_value)) if zip_value else resolved_pack_dir.with_suffix(".zip")
    checks = [
        _check("pack_dir_exists", resolved_pack_dir.exists() and resolved_pack_dir.is_dir(), str(resolved_pack_dir)),
        _check("manifest_exists", manifest_path.exists() and manifest_path.is_file(), str(manifest_path)),
        _check("readme_exists", readme_path.exists() and readme_path.is_file(), str(readme_path)),
        _check("raw_audio_copied_false", manifest.get("raw_audio_copied") is False, str(manifest.get("raw_audio_copied"))),
        _check("readme_has_finalize_board_audit", "pavo batch finalize-board-audit" in readme_text, "finalize-board-audit"),
        _check("readme_has_readiness", "pavo batch readiness" in readme_text, "readiness"),
        _check("readme_has_review_cockpit", "pavo batch review-cockpit" in readme_text, "review cockpit"),
        _check("readme_has_speaker_calibration", "pavo batch speaker-calibration" in readme_text, "speaker calibration"),
        _check("readme_has_safety_boundary", "excludes raw audio" in readme_text, "raw-audio boundary"),
        _check("has_review_cockpit_html", "review_cockpit_html" in artifacts, "review_cockpit_html"),
        _check("has_speaker_calibration_json", "speaker_calibration_json" in artifacts, "speaker_calibration_json"),
        _check("has_speaker_calibration_markdown", "speaker_calibration_markdown" in artifacts, "speaker_calibration_markdown"),
        _check("has_speaker_calibration_tsv", "speaker_calibration_tsv" in artifacts, "speaker_calibration_tsv"),
        _check("zip_exists", zip_path.exists() and zip_path.is_file(), str(zip_path)),
    ]
    artifact_checks, artifact_manifest_sha256 = _verify_review_pack_artifacts(resolved_pack_dir, artifacts)
    checks.extend(artifact_checks)
    raw_audio_files = _review_pack_raw_audio_files(resolved_pack_dir)
    checks.append(_check("no_raw_audio_files", not raw_audio_files, ", ".join(raw_audio_files) or "none"))
    expected_manifest_sha256 = manifest.get("artifact_manifest_sha256")
    checks.append(
        _check(
            "artifact_manifest_sha256_matches",
            bool(artifact_manifest_sha256 and artifact_manifest_sha256 == expected_manifest_sha256),
            f"{artifact_manifest_sha256}/{expected_manifest_sha256}",
        )
    )
    board_verification: dict[str, Any] | None = None
    sprint_verification: dict[str, Any] | None = None
    try:
        board = verify_batch_decision_board(proof_path)
        board_verification = board.as_report()
        checks.append(_check("decision_board_verifies", board.passed, str(board.decision_board_path)))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        board_verification = {"passed": False, "error": str(exc)}
        checks.append(_check("decision_board_verifies", False, str(exc)))
    try:
        sprint = verify_batch_review_sprint(proof_path)
        sprint_verification = sprint.as_report()
        checks.append(_check("review_sprint_verifies", sprint.passed, str(sprint.markdown_path)))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sprint_verification = {"passed": False, "error": str(exc)}
        checks.append(_check("review_sprint_verifies", False, str(exc)))
    blockers = [f"{check['name']}: {check['detail']}" for check in checks if not check.get("passed")]
    return BatchReviewPackVerifyResult(
        proof_report_path=proof_path,
        pack_dir=resolved_pack_dir,
        manifest_path=manifest_path,
        readme_path=readme_path,
        zip_path=zip_path,
        passed=not blockers,
        artifact_count=len(artifacts),
        missing_artifact_count=len(missing_artifacts),
        checks=checks,
        blockers=blockers,
        artifact_manifest_sha256=artifact_manifest_sha256,
        board_verification=board_verification,
        sprint_verification=sprint_verification,
    )


def _verify_review_pack_artifacts(
    pack_dir: Path, artifacts: dict[str, Any]
) -> tuple[list[dict[str, Any]], str | None]:
    checks: list[dict[str, Any]] = []
    manifest_entries: dict[str, dict[str, Any]] = {}
    if not artifacts:
        return [_check("artifacts_present", False, "no artifacts in manifest")], None
    checks.append(_check("artifacts_present", True, f"{len(artifacts)} artifacts"))
    for name, payload in sorted(artifacts.items()):
        packed = payload.get("packed") if isinstance(payload, dict) else {}
        relative = str(payload.get("packed_relative_path") or "") if isinstance(payload, dict) else ""
        path = pack_dir / relative if relative else None
        exists = bool(path and path.exists() and path.is_file())
        checks.append(_check(f"artifact_exists:{name}", exists, str(path) if path else "missing path"))
        if not exists or path is None:
            continue
        fingerprint = _file_fingerprint(path)
        if name == "review_pack_manifest":
            continue
        sha_matches = fingerprint.get("sha256") == packed.get("sha256")
        bytes_matches = fingerprint.get("bytes") == packed.get("bytes")
        checks.append(_check(f"artifact_sha256_matches:{name}", sha_matches, str(path)))
        checks.append(_check(f"artifact_bytes_match:{name}", bytes_matches, str(path)))
        manifest_entries[name] = {
            "path": relative,
            "exists": True,
            "bytes": fingerprint.get("bytes"),
            "sha256": fingerprint.get("sha256"),
        }
    return checks, _handoff_artifact_manifest_sha256(manifest_entries)


def _review_pack_raw_audio_files(pack_dir: Path) -> list[str]:
    raw_audio_suffixes = {".aac", ".aif", ".aiff", ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".wma"}
    if not pack_dir.exists():
        return []
    return [
        str(path.relative_to(pack_dir))
        for path in sorted(pack_dir.rglob("*"))
        if path.is_file() and path.suffix.lower() in raw_audio_suffixes
    ]


def summarize_batch_readiness(
    proof_report_path: Path | str,
    *,
    pack_dir: Path | str | None = None,
) -> BatchReadinessResult:
    proof_path = Path(proof_report_path)
    proof_report = json.loads(proof_path.read_text())
    handoff = enrich_operator_handoff_with_validation(load_operator_handoff(proof_path))
    board_report: dict[str, Any] | None = None
    pack_report: dict[str, Any] | None = None
    blockers: list[str] = []
    machine_ready = bool(proof_report.get("passed"))
    complete = bool(proof_report.get("complete"))
    if not machine_ready:
        blockers.append("batch proof has not passed")
    try:
        board = verify_batch_decision_board(proof_path)
        board_report = board.as_report()
        if not board.passed:
            blockers.extend(f"decision board: {blocker}" for blocker in board.blockers)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        board_report = {"passed": False, "error": str(exc)}
        blockers.append(f"decision board: {exc}")
    try:
        review_pack = verify_batch_review_pack(proof_path, pack_dir=pack_dir)
        pack_report = review_pack.as_report()
        if not review_pack.passed:
            blockers.extend(f"review pack: {blocker}" for blocker in review_pack.blockers)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        pack_report = {"passed": False, "error": str(exc)}
        blockers.append(f"review pack: {exc}")
    validation = handoff.get("validation") if isinstance(handoff.get("validation"), dict) else {}
    validation_status = validation.get("status")
    validation_ready = bool(validation.get("status") == "ready_to_finish" and validation.get("decision_ready"))
    pending_decision_count = _optional_int(validation.get("pending_decision_count"))
    pending_row_count = _optional_int(validation.get("pending_count"))
    review_sprint = _batch_sprint_with_decision_groups(_batch_review_sprint_from_validation(validation), handoff)
    review_completion = _decision_slate_review_completion(str(handoff.get("proof_decision_slate_tsv") or ""))
    board_ready = bool(board_report and board_report.get("passed"))
    review_pack_ready = bool(pack_report and pack_report.get("passed"))
    if complete:
        state = "complete"
        next_action = "no action required; strict proof is complete"
    elif machine_ready and board_ready and review_pack_ready and validation_ready:
        state = "ready_to_finalize"
        next_action = str(handoff.get("finish_command") or "run finish command, then strict proof")
    elif machine_ready and board_ready and review_pack_ready:
        state = "machine_ready_human_review_pending"
        next_action = str(
            validation.get("next_action")
            or "open the decision board, review pending speaker decisions, download audit JSON, then run finalize-board-audit"
        )
    else:
        state = "needs_machine_repair"
        next_action = "repair blockers, regenerate proof, board, and review pack, then rerun readiness"
    return BatchReadinessResult(
        proof_report_path=proof_path,
        state=state,
        passed=bool(complete),
        complete=complete,
        machine_ready=machine_ready,
        board_ready=board_ready,
        review_pack_ready=review_pack_ready,
        validation_status=str(validation_status) if validation_status is not None else None,
        validation_ready=validation_ready,
        pending_decision_count=pending_decision_count,
        pending_row_count=pending_row_count,
        review_sprint=review_sprint,
        review_completion=review_completion,
        next_action=next_action,
        blockers=list(dict.fromkeys(blockers)),
        proof=proof_report,
        handoff=handoff,
        board=board_report,
        review_pack=pack_report,
    )


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _batch_review_sprint_from_validation(validation: dict[str, Any]) -> dict[str, Any]:
    questions = validation.get("pending_review_questions")
    if not isinstance(questions, list):
        questions = []
    items = [_batch_review_sprint_item(item, index) for index, item in enumerate(questions, start=1) if isinstance(item, dict)]
    total_clips = sum(int(item.get("clip_count") or 0) for item in items)
    estimated_seconds = sum(int(item.get("estimated_seconds") or 0) for item in items)
    return {
        "pending_decision_count": len(items),
        "pending_clip_count": total_clips,
        "estimated_seconds": estimated_seconds,
        "estimated_minutes": round(estimated_seconds / 60, 1) if estimated_seconds else 0,
        "focus_order": items,
        "priority_queue": _batch_review_priority_queue(items),
        "review_rule": "Listen to every supporting clip before approving or rejecting a speaker identity decision.",
    }


def _batch_review_sprint_item(item: dict[str, Any], index: int) -> dict[str, Any]:
    clip_count = _optional_int(item.get("clip_count")) or len(item.get("clip_paths") or [])
    tier = str(item.get("priority_tier") or "standard")
    estimated_seconds = max(1, clip_count) * 45 + 20
    clip_paths = [str(value) for value in item.get("clip_paths") or []]
    transcript_samples = [
        {
            "row_index": sample.get("row_index"),
            "excerpt": sample.get("excerpt"),
        }
        for sample in item.get("transcript_samples") or []
        if isinstance(sample, dict)
    ]
    return {
        "order": index,
        "decision_group": item.get("decision_group"),
        "cluster_id": item.get("cluster_id"),
        "speaker": item.get("speaker"),
        "question": item.get("question"),
        "priority_tier": tier,
        "priority_score": item.get("priority_score"),
        "acoustic_verdict": item.get("acoustic_verdict"),
        "clip_count": clip_count,
        "clip_paths": clip_paths,
        "transcript_samples": transcript_samples,
        "estimated_seconds": estimated_seconds,
        "estimated_minutes": round(estimated_seconds / 60, 1),
        "why_first": _batch_review_sprint_reason(item),
        "decision_shape": _batch_speaker_decision_shape(item),
        "decision_risk": _batch_speaker_decision_risk(item, clip_count=clip_count),
        "suggested_review_action": _batch_speaker_suggested_review_action(item, clip_count=clip_count),
        "evidence_hints": _batch_speaker_evidence_hints(item, clip_count=clip_count),
    }


def _batch_review_sprint_reason(item: dict[str, Any]) -> str:
    tier = str(item.get("priority_tier") or "").replace("_", " ")
    acoustic = str(item.get("acoustic_verdict") or "").replace("_", " ")
    score = str(item.get("priority_score") or "").strip()
    parts = []
    if tier:
        parts.append(tier)
    if acoustic:
        parts.append(acoustic)
    if score:
        parts.append(f"score {score}")
    return "; ".join(parts) or "pending speaker decision"


def _batch_speaker_decision_shape(item: dict[str, Any]) -> str:
    question = str(item.get("question") or "").lower()
    if " or " in question:
        return "choose_between_named_speakers"
    if "what speaker identity" in question:
        return "open_identity_choice"
    if "can cluster" in question and "confirmed" in question:
        return "confirm_or_reject_proposed_identity"
    return "speaker_identity_review"


def _batch_speaker_decision_risk(item: dict[str, Any], *, clip_count: int) -> str:
    tier = str(item.get("priority_tier") or "").lower()
    acoustic = str(item.get("acoustic_verdict") or "").lower()
    shape = _batch_speaker_decision_shape(item)
    if "urgent" in tier or "drift" in acoustic or shape in {"choose_between_named_speakers", "open_identity_choice"}:
        return "high"
    if "careful" in tier or "mixed" in acoustic or clip_count > 1:
        return "medium"
    return "low"


def _batch_speaker_suggested_review_action(item: dict[str, Any], *, clip_count: int) -> str:
    risk = _batch_speaker_decision_risk(item, clip_count=clip_count)
    shape = _batch_speaker_decision_shape(item)
    if shape == "choose_between_named_speakers":
        return "A/B listen: compare every clip against each named candidate before deciding."
    if shape == "open_identity_choice":
        return "Identity search: do not anchor on the proposed label; decide the safest speaker constraint."
    if risk == "high":
        return "Slow listen: play all clips, look for channel drift, overlap, and context contradictions."
    if risk == "medium":
        return "Confirm all clips: approve only if every clip supports the same speaker."
    return "Quick confirm: still listen to every clip, but this is not currently a high-risk decision."


def _batch_speaker_evidence_hints(item: dict[str, Any], *, clip_count: int) -> list[str]:
    hints: list[str] = []
    shape = _batch_speaker_decision_shape(item)
    acoustic = str(item.get("acoustic_verdict") or "").replace("_", " ").lower()
    tier = str(item.get("priority_tier") or "").replace("_", " ").lower()
    score = str(item.get("priority_score") or "").strip()
    if shape == "choose_between_named_speakers":
        hints.append("The question names competing speakers, so this is not a simple confirmation.")
    elif shape == "open_identity_choice":
        hints.append("The question is open-ended; treat the proposed speaker as a hypothesis, not the answer.")
    elif shape == "confirm_or_reject_proposed_identity":
        hints.append("This is a confirmation question; try to disprove the proposed speaker with each clip.")
    if "drift" in acoustic:
        hints.append("Acoustic drift was detected; compare voice shape and recording channel across clips.")
    elif "mixed" in acoustic:
        hints.append("Mixed acoustic shape was detected; require the clips to agree before approving.")
    if "urgent" in tier:
        hints.append("The priority tier is urgent; resolve this before lower-impact speaker questions.")
    elif "careful" in tier:
        hints.append("The priority tier calls for careful listening, not bulk approval.")
    if clip_count > 1:
        hints.append(f"There are {clip_count} supporting clips; approval requires every clip to match.")
    if score:
        hints.append(f"Priority score `{score}` explains the current focus ordering.")
    return list(dict.fromkeys(hints))


def _batch_review_priority_queue(items: list[dict[str, Any]]) -> dict[str, Any]:
    risk_rank = {"high": 0, "medium": 1, "low": 2}
    ordered = sorted(
        items,
        key=lambda item: (
            risk_rank.get(str(item.get("decision_risk") or "low"), 3),
            -_optional_float(item.get("priority_score"), default=0.0),
            int(item.get("order") or 0),
        ),
    )
    queue_items = [
        {
            "queue_order": index,
            "original_order": item.get("order"),
            "decision_group": item.get("decision_group"),
            "cluster_id": item.get("cluster_id"),
            "speaker": item.get("speaker"),
            "decision_risk": item.get("decision_risk"),
            "decision_shape": item.get("decision_shape"),
            "priority_score": item.get("priority_score"),
            "clip_count": item.get("clip_count"),
            "question": item.get("question"),
            "suggested_review_action": item.get("suggested_review_action"),
            "why_queued": _batch_review_priority_reason(item),
        }
        for index, item in enumerate(ordered, start=1)
    ]
    counts = {
        "high": sum(1 for item in queue_items if item.get("decision_risk") == "high"),
        "medium": sum(1 for item in queue_items if item.get("decision_risk") == "medium"),
        "low": sum(1 for item in queue_items if item.get("decision_risk") == "low"),
    }
    return {
        "strategy": "risk_then_priority_score",
        "rationale": "Review high-risk speaker decisions first, then medium/low risk by descending priority score.",
        "risk_counts": counts,
        "items": queue_items,
    }


def _batch_review_priority_reason(item: dict[str, Any]) -> str:
    risk = str(item.get("decision_risk") or "low")
    shape = str(item.get("decision_shape") or "speaker_identity_review").replace("_", " ")
    score = str(item.get("priority_score") or "").strip()
    score_text = f"; score {score}" if score else ""
    return f"{risk} risk; {shape}{score_text}"


def _optional_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def write_batch_review_sprint(
    proof_report_path: Path | str,
    *,
    out_dir: Path | str | None = None,
) -> BatchReviewSprintResult:
    proof_path = Path(proof_report_path)
    proof_report = json.loads(proof_path.read_text())
    handoff = enrich_operator_handoff_with_validation(load_operator_handoff(proof_path))
    validation = handoff.get("validation") if isinstance(handoff.get("validation"), dict) else {}
    sprint = _batch_sprint_with_decision_groups(_batch_review_sprint_from_validation(validation), handoff)
    target_dir = Path(out_dir) if out_dir else proof_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "pavo-batch-review-sprint.json"
    markdown_path = target_dir / "pavo-batch-review-sprint.md"
    payload = _batch_review_sprint_payload(proof_path, proof_report, handoff, validation, sprint)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_batch_review_sprint_markdown(payload), encoding="utf-8")
    return BatchReviewSprintResult(
        proof_report_path=proof_path,
        out_dir=target_dir,
        json_path=json_path,
        markdown_path=markdown_path,
        state=str(payload.get("state") or ""),
        complete=bool(payload.get("complete")),
        pending_decision_count=int(sprint.get("pending_decision_count") or 0),
        pending_clip_count=int(sprint.get("pending_clip_count") or 0),
        estimated_minutes=float(sprint.get("estimated_minutes") or 0),
        payload=payload,
    )


def verify_batch_review_sprint(
    proof_report_path: Path | str,
    *,
    json_path: Path | str | None = None,
    markdown_path: Path | str | None = None,
) -> BatchReviewSprintVerifyResult:
    proof_path = Path(proof_report_path)
    resolved_json = Path(json_path) if json_path else proof_path.with_name("pavo-batch-review-sprint.json")
    resolved_markdown = Path(markdown_path) if markdown_path else proof_path.with_name("pavo-batch-review-sprint.md")
    payload = json.loads(resolved_json.read_text()) if resolved_json.exists() else {}
    markdown = resolved_markdown.read_text(encoding="utf-8") if resolved_markdown.exists() else ""
    sprint = payload.get("review_sprint") if isinstance(payload.get("review_sprint"), dict) else {}
    focus_order = sprint.get("focus_order") if isinstance(sprint.get("focus_order"), list) else []
    priority_queue = sprint.get("priority_queue") if isinstance(sprint.get("priority_queue"), dict) else {}
    priority_items = priority_queue.get("items") if isinstance(priority_queue.get("items"), list) else []
    pending_decision_count = _optional_int(sprint.get("pending_decision_count")) or 0
    pending_clip_count = _optional_int(sprint.get("pending_clip_count")) or 0
    clip_paths = [
        str(path)
        for item in focus_order
        if isinstance(item, dict)
        for path in item.get("clip_paths") or []
    ]
    transcript_count = sum(
        len(item.get("transcript_samples") or [])
        for item in focus_order
        if isinstance(item, dict)
    )
    checks = [
        _check("review_sprint_json_exists", resolved_json.exists() and resolved_json.is_file(), str(resolved_json)),
        _check("review_sprint_markdown_exists", resolved_markdown.exists() and resolved_markdown.is_file(), str(resolved_markdown)),
        _check("proof_report_matches", str(payload.get("proof_report_path") or "") == str(proof_path), str(payload.get("proof_report_path"))),
        _check("has_focus_order", bool(focus_order) or pending_decision_count == 0, f"{len(focus_order)} focus item(s)"),
        _check("pending_decision_count_matches_focus", pending_decision_count == len(focus_order), f"{pending_decision_count}/{len(focus_order)}"),
        _check(
            "has_priority_queue",
            pending_decision_count == 0
            or (
                priority_queue.get("strategy") == "risk_then_priority_score"
                and len(priority_items) == pending_decision_count
                and "Priority Queue" in markdown
                and "risk then priority score" in markdown
            ),
            f"{len(priority_items)}/{pending_decision_count}",
        ),
        _check("pending_clip_count_matches_paths", pending_clip_count == len(clip_paths), f"{pending_clip_count}/{len(clip_paths)}"),
        _check("has_transcript_samples", transcript_count >= pending_decision_count or pending_decision_count == 0, f"{transcript_count}/{pending_decision_count}"),
        _check(
            "has_evidence_hints",
            pending_decision_count == 0
            or (
                all(item.get("evidence_hints") for item in focus_order if isinstance(item, dict))
                and "Evidence hints" in markdown
                and "Suggested action" in markdown
            ),
            "speaker decision evidence hints",
        ),
        _check("markdown_has_listen_checklist", pending_decision_count == 0 or "Listen checklist" in markdown, "Listen checklist"),
        _check("markdown_has_clip_checkboxes", "- [ ] Clip 1:" in markdown or pending_clip_count == 0, "clip checkboxes"),
        _check(
            "markdown_has_decision_checkboxes",
            pending_decision_count == 0 or ("- [ ] Approved" in markdown and "- [ ] Rejected" in markdown),
            "decision checkboxes",
        ),
        _check(
            "markdown_has_decision_rubric",
            pending_decision_count == 0 or all(rule in markdown for rule in BATCH_SPEAKER_DECISION_RUBRIC),
            "approve/reject/pending rubric",
        ),
        _check("markdown_has_finalize_command", "pavo batch finalize-board-audit" in markdown, "finalize command"),
        _check("has_safety_boundary", "human owns the final identity decision" in str(payload.get("safety_boundary") or ""), "identity boundary"),
    ]
    for clip_path in clip_paths:
        checks.append(_check(f"clip_exists:{Path(clip_path).name}", Path(clip_path).exists(), clip_path))
    blockers = [f"{check['name']}: {check['detail']}" for check in checks if not check.get("passed")]
    return BatchReviewSprintVerifyResult(
        proof_report_path=proof_path,
        json_path=resolved_json,
        markdown_path=resolved_markdown,
        passed=not blockers,
        pending_decision_count=pending_decision_count,
        pending_clip_count=pending_clip_count,
        checks=checks,
        blockers=blockers,
    )


def write_batch_speaker_answer_sheet(
    proof_report_path: Path | str,
    *,
    out_dir: Path | str | None = None,
) -> BatchSpeakerAnswerSheetResult:
    proof_path = Path(proof_report_path)
    proof_report = json.loads(proof_path.read_text())
    handoff = enrich_operator_handoff_with_validation(load_operator_handoff(proof_path))
    validation = handoff.get("validation") if isinstance(handoff.get("validation"), dict) else {}
    sprint = _batch_sprint_with_decision_groups(_batch_review_sprint_from_validation(validation), handoff)
    target_dir = Path(out_dir) if out_dir else proof_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = target_dir / "pavo-batch-speaker-answer-sheet.md"
    tsv_path = target_dir / "pavo-batch-speaker-answer-sheet.tsv"
    payload = _batch_speaker_answer_sheet_payload(proof_path, proof_report, handoff, validation, sprint)
    markdown_path.write_text(_render_batch_speaker_answer_sheet_markdown(payload), encoding="utf-8")
    _write_batch_speaker_answer_sheet_tsv(tsv_path, payload)
    return BatchSpeakerAnswerSheetResult(
        proof_report_path=proof_path,
        out_dir=target_dir,
        markdown_path=markdown_path,
        tsv_path=tsv_path,
        pending_decision_count=int(sprint.get("pending_decision_count") or 0),
        pending_clip_count=int(sprint.get("pending_clip_count") or 0),
        estimated_minutes=float(sprint.get("estimated_minutes") or 0),
        payload=payload,
    )


def verify_batch_speaker_answer_sheet(
    proof_report_path: Path | str,
    *,
    markdown_path: Path | str | None = None,
    tsv_path: Path | str | None = None,
) -> BatchSpeakerAnswerSheetVerifyResult:
    proof_path = Path(proof_report_path)
    resolved_markdown = Path(markdown_path) if markdown_path else proof_path.with_name("pavo-batch-speaker-answer-sheet.md")
    resolved_tsv = Path(tsv_path) if tsv_path else proof_path.with_name("pavo-batch-speaker-answer-sheet.tsv")
    markdown = resolved_markdown.read_text(encoding="utf-8") if resolved_markdown.exists() else ""
    rows: list[dict[str, str]] = []
    fieldnames: list[str] = []
    if resolved_tsv.exists():
        rows, fieldnames = _read_tsv(resolved_tsv)
    handoff = enrich_operator_handoff_with_validation(load_operator_handoff(proof_path))
    validation = handoff.get("validation") if isinstance(handoff.get("validation"), dict) else {}
    sprint = _batch_review_sprint_from_validation(validation)
    pending_decision_count = int(sprint.get("pending_decision_count") or 0)
    pending_clip_count = int(sprint.get("pending_clip_count") or 0)
    required_fields = {
        "queue_order",
        "decision_group",
        "cluster_id",
        "speaker",
        "decision_risk",
        "decision_shape",
        "question",
        "suggested_review_action",
        "clip_count",
        "decision",
        "review_reason",
        "notes",
    }
    checks = [
        _check("answer_sheet_markdown_exists", resolved_markdown.exists() and resolved_markdown.is_file(), str(resolved_markdown)),
        _check("answer_sheet_tsv_exists", resolved_tsv.exists() and resolved_tsv.is_file(), str(resolved_tsv)),
        _check("tsv_has_required_fields", required_fields.issubset(set(fieldnames)), ",".join(fieldnames)),
        _check("pending_decision_count_matches_rows", pending_decision_count == len(rows), f"{pending_decision_count}/{len(rows)}"),
        _check("markdown_has_answer_sheet_title", "Pavo Speaker Answer Sheet" in markdown, "title"),
        _check("markdown_has_priority_order", "Priority Listen Order" in markdown, "priority listen order"),
        _check("markdown_has_fill_rules", "Allowed decision values" in markdown and "Allowed review reasons" in markdown, "fill rules"),
        _check("markdown_has_finish_command", "pavo batch finalize-board-audit" in markdown, "finalize command"),
        _check("markdown_has_safety_boundary", "human owns the final identity decision" in markdown, "identity boundary"),
    ]
    for row in rows:
        clip_count = _optional_int(row.get("clip_count")) or 0
        checks.append(
            _check(
                f"row_has_review_context:{row.get('decision_group')}",
                bool(
                    row.get("decision_group")
                    and row.get("decision_risk")
                    and row.get("decision_shape")
                    and row.get("suggested_review_action")
                ),
                str(row.get("decision_group") or ""),
            )
        )
        checks.append(
            _check(
                f"row_clip_count_present:{row.get('decision_group')}",
                clip_count > 0 or pending_clip_count == 0,
                str(row.get("clip_count") or ""),
            )
        )
    blockers = [f"{check['name']}: {check['detail']}" for check in checks if not check.get("passed")]
    return BatchSpeakerAnswerSheetVerifyResult(
        proof_report_path=proof_path,
        markdown_path=resolved_markdown,
        tsv_path=resolved_tsv,
        passed=not blockers,
        pending_decision_count=pending_decision_count,
        pending_clip_count=pending_clip_count,
        checks=checks,
        blockers=blockers,
    )


def write_batch_review_rehearsal(
    proof_report_path: Path | str,
    *,
    out_dir: Path | str | None = None,
    pack_dir: Path | str | None = None,
) -> BatchReviewRehearsalResult:
    proof_path = Path(proof_report_path)
    target_dir = Path(out_dir) if out_dir else proof_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    board_result = write_batch_decision_board(proof_path)
    sprint_result = write_batch_review_sprint(proof_path)
    answer_result = write_batch_speaker_answer_sheet(proof_path)
    calibration_result = write_batch_speaker_calibration(proof_path)
    pack_result = write_batch_review_pack(proof_path, out_dir=pack_dir)

    board_verification = verify_batch_decision_board(proof_path)
    sprint_verification = verify_batch_review_sprint(proof_path)
    answer_verification = verify_batch_speaker_answer_sheet(proof_path)
    pack_verification = verify_batch_review_pack(proof_path, pack_dir=pack_dir)
    readiness = summarize_batch_readiness(proof_path, pack_dir=pack_dir)

    answer_rows, _fields = _read_tsv(answer_result.tsv_path)
    first_decision = dict(answer_rows[0]) if answer_rows else None
    expected_pending = readiness.pending_decision_count or 0
    expected_clips = int(readiness.review_sprint.get("pending_clip_count") or 0)
    checks = [
        _check("machine_ready", readiness.machine_ready, readiness.state),
        _check("board_verified", board_verification.passed, str(board_verification.decision_board_path)),
        _check("review_sprint_verified", sprint_verification.passed, str(sprint_verification.markdown_path)),
        _check("answer_sheet_verified", answer_verification.passed, str(answer_verification.markdown_path)),
        _check("review_pack_verified", pack_verification.passed, str(pack_verification.pack_dir)),
        _check("pending_decision_count_consistent", expected_pending == len(answer_rows), f"{expected_pending}/{len(answer_rows)}"),
        _check("pending_clip_count_consistent", expected_clips == answer_verification.pending_clip_count, f"{expected_clips}/{answer_verification.pending_clip_count}"),
        _check("first_decision_has_group", bool(first_decision and first_decision.get("decision_group")), str(first_decision or {})),
        _check("first_decision_has_clip_paths", bool(first_decision and first_decision.get("clip_paths")), str(first_decision or {})),
        _check("human_gate_is_explicit", readiness.state in {"machine_ready_human_review_pending", "ready_to_finalize", "complete"}, readiness.state),
    ]
    blockers = [f"{check['name']}: {check['detail']}" for check in checks if not check.get("passed")]
    blockers.extend(f"decision board: {blocker}" for blocker in board_verification.blockers)
    blockers.extend(f"review sprint: {blocker}" for blocker in sprint_verification.blockers)
    blockers.extend(f"answer sheet: {blocker}" for blocker in answer_verification.blockers)
    blockers.extend(f"review pack: {blocker}" for blocker in pack_verification.blockers)
    blockers.extend(f"readiness: {blocker}" for blocker in readiness.blockers)
    blockers = list(dict.fromkeys(blockers))
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "proof_report_path": str(proof_path),
        "state": readiness.state,
        "passed": not blockers,
        "complete": readiness.complete,
        "machine_ready": readiness.machine_ready,
        "human_gate": "complete" if readiness.complete else "pending",
        "pending_decision_count": expected_pending,
        "pending_clip_count": expected_clips,
        "estimated_minutes": float(readiness.review_sprint.get("estimated_minutes") or 0),
        "first_decision": first_decision,
        "artifacts": {
            "decision_board": str(board_result.out_path),
            "review_sprint_markdown": str(sprint_result.markdown_path),
            "speaker_answer_sheet_markdown": str(answer_result.markdown_path),
            "speaker_answer_sheet_tsv": str(answer_result.tsv_path),
            "speaker_calibration_markdown": str(calibration_result["markdown_path"]),
            "speaker_calibration_tsv": str(calibration_result["tsv_path"]),
            "review_pack": str(pack_result.out_dir),
            "review_pack_zip": str(pack_result.zip_path) if pack_result.zip_path else None,
        },
        "commands": {
            "review_now": f"pavo batch review-now {shlex.quote(str(proof_path))}",
            "verify_rehearsal": f"pavo batch verify-review-rehearsal {shlex.quote(str(proof_path))}",
            "finalize_board_audit": _batch_finalize_board_audit_command(proof_path, readiness.handoff),
        },
        "checks": checks,
        "blockers": blockers,
        "board_verification": board_verification.as_report(),
        "review_sprint_verification": sprint_verification.as_report(),
        "speaker_answer_sheet_verification": answer_verification.as_report(),
        "review_pack_verification": pack_verification.as_report(),
        "readiness": readiness.as_report(),
        "safety_boundary": "This rehearsal proves the review path is ready. It does not approve speaker identity or remove the human listening gate.",
    }
    json_path = target_dir / "pavo-batch-review-rehearsal.json"
    markdown_path = target_dir / "pavo-batch-review-rehearsal.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_batch_review_rehearsal_markdown(payload), encoding="utf-8")
    return BatchReviewRehearsalResult(
        proof_report_path=proof_path,
        out_dir=target_dir,
        json_path=json_path,
        markdown_path=markdown_path,
        passed=not blockers,
        state=readiness.state,
        pending_decision_count=expected_pending,
        pending_clip_count=expected_clips,
        estimated_minutes=float(readiness.review_sprint.get("estimated_minutes") or 0),
        first_decision=first_decision,
        checks=checks,
        blockers=blockers,
        payload=payload,
    )


def _batch_finalize_board_audit_command(proof_path: Path, handoff: dict[str, Any]) -> str:
    board_audit_json = proof_path.with_name("pavo-batch-proof.decision-board.audit.json")
    reviewed_decision_slate = proof_path.with_name("pavo-batch-proof.decision-slate.reviewed.tsv")
    review_slate = handoff.get("proof_review_slate_tsv") or str(proof_path.with_name("pavo-batch-proof.review-slate.tsv"))
    return " ".join(
        [
            "pavo",
            "batch",
            "finalize-board-audit",
            shlex.quote(str(proof_path)),
            shlex.quote(str(board_audit_json)),
            "--out",
            shlex.quote(str(review_slate)),
            "--decision-slate-out",
            shlex.quote(str(reviewed_decision_slate)),
        ]
    )


def verify_batch_review_rehearsal(
    proof_report_path: Path | str,
    *,
    json_path: Path | str | None = None,
    markdown_path: Path | str | None = None,
) -> BatchReviewRehearsalResult:
    proof_path = Path(proof_report_path)
    resolved_json = Path(json_path) if json_path else proof_path.with_name("pavo-batch-review-rehearsal.json")
    resolved_markdown = Path(markdown_path) if markdown_path else proof_path.with_name("pavo-batch-review-rehearsal.md")
    payload = json.loads(resolved_json.read_text()) if resolved_json.exists() else {}
    markdown = resolved_markdown.read_text(encoding="utf-8") if resolved_markdown.exists() else ""
    first_decision = payload.get("first_decision") if isinstance(payload.get("first_decision"), dict) else None
    checks = [
        _check("review_rehearsal_json_exists", resolved_json.exists() and resolved_json.is_file(), str(resolved_json)),
        _check("review_rehearsal_markdown_exists", resolved_markdown.exists() and resolved_markdown.is_file(), str(resolved_markdown)),
        _check("proof_report_matches", str(payload.get("proof_report_path") or "") == str(proof_path), str(payload.get("proof_report_path") or "")),
        _check("payload_passed", bool(payload.get("passed")), str(payload.get("state") or "")),
        _check("has_first_decision", bool(first_decision and first_decision.get("decision_group") and first_decision.get("clip_paths")), str(first_decision or {})),
        _check(
            "has_speaker_calibration_artifact",
            bool((payload.get("artifacts") or {}).get("speaker_calibration_tsv")),
            str((payload.get("artifacts") or {}).get("speaker_calibration_tsv") or ""),
        ),
        _check("markdown_has_rehearsal_title", "Pavo Batch Review Rehearsal" in markdown, "title"),
        _check("markdown_has_first_decision", "First Decision" in markdown and "decision group" in markdown.lower(), "first decision"),
        _check("markdown_has_finalize_command", "pavo batch finalize-board-audit" in markdown, "finalize command"),
        _check("markdown_has_safety_boundary", "does not approve speaker identity" in markdown, "safety boundary"),
    ]
    blockers = [f"{check['name']}: {check['detail']}" for check in checks if not check.get("passed")]
    blockers.extend(str(blocker) for blocker in payload.get("blockers") or [])
    blockers = list(dict.fromkeys(blockers))
    return BatchReviewRehearsalResult(
        proof_report_path=proof_path,
        out_dir=resolved_json.parent,
        json_path=resolved_json,
        markdown_path=resolved_markdown,
        passed=not blockers,
        state=str(payload.get("state") or "unknown"),
        pending_decision_count=int(payload.get("pending_decision_count") or 0),
        pending_clip_count=int(payload.get("pending_clip_count") or 0),
        estimated_minutes=float(payload.get("estimated_minutes") or 0),
        first_decision=first_decision,
        checks=checks,
        blockers=blockers,
        payload=payload,
    )


def _render_batch_review_rehearsal_markdown(payload: dict[str, Any]) -> str:
    first = payload.get("first_decision") if isinstance(payload.get("first_decision"), dict) else {}
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    commands = payload.get("commands") if isinstance(payload.get("commands"), dict) else {}
    lines = [
        "# Pavo Batch Review Rehearsal",
        "",
        f"- State: `{payload.get('state')}`",
        f"- Passed: `{str(bool(payload.get('passed'))).lower()}`",
        f"- Human gate: `{payload.get('human_gate')}`",
        f"- Pending decisions: `{payload.get('pending_decision_count')}`",
        f"- Pending clips: `{payload.get('pending_clip_count')}`",
        f"- Estimated review time: `{payload.get('estimated_minutes')}` minutes",
        "",
        "## First Decision",
        "",
        f"- Decision group: `{first.get('decision_group')}`",
        f"- Cluster: `{first.get('cluster_id')}`",
        f"- Proposed speaker: `{first.get('speaker')}`",
        f"- Risk: `{first.get('decision_risk')}`",
        f"- Shape: `{first.get('decision_shape')}`",
        f"- Question: {first.get('question')}",
        f"- Suggested action: {first.get('suggested_review_action')}",
        "",
        "## Artifacts",
        "",
    ]
    for name, value in artifacts.items():
        lines.append(f"- `{name}`: `{value}`")
    lines.extend(["", "## Checks", ""])
    for check in payload.get("checks") or []:
        status = "pass" if check.get("passed") else "fail"
        lines.append(f"- `{status}` {check.get('name')}: {check.get('detail')}")
    lines.extend(["", "## Commands", "", "```bash"])
    for command in commands.values():
        lines.append(str(command or ""))
    lines.extend(["```", "", "## Safety Boundary", "", str(payload.get("safety_boundary") or "")])
    return "\n".join(lines).rstrip() + "\n"


def write_batch_review_cockpit(
    proof_report_path: Path | str,
    *,
    out_path: Path | str | None = None,
) -> dict[str, Any]:
    proof_path = Path(proof_report_path)
    rehearsal = write_batch_review_rehearsal(proof_path)
    target = Path(out_path) if out_path else proof_path.with_name("pavo-batch-review-cockpit.html")
    target.write_text(_render_batch_review_cockpit_html(rehearsal.payload), encoding="utf-8")
    return {
        "proof_report_path": str(proof_path),
        "out_path": str(target),
        "passed": rehearsal.passed,
        "state": rehearsal.state,
        "pending_decision_count": rehearsal.pending_decision_count,
        "pending_clip_count": rehearsal.pending_clip_count,
        "first_decision": rehearsal.first_decision,
        "blockers": rehearsal.blockers,
        "safety_boundary": "Review cockpit is an operator surface for human review. It does not approve speaker identity.",
    }


def verify_batch_review_cockpit(
    proof_report_path: Path | str,
    *,
    cockpit_path: Path | str | None = None,
) -> dict[str, Any]:
    proof_path = Path(proof_report_path)
    target = Path(cockpit_path) if cockpit_path else proof_path.with_name("pavo-batch-review-cockpit.html")
    html = target.read_text(encoding="utf-8") if target.exists() else ""
    checks = [
        _check("review_cockpit_exists", target.exists() and target.is_file(), str(target)),
        _check("has_title", "Pavo Review Cockpit" in html, "title"),
        _check("has_readiness", "Machine ready" in html and "Human gate" in html, "readiness cards"),
        _check("has_first_decision", "First decision" in html and "Decision group" in html, "first decision"),
        _check("has_calibration", "Calibration" in html and "speaker-calibration" in html, "calibration"),
        _check("has_finish_command", "finalize-board-audit" in html, "finish command"),
        _check("has_safety_boundary", "does not approve speaker identity" in html, "safety boundary"),
    ]
    blockers = [f"{check['name']}: {check['detail']}" for check in checks if not check.get("passed")]
    return {
        "proof_report_path": str(proof_path),
        "cockpit_path": str(target),
        "passed": not blockers,
        "checks": checks,
        "blockers": blockers,
        "safety_boundary": "Review-cockpit verification proves the operator page is present and wired. It does not approve speaker identity.",
    }


def _render_batch_review_cockpit_html(payload: dict[str, Any]) -> str:
    first = payload.get("first_decision") if isinstance(payload.get("first_decision"), dict) else {}
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    commands = payload.get("commands") if isinstance(payload.get("commands"), dict) else {}
    checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    artifact_cards = "\n".join(
        f'<li><strong>{escape(str(name))}</strong><br><code>{escape(str(value))}</code></li>'
        for name, value in artifacts.items()
    )
    command_cards = "\n".join(f"<pre>{escape(str(command or ''))}</pre>" for command in commands.values())
    check_rows = "\n".join(
        f"<tr><td>{'pass' if check.get('passed') else 'fail'}</td><td>{escape(str(check.get('name') or ''))}</td><td>{escape(str(check.get('detail') or ''))}</td></tr>"
        for check in checks
        if isinstance(check, dict)
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pavo Review Cockpit</title>
  <style>
    body {{ margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f4f7fb; color: #172033; }}
    header {{ padding: 28px 32px; background: #111827; color: #fff; }}
    main {{ padding: 24px 32px; display: grid; gap: 18px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }}
    .card {{ background: #fff; border: 1px solid #d9e1ef; border-radius: 16px; padding: 16px; box-shadow: 0 8px 22px rgba(23,32,51,.06); }}
    .big {{ font-size: 30px; font-weight: 800; }}
    code, pre {{ background: #eef3fb; border-radius: 10px; padding: 8px; white-space: pre-wrap; overflow-wrap: anywhere; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 12px; overflow: hidden; }}
    th, td {{ border-bottom: 1px solid #e5eaf3; padding: 10px; text-align: left; vertical-align: top; }}
    ul {{ padding-left: 20px; }}
  </style>
</head>
<body>
  <header>
    <h1>Pavo Review Cockpit</h1>
    <p>One-page operator surface for the current speaker-review handoff. This page does not approve speaker identity.</p>
  </header>
  <main>
    <section class="grid">
      <div class="card"><div>Machine ready</div><div class="big">{escape(str(bool(payload.get('machine_ready'))).lower())}</div></div>
      <div class="card"><div>Human gate</div><div class="big">{escape(str(payload.get('human_gate') or 'pending'))}</div></div>
      <div class="card"><div>Pending decisions</div><div class="big">{escape(str(payload.get('pending_decision_count') or 0))}</div></div>
      <div class="card"><div>Pending clips</div><div class="big">{escape(str(payload.get('pending_clip_count') or 0))}</div></div>
    </section>
    <section class="card">
      <h2>First decision</h2>
      <p><strong>Decision group:</strong> {escape(str(first.get('decision_group') or ''))}</p>
      <p><strong>Cluster:</strong> {escape(str(first.get('cluster_id') or ''))}</p>
      <p><strong>Risk:</strong> {escape(str(first.get('decision_risk') or ''))}</p>
      <p><strong>Question:</strong> {escape(str(first.get('question') or ''))}</p>
      <p><strong>Suggested action:</strong> {escape(str(first.get('suggested_review_action') or ''))}</p>
    </section>
    <section class="card">
      <h2>Calibration</h2>
      <p>Second-listener calibration is included in this handoff. Run <code>pavo batch speaker-calibration</code> before review if you need to refresh it.</p>
      <p><code>{escape(str(artifacts.get('speaker_calibration_tsv') or ''))}</code></p>
    </section>
    <section class="card">
      <h2>Artifacts</h2>
      <ul>{artifact_cards}</ul>
    </section>
    <section class="card">
      <h2>Finish commands</h2>
      {command_cards}
    </section>
    <section class="card">
      <h2>Checks</h2>
      <table><thead><tr><th>Status</th><th>Check</th><th>Detail</th></tr></thead><tbody>{check_rows}</tbody></table>
    </section>
  </main>
</body>
</html>
"""


def write_batch_speaker_calibration(
    proof_report_path: Path | str,
    *,
    out_dir: Path | str | None = None,
    max_decisions: int = 3,
) -> dict[str, Any]:
    proof_path = Path(proof_report_path)
    target_dir = Path(out_dir) if out_dir else proof_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    answer_sheet = write_batch_speaker_answer_sheet(proof_path, out_dir=proof_path.parent)
    rows, fieldnames = _read_tsv(answer_sheet.tsv_path)
    risk_rank = {"high": 0, "medium": 1, "low": 2}
    ordered = sorted(
        rows,
        key=lambda row: (
            risk_rank.get(str(row.get("decision_risk") or "low"), 3),
            int(row.get("queue_order") or 999999),
            str(row.get("decision_group") or ""),
        ),
    )
    selected = ordered[: max(0, max_decisions)]
    calibration_rows: list[dict[str, str]] = []
    for row in selected:
        item = dict(row)
        item["calibration_reason"] = _speaker_calibration_reason(item)
        item["second_listener_decision"] = ""
        item["second_listener_review_reason"] = ""
        item["second_listener_notes"] = ""
        calibration_rows.append(item)
    calibration_fields = list(fieldnames)
    for field in [
        "calibration_reason",
        "second_listener_decision",
        "second_listener_review_reason",
        "second_listener_notes",
    ]:
        if field not in calibration_fields:
            calibration_fields.append(field)
    json_path = target_dir / "pavo-batch-speaker-calibration.json"
    markdown_path = target_dir / "pavo-batch-speaker-calibration.md"
    tsv_path = target_dir / "pavo-batch-speaker-calibration.tsv"
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "proof_report_path": str(proof_path),
        "answer_sheet_path": str(answer_sheet.tsv_path),
        "strategy": "second_listener_high_risk_then_queue_order",
        "requested_max_decisions": max_decisions,
        "selected_decision_count": len(calibration_rows),
        "source_decision_count": len(rows),
        "selected_decisions": calibration_rows,
        "safety_boundary": "Calibration selects decisions for independent human review. It does not approve speaker identity or create voiceprints.",
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_batch_speaker_calibration_markdown(payload), encoding="utf-8")
    _write_tsv(tsv_path, calibration_rows, calibration_fields)
    return {
        "proof_report_path": str(proof_path),
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "tsv_path": str(tsv_path),
        "selected_decision_count": len(calibration_rows),
        "source_decision_count": len(rows),
        "selected_decisions": calibration_rows,
        "passed": bool(calibration_rows) or not rows,
        "blockers": [] if calibration_rows or not rows else ["no calibration decisions selected"],
        "safety_boundary": payload["safety_boundary"],
    }


def score_batch_speaker_agreement(
    primary_tsv: Path | str,
    secondary_tsv: Path | str,
    *,
    out_path: Path | str | None = None,
) -> dict[str, Any]:
    primary_path = Path(primary_tsv)
    secondary_path = Path(secondary_tsv)
    primary_rows, _primary_fields = _read_tsv(primary_path)
    secondary_rows, _secondary_fields = _read_tsv(secondary_path)
    primary_by_group = {str(row.get("decision_group") or "").strip(): row for row in primary_rows if row.get("decision_group")}
    secondary_by_group = {str(row.get("decision_group") or "").strip(): row for row in secondary_rows if row.get("decision_group")}
    common_groups = sorted(set(primary_by_group) & set(secondary_by_group))
    labels = sorted(VALID_REVIEW_DECISIONS)
    pairs: list[tuple[str, str, str]] = []
    disagreements: list[dict[str, Any]] = []
    for group in common_groups:
        primary_decision = _agreement_decision(primary_by_group[group], preferred="decision")
        secondary_decision = _agreement_decision(secondary_by_group[group], preferred="second_listener_decision")
        pairs.append((group, primary_decision, secondary_decision))
        if primary_decision != secondary_decision:
            disagreements.append(
                {
                    "decision_group": group,
                    "cluster_id": primary_by_group[group].get("cluster_id") or secondary_by_group[group].get("cluster_id"),
                    "primary_decision": primary_decision,
                    "secondary_decision": secondary_decision,
                    "primary_reason": primary_by_group[group].get("review_reason"),
                    "secondary_reason": secondary_by_group[group].get("second_listener_review_reason") or secondary_by_group[group].get("review_reason"),
                }
            )
    total = len(pairs)
    agreed = sum(1 for _group, primary, secondary in pairs if primary == secondary)
    observed = agreed / total if total else 0.0
    primary_counts = {label: sum(1 for _group, primary, _secondary in pairs if primary == label) for label in labels}
    secondary_counts = {label: sum(1 for _group, _primary, secondary in pairs if secondary == label) for label in labels}
    expected = (
        sum((primary_counts[label] / total) * (secondary_counts[label] / total) for label in labels)
        if total
        else 0.0
    )
    if total == 0:
        kappa = None
    elif expected == 1.0:
        kappa = 1.0 if observed == 1.0 else 0.0
    else:
        kappa = (observed - expected) / (1.0 - expected)
    report = {
        "primary_tsv": str(primary_path),
        "secondary_tsv": str(secondary_path),
        "common_decision_count": total,
        "agreed_decision_count": agreed,
        "agreement_rate": round(observed, 4),
        "cohen_kappa": round(kappa, 4) if kappa is not None else None,
        "primary_counts": primary_counts,
        "secondary_counts": secondary_counts,
        "disagreements": disagreements,
        "passed": total > 0 and not disagreements,
        "blockers": [] if total > 0 else ["no common decision_group rows"],
        "safety_boundary": "Agreement scoring measures reviewer consistency. It does not decide which speaker label is true.",
    }
    if out_path:
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report["out_path"] = str(target)
    return report


def _speaker_calibration_reason(row: dict[str, str]) -> str:
    risk = str(row.get("decision_risk") or "unknown")
    shape = str(row.get("decision_shape") or "speaker_identity_review").replace("_", " ")
    score = str(row.get("priority_score") or "").strip()
    score_text = f"; priority score {score}" if score else ""
    return f"{risk} risk; {shape}{score_text}"


def _render_batch_speaker_calibration_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Pavo Speaker Calibration",
        "",
        f"- Strategy: `{payload.get('strategy')}`",
        f"- Selected decisions: `{payload.get('selected_decision_count')}` of `{payload.get('source_decision_count')}`",
        f"- Answer sheet: `{payload.get('answer_sheet_path')}`",
        "",
        "## Second-Listener Queue",
        "",
    ]
    for row in payload.get("selected_decisions") or []:
        lines.extend(
            [
                f"### {row.get('queue_order')}. {row.get('decision_group')} / {row.get('cluster_id')}",
                "",
                f"- Proposed speaker: `{row.get('speaker')}`",
                f"- Risk: `{row.get('decision_risk')}`",
                f"- Question: {row.get('question')}",
                f"- Calibration reason: {row.get('calibration_reason')}",
                f"- Suggested action: {row.get('suggested_review_action')}",
                f"- Clip paths: `{row.get('clip_paths')}`",
                "",
            ]
        )
    if not payload.get("selected_decisions"):
        lines.append("- No calibration decisions selected.")
        lines.append("")
    lines.extend(
        [
            "## How To Score",
            "",
            "Fill `second_listener_decision` and `second_listener_review_reason`, then run:",
            "",
            "```bash",
            "pavo batch score-speaker-agreement primary.tsv secondary.tsv --json",
            "```",
            "",
            "## Safety Boundary",
            "",
            str(payload.get("safety_boundary") or ""),
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _agreement_decision(row: dict[str, str], *, preferred: str) -> str:
    decision = str(row.get(preferred) or "").strip().lower()
    if decision in VALID_REVIEW_DECISIONS:
        return decision
    fallback = str(row.get("decision") or "").strip().lower()
    return fallback if fallback in VALID_REVIEW_DECISIONS else "pending"


def _batch_review_sprint_payload(
    proof_path: Path,
    proof_report: dict[str, Any],
    handoff: dict[str, Any],
    validation: dict[str, Any],
    sprint: dict[str, Any],
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "proof_report_path": str(proof_path),
        "batch_root": proof_report.get("batch_root"),
        "state": handoff.get("state"),
        "complete": bool(handoff.get("complete")),
        "review_page": handoff.get("review_page"),
        "decision_board": handoff.get("proof_decision_board_html"),
        "proof_review_slate_tsv": handoff.get("proof_review_slate_tsv"),
        "proof_decision_slate_tsv": handoff.get("proof_decision_slate_tsv"),
        "validation": {
            "path": validation.get("path"),
            "status": validation.get("status"),
            "fresh": validation.get("fresh"),
            "passed": validation.get("passed"),
            "pending_count": validation.get("pending_count"),
            "pending_decision_count": validation.get("pending_decision_count"),
            "next_action": validation.get("next_action"),
        },
        "review_sprint": sprint,
        "decision_rubric": list(BATCH_SPEAKER_DECISION_RUBRIC),
        "commands": {
            "readiness": f"pavo batch readiness {shlex.quote(str(proof_path))}",
            "finalize_board_audit": (
                f"pavo batch finalize-board-audit {shlex.quote(str(proof_path))} "
                "pavo-batch-proof.decision-board.audit.json"
            ),
            "validate": handoff.get("validate_command"),
            "finish": handoff.get("finish_command"),
            "strict_proof": handoff.get("strict_proof_command"),
        },
        "safety_boundary": "Listen to every supporting clip before approving or rejecting speaker identity. Pavo can guide and verify the workflow, but the human owns the final identity decision.",
    }


def _batch_speaker_answer_sheet_payload(
    proof_path: Path,
    proof_report: dict[str, Any],
    handoff: dict[str, Any],
    validation: dict[str, Any],
    sprint: dict[str, Any],
) -> dict[str, Any]:
    priority_queue = sprint.get("priority_queue") if isinstance(sprint.get("priority_queue"), dict) else {}
    queue_items = priority_queue.get("items") if isinstance(priority_queue.get("items"), list) else []
    focus_by_cluster = {
        str(item.get("cluster_id") or ""): item
        for item in sprint.get("focus_order", [])
        if isinstance(item, dict)
    }
    decision_group_by_cluster = _batch_decision_group_by_cluster(handoff)
    rows: list[dict[str, Any]] = []
    for queue_item in queue_items:
        if not isinstance(queue_item, dict):
            continue
        focus_item = focus_by_cluster.get(str(queue_item.get("cluster_id") or ""), {})
        row = dict(queue_item)
        if not row.get("decision_group"):
            row["decision_group"] = decision_group_by_cluster.get(str(row.get("cluster_id") or ""))
        row["clip_paths"] = focus_item.get("clip_paths") or []
        row["transcript_samples"] = focus_item.get("transcript_samples") or []
        row["evidence_hints"] = focus_item.get("evidence_hints") or []
        row["estimated_minutes"] = focus_item.get("estimated_minutes")
        row["acoustic_verdict"] = focus_item.get("acoustic_verdict")
        row["decision"] = "pending"
        row["review_reason"] = ""
        row["notes"] = ""
        rows.append(row)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "proof_report_path": str(proof_path),
        "batch_root": proof_report.get("batch_root"),
        "state": handoff.get("state"),
        "complete": bool(handoff.get("complete")),
        "decision_board": handoff.get("proof_decision_board_html"),
        "proof_review_slate_tsv": handoff.get("proof_review_slate_tsv"),
        "pending_decision_count": sprint.get("pending_decision_count"),
        "pending_clip_count": sprint.get("pending_clip_count"),
        "estimated_minutes": sprint.get("estimated_minutes"),
        "priority_strategy": priority_queue.get("strategy") or "risk_then_priority_score",
        "rows": rows,
        "allowed_decisions": ["approved", "rejected", "pending"],
        "allowed_review_reasons": dict(BATCH_SPEAKER_REVIEW_REASONS),
        "commands": {
            "readiness": f"pavo batch readiness {shlex.quote(str(proof_path))}",
            "decision_board": f"pavo batch decision-board {shlex.quote(str(proof_path))}",
            "finalize_board_audit": (
                f"pavo batch finalize-board-audit {shlex.quote(str(proof_path))} "
                "pavo-batch-proof.decision-board.audit.json"
            ),
            "validate": handoff.get("validate_command"),
            "finish": handoff.get("finish_command"),
            "strict_proof": handoff.get("strict_proof_command"),
        },
        "safety_boundary": "Listen to every supporting clip before approving or rejecting speaker identity. Pavo can guide and verify the workflow, but the human owns the final identity decision.",
        "source_note": "This answer sheet is a compact review aid derived from the current Pavo proof validation and review sprint. Use the decision board for audio playback and audit JSON export.",
    }


def _batch_decision_group_by_cluster(handoff: dict[str, Any]) -> dict[str, str]:
    path_value = str(handoff.get("proof_decision_slate_tsv") or "").strip()
    if not path_value:
        return {}
    path = Path(path_value)
    if not path.exists():
        return {}
    rows, _fieldnames = _read_tsv(path)
    mapping: dict[str, str] = {}
    for row in rows:
        cluster_id = str(row.get("cluster_id") or "").strip()
        decision_group = str(row.get("decision_group") or "").strip()
        if cluster_id and decision_group:
            mapping.setdefault(cluster_id, decision_group)
    return mapping


def _batch_sprint_with_decision_groups(sprint: dict[str, Any], handoff: dict[str, Any]) -> dict[str, Any]:
    mapping = _batch_decision_group_by_cluster(handoff)
    if not mapping:
        return sprint
    enriched = dict(sprint)
    focus_order: list[dict[str, Any]] = []
    for item in sprint.get("focus_order") or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        if not row.get("decision_group"):
            row["decision_group"] = mapping.get(str(row.get("cluster_id") or ""))
        focus_order.append(row)
    enriched["focus_order"] = focus_order
    priority_queue = sprint.get("priority_queue") if isinstance(sprint.get("priority_queue"), dict) else {}
    queue_items: list[dict[str, Any]] = []
    for item in priority_queue.get("items") or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        if not row.get("decision_group"):
            row["decision_group"] = mapping.get(str(row.get("cluster_id") or ""))
        queue_items.append(row)
    if priority_queue:
        updated_queue = dict(priority_queue)
        updated_queue["items"] = queue_items
        enriched["priority_queue"] = updated_queue
    return enriched


def _render_batch_speaker_answer_sheet_markdown(payload: dict[str, Any]) -> str:
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    commands = payload.get("commands") if isinstance(payload.get("commands"), dict) else {}
    lines = [
        "# Pavo Speaker Answer Sheet",
        "",
        f"- State: `{payload.get('state')}`",
        f"- Pending decisions: `{payload.get('pending_decision_count')}`",
        f"- Pending clips: `{payload.get('pending_clip_count')}`",
        f"- Estimated review time: `{payload.get('estimated_minutes')}` minutes",
        f"- Priority strategy: `{str(payload.get('priority_strategy') or '').replace('_', ' ')}`",
        f"- Decision board: `{payload.get('decision_board')}`",
        "",
        "## How To Use",
        "",
        "1. Open the decision board so the clips are playable.",
        "2. Work down the priority order below.",
        "3. For each row, listen to every clip before writing `approved`, `rejected`, or `pending`.",
        "4. Use the browser board to download `pavo-batch-proof.decision-board.audit.json`, then run the finalize command.",
        "",
        "Allowed decision values: `approved`, `rejected`, `pending`.",
        "Allowed review reasons:",
        "",
    ]
    for value, label in BATCH_SPEAKER_REVIEW_REASONS.items():
        lines.append(f"- `{value}`: {label}")
    lines.extend(
        [
            "",
            "## Priority Listen Order",
            "",
        ]
    )
    if rows:
        for row in rows:
            lines.extend(
                [
                    f"### {row.get('queue_order')}. {row.get('cluster_id')} -> {row.get('speaker')}",
                    "",
                    f"- Decision group: `{row.get('decision_group')}`",
                    f"- Risk: `{row.get('decision_risk')}`",
                    f"- Shape: `{row.get('decision_shape')}`",
                    f"- Question: {row.get('question')}",
                    f"- Suggested action: {row.get('suggested_review_action')}",
                    f"- Clips: `{row.get('clip_count')}`",
                    f"- Acoustic verdict: `{row.get('acoustic_verdict')}`",
                    f"- Why queued: {row.get('why_queued')}",
                    "",
                    "Evidence hints:",
                    "",
                ]
            )
            for hint in row.get("evidence_hints") or []:
                lines.append(f"- {hint}")
            lines.extend(["", "Clip checklist:", ""])
            clip_paths = row.get("clip_paths") if isinstance(row.get("clip_paths"), list) else []
            samples = row.get("transcript_samples") if isinstance(row.get("transcript_samples"), list) else []
            for index, clip_path in enumerate(clip_paths, start=1):
                lines.append(f"- [ ] Clip {index}: `{clip_path}`")
                sample = samples[index - 1] if index - 1 < len(samples) else None
                if isinstance(sample, dict) and sample.get("excerpt"):
                    lines.append(f"      Row {sample.get('row_index')}: {sample.get('excerpt')}")
            lines.extend(
                [
                    "",
                    "Answer:",
                    "",
                    "- Decision: `pending`",
                    "- Review reason:",
                    "- Notes:",
                    "",
                ]
            )
    else:
        lines.append("- No pending speaker decisions.")
        lines.append("")
    lines.extend(
        [
            "## Commands",
            "",
            "```bash",
            str(commands.get("readiness") or ""),
            str(commands.get("decision_board") or ""),
            str(commands.get("finalize_board_audit") or ""),
            str(commands.get("validate") or ""),
            str(commands.get("finish") or ""),
            str(commands.get("strict_proof") or ""),
            "```",
            "",
            "## Safety Boundary",
            "",
            str(payload.get("safety_boundary") or ""),
            "",
        ]
    )
    return "\n".join(lines)


def _write_batch_speaker_answer_sheet_tsv(path: Path, payload: dict[str, Any]) -> None:
    fieldnames = [
        "queue_order",
        "decision_group",
        "cluster_id",
        "speaker",
        "decision_risk",
        "decision_shape",
        "question",
        "suggested_review_action",
        "clip_count",
        "priority_score",
        "acoustic_verdict",
        "clip_paths",
        "transcript_samples",
        "decision",
        "review_reason",
        "notes",
    ]
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    safe_rows: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        safe_rows.append(
            {
                "queue_order": str(row.get("queue_order") or ""),
                "decision_group": str(row.get("decision_group") or ""),
                "cluster_id": str(row.get("cluster_id") or ""),
                "speaker": str(row.get("speaker") or ""),
                "decision_risk": str(row.get("decision_risk") or ""),
                "decision_shape": str(row.get("decision_shape") or ""),
                "question": str(row.get("question") or ""),
                "suggested_review_action": str(row.get("suggested_review_action") or ""),
                "clip_count": str(row.get("clip_count") or ""),
                "priority_score": str(row.get("priority_score") or ""),
                "acoustic_verdict": str(row.get("acoustic_verdict") or ""),
                "clip_paths": " | ".join(str(value) for value in row.get("clip_paths") or []),
                "transcript_samples": " | ".join(
                    str(sample.get("excerpt") or "")
                    for sample in row.get("transcript_samples") or []
                    if isinstance(sample, dict)
                ),
                "decision": str(row.get("decision") or "pending"),
                "review_reason": str(row.get("review_reason") or ""),
                "notes": str(row.get("notes") or ""),
            }
        )
    _write_tsv(path, safe_rows, fieldnames)


def _render_batch_review_sprint_markdown(payload: dict[str, Any]) -> str:
    sprint = payload.get("review_sprint") if isinstance(payload.get("review_sprint"), dict) else {}
    commands = payload.get("commands") if isinstance(payload.get("commands"), dict) else {}
    lines = [
        "# Pavo Batch Review Sprint",
        "",
        f"- State: `{payload.get('state')}`",
        f"- Complete: `{str(bool(payload.get('complete'))).lower()}`",
        f"- Pending decisions: `{sprint.get('pending_decision_count')}`",
        f"- Pending clips: `{sprint.get('pending_clip_count')}`",
        f"- Estimated review time: `{sprint.get('estimated_minutes')}` minutes",
        f"- Decision board: `{payload.get('decision_board')}`",
        f"- Review page: `{payload.get('review_page')}`",
        "",
        "## Review Rule",
        "",
        str(payload.get("safety_boundary")),
        "",
        "## Decision Rubric",
        "",
    ]
    for rule in payload.get("decision_rubric") or BATCH_SPEAKER_DECISION_RUBRIC:
        lines.append(f"- {rule}")
    priority_queue = sprint.get("priority_queue") if isinstance(sprint.get("priority_queue"), dict) else {}
    priority_items = priority_queue.get("items") if isinstance(priority_queue.get("items"), list) else []
    lines.extend(
        [
            "",
            "## Priority Queue",
            "",
            f"- Strategy: `{str(priority_queue.get('strategy') or '').replace('_', ' ')}`",
            f"- Rationale: {priority_queue.get('rationale') or 'Review the most informative pending decisions first.'}",
        ]
    )
    risk_counts = priority_queue.get("risk_counts") if isinstance(priority_queue.get("risk_counts"), dict) else {}
    if risk_counts:
        lines.append(
            f"- Risk counts: high `{risk_counts.get('high', 0)}`, medium `{risk_counts.get('medium', 0)}`, low `{risk_counts.get('low', 0)}`"
        )
    lines.append("")
    if priority_items:
        for item in priority_items:
            lines.append(
                f"{item.get('queue_order')}. `{item.get('cluster_id')}` -> `{item.get('speaker')}` "
                f"({item.get('decision_risk')} risk): {item.get('why_queued')}"
            )
    else:
        lines.append("- No pending speaker decisions.")
    lines.extend(
        [
            "",
        "## Focus Order",
        "",
        ]
    )
    focus_order = sprint.get("focus_order") if isinstance(sprint.get("focus_order"), list) else []
    if focus_order:
        for item in focus_order:
            lines.extend(
                [
                    f"### {item.get('order')}. {item.get('cluster_id')} -> {item.get('speaker')}",
                    "",
                    f"- Question: {item.get('question')}",
                    f"- Clips: `{item.get('clip_count')}`",
                    f"- Estimate: `{item.get('estimated_minutes')}` minutes",
                    f"- Why now: {item.get('why_first')}",
                    f"- Decision shape: `{item.get('decision_shape')}`",
                    f"- Decision risk: `{item.get('decision_risk')}`",
                    f"- Suggested action: {item.get('suggested_review_action')}",
                    "",
                    "Evidence hints:",
                    "",
                ]
            )
            for hint in item.get("evidence_hints") or []:
                lines.append(f"- {hint}")
            lines.extend(
                [
                    "",
                    "Listen checklist:",
                    "",
                ]
            )
            clip_paths = item.get("clip_paths") if isinstance(item.get("clip_paths"), list) else []
            transcript_samples = item.get("transcript_samples") if isinstance(item.get("transcript_samples"), list) else []
            for clip_index, clip_path in enumerate(clip_paths, start=1):
                lines.append(f"- [ ] Clip {clip_index}: `{clip_path}`")
                sample = transcript_samples[clip_index - 1] if clip_index - 1 < len(transcript_samples) else None
                if isinstance(sample, dict) and sample.get("excerpt"):
                    lines.append(f"      Row {sample.get('row_index')}: {sample.get('excerpt')}")
            if not clip_paths:
                lines.append("- [ ] Open the decision board and listen to the supporting clips.")
            lines.append("")
            lines.extend(
                [
                    "Decision:",
                    "",
                    "- [ ] Approved",
                    "- [ ] Rejected",
                    "- [ ] Still pending / needs another listener",
                    "",
                ]
            )
    else:
        lines.append("- No pending speaker decisions.")
        lines.append("")
    lines.extend(
        [
            "## Commands",
            "",
            "```bash",
            str(commands.get("readiness") or ""),
            str(commands.get("finalize_board_audit") or ""),
            str(commands.get("validate") or ""),
            str(commands.get("finish") or ""),
            str(commands.get("strict_proof") or ""),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _batch_review_pack_artifacts(
    proof_path: Path,
    proof_report: dict[str, Any],
    handoff: dict[str, Any],
    review_packet: dict[str, Any],
) -> dict[str, Path | None]:
    proof_slate = Path(str(handoff.get("proof_review_slate_tsv"))) if handoff.get("proof_review_slate_tsv") else None
    validation_report = proof_slate.with_suffix(".validation.json") if proof_slate else None
    candidates = proof_path.with_name("pavo-speaker-memory-candidates.json")
    return {
        "proof_json": proof_path,
        "proof_markdown": _path_from_report(proof_report.get("proof_markdown_path")),
        "doctor_json": _path_from_report(proof_report.get("doctor_report_path")),
        "doctor_markdown": _path_from_report(proof_report.get("doctor_markdown_path")),
        "manifest_verification_markdown": _path_from_report(proof_report.get("verification_markdown_path")),
        "proof_review_slate_tsv": proof_slate,
        "proof_decision_slate_tsv": _path_from_report(handoff.get("proof_decision_slate_tsv")),
        "proof_decision_board_html": _path_from_report(handoff.get("proof_decision_board_html")),
        "proof_review_sprint_json": proof_path.with_name("pavo-batch-review-sprint.json"),
        "proof_review_sprint_markdown": proof_path.with_name("pavo-batch-review-sprint.md"),
        "speaker_answer_sheet_markdown": proof_path.with_name("pavo-batch-speaker-answer-sheet.md"),
        "speaker_answer_sheet_tsv": proof_path.with_name("pavo-batch-speaker-answer-sheet.tsv"),
        "speaker_calibration_json": proof_path.with_name("pavo-batch-speaker-calibration.json"),
        "speaker_calibration_markdown": proof_path.with_name("pavo-batch-speaker-calibration.md"),
        "speaker_calibration_tsv": proof_path.with_name("pavo-batch-speaker-calibration.tsv"),
        "review_cockpit_html": proof_path.with_name("pavo-batch-review-cockpit.html"),
        "proof_review_checklist_markdown": _path_from_report(handoff.get("proof_review_checklist_markdown")),
        "proof_review_validation_json": validation_report,
        "cluster_review_page_html": _path_from_report(review_packet.get("review_page")),
        "cluster_decision_brief_html": _path_from_report(review_packet.get("decision_brief_html")),
        "cluster_review_slate_tsv": _path_from_report(review_packet.get("slate_tsv")),
        "speaker_memory_candidates_json": candidates,
    }


def _path_from_report(value: Any) -> Path | None:
    text = str(value or "").strip()
    return Path(text) if text else None


def _review_pack_artifact_filename(name: str, source: Path) -> str:
    suffix = "".join(source.suffixes) or ".artifact"
    return f"{name}{suffix}"


def _render_batch_review_pack_readme(manifest: dict[str, Any]) -> str:
    handoff = manifest.get("operator_handoff") if isinstance(manifest.get("operator_handoff"), dict) else {}
    validation = manifest.get("validation") if isinstance(manifest.get("validation"), dict) else {}
    proof_report = str(manifest.get("proof_report_path") or "")
    batch_root = str(manifest.get("batch_root") or "")
    proof_review_slate = str(handoff.get("proof_review_slate_tsv") or "")
    reviewed_decision_slate = str(Path(batch_root) / "pavo-batch-proof.decision-slate.reviewed.tsv") if batch_root else "pavo-batch-proof.decision-slate.reviewed.tsv"
    audit_import_command = (
        "pavo batch apply-decision-board-audit "
        f"{shlex.quote(proof_report)} "
        "pavo-batch-proof.decision-board.audit.json "
        f"--out {shlex.quote(proof_review_slate)} "
        f"--decision-slate-out {shlex.quote(reviewed_decision_slate)}"
    )
    audit_finalize_command = (
        "pavo batch finalize-board-audit "
        f"{shlex.quote(proof_report)} "
        "pavo-batch-proof.decision-board.audit.json "
        f"--out {shlex.quote(proof_review_slate)} "
        f"--decision-slate-out {shlex.quote(reviewed_decision_slate)}"
    )
    readiness_command = f"pavo batch readiness {shlex.quote(proof_report)}"
    cockpit_command = f"pavo batch review-cockpit {shlex.quote(proof_report)}"
    verify_cockpit_command = f"pavo batch verify-review-cockpit {shlex.quote(proof_report)}"
    calibration_command = f"pavo batch speaker-calibration {shlex.quote(proof_report)}"
    agreement_command = "pavo batch score-speaker-agreement pavo-batch-speaker-calibration.tsv pavo-batch-speaker-calibration.tsv"
    lines = [
        "# Pavo Batch Review Pack",
        "",
        f"- Batch root: `{manifest.get('batch_root')}`",
        f"- Proof report: `{manifest.get('proof_report_path')}`",
        f"- Generated: `{manifest.get('generated_at')}`",
        f"- Copied artifacts: {manifest.get('copied_artifact_count')}",
        f"- Missing optional artifacts: {manifest.get('missing_artifact_count')}",
        f"- Artifact manifest SHA-256: `{manifest.get('artifact_manifest_sha256')}`",
        f"- Raw audio copied: `{str(bool(manifest.get('raw_audio_copied'))).lower()}`",
        "",
        "## What To Open",
        "",
        "- Start with the artifact manifest entry named `review_cockpit_html` for the one-page operator cockpit.",
        "- Use the artifact manifest entry named `proof_decision_board_html` for the human speaker decisions.",
        "- Use the entry named `proof_review_checklist_markdown` as the command checklist.",
        "- Inspect `proof_json` and `proof_review_validation_json` when a gate fails.",
        "",
        "## Current Gate",
        "",
        f"- Handoff state: `{handoff.get('state')}`",
        f"- Complete: `{str(bool(handoff.get('complete'))).lower()}`",
        f"- Validation status: `{validation.get('status')}`",
        f"- Pending decisions: `{validation.get('pending_decision_count')}`",
        f"- Next action: {validation.get('next_action')}",
        "",
        "## Commands",
        "",
        "Run readiness before and after review to prove whether this pack is machine-clean, human-pending, or complete. After reviewing the board, download `pavo-batch-proof.decision-board.audit.json`, place it beside this README or run from your download directory, then use the one-command finalize path. The lower-level import command is included as a fallback.",
        "",
        f"```bash\n{readiness_command}\n{cockpit_command}\n{verify_cockpit_command}\n{calibration_command}\n{audit_finalize_command}\n{readiness_command}\n\n# Optional second-listener agreement scoring after calibration TSV is filled:\n{agreement_command}\n\n# Fallback/manual path:\n{audit_import_command}\n{handoff.get('validate_command')}\n{handoff.get('finish_command')}\n{handoff.get('strict_proof_command')}\n```",
        "",
        "## Safety Boundary",
        "",
        "This pack excludes raw audio, signed URLs, credentials, voiceprints, and identity approvals. It is a review handoff, not a substitute for human speaker confirmation.",
        "",
        "## Missing Optional Artifacts",
        "",
    ]
    missing = manifest.get("missing_artifacts") if isinstance(manifest.get("missing_artifacts"), list) else []
    if missing:
        lines.extend(f"- `{item.get('name')}`: `{item.get('path')}`" for item in missing)
    else:
        lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def _proof_review_slate_path_from_report(proof_path: Path) -> Path:
    proof_report = json.loads(proof_path.read_text())
    review_slate_value = (
        proof_report.get("proof_review_slate_path")
        or (proof_report.get("review_packet") or {}).get("proof_review_slate_tsv")
        or (proof_report.get("operator_handoff") or {}).get("proof_review_slate_tsv")
    )
    if not review_slate_value:
        raise ValueError(f"proof report does not name a proof review slate: {proof_path}")
    review_slate_path = Path(str(review_slate_value))
    if not review_slate_path.exists():
        raise FileNotFoundError(f"proof review slate not found: {review_slate_path}")
    return review_slate_path


def _read_decision_slate_tsv(path: Path) -> dict[str, dict[str, str]]:
    rows, _fieldnames = _read_tsv(path)
    decisions: dict[str, dict[str, str]] = {}
    for row_number, row in enumerate(rows, start=2):
        decision_group = str(row.get("decision_group") or "").strip()
        if not decision_group:
            raise ValueError(f"decision slate row {row_number} is missing decision_group")
        decision = str(row.get("decision") or "").strip().lower()
        if decision not in VALID_REVIEW_DECISIONS:
            raise ValueError(
                f"decision slate row {row_number} has invalid decision {decision!r}; "
                f"expected one of {sorted(VALID_REVIEW_DECISIONS)}"
            )
        if decision_group in decisions:
            raise ValueError(f"decision slate repeats decision_group {decision_group!r}")
        decisions[decision_group] = {
            "decision": decision,
            "speaker": str(row.get("speaker") or "").strip(),
            "review_reason": str(row.get("review_reason") or "").strip(),
        }
    return decisions


def _read_tsv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames:
            raise ValueError(f"TSV has no header: {path}")
        return [dict(row) for row in reader], list(reader.fieldnames)


def _write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _render_batch_decision_board_html(
    *,
    proof_report: dict[str, Any],
    proof_report_path: Path,
    proof_slate_path: Path,
    decision_slate_path: Path,
    decisions: list[dict[str, str]],
    rows_by_group: dict[str, list[dict[str, str]]],
) -> str:
    batch_root = str(proof_report.get("batch_root") or "")
    pending_count = sum(1 for row in decisions if str(row.get("decision") or "").strip().lower() == "pending")
    supporting_count = sum(len(rows_by_group.get(str(row.get("decision_group") or ""), [])) for row in decisions)
    estimated_seconds = sum(_batch_decision_review_seconds(row, rows_by_group.get(str(row.get("decision_group") or ""), [])) for row in decisions)
    estimated_minutes = round(estimated_seconds / 60, 1) if estimated_seconds else 0
    enriched_decisions = [
        _batch_decision_with_review_context(row, rows_by_group.get(str(row.get("decision_group") or ""), []))
        for row in decisions
    ]
    rows_json = json.dumps(enriched_decisions, sort_keys=True)
    reason_options_json = json.dumps(BATCH_SPEAKER_REVIEW_REASONS, sort_keys=True)
    storage_key = json.dumps(f"pavo-decision-board:{proof_report_path}:{decision_slate_path}")
    cards = "\n".join(
        _render_batch_decision_card(row, rows_by_group.get(str(row.get("decision_group") or ""), []))
        for row in enriched_decisions
    )
    decision_rubric_html = "\n".join(f"<li>{escape(rule)}</li>" for rule in BATCH_SPEAKER_DECISION_RUBRIC)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pavo Batch Decision Board</title>
  <style>
    :root {{ color-scheme: light; --ink:#172033; --muted:#647086; --line:#d9e1ef; --soft:#f5f7fb; --brand:#3157d5; --ok:#0f8f61; --bad:#b42318; --pending:#9a6700; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--ink); background:#eef3fb; }}
    header {{ position:sticky; top:0; z-index:2; background:rgba(255,255,255,.94); border-bottom:1px solid var(--line); padding:18px 24px; backdrop-filter: blur(8px); }}
    h1 {{ margin:0; font-size:24px; }}
    .sub {{ margin-top:5px; color:var(--muted); font-size:13px; }}
    .scorebar {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; }}
    .score {{ background:var(--soft); border:1px solid var(--line); border-radius:12px; padding:9px 12px; min-width:130px; }}
    .score strong {{ display:block; font-size:20px; }}
    .sprint {{ margin-top:14px; border:1px solid #c7d7fe; background:#eff5ff; border-radius:14px; padding:12px; display:flex; gap:12px; align-items:center; justify-content:space-between; }}
    .sprint strong {{ display:block; font-size:15px; }}
    .sprint button {{ background:var(--brand); }}
    .sprint-actions {{ display:flex; flex-wrap:wrap; gap:8px; justify-content:flex-end; }}
    .rubric {{ margin-top:12px; background:#fff7ed; border:1px solid #fed7aa; border-radius:14px; padding:12px 14px; }}
    .rubric strong {{ display:block; margin-bottom:6px; }}
    .rubric ul {{ margin:0; padding-left:20px; color:#4b5563; font-size:13px; line-height:1.45; }}
    main {{ display:grid; grid-template-columns:minmax(0,1fr) 360px; gap:18px; padding:18px 24px 32px; }}
    .card {{ background:#fff; border:1px solid var(--line); border-radius:16px; box-shadow:0 8px 24px rgba(23,32,51,.06); margin-bottom:14px; overflow:hidden; }}
    .card-head {{ display:flex; gap:12px; align-items:flex-start; justify-content:space-between; padding:16px; border-bottom:1px solid var(--line); }}
    .card h2 {{ margin:0 0 6px; font-size:17px; }}
    .pill {{ display:inline-flex; align-items:center; border:1px solid var(--line); border-radius:999px; padding:3px 8px; font-size:12px; color:var(--muted); background:var(--soft); }}
    .decision {{ min-width:160px; display:grid; gap:8px; }}
    .quick-reasons {{ display:grid; grid-template-columns:1fr; gap:6px; }}
    .quick-reasons button {{ padding:7px 9px; font-size:12px; }}
    button {{ border:0; border-radius:10px; padding:9px 10px; color:#fff; font-weight:700; cursor:pointer; }}
    button.approve {{ background:var(--ok); }}
    button.reject {{ background:var(--bad); }}
    button.pending {{ background:var(--pending); }}
    button:focus {{ outline:3px solid rgba(49,87,213,.28); }}
    label {{ display:block; font-size:12px; color:var(--muted); margin-bottom:4px; }}
    input, select, textarea {{ width:100%; border:1px solid var(--line); border-radius:10px; padding:8px 10px; font:inherit; }}
    .body {{ padding:16px; }}
    .meta {{ display:flex; flex-wrap:wrap; gap:8px; margin:8px 0 12px; }}
    .guidance {{ border:1px solid #bfdbfe; background:#eff6ff; border-radius:14px; padding:12px; margin-bottom:14px; }}
    .guidance strong {{ display:block; margin-bottom:6px; }}
    .guidance ul {{ margin:8px 0 0; padding-left:20px; color:#334155; font-size:13px; line-height:1.45; }}
    .sample {{ border-top:1px solid var(--line); padding:12px 0; }}
    .sample:first-child {{ border-top:0; padding-top:0; }}
    audio {{ width:100%; margin:8px 0; }}
    .transcript {{ background:var(--soft); border-radius:12px; padding:10px; color:#28344d; line-height:1.45; }}
    aside {{ position:sticky; top:118px; align-self:start; background:#fff; border:1px solid var(--line); border-radius:16px; box-shadow:0 8px 24px rgba(23,32,51,.06); padding:16px; }}
    aside h2 {{ margin:0 0 8px; font-size:16px; }}
    .commands {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:12px; white-space:pre-wrap; background:#0d1324; color:#dbeafe; border-radius:12px; padding:12px; overflow:auto; }}
    #tsv {{ min-height:220px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:12px; }}
    .notice {{ color:var(--muted); font-size:13px; line-height:1.4; }}
    @media (max-width: 980px) {{ main {{ grid-template-columns:1fr; }} aside {{ position:static; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Pavo Batch Decision Board</h1>
    <div class="sub">Human review surface for grouped speaker decisions. This page does not write files or approve identity by itself.</div>
    <div class="scorebar">
      <div class="score"><strong>{len(decisions)}</strong> decisions</div>
      <div class="score"><strong id="pending-count">{pending_count}</strong> pending</div>
      <div class="score"><strong id="reviewed-count">0</strong> reviewed</div>
      <div class="score"><strong id="review-progress-percent">0%</strong> complete</div>
      <div class="score"><strong id="missing-reason-count">0</strong> missing reasons</div>
      <div class="score"><strong id="export-ready-status">No</strong> export ready</div>
      <div class="score"><strong id="high-risk-count">0</strong> high risk</div>
      <div class="score"><strong id="medium-risk-count">0</strong> medium risk</div>
      <div class="score"><strong>{supporting_count}</strong> supporting clips</div>
      <div class="score"><strong id="sprint-minutes">{estimated_minutes}</strong> est. minutes</div>
    </div>
    <div class="sprint" id="review-sprint">
      <div>
        <strong>Review Sprint</strong>
        <div class="sub">Listen to every supporting clip, decide the grouped speaker question, then download the audit JSON. Pavo will not approve identity by itself.</div>
      </div>
      <div class="sprint-actions">
        <button onclick="focusNextHighRisk()">Focus high risk</button>
        <button onclick="focusNextPending()">Focus next pending</button>
      </div>
    </div>
    <div class="rubric" id="decision-rubric">
      <strong>Decision Rubric</strong>
      <ul>
        {decision_rubric_html}
      </ul>
    </div>
  </header>
  <main>
    <section>
      {cards}
    </section>
    <aside>
      <h2>Finish Flow</h2>
      <p class="notice">Use the buttons to update the TSV below. Fastest safe path: download the audit JSON, then run <code>finalize-board-audit</code>. Keyboard: <strong>A</strong> approve, <strong>R</strong> reject, <strong>P</strong> pending, <strong>J/K</strong> move.</p>
      <div class="commands">pavo batch finalize-board-audit {escape(str(proof_report_path))} pavo-batch-proof.decision-board.audit.json --out {escape(str(proof_slate_path))} --decision-slate-out {escape(str(decision_slate_path.with_name("pavo-batch-proof.decision-slate.reviewed.tsv")))}

pavo batch apply-decision-board-audit {escape(str(proof_report_path))} pavo-batch-proof.decision-board.audit.json --out {escape(str(proof_slate_path))} --decision-slate-out {escape(str(decision_slate_path.with_name("pavo-batch-proof.decision-slate.reviewed.tsv")))}

pavo batch apply-decision-slate {escape(str(proof_report_path))} {escape(str(decision_slate_path))} --out {escape(str(proof_slate_path))}

pavo batch finalize-reviewed-proof {escape(str(proof_report_path))}</div>
      <h2 style="margin-top:16px;">Generated Decision TSV</h2>
      <textarea id="tsv" spellcheck="false"></textarea>
      <button class="approve" style="margin-top:8px;" onclick="downloadTsv()">Download TSV</button>
      <button class="pending" style="margin-top:8px;" onclick="downloadAudit()">Download Audit JSON</button>
      <button class="reject" style="margin-top:8px;" onclick="resetSavedState()">Reset Saved Board State</button>
      <p class="notice" id="autosave-status">Autosave ready.</p>
      <p class="notice">Batch root: <code>{escape(batch_root)}</code></p>
    </aside>
  </main>
  <script>
    const rows = {rows_json};
    const reviewReasonOptions = {reason_options_json};
    const headers = ["decision_group","decision","speaker","review_reason","cluster_id","question","row_indices","clip_count","priority_tier","priority_score","priority_reason","acoustic_verdict","clip_paths","transcript_samples"];
    const storageKey = {storage_key};
    const source = {{
      proofReport: {json.dumps(str(proof_report_path))},
      proofReviewSlate: {json.dumps(str(proof_slate_path))},
      decisionSlate: {json.dumps(str(decision_slate_path))},
      batchRoot: {json.dumps(batch_root)}
    }};
    let auditEvents = [];
    let activeIndex = 0;
    function clean(value) {{ return String(value ?? "").replace(/[\\t\\r\\n]+/g, " ").trim(); }}
    function setDecision(group, decision, reason = "manual") {{
      const row = rows.find(item => item.decision_group === group);
      if (!row) return;
      const before = row.decision;
      row.decision = decision;
      const card = document.querySelector(`[data-group="${{CSS.escape(group)}}"]`);
      if (card) {{
        card.querySelector("[data-status]").textContent = decision;
        card.querySelector("[data-status]").className = "pill " + decision;
      }}
      recordAudit({{ type: "decision", group, before, after: decision, reason }});
      renderTsv();
    }}
    function setDecisionWithReason(group, decision, reviewReason, reason = "reasoned_shortcut") {{
      const row = rows.find(item => item.decision_group === group);
      if (!row) return;
      const before = row.review_reason || "";
      row.review_reason = reviewReason;
      const card = document.querySelector(`[data-group="${{CSS.escape(group)}}"]`);
      if (card) {{
        const select = card.querySelector("select");
        if (select) select.value = reviewReason;
      }}
      recordAudit({{ type: "review_reason", group, before, after: reviewReason, reason }});
      setDecision(group, decision, reason);
    }}
    function updateReviewReason(group, value) {{
      const row = rows.find(item => item.decision_group === group);
      if (row) {{
        const before = row.review_reason || "";
        row.review_reason = value;
        recordAudit({{ type: "review_reason", group, before, after: value, reason: "manual" }});
      }}
      renderTsv();
    }}
    function updateSpeaker(group, value) {{
      const row = rows.find(item => item.decision_group === group);
      if (row) {{
        const before = row.speaker;
        row.speaker = value;
        recordAudit({{ type: "speaker", group, before, after: value, reason: "manual" }});
      }}
      renderTsv();
    }}
    function renderTsv() {{
      const lines = [headers.join("\\t")];
      for (const row of rows) lines.push(headers.map(key => clean(row[key])).join("\\t"));
      document.getElementById("tsv").value = lines.join("\\n") + "\\n";
      updateProgress();
      saveState();
    }}
    function updateProgress() {{
      const completion = reviewCompletion();
      const risk = riskCompletion();
      document.getElementById("pending-count").textContent = String(completion.pendingCount);
      document.getElementById("reviewed-count").textContent = String(completion.reviewedCount);
      document.getElementById("review-progress-percent").textContent = `${{completion.progressPercent}}%`;
      document.getElementById("missing-reason-count").textContent = String(completion.missingReasonCount);
      document.getElementById("export-ready-status").textContent = completion.exportReady ? "Yes" : "No";
      document.getElementById("high-risk-count").textContent = String(risk.highPendingCount);
      document.getElementById("medium-risk-count").textContent = String(risk.mediumPendingCount);
      document.getElementById("autosave-status").textContent = `Autosaved locally. ${{completion.reviewedCount}}/${{completion.decisionCount}} decisions reviewed; ${{completion.missingReasonCount}} missing reason(s); export ready: ${{completion.exportReady ? "yes" : "no"}}.`;
    }}
    function reviewCompletion() {{
      const pending = rows.filter(row => row.decision === "pending").length;
      const approved = rows.filter(row => row.decision === "approved").length;
      const rejected = rows.filter(row => row.decision === "rejected").length;
      const reviewed = rows.length - pending;
      const missingReasons = rows.filter(row => ["approved", "rejected"].includes(row.decision) && !row.review_reason).length;
      const progress = rows.length ? Math.round((reviewed / rows.length) * 1000) / 10 : 100;
      return {{
        decisionCount: rows.length,
        pendingCount: pending,
        approvedCount: approved,
        rejectedCount: rejected,
        reviewedCount: reviewed,
        missingReasonCount: missingReasons,
        progressPercent: progress,
        exportReady: pending === 0 && missingReasons === 0
      }};
    }}
    function reviewContext() {{
      return {{
        strategy: "risk_then_priority_score",
        contextVersion: 1,
        rows: rows.map(row => ({{
          decision_group: row.decision_group,
          cluster_id: row.cluster_id,
          speaker: row.speaker,
          decision_shape: row.decision_shape,
          decision_risk: row.decision_risk,
          suggested_review_action: row.suggested_review_action,
          evidence_hints: row.evidence_hints || [],
          priority_score: row.priority_score,
          acoustic_verdict: row.acoustic_verdict,
          clip_count: row.clip_count
        }}))
      }};
    }}
    function riskCompletion() {{
      const cards = Array.from(document.querySelectorAll("[data-group]"));
      let highPendingCount = 0;
      let mediumPendingCount = 0;
      for (const card of cards) {{
        const row = rows.find(item => item.decision_group === card.dataset.group);
        if (!row || row.decision !== "pending") continue;
        if (card.dataset.risk === "high") highPendingCount += 1;
        if (card.dataset.risk === "medium") mediumPendingCount += 1;
      }}
      return {{ highPendingCount, mediumPendingCount }};
    }}
    function recordAudit(event) {{
      auditEvents.push({{ ...event, at: new Date().toISOString() }});
    }}
    function saveState() {{
      const payload = {{ savedAt: new Date().toISOString(), source, rows, auditEvents }};
      try {{ localStorage.setItem(storageKey, JSON.stringify(payload)); }} catch (_err) {{}}
    }}
    function loadState() {{
      try {{
        const raw = localStorage.getItem(storageKey);
        if (!raw) return;
        const payload = JSON.parse(raw);
        if (Array.isArray(payload.auditEvents)) auditEvents = payload.auditEvents;
        if (Array.isArray(payload.rows)) {{
          for (const saved of payload.rows) {{
            const row = rows.find(item => item.decision_group === saved.decision_group);
            if (row) {{
              row.decision = saved.decision || row.decision;
              row.speaker = saved.speaker || row.speaker;
              row.review_reason = saved.review_reason || row.review_reason || "";
            }}
          }}
        }}
        for (const row of rows) {{
          const card = document.querySelector(`[data-group="${{CSS.escape(row.decision_group)}}"]`);
          if (card) {{
            card.querySelector("[data-status]").textContent = row.decision;
            card.querySelector("[data-status]").className = "pill " + row.decision;
            const input = card.querySelector("input");
            if (input) input.value = row.speaker;
            const select = card.querySelector("select");
            if (select) select.value = row.review_reason || "";
          }}
        }}
      }} catch (_err) {{}}
    }}
    function focusCard(index) {{
      const cards = Array.from(document.querySelectorAll("[data-group]"));
      if (!cards.length) return;
      activeIndex = Math.max(0, Math.min(index, cards.length - 1));
      cards[activeIndex].scrollIntoView({{ block: "center" }});
      cards[activeIndex].querySelector("button").focus();
    }}
    function focusNextPending() {{
      const cards = Array.from(document.querySelectorAll("[data-group]"));
      const index = cards.findIndex(card => {{
        const group = card.dataset.group;
        const row = rows.find(item => item.decision_group === group);
        return row && row.decision === "pending";
      }});
      focusCard(index >= 0 ? index : 0);
    }}
    function focusNextHighRisk() {{
      const cards = Array.from(document.querySelectorAll("[data-group]"));
      const index = cards.findIndex(card => {{
        const group = card.dataset.group;
        const row = rows.find(item => item.decision_group === group);
        return row && row.decision === "pending" && card.dataset.risk === "high";
      }});
      focusCard(index >= 0 ? index : 0);
    }}
    function downloadTsv() {{
      const blob = new Blob([document.getElementById("tsv").value], {{ type: "text/tab-separated-values" }});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "pavo-batch-proof.decision-slate.reviewed.tsv";
      link.click();
      URL.revokeObjectURL(url);
    }}
    function auditPayload() {{
      return {{
        exportedAt: new Date().toISOString(),
        source,
        summary: reviewCompletion(),
        reviewContext: reviewContext(),
        rows,
        auditEvents,
        safetyBoundary: "This audit records human review-board edits. It is not a voiceprint and does not prove identity by itself."
      }};
    }}
    function validateAuditReady() {{
      const missing = rows.filter(row => ["approved", "rejected"].includes(row.decision) && !row.review_reason);
      if (!missing.length) return true;
      const first = missing[0];
      const index = rows.findIndex(row => row.decision_group === first.decision_group);
      focusCard(index >= 0 ? index : 0);
      const message = `Missing review reason for ${{first.decision_group}}. Choose a reason before downloading audit JSON.`;
      document.getElementById("autosave-status").textContent = message;
      alert(message);
      recordAudit({{ type: "export_blocked", group: first.decision_group, reason: "missing_review_reason" }});
      saveState();
      return false;
    }}
    function downloadAudit() {{
      if (!validateAuditReady()) return;
      const blob = new Blob([JSON.stringify(auditPayload(), null, 2) + "\\n"], {{ type: "application/json" }});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "pavo-batch-proof.decision-board.audit.json";
      link.click();
      URL.revokeObjectURL(url);
    }}
    function resetSavedState() {{
      localStorage.removeItem(storageKey);
      location.reload();
    }}
    document.addEventListener("keydown", event => {{
      if (["INPUT","TEXTAREA"].includes(document.activeElement.tagName)) return;
      const cards = Array.from(document.querySelectorAll("[data-group]"));
      const group = cards[activeIndex]?.dataset.group;
      if (event.key.toLowerCase() === "j") {{ focusCard(activeIndex + 1); event.preventDefault(); }}
      if (event.key.toLowerCase() === "k") {{ focusCard(activeIndex - 1); event.preventDefault(); }}
      if (group && event.key.toLowerCase() === "a") {{ setDecisionWithReason(group, "approved", "approved_clean_match", "keyboard"); event.preventDefault(); }}
      if (group && event.key.toLowerCase() === "r") {{ setDecisionWithReason(group, "rejected", "rejected_wrong_speaker", "keyboard"); event.preventDefault(); }}
      if (group && event.key.toLowerCase() === "p") {{ setDecisionWithReason(group, "pending", "pending_uncertain", "keyboard"); event.preventDefault(); }}
    }});
    loadState();
    renderTsv();
    focusNextPending();
  </script>
</body>
</html>
"""


def _render_batch_decision_card(decision: dict[str, str], proof_rows: list[dict[str, str]]) -> str:
    group = str(decision.get("decision_group") or "")
    current = str(decision.get("decision") or "pending").strip().lower() or "pending"
    speaker = str(decision.get("speaker") or "")
    review_reason = str(decision.get("review_reason") or "")
    clip_count = _optional_int(decision.get("clip_count")) or len(proof_rows)
    risk = _batch_speaker_decision_risk(decision, clip_count=clip_count)
    shape = _batch_speaker_decision_shape(decision)
    reason_options = ['<option value="">Choose review reason...</option>'] + [
        (
            f'<option value="{escape(value)}"'
            f'{" selected" if value == review_reason else ""}>{escape(label)}</option>'
        )
        for value, label in BATCH_SPEAKER_REVIEW_REASONS.items()
    ]
    samples = "\n".join(_render_batch_decision_sample(row) for row in proof_rows)
    if not samples:
        samples = '<div class="sample"><p class="notice">No supporting proof rows found for this decision group.</p></div>'
    guidance = _render_batch_decision_guidance(decision, proof_rows)
    return f"""<article class="card" data-group="{escape(group)}" data-risk="{escape(risk)}" data-shape="{escape(shape)}">
  <div class="card-head">
    <div>
      <h2>{escape(group)} · {escape(str(decision.get('cluster_id') or 'unknown cluster'))}</h2>
      <div>{escape(str(decision.get('question') or 'Review this speaker decision'))}</div>
      <div class="meta">
        <span class="pill" data-status>{escape(current)}</span>
        <span class="pill">{escape(str(decision.get('priority_tier') or 'priority unknown'))}</span>
        <span class="pill">score {escape(str(decision.get('priority_score') or ''))}</span>
        <span class="pill">{len(proof_rows)} clips</span>
      </div>
    </div>
    <div class="decision">
      <label>Speaker</label>
      <input value="{escape(speaker)}" oninput="updateSpeaker('{escape(group)}', this.value)">
      <label>Review reason</label>
      <select onchange="updateReviewReason('{escape(group)}', this.value)">
        {"".join(reason_options)}
      </select>
      <label>Reasoned shortcuts</label>
      <div class="quick-reasons">
        <button class="approve" onclick="setDecisionWithReason('{escape(group)}','approved','approved_clean_match')">Approve clean</button>
        <button class="approve" onclick="setDecisionWithReason('{escape(group)}','approved','approved_speaker_corrected')">Approve corrected</button>
        <button class="reject" onclick="setDecisionWithReason('{escape(group)}','rejected','rejected_wrong_speaker')">Reject wrong speaker</button>
        <button class="reject" onclick="setDecisionWithReason('{escape(group)}','rejected','rejected_overlap_or_noise')">Reject noisy/overlap</button>
        <button class="pending" onclick="setDecisionWithReason('{escape(group)}','pending','pending_uncertain')">Pending uncertain</button>
        <button class="pending" onclick="setDecisionWithReason('{escape(group)}','pending','pending_second_listener')">Needs second listener</button>
      </div>
      <button class="approve" onclick="setDecision('{escape(group)}','approved')">Approve</button>
      <button class="reject" onclick="setDecision('{escape(group)}','rejected')">Reject</button>
      <button class="pending" onclick="setDecision('{escape(group)}','pending')">Pending</button>
    </div>
  </div>
  <div class="body">
    <div class="meta">
      <span class="pill">Acoustic: {escape(str(decision.get('acoustic_verdict') or 'unknown'))}</span>
      <span class="pill">Rows: {escape(str(decision.get('row_indices') or ''))}</span>
    </div>
    {guidance}
    {samples}
  </div>
</article>"""


def _batch_decision_with_review_context(
    decision: dict[str, str],
    proof_rows: list[dict[str, str]],
) -> dict[str, Any]:
    enriched: dict[str, Any] = dict(decision)
    clip_count = _optional_int(decision.get("clip_count")) or len(proof_rows)
    enriched["decision_shape"] = _batch_speaker_decision_shape(decision)
    enriched["decision_risk"] = _batch_speaker_decision_risk(decision, clip_count=clip_count)
    enriched["suggested_review_action"] = _batch_speaker_suggested_review_action(decision, clip_count=clip_count)
    enriched["evidence_hints"] = _batch_speaker_evidence_hints(decision, clip_count=clip_count)
    return enriched


def _render_batch_decision_guidance(decision: dict[str, str], proof_rows: list[dict[str, str]]) -> str:
    clip_count = _optional_int(decision.get("clip_count")) or len(proof_rows)
    shape = _batch_speaker_decision_shape(decision)
    risk = _batch_speaker_decision_risk(decision, clip_count=clip_count)
    action = _batch_speaker_suggested_review_action(decision, clip_count=clip_count)
    hints = _batch_speaker_evidence_hints(decision, clip_count=clip_count)
    hint_html = "\n".join(f"<li>{escape(hint)}</li>" for hint in hints)
    if not hint_html:
        hint_html = "<li>Listen to every supporting clip before making a speaker decision.</li>"
    return f"""<div class="guidance">
      <strong>Review guidance</strong>
      <div class="meta">
        <span class="pill">Decision shape: {escape(shape)}</span>
        <span class="pill">Decision risk: {escape(risk)}</span>
      </div>
      <div class="notice"><strong>Suggested action:</strong> {escape(action)}</div>
      <div class="notice"><strong>Evidence hints:</strong></div>
      <ul>
        {hint_html}
      </ul>
    </div>"""


def _batch_decision_review_seconds(_decision: dict[str, str], proof_rows: list[dict[str, str]]) -> int:
    return max(1, len(proof_rows)) * 45 + 20


def _render_batch_decision_sample(row: dict[str, str]) -> str:
    clip = str(row.get("clip_path") or "")
    clip_uri = Path(clip).absolute().as_uri() if clip and Path(clip).exists() else clip
    audio = f'<audio controls preload="none" src="{escape(clip_uri)}"></audio>' if clip else ""
    return f"""<div class="sample">
  <div class="meta">
    <span class="pill">row {escape(str(row.get('row_index') or ''))}</span>
    <span class="pill">{escape(str(row.get('acoustic_verdict') or ''))}</span>
    <span class="pill">{escape(str(row.get('clip_path') or 'no clip path'))}</span>
  </div>
  {audio}
  <div class="transcript">{escape(str(row.get('transcript') or ''))}</div>
</div>"""


def _speaker_slug(value: str) -> str:
    slug = "".join(character.lower() if character.isalnum() else "-" for character in value)
    return "-".join(part for part in slug.split("-") if part) or "speaker"


def _unknown_speaker_label(value: str) -> bool:
    lowered = value.strip().lower()
    return not lowered or lowered in {"unknown", "unknown speaker", "speaker", "unidentified"} or lowered.startswith("speaker_")


def _tsv_safe(value: str) -> str:
    return value.replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def verify_batch_manifest(report_path: Path | str) -> BatchManifestVerificationResult:
    path = Path(report_path)
    report = json.loads(path.read_text())
    source_recordings = report.get("source_recordings") or []
    expected_generated_artifacts = report.get("generated_artifacts") or {}
    verified_recordings: list[dict[str, Any]] = []
    verified_generated_artifacts: dict[str, dict[str, Any]] = {}
    mismatches: list[dict[str, Any]] = []
    checked_artifact_count = 0

    for item in source_recordings:
        recording_id = str(item.get("recording_id") or "")
        expected_artifacts = item.get("artifacts") or {}
        actual_artifacts: dict[str, dict[str, Any]] = {}
        for name, expected in sorted(expected_artifacts.items()):
            artifact_path = Path(str(expected.get("path") or ""))
            checked_artifact_count += 1
            if not artifact_path.exists():
                mismatches.append(
                    {
                        "recording_id": recording_id,
                        "artifact": name,
                        "path": str(artifact_path),
                        "reason": "missing",
                        "expected": expected,
                        "actual": None,
                    }
                )
                continue
            actual = _file_fingerprint(artifact_path)
            actual_artifacts[name] = actual
            if actual.get("bytes") != expected.get("bytes") or actual.get("sha256") != expected.get("sha256"):
                mismatches.append(
                    {
                        "recording_id": recording_id,
                        "artifact": name,
                        "path": str(artifact_path),
                        "reason": "fingerprint_mismatch",
                        "expected": {
                            "bytes": expected.get("bytes"),
                            "sha256": expected.get("sha256"),
                        },
                        "actual": {
                            "bytes": actual.get("bytes"),
                            "sha256": actual.get("sha256"),
                        },
                    }
                )
        verified_recordings.append(
            {
                "recording_id": recording_id,
                "artifacts": actual_artifacts,
                "recording_manifest_sha256": _recording_manifest_sha256(actual_artifacts),
            }
        )

    for name, expected in sorted(expected_generated_artifacts.items()):
        artifact_path = Path(str(expected.get("path") or ""))
        checked_artifact_count += 1
        if not artifact_path.exists():
            mismatches.append(
                {
                    "recording_id": None,
                    "artifact": name,
                    "path": str(artifact_path),
                    "reason": "missing_generated_artifact",
                    "expected": expected,
                    "actual": None,
                }
            )
            continue
        actual = _file_fingerprint(artifact_path)
        verified_generated_artifacts[name] = actual
        if actual.get("bytes") != expected.get("bytes") or actual.get("sha256") != expected.get("sha256"):
            mismatches.append(
                {
                    "recording_id": None,
                    "artifact": name,
                    "path": str(artifact_path),
                    "reason": "generated_fingerprint_mismatch",
                    "expected": {
                        "bytes": expected.get("bytes"),
                        "sha256": expected.get("sha256"),
                    },
                    "actual": {
                        "bytes": actual.get("bytes"),
                        "sha256": actual.get("sha256"),
                    },
                }
            )

    source_manifest_sha256 = _source_manifest_sha256(verified_recordings)
    expected_source_manifest_sha256 = report.get("source_manifest_sha256")
    if source_manifest_sha256 != expected_source_manifest_sha256:
        mismatches.append(
            {
                "recording_id": None,
                "artifact": "source_manifest",
                "path": str(path),
                "reason": "source_manifest_mismatch",
                "expected": expected_source_manifest_sha256,
                "actual": source_manifest_sha256,
            }
        )
    generated_manifest_sha256 = _artifact_manifest_sha256(verified_generated_artifacts)
    expected_generated_manifest_sha256 = report.get("generated_manifest_sha256")
    if generated_manifest_sha256 != expected_generated_manifest_sha256:
        mismatches.append(
            {
                "recording_id": None,
                "artifact": "generated_manifest",
                "path": str(path),
                "reason": "generated_manifest_mismatch",
                "expected": expected_generated_manifest_sha256,
                "actual": generated_manifest_sha256,
            }
        )

    return BatchManifestVerificationResult(
        report_path=path,
        passed=not mismatches,
        source_manifest_sha256=source_manifest_sha256,
        expected_source_manifest_sha256=expected_source_manifest_sha256,
        generated_manifest_sha256=generated_manifest_sha256,
        expected_generated_manifest_sha256=expected_generated_manifest_sha256,
        checked_artifact_count=checked_artifact_count,
        mismatches=mismatches,
    )


def _source_recordings(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    recordings: list[dict[str, Any]] = []
    for child in sorted(path for path in root.iterdir() if path.is_dir()):
        recording_id = child.name
        if recording_id.startswith("_") or recording_id.startswith("pavo-"):
            continue
        audio_path = child / f"{recording_id}.mp3"
        transcript_json_path = child / f"{recording_id}.transcript.json"
        transcript_markdown_path = child / "transcript.md"
        diarized_markdown_path = child / "transcript-diarized.md"
        attributed_markdown_path = child / "transcript-speaker-attributed.md"
        readme_path = child / "README.md"
        fetch_manifest_path = child / "fetch.json"
        artifact_paths = {
            "audio": audio_path,
            "transcript_json": transcript_json_path,
            "transcript_markdown": transcript_markdown_path,
            "diarized_markdown": diarized_markdown_path,
            "speaker_attributed_markdown": attributed_markdown_path,
            "readme": readme_path,
            "fetch_manifest": fetch_manifest_path,
        }
        if not any(
            path.exists()
            for path in artifact_paths.values()
        ):
            continue
        item = {
            "recording_id": recording_id,
            "directory": str(child),
            "audio_path": str(audio_path),
            "transcript_json_path": str(transcript_json_path),
            "transcript_markdown_path": str(transcript_markdown_path),
            "diarized_markdown_path": str(diarized_markdown_path),
            "speaker_attributed_markdown_path": str(attributed_markdown_path),
            "readme_path": str(readme_path),
            "fetch_manifest_path": str(fetch_manifest_path),
            "audio_present": audio_path.exists(),
            "transcript_json_present": transcript_json_path.exists(),
            "transcript_markdown_present": transcript_markdown_path.exists(),
            "diarized_markdown_present": diarized_markdown_path.exists(),
            "speaker_attributed_markdown_present": attributed_markdown_path.exists(),
            "readme_present": readme_path.exists(),
            "fetch_manifest_present": fetch_manifest_path.exists(),
        }
        item["missing"] = [
            name
            for name, present_key in [
                ("audio", "audio_present"),
                ("transcript_json", "transcript_json_present"),
                ("transcript_markdown", "transcript_markdown_present"),
                ("diarized_markdown", "diarized_markdown_present"),
                ("speaker_attributed_markdown", "speaker_attributed_markdown_present"),
                ("readme", "readme_present"),
                ("fetch_manifest", "fetch_manifest_present"),
            ]
            if not item[present_key]
        ]
        item["artifacts"] = {
            name: _file_fingerprint(path)
            for name, path in artifact_paths.items()
            if path.exists()
        }
        item["recording_manifest_sha256"] = _recording_manifest_sha256(item["artifacts"])
        recordings.append(item)
    return recordings


def _generated_artifacts(root: Path) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for name, relative_path in GENERATED_ARTIFACT_PATHS.items():
        path = root / relative_path
        if path.exists() and path.is_file():
            artifacts[name] = _file_fingerprint(path)
    return artifacts


def _required_generated_artifacts_present(artifacts: dict[str, dict[str, Any]]) -> bool:
    return all(name in artifacts for name in GENERATED_ARTIFACT_PATHS)


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text()) if path.exists() else None
    except (OSError, json.JSONDecodeError):
        return None


def _check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def _coverage_detail(recordings: list[dict[str, Any]], key: str) -> str:
    total = len(recordings)
    covered = sum(1 for item in recordings if item.get(key))
    return f"{covered}/{total}"


def _file_fingerprint(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def _recording_manifest_sha256(artifacts: dict[str, dict[str, Any]]) -> str | None:
    return _artifact_manifest_sha256(artifacts)


def _artifact_manifest_sha256(artifacts: dict[str, dict[str, Any]]) -> str | None:
    if not artifacts:
        return None
    manifest = [
        {
            "name": name,
            "bytes": payload.get("bytes"),
            "sha256": payload.get("sha256"),
        }
        for name, payload in sorted(artifacts.items())
    ]
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _source_manifest_sha256(recordings: list[dict[str, Any]]) -> str | None:
    if not recordings:
        return None
    manifest = [
        {
            "recording_id": item.get("recording_id"),
            "recording_manifest_sha256": item.get("recording_manifest_sha256"),
            "artifacts": [
                {
                    "name": name,
                    "bytes": payload.get("bytes"),
                    "sha256": payload.get("sha256"),
                }
                for name, payload in sorted((item.get("artifacts") or {}).items())
            ],
        }
        for item in recordings
    ]
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
