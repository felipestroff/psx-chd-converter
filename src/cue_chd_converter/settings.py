import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class AppSettings:
    last_source_path: str = ""
    destination_path: str = ""
    same_folder: bool = True
    recursive_scan: bool = False
    extract_archives: bool = True
    overwrite_output: bool = False
    window_geometry: str = ""


class SettingsManager:
    def __init__(self, app_name: str = "CueChdConverter"):
        self.app_name = app_name
        self.settings_path = self._resolve_settings_path()

    def _resolve_settings_path(self) -> Path:
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / self.app_name / "settings.json"
        return Path(".") / "config" / "settings.json"

    def load(self) -> AppSettings:
        if not self.settings_path.exists():
            return AppSettings()

        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return AppSettings()

        return AppSettings(
            last_source_path=str(data.get("last_source_path", "")),
            destination_path=str(data.get("destination_path", "")),
            same_folder=bool(data.get("same_folder", True)),
            recursive_scan=bool(data.get("recursive_scan", False)),
            extract_archives=bool(data.get("extract_archives", True)),
            overwrite_output=bool(data.get("overwrite_output", False)),
            window_geometry=str(data.get("window_geometry", "")),
        )

    def save(self, settings: AppSettings) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(asdict(settings), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
