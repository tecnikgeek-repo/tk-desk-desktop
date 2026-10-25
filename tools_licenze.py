"""Prepara la cartella «licenze» del pacchetto di tk-desk: AGPL del programma, testi di licenza dei componenti
inclusi DAVVERO (presi dai *.dist-info del venv di build) e COMPONENTI.txt (componente, versione, licenza, dove si
scarica il sorgente).

Uso (con il Python del venv di build):  python tools_licenze.py <cartella-di-destinazione> [--mac]
Lo chiamano installer/build.ps1 (Windows) e mac/build_mac.sh (Mac).
"""
import os
import re
import shutil
import sys
from importlib import metadata

ROOT = os.path.dirname(os.path.abspath(__file__))
# quello che tk-desk importa; il resto (shiboken6, aioice, cryptography…) viene dalle dipendenze
RADICI = ["pyside6-essentials", "certifi", "aiortc", "mss", "pynput", "numpy", "sounddevice"]
QT_SORGENTE = ("https://download.qt.io/official_releases/QtForPython/ e "
               "https://code.qt.io/cgit/pyside/pyside-setup.git")
# librerie native che stanno DENTRO alcuni pacchetti Python
DENTRO = {
    "pyside6-essentials": [("Qt {v} (librerie Qt6*, file separati e sostituibili)", "LGPL-3.0-only",
                            "https://download.qt.io/official_releases/qt/")],
    "av": [("FFmpeg (cartella av.libs, con libvpx, opus, x264, x265, dav1d, SVT-AV1, LAME…)",
            "GPL-2.0-or-later (FFmpeg compilato con x264/x265)", "https://github.com/PyAV-Org/pyav-ffmpeg e "
            "https://ffmpeg.org/download.html")],
    "sounddevice": [("PortAudio (in _sounddevice_data)", "MIT", "https://github.com/spatialaudio/portaudio-binaries")],
    "cryptography": [("OpenSSL", "Apache-2.0", "https://www.openssl.org/source/")],
    "pylibsrtp": [("libsrtp", "BSD-3-Clause", "https://github.com/cisco/libsrtp")],
    "numpy": [("OpenBLAS e runtime GCC (in numpy.libs)", "BSD-3-Clause; GPL-3.0 con eccezione GCC Runtime",
               "https://github.com/OpenMathLib/OpenBLAS")],
}


def _nome(req):
    return re.split(r"[ ;<>=!~\[(]", req.strip(), maxsplit=1)[0].lower().replace("_", "-")


def _marcatore_ok(req):
    if ";" not in req:
        return True
    marcatore = req.split(";", 1)[1]
    if "extra" in marcatore:
        return False
    try:
        try:
            from packaging.markers import Marker
        except ImportError:
            from pip._vendor.packaging.markers import Marker
        return Marker(marcatore).evaluate()
    except Exception:
        return True   # nel dubbio la si prende, se è installata


def distribuzioni():
    """Le distribuzioni installate raggiungibili dalle RADICI (dipendenze comprese)."""
    viste, coda, fuori = {}, list(RADICI), []
    while coda:
        n = coda.pop(0)
        if n in viste:
            continue
        try:
            d = metadata.distribution(n)
        except metadata.PackageNotFoundError:
            fuori.append(n)
            continue
        viste[n] = d
        for r in d.requires or []:
            if _marcatore_ok(r):
                coda.append(_nome(r))
    return viste, fuori


def _licenza(d):
    m = d.metadata
    lic = m.get("License-Expression") or ""
    if not lic:
        breve = (m.get("License") or "").strip()
        lic = breve if breve and "\n" not in breve and len(breve) < 80 else ""
    if not lic:
        cl = [c.split("::")[-1].strip() for c in (m.get_all("Classifier") or []) if c.startswith("License ::")]
        lic = ", ".join(cl)
    return lic or "vedi il testo incluso"


def _sorgente(d):
    m = d.metadata
    for voce in m.get_all("Project-URL") or []:
        etichetta, _, url = voce.partition(",")
        if etichetta.strip().lower() in ("source", "source code", "repository", "code", "github", "homepage"):
            return url.strip()
    if m.get("Home-page"):
        return m["Home-page"].strip()
    return f"https://pypi.org/project/{m['Name']}/{d.version}/#files"


def _file_licenza(d):
    out = []
    for f in d.files or []:
        s = str(f).replace("\\", "/")
        base = s.rsplit("/", 1)[-1]
        if ".dist-info/" not in s or base.endswith((".py", ".pyc")):
            continue
        if "/licenses/" in s or re.match(r"(?i)(licen[cs]e|copying|notice|authors)", base):
            if "Qt-Commercial" in base:   # PySide6/Qt si usano sotto LGPL-3.0 (testo nella cartella)
                continue
            p = d.locate_file(f)
            if os.path.isfile(p):
                out.append((base, p))
    return out


def _licenza_python():
    for c in (os.path.join(sys.base_prefix, "LICENSE.txt"),
              os.path.join(sys.base_prefix, "lib", f"python{sys.version_info[0]}.{sys.version_info[1]}", "LICENSE.txt"),
              os.path.join(sys.base_prefix, "LICENSE")):
        if os.path.isfile(c):
            return c
    return os.path.join(ROOT, "licenze", "Python-PSF.txt")


def prepara(dest, mac=False):
    from tkdesk import VERSION
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    shutil.copyfile(os.path.join(ROOT, "COPYING"), os.path.join(dest, "COPYING-AGPL-3.0.txt"))
    for f in sorted(os.listdir(os.path.join(ROOT, "licenze"))):   # modelli: GPL, LGPL, PSF
        if f.endswith(".txt"):
            shutil.copyfile(os.path.join(ROOT, "licenze", f), os.path.join(dest, f))
    shutil.copyfile(_licenza_python(), os.path.join(dest, "Python-LICENSE.txt"))
    viste, fuori = distribuzioni()
    if fuori and not mac:
        print("attenzione, non installati:", ", ".join(fuori))
    py = ".".join(map(str, sys.version_info[:3]))
    righe = [
        f"tk-desk {VERSION} — componenti inclusi nel pacchetto ({'macOS' if mac else 'Windows'})",
        "=" * 72,
        "tk-desk è software libero: GNU AGPL-3.0-or-later (COPYING-AGPL-3.0.txt).",
        f"Codice sorgente: https://github.com/tecnikgeek-repo/tk-desk-desktop/tree/v{VERSION}",
        "I testi di licenza dei componenti sono in questa cartella (nome-del-componente-…).",
        "",
        "COMPONENTE | VERSIONE | LICENZA | SORGENTE",
        f"Python | {py} | PSF-2.0 (Python-LICENSE.txt) | https://www.python.org/downloads/source/",
    ]
    for n in sorted(viste):
        d = viste[n]
        nome = d.metadata["Name"]
        sorgente = QT_SORGENTE if n in ("pyside6-essentials", "shiboken6") else _sorgente(d)
        lic = _licenza(d)
        if n in ("pyside6-essentials", "shiboken6"):
            lic = "LGPL-3.0-only (LGPL-3.0.txt + GPL-3.0.txt)"
        righe.append(f"{nome} | {d.version} | {lic} | {sorgente}")
        for titolo, lic_d, src in DENTRO.get(n, []):
            righe.append(f"  dentro {nome}: {titolo.format(v=d.version)} | {lic_d} | {src}")
        for base, p in _file_licenza(d):
            nome_file = re.sub(r"[^A-Za-z0-9._-]", "_", f"{nome}-{base}")
            if not nome_file.lower().endswith(".txt"):
                nome_file += ".txt"
            shutil.copyfile(p, os.path.join(dest, nome_file))
    if mac:
        righe.append("PyInstaller (programma di avvio dentro l'app) | — | GPL-2.0-or-later con eccezione per il "
                     "programma di avvio | https://github.com/pyinstaller/pyinstaller")
    righe += ["", "Le librerie Qt restano file separati: si possono sostituire con una versione compatibile "
                  "(LGPL-3.0, sezione 4)."]
    with open(os.path.join(dest, "COMPONENTI.txt"), "w", encoding="utf-8", newline="\r\n" if not mac else "\n") as fh:
        fh.write("\n".join(righe) + "\n")
    return len(os.listdir(dest))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("uso: python tools_licenze.py <cartella> [--mac]")
    sys.path.insert(0, ROOT)
    n = prepara(sys.argv[1], "--mac" in sys.argv)
    print(f"licenze: {n} file in {sys.argv[1]}")
