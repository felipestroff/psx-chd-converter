from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from cue_chd_converter.models import CueGame


DEFAULT_ESTIMATED_CHD_RATIO = 0.62


@dataclass(frozen=True)
class SizeEstimate:
    source_bytes: int
    estimated_output_bytes: int
    delta_bytes: int
    ratio: float


def estimate_conversion_size(
    games: Sequence[CueGame],
    archive_paths: Sequence[Path],
    ratio: float = DEFAULT_ESTIMATED_CHD_RATIO,
) -> SizeEstimate:
    if ratio <= 0.0:
        raise ValueError("ratio must be greater than 0")

    source_bytes = 0
    seen = set()

    for game in games:
        if game.is_archive:
            continue

        source_bytes += _add_unique_file_size(game.cue_path, seen)
        for referenced in game.referenced_files:
            source_bytes += _add_unique_file_size(referenced, seen)

    for archive_path in archive_paths:
        source_bytes += _add_unique_file_size(archive_path, seen)

    estimated_output = int(round(float(source_bytes) * ratio)) if source_bytes else 0
    if source_bytes > 0 and estimated_output <= 0:
        estimated_output = 1

    delta = source_bytes - estimated_output
    return SizeEstimate(
        source_bytes=source_bytes,
        estimated_output_bytes=estimated_output,
        delta_bytes=delta,
        ratio=ratio,
    )


def format_bytes(size_bytes: int) -> str:
    if size_bytes < 0:
        return "-{0}".format(format_bytes(-size_bytes))

    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(size_bytes)
    unit_index = 0
    while value >= 1024.0 and unit_index < len(units) - 1:
        value /= 1024.0
        unit_index += 1

    if unit_index == 0:
        return "{0} {1}".format(int(value), units[unit_index])
    return "{0:.2f} {1}".format(value, units[unit_index])


def format_estimate_summary(
    estimate: SizeEstimate,
    scope_label: str,
    contains_archives: bool,
) -> str:
    if estimate.source_bytes <= 0:
        return "Estimate ({0}): no measurable source files.".format(scope_label)

    if estimate.delta_bytes >= 0:
        delta_text = "Estimated savings: {0}".format(format_bytes(estimate.delta_bytes))
    else:
        delta_text = "Estimated growth: {0}".format(format_bytes(-estimate.delta_bytes))

    ratio_percent = estimate.ratio * 100.0
    text = (
        "Estimate ({0}) -> Source: {1} | Est. CHD: {2} | {3} "
        "(ratio {4:.0f}% of source)"
    ).format(
        scope_label,
        format_bytes(estimate.source_bytes),
        format_bytes(estimate.estimated_output_bytes),
        delta_text,
        ratio_percent,
    )

    if contains_archives:
        return "{0}. Archive-based estimates are approximate.".format(text)
    return text


def _add_unique_file_size(path: Path, seen: set[str]) -> int:
    key = _path_key(path)
    if key in seen:
        return 0

    seen.add(key)
    if not path.exists() or not path.is_file():
        return 0

    try:
        return path.stat().st_size
    except OSError:
        return 0


def _path_key(path: Path) -> str:
    try:
        return str(path.resolve()).lower()
    except OSError:
        return str(path).lower()
