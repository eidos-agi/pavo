import json
import tempfile
import unittest
from pathlib import Path

from pavo.overlap import SeparateOverlapsRequest, separate_overlaps


class SeparateOverlapsTests(unittest.TestCase):
    def test_separate_overlaps_uses_rolling_transcript_and_signatures(self):
        calls = []

        def runner(args):
            calls.append(args)
            out_dir = Path(args[args.index("--out-dir") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "separate-overlaps.manifest.json").write_text("{}\n")
            return "ok\n"

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "Pavo"
            source_dir = home / "cache" / "imports" / "youtube_123"
            process_dir = source_dir / "process-call"
            speaker_dir = process_dir / "speaker-pipeline"
            speaker_dir.mkdir(parents=True)
            audio_wav = speaker_dir / "audio-16k-mono.wav"
            audio_wav.write_bytes(b"wav")
            rolling_json = speaker_dir / "best.immune.attributed.json"
            rolling_json.write_text("[]\n")
            signatures_manifest = speaker_dir / "speaker-signatures.manifest.json"
            signatures_manifest.write_text("{}\n")
            speaker_manifest = speaker_dir / "speaker-pipeline.manifest.json"
            speaker_manifest.write_text(
                json.dumps(
                    {
                        "speaker_signatures_manifest": str(signatures_manifest),
                    }
                )
            )
            process_manifest = process_dir / "process-call.manifest.json"
            process_manifest.write_text(
                json.dumps(
                    {
                        "speaker_pipeline_manifest": str(speaker_manifest),
                        "best_rolling_attributed_json": str(rolling_json),
                    }
                )
            )
            (source_dir / "pavo-process-manifest.json").write_text(
                json.dumps({"eidos_transcribe_manifest": str(process_manifest)})
            )

            result = separate_overlaps(
                SeparateOverlapsRequest(
                    source_id="youtube_123",
                    home=home,
                    max_regions=2,
                    min_duration=0.25,
                    start=17,
                    end=21,
                ),
                runner=runner,
            )

            self.assertEqual(result.audio_wav, audio_wav)
            self.assertEqual(result.transcript_json, rolling_json)
            self.assertEqual(result.signatures_manifest, signatures_manifest)
            self.assertEqual(calls[0][0:2], ["eidos-transcribe", "separate-overlaps"])
            self.assertIn("--start", calls[0])
            self.assertIn("17", calls[0])
            self.assertIn("--min-duration", calls[0])
            self.assertIn("0.25", calls[0])
            self.assertTrue(result.manifest_path.exists())
            manifest = json.loads(result.manifest_path.read_text())
            self.assertEqual(manifest["source_id"], "youtube_123")
            self.assertEqual(manifest["transcript_json"], str(rolling_json))
            self.assertEqual(manifest["min_duration"], 0.25)
