#!/bin/bash
# Crea dist/tk-desk-<versione>-mac-<arch>.dmg. Da eseguire su un Mac (o sul runner macOS di GitHub).
# Uso: bash mac/build_mac.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ARCH="$(uname -m)"
PY="${PYTHON:-python3}"
VERSION="$($PY -c "import re;print(re.search(r'VERSION = \"(.+)\"', open('tkdesk/__init__.py').read()).group(1))")"
echo "== tk-desk $VERSION per macOS ($ARCH)"

$PY -m venv .venv-mac
# shellcheck disable=SC1091
source .venv-mac/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet "pyside6-essentials==6.11.*" certifi pyinstaller aiortc mss pynput numpy sounddevice
# Mac Intel: dalla 49 cryptography non ha più il pacchetto pronto (si compila contro l'OpenSSL di Homebrew e nel .app
# finisce la libssl di Python, più vecchia: «Symbol not found: _SSL_get0_group_name»). La 48 universal2 ha OpenSSL dentro.
# Stesso rimedio di tk-ftp.
if [ "$(uname -m)" = "x86_64" ]; then
  python -m pip install --quiet --only-binary=cryptography "cryptography<49" "pyopenssl<26.3"
fi

echo "== prove del motore (due tk-desk in locale, sessione WebRTC vera) e delle finestre"
QT_QPA_PLATFORM=offscreen python tests/test_core.py
QT_QPA_PLATFORM=offscreen python tests/test_finestre.py

echo "== icona"
python tools_make_icon.py --iconset
iconutil -c icns assets/tk-desk.iconset -o assets/tk-desk.icns

echo "== app"
rm -rf build dist
# testi delle licenze (AGPL + componenti inclusi + COMPONENTI.txt): lo spec li mette in Contents/Resources/licenze
python tools_licenze.py build/licenze --mac
[ -f build/licenze/COPYING-AGPL-3.0.txt ] || { echo "CARTELLA LICENZE NON CREATA"; exit 1; }
pyinstaller --noconfirm --clean mac/tk-desk-mac.spec
[ -f "dist/tk-desk.app/Contents/Resources/licenze/COPYING-AGPL-3.0.txt" ] || { echo "LICENZE NON INCLUSE NELL'APP"; exit 1; }
APP="dist/tk-desk.app"
# Firma STABILE (stesso certificato nostro a ogni versione, segreto MAC_CERT_P12 su GitHub): il Mac lega i permessi
# (Registrazione schermo, Accessibilità, Microfono) alla firma; con la firma «ad-hoc» ogni versione è un programma
# nuovo e i permessi andavano ridati a ogni aggiornamento. Senza segreto (o se non riesce) resta l'ad-hoc.
FIRMATO=0
if [ -n "${MAC_CERT_P12:-}" ]; then
    KC="$HOME/tk-firma.keychain-db"
    security delete-keychain "$KC" 2>/dev/null || true
    security create-keychain -p tk "$KC"
    security set-keychain-settings -lut 3600 "$KC"
    security unlock-keychain -p tk "$KC"
    printf '%s' "$MAC_CERT_P12" | base64 --decode > "$HOME/tk-firma.p12"
    if security import "$HOME/tk-firma.p12" -k "$KC" -P "${MAC_CERT_PASSWORD:-}" -T /usr/bin/codesign        && security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k tk "$KC" >/dev/null; then
        security list-keychains -d user -s "$KC" $(security list-keychains -d user | tr -d '"')
        HASH="$(security find-certificate -c 'TecnikGeek Firma App' -Z "$KC" | awk '/SHA-1/{print $NF}')"
        echo "   firma stabile con il certificato $HASH"
        codesign --force --deep --sign "$HASH" --keychain "$KC" "$APP" && FIRMATO=1
    fi
    rm -f "$HOME/tk-firma.p12"
fi
if [ "$FIRMATO" != "1" ]; then
    echo "   ATTENZIONE: firma stabile non riuscita, firma ad-hoc"
    codesign --force --deep --sign - "$APP"
fi
codesign -d -r- "$APP" 2>&1 | grep -i "designated" || true

echo "== selftest"
SHOT="$ROOT/dist/selftest-$ARCH.png"
run_selftest() {
    "$APP/Contents/MacOS/tk-desk" --selftest "$SHOT" >>"$ROOT/dist/selftest-$ARCH.log" 2>&1 &
    local pid=$!
    for _ in $(seq 1 60); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 1
    done
    kill "$pid" 2>/dev/null || true
}
run_selftest
if [ ! -f "$SHOT" ]; then
    echo "   finestra non disponibile, riprovo in modalità offscreen"
    export QT_QPA_PLATFORM=offscreen
    run_selftest
    unset QT_QPA_PLATFORM
fi
[ -f "$SHOT" ] || { echo "SELFTEST FALLITO: l'app non si avvia o la sessione non arriva"; cat "$ROOT/dist/selftest-$ARCH.log" 2>/dev/null; exit 1; }
[ -f "$ROOT/dist/selftest-$ARCH.txt" ] || { echo "SELFTEST FALLITO: la sessione non arriva"; exit 1; }
echo "   selftest OK (finestra + sessione con video)"
grep -E "traduzione qt|puntatore|permessi" "$ROOT/dist/selftest-$ARCH.log" || true

echo "== dmg"
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applicazioni"
cp mac/LEGGIMI.txt "$STAGE/Leggimi - primo avvio.txt"
DMG="dist/tk-desk-$VERSION-mac-$ARCH.dmg"
for tentativo in 1 2 3 4; do
    if hdiutil create -volname "tk-desk $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$DMG"; then
        break
    fi
    echo "   hdiutil occupato, riprovo ($tentativo)"
    sleep 6
    [ "$tentativo" = "4" ] && { echo "CREAZIONE DMG FALLITA"; exit 1; }
done
rm -rf "$STAGE"
echo "== Creato $DMG ($(du -h "$DMG" | cut -f1))"

if [ "${SKIP_UPDATE_TEST:-0}" != "1" ]; then
    echo "== test aggiornamento automatico"
    TESTAPP="$HOME/Applications/tk-desk.app"
    mkdir -p "$HOME/Applications"
    rm -rf "$TESTAPP"
    cp -R "$APP" "$TESTAPP"
    BEFORE="$(stat -f %i "$TESTAPP/Contents/Info.plist")"
    COPY="$(mktemp -d)/tk-desk-test.dmg"
    cp "$DMG" "$COPY"
    SHA="$(shasum -a 256 "$COPY" | cut -d' ' -f1)"
    SIZE="$(stat -f %z "$COPY")"
    MANIFEST="$(mktemp -d)/tk-desk.json"
    printf '{"version":"99.0.0","notes":["test"],"mac-%s":{"url":"file://%s","sha256":"%s","size":%s}}' "$ARCH" "$COPY" "$SHA" "$SIZE" > "$MANIFEST"
    # aggiornamenti firmati: chiave usa e getta solo per questo test (la vera resta sul PC di Pietro)
    read -r SEME PUB <<< "$(python mac/firma_aggiornamenti.py prova)"
    TK_FIRMA_SEME_PROVA="$SEME" python mac/firma_aggiornamenti.py firma --slug tk-desk "$MANIFEST"
    TK_AGGIORNAMENTI_PROVA="$PUB" "$TESTAPP/Contents/MacOS/tk-desk" --update-test "file://$MANIFEST" --no-relaunch
    AFTER="$BEFORE"
    for _ in $(seq 1 120); do
        if [ -f "$TESTAPP/Contents/Info.plist" ]; then
            AFTER="$(stat -f %i "$TESTAPP/Contents/Info.plist" 2>/dev/null || echo "$BEFORE")"
            [ "$AFTER" != "$BEFORE" ] && break
        fi
        sleep 1
    done
    cat "$HOME/Library/Application Support/tk-desk/aggiornamento.log" 2>/dev/null || true
    if [ "$AFTER" = "$BEFORE" ] || [ ! -x "$TESTAPP/Contents/MacOS/tk-desk" ]; then
        echo "TEST AGGIORNAMENTO FALLITO"
        exit 1
    fi
    rm -rf "$TESTAPP"
    echo "   aggiornamento OK (bundle sostituito)"
fi
