import tempfile
import unittest
import zipfile
from pathlib import Path

from cue_chd_converter.archive_utils import detect_archive_type, extract_archive_to_workspace
from cue_chd_converter.scanner import scan_roms


class ArchiveUtilsTests(unittest.TestCase):
    def test_detect_zip_archive(self) -> None:
        archive_type = detect_archive_type(Path("game.zip"))
        self.assertEqual(archive_type, "zip")

    def test_extract_zip_and_scan_cue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "pack.zip"
            workspace = root / "workspace"

            with zipfile.ZipFile(archive, mode="w") as zipped:
                zipped.writestr("game.cue", 'FILE "game.bin" BINARY\n')
                zipped.writestr("game.bin", b"bin-data")

            ok, extracted_dir, _ = extract_archive_to_workspace(archive, workspace)

            self.assertTrue(ok)
            self.assertIsNotNone(extracted_dir)
            compatible, _ = scan_roms(extracted_dir or root, recursive=True)
            self.assertEqual(len(compatible), 1)


if __name__ == "__main__":
    unittest.main()
