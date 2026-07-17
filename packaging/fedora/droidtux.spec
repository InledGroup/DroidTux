Name:           droidtux
Version:        1.0.0
Release:        1%{?dist}
Summary:        Android Desktop Integrator
Summary(es):    Integrador de Aplicaciones Android

License:        MIT
URL:            https://github.com/nexu-io
Source0:        %{name}-%{version}.tar.gz

Requires:       scrcpy android-tools python3-gobject desktop-file-utils sudo
BuildArch:      noarch

%description
DroidTux is a tool designed to seamlessly integrate your Android applications directly into your Linux desktop.
It leverages scrcpy for screen mirroring and a small "Bridge" app on the device to extract original icons and labels.

%description -l es
DroidTux es una herramienta diseñada para integrar de forma fluida tus aplicaciones de Android directamente en tu escritorio Linux.
Utiliza scrcpy para la transmisión de pantalla y un pequeño "Bridge" en el dispositivo para extraer iconos y etiquetas originales.

%prep
# No source tarball yet, we assume the files are in the current directory during build
# En un entorno real, aquí se desempaquetaría el source0
mkdir -p %{name}-%{version}
cp -r %{_sourcedir}/* %{name}-%{version}/

%install
mkdir -p %{buildroot}/usr/local/share/droidtux
mkdir -p %{buildroot}/usr/local/bin
mkdir -p %{buildroot}/usr/share/icons/hicolor/512x512/apps
mkdir -p %{buildroot}/etc/udev/rules.d
mkdir -p %{buildroot}/usr/share/applications
mkdir -p %{buildroot}/usr/lib/systemd/user

# Copy main files
# Copiar archivos principales
cp app_integrator.py %{buildroot}/usr/local/share/droidtux/
cp droidtux_settings.py %{buildroot}/usr/local/share/droidtux/
cp droidtux.png %{buildroot}/usr/local/share/droidtux/
cp 99-android-integrator.rules %{buildroot}/usr/local/share/droidtux/
cp droidtux-bridge-final.apk %{buildroot}/usr/local/share/droidtux/

# Copy icons and rules
# Copiar iconos y reglas
cp droidtux.png %{buildroot}/usr/share/icons/hicolor/512x512/apps/droidtux.png
cp 99-android-integrator.rules %{buildroot}/etc/udev/rules.d/

# Install systemd service
# Instalar servicio de systemd
cat > %{buildroot}/usr/lib/systemd/user/android-integrator.service << EOF
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

# Create trigger script
# Crear script disparador
cat > %{buildroot}/usr/local/bin/android-integrator-trigger.sh << 'EOF'
#!/bin/bash
exec &> >(logger -t droidtux-trigger)
echo "Trigger called with argument: $1"

for uid in $(loginctl list-sessions --no-legend | awk '{print $2}'); do
    user=$(id -un "$uid")
    display=$(sudo -u "$user" env | grep '^DISPLAY=' | cut -d= -f2-)
    if [ -z "$display" ]; then
        display=$(pgrep -u "$uid" -a gnome-session | grep -o 'DISPLAY=[^ ]*' | cut -d= -f2 | head -n1)
        [ -z "$display" ] && display=":0"
    fi

    if [ "$1" == "add" ]; then
        sudo -u "$user" env DISPLAY="$display" XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" systemctl --user restart android-integrator.service
    elif [ "$1" == "remove" ]; then
        sudo -u "$user" env XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" systemctl --user stop android-integrator.service
    fi
done
EOF
chmod +x %{buildroot}/usr/local/bin/android-integrator-trigger.sh

# Create wrapper scripts
# Crear scripts envoltorios
cat > %{buildroot}/usr/local/bin/droidtux-sync << 'EOF'
#!/bin/bash
/usr/bin/python3 /usr/local/share/droidtux/app_integrator.py "$@"
EOF
cat > %{buildroot}/usr/local/bin/droidtux-settings << 'EOF'
#!/bin/bash
/usr/bin/python3 /usr/local/share/droidtux/droidtux_settings.py "$@"
EOF
chmod +x %{buildroot}/usr/local/bin/droidtux-sync
chmod +x %{buildroot}/usr/local/bin/droidtux-settings

# Desktop entries
# Entradas de escritorio
cat > %{buildroot}/usr/share/applications/droidtux_sync.desktop << EOF
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
cat > %{buildroot}/usr/share/applications/droidtux_settings.desktop << EOF
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

%post

# Setup RPM Repository
if [ -d /etc/yum.repos.d ]; then
    echo "Configuring DroidTux RPM repository..."
    cat > /etc/yum.repos.d/inled.repo << EOF
[inled]
name=Inled Repository
baseurl=https://apt.inled.es/rpm/
enabled=1
gpgcheck=1
gpgkey=https://apt.inled.es/archive.key
EOF
fi

# Reload udev
udevadm control --reload-rules && udevadm trigger

# Update databases
update-desktop-database /usr/share/applications || true
gtk-update-icon-cache -f -t /usr/share/icons/hicolor || true

%postun
update-desktop-database /usr/share/applications || true

%files
/usr/local/share/droidtux/
/usr/local/bin/android-integrator-trigger.sh
/usr/local/bin/droidtux-sync
/usr/local/bin/droidtux-settings
/usr/share/icons/hicolor/512x512/apps/droidtux.png
/etc/udev/rules.d/99-android-integrator.rules
/usr/lib/systemd/user/android-integrator.service
/usr/share/applications/droidtux_sync.desktop
/usr/share/applications/droidtux_settings.desktop

%changelog
* Wed Jun 17 2026 Jaime <hi@inled.es> - 1.0.0-1
- Initial release for Fedora
