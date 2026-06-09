from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def conan_experience_comparison_report(path: Path | str) -> dict[str, Any]:
    comparison = json.loads(Path(path).read_text())
    case = _find_case(comparison, "Opening prompt")
    pavo_rows = case.get("pavo", [])
    phrase_row = _find_phrase_row(pavo_rows, "what was that experience like")
    rolling = phrase_row.get("rolling_fingerprint", {}) if phrase_row else {}
    pavo_named_speakers = comparison.get("pavo_named_speakers", [])
    youtube_text = case.get("youtube", "")
    youtube_has_phrase = "what was that" in normalize_text(youtube_text)
    pavo_has_named_speaker = phrase_row and phrase_row.get("speaker") in pavo_named_speakers
    pavo_preserves_speaker_evidence = bool(
        phrase_row
        and rolling.get("status") == "mixed"
        and rolling.get("runs")
        and len(rolling.get("runs", [])) >= 2
    )
    passed = bool(
        not comparison.get("youtube_has_speaker_names", True)
        and pavo_named_speakers
        and youtube_has_phrase
        and pavo_has_named_speaker
        and pavo_preserves_speaker_evidence
    )
    return {
        "passed": passed,
        "case_label": case.get("label"),
        "youtube_has_speaker_names": comparison.get("youtube_has_speaker_names"),
        "youtube_has_phrase": youtube_has_phrase,
        "pavo_named_speaker_count": len(pavo_named_speakers),
        "phrase_found": phrase_row is not None,
        "phrase_speaker": phrase_row.get("speaker") if phrase_row else None,
        "pavo_has_named_speaker": bool(pavo_has_named_speaker),
        "rolling_status": rolling.get("status"),
        "rolling_run_count": len(rolling.get("runs", [])),
        "pavo_preserves_speaker_evidence": pavo_preserves_speaker_evidence,
    }


def nz_slang_comparison_report(
    path: Path | str,
    *,
    required_improvements: list[str] | None = None,
) -> dict[str, Any]:
    comparison = json.loads(Path(path).read_text())
    required = required_improvements or ["box of birds", "sweet as", "bottle of milk"]
    term_presence = comparison.get("term_presence", {})
    improved = []
    missing = []
    for term in required:
        presence = term_presence.get(term, {})
        if presence.get("pavo") is True and presence.get("youtube") is False:
            improved.append(term)
        else:
            missing.append(
                {
                    "term": term,
                    "youtube": presence.get("youtube"),
                    "pavo": presence.get("pavo"),
                }
            )

    passed = bool(
        not comparison.get("youtube_has_speaker_names", True)
        and int(comparison.get("speaker_count") or 0) >= 2
        and not missing
    )
    return {
        "passed": passed,
        "title": comparison.get("title"),
        "channel": comparison.get("channel"),
        "youtube_has_speaker_names": comparison.get("youtube_has_speaker_names"),
        "pavo_best_method": comparison.get("pavo_best_method"),
        "speaker_count": comparison.get("speaker_count"),
        "required_improvements": required,
        "improved_terms": improved,
        "missing_improvements": missing,
        "improved_term_count": len(improved),
    }


def conan_demo_video_report(
    root: Path | str,
    *,
    required_sections: list[str] | None = None,
) -> dict[str, Any]:
    demo_root = Path(root)
    required = required_sections or [
        "02-youtube.mp4",
        "03-pavo-captioned.mp4",
        "04-comparison-slide.mp4",
        "05-ai-explainer.mp4",
        "06-overlap-original.mp4",
        "07-mixed-stem.mp4",
        "08-conan-stem.mp4",
        "09-kaitlin-stem.mp4",
        "10-takeaway.mp4",
    ]
    final_video = demo_root / "pavo-conan-demo.mp4"
    comparison = demo_root / "comparison.json"
    narration = demo_root / "narration.txt"
    normalized_dir = demo_root / "normalized"
    existing_sections = []
    missing_sections = []
    for name in required:
        path = normalized_dir / name
        if path.exists() and path.stat().st_size > 0:
            existing_sections.append(name)
        else:
            missing_sections.append(name)

    comparison_valid = False
    if comparison.exists():
        payload = json.loads(comparison.read_text())
        comparison_valid = bool(payload.get("cases")) and not payload.get("youtube_has_speaker_names", True)

    narration_present = narration.exists() and bool(narration.read_text().strip())
    final_video_present = final_video.exists() and final_video.stat().st_size > 0
    passed = bool(final_video_present and comparison_valid and narration_present and not missing_sections)
    return {
        "passed": passed,
        "final_video": str(final_video),
        "final_video_present": final_video_present,
        "final_video_size_bytes": final_video.stat().st_size if final_video.exists() else 0,
        "comparison_json": str(comparison),
        "comparison_valid": comparison_valid,
        "narration_present": narration_present,
        "required_sections": required,
        "existing_sections": existing_sections,
        "missing_sections": missing_sections,
        "section_count": len(existing_sections),
    }


def plaud_real_recording_report(recording_dir: Path | str) -> dict[str, Any]:
    root = Path(recording_dir)
    pavo_manifest_path = root / "pavo-transcribe-manifest.json"
    pavo_manifest = json.loads(pavo_manifest_path.read_text()) if pavo_manifest_path.exists() else {}
    audio_path = Path(pavo_manifest.get("audio_path", root / "audio.mp3"))
    eidos_manifest_path = Path(pavo_manifest.get("eidos_transcribe_manifest", root / "transcribe" / "manifest.json"))
    eidos_manifest = json.loads(eidos_manifest_path.read_text()) if eidos_manifest_path.exists() else {}
    ensemble_path = Path(eidos_manifest.get("ensemble", root / "transcribe" / "ensembled-contextual-transcript.md"))
    raw_outputs = eidos_manifest.get("raw_outputs", {})
    raw_output_paths = [Path(path) for path in raw_outputs.values()]
    required_transcribe_paths = [pavo_manifest_path, audio_path, eidos_manifest_path, ensemble_path, *raw_output_paths]
    missing_transcribe_paths = [str(path) for path in required_transcribe_paths if not path.exists()]

    decompose_manifest = root / "pavo-decompose-manifest.json"
    eidos_decompose_manifest = root / "decompose-transcribe" / "decompose-transcribe.manifest.json"
    speaker_manifest = root / "decompose-transcribe" / "speaker-pipeline" / "speaker-pipeline.manifest.json"
    stem_asr_manifest = root / "decompose-transcribe" / "stem-asr" / "stem-asr.manifest.json"
    transcribe_complete = bool(
        pavo_manifest.get("recording_id")
        and pavo_manifest.get("audio_sha256")
        and pavo_manifest.get("engines")
        and eidos_manifest.get("method")
        and not missing_transcribe_paths
    )
    stages = {
        "download": audio_path.exists() and audio_path.stat().st_size > 0,
        "transcribe": transcribe_complete,
        "voiceprints": speaker_manifest.exists(),
        "speaker_change_detection": speaker_manifest.exists(),
        "decomposition": decompose_manifest.exists() and eidos_decompose_manifest.exists(),
        "stem_asr": stem_asr_manifest.exists(),
    }
    missing_stages = [name for name, present in stages.items() if not present]
    full_item_24_passed = all(stages.values())
    return {
        "passed": full_item_24_passed,
        "partial": transcribe_complete and not full_item_24_passed,
        "recording_id": pavo_manifest.get("recording_id"),
        "audio_sha256": pavo_manifest.get("audio_sha256"),
        "audio_path": str(audio_path),
        "audio_size_bytes": audio_path.stat().st_size if audio_path.exists() else 0,
        "engines": pavo_manifest.get("engines", []),
        "context_terms": pavo_manifest.get("context_terms", []),
        "pavo_manifest": str(pavo_manifest_path),
        "eidos_transcribe_manifest": str(eidos_manifest_path),
        "ensemble": str(ensemble_path),
        "raw_output_count": len(raw_output_paths),
        "missing_transcribe_paths": missing_transcribe_paths,
        "stages": stages,
        "missing_stages": missing_stages,
        "next_required_proof": "real multi-speaker Plaud recording with voiceprints, speaker changes, decomposition, stem ASR, and manifests",
    }


def _find_case(comparison: dict[str, Any], label: str) -> dict[str, Any]:
    for case in comparison.get("cases", []):
        if case.get("label") == label:
            return case
    raise ValueError(f"comparison case not found: {label}")


def _find_phrase_row(rows: list[dict[str, Any]], phrase: str) -> dict[str, Any] | None:
    needle = normalize_text(phrase)
    for row in rows:
        if needle in normalize_text(str(row.get("text", ""))):
            return row
    return None


def normalize_text(text: str) -> str:
    return " ".join(text.lower().replace("?", "").replace("!", "").replace(".", "").split())
