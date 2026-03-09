import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cue_chd_converter.pbp_utils import extract_pbp_to_workspace, is_pbp_file


class PbpUtilsTests(unittest.TestCase):
    def test_is_pbp_file(self) -> None:
        self.assertTrue(is_pbp_file(Path("game.pbp")))
        self.assertTrue(is_pbp_file(Path("GAME.PBP")))
        self.assertFalse(is_pbp_file(Path("game.cue")))

    def test_extract_rejects_non_pbp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_file = root / "game.cue"
            fake_file.write_text("dummy", encoding="utf-8")
            workspace = root / "workspace"
            missing_psxtract = root / "psxtract.exe"

            ok, extracted_dir, message = extract_pbp_to_workspace(
                pbp_path=fake_file,
                workspace_root=workspace,
                psxtract_path=missing_psxtract,
            )

            self.assertFalse(ok)
            self.assertIsNone(extracted_dir)
            self.assertIn("not a .pbp", message)

    def test_extract_requires_psxtract_binary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pbp_file = root / "game.pbp"
            pbp_file.write_bytes(b"PBP")
            workspace = root / "workspace"
            missing_psxtract = root / "psxtract.exe"

            ok, extracted_dir, message = extract_pbp_to_workspace(
                pbp_path=pbp_file,
                workspace_root=workspace,
                psxtract_path=missing_psxtract,
            )

            self.assertFalse(ok)
            self.assertIsNone(extracted_dir)
            self.assertIn("psxtract.exe was not found", message)

    @patch("cue_chd_converter.pbp_utils.subprocess.run")
    def test_extract_detects_failure_marker_even_with_zero_exit(self, mocked_run) -> None:
        mocked_run.return_value = subprocess.CompletedProcess(
            args=["psxtract"],
            returncode=0,
            stdout="ERROR: ISO header decryption failed!",
            stderr="",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pbp_file = root / "game.pbp"
            pbp_file.write_bytes(b"PBP")
            workspace = root / "workspace"
            psxtract = root / "psxtract.exe"
            psxtract.write_bytes(b"EXE")

            ok, extracted_dir, message = extract_pbp_to_workspace(
                pbp_path=pbp_file,
                workspace_root=workspace,
                psxtract_path=psxtract,
            )

            self.assertFalse(ok)
            self.assertIsNone(extracted_dir)
            self.assertIn("PBP extraction failed", message)
            self.assertIn("decryption failed", message.lower())

    @patch("cue_chd_converter.pbp_utils.subprocess.run")
    def test_extract_reports_output_when_no_cue_is_created(self, mocked_run) -> None:
        mocked_run.return_value = subprocess.CompletedProcess(
            args=["psxtract"],
            returncode=0,
            stdout="Single disc game detected!",
            stderr="",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pbp_file = root / "game.pbp"
            pbp_file.write_bytes(b"PBP")
            workspace = root / "workspace"
            psxtract = root / "psxtract.exe"
            psxtract.write_bytes(b"EXE")

            ok, extracted_dir, message = extract_pbp_to_workspace(
                pbp_path=pbp_file,
                workspace_root=workspace,
                psxtract_path=psxtract,
            )

            self.assertFalse(ok)
            self.assertIsNone(extracted_dir)
            self.assertIn("no .cue was produced", message.lower())
            self.assertIn("Single disc game detected!", message)

    @patch("cue_chd_converter.pbp_utils.subprocess.run")
    def test_extract_uses_document_and_keys_sidecars(self, mocked_run) -> None:
        def run_side_effect(command, cwd, **kwargs):
            cue_file = Path(cwd) / "disc.cue"
            cue_file.write_text('FILE "disc.bin" BINARY\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="ok", stderr="")

        mocked_run.side_effect = run_side_effect

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pbp_file = root / "game.pbp"
            pbp_file.write_bytes(b"PBP")
            document = root / "DOCUMENT.DAT"
            document.write_bytes(b"DOC")
            keys = root / "KEYS.BIN"
            keys.write_bytes(b"KEY")
            workspace = root / "workspace"
            psxtract = root / "psxtract.exe"
            psxtract.write_bytes(b"EXE")

            ok, extracted_dir, message = extract_pbp_to_workspace(
                pbp_path=pbp_file,
                workspace_root=workspace,
                psxtract_path=psxtract,
            )

            self.assertTrue(ok)
            self.assertIsNotNone(extracted_dir)
            self.assertIn("completed", message.lower())

            used_command = mocked_run.call_args.args[0]
            self.assertIn(str(document.resolve()), used_command)
            self.assertIn(str(keys.resolve()), used_command)


if __name__ == "__main__":
    unittest.main()
