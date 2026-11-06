#!/usr/bin/env bash
# Euro Info Plasma widget bridge: prints the latest stories and weather as JSON.
#
# Order of preference:
#   1. EURO_INFO_BIN, if set
#   2. the installed app: `euro-info` on PATH or ~/.local/bin/euro-info
#   3. a source checkout named in ~/.config/euro-info/widget-source (developers)
set -euo pipefail

emit_error() {
    printf '{"ok":false,"articles":[],"weather":{},"status":"%s"}\n' "$1"
    exit 1
}

if [[ -n "${EURO_INFO_BIN:-}" && -x "${EURO_INFO_BIN}" ]]; then
    exec "${EURO_INFO_BIN}" --widget-json
fi
for candidate in "$(command -v euro-info 2>/dev/null || true)" "$HOME/.local/bin/euro-info"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
        exec "$candidate" --widget-json
    fi
done

CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/euro-info/widget-source"
if [[ -f "$CONFIG" ]]; then
    IFS= read -r PROJECT < "$CONFIG" || true
    if [[ -n "${PROJECT:-}" && -x "$PROJECT/.venv/bin/python" && -d "$PROJECT/euroinfo" ]]; then
        cd -- "$PROJECT"
        exec "$PROJECT/.venv/bin/python" -m euroinfo --widget-json
    fi
fi
emit_error "Euro Info is not installed. Run install.sh from the Euro Info download."
