from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.request import urlopen


DEFAULT_COCKPIT_ROOT = Path("/Volumes/GREENMARK/Clouds/repos-greenmark-waste-solutions/greenmark-cockpit")
DEFAULT_PLAUD_BIN = Path("/Users/rentamac/.local/bin/plaud")


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""


def compact_text(value: str, *, limit: int = 2000) -> str:
    value = re.sub(r"https://\S+", "[url-redacted]", value)
    if len(value) <= limit:
        return value
    return value[:limit] + f"...[truncated {len(value) - limit} chars]"


def cockpit_root() -> Path:
    return Path(os.environ.get("GREENMARK_COCKPIT_ROOT", str(DEFAULT_COCKPIT_ROOT)))


def plaud_bin() -> str:
    return os.environ.get("PLAUD_BIN", str(DEFAULT_PLAUD_BIN))


def processing_python() -> str:
    return os.environ.get("PAVO_PYTHON", sys.executable)


def log_dir() -> Path:
    return Path(os.environ.get("PAVO_LOG_DIR", str(cockpit_root() / "logs" / "pavo")))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_audit_event(event: dict[str, object]) -> Path:
    directory = log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{date.today().isoformat()}.jsonl"
    payload = {"logged_at": utc_now(), **event}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
    return path


def audit_step(action: str, **fields: object) -> Path:
    return append_audit_event({"event": "step", "action": action, **fields})


def run_plaud(args: list[str]) -> subprocess.CompletedProcess[str]:
    started = time.monotonic()
    proc = subprocess.run(
        [plaud_bin(), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    append_audit_event(
        {
            "event": "plaud_command",
            "command": [plaud_bin(), *args],
            "exit_code": proc.returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout_preview": compact_text(proc.stdout),
            "stderr_preview": compact_text(proc.stderr),
        }
    )
    return proc


def run_logged_command(action: str, command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    started = time.monotonic()
    audit_step(f"{action}.start", command=command, cwd=str(cwd) if cwd else None)
    proc = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )
    append_audit_event(
        {
            "event": "local_command",
            "action": action,
            "command": command,
            "cwd": str(cwd) if cwd else None,
            "exit_code": proc.returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout_preview": compact_text(proc.stdout),
            "stderr_preview": compact_text(proc.stderr),
        }
    )
    audit_step(
        f"{action}.end",
        ok=proc.returncode == 0,
        exit_code=proc.returncode,
        duration_seconds=round(time.monotonic() - started, 3),
    )
    return proc


def emit_result(proc: subprocess.CompletedProcess[str], *, as_json: bool) -> int:
    if as_json:
        print(
            json.dumps(
                {
                    "ok": proc.returncode == 0,
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                },
                indent=2,
            )
        )
    else:
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)
    return proc.returncode


def meeting_dir(slug: str | None) -> Path:
    audit_step("meeting_dir.resolve.start", slug=slug)
    safe_slug = slug or "plaud-intake"
    safe_slug = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in safe_slug.lower()).strip("-")
    path = cockpit_root() / "meetings" / f"{date.today().isoformat()}-{safe_slug}"
    audit_step("meeting_dir.resolve.end", slug=slug, safe_slug=safe_slug, path=str(path))
    return path


def extract_first_url(text: str) -> str | None:
    audit_step("url.extract.start", text_length=len(text))
    match = re.search(r"https://\S+", text)
    url = match.group(0) if match else None
    audit_step("url.extract.end", found=bool(url))
    return url


def download_url(url: str, dest: Path) -> None:
    started = time.monotonic()
    audit_step("download.start", destination=str(dest))
    try:
        with urlopen(url, timeout=120) as response:
            dest.write_bytes(response.read())
    finally:
        append_audit_event(
            {
                "event": "download_url",
                "destination": str(dest),
                "exists": dest.exists(),
                "bytes": dest.stat().st_size if dest.exists() else 0,
                "duration_seconds": round(time.monotonic() - started, 3),
            }
        )


def meetings_today(*, json_output: bool = False) -> int:
    audit_step("meetings_today.start", json_output=json_output)
    proc = run_plaud(["today"])
    audit_step("meetings_today.end", ok=proc.returncode == 0, exit_code=proc.returncode)
    return emit_result(proc, as_json=json_output)


def meetings_latest(*, days: int = 7, json_output: bool = False) -> int:
    audit_step("meetings_latest.start", days=days, json_output=json_output)
    proc = run_plaud(["recent", "--days", str(days)])
    audit_step("meetings_latest.end", ok=proc.returncode == 0, exit_code=proc.returncode)
    return emit_result(proc, as_json=json_output)


def meetings_fetch(
    recording_id: str,
    *,
    audio: bool = False,
    out: Path | None = None,
    slug: str | None = None,
    json_output: bool = False,
) -> int:
    started = time.monotonic()
    audit_step(
        "meetings_fetch.start",
        recording_id=recording_id,
        out=str(out) if out else None,
        slug=slug,
        audio_requested=audio,
        json_output=json_output,
    )
    out_dir = out if out else meeting_dir(slug)
    out_dir.mkdir(parents=True, exist_ok=True)

    metadata_proc = run_plaud(["file", recording_id])
    transcript_path = out_dir / "transcript.md"
    transcript_proc = run_plaud(["transcript", recording_id, "--output", str(transcript_path)])
    transcript_available = transcript_path.exists() and "not available" not in transcript_path.read_text(errors="ignore").lower()

    audio_proc = None
    audio_path = out_dir / f"{recording_id}.mp3"
    audio_downloaded = False
    audio_error = None
    if audio:
        audio_proc = run_plaud(["audio", recording_id])
        url = extract_first_url(audio_proc.stdout)
        if url:
            try:
                download_url(url, audio_path)
                audio_downloaded = True
            except Exception as exc:  # pragma: no cover - network failure shape
                audio_error = str(exc)

    readme = out_dir / "README.md"
    if not readme.exists():
        readme.write_text(
            "\n".join(
                [
                    f"# Plaud Intake {date.today().isoformat()}",
                    "",
                    f"- Recording ID: `{recording_id}`",
                    "- Source: Plaud via `pavo meetings fetch`",
                    f"- Transcript: `{transcript_path.name}`",
                    f"- Audio: `{audio_path.name}`" if audio_downloaded else "- Audio: unavailable or not fetched",
                    "",
                    "## Next Step",
                    "",
                    "Run the Cockpit diarize workflow against `transcript.md` and update this README with decisions, action items, and follow-up work.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    ok = metadata_proc.returncode == 0 and (transcript_proc.returncode == 0 or audio_downloaded)
    summary = {
        "event": "meetings_fetch",
        "recording_id": recording_id,
        "ok": ok,
        "out_dir": str(out_dir),
        "transcript_path": str(transcript_path),
        "transcript_exists": transcript_path.exists(),
        "transcript_available": transcript_available,
        "metadata_exit_code": metadata_proc.returncode,
        "transcript_exit_code": transcript_proc.returncode,
        "audio_requested": audio,
        "audio_downloaded": audio_downloaded,
        "audio_path": str(audio_path),
        "audio_exists": audio_path.exists(),
        "audio_bytes": audio_path.stat().st_size if audio_path.exists() else 0,
        "audio_exit_code": audio_proc.returncode if audio_proc else None,
        "audio_error": audio_error,
        "duration_seconds": round(time.monotonic() - started, 3),
    }
    append_audit_event(summary)
    if json_output:
        print(json.dumps({**summary, "metadata_stdout": metadata_proc.stdout, "transcript_stdout": transcript_proc.stdout}, indent=2))
    else:
        print(f"Meeting intake folder: {out_dir}")
        if metadata_proc.stdout:
            print(metadata_proc.stdout, end="")
        if metadata_proc.stderr:
            print(metadata_proc.stderr, end="", file=sys.stderr)
        if transcript_proc.stdout:
            print(transcript_proc.stdout, end="")
        if transcript_proc.stderr:
            print(transcript_proc.stderr, end="", file=sys.stderr)
        if audio:
            if audio_downloaded:
                print(f"Audio downloaded: {audio_path}")
            elif audio_error:
                print(f"Audio download failed: {audio_error}", file=sys.stderr)
            else:
                print("Audio unavailable.")
    audit_step("meetings_fetch.end", recording_id=recording_id, ok=ok, duration_seconds=summary["duration_seconds"])
    return 0 if ok else 1


def diarize(transcript_path: Path, *, project: str = "greenmark") -> int:
    started = time.monotonic()
    audit_step("diarize.start", project=project, transcript=str(transcript_path))
    if not transcript_path.exists():
        print(f"Transcript not found: {transcript_path}", file=sys.stderr)
        audit_step("diarize.end", ok=False, project=project, reason="transcript_not_found")
        return 2

    print("Pavo prepared the transcript for Cockpit diarization.")
    print(f"Transcript: {transcript_path}")
    print("Next: run the Cockpit /diarize workflow and write decisions/action items into the meeting README.")
    append_audit_event(
        {
            "event": "diarize",
            "ok": True,
            "project": project,
            "transcript": str(transcript_path),
            "transcript_bytes": transcript_path.stat().st_size,
            "duration_seconds": round(time.monotonic() - started, 3),
        }
    )
    audit_step("diarize.end", ok=True, project=project, duration_seconds=round(time.monotonic() - started, 3))
    return 0


def meetings_process(
    recordings_root: Path,
    *,
    model: str = "mlx-community/whisper-tiny",
    suffix: str = "",
    force: bool = False,
    speakers: int = 7,
    min_duration: float = 1.2,
    skip_transcribe: bool = False,
    skip_diarize: bool = False,
    skip_attribute: bool = False,
    skip_evidence: bool = False,
    keep_going: bool = False,
    json_output: bool = False,
) -> int:
    started = time.monotonic()
    root = recordings_root
    scripts = cockpit_root() / "tools"
    rec_dirs = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")) if root.exists() else []
    mp3s = sorted(root.glob("*/*.mp3")) if root.exists() else []
    summary: dict[str, object] = {
        "ok": False,
        "recordings_root": str(root),
        "recording_dirs": len(rec_dirs),
        "mp3_count": len(mp3s),
        "steps": [],
    }
    audit_step("meetings_process.start", **summary)

    if not root.exists():
        message = f"Recordings root not found: {root}"
        print(message, file=sys.stderr)
        summary["error"] = message
        if json_output:
            print(json.dumps(summary, indent=2))
        return 2
    if not mp3s:
        message = f"No MP3 files found below {root}"
        print(message, file=sys.stderr)
        summary["error"] = message
        if json_output:
            print(json.dumps(summary, indent=2))
        return 2

    def run_step(name: str, command: list[str]) -> int:
        proc = run_logged_command(f"meetings_process.{name}", command, cwd=cockpit_root())
        step = {
            "name": name,
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout_preview": compact_text(proc.stdout, limit=1000),
            "stderr_preview": compact_text(proc.stderr, limit=1000),
        }
        steps = summary["steps"]
        assert isinstance(steps, list)
        steps.append(step)
        if not json_output:
            if proc.stdout:
                print(proc.stdout, end="")
            if proc.stderr:
                print(proc.stderr, end="", file=sys.stderr)
        return proc.returncode

    code = 0
    if not skip_transcribe:
        command = [processing_python(), str(scripts / "transcribe_plaud_recordings.py"), str(root), "--model", model]
        if suffix:
            command.extend(["--suffix", suffix])
        if force:
            command.append("--force")
        code = run_step("transcribe", command)
        if code != 0 and not keep_going:
            summary["ok"] = False
            if json_output:
                print(json.dumps(summary, indent=2))
            return code

    for enabled, name, command in [
        (
            not skip_diarize,
            "diarize",
            [
                processing_python(),
                str(scripts / "diarize_plaud_recordings.py"),
                str(root),
                "--speakers",
                str(speakers),
                "--min-duration",
                str(min_duration),
            ],
        ),
        (not skip_attribute, "attribute", [processing_python(), str(scripts / "attribute_plaud_speakers.py"), str(root)]),
        (
            not skip_evidence,
            "evidence",
            [
                processing_python(),
                str(scripts / "build_plaud_named_speaker_evidence.py"),
                str(root),
                "--output-root",
                str(root),
            ],
        ),
    ]:
        if not enabled:
            continue
        step_code = run_step(name, command)
        code = code or step_code
        if step_code != 0 and not keep_going:
            summary["ok"] = False
            if json_output:
                print(json.dumps(summary, indent=2))
            return step_code

    outputs = {
        "diarization_summary": str(root / "diarization-summary.md"),
        "speaker_characterization": str(root / "speaker-characterization.md"),
        "named_speaker_evidence": str(root / "named-speaker-evidence.md"),
        "speaker_attribution_json": str(root / "_work" / "speaker-attribution.json"),
        "named_speaker_evidence_json": str(root / "_work" / "named-speaker-evidence.json"),
    }
    summary["outputs"] = {key: {"path": value, "exists": Path(value).exists()} for key, value in outputs.items()}
    summary["ok"] = code == 0
    summary["duration_seconds"] = round(time.monotonic() - started, 3)
    append_audit_event({"event": "meetings_process", **summary})
    if json_output:
        print(json.dumps(summary, indent=2))
    elif code == 0:
        print(f"Pavo processing complete: {root}")
    return code
