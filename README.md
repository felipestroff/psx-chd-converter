# PSX CHD Converter

Windows desktop application to convert PlayStation `.cue` and `.pbp` games to `.chd` using `chdman.exe createcd` (MAME).

## Inspiration

This project started from a real need: compress PS1 games for emulators (including RetroPie), reducing storage usage on small-capacity memory cards.
In addition to storage savings with the `.chd` format, the goal was to simplify a repetitive task through batch conversion, allowing multiple ROMs to be processed in a more automatic, fast, and organized workflow.

## What's Already Implemented

- Portable executable build (no installer) via PyInstaller (`one-dir`).
- `chdman` kept in a separate folder: `tools/mame`.
- Source selection:
  - ROM folder
  - single `.cue`, `.pbp`, or supported archive file
- Compatible ROM scan:
  - lists valid `.cue` files, `.pbp` files, and supported archives
  - visually shows ignored/incompatible entries with reason
- PBP conversion flow:
  - extracts `.pbp` to temporary `.cue/.bin` using `psxtract.exe`
  - auto-detects sidecar `DOCUMENT.DAT` / `KEYS.BIN` in the same folder when available
  - converts extracted `.cue` to `.chd`
- Conversion modes:
  - single ROM (selecting one item)
  - multiple selected ROMs
  - full batch (all listed items)
- Automatic archive extraction before conversion:
  - `.zip`, `.7z`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`, `.tar.xz`, `.txz`
  - `.rar` is detected and shown as unsupported for automatic extraction
- Cancel running conversion (including queued steps).
- Conversion progress:
  - current/total considering extraction + conversion steps
  - per-item status (`Ready`, `Queued`, `Converting`, `Verified`, `Failed`, `Canceled`)
  - detailed `chdman` log with probable failure diagnosis
  - `Open log` button for a separate log window (useful on small screens)
  - completion modal/alert with default Windows sound
- Pre-conversion size estimate (current size vs estimated CHD size and estimated savings).
- Post-conversion validation via `chdman verify` with final status `Verified`.
- Configurable output:
  - same folder as source ROM (default)
  - custom output folder
- Option to overwrite existing `.chd`.
- Settings persistence:
  - last source path
  - default output path
  - overwrite option
  - recursive scan
  - window size/position

## Project Structure

```
.
├─ src/
│  ├─ main.py
│  └─ cue_chd_converter/
│     ├─ cue_parser.py
│     ├─ scanner.py
│     ├─ converter.py
│     ├─ pbp_utils.py
│     ├─ paths.py
│     ├─ models.py
│     └─ ui.py
├─ scripts/
│  ├─ run-dev.ps1
│  ├─ build.ps1
│  ├─ fetch-mame.ps1
│  ├─ fetch-psxtract.ps1
│  └─ fetch-7zip.ps1
└─ tools/
   ├─ mame/
   │  └─ README.txt
   ├─ psxtract/
   │  └─ README.txt
   └─ 7zip/
      └─ README.txt
```

## Running in Development

1. Place `chdman.exe` at `tools/mame/chdman.exe`.
2. For `.pbp` support, place `psxtract.exe` at `tools/psxtract/psxtract.exe`.
3. Run:

```powershell
python src/main.py
```

For `.7z` support in development environment:

```powershell
python -m pip install py7zr
```

Alternative without `py7zr`: place `7z.exe` at `tools/7zip/7z.exe` (or have `7z` available in system `PATH`).

## Building Portable Executable

1. `chdman.exe` is downloaded automatically if missing (`tools/mame/chdman.exe`).
2. `psxtract.exe` is downloaded automatically if missing (`tools/psxtract/psxtract.exe`).
3. Run:

```powershell
.\scripts\build.ps1
```

4. Final distribution is generated at `dist/CueChdConverter/`.

### Build with Automatic Tool Download (Official Release)

Automatically downloads:
- latest official MAME package from `https://www.mamedev.org/release.html` (`chdman.exe` + required DLLs to `tools/mame`)
- official `7zr.exe` to `tools/7zip`
- latest `psxtract` release binary to `tools/psxtract`

Then runs the build:

```powershell
.\scripts\build.ps1 -FetchMame
```

To force refresh even when `tools/mame/chdman.exe` already exists:

```powershell
.\scripts\build.ps1 -FetchMame -ForceMameRefresh
```

You can also download without building:

```powershell
.\scripts\fetch-mame.ps1 -OutputDir tools/mame
```

Download only 7-Zip without build:

```powershell
.\scripts\fetch-7zip.ps1 -OutputDir tools/7zip
```

Download only psxtract without build:

```powershell
.\scripts\fetch-psxtract.ps1 -OutputDir tools/psxtract
```

To pin a specific version using a direct URL:

```powershell
.\scripts\fetch-mame.ps1 -PackageUrl https://github.com/mamedev/mame/releases/download/mame0286/mame0286b_x64.exe
```

To force 7-Zip refresh during build:

```powershell
.\scripts\build.ps1 -FetchMame -Force7ZipRefresh
```

To force psxtract refresh during build:

```powershell
.\scripts\build.ps1 -FetchMame -ForcePsxtractRefresh
```

To force psxtract download/refresh without MAME update:

```powershell
.\scripts\build.ps1 -FetchPsxtract -ForcePsxtractRefresh
```

## Windows Compatibility

- Native UI using `tkinter/ttk` (automatic theme according to Windows).
- For **Windows 10/11**: normal build with current Python.
- For **Windows 7**: build with **Python 3.8.x (64-bit)** for better legacy compatibility in this scenario.

## Notes

- The app validates files referenced inside `.cue` before listing as compatible.
- `.pbp` conversion requires `psxtract.exe` at `tools/psxtract/psxtract.exe`.
- Non-`.cue` files or invalid `.cue` files are not listed for conversion.
- Settings are stored at `%APPDATA%\CueChdConverter\settings.json`.
- Supported archives and `.pbp` files are listed in `Compatible ROMs` and can be converted by selection or batch.

## Credits

- Developer: **Felipe Stroff**
- Contact: **stroff.felipe@gmail.com** (questions, suggestions, and contact)
- GitHub: **https://github.com/felipestroff**

## License

This project is distributed under a **non-commercial** license. Commercial use and code commercialization are prohibited without prior author permission. See [LICENSE](LICENSE).



