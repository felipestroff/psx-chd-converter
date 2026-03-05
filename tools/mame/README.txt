Place required MAME executables for conversion here.

Expected structure:
- tools/mame/chdman.exe
- (optional) required chdman DLL files in the same folder

The application looks for `tools/mame/chdman.exe` relative to the executable.

Optionally, use:
- scripts/fetch-mame.ps1
- scripts/build.ps1 -FetchMame

to download automatically from the official MAME release.
