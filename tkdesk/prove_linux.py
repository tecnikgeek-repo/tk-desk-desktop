"""Prove di tk-desk su Linux da riga di comando (dal file AppImage o dai sorgenti). Scrivono sul Terminale e
ritornano 0 se tutto va bene.

  --prova-portale              cosa offre questo Linux (sessione, portali, GStreamer, PortAudio, portachiavi) e una
                               sessione del portale preparata e chiusa SENZA chiedere niente (nessuna finestra)
  --prova-cattura FILE.png     cattura lo schermo per 3 secondi e salva l'ultimo fotogramma (Wayland: la prima
                               volta il sistema chiede il permesso con la sua finestra; dalla seconda non più)
  --prova-comandi              muove il puntatore in un quadrato al centro dello schermo (niente clic né tasti)
  --prova-gst FILE.png         la lettura dei fotogrammi con GStreamer, con un video di prova (nessuna finestra)
  --prova-portachiavi FILE.txt scrive, legge e cancella un segreto di prova nel portachiavi
"""
import os
import shutil
import subprocess
import sys
import time

from tkdesk import portale


def _salva_png(img, percorso):
    """img = array BGRA/BGRx (altezza, larghezza, 4) → PNG (QImage: niente finestre)."""
    import numpy as np
    from PySide6.QtGui import QImage
    img = np.ascontiguousarray(img)
    h, w = img.shape[:2]
    q = QImage(img.data, w, h, w * 4, QImage.Format.Format_RGB32).copy()
    return q.save(percorso, "PNG")


def _sorgente():
    if portale.e_wayland():
        s = portale.SorgenteWayland()
        s.al_problema = lambda testo: print("   avviso:", testo, flush=True)
        s.avvia()
        print("== Wayland: chiedo lo schermo al portale (la prima volta compare la finestra del sistema)…", flush=True)
        if not portale.aspetta_pronta(s):
            print("NO:", s.errore or "il portale non ha risposto", flush=True)
            s.chiudi()
            return None
        return s
    from tkdesk.schermo import SorgenteSchermo
    print("== X11: cattura con mss", flush=True)
    return SorgenteSchermo()


def prova_portale():
    from tkdesk import tk_linux
    print("sessione:", os.environ.get("XDG_SESSION_TYPE", "?"), "| WAYLAND_DISPLAY:", os.environ.get("WAYLAND_DISPLAY", "-"),
          "| DISPLAY:", os.environ.get("DISPLAY", "-"), "| desktop:", os.environ.get("XDG_CURRENT_DESKTOP", "?"))
    print("Wayland (portale):", portale.e_wayland())
    gst = portale.gst_launch()
    print("gst-launch-1.0:", gst or "NON TROVATO")
    ok = True
    if gst:
        ispeziona = shutil.which("gst-inspect-1.0")
        for el in ("pipewiresrc", "videorate", "videoconvert", "videoscale", "fdsink"):
            r = subprocess.run([ispeziona or "gst-inspect-1.0", "--exists", el], env=tk_linux.system_env(),
                               capture_output=True) if ispeziona else None
            presente = r is not None and r.returncode == 0
            ok = ok and presente
            print(f"   {el}:", "sì" if presente else "NO")
    try:
        from tkdesk.audio import prepara_portaudio
        prepara_portaudio()
        import sounddevice as sd
        print("PortAudio:", sd.get_portaudio_version()[1], "| dispositivi:", len(sd.query_devices()))
    except Exception as exc:
        print("PortAudio: NON disponibile", repr(exc))
    try:
        from jeepney.io.blocking import Proxy, open_dbus_connection
        from jeepney import message_bus
        c = open_dbus_connection(bus="SESSION")
        print("portachiavi (Secret Service):", "presente" if Proxy(message_bus, c, timeout=5).NameHasOwner(
            "org.freedesktop.secrets")[0] else "assente")
        c.close()
    except Exception as exc:
        print("D-Bus di sessione: NON raggiungibile", repr(exc))
        return 1
    p = portale.Portale()
    try:
        for i in ("ScreenCast", "RemoteDesktop", "Inhibit"):
            print(f"portale {i}: versione", p.versione(i))
        print("   modi del puntatore:", p.proprieta("ScreenCast", "AvailableCursorModes"),
              "| tipi di sorgente:", p.proprieta("ScreenCast", "AvailableSourceTypes"),
              "| dispositivi:", p.proprieta("RemoteDesktop", "AvailableDeviceTypes"))
        if p.versione("ScreenCast"):
            # CreateSession + SelectDevices + SelectSources: nessuna finestra (quella arriva solo con Start)
            p.prepara(token="", comandi=True)
            print("sessione del portale preparata:", p.sessione, "| comandi:", "sì" if p.remoto else "no")
    except Exception as exc:
        print("NO portale:", repr(exc))
        ok = False
    finally:
        p.chiudi()
    print("OK" if ok else "QUALCOSA MANCA")
    return 0 if ok else 1


def prova_cattura(percorso, secondi=3.0):
    s = _sorgente()
    if s is None:
        return 1
    try:
        print("schermi:", s.schermi, flush=True)
        fine = time.time() + secondi
        img, n, ultimo_id = None, 0, None
        while time.time() < fine:
            try:
                img = s.cattura().result(timeout=5)
                if id(img) != ultimo_id:
                    ultimo_id = id(img)
                    n += 1
            except Exception:
                pass
            time.sleep(1 / 25)
        if img is None:
            print("NO: nessun fotogramma in", secondi, "secondi", getattr(getattr(s, "_lettore", None), "errore", ""))
            return 1
        _salva_png(img, percorso)
        print(f"OK {img.shape[1]}x{img.shape[0]}, {n} fotogrammi diversi in {secondi:.0f} s → {percorso}")
        if portale.e_wayland():
            print("   permesso ricordato per la prossima volta:", "sì" if portale.leggi_token() else "no "
                  "(questo portale non lo permette: la finestra tornerà a ogni collegamento)")
        return 0
    finally:
        s.chiudi()


def prova_comandi():
    from tkdesk.comandi import Esecutore
    s = _sorgente()
    if s is None:
        return 1
    try:
        es = Esecutore()
        es.schermo = dict(s.attuale)
        if es.wayland and not (portale.portale_attivo() and portale.portale_attivo().remoto):
            print("NO: il portale ha dato lo schermo ma non il controllo di mouse e tastiera")
            return 1
        angoli = [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6), (0.4, 0.4)]
        print("== muovo il puntatore in un quadrato al centro dello schermo", es.schermo, flush=True)
        sbagliati = 0
        da = angoli[0]
        for a in angoli:
            for i in range(1, 21):
                x = da[0] + (a[0] - da[0]) * i / 20
                y = da[1] + (a[1] - da[1]) * i / 20
                es.esegui({"t": "mm", "x": x, "y": y})
                time.sleep(0.015)
            da = a
            if not es.wayland:     # X11: si rilegge la posizione vera
                time.sleep(0.05)
                pos = s.cursore()
                bene = pos is not None and abs(pos[0] - a[0]) < 0.01 and abs(pos[1] - a[1]) < 0.01
                sbagliati += 0 if bene else 1
                print(f"   angolo {a}: puntatore a {pos}", "ok" if bene else "SBAGLIATO", flush=True)
        es.rilascia_tutto()
        if sbagliati:
            print("NO: il puntatore non è dove doveva")
            return 1
        print("OK quadrato fatto" + (" (Wayland: controlla a occhio che il puntatore si sia mosso)" if es.wayland else ""))
        return 0
    finally:
        s.chiudi()


def prova_gst(percorso):
    if not portale.gst_launch():
        print("SALTATA: gst-launch-1.0 non c'è")
        return 0
    lettore = portale.LettoreGst(["videotestsrc", "is-live=true", "pattern=smpte"], 640, 360)
    try:
        fine = time.time() + 10
        while time.time() < fine and lettore.contati < 5:
            time.sleep(0.05)
        if lettore.ultimo is None:
            print("NO: nessun fotogramma da GStreamer", lettore.errore)
            return 1
        _salva_png(lettore.ultimo, percorso)
        print(f"OK GStreamer {lettore.ultimo.shape[1]}x{lettore.ultimo.shape[0]}, {lettore.contati} fotogrammi → {percorso}")
        return 0
    finally:
        lettore.ferma()


def prova_portachiavi(percorso):
    os.environ["TKDESK_PORTACHIAVI_SERVIZIO"] = "tk-desk-prova"
    from tkdesk import util
    util.SERVIZIO_PORTACHIAVI = "tk-desk-prova"
    valore = "v2:" + "ab" * 32
    try:
        salvato = util.proteggi(valore, "prova")
        if not util.protetto(salvato):
            testo = "NO portachiavi non disponibile (valore lasciato com'era)"
        elif util.svela(salvato) != valore:
            testo = "NO il segreto letto non è quello scritto"
        else:
            util.dimentica(salvato)
            testo = "OK portachiavi: scritto, letto e cancellato" if util.svela(salvato) == "" else \
                "NO la voce non si cancella"
    except Exception as exc:
        testo = f"NO {exc!r}"
    with open(percorso, "w", encoding="utf-8") as fh:
        fh.write(testo + "\n")
    print(testo)
    return 0 if testo.startswith("OK") else 1


def esegui(argv):
    """Ritorna il codice di uscita, oppure None se argv non chiede una prova Linux."""
    def arg(nome, predefinito=""):
        return argv[argv.index(nome) + 1] if nome in argv and argv.index(nome) + 1 < len(argv) else predefinito
    if "--prova-portale" in argv:
        return prova_portale()
    if "--prova-cattura" in argv:
        return prova_cattura(arg("--prova-cattura", "tk-desk-cattura.png"), float(arg("--secondi", "3") or 3))
    if "--prova-comandi" in argv:
        return prova_comandi()
    if "--prova-gst" in argv:
        return prova_gst(arg("--prova-gst", "tk-desk-gst.png"))
    if "--prova-portachiavi" in argv:
        return prova_portachiavi(arg("--prova-portachiavi", "tk-desk-portachiavi.txt"))
    return None


if __name__ == "__main__":
    sys.exit(esegui(sys.argv[1:]) or 0)
