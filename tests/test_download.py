import tempfile
import unittest
from pathlib import Path

from pavo.download import DownloadResult, save_audio


class DownloadTests(unittest.TestCase):
    def test_save_audio_writes_audio_and_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fetcher(url):
                self.assertEqual(url, "https://example.com/audio.mp3")
                return b"audio bytes"

            result = save_audio(
                url="https://example.com/audio.mp3",
                out_dir=Path(tmp) / "recording",
                filename="audio.mp3",
                fetcher=fetcher,
            )

            self.assertIsInstance(result, DownloadResult)
            self.assertEqual(result.path, Path(tmp) / "recording" / "audio.mp3")
            self.assertEqual(result.path.read_bytes(), b"audio bytes")
            self.assertEqual(
                result.sha256,
                "ef71589075ccf9332917b0d8d711d1a8d205560f96842f9221de70e6c29454e0",
            )
            self.assertEqual(result.size_bytes, 11)
