import tempfile
import unittest
from pathlib import Path

from pavo.audio import AudioDoctorResult, run_audio_doctor


class AudioDoctorTests(unittest.TestCase):
    def test_audio_doctor_checks_pavo_plaud_and_eidos_transcribe(self):
        calls = []

        def which(name):
            return f"/bin/{name}"

        def runner(args):
            calls.append(args)
            if args == ["plaud", "version"]:
                return "plaud 0.2.4\n"
            if args == ["eidos-transcribe", "--version"]:
                return "eidos-transcribe 0.1.0\n"
            if args == ["eidos-transcribe", "doctor"]:
                return "OK: baseline environment is ready.\n"
            raise AssertionError(args)

        with tempfile.TemporaryDirectory() as tmp:
            result = run_audio_doctor(Path(tmp) / "Pavo", runner=runner, which=which)

        self.assertIsInstance(result, AudioDoctorResult)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Plaud CLI: /bin/plaud", result.report)
        self.assertIn("eidos-transcribe: /bin/eidos-transcribe", result.report)
        self.assertEqual(
            calls,
            [
                ["plaud", "version"],
                ["eidos-transcribe", "--version"],
                ["eidos-transcribe", "doctor"],
            ],
        )

    def test_audio_doctor_degrades_when_eidos_doctor_is_missing(self):
        def which(name):
            return f"/bin/{name}"

        def runner(args):
            if args == ["plaud", "version"]:
                return "plaud 0.2.4\n"
            if args == ["eidos-transcribe", "--version"]:
                return "eidos-transcribe 0.1.0\n"
            if args == ["eidos-transcribe", "doctor"]:
                raise RuntimeError("invalid choice: doctor")
            raise AssertionError(args)

        with tempfile.TemporaryDirectory() as tmp:
            result = run_audio_doctor(Path(tmp) / "Pavo", runner=runner, which=which)

        self.assertEqual(result.exit_code, 0)
        self.assertIn("doctor unavailable", result.report)
