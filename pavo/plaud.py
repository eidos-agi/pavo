from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Callable


Runner = Callable[[list[str]], str]


class PlaudCliError(RuntimeError):
    pass


def default_runner(args: list[str]) -> str:
    try:
        completed = subprocess.run(
            args,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or str(exc)).strip()
        raise PlaudCliError(message) from exc
    return completed.stdout


def extract_audio_url(output: str) -> str:
    match = re.search(r"https?://\S+", output.strip())
    if not match:
        message = output.strip() or "Plaud audio command did not return a URL"
        raise PlaudCliError(message)
    return match.group(0)


@dataclass
class PlaudCli:
    runner: Runner = default_runner

    def me(self) -> str:
        return self.runner(["plaud", "me"])

    def files(self, *args: str) -> str:
        return self.runner(["plaud", "files", *args])

    def file(self, recording_id: str) -> str:
        return self.runner(["plaud", "file", recording_id])

    def audio_url(self, recording_id: str) -> str:
        return extract_audio_url(self.runner(["plaud", "audio", recording_id]))
