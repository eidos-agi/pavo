import json
import tempfile
import unittest
from pathlib import Path

from pavo.render import RenderVideoRequest, render_video


class RenderVideoTests(unittest.TestCase):
    def test_render_video_selects_named_transcript_and_writes_manifest(self):
        calls = []

        def runner(args):
            calls.append(args)
            out_path = Path(args[args.index("--out") + 1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"captioned video")
            out_path.with_suffix(".manifest.json").write_text("{}\n")
            return "wrote video\n"

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "Pavo"
            source_dir = home / "cache" / "imports" / "youtube_123"
            process_dir = source_dir / "process-call"
            speaker_dir = process_dir / "speaker-pipeline"
            speaker_dir.mkdir(parents=True)
            audio_path = Path(tmp) / "clip.mp4"
            audio_path.write_bytes(b"video bytes")
            rolling_json = speaker_dir / "best.immune.attributed.json"
            rolling_json.write_text("[]\n")
            labeled_json = speaker_dir / "best.labeled.attributed.json"
            labeled_json.write_text("[]\n")
            speaker_manifest = speaker_dir / "speaker-pipeline.manifest.json"
            speaker_manifest.write_text(
                json.dumps(
                    {
                        "best_labeled_attributed_json": str(labeled_json),
                        "best_bridged_attributed_json": None,
                    }
                )
            )
            eidos_manifest = process_dir / "process-call.manifest.json"
            eidos_manifest.write_text(
                json.dumps(
                    {
                        "speaker_pipeline_manifest": str(speaker_manifest),
                        "best_rolling_attributed_json": str(rolling_json),
                        "best_immune_attributed_json": str(rolling_json),
                        "best_verified_attributed_json": None,
                    }
                )
            )
            (source_dir / "pavo-process-manifest.json").write_text(
                json.dumps(
                    {
                        "audio_path": str(audio_path),
                        "eidos_transcribe_manifest": str(eidos_manifest),
                    }
                )
            )

            result = render_video(
                RenderVideoRequest(
                    source_id="youtube_123",
                    home=home,
                    title="Clip",
                    portraits=["Conan O'Brien=/tmp/conan.png"],
                    duration=12,
                ),
                runner=runner,
            )

            self.assertEqual(result.transcript_json, rolling_json)
            self.assertEqual(calls[0][0:2], ["eidos-transcribe", "render-video"])
            self.assertIn("--transcript-json", calls[0])
            self.assertIn(str(rolling_json), calls[0])
            self.assertIn("--portrait", calls[0])
            self.assertIn("Conan O'Brien=/tmp/conan.png", calls[0])
            self.assertTrue(result.out_path.exists())
            manifest = json.loads(result.manifest_path.read_text())
            self.assertEqual(manifest["source_id"], "youtube_123")
            self.assertEqual(manifest["transcript_json"], str(rolling_json))
            self.assertEqual(manifest["duration"], 12)

