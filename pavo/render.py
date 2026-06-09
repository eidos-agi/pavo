from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import DEFAULT_HOME, init_home


Runner = Callable[[list[str]], str]


@dataclass(frozen=True)
class RenderVideoRequest:
    source_id: str
    home: Path = DEFAULT_HOME
    audio_path: Path | None = None
    transcript_json: Path | None = None
    out_path: Path | None = None
    title: str | None = None
    portraits: list[str] | None = None
    width: int | None = None
    height: int | None = None
    fps: int | None = None
    start: float | None = None
    duration: float | None = None


@dataclass(frozen=True)
class RenderVideoResult:
    source_id: str
    audio_path: Path
    transcript_json: Path
    out_path: Path
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


def render_video(request: RenderVideoRequest, *, runner: Runner = default_runner) -> RenderVideoResult:
    pavo_home = init_home(request.home)
    source_dir = pavo_home.cache_dir / "imports" / request.source_id
    process_manifest_path = source_dir / "pavo-process-manifest.json"
    process_manifest = _read_json(process_manifest_path)

    audio_path = _resolve_existing_path(request.audio_path or Path(process_manifest["audio_path"]))
    transcript_json = _resolve_existing_path(
        request.transcript_json or _select_transcript_json(Path(process_manifest["eidos_transcribe_manifest"]))
    )
    out_path = (request.out_path or source_dir / "render" / "captioned.mp4").expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "eidos-transcribe",
        "render-video",
        "--audio",
        str(audio_path),
        "--transcript-json",
        str(transcript_json),
        "--out",
        str(out_path),
    ]
    for portrait in request.portraits or []:
        command.extend(["--portrait", portrait])
    if request.title:
        command.extend(["--title", request.title])
    for flag, value in [
        ("--width", request.width),
        ("--height", request.height),
        ("--fps", request.fps),
        ("--start", request.start),
        ("--duration", request.duration),
    ]:
        if value is not None:
            command.extend([flag, str(value)])

    runner(command)
    manifest_path = source_dir / "pavo-render-manifest.json"
    manifest = {
        "source_id": request.source_id,
        "audio_path": str(audio_path),
        "audio_sha256": _sha256(audio_path),
        "transcript_json": str(transcript_json),
        "output_video": str(out_path),
        "output_sha256": _sha256(out_path) if out_path.exists() else None,
        "eidos_transcribe_manifest": str(out_path.with_suffix(".manifest.json")),
        "command": command,
        "title": request.title,
        "portraits": request.portraits or [],
        "width": request.width,
        "height": request.height,
        "fps": request.fps,
        "start": request.start,
        "duration": request.duration,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return RenderVideoResult(
        source_id=request.source_id,
        audio_path=audio_path,
        transcript_json=transcript_json,
        out_path=out_path,
        manifest_path=manifest_path,
        command=command,
    )


def _select_transcript_json(process_manifest_path: Path) -> Path:
    manifest = _read_json(process_manifest_path)
    for key in [
        "best_rolling_attributed_json",
        "best_immune_attributed_json",
        "best_verified_attributed_json",
    ]:
        value = manifest.get(key)
        if value and Path(value).expanduser().exists():
            return Path(value)

    speaker_manifest_path = Path(manifest["speaker_pipeline_manifest"]).expanduser()
    speaker_manifest = _read_json(speaker_manifest_path)
    for key in [
        "best_labeled_attributed_json",
        "best_bridged_attributed_json",
    ]:
        value = speaker_manifest.get(key)
        if value and Path(value).expanduser().exists():
            return Path(value)
    raise FileNotFoundError(f"No renderable transcript JSON found in {process_manifest_path}")


def _read_json(path: Path) -> dict:
    path = _resolve_existing_path(path)
    return json.loads(path.read_text())


def _resolve_existing_path(path: Path) -> Path:
    resolved = path.expanduser()
    if not resolved.exists():
        raise FileNotFoundError(f"Path not found: {resolved}")
    return resolved


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
