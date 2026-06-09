# Pavo

![Pavo logo](assets/logo.png)

**Manifest Anything.**

Pavo is the Eidos capture CLI for Plaud recordings. Its first job is to prove
that Daniel's Plaud account can be reached, list recordings, obtain temporary
audio URLs, and download the real audio files for later upload to Google Drive.

## Why Pavo Exists

Pavo exists because Plaud alone was not enough for Eidos work. Plaud can capture
meetings and produce useful notes, but the product workflow did not give an
agent a durable, auditable path from the real recording to transcription
evidence, speaker evidence, dictionaries, and later reprocessing.

The target loop is:

```text
Plaud Cloud -> real audio -> local manifest -> eidos-transcribe -> better transcript -> durable archive
```

Pavo owns the capture and orchestration layer. `eidos-transcribe` owns the
installable audio-intelligence layer.

The problems we hit:

1. **Transcript-only access was not enough.** Plaud notes are useful, but they
   are not the source artifact. Pavo downloads the original audio and hashes it.
   `eidos-transcribe` treats raw audio and raw engine outputs as evidence.
2. **The real audio had to be discoverable from Plaud Cloud.** Plaud exposed a
   CLI and an MCP server, with different setup behavior. Pavo keeps those
   surfaces separate and starts from the reliable CLI path.
3. **Account identity was not obvious.** The Plaud login came through a
   Google-linked Plaud identity, not a clean human-readable email address. Pavo
   exposes the authenticated Plaud user through doctor/list commands so the
   operator can verify the account before fetching recordings.
4. **MCP installation did not mean Codex could immediately see MCP tools.** The
   Plaud MCP server worked over stdio, but the current Codex session did not
   immediately expose the tools. Pavo therefore keeps a CLI fallback instead of
   depending on session-level tool discovery.
5. **Temporary audio URLs are not durable artifacts.** Signed Plaud URLs are
   useful for download, but should not be stored in public docs, issues, logs,
   or manifests. Pavo stores local file paths, hashes, and manifests instead.
6. **Local configuration needed to be private and inspectable.** Plaud tokens
   stay with the Plaud CLI, Google credentials stay with Google, and OpenAI
   credentials stay in their normal stores. Pavo stores only non-secret local
   config and cache state under `~/Eidos/Pavo`.
7. **Google Drive should become the durable archive.** Pavo is the right layer
   for Drive sync because Drive is storage/orchestration. `eidos-transcribe`
   should not know about Plaud or Drive.
8. **Generic transcription misses domain terms.** Eidos recordings contain
   names, companies, project names, and invented tool names. `eidos-transcribe`
   supports context terms and context files so Pavo can pass reviewed
   vocabulary instead of trusting generic recognizer spelling.
9. **One recognizer is not enough for important audio.** Different ASR engines
   fail differently. `eidos-transcribe` can preserve raw outputs, run multiple
   engines, ensemble candidates, and record manifests showing which engines and
   context terms influenced the result.
10. **Speaker identity requires audio evidence, not guesses.** Plaud recordings
    can include multiple people, interruptions, and diarization errors.
    `eidos-transcribe` compares diarization methods, attributes transcript
    segments by audio overlap, preserves provenance, and supports explicit
    speaker mappings and signatures.
11. **Overlapping speech and noisy audio need custom handling.** Forcing mixed
    speech into one speaker creates false certainty. `eidos-transcribe` uses
    rolling acoustic fingerprinting to flag mixed speaker evidence and has a
    source-separation path for overlap regions.
12. **Better transcription needed to be updatable without rewriting Pavo.** Pavo
    calls `eidos-transcribe` as a subprocess, so the audio algorithms can be
    installed, upgraded, tested, and versioned independently while Pavo keeps
    the recording lifecycle stable.

The short version:

- **Pavo solves:** Plaud discovery, real audio download, local cache/config,
  recording manifests, future Google Drive sync, and agent/plugin routing.
- **`eidos-transcribe` solves:** multi-engine transcription, context-aware
  scoring, raw-output preservation, transcript manifests, speaker diarization,
  speaker signatures, rolling acoustic fingerprints, overlap analysis, and
  future reprocessing as models and dictionaries improve.

Read the full [backstory](docs/backstory.md) for the longer version.

The original parrot scribe mascot is preserved at
[`assets/mascot.png`](assets/mascot.png).

Pavo stores local non-secret configuration under:

```text
~/Eidos/Pavo/
```

Secrets do not belong in Pavo config. Plaud OAuth tokens remain owned by the
Plaud CLI under `~/.plaud/`, and Google/OpenAI credentials remain in their
normal credential stores.

## Install for local development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
ln -sf "$PWD/.venv/bin/pavo" ~/.local/bin/pavo
```

Install the Plaud CLI separately:

```bash
npm install -g @plaud-ai/cli
plaud login
```

## Commands

```bash
pavo init
pavo doctor
pavo config show
pavo plaud me
pavo plaud files
pavo plaud audio-url <recording-id>
pavo plaud download <recording-id>
pavo audio doctor
pavo transcribe <recording-id> --context-term Plaud
```

`pavo plaud download` writes the audio to
`~/Eidos/Pavo/cache/plaud/<recording-id>/audio.mp3` by default and prints its
SHA-256 hash.

`pavo transcribe` reuses that audio file if it already exists, or downloads it
first. It calls `eidos-transcribe` as a subprocess and writes the transcript
bundle under `~/Eidos/Pavo/cache/plaud/<recording-id>/transcribe/`. Pavo records
its own run manifest next to the audio as `pavo-transcribe-manifest.json`.

## Tests

```bash
python3 -m unittest discover -s tests
```
