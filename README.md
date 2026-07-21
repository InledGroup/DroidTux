<p align="center">
  <img src="static/logo.png" alt="DroidTux Logo" width="120">
</p>

<h1 align="center">DroidTux</h1>

---

Droidtux is an application that acts as a scrcpy GUI, making the difficult simple. It allows you to integrate phone applications as desktop apps on your computer. You can select which applications to integrate and which not to. Decide the resolution, DPI and bitrate of these. It also allows you to use your phone as a virtual camera in Linux.

> [!WARNING]
> Keep Droidtux updated: configure the [Inled Repo for your distro](https://apt.inled.es).

### Features
-**Synchronize all apps**: Automatically or manually, connect the phone and the apps will magically appear as if they were normal apps. It works in any Linux graphical environment.  

-**Selective synchronization**: You may only want to sync one app or not others: well you can do it  

-**Adjust EVERYTHING**: From the resolution to the bitrate, the DPI or the audio redirection so that it comes out through the PC or the speakers connected to it.  

-**Virtual camera**: Don't you have a camera? Is the one on your computer more like a Nokia than a decent one? Well don't worry because with Droidtux your phone becomes a camera. You can choose which camera on your phone to use, its resolution, and even whether to redirect audio.  

-**No cables, no ties**: You can do everything remotely (obviously the video will have more lag, depending on your network, how it is managed by the phone and the processor of the phone and PC).  

-**Configure your phone for wireless with a wizard**: Connect the phone via USB the first time and click on the wireless mode configurator. Then disconnect and click on search for the device and that's it.  


### Prerequisites
- **Linux:** Python 3, `scrcpy`, `adb`, and GTK4 libraries.
- **Android:** Depuración por USB activada o wireless. Soporte para instalación de aplicaciones vía ADB (para instalar un simple apk compuesto por un único archivo Java que puedes auditar en el repo, que simplemente extrae los iconos de las apps)

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

### License    


Licensed under MIT-INLED license. Learn more at [license.inled.es](https://license.inled.es) and how it benefits you.  

---

### Contribute   
Do you have any idea? Pr's and issues are welcome! We will give you appropiate credit and you will appear as a contributor on any publication on social media.   

---
*Developed by JaimeGH.*
*vreadme1.2.1*

> [!NOTE]
> This project was developed with the assistance of Artificial Intelligence (AI) for coding, and all the code and its operations have been thoroughly reviewed and tested.
