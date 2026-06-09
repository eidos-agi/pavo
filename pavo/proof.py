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
