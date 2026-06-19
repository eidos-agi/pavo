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
    manifest["artifact_manifest_sha256"] = _handoff_artifact_manifest_sha256(
        {
            name: {
                "path": payload.get("packed_relative_path"),
                "exists": True,
                "bytes": (payload.get("packed") or {}).get("bytes"),
                "sha256": (payload.get("packed") or {}).get("sha256"),
            }
            for name, payload in copied.items()
        }
    )
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
    manifest["artifact_manifest_sha256"] = _handoff_artifact_manifest_sha256(
        {
            name: {
                "path": payload.get("packed_relative_path"),
                "exists": True,
                "bytes": (payload.get("packed") or {}).get("bytes"),
                "sha256": (payload.get("packed") or {}).get("sha256"),
            }
            for name, payload in copied.items()
        }
    )
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
        "- Start with the artifact manifest entry named `proof_decision_board_html` for the human speaker decisions.",
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
        f"```bash\n{handoff.get('validate_command')}\n{handoff.get('finish_command')}\n{handoff.get('strict_proof_command')}\n```",
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
    rows_json = json.dumps(decisions, sort_keys=True)
    storage_key = json.dumps(f"pavo-decision-board:{proof_report_path}:{decision_slate_path}")
    cards = "\n".join(
        _render_batch_decision_card(row, rows_by_group.get(str(row.get("decision_group") or ""), []))
        for row in decisions
    )
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
    main {{ display:grid; grid-template-columns:minmax(0,1fr) 360px; gap:18px; padding:18px 24px 32px; }}
    .card {{ background:#fff; border:1px solid var(--line); border-radius:16px; box-shadow:0 8px 24px rgba(23,32,51,.06); margin-bottom:14px; overflow:hidden; }}
    .card-head {{ display:flex; gap:12px; align-items:flex-start; justify-content:space-between; padding:16px; border-bottom:1px solid var(--line); }}
    .card h2 {{ margin:0 0 6px; font-size:17px; }}
    .pill {{ display:inline-flex; align-items:center; border:1px solid var(--line); border-radius:999px; padding:3px 8px; font-size:12px; color:var(--muted); background:var(--soft); }}
    .decision {{ min-width:160px; display:grid; gap:8px; }}
    button {{ border:0; border-radius:10px; padding:9px 10px; color:#fff; font-weight:700; cursor:pointer; }}
    button.approve {{ background:var(--ok); }}
    button.reject {{ background:var(--bad); }}
    button.pending {{ background:var(--pending); }}
    button:focus {{ outline:3px solid rgba(49,87,213,.28); }}
    label {{ display:block; font-size:12px; color:var(--muted); margin-bottom:4px; }}
    input, textarea {{ width:100%; border:1px solid var(--line); border-radius:10px; padding:8px 10px; font:inherit; }}
    .body {{ padding:16px; }}
    .meta {{ display:flex; flex-wrap:wrap; gap:8px; margin:8px 0 12px; }}
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
      <div class="score"><strong>{supporting_count}</strong> supporting clips</div>
    </div>
  </header>
  <main>
    <section>
      {cards}
    </section>
    <aside>
      <h2>Finish Flow</h2>
      <p class="notice">Use the buttons to update the TSV below, then save it over the decision slate or pass it to <code>apply-decision-slate</code>. Keyboard: <strong>A</strong> approve, <strong>R</strong> reject, <strong>P</strong> pending, <strong>J/K</strong> move.</p>
      <div class="commands">pavo batch apply-decision-slate {escape(str(proof_report_path))} {escape(str(decision_slate_path))} --out {escape(str(proof_slate_path))}

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
    const headers = ["decision_group","decision","speaker","cluster_id","question","row_indices","clip_count","priority_tier","priority_score","priority_reason","acoustic_verdict","clip_paths","transcript_samples"];
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
      const pending = rows.filter(row => row.decision === "pending").length;
      const reviewed = rows.length - pending;
      document.getElementById("pending-count").textContent = String(pending);
      document.getElementById("reviewed-count").textContent = String(reviewed);
      document.getElementById("autosave-status").textContent = `Autosaved locally. ${{reviewed}}/${{rows.length}} decisions reviewed.`;
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
        summary: {{
          decisionCount: rows.length,
          pendingCount: rows.filter(row => row.decision === "pending").length,
          approvedCount: rows.filter(row => row.decision === "approved").length,
          rejectedCount: rows.filter(row => row.decision === "rejected").length
        }},
        rows,
        auditEvents,
        safetyBoundary: "This audit records human review-board edits. It is not a voiceprint and does not prove identity by itself."
      }};
    }}
    function downloadAudit() {{
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
      if (group && event.key.toLowerCase() === "a") {{ setDecision(group, "approved", "keyboard"); event.preventDefault(); }}
      if (group && event.key.toLowerCase() === "r") {{ setDecision(group, "rejected", "keyboard"); event.preventDefault(); }}
      if (group && event.key.toLowerCase() === "p") {{ setDecision(group, "pending", "keyboard"); event.preventDefault(); }}
    }});
    loadState();
    renderTsv();
  </script>
</body>
</html>
"""


def _render_batch_decision_card(decision: dict[str, str], proof_rows: list[dict[str, str]]) -> str:
    group = str(decision.get("decision_group") or "")
    current = str(decision.get("decision") or "pending").strip().lower() or "pending"
    speaker = str(decision.get("speaker") or "")
    samples = "\n".join(_render_batch_decision_sample(row) for row in proof_rows)
    if not samples:
        samples = '<div class="sample"><p class="notice">No supporting proof rows found for this decision group.</p></div>'
    return f"""<article class="card" data-group="{escape(group)}">
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
    {samples}
  </div>
</article>"""


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
