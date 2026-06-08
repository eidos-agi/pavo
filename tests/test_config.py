import tempfile
import unittest
from pathlib import Path

from pavo.config import init_home


class ConfigTests(unittest.TestCase):
    def test_init_home_creates_config_state_and_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Pavo"

            result = init_home(root)

            self.assertEqual(result.root, root)
            self.assertTrue((root / "config.yaml").exists())
            self.assertTrue((root / "state.yaml").exists())
            self.assertTrue((root / "cache").is_dir())
            self.assertTrue((root / "logs").is_dir())
            self.assertIn(
                "plaud_email: daniel@eidosagi.com",
                (root / "config.yaml").read_text(),
            )
            self.assertIn("last_sync_at: null", (root / "state.yaml").read_text())

    def test_init_home_does_not_overwrite_existing_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Pavo"
            root.mkdir()
            config = root / "config.yaml"
            config.write_text("custom: true\n")

            init_home(root)

            self.assertEqual(config.read_text(), "custom: true\n")
