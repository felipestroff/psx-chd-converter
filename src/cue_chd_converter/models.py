from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class CueGame:
    cue_path: Path
    referenced_files: List[Path]
    source_kind: str = "cue"
    archive_origin: Optional[Path] = None
    extraction_dir: Optional[Path] = None

    @property
    def display_name(self) -> str:
        return self.cue_path.stem

    @property
    def is_archive(self) -> bool:
        return self.source_kind == "archive"


@dataclass
class IgnoredEntry:
    path: Path
    reason: str
