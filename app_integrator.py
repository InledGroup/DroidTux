import os
import subprocess
import shutil
import tempfile
import threading
import json
import time
from pathlib import Path
import gi
import sys
import argparse

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gdk, GLib, Pango, Gio, GdkPixbuf, Adw

# Path Configuration
BASE_DIR = Path(__file__).resolve().parent
ICONS_DIR = Path.home() / ".local/share/icons/android_apps"
DESKTOP_DIR = Path.home() / ".local/share/applications"
SETTINGS_DIR = Path.home() / ".config/droidtux"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

# Search for Bridge APK in multiple locations
BRIDGE_APK_SEARCH_PATHS = [
    BASE_DIR / "droidtux-bridge-final.apk",
    Path("/usr/local/share/droidtux/droidtux-bridge-final.apk"),
    Path("/usr/share/droidtux/droidtux-bridge-final.apk"),
    Path.home() / ".local/bin/droidtux-bridge-final.apk"
]

BRIDGE_APK = None
for p in BRIDGE_APK_SEARCH_PATHS:
    if p.exists():
        BRIDGE_APK = p
        break

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
.brand-title { font-size: 24px; font-weight: bold; }
.subtitle { font-size: 14px; opacity: 0.8; }
.card { border-radius: 12px; margin: 20px; padding: 20px; border: 1px solid @theme_bg_color; }
.log-view { font-family: 'Monospace'; font-size: 12px; border-radius: 8px; }
progressbar trough { border-radius: 5px; min-height: 10px; }
progressbar progress { border-radius: 5px; }
.splash-window { background-color: @theme_bg_color; border: 2px solid @theme_selected_bg_color; border-radius: 20px; }
.splash-label { font-size: 13px; font-weight: normal; color: @theme_fg_color; }
"""

DEFAULT_SETTINGS = {
    "resolution": "1280x720",
    "dpi": 240,
    "bitrate": "16M",
    "auto_sync": False
}

def load_settings():
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return {**DEFAULT_SETTINGS, **json.load(f)}
        except: pass
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)

class DroidTuxApp(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="DroidTux Dashboard")
        self.set_default_size(500, 700)
        
        self.settings = load_settings()
        self.serial = None
        self.automatic = False

        # Apply CSS
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(NORD_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.setup_ui()
        
    def setup_ui(self):
        # Main Toolbar View
        toolbar_view = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        toolbar_view.add_top_bar(hb)
        self.set_content(toolbar_view)

        # View Stack
        self.stack = Adw.ViewStack()
        toolbar_view.set_content(self.stack)

        # View Switcher in Header Bar
        switcher = Adw.ViewSwitcher(stack=self.stack)
        hb.set_title_widget(switcher)

        # PAGE 1: Sync Dashboard
        sync_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.setup_sync_page(sync_box)
        self.stack.add_titled_with_icon(
            sync_box,
            "sync",
            "Sync",
            "view-refresh-symbolic"
        )

        # PAGE 2: Settings
        settings_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.setup_settings_page(settings_box)
        self.stack.add_titled_with_icon(
            settings_box,
            "settings",
            "Settings",
            "preferences-system-symbolic"
        )

    def setup_sync_page(self, vbox):
        # Header Box
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        header.add_css_class("header")
        
        if LOGO_PATH and LOGO_PATH.exists():
            img = Gtk.Image.new_from_file(str(LOGO_PATH))
            img.set_pixel_size(120)
            header.append(img)

        title = Gtk.Label(label="DroidTux")
        title.add_css_class("brand-title")
        header.append(title)
        
        subtitle = Gtk.Label(label="Android Desktop Integrator")
        subtitle.add_css_class("subtitle")
        header.append(subtitle)
        vbox.append(header)

        # Main Card
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        card.add_css_class("card")
        card.set_vexpand(True)
        vbox.append(card)

        self.status_label = Gtk.Label(label="Ready to sync")
        self.status_label.set_halign(Gtk.Align.CENTER)
        card.append(self.status_label)

        self.progress_bar = Gtk.ProgressBar()
        card.append(self.progress_bar)

        # Log Area
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.add_css_class("log-view")
        self.text_view = Gtk.TextView()
        self.text_view.set_editable(False)
        self.text_view.set_cursor_visible(False)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        scrolled.set_child(self.text_view)
        card.append(scrolled)

        # Action Buttons
        bbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bbox.set_homogeneous(True)
        bbox.set_margin_top(10)
        bbox.set_margin_bottom(10)
        card.append(bbox)

        self.sync_btn = Gtk.Button(label="START SYNC (all apps)")
        self.sync_btn.add_css_class("suggested-action")
        self.sync_btn.connect("clicked", self.on_sync_clicked)
        bbox.append(self.sync_btn)

        self.select_btn = Gtk.Button(label="CUSTOM APP SELECT")
        self.select_btn.connect("clicked", self.on_custom_select_clicked)
        bbox.append(self.select_btn)

        help_btn = Gtk.Button(label="USB HELP")
        help_btn.connect("clicked", self.show_usb_help)
        bbox.append(help_btn)

    def setup_settings_page(self, vbox):
        vbox.set_spacing(10)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        vbox.set_margin_start(20)
        vbox.set_margin_end(20)

        # Logo
        if LOGO_PATH and LOGO_PATH.exists():
            img = Gtk.Image.new_from_file(str(LOGO_PATH))
            img.set_pixel_size(80)
            vbox.append(img)

        title = Gtk.Label()
        title.set_markup("<span size='large' weight='bold'>DroidTux Control Panel</span>")
        vbox.append(title)

        grid = Gtk.Grid(column_spacing=15, row_spacing=15)
        grid.set_halign(Gtk.Align.CENTER)
        vbox.append(grid)

        # Resolution
        res_label = Gtk.Label(label="Resolution:")
        res_label.set_xalign(1.0)
        grid.attach(res_label, 0, 0, 1, 1)
        
        self.res_combo = Gtk.ComboBoxText()
        res_opts = ["1920x1080", "1600x900", "1280x720", "1024x576", "800x450"]
        for opt in res_opts:
            self.res_combo.append_text(opt)
        self.res_combo.set_active(res_opts.index(self.settings["resolution"]) if self.settings["resolution"] in res_opts else 2)
        grid.attach(self.res_combo, 1, 0, 1, 1)

        # DPI
        dpi_label = Gtk.Label(label="DPI (Density):")
        dpi_label.set_xalign(1.0)
        grid.attach(dpi_label, 0, 1, 1, 1)
        
        self.dpi_adj = Gtk.Adjustment(value=self.settings["dpi"], lower=120, upper=480, step_increment=10, page_increment=40, page_size=0)
        self.dpi_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.dpi_adj)
        self.dpi_scale.set_size_request(200, -1)
        grid.attach(self.dpi_scale, 1, 1, 1, 1)

        # Bitrate
        bit_label = Gtk.Label(label="Bitrate:")
        bit_label.set_xalign(1.0)
        grid.attach(bit_label, 0, 2, 1, 1)
        
        self.bit_combo = Gtk.ComboBoxText()
        bit_opts = ["4M", "8M", "16M", "32M"]
        for opt in bit_opts:
            self.bit_combo.append_text(opt)
        self.bit_combo.set_active(bit_opts.index(self.settings["bitrate"]) if self.settings["bitrate"] in bit_opts else 2)
        grid.attach(self.bit_combo, 1, 2, 1, 1)

        # Automatic sync
        self.auto_sync_check = Gtk.CheckButton(label="Enable automatic sync on USB connect")
        self.auto_sync_check.set_active(bool(self.settings.get("auto_sync", False)))
        grid.attach(self.auto_sync_check, 1, 3, 1, 1)

        # Save Button
        save_btn = Gtk.Button(label="SAVE CHANGES")
        save_btn.connect("clicked", self.on_save_clicked)
        save_btn.add_css_class("suggested-action")
        vbox.append(save_btn)

        # Help Buttons
        help_label = Gtk.Label()
        help_label.set_markup("<span weight='bold'>Help &amp; Configuration</span>")
        vbox.append(help_label)

        h_bbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        vbox.append(h_bbox)

        btns = [
            ("ADB Debugging", self.show_adb_help),
            ("SecondScreen", self.show_ss_help),
            ("USB Installation", self.show_usb_help)
        ]
        for label, cmd in btns:
            b = Gtk.Button(label=label)
            b.connect("clicked", cmd)
            h_bbox.append(b)

    def on_save_clicked(self, btn):
        self.settings["resolution"] = self.res_combo.get_active_text()
        self.settings["dpi"] = int(self.dpi_adj.get_value())
        self.settings["bitrate"] = self.bit_combo.get_active_text()
        self.settings["auto_sync"] = self.auto_sync_check.get_active()
        save_settings(self.settings)
        
        dialog = Adw.MessageDialog(transient_for=self, heading="Settings Saved",
                                  body="Changes will be applied on next connection.")
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.present()

    def show_help(self, title, content):
        dialog = Adw.MessageDialog(transient_for=self, heading=title, body=content)
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.present()

    def show_adb_help(self, btn):
        self.show_help("ADB Debugging", 
            "1. Go to 'Settings' on your phone.\n"
            "2. 'About phone' -> Tap 'Build number' 7 times.\n"
            "3. Go back -> 'System' -> 'Developer options'.\n"
            "4. Enable 'USB Debugging'.")

    def show_ss_help(self, btn):
        self.show_help("SecondScreen", 
            "1. Install SecondScreen from Play Store.\n"
            "2. Create a new profile named exactly 'Linux'.\n"
            "3. Set resolution to 1920x1080 and density to 240.")

    def show_usb_help(self, btn):
        self.show_help("USB Installation", 
            "On Xiaomi/MIUI phones:\n\n1. Developer options -> Enable 'Install via USB'.\n2. May require Mi Account login.")

    def log(self, message):
        print(f"[DroidTux] {message}")
        if hasattr(self, 'text_view'):
            GLib.idle_add(self._log_idle, message)
        if hasattr(self, 'splash') and self.splash:
            GLib.idle_add(self.splash.update_status, message)

    def _log_idle(self, message):
        buffer = self.text_view.get_buffer()
        buffer.insert(buffer.get_end_iter(), f"> {message}\n")
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
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Error",
            body=text
        )
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.present()
        return False

    def _show_app_selector_dialog(self, packages, serial):
        dialog = Adw.Window(
            title="Select apps to integrate",
            transient_for=self,
            modal=True,
            default_width=420,
            default_height=600
        )

        hb = Adw.HeaderBar()
        
        cancel_btn = Gtk.Button(label="Cancel")
        integrate_btn = Gtk.Button(label="Integrate selected")
        integrate_btn.add_css_class("suggested-action")
        
        hb.pack_start(cancel_btn)
        hb.pack_end(integrate_btn)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(hb)
        dialog.set_content(toolbar_view)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        content.set_margin_top(10)
        content.set_margin_bottom(10)
        content.set_margin_start(10)
        content.set_margin_end(10)
        toolbar_view.set_content(content)

        search_entry = Gtk.SearchEntry()
        search_entry.set_placeholder_text("Filter apps...")
        content.append(search_entry)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        content.append(scrolled)

        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        scrolled.set_child(listbox)

        checkboxes = {}
        icon_images = {}

        for pkg in packages:
            row = Gtk.ListBoxRow()
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            hbox.set_margin_top(4)
            hbox.set_margin_bottom(4)
            hbox.set_margin_start(6)
            hbox.set_margin_end(6)

            check = Gtk.CheckButton()
            hbox.append(check)
            checkboxes[pkg] = check

            icon_img = Gtk.Image.new_from_icon_name("application-x-executable")
            icon_img.set_icon_size(Gtk.IconSize.LARGE)
            
            # Use cached local icon if already extracted previously
            local_icon = ICONS_DIR / f"{pkg}.png"
            if local_icon.exists():
                try:
                    icon_img.set_from_file(str(local_icon))
                    icon_img.set_pixel_size(32)
                except:
                    pass

            hbox.append(icon_img)
            icon_images[pkg] = icon_img

            label = Gtk.Label(label=pkg)
            label.set_halign(Gtk.Align.START)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            hbox.append(label)

            row.set_child(hbox)
            row.pkg_name = pkg
            listbox.append(row)

        def on_search_changed(entry):
            query = entry.get_text().lower()
            child = listbox.get_first_child()
            while child:
                child.set_visible(query in child.pkg_name.lower())
                child = child.get_next_sibling()
        search_entry.connect("search-changed", on_search_changed)

        select_all_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        select_all_btn = Gtk.Button(label="Select all")
        deselect_all_btn = Gtk.Button(label="Deselect all")
        select_all_row.append(select_all_btn)
        select_all_row.append(deselect_all_btn)
        select_all_btn.set_hexpand(True)
        deselect_all_btn.set_hexpand(True)
        content.append(select_all_row)
        
        select_all_btn.connect("clicked", lambda b: [c.set_active(True) for c in checkboxes.values()])
        deselect_all_btn.connect("clicked", lambda b: [c.set_active(False) for c in checkboxes.values()])

        stop_flag = {"stop": False}
        def load_icons():
            # Trigger asynchronous extraction of all launcher app icons on phone
            self.run_adb("shell am start-foreground-service -n com.droidtux.bridge/.IconService --es package all", serial)
            time.sleep(1.0)
            
            BRIDGE_REMOTE_DIR = "/sdcard/Android/data/com.droidtux.bridge/files"
            
            # Periodically pull directory content and update icons in UI
            for _ in range(20):
                if stop_flag["stop"]:
                    return
                # Pull the entire folder to ICONS_DIR (only downloads modifications)
                self.run_adb(f"pull {BRIDGE_REMOTE_DIR}/. {ICONS_DIR}/", serial)
                
                # Scan local ICONS_DIR and update Gtk.Image widgets in list box
                for pkg in packages:
                    icon_path = ICONS_DIR / f"{pkg}.png"
                    if icon_path.exists():
                        GLib.idle_add(self._update_selector_icon, icon_images, pkg, str(icon_path))
                
                time.sleep(1.0)

        icon_thread = threading.Thread(target=load_icons, daemon=True)
        icon_thread.start()

        def on_cancel(btn):
            stop_flag["stop"] = True
            dialog.destroy()
        cancel_btn.connect("clicked", on_cancel)

        def on_integrate(btn):
            stop_flag["stop"] = True
            selected = [pkg for pkg, cb in checkboxes.items() if cb.get_active()]
            dialog.destroy()

            if selected:
                self.sync_btn.set_sensitive(False)
                self.select_btn.set_sensitive(False)
                self.text_view.get_buffer().set_text("")
                threading.Thread(target=self.run_sync, args=(selected,), daemon=True).start()

        integrate_btn.connect("clicked", on_integrate)
        dialog.present()

    def _update_selector_icon(self, icon_images, pkg, icon_path):
        try:
            icon_images[pkg].set_from_file(icon_path)
            icon_images[pkg].set_pixel_size(32)
        except Exception:
            pass
        return False

    def show_usb_help(self, btn):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="How to enable 'Install via USB'",
            body=(
                "If you don't see 'Install via USB' in Developer Options:\n\n"
                "1. XIAOMI / MIUI: Log in to your Mi Account and insert a SIM card.\n"
                "2. REALME / OPPO: Enable 'ADB Installation'.\n"
                "3. OTHERS: Search for 'Allow app installation via ADB'.\n\n"
                "DroidTux needs this for high-quality icons."
            )
        )
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.present()

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
        if BRIDGE_APK and BRIDGE_APK.exists():
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
            
            self.run_adb(f"shell \"rm /sdcard/Download/{pkg}.png /sdcard/Download/{pkg}.label 2>/dev/null\"", serial)
            self.run_adb(f"shell \"rm {BRIDGE_REMOTE_DIR}/{pkg}.png {BRIDGE_REMOTE_DIR}/{pkg}.label 2>/dev/null\"", serial)
            
            self.run_adb(f"shell am start-foreground-service -n com.droidtux.bridge/.IconService --es package {pkg}", serial)
            
            icon_path = ICONS_DIR / f"{pkg}.png"
            name = pkg.split('.')[-1].capitalize()
            
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
            threading.Thread(target=self.watchdog, daemon=True).start()
        else:
            if hasattr(self, 'sync_btn'):
                GLib.idle_add(self.sync_btn.set_sensitive, True)

def cleanup():
    print("Cleaning DroidTux apps...")
    prefixes = ["dtapp-*.desktop", "droidtux-*.desktop"]
    for pattern in prefixes:
        for f in DESKTOP_DIR.glob(pattern):
            try: f.unlink()
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
    def __init__(self, app):
        super().__init__(application=app)
        self.set_keep_above(True)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(250, 200)
        self.add_css_class("splash-window")

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        vbox.set_valign(Gtk.Align.CENTER)
        vbox.set_halign(Gtk.Align.CENTER)
        vbox.set_margin_start(20)
        vbox.set_margin_end(20)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        self.set_child(vbox)

        if LOGO_PATH and LOGO_PATH.exists():
            img = Gtk.Image.new_from_file(str(LOGO_PATH))
            img.set_pixel_size(64)
            vbox.append(img)

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(32, 32)
        self.spinner.start()
        vbox.append(self.spinner)

        self.status_label = Gtk.Label(label="Initializing...")
        self.status_label.add_css_class("splash-label")
        self.status_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.status_label.set_max_width_chars(25)
        self.status_label.set_halign(Gtk.Align.CENTER)
        vbox.append(self.status_label)

    def update_status(self, text):
        self.status_label.set_text(text)

    def update_progress(self, text, fraction):
        self.status_label.set_text(text)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DroidTux Integrator")
    parser.add_argument("--add", action="store_true", help="Sync automatically")
    parser.add_argument("--remove", action="store_true", help="Remove apps")
    parser.add_argument("--settings", action="store_true", help="Open settings panel directly")
    args = parser.parse_args()

    if args.remove:
        cleanup()
        sys.exit(0)

    app = Adw.Application(application_id="com.droidtux.dashboard", flags=Gio.ApplicationFlags.FLAGS_NONE)

    def on_activate(application):
        main_win = DroidTuxApp(application)
        if args.add:
            settings = load_settings()
            if not settings.get("auto_sync", False):
                print("Automatic sync is disabled in DroidTux settings.")
                application.quit()
                return

            print("Starting automatic sync (Splash Mode)...")
            main_win.automatic = True
            main_win.splash = DroidTuxSplash(application)
            main_win.splash.present()
            threading.Thread(target=main_win.run_sync, daemon=True).start()
        else:
            if args.settings:
                main_win.stack.set_visible_child_name("settings")
            main_win.present()

    app.connect("activate", on_activate)
    app.run([sys.argv[0]])
