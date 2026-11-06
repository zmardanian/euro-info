# Install Euro Info

Download from [Releases](https://github.com/zmardanian/euro-info/releases/latest). Check a download with
`sha256sum -c SHA256SUMS.txt` (Linux) or `Get-FileHash` (Windows).

## Windows 10 and 11
Run `Euro-Info-<version>-windows-x64-setup.exe`. It installs for your user only (no administrator rights) into
`%LOCALAPPDATA%\Programs\Euro Info`, with a Start menu entry. Prefer no installer? Unzip
`Euro-Info-<version>-windows-x64.zip` anywhere and run `euro-info.exe`. Windows may show a SmartScreen notice
for new, unsigned apps: choose **More info → Run anyway**.

## Linux (x86_64)
```sh
tar --zstd -xf Euro-Info-<version>-x86_64.tar.zst
Euro-Info.AppDir/install.sh
```
Installs to `~/.local/opt/euro-info`, adds `euro-info` to `~/.local/bin`, a menu entry and the KDE Plasma
widget. Built on Ubuntu 22.04, so it runs on most current distributions (glibc 2.35 or newer).

## Updating
Euro Info checks GitHub once a day and shows a banner when a new version is out. Install the new download
the same way; your settings and library stay.

## Uninstalling
- Windows: Settings → Apps → Euro Info → Uninstall.
- Linux: `~/.local/opt/euro-info/install.sh --uninstall`.

Your library and settings are kept (Linux: `~/.config/euro-info`, `~/.local/share/euro-info`; Windows:
`%APPDATA%\Euro Info`, `%LOCALAPPDATA%\Euro Info`). Delete those folders to remove them too.
