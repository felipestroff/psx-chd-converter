import tempfile
import unittest
import zipfile
from pathlib import Path

from cue_chd_converter.scanner import scan_roms


class ScannerTests(unittest.TestCase):
    def test_scans_only_valid_cue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "valid.bin").write_bytes(b"bin")
            (root / "valid.cue").write_text('FILE "valid.bin" BINARY\n', encoding="utf-8")
            (root / "readme.txt").write_text("ignore", encoding="utf-8")
            (root / "broken.cue").write_text('FILE "missing.bin" BINARY\n', encoding="utf-8")

            compatible, ignored = scan_roms(root)

            self.assertEqual(len(compatible), 1)
            self.assertGreaterEqual(len(ignored), 2)

    def test_lists_supported_archive_as_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "collection.zip"
            with zipfile.ZipFile(archive_path, mode="w") as zipped:
                zipped.writestr("dummy.txt", "content")

            compatible, ignored = scan_roms(root)

            archive_entries = [entry for entry in compatible if entry.is_archive]
            self.assertEqual(len(archive_entries), 1)
            self.assertEqual(archive_entries[0].cue_path.name, "collection.zip")
            self.assertEqual(len(ignored), 0)


if __name__ == "__main__":
    unittest.main()
