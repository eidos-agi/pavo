# Media Tests

This page records real-media fixtures used to prove Pavo behavior. The source
videos, generated previews, and full transcripts are not committed to this
public repo. They live under `~/Eidos/Pavo/demos/` on the test machine.

## Test 1: Conan Overlap And Captioning

- Source: `When The Always Sunny Cast Met Danny DeVito | CONAN on TBS`
- YouTube ID: `KxJWK8R7uVQ`
- Pavo source ID: `youtube_KxJWK8R7uVQ_named_v1`
- Local demo: `/Users/dshanklinbv/Eidos/Pavo/demos/conan-pavo-demo/pavo-conan-demo.mp4`
- Comparison: `/Users/dshanklinbv/Eidos/Pavo/demos/conan-pavo-demo/comparison.json`
- Overlap report: `/Users/dshanklinbv/Eidos/Pavo/cache/imports/youtube_KxJWK8R7uVQ_named_v1/process-call/pavo-separated-overlaps-that-old-sitcom/region-01-00m18s-00m18s/analysis.md`
- Diagnostic stem ASR report: [Conan diagnostic stems](conan-diagnostic-stems.md)
- Speaker-change fixture: [Conan "Experience Like" fixture](conan-experience-like.md)

Useful cases:

- Reviewed speaker anchors for named captioning.
- Short overlap review for the "that old sitcom" moment.
- Speaker-change recall for short interjections, independent from whether the
  final speaker attribution is accepted.
- Pavo-branded burned-caption preview.
- Comparison against YouTube captions without copying full transcripts into
  the repo.

Rerun the overlap review:

```bash
pavo audio separate-overlaps youtube_KxJWK8R7uVQ_named_v1 \
  --start 17 \
  --end 21 \
  --min-duration 0.25
```

## Test 2: New Zealand Accent / Slang

- Source: `New Zealand Accent/ Slang`
- Channel: `King Country Kiwi`
- YouTube ID: `ddIP0k-XzpI`
- Pavo source ID: `youtube_ddIP0k-XzpI_nz_accent_6speakers`
- Local demo folder: `/Users/dshanklinbv/Eidos/Pavo/demos/nz-accent-test/`
- Preview video: `/Users/dshanklinbv/Eidos/Pavo/demos/nz-accent-test/pavo-nz-accent-preview.mp4`
- Comparison: `/Users/dshanklinbv/Eidos/Pavo/demos/nz-accent-test/comparison.json`
- Process manifest: `/Users/dshanklinbv/Eidos/Pavo/cache/imports/youtube_ddIP0k-XzpI_nz_accent_6speakers/pavo-process-manifest.json`
- Scorecard: `/Users/dshanklinbv/Eidos/Pavo/cache/imports/youtube_ddIP0k-XzpI_nz_accent_6speakers/process-call/speaker-pipeline/scorecard.json`

Useful cases:

- Accent and slang vocabulary with a context dictionary.
- Multi-speaker news-style diarization without reviewed names.
- Speaker-change recall before speaker-name mapping.
- Comparison against YouTube auto-captions, which have no speaker names or
  diarization.
- Term checks for phrases such as `box of birds`, `sweet as`, and
  `bottle of milk`.

Rerun the six-speaker process:

```bash
pavo audio process /Users/dshanklinbv/Eidos/Pavo/imports/youtube/ddIP0k-XzpI/ddIP0k-XzpI.mp4 \
  --source-id youtube_ddIP0k-XzpI_nz_accent_6speakers \
  --title "New Zealand Accent/ Slang | King Country Kiwi" \
  --context-file /Users/dshanklinbv/Eidos/Pavo/demos/nz-accent-test/context-terms.txt \
  --context-term "New Zealand" \
  --context-term Kiwi \
  --context-term "King Country Kiwi" \
  --num-speakers 6
```

Rerun the preview render:

```bash
pavo video render youtube_ddIP0k-XzpI_nz_accent_6speakers \
  --title "New Zealand Accent/ Slang | Pavo Test" \
  --duration 45 \
  --out /Users/dshanklinbv/Eidos/Pavo/demos/nz-accent-test/pavo-nz-accent-preview.mp4
```

Current proof notes:

- Best method: `resemblyzer-kmeans`
- Score: `0.8042`
- Speaker clusters: `6`
- Transcript assignment rate: `1.0`
- Preview verification: 45 seconds, 1280x720, audio present, clean ffmpeg
  decode.

The useful limitation is clear: Pavo can discover clusters, preserve more
call-specific phrasing, and render captions, but this fixture still needs
speaker-change recall scoring and human-reviewed speaker-name mapping before
final named output.
