"""Percorsi, impostazioni, segreti e piccole utilità di sistema (Windows, Mac e Linux)."""
import json
import os
import sys

from tkdesk import APP_TITLE, VERSION
from tkdesk import tk_linux  # libreria comune dei software TK (su Windows e Mac non fa niente)

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")
LINUX_DESKTOP_ID = "tk-desk"   # nome del file .desktop = app_id della finestra su Wayland (icona nella barra)


def mac_bundle_path():
    """Percorso di «tk-desk.app» se il programma gira dal bundle macOS."""
    exe = os.path.abspath(sys.executable)
    marker = ".app/Contents/MacOS/"
    i = exe.find(marker)
    return exe[:i + 4] if i >= 0 else None


def is_installed():
    """True se gira dal pacchetto portatile (Windows: cartella «app» con il Python incluso; Mac: bundle .app;
    Linux: file AppImage)."""
    if IS_MAC:
        return bool(getattr(sys, "frozen", False) and mac_bundle_path())
    if IS_LINUX:
        return bool(tk_linux.appimage_path())
    bundled = os.path.join(APP_ROOT, "python")
    return os.path.isfile(os.path.join(bundled, "pythonw.exe")) and \
        os.path.normcase(os.path.abspath(sys.base_prefix)) == os.path.normcase(bundled)


def _writable_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".prova")
        open(probe, "w").close()
        os.remove(probe)
        return True
    except OSError:
        return False


def data_dir():
    """Impostazioni e rubrica. Windows: «Dati» accanto ad «app» (portatile). Mac: Application Support.
    Linux: ~/.local/share/tk-desk. Gli aggiornamenti non la toccano. TKDESK_DATA la sostituisce (test)."""
    if os.environ.get("TKDESK_DATA"):
        path = os.environ["TKDESK_DATA"]
    elif IS_MAC:
        path = os.path.join(os.path.expanduser("~"), "Library", "Application Support", APP_TITLE)
    elif IS_LINUX:
        path = tk_linux.cartella_dati(APP_TITLE)
    else:
        base = os.path.dirname(APP_ROOT) if is_installed() else APP_ROOT
        path = os.path.join(base, "Dati")
    if not _writable_dir(path):
        path = os.path.join(os.path.expanduser("~"), "Documents", APP_TITLE)
        os.makedirs(path, exist_ok=True)
    return path


def log_dir():
    return data_dir()


def cartella_utente(chiave, riserva):
    """Cartelle dell'utente. Linux: quelle di ~/.config/user-dirs.dirs (in italiano «Scrivania», «Scaricati»,
    «Video», «Documenti»), chiave = DESKTOP, DOWNLOAD, VIDEOS, DOCUMENTS. Altrove (o se manca): ~/<riserva>.
    "" se non esiste."""
    casa = os.path.expanduser("~")
    if IS_LINUX and chiave:
        conf = os.environ.get("XDG_CONFIG_HOME") or os.path.join(casa, ".config")
        try:
            with open(os.path.join(conf, "user-dirs.dirs"), "r", encoding="utf-8") as fh:
                for riga in fh:
                    riga = riga.strip()
                    if riga.startswith(f"XDG_{chiave}_DIR="):
                        valore = riga.split("=", 1)[1].strip().strip('"').replace("$HOME", casa)
                        if os.path.isdir(valore) and os.path.abspath(valore) != os.path.abspath(casa):
                            return valore
        except OSError:
            pass
    path = os.path.join(casa, riserva)
    return path if os.path.isdir(path) else ""


def export_dir():
    """Dove proporre il salvataggio delle esportazioni."""
    return cartella_utente("DOCUMENTS", "Documents") or os.path.expanduser("~")


def open_path(path):
    import subprocess
    if IS_WIN:
        os.startfile(path)
    elif IS_MAC:
        subprocess.Popen(["open", path])
    else:
        tk_linux.apri(path)


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


class Settings:
    """Impostazioni in un file JSON nella cartella dei dati."""

    def __init__(self):
        self.path = os.path.join(data_dir(), "impostazioni.json")
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                self.data = json.load(fh)
        except Exception:
            self.data = {}

    def value(self, key, default=None):
        return self.data.get(key, default)

    def setValue(self, key, value):
        self.data[key] = value
        if not self.path:
            return
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=1)
        except OSError:
            pass


def _make_shortcut(folder_expr, argomenti=""):
    """Collegamento «tk-desk»: avvia il Python incluso (stesso pythonw.exe già accettato da Windows)."""
    import subprocess
    exe = os.path.join(APP_ROOT, "python", "pythonw.exe")
    if not os.path.isfile(exe):
        exe = sys.executable
    icon = os.path.join(APP_ROOT, "assets", "tk-desk.ico")
    # ogni percorso tra apici singoli con gli apostrofi raddoppiati (cartelle come «Documenti di Dell'Acqua»)
    run_py = '"' + os.path.join(APP_ROOT, "run.py") + '"' + (" " + argomenti if argomenti else "")
    ps = (
        f"$d={folder_expr};"
        f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d '{APP_TITLE}.lnk'));"
        f"$s.TargetPath={_ps_literal(exe)};"
        f"$s.Arguments={_ps_literal(run_py)};"
        f"$s.WorkingDirectory={_ps_literal(APP_ROOT)};"
        f"$s.IconLocation={_ps_literal(icon + ',0')};"
        f"$s.Description='{APP_TITLE} - controllo remoto e assistenza';$s.Save();"
        f"Write-Output (Join-Path $d '{APP_TITLE}.lnk')"
    )
    ps_exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0",
                          "powershell.exe")
    r = subprocess.run([ps_exe, "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, creationflags=0x08000000, timeout=30)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[-300:])
    return r.stdout.strip()


def create_desktop_shortcut():
    if not IS_WIN:
        raise RuntimeError("disponibile solo su Windows")
    return _make_shortcut("[Environment]::GetFolderPath('Desktop')")


def ensure_folder_shortcut():
    """Collegamento con icona nella cartella del programma (accanto ad «app» e «Dati»). Solo Windows."""
    if not IS_WIN:
        return ""
    return _make_shortcut(_ps_literal(os.path.dirname(APP_ROOT)))


def _ps_literal(path):
    return "'" + path.replace("'", "''") + "'"


def _shell_folder(csidl):
    import ctypes
    buf = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) != 0:
        return ""
    return buf.value


def downloads_dir():
    """Dove salvare i file ricevuti dall'altro computer: Download/tk-desk."""
    base = cartella_utente("DOWNLOAD", "Downloads") or os.path.expanduser("~")
    path = os.path.join(base, APP_TITLE)
    os.makedirs(path, exist_ok=True)
    return path


def cartella_ricevuti():
    """File ricevuti dall'altro computer: sulla Scrivania (passaggio da desktop a desktop); di riserva Download/tk-desk."""
    try:
        cartella = _shell_folder(0x10) if IS_WIN else cartella_utente("DESKTOP", "Desktop")
        if cartella and os.path.isdir(cartella) and _writable_dir(cartella):
            return cartella
    except Exception:
        pass
    return downloads_dir()


LIMITE_FILE = 2 * 1024 ** 3     # 2 GB: oltre, un file in arrivo si rifiuta


def cartella_in_arrivo():
    """File in arrivo non ancora accettati: restano qui (nella cartella dei dati) finché chi è davanti non dice sì;
    solo allora vanno sulla Scrivania."""
    path = os.path.join(data_dir(), "in-arrivo")
    os.makedirs(path, exist_ok=True)
    return path


def pulisci_in_arrivo():
    """All'avvio: via i resti di file mai accettati (programma chiuso a metà di un passaggio)."""
    import shutil
    path = os.path.join(data_dir(), "in-arrivo")
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def segna_come_scaricato(percorso):
    """Un file arrivato da un altro computer è trattato come scaricato da internet: Windows lo apre con l'avviso
    di sicurezza (Mark-of-the-Web, ZoneId=3), il Mac con la quarantena di Gatekeeper. Linux non ha un segno
    così: il file arriva senza il permesso di esecuzione, quindi un programma non parte con un doppio clic."""
    try:
        if IS_WIN:
            with open(percorso + ":Zone.Identifier", "w", encoding="ascii") as fh:
                fh.write("[ZoneTransfer]\r\nZoneId=3\r\nHostUrl=about:internet\r\n")
        elif IS_MAC:
            import subprocess
            import time
            subprocess.run(["/usr/bin/xattr", "-w", "com.apple.quarantine", f"0081;{int(time.time()):x};tk-desk;",
                            percorso], capture_output=True, timeout=10)
    except Exception as exc:   # chiavetta FAT, disco di rete: il file resta comunque
        print("tk-desk: file non segnato come scaricato:", exc)


def cartella_licenze():
    """Testi delle licenze del pacchetto: Windows app\\licenze (accanto a run.py), Mac Contents/Resources/licenze,
    Linux _internal/licenze dentro l'AppImage; da sorgente la cartella licenze del progetto."""
    candidati = [os.path.join(APP_ROOT, "licenze")]
    if getattr(sys, "_MEIPASS", ""):
        candidati.append(os.path.join(sys._MEIPASS, "licenze"))
    bundle = mac_bundle_path()
    if bundle:
        candidati.append(os.path.join(bundle, "Contents", "Resources", "licenze"))
    for c in candidati:
        if os.path.isdir(c):
            return c
    return candidati[0]


# ───────────────────────────────────────────── segreti (chiave della password fissa, password della rubrica)
# Windows: DPAPI dell'utente («dpapi:…», si legge solo da questo utente su questo computer).
# Mac: Portachiavi («portachiavi:<nome>», il segreto passa a `security` dallo stdin, mai come argomento).
# Linux: portachiavi del sistema via Secret Service (stesso «portachiavi:<nome>», voce service=tk-desk,
# account=<nome>; GNOME «Password e chiavi», KDE Wallet…), con secretstorage incluso nel pacchetto.
# Se nessuno funziona il valore resta com'era (esadecimale), come nelle versioni di prima.
SERVIZIO_PORTACHIAVI = os.environ.get("TKDESK_PORTACHIAVI_SERVIZIO", "tk-desk")   # i test usano un nome loro


def _dpapi(dati, cifra):
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(dati, len(dati))
    ingresso = BLOB(len(dati), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    uscita = BLOB()
    crypt32 = ctypes.windll.crypt32
    fn = crypt32.CryptProtectData if cifra else crypt32.CryptUnprotectData
    if not fn(ctypes.byref(ingresso), None, None, None, None, 0x01, ctypes.byref(uscita)):   # UI_FORBIDDEN
        raise OSError("DPAPI non disponibile")
    try:
        return ctypes.string_at(uscita.pbData, uscita.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(uscita.pbData)


def _portachiavi(comando):
    import subprocess
    r = subprocess.run(["/usr/bin/security", "-i"], input=comando + "\n", capture_output=True, text=True, timeout=15)
    return r.returncode == 0


def _portachiavi_leggi(nome):
    import subprocess
    r = subprocess.run(["/usr/bin/security", "find-generic-password", "-a", nome, "-s", SERVIZIO_PORTACHIAVI, "-w"],
                       capture_output=True, text=True, timeout=15)
    return r.stdout.strip() if r.returncode == 0 else ""


def proteggi(valore, nome):
    """`valore` (esadecimale, anche «v2:…») → testo da salvare in impostazioni.json. `nome` = voce nel Portachiavi."""
    if not valore:
        return ""
    try:
        if IS_WIN:
            import base64
            return "dpapi:" + base64.b64encode(_dpapi(valore.encode("ascii"), True)).decode("ascii")
        # solo «v2:» e cifre esadecimali: nella riga per `security -i` non servono virgolette
        if IS_MAC and all(c in "0123456789abcdefv:" for c in valore) and nome.replace("-", "").isalnum():
            _portachiavi(f"add-generic-password -U -a {nome} -s {SERVIZIO_PORTACHIAVI} -w {valore}")
            if _portachiavi_leggi(nome) == valore:
                return "portachiavi:" + nome
        if IS_LINUX and nome:
            tk_linux.scrivi_segreto(SERVIZIO_PORTACHIAVI, nome, valore.encode("utf-8"), f"tk-desk: {nome}")
            if tk_linux.leggi_segreto(SERVIZIO_PORTACHIAVI, nome) == valore.encode("utf-8"):
                return "portachiavi:" + nome
    except Exception as exc:
        print("tk-desk: segreto non protetto:", exc)
    return valore


def svela(salvato):
    """Contrario di proteggi(); "" se il segreto non si legge (altro utente, altro computer, voce tolta)."""
    salvato = str(salvato or "")
    try:
        if salvato.startswith("dpapi:"):
            import base64
            return _dpapi(base64.b64decode(salvato[6:]), False).decode("ascii") if IS_WIN else ""
        if salvato.startswith("portachiavi:"):
            if IS_LINUX:
                return (tk_linux.leggi_segreto(SERVIZIO_PORTACHIAVI, salvato[12:]) or b"").decode("utf-8", "replace")
            return _portachiavi_leggi(salvato[12:]) if IS_MAC else ""
    except Exception as exc:
        print("tk-desk: segreto non leggibile:", exc)
        return ""
    return salvato


def protetto(salvato):
    return str(salvato or "").startswith(("dpapi:", "portachiavi:"))


def dimentica(salvato):
    """Toglie la voce dal Portachiavi (Mac) o dal portachiavi di Linux. Con DPAPI basta cancellare il testo."""
    salvato = str(salvato or "")
    if IS_LINUX and salvato.startswith("portachiavi:"):
        tk_linux.cancella_segreto(SERVIZIO_PORTACHIAVI, salvato[12:])
        return
    if IS_MAC and salvato.startswith("portachiavi:"):
        try:
            import subprocess
            subprocess.run(["/usr/bin/security", "delete-generic-password", "-a", salvato[12:], "-s",
                            SERVIZIO_PORTACHIAVI], capture_output=True, timeout=15)
        except Exception:
            pass


def cancella_tutto(impostazioni):
    """Mac e Linux (non c'è un disinstallatore): toglie l'avvio automatico (LaunchAgent / autostart), le voci nel
    portachiavi, la cartella dei dati (impostazioni, rubrica, licenza) e su Linux la voce nel menu.
    Il programma va chiuso subito dopo."""
    import shutil
    try:
        avvio_automatico(False)
    except Exception:
        pass
    voci = [impostazioni.value("chiave_fissa", "")] + [v.get("chiave", "") for v in (impostazioni.value("rubrica", []) or [])]
    for v in voci:
        dimentica(v)
    if IS_LINUX:
        togli_menu_linux()
    shutil.rmtree(data_dir(), ignore_errors=True)


cancella_tutto_mac = cancella_tutto   # nome di prima


def videos_dir():
    """Dove salvare le registrazioni delle sessioni: Video/tk-desk (Filmati su Mac)."""
    for chiave, nome in (("VIDEOS", "Videos"), ("", "Movies"), ("DOCUMENTS", "Documents")):
        base = cartella_utente(chiave, nome)
        if base:
            break
    else:
        base = os.path.expanduser("~")
    path = os.path.join(base, APP_TITLE)
    os.makedirs(path, exist_ok=True)
    return path


def avvio_automatico(acceso=None):
    """Avvio insieme al computer (accesso non presidiato). Senza argomento dice se è attivo.
    Windows: collegamento nella cartella Esecuzione automatica; Mac: LaunchAgent nell'utente;
    Linux: ~/.config/autostart/tk-desk.desktop che avvia il file AppImage."""
    if IS_LINUX:
        return _avvio_linux(acceso)
    if IS_WIN:
        cartella = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
        lnk = os.path.join(cartella, f"{APP_TITLE}.lnk")
        if acceso is None:
            return os.path.isfile(lnk)
        if acceso:
            _make_shortcut(_ps_literal(cartella), argomenti="--in-sottofondo")
        elif os.path.isfile(lnk):
            os.remove(lnk)
        return acceso
    if IS_MAC:
        plist = os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents", "com.tecnikgeek.tkdesk.plist")
        if acceso is None:
            return os.path.isfile(plist)
        if acceso:
            bundle = mac_bundle_path()
            if not bundle:
                raise RuntimeError("disponibile solo con tk-desk installato in Applicazioni")
            os.makedirs(os.path.dirname(plist), exist_ok=True)
            with open(plist, "w", encoding="utf-8") as fh:
                fh.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.tecnikgeek.tkdesk</string>
<key>ProgramArguments</key><array><string>{bundle}/Contents/MacOS/tk-desk</string><string>--in-sottofondo</string></array>
<key>RunAtLoad</key><true/>
</dict></plist>
""")
        elif os.path.isfile(plist):
            os.remove(plist)
        return acceso
    raise RuntimeError("non disponibile su questo sistema")


def _desktop_exec(path):
    """Percorso tra virgolette per la riga Exec di un file .desktop (specifica freedesktop)."""
    for c in ("\\", '"', "`", "$"):
        path = path.replace(c, "\\" + c)
    return f'"{path}"'


def _file_avvio_linux():
    conf = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(conf, "autostart", f"{LINUX_DESKTOP_ID}.desktop")


def _avvio_linux(acceso):
    path = _file_avvio_linux()
    if acceso is None:
        return os.path.isfile(path)
    if acceso:
        appimage = tk_linux.appimage_path()
        if not appimage:
            raise RuntimeError("disponibile solo con il file AppImage di tk-desk")
        testo = "\n".join([
            "[Desktop Entry]", "Type=Application", f"Name={APP_TITLE}",
            "Comment=Accesso non presidiato di tk-desk (resta vicino all'orologio)",
            f"Exec={_desktop_exec(appimage)} --in-sottofondo", f"TryExec={appimage}", f"Icon={LINUX_DESKTOP_ID}",
            "Terminal=false", "X-GNOME-Autostart-enabled=true", "X-GNOME-Autostart-Delay=5", "X-TecnikGeek=1",
        ]) + "\n"
        try:
            with open(path, "r", encoding="utf-8") as fh:
                if fh.read() == testo:
                    return True
        except OSError:
            pass
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as fh:
            fh.write(testo)
        os.replace(path + ".tmp", path)
    elif os.path.isfile(path):
        os.remove(path)
    return acceso


def installa_menu_linux():
    """Linux: voce «tk-desk» nel menu delle applicazioni con l'icona; se l'avvio automatico è acceso lo si
    riallinea al file AppImage (spostato o aggiornato con un nome nuovo)."""
    icona = os.path.join(getattr(sys, "_MEIPASS", APP_ROOT), "assets", "tk-desk-512.png")
    fatto = tk_linux.installa_menu(LINUX_DESKTOP_ID, APP_TITLE, "Assistenza remota: schermo, mouse, tastiera, file e "
                                   "chat (TecnikGeek)", "Network;RemoteAccess;", icona,
                                   nome_generico="Assistenza remota", parole="assistenza;remoto;desktop;controllo;")
    if _avvio_linux(None):
        _avvio_linux(True)
    return fatto


def togli_menu_linux():
    """Contrario di installa_menu_linux (per «Cancella tutto»)."""
    base = tk_linux.xdg_data_home()
    for p in (os.path.join(base, "applications", f"{LINUX_DESKTOP_ID}.desktop"),
              os.path.join(base, "icons", "hicolor", "512x512", "apps", f"{LINUX_DESKTOP_ID}.png")):
        try:
            os.remove(p)
        except OSError:
            pass


def mac_permessi(chiedi=False):
    """Mac: (registrazione schermo, accessibilità) concessi DAVVERO a questa versione di tk-desk?
    Con chiedi=True macOS mostra le sue due richieste. Senza «Registrazione schermo» l'altro vede solo lo sfondo;
    senza «Accessibilità» mouse e tastiera dell'altro vengono ignorati (senza errori).
    Prima pyobjc (Quartz e HIServices, gli stessi che usa pynput), poi ctypes."""
    if not IS_MAC:
        return True, True
    schermo = accesso = True
    try:
        import Quartz
        schermo = bool(Quartz.CGPreflightScreenCaptureAccess())
        if chiedi and not schermo:
            Quartz.CGRequestScreenCaptureAccess()
    except Exception:
        try:
            import ctypes
            import ctypes.util
            cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))
            cg.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
            schermo = bool(cg.CGPreflightScreenCaptureAccess())
            if chiedi and not schermo:
                cg.CGRequestScreenCaptureAccess()
        except Exception:
            pass
    try:
        import HIServices
        if chiedi:
            accesso = bool(HIServices.AXIsProcessTrustedWithOptions({HIServices.kAXTrustedCheckOptionPrompt: True}))
        else:
            accesso = bool(HIServices.AXIsProcessTrusted())
    except Exception:
        try:
            import ctypes
            import ctypes.util
            ax = ctypes.cdll.LoadLibrary(ctypes.util.find_library("ApplicationServices"))
            ax.AXIsProcessTrusted.restype = ctypes.c_bool
            accesso = bool(ax.AXIsProcessTrusted())
        except Exception:
            pass
    return schermo, accesso


def mac_ripristina_permessi():
    """Toglie le voci di tk-desk da «Registrazione schermo», «Accessibilità» e «Microfono» (quelle delle versioni
    vecchie restano ACCESE nelle Impostazioni ma non valgono per questa) e richiede subito i permessi.
    Ritorna il testo degli errori di tccutil, vuoto se tutto bene."""
    import subprocess
    errori = []
    for servizio in ("ScreenCapture", "Accessibility", "Microphone"):
        r = subprocess.run(["/usr/bin/tccutil", "reset", servizio, "com.tecnikgeek.tkdesk"],
                           capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            errori.append(f"{servizio}: {(r.stderr or r.stdout).strip()[:120]}")
    mac_permessi(chiedi=True)
    return " · ".join(errori)


def riavvia():
    """Chiude e riapre tk-desk (Mac: il permesso Accessibilità vale solo dal riavvio)."""
    import subprocess
    bundle = mac_bundle_path() if IS_MAC else None
    if bundle:
        subprocess.Popen(["/bin/sh", "-c", f'sleep 1; open -n "{bundle}"'], start_new_session=True)
    elif IS_LINUX and tk_linux.appimage_path():
        tk_linux.avvia(["/bin/sh", "-c", 'sleep 1; exec "$0"', tk_linux.appimage_path()])
    elif IS_WIN and is_installed():
        subprocess.Popen([os.path.join(APP_ROOT, "python", "pythonw.exe"), os.path.join(APP_ROOT, "run.py")],
                         creationflags=0x00000008)


def apri_impostazioni_mac(quale):
    """Apre Impostazioni di Sistema → Privacy e sicurezza alla voce giusta ("schermo" o "accessibilita")."""
    import subprocess
    voce = "Privacy_ScreenCapture" if quale == "schermo" else "Privacy_Accessibility"
    subprocess.Popen(["open", f"x-apple.systempreferences:com.apple.preference.security?{voce}"])


def nascondi_dalla_cattura(widget):
    """La finestra resta visibile a chi è davanti al computer ma non compare nello schermo trasmesso
    (chat, barra «sei controllato», domande di tk-desk). Windows 10 2004+: WDA_EXCLUDEFROMCAPTURE;
    Mac: NSWindow.sharingType = NSWindowSharingNone. Linux: né X11 né Wayland hanno un modo per escludere una
    finestra dalla cattura (sul portale decide il compositore): non si fa niente e le finestre si vedono."""
    try:
        import ctypes
        wid = int(widget.winId())
        if IS_WIN:
            ctypes.windll.user32.SetWindowDisplayAffinity(ctypes.c_void_p(wid), 0x11)
        elif IS_MAC:
            import ctypes.util
            objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
            objc.sel_registerName.restype = ctypes.c_void_p
            objc.sel_registerName.argtypes = [ctypes.c_char_p]
            indirizzo = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
            prendi = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(indirizzo)
            imposta = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)(indirizzo)
            finestra = prendi(wid, objc.sel_registerName(b"window"))   # winId su Mac = NSView
            if finestra:
                imposta(finestra, objc.sel_registerName(b"setSharingType:"), 0)
    except Exception as exc:
        print("tk-desk: finestra non esclusa dalla cattura:", exc)


class Veglia:
    """Mentre qualcuno controlla questo computer: niente salvaschermo, schermo spento o stop.
    Windows: SetThreadExecutionState (dal thread della finestra). Mac: caffeinate per la durata della sessione
    e ogni 30 secondi «utente attivo» (i comandi simulati non sempre azzerano il conto del salvaschermo).
    Linux: inibizione via D-Bus (org.gnome.SessionManager.Inhibit, altrimenti org.freedesktop.ScreenSaver),
    che vale finché resta aperta la nostra connessione al bus."""

    def __init__(self):
        self._proc = None
        self.attiva = False
        self._dbus = None             # Linux: (connessione, voce, cookie)

    def accendi(self):
        self.attiva = True
        try:
            if IS_WIN:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)
            elif IS_MAC and self._proc is None:
                import subprocess
                self._proc = subprocess.Popen(["/usr/bin/caffeinate", "-d", "-i", "-s"],
                                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif IS_LINUX and self._dbus is None:
                self._dbus = inibisci_linux("Assistenza remota in corso")
            self.sveglia()
        except Exception:
            pass

    def sveglia(self):
        """Dichiara l'utente attivo (Mac: chiude anche il salvaschermo già partito)."""
        if not self.attiva:
            return
        try:
            if IS_MAC:
                import subprocess
                subprocess.Popen(["/usr/bin/caffeinate", "-u", "-t", "2"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif IS_WIN:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)
        except Exception:
            pass

    def spegni(self):
        self.attiva = False
        try:
            if IS_WIN:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            if self._proc is not None:
                self._proc.terminate()
            if self._dbus is not None:
                togli_inibizione_linux(self._dbus)
        except Exception:
            pass
        self._proc = None
        self._dbus = None


_INIBIZIONI = (
    # (percorso, servizio = interfaccia, metodo, firma, argomenti(motivo), metodo per togliere)
    ("/org/gnome/SessionManager", "org.gnome.SessionManager", "Inhibit", "susu",
     lambda motivo: (APP_TITLE, 0, motivo, 4 | 8), "Uninhibit"),          # 4 = sospensione, 8 = inattività
    ("/org/freedesktop/ScreenSaver", "org.freedesktop.ScreenSaver", "Inhibit", "ss",
     lambda motivo: (APP_TITLE, motivo), "UnInhibit"),
)


def inibisci_linux(motivo):
    """Linux: niente salvaschermo, blocco o sospensione finché non si chiama togli_inibizione_linux().
    Ritorna (connessione, voce, cookie) oppure None se il desktop non lo permette."""
    from jeepney import DBusAddress, new_method_call
    from jeepney.io.blocking import open_dbus_connection
    from jeepney.wrappers import unwrap_msg
    conn = open_dbus_connection(bus="SESSION")
    for voce in _INIBIZIONI:
        percorso, servizio, metodo, firma, argomenti, _togli = voce
        try:
            msg = new_method_call(DBusAddress(percorso, bus_name=servizio, interface=servizio), metodo, firma,
                                  argomenti(motivo))
            cookie = unwrap_msg(conn.send_and_get_reply(msg, timeout=5))[0]
            return conn, voce, cookie
        except Exception:
            continue
    conn.close()
    return None


def togli_inibizione_linux(stato):
    from jeepney import DBusAddress, new_method_call
    conn, voce, cookie = stato
    try:
        percorso, servizio, _m, _f, _a, togli = voce
        conn.send_and_get_reply(new_method_call(DBusAddress(percorso, bus_name=servizio, interface=servizio),
                                                togli, "u", (int(cookie),)), timeout=5)
    except Exception:
        pass
    finally:
        conn.close()
