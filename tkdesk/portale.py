"""Linux con Wayland (Ubuntu e GNOME di oggi): schermo, mouse e tastiera attraverso i portali del desktop.

Su Wayland un programma non può leggere lo schermo né muovere il mouse da solo (mss e pynput non funzionano):
lo chiede al sistema con xdg-desktop-portal, che mostra a chi è davanti la sua finestra «Condividi lo schermo /
Consenti il controllo remoto». Tutto passa da D-Bus con jeepney (già nel pacchetto per il portachiavi):

- RemoteDesktop.CreateSession → SelectDevices (tastiera + puntatore, persist_mode=2 con il restore_token salvato:
  dalla seconda volta la finestra non torna, dove il portale lo permette) → ScreenCast.SelectSources (schermi,
  puntatore disegnato nel video) → Start (qui compare la finestra del sistema) → flussi PipeWire, uno per schermo.
- I fotogrammi: ScreenCast.OpenPipeWireRemote dà un descrittore PipeWire; un processo figlio
  «gst-launch-1.0 pipewiresrc fd=… path=<nodo> ! … ! video/x-raw,format=BGRx ! fdsink» (GStreamer e il suo
  modulo PipeWire ci sono in Ubuntu desktop di base, 22.04 e 24.04) scrive i fotogrammi grezzi sul suo stdout.
  Niente PyGObject né GStreamer nel pacchetto: il processo gira con le librerie del sistema (tk_linux.system_env).
- Mouse e tastiera: RemoteDesktop.NotifyPointerMotionAbsolute (coordinate del flusso), NotifyPointerButton,
  NotifyPointerAxisDiscrete e NotifyKeyboardKeysym. Niente uinput (vorrebbe i permessi di amministratore).

Se il desktop offre solo ScreenCast (niente RemoteDesktop) si vede lo schermo ma i comandi non arrivano.
"""
import concurrent.futures
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time

import numpy as np

PORTALE = "org.freedesktop.portal.Desktop"
PERCORSO = "/org/freedesktop/portal/desktop"
FPS = 25
ATTESA_PERMESSO = 180      # secondi per rispondere alla finestra del sistema

# codici dei pulsanti (linux/input-event-codes.h)
PULSANTI = {"l": 0x110, "r": 0x111, "m": 0x112}

# nomi dei tasti di comandi.py → keysym di X11/xkb (li capisce NotifyKeyboardKeysym)
KEYSYM = {
    "enter": 0xff0d, "esc": 0xff1b, "tab": 0xff09, "backspace": 0xff08, "delete": 0xffff, "insert": 0xff63,
    "home": 0xff50, "end": 0xff57, "page_up": 0xff55, "page_down": 0xff56, "left": 0xff51, "up": 0xff52,
    "right": 0xff53, "down": 0xff54, "space": 0x20, "caps_lock": 0xffe5, "shift": 0xffe1, "ctrl": 0xffe3,
    "alt": 0xffe9, "alt_gr": 0xfe03, "meta": 0xffeb, "print_screen": 0xff61, "pause": 0xff13, "menu": 0xff67,
    "num_lock": 0xff7f, "scroll_lock": 0xff14,
}
KEYSYM.update({f"f{n}": 0xffbe + n - 1 for n in range(1, 21)})
# caratteri fuori da Latin-1 che sulle tastiere europee hanno un keysym loro (non quello «Unicode»)
KEYSYM_SPECIALI = {"€": 0x20ac, "\n": 0xff0d, "\r": 0xff0d, "\t": 0xff09}


def e_wayland():
    """Vero se la sessione grafica è Wayland (lì mss e pynput non vedono e non toccano niente)."""
    if not sys.platform.startswith("linux"):
        return False
    tipo = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if tipo in ("x11", "tty") and not os.environ.get("WAYLAND_DISPLAY"):
        return False
    return tipo == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))


def keysym_tasto(nome):
    """Nome di comandi.py («ctrl», «f5», «c»…) → keysym, None se sconosciuto."""
    if nome in KEYSYM:
        return KEYSYM[nome]
    if len(nome) == 1:
        return keysym_carattere(nome)
    return None


def keysym_carattere(c):
    if c in KEYSYM_SPECIALI:
        return KEYSYM_SPECIALI[c]
    o = ord(c)
    if 0x20 <= o <= 0x7e or 0xa0 <= o <= 0xff:
        return o                         # Latin-1: il keysym è il codice del carattere
    return 0x01000000 + o                # il resto: keysym «Unicode» di xkb


class ErrorePortale(Exception):
    pass


# --------------------------------------------------------------------------- D-Bus
class Portale:
    """Una sessione del portale (RemoteDesktop con ScreenCast, oppure solo ScreenCast). Tutte le chiamate passano
    dalla stessa connessione D-Bus: il portale accetta i comandi solo da chi ha creato la sessione."""

    def __init__(self, conn=None):
        if conn is None:
            from jeepney.io.blocking import open_dbus_connection
            conn = open_dbus_connection(bus="SESSION", enable_fds=True)
        self.conn = conn
        self.lock = threading.RLock()
        self.sessione = ""
        self.remoto = False          # True = RemoteDesktop (mouse e tastiera), False = solo schermo
        self.dispositivi = 0
        self.flussi = []             # [{"nodo", "left", "top", "width", "height"}]
        self.restore_token = ""
        self.pronto = False
        self.chiuso = False
        self._tok = "tkdesk" + secrets.token_hex(4)
        self._n = 0

    # ---- basi
    def _indirizzo(self, interfaccia, percorso=PERCORSO):
        from jeepney import DBusAddress
        return DBusAddress(percorso, bus_name=PORTALE, interface=interfaccia)

    def _chiama(self, interfaccia, metodo, firma, corpo, timeout=20, percorso=PERCORSO):
        from jeepney import new_method_call
        from jeepney.wrappers import unwrap_msg
        msg = new_method_call(self._indirizzo(interfaccia, percorso), metodo, firma, corpo)
        with self.lock:
            return unwrap_msg(self.conn.send_and_get_reply(msg, timeout=timeout))

    def proprieta(self, interfaccia, nome, predefinito=0):
        try:
            corpo = self._chiama("org.freedesktop.DBus.Properties", "Get", "ss",
                                 ("org.freedesktop.portal." + interfaccia, nome), timeout=5)
            return corpo[0][1]
        except Exception:
            return predefinito

    def versione(self, interfaccia):
        return int(self.proprieta(interfaccia, "version", 0) or 0)

    def _richiesta(self, interfaccia, metodo, firma, prima, opzioni, timeout):
        """Metodo del portale che risponde con il segnale Request.Response: ritorna i risultati (a{sv} senza
        varianti al primo livello). Codice 1 = annullato da chi è davanti, 2 = altro errore."""
        from jeepney import MatchRule, message_bus
        from jeepney.io.blocking import Proxy
        self._n += 1
        token = f"{self._tok}_{self._n}"
        mittente = (self.conn.unique_name or "")[1:].replace(".", "_")
        percorso = f"/org/freedesktop/portal/desktop/request/{mittente}/{token}"
        regola = MatchRule(type="signal", interface="org.freedesktop.portal.Request", member="Response",
                           path=percorso)
        opzioni = dict(opzioni)
        opzioni["handle_token"] = ("s", token)
        with self.lock:
            bus = Proxy(message_bus, self.conn, timeout=10)
            bus.AddMatch(regola)
            try:
                with self.conn.filter(regola) as coda:
                    self._chiama("org.freedesktop.portal." + interfaccia, metodo, firma,
                                 tuple(prima) + (opzioni,), timeout=30)
                    try:
                        risposta = self.conn.recv_until_filtered(coda, timeout=timeout)
                    except TimeoutError:
                        raise ErrorePortale("nessuno ha risposto alla richiesta di condividere lo schermo") from None
            finally:
                try:
                    bus.RemoveMatch(regola)
                except Exception:
                    pass
        codice, risultati = risposta.body
        if codice == 1:
            raise ErrorePortale("chi è davanti al computer non ha consentito la condivisione dello schermo")
        if codice != 0:
            raise ErrorePortale(f"il portale ha rifiutato la richiesta ({metodo}, codice {codice})")
        return {k: v[1] for k, v in risultati.items()}

    # ---- sessione
    def prepara(self, token="", comandi=True):
        """CreateSession + SelectDevices + SelectSources (nessuna finestra sullo schermo)."""
        v_sc = self.versione("ScreenCast")
        if not v_sc:
            raise ErrorePortale("il desktop non offre la condivisione dello schermo (xdg-desktop-portal ScreenCast)")
        v_rd = self.versione("RemoteDesktop") if comandi else 0
        self.remoto = bool(v_rd)
        interfaccia = "RemoteDesktop" if self.remoto else "ScreenCast"
        r = self._richiesta(interfaccia, "CreateSession", "a{sv}", (),
                            {"session_handle_token": ("s", self._tok + "s")}, 30)
        self.sessione = str(r.get("session_handle") or "")
        if not self.sessione:
            raise ErrorePortale("il portale non ha creato la sessione")
        if self.remoto:
            opz = {"types": ("u", 3)}                       # 1 tastiera + 2 puntatore
            if v_rd >= 2:                                    # permesso ricordato (GNOME 45+, Ubuntu 24.04)
                opz["persist_mode"] = ("u", 2)
                if token:
                    opz["restore_token"] = ("s", token)
            self._richiesta("RemoteDesktop", "SelectDevices", "oa{sv}", (self.sessione,), opz, 30)
        modi = int(self.proprieta("ScreenCast", "AvailableCursorModes", 0) or 0)
        # 2 = puntatore disegnato nel video (chi controlla vede la freccia vera), altrimenti 1 = nascosto
        opz = {"types": ("u", 1), "multiple": ("b", True), "cursor_mode": ("u", 2 if modi & 2 else 1)}
        if not self.remoto and v_sc >= 4:
            opz["persist_mode"] = ("u", 2)
            if token:
                opz["restore_token"] = ("s", token)
        self._richiesta("ScreenCast", "SelectSources", "oa{sv}", (self.sessione,), opz, 30)

    def avvia(self, timeout=ATTESA_PERMESSO):
        """Start: qui il sistema mostra la sua finestra (se il permesso non è già ricordato)."""
        interfaccia = "RemoteDesktop" if self.remoto else "ScreenCast"
        r = self._richiesta(interfaccia, "Start", "osa{sv}", (self.sessione, ""), {}, timeout)
        self.dispositivi = int(r.get("devices") or 0)
        self.restore_token = str(r.get("restore_token") or "")
        self.flussi = []
        for nodo, prop in r.get("streams") or []:
            pos = (prop.get("position") or ("(ii)", (0, 0)))[1]
            dim = (prop.get("size") or ("(ii)", (0, 0)))[1]
            self.flussi.append({"nodo": int(nodo), "left": int(pos[0]), "top": int(pos[1]),
                                "width": int(dim[0]), "height": int(dim[1])})
        if not self.flussi:
            raise ErrorePortale("nessuno schermo scelto nella finestra del sistema")
        if self.remoto and not self.dispositivi & 2:
            self.remoto = False                             # schermo sì, controllo no
        self.pronto = True

    def apri_pipewire(self):
        """Descrittore della connessione PipeWire per leggere i flussi (uno nuovo a ogni chiamata)."""
        corpo = self._chiama("org.freedesktop.portal.ScreenCast", "OpenPipeWireRemote", "oa{sv}",
                             (self.sessione, {}), timeout=10)
        return corpo[0].to_raw_fd()

    def chiudi(self):
        if self.chiuso:
            return
        self.chiuso = True
        self.pronto = False
        # se un altro thread aspetta ancora la finestra del sistema (lock occupato) si chiude solo la connessione:
        # il portale chiude da sé le sessioni di chi esce dal bus, e chi aspetta si sblocca con un errore
        if self.lock.acquire(timeout=0.5):
            try:
                if self.sessione:
                    self._chiama("org.freedesktop.portal.Session", "Close", "", (), timeout=5,
                                 percorso=self.sessione)
            except Exception:
                pass
            finally:
                self.lock.release()
        try:
            import socket
            self.conn.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            self.conn.close()
        except Exception:
            pass

    # ---- comandi (solo con RemoteDesktop)
    def _notifica(self, metodo, firma, *args):
        if not (self.pronto and self.remoto):
            return
        self._chiama("org.freedesktop.portal.RemoteDesktop", metodo, "oa{sv}" + firma, (self.sessione, {}) + args,
                     timeout=5)

    def muovi(self, nodo, x, y):
        self._notifica("NotifyPointerMotionAbsolute", "udd", int(nodo), float(x), float(y))

    def pulsante(self, codice, giu):
        self._notifica("NotifyPointerButton", "iu", int(codice), 1 if giu else 0)

    def rotella(self, asse, scatti):
        self._notifica("NotifyPointerAxisDiscrete", "ui", int(asse), int(scatti))

    def tasto(self, keysym, giu):
        self._notifica("NotifyKeyboardKeysym", "iu", int(keysym), 1 if giu else 0)


_ATTIVO = None   # sessione del portale della sessione in entrata (una sola alla volta: le altre sono «occupato»)


def portale_attivo():
    return _ATTIVO


def _imposta_attivo(p):
    global _ATTIVO
    _ATTIVO = p


# --------------------------------------------------------------------------- permesso ricordato
def _file_token():
    from tkdesk.util import data_dir
    return os.path.join(data_dir(), "portale.json")


def leggi_token():
    try:
        with open(_file_token(), "r", encoding="utf-8") as fh:
            return str(json.load(fh).get("restore_token") or "")
    except Exception:
        return ""


def salva_token(token):
    """Il token vale una volta sola: a ogni sessione il portale ne dà uno nuovo."""
    if not token:
        return
    try:
        path = _file_token()
        with open(path + ".tmp", "w", encoding="utf-8") as fh:
            json.dump({"restore_token": token}, fh)
        os.replace(path + ".tmp", path)
    except OSError:
        pass


# --------------------------------------------------------------------------- fotogrammi (GStreamer del sistema)
def gst_launch():
    return shutil.which("gst-launch-1.0") or ""


def comando_gst(sorgente, larghezza, altezza, fps=FPS):
    """Pipeline: sorgente → al massimo `fps` al secondo (solo scarti, niente copie se lo schermo è fermo) →
    BGRx della misura dello schermo → stdout."""
    return ([gst_launch() or "gst-launch-1.0", "-q"] + list(sorgente)
            + ["!", "videorate", "drop-only=true", f"max-rate={int(fps)}",
               "!", "videoconvert", "!", "videoscale",
               "!", f"video/x-raw,format=BGRx,width={int(larghezza)},height={int(altezza)}",
               "!", "fdsink", "fd=1", "sync=false"])


class LettoreGst:
    """Processo gst-launch-1.0 che scrive fotogrammi BGRx sul suo stdout; un thread li legge e tiene l'ultimo."""

    def __init__(self, sorgente, larghezza, altezza, pass_fds=(), fps=FPS):
        from tkdesk.tk_linux import system_env
        self.larghezza, self.altezza = int(larghezza), int(altezza)
        self.dim = self.larghezza * self.altezza * 4
        self.ultimo = None
        self.contati = 0
        self.errore = ""
        self._stderr = []
        self.proc = subprocess.Popen(comando_gst(sorgente, larghezza, altezza, fps), stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, pass_fds=tuple(pass_fds),
                                     env=system_env(), bufsize=0, start_new_session=True)
        try:
            import fcntl
            fcntl.fcntl(self.proc.stdout.fileno(), 1031, 1 << 20)   # F_SETPIPE_SZ: meno letture per fotogramma
        except Exception:
            pass
        threading.Thread(target=self._leggi, name="gst-fotogrammi", daemon=True).start()
        threading.Thread(target=self._errori, name="gst-errori", daemon=True).start()

    def _leggi(self):
        out = self.proc.stdout
        try:
            while True:
                buf = bytearray(self.dim)
                vista = memoryview(buf)
                fatti = 0
                while fatti < self.dim:
                    n = out.readinto(vista[fatti:])
                    if not n:
                        return
                    fatti += n
                self.ultimo = np.frombuffer(buf, dtype=np.uint8).reshape(self.altezza, self.larghezza, 4)
                self.contati += 1
        except (OSError, ValueError):
            pass
        finally:
            self.errore = self.errore or ("; ".join(self._stderr[-3:]) or "il flusso dello schermo si è fermato")

    def _errori(self):
        try:
            for riga in self.proc.stderr:
                testo = riga.decode("utf-8", "replace").strip()
                if testo:
                    self._stderr = (self._stderr + [testo])[-20:]
        except (OSError, ValueError):
            pass

    def vivo(self):
        return self.proc.poll() is None

    def ferma(self):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=3)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


# --------------------------------------------------------------------------- sorgente per la sessione
def _misura_di_riserva():
    """Se il portale non dice la misura del flusso: quella dello schermo principale secondo Qt."""
    try:
        from PySide6.QtGui import QGuiApplication
        if QGuiApplication.instance() is not None and QGuiApplication.primaryScreen() is not None:
            g = QGuiApplication.primaryScreen().geometry()
            return {"left": g.x(), "top": g.y(), "width": g.width(), "height": g.height()}
    except Exception:
        pass
    return {"left": 0, "top": 0, "width": 1920, "height": 1080}


class SorgenteWayland:
    """Come schermo.SorgenteSchermo, ma attraverso il portale. Il permesso lo dà chi è davanti nella finestra del
    sistema, quindi la sorgente diventa pronta DOPO: intanto i fotogrammi sono neri e, appena pronta, chiama
    al_cambio() (il motore rimanda l'elenco degli schermi). al_problema(testo) = avviso per chi controlla."""

    def __init__(self, comandi=True):
        self.comandi = comandi
        self.schermi = [_misura_di_riserva()]
        self.indice = 0
        self.pronta = False
        self.errore = ""
        self.al_cambio = None
        self.al_problema = None
        self.portale = None
        self._lettore = None
        self._chiusa = False
        self._lock = threading.Lock()
        self._avviata = False

    def avvia(self):
        if not self._avviata:
            self._avviata = True
            threading.Thread(target=self._apri, name="portale", daemon=True).start()

    def _avvisa(self, cb, *a):
        try:
            if cb:
                cb(*a)
        except Exception:
            pass

    def _apri(self):
        try:
            if not gst_launch():
                raise ErrorePortale("manca GStreamer (gst-launch-1.0) per leggere lo schermo")
            p = Portale()
            self.portale = p
            token = leggi_token()
            p.prepara(token, self.comandi)
            if not token:
                self._avvisa(self.al_problema, "Sull'altro computer chi è davanti deve consentire la condivisione "
                                               "dello schermo nella finestra del sistema.")
            p.avvia()
            salva_token(p.restore_token)
            if self._chiusa:
                p.chiudi()
                return
            for s in p.flussi:
                if s["width"] <= 0 or s["height"] <= 0:
                    s.update({k: v for k, v in _misura_di_riserva().items() if k in ("width", "height")})
            self.schermi = list(p.flussi)
            self.indice = 0
            _imposta_attivo(p)
            self._nuovo_lettore()
            self.pronta = True
            self._avvisa(self.al_cambio)
            if self.comandi and not p.remoto:
                self._avvisa(self.al_problema, "Su questo Linux il sistema permette solo di vedere lo schermo: "
                                               "mouse e tastiera non arrivano.")
        except Exception as exc:
            self.errore = str(exc) if isinstance(exc, ErrorePortale) else f"{exc.__class__.__name__}: {exc}"
            self._avvisa(self.al_problema, f"Schermo dell'altro computer non disponibile: {self.errore}.")

    def _nuovo_lettore(self):
        with self._lock:
            if self._lettore is not None:
                self._lettore.ferma()
                self._lettore = None
            if self._chiusa or self.portale is None:
                return
            s = self.attuale
            fd = self.portale.apri_pipewire()
            try:
                self._lettore = LettoreGst(["pipewiresrc", f"fd={fd}", f"path={s['nodo']}", "do-timestamp=true"],
                                           s["width"], s["height"], pass_fds=(fd,))
            finally:
                os.close(fd)

    def scegli(self, indice):
        if 0 <= indice < len(self.schermi) and indice != self.indice:
            self.indice = indice
            if self.pronta:
                try:
                    self._nuovo_lettore()
                except Exception as exc:
                    self._avvisa(self.al_problema, f"Cambio di schermo non riuscito: {exc}")

    @property
    def attuale(self):
        return self.schermi[min(self.indice, len(self.schermi) - 1)]

    def cattura(self):
        f = concurrent.futures.Future()
        lettore = self._lettore
        img = lettore.ultimo if lettore is not None else None
        if img is None:
            f.set_exception(RuntimeError(self.errore or "schermo non ancora disponibile"))
        else:
            if not lettore.vivo() and not getattr(self, "_fermo_segnalato", False):
                self._fermo_segnalato = True
                self._avvisa(self.al_problema, "Chi è davanti ha fermato la condivisione dello schermo.")
            f.set_result(img)
        return f

    def cursore(self):
        """Il puntatore è già disegnato nel video (cursor_mode del portale): niente freccia in più."""
        return None

    def chiudi(self):
        self._chiusa = True
        with self._lock:
            if self._lettore is not None:
                self._lettore.ferma()
                self._lettore = None
        p = self.portale
        if p is not None:
            if portale_attivo() is p:
                _imposta_attivo(None)
            threading.Thread(target=p.chiudi, daemon=True).start()


def aspetta_pronta(sorgente, timeout=ATTESA_PERMESSO + 10):
    """Per le prove da riga di comando: aspetta il permesso (o l'errore)."""
    fine = time.time() + timeout
    while time.time() < fine and not sorgente.pronta and not sorgente.errore:
        time.sleep(0.1)
    return sorgente.pronta
