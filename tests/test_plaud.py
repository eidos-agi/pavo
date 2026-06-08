import unittest
from subprocess import CalledProcessError
from unittest.mock import patch

from pavo.plaud import PlaudCli, PlaudCliError, default_runner, extract_audio_url


class PlaudTests(unittest.TestCase):
    def test_extract_audio_url_accepts_plain_url(self):
        self.assertEqual(
            extract_audio_url("https://example.com/audio.mp3\n"),
            "https://example.com/audio.mp3",
        )

    def test_extract_audio_url_accepts_labeled_output(self):
        output = "Audio URL: https://example.com/download/audio.mp3?token=abc\n"

        self.assertEqual(
            extract_audio_url(output),
            "https://example.com/download/audio.mp3?token=abc",
        )

    def test_extract_audio_url_raises_readable_error_when_unavailable(self):
        with self.assertRaises(PlaudCliError) as raised:
            extract_audio_url("Audio not available for this recording.\n")

        self.assertIn("Audio not available", str(raised.exception))

    def test_audio_url_calls_plaud_audio_with_recording_id(self):
        calls = []

        def runner(args):
            calls.append(args)
            return "https://example.com/audio.mp3\n"

        cli = PlaudCli(runner=runner)

        self.assertEqual(cli.audio_url("rec_123"), "https://example.com/audio.mp3")
        self.assertEqual(calls, [["plaud", "audio", "rec_123"]])

    def test_default_runner_raises_readable_plaud_error(self):
        def fake_run(*args, **kwargs):
            raise CalledProcessError(
                returncode=2,
                cmd=["plaud", "me"],
                stderr="AUTH_FAILED: Run `plaud login`.",
            )

        with patch("pavo.plaud.subprocess.run", fake_run):
            with self.assertRaises(PlaudCliError) as raised:
                default_runner(["plaud", "me"])

        self.assertIn("AUTH_FAILED", str(raised.exception))
