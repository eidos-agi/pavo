from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_HOME = Path.home() / "Eidos" / "Pavo"


DEFAULT_CONFIG = """account:
  plaud_email: daniel@eidosagi.com
  google_email: daniel@eidosagi.com

drive:
  root_folder_name: Eidos/Capture/Pavo
  root_folder_id: null

ingest:
  source: plaud_cli
  audio_format: mp3
  keep_local_audio: false
  verify_upload: true
"""


DEFAULT_STATE = """last_sync_at: null
known_plaud_file_ids: []
"""


@dataclass(frozen=True)
class PavoHome:
    root: Path
    config_path: Path
    state_path: Path
    cache_dir: Path
    logs_dir: Path


def home_from_arg(path: str | None = None) -> Path:
    return Path(path).expanduser() if path else DEFAULT_HOME


def init_home(root: Path = DEFAULT_HOME) -> PavoHome:
    root = root.expanduser()
    cache_dir = root / "cache"
    logs_dir = root / "logs"
    config_path = root / "config.yaml"
    state_path = root / "state.yaml"

    cache_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    if not config_path.exists():
        config_path.write_text(DEFAULT_CONFIG)
    if not state_path.exists():
        state_path.write_text(DEFAULT_STATE)

    return PavoHome(
        root=root,
        config_path=config_path,
        state_path=state_path,
        cache_dir=cache_dir,
        logs_dir=logs_dir,
    )
