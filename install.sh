#!/bin/bash
# install.sh - Installation script for DroidTux

# Exit immediately if a command fails
set -e

USE_LN=false
for arg in "$@"; do
    if [ "$arg" == "--ln" ]; then
        USE_LN=true
    fi
done

echo "=== Installing DroidTux (Android App Integrator) ==="
if [ "$USE_LN" = true ]; then
    echo "(!) Development mode active: Symbolic links will be used."
fi

# 1. Check and install system dependencies
echo "[1/4] Installing system dependencies (requires pkexec)..."
if command -v pacman >/dev/null; then
    pkexec pacman -S --noconfirm scrcpy android-tools python-gobject desktop-file-utils
elif command -v dnf >/dev/null; then
    pkexec dnf install -y scrcpy android-tools python3-gobject desktop-file-utils
elif command -v apt-get >/dev/null; then
    pkexec apt-get update
    pkexec apt-get install -y scrcpy adb python3-gi desktop-file-utils
else
    echo "Unsupported package manager. Please ensure scrcpy, adb, python3, and pygobject (gi) are installed."
fi

# 2. Setup paths and copy files
echo "[2/4] Setting up paths..."

# Ensure the bridge APK is built/present
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -f "$SCRIPT_DIR/droidtux-bridge-final.apk" ]; then
    echo "[*] Bridge APK not found. Trying to build it..."
    if (cd "$SCRIPT_DIR" && ./build_bridge.sh); then
        echo "[+] Bridge APK built successfully."
    else
        echo "[!] Error: Bridge APK is missing and could not be built automatically."
        echo "Please make sure you have the Android SDK installed, or obtain a pre-built apk,"
        echo "and place it in the project root before installing."
        exit 1
    fi
fi

SYSTEM_PYTHON="/usr/bin/python3"

# Install scripts
mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.local/share/icons"

# Copy logo
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$SCRIPT_DIR/droidtux.png" "$HOME/.local/share/icons/droidtux.png"

if [ "$USE_LN" = true ]; then
    echo "Creating symbolic links in ~/.local/bin/..."
    rm -f "$HOME/.local/bin/app_integrator.py" "$HOME/.local/bin/droidtux_settings.py"
    ln -sf "$SCRIPT_DIR/app_integrator.py" "$HOME/.local/bin/app_integrator.py"
    ln -sf "$SCRIPT_DIR/droidtux_settings.py" "$HOME/.local/bin/droidtux_settings.py"
else
    echo "Copying files to ~/.local/bin/..."
    rm -f "$HOME/.local/bin/app_integrator.py" "$HOME/.local/bin/droidtux_settings.py"
    cp "$SCRIPT_DIR/app_integrator.py" "$HOME/.local/bin/app_integrator.py"
    cp "$SCRIPT_DIR/droidtux_settings.py" "$HOME/.local/bin/droidtux_settings.py"
    if [ -f "$SCRIPT_DIR/droidtux-bridge-final.apk" ]; then
        cp "$SCRIPT_DIR/droidtux-bridge-final.apk" "$HOME/.local/bin/droidtux-bridge-final.apk"
    fi
fi
chmod +x "$HOME/.local/bin/app_integrator.py"
chmod +x "$HOME/.local/bin/droidtux_settings.py"

# Create desktop shortcuts (.desktop)
mkdir -p "$HOME/.local/share/applications"

# Desktop Entry for Sync Dashboard
cat > "$HOME/.local/share/applications/droidtux_sync.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=DroidTux Sync
Comment=Sync your Android apps
Exec=$SYSTEM_PYTHON $HOME/.local/bin/app_integrator.py
Icon=$HOME/.local/share/icons/droidtux.png
Terminal=false
Categories=Utility;
EOF

# Desktop Entry for Settings Panel
cat > "$HOME/.local/share/applications/droidtux_settings.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=DroidTux Settings
Comment=Configure DroidTux
Exec=$SYSTEM_PYTHON $HOME/.local/bin/droidtux_settings.py
Icon=$HOME/.local/share/icons/droidtux.png
Terminal=false
Categories=Settings;
EOF

update-desktop-database "$HOME/.local/share/applications"

# 3. Create Udev wrapper
echo "[3/4] Configuring Udev and Systemd integration..."
WRAPPER_PATH="/usr/local/bin/android-integrator-trigger.sh"
pkexec bash -c "cat > $WRAPPER_PATH" << 'EOF'
#!/bin/bash
# Find active sessions and launch user systemd service
for uid in $(loginctl list-sessions --no-legend | awk '{print $2}'); do
    user=$(id -un "$uid")
    # Capture DISPLAY and XAUTHORITY for GUI support
    display=$(sudo -u "$user" env | grep '^DISPLAY=' | cut -d= -f2-)
    xauthority=$(sudo -u "$user" env | grep '^XAUTHORITY=' | cut -d= -f2-)
    
    if [ -z "$display" ]; then display=":0"; fi

    if [ "$1" == "add" ]; then
        pkexec --user "$user" env DISPLAY="$display" XAUTHORITY="$xauthority" XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" systemctl --user restart android-integrator.service
    elif [ "$1" == "remove" ]; then
        pkexec --user "$user" env XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" systemctl --user stop android-integrator.service
    fi
done
EOF
pkexec chmod +x "$WRAPPER_PATH"

# Install udev rule
pkexec cp "$SCRIPT_DIR/99-android-integrator.rules" /etc/udev/rules.d/
pkexec udevadm control --reload-rules
pkexec udevadm trigger

# 4. Install and enable user Systemd service
echo "[4/4] Installing Systemd service..."
mkdir -p "$HOME/.config/systemd/user"
if [ "$USE_LN" = true ]; then
    echo "Creating symbolic link for systemd service..."
    ln -sf "$SCRIPT_DIR/android-integrator.service" "$HOME/.config/systemd/user/android-integrator.service"
else
    cp "$SCRIPT_DIR/android-integrator.service" "$HOME/.config/systemd/user/"
fi

# Run daemon-reload and enable as the current user
# We try to use the user who launched the script if possible
REAL_USER="${PKEXEC_UID:-$UID}"
USER_NAME=$(id -un "$REAL_USER")

pkexec --user "$USER_NAME" env XDG_RUNTIME_DIR="/run/user/$REAL_USER" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$REAL_USER/bus" systemctl --user daemon-reload
pkexec --user "$USER_NAME" env XDG_RUNTIME_DIR="/run/user/$REAL_USER" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$REAL_USER/bus" systemctl --user enable android-integrator.service

echo "=== Installation completed successfully ==="
echo "DroidTux is ready. When you connect your Android device via USB (with USB Debugging enabled), your apps will automatically appear in your menu."
