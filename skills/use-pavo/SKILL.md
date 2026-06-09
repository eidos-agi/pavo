---
name: use-pavo
description: Use when the user asks about Pavo, Plaud recordings, Plaud CLI, Plaud MCP, real audio files, speaker identification, custom dictionaries, Pavo manifests, Google Drive sync planning, routing, or task creation from recordings.
---

# Use Pavo

Pavo is a control layer for Plaud recordings. It wraps the Plaud CLI and Plaud
MCP surfaces so agents can work with the real audio files, speaker-aware
transcripts, custom dictionaries per call, routing, task creation, and durable
archives.

## Source of Truth

Use the local Pavo CLI/package first:

```bash
pavo --help
pavo doctor
pavo config show
pavo plaud me
pavo plaud files
pavo plaud download <recording-id>
pavo audio doctor
pavo transcribe <recording-id> --context-term Plaud
```

Canonical source repo:

```text
/Users/dshanklinbv/repos-eidos-agi/pavo
```

Local non-secret config/cache root:

```text
~/Eidos/Pavo
```

## Operating Rules

- Treat original Plaud audio as the source artifact, not transcript-only data.
- Keep Plaud, Google, and OpenAI credentials in their native credential stores.
- Do not paste raw recordings, signed URLs, OAuth tokens, or voice fingerprints
  into chat, Linear, GitHub, logs, or docs.
- Keep Codex, Claude, and MCP surfaces thin; the Pavo CLI/package owns behavior.
- Prefer manifest-backed proof: command output, local file paths, hashes, and
  redacted metadata.

## Common Flows

### Check Readiness

```bash
pavo doctor
pavo audio doctor
```

### List Plaud Recordings

```bash
pavo plaud files
```

### Download Real Audio

```bash
pavo plaud download <recording-id>
```

Expected local path:

```text
~/Eidos/Pavo/cache/plaud/<recording-id>/audio.mp3
```

### Transcribe With Call-Specific Vocabulary

```bash
pavo transcribe <recording-id> --context-term Plaud --context-term Pavo
```

Expected Pavo manifest:

```text
~/Eidos/Pavo/cache/plaud/<recording-id>/pavo-transcribe-manifest.json
```

## Boundaries

Pavo may inspect local files and run local CLI commands. For external writes
such as Google Drive upload, start with dry-run or explicit user approval when
the command would create or modify remote artifacts.
