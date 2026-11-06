#!/usr/bin/env bash
# Install Euro Info for the current user (no root needed).
#
#   ./install.sh              install or upgrade
#   ./install.sh --uninstall  remove the app (your library and settings stay)
#
# The app goes to ~/.local/opt/euro-info and starts from the menu, from
# `euro-info` in a terminal, and from the KDE Plasma widget.
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
PREFIX="${EURO_INFO_PREFIX:-$HOME/.local/opt/euro-info}"
BIN="$HOME/.local/bin"
APPLICATIONS="$DATA/applications"
ICONS="$DATA/icons/hicolor/scalable/apps"
WIDGET_ID="com.alexpetre.euroinfo"
WIDGET_DIR="$DATA/plasma/plasmoids/$WIDGET_ID"

uninstall() {
    rm -rf -- "$PREFIX" "$WIDGET_DIR"
    rm -f -- "$BIN/euro-info" "$APPLICATIONS/euro-info.desktop" "$ICONS/euro-info.svg"
    command -v update-desktop-database >/dev/null && update-desktop-database "$APPLICATIONS" 2>/dev/null || true
    echo "Euro Info removed. Your library and settings are kept in ~/.local/share/euro-info and ~/.config/euro-info."
}

if [[ "${1:-}" == "--uninstall" ]]; then
    uninstall
    exit 0
fi

if [[ ! -x "$HERE/AppRun" ]]; then
    echo "install.sh must be run from inside the extracted Euro-Info.AppDir folder." >&2
    exit 1
fi

if [[ "$HERE" != "$PREFIX" ]]; then
    # Copy next to the target first, then swap, so a failed copy never leaves
    # a half-installed app behind.
    mkdir -p -- "$(dirname -- "$PREFIX")"
    rm -rf -- "$PREFIX.new" "$PREFIX.old"
    cp -a -- "$HERE" "$PREFIX.new"
    [[ -d "$PREFIX" ]] && mv -- "$PREFIX" "$PREFIX.old"
    mv -- "$PREFIX.new" "$PREFIX"
    rm -rf -- "$PREFIX.old"
fi

mkdir -p -- "$BIN" "$APPLICATIONS" "$ICONS"
ln -sfn -- "$PREFIX/AppRun" "$BIN/euro-info"
install -m 644 -- "$PREFIX/euro-info.svg" "$ICONS/euro-info.svg"
sed -e "s|^Exec=.*|Exec=$BIN/euro-info|" -e "s|^Icon=.*|Icon=euro-info|" \
    "$PREFIX/euro-info.desktop" > "$APPLICATIONS/euro-info.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPLICATIONS" 2>/dev/null || true

if [[ -d "$PREFIX/plasma-widget" ]]; then
    if command -v kpackagetool6 >/dev/null; then
        kpackagetool6 --type Plasma/Applet --upgrade "$PREFIX/plasma-widget" >/dev/null 2>&1 \
            || kpackagetool6 --type Plasma/Applet --install "$PREFIX/plasma-widget" >/dev/null 2>&1 || true
    else
        rm -rf -- "$WIDGET_DIR"
        mkdir -p -- "$(dirname -- "$WIDGET_DIR")"
        cp -a -- "$PREFIX/plasma-widget" "$WIDGET_DIR"
    fi
fi

VERSION="$("$PREFIX/AppRun" --version 2>/dev/null || echo "Euro Info")"
echo "$VERSION installed in $PREFIX"
echo "Start it from the application menu or run: euro-info"
case ":$PATH:" in
    *":$BIN:"*) ;;
    *) echo "Note: $BIN is not on your PATH; the menu entry and widget still work." ;;
esac
