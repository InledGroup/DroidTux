<p align="center">
  <img src="static/logo.png" alt="DroidTux Logo" width="120">
</p>

<h1 align="center">DroidTux - Integrate your phone app's as desktop apps</h1>

---

DroidTux is a tool designed to seamlessly integrate your Android applications directly into your Linux desktop. It leverages `scrcpy` for screen mirroring and a small "Bridge" app on the device to extract original icons and labels, creating `.desktop` files that allow you to launch Android apps as if they were native.

### Features
- **Native Integration:** Launch Android apps from your application menu (GNOME, KDE, XFCE, etc.).
- **Icon Extraction:** Fetches real icons and names from the device.
- **Automatic Sync:** Thanks to `udev` rules, DroidTux can automatically sync your apps when connecting your phone via USB.
- **GTK Dashboard:** A simple interface to manage synchronization and view logs.
- **Multidisplay:** Uses `scrcpy` capabilities to create virtual displays with custom resolutions.

### Prerequisites
- **Linux:** Python 3, `scrcpy`, `adb`, and GTK3 libraries.
- **Android:** USB Debugging enabled. Enabling "Install via USB" in developer options is highly recommended for the best experience.

### Installation
1. Clone this repository.
2. Ensure the bridge APK is generated (or use the included one):
   ```bash
   ./build_bridge.sh
   ```
3. Run the installation script:
   ```bash
   chmod +x install.sh
   ./install.sh
   ```

### Packages (Debian, Fedora, Arch Linux)
You can generate native packages for your distribution using the `package.sh` script. This script requires `fpm`:
```bash
./package.sh [version]
```
This will generate `.deb`, `.rpm`, and `.pkg.tar.zst` files in the root directory.

You can also find the native definition files in the `packaging/` folder:
- **Arch Linux:** `packaging/arch/PKGBUILD`
- **Fedora:** `packaging/fedora/droidtux.spec`

To uninstall the package version:
- Debian: `./uninstall_deb.sh`
- Fedora: `./uninstall_rpm.sh`
- Arch Linux: `./uninstall_pacman.sh`

### Development
To manually compile the Android bridge, you need the Android SDK (aapt2, d8, apksigner, etc.) and run:
```bash
./build_bridge.sh
```

---
*Developed by JaimeGH.*
*vreadme1.2.1*

> [!NOTE]
> This project was developed with the assistance of Artificial Intelligence (AI) for coding, and all the code and its operations have been thoroughly reviewed and tested.
