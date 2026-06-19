from __future__ import annotations

import hashlib
import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .review import gate_cluster_review


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
    _add_proof_slate_commands(
        review_packet,
        batch_root=root,
        proof_review_slate_path=proof_review_slate_path,
    )

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
        doctor_report_path=doctor_report_path,
        doctor_markdown_path=doctor_markdown_path,
        verification_markdown_path=verification_markdown_path,
        review_packet=review_packet,
    )
    proof_report_path.write_text(json.dumps(result.as_report(), indent=2, sort_keys=True) + "\n")
    proof_markdown_path.write_text(result.as_markdown())
    return result


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


def _review_packet_slate_tsv_lines(items: list[dict[str, Any]]) -> list[str]:
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
            ]
        )
    ]
    for item in items:
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
                ]
            )
        )
    return lines


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
