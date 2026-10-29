# -*- mode: python -*-
# PyInstaller: crea la cartella «dist/tk-desk» per Linux, poi build_linux.sh la mette nell'AppImage.
# Uso: pyinstaller --noconfirm --clean linux/tk-desk-linux.spec
import os

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

# cartella «licenze» preparata da tools_licenze.py --linux (vedi build_linux.sh): finisce in _internal/licenze
LICENZE = os.path.join(ROOT, "build", "licenze")
# librerie prese dai pacchetti Ubuntu (apt-get download, non installate): PortAudio non c'è in Ubuntu di base,
# JACK lo chiede PortAudio e manca nella 24.04 di base, libxcb-cursor serve a Qt con X11
LIBS = os.path.join(ROOT, "build", "linux-libs")
extra_bin = []
for deb, nome in (("libportaudio2", "libportaudio.so.2"), ("libjack-jackd2-0", "libjack.so.0"),
                  ("libxcb-cursor0", "libxcb-cursor.so.0")):
    if os.path.isfile(os.path.join(LIBS, deb, nome)):
        extra_bin.append((os.path.join(LIBS, deb, nome), "."))

datas = [(os.path.join(ROOT, "assets", "tk-desk-512.png"), "assets")]
if os.path.isdir(LICENZE):
    datas.append((LICENZE, "licenze"))

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    binaries=extra_bin,
    datas=datas,
    # pynput con X11 (python-xlib carica le sue estensioni a runtime); portale e portachiavi via jeepney;
    # aiortc e av caricano codec e moduli in modo dinamico
    hiddenimports=["certifi", "tkdesk.tk_licenza", "tkdesk.tk_licenza_qt", "tkdesk.tk_aggiornamento", "tkdesk.prova",
                   "tkdesk.audio", "tkdesk.portale", "tkdesk.prove_linux", "tkdesk.tk_linux", "sounddevice",
                   "secretstorage", "jeepney", "jeepney.io.blocking",
                   "pynput.keyboard._xorg", "pynput.mouse._xorg", "pynput._util.xorg", "pynput._util.xorg_keysyms"]
                  + collect_submodules("Xlib") + collect_submodules("mss") + collect_submodules("aiortc")
                  + collect_submodules("av") + collect_submodules("aioice"),
    excludes=["tkinter", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore", "PySide6.QtMultimedia",
              "PySide6.QtPdf", "PySide6.QtNetwork", "pynput.keyboard._uinput", "pynput.mouse._uinput", "evdev"],
)

# componenti Qt non usati da un'app a widget (QtOpenGL e QtDBus restano: piattaforme xcb/wayland e icona nell'area
# di notifica); libasound e libdb li ha Ubuntu di base: si usano quelli del sistema (moduli ALSA/PipeWire compresi)
DROP = ("QtQuick", "QtQml", "QtVirtualKeyboard", "QtPdf", "libqpdf", "QtWebEngine", "Qt3D", "QtMultimedia",
        "libasound.so", "libdb-5")
a.binaries = [b for b in a.binaries if not any(k in b[0] for k in DROP)]
a.datas = [d for d in a.datas if not any(k in d[0] for k in DROP)]

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="tk-desk", console=False, strip=False)
coll = COLLECT(exe, a.binaries, a.datas, name="tk-desk")
