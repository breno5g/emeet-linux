#!/bin/sh
# Install emeet-linux for the current user: system packages, the wheel, the menu entry.
# Usage: ./install.sh            (from an extracted release tarball or the repo)
#        ./install.sh --uninstall
set -eu
cd "$(dirname "$0")"

DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
PIP="python3 -m pip"
PIP_INSTALL="$PIP install --user --break-system-packages --force-reinstall --no-deps"

if [ "${1:-}" = "--uninstall" ]; then
    $PIP uninstall -y --break-system-packages emeet-linux || true
    rm -f "$DATA/applications/dev.breno5g.emeet.desktop" "$DATA/icons/hicolor/scalable/apps/dev.breno5g.emeet.svg"
    echo "removed"
    exit 0
fi

# 1. system packages: PyGObject, GTK 4, libadwaita, GStreamer with the GTK4 sink, v4l-utils
if command -v pacman >/dev/null; then
    sudo pacman -S --needed --noconfirm python-gobject gtk4 libadwaita gstreamer gst-plugins-base gst-plugins-good gst-plugin-gtk4 v4l-utils
elif command -v apt-get >/dev/null; then
    sudo apt-get install -y python3-gi python3-pip gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gstreamer-1.0 gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-gtk4 v4l-utils
elif command -v dnf >/dev/null; then
    sudo dnf install -y python3-gobject python3-pip gtk4 libadwaita gstreamer1-plugins-base gstreamer1-plugins-good gstreamer1-plugin-gtk4 v4l-utils
else
    echo "unknown distro: install PyGObject, GTK 4, libadwaita, GStreamer (base, good, gtk4 sink) and v4l-utils yourself" >&2
fi

# 2. the app, into the user's site-packages so it sees the system PyGObject
WHEEL=$(ls emeet_linux-*.whl 2>/dev/null | head -1 || true)
if [ -n "$WHEEL" ]; then
    $PIP_INSTALL "$WHEEL"
else
    $PIP_INSTALL .
fi

# 3. menu entry and icon
install -Dm644 data/dev.breno5g.emeet.desktop "$DATA/applications/dev.breno5g.emeet.desktop"
install -Dm644 data/dev.breno5g.emeet.svg "$DATA/icons/hicolor/scalable/apps/dev.breno5g.emeet.svg"
update-desktop-database "$DATA/applications" 2>/dev/null || true
gtk-update-icon-cache -q "$DATA/icons/hicolor" 2>/dev/null || true

case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "note: add ~/.local/bin to PATH to run 'emeet' from a terminal" ;; esac
echo "installed: run 'emeet' or open EMEET Webcam from the app menu"
