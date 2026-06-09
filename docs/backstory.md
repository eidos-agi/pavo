# Backstory

Pavo exists because Plaud is excellent at capture, but the stock Plaud workflow
is not enough when recordings need to become real working intelligence. A user
needs more control over the actual audio files, speaker identification, custom
dictionaries per call, routing, task creation, and durable archives.

The goal is simple:

```text
Plaud Cloud -> real audio -> speaker-aware transcript -> routed notes and tasks -> durable archive
```

Pavo owns the Plaud wrapper, file control, routing, task creation, and archive
layer. `eidos-transcribe` owns the audio-intelligence layer that Pavo can call
as an installable package.

## Why Plaud Alone Was Not Sufficient

### 1. Transcript-only access is not enough

Plaud notes and transcripts are useful, but they are not the source artifact.
If the transcript is wrong, incomplete, or missing context, an agent needs the
actual audio file so it can run a better model, compare engines, apply known
vocabulary, and preserve proof.

Pavo solves the capture side by downloading the original audio and hashing it.
`eidos-transcribe` solves the intelligence side by treating raw audio and raw
engine outputs as evidence instead of trusting one transcript.

### 2. The real audio needed to be discoverable from Plaud Cloud

The first practical problem was proving that a Plaud account could be reached
and that the real recording files could be listed and downloaded. Plaud exposed
multiple surfaces: a CLI and an MCP server. They were related but not identical,
and each had its own setup behavior.

Pavo keeps those surfaces separate. It can call the Plaud CLI today, and its
design leaves room for a Plaud MCP adapter without making the MCP path the only
source of truth.

### 3. Account identity was not obvious

The Plaud login came through a Google-linked Plaud identity, not a clean
human-readable email address. That made it important to record the authenticated
Plaud user and avoid assuming that the visible Google address and Plaud account
identifier would always look the same.

Pavo's doctor and Plaud commands expose the current authenticated user so the
operator can verify the account before fetching recordings.

### 4. MCP installation did not mean Codex could immediately see MCP tools

The Plaud MCP installer worked and the MCP server could be probed over stdio,
but the current Codex session did not immediately expose the Plaud MCP tools.
That meant the system needed a CLI fallback instead of depending on a session
restart or plugin discovery state.

Pavo therefore starts from the CLI path and treats MCP as an adapter that can be
added when visible. This keeps recording capture reliable even when agent tool
discovery is stale.

### 5. Temporary audio URLs are not durable artifacts

Plaud can return temporary or signed URLs for recordings. Those URLs are useful
for download, but they are not artifacts that should be stored in public docs,
issues, logs, or manifests.

Pavo downloads the audio, records local paths and hashes, and avoids making
temporary URLs the durable record.

### 6. Local configuration needed to be private and inspectable

Pavo needed a local operating folder without becoming a credential dump. Plaud
tokens belong to the Plaud CLI. Google credentials belong to Google credential
stores. OpenAI credentials belong to their normal stores.

Pavo stores non-secret config and cache state under:

```text
~/Eidos/Pavo
```

That keeps the system inspectable while avoiding secrets in the repo or plugin.

### 7. Google Drive should become the durable archive

Google Drive is the first durable archive target. That means Pavo needs to track
local files, manifests, transcripts, and future Drive artifact ids without
duplicating uploads or losing the original source audio.

Pavo is the right layer for Drive sync because Drive is orchestration and
storage. `eidos-transcribe` should not know about Plaud or Drive.

### 8. Generic transcription misses domain terms

Real recordings contain names, companies, product names, account concepts, and
call-specific terms. A generic recognizer can produce plausible but wrong words.

`eidos-transcribe` addresses this with context terms and context files. Pavo can
pass a custom dictionary per call, while future Pavo profiles can pass reviewed
personal, company, customer, or project dictionaries.

### 9. One recognizer is not enough for important audio

Different speech recognition engines fail differently. One model may catch a
name while another model catches a phrase boundary. A single transcript hides
those disagreements.

`eidos-transcribe` can run multiple engines, preserve raw outputs, and ensemble
candidate transcripts. It records manifests so a reviewer can see which engines
ran and which context terms influenced the result.

### 10. Speaker identity requires audio evidence, not guesses

Plaud recordings can include multiple people, interruptions, and diarization
errors. A transcript label such as `SPEAKER_00` is not the same as knowing who
spoke.

`eidos-transcribe` has a speaker pipeline that compares local diarization
methods, attributes transcript segments by audio overlap, preserves provenance,
and supports explicit speaker mappings. It can create and use speaker
signatures from high-confidence spans instead of pretending speaker names are
known by default.

### 11. Overlapping speech and noisy audio need custom handling

Meetings are messy. People talk over each other, rooms are noisy, and some
segments contain mixed speaker evidence. Forcing those segments into a single
speaker or single transcript line creates false certainty.

`eidos-transcribe` includes rolling acoustic fingerprinting to flag mixed
speaker evidence and a source-separation path for overlap regions. The design
is conservative: mark uncertainty, isolate suspicious regions, and preserve
reports instead of silently smoothing over the problem.

### 12. Better transcription should be updatable without rewriting Pavo

Pavo should not contain every transcription algorithm. If it did, every audio
upgrade would require changing the Plaud/Drive orchestration tool too.

The solution is an installable package boundary:

```text
Pavo -> eidos-transcribe CLI -> transcript bundle and manifests
```

Pavo calls `eidos-transcribe` as a subprocess. That means `eidos-transcribe` can
be installed, upgraded, tested, and versioned independently while Pavo keeps the
recording lifecycle stable.

## The Split

Pavo solves:

- Plaud recording discovery.
- Plaud CLI and Plaud MCP wrapping.
- Real audio download.
- Local cache and config structure.
- Recording manifests.
- Google Drive archiving.
- Intelligent routing and task creation.
- Agent/plugin instructions for safe use.

`eidos-transcribe` solves:

- Multi-engine transcription.
- Call-specific dictionaries and context-aware scoring.
- Raw-output preservation.
- Transcript manifests.
- Speaker diarization bakeoffs.
- Speaker signatures and rolling acoustic fingerprints.
- Overlap detection and source-separation analysis.
- Reprocessing as models, dictionaries, and algorithms improve.

## Current Proof

The first proof recording was downloaded as real MP3 audio, hashed locally, and
transcribed through `eidos-transcribe` with Pavo/Plaud context terms. That
proved the critical path:

```text
Plaud recording id -> audio.mp3 -> eidos-transcribe -> transcript + manifest
```

The remaining product work is to make the loop durable for daily use: local
sync index, Google Drive archive, duplicate-safe uploads, and a thin Codex
plugin surface that routes agents back to the Pavo CLI.
