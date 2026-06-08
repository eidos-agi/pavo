from __future__ import annotations

import hashlib
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


Fetcher = Callable[[str], bytes]


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    sha256: str
    size_bytes: int


def default_fetcher(url: str) -> bytes:
    with urllib.request.urlopen(url) as response:
        return response.read()


def save_audio(
    url: str,
    out_dir: Path,
    filename: str = "audio.mp3",
    fetcher: Fetcher = default_fetcher,
) -> DownloadResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    data = fetcher(url)
    path = out_dir / filename
    path.write_bytes(data)
    return DownloadResult(
        path=path,
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
    )
