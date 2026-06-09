import json
import tempfile
import unittest
from pathlib import Path

from pavo.transcribe import (
    DecomposeAudioRequest,
    ProcessAudioRequest,
    TranscribeRequest,
    decompose_audio,
    process_audio,
    transcribe_recording,
)


class TranscribeTests(unittest.TestCase):
    def test_transcribe_recording_downloads_missing_audio_and_invokes_eidos_transcribe(self):
        calls = []

        def audio_url(recording_id):
            self.assertEqual(recording_id, "rec_123")
            return "https://example.com/audio.mp3"

        def fetcher(url):
            self.assertEqual(url, "https://example.com/audio.mp3")
            return b"audio bytes"

        def runner(args):
            calls.append(args)
            out_dir = Path(args[args.index("--out-dir") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "manifest.json").write_text("{}\n")
            return "wrote manifest\n"

        with tempfile.TemporaryDirectory() as tmp:
            request = TranscribeRequest(
                recording_id="rec_123",
                home=Path(tmp) / "Pavo",
                context_terms=["Plaud", "Pavo"],
                engines=["faster-whisper"],
            )
            result = transcribe_recording(
                request,
                audio_url=audio_url,
                fetcher=fetcher,
                runner=runner,
            )

            self.assertEqual(result.audio_path.name, "audio.mp3")
            self.assertEqual(result.audio_sha256, "ef71589075ccf9332917b0d8d711d1a8d205560f96842f9221de70e6c29454e0")
            self.assertEqual(calls[0][0:2], ["eidos-transcribe", "transcribe"])
            self.assertIn("--context-term", calls[0])
            self.assertIn("Plaud", calls[0])
            self.assertIn("Pavo", calls[0])
            self.assertTrue(result.manifest_path.exists())
            manifest = json.loads(result.manifest_path.read_text())
            self.assertEqual(manifest["recording_id"], "rec_123")
            self.assertEqual(manifest["engines"], ["faster-whisper"])
            self.assertEqual(manifest["context_terms"], ["Plaud", "Pavo"])

    def test_transcribe_recording_reuses_existing_audio(self):
        calls = []

        def audio_url(_recording_id):
            raise AssertionError("audio URL should not be requested")

        def runner(args):
            calls.append(args)
            out_dir = Path(args[args.index("--out-dir") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "manifest.json").write_text("{}\n")
            return "ok\n"

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "Pavo"
            audio_path = home / "cache" / "plaud" / "rec_123" / "audio.mp3"
            audio_path.parent.mkdir(parents=True)
            audio_path.write_bytes(b"audio bytes")
            result = transcribe_recording(
                TranscribeRequest(recording_id="rec_123", home=home),
                audio_url=audio_url,
                runner=runner,
            )

        self.assertEqual(result.audio_path, audio_path)
        self.assertEqual(len(calls), 1)

    def test_process_audio_invokes_process_call_for_imported_media(self):
        calls = []

        def runner(args):
            calls.append(args)
            out_dir = Path(args[args.index("--out-dir") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "manifest.json").write_text("{}\n")
            return "ok\n"

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "Pavo"
            audio_path = Path(tmp) / "clip.mp4"
            audio_path.write_bytes(b"video bytes")

            result = process_audio(
                ProcessAudioRequest(
                    audio_path=audio_path,
                    source_id="youtube_KxJWK8R7uVQ",
                    home=home,
                    title="When The Always Sunny Cast Met Danny DeVito",
                    context_terms=["Danny DeVito", "Conan"],
                    engines=["faster-whisper"],
                    num_speakers=4,
                    speakers=[
                        "SPEAKER_00=Conan O'Brien=conan-obrien",
                        "SPEAKER_01=Kaitlin Olson=kaitlin-olson",
                    ],
                    speaker_corrections=["00:00-00:06=SPEAKER_00"],
                ),
                runner=runner,
            )

            self.assertEqual(result.source_id, "youtube_KxJWK8R7uVQ")
            self.assertEqual(result.audio_path, audio_path.resolve())
            self.assertEqual(calls[0][0:2], ["eidos-transcribe", "process-call"])
            self.assertIn("--num-speakers", calls[0])
            self.assertIn("4", calls[0])
            self.assertIn("--speaker", calls[0])
            self.assertIn("SPEAKER_00=Conan O'Brien=conan-obrien", calls[0])
            self.assertIn("--speaker-correction", calls[0])
            self.assertIn("00:00-00:06=SPEAKER_00", calls[0])
            self.assertTrue(result.manifest_path.exists())
            manifest = json.loads(result.manifest_path.read_text())
            self.assertEqual(manifest["source_id"], "youtube_KxJWK8R7uVQ")
            self.assertEqual(manifest["title"], "When The Always Sunny Cast Met Danny DeVito")
            self.assertEqual(manifest["context_terms"], ["Danny DeVito", "Conan"])
            self.assertEqual(
                manifest["speakers"],
                [
                    "SPEAKER_00=Conan O'Brien=conan-obrien",
                    "SPEAKER_01=Kaitlin Olson=kaitlin-olson",
                ],
            )
            self.assertEqual(manifest["speaker_corrections"], ["00:00-00:06=SPEAKER_00"])

    def test_decompose_audio_invokes_voiceprint_first_pipeline(self):
        calls = []

        def runner(args):
            calls.append(args)
            out_dir = Path(args[args.index("--out-dir") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "decompose-transcribe.manifest.json").write_text("{}\n")
            return "ok\n"

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "Pavo"
            audio_path = Path(tmp) / "clip.mp4"
            audio_path.write_bytes(b"video bytes")

            result = decompose_audio(
                DecomposeAudioRequest(
                    audio_path=audio_path,
                    source_id="youtube_KxJWK8R7uVQ",
                    home=home,
                    title="Conan overlap test",
                    context_terms=["Conan", "Kaitlin"],
                    engines=["faster-whisper"],
                    num_speakers=4,
                    speakers=["SPEAKER_00=Conan O'Brien=conan-obrien"],
                    speaker_corrections=["00:00-00:06=SPEAKER_00"],
                    max_regions=5,
                    min_duration=0.25,
                ),
                runner=runner,
            )

            self.assertEqual(result.source_id, "youtube_KxJWK8R7uVQ")
            self.assertEqual(calls[0][0:2], ["eidos-transcribe", "decompose-transcribe"])
            self.assertIn("--max-regions", calls[0])
            self.assertIn("5", calls[0])
            self.assertIn("--min-duration", calls[0])
            self.assertIn("0.25", calls[0])
            self.assertTrue(result.manifest_path.exists())
            manifest = json.loads(result.manifest_path.read_text())
            self.assertEqual(manifest["source_id"], "youtube_KxJWK8R7uVQ")
            self.assertEqual(manifest["strategy"], "voiceprint-first, separation-on-demand")
            self.assertEqual(manifest["speakers"], ["SPEAKER_00=Conan O'Brien=conan-obrien"])

    def test_decompose_audio_can_include_rejected_stems_for_diagnostics(self):
        calls = []

        def runner(args):
            calls.append(args)
            out_dir = Path(args[args.index("--out-dir") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "decompose-transcribe.manifest.json").write_text("{}\n")
            return "ok\n"

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "Pavo"
            audio_path = Path(tmp) / "clip.mp4"
            audio_path.write_bytes(b"video bytes")

            result = decompose_audio(
                DecomposeAudioRequest(
                    audio_path=audio_path,
                    source_id="youtube_KxJWK8R7uVQ",
                    home=home,
                    include_rejected_stems=True,
                ),
                runner=runner,
            )

            self.assertIn("--include-rejected-stems", calls[0])
            manifest = json.loads(result.manifest_path.read_text())
            self.assertTrue(manifest["include_rejected_stems"])
