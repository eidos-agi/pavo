from __future__ import annotations

import hashlib
import json
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


@dataclass(frozen=True)
class BatchDoctorResult:
    batch_root: Path
    passed: bool
    complete: bool
    state: str
    source_recording_count: int
    source_recordings: list[dict[str, Any]]
    source_manifest_sha256: str | None
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
    checked_artifact_count: int
    mismatches: list[dict[str, Any]]

    def as_report(self) -> dict[str, Any]:
        return {
            "report_path": str(self.report_path),
            "passed": self.passed,
            "source_manifest_sha256": self.source_manifest_sha256,
            "expected_source_manifest_sha256": self.expected_source_manifest_sha256,
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

    source_count = len(recordings)
    source_missing = {
        item["recording_id"]: item["missing"]
        for item in recordings
        if item["missing"]
    }
    source_manifest_sha256 = _source_manifest_sha256(recordings)
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
        checks=checks,
        blockers=list(dict.fromkeys(blockers)),
        next_command=next_command,
        cluster_gate=cluster_gate,
    )


def verify_batch_manifest(report_path: Path | str) -> BatchManifestVerificationResult:
    path = Path(report_path)
    report = json.loads(path.read_text())
    source_recordings = report.get("source_recordings") or []
    verified_recordings: list[dict[str, Any]] = []
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

    return BatchManifestVerificationResult(
        report_path=path,
        passed=not mismatches,
        source_manifest_sha256=source_manifest_sha256,
        expected_source_manifest_sha256=expected_source_manifest_sha256,
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
