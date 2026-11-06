#!/usr/bin/env bash
# Build the Euro Info Linux release.
#
#   ./build-linux.sh             checks, tests, app folder archive (.tar.zst)
#   ./build-linux.sh --appimage  also build a single-file AppImage
#   ./build-linux.sh --skip-tests
#
# Output in dist/:
#   Euro-Info-<version>-x86_64.tar.zst   unpacked app folder with install.sh
#   Euro-Info-<version>-x86_64.AppImage  (with --appimage)
#   SHA256SUMS-linux.txt                 checksums with plain file names
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ROOT/.venv/bin/python"
ARCH="x86_64"
BUILD="$ROOT/build-linux"
APPDIR="$BUILD/Euro-Info.AppDir"
DIST="$ROOT/dist"
WITH_APPIMAGE=0
RUN_TESTS=1
for argument in "$@"; do
    case "$argument" in
        --appimage) WITH_APPIMAGE=1 ;;
        --skip-tests) RUN_TESTS=0 ;;
        *) echo "Unknown option: $argument" >&2; exit 2 ;;
    esac
done

cd "$ROOT"
# The version has one source: euroinfo/__init__.py.
VERSION="$("$PYTHON" -c 'import re, pathlib; print(re.search(r"__version__ = \"([^\"]+)\"", pathlib.Path("euroinfo/__init__.py").read_text()).group(1))')"
ARCHIVE="Euro-Info-${VERSION}-${ARCH}.tar.zst"
APPIMAGE="Euro-Info-${VERSION}-${ARCH}.AppImage"
echo "== Euro Info ${VERSION} (${ARCH})"

echo "== Checks"
"$PYTHON" -m ruff check euroinfo tests app.py
if [[ "$RUN_TESTS" == 1 ]]; then
    QT_QPA_PLATFORM=offscreen "$PYTHON" -m unittest discover -s tests -q
fi

echo "== Clean"
rm -rf -- "$BUILD" "$ROOT/build" "$DIST/euro-info" "$DIST/$ARCHIVE" "$DIST/$APPIMAGE" "$DIST/SHA256SUMS-linux.txt"
mkdir -p "$BUILD" "$DIST"

echo "== PyInstaller"
"$PYTHON" -m PyInstaller --noconfirm --clean --log-level WARN "$ROOT/euro-info.spec"
BUNDLE="$DIST/euro-info"
[[ -x "$BUNDLE/euro-info" ]] || { echo "PyInstaller output missing: $BUNDLE/euro-info" >&2; exit 1; }

# Use the system's font libraries. Bundled copies are older than the system's
# font configuration and print a flood of "invalid constant" warnings.
find "$BUNDLE/_internal" -maxdepth 1 \( -name 'libfontconfig.so*' -o -name 'libfreetype.so*' \) -print -delete

# Qt WebEngine ships browser strings for dozens of languages; keep the eight
# the interface supports.
LOCALES="$BUNDLE/_internal/PySide6/Qt/translations/qtwebengine_locales"
if [[ -d "$LOCALES" ]]; then
    find "$LOCALES" -maxdepth 1 -name '*.pak' \
        ! -name en-US.pak ! -name en-GB.pak ! -name fr.pak ! -name de.pak ! -name it.pak \
        ! -name ro.pak ! -name pl.pak ! -name es.pak ! -name es-419.pak -delete
fi

# Qt's own interface translations: keep the seven supported languages.
find "$BUNDLE/_internal/PySide6/Qt/translations" -maxdepth 1 -name '*.qm' \
    ! -name '*_en.qm' ! -name '*_fr.qm' ! -name '*_de.qm' ! -name '*_it.qm' \
    ! -name '*_ro.qm' ! -name '*_pl.qm' ! -name '*_es.qm' -delete 2>/dev/null || true

echo "== App folder"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/metainfo" \
         "$APPDIR/usr/share/icons/hicolor/scalable/apps"
cp -a "$BUNDLE" "$APPDIR/usr/lib/euro-info"
cp assets/euro-info.svg "$APPDIR/euro-info.svg"
cp assets/euro-info.svg "$APPDIR/usr/share/icons/hicolor/scalable/apps/euro-info.svg"
cp packaging/install.sh "$APPDIR/install.sh"
cp -a plasma-widget/package "$APPDIR/plasma-widget"
chmod +x "$APPDIR/install.sh" "$APPDIR/plasma-widget/contents/code/bridge.sh"

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/euro-info/euro-info" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

cat > "$APPDIR/euro-info.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Euro Info
GenericName=European News & Weather
Comment=European news, weather and research with private local AI
Exec=euro-info
Icon=euro-info
Terminal=false
StartupNotify=true
StartupWMClass=euro-info
Categories=News;Network;Utility;
Keywords=Europe;News;Weather;RSS;Economy;Research;
EOF
cp "$APPDIR/euro-info.desktop" "$APPDIR/usr/share/applications/euro-info.desktop"

RELEASE_DATE="$(git log -1 --format=%cs 2>/dev/null || date +%F)"
cat > "$APPDIR/usr/share/metainfo/com.euroinfo.EuroInfo.metainfo.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>com.euroinfo.EuroInfo</id>
  <name>Euro Info</name>
  <summary>European news, weather and research reader</summary>
  <metadata_license>CC0-1.0</metadata_license>
  <description>
    <p>Euro Info collects curated Romanian, European, world and technology news feeds,
    weather and ECB reference rates, with a research library and private local AI analysis.</p>
  </description>
  <launchable type="desktop-id">euro-info.desktop</launchable>
  <provides><binary>euro-info</binary></provides>
  <releases><release version="${VERSION}" date="${RELEASE_DATE}"/></releases>
</component>
EOF

echo "== Self-test"
"$APPDIR/AppRun" --version
# Builds the window headless in a throwaway profile, refreshes once and checks Qt WebEngine.
QT_QPA_PLATFORM=offscreen "$APPDIR/AppRun" --self-test "$DIST/self-test-linux.json" \
    || { cat "$DIST/self-test-linux.json"; echo "Self-test failed" >&2; exit 1; }
cat "$DIST/self-test-linux.json"

echo "== Archive"
tar -C "$BUILD" --zstd -cf "$DIST/$ARCHIVE" Euro-Info.AppDir

if [[ "$WITH_APPIMAGE" == 1 ]]; then
    echo "== AppImage"
    TOOL="${XDG_CACHE_HOME:-$HOME/.cache}/euro-info/appimagetool-x86_64.AppImage"
    if [[ ! -x "$TOOL" ]]; then
        mkdir -p "$(dirname "$TOOL")"
        curl -L --fail --retry 3 -o "$TOOL" \
            "https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
        chmod +x "$TOOL"
    fi
    ln -sf euro-info.svg "$APPDIR/.DirIcon"
    ARCH="$ARCH" "$TOOL" --appimage-extract-and-run "$APPDIR" "$DIST/$APPIMAGE" >/dev/null
fi

echo "== Checksums"
(
    cd "$DIST"
    files=("$ARCHIVE")
    [[ -f "$APPIMAGE" ]] && files+=("$APPIMAGE")
    sha256sum "${files[@]}" > SHA256SUMS-linux.txt
    sha256sum -c SHA256SUMS-linux.txt
)

echo "== Done"
du -sh "$APPDIR" "$DIST"/Euro-Info-"$VERSION"-*
echo "Install with: tar --zstd -xf dist/$ARCHIVE && Euro-Info.AppDir/install.sh"
