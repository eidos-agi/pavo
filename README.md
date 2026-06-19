# Pavo

![Pavo logo](assets/logo.png)

**Manifest Anything.**

Pavo is a data-science-led transcription workbench for teams that need
trustworthy records from messy audio. It was inspired by Plaud workflow gaps,
but it is not a Plaud-only tool: Pavo gives operators control over real audio
files, speaker identification, custom dictionaries per call, intelligent
routing, task creation, and durable archives.

Use it when the stock transcript is not enough and the team needs a repeatable
way to improve the audio, prove who spoke, preserve the source file, and route
the resulting intelligence into real work.

## Bio-Inspired Audio Intelligence

Pavo can route captured or imported audio through `eidos-transcribe`, an
installable audio intelligence package with bio-inspired speaker analysis.

The key idea is simple: instead of trusting one transcript or one speaker label,
`eidos-transcribe` builds speaker detector banks, checks audio in rolling
windows, and lets those detectors vote on who is speaking. That immune-inspired
bootstrap process can confirm a speaker label, challenge it, or mark a segment
as mixed when the audio looks like more than one voice.

When a segment looks messy, Pavo can send it down a deeper path:

```text
source audio -> speaker fingerprints -> rolling detector votes -> overlap flags -> source-separation analysis
```

That is not a claim that Pavo currently runs genetic algorithms. The current
implementation is better described as **bio-inspired audio decomposition**:
immune-style speaker detectors, rolling acoustic fingerprints, source
separation for overlap regions, and proof manifests that show what happened.

See [proof](docs/proof.md) for current test results, media fixtures, and a real
Plaud audio transcription run.

See [media tests](docs/media-tests.md) for the real Conan overlap fixture and
the New Zealand accent/slang fixture.

See [proof matrix](docs/proof-matrix.md) for the 25-test proof plan and current
coverage status.

See [diarization direction](docs/diarization.md) for the current product
principle: detect speaker changes first, then attribute and merge.

## Why Pavo Exists

Pavo exists because high-value conversations are rarely clean. Teams capture
calls, interviews, meetings, field notes, and voice memos across tools, then
get back a transcript that may be convenient but is hard to audit, improve, or
route. Plaud was the first pain point: it captured well, but the stock workflow
did not give enough control over the underlying audio or the downstream
intelligence layer.

The larger product is for any team that wants transcription led by data
scientists instead of treated as a black box. A team needs access to the audio
itself, control over where it goes, better speaker identification,
call-specific vocabulary, source-separation checks for messy regions, and a way
to turn the recording into follow-up work.

The target loop is:

```text
recording source -> real audio -> speaker-aware transcript -> routed notes and tasks -> durable archive
```

Pavo owns ingestion wrappers, file control, routing, and the archive layer. It
can wrap Plaud CLI/MCP today, and it can also process imported local media. For
the audio intelligence layer, Pavo uses `eidos-transcribe` as an installable
package that can improve independently.

## Briefing Readout

After a batch is processed, use one command to get the operational truth:

```bash
pavo brief /path/to/meeting-batch
pavo brief /path/to/meeting-batch --review-plan
pavo brief /path/to/meeting-batch --review-plan-clips
pavo brief-apply-hints /path/to/meeting-batch /path/to/pavo-reviewed-speaker-hints.json
pavo brief-improvement baseline/pavo-meeting-brief.json current/pavo-meeting-brief.json
pavo batch doctor /path/to/meeting-batch --json \
  --report /path/to/meeting-batch/pavo-batch-doctor.json \
  --markdown-report /path/to/meeting-batch/pavo-batch-doctor.md

pavo batch verify-manifest /path/to/meeting-batch/pavo-batch-doctor.json --json \
  --markdown-report /path/to/meeting-batch/pavo-batch-manifest-verification.md

pavo batch prove /path/to/meeting-batch --json
pavo batch prove /path/to/meeting-batch --strict-complete
pavo batch decision-board /path/to/meeting-batch/pavo-batch-proof.json
pavo batch verify-decision-board /path/to/meeting-batch/pavo-batch-proof.json
pavo batch apply-decision-board-audit \
  /path/to/meeting-batch/pavo-batch-proof.json \
  /path/to/meeting-batch/pavo-batch-proof.decision-board.audit.json \
  --out /path/to/meeting-batch/pavo-batch-proof.review-slate.tsv
pavo batch finalize-board-audit \
  /path/to/meeting-batch/pavo-batch-proof.json \
  /path/to/meeting-batch/pavo-batch-proof.decision-board.audit.json
pavo batch apply-decision-slate \
  /path/to/meeting-batch/pavo-batch-proof.json \
  /path/to/meeting-batch/pavo-batch-proof.decision-slate.tsv \
  --out /path/to/meeting-batch/pavo-batch-proof.review-slate.tsv
pavo batch speaker-memory-candidates \
  /path/to/meeting-batch/pavo-batch-proof.json \
  --out /path/to/meeting-batch/pavo-speaker-memory-candidates.json
pavo batch review-pack /path/to/meeting-batch/pavo-batch-proof.json
pavo batch verify-review-pack /path/to/meeting-batch/pavo-batch-proof.json
pavo batch status /path/to/meeting-batch/pavo-batch-proof.json
pavo batch readiness /path/to/meeting-batch/pavo-batch-proof.json
pavo batch review-completion /path/to/meeting-batch/pavo-batch-proof.json
pavo batch verify-review-completion /path/to/meeting-batch/pavo-batch-proof.json
pavo batch review-sprint /path/to/meeting-batch/pavo-batch-proof.json
pavo batch verify-review-sprint /path/to/meeting-batch/pavo-batch-proof.json
pavo batch speaker-answer-sheet /path/to/meeting-batch/pavo-batch-proof.json
pavo batch verify-speaker-answer-sheet /path/to/meeting-batch/pavo-batch-proof.json
pavo batch speaker-suggestions /path/to/meeting-batch/pavo-batch-proof.json
pavo batch verify-speaker-suggestions /path/to/meeting-batch/pavo-batch-proof.json
pavo batch review-rehearsal /path/to/meeting-batch/pavo-batch-proof.json
pavo batch verify-review-rehearsal /path/to/meeting-batch/pavo-batch-proof.json
pavo batch speaker-calibration /path/to/meeting-batch/pavo-batch-proof.json
pavo batch score-speaker-agreement primary.tsv secondary.tsv
pavo batch review-cockpit /path/to/meeting-batch/pavo-batch-proof.json
pavo batch verify-review-cockpit /path/to/meeting-batch/pavo-batch-proof.json
pavo batch review-now /path/to/meeting-batch/pavo-batch-proof.json
pavo batch finalize-reviewed-proof /path/to/meeting-batch/pavo-batch-proof.json
pavo batch handoff /path/to/meeting-batch/pavo-batch-proof.json --check-validation
pavo batch handoff /path/to/meeting-batch/pavo-batch-proof.json --strict-ready
```

The brief writes `pavo-meeting-brief.json` and `pavo-meeting-brief.md` with
source counts, verification gates, a readiness score, review pressure,
speaker-confidence counts, deduped candidate work packets, next actions, resume
commands, and the privacy boundary. It is the simple front door before routing
anything into tasks or other systems.

`pavo batch doctor` is the hard coverage check for a processed meeting batch. It
proves every source recording directory has audio, transcript JSON, transcript
Markdown, diarized Markdown, speaker-attributed Markdown, README, and fetch
manifest coverage. It records byte counts and SHA-256 fingerprints for each
source artifact, plus a rollup source manifest hash for the batch. It also
fingerprints required generated outputs: the run report, meeting brief, work
JSONs, cluster gate, and cluster review bundle artifacts. By default it
refreshes the cluster gate before scoring the batch so stale review artifacts
cannot silently pass. Use `--no-refresh-cluster-gate` only when intentionally
inspecting an existing gate report. Its `passed` field means machine plumbing
is healthy. Its `complete` field remains false until downstream human speaker
review gates are actually cleared.

Use `pavo batch verify-manifest` later to re-read the doctor JSON and verify
that the source files and generated outputs still match their recorded byte
counts and SHA-256 hashes. It exits nonzero if any tracked artifact is missing
or changed.

Use `pavo batch prove` as the simple operator front door. It refreshes the
batch doctor, writes the doctor reports, verifies the manifest immediately, and
writes `pavo-batch-proof.json`, `pavo-batch-proof.md`,
`pavo-batch-proof.review-slate.tsv`, `pavo-batch-proof.decision-slate.tsv`, and
`pavo-batch-proof.review-checklist.md`. It also writes
`pavo-batch-proof.decision-board.html`, a browser review board for the grouped
decisions. The checklist and board group proof rows into the smallest pending
speaker decisions, with clips and transcript samples, so the reviewer can work
top-to-bottom without reverse-engineering the TSV. The board includes a Review
Sprint summary with estimated minutes and a focus-next-pending control for fast
auditable review. By default it exits zero
when machine proof passes. With `--strict-complete`, it exits nonzero until the
human speaker review gate is complete.

Use `pavo batch decision-board` to write a self-contained browser board for the
grouped speaker decisions again when you need to regenerate just that artifact.
It shows each decision, supporting clips and transcript samples, keyboard
shortcuts, and a generated decision TSV surface for the reviewer. It does not
write reviewed decisions by itself.

Use `pavo batch verify-decision-board` to prove the rendered board is fit for
handoff. It checks the board exists, fingerprints it, compares decision/support
counts against the proof slates, and verifies the required review controls,
autosave, audit export, and finish commands are present. It exits `3` if the
board is stale or missing required controls.

Use `pavo batch apply-decision-board-audit` when the reviewer uses the browser
board's "Download Audit JSON" button. It validates that the audit came from the
same proof packet, writes a reviewed decision slate TSV, then expands that into
the row-level proof review slate through the same gate as `apply-decision-slate`.
It does not validate or finalize speaker identity by itself.

Use `pavo batch finalize-board-audit` for the one-command path after human
review. It imports the downloaded decision-board audit JSON, validates the
review slate, materializes the speaker decisions, writes speaker memory
candidates, and reruns strict proof. It exits `3` while any reviewed board
decision remains pending.

Use `pavo batch apply-decision-slate` after editing the compact decision slate.
It expands each grouped `approved` / `rejected` / `pending` decision back onto
every supporting row in `pavo-batch-proof.review-slate.tsv`, preserving the
existing validation and finish gates instead of bypassing them.

Use `pavo batch speaker-memory-candidates` after human review has approved rows
in the proof slate. It writes reviewed speaker sample candidates grouped by
speaker, with clip/transcript/provenance fields for later enrollment or
verification. It does not create voiceprints or prove identity by itself.

Use `pavo batch review-pack` to make a portable handoff folder and zip from a
proof packet. It copies the proof JSON/Markdown, decision board, decision slate,
review slate, checklist, validation report when present, and related cluster
review pages into `pavo-batch-review-pack/`, then writes a manifest with
SHA-256 fingerprints and a README with the exact next commands. It intentionally
does not copy raw audio, signed URLs, credentials, voiceprints, or identity
approvals.

Use `pavo batch verify-review-pack` before sending or archiving a handoff pack.
It rehashes every packed artifact against the manifest, checks the review-pack
README and zip exist, verifies no raw audio files were copied, recomputes the
artifact manifest hash, and runs `verify-decision-board` against the source
proof. It exits `3` if the pack is stale, tampered, incomplete, or missing the
safe finish commands.

Use `pavo batch status` when you want the short operator answer. It uses the
same readiness engine as `pavo batch readiness`, but text output is intentionally
compact: state, machine readiness, human gate, pending decisions/clips,
estimated review minutes, the review sprint Markdown path, the browser decision
board path, the exact `finalize-board-audit` command to run after review, and
next action. It exits `0` only when strict proof is complete, `3` when machine
surfaces are healthy but human review remains, and `2` when machine repair is
needed.

Use `pavo batch readiness` as the concise operator rollup across proof, board,
review pack, validation, and human-review gates. It exits `0` only when strict
proof is complete, exits `3` when the machine surfaces are healthy but human
speaker review is still pending or ready to finalize, and exits `2` when a
machine artifact needs repair. Its JSON report includes a `review_sprint`
object with pending decisions, pending clips, estimated minutes, focus order,
and the rule that every supporting clip must be heard before identity approval.

Use `pavo batch review-sprint` to write `pavo-batch-review-sprint.json` and
`pavo-batch-review-sprint.md`, a compact reviewer packet with the same sprint
estimate, focus order, links, finish commands, and safety boundary. Review packs
generate and include these sprint files automatically.

Use `pavo batch verify-review-sprint` to prove the sprint packet is fit for
handoff. It checks the packet JSON/Markdown exist, the proof report matches,
the focus-order and clip counts agree, transcript samples are present, clip
paths exist, checklist boxes are rendered, finish commands are included, and the
identity safety boundary is present. Review-pack verification runs this gate too.

Use `pavo batch speaker-answer-sheet` to write
`pavo-batch-speaker-answer-sheet.md` and
`pavo-batch-speaker-answer-sheet.tsv`, a compact listen-and-decide sheet for the
pending grouped speaker decisions. It is sorted by the same risk-then-priority
queue as the sprint, but it removes everything except the decision question,
suggested action, evidence hints, clip checklist, allowed decision values, and
allowed review reasons. Use `pavo batch verify-speaker-answer-sheet` to prove
that this sheet exists, has the expected pending decision count, includes
review context for every row, and carries the finish command plus identity
safety boundary. Review packs generate and include these answer-sheet files
automatically.

Use `pavo batch speaker-suggestions` to write
`pavo-batch-speaker-suggestions.json`, Markdown, and TSV from the current
answer sheet. This is the machine-side review assistant: it labels each pending
speaker decision with a machine suggested decision, confidence tier, review
lane, recommended review reason, and explicit safety blockers. Every row
remains `human_required=true`; suggestions are hypotheses that speed review,
not approvals. Use `pavo batch verify-speaker-suggestions` to prove the
suggestion files exist, match the current proof report, include confidence and
review-lane labels, carry the finish command, and preserve the safety boundary.
Review packs generate and include these suggestion files automatically.

Use `pavo batch review-completion` to write
`pavo-batch-review-completion.json` and Markdown, a durable audit readout of
the remaining human-review gate. It records the reviewed, pending, and missing
reason counts, export readiness, pending decision groups, next action, and
finish commands. Use `pavo batch verify-review-completion` to prove the report
exists, matches the proof report, carries export-ready and missing-reason
fields, and preserves the identity safety boundary. Review packs generate and
include these completion files automatically.

Use `pavo batch review-rehearsal` immediately before a human listener starts.
It regenerates the decision board, review sprint, speaker answer sheet, and
review pack; verifies all of them; compares pending decision and clip counts;
extracts the first queued decision; and writes
`pavo-batch-review-rehearsal.json` plus `pavo-batch-review-rehearsal.md`. This
is a pre-review QC gate: passing rehearsal means the human review path is
coherent and ready, not that speaker identity has been approved. Use
`pavo batch verify-review-rehearsal` to check a written rehearsal report before
sending or archiving it.

Use `pavo batch speaker-calibration` to create a second-listener subset from the
speaker answer sheet. It selects the highest-risk queued speaker decisions first
and writes `pavo-batch-speaker-calibration.json`, Markdown, and TSV with
`second_listener_decision`, `second_listener_review_reason`, and notes columns.
After a second listener fills those columns, run
`pavo batch score-speaker-agreement primary.tsv secondary.tsv` to report common
decision count, agreement rate, Cohen's kappa for categorical decisions, and
the exact disagreement rows to resolve. This measures reviewer consistency; it
does not decide which speaker label is true.

Use `pavo batch review-cockpit` to render a browser-friendly one-page operator
surface for the current handoff. It shows machine readiness, human gate state,
pending decision/clip counts, the first decision to review, speaker suggestion
counts and preview rows, calibration path, artifact links, finish commands, and
the rehearsal checks. Use
`pavo batch verify-review-cockpit` before sending the page as the human-review
front door.

Use `pavo batch review-now` as the fastest safe human-review launch path. It
regenerates the sprint, speaker answer sheet, speaker suggestions, and decision
board, verifies the sprint, answer sheet, suggestions, and cockpit, checks
readiness, prints the review sprint, speaker answer sheet, speaker suggestions,
decision board, expected audit JSON path, exact
`finalize-board-audit` command, review progress percent, export readiness,
missing reason count, and next action. Add `--open-board` or `--open-sprint` when the
operator wants Pavo to open the local review surfaces directly. The sprint and
board both carry the same decision rubric: approve only when every supporting
clip matches the named speaker, reject wrong-speaker/overlap/noisy conflicts,
and keep uncertain cases pending for another listener. The board also captures a
structured `review_reason`; Pavo rejects approved/rejected board-audit imports
when that reason is missing, so final identity decisions have a defensible
human rationale. The browser board also blocks audit JSON download for final
decisions that are missing a reason, surfacing the issue before the operator
leaves the review page. Its header updates live with reviewed count, progress
percent, missing reasons, and export-ready status as the reviewer works. The
board includes one-click reasoned shortcuts such as `Approve clean`,
`Reject wrong speaker`, and `Pending uncertain`, so reviewers can make a
defensible decision without separately hunting for the matching reason code.
The review sprint also explains each pending speaker decision with a
deterministic `decision_shape`, `decision_risk`, `suggested_review_action`, and
`evidence_hints` list. These hints are guidance only: they help the reviewer
listen in the right order and know what to check, but they never approve
speaker identity without human review. The sprint JSON also exports a
`priority_queue` sorted by risk and priority score, with risk counts and
per-decision `why_queued` explanations for downstream audit and handoff.

Use `pavo batch finalize-reviewed-proof` when the proof slate has been reviewed.
It validates the proof slate, materializes the cluster decisions, writes speaker
memory candidates, and reruns batch proof in one audited command. It fails
closed while any speaker decision remains pending.

Use `pavo batch handoff` when you already have a proof packet and need to know
what to do next without re-running the batch. It reads `pavo-batch-proof.json`
and prints the review page, proof TSV, proof checklist, validate command,
finish command, strict proof command, expected pending/complete states, and
safety boundary. Add `--check-validation` to include the current proof-slate
validation report, artifact existence checks, stale-validation detection,
approved/rejected/pending counts, grouped pending speaker decisions, and
transcript samples. Add `--strict-ready` in automation: it exits `0` only when all
handoff artifacts exist, validation is fresh, and validation says the slate is
ready to finish; it exits `3` when the handoff exists but is still pending,
stale, or otherwise not ready.

When `--review-plan` is passed, Pavo also writes
`pavo-review-cluster-plan.json` and `pavo-review-cluster-plan.md`. The plan
turns speaker-review clusters into safe human review actions: identify or
enroll unknown speakers, sample low-confidence named speakers, export reviewed
corrections, and rerun attribution. It explicitly forbids mass approval of a
speaker cluster.

When `--review-plan-clips` is passed, Pavo also extracts the sampled cluster
spans into local audio clips, writes `pavo-review-cluster-clips.json`, creates
`pavo-review-cluster-sheet.json`, renders `pavo-review-cluster.html`, and builds
`pavo-review-cluster-bundle/` for localhost review.

For the newer impact-ranked cluster workflow, `pavo review clusters prepare
<batch-root>` builds the listening bundle, acoustic evidence, forecast, and
browser-safe review page. `pavo review clusters status <batch-root>` explains
what remains. `pavo review clusters doctor <batch-root>` verifies the
non-human plumbing: review sheet, page, clips, acoustic evidence, forecast,
decision slate, and finish command. Passing doctor means Pavo is operationally
ready for the required human speaker decisions; it does not mean Pavo has
approved identities by itself. To finish from a reviewed TSV, run
`pavo review clusters finish-from-slate <batch-root> <review-sheet> <slate.tsv>`.

`pavo brief-improvement` compares two meeting briefs and writes
`pavo-brief-improvement-report.json` plus Markdown. It gates on review-pressure
reduction, routeable named-span gain, readiness score, and recording parity. It
fails closed when the before/after metrics are unchanged. Generated review clips
and Pavo artifacts are excluded from source recording counts so Pavo does not
poison its own future briefs.

`pavo brief-apply-hints` converts approved reviewed speaker hints into a
`reviewed-hints.named-speaker-evidence.json` overlay under the batch `_work/`
directory. The next `pavo brief` ensembles that overlay with raw attribution,
which lets reviewed speaker decisions reduce review pressure without rewriting
source evidence.

The problems Pavo is built around:

1. **The notes were not enough.** We needed the real recording, not just a
   summary. Pavo saves the actual audio so better AI and reviewers can listen
   again.
2. **The audio was hard to control.** Recordings can live behind app, cloud,
   and tool layers. Pavo brings audio onto the computer with hashes and
   manifests so the source artifact is not lost.
3. **The account was confusing.** The Plaud login did not look like a normal
   email address. Pavo shows which Plaud account is connected before it
   downloads anything.
4. **The AI tool path was flaky.** MCP and agent tools are useful, but they
   should not be the only path. Pavo keeps a simple command-line path that
   works even when an agent integration is hidden or unavailable.
5. **Links expired.** Temporary audio links should not become the record. Pavo
   saves the file, the hash, and the manifest instead.
6. **Secrets needed boundaries.** We needed local settings without leaking
   tokens or private data. Pavo keeps settings under `~/Eidos/Pavo` and leaves
   secrets in their proper stores.
7. **Recordings needed a home.** Local cache is not enough for a durable
   archive. Pavo is being built to sync audio, notes, and manifests into Google
   Drive.
8. **AI misheard important words.** Names, companies, product names, and
   call-specific terms can sound like other words. `eidos-transcribe` lets Pavo
   pass a custom dictionary for each call so transcripts get smarter.
9. **One transcript was too fragile.** One AI model can miss things another
   model catches. `eidos-transcribe` can compare multiple engines and keep the
   evidence.
10. **Who spoke mattered.** Speaker labels are not the same as knowing the
    person. `eidos-transcribe` uses audio evidence and known speaker mappings to
    improve attribution.
11. **Messy audio needed help.** People interrupt, rooms are noisy, and speech
    overlaps. `eidos-transcribe` can flag messy regions and analyze them
    separately.
12. **The system needed to improve over time.** Pavo should not be rebuilt every
    time transcription gets better. Pavo calls `eidos-transcribe` as an
    installable package that can be upgraded.

## Problem -> Solution Visuals

Pavo starts by getting teams out of summary-only workflows and back to the real
audio file, with hashes, manifests, and durable archives.

![Audio Escape](assets/problem-solutions-v2/audio-escape.png)

The audio intelligence layer then treats speaker identification as an evidence
pipeline: fingerprints, detector votes, overlap flags, source separation, and a
named speaker transcript.

![Speaker Intelligence Pipeline](assets/problem-solutions-v2/speaker-intelligence-pipeline.png)

The final product loop turns recordings into speaker-aware transcripts, routed
notes and tasks, and a durable archive that future models can revisit.

![From Recording to Work](assets/problem-solutions-v2/recording-to-work.png)

The short version:

- **Pavo solves:** source wrapping, Plaud CLI/MCP access, real audio download,
  local file control, recording manifests, Google Drive archiving, routing,
  task creation, and agent/plugin access.
- **`eidos-transcribe` solves:** better transcription, speaker identification,
  custom dictionaries, multi-engine comparison, messy-audio analysis, and future
  reprocessing as models improve.

Read the full [backstory](docs/backstory.md) for the longer version.

The original parrot scribe mascot is preserved at
[`assets/mascot.png`](assets/mascot.png).

By default, Pavo stores local non-secret configuration under:

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
pavo meetings today
pavo meetings latest --days 7
pavo meetings fetch <recording-id> --audio --slug greenmark-call
pavo meetings process ./meetings/2026-06-18-plaud
pavo plaud me
pavo plaud files
pavo plaud audio-url <recording-id>
pavo plaud download <recording-id>
pavo audio doctor
pavo audio process ./clip.mp4 --source-id youtube_<id> --num-speakers 6 \
  --speaker "SPEAKER_00=Conan O'Brien=conan-obrien" \
  --speaker-correction "00:00-00:06=SPEAKER_00"
pavo audio decompose ./clip.mp4 --source-id youtube_<id> --num-speakers 6 \
  --speaker "SPEAKER_00=Conan O'Brien=conan-obrien"
pavo audio decompose ./clip.mp4 --source-id youtube_<id> --include-rejected-stems
pavo audio separate-overlaps youtube_<id> --start 17 --end 21 --min-duration 0.25
pavo review anchors init docs/plaud-c37-speaker1-anchor-review-clips.json
pavo review anchors corrections docs/plaud-c37-speaker1-anchor-review-sheet.json
pavo review anchors decisions docs/pavo-review-cluster-sheet.json
pavo review anchors materialize-decisions docs/pavo-review-cluster-decisions.json
pavo review clusters decision-brief ./meetings/2026-06-18-plaud/pavo-each
pavo review clusters gate ./meetings/2026-06-18-plaud/pavo-each --json \
  --report ./meetings/2026-06-18-plaud/pavo-each/pavo-cluster-review-gate.json \
  --markdown-report ./meetings/2026-06-18-plaud/pavo-each/pavo-cluster-review-gate.md
pavo video render youtube_<id> --title "Reviewed call" --duration 30
pavo transcribe <recording-id> --context-term Plaud
```

`pavo plaud download` writes the audio to
`~/Eidos/Pavo/cache/plaud/<recording-id>/audio.mp3` by default and prints its
SHA-256 hash.

`pavo transcribe` reuses that audio file if it already exists, or downloads it
first. It calls `eidos-transcribe` as a subprocess and writes the transcript
bundle under `~/Eidos/Pavo/cache/plaud/<recording-id>/transcribe/`. Pavo records
its own run manifest next to the audio as `pavo-transcribe-manifest.json`.

`pavo audio process` runs imported audio or video-derived audio through
`eidos-transcribe process-call`, including speaker analysis. It writes output to
`~/Eidos/Pavo/cache/imports/<source-id>/process-call/` and records a
`pavo-process-manifest.json` with the source file hash and command.
Pass `--speaker` only for labels you have reviewed, and use
`--speaker-correction` for trusted time ranges where a human or video frame has
confirmed the speaker.

`pavo audio decompose` runs the stronger voiceprint-first orchestration path via
`eidos-transcribe decompose-transcribe`. It writes output to
`~/Eidos/Pavo/cache/imports/<source-id>/decompose-transcribe/` and records a
`pavo-decompose-manifest.json`. The current flow builds clean speaker anchors,
voiceprints, rolling disputed-region evidence, and separation-on-demand reports.
Accepted separated stems are transcribed into evidence, but they do not
automatically replace the canonical transcript without a reviewed merge policy.

`pavo video render` burns captions into a video using the best transcript JSON
from a processed source. It prefers rolling/immune or verified named artifacts
when available, falls back to labeled speaker output, and writes
`pavo-render-manifest.json` next to the processed source so caption rendering
can avoid pretending uncertainty is certainty.

`pavo audio separate-overlaps` runs the source-separation review path for mixed
speaker regions that the rolling fingerprint marks as suspect. It writes
separated stems, a score report for each stem, and `pavo-overlap-manifest.json`.

`pavo review clusters decision-brief` writes JSON, Markdown, and a light-mode
HTML dashboard for the ranked cluster-review queue, with embedded local audio
clips, expected unlock, acoustic caution, finish commands, and browser-side
export of an import-ready reviewed TSV.

`pavo review clusters gate` is the one-command readiness check for that queue.
It refreshes the slate validation report, runs the cluster doctor, writes
machine-readable JSON and Markdown, and exits nonzero until the reviewed slate is
safe to finalize. The gate report also embeds the active-learning queue: minimum
human listens, pending clips, possible reviews saved, expected unlock,
acoustic/priority rationale, and the exact next clip/question rows. Pavo can
rank and validate the work, but it still cannot approve speaker identity without
human listening decisions in the slate.

`pavo review anchors init` creates a pending review sheet from speaker-anchor
clips. After a human marks clean rows as `approved`, `pavo review anchors
corrections` prints the exact `--speaker-correction` flags for the corrected
`pavo audio decompose` rerun.

For mixed cluster review pages from `pavo brief --review-plan-clips`, use
`pavo review anchors decisions <review-sheet>` instead. It writes a decision
report with routeable rows, enrollment candidates, pending blockers, and the
safety boundary for the next attribution pass without inventing speaker
correction flags.

After the decision report exists, `pavo review anchors materialize-decisions
<decision-report>` writes `pavo-reviewed-speaker-hints.json`,
`pavo-reviewed-speaker-enrollment.json`, and
`pavo-reviewed-speaker-rerun-plan.json`. Pending or unapproved reports fail
closed, but still write the artifacts so the next operator can see exactly what
is missing.

## Tests

```bash
python3 -m unittest discover -s tests
```
