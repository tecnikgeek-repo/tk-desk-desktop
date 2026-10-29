#!/bin/bash
# Crea dist/tk-desk-<versione>-linux-<arch>.AppImage. Da eseguire su Linux (Ubuntu di casa o runner di GitHub).
# Uso: bash linux/build_linux.sh   (sull'Ubuntu di casa: flock /tmp/tk-build.lock bash linux/build_linux.sh)
# Usa al massimo METÀ dei processori (JOBS per cambiarlo): con tutti, sul PC di casa la memoria si riempie.
# Non installa niente nel sistema: le librerie native che mancano a Ubuntu di base si prendono con apt-get download.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export JOBS="${JOBS:-$(( $(nproc) / 2 > 0 ? $(nproc) / 2 : 1 ))}"  # esportato: dopo taskset nproc vede già la metà
if [ -z "${TK_BUILD_LIMITATA:-}" ] && command -v taskset >/dev/null; then
    export TK_BUILD_LIMITATA=1
    exec nice -n 10 taskset -c "0-$(( JOBS - 1 ))" bash "$0" "$@"
fi
ARCH="$(uname -m)"
PY="${PYTHON:-python3}"
VERSION="$($PY -c "import re;print(re.search(r'VERSION = \"(.+)\"', open('tkdesk/__init__.py').read()).group(1))")"
APPIMAGETOOL_VER="1.9.0"
echo "== tk-desk $VERSION per Linux ($ARCH), $JOBS processori"

$PY -m venv .venv-linux
# shellcheck disable=SC1091
source .venv-linux/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet "pyside6-essentials==6.11.*" certifi pyinstaller aiortc mss numpy sounddevice \
    secretstorage jeepney python-xlib six
# pynput senza evdev (serve solo al suo modo «uinput», che vorrebbe i permessi di amministratore e non usiamo)
python -m pip install --quiet --no-deps pynput

mkdir -p dist build
echo "== librerie native dai pacchetti Ubuntu (prese, non installate)"
LIBS="$ROOT/build/linux-libs"
rm -rf "$LIBS" && mkdir -p "$LIBS"
prendi() {   # prendi <pacchetto> <libreria da cercare> <nome nel pacchetto>
    local deb="$1" lib="$2" nome="$3" dir="$LIBS/$1"
    mkdir -p "$dir"
    if (cd "$dir" && apt-get download "$deb" >/dev/null 2>&1 && dpkg-deb -x "$deb"_*.deb x); then
        local f
        f="$(find "$dir/x" -name "$lib" -type f | head -n 1)"
        if [ -n "$f" ]; then
            cp "$f" "$dir/$nome"
            cp "$dir/x/usr/share/doc/$deb/copyright" "$dir/copyright" 2>/dev/null || true
            dpkg-deb -f "$dir/$deb"_*.deb Version > "$dir/versione"
            rm -rf "$dir/x" "$dir/$deb"_*.deb
            echo "   $deb $(cat "$dir/versione") → $nome"
            return 0
        fi
    fi
    rm -rf "$dir"
    echo "   ATTENZIONE: $deb non disponibile"
    return 1
}
prendi libportaudio2 'libportaudio.so.2.*' libportaudio.so.2 || echo "   senza PortAudio la chiamata vocale non funziona"
prendi libjack-jackd2-0 'libjack.so.0.*' libjack.so.0 || true
prendi libxcb-cursor0 'libxcb-cursor.so.0.*' libxcb-cursor.so.0 || echo "   senza libxcb-cursor Qt va solo con Wayland"

if [ "${SKIP_CORE_TEST:-0}" != "1" ]; then
    echo "== prove del motore (due tk-desk in locale, sessione WebRTC vera) e delle finestre"
    QT_QPA_PLATFORM=offscreen python tests/test_core.py > "dist/test-core-linux-$ARCH.txt" 2>&1 || {
        tail -n 60 "dist/test-core-linux-$ARCH.txt"; echo "PROVE DEL MOTORE FALLITE"; exit 1; }
    grep -E "^  (ok|NO|--)" "dist/test-core-linux-$ARCH.txt" | grep -iE "wayland|gstreamer" || true
    tail -n 1 "dist/test-core-linux-$ARCH.txt"
    QT_QPA_PLATFORM=offscreen python tests/test_finestre.py > "dist/test-finestre-linux-$ARCH.txt" 2>&1 || {
        tail -n 40 "dist/test-finestre-linux-$ARCH.txt"; echo "PROVE DELLE FINESTRE FALLITE"; exit 1; }
    tail -n 1 "dist/test-finestre-linux-$ARCH.txt"
fi

echo "== programma"
rm -rf build/tk-desk-linux dist/tk-desk
# testi delle licenze (AGPL + componenti inclusi + COMPONENTI.txt): lo spec li mette in _internal/licenze
python tools_licenze.py build/licenze --linux
[ -f build/licenze/COPYING-AGPL-3.0.txt ] || { echo "CARTELLA LICENZE NON CREATA"; exit 1; }
pyinstaller --noconfirm --clean --workpath build/tk-desk-linux linux/tk-desk-linux.spec
[ -f dist/tk-desk/_internal/licenze/COPYING-AGPL-3.0.txt ] || { echo "LICENZE NON INCLUSE"; exit 1; }

echo "== AppImage"
APPDIR="build/AppDir"
rm -rf "$APPDIR" && mkdir -p "$APPDIR/usr/lib"
cp -a dist/tk-desk "$APPDIR/usr/lib/tk-desk"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/tk-desk/tk-desk" "$@"
EOF
chmod 755 "$APPDIR/AppRun"
cat > "$APPDIR/tk-desk.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=tk-desk
GenericName=Assistenza remota
Comment=Assistenza remota: schermo, mouse, tastiera, file e chat (TecnikGeek)
Exec=tk-desk %U
Icon=tk-desk
Terminal=false
Categories=Network;RemoteAccess;
StartupWMClass=tk-desk
EOF
cp assets/tk-desk-512.png "$APPDIR/tk-desk.png"
ln -sf tk-desk.png "$APPDIR/.DirIcon"

TOOLS="${TK_STRUMENTI_BUILD:-$HOME/.cache/tk-build}"
TOOL="$TOOLS/appimagetool-$APPIMAGETOOL_VER-$ARCH.AppImage"
if [ ! -x "$TOOL" ]; then
    mkdir -p "$TOOLS"
    curl -fsSL -o "$TOOL.part" \
        "https://github.com/AppImage/appimagetool/releases/download/$APPIMAGETOOL_VER/appimagetool-$ARCH.AppImage"
    chmod 755 "$TOOL.part" && mv "$TOOL.part" "$TOOL"
fi
OUT="dist/tk-desk-$VERSION-linux-$ARCH.AppImage"
rm -f "$OUT"
APPIMAGE_EXTRACT_AND_RUN=1 ARCH="$ARCH" "$TOOL" --no-appstream \
    --mksquashfs-opt -processors --mksquashfs-opt "$JOBS" "$APPDIR" "$OUT" > build/appimagetool.log 2>&1 || {
    tail -n 30 build/appimagetool.log; echo "CREAZIONE APPIMAGE FALLITA"; exit 1; }
chmod 755 "$OUT"
echo "== Creato $OUT ($(du -h "$OUT" | cut -f1))"

# le prove dal pacchetto non devono toccare la sessione grafica di chi compila (Ubuntu di casa): niente Wayland
NOSCHERMO=(env -u WAYLAND_DISPLAY -u DISPLAY XDG_SESSION_TYPE=tty)

echo "== selftest (dal file AppImage: finestra principale + sessione WebRTC con video, schermo di prova)"
SHOT="$ROOT/dist/selftest-linux-$ARCH.png"
rm -f "$SHOT" "${SHOT%.png}.txt" "${SHOT%.png}.log"
"${NOSCHERMO[@]}" QT_QPA_PLATFORM=offscreen TKDESK_PORTACHIAVI_SERVIZIO=tk-desk-prova timeout 120 "$OUT" --selftest "$SHOT" || true
cat "${SHOT%.png}.log" 2>/dev/null | grep -E "linux|aiortc|fine:|ERRORE" || true
[ -f "$SHOT" ] && [ -f "${SHOT%.png}.txt" ] || { echo "SELFTEST FALLITO: il programma non si avvia o il video non arriva"; cat "${SHOT%.png}.log" 2>/dev/null; exit 1; }
echo "   selftest OK ($(cat "${SHOT%.png}.txt"))"

echo "== portachiavi dal pacchetto"
"${NOSCHERMO[@]}" timeout 60 "$OUT" --prova-portachiavi "$ROOT/dist/portachiavi-linux-$ARCH.txt" || true
if ! grep -q "^OK" "$ROOT/dist/portachiavi-linux-$ARCH.txt" 2>/dev/null && [ "${TK_PORTACHIAVI_OBBLIGATORIO:-0}" = "1" ]; then
    echo "PROVA DEL PORTACHIAVI FALLITA"; exit 1
fi

echo "== fotogrammi con GStreamer dal pacchetto (video di prova: la stessa lettura dello schermo con Wayland)"
if command -v gst-launch-1.0 >/dev/null; then
    "${NOSCHERMO[@]}" timeout 60 "$OUT" --prova-gst "$ROOT/dist/gst-linux-$ARCH.png" || { echo "PROVA GSTREAMER FALLITA"; exit 1; }
else
    echo "   gst-launch-1.0 non c'è su questa macchina: saltata"
fi

if command -v Xvfb >/dev/null; then
    echo "== X11 (Xvfb): cattura con mss e puntatore con pynput, dal pacchetto"
    Xvfb :77 -screen 0 1280x800x24 -nolisten tcp >/dev/null 2>&1 &
    XPID=$!
    sleep 2
    X11=(env -u WAYLAND_DISPLAY DISPLAY=:77 XDG_SESSION_TYPE=x11)
    ESITO=0
    "${X11[@]}" timeout 60 "$OUT" --prova-cattura "$ROOT/dist/cattura-x11-$ARCH.png" --secondi 1 || ESITO=1
    "${X11[@]}" timeout 60 "$OUT" --prova-comandi || ESITO=1
    kill "$XPID" 2>/dev/null || true
    [ "$ESITO" = "0" ] || { echo "PROVA X11 FALLITA"; exit 1; }
else
    echo "   Xvfb non c'è: prova X11 saltata"
fi

if [ "${SKIP_UPDATE_TEST:-0}" != "1" ]; then
    echo "== test aggiornamento automatico"
    WORK="$(mktemp -d)"
    TESTAPP="$WORK/Programmi/tk-desk.AppImage"     # copia «installata» che deve essere sostituita
    mkdir -p "$(dirname "$TESTAPP")"
    cp "$OUT" "$TESTAPP"
    BEFORE="$(stat -c %i "$TESTAPP")"
    COPY="$WORK/tk-desk-nuova.AppImage"
    cp "$OUT" "$COPY"   # lo script di aggiornamento cancella il file usato
    SHA="$(sha256sum "$COPY" | cut -d' ' -f1)"
    SIZE="$(stat -c %s "$COPY")"
    MANIFEST="$WORK/tk-desk.json"
    printf '{"version":"99.0.0","notes":["test"],"linux-%s":{"url":"file://%s","sha256":"%s","size":%s}}' \
        "$ARCH" "$COPY" "$SHA" "$SIZE" > "$MANIFEST"
    # aggiornamenti firmati: chiave usa e getta solo per questo test (la vera resta sul PC di Pietro)
    read -r SEME PUB <<< "$(python mac/firma_aggiornamenti.py prova)"
    TK_FIRMA_SEME_PROVA="$SEME" python mac/firma_aggiornamenti.py firma --slug tk-desk "$MANIFEST"
    export TKDESK_DATA="$WORK/dati"
    mkdir -p "$TKDESK_DATA"
    # prima la prova contraria: manifest firmato con un'altra chiave = rifiutato
    read -r _ ALTRA <<< "$(python mac/firma_aggiornamenti.py prova)"
    "${NOSCHERMO[@]}" TK_AGGIORNAMENTI_PROVA="$ALTRA" "$TESTAPP" --update-test "file://$MANIFEST" --no-relaunch || true
    grep -q "rifiutato" "$TKDESK_DATA/update-test.log" || { cat "$TKDESK_DATA/update-test.log"; echo "TEST FIRMA FALLITO: accettato con la chiave sbagliata"; exit 1; }
    "${NOSCHERMO[@]}" TK_AGGIORNAMENTI_PROVA="$PUB" "$TESTAPP" --update-test "file://$MANIFEST" --no-relaunch
    AFTER="$BEFORE"
    for _ in $(seq 1 120); do
        AFTER="$(stat -c %i "$TESTAPP" 2>/dev/null || echo "$BEFORE")"
        [ "$AFTER" != "$BEFORE" ] && break
        sleep 1
    done
    cat "$TKDESK_DATA/update-test.log" "$TKDESK_DATA/aggiornamento.log" 2>/dev/null || true
    unset TKDESK_DATA
    if [ "$AFTER" = "$BEFORE" ] || [ ! -x "$TESTAPP" ] || ! cmp -s "$TESTAPP" "$OUT"; then
        echo "TEST AGGIORNAMENTO FALLITO"
        exit 1
    fi
    rm -rf "$WORK"
    echo "   aggiornamento OK (file AppImage sostituito, firma sbagliata rifiutata)"
fi
echo "== tutto OK: $OUT"
