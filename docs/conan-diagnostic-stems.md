# Conan Diagnostic Stem ASR

This page records the real-media diagnostic run for the Conan overlap fixtures.
It uses rejected separated stems as untrusted diagnostic evidence. It does not
promote those stems into the canonical transcript.

## Source

- Video: `When The Always Sunny Cast Met Danny DeVito | CONAN on TBS`
- YouTube ID: `KxJWK8R7uVQ`
- Pavo source ID: `youtube_KxJWK8R7uVQ_named_v1`

## Diagnostic Runs

Diagnostic rejected-stem ASR was run over these separation manifests:

- `/Users/dshanklinbv/Eidos/Pavo/cache/imports/youtube_KxJWK8R7uVQ_named_v1/process-call/pavo-separated-overlaps-that-old-sitcom/separate-overlaps.manifest.json`
- `/Users/dshanklinbv/Eidos/Pavo/cache/imports/youtube_KxJWK8R7uVQ_named_v1/process-call/pavo-separated-overlaps-old-sitcom/separate-overlaps.manifest.json`

Outputs:

- `/Users/dshanklinbv/Eidos/Pavo/cache/imports/youtube_KxJWK8R7uVQ_named_v1/process-call/pavo-separated-overlaps-that-old-sitcom/stem-asr-diagnostic/decomposed-transcript.json`
- `/Users/dshanklinbv/Eidos/Pavo/cache/imports/youtube_KxJWK8R7uVQ_named_v1/process-call/pavo-separated-overlaps-old-sitcom/stem-asr-diagnostic/decomposed-transcript.json`
- Machine-readable "That Old Sitcom" report: [conan-old-sitcom-report.json](conan-old-sitcom-report.json)
- Current accepted real-media stem audit: [real-media-accepted-stems-audit.json](real-media-accepted-stems-audit.json)

## Results

### "That Old Sitcom" Region

- Region: `18.04s` to `18.96s`
- Padding start: `17.04s`
- Separation accepted: `false`
- Diagnostic stems transcribed: `2`
- Diagnostic transcript segments: `4`
- Trust status: every segment is `trusted: false`
- Canonical merge policy: evidence only; does not replace canonical transcript

Stem quality:

- Conan stem: whole-clip match `Conan O'Brien`, margin `0.0655`, wrong-window rate `0.3333`
- Kaitlin stem: whole-clip match `Kaitlin Olson`, margin `0.0517`, wrong-window rate `0.3333`

Interpretation: both stems have the right whole-clip speaker match, but leakage is
too high. The current rejection is appropriate.

### Earlier "Old Sitcom" Region

- Region: `15.96s` to `17.77s`
- Padding start: `14.96s`
- Separation accepted: `false`
- Diagnostic stems transcribed: `2`
- Diagnostic transcript segments: `3`
- Trust status: every segment is `trusted: false`
- Canonical merge policy: evidence only; does not replace canonical transcript

Stem quality:

- Conan stem: whole-clip match `Conan O'Brien`, margin `0.0032`, wrong-window rate `1.0`
- Kaitlin stem: whole-clip match `Kaitlin Olson`, margin `0.1368`, wrong-window rate `0.0`

Interpretation: one stem is clean enough to inspect, but the paired stem fails
badly. The region remains rejected.

## What This Proves

- Pavo/eidos-transcribe can run diagnostic ASR over rejected real-media stems.
- Diagnostic stem ASR is kept separate from trusted/canonical transcript output.
- The current quality gates are doing useful work: these Conan stems are
  inspectable, but not trustworthy enough to accept.

## What This Does Not Prove

- It does not prove accepted real-media source separation.
- It does not prove a stem-ASR improvement over mixed ASR on this clip.
- It does not prove the final merge policy.
