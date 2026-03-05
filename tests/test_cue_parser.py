import tempfile
import unittest
from pathlib import Path

from cue_chd_converter.cue_parser import parse_cue_references


class CueParserTests(unittest.TestCase):
    def test_valid_cue_with_existing_bin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bin_path = root / "game.bin"
            cue_path = root / "game.cue"

            bin_path.write_bytes(b"dummy")
            cue_path.write_text('FILE "game.bin" BINARY\n  TRACK 01 MODE2/2352\n', encoding="utf-8")

            valid, references, reason = parse_cue_references(cue_path)

            self.assertTrue(valid)
            self.assertEqual(len(references), 1)
            self.assertIsNone(reason)

    def test_invalid_when_missing_referenced_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cue_path = root / "missing.cue"
            cue_path.write_text('FILE "missing.bin" BINARY\n', encoding="utf-8")

            valid, _, reason = parse_cue_references(cue_path)

            self.assertFalse(valid)
            self.assertIn("ausentes", reason or "")


if __name__ == "__main__":
    unittest.main()
