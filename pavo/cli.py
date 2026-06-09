from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from .audio import run_audio_doctor
from .config import DEFAULT_HOME, home_from_arg, init_home
from .download import save_audio
from .plaud import PlaudCli, PlaudCliError
from .transcribe import ProcessAudioRequest, TranscribeRequest, process_audio, transcribe_recording


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pavo")
    parser.add_argument("--home", help="Override Pavo home directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create local Pavo config and state")
    subparsers.add_parser("doctor", help="Check local Pavo and Plaud readiness")

    audio = subparsers.add_parser("audio", help="Audio intelligence checks")
    audio_sub = audio.add_subparsers(dest="audio_command", required=True)
    audio_sub.add_parser("doctor", help="Check eidos-transcribe readiness")
    audio_process = audio_sub.add_parser("process", help="Process imported audio with eidos-transcribe speaker analysis")
    audio_process.add_argument("audio_path", type=Path)
    audio_process.add_argument("--source-id", required=True, help="Stable source identifier for the imported audio")
    audio_process.add_argument("--title", help="Human-readable source title")
    audio_process.add_argument("--context-term", action="append", default=[], help="Known-good term to pass to eidos-transcribe")
    audio_process.add_argument("--context-file", type=Path, help="Context file to pass to eidos-transcribe")
    audio_process.add_argument("--engine", action="append", default=[], help="ASR engine to run; repeatable. Defaults to faster-whisper.")
    audio_process.add_argument("--num-speakers", type=int, help="Expected speaker count")

    transcribe = subparsers.add_parser("transcribe", help="Transcribe a Plaud recording with eidos-transcribe")
    transcribe.add_argument("recording_id")
    transcribe.add_argument("--context-term", action="append", default=[], help="Known-good term to pass to eidos-transcribe")
    transcribe.add_argument("--context-file", type=Path, help="Context file to pass to eidos-transcribe")
    transcribe.add_argument("--engine", action="append", default=[], help="ASR engine to run; repeatable. Defaults to faster-whisper.")

    config = subparsers.add_parser("config", help="Inspect local Pavo config")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser("show", help="Print non-secret config")

    plaud = subparsers.add_parser("plaud", help="Plaud recording commands")
    plaud_sub = plaud.add_subparsers(dest="plaud_command", required=True)
    plaud_sub.add_parser("me", help="Show current Plaud account")
    plaud_sub.add_parser("files", help="List Plaud recordings")
    audio_url = plaud_sub.add_parser("audio-url", help="Print audio URL")
    audio_url.add_argument("recording_id")
    download = plaud_sub.add_parser("download", help="Download Plaud audio")
    download.add_argument("recording_id")
    download.add_argument("--out-dir", help="Override output directory")

    return parser


def run_doctor(home: Path) -> int:
    pavo_home = init_home(home)
    print(f"Pavo home: {pavo_home.root}")
    print(f"Config: {pavo_home.config_path}")
    print(f"State: {pavo_home.state_path}")

    plaud_path = shutil.which("plaud")
    if not plaud_path:
        print("Plaud CLI: missing")
        print("Install with: npm install -g @plaud-ai/cli")
        return 1

    print(f"Plaud CLI: {plaud_path}")
    try:
        output = subprocess.run(
            ["plaud", "version"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        print(f"Plaud CLI version check failed: {exc.stderr.strip()}")
        return 1
    print(f"Plaud version: {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    home = home_from_arg(args.home)

    if args.command == "init":
        pavo_home = init_home(home)
        print(f"Initialized Pavo home at {pavo_home.root}")
        return 0

    if args.command == "doctor":
        return run_doctor(home)

    if args.command == "audio":
        if args.audio_command == "doctor":
            result = run_audio_doctor(home)
            print(result.report, end="")
            return result.exit_code
        if args.audio_command == "process":
            try:
                result = process_audio(
                    ProcessAudioRequest(
                        audio_path=args.audio_path,
                        source_id=args.source_id,
                        home=home,
                        title=args.title,
                        context_terms=args.context_term,
                        context_file=args.context_file,
                        engines=args.engine or ["faster-whisper"],
                        num_speakers=args.num_speakers,
                    )
                )
            except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as exc:
                print(str(exc), file=sys.stderr)
                return 2
            print(f"source_id: {result.source_id}")
            print(f"audio_path: {result.audio_path}")
            print(f"audio_sha256: {result.audio_sha256}")
            print(f"process_output_dir: {result.output_dir}")
            print(f"manifest: {result.manifest_path}")
            return 0

    if args.command == "transcribe":
        try:
            result = transcribe_recording(
                TranscribeRequest(
                    recording_id=args.recording_id,
                    home=home,
                    context_terms=args.context_term,
                    context_file=args.context_file,
                    engines=args.engine or ["faster-whisper"],
                )
            )
        except (PlaudCliError, subprocess.CalledProcessError, RuntimeError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"audio_path: {result.audio_path}")
        print(f"audio_sha256: {result.audio_sha256}")
        print(f"transcribe_output_dir: {result.output_dir}")
        print(f"manifest: {result.manifest_path}")
        return 0

    if args.command == "config":
        pavo_home = init_home(home)
        if args.config_command == "show":
            print(pavo_home.config_path.read_text(), end="")
            return 0

    if args.command == "plaud":
        cli = PlaudCli()
        try:
            if args.plaud_command == "me":
                print(cli.me(), end="")
                return 0
            if args.plaud_command == "files":
                print(cli.files(), end="")
                return 0
            if args.plaud_command == "audio-url":
                print(cli.audio_url(args.recording_id))
                return 0
            if args.plaud_command == "download":
                pavo_home = init_home(home)
                out_dir = (
                    Path(args.out_dir).expanduser()
                    if args.out_dir
                    else pavo_home.cache_dir / "plaud" / args.recording_id
                )
                url = cli.audio_url(args.recording_id)
                result = save_audio(url=url, out_dir=out_dir)
                print(f"path: {result.path}")
                print(f"sha256: {result.sha256}")
                print(f"size_bytes: {result.size_bytes}")
                return 0
        except PlaudCliError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    parser.error("Unhandled command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
