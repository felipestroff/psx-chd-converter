import tempfile
import unittest
from pathlib import Path

from cue_chd_converter.settings import AppSettings, SettingsManager


class SettingsTests(unittest.TestCase):
    def test_save_and_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = SettingsManager()
            manager.settings_path = Path(temp_dir) / "settings.json"

            expected = AppSettings(
                last_source_path="C:/roms",
                destination_path="D:/out",
                same_folder=False,
                recursive_scan=True,
                extract_archives=True,
                overwrite_output=True,
                window_geometry="1200x700+10+10",
            )
            manager.save(expected)
            loaded = manager.load()

            self.assertEqual(loaded, expected)


if __name__ == "__main__":
    unittest.main()
