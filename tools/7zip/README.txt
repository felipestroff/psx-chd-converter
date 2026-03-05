Optional: place the 7-Zip extractor here to support `.7z` ROMs without depending on `py7zr`.

Expected structure:
- tools/7zip/7z.exe

If this file exists, the app uses it automatically to extract `.7z`.

You can also download automatically with:
- scripts/fetch-7zip.ps1
- scripts/build.ps1 -FetchMame
