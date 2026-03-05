import hashlib
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple

from cue_chd_converter.paths import get_app_base_dir


SUPPORTED_ARCHIVE_TYPES = {
    ".zip": "zip",
    ".7z": "7z",
    ".tar": "tar",
    ".tgz": "tar",
    ".tar.gz": "tar",
    ".tbz2": "tar",
    ".tar.bz2": "tar",
    ".txz": "tar",
    ".tar.xz": "tar",
}

KNOWN_UNSUPPORTED_ARCHIVE_TYPES = {".rar"}


def detect_archive_suffix(path: Path) -> Optional[str]:
    name = path.name.lower()
    for suffix in SUPPORTED_ARCHIVE_TYPES.keys():
        if name.endswith(suffix):
            return suffix

    for suffix in KNOWN_UNSUPPORTED_ARCHIVE_TYPES:
        if name.endswith(suffix):
            return suffix

    return None


def detect_archive_type(path: Path) -> Optional[str]:
    suffix = detect_archive_suffix(path)
    if suffix is None:
        return None

    if suffix in KNOWN_UNSUPPORTED_ARCHIVE_TYPES:
        return "unsupported"

    return SUPPORTED_ARCHIVE_TYPES[suffix]


def is_archive_file(path: Path) -> bool:
    return detect_archive_type(path) is not None


def is_supported_archive(path: Path) -> bool:
    archive_type = detect_archive_type(path)
    return archive_type is not None and archive_type != "unsupported"


def extract_archive_to_workspace(
    archive_path: Path,
    workspace_root: Path,
) -> Tuple[bool, Optional[Path], str]:
    archive_type = detect_archive_type(archive_path)
    if archive_type is None:
        return False, None, "File is not an archive"

    if archive_type == "unsupported":
        return False, None, "Archive format not supported for automatic extraction (.rar)"

    workspace_root.mkdir(parents=True, exist_ok=True)
    target_dir = workspace_root / _build_archive_folder_name(archive_path)
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        if archive_type == "zip":
            _extract_zip_safely(archive_path, target_dir)
        elif archive_type == "tar":
            _extract_tar_safely(archive_path, target_dir)
        elif archive_type == "7z":
            _extract_7z_safely(archive_path, target_dir)
        else:
            return False, None, "Archive format not supported: {0}".format(archive_path.suffix)
    except Exception as exc:
        shutil.rmtree(target_dir, ignore_errors=True)
        return False, None, "Failed to extract {0}: {1}".format(archive_path.name, exc)

    return True, target_dir, "Extraction completed"


def _extract_zip_safely(archive_path: Path, target_dir: Path) -> None:
    root = target_dir.resolve()
    with zipfile.ZipFile(archive_path, mode="r") as zipped:
        for info in zipped.infolist():
            candidate = (target_dir / info.filename).resolve()
            if not _is_path_inside(candidate, root):
                raise ValueError("Invalid ZIP entry: {0}".format(info.filename))
        zipped.extractall(target_dir)


def _extract_tar_safely(archive_path: Path, target_dir: Path) -> None:
    root = target_dir.resolve()
    with tarfile.open(archive_path, mode="r:*") as tarred:
        for member in tarred.getmembers():
            candidate = (target_dir / member.name).resolve()
            if not _is_path_inside(candidate, root):
                raise ValueError("Invalid TAR entry: {0}".format(member.name))
        tarred.extractall(target_dir)


def _extract_7z_safely(archive_path: Path, target_dir: Path) -> None:
    try:
        import py7zr  # type: ignore
    except ImportError:
        _extract_7z_with_cli(archive_path, target_dir)
        return

    root = target_dir.resolve()
    with py7zr.SevenZipFile(archive_path, mode="r") as zipped:
        names: List[str] = zipped.getnames()
        for name in names:
            candidate = (target_dir / name).resolve()
            if not _is_path_inside(candidate, root):
                raise ValueError("Invalid 7z entry: {0}".format(name))
        zipped.extractall(path=target_dir)


def _extract_7z_with_cli(archive_path: Path, target_dir: Path) -> None:
    exe = _find_7z_executable()
    if not exe:
        raise RuntimeError(".7z support requires py7zr or 7z.exe (tools/7zip/7z.exe)")

    command = [str(exe), "x", str(archive_path), "-o{0}".format(target_dir), "-y"]
    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if process.returncode != 0:
        details = "\n".join(part for part in [process.stdout, process.stderr] if part).strip()
        raise RuntimeError("7z extraction failed (code {0}): {1}".format(process.returncode, details or "no details"))


def _find_7z_executable() -> Optional[Path]:
    base = get_app_base_dir()
    bundled_candidates = [
        base / "tools" / "7zip" / "7z.exe",
        base / "tools" / "7zip" / "7zr.exe",
        base / "tools" / "7z.exe",
        base / "tools" / "7zr.exe",
        base / "7z.exe",
        base / "7zr.exe",
    ]
    for candidate in bundled_candidates:
        if candidate.exists():
            return candidate

    for cmd_name in ("7z", "7zz", "7za"):
        found = shutil.which(cmd_name)
        if found:
            return Path(found)

    return None


def _is_path_inside(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _build_archive_folder_name(archive_path: Path) -> str:
    digest = hashlib.sha1(str(archive_path.resolve()).encode("utf-8")).hexdigest()[:10]
    return "{0}_{1}".format(archive_path.stem, digest)

