import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional, Tuple

from cue_chd_converter.models import CueGame


LogCallback = Callable[[str], None]


class ChdConverter:
    def __init__(self, chdman_path: Path):
        self.chdman_path = chdman_path

    def convert(
        self,
        game: CueGame,
        output_path: Path,
        overwrite: bool = False,
        on_log: Optional[LogCallback] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Tuple[bool, str]:
        ok, message = self.create_cd(
            game=game,
            output_path=output_path,
            overwrite=overwrite,
            on_log=on_log,
            cancel_event=cancel_event,
        )
        if not ok:
            return False, message

        if cancel_event and cancel_event.is_set():
            return False, "Conversion canceled by user"

        ok, message = self.verify_chd(
            game=game,
            output_path=output_path,
            on_log=on_log,
            cancel_event=cancel_event,
        )
        if not ok:
            return False, message

        return True, "Conversion completed and verified"

    def create_cd(
        self,
        game: CueGame,
        output_path: Path,
        overwrite: bool = False,
        on_log: Optional[LogCallback] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Tuple[bool, str]:
        chdman_check = self._ensure_chdman_available(game=game, output_path=output_path, on_log=on_log)
        if chdman_check:
            return chdman_check

        if output_path.exists() and not overwrite:
            detail = _build_precheck_failure_details(
                title="Pre-validation failure",
                game=game,
                output_path=output_path,
                chdman_path=self.chdman_path,
                reason="output file already exists",
                hint="Enable overwrite for an existing .chd file",
            )
            if on_log:
                on_log(detail)
            return False, "Pre-validation failure (output file already exists)"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        create_command = [
            str(self.chdman_path),
            "createcd",
            "-i",
            str(game.cue_path),
            "-o",
            str(output_path),
        ]
        if overwrite:
            create_command.append("-f")

        ok, message = _run_chdman_stage(
            stage_label="conversion",
            command=create_command,
            game=game,
            output_path=output_path,
            chdman_path=self.chdman_path,
            on_log=on_log,
            cancel_event=cancel_event,
        )
        if not ok:
            return False, message

        return True, "Conversion stage completed"

    def verify_chd(
        self,
        game: CueGame,
        output_path: Path,
        on_log: Optional[LogCallback] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Tuple[bool, str]:
        chdman_check = self._ensure_chdman_available(game=game, output_path=output_path, on_log=on_log)
        if chdman_check:
            return chdman_check

        if not output_path.exists() or not output_path.is_file():
            detail = _build_precheck_failure_details(
                title="Pre-validation failure",
                game=game,
                output_path=output_path,
                chdman_path=self.chdman_path,
                reason="output CHD file not found for verification",
                hint="Check conversion logs and ensure output path is writable",
            )
            if on_log:
                on_log(detail)
            return False, "Verification failed (output CHD not found)"

        verify_command = [
            str(self.chdman_path),
            "verify",
            "-i",
            str(output_path),
        ]

        ok, message = _run_chdman_stage(
            stage_label="verification",
            command=verify_command,
            game=game,
            output_path=output_path,
            chdman_path=self.chdman_path,
            on_log=on_log,
            cancel_event=cancel_event,
        )
        if not ok:
            return False, message

        return True, "Verification stage completed"

    def _ensure_chdman_available(
        self,
        game: CueGame,
        output_path: Path,
        on_log: Optional[LogCallback],
    ) -> Optional[Tuple[bool, str]]:
        if self.chdman_path.exists():
            return None

        detail = _build_precheck_failure_details(
            title="Pre-validation failure",
            game=game,
            output_path=output_path,
            chdman_path=self.chdman_path,
            reason="chdman was not found",
            hint="Place chdman.exe at tools\\mame\\chdman.exe",
        )
        if on_log:
            on_log(detail)
        return False, "Pre-validation failure (missing chdman)"


def _run_chdman_stage(
    stage_label: str,
    command: list[str],
    game: CueGame,
    output_path: Path,
    chdman_path: Path,
    on_log: Optional[LogCallback],
    cancel_event: Optional[threading.Event],
) -> Tuple[bool, str]:
    if on_log:
        on_log("Command: {0}".format(" ".join(_quote(arg) for arg in command)))

    process: Optional[subprocess.Popen[str]] = None
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        detail = _build_precheck_failure_details(
            title="Failed to start chdman {0}".format(stage_label),
            game=game,
            output_path=output_path,
            chdman_path=chdman_path,
            reason=str(exc),
            hint="Check execution permissions and MAME DLL dependencies",
        )
        if on_log:
            on_log(detail)
        return False, "Failed to start chdman {0}".format(stage_label)

    stdout, stderr, canceled = _wait_process_with_cancel(process, cancel_event)
    combined_output = "\n".join(part for part in [stdout, stderr] if part).strip()
    if combined_output and on_log:
        on_log(combined_output)

    if canceled:
        return False, "Conversion canceled by user"

    if process.returncode != 0:
        detail = _build_runtime_failure_details(
            game=game,
            output_path=output_path,
            chdman_path=chdman_path,
            command=command,
            return_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            stage_label=stage_label,
        )
        if on_log:
            on_log(detail)

        if stage_label == "verification":
            return False, "Verification failed (see log details)"
        return False, "Conversion failed (see log details)"

    return True, "OK"


def _quote(arg: str) -> str:
    if " " in arg or '"' in arg:
        return '"{0}"'.format(arg.replace('"', '\\"'))
    return arg


def _wait_process_with_cancel(
    process: subprocess.Popen[str], cancel_event: Optional[threading.Event]
) -> Tuple[str, str, bool]:
    while True:
        if cancel_event and cancel_event.is_set():
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
            return stdout, stderr, True

        try:
            stdout, stderr = process.communicate(timeout=0.2)
            return stdout, stderr, False
        except subprocess.TimeoutExpired:
            continue


def _build_precheck_failure_details(
    title: str,
    game: CueGame,
    output_path: Path,
    chdman_path: Path,
    reason: str,
    hint: str,
) -> str:
    lines = [
        "[DETAILED ERROR] {0}".format(title),
        "Game: {0}".format(game.display_name),
        "Source: {0}".format(game.cue_path),
        "Output: {0}".format(output_path),
        "chdman: {0}".format(chdman_path),
        "Cause: {0}".format(reason),
        "Suggestion: {0}".format(hint),
    ]
    return "\n".join(lines)


def _build_runtime_failure_details(
    game: CueGame,
    output_path: Path,
    chdman_path: Path,
    command: list[str],
    return_code: int,
    stdout: str,
    stderr: str,
    stage_label: str = "conversion",
) -> str:
    diagnosis, hint = _infer_failure_cause(stdout=stdout, stderr=stderr)
    lines = [
        "[DETAILED ERROR] chdman {0} failed".format(stage_label),
        "Game: {0}".format(game.display_name),
        "Source: {0}".format(game.cue_path),
        "Output: {0}".format(output_path),
        "chdman: {0}".format(chdman_path),
        "Return code: {0}".format(return_code),
        "Likely diagnosis: {0}".format(diagnosis),
        "Suggestion: {0}".format(hint),
        "Full command: {0}".format(" ".join(_quote(arg) for arg in command)),
    ]

    stderr_clean = _clean_output(stderr)
    stdout_clean = _clean_output(stdout)

    if stderr_clean:
        lines.append("STDERR:")
        lines.append(stderr_clean)
    if stdout_clean:
        lines.append("STDOUT:")
        lines.append(stdout_clean)

    return "\n".join(lines)


def _infer_failure_cause(stdout: str, stderr: str) -> Tuple[str, str]:
    merged = "{0}\n{1}".format(stdout, stderr).lower()

    if "no such file" in merged or "cannot find" in merged or "unable to open" in merged:
        return "missing input file or invalid path", "Check whether the .cue and referenced files exist"
    if "permission denied" in merged or "access is denied" in merged:
        return "permission denied while reading/writing files", "Run in a folder with write access and no lock"
    if "already exists" in merged or "file exists" in merged:
        return "output file already exists", "Enable overwrite or remove the existing .chd"
    if "unsupported" in merged or "not supported" in merged:
        return "format not supported by chdman", "Validate the .cue content and referenced tracks"
    if "out of memory" in merged:
        return "insufficient memory during conversion", "Close other programs and try again"
    if "error parsing" in merged or "parse error" in merged:
        return "malformed .cue file", "Fix the .cue file or use a different dump"
    if "crc" in merged:
        return "corrupted input data", "Extract the files again or obtain another dump"
    if "sha-1" in merged or "sha1" in merged or "checksum" in merged:
        return "integrity verification failed", "Recreate the CHD from a known-good source and verify again"
    if "dll" in merged and "not found" in merged:
        return "missing chdman dependencies", "Copy MAME DLLs together with chdman.exe"

    return "uncategorized failure returned by chdman", "Check STDERR/STDOUT above to identify the root cause"


def _clean_output(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""

    max_chars = 6000
    if len(cleaned) > max_chars:
        return "{0}\n...[output truncated to {1} characters]...".format(cleaned[:max_chars], max_chars)
    return cleaned
