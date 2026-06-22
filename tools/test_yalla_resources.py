import tempfile
import unittest
from pathlib import Path

import yalla_resources

class YallaResourcesTests(unittest.TestCase):
    def test_validate_strict(self):
        self.assertEqual(yalla_resources.validate(strict=True), 0)

    def test_generate_expected_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "generated"

            self.assertEqual(yalla_resources.generate(out), 0)

            errors = yalla_resources.verify_generated_output(out)
            self.assertEqual(errors, [])

    def test_generate_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first"
            second = Path(tmp) / "second"

            self.assertEqual(yalla_resources.generate(first), 0)
            self.assertEqual(yalla_resources.generate(second), 0)

            self.assertEqual(
                yalla_resources.tree_snapshot(first),
                yalla_resources.tree_snapshot(second),
            )

    def test_sync_directory_preserves_unrelated_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            destination.mkdir()

            (source / "img_generated.png").write_bytes(b"generated")
            (destination / "img_old.png").write_bytes(b"old")
            (destination / "manual.png").write_bytes(b"manual")
            (destination / "notes.txt").write_text("keep")

            yalla_resources.sync_directory_contents(
                source,
                destination,
                "img_*.png",
                prune=True,
            )

            self.assertTrue((destination / "img_generated.png").exists())
            self.assertFalse((destination / "img_old.png").exists())
            self.assertTrue((destination / "manual.png").exists())
            self.assertTrue((destination / "notes.txt").exists())

if __name__ == "__main__":
    unittest.main()
