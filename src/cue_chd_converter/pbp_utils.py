import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple


def is_pbp_file(path: Path) -> bool:
    return path.suffix.lower() == ".pbp"


def extract_pbp_to_workspace(
    pbp_path: Path,
    workspace_root: Path,
    psxtract_path: Path,
) -> Tuple[bool, Optional[Path], str]:
    if not is_pbp_file(pbp_path):
        return False, None, "File is not a .pbp"

    if not psxtract_path.exists():
        return False, None, "psxtract.exe was not found"

    workspace_root.mkdir(parents=True, exist_ok=True)
    target_dir = workspace_root / _build_pbp_folder_name(pbp_path)
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)

    command = [str(psxtract_path), str(pbp_path.resolve())]
    document_dat = _find_sidecar_file(pbp_path.parent, "DOCUMENT.DAT")
    keys_bin = _find_sidecar_file(pbp_path.parent, "KEYS.BIN")
    if document_dat:
        command.append(str(document_dat.resolve()))
        if keys_bin:
            command.append(str(keys_bin.resolve()))

    process = subprocess.run(
        command,
        cwd=target_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    combined_output = "\n".join(part for part in [process.stdout, process.stderr] if part).strip()

    details = _summarize_output(combined_output)

    if process.returncode != 0:
        shutil.rmtree(target_dir, ignore_errors=True)
        return False, None, "PBP extraction failed (code {0}): {1}".format(process.returncode, details)

    if _contains_psxtract_failure(combined_output):
        shutil.rmtree(target_dir, ignore_errors=True)
        return False, None, "PBP extraction failed: {0}".format(details)

    has_cue = any(candidate.suffix.lower() == ".cue" for candidate in target_dir.rglob("*") if candidate.is_file())
    if not has_cue:
        shutil.rmtree(target_dir, ignore_errors=True)
        return False, None, "PBP extraction finished, but no .cue was produced. psxtract output: {0}".format(details)

    if combined_output:
        return True, target_dir, "PBP extraction completed: {0}".format(details)

    return True, target_dir, "PBP extraction completed"


def _build_pbp_folder_name(pbp_path: Path) -> str:
    digest = hashlib.sha1(str(pbp_path.resolve()).encode("utf-8")).hexdigest()[:10]
    return "{0}_{1}".format(pbp_path.stem, digest)


def _find_sidecar_file(folder: Path, expected_name: str) -> Optional[Path]:
    direct = folder / expected_name
    if direct.is_file():
        return direct

    expected_lower = expected_name.lower()
    for candidate in folder.iterdir():
        if candidate.is_file() and candidate.name.lower() == expected_lower:
            return candidate
    return None


def _contains_psxtract_failure(output: str) -> bool:
    lowered = output.lower()
    markers = [
        "error:",
        "failed!",
        "decryption failed",
        "invalid 0x80 mac hash",
    ]
    return any(marker in lowered for marker in markers)


def _summarize_output(output: str, limit: int = 1200) -> str:
    cleaned = output.replace("\r", "").strip()
    if not cleaned:
        return "no details"

    if len(cleaned) <= limit:
        return cleaned
    return "{0}... (truncated)".format(cleaned[:limit])
