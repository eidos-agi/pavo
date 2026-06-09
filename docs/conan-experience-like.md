# Conan "Experience Like" Speaker-Change Fixture

This fixture tracks the short Conan handoff around the phrase `what was that
experience like`. The goal is to prove that Pavo does not treat the transcript
row as the only unit of truth. It should see the voice evidence around the
phrase and preserve a speaker-change candidate.

## Source

- Video: `When The Always Sunny Cast Met Danny DeVito | CONAN on TBS`
- YouTube ID: `KxJWK8R7uVQ`
- Pavo source ID: `youtube_KxJWK8R7uVQ_named_v1`
- Transcript artifact: `/Users/dshanklinbv/Eidos/Pavo/cache/imports/youtube_KxJWK8R7uVQ_named_v1/process-call/speaker-pipeline/resemblyzer-agglomerative.immune.attributed.json`
- Fixture JSON: [conan-experience-like-fixture.json](conan-experience-like-fixture.json)
- YouTube comparison report: [conan-experience-comparison-report.json](conan-experience-comparison-report.json)

## Result

- Fixture passed: `true`
- Phrase window: `5.56s` to `6.84s`
- Final attributed speaker: `Kaitlin Olson`
- Opposing label found: `SPEAKER_00`
- Rolling run slugs: `conan-obrien`, then `kaitlin-olson`
- YouTube phrase present: `true`
- YouTube speaker names present: `false`
- Pavo named speaker count: `5`

## Interpretation

This is the behavior Pavo needs: the final phrase attribution can be Kaitlin
while the rolling fingerprint still records the nearby Conan voice evidence.
That means the system can preserve a speaker-change candidate instead of
collapsing the whole moment into one coarse transcript row. The comparison
report also proves the specific advantage over the YouTube captions for this
case: YouTube preserves the words, but Pavo adds named speaker evidence and the
mixed voiceprint handoff.

## Limits

- This is phrase-level evidence, not a human-scored DER benchmark.
- It does not prove source separation acceptance.
- It does not prove stem ASR improvement.
