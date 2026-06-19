from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AUDIO_SUFFIXES = {".aac", ".m4a", ".mp3", ".wav"}
TRANSCRIPT_SUFFIXES = {".json", ".md", ".txt"}
TASK_VERBS = (
    "add",
    "ask",
    "build",
    "check",
    "create",
    "document",
    "download",
    "extract",
    "fix",
    "identify",
    "load",
    "map",
    "process",
    "prove",
    "publish",
    "reconcile",
    "review",
    "route",
    "run",
    "ship",
    "sync",
    "test",
    "update",
    "verify",
)


@dataclass(frozen=True)
class BriefOutputs:
    json_path: Path
    markdown_path: Path


@dataclass(frozen=True)
class ReviewClusterPlanOutputs:
    json_path: Path
    markdown_path: Path


@dataclass(frozen=True)
class ReviewClusterClipPacketOutputs:
    packet_path: Path
    clips_dir: Path
    extracted_clip_count: int
    missing_audio_count: int


@dataclass(frozen=True)
class BriefImprovementOutputs:
    json_path: Path
    markdown_path: Path


@dataclass(frozen=True)
class ReviewedHintsOverlayOutputs:
    overlay_path: Path
    segment_count: int
    speaker_count: int


def build_meeting_brief(root: Path, *, review_limit: int = 200, packet_limit: int = 25) -> dict[str, Any]:
    root = root.expanduser().resolve()
    audio_files = _find_files(root, AUDIO_SUFFIXES)
    transcript_json = _find_named(root, lambda path: path.suffix.lower() == ".json" and "transcript" in path.name.lower())
    transcript_text = _find_named(
        root,
        lambda path: path.suffix.lower() in {".md", ".txt"} and "transcript" in path.name.lower() and not path.name.startswith("pavo-"),
    )
    diarization_files = _find_named(root, lambda path: "diarization" in path.name.lower())
    speaker_files = _find_named(root, lambda path: "speaker" in path.name.lower() and path.suffix.lower() in TRANSCRIPT_SUFFIXES)
    named_speaker_files = _find_named(
        root,
        lambda path: "named-speaker" in path.name.lower() or "speaker-characterization" in path.name.lower(),
    )
    attribution_segments = _load_speaker_attribution_segments(root)
    named_evidence_segments = _load_named_evidence_segments(root)
    ensemble_segments = _ensemble_speaker_segments(attribution_segments, named_evidence_segments)
    diarization_segments = _load_diarization_segments(root)
    review_items, review_summary = _build_review_items(root, ensemble_segments, limit=review_limit)
    review_clusters = _build_review_clusters(ensemble_segments)
    packets = _extract_task_packets(root, limit=packet_limit)
    gates = _brief_gates(
        audio_files=audio_files,
        transcript_json=transcript_json,
        diarization_segments=diarization_segments,
        attribution_segments=attribution_segments,
        named_speaker_files=named_speaker_files,
    )
    verification_ok = all(gate["status"] == "pass" for gate in gates)
    readiness = _readiness_score(gates, review_items)
    state = "ready_to_route"
    if not verification_ok:
        state = "blocked_by_evidence"
    elif review_items:
        state = "needs_human_review"
    elif packets:
        state = "ready_for_task_routing"
    counts = {
        "audio_files": len(audio_files),
        "transcript_json_files": len(transcript_json),
        "transcript_text_files": len(transcript_text),
        "diarization_files": len(diarization_files),
        "diarized_segments": len(diarization_segments),
        "speaker_files": len(speaker_files),
        "attributed_segments": len(attribution_segments),
        "named_speaker_artifacts": len(named_speaker_files),
        "recordings_observed": len(_recording_ids(audio_files, transcript_json)),
    }
    return {
        "generated_at": _utc_now(),
        "root": str(root),
        "state": state,
        "readiness_score": readiness,
        "summary": _brief_summary(gates, review_summary["total_count"], packets),
        "counts": counts,
        "verification": {
            "ok": verification_ok,
            "gates": gates,
        },
        "speaker_ensemble": _speaker_ensemble_summary(attribution_segments, named_evidence_segments, ensemble_segments),
        "review": {
            "item_count": review_summary["sampled_count"],
            "total_count": review_summary["total_count"],
            "capped": review_summary["capped"],
            "by_type": dict(Counter(str(item.get("type") or "unknown") for item in review_items)),
            "by_reason": dict(Counter(str(item.get("reason") or "unknown") for item in review_items)),
            "top_items": review_items[:10],
            "clusters": review_clusters[:10],
        },
        "speaker_confidence": dict(Counter(str(segment.get("confidence") or "unknown") for segment in ensemble_segments)),
        "work_packets": {
            "packet_count": len(packets),
            "top_packets": packets[:10],
        },
        "next_actions": _rank_actions(str(root), gates, review_summary["total_count"], packets),
        "resume_commands": [
            f"pavo brief {root}",
            f"pavo review anchors status <review-sheet>",
            f"pavo review anchors gate <review-sheet>",
            f"pavo audio decompose <audio-path> --source-id <source-id>",
        ],
        "privacy": "Do not copy raw audio, voiceprints, embeddings, signed URLs, or unreviewed speaker evidence into external task systems.",
    }


def write_meeting_brief(brief: dict[str, Any], out_dir: Path) -> BriefOutputs:
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "pavo-meeting-brief.json"
    markdown_path = out_dir / "pavo-meeting-brief.md"
    json_path.write_text(json.dumps(brief, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_meeting_brief_markdown(brief), encoding="utf-8")
    return BriefOutputs(json_path=json_path, markdown_path=markdown_path)


def build_review_cluster_plan(
    brief: dict[str, Any],
    *,
    sample_limit_per_cluster: int = 5,
) -> dict[str, Any]:
    clusters = brief.get("review", {}).get("clusters") or []
    review_items = brief.get("review", {}).get("top_items") or []
    actions = [_cluster_review_action(cluster, review_items, sample_limit_per_cluster=sample_limit_per_cluster) for cluster in clusters]
    total_segments = sum(int(action["segment_count"]) for action in actions)
    total_duration = round(sum(float(action["duration_seconds"]) for action in actions), 2)
    return {
        "generated_at": _utc_now(),
        "root": brief.get("root"),
        "source_brief_state": brief.get("state"),
        "source_brief_readiness": brief.get("readiness_score"),
        "approval_boundary": {
            "mass_approval_allowed": False,
            "human_required": bool(actions),
            "rule": "Review clusters speed up sampling and enrollment, but they never approve speaker identity automatically.",
        },
        "summary": {
            "cluster_count": len(actions),
            "review_pressure_segments": total_segments,
            "review_pressure_duration_seconds": total_duration,
            "top_cluster": actions[0]["cluster_key"] if actions else None,
            "next_action": actions[0]["recommended_next_action"] if actions else "No speaker review clusters remain.",
        },
        "clusters": actions,
        "resume_commands": [
            f"pavo brief {brief.get('root')} --review-plan",
            "pavo review anchors init <clip-packet>",
            "pavo review anchors page <review-sheet>",
            "pavo review anchors import <review-sheet> <reviewed-export>",
            "pavo review anchors rerun-command <review-sheet> <pavo-decompose-manifest>",
        ],
    }


def write_review_cluster_plan(plan: dict[str, Any], out_dir: Path) -> ReviewClusterPlanOutputs:
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "pavo-review-cluster-plan.json"
    markdown_path = out_dir / "pavo-review-cluster-plan.md"
    json_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_review_cluster_plan_markdown(plan), encoding="utf-8")
    return ReviewClusterPlanOutputs(json_path=json_path, markdown_path=markdown_path)


def write_review_cluster_clip_packet(
    plan: dict[str, Any],
    out_dir: Path,
    *,
    clip_padding: float = 0.25,
    max_clips: int = 25,
) -> ReviewClusterClipPacketOutputs:
    out_dir = out_dir.expanduser().resolve()
    clips_dir = out_dir / "pavo-review-cluster-clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    root = Path(str(plan.get("root") or "")).expanduser()
    ffmpeg = shutil.which("ffmpeg")
    clips: list[dict[str, Any]] = []
    missing_audio = 0
    for cluster_index, cluster in enumerate(plan.get("clusters") or [], start=1):
        for sample_index, sample in enumerate(cluster.get("samples") or [], start=1):
            if len(clips) >= max_clips:
                break
            audio_path = _resolve_sample_audio_path(root, sample.get("recording_id"))
            start, end = _sample_window(sample, padding=clip_padding)
            clip_path = clips_dir / f"cluster-{cluster_index:02d}-sample-{sample_index:02d}.mp3"
            present = False
            if audio_path and ffmpeg and start is not None and end is not None:
                present = _extract_audio_clip(ffmpeg, audio_path, clip_path, start=start, end=end)
            if not present:
                missing_audio += 1
            clips.append(
                {
                    "index": len(clips) + 1,
                    "case": cluster.get("cluster_key"),
                    "recording_id": sample.get("recording_id"),
                    "target_speaker_label": cluster.get("speaker"),
                    "target_speaker_name": cluster.get("speaker"),
                    "start": sample.get("start"),
                    "end": sample.get("end"),
                    "duration": _window_duration(sample),
                    "text": sample.get("text"),
                    "confidence": sample.get("confidence"),
                    "method": sample.get("ensemble_source"),
                    "clip_path": str(clip_path),
                    "clip_size_bytes": clip_path.stat().st_size if clip_path.exists() else 0,
                    "present": present,
                    "suggested_speaker_correction": "",
                    "review_heading": str(cluster.get("cluster_key") or "Review cluster"),
                    "review_subtitle": str(cluster.get("review_mode") or "speaker review"),
                    "review_prompt": str(cluster.get("recommended_next_action") or "Listen and decide whether the speaker claim is usable."),
                    "expected_behavior": str(cluster.get("stop_condition") or "Human reviewer records a clear decision."),
                }
            )
        if len(clips) >= max_clips:
            break
    packet = {
        "passed": bool(clips and missing_audio == 0),
        "human_reviewed": False,
        "review_packet": str(out_dir / "pavo-review-cluster-plan.json"),
        "target_speaker_label": "PAVO_REVIEW_CLUSTER",
        "target_speaker_name": "Pavo review clusters",
        "review_title": "Pavo Review Clusters",
        "display_mode": "human_review",
        "requires_import_instruction": False,
        "requires_rerun_instruction": False,
        "review_labels": {
            "buttons": {"approved": "Usable", "rejected": "Problem", "pending": "Unsure"},
            "status": {"approved": "usable", "rejected": "problem", "pending": "unreviewed"},
        },
        "page_instructions": [
            "Listen to each cluster sample.",
            "Mark Usable only when the speaker evidence is clear enough to become an anchor or routing hint.",
            "Mark Problem when the speaker is wrong, mixed, noisy, or uncertain.",
            "This review does not mass-approve a cluster; it creates human evidence for the next rerun.",
        ],
        "candidate_count": len(clips),
        "clip_count": sum(1 for clip in clips if clip["present"]),
        "missing_audio_count": missing_audio,
        "clips_dir": str(clips_dir),
        "clips": clips,
        "next_required_proof": "human reviewer clears sampled cluster clips, then Pavo generates reviewed corrections or enrollment anchors.",
    }
    packet_path = out_dir / "pavo-review-cluster-clips.json"
    packet_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ReviewClusterClipPacketOutputs(
        packet_path=packet_path,
        clips_dir=clips_dir,
        extracted_clip_count=sum(1 for clip in clips if clip["present"]),
        missing_audio_count=missing_audio,
    )


def build_brief_improvement_report(
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    label: str | None = None,
) -> dict[str, Any]:
    baseline_metrics = _brief_metrics(baseline)
    current_metrics = _brief_metrics(current)
    review_delta = baseline_metrics["review_pressure_total"] - current_metrics["review_pressure_total"]
    routeable_delta = current_metrics["routeable_named_spans"] - baseline_metrics["routeable_named_spans"]
    score_delta = current_metrics["readiness_score"] - baseline_metrics["readiness_score"]
    baseline_clusters = _cluster_map(baseline)
    current_clusters = _cluster_map(current)
    cluster_deltas = []
    for key in sorted(set(baseline_clusters) | set(current_clusters)):
        before = baseline_clusters.get(key, {})
        after = current_clusters.get(key, {})
        cluster_deltas.append(
            {
                "cluster": key,
                "before_segments": int(before.get("segment_count") or 0),
                "after_segments": int(after.get("segment_count") or 0),
                "segment_delta": int(before.get("segment_count") or 0) - int(after.get("segment_count") or 0),
                "before_duration_seconds": float(before.get("duration_seconds") or 0.0),
                "after_duration_seconds": float(after.get("duration_seconds") or 0.0),
            }
        )
    cluster_deltas.sort(key=lambda item: (-abs(item["segment_delta"]), item["cluster"]))
    blockers = _improvement_blockers(baseline_metrics, current_metrics, review_delta, routeable_delta)
    passed = (
        current_metrics["verification_ok"]
        and review_delta >= 0
        and routeable_delta >= 0
        and current_metrics["recording_parity_status"] == "pass"
        and not blockers
    )
    return {
        "generated_at": _utc_now(),
        "label": label or "Pavo brief improvement",
        "passed": bool(passed),
        "baseline": baseline_metrics,
        "current": current_metrics,
        "deltas": {
            "review_pressure_reduction": review_delta,
            "review_pressure_reduction_percent": _percent_delta(review_delta, baseline_metrics["review_pressure_total"]),
            "routeable_named_span_gain": routeable_delta,
            "readiness_score_gain": score_delta,
        },
        "cluster_deltas": cluster_deltas,
        "blockers": blockers,
        "next_required_proof": "Run a reviewed-hint attribution pass, regenerate the brief, and require review pressure to fall without losing routeable named spans.",
    }


def write_brief_improvement_report(report: dict[str, Any], out_dir: Path) -> BriefImprovementOutputs:
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "pavo-brief-improvement-report.json"
    markdown_path = out_dir / "pavo-brief-improvement-report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_brief_improvement_markdown(report), encoding="utf-8")
    return BriefImprovementOutputs(json_path=json_path, markdown_path=markdown_path)


def write_reviewed_hints_named_evidence(
    hints_path: Path,
    batch_root: Path,
    *,
    out_path: Path | None = None,
) -> ReviewedHintsOverlayOutputs:
    payload = json.loads(hints_path.expanduser().read_text(encoding="utf-8"))
    segments = _reviewed_hint_segments(payload)
    target = out_path or batch_root.expanduser() / "_work" / "reviewed-hints.named-speaker-evidence.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    speakers = sorted({str(segment.get("speaker")) for segment in segments if segment.get("speaker")})
    overlay = {
        "source_hints": str(hints_path),
        "generated_at": _utc_now(),
        "passed": bool(segments),
        "segment_count": len(segments),
        "speaker_count": len(speakers),
        "speakers": speakers,
        "segments": segments,
        "privacy": "Human-reviewed hints are routing evidence; do not publish raw audio or voiceprints outside Pavo.",
    }
    target.write_text(json.dumps(overlay, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ReviewedHintsOverlayOutputs(
        overlay_path=target,
        segment_count=len(segments),
        speaker_count=len(speakers),
    )


def render_meeting_brief_markdown(brief: dict[str, Any]) -> str:
    counts = brief["counts"]
    lines = [
        "# Pavo Meeting Brief",
        "",
        f"Generated: {brief['generated_at']}",
        f"Root: `{brief['root']}`",
        f"State: `{brief['state']}`",
        f"Readiness score: **{brief['readiness_score']['score']}/100** ({brief['readiness_score']['grade']})",
        "",
        "## Summary",
        "",
        brief["summary"],
        "",
        "## Evidence Counts",
        "",
        f"- Audio files: {counts['audio_files']}",
        f"- Transcript JSON files: {counts['transcript_json_files']}",
        f"- Transcript text files: {counts['transcript_text_files']}",
        f"- Diarized segments: {counts['diarized_segments']}",
        f"- Attributed speaker segments: {counts['attributed_segments']}",
        f"- Named speaker artifacts: {counts['named_speaker_artifacts']}",
        f"- Sampled review items: {brief['review']['item_count']}",
        f"- Total review pressure: {brief['review'].get('total_count', brief['review']['item_count'])}",
        f"- Candidate work packets: {brief['work_packets']['packet_count']}",
        "",
        "## Gate Results",
        "",
    ]
    for gate in brief["verification"]["gates"]:
        lines.append(f"- {gate['name']}: `{gate['status']}` - {gate['message']}")
    ensemble = brief.get("speaker_ensemble", {})
    if ensemble:
        lines.extend(
            [
                "",
                "## Speaker Ensemble",
                "",
                f"- Raw attribution segments: {ensemble.get('raw_segment_count', 0)}",
                f"- Named-evidence segments: {ensemble.get('named_evidence_segment_count', 0)}",
                f"- Routeable named spans: {ensemble.get('routeable_named_segment_count', 0)}",
                f"- Routeable speaker counts: `{json.dumps(ensemble.get('routeable_speaker_counts', {}), sort_keys=True)}`",
                f"- Ensemble source counts: `{json.dumps(ensemble.get('source_counts', {}), sort_keys=True)}`",
            ]
        )
    lines.extend(["", "## Next Actions", ""])
    for index, action in enumerate(brief["next_actions"], start=1):
        lines.extend(
            [
                f"{index}. **{action['title']}**",
                f"   Priority: `{action['priority']}`",
                f"   Why: {action['why']}",
                f"   Command: `{action['command']}`",
                "",
            ]
        )
    if brief["work_packets"]["top_packets"]:
        lines.extend(["## Top Work Packets", ""])
        for packet in brief["work_packets"]["top_packets"]:
            lines.extend(
                [
                    f"- **{packet['title']}**",
                    f"  Source: `{packet['source']}:{packet['line']}`",
                    f"  Evidence: {packet['excerpt']}",
                ]
            )
        lines.append("")
    if brief["review"].get("clusters"):
        lines.extend(["## Review Clusters", ""])
        for cluster in brief["review"]["clusters"]:
            lines.append(
                f"- {cluster['speaker']} / {cluster['reason']}: {cluster['segment_count']} spans, {cluster['duration_seconds']:.1f}s across {cluster['recording_count']} recordings"
            )
        lines.append("")
    lines.extend(
        [
            "## Resume Commands",
            "",
            "```bash",
            *brief["resume_commands"],
            "```",
            "",
            "## Privacy Boundary",
            "",
            brief["privacy"],
            "",
        ]
    )
    return "\n".join(lines)


def render_brief_improvement_markdown(report: dict[str, Any]) -> str:
    baseline = report["baseline"]
    current = report["current"]
    deltas = report["deltas"]
    lines = [
        "# Pavo Brief Improvement Report",
        "",
        f"Generated: {report['generated_at']}",
        f"Label: {report['label']}",
        f"Passed: `{str(report['passed']).lower()}`",
        "",
        "## Scoreboard",
        "",
        f"- Review pressure: {baseline['review_pressure_total']} -> {current['review_pressure_total']} ({deltas['review_pressure_reduction']} fewer, {deltas['review_pressure_reduction_percent']}%)",
        f"- Routeable named spans: {baseline['routeable_named_spans']} -> {current['routeable_named_spans']} ({deltas['routeable_named_span_gain']} gain)",
        f"- Readiness score: {baseline['readiness_score']} -> {current['readiness_score']} ({deltas['readiness_score_gain']} gain)",
        f"- Recording parity: `{baseline['recording_parity_status']}` -> `{current['recording_parity_status']}`",
        "",
        "## Blockers",
        "",
    ]
    if report.get("blockers"):
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    else:
        lines.append("- None")
    lines.extend(["", "## Largest Cluster Changes", ""])
    for item in report.get("cluster_deltas", [])[:10]:
        lines.append(
            f"- {item['cluster']}: {item['before_segments']} -> {item['after_segments']} ({item['segment_delta']} fewer)"
        )
    lines.extend(["", "## Next Required Proof", "", report["next_required_proof"], ""])
    return "\n".join(lines)


def render_review_cluster_plan_markdown(plan: dict[str, Any]) -> str:
    summary = plan.get("summary") or {}
    boundary = plan.get("approval_boundary") or {}
    lines = [
        "# Pavo Review Cluster Plan",
        "",
        f"Generated: {plan.get('generated_at')}",
        f"Root: `{plan.get('root')}`",
        f"Source brief state: `{plan.get('source_brief_state')}`",
        "",
        "## Summary",
        "",
        f"- Cluster count: {summary.get('cluster_count', 0)}",
        f"- Review-pressure segments: {summary.get('review_pressure_segments', 0)}",
        f"- Review-pressure duration seconds: {summary.get('review_pressure_duration_seconds', 0)}",
        f"- Top cluster: `{summary.get('top_cluster') or 'none'}`",
        f"- Next action: {summary.get('next_action')}",
        "",
        "## Approval Boundary",
        "",
        f"- Mass approval allowed: `{str(boundary.get('mass_approval_allowed', False)).lower()}`",
        f"- Human required: `{str(boundary.get('human_required', False)).lower()}`",
        f"- Rule: {boundary.get('rule')}",
        "",
        "## Clusters",
        "",
    ]
    for index, cluster in enumerate(plan.get("clusters") or [], start=1):
        lines.extend(
            [
                f"### {index}. {cluster['cluster_key']}",
                "",
                f"- Approval state: `{cluster['approval_state']}`",
                f"- Review mode: `{cluster['review_mode']}`",
                f"- Segment count: {cluster['segment_count']}",
                f"- Duration seconds: {cluster['duration_seconds']}",
                f"- Recordings: {cluster['recording_count']}",
                f"- Recommended next action: {cluster['recommended_next_action']}",
                f"- Allowed actions: `{json.dumps(cluster['allowed_actions'])}`",
                f"- Stop condition: {cluster['stop_condition']}",
                "",
                "Sample evidence:",
            ]
        )
        for sample in cluster.get("samples") or []:
            lines.append(
                f"- `{sample.get('recording_id')}` {sample.get('start')} - {sample.get('end')}: {sample.get('text')}"
            )
        if not cluster.get("samples"):
            lines.append("- No sampled row evidence was available in the capped brief; rerun with a higher review limit if needed.")
        lines.append("")
    lines.extend(["## Resume Commands", "", "```bash", *plan.get("resume_commands", []), "```", ""])
    return "\n".join(lines)


def _find_files(root: Path, suffixes: set[str]) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in suffixes and not _skip_path(path))


def _find_named(root: Path, predicate: Any) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and predicate(path) and not _skip_path(path))


def _skip_path(path: Path) -> bool:
    generated_dirs = {
        ".git",
        ".venv",
        "__pycache__",
        "node_modules",
        "pavo-review-cluster-clips",
        "pavo-review-cluster-bundle",
        "pavo-reviewed-speaker-artifacts",
    }
    if any(part in generated_dirs for part in path.parts):
        return True
    return path.name.startswith("pavo-") and path.suffix.lower() in {".json", ".md", ".html"}


def _load_speaker_attribution_segments(root: Path) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for path in _find_named(root, lambda p: p.name in {"speaker-attribution.json", "best.labeled.attributed.json", "best.immune.attributed.json"}):
        payload = _read_json(path)
        candidate = payload.get("segments") if isinstance(payload, dict) else payload
        if isinstance(candidate, list):
            segments.extend(item for item in candidate if isinstance(item, dict))
    return segments


def _load_named_evidence_segments(root: Path) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for path in _find_named(root, lambda p: p.name == "named-speaker-evidence.json" or p.name.endswith(".named-speaker-evidence.json")):
        payload = _read_json(path)
        candidate = payload.get("segments") if isinstance(payload, dict) else None
        if isinstance(candidate, list):
            for item in candidate:
                if isinstance(item, dict):
                    enriched = dict(item)
                    enriched["_pavo_source"] = str(path)
                    segments.append(enriched)
    return segments


def _reviewed_hint_segments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    segments = []
    for hint in payload.get("hints") or []:
        speaker = str(hint.get("speaker") or "").strip()
        if not speaker:
            continue
        start = hint.get("start")
        end = hint.get("end")
        if start is None or end is None:
            continue
        segments.append(
            {
                "recording_id": hint.get("recording_id"),
                "source_id": hint.get("recording_id"),
                "start": start,
                "end": end,
                "speaker": speaker,
                "confidence": "manual_confirmed",
                "reason": "human_reviewed_speaker_hint",
                "text": hint.get("text"),
                "reviewer_note": hint.get("reviewer_note"),
                "clip_path": hint.get("clip_path"),
                "ensemble_source": "reviewed_speaker_hint",
            }
        )
    return segments


def _ensemble_speaker_segments(primary: list[dict[str, Any]], named: list[dict[str, Any]]) -> list[dict[str, Any]]:
    named_by_key = {_segment_key(segment): segment for segment in named}
    output: list[dict[str, Any]] = []
    for segment in primary:
        candidate = named_by_key.get(_segment_key(segment))
        output.append(_choose_segment(segment, candidate))
    primary_keys = {_segment_key(segment) for segment in primary}
    for segment in named:
        if _segment_key(segment) not in primary_keys:
            enriched = dict(segment)
            enriched["ensemble_source"] = "named_speaker_evidence_only"
            output.append(enriched)
    return output


def _choose_segment(primary: dict[str, Any], named: dict[str, Any] | None) -> dict[str, Any]:
    enriched = dict(primary)
    enriched["raw_speaker"] = primary.get("speaker")
    enriched["raw_confidence"] = primary.get("confidence")
    if named is None:
        enriched["ensemble_source"] = "speaker_attribution"
        return enriched
    named_speaker = str(named.get("speaker") or "")
    named_confidence = str(named.get("confidence") or "unknown")
    raw_confidence = str(primary.get("confidence") or "unknown")
    if _confidence_rank(named_confidence) > _confidence_rank(raw_confidence) or (
        _is_unknown_speaker(primary.get("speaker")) and not _is_unknown_speaker(named_speaker)
    ):
        enriched["speaker"] = named_speaker
        enriched["confidence"] = named_confidence
        enriched["reason"] = named.get("reason")
        enriched["ensemble_source"] = "named_speaker_evidence"
    else:
        enriched["ensemble_source"] = "speaker_attribution"
        if named.get("reason"):
            enriched["secondary_reason"] = named.get("reason")
    return enriched


def _segment_key(segment: dict[str, Any]) -> tuple[str, float | None, float | None]:
    return (
        str(segment.get("recording_id") or segment.get("source_id") or ""),
        _rounded_time(segment.get("start")),
        _rounded_time(segment.get("end")),
    )


def _rounded_time(value: Any) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _confidence_rank(value: str) -> int:
    return {"manual_confirmed": 4, "high": 3, "medium": 2, "low": 1}.get(value, 0)


def _load_diarization_segments(root: Path) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for path in _find_named(root, lambda p: p.name in {"diarization-segments.json", "diarization.json"}):
        payload = _read_json(path)
        candidate = payload.get("segments") if isinstance(payload, dict) else payload
        if isinstance(candidate, list):
            segments.extend(item for item in candidate if isinstance(item, dict))
    return segments


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _build_review_items(root: Path, segments: list[dict[str, Any]], *, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    items: list[dict[str, Any]] = []
    source = root / "_work" / "speaker-attribution.json"
    total = 0
    for segment in segments:
        confidence = str(segment.get("confidence") or "unknown")
        speaker = str(segment.get("speaker") or segment.get("speaker_name") or "UNKNOWN")
        if _needs_speaker_review(speaker, confidence):
            total += 1
            if len(items) >= limit:
                continue
            items.append(
                {
                    "type": "speaker_identity",
                    "state": "review_needed",
                    "reason": _review_reason(speaker, confidence),
                    "recording_id": segment.get("recording_id") or segment.get("source_id"),
                    "start": segment.get("start"),
                    "end": segment.get("end"),
                    "speaker": speaker,
                    "confidence": confidence,
                    "text": str(segment.get("text") or "")[:500],
                    "source": str(segment.get("_pavo_source") or source),
                    "ensemble_source": str(segment.get("ensemble_source") or "unknown"),
                    "raw_speaker": segment.get("raw_speaker"),
                    "raw_confidence": segment.get("raw_confidence"),
                    "allowed_actions": ["confirm_speaker", "assign_speaker", "mark_unassigned", "ignore"],
                }
            )
    return items, {"total_count": total, "sampled_count": len(items), "capped": total > len(items)}


def _needs_speaker_review(speaker: str, confidence: str) -> bool:
    if _is_unknown_speaker(speaker):
        return True
    return confidence not in {"high", "manual_confirmed", "medium"}


def _is_unknown_speaker(value: Any) -> bool:
    lower = str(value or "").lower()
    return lower.startswith("unknown") or lower.startswith("unattributed") or lower.endswith("-mentioned")


def _review_reason(speaker: str, confidence: str) -> str:
    if _is_unknown_speaker(speaker):
        return "unattributed_speaker"
    return f"{confidence}_confidence_named_speaker"


def _build_review_clusters(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters: dict[tuple[str, str], dict[str, Any]] = {}
    for segment in segments:
        confidence = str(segment.get("confidence") or "unknown")
        speaker = str(segment.get("speaker") or "UNKNOWN")
        if not _needs_speaker_review(speaker, confidence):
            continue
        reason = _review_reason(speaker, confidence)
        key = (speaker, reason)
        cluster = clusters.setdefault(
            key,
            {
                "speaker": speaker,
                "reason": reason,
                "segment_count": 0,
                "duration_seconds": 0.0,
                "recordings": set(),
                "sample_text": [],
                "samples": [],
            },
        )
        cluster["segment_count"] += 1
        cluster["duration_seconds"] += _duration(segment)
        recording_id = segment.get("recording_id") or segment.get("source_id")
        if recording_id:
            cluster["recordings"].add(str(recording_id))
        text = str(segment.get("text") or "").strip()
        if text and len(cluster["sample_text"]) < 3:
            cluster["sample_text"].append(text[:180])
        if len(cluster["samples"]) < 5:
            cluster["samples"].append(
                {
                    "recording_id": recording_id,
                    "start": segment.get("start"),
                    "end": segment.get("end"),
                    "confidence": confidence,
                    "ensemble_source": segment.get("ensemble_source"),
                    "text": text[:500],
                }
            )
    results = []
    for cluster in clusters.values():
        results.append(
            {
                "speaker": cluster["speaker"],
                "reason": cluster["reason"],
                "segment_count": cluster["segment_count"],
                "duration_seconds": round(cluster["duration_seconds"], 2),
                "recording_count": len(cluster["recordings"]),
                "sample_text": cluster["sample_text"],
                "samples": cluster["samples"],
            }
        )
    return sorted(results, key=lambda item: (-item["segment_count"], item["speaker"]))


def _cluster_review_action(
    cluster: dict[str, Any],
    review_items: list[dict[str, Any]],
    *,
    sample_limit_per_cluster: int,
) -> dict[str, Any]:
    speaker = str(cluster.get("speaker") or "UNKNOWN")
    reason = str(cluster.get("reason") or "unknown")
    cluster_key = f"{speaker} / {reason}"
    samples = [
        item
        for item in review_items
        if str(item.get("speaker") or "UNKNOWN") == speaker and str(item.get("reason") or "unknown") == reason
    ][:sample_limit_per_cluster]
    if not samples:
        samples = list(cluster.get("samples") or [])[:sample_limit_per_cluster]
    if reason == "unattributed_speaker":
        review_mode = "identify_or_enroll_speaker"
        recommended = "Sample this cluster across recordings, identify the person if possible, then create speaker anchors before rerun."
        allowed_actions = ["sample_audio", "identify_speaker", "create_anchor_review_sheet", "rerun_with_reviewed_corrections"]
        stop_condition = "At least one human-confirmed speaker identity or an explicit unassigned decision exists for this cluster."
    else:
        review_mode = "confirm_named_speaker_confidence"
        recommended = "Sample the highest-impact spans, approve only clean clips, and rerun attribution with reviewed corrections."
        allowed_actions = ["sample_audio", "approve_clean_anchor_clips", "reject_uncertain_clips", "rerun_with_reviewed_corrections"]
        stop_condition = "Reviewed clips are all approved or rejected, and approved corrections can be exported by Pavo."
    return {
        "cluster_key": cluster_key,
        "speaker": speaker,
        "reason": reason,
        "approval_state": "human_required",
        "review_mode": review_mode,
        "segment_count": int(cluster.get("segment_count") or 0),
        "duration_seconds": float(cluster.get("duration_seconds") or 0.0),
        "recording_count": int(cluster.get("recording_count") or 0),
        "sample_text": cluster.get("sample_text") or [],
        "samples": [
            {
                "recording_id": item.get("recording_id"),
                "start": item.get("start"),
                "end": item.get("end"),
                "confidence": item.get("confidence"),
                "ensemble_source": item.get("ensemble_source"),
                "text": item.get("text"),
            }
            for item in samples
        ],
        "recommended_next_action": recommended,
        "allowed_actions": allowed_actions,
        "forbidden_actions": ["mass_approve_cluster", "publish_raw_audio", "publish_voiceprints", "write_external_tasks_with_unreviewed_speaker_claims"],
        "stop_condition": stop_condition,
    }


def _resolve_sample_audio_path(root: Path, recording_id: Any) -> Path | None:
    if not recording_id:
        return None
    recording = str(recording_id)
    candidates = [
        root / recording / f"{recording}.mp3",
        root / recording / f"{recording}.m4a",
        root / recording / f"{recording}.wav",
        root / recording / f"{recording}.aac",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    for candidate in root.rglob(f"{recording}.*"):
        if candidate.suffix.lower() in AUDIO_SUFFIXES and candidate.is_file():
            return candidate
    return None


def _sample_window(sample: dict[str, Any], *, padding: float) -> tuple[float | None, float | None]:
    try:
        start = max(0.0, float(sample.get("start")) - padding)
        end = float(sample.get("end")) + padding
    except (TypeError, ValueError):
        return None, None
    if end <= start:
        return None, None
    return start, end


def _window_duration(sample: dict[str, Any]) -> float:
    try:
        return round(max(0.0, float(sample.get("end")) - float(sample.get("start"))), 2)
    except (TypeError, ValueError):
        return 0.0


def _extract_audio_clip(ffmpeg: str, source: Path, target: Path, *, start: float, end: float) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        str(source),
        "-vn",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "4",
        str(target),
    ]
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError:
        return target.exists() and target.stat().st_size > 0
    return target.exists() and target.stat().st_size > 0


def _duration(segment: dict[str, Any]) -> float:
    try:
        return max(0.0, float(segment.get("end")) - float(segment.get("start")))
    except (TypeError, ValueError):
        return 0.0


def _speaker_ensemble_summary(
    primary: list[dict[str, Any]],
    named: list[dict[str, Any]],
    ensemble: list[dict[str, Any]],
) -> dict[str, Any]:
    routeable = [
        segment
        for segment in ensemble
        if not _needs_speaker_review(str(segment.get("speaker") or ""), str(segment.get("confidence") or "unknown"))
    ]
    return {
        "raw_segment_count": len(primary),
        "named_evidence_segment_count": len(named),
        "ensemble_segment_count": len(ensemble),
        "source_counts": dict(Counter(str(segment.get("ensemble_source") or "unknown") for segment in ensemble)),
        "routeable_named_segment_count": len(routeable),
        "routeable_speaker_counts": dict(Counter(str(segment.get("speaker") or "unknown") for segment in routeable)),
    }


def _brief_metrics(brief: dict[str, Any]) -> dict[str, Any]:
    review = brief.get("review") or {}
    ensemble = brief.get("speaker_ensemble") or {}
    readiness = brief.get("readiness_score") or {}
    counts = brief.get("counts") or {}
    gates = {gate.get("name"): gate for gate in (brief.get("verification") or {}).get("gates", [])}
    return {
        "root": brief.get("root"),
        "state": brief.get("state"),
        "verification_ok": bool((brief.get("verification") or {}).get("ok")),
        "readiness_score": int(readiness.get("score") or 0),
        "readiness_grade": readiness.get("grade"),
        "review_pressure_total": int(review.get("total_count") or review.get("item_count") or 0),
        "sampled_review_items": int(review.get("item_count") or 0),
        "routeable_named_spans": int(ensemble.get("routeable_named_segment_count") or 0),
        "routeable_speaker_counts": ensemble.get("routeable_speaker_counts") or {},
        "audio_files": int(counts.get("audio_files") or 0),
        "transcript_json_files": int(counts.get("transcript_json_files") or 0),
        "recording_parity_status": (gates.get("recording_parity") or {}).get("status", "unknown"),
    }


def _cluster_map(brief: dict[str, Any]) -> dict[str, dict[str, Any]]:
    clusters = (brief.get("review") or {}).get("clusters") or []
    return {f"{cluster.get('speaker')} / {cluster.get('reason')}": cluster for cluster in clusters}


def _percent_delta(delta: int, baseline: int) -> float:
    if not baseline:
        return 0.0
    return round((delta / baseline) * 100, 2)


def _improvement_blockers(
    baseline: dict[str, Any],
    current: dict[str, Any],
    review_delta: int,
    routeable_delta: int,
) -> list[str]:
    blockers = []
    if current["recording_parity_status"] != "pass":
        blockers.append("current brief recording parity is not passing")
    if not current["verification_ok"]:
        blockers.append("current brief verification is not passing")
    if review_delta < 0:
        blockers.append("review pressure increased")
    if routeable_delta < 0:
        blockers.append("routeable named spans decreased")
    if baseline["root"] == current["root"] and review_delta == 0 and routeable_delta == 0:
        blockers.append("baseline and current metrics are unchanged")
    return blockers


def _extract_task_packets(root: Path, *, limit: int) -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    seen: set[str] = set()
    candidates = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".md", ".txt"}
        and path.stat().st_size < 2_000_000
        and not path.name.startswith("pavo-")
        and "speaker-characterization" not in path.name.lower()
        and "named-speaker-evidence" not in path.name.lower()
        and "diarization-summary" not in path.name.lower()
    ]
    for path in sorted(candidates):
        for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            if not _is_task_line(line):
                continue
            fingerprint = _task_fingerprint(line)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            packets.append(
                {
                    "title": _packet_title(line),
                    "source": str(path),
                    "line": line_number,
                    "excerpt": line.strip()[:500],
                    "confidence": "candidate",
                    "state": "review_needed",
                    "acceptance_criteria": [
                        "Source evidence is cited.",
                        "Owner/team/project are confirmed before external writes.",
                        "Sensitive audio or speaker evidence is not copied into external task systems.",
                    ],
                }
            )
            if len(packets) >= limit:
                return packets
    return packets


def _brief_gates(
    *,
    audio_files: list[Path],
    transcript_json: list[Path],
    diarization_segments: list[dict[str, Any]],
    attribution_segments: list[dict[str, Any]],
    named_speaker_files: list[Path],
) -> list[dict[str, str]]:
    return [
        _gate("source_truth", bool(audio_files), "original audio files are present"),
        _gate("local_transcripts", bool(transcript_json), "local transcript JSON files are present"),
        _gate("diarization", bool(diarization_segments), "diarized segments are present"),
        _gate("speaker_attribution", bool(attribution_segments), "speaker attribution segments are present"),
        _gate("named_speaker_evidence", bool(named_speaker_files), "named speaker evidence artifacts are present"),
        _gate("recording_parity", len(audio_files) == len(transcript_json), "audio and transcript counts match"),
    ]


def _readiness_score(gates: list[dict[str, str]], review_items: list[dict[str, Any]]) -> dict[str, Any]:
    weights = {
        "source_truth": 20,
        "local_transcripts": 20,
        "diarization": 15,
        "speaker_attribution": 15,
        "named_speaker_evidence": 10,
        "recording_parity": 10,
        "review_pressure": 10,
    }
    score = 0
    components: list[dict[str, Any]] = []
    by_name = {gate["name"]: gate for gate in gates}
    for name, possible in weights.items():
        if name == "review_pressure":
            points = _review_pressure_points(review_items, possible)
            status = "pass" if points == possible else "warn"
        else:
            passed = by_name.get(name, {}).get("status") == "pass"
            points = possible if passed else 0
            status = "pass" if passed else "fail"
        score += points
        components.append({"name": name, "status": status, "points": points, "possible": possible})
    score = min(100, score)
    verification_ok = all(component["status"] != "fail" for component in components if component["name"] != "review_pressure")
    return {
        "score": score,
        "grade": _score_grade(score, has_review_items=bool(review_items), verification_ok=verification_ok),
        "components": components,
    }


def _review_pressure_points(review_items: list[dict[str, Any]], possible: int) -> int:
    if not review_items:
        return possible
    speaker_items = sum(1 for item in review_items if item.get("type") == "speaker_identity")
    return max(0, possible - min(possible, 2 + speaker_items if speaker_items else len(review_items)))


def _score_grade(score: int, *, has_review_items: bool, verification_ok: bool) -> str:
    if not verification_ok:
        return "blocked"
    if has_review_items and score >= 75:
        return "usable_with_review"
    if score >= 90:
        return "ship_ready"
    if score >= 75:
        return "usable_with_review"
    if score >= 55:
        return "needs_cleanup"
    return "not_ready"


def _brief_summary(gates: list[dict[str, str]], review_count: int, packets: list[dict[str, Any]]) -> str:
    failed = [gate["name"] for gate in gates if gate["status"] != "pass"]
    if failed:
        return f"This batch is not ready to route because {', '.join(failed)} still needs proof. Pavo found {review_count} review-pressure spans and {len(packets)} candidate work packets."
    if review_count:
        return f"This batch has source evidence and transcripts, but {review_count} review-pressure spans should be cleared or clustered before routing work outside Pavo."
    if packets:
        return f"This batch is evidence-ready and has {len(packets)} candidate work packets ready for human-approved routing."
    return "This batch is evidence-ready and has no obvious review queue or task packet pressure."


def _rank_actions(root: str, gates: list[dict[str, str]], review_count: int, packets: list[dict[str, Any]]) -> list[dict[str, str]]:
    failed = {gate["name"] for gate in gates if gate["status"] != "pass"}
    actions: list[dict[str, str]] = []
    if "source_truth" in failed:
        actions.append({"priority": "P0", "title": "Recover or attach original audio", "why": "Original audio is Pavo's source truth.", "command": f"pavo plaud download <recording-id> --out-dir {root}"})
    if "local_transcripts" in failed:
        actions.append({"priority": "P0", "title": "Generate local transcripts", "why": "Task extraction and speaker review are weak without local transcript JSON.", "command": "pavo transcribe <recording-id>"})
    if failed & {"diarization", "speaker_attribution", "named_speaker_evidence"}:
        actions.append({"priority": "P1", "title": "Run or repair speaker evidence", "why": "Speaker-aware tasks should not route until speaker evidence is present.", "command": "pavo audio decompose <audio-path> --source-id <source-id>"})
    if review_count:
        actions.append({"priority": "P1", "title": "Clear the review clusters", "why": f"{review_count} review-pressure spans remain; use the clusters to approve by evidence bucket instead of reading every row.", "command": f"pavo brief {root}"})
    if packets:
        actions.append({"priority": "P2", "title": "Turn candidate work packets into approved tasks", "why": f"{len(packets)} candidate packets were found; external writes remain approval-gated.", "command": f"pavo brief {root}"})
    if not actions:
        actions.append({"priority": "P3", "title": "Archive the clean proof bundle", "why": "No blocking evidence gaps or candidate tasks were found.", "command": f"pavo brief {root}"})
    return actions


def _gate(name: str, ok: bool, message: str) -> dict[str, str]:
    return {"name": name, "status": "pass" if ok else "fail", "message": message}


def _recording_ids(audio_files: list[Path], transcript_json: list[Path]) -> set[str]:
    return {path.stem.replace(".transcript", "") for path in [*audio_files, *transcript_json]}


def _is_task_line(line: str) -> bool:
    text = _task_text(line)
    lower = text.lower()
    if lower.startswith("|"):
        return False
    if not lower or len(lower.split()) < 3 or len(lower) > 320:
        return False
    if lower.startswith(("i was like", "what do ", "do you ", "did i ", "can i ")):
        return False
    if "todo" in lower or "follow up" in lower:
        return True
    verbs = "|".join(TASK_VERBS)
    imperative = rf"^({verbs})\b(?!\?)"
    need_to_action = rf"\b(we|i|you|they|pavo|codex|team)\s+(need|needs|should|must|have to)\s+to\s+({verbs})\b"
    passive_need = rf"\b(needs|should be|must be|has to be)\s+({verbs})(ed|d)?\b"
    return any(re.search(pattern, lower) for pattern in (imperative, need_to_action, passive_need))


def _task_fingerprint(line: str) -> str:
    text = _task_text(line)
    text = re.sub(r"\b(s\d+|daniel|unknown office speaker)\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return " ".join(text.split())[:180]


def _task_text(line: str) -> str:
    text = re.sub(r"^[-*]\s+", "", line.strip())
    text = re.sub(r"^`?\d\d:\d\d:\d\d`?\s*[-–]\s*`?\d\d:\d\d:\d\d`?\s*", "", text)
    text = re.sub(r"^\*\*[^*]+\*\*:\s*", "", text)
    return text.strip()


def _packet_title(line: str) -> str:
    cleaned = " ".join(_task_text(line).split())
    return cleaned[:90] or "Review meeting follow-up"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
