# Diarization Direction

Pavo should treat speaker change detection as a first-class signal.

The system should not start by asking, "Which known speaker said this whole
line?" It should start by asking, "Did the voice event change here?" Every
candidate change can then be tested, attributed, merged, or marked uncertain.

## Target Loop

```text
audio
-> voice activity regions
-> speaker-change candidates
-> short acoustic segments
-> speaker fingerprint scoring
-> transcript alignment
-> reviewed speaker turns
```

## Principle

Prefer controlled over-segmentation before attribution.

If a phrase is short, interrupted, or spoken over another person, Pavo should
still create a candidate turn boundary when the audio indicates a speaker
change. The next layer can decide whether that boundary is real.

That gives Pavo a better failure mode:

- Good: "A speaker-change candidate occurred at 00:18.42; evidence suggests
  this may be Conan, but confidence is low."
- Bad: "This whole transcript row belongs to Kaitlin because the surrounding
  segment was assigned to Kaitlin."

## Required Signals

Speaker-change candidates should combine several signals:

- voice activity boundaries
- embedding distance between adjacent windows
- pitch/formant shifts
- energy and spectral changes
- lexical interruption cues from the transcript
- source-separation evidence when speech overlaps
- reviewed speaker anchors when names are known

No single signal should be trusted alone.

## Attribution Comes Later

Once candidate change points exist, Pavo can score each resulting segment:

- known speaker fingerprint match
- local cluster consistency
- overlap with transcript timing
- separation stem quality
- confidence score and reason

Only after that should the system merge adjacent segments. Merging should be an
explicit decision, not a side effect of coarse transcript rows.

## Media Test Implication

The Conan clip exposed this weakness. The system should not only ask whether
the phrase was transcribed correctly. It should also ask whether Pavo detected
the speaker change at the right time, even when the phrase is short.

The New Zealand accent/slang fixture should be evaluated similarly: first for
speaker-change recall, then for speaker attribution, then for words and custom
dictionary improvements.
