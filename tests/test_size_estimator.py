import tempfile
import unittest
from pathlib import Path

from cue_chd_converter.models import CueGame
from cue_chd_converter.size_estimator import (
    estimate_conversion_size,
    format_bytes,
    format_estimate_summary,
)


class SizeEstimatorTests(unittest.TestCase):
    def test_estimate_with_cue_and_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cue_path = root / "game.cue"
            bin_path = root / "game.bin"
            archive_path = root / "collection.zip"

            cue_path.write_text('FILE "game.bin" BINARY\n', encoding="utf-8")
            bin_path.write_bytes(b"A" * 1000)
            archive_path.write_bytes(b"B" * 500)

            game = CueGame(cue_path=cue_path, referenced_files=[bin_path], source_kind="cue")
            estimate = estimate_conversion_size([game], [archive_path], ratio=0.5)

            self.assertEqual(estimate.source_bytes, cue_path.stat().st_size + 1000 + 500)
            self.assertEqual(estimate.estimated_output_bytes, int(round(estimate.source_bytes * 0.5)))
            self.assertEqual(estimate.delta_bytes, estimate.source_bytes - estimate.estimated_output_bytes)

    def test_deduplicates_referenced_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shared_bin = root / "shared.bin"
            shared_bin.write_bytes(b"X" * 200)

            cue1 = root / "disc1.cue"
            cue2 = root / "disc2.cue"
            cue1.write_text('FILE "shared.bin" BINARY\n', encoding="utf-8")
            cue2.write_text('FILE "shared.bin" BINARY\n', encoding="utf-8")

            game1 = CueGame(cue_path=cue1, referenced_files=[shared_bin], source_kind="cue")
            game2 = CueGame(cue_path=cue2, referenced_files=[shared_bin], source_kind="cue")
            estimate = estimate_conversion_size([game1, game2], [], ratio=0.5)

            expected = cue1.stat().st_size + cue2.stat().st_size + shared_bin.stat().st_size
            self.assertEqual(estimate.source_bytes, expected)

    def test_formatters(self) -> None:
        self.assertEqual(format_bytes(1024), "1.00 KiB")
        summary = format_estimate_summary(
            estimate=estimate_conversion_size([], [], ratio=0.62),
            scope_label="selected items",
            contains_archives=False,
        )
        self.assertIn("no measurable source files", summary)


if __name__ == "__main__":
    unittest.main()
