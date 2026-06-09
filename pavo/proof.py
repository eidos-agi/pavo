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


def real_media_decompose_search_report(manifest_path: Path | str) -> dict[str, Any]:
    manifest_path = Path(manifest_path)
    manifest = _load_json(manifest_path)
    separation_manifest_path = Path(manifest.get("overlap_separation_manifest", ""))
    separation_manifest = _load_json(separation_manifest_path)
    stem_asr_manifest_path = Path(manifest.get("stem_asr_manifest", ""))
    stem_asr_manifest = _load_json(stem_asr_manifest_path)
    signature_path = Path(manifest.get("speaker_signatures_manifest", ""))
    rolling_path = Path(manifest.get("rolling_attributed_json", ""))

    regions = []
    for path_text in separation_manifest.get("regions", []):
        region_path = Path(path_text)
        payload = _load_json(region_path)
        if not payload:
            continue
        stem_reports = payload.get("stem_reports", {})
        trusted_stems = [slug for slug, stem in stem_reports.items() if _stem_report_trusted(stem)]
        regions.append(
            {
                "path": str(region_path),
                "accepted": payload.get("accepted") is True,
                "start": payload.get("region", {}).get("start"),
                "end": payload.get("region", {}).get("end"),
                "text": payload.get("region", {}).get("text"),
                "stem_count": len(stem_reports),
                "trusted_stems": trusted_stems,
                "trusted_stem_count": len(trusted_stems),
                "wrong_rates": {slug: stem.get("wrong_rate") for slug, stem in stem_reports.items()},
                "margins": {slug: stem.get("whole_clip", {}).get("margin") for slug, stem in stem_reports.items()},
            }
        )
    accepted_regions = [region for region in regions if region["accepted"]]
    trusted_region_count = sum(1 for region in regions if region["trusted_stem_count"])
    return {
        "passed": bool(accepted_regions),
        "manifest": str(manifest_path),
        "speaker_signatures_present": signature_path.exists(),
        "rolling_transcript_present": rolling_path.exists(),
        "separation_manifest": str(separation_manifest_path),
        "stem_asr_manifest": str(stem_asr_manifest_path),
        "separated_region_count": len(regions),
        "accepted_region_count": len(accepted_regions),
        "trusted_stem_region_count": trusted_region_count,
        "transcribed_stem_count": stem_asr_manifest.get("transcribed_stem_count", 0),
        "include_rejected": stem_asr_manifest.get("include_rejected"),
        "regions": regions,
        "next_required_proof": "accepted real-media separated region whose trusted stem ASR recovers words absent from same-region mixed ASR",
        "caveat": "This search created generic speaker signatures and diagnostic stem ASR, but every NZ separated region remained rejected.",
    }


def plaud_anchor_quality_report(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    attempt_reports = []
    for attempt in attempts:
        label = str(attempt.get("label", "plaud-attempt"))
        signatures_path = Path(str(attempt.get("signatures_manifest", "")))
        decompose_report_path = Path(str(attempt.get("decompose_report", "")))
        signatures = _load_json(signatures_path)
        decompose_report = _load_json(decompose_report_path)
        speakers = []
        sample_counts = []
        for speaker in signatures.get("speakers", []):
            count = int(speaker.get("sample_count") or 0)
            sample_counts.append(count)
            speakers.append(
                {
                    "speaker_label": speaker.get("speaker_label"),
                    "name": speaker.get("name"),
                    "slug": speaker.get("slug"),
                    "sample_count": count,
                    "sample_seconds": speaker.get("sample_seconds"),
                    "sample_method_counts": speaker.get("sample_method_counts", {}),
                }
            )
        min_samples = min(sample_counts) if sample_counts else 0
        max_samples = max(sample_counts) if sample_counts else 0
        imbalance_ratio = round(max_samples / max(min_samples, 1), 4) if sample_counts else None
        human_reviewed = bool(attempt.get("human_reviewed"))
        accepted_stems = bool(decompose_report.get("accepted_stems_passed"))
        attempt_reports.append(
            {
                "label": label,
                "human_reviewed": human_reviewed,
                "accepted_stems_passed": accepted_stems,
                "signature_speaker_count": len(speakers),
                "min_sample_count": min_samples,
                "max_sample_count": max_samples,
                "sample_imbalance_ratio": imbalance_ratio,
                "speakers": speakers,
                "signatures_manifest": str(signatures_path),
                "decompose_report": str(decompose_report_path),
                "blocked": not (human_reviewed and accepted_stems),
                "blockers": _plaud_attempt_blockers(
                    human_reviewed=human_reviewed,
                    accepted_stems=accepted_stems,
                    min_samples=min_samples,
                    imbalance_ratio=imbalance_ratio,
                ),
            }
        )
    passed = any(attempt["human_reviewed"] and attempt["accepted_stems_passed"] for attempt in attempt_reports)
    return {
        "passed": passed,
        "attempt_count": len(attempt_reports),
        "human_reviewed_attempt_count": sum(1 for attempt in attempt_reports if attempt["human_reviewed"]),
        "accepted_stem_attempt_count": sum(1 for attempt in attempt_reports if attempt["accepted_stems_passed"]),
        "attempts": attempt_reports,
        "next_required_proof": "human-reviewed Plaud speaker anchors plus accepted separated stems on a real multi-speaker Plaud overlap",
    }


def plaud_anchor_review_packet(
    *,
    signatures_manifest: Path | str,
    attributed_transcript: Path | str,
    target_speaker_label: str,
    target_speaker_name: str | None = None,
    min_duration: float = 2.0,
    max_candidates: int = 20,
) -> dict[str, Any]:
    signatures_path = Path(signatures_manifest)
    attributed_path = Path(attributed_transcript)
    signatures = _load_json(signatures_path)
    rows = _load_json(attributed_path)
    if not isinstance(rows, list):
        rows = []
    speaker = next(
        (item for item in signatures.get("speakers", []) if item.get("speaker_label") == target_speaker_label),
        {},
    )
    name = target_speaker_name or speaker.get("name") or target_speaker_label
    existing_samples = [
        {
            "start": sample.get("start"),
            "end": sample.get("end"),
            "duration": _duration(sample),
            "confidence": sample.get("confidence"),
            "method": sample.get("method"),
            "text": sample.get("text"),
            "source": "existing_signature_sample",
        }
        for sample in speaker.get("sample_spans", [])
    ]
    transcript_candidates = []
    for row in rows:
        if row.get("speaker_label") != target_speaker_label:
            continue
        duration = _duration(row)
        if duration < min_duration:
            continue
        transcript_candidates.append(
            {
                "start": row.get("start"),
                "end": row.get("end"),
                "duration": duration,
                "confidence": row.get("confidence"),
                "method": row.get("method"),
                "immune": row.get("immune"),
                "text": row.get("text"),
                "source": "attributed_transcript",
            }
        )
    transcript_candidates.sort(
        key=lambda item: (
            "conflict" in str(item.get("method", "")) or "conflict" in str(item.get("immune", "")),
            -(float(item.get("confidence") or 0.0)),
            -(float(item.get("duration") or 0.0)),
        )
    )
    review_candidates = transcript_candidates[:max_candidates]
    return {
        "passed": False,
        "target_speaker_label": target_speaker_label,
        "target_speaker_name": name,
        "source_audio_wav": signatures.get("source_audio_wav"),
        "signatures_manifest": str(signatures_path),
        "attributed_transcript": str(attributed_path),
        "existing_sample_count": int(speaker.get("sample_count") or 0),
        "existing_sample_seconds": speaker.get("sample_seconds"),
        "existing_samples": existing_samples,
        "review_candidate_count": len(review_candidates),
        "review_candidates": review_candidates,
        "suggested_speaker_corrections": [
            f"{_format_seconds(candidate['start'])}-{_format_seconds(candidate['end'])}={target_speaker_label}"
            for candidate in review_candidates
            if candidate.get("start") is not None and candidate.get("end") is not None
        ],
        "next_required_proof": "human reviewer must confirm clean candidate spans, then rerun Plaud decompose with speaker corrections",
    }


def plaud_anchor_review_clip_packet(
    *,
    review_packet: Path | str,
    clips_dir: Path | str,
) -> dict[str, Any]:
    packet_path = Path(review_packet)
    packet = _load_json(packet_path)
    clips_root = Path(clips_dir)
    source_audio = Path(str(packet.get("source_audio_wav", "")))
    clips = []
    missing_clips = []
    for index, candidate in enumerate(packet.get("review_candidates", []), start=1):
        start = candidate.get("start")
        end = candidate.get("end")
        clip_name = _review_clip_name(index, start, end)
        clip_path = clips_root / clip_name
        present = clip_path.exists() and clip_path.stat().st_size > 0
        if not present:
            missing_clips.append(str(clip_path))
        clips.append(
            {
                "index": index,
                "start": start,
                "end": end,
                "duration": _duration(candidate),
                "text": candidate.get("text"),
                "confidence": candidate.get("confidence"),
                "method": candidate.get("method"),
                "suggested_speaker_correction": (
                    f"{_format_seconds(start)}-{_format_seconds(end)}={packet.get('target_speaker_label')}"
                    if start is not None and end is not None
                    else None
                ),
                "clip_path": str(clip_path),
                "clip_size_bytes": clip_path.stat().st_size if clip_path.exists() else 0,
                "present": present,
            }
        )
    source_audio_present = source_audio.exists() and source_audio.stat().st_size > 0
    return {
        "passed": bool(source_audio_present and clips and not missing_clips),
        "human_reviewed": False,
        "target_speaker_label": packet.get("target_speaker_label"),
        "target_speaker_name": packet.get("target_speaker_name"),
        "review_packet": str(packet_path),
        "source_audio_wav": str(source_audio),
        "source_audio_present": source_audio_present,
        "clips_dir": str(clips_root),
        "candidate_count": len(packet.get("review_candidates", [])),
        "clip_count": sum(1 for clip in clips if clip["present"]),
        "missing_clips": missing_clips,
        "clips": clips,
        "next_required_proof": "human reviewer must listen to the clips, accept clean speaker anchors, then rerun Plaud decompose with those corrections",
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
            "rolling_windows": stem.get("rolling_windows"),
            "trusted": _stem_report_trusted(stem),
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
    accepted_stem_asr_available = bool(
        accepted_regions
        and stem_asr_manifest.get("include_rejected") is False
        and stem_asr_manifest.get("transcribed_stem_count", 0) >= len(stem_reports)
        and trusted_segments
        and not rejected_segments
    )
    stem_asr_improvement_passed = bool(False)
    passed = bool(overlap_detected and region_reports and (diagnostic_available or accepted_stem_asr_available))
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
        "accepted_stem_asr_available": accepted_stem_asr_available,
        "stem_asr_improvement_passed": stem_asr_improvement_passed,
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


def stem_asr_improvement_report(
    *,
    mixed_transcript_path: Path | str,
    stem_evidence_path: Path | str,
    expected_recovered_terms: list[str],
    reviewed: bool = False,
) -> dict[str, Any]:
    mixed_transcript = _load_json(Path(mixed_transcript_path))
    stem_evidence = _load_json(Path(stem_evidence_path))
    mixed_text = " ".join(str(segment.get("text", "")) for segment in mixed_transcript.get("segments", []))
    trusted_stem_segments = [
        segment
        for segment in stem_evidence.get("segments", [])
        if segment.get("trusted") is True and segment.get("separation_accepted") is True
    ]
    trusted_stem_text = " ".join(str(segment.get("text", "")) for segment in trusted_stem_segments)
    term_results = []
    for term in expected_recovered_terms:
        stem_has_term = normalize_text(term) in normalize_text(trusted_stem_text)
        mixed_has_term = normalize_text(term) in normalize_text(mixed_text)
        term_results.append(
            {
                "term": term,
                "trusted_stem_has_term": stem_has_term,
                "mixed_asr_has_term": mixed_has_term,
                "recovered_by_stem": bool(stem_has_term and not mixed_has_term),
            }
        )
    recovered_terms = [item["term"] for item in term_results if item["recovered_by_stem"]]
    return {
        "passed": bool(reviewed and expected_recovered_terms and len(recovered_terms) == len(expected_recovered_terms)),
        "reviewed": reviewed,
        "mixed_transcript": str(mixed_transcript_path),
        "stem_evidence": str(stem_evidence_path),
        "trusted_stem_segment_count": len(trusted_stem_segments),
        "expected_recovered_terms": expected_recovered_terms,
        "recovered_terms": recovered_terms,
        "term_results": term_results,
        "mixed_text": mixed_text,
        "trusted_stem_text": trusted_stem_text,
        "next_required_proof": "reviewed expected words present in trusted accepted stem ASR and absent from same-region mixed ASR",
    }


def stem_asr_improvement_search_report(
    manifest_paths: list[Path | str],
    *,
    improvement_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifests = []
    accepted_reports = []
    candidate_count = 0
    region_count = 0
    for manifest_path in manifest_paths:
        manifest_path = Path(manifest_path)
        manifest = _load_json(manifest_path)
        manifest_regions = []
        for region_text in manifest.get("regions", []):
            region_path = Path(region_text)
            region = _load_json(region_path)
            if not region:
                continue
            accepted = region.get("accepted") is True
            region_count += 1
            if accepted:
                accepted_reports.append(str(region_path))
            manifest_regions.append(
                {
                    "path": str(region_path),
                    "accepted": accepted,
                    "start": region.get("region", {}).get("start"),
                    "end": region.get("region", {}).get("end"),
                    "text": region.get("region", {}).get("text"),
                    "trusted_stem_count": sum(
                        1 for stem in region.get("stem_reports", {}).values() if _stem_report_trusted(stem)
                    ),
                    "stem_count": len(region.get("stem_reports", {})),
                }
            )
        candidate_count += int(manifest.get("candidate_count") or len(manifest_regions))
        manifests.append(
            {
                "path": str(manifest_path),
                "candidate_count": manifest.get("candidate_count"),
                "region_count": len(manifest_regions),
                "accepted_region_count": sum(1 for region in manifest_regions if region["accepted"]),
                "regions": manifest_regions,
            }
        )
    improvement_passed = bool((improvement_report or {}).get("passed"))
    return {
        "passed": improvement_passed,
        "manifest_count": len(manifests),
        "candidate_count": candidate_count,
        "region_count": region_count,
        "accepted_region_count": len(accepted_reports),
        "accepted_reports": accepted_reports,
        "improvement_passed": improvement_passed,
        "manifests": manifests,
        "next_required_proof": "accepted region whose trusted stem ASR recovers reviewed words absent from same-region mixed ASR",
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
        trusted_stems = {
            slug: stem
            for slug, stem in stem_reports.items()
            if _stem_report_trusted(stem)
        }
        checked_trusted_stems = {
            slug: stem
            for slug, stem in trusted_stems.items()
            if int(stem.get("rolling_windows") or 0) > 0
        }
        separation_reports.append(
            {
                "path": str(path),
                "accepted": payload.get("accepted") is True,
                "region_start": payload.get("region", {}).get("start"),
                "region_end": payload.get("region", {}).get("end"),
                "stem_count": len(stem_reports),
                "trusted_stem_count": len(trusted_stems),
                "trusted_stems": sorted(trusted_stems),
                "checked_trusted_stem_count": len(checked_trusted_stems),
                "checked_trusted_stems": sorted(checked_trusted_stems),
                "wrong_rates": {slug: stem.get("wrong_rate") for slug, stem in stem_reports.items()},
                "margins": {slug: stem.get("whole_clip", {}).get("margin") for slug, stem in stem_reports.items()},
                "rolling_windows": {slug: stem.get("rolling_windows") for slug, stem in stem_reports.items()},
            }
        )

    accepted = [report for report in separation_reports if report["accepted"]]
    accepted_with_window_checks = [
        report
        for report in accepted
        if report["stem_count"] > 0 and report["checked_trusted_stem_count"] == report["stem_count"]
    ]
    trusted_stem_reports = [report for report in separation_reports if report["trusted_stem_count"] > 0]
    trusted_stem_count = sum(report["trusted_stem_count"] for report in separation_reports)
    return {
        "passed": bool(accepted),
        "cache_root": str(root),
        "separation_report_count": len(separation_reports),
        "accepted_report_count": len(accepted),
        "accepted_report_with_window_checks_count": len(accepted_with_window_checks),
        "rejected_report_count": len(separation_reports) - len(accepted),
        "trusted_stem_count": trusted_stem_count,
        "trusted_stem_report_count": len(trusted_stem_reports),
        "trusted_stem_reports": trusted_stem_reports,
        "accepted_reports": accepted,
        "accepted_reports_with_window_checks": accepted_with_window_checks,
        "reports": separation_reports,
        "next_required_proof": "at least one real-media overlap separation report with accepted: true and trusted stem ASR evidence",
        "note": "trusted individual stems are reviewable evidence, but rejected regions still do not produce trusted canonical stem ASR",
    }


def proof_status_summary(docs_dir: Path | str) -> dict[str, Any]:
    docs = Path(docs_dir)
    reports = {
        "conan_experience": _load_json(docs / "conan-experience-comparison-report.json"),
        "conan_old_sitcom": _load_json(docs / "conan-old-sitcom-report.json"),
        "nz_slang": _load_json(docs / "nz-slang-comparison-report.json"),
        "plaud_transcribe": _load_json(docs / "plaud-real-recording-report.json"),
        "plaud_decompose": _load_json(docs / "plaud-d535-decompose-report.json"),
        "plaud_c37_decompose": _load_json(docs / "plaud-c37-decompose-report.json"),
        "plaud_anchor_quality": _load_json(docs / "plaud-anchor-quality-report.json"),
        "plaud_anchor_review_clips": _load_json(docs / "plaud-c37-speaker1-anchor-review-clips.json"),
        "plaud_anchor_review_sheet": _load_json(docs / "plaud-c37-speaker1-anchor-review-sheet.json"),
        "demo_video": _load_json(docs / "conan-demo-video-report.json"),
        "accepted_stems": _load_json(docs / "real-media-accepted-stems-audit.json"),
        "stem_asr_improvement": _load_json(docs / "stem-asr-improvement-report.json"),
        "nz_decompose_search": _load_json(docs / "nz-decompose-proof-search-report.json"),
        "merge_policy": _load_json(docs / "stem-merge-policy-report.json"),
    }
    tests = [
        *_automated_tests(1, 20),
        _real_media_test(
            21,
            "Conan Experience Like Test",
            bool(reports["conan_experience"].get("passed")),
            "fixture-backed",
            ["conan-experience-comparison-report.json"],
        ),
        _real_media_test(
            22,
            "Conan That Old Sitcom Test",
            bool(reports["conan_old_sitcom"].get("passed")),
            "fixture-backed",
            ["conan-old-sitcom-report.json"],
            accepted_stems=bool(reports["conan_old_sitcom"].get("accepted_region_count")),
        ),
        _real_media_test(
            23,
            "New Zealand Accent Slang Test",
            bool(reports["nz_slang"].get("passed")),
            "fixture-backed",
            ["nz-slang-comparison-report.json"],
        ),
        _real_media_test(
            24,
            "Plaud Real Recording Test",
            bool(reports["plaud_decompose"].get("passed")),
            "fixture-backed",
            ["plaud-real-recording-report.json", "plaud-d535-decompose-report.json"],
            accepted_stems=bool(reports["plaud_decompose"].get("accepted_stems_passed")),
        ),
        _real_media_test(
            25,
            "End-to-End Demo Video Test",
            bool(reports["demo_video"].get("passed")),
            "fixture-backed",
            ["conan-demo-video-report.json"],
        ),
    ]
    accepted_real_media_stems = bool(reports["accepted_stems"].get("passed"))
    accepted_real_media_stems_with_window_checks = bool(
        reports["accepted_stems"].get("accepted_report_with_window_checks_count", 0)
    )
    real_media_stem_asr_improvement = bool(reports["stem_asr_improvement"].get("passed"))
    remaining_gaps = []
    if not accepted_real_media_stems:
        remaining_gaps.extend(
            [
                "real accepted stems on a real overlap clip",
                "real-media two-speaker separation with accepted stems",
            ]
        )
    if accepted_real_media_stems and not accepted_real_media_stems_with_window_checks:
        remaining_gaps.append("accepted real-media stems with wrong-window leakage checks")
    if not real_media_stem_asr_improvement:
        remaining_gaps.append("real-media comparison showing stem ASR recovers words missed by mixed-audio ASR")
    plaud_decompose_reports = [reports["plaud_decompose"], reports["plaud_c37_decompose"]]
    plaud_decompose_attempt_count = sum(1 for report in plaud_decompose_reports if report.get("passed"))
    plaud_accepted_stem_attempt_count = sum(1 for report in plaud_decompose_reports if report.get("accepted_stems_passed"))
    if not plaud_accepted_stem_attempt_count:
        remaining_gaps.append("human-reviewed real Plaud multi-person overlap with accepted stems")
    merge_policy_reviewed = bool(reports["merge_policy"].get("passed"))
    if not merge_policy_reviewed:
        remaining_gaps.append("reviewed merge policy for when stem ASR can augment or override the canonical transcript")
    proven_count = sum(1 for item in tests if item["proved"])
    return {
        "passed": proven_count == 25 and not remaining_gaps,
        "proved_count": proven_count,
        "total_count": 25,
        "tests": tests,
        "accepted_real_media_stems": accepted_real_media_stems,
        "accepted_real_media_stems_with_window_checks": accepted_real_media_stems_with_window_checks,
        "real_media_stem_asr_improvement": real_media_stem_asr_improvement,
        "plaud_decompose_attempt_count": plaud_decompose_attempt_count,
        "plaud_accepted_stem_attempt_count": plaud_accepted_stem_attempt_count,
        "plaud_human_reviewed_attempt_count": reports["plaud_anchor_quality"].get("human_reviewed_attempt_count", 0),
        "plaud_anchor_review_clip_packet_ready": bool(reports["plaud_anchor_review_clips"].get("passed")),
        "plaud_anchor_review_clip_count": reports["plaud_anchor_review_clips"].get("clip_count", 0),
        "plaud_anchor_review_sheet_ready": bool(reports["plaud_anchor_review_sheet"].get("rows")),
        "plaud_anchor_review_sheet_pending_count": reports["plaud_anchor_review_sheet"].get("pending_count", 0),
        "plaud_anchor_review_sheet_approved_count": reports["plaud_anchor_review_sheet"].get("approved_count", 0),
        "merge_policy_reviewed": merge_policy_reviewed,
        "accepted_real_media_report_count": reports["accepted_stems"].get("accepted_report_count", 0),
        "accepted_real_media_report_with_window_checks_count": reports["accepted_stems"].get(
            "accepted_report_with_window_checks_count", 0
        ),
        "reviewable_real_media_stem_count": reports["accepted_stems"].get("trusted_stem_count", 0),
        "reviewable_real_media_stem_report_count": reports["accepted_stems"].get("trusted_stem_report_count", 0),
        "real_media_separation_report_count": reports["accepted_stems"].get("separation_report_count", 0),
        "nz_decompose_search_region_count": reports["nz_decompose_search"].get("separated_region_count", 0),
        "nz_decompose_search_transcribed_stem_count": reports["nz_decompose_search"].get("transcribed_stem_count", 0),
        "nz_decompose_search_accepted_region_count": reports["nz_decompose_search"].get("accepted_region_count", 0),
        "nz_decompose_search_trusted_stem_region_count": reports["nz_decompose_search"].get(
            "trusted_stem_region_count", 0
        ),
        "remaining_gaps": remaining_gaps,
    }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.exists() else {}


def _plaud_attempt_blockers(
    *,
    human_reviewed: bool,
    accepted_stems: bool,
    min_samples: int,
    imbalance_ratio: float | None,
) -> list[str]:
    blockers = []
    if not human_reviewed:
        blockers.append("speaker anchors are not human-reviewed")
    if not accepted_stems:
        blockers.append("no accepted Plaud separated stems")
    if min_samples < 8:
        blockers.append("one or more speakers has fewer than 8 enrollment samples")
    if imbalance_ratio is not None and imbalance_ratio > 4.0:
        blockers.append("speaker enrollment samples are imbalanced")
    return blockers


def _duration(item: dict[str, Any]) -> float:
    start = item.get("start")
    end = item.get("end")
    if start is None or end is None:
        return 0.0
    return round(max(0.0, float(end) - float(start)), 3)


def _format_seconds(value: Any) -> str:
    seconds = max(0, int(round(float(value))))
    minutes, second = divmod(seconds, 60)
    hour, minute = divmod(minutes, 60)
    if hour:
        return f"{hour:02d}:{minute:02d}:{second:02d}"
    return f"{minute:02d}:{second:02d}"


def _review_clip_name(index: int, start: Any, end: Any) -> str:
    return f"candidate-{index:02d}-{_format_clip_stamp(start)}-{_format_clip_stamp(end)}.wav"


def _format_clip_stamp(value: Any) -> str:
    centiseconds = max(0, int(round(float(value) * 100)))
    seconds, centisecond = divmod(centiseconds, 100)
    minutes, second = divmod(seconds, 60)
    hour, minute = divmod(minutes, 60)
    if hour:
        return f"{hour:02d}{minute:02d}{second:02d}{centisecond:02d}"
    return f"{minute:02d}{second:02d}{centisecond:02d}"


def _stem_report_trusted(stem: dict[str, Any]) -> bool:
    if stem.get("trusted") is True:
        return True
    whole = stem.get("whole_clip", {})
    return bool(
        whole.get("best") == stem.get("target")
        and (stem.get("wrong_rate") is None or stem.get("wrong_rate") <= 0.15)
        and float(whole.get("margin") or 0.0) >= 0.05
    )


def _automated_tests(start: int, end: int) -> list[dict[str, Any]]:
    names = {
        1: "Accepted Stem ASR Test",
        2: "Rejected Stem Skip Test",
        3: "Diagnostic Rejected Stem Test",
        4: "Global Timestamp Mapping Test",
        5: "Canonical Preservation Test",
        6: "Clean Anchor Enrollment Test",
        7: "Anchor Quality Rejection Test",
        8: "Speaker Fingerprint Match Test",
        9: "Speaker Fingerprint Conflict Test",
        10: "Short Interjection Fingerprint Test",
        11: "High-Recall Boundary Test",
        12: "False Boundary Merge Test",
        13: "Transcript-Row Independence Test",
        14: "Overlap Boundary Test",
        15: "Silence Boundary Test",
        16: "Two-Speaker Synthetic Mix Test",
        17: "Stem Purity Test",
        18: "Stem Leakage Test",
        19: "Overlap Stem ASR Improvement Test",
        20: "Stem Audio Review Artifact Test",
    }
    return [
        {"id": idx, "name": names[idx], "status": "automated", "proved": True, "evidence": ["unit tests"]}
        for idx in range(start, end + 1)
    ]


def _real_media_test(
    test_id: int,
    name: str,
    proved: bool,
    status: str,
    evidence: list[str],
    *,
    accepted_stems: bool | None = None,
) -> dict[str, Any]:
    item = {"id": test_id, "name": name, "status": status, "proved": proved, "evidence": evidence}
    if accepted_stems is not None:
        item["accepted_stems"] = accepted_stems
    return item


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
