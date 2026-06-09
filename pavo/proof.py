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
