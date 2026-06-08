from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import init_home


Runner = Callable[[list[str]], str]
Which = Callable[[str], str | None]


@dataclass(frozen=True)
class AudioDoctorResult:
    report: str
    exit_code: int


def default_runner(args: list[str]) -> str:
    completed = subprocess.run(
        args,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def run_audio_doctor(
    home: Path,
    *,
    runner: Runner = default_runner,
    which: Which = shutil.which,
) -> AudioDoctorResult:
    pavo_home = init_home(home)
    lines = [
        "pavo audio doctor",
        "",
        f"Pavo home: {pavo_home.root}",
        f"Config: {pavo_home.config_path}",
        f"State: {pavo_home.state_path}",
    ]
    exit_code = 0

    plaud_path = which("plaud")
    if not plaud_path:
        lines.extend(["Plaud CLI: missing", "Install with: npm install -g @plaud-ai/cli"])
        exit_code = 1
    else:
        lines.append(f"Plaud CLI: {plaud_path}")
        try:
            lines.append(f"Plaud version: {runner(['plaud', 'version']).strip()}")
        except Exception as exc:
            lines.append(f"Plaud version check failed: {exc}")
            exit_code = 1

    transcribe_path = which("eidos-transcribe")
    if not transcribe_path:
        lines.append("eidos-transcribe: missing")
        lines.append("Install eidos-transcribe and make it available on PATH.")
        exit_code = 1
    else:
        lines.append(f"eidos-transcribe: {transcribe_path}")
        try:
            lines.append(f"eidos-transcribe version: {runner(['eidos-transcribe', '--version']).strip()}")
        except Exception as exc:
            lines.append(f"eidos-transcribe version check failed: {exc}")
            exit_code = 1
        try:
            doctor = runner(["eidos-transcribe", "doctor"]).strip()
        except Exception as exc:
            lines.append(f"eidos-transcribe doctor unavailable: {exc}")
        else:
            lines.append("")
            lines.append(doctor)

    return AudioDoctorResult(report="\n".join(lines) + "\n", exit_code=exit_code)
