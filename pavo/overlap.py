from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import DEFAULT_HOME, init_home


Runner = Callable[[list[str]], str]


@dataclass(frozen=True)
class SeparateOverlapsRequest:
    source_id: str
    home: Path = DEFAULT_HOME
    out_dir: Path | None = None
    max_regions: int = 3
    padding: float = 1.0
    min_duration: float = 1.0
    start: float | None = None
    end: float | None = None


@dataclass(frozen=True)
class SeparateOverlapsResult:
    source_id: str
    audio_wav: Path
    transcript_json: Path
    signatures_manifest: Path
    out_dir: Path
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


def separate_overlaps(
    request: SeparateOverlapsRequest,
    *,
    runner: Runner = default_runner,
) -> SeparateOverlapsResult:
    pavo_home = init_home(request.home)
    source_dir = pavo_home.cache_dir / "imports" / request.source_id
    pavo_process_manifest = _read_json(source_dir / "pavo-process-manifest.json")
    process_manifest = _read_json(Path(pavo_process_manifest["eidos_transcribe_manifest"]))
    speaker_manifest = _read_json(Path(process_manifest["speaker_pipeline_manifest"]))

    speaker_pipeline_dir = Path(process_manifest["speaker_pipeline_manifest"]).expanduser().parent
    audio_wav = _resolve_existing_path(speaker_pipeline_dir / "audio-16k-mono.wav")
    transcript_json = _select_rolling_transcript(process_manifest, speaker_manifest)
    signatures_manifest = _resolve_existing_path(Path(speaker_manifest["speaker_signatures_manifest"]))
    out_dir = (request.out_dir or source_dir / "process-call" / "separated-overlaps").expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    command = [
        "eidos-transcribe",
        "separate-overlaps",
        "--audio-wav",
        str(audio_wav),
        "--transcript-json",
        str(transcript_json),
        "--signatures-manifest",
        str(signatures_manifest),
        "--out-dir",
        str(out_dir),
        "--max-regions",
        str(request.max_regions),
        "--padding",
        str(request.padding),
        "--min-duration",
        str(request.min_duration),
    ]
    if request.start is not None:
        command.extend(["--start", str(request.start)])
    if request.end is not None:
        command.extend(["--end", str(request.end)])

    runner(command)
    eidos_manifest = out_dir / "separate-overlaps.manifest.json"
    manifest_path = source_dir / "pavo-overlap-manifest.json"
    manifest = {
        "source_id": request.source_id,
        "audio_wav": str(audio_wav),
        "transcript_json": str(transcript_json),
        "signatures_manifest": str(signatures_manifest),
        "out_dir": str(out_dir),
        "eidos_transcribe_manifest": str(eidos_manifest),
        "command": command,
        "max_regions": request.max_regions,
        "padding": request.padding,
        "min_duration": request.min_duration,
        "start": request.start,
        "end": request.end,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return SeparateOverlapsResult(
        source_id=request.source_id,
        audio_wav=audio_wav,
        transcript_json=transcript_json,
        signatures_manifest=signatures_manifest,
        out_dir=out_dir,
        manifest_path=manifest_path,
        command=command,
    )


def _select_rolling_transcript(process_manifest: dict, speaker_manifest: dict) -> Path:
    for key in [
        "best_rolling_attributed_json",
        "best_immune_attributed_json",
        "best_verified_attributed_json",
    ]:
        value = process_manifest.get(key)
        if value and Path(value).expanduser().exists():
            return Path(value).expanduser()
    for key in [
        "best_rolling_attributed_json",
        "best_immune_attributed_json",
        "best_verified_attributed_json",
        "best_labeled_attributed_json",
    ]:
        value = speaker_manifest.get(key)
        if value and Path(value).expanduser().exists():
            return Path(value).expanduser()
    raise FileNotFoundError("No overlap-ready transcript JSON found")


def _read_json(path: Path) -> dict:
    return json.loads(_resolve_existing_path(path).read_text())


def _resolve_existing_path(path: Path) -> Path:
    resolved = path.expanduser()
    if not resolved.exists():
        raise FileNotFoundError(f"Path not found: {resolved}")
    return resolved
