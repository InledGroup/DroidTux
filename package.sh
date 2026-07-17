#!/bin/bash
set -e

# Packaging script for DroidTux
# Dependencies: fpm, zip, build-essential, curl, gnupg

VERSION="${1:-1.0.0}"
BUILD_DIR="pkg_build"
STAGING_DIR="$BUILD_DIR/staging"

echo "[*] Starting packaging process v$VERSION..."

# 1. Build the Bridge APK
if [ ! -f droidtux-bridge-final.apk ]; then
    echo "[*] Bridge APK not found. Trying to build it..."
    if ./build_bridge.sh; then
        echo "[+] Bridge APK built successfully."
    else
        echo "[!] Error: Bridge APK is missing and could not be built automatically."
        echo "Please build it manually using ./build_bridge.sh before running package.sh"
        exit 1
    fi
fi

# 2. Prepare Staging Area
rm -rf "$BUILD_DIR"
mkdir -p "$STAGING_DIR/usr/local/bin"
mkdir -p "$STAGING_DIR/usr/local/share/droidtux"
mkdir -p "$STAGING_DIR/usr/share/icons/hicolor/512x512/apps"
mkdir -p "$STAGING_DIR/etc/udev/rules.d"
mkdir -p "$STAGING_DIR/usr/share/applications"
mkdir -p "$STAGING_DIR/usr/lib/systemd/user"

# Copy files
cp app_integrator.py "$STAGING_DIR/usr/local/share/droidtux/"
cp droidtux_settings.py "$STAGING_DIR/usr/local/share/droidtux/"
if [ -f droidtux-bridge-final.apk ]; then
    cp droidtux-bridge-final.apk "$STAGING_DIR/usr/local/share/droidtux/"
else
    echo "[!] Error: droidtux-bridge-final.apk not found even after build attempt!"
    exit 1
fi
cp droidtux.png "$STAGING_DIR/usr/local/share/droidtux/"
cp droidtux.png "$STAGING_DIR/usr/share/icons/hicolor/512x512/apps/droidtux.png"
cp 99-android-integrator.rules "$STAGING_DIR/etc/udev/rules.d/"

# Create system-specific systemd service for the package
cat > "$STAGING_DIR/usr/lib/systemd/user/android-integrator.service" << EOF
[Unit]
Description=DroidTux - Integrador de Aplicaciones Android
Documentation=https://github.com/nexu-io
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/share/droidtux/app_integrator.py --add
ExecStop=/usr/bin/python3 /usr/local/share/droidtux/app_integrator.py --remove
KillMode=process
TimeoutStopSec=5

[Install]
WantedBy=default.target
EOF

# Create the Trigger Wrapper script with LOGGING
cat > "$STAGING_DIR/usr/local/bin/android-integrator-trigger.sh" << 'EOF'
#!/bin/bash
# Log execution
exec &> >(logger -t droidtux-trigger)
echo "Trigger called with argument: $1"

# Find active sessions and launch user systemd service
for uid in $(loginctl list-sessions --no-legend | awk '{print $2}'); do
    user=$(id -un "$uid")
    echo "Processing session for user: $user (UID: $uid)"
    
    # Better way to find DISPLAY
    display=$(sudo -u "$user" env | grep '^DISPLAY=' | cut -d= -f2-)
    if [ -z "$display" ]; then
        display=$(pgrep -u "$uid" -a gnome-session | grep -o 'DISPLAY=[^ ]*' | cut -d= -f2 | head -n1)
        [ -z "$display" ] && display=$(pgrep -u "$uid" -a x-session-manager | grep -o 'DISPLAY=[^ ]*' | cut -d= -f2 | head -n1)
        [ -z "$display" ] && display=":0"
    fi
    echo "Found DISPLAY: $display"

    if [ "$1" == "add" ]; then
        echo "Restarting service for $user..."
        sudo -u "$user" env DISPLAY="$display" XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" systemctl --user restart android-integrator.service
    elif [ "$1" == "remove" ]; then
        echo "Stopping service for $user..."
        sudo -u "$user" env XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" systemctl --user stop android-integrator.service
    fi
done
EOF
chmod +x "$STAGING_DIR/usr/local/bin/android-integrator-trigger.sh"

# Create desktop entries for the package
cat > "$STAGING_DIR/usr/share/applications/droidtux_sync.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=DroidTux Sync
Comment=Sync your Android apps
Exec=/usr/local/bin/droidtux-sync
Icon=droidtux
Terminal=false
Categories=Utility;
EOF

cat > "$STAGING_DIR/usr/share/applications/droidtux_settings.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=DroidTux Settings
Comment=Configure DroidTux
Exec=/usr/local/bin/droidtux-settings
Icon=droidtux
Terminal=false
Categories=Settings;
EOF

# Create wrapper scripts for /usr/local/bin
cat > "$STAGING_DIR/usr/local/bin/droidtux-sync" << 'EOF'
#!/bin/bash
/usr/bin/python3 /usr/local/share/droidtux/app_integrator.py "$@"
EOF

cat > "$STAGING_DIR/usr/local/bin/droidtux-settings" << 'EOF'
#!/bin/bash
/usr/bin/python3 /usr/local/share/droidtux/droidtux_settings.py "$@"
EOF

chmod +x "$STAGING_DIR/usr/local/bin/droidtux-sync"
chmod +x "$STAGING_DIR/usr/local/bin/droidtux-settings"

# Prepare after-install script
cat > "$BUILD_DIR/after-install.sh" << 'EOF'
#!/bin/bash
set -e

# Force Udev rules (in case the package manager didn't install them correctly)
cp /usr/local/share/droidtux/99-android-integrator.rules /etc/udev/rules.d/ 2>/dev/null || true
udevadm control --reload-rules && udevadm trigger



# Update databases
update-desktop-database /usr/share/applications || true
gtk-update-icon-cache -f -t /usr/share/icons/hicolor || true
EOF

# Prepare after-remove script
cat > "$BUILD_DIR/after-remove.sh" << 'EOF'
#!/bin/bash
rm -f /usr/local/bin/android-integrator-trigger.sh
rm -f /etc/udev/rules.d/99-android-integrator.rules
udevadm control --reload-rules
rm -f /etc/apt/sources.list.d/inled.list
rm -f /usr/share/keyrings/inled-archive-keyring.gpg
update-desktop-database /usr/share/applications || true
EOF

# Add a backup of the udev rules inside /usr/local/share/droidtux/ for the after-install script
cp 99-android-integrator.rules "$STAGING_DIR/usr/local/share/droidtux/"

# 3. Build Packages
echo "[*] Building packages..."

# Dependencies mapping
DEB_DEPS=(
    "scrcpy" "adb" "python3-gi" "desktop-file-utils" "sudo"
)

RPM_DEPS=(
    "scrcpy" "android-tools" "python3-gobject" "desktop-file-utils" "sudo"
)

PACMAN_DEPS=(
    "scrcpy" "android-tools" "python-gobject" "desktop-file-utils" "sudo"
)

build_package() {
    local target=$1
    local arch=$2
    local deps=("${@:3}")
    
    echo "[*] Generating $target ($arch) package..."
    
    fpm_cmd=(fpm -s dir -t "$target" -n droidtux -v "$VERSION" -a "$arch" \
        --after-install "$BUILD_DIR/after-install.sh" \
        --after-remove "$BUILD_DIR/after-remove.sh" \
        -C "$STAGING_DIR")
    
    for dep in "${deps[@]}"; do
        fpm_cmd+=("--depends" "$dep")
    done
    
    # The source path must be the last argument
    fpm_cmd+=(".")
    
    "${fpm_cmd[@]}"
}

# Build for Debian
build_package "deb" "all" "${DEB_DEPS[@]}"

# Build for Fedora (RPM)
build_package "rpm" "noarch" "${RPM_DEPS[@]}"

# Build for Arch Linux (Pacman)
# Note: fpm might need 'bsdtar' and 'zstd' installed for pacman target
build_package "pacman" "any" "${PACMAN_DEPS[@]}"

echo "[+] Packaging complete!"
