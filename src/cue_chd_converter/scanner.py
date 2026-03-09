from pathlib import Path
from typing import Iterable, List, Tuple

from cue_chd_converter.archive_utils import detect_archive_type
from cue_chd_converter.cue_parser import parse_cue_references
from cue_chd_converter.models import CueGame, IgnoredEntry
from cue_chd_converter.pbp_utils import is_pbp_file


def _iter_files(base: Path, recursive: bool) -> Iterable[Path]:
    if base.is_file():
        yield base
        return

    pattern = "**/*" if recursive else "*"
    for candidate in base.glob(pattern):
        if candidate.is_file():
            yield candidate


def scan_roms(path: Path, recursive: bool = False) -> Tuple[List[CueGame], List[IgnoredEntry]]:
    compatible: List[CueGame] = []
    ignored: List[IgnoredEntry] = []

    for file_path in _iter_files(path, recursive):
        if is_pbp_file(file_path):
            compatible.append(
                CueGame(
                    cue_path=file_path.resolve(),
                    referenced_files=[],
                    source_kind="pbp",
                )
            )
            continue

        if file_path.suffix.lower() != ".cue":
            archive_type = detect_archive_type(file_path)
            if archive_type is None:
                reason = "Unsupported format"
            elif archive_type == "unsupported":
                reason = "Archive detected (.rar) without automatic extraction support"
            else:
                compatible.append(
                    CueGame(
                        cue_path=file_path.resolve(),
                        referenced_files=[],
                        source_kind="archive",
                    )
                )
                continue
            ignored.append(IgnoredEntry(path=file_path, reason=reason))
            continue

        is_valid, references, reason = parse_cue_references(file_path)
        if is_valid:
            compatible.append(
                CueGame(
                    cue_path=file_path.resolve(),
                    referenced_files=references,
                    source_kind="cue",
                )
            )
        else:
            ignored.append(IgnoredEntry(path=file_path, reason=reason or "Invalid CUE"))

    compatible.sort(key=lambda item: item.display_name.lower())
    ignored.sort(key=lambda item: item.path.name.lower())
    return compatible, ignored

