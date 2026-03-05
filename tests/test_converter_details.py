import unittest
from pathlib import Path

from cue_chd_converter.converter import _build_runtime_failure_details, _infer_failure_cause
from cue_chd_converter.models import CueGame


class ConverterDetailsTests(unittest.TestCase):
    def test_infer_missing_file_cause(self) -> None:
        diagnosis, hint = _infer_failure_cause(stdout="", stderr="unable to open input file: game.bin")
        self.assertIn("missing input", diagnosis)
        self.assertIn(".cue", hint)

    def test_runtime_failure_details_contains_context(self) -> None:
        game = CueGame(cue_path=Path("C:/roms/game.cue"), referenced_files=[Path("C:/roms/game.bin")])
        details = _build_runtime_failure_details(
            game=game,
            output_path=Path("C:/roms/game.chd"),
            chdman_path=Path("C:/tools/chdman.exe"),
            command=["C:/tools/chdman.exe", "createcd", "-i", "C:/roms/game.cue", "-o", "C:/roms/game.chd"],
            return_code=1,
            stdout="",
            stderr="access is denied",
        )

        self.assertIn("[DETAILED ERROR]", details)
        self.assertIn("Return code: 1", details)
        self.assertIn("Likely diagnosis", details)
        self.assertIn("Full command", details)


if __name__ == "__main__":
    unittest.main()

