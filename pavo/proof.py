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


def plaud_decompose_recording_report(source_dir: Path | str) -> dict[str, Any]:
    root = Path(source_dir)
    pavo_manifest_path = root / "pavo-decompose-manifest.json"
    pavo_manifest = json.loads(pavo_manifest_path.read_text()) if pavo_manifest_path.exists() else {}
    eidos_manifest_path = Path(
        pavo_manifest.get("eidos_transcribe_manifest", root / "decompose-transcribe" / "decompose-transcribe.manifest.json")
    )
    eidos_manifest = json.loads(eidos_manifest_path.read_text()) if eidos_manifest_path.exists() else {}
    signatures_manifest_text = eidos_manifest.get("speaker_signatures_manifest")
    speaker_manifest_path = root / "decompose-transcribe" / "process-call" / "speaker-pipeline" / "speaker-pipeline.manifest.json"
    if signatures_manifest_text:
        candidate_speaker_manifest = Path(signatures_manifest_text).parent.parent / "speaker-pipeline.manifest.json"
        if candidate_speaker_manifest.exists():
            speaker_manifest_path = candidate_speaker_manifest
    speaker_manifest = json.loads(speaker_manifest_path.read_text()) if speaker_manifest_path.exists() else {}
    signatures_path = Path(signatures_manifest_text) if signatures_manifest_text else root / "__missing_speaker_signatures__.json"
    signatures = json.loads(signatures_path.read_text()) if signatures_path.exists() else {}
    separation_manifest_text = eidos_manifest.get("overlap_separation_manifest")
    separation_manifest_path = Path(separation_manifest_text) if separation_manifest_text else root / "__missing_separation__.json"
    separation_manifest = json.loads(separation_manifest_path.read_text()) if separation_manifest_path.exists() else {}
    stem_asr_manifest_text = eidos_manifest.get("stem_asr_manifest")
    stem_asr_manifest_path = Path(stem_asr_manifest_text) if stem_asr_manifest_text else root / "__missing_stem_asr__.json"
    stem_asr_manifest = json.loads(stem_asr_manifest_path.read_text()) if stem_asr_manifest_path.exists() else {}
    decomposed_text = eidos_manifest.get("decomposed_transcript_json")
    decomposed_path = Path(decomposed_text) if decomposed_text else root / "__missing_decomposed_transcript__.json"
    decomposed = json.loads(decomposed_path.read_text()) if decomposed_path.exists() else {}

    region_reports = []
    for path_text in separation_manifest.get("regions", []):
        path = Path(path_text)
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        stem_reports = payload.get("stem_reports", {})
        region_reports.append(
            {
                "path": str(path),
                "accepted": payload.get("accepted") is True,
                "start": payload.get("region", {}).get("start"),
                "end": payload.get("region", {}).get("end"),
                "stem_count": len(stem_reports),
                "wrong_rates": {slug: stem.get("wrong_rate") for slug, stem in stem_reports.items()},
                "margins": {slug: stem.get("whole_clip", {}).get("margin") for slug, stem in stem_reports.items()},
            }
        )
    diagnostic_segments = decomposed.get("segments", [])
    trusted_segments = [segment for segment in diagnostic_segments if segment.get("trusted") is True]
    audio_path_text = pavo_manifest.get("audio_path")
    stages = {
        "download": bool(audio_path_text) and Path(audio_path_text).exists(),
        "voiceprints": signatures_path.exists() and len(signatures.get("speakers", [])) >= 2,
        "speaker_change_detection": bool(speaker_manifest.get("speaker_immune_summary", {}).get("segments")),
        "decomposition": eidos_manifest_path.exists() and bool(eidos_manifest.get("overlap_separation_manifest")),
        "stem_asr": stem_asr_manifest_path.exists() and stem_asr_manifest.get("transcribed_stem_count", 0) > 0,
        "manifests": pavo_manifest_path.exists()
        and eidos_manifest_path.exists()
        and speaker_manifest_path.exists()
        and signatures_path.exists()
        and separation_manifest_path.exists()
        and stem_asr_manifest_path.exists(),
    }
    accepted_regions = [region for region in region_reports if region["accepted"]]
    passed = all(stages.values()) and int(speaker_manifest.get("num_speakers") or 0) >= 2
    return {
        "passed": passed,
        "accepted_stems_passed": bool(accepted_regions),
        "source_id": pavo_manifest.get("source_id"),
        "audio_sha256": pavo_manifest.get("audio_sha256"),
        "num_speakers": speaker_manifest.get("num_speakers"),
        "best_method": speaker_manifest.get("best_method"),
        "speaker_signature_count": len(signatures.get("speakers", [])),
        "signature_sample_counts": {
            speaker.get("slug"): speaker.get("sample_count") for speaker in signatures.get("speakers", [])
        },
        "immune_counts": speaker_manifest.get("speaker_immune_summary", {}).get("immune_counts", {}),
        "separated_region_count": eidos_manifest.get("separated_region_count", 0),
        "region_count": len(region_reports),
        "accepted_region_count": len(accepted_regions),
        "transcribed_stem_count": stem_asr_manifest.get("transcribed_stem_count", 0),
        "diagnostic_segment_count": len(diagnostic_segments),
        "trusted_segment_count": len(trusted_segments),
        "stages": stages,
        "regions": region_reports,
        "pavo_manifest": str(pavo_manifest_path),
        "eidos_manifest": str(eidos_manifest_path),
        "speaker_manifest": str(speaker_manifest_path),
        "signatures_manifest": str(signatures_path),
        "separation_manifest": str(separation_manifest_path),
        "stem_asr_manifest": str(stem_asr_manifest_path),
        "decomposed_transcript_json": str(decomposed_path),
        "caveat": "Pipeline proof passes, but all separated regions are currently rejected; accepted real-media stems remain unproven.",
    }


def conan_old_sitcom_report(separation_manifest_path: Path | str, stem_asr_manifest_path: Path | str) -> dict[str, Any]:
    separation_manifest = json.loads(Path(separation_manifest_path).read_text())
    stem_asr_manifest = json.loads(Path(stem_asr_manifest_path).read_text())
    region_paths = [Path(path) for path in separation_manifest.get("regions", [])]
    region_reports = [json.loads(path.read_text()) for path in region_paths if path.exists()]
    decomposed_path = Path(stem_asr_manifest.get("decomposed_transcript_json", ""))
    decomposed = json.loads(decomposed_path.read_text()) if decomposed_path.exists() else {}
    diagnostic_segments = decomposed.get("segments", [])
    trusted_segments = [segment for segment in diagnostic_segments if segment.get("trusted") is True]
    rejected_segments = [segment for segment in diagnostic_segments if segment.get("trusted") is False]
    accepted_regions = [report for report in region_reports if report.get("accepted") is True]
    stem_reports = [
        {
            "speaker_slug": slug,
            "target": stem.get("target"),
            "whole_clip_best": stem.get("whole_clip", {}).get("best"),
            "margin": stem.get("whole_clip", {}).get("margin"),
            "wrong_rate": stem.get("wrong_rate"),
            "path": stem.get("path"),
        }
        for report in region_reports
        for slug, stem in report.get("stem_reports", {}).items()
    ]
    overlap_detected = bool(
        separation_manifest.get("candidate_count", 0) > 0
        and region_reports
        and any("rolling_mixed" in str(report.get("region", {}).get("immune", "")) for report in region_reports)
    )
    diagnostic_available = bool(
        stem_asr_manifest.get("include_rejected") is True
        and stem_asr_manifest.get("transcribed_stem_count", 0) >= len(stem_reports)
        and rejected_segments
        and not trusted_segments
    )
    passed = bool(overlap_detected and region_reports and not accepted_regions and diagnostic_available)
    return {
        "passed": passed,
        "overlap_detected": overlap_detected,
        "candidate_count": separation_manifest.get("candidate_count", 0),
        "region_count": len(region_reports),
        "accepted_region_count": len(accepted_regions),
        "all_regions_rejected": bool(region_reports and not accepted_regions),
        "stem_count": len(stem_reports),
        "stem_reports": stem_reports,
        "diagnostic_available": diagnostic_available,
        "include_rejected": stem_asr_manifest.get("include_rejected"),
        "transcribed_stem_count": stem_asr_manifest.get("transcribed_stem_count", 0),
        "diagnostic_segment_count": len(diagnostic_segments),
        "trusted_segment_count": len(trusted_segments),
        "rejected_segment_count": len(rejected_segments),
        "merge_policy": decomposed.get("merge_policy"),
        "separation_manifest": str(separation_manifest_path),
        "stem_asr_manifest": str(stem_asr_manifest_path),
        "decomposed_transcript_json": str(decomposed_path),
    }


def real_media_accepted_stems_audit(cache_root: Path | str) -> dict[str, Any]:
    root = Path(cache_root)
    separation_reports = []
    for path in sorted(root.rglob("analysis.json")):
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if "stem_reports" not in payload:
            continue
        stem_reports = payload.get("stem_reports", {})
        separation_reports.append(
            {
                "path": str(path),
                "accepted": payload.get("accepted") is True,
                "region_start": payload.get("region", {}).get("start"),
                "region_end": payload.get("region", {}).get("end"),
                "stem_count": len(stem_reports),
                "wrong_rates": {slug: stem.get("wrong_rate") for slug, stem in stem_reports.items()},
                "margins": {slug: stem.get("whole_clip", {}).get("margin") for slug, stem in stem_reports.items()},
            }
        )

    accepted = [report for report in separation_reports if report["accepted"]]
    return {
        "passed": bool(accepted),
        "cache_root": str(root),
        "separation_report_count": len(separation_reports),
        "accepted_report_count": len(accepted),
        "rejected_report_count": len(separation_reports) - len(accepted),
        "accepted_reports": accepted,
        "reports": separation_reports,
        "next_required_proof": "at least one real-media overlap separation report with accepted: true and trusted stem ASR evidence",
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
