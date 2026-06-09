# Proof Matrix

This matrix tracks the 25 tests that would prove Pavo and `eidos-transcribe`
work as a voiceprint-first audio intelligence system.

Status values:

- `automated`: covered by local unit tests.
- `fixture-backed`: has local media artifacts, but not a stable automated pass.
- `planned`: not yet implemented.

## Core Pipeline

1. Accepted Stem ASR Test - `automated`
   - Evidence: `eidos-transcribe/tests/test_decompose.py::test_transcribe_accepted_stems_writes_global_timed_evidence`
2. Rejected Stem Skip Test - `automated`
   - Evidence: `eidos-transcribe/tests/test_decompose.py::test_transcribe_accepted_stems_skips_rejected_regions`
3. Diagnostic Rejected Stem Test - `automated`
   - Evidence: `eidos-transcribe/tests/test_decompose.py::test_diagnostic_mode_transcribes_rejected_stems_as_untrusted`
4. Global Timestamp Mapping Test - `automated`
   - Evidence: `eidos-transcribe/tests/test_decompose.py::test_transcribe_accepted_stems_writes_global_timed_evidence`
5. Canonical Preservation Test - `automated`
   - Evidence: `eidos-transcribe/tests/test_decompose.py::test_decomposition_manifest_preserves_canonical_transcript_reference`

## Speaker Fingerprints

6. Clean Anchor Enrollment Test - `automated`
   - Evidence: speaker signature creation tests and `select_signature_spans` coverage.
7. Anchor Quality Rejection Test - `automated`
   - Evidence: `eidos-transcribe/tests/test_speaker_pipeline.py::test_signature_spans_reject_low_quality_anchors`
8. Speaker Fingerprint Match Test - `automated`
   - Evidence: immune detector vote and signature verification tests.
9. Speaker Fingerprint Conflict Test - `automated`
   - Evidence: immune conflict/override tests.
10. Short Interjection Fingerprint Test - `automated`
   - Evidence: `test_select_overlap_candidates_can_include_short_interjections`.

## Speaker Change Detection

11. High-Recall Boundary Test - `automated`
   - Evidence: `eidos-transcribe/tests/test_proof_metrics.py`.
12. False Boundary Merge Test - `automated`
   - Evidence: `eidos-transcribe/tests/test_speaker_pipeline.py::test_same_speaker_rolling_runs_merge_before_boundary_split`
13. Transcript-Row Independence Test - `automated`
   - Evidence: `test_rolling_fingerprint_split_preserves_handoff_phrase`.
14. Overlap Boundary Test - `automated`
   - Evidence: rolling mixed segment and overlap candidate tests.
15. Silence Boundary Test - `automated`
   - Evidence: `eidos-transcribe/tests/test_proof_metrics.py::test_speaker_change_recall_counts_silence_separated_turns`

## Source Separation

16. Two-Speaker Synthetic Mix Test - `automated`
   - Evidence: `eidos-transcribe/tests/test_synthetic_proof.py::test_two_speaker_synthetic_mix_confirms_stems_match_expected_fingerprints`
17. Stem Purity Test - `automated`
   - Evidence: `test_separation_passes_requires_matching_low_leakage_stems`.
18. Stem Leakage Test - `automated`
   - Evidence: `test_separation_passes_requires_matching_low_leakage_stems`.
19. Overlap Stem ASR Improvement Test - `automated`
   - Evidence: `eidos-transcribe/tests/test_synthetic_proof.py::test_overlap_stem_asr_improvement_reports_recovered_words`
20. Stem Audio Review Artifact Test - `automated`
   - Evidence: `eidos-transcribe/tests/test_proof_metrics.py::test_stem_audio_review_artifacts_requires_reviewable_region_files`
   - Evidence: local Conan separation artifacts under `~/Eidos/Pavo/cache/imports/`.
   - Evidence: `docs/conan-diagnostic-stems.md`

## Real Media Proof

21. Conan "Experience Like" Test - `fixture-backed`
   - Evidence: [Conan "Experience Like" fixture](conan-experience-like.md)
   - Evidence: [conan-experience-like-fixture.json](conan-experience-like-fixture.json)
   - Evidence: [conan-experience-comparison-report.json](conan-experience-comparison-report.json)
22. Conan "That Old Sitcom" Test - `fixture-backed`
   - Evidence: local Conan overlap reports exist, current reports are rejected, and rejected stems have diagnostic ASR evidence.
   - Evidence: `docs/conan-diagnostic-stems.md`
   - Evidence: [conan-old-sitcom-report.json](conan-old-sitcom-report.json)
23. New Zealand Accent Slang Test - `fixture-backed`
   - Evidence: `~/Eidos/Pavo/demos/nz-accent-test/`.
   - Evidence: [nz-slang-comparison-report.json](nz-slang-comparison-report.json)
24. Plaud Real Recording Test - `fixture-backed`
   - Evidence: single-speaker Plaud proof exists; multi-speaker overlap proof is still missing.
   - Evidence: [plaud-real-recording-report.json](plaud-real-recording-report.json)
25. End-to-End Demo Video Test - `fixture-backed`
   - Evidence: `~/Eidos/Pavo/demos/conan-pavo-demo/pavo-conan-demo.mp4`.
   - Evidence: [conan-demo-video-report.json](conan-demo-video-report.json)

## Current Gaps

The strongest remaining proof gaps are:

- real accepted stems on a real overlap clip
- real-media two-speaker separation with accepted stems
- real-media comparison showing stem ASR recovers words missed by mixed-audio ASR
- real Plaud multi-speaker overlap recording
- reviewed merge policy for when stem ASR can augment or override the canonical
  transcript
