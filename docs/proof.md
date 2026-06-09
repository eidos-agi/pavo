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
- Current result: `partial: true`
- Full item-24 result: `passed: false`

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

## What Is Not Yet Proven

- This Plaud proof recording is not a multi-speaker overlap recording.
- The proof above does not show a full real-world separated two-speaker Plaud
  call.
- The machine-readable report currently marks voiceprints, speaker-change
  detection, decomposition, and stem ASR as missing for this real Plaud
  recording.
- Pavo does not currently run genetic algorithms.

The next proof target should be a real two-speaker Plaud recording with overlap,
speaker mappings, and a `separate-overlaps` run that produces accepted stem
reports.
