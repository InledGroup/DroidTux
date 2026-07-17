#!/bin/bash
# package_arch.sh - Helper script to package DroidTux for Arch Linux using makepkg
set -e

# Base directory
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCH_DIR="$BASE_DIR/packaging/arch"

echo "=== Packaging DroidTux for Arch Linux ==="

# 0. Ensure the Bridge APK is built
if [ ! -f "$BASE_DIR/droidtux-bridge-final.apk" ]; then
    echo "[*] Bridge APK not found. Trying to build it..."
    if (cd "$BASE_DIR" && ./build_bridge.sh); then
        echo "[+] Bridge APK built successfully."
    else
        echo "[!] Error: Bridge APK is missing and could not be built."
        exit 1
    fi
fi

# 1. Ensure we enter the Arch packaging directory
cd "$ARCH_DIR"

# 2. Create temporary links for makepkg to locate local sources
echo "[1/4] Setting up temporary source links..."
ln -sf "$BASE_DIR/app_integrator.py" .
ln -sf "$BASE_DIR/droidtux_settings.py" .
ln -sf "$BASE_DIR/droidtux.png" .
ln -sf "$BASE_DIR/99-android-integrator.rules" .
ln -sf "$BASE_DIR/android-integrator.service" .
ln -sf "$BASE_DIR/droidtux-bridge-final.apk" .

# 3. Run makepkg
echo "[2/4] Running makepkg..."
# -s: install dependencies, -c: clean build files afterward, -f: overwrite existing package
makepkg -scf

# 4. Clean up temporary links
echo "[3/4] Cleaning up temporary source links..."
rm -f app_integrator.py droidtux_settings.py droidtux.png 99-android-integrator.rules android-integrator.service droidtux-bridge-final.apk

# 5. Move output package to root directory
echo "[4/4] Locating generated package..."
PKG_FILE=$(ls -t *.pkg.tar.zst 2>/dev/null | head -n1)
if [ -n "$PKG_FILE" ]; then
    mv "$PKG_FILE" "$BASE_DIR/"
    echo "=== Packaging completed successfully! ==="
    echo "Package file generated in the project root: $PKG_FILE"
else
    echo "(!) Error: Package file was not generated."
    exit 1
fi
