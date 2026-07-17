import os
import subprocess
import shutil
import tempfile
import threading
import json
import time
from pathlib import Path
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango, Gio, GdkPixbuf
import sys
import argparse

# Path Configuration
BASE_DIR = Path(__file__).resolve().parent
ICONS_DIR = Path.home() / ".local/share/icons/android_apps"
DESKTOP_DIR = Path.home() / ".local/share/applications"
SETTINGS_DIR = Path.home() / ".config/droidtux"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
BRIDGE_APK = BASE_DIR / "droidtux-bridge-final.apk"

# Search for logo in multiple locations
LOGO_SEARCH_PATHS = [
    Path.home() / ".local/share/icons/droidtux.png",
    BASE_DIR / "droidtux.png",
    Path("/usr/share/icons/hicolor/512x512/apps/droidtux.png"),
    Path("/usr/local/share/icons/droidtux.png")
]

LOGO_PATH = None
for p in LOGO_SEARCH_PATHS:
    if p.exists():
        LOGO_PATH = p
        break

# Native CSS Styling
NORD_CSS = b"""
.header { padding: 20px; border-bottom: 2px solid @theme_selected_bg_color; }
.title { font-size: 24px; font-weight: bold; }
.subtitle { font-size: 14px; opacity: 0.8; }
.card { border-radius: 12px; margin: 20px; padding: 20px; border: 1px solid @theme_bg_color; }
.log-view { font-family: 'Monospace'; font-size: 12px; border-radius: 8px; }
progressbar trough { border-radius: 5px; min-height: 10px; }
progressbar progress { border-radius: 5px; }
.splash-window { background-color: @theme_bg_color; border: 2px solid @theme_selected_bg_color; border-radius: 20px; }
.splash-label { font-size: 13px; font-weight: normal; color: @theme_fg_color; }
"""

def load_settings():
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return {
                    "resolution": "1280x720",
                    "dpi": 240,
                    "bitrate": "16M",
                    "auto_sync": False,
                    **json.load(f),
                }
        except: pass
    return {"resolution": "1280x720", "dpi": 240, "bitrate": "16M", "auto_sync": False}

class DroidTuxApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="DroidTux Dashboard")
        self.set_default_size(500, 700)
        self.set_position(Gtk.WindowPosition.CENTER)
        
        if LOGO_PATH:
            self.set_icon_from_file(str(LOGO_PATH))
        
        self.settings = load_settings()
        self.serial = None
        self.automatic = False

        # Apply CSS
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(NORD_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.setup_ui()
        self.show_all()
        
    def setup_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vbox)

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        header.get_style_context().add_class("header")
        
        if LOGO_PATH.exists():
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                str(LOGO_PATH), 120, 120, True
            )
            img = Gtk.Image.new_from_pixbuf(pixbuf)
            header.pack_start(img, False, False, 0)

        title = Gtk.Label(label="DROIDTUX")
        title.get_style_context().add_class("title")
        header.pack_start(title, False, False, 0)
        
        subtitle = Gtk.Label(label="Android Desktop Integrator")
        subtitle.get_style_context().add_class("subtitle")
        header.pack_start(subtitle, False, False, 0)
        vbox.pack_start(header, False, False, 0)

        # Main Card
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        card.get_style_context().add_class("card")
        vbox.pack_start(card, True, True, 0)

        self.status_label = Gtk.Label(label="Ready to sync")
        self.status_label.set_halign(Gtk.Align.CENTER)
        card.pack_start(self.status_label, False, False, 0)

        self.progress_bar = Gtk.ProgressBar()
        card.pack_start(self.progress_bar, False, False, 0)

        # Log Area
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.get_style_context().add_class("log-view")
        self.text_view = Gtk.TextView()
        self.text_view.set_editable(False)
        self.text_view.set_cursor_visible(False)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        scrolled.add(self.text_view)
        card.pack_start(scrolled, True, True, 0)

        # Action Buttons
        bbox = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        bbox.set_layout(Gtk.ButtonBoxStyle.SPREAD)
        card.pack_start(bbox, False, False, 10)

        self.sync_btn = Gtk.Button(label="START SYNC (all apps)")
        self.sync_btn.get_style_context().add_class("suggested-action")
        self.sync_btn.connect("clicked", self.on_sync_clicked)
        bbox.pack_start(self.sync_btn, True, True, 0)

        self.select_btn = Gtk.Button(label="CUSTOM APP SELECT")
        self.select_btn.connect("clicked", self.on_custom_select_clicked)
        bbox.pack_start(self.select_btn, True, True, 0)

        help_btn = Gtk.Button(label="USB HELP")
        help_btn.connect("clicked", self.show_usb_help)
        bbox.pack_start(help_btn, True, True, 0)

    def log(self, message):
        print(f"[DroidTux] {message}")
        if hasattr(self, 'text_view'):
            GLib.idle_add(self._log_idle, message)
        if hasattr(self, 'splash') and self.splash:
            GLib.idle_add(self.splash.update_status, message)

    def _log_idle(self, message):
        buffer = self.text_view.get_buffer()
        buffer.insert(buffer.get_end_iter(), f"> {message}\n")
        # Scroll to bottom
        adj = self.text_view.get_vadjustment()
        adj.set_value(adj.get_upper() - adj.get_page_size())
        return False

    def update_progress(self, text, fraction):
        print(f"[Progress {int(fraction*100)}%] {text}")
        if hasattr(self, 'status_label'):
            GLib.idle_add(self._update_progress_idle, text, fraction)
        if hasattr(self, 'splash') and self.splash:
            GLib.idle_add(self.splash.update_progress, text, fraction)

    def _update_progress_idle(self, text, fraction):
        self.status_label.set_text(text)
        self.progress_bar.set_fraction(fraction)
        return False

    def on_sync_clicked(self, btn):
        self.sync_btn.set_sensitive(False)
        self.text_view.get_buffer().set_text("")
        threading.Thread(target=self.run_sync, daemon=True).start()

    def on_custom_select_clicked(self, btn):
        self.select_btn.set_sensitive(False)
        threading.Thread(target=self._prepare_app_selector, daemon=True).start()

    def _prepare_app_selector(self):
        GLib.idle_add(self._update_progress_idle, "Searching for device...", 0.1)
        serial = None
        for _ in range(15):
            output = self.run_adb("devices")
            lines = [l for l in (output or "").splitlines()[1:] if l.strip()]
            devs = [l.split()[0] for l in lines if "\tdevice" in l]
            if devs:
                serial = devs[0]
                break
            time.sleep(1)

        if not serial:
            GLib.idle_add(self._show_error_dialog, "No device found. Connect your phone via USB and enable USB debugging.")
            GLib.idle_add(self.select_btn.set_sensitive, True)
            return

        self.serial = serial
        cmd = "shell \"cmd package query-activities --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER\""
        pkgs_raw = self.run_adb(cmd, serial)
        packages = sorted(set([l.split("/")[0].strip() for l in pkgs_raw.splitlines() if "/" in l]))

        GLib.idle_add(self.select_btn.set_sensitive, True)
        GLib.idle_add(self._show_app_selector_dialog, packages, serial)

    def _show_error_dialog(self, text):
        dialog = Gtk.MessageDialog(
            transient_for=self, flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK, text=text
        )
        dialog.run()
        dialog.destroy()
        return False

    def _show_app_selector_dialog(self, packages, serial):
        dialog = Gtk.Dialog(title="Select apps to integrate", transient_for=self, flags=0)
        dialog.set_default_size(420, 600)
        dialog.add_buttons(
            "Cancel", Gtk.ResponseType.CANCEL,
            "Integrate selected", Gtk.ResponseType.OK
        )

        content = dialog.get_content_area()
        content.set_spacing(6)

        search_entry = Gtk.SearchEntry()
        search_entry.set_placeholder_text("Filter apps...")
        content.pack_start(search_entry, False, False, 4)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        content.pack_start(scrolled, True, True, 0)

        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        scrolled.add(listbox)

        checkboxes = {}
        icon_images = {}
        generic_icon = Gtk.IconTheme.get_default().load_icon("application-x-executable", 32, 0)

        for pkg in packages:
            row = Gtk.ListBoxRow()
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            hbox.set_margin_top(4)
            hbox.set_margin_bottom(4)
            hbox.set_margin_start(6)
            hbox.set_margin_end(6)

            check = Gtk.CheckButton()
            hbox.pack_start(check, False, False, 0)
            checkboxes[pkg] = check

            icon_img = Gtk.Image.new_from_pixbuf(generic_icon)
            hbox.pack_start(icon_img, False, False, 0)
            icon_images[pkg] = icon_img

            label = Gtk.Label(label=pkg)
            label.set_halign(Gtk.Align.START)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            hbox.pack_start(label, True, True, 0)

            row.add(hbox)
            row.pkg_name = pkg
            listbox.add(row)

        listbox.show_all()

        def on_search_changed(entry):
            query = entry.get_text().lower()
            for row in listbox.get_children():
                row.set_visible(query in row.pkg_name.lower())
        search_entry.connect("search-changed", on_search_changed)

        select_all_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        select_all_btn = Gtk.Button(label="Select all")
        deselect_all_btn = Gtk.Button(label="Deselect all")
        select_all_row.pack_start(select_all_btn, True, True, 0)
        select_all_row.pack_start(deselect_all_btn, True, True, 0)
        content.pack_start(select_all_row, False, False, 4)
        select_all_btn.connect("clicked", lambda b: [c.set_active(True) for c in checkboxes.values()])
        deselect_all_btn.connect("clicked", lambda b: [c.set_active(False) for c in checkboxes.values()])

        dialog.show_all()

        stop_flag = {"stop": False}
        def load_icons():
            BRIDGE_REMOTE_DIR = "/sdcard/Android/data/com.droidtux.bridge/files"
            for pkg in packages:
                if stop_flag["stop"]:
                    return
                self.run_adb(f"shell am start-foreground-service -n com.droidtux.bridge/.IconService --es package {pkg}", serial)
                icon_path = ICONS_DIR / f"{pkg}.png"
                for _ in range(10):
                    if stop_flag["stop"]:
                        return
                    size_raw = self.run_adb(f"shell stat -c %s {BRIDGE_REMOTE_DIR}/{pkg}.png 2>/dev/null", serial)
                    if size_raw.isdigit() and int(size_raw) > 0:
                        ICONS_DIR.mkdir(parents=True, exist_ok=True)
                        self.run_adb(f"pull {BRIDGE_REMOTE_DIR}/{pkg}.png {icon_path}", serial)
                        GLib.idle_add(self._update_selector_icon, icon_images, pkg, str(icon_path))
                        break
                    time.sleep(0.15)
        icon_thread = threading.Thread(target=load_icons, daemon=True)
        icon_thread.start()

        response = dialog.run()
        stop_flag["stop"] = True

        selected = [pkg for pkg, cb in checkboxes.items() if cb.get_active()]
        dialog.destroy()

        if response == Gtk.ResponseType.OK and selected:
            self.sync_btn.set_sensitive(False)
            self.select_btn.set_sensitive(False)
            self.text_view.get_buffer().set_text("")
            threading.Thread(target=self.run_sync, args=(selected,), daemon=True).start()

    def _update_selector_icon(self, icon_images, pkg, icon_path):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_path, 32, 32, True)
            icon_images[pkg].set_from_pixbuf(pixbuf)
        except Exception:
            pass
        return False

    def show_usb_help(self, btn):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="How to enable 'Install via USB'"
        )
        msg = (
            "If you don't see 'Install via USB' in Developer Options:\n\n"
            "1. XIAOMI / MIUI: Log in to your Mi Account and insert a SIM card.\n"
            "2. REALME / OPPO: Enable 'ADB Installation'.\n"
            "3. OTHERS: Search for 'Allow app installation via ADB'.\n\n"
            "DroidTux needs this for high-quality icons."
        )
        dialog.format_secondary_text(msg)
        dialog.run()
        dialog.destroy()

    def run_adb(self, cmd, serial=None):
        prefix = f"adb -s {serial} " if serial else "adb "
        try:
            res = subprocess.run(f"{prefix}{cmd}", shell=True, capture_output=True, text=True, timeout=20)
            if res.returncode != 0: return f"ERROR: {res.stderr.strip()}"
            return res.stdout.strip()
        except Exception as e: return f"ERROR: {str(e)}"

    def watchdog(self):
        print(f"[Watchdog] Monitoring device: {self.serial}")
        while True:
            time.sleep(5)
            output = self.run_adb("devices")
            found = False
            for line in output.splitlines():
                if self.serial in line and "\tdevice" in line:
                    found = True
                    break
            
            if not found:
                print(f"[Watchdog] Device {self.serial} disconnected. Cleaning up.")
                cleanup()
                os._exit(0)

    def run_sync(self, selected_packages=None):
        self.update_progress("Searching for device...", 0.1)
        serial = None
        while not serial:
            output = self.run_adb("devices")
            lines = [l for l in (output or "").splitlines()[1:] if l.strip()]
            devs = [l.split()[0] for l in lines if "\tdevice" in l]
            if devs: serial = devs[0]
            else: 
                self.log("Waiting for USB device...")
                time.sleep(2)
        
        self.log(f"Connected to {serial}")
        self.serial = serial
        
        # Prevent phone sleep
        self.log("Setting 'Stay Awake' mode...")
        self.run_adb("shell svc power stayon usb", serial)
        self.run_adb("shell wm dismiss-keyguard", serial)

        self.update_progress("Validating Bridge App...", 0.2)
        
        bridge_pkg = "com.droidtux.bridge"
        self.log("Ensuring Bridge APK is installed and up to date...")
        if BRIDGE_APK.exists():
            res = self.run_adb(f"install -r -g {BRIDGE_APK}", serial)
            if "INSTALL_FAILED_USER_RESTRICTED" in res:
                self.log("ERROR: USB Installation blocked by phone.")
                GLib.idle_add(self.show_usb_help, None)
                self.update_progress("Error: Enable USB Installation", 0)
                if not self.automatic:
                    GLib.idle_add(self.sync_btn.set_sensitive, True)
                    GLib.idle_add(self.select_btn.set_sensitive, True)
                return
            elif "ERROR:" in res:
                self.log(f"Warning: Bridge installation might have failed: {res}")
        else:
            self.log("Error: Bridge APK not found.")
            if not self.automatic:
                GLib.idle_add(self.sync_btn.set_sensitive, True)
                GLib.idle_add(self.select_btn.set_sensitive, True)
            return

        self.update_progress("Syncing apps...", 0.4)
        ICONS_DIR.mkdir(parents=True, exist_ok=True)
        DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
        
        # Load current settings
        self.settings = load_settings()
        resolution = self.settings.get("resolution", "1280x720")
        res_w = resolution.split('x')[0]
        res_h = resolution.split('x')[1]
        dpi = self.settings.get("dpi", 240)
        bitrate = self.settings.get("bitrate", "16M").lower()

        cmd = "shell \"cmd package query-activities --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER\""
        pkgs_raw = self.run_adb(cmd, serial)
        packages = list(set([l.split("/")[0].strip() for l in pkgs_raw.splitlines() if "/" in l]))
        if selected_packages is not None:
            packages = [p for p in packages if p in selected_packages]

        BRIDGE_REMOTE_DIR = "/sdcard/Android/data/com.droidtux.bridge/files"
        
        for i, pkg in enumerate(packages):
            perc = 0.4 + (0.5 * (i/len(packages)))
            self.update_progress(f"Processing {pkg}", perc)
            self.log(f"Integrating: {pkg}")
            
            # Clean previous files on phone (using both old and new paths for safety)
            self.run_adb(f"shell \"rm /sdcard/Download/{pkg}.png /sdcard/Download/{pkg}.label 2>/dev/null\"", serial)
            self.run_adb(f"shell \"rm {BRIDGE_REMOTE_DIR}/{pkg}.png {BRIDGE_REMOTE_DIR}/{pkg}.label 2>/dev/null\"", serial)
            
            # Launch bridge
            self.run_adb(f"shell am start-foreground-service -n com.droidtux.bridge/.IconService --es package {pkg}", serial)
            
            icon_path = ICONS_DIR / f"{pkg}.png"
            name = pkg.split('.')[-1].capitalize() # Initial fallback
            
            # Wait for files (PNG and Label)
            success = False
            for _ in range(20):
                size_raw = self.run_adb(f"shell stat -c %s {BRIDGE_REMOTE_DIR}/{pkg}.png 2>/dev/null", serial)
                label_check = self.run_adb(f"shell ls {BRIDGE_REMOTE_DIR}/{pkg}.label 2>/dev/null", serial)
                
                if size_raw.isdigit() and int(size_raw) > 0 and pkg in label_check:
                    self.run_adb(f"pull {BRIDGE_REMOTE_DIR}/{pkg}.png {icon_path}", serial)
                    name_raw = self.run_adb(f"shell cat {BRIDGE_REMOTE_DIR}/{pkg}.label", serial)
                    if not name_raw.startswith("ERROR:"):
                        name = name_raw
                    success = True
                    break
                time.sleep(0.2)
            
            if not success:
                self.log(f"Warning: Failed to extract icons for {pkg}. Using fallbacks.")
                label_check = self.run_adb(f"shell cat {BRIDGE_REMOTE_DIR}/{pkg}.label 2>/dev/null", serial)
                if label_check and "No such file" not in label_check and not label_check.startswith("ERROR:"):
                    name = label_check
                
                icon_path_str = "android" if not icon_path.exists() else str(icon_path.absolute())
            else:
                icon_path_str = str(icon_path.absolute())

            # Build scrcpy command with MULTI-DISPLAY
            scrcpy_args = (
                f"-s {serial} --start-app={pkg} --window-title=\"{name}\" "
                f"--new-display={resolution}/{dpi} -b {bitrate} "
                f"--always-on-top --stay-awake"
            )
            exec_cmd = f"scrcpy {scrcpy_args}"
            
            content = f"[Desktop Entry]\nType=Application\nName={name}\nExec={exec_cmd}\nIcon={icon_path_str}\nTerminal=false\nCategories=X-Android;\n"
            (DESKTOP_DIR / f"droidtux-{pkg}.desktop").write_text(content)

        subprocess.run(["update-desktop-database", str(DESKTOP_DIR)], capture_output=True)
        self.update_progress("Sync complete", 1.0)
        self.log("All done! Your apps are in the menu.")
        
        if self.automatic:
            time.sleep(2)
            GLib.idle_add(self.splash.hide)
            # Start watchdog to clean up on disconnect
            threading.Thread(target=self.watchdog, daemon=True).start()
        else:
            if hasattr(self, 'sync_btn'):
                GLib.idle_add(self.sync_btn.set_sensitive, True)

def cleanup():
    print("Cleaning DroidTux apps...")
    prefixes = ["dtapp-*.desktop", "droidtux-*.desktop"]
    for pattern in prefixes:
        for f in DESKTOP_DIR.glob(pattern):
            try:
                f.unlink()
            except: pass

    desktop_folders = [Path.home() / "Desktop", Path.home() / "Escritorio"]
    try:
        xdg_desktop = subprocess.check_output(["xdg-user-dir", "DESKTOP"], encoding='utf-8').strip()
        if xdg_desktop: desktop_folders.append(Path(xdg_desktop))
    except: pass

    for folder in set(desktop_folders):
        if folder.exists():
            for pattern in prefixes:
                for f in folder.glob(pattern):
                    try: f.unlink()
                    except: pass

    if ICONS_DIR.exists(): shutil.rmtree(ICONS_DIR)
    subprocess.run(["update-desktop-database", str(DESKTOP_DIR)], capture_output=True)
    print("Cleanup complete.")

class DroidTuxSplash(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_keep_above(True)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_default_size(250, 200)
        self.get_style_context().add_class("splash-window")

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        vbox.set_valign(Gtk.Align.CENTER)
        vbox.set_halign(Gtk.Align.CENTER)
        vbox.set_margin_start(20)
        vbox.set_margin_end(20)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        self.add(vbox)

        # Row 1: Logo
        if LOGO_PATH.exists():
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(LOGO_PATH), 64, 64, True)
            img = Gtk.Image.new_from_pixbuf(pixbuf)
            vbox.pack_start(img, False, False, 0)

        # Row 2: Spinner
        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(32, 32)
        self.spinner.start()
        vbox.pack_start(self.spinner, False, False, 0)

        # Row 3: Status Label (Logs)
        self.status_label = Gtk.Label(label="Initializing...")
        self.status_label.get_style_context().add_class("splash-label")
        self.status_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.status_label.set_max_width_chars(25)
        self.status_label.set_halign(Gtk.Align.CENTER)
        vbox.pack_start(self.status_label, False, False, 0)
        
        self.show_all()

    def update_status(self, text):
        self.status_label.set_text(text)

    def update_progress(self, text, fraction):
        self.status_label.set_text(text)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DroidTux Integrator")
    parser.add_argument("--add", action="store_true", help="Sync automatically")
    parser.add_argument("--remove", action="store_true", help="Remove apps")
    args = parser.parse_args()

    if args.remove:
        cleanup()
        sys.exit(0)
    
    if args.add:
        settings = load_settings()
        if not settings.get("auto_sync", False):
            print("Automatic sync is disabled in DroidTux settings.")
            sys.exit(0)

        print("Starting automatic sync (Splash Mode)...")
        app = DroidTuxApp()
        app.automatic = True
        app.hide() # Main window hidden
        app.splash = DroidTuxSplash()
        threading.Thread(target=app.run_sync, daemon=True).start()
        Gtk.main()
    else:
        app = DroidTuxApp()
        Gtk.main()
