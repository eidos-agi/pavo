# Proof

This page records the current proof that Pavo can hand real Plaud audio into
the installable `eidos-transcribe` audio-intelligence layer.

## 1. Audio Intelligence Environment

Command:

```bash
pavo audio doctor
```

Result:

```text
Plaud CLI: /opt/homebrew/bin/plaud
Plaud version: plaud 0.2.4
eidos-transcribe: /Users/dshanklinbv/.pyenv/shims/eidos-transcribe
eidos-transcribe version: eidos-transcribe 0.1.0

[ok ] ffmpeg
[ok ] whisper.cpp binary
[ok ] whisper.cpp model (base.en)
[ok ] faster-whisper import
[ok ] local-whisper CLI (small.en)
[ok ] speaker extras                numpy, librosa, resemblyzer, sklearn
[ok ] separation extras             torch, torchaudio

OK: baseline environment is ready.
```

This proves that Pavo can see the Plaud CLI and that `eidos-transcribe` has the
optional speaker and separation dependencies installed.

## 2. Bio-Inspired Speaker Logic

Command:

```bash
cd /Users/dshanklinbv/repos-eidos-agi/eidos-transcribe
/Users/dshanklinbv/.pyenv/versions/3.12.7/bin/python -m pytest -q \
  tests/test_speaker_pipeline.py \
  -k "immune or rolling or separation or stems"
```

Result:

```text
9 passed, 9 deselected
```

Those targeted tests cover:

- immune detector voting over speaker detector banks
- expansion of detector banks from call-local anchors
- immune/context overrides for weak speaker labels
- rolling fingerprint detection of mixed-speaker regions
- splitting transcript rows using rolling fingerprint runs
- selecting overlap regions for separation analysis
- assigning separated stems to speakers by best global score
- rejecting separation output when leakage or speaker mismatch is too high

This is the basis for the README claim that the audio-intelligence layer is
bio-inspired. It is immune-style detector voting and rolling fingerprinting,
not a genetic algorithm.

## 3. Real Plaud Audio Through Pavo

Command:

```bash
pavo transcribe d195d22dec3d2bf3ea31b12a0aa43654 \
  --context-term Plaud \
  --context-term Pavo
```

Result:

```text
audio_path: /Users/dshanklinbv/Eidos/Pavo/cache/plaud/d195d22dec3d2bf3ea31b12a0aa43654/audio.mp3
audio_sha256: dee0b7c5134b1c3c6e5408a42df21873c11412e4847a7bedf29347ea2716e9d6
transcribe_output_dir: /Users/dshanklinbv/Eidos/Pavo/cache/plaud/d195d22dec3d2bf3ea31b12a0aa43654/transcribe
manifest: /Users/dshanklinbv/Eidos/Pavo/cache/plaud/d195d22dec3d2bf3ea31b12a0aa43654/pavo-transcribe-manifest.json
```

The Pavo manifest records:

```json
{
  "recording_id": "d195d22dec3d2bf3ea31b12a0aa43654",
  "audio_sha256": "dee0b7c5134b1c3c6e5408a42df21873c11412e4847a7bedf29347ea2716e9d6",
  "engines": ["faster-whisper"],
  "context_terms": ["Plaud", "Pavo"]
}
```

The `eidos-transcribe` manifest records:

```json
{
  "engines": ["faster-whisper"],
  "method": "timed primary-spine ensemble with context-term correction; raw outputs preserved"
}
```

Machine-readable proof report:

- [plaud-real-recording-report.json](plaud-real-recording-report.json)
- [plaud-d535-decompose-report.json](plaud-d535-decompose-report.json)
- Current result: `partial: true`
- Full item-24 pipeline result: `passed: true`
- Accepted stem result: `accepted_stems_passed: false`

Transcript output:

```text
[00:00:00 --> 00:00:06] I am a very model of a modern Major General.
[00:00:06 --> 00:00:14] The quick brown fox jumped over the lazy dog, and now it's time to see if you can translate
[00:00:14 --> 00:00:15] various actions.
[00:00:15 --> 00:00:20] I am curious to know if you can tell the different actions.
```

## What Is Proven

- Pavo can use the Plaud CLI path to work with real recording audio.
- Pavo can call `eidos-transcribe` as an installable package boundary.
- The transcribe run preserves raw outputs, context terms, transcript output,
  and manifests.
- The audio-intelligence package has tested immune-style detector voting,
  rolling fingerprints, overlap candidate selection, and separation scoring.
- The reviewed stem merge policy is now code-backed in `eidos-transcribe`: stem
  ASR can propose transcript augmentations, but reviewed approval is required
  before augmentation, and reviewed override requires accepted stem evidence,
  high separation margin, and low-confidence canonical overlap.

## What Is Not Yet Proven

- This Plaud proof recording is not a multi-speaker overlap recording.
- The proof above does not show a full real-world separated two-speaker Plaud
  call.
- The machine-readable report currently marks voiceprints, speaker-change
  detection, decomposition, and stem ASR as missing for this real Plaud
  recording.
- A second Plaud recording, `d535f050e8b65bd1ee0cf144cf215873`, now proves the
  voiceprint-first pipeline can run on real Plaud audio with generic speaker
  labels: download, two speaker signatures, rolling speaker-change evidence,
  three separated regions, diagnostic stem ASR, and manifests.
- A longer Plaud recording, `c37d65f27fc0cf75c85fd0dadb8a6ba1`, also runs
  through the full Plaud decompose path: download, ASR, voiceprints,
  speaker-change candidates, five separated regions, diagnostic stem ASR, and
  manifests.
- The separated regions in both Plaud decompose runs are still rejected by the
  quality gates, so this is not accepted Plaud stem proof.
- The Plaud anchor-quality report shows the remaining item-24 blocker more
  precisely: 2 Plaud attempts have run, 0 have human-reviewed speaker anchors,
  and 0 have accepted Plaud stems. The c37 run is especially imbalanced:
  Speaker 0 has many more enrollment samples than Speaker 1.
- Pavo now writes a c37 Speaker 1 anchor review packet with 20 candidate spans
  and suggested `--speaker-correction` values:
  [plaud-c37-speaker1-anchor-review-packet.json](plaud-c37-speaker1-anchor-review-packet.json).
- Pavo also cuts the 20 real c37 candidate spans into reviewable WAV clips, so
  a human can listen to the likely Speaker 1 anchors before rerunning the
  Plaud decompose path with corrections:
  [plaud-c37-speaker1-anchor-review-clips.json](plaud-c37-speaker1-anchor-review-clips.json).
- Pavo now turns those clips into a pending human review sheet:
  [plaud-c37-speaker1-anchor-review-sheet.json](plaud-c37-speaker1-anchor-review-sheet.json).
  The sheet currently has 20 pending rows and 0 approved corrections, so no
  unreviewed clip can be exported as a speaker override.
- Pavo also writes a local HTML listening page for that same sheet:
  [plaud-c37-speaker1-anchor-review.html](plaud-c37-speaker1-anchor-review.html).
  It embeds all 20 WAV clips with their proposed `--speaker-correction` values
  and lets the reviewer approve, reject, annotate, and export an updated JSON
  sheet without opening clip paths or editing JSON by hand. The exported sheet
  can be validated and imported with `pavo review anchors import`, which rejects
  changed clip identities before corrections are generated. Once approved rows
  exist, `pavo review anchors rerun-command` prints the exact corrected
  `pavo audio decompose` command from the original Pavo manifest plus the
  approved `--speaker-correction` flags. The current c37 sheet still has no
  approved rows, so the rerun command report correctly remains blocked:
  [plaud-c37-anchor-rerun-command-report.json](plaud-c37-anchor-rerun-command-report.json).
- The review page itself is now verified by a local HTML parser because the
  in-app browser blocks direct `file://` navigation. The page verification
  report confirms 20 audio players, 20 approve controls, 20 reject controls,
  20 pending controls, 20 note fields, embedded sheet JSON, and import/rerun
  instructions:
  [plaud-c37-anchor-review-page-report.json](plaud-c37-anchor-review-page-report.json).
- Pavo now also creates a browser-safe review bundle with all 20 WAV clips
  copied beside `index.html` using relative audio URLs. The bundle can be
  served locally with
  `cd docs/plaud-c37-anchor-review-bundle && python3 -m http.server 9876 --bind 127.0.0.1`.
  Browser DOM verification over `http://127.0.0.1:9876/index.html` confirms the
  same 20 audio controls and review controls render over HTTP:
  [plaud-c37-anchor-review-bundle-manifest.json](plaud-c37-anchor-review-bundle-manifest.json),
  [plaud-c37-anchor-review-browser-report.json](plaud-c37-anchor-review-browser-report.json).
- The combined review gate now checks sheet status, page verification, bundle
  readiness, browser verification, and rerun-command readiness in one report:
  [plaud-c37-anchor-review-gate-report.json](plaud-c37-anchor-review-gate-report.json).
  It currently passes every UI/bundle check and fails only because 20 review
  rows are still pending and no speaker-anchor clips are approved.
- The real-media audit now finds accepted Conan/Kaitlin overlap separation:
  both stems pass the trust gate with wrong-window leakage checks. The accepted
  stem ASR manifest writes trusted global-timed evidence for that overlap.
- The accepted Conan stem ASR does not prove transcript improvement by itself:
  the reviewed expected phrase appears in the same-region mixed ASR too, so
  [stem-asr-improvement-report.json](stem-asr-improvement-report.json) remains
  `passed: false`.
- A broader Conan search checked 80 candidate overlap regions across 4 padding
  settings and did not find another accepted region that proves stem-ASR word
  recovery; see
  [stem-asr-improvement-search-report.json](stem-asr-improvement-search-report.json).
- The New Zealand accent/slang fixture now runs through generic speaker
  signature enrollment, rolling/immune attribution, separated overlap regions,
  and diagnostic stem transcripts. A later assignment fix lets stems match any
  of the six speaker labels instead of only the first two labels. The accepted
  sweep evidence shows trusted stem ASR recovered three words that the
  same-region mixed ASR missed; see
  [accepted-stem-asr-recovery-report.json](accepted-stem-asr-recovery-report.json).
  This closes the machine-comparison proof gap, but it is still not
  human-reviewed.
- Pavo does not currently run genetic algorithms.
- The merge policy is now proven by
  [stem-merge-policy-report.json](stem-merge-policy-report.json); the remaining
  blocker is human-reviewed multi-person Plaud accepted overlap.

The next proof target should be a real two-speaker Plaud recording with overlap,
speaker mappings, and a `separate-overlaps` run that produces accepted stem
reports, ideally with human-reviewed speaker identities.
