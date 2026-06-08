import json
import tempfile
import unittest
from pathlib import Path

from pavo.transcribe import TranscribeRequest, transcribe_recording


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
