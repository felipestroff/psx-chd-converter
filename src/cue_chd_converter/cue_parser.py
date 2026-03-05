import re
from pathlib import Path
from typing import List, Optional, Tuple


FILE_QUOTED_REGEX = re.compile(r'^\s*FILE\s+"(?P<name>.+?)"\s+\S+', re.IGNORECASE)
FILE_UNQUOTED_REGEX = re.compile(r"^\s*FILE\s+(?P<name>\S+)\s+\S+", re.IGNORECASE)


def parse_cue_references(cue_path: Path) -> Tuple[bool, List[Path], Optional[str]]:
    if cue_path.suffix.lower() != ".cue":
        return False, [], "File extension is not .cue"

    if not cue_path.exists() or not cue_path.is_file():
        return False, [], ".cue file was not found"

    try:
        lines = _read_cue_lines(cue_path)
    except OSError as exc:
        return False, [], "Failed to read .cue: {0}".format(exc)

    referenced_files: List[Path] = []
    for line in lines:
        match = FILE_QUOTED_REGEX.match(line) or FILE_UNQUOTED_REGEX.match(line)
        if not match:
            continue

        ref_name = match.group("name").strip()
        if not ref_name:
            continue

        referenced_files.append((cue_path.parent / ref_name).resolve())

    if not referenced_files:
        return False, [], "No FILE line found"

    missing = [str(path.name) for path in referenced_files if not path.exists()]
    if missing:
        return False, referenced_files, "Missing referenced files: {0}".format(", ".join(missing))

    return True, referenced_files, None


def _read_cue_lines(cue_path: Path) -> List[str]:
    encodings = ["utf-8-sig", "cp1252", "latin-1"]
    for encoding in encodings:
        try:
            return cue_path.read_text(encoding=encoding).splitlines()
        except UnicodeDecodeError:
            continue
    return cue_path.read_text(encoding="utf-8", errors="replace").splitlines()

