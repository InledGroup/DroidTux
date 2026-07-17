import os
import subprocess
import shutil
import tempfile
import threading
import json
import time
import webbrowser
import socket
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
    "auto_sync": False,
    "audio_redirect": True,
    "v4l2_sink": "",
    "force_x11": True
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
        self.set_default_size(500, 750)
        
        self.settings = load_settings()
        self.serial = None
        self.automatic = False
        self.devices_map = {}

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

        # Device Selector Box
        dev_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        dev_box.set_margin_start(20)
        dev_box.set_margin_end(20)
        dev_box.set_margin_top(15)
        dev_box.set_margin_bottom(5)
        vbox.append(dev_box)

        dev_label = Gtk.Label(label="Device:")
        dev_box.append(dev_label)

        self.device_dropdown = Gtk.DropDown()
        self.device_dropdown.set_hexpand(True)
        self.device_dropdown.connect("notify::selected", self.on_device_changed)
        dev_box.append(self.device_dropdown)

        self.refresh_btn = Gtk.Button(label="Scan & Refresh")
        self.refresh_btn.connect("clicked", self.on_refresh_clicked)
        dev_box.append(self.refresh_btn)

        # Main Card
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        card.add_css_class("card")
        card.set_vexpand(True)
        vbox.append(card)

        # Single line status label
        self.status_label = Gtk.Label(label="Ready to sync")
        self.status_label.set_halign(Gtk.Align.CENTER)
        card.append(self.status_label)

        # Progress bar (hidden by default)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_visible(False)
        card.append(self.progress_bar)

        # Collapsible Log Expander
        self.log_expander = Gtk.Expander(label="Show Sync Logs")
        self.log_expander.set_expanded(False)
        card.append(self.log_expander)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_size_request(-1, 150)
        scrolled.add_css_class("log-view")
        self.text_view = Gtk.TextView()
        self.text_view.set_editable(False)
        self.text_view.set_cursor_visible(False)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        scrolled.set_child(self.text_view)
        
        self.log_expander.set_child(scrolled)

        # Action Buttons (Sync, Custom, Camera, Help)
        bbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bbox.set_homogeneous(True)
        bbox.set_margin_top(10)
        bbox.set_margin_bottom(10)
        card.append(bbox)

        self.sync_btn = Gtk.Button(label="START SYNC")
        self.sync_btn.add_css_class("suggested-action")
        self.sync_btn.connect("clicked", self.on_sync_clicked)
        bbox.append(self.sync_btn)

        self.select_btn = Gtk.Button(label="CUSTOM SELECT")
        self.select_btn.connect("clicked", self.on_custom_select_clicked)
        bbox.append(self.select_btn)

        self.camera_btn = Gtk.Button(label="PHONE CAMERA")
        self.camera_btn.connect("clicked", self.on_camera_clicked)
        bbox.append(self.camera_btn)

        help_btn = Gtk.Button(label="HELP")
        help_btn.connect("clicked", lambda b: webbrowser.open("https://help.inled.es"))
        bbox.append(help_btn)

        # Start initial device scan
        GLib.idle_add(lambda: self.on_refresh_clicked(self.refresh_btn))

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
        
        res_opts = ["1920x1080", "1600x900", "1280x720", "1024x576", "800x450"]
        self.res_dropdown = Gtk.DropDown.new_from_strings(res_opts)
        idx = res_opts.index(self.settings["resolution"]) if self.settings["resolution"] in res_opts else 2
        self.res_dropdown.set_selected(idx)
        grid.attach(self.res_dropdown, 1, 0, 1, 1)

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
        
        bit_opts = ["4M", "8M", "16M", "32M"]
        self.bit_dropdown = Gtk.DropDown.new_from_strings(bit_opts)
        idx = bit_opts.index(self.settings["bitrate"]) if self.settings["bitrate"] in bit_opts else 2
        self.bit_dropdown.set_selected(idx)
        grid.attach(self.bit_dropdown, 1, 2, 1, 1)

        # Automatic sync
        self.auto_sync_check = Gtk.CheckButton(label="Enable automatic sync on USB connect")
        self.auto_sync_check.set_active(bool(self.settings.get("auto_sync", False)))
        grid.attach(self.auto_sync_check, 1, 3, 1, 1)

        # Audio redirection
        self.audio_check = Gtk.CheckButton(label="Redirect Audio to PC (scrcpy 2.0+)")
        self.audio_check.set_active(bool(self.settings.get("audio_redirect", True)))
        grid.attach(self.audio_check, 1, 4, 1, 1)

        # V4L2 webcam sink
        v4l2_label = Gtk.Label(label="V4L2 Loopback (Webcam):")
        v4l2_label.set_xalign(1.0)
        grid.attach(v4l2_label, 0, 5, 1, 1)
        
        self.v4l2_entry = Gtk.Entry()
        self.v4l2_entry.set_placeholder_text("e.g. /dev/video2 (optional)")
        self.v4l2_entry.set_text(self.settings.get("v4l2_sink", ""))
        grid.attach(self.v4l2_entry, 1, 5, 1, 1)

        # Force X11 for OBS
        self.x11_check = Gtk.CheckButton(label="Force X11 Mode (highly recommended for OBS capture on Wayland)")
        self.x11_check.set_active(bool(self.settings.get("force_x11", True)))
        grid.attach(self.x11_check, 1, 6, 1, 1)

        # Save Button
        save_btn = Gtk.Button(label="SAVE CHANGES")
        save_btn.connect("clicked", self.on_save_clicked)
        save_btn.add_css_class("suggested-action")
        vbox.append(save_btn)

        # Help Button
        help_btn = Gtk.Button(label="HELP & SUPPORT")
        help_btn.connect("clicked", lambda b: webbrowser.open("https://help.inled.es"))
        vbox.append(help_btn)

    def on_save_clicked(self, btn):
        res_item = self.res_dropdown.get_selected_item()
        self.settings["resolution"] = res_item.get_string() if res_item else "1280x720"
        self.settings["dpi"] = int(self.dpi_adj.get_value())
        bit_item = self.bit_dropdown.get_selected_item()
        self.settings["bitrate"] = bit_item.get_string() if bit_item else "16M"
        self.settings["auto_sync"] = self.auto_sync_check.get_active()
        self.settings["audio_redirect"] = self.audio_check.get_active()
        self.settings["v4l2_sink"] = self.v4l2_entry.get_text().strip()
        self.settings["force_x11"] = self.x11_check.get_active()
        save_settings(self.settings)
        
        dialog = Adw.MessageDialog(transient_for=self, heading="Settings Saved",
                                  body="Changes will be applied on next connection.")
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.present()

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

    def on_refresh_clicked(self, btn):
        btn.set_sensitive(False)
        self.device_dropdown.set_sensitive(False)
        self.device_dropdown.set_model(Gtk.StringList.new(["Scanning network..."]))
        self.device_dropdown.set_selected(0)
        
        def run_refresh():
            discovered_ips = []
            try:
                # Get local IP
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
                
                parts = local_ip.split('.')
                if len(parts) == 4:
                    base_ip = f"{parts[0]}.{parts[1]}.{parts[2]}."
                    
                    def check_ip(ip):
                        try:
                            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            sock.settimeout(0.15)
                            if sock.connect_ex((ip, 5555)) == 0:
                                discovered_ips.append(ip)
                            sock.close()
                        except:
                            pass
                    
                    threads = []
                    for i in range(1, 255):
                        t = threading.Thread(target=check_ip, args=(base_ip + str(i),))
                        threads.append(t)
                        t.start()
                    for t in threads:
                        t.join()
            except Exception as e:
                print(f"[Scan Error] {e}")

            # Connect discovered TCP devices
            for ip in discovered_ips:
                self.run_adb(f"connect {ip}:5555")

            # Query connected devices
            output = self.run_adb("devices")
            lines = [l for l in (output or "").splitlines()[1:] if l.strip()]
            devices = [l.split()[0] for l in lines if "\tdevice" in l]

            # Fetch human readable names for each device
            devices_info = []
            for d in devices:
                brand = self.run_adb("shell getprop ro.product.brand", d).strip()
                model = self.run_adb("shell getprop ro.product.model", d).strip()
                if "ERROR" in brand or not brand: brand = ""
                if "ERROR" in model or not model: model = ""
                name = f"{brand} {model}".strip()
                if not name: name = "Android Device"
                
                conn_type = "Wireless" if ":" in d else "USB"
                display_name = f"{name} ({conn_type}: {d})"
                devices_info.append((d, display_name))

            GLib.idle_add(self._update_devices_combo, devices_info, btn)

        threading.Thread(target=run_refresh, daemon=True).start()

    def _update_devices_combo(self, devices_info, btn):
        self.devices_map.clear()
        if not devices_info:
            self.device_dropdown.set_model(Gtk.StringList.new(["No devices found"]))
            self.device_dropdown.set_selected(0)
            self.sync_btn.set_sensitive(False)
            self.select_btn.set_sensitive(False)
            self.camera_btn.set_sensitive(False)
            self.serial = None
        else:
            display_names = []
            for serial, display_name in devices_info:
                display_names.append(display_name)
                self.devices_map[display_name] = serial
            
            self.device_dropdown.set_model(Gtk.StringList.new(display_names))
            self.device_dropdown.set_selected(0)
            self.sync_btn.set_sensitive(True)
            self.select_btn.set_sensitive(True)
            self.camera_btn.set_sensitive(True)
            self.serial = devices_info[0][0]
            
        btn.set_sensitive(True)
        self.device_dropdown.set_sensitive(True)
        return False

    def on_device_changed(self, dropdown, pspec):
        selected_item = dropdown.get_selected_item()
        if selected_item:
            active_text = selected_item.get_string()
            if active_text and active_text not in ["Scanning network...", "No devices found"]:
                self.serial = self.devices_map.get(active_text)
                self.sync_btn.set_sensitive(True)
                self.select_btn.set_sensitive(True)
                self.camera_btn.set_sensitive(True)
                return
        
        self.serial = None
        self.sync_btn.set_sensitive(False)
        self.select_btn.set_sensitive(False)
        self.camera_btn.set_sensitive(False)

    def on_sync_clicked(self, btn):
        self.sync_btn.set_sensitive(False)
        self.progress_bar.set_visible(True)
        self.text_view.get_buffer().set_text("")
        threading.Thread(target=self.run_sync, daemon=True).start()

    def on_custom_select_clicked(self, btn):
        self.select_btn.set_sensitive(False)
        threading.Thread(target=self._prepare_app_selector, daemon=True).start()

    def _set_button_spinner(self, btn, show_spinner, label_text):
        if show_spinner:
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            box.set_halign(Gtk.Align.CENTER)
            box.set_valign(Gtk.Align.CENTER)
            
            spinner = Gtk.Spinner()
            spinner.start()
            box.append(spinner)
            
            label = Gtk.Label(label=label_text)
            box.append(label)
            
            btn.set_child(box)
            btn.set_sensitive(False)
        else:
            btn.set_child(None)
            btn.set_label(label_text)
            btn.set_sensitive(True)
        return False

    def on_camera_clicked(self, btn):
        if not self.serial:
            self._show_error_dialog("No device selected.")
            return
        
        self.settings = load_settings()
        v4l2 = self.settings.get("v4l2_sink", "").strip()
        force_x11 = self.settings.get("force_x11", True)
        
        GLib.idle_add(self._set_button_spinner, btn, True, "Starting Camera...")
        
        # Safe fallback: stop spinner after 3 seconds anyway
        GLib.timeout_add_seconds(3, lambda: self._set_button_spinner(btn, False, "PHONE CAMERA") and False)
        
        def run_camera():
            self.log(f"Starting phone camera feed on {self.serial}...")
            
            env_vars = os.environ.copy()
            if force_x11:
                env_vars["SDL_VIDEODRIVER"] = "x11"
            
            cmd = f"scrcpy -s {self.serial} --video-source=camera"
            
            # Check if V4L2 device exists before trying to use it
            if v4l2 and os.path.exists(v4l2):
                self.log(f"Redirecting video output to V4L2 sink {v4l2}...")
                cmd += f" --v4l2-sink={v4l2}"
            else:
                if v4l2:
                    self.log(f"Warning: V4L2 device {v4l2} not found. Falling back to window display.")
                cmd += " --always-on-top"
                
            try:
                proc = subprocess.Popen(
                    cmd, shell=True, env=env_vars,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                
                spinner_active = True
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    print(f"[scrcpy] {line.strip()}")
                    if spinner_active and ("Texture:" in line or "v4l2-sink" in line or "INFO: Renderer:" in line):
                        GLib.idle_add(self._set_button_spinner, btn, False, "PHONE CAMERA")
                        spinner_active = False
                
                proc.wait()
                if spinner_active:
                    GLib.idle_add(self._set_button_spinner, btn, False, "PHONE CAMERA")
            except Exception as e:
                self.log(f"Error starting camera: {e}")
                GLib.idle_add(self._set_button_spinner, btn, False, "PHONE CAMERA")
            
        threading.Thread(target=run_camera, daemon=True).start()

    def _prepare_app_selector(self):
        if not self.serial:
            GLib.idle_add(self._show_error_dialog, "No device selected. Click Scan & Refresh.")
            GLib.idle_add(self.select_btn.set_sensitive, True)
            return

        serial = self.serial
        cmd = "shell \"cmd package query-activities --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER\""
        pkgs_raw = self.run_adb(cmd, serial)
        packages = sorted(set([l.split("/")[0].strip() for l in pkgs_raw.splitlines() if "/" in l]))

        GLib.idle_add(self.select_btn.set_sensitive, True)
        GLib.idle_add(self._show_app_selector_dialog, packages, serial)

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
                self.progress_bar.set_visible(True)
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
        if not self.serial:
            self.update_progress("Error: No device selected", 0)
            if not self.automatic:
                GLib.idle_add(self.sync_btn.set_sensitive, True)
                GLib.idle_add(self.select_btn.set_sensitive, True)
            return

        serial = self.serial
        self.log(f"Connected to {serial}")
        
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
        
        # Load settings
        self.settings = load_settings()
        resolution = self.settings.get("resolution", "1280x720")
        res_w = resolution.split('x')[0]
        res_h = resolution.split('x')[1]
        dpi = self.settings.get("dpi", 240)
        bitrate = self.settings.get("bitrate", "16M").lower()
        audio = self.settings.get("audio_redirect", True)

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

            audio_flag = "" if audio else " --no-audio"
            scrcpy_args = (
                f"-s {serial} --start-app={pkg} --window-title=\"{name}\" "
                f"--new-display={resolution}/{dpi} -b {bitrate} "
                f"--always-on-top --stay-awake{audio_flag}"
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
        [f.unlink() for f in DESKTOP_DIR.glob(pattern) if f.exists()]

    desktop_folders = [Path.home() / "Desktop", Path.home() / "Escritorio"]
    try:
        xdg_desktop = subprocess.check_output(["xdg-user-dir", "DESKTOP"], encoding='utf-8').strip()
        if xdg_desktop: desktop_folders.append(Path(xdg_desktop))
    except: pass

    for folder in set(desktop_folders):
        if folder.exists():
            for pattern in prefixes:
                [f.unlink() for f in folder.glob(pattern) if f.exists()]

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
