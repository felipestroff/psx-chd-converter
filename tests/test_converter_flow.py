import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cue_chd_converter.converter import ChdConverter
from cue_chd_converter.models import CueGame


class ConverterFlowTests(unittest.TestCase):
    def _build_game(self, root: Path) -> CueGame:
        cue_path = root / "game.cue"
        bin_path = root / "game.bin"
        cue_path.write_text('FILE "game.bin" BINARY\n', encoding="utf-8")
        bin_path.write_bytes(b"dummy")
        return CueGame(cue_path=cue_path, referenced_files=[bin_path])

    @patch("cue_chd_converter.converter.subprocess.Popen")
    def test_runs_verify_after_successful_create(self, mock_popen: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            chdman = root / "chdman.exe"
            chdman.write_bytes(b"")

            game = self._build_game(root)
            output_path = root / "game.chd"

            create_proc = MagicMock()

            def create_communicate(*_args, **_kwargs):
                output_path.write_bytes(b"fake-chd")
                return ("create ok", "")

            create_proc.communicate.side_effect = create_communicate
            create_proc.returncode = 0

            verify_proc = MagicMock()
            verify_proc.communicate.return_value = ("verify ok", "")
            verify_proc.returncode = 0

            mock_popen.side_effect = [create_proc, verify_proc]

            logs: list[str] = []
            ok, message = ChdConverter(chdman).convert(
                game=game,
                output_path=output_path,
                overwrite=True,
                on_log=logs.append,
            )

            self.assertTrue(ok)
            self.assertIn("verified", message.lower())
            self.assertEqual(mock_popen.call_count, 2)

            create_cmd = mock_popen.call_args_list[0].args[0]
            verify_cmd = mock_popen.call_args_list[1].args[0]
            self.assertEqual(create_cmd[1], "createcd")
            self.assertEqual(verify_cmd[1], "verify")
            self.assertEqual(verify_cmd[2], "-i")
            self.assertEqual(verify_cmd[3], str(output_path))

    @patch("cue_chd_converter.converter.subprocess.Popen")
    def test_returns_failure_when_verify_fails(self, mock_popen: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            chdman = root / "chdman.exe"
            chdman.write_bytes(b"")

            game = self._build_game(root)
            output_path = root / "game.chd"

            create_proc = MagicMock()

            def create_communicate(*_args, **_kwargs):
                output_path.write_bytes(b"fake-chd")
                return ("create ok", "")

            create_proc.communicate.side_effect = create_communicate
            create_proc.returncode = 0

            verify_proc = MagicMock()
            verify_proc.communicate.return_value = ("", "sha1 mismatch")
            verify_proc.returncode = 1

            mock_popen.side_effect = [create_proc, verify_proc]

            logs: list[str] = []
            ok, message = ChdConverter(chdman).convert(
                game=game,
                output_path=output_path,
                overwrite=True,
                on_log=logs.append,
            )

            self.assertFalse(ok)
            self.assertIn("verification failed", message.lower())
            self.assertTrue(any("chdman verification failed" in entry.lower() for entry in logs))


if __name__ == "__main__":
    unittest.main()
