from __future__ import annotations

import json
import re
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
    diarization_segments = _load_diarization_segments(root)
    review_items = _build_review_items(root, attribution_segments, limit=review_limit)
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
        "summary": _brief_summary(gates, review_items, packets),
        "counts": counts,
        "verification": {
            "ok": verification_ok,
            "gates": gates,
        },
        "review": {
            "item_count": len(review_items),
            "by_type": dict(Counter(str(item.get("type") or "unknown") for item in review_items)),
            "by_reason": dict(Counter(str(item.get("reason") or "unknown") for item in review_items)),
            "top_items": review_items[:10],
        },
        "speaker_confidence": dict(Counter(str(segment.get("confidence") or "unknown") for segment in attribution_segments)),
        "work_packets": {
            "packet_count": len(packets),
            "top_packets": packets[:10],
        },
        "next_actions": _rank_actions(str(root), gates, review_items, packets),
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
        f"- Review items: {brief['review']['item_count']}",
        f"- Candidate work packets: {brief['work_packets']['packet_count']}",
        "",
        "## Gate Results",
        "",
    ]
    for gate in brief["verification"]["gates"]:
        lines.append(f"- {gate['name']}: `{gate['status']}` - {gate['message']}")
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


def _find_files(root: Path, suffixes: set[str]) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in suffixes)


def _find_named(root: Path, predicate: Any) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and predicate(path) and not _skip_path(path))


def _skip_path(path: Path) -> bool:
    return any(part in {".git", ".venv", "__pycache__", "node_modules"} for part in path.parts)


def _load_speaker_attribution_segments(root: Path) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for path in _find_named(root, lambda p: p.name in {"speaker-attribution.json", "best.labeled.attributed.json", "best.immune.attributed.json"}):
        payload = _read_json(path)
        candidate = payload.get("segments") if isinstance(payload, dict) else payload
        if isinstance(candidate, list):
            segments.extend(item for item in candidate if isinstance(item, dict))
    return segments


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


def _build_review_items(root: Path, segments: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    source = root / "_work" / "speaker-attribution.json"
    for segment in segments:
        confidence = str(segment.get("confidence") or "unknown")
        speaker = str(segment.get("speaker") or segment.get("speaker_name") or "UNKNOWN")
        if confidence not in {"high", "manual_confirmed"} or speaker.lower().startswith("unknown"):
            items.append(
                {
                    "type": "speaker_identity",
                    "state": "review_needed",
                    "reason": "low_or_unknown_speaker_confidence",
                    "recording_id": segment.get("recording_id") or segment.get("source_id"),
                    "start": segment.get("start"),
                    "end": segment.get("end"),
                    "speaker": speaker,
                    "confidence": confidence,
                    "text": str(segment.get("text") or "")[:500],
                    "source": str(source),
                    "allowed_actions": ["confirm_speaker", "assign_speaker", "mark_unassigned", "ignore"],
                }
            )
            if len(items) >= limit:
                break
    return items


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


def _brief_summary(gates: list[dict[str, str]], review_items: list[dict[str, Any]], packets: list[dict[str, Any]]) -> str:
    failed = [gate["name"] for gate in gates if gate["status"] != "pass"]
    if failed:
        return f"This batch is not ready to route because {', '.join(failed)} still needs proof. Pavo found {len(review_items)} review items and {len(packets)} candidate work packets."
    if review_items:
        return f"This batch has source evidence and transcripts, but {len(review_items)} review items should be cleared before routing work outside Pavo."
    if packets:
        return f"This batch is evidence-ready and has {len(packets)} candidate work packets ready for human-approved routing."
    return "This batch is evidence-ready and has no obvious review queue or task packet pressure."


def _rank_actions(root: str, gates: list[dict[str, str]], review_items: list[dict[str, Any]], packets: list[dict[str, Any]]) -> list[dict[str, str]]:
    failed = {gate["name"] for gate in gates if gate["status"] != "pass"}
    actions: list[dict[str, str]] = []
    if "source_truth" in failed:
        actions.append({"priority": "P0", "title": "Recover or attach original audio", "why": "Original audio is Pavo's source truth.", "command": f"pavo plaud download <recording-id> --out-dir {root}"})
    if "local_transcripts" in failed:
        actions.append({"priority": "P0", "title": "Generate local transcripts", "why": "Task extraction and speaker review are weak without local transcript JSON.", "command": "pavo transcribe <recording-id>"})
    if failed & {"diarization", "speaker_attribution", "named_speaker_evidence"}:
        actions.append({"priority": "P1", "title": "Run or repair speaker evidence", "why": "Speaker-aware tasks should not route until speaker evidence is present.", "command": "pavo audio decompose <audio-path> --source-id <source-id>"})
    if review_items:
        actions.append({"priority": "P1", "title": "Clear the review queue", "why": f"{len(review_items)} review items are waiting.", "command": "pavo review anchors status <review-sheet>"})
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
