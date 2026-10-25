# -*- mode: python -*-
# PyInstaller: crea "tk-desk.app" per macOS. Uso: pyinstaller --noconfirm --clean mac/tk-desk-mac.spec
import os
import re

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
with open(os.path.join(ROOT, "tkdesk", "__init__.py"), encoding="utf-8") as fh:
    VERSION = re.search(r'VERSION = "(.+)"', fh.read()).group(1)

# cartella «licenze» preparata da tools_licenze.py (vedi build_mac.sh): finisce in Contents/Resources/licenze
LICENZE = os.path.join(ROOT, "build", "licenze")

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    datas=[(LICENZE, "licenze")] if os.path.isdir(LICENZE) else [],
    # pynput sceglie il «motore» del sistema a runtime; aiortc e av caricano codec e moduli in modo dinamico
    hiddenimports=["certifi", "tkdesk.tk_licenza", "tkdesk.tk_licenza_qt", "tkdesk.tk_aggiornamento", "tkdesk.prova", "tkdesk.audio", "sounddevice", "Quartz", "HIServices", "ApplicationServices",
                   "pynput.keyboard._darwin", "pynput.mouse._darwin", "mss.darwin"]
                  + collect_submodules("aiortc") + collect_submodules("av") + collect_submodules("aioice"),
    excludes=["tkinter", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore", "PySide6.QtMultimedia",
              "PySide6.QtPdf", "PySide6.QtNetwork"],
)

# componenti Qt non usati da un'app a widget
DROP = ("QtQuick", "QtQml", "QtVirtualKeyboard", "QtPdf", "libqpdf", "QtWebEngine", "Qt3D", "QtMultimedia",
        "QtNetwork", "QtOpenGL")
a.binaries = [b for b in a.binaries if not any(k in b[0] for k in DROP)]
a.datas = [d for d in a.datas if not any(k in d[0] for k in DROP)]

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="tk-desk", console=False, argv_emulation=False)
coll = COLLECT(exe, a.binaries, a.datas, name="tk-desk")
app = BUNDLE(
    coll,
    name="tk-desk.app",
    icon=os.path.join(ROOT, "assets", "tk-desk.icns"),
    bundle_identifier="com.tecnikgeek.tkdesk",  # interno: non cambiarlo (i permessi del Mac sono legati a questo)
    version=VERSION,
    info_plist={
        "CFBundleName": "tk-desk",
        "CFBundleDisplayName": "tk-desk",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "NSHighResolutionCapable": True,
        # app in italiano: senza, macOS usa l'inglese per le sue parti (menu dell'app, Servizi, finestre di sistema)
        "CFBundleDevelopmentRegion": "it",
        "CFBundleLocalizations": ["it"],
        "CFBundleAllowMixedLocalizations": True,
        "NSRequiresAquaSystemAppearance": True,
        "NSHumanReadableCopyright": "© 2026 Pietro De Filippis (TecnikGeek) - software libero AGPL-3.0",
        "LSApplicationCategoryType": "public.app-category.utilities",
        "NSAppleEventsUsageDescription": "tk-desk usa la tastiera e il mouse per l'assistenza remota.",
        # senza queste frasi macOS chiude l'app appena tocca il microfono o la Scrivania
        "NSMicrophoneUsageDescription": "tk-desk usa il microfono per la chiamata vocale durante l'assistenza.",
        "NSDesktopFolderUsageDescription": "tk-desk mette sulla Scrivania i file che ricevi dall'altro computer.",
    },
)
