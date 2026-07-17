#!/bin/bash
set -e

# Intentar localizar Android SDK y Build Tools si no están en el PATH (útil para CI)
if ! command -v aapt2 &> /dev/null; then
    ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$ANDROID_HOME}"
    if [ -d "$ANDROID_SDK_ROOT/build-tools" ]; then
        # Coger la versión más reciente de build-tools
        LATEST_BUILD_TOOLS=$(ls -1 "$ANDROID_SDK_ROOT/build-tools" | sort -V | tail -n 1)
        export PATH="$PATH:$ANDROID_SDK_ROOT/build-tools/$LATEST_BUILD_TOOLS"
        echo "[*] Añadido al PATH: $ANDROID_SDK_ROOT/build-tools/$LATEST_BUILD_TOOLS"
    fi
fi

# Verificar de nuevo
if ! command -v aapt2 &> /dev/null; then
    echo "[!] Error: No se pudo encontrar 'aapt2'. Asegúrate de tener instalado el Android SDK Build-Tools."
    exit 1
fi

PLATFORMS_DIR="${ANDROID_SDK_ROOT:-/usr/lib/android-sdk}/platforms"
if [ -d "$PLATFORMS_DIR" ]; then
    LATEST_PLATFORM=$(ls -1 "$PLATFORMS_DIR" | grep -E '^android-[0-9]+$' | sort -V | tail -n 1)
    if [ -n "$LATEST_PLATFORM" ]; then
        SDK_PLATFORM="$PLATFORMS_DIR/$LATEST_PLATFORM"
        echo "[*] Usando plataforma Android detectada: $LATEST_PLATFORM"
    else
        SDK_PLATFORM="$PLATFORMS_DIR/android-34"
    fi
else
    SDK_PLATFORM="/usr/lib/android-sdk/platforms/android-34"
fi
ANDROID_JAR="$SDK_PLATFORM/android.jar"
BUILD_DIR="build_out"
SRC_DIR="bridge_src"
PACKAGE_NAME="com.droidtux.bridge"

echo "[*] Limpiando entorno..."
rm -rf "$BUILD_DIR" && mkdir -p "$BUILD_DIR/obj" "$BUILD_DIR/apk"

echo "[*] Generando recursos..."
mkdir -p res
if [ "$(ls -A res)" ]; then
    aapt2 compile --dir res -o "$BUILD_DIR/res.zip"
    aapt2 link "$BUILD_DIR/res.zip" -I "$ANDROID_JAR" \
        --manifest "$SRC_DIR/AndroidManifest.xml" \
        --java "$BUILD_DIR/gen" \
        -o "$BUILD_DIR/base.apk"
else
    echo "[*] No se detectaron recursos, enlazando solo con el manifiesto..."
    aapt2 link -I "$ANDROID_JAR" \
        --manifest "$SRC_DIR/AndroidManifest.xml" \
        --java "$BUILD_DIR/gen" \
        -o "$BUILD_DIR/base.apk"
fi

echo "[*] Compilando Java..."
javac -d "$BUILD_DIR/obj" \
    -classpath "$ANDROID_JAR" \
    "$SRC_DIR/IconService.java"

echo "[*] Generando DEX..."
mkdir -p "$BUILD_DIR/dex"
d8 --release --output "$BUILD_DIR/dex" \
    --lib "$ANDROID_JAR" \
    "$BUILD_DIR/obj/com/droidtux/bridge/IconService.class"

echo "[*] Construyendo APK final..."
cp "$BUILD_DIR/base.apk" "$BUILD_DIR/droidtux-bridge.apk"
cd "$BUILD_DIR/dex"
zip -u "../droidtux-bridge.apk" "classes.dex"
cd ../..

echo "[*] Alineando APK..."
zipalign -f 4 "$BUILD_DIR/droidtux-bridge.apk" "droidtux-bridge-aligned.apk"

echo "[*] Firmando APK (Debug)..."
# Generar keystore si no existe
if [ ! -f debug.keystore ]; then
    keytool -genkey -v -keystore debug.keystore -alias androiddebugkey -storepass android -keypass android -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Android Debug,O=Android,C=US"
fi

apksigner sign --ks debug.keystore --ks-pass pass:android --out droidtux-bridge-final.apk droidtux-bridge-aligned.apk

echo "[+] ¡APK generado con éxito: droidtux-bridge-final.apk!"
