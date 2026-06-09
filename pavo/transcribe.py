from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import DEFAULT_HOME, init_home
from .download import default_fetcher, save_audio
from .plaud import PlaudCli


Runner = Callable[[list[str]], str]
AudioUrl = Callable[[str], str]
Fetcher = Callable[[str], bytes]


@dataclass(frozen=True)
class TranscribeRequest:
    recording_id: str
    home: Path = DEFAULT_HOME
    context_terms: list[str] | None = None
    context_file: Path | None = None
    engines: list[str] | None = None


@dataclass(frozen=True)
class TranscribeResult:
    recording_id: str
    audio_path: Path
    audio_sha256: str
    output_dir: Path
    manifest_path: Path
    command: list[str]


@dataclass(frozen=True)
class ProcessAudioRequest:
    audio_path: Path
    source_id: str
    home: Path = DEFAULT_HOME
    title: str | None = None
    context_terms: list[str] | None = None
    context_file: Path | None = None
    engines: list[str] | None = None
    num_speakers: int | None = None
    speakers: list[str] | None = None
    speaker_corrections: list[str] | None = None


@dataclass(frozen=True)
class ProcessAudioResult:
    source_id: str
    audio_path: Path
    audio_sha256: str
    output_dir: Path
    manifest_path: Path
    command: list[str]


def default_runner(args: list[str]) -> str:
    completed = subprocess.run(
        args,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def transcribe_recording(
    request: TranscribeRequest,
    *,
    audio_url: AudioUrl | None = None,
    fetcher: Fetcher = default_fetcher,
    runner: Runner = default_runner,
) -> TranscribeResult:
    pavo_home = init_home(request.home)
    recording_dir = pavo_home.cache_dir / "plaud" / request.recording_id
    audio_path = recording_dir / "audio.mp3"

    if not audio_path.exists():
        url_getter = audio_url or PlaudCli().audio_url
        save_audio(
            url=url_getter(request.recording_id),
            out_dir=recording_dir,
            filename="audio.mp3",
            fetcher=fetcher,
        )

    audio_bytes = audio_path.read_bytes()
    audio_hash = __import__("hashlib").sha256(audio_bytes).hexdigest()
    output_dir = recording_dir / "transcribe"
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        "eidos-transcribe",
        "transcribe",
        str(audio_path),
        "--out-dir",
        str(output_dir),
    ]
    for engine in request.engines or ["faster-whisper"]:
        command.extend(["--engine", engine])
    for term in request.context_terms or []:
        command.extend(["--context-term", term])
    if request.context_file:
        command.extend(["--context-file", str(request.context_file.expanduser())])

    runner(command)
    manifest_path = recording_dir / "pavo-transcribe-manifest.json"
    manifest = {
        "recording_id": request.recording_id,
        "audio_path": str(audio_path),
        "audio_sha256": audio_hash,
        "transcribe_output_dir": str(output_dir),
        "eidos_transcribe_manifest": str(output_dir / "manifest.json"),
        "command": command,
        "engines": request.engines or ["faster-whisper"],
        "context_terms": request.context_terms or [],
        "context_file": str(request.context_file.expanduser()) if request.context_file else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return TranscribeResult(
        recording_id=request.recording_id,
        audio_path=audio_path,
        audio_sha256=audio_hash,
        output_dir=output_dir,
        manifest_path=manifest_path,
        command=command,
    )


def process_audio(
    request: ProcessAudioRequest,
    *,
    runner: Runner = default_runner,
) -> ProcessAudioResult:
    pavo_home = init_home(request.home)
    audio_path = request.audio_path.expanduser().resolve()
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    audio_bytes = audio_path.read_bytes()
    audio_hash = __import__("hashlib").sha256(audio_bytes).hexdigest()
    source_dir = pavo_home.cache_dir / "imports" / request.source_id
    output_dir = source_dir / "process-call"
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        "eidos-transcribe",
        "process-call",
        str(audio_path),
        "--out-dir",
        str(output_dir),
    ]
    for engine in request.engines or ["faster-whisper"]:
        command.extend(["--engine", engine])
    if request.title:
        command.extend(["--title", request.title])
    for term in request.context_terms or []:
        command.extend(["--context-term", term])
    if request.context_file:
        command.extend(["--context-file", str(request.context_file.expanduser())])
    if request.num_speakers:
        command.extend(["--num-speakers", str(request.num_speakers)])
    for speaker in request.speakers or []:
        command.extend(["--speaker", speaker])
    for correction in request.speaker_corrections or []:
        command.extend(["--speaker-correction", correction])

    runner(command)
    manifest_path = source_dir / "pavo-process-manifest.json"
    manifest = {
        "source_id": request.source_id,
        "audio_path": str(audio_path),
        "audio_sha256": audio_hash,
        "process_output_dir": str(output_dir),
        "eidos_transcribe_manifest": str(output_dir / "process-call.manifest.json"),
        "command": command,
        "engines": request.engines or ["faster-whisper"],
        "title": request.title,
        "context_terms": request.context_terms or [],
        "context_file": str(request.context_file.expanduser()) if request.context_file else None,
        "num_speakers": request.num_speakers,
        "speakers": request.speakers or [],
        "speaker_corrections": request.speaker_corrections or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return ProcessAudioResult(
        source_id=request.source_id,
        audio_path=audio_path,
        audio_sha256=audio_hash,
        output_dir=output_dir,
        manifest_path=manifest_path,
        command=command,
    )
