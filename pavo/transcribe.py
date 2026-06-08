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
