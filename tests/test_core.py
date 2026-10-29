"""Prove del motore di tk-desk senza rete e senza schermo: due tk-desk nello stesso processo.

Centralino finto in memoria, schermo di prova (SorgenteFinta) e mouse/tastiera finti (Esecutore(finto=True)):
la sessione WebRTC invece è vera (aiortc in locale). Uso: python tests/test_core.py
"""
import os
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["TKDESK_DATA"] = tempfile.mkdtemp(prefix="tkdesk-test-")
os.environ["TKDESK_PORTACHIAVI_SERVIZIO"] = "tk-desk-prova"   # Mac e Linux: mai le voci vere del portachiavi

from PySide6.QtCore import QCoreApplication  # noqa: E402

from tkdesk import centralino as ce  # noqa: E402
from tkdesk.comandi import Esecutore  # noqa: E402
from tkdesk.schermo import SorgenteFinta  # noqa: E402
from tkdesk import sessione, util  # noqa: E402
from tkdesk.prova import CentralinoFinto, Imp  # noqa: E402
from tkdesk.audio import AudioFinto  # noqa: E402

RICEVUTI = tempfile.mkdtemp(prefix="tkdesk-ricevuti-")
util.cartella_ricevuti = lambda: RICEVUTI


class Raccogli:
    def __init__(self):
        self.ev = {}
        self.cond = threading.Condition()

    def __call__(self, nome):
        def f(*a):
            with self.cond:
                self.ev.setdefault(nome, []).append(a)
                self.cond.notify_all()
        return f

    def conta(self, nome):
        with self.cond:
            return len(self.ev.get(nome, []))

    def aspetta(self, nome, n=1, timeout=30, test=None):
        fine = time.time() + timeout
        while time.time() < fine:
            QCoreApplication.processEvents()
            with self.cond:
                lista = [x for x in self.ev.get(nome, []) if test is None or test(x)]
                if len(lista) >= n:
                    return lista
                self.cond.wait(0.05)
        raise AssertionError(f"non è arrivato «{nome}» (×{n}) in {timeout}s: {list(self.ev)}")

    def niente(self, nome, secondi, test=None):
        """Vero se in `secondi` non arriva nessun «nome» (che passa `test`)."""
        fine = time.time() + secondi
        while time.time() < fine:
            QCoreApplication.processEvents()
            with self.cond:
                if [x for x in self.ev.get(nome, []) if test is None or test(x)]:
                    return False
                self.cond.wait(0.05)
        return True


FALLITI = []


def prova(nome, fn):
    try:
        fn()
        print(f"  ok  {nome}", flush=True)
    except Exception as exc:
        FALLITI.append(nome)
        print(f"  NO  {nome}: {exc!r}", flush=True)


def aspetta_che(cond, timeout=10):
    fine = time.time() + timeout
    while time.time() < fine:
        QCoreApplication.processEvents()
        if cond():
            return True
        time.sleep(0.05)
    return False


class PortaleFinto:
    """Al posto del portale RemoteDesktop di Wayland: registra le chiamate."""
    pronto = True
    remoto = True

    def __init__(self):
        self.chiamate = []

    def muovi(self, nodo, x, y):
        self.chiamate.append(("muovi", nodo, round(x), round(y)))

    def pulsante(self, codice, giu):
        self.chiamate.append(("pulsante", codice, giu))

    def rotella(self, asse, scatti):
        self.chiamate.append(("rotella", asse, scatti))

    def tasto(self, keysym, giu):
        self.chiamate.append(("tasto", keysym, giu))


def prove_wayland():
    """Linux con Wayland: traduzione dei comandi per il portale (vale su ogni sistema: niente D-Bus) e lettura dei
    fotogrammi con GStreamer (solo se gst-launch-1.0 c'è)."""
    from tkdesk import portale

    def tasti():
        assert portale.keysym_tasto("ctrl") == 0xffe3 and portale.keysym_tasto("meta") == 0xffeb
        assert portale.keysym_tasto("f5") == 0xffc2 and portale.keysym_tasto("enter") == 0xff0d
        assert portale.keysym_tasto("c") == ord("c") and portale.keysym_tasto("nessuno") is None
        assert portale.keysym_carattere("à") == 0xe0 and portale.keysym_carattere("€") == 0x20ac
        assert portale.keysym_carattere("ж") == 0x01000000 + ord("ж")
    prova("Wayland: nomi dei tasti e caratteri → keysym", tasti)

    def esecutore():
        p = PortaleFinto()
        es = Esecutore(portale=p)
        assert es.wayland
        es.schermo = {"left": 1920, "top": 0, "width": 1001, "height": 501, "nodo": 47}
        es.esegui({"t": "mm", "x": 0.5, "y": 1.5})
        es.esegui({"t": "mb", "b": "r", "d": 1, "x": 0, "y": 0})
        es.esegui({"t": "mw", "dx": 0, "dy": 2})
        es.esegui({"t": "k", "k": "ctrl", "d": 1})
        es.esegui({"t": "k", "k": "c", "d": 1})
        es.esegui({"t": "c", "c": "Aè"})
        assert p.chiamate[:6] == [("muovi", 47, 500, 500), ("muovi", 47, 0, 0), ("pulsante", 0x111, True),
                                  ("rotella", 0, -2), ("tasto", 0xffe3, True), ("tasto", ord("c"), True)], p.chiamate
        assert p.chiamate[6:] == [("tasto", 0x41, True), ("tasto", 0x41, False), ("tasto", 0xe8, True),
                                  ("tasto", 0xe8, False)], p.chiamate[6:]
        p.chiamate.clear()
        es.rilascia_tutto()
        assert sorted(p.chiamate) == sorted([("tasto", 0xffe3, False), ("tasto", ord("c"), False),
                                             ("pulsante", 0x111, False)]), p.chiamate
        p.pronto = False      # permesso non ancora dato: i comandi si scartano
        p.chiamate.clear()
        es.esegui({"t": "mm", "x": 0.1, "y": 0.1})
        assert p.chiamate == []
    prova("Wayland: mouse, rotella e tastiera tradotti per il portale RemoteDesktop", esecutore)

    if sys.platform.startswith("linux") and portale.gst_launch():
        def gst():
            lettore = portale.LettoreGst(["videotestsrc", "is-live=true"], 320, 240)
            try:
                assert aspetta_che(lambda: lettore.contati >= 3, 15), f"nessun fotogramma: {lettore.errore}"
                assert lettore.ultimo.shape == (240, 320, 4), lettore.ultimo.shape
                assert lettore.ultimo[:, :, :3].any(), "fotogramma tutto nero"
            finally:
                lettore.ferma()
        prova("Wayland: fotogrammi BGRx letti da gst-launch-1.0 (video di prova)", gst)
    else:
        print("  --  GStreamer non disponibile qui: prova dei fotogrammi saltata", flush=True)


def main():
    app = QCoreApplication(sys.argv)  # noqa: F841
    prove_wayland()
    esec = Esecutore(finto=True)
    au_h, au_c = AudioFinto(), AudioFinto()
    host = sessione.Motore(Imp(), sorgente_factory=SorgenteFinta, esecutore=esec, centralino=CentralinoFinto(None), audio=au_h)
    ctrl = sessione.Motore(Imp(), centralino=CentralinoFinto(None), esecutore=Esecutore(finto=True), audio=au_c)
    rh, rc = Raccogli(), Raccogli()
    for nome in ("pronto", "password_cambiata", "controllato_inizio", "controllato_fine", "chat", "appunti",
                 "file_ricevuto", "voce_chiesta", "voce_stato", "richiesta_chiusa", "tentativi", "registrazione_remota",
                 "file_in_arrivo"):
        getattr(host.s, nome).connect(rh(nome))
    for nome in ("pronto", "sessione_aperta", "sessione_chiusa", "chat", "appunti", "stato_chiamata",
                 "registrazione", "file_avanzamento", "voce_chiesta", "voce_stato", "cursore", "file_rifiutato"):
        getattr(ctrl.s, nome).connect(rc(nome))

    # chi è davanti al computer controllato: accetta (o rifiuta, o non risponde) le richieste e i file
    auto = {"attiva": True, "si": True, "file": True}

    def su_richiesta(rid, da, nome):
        rh("richiesta_accesso")(rid, da, nome)
        if auto["attiva"]:
            host.rispondi_accesso(rid, auto["si"])
    host.s.richiesta_accesso.connect(su_richiesta)
    host.s.file_in_arrivo.connect(lambda k, fid, n, t: host.accetta_file(k, fid, auto["file"]))

    def foto(chiave, dati, w, h):
        rc("fotogramma")(chiave, len(dati), w, h)
        ctrl.disegnato(chiave)
    ctrl.s.fotogramma.connect(foto)
    host.avvia()
    ctrl.avvia()
    id_h = rh.aspetta("pronto")[0][0]
    rc.aspetta("pronto")

    stato = {}

    def spake():
        from tkdesk import pake
        assert pake._ricava_punto(b"tk-desk SPAKE2 M").hex() == pake.M_HEX
        assert pake._ricava_punto(b"tk-desk SPAKE2 N").hex() == pake.N_HEX
        for p in (pake.M, pake.N):
            assert pake.codifica(pake._per(pake._Q, p)) == pake._IDENTITA, "M e N nel sottogruppo giusto"
        k = ce.chiave2("ab3xyz", "123456789")
        assert ce.chiave2("AB3 XYZ", "123456789") == k   # la monouso non distingue maiuscole e spazi
        a, b = pake.Spake2("A", "1", "2", k), pake.Spake2("B", "1", "2", k)
        b.finisci(a.messaggio())
        a.finisci(b.messaggio())
        assert a.conferma_valida(b.conferma()) and b.conferma_valida(a.conferma())
        assert b.sigillo_valido("offerta", "sdp", a.sigilla("offerta", "sdp"))
        assert not b.sigillo_valido("offerta", "sdp-cambiato", a.sigilla("offerta", "sdp"))
        assert not b.sigillo_valido("risposta", "sdp", a.sigilla("offerta", "sdp"))
        for altra_b in (pake.Spake2("B", "1", "2", ce.chiave2("ab3xyw", "123456789")),   # password sbagliata
                        pake.Spake2("B", "9", "2", k)):                                  # ID cambiato per strada
            a = pake.Spake2("A", "1", "2", k)
            altra_b.finisci(a.messaggio())
            a.finisci(altra_b.messaggio())
            assert not a.conferma_valida(altra_b.conferma()) and not altra_b.conferma_valida(a.conferma())
        a = pake.Spake2("A", "1", "2", k)
        for storto in ("zz", "ff" * 32, "00" * 32, a.messaggio()):
            try:
                pake.Spake2("A", "1", "2", k).finisci(storto) if storto != a.messaggio() else a.finisci(storto)
            except pake.ErrorePake:
                pass
            else:
                raise AssertionError(f"messaggio storto accettato: {storto[:10]}")
        # vettore fisso: tk-desk-app/test/pake_test.dart deve dare gli stessi numeri
        a = pake.Spake2("A", "123456789", "987654321", bytes(range(32)), casuale=12345678901234567890)
        b = pake.Spake2("B", "123456789", "987654321", bytes(range(32)), casuale=98765432109876543210)
        b.finisci(a.messaggio())
        a.finisci(b.messaggio())
        assert a.messaggio() == "36248fd005296495ec44d9654840d38ece44021cea09da2555a25d15fc8709de"
        assert b.messaggio() == "8449501d946aa2017d41ccb4592503954e71b3d7bbc61f5d64fa16324581ecaf"
        assert a.conferma() == "e926a04f139cced74a28e3999bb2e582e30dff4dd7f5a7dfed12bebe23a21a61"
        assert b.conferma() == "3e921e9b95e97770690626bab3f61694f4b4a803ade611af414e8f75c01a751b"
        assert a.sigilla("offerta", "ciao è") == "a41499441380f89e352e03863404992b0322c6f16c6df4b1020496217137c313"
        assert ce.formatta_id("123456789") == "123 456 789" and ce.pulisci_id("123 456 789") == "123456789"
        assert host.password.isdigit() and len(host.password) == 6, "la monouso resta di 6 cifre"
        assert not ce.e_fissa(host.password) and ce.e_fissa("Ufficio-2026!")
    prova("SPAKE2: stessa password = stessa chiave, sbagliata o ID cambiato = no, sigilli, vettore per l'app", spake)

    def vecchia_versione():
        # una tk-desk di prima della 1.2.0 (firma HMAC, nessun «p»): rifiutata con «aggiorna», senza contare tentativi
        cv = CentralinoFinto(None)
        cv.registra()
        cv.invia(id_h, "chiamata", {"sdp": "x", "nonce": "n", "prova2": "ab", "nome": "vecchio", "v": 2})
        fine = time.time() + 15
        while time.time() < fine and not cv.cassette[cv.id]:
            time.sleep(0.1)
        r = cv.ricevi()
        assert r and r[0]["tipo"] == "rifiuto" and r[0]["dati"]["motivo"] == "aggiorna", r
        assert not host._sbagliate, host._sbagliate
        assert rh.conta("richiesta_accesso") == 0
    prova("le tk-desk di prima della 1.2.0 non si collegano più (rifiuto «aggiorna»)", vecchia_versione)

    def chi_si_ferma():
        # chi chiama vede che la sfida non torna e smette: il tentativo conta lo stesso (ATTESA_STRETTA)
        from tkdesk import pake
        vecchia = sessione.ATTESA_STRETTA
        sessione.ATTESA_STRETTA = 2
        try:
            host.azzera_tentativi()
            cv = CentralinoFinto(None)
            cv.registra()
            sp = pake.Spake2("A", cv.id, id_h, ce.chiave2("000000", id_h))
            cv.invia(id_h, "chiamata", {"v": ce.PROTOCOLLO, "p": sp.messaggio(), "fissa": False})
            assert aspetta_che(lambda: cv.id in host._sbagliate, 20), "il tentativo abbandonato non è stato contato"
            assert host._bloccato(cv.id) == 0 and host._bloccato(id_h_rem() or "nessuno") == 0
        finally:
            sessione.ATTESA_STRETTA = vecchia
            host.azzera_tentativi()
    prova("una chiamata lasciata a metà conta come password sbagliata", chi_si_ferma)

    def nomi_file():
        n = sessione.nome_file_sicuro
        assert n("..\\..\\Windows\\evil.dll") == "evil.dll"
        assert n("nota.txt:Zone.Identifier") == "nota.txtZone.Identifier"
        assert n("foto‮gpj.exe") == "fotogpj.exe" and sessione.e_programma(n("foto‮gpj.exe"))
        assert n("CON.txt") == "_CON.txt" and n("  ... ") == "file" and n("fattura è prova.pdf") == "fattura è prova.pdf"
        assert not sessione.e_programma("fattura.pdf") and sessione.e_programma("Setup.EXE")
    prova("nomi dei file in arrivo puliti (cartelle, «:», caratteri invisibili, nomi riservati)", nomi_file)

    def sbagliata():
        k = ctrl.connetti(id_h, "zzzzzz")
        x = rc.aspetta("sessione_chiusa", test=lambda a: a[0] == k)
        assert "Password sbagliata" in x[0][1], x
        assert rh.conta("richiesta_accesso") == 0, "con la password sbagliata non si chiede niente a chi è davanti"
    prova("password sbagliata rifiutata", sbagliata)

    def collega():
        k = ctrl.connetti(id_h, host.password)
        stato["k"] = k
        info = rc.aspetta("sessione_aperta", test=lambda a: a[0] == k, timeout=40)[0][1]
        assert len(info["schermi"]) == 2, info
        assert rh.conta("richiesta_accesso") == 1, "con la monouso chi è davanti deve accettare"
        rh.aspetta("controllato_inizio")
        f = rc.aspetta("fotogramma", n=5, test=lambda a: a[0] == k, timeout=40)
        assert (f[-1][2], f[-1][3]) == (1280, 720), f[-1]
        c = rc.aspetta("cursore", test=lambda a: a[0] == k, timeout=10)[0]
        assert (round(c[1], 2), round(c[2], 2)) == (0.25, 0.5), c
    prova("collegamento con la password monouso ACCETTATO da chi è davanti, video e puntatore", collega)

    def comandi():
        k = stato["k"]
        ctrl.manda(k, {"t": "mm", "x": 0.5, "y": 0.5})
        ctrl.manda(k, {"t": "mb", "b": "l", "d": 1, "x": 0.25, "y": 0.75})
        ctrl.manda(k, {"t": "mb", "b": "l", "d": 0, "x": 0.25, "y": 0.75})
        ctrl.manda(k, {"t": "k", "k": "ctrl", "d": 1})
        ctrl.manda(k, {"t": "k", "k": "c", "d": 1})
        ctrl.manda(k, {"t": "c", "c": "è"})
        ctrl.manda(k, {"t": "mw", "dx": 0, "dy": -2})
        fine = time.time() + 10
        while time.time() < fine and len(esec.registro) < 7:
            time.sleep(0.05)
        r = esec.registro
        assert ("sposta", (639, 359)) in r, r
        assert ("clic", "left", 1) in r and ("clic", "left", 0) in r, r
        assert ("tasto", "ctrl", 1) in r and ("tasto", "c", 1) in r and ("scrivi", "è") in r, r
        assert ("rotella", 0, -2) in r, r
    prova("mouse, tasti, Ctrl+C, lettere accentate e rotella arrivano al controllato", comandi)

    def secondo_schermo():
        k = stato["k"]
        ctrl.manda(k, {"t": "schermo", "i": 1})
        rc.aspetta("fotogramma", test=lambda a: a[0] == k and (a[2], a[3]) == (800, 600), timeout=20)
        n = len(esec.registro)
        ctrl.manda(k, {"t": "mm", "x": 0.0, "y": 0.0})
        fine = time.time() + 5
        while time.time() < fine and len(esec.registro) == n:
            time.sleep(0.05)
        assert esec.registro[-1] == ("sposta", (1280, 0)), esec.registro[-1]
    prova("cambio di schermo (video e coordinate del mouse sul secondo schermo)", secondo_schermo)

    def chat():
        k = stato["k"]
        ctrl.manda(k, {"t": "chat", "s": "Ciao, ti vedo"})
        rh.aspetta("chat", test=lambda a: a[1] == "Ciao, ti vedo")
        host.manda(id_h_rem(), {"t": "chat", "s": "Perfetto"})
        rc.aspetta("chat", test=lambda a: a[1] == "Perfetto")
    prova("chat nei due sensi", chat)

    def appunti():
        k = stato["k"]
        assert not host.appunti_attivi() and not ctrl.appunti_attivi(), "gli appunti devono partire spenti"
        ctrl.manda_appunti(k, "password copiata")             # spenti da entrambe le parti: non parte nulla
        ctrl.manda(k, {"t": "appunti", "s": "password copiata"})
        assert rh.niente("appunti", 1.5), "con gli appunti spenti non deve passare niente"
        ctrl.imp["appunti"] = True                            # acceso solo da chi controlla: chi riceve li scarta
        ctrl.manda_appunti(k, "solo da una parte")
        assert rh.niente("appunti", 1.5), "il controllato con gli appunti spenti non deve riceverli"
        host.imp["appunti"] = True                            # accesi tutti e due: passano
        ctrl.manda_appunti(k, "testo copiato")
        rh.aspetta("appunti", test=lambda a: a[1] == "testo copiato")
        host.imp["appunti"] = ctrl.imp["appunti"] = False
    prova("appunti spenti di default (non partono e non si ricevono), passano solo se accesi", appunti)

    def file():
        k = stato["k"]
        src = os.path.join(tempfile.mkdtemp(), "fattura è prova.pdf")
        dati = os.urandom(300_000)
        with open(src, "wb") as fh:
            fh.write(dati)
        ctrl.manda_file(k, src)
        arrivo = rh.aspetta("file_in_arrivo", timeout=30)[0]
        assert arrivo[2] == "fattura è prova.pdf" and arrivo[3] == 300_000, arrivo
        p = rh.aspetta("file_ricevuto", timeout=30)[0][1]
        with open(p, "rb") as fh:
            assert fh.read() == dati
        assert os.path.basename(p) == "fattura è prova.pdf", p
        if util.IS_WIN:
            with open(p + ":Zone.Identifier", encoding="ascii") as fh:
                assert "ZoneId=3" in fh.read(), "manca il Mark-of-the-Web"
        # rifiutato: non arriva sulla Scrivania e chi manda lo sa
        auto["file"] = False
        src2 = os.path.join(tempfile.mkdtemp(), "programma.exe")
        with open(src2, "wb") as fh:
            fh.write(os.urandom(200_000))
        ctrl.manda_file(k, src2)
        rc.aspetta("file_rifiutato", test=lambda a: a[1] == "programma.exe", timeout=20)
        time.sleep(0.5)
        assert not os.path.exists(os.path.join(RICEVUTI, "programma.exe"))
        auto["file"] = True
        # oltre 2 GB: rifiutato subito, senza chiedere
        prima = rh.conta("file_in_arrivo")
        s_h = host._entrate[id_h_rem()]
        host.loop.call_soon_threadsafe(host._file_controllo, s_h, {"t": "file", "id": "grosso01", "n": "x.iso",
                                                                    "size": util.LIMITE_FILE + 1})
        assert rh.niente("file_in_arrivo", 1, test=lambda a: a[2] == "x.iso") and rh.conta("file_in_arrivo") == prima
    prova("file: conferma prima di ricevere, Mark-of-the-Web, rifiuto, limite di 2 GB", file)

    def voce():
        k = stato["k"]
        id_c = id_h_rem()
        ctrl.voce(k, False)   # rifiutata: nessuno parla
        ctrl.voce(k, True)
        rh.aspetta("voce_chiesta", timeout=10)
        host.voce(id_c, True)
        rh.aspetta("voce_stato", test=lambda a: a[1] == "attiva", timeout=10)
        rc.aspetta("voce_stato", test=lambda a: a[1] == "attiva", timeout=10)
        fine = time.time() + 15
        while time.time() < fine and (au_h.suonati < 20000 or au_c.suonati < 20000):
            time.sleep(0.1)
        assert au_h.suonati >= 20000 and au_c.suonati >= 20000, (au_h.suonati, au_c.suonati)
        host.voce(id_c, False)
        rc.aspetta("voce_stato", test=lambda a: a[1] == "chiusa", n=2, timeout=10)
        assert not au_h.attivo and not au_c.attivo
        ctrl.voce(k, True)
        rh.aspetta("voce_chiesta", n=2, timeout=10)
        host.voce(id_c, False)
        rc.aspetta("voce_stato", test=lambda a: a[1] == "rifiutata", timeout=10)
    prova("chiamata vocale: richiesta, risposta, voce nei due sensi, chiusura e rifiuto", voce)

    def registrazione():
        k = stato["k"]
        dest = os.path.join(tempfile.mkdtemp(), "sessione.mp4")
        ctrl.registra(k, dest)
        rc.aspetta("registrazione", test=lambda a: a[1] == dest, timeout=15)
        rh.aspetta("registrazione_remota", test=lambda a: a[1] is True, timeout=10)
        time.sleep(2.0)
        ctrl.registra(k, "")
        rc.aspetta("registrazione", test=lambda a: a[1] == "", timeout=15)
        rh.aspetta("registrazione_remota", test=lambda a: a[1] is False, timeout=10)
        import av
        with av.open(dest) as v:
            n = sum(1 for _ in v.decode(video=0))
        assert n >= 10, n
    prova("registrazione in MP4, con avviso «REC» al controllato", registrazione)

    def bloccate():
        assert host.controllo_in_corso()
        try:
            host.imposta_password_fissa("Durante-2026!")
        except RuntimeError as exc:
            assert "controlla" in str(exc), exc
        else:
            raise AssertionError("durante un controllo la password fissa non si deve poter impostare")
        assert not host.ha_password_fissa()
    prova("impostazioni bloccate durante un controllo in entrata (password fissa)", bloccate)

    def chiusura():
        prima = host.password
        n = rh.conta("password_cambiata")
        ctrl.chiudi(stato["k"])
        rh.aspetta("controllato_fine", timeout=15)
        rc.aspetta("sessione_chiusa", test=lambda a: a[0] == stato["k"], timeout=15)
        rh.aspetta("password_cambiata", n=n + 1, timeout=10)
        assert host.password != prima and len(host.password) == 6 and host.password.isdigit()
        assert not host.sessioni_entrata() and not ctrl.sessioni_uscita()
        assert not host.controllo_in_corso()
    prova("chiusura: la password monouso cambia dopo la sessione", chiusura)

    def vecchia_password():
        k = ctrl.connetti(id_h, "ab3xyz" if host.password != "ab3xyz" else "ab3xyw")
        x = rc.aspetta("sessione_chiusa", test=lambda a: a[0] == k)
        assert "Password sbagliata" in x[0][1]
        host.azzera_tentativi()
    prova("la password di prima non vale più", vecchia_password)

    def rifiutata():
        auto["si"] = False
        prima = host.password
        n = rh.conta("richiesta_accesso")
        k = ctrl.connetti(id_h, host.password)
        x = rc.aspetta("sessione_chiusa", test=lambda a: a[0] == k, timeout=20)
        assert "non ha accettato" in x[0][1], x
        assert rh.conta("richiesta_accesso") == n + 1
        assert aspetta_che(lambda: host.password != prima), "dopo un rifiuto la password deve cambiare"
        assert not host.sessioni_entrata()
        auto["si"] = True
    prova("conferma locale: «Rifiuta» chiude la chiamata e cambia la password", rifiutata)

    def scaduta():
        auto["attiva"] = False
        vecchio = sessione.ATTESA_CONFERMA
        sessione.ATTESA_CONFERMA = 2       # nel programma 30 secondi
        try:
            n = rh.conta("richiesta_chiusa")
            t0 = time.time()
            k = ctrl.connetti(id_h, host.password)
            x = rc.aspetta("sessione_chiusa", test=lambda a: a[0] == k, timeout=20)
            assert "non ha accettato" in x[0][1], x
            assert time.time() - t0 >= 2, "rifiutata prima della scadenza"
            rh.aspetta("richiesta_chiusa", n=n + 1, timeout=5)   # la finestra di conferma si chiude da sola
            assert not host.sessioni_entrata()
        finally:
            sessione.ATTESA_CONFERMA = vecchio
            auto["attiva"] = True
    prova("conferma locale: senza risposta la richiesta scade e vale come rifiuto", scaduta)

    def fissa():
        host.imposta_password_fissa("Ufficio-2026!")
        assert util.protetto(host.imp["chiave_fissa"]) or not util.IS_WIN, host.imp["chiave_fissa"][:12]
        n = rh.conta("richiesta_accesso")
        k = ctrl.connetti(id_h, "Ufficio-2026!")
        rc.aspetta("sessione_aperta", test=lambda a: a[0] == k, timeout=40)
        assert rh.conta("richiesta_accesso") == n, "con la password fissa non si chiede la conferma"
        cambi = rh.conta("password_cambiata")
        ctrl.chiudi(k)
        rc.aspetta("sessione_chiusa", test=lambda a: a[0] == k, timeout=15)
        rh.aspetta("password_cambiata", n=cambi + 1, timeout=15)   # anche dopo la password fissa
        assert "Ufficio" not in str(host.imp), "la password fissa non va conservata in chiaro"
        host.imposta_password_fissa("")
        assert not host.ha_password_fissa()
    prova("accesso non presidiato con password fissa: senza conferma, chiave cifrata, per tutti", fissa)

    def ospite_vecchio():
        # dall'altra parte una tk-desk di prima: il suo rifiuto non dice «v»: 3 → «va aggiornata», non «password»
        rifiuta = host._rifiuta

        async def rifiuta_vecchio(a, motivo, **altro):
            await host._in_thread(host.ce.invia, a, "rifiuto", {"motivo": "password", "v": 2})

        async def chiamata_vecchia(da, d):
            await rifiuta_vecchio(da, "password")
        originale = host._chiamata_in_arrivo
        host._chiamata_in_arrivo = chiamata_vecchia
        try:
            k = ctrl.connetti(id_h, host.password)
            x = rc.aspetta("sessione_chiusa", test=lambda a: a[0] == k, timeout=30)
            assert "versione vecchia" in x[0][1], x
        finally:
            host._chiamata_in_arrivo, host._rifiuta = originale, rifiuta
            host.azzera_tentativi()
    prova("chiamando una tk-desk di prima si legge «va aggiornata»", ospite_vecchio)

    def rubrica_vecchia():
        k = ctrl.connetti(id_h, "", "ab" * 32)      # chiave v1 salvata nella rubrica dalle versioni 1.0.x
        x = rc.aspetta("sessione_chiusa", test=lambda a: a[0] == k, timeout=15)
        assert "scrivila di nuovo" in x[0][1], x
        imp = Imp(chiave_fissa="cd" * 32, rubrica=[{"id": "123456789", "chiave": "ab" * 32},
                                                  {"id": "987654321", "chiave": "v2:" + "ef" * 32}])
        m = sessione.Motore(imp, sorgente_factory=SorgenteFinta, esecutore=Esecutore(finto=True),
                            centralino=CentralinoFinto(None), audio=AudioFinto())
        assert not m.ha_password_fissa(), "la password fissa v1 va tolta"
        assert "chiave" not in imp["rubrica"][0] and util.svela(imp["rubrica"][1]["chiave"]) == "v2:" + "ef" * 32
    prova("chiavi v1 delle versioni di prima: tolte dalla rubrica e dalla password fissa", rubrica_vecchia)

    def a_riposo():
        # su un runner lento la sessione o la richiesta di conferma della prova di prima possono essere ancora
        # aperte: con una richiesta in attesa le nuove chiamate dello stesso computer vengono ignorate (è voluto)
        # e la password non cambia per inattività. Si aspetta che il computer controllato sia libero.
        assert aspetta_che(lambda: not host._entrate and not host._richieste, 90), \
            f"il computer controllato non si libera: entrate={list(host._entrate)} richieste={list(host._richieste)}"

    def tentativi():
        a_riposo()
        vecchi = sessione.BLOCCHI
        sessione.BLOCCHI = (2, 3, 4)          # nel programma 1, 5 e 15 minuti
        try:
            host.azzera_tentativi()
            prima = host.password
            # margini larghi: sul runner Mac Intel di GitHub ogni chiamata è molto più lenta
            for i in range(3):
                k = ctrl.connetti(id_h, "zzzzzz")
                x = rc.aspetta("sessione_chiusa", test=lambda a, k=k: a[0] == k, timeout=60)
                assert "Password sbagliata" in x[0][1], (i, x)
            assert host.password == prima, "fino alla terza la password resta"
            k = ctrl.connetti(id_h, host.password)       # bloccato: neanche quella giusta passa
            x = rc.aspetta("sessione_chiusa", test=lambda a: a[0] == k, timeout=60)
            assert "Troppe password sbagliate" in x[0][1], x
            assert rh.aspetta("tentativi", test=lambda a: a[0] == 3 and a[1] == 2)
            time.sleep(2.2)
            k = ctrl.connetti(id_h, "zzzzzz")            # la quarta: la password cambia
            x = rc.aspetta("sessione_chiusa", test=lambda a: a[0] == k, timeout=60)
            assert "Password sbagliata" in x[0][1], x
            assert aspetta_che(lambda: host.password != prima), "oltre la terza la password deve cambiare"
            seconda = host.password
            for _ in range(2):                           # quinta e sesta: cambia ancora, poi blocco di 5 «minuti»
                k = ctrl.connetti(id_h, "zzzzzz")
                rc.aspetta("sessione_chiusa", test=lambda a, k=k: a[0] == k, timeout=60)
            assert aspetta_che(lambda: host.password != seconda, 30)
            rh.aspetta("tentativi", test=lambda a: a[0] == 6 and a[1] == 3)
        finally:
            sessione.BLOCCHI = vecchi
            host.azzera_tentativi()
    prova("password sbagliate: blocco crescente e password nuova dopo ogni errore oltre il terzo", tentativi)

    def inattivita():
        a_riposo()
        vecchi = sessione.SCADENZA_PASSWORD, sessione.CONTROLLO_SCADENZA
        sessione.SCADENZA_PASSWORD, sessione.CONTROLLO_SCADENZA = 2, 0.5   # nel programma 10 minuti
        try:
            prima = host.password
            host.azzera_tentativi()   # nessun blocco rimasto dalla prova di prima
            assert aspetta_che(lambda: host.password != prima, 30), "la password doveva cambiare da sola"
            assert host.password.isdigit() and len(host.password) == 6
            k = ctrl.connetti(id_h, prima)
            x = rc.aspetta("sessione_chiusa", test=lambda a: a[0] == k)
            assert "Password sbagliata" in x[0][1], "la password scaduta non deve più valere"
        finally:
            sessione.SCADENZA_PASSWORD, sessione.CONTROLLO_SCADENZA = vecchi
            host.azzera_tentativi()
    prova("la password monouso cambia da sola dopo un periodo senza collegamenti", inattivita)

    host.ferma()
    ctrl.ferma()
    if util.IS_LINUX:
        try:
            from tkdesk import tk_linux
            tk_linux.cancella_servizio(util.SERVIZIO_PORTACHIAVI)   # voci di prova nel portachiavi
        except Exception:
            pass
    print("TUTTO OK" if not FALLITI else f"FALLITE: {FALLITI}", flush=True)
    os._exit(1 if FALLITI else 0)


def id_h_rem():
    """Chiave della sessione vista dal controllato = ID di chi controlla."""
    from gc import get_objects
    for o in get_objects():
        if isinstance(o, sessione.Motore) and o.sessioni_entrata():
            return o.sessioni_entrata()[0]
    return ""


if __name__ == "__main__":
    main()
