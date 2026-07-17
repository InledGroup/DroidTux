import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf
import json
import os
import subprocess
from pathlib import Path

SETTINGS_DIR = Path.home() / ".config/droidtux"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
BASE_DIR = Path(__file__).resolve().parent

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

class DroidTuxSettingsApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="DroidTux Settings")
        self.set_default_size(450, 600)
        self.set_position(Gtk.WindowPosition.CENTER)
        
        if LOGO_PATH:
            self.set_icon_from_file(str(LOGO_PATH))
        
        self.settings = load_settings()
        self.setup_ui()
        self.show_all()

    def setup_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        vbox.set_margin_start(20)
        vbox.set_margin_end(20)
        self.add(vbox)

        # Logo
        if LOGO_PATH.exists():
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(LOGO_PATH), 80, 80, True)
            img = Gtk.Image.new_from_pixbuf(pixbuf)
            vbox.pack_start(img, False, False, 0)

        title = Gtk.Label(label="DroidTux Control Panel")
        title.set_markup("<span size='large' weight='bold'>DroidTux Control Panel</span>")
        vbox.pack_start(title, False, False, 10)

        grid = Gtk.Grid(column_spacing=15, row_spacing=15)
        grid.set_halign(Gtk.Align.CENTER)
        vbox.pack_start(grid, True, True, 0)

        # Resolution
        grid.attach(Gtk.Label(label="Resolution:", xalign=1), 0, 0, 1, 1)
        self.res_combo = Gtk.ComboBoxText()
        res_opts = ["1920x1080", "1600x900", "1280x720", "1024x576", "800x450"]
        for opt in res_opts: self.res_combo.append_text(opt)
        self.res_combo.set_active(res_opts.index(self.settings["resolution"]) if self.settings["resolution"] in res_opts else 2)
        grid.attach(self.res_combo, 1, 0, 1, 1)

        # DPI
        grid.attach(Gtk.Label(label="DPI (Density):", xalign=1), 0, 1, 1, 1)
        self.dpi_adj = Gtk.Adjustment(value=self.settings["dpi"], lower=120, upper=480, step_increment=10, page_increment=40, page_size=0)
        self.dpi_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.dpi_adj)
        self.dpi_scale.set_size_request(200, -1)
        grid.attach(self.dpi_scale, 1, 1, 1, 1)

        # Bitrate
        grid.attach(Gtk.Label(label="Bitrate:", xalign=1), 0, 2, 1, 1)
        self.bit_combo = Gtk.ComboBoxText()
        bit_opts = ["4M", "8M", "16M", "32M"]
        for opt in bit_opts: self.bit_combo.append_text(opt)
        self.bit_combo.set_active(bit_opts.index(self.settings["bitrate"]) if self.settings["bitrate"] in bit_opts else 2)
        grid.attach(self.bit_combo, 1, 2, 1, 1)

        # Automatic sync
        self.auto_sync_check = Gtk.CheckButton(label="Enable automatic sync on USB connect")
        self.auto_sync_check.set_active(bool(self.settings.get("auto_sync", False)))
        grid.attach(self.auto_sync_check, 1, 3, 1, 1)

        # Save Button
        save_btn = Gtk.Button(label="SAVE CHANGES")
        save_btn.connect("clicked", self.on_save_clicked)
        save_btn.get_style_context().add_class("suggested-action")
        vbox.pack_start(save_btn, False, False, 10)

        # Help Buttons
        help_label = Gtk.Label(label="Help &amp; Configuration")
        help_label.set_markup("<span weight='bold'>Help &amp; Configuration</span>")
        vbox.pack_start(help_label, False, False, 10)

        h_bbox = Gtk.ButtonBox(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        vbox.pack_start(h_bbox, False, False, 0)

        btns = [
            ("ADB Debugging", self.show_adb_help),
            ("SecondScreen", self.show_ss_help),
            ("USB Installation", self.show_usb_help)
        ]
        for label, cmd in btns:
            b = Gtk.Button(label=label)
            b.connect("clicked", cmd)
            h_bbox.add(b)

    def on_save_clicked(self, btn):
        self.settings["resolution"] = self.res_combo.get_active_text()
        self.settings["dpi"] = int(self.dpi_adj.get_value())
        self.settings["bitrate"] = self.bit_combo.get_active_text()
        self.settings["auto_sync"] = self.auto_sync_check.get_active()
        save_settings(self.settings)
        
        dialog = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.INFO,
                                  buttons=Gtk.ButtonsType.OK, text="Settings Saved")
        dialog.format_secondary_text("Changes will be applied on next connection.")
        dialog.run()
        dialog.destroy()

    def show_help(self, title, content):
        dialog = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.INFO,
                                  buttons=Gtk.ButtonsType.OK, text=title)
        dialog.format_secondary_text(content)
        dialog.run()
        dialog.destroy()

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

if __name__ == "__main__":
    app = DroidTuxSettingsApp()
    Gtk.main()
