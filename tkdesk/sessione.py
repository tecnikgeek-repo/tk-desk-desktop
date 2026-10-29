"""Motore di tk-desk: centralino, WebRTC e sessioni, in un thread con il suo ciclo asyncio.

Ruoli:
  - computer CONTROLLATO: tiene una password monouso di 6 cifre (cambia dopo ogni sessione, dopo 10 minuti senza
    collegamenti e dopo ogni tentativo sbagliato oltre il terzo) e, se l'utente la imposta, una password fissa per
    l'accesso non presidiato. Riceve le chiamate dal centralino e controlla la firma; con la monouso chiede a chi
    è davanti «Accetta / Rifiuta» (rifiuto da solo dopo 30 secondi), con la password fissa no. Poi risponde,
    manda lo schermo ed esegue mouse e tastiera.
  - computer che CONTROLLA: chiama un ID con la password, riceve il video e manda i comandi.

Stretta di mano dal centralino (protocollo 3, dalla 1.2.0, SPAKE2 in pake.py; A = chi controlla, B = controllato):
  chiamata  A→B {v, n: codice della chiamata, p: messaggio SPAKE2 di A, fissa: password fissa o monouso}
  (B ripete «n» in sfida, risposta e rifiuto, A li riporta in offerta: un rifiuto in ritardo di una chiamata di prima
  non viene preso per la risposta a quella nuova)
  sfida     B→A {v, p: messaggio di B, c: conferma di B}            (A: conferma sbagliata = password sbagliata)
  offerta   A→B {c: conferma di A, corpo: JSON {sdp, nome, piattaforma, versione}, sigillo}
  risposta  B→A {corpo: JSON {sdp, nome, versione}, sigillo}        rifiuto B→A {v, motivo, …} in ogni momento
  Il centralino passa i messaggi ma non può ricavarne la password né cambiarli (sigillo con la chiave della sessione).
  Ogni chiamata conta come un tentativo finché A non dimostra di conoscere la password (conferma giusta).

Verso la finestra parla solo con i segnali Qt di `Segnali` (sicuri tra thread). Dalla finestra si chiamano
i metodi pubblici del Motore, che passano il lavoro al ciclo asyncio.

Canale dati «tk» (aperto da chi controlla), messaggi JSON:
  comandi (vedi comandi.py), {"t":"info"} (schermi del controllato), {"t":"schermo","i":n},
  {"t":"appunti","s":..}, {"t":"chat","s":..}, {"t":"file","id":..,"n":nome,"size":n} + pezzi binari
  (8 byte di id + dati) + {"t":"file-fine","id":..}, {"t":"voce","on":1|0}, {"t":"fine"}.
  Dalla 1.1.0: {"t":"file-no","id":..} (file rifiutato o troppo grande: chi manda si ferma),
  {"t":"rec","on":1|0} (chi controlla sta registrando: il controllato vede «REC»). Le versioni di prima li ignorano.

Appunti: passano solo se l'utente li ha accesi nelle Impostazioni (spenti di default), in entrambi i sensi.
File in arrivo: restano in una cartella di attesa finché chi è davanti non li accetta, poi vanno sulla Scrivania
segnati come scaricati da internet; oltre 2 GB si rifiutano.

Chiamata vocale: la traccia audio c'è da subito e manda silenzio (vedi audio.py). Chi preme «Chiamata» manda
voce on=1; l'altro risponde con on=1 (si parla) o on=0 (rifiutata). on=0 in qualsiasi momento chiude.
I file ricevuti vanno sulla Scrivania (passaggio da desktop a desktop).
"""
import asyncio
import json
import sys
import os
import secrets
import threading
import time
import unicodedata

from PySide6.QtCore import QObject, Signal

from tkdesk import VERSION, centralino as ce, util
from tkdesk import audio as au
from tkdesk import pake
from tkdesk.comandi import Esecutore

# STUN di Google: dice a ogni computer il suo indirizzo pubblico, per il collegamento diretto (vedi Leggimi)
STUN = ["stun:stun.l.google.com:19302", "stun:stun1.l.google.com:19302"]
ATTESA_CONFERMA = 30         # secondi per «Accetta» sul computer controllato, poi rifiuto automatico
ATTESA_RISPOSTA = ATTESA_CONFERMA + 20   # chi chiama aspetta anche la conferma dell'altra persona
ATTESA_COLLEGAMENTO = 25     # secondi perché WebRTC si colleghi
ATTESA_STRETTA = 20          # secondi per ogni passo della stretta di mano (sfida, offerta)
PEZZO_FILE = 16 * 1024
SCADENZA_PASSWORD = 600      # la monouso cambia da sola dopo 10 minuti senza collegamenti
CONTROLLO_SCADENZA = 5       # ogni quanti secondi si guarda se è scaduta
TENTATIVI_PER_BLOCCO = 3     # ogni 3 password sbagliate DALLO STESSO ID un blocco per quell'ID…
BLOCCHI = (60, 300, 900)     # …di 1, poi 5, poi 15 minuti (gli altri ID possono chiamare: niente blocchi dispettosi)
OBLIO_TENTATIVI = 3600       # dopo un'ora senza tentativi sbagliati si riparte da zero
MAX_SBAGLIATE_ORA = 20       # da tutti gli ID insieme in un'ora: oltre, nessuno entra per…
BLOCCO_TUTTI = 900           # …15 minuti (chi prova da tanti ID diversi)
ESEGUIBILI = {".exe", ".msi", ".bat", ".cmd", ".com", ".scr", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".hta",
              ".lnk", ".reg", ".jar", ".app", ".pkg", ".dmg", ".command", ".sh", ".py"}
_RISERVATI = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def nome_file_sicuro(nome):
    """Nome di un file in arrivo: niente cartelle, niente «:» (flussi nascosti di Windows), niente caratteri
    invisibili o che girano il testo («foto‮gpj.exe» si leggerebbe «fotoexe.jpg»), niente nomi riservati."""
    n = os.path.basename(str(nome or "").replace("\\", "/"))
    n = "".join(c for c in n if unicodedata.category(c) not in ("Cc", "Cf") and c not in '<>:"/|?*')
    n = n.strip().rstrip(". ")[:180].strip()
    if os.path.splitext(n)[0].upper() in _RISERVATI:
        n = "_" + n
    return n or "file"


def e_programma(nome):
    return os.path.splitext(str(nome or ""))[1].lower() in ESEGUIBILI


def _alza_bitrate():
    """Ritocchi a WebRTC, una volta sola.
    - Lo schermo ha testo fine: il VP8 di aiortc parte da 0,5 Mbps, troppo poco. Si sale fino a 6 Mbps.
    - La raccolta degli indirizzi aspetta lo STUN fino a 5 secondi su OGNI scheda di rete, anche su quelle
      dove non risponderà mai (VPN, Tailscale, schede virtuali): da entrambe le parti erano 10 secondi persi.
      Lo STUN risponde in meno di mezzo secondo: si aspetta al massimo 1,2 secondi."""
    try:
        _vp8_per_lo_schermo()
    except Exception as exc:
        print("tk-desk: VP8 non adattato:", exc)
    try:
        import functools
        import aioice.ice
        originale = aioice.ice.Connection.get_component_candidates
        if not getattr(originale, "_tk_desk", False):
            @functools.wraps(originale)
            async def piu_veloce(self, component, addresses, timeout=5):
                return await originale(self, component, addresses, timeout=min(timeout, 1.2))
            piu_veloce._tk_desk = True
            aioice.ice.Connection.get_component_candidates = piu_veloce
    except Exception:
        pass


def _vp8_per_lo_schermo():
    """Il VP8 di aiortc è tarato per le videochiamate: filtro anti-rumore (sfoca il testo), compressione fino a
    qmax 56, banda 0,25-1,5 Mbps e codificatore ricreato (= fotogramma completo) a ogni variazione del 10% della
    banda. Per uno schermo: niente filtro, modalità «contenuto schermo», qmax 42, 1,5-12 Mbps, si ricrea solo
    sopra il 35%. Copia di Vp8Encoder.encode di aiortc 1.15 con queste opzioni."""
    import av
    from aiortc.codecs import vpx
    vpx.DEFAULT_BITRATE = 6_000_000
    vpx.MAX_BITRATE = 12_000_000
    vpx.MIN_BITRATE = 1_500_000
    if getattr(vpx.Vp8Encoder.encode, "_tk_desk", False):
        return

    def encode(self, frame, force_keyframe=False):
        if frame.format.name != "yuv420p":
            frame = frame.reformat(format="yuv420p")
        if self.codec and (frame.width != self.codec.width or frame.height != self.codec.height
                           or abs(self.target_bitrate - self.codec.bit_rate) / self.codec.bit_rate > 0.35):
            self.codec = None
        if force_keyframe:
            frame.pict_type = av.video.frame.PictureType.I
        if self.codec is None:
            c = av.CodecContext.create("libvpx", "w")
            c.width, c.height = frame.width, frame.height
            c.bit_rate = self.target_bitrate
            c.pix_fmt = "yuv420p"
            c.gop_size = 3000
            c.qmin = 2
            c.qmax = 42
            c.options = {
                "bufsize": str(self.target_bitrate), "cpu-used": "-6", "deadline": "realtime",
                "lag-in-frames": "0", "minrate": str(self.target_bitrate), "maxrate": str(self.target_bitrate),
                "noise-sensitivity": "0", "overshoot-pct": "15", "partitions": "0", "static-thresh": "0",
                "undershoot-pct": "100", "screen-content-mode": "1",
            }
            c.thread_count = vpx.number_of_threads(frame.width * frame.height, vpx.multiprocessing.cpu_count())
            self.codec = c
        data = b"".join(bytes(p) for p in self.codec.encode(frame))
        payloads = self._packetize(data, self.picture_id)
        timestamp = vpx.convert_timebase(frame.pts, frame.time_base, vpx.VIDEO_TIME_BASE)
        self.picture_id = (self.picture_id + 1) % (1 << 15)
        return payloads, timestamp

    encode._tk_desk = True
    vpx.Vp8Encoder.encode = encode


def _diagnosi(testo, exc=None):
    """Una riga in diagnosi.log (cartella dei dati): chiamate rifiutate, stati del collegamento, errori."""
    try:
        import traceback
        from tkdesk.util import log_dir
        with open(os.path.join(log_dir(), "diagnosi.log"), "a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {testo}\n")
            if exc is not None:
                fh.write("".join(traceback.format_exception(exc))[-2500:] + "\n")
    except Exception:
        pass


class Segnali(QObject):
    pronto = Signal(str)                          # ID del computer
    errore_centralino = Signal(str)               # niente rete / server non raggiungibile
    password_cambiata = Signal(str)
    # lato controllato
    controllato_inizio = Signal(str, str)         # id di chi controlla, nome
    controllato_fine = Signal(str, str)           # id, motivo
    richiesta_accesso = Signal(str, str, str)     # richiesta, id di chi chiama, nome che dice di avere
    richiesta_chiusa = Signal(str)                # richiesta decisa o scaduta: la finestra di conferma si chiude
    tentativi = Signal(int, int)                  # password sbagliate di fila, secondi di blocco (0 = nessuno)
    registrazione_remota = Signal(str, bool)      # id di chi controlla, sta registrando
    # lato di chi controlla
    stato_chiamata = Signal(str, str)             # id chiave sessione, testo
    sessione_aperta = Signal(str, dict)           # chiave, info del controllato
    sessione_chiusa = Signal(str, str)            # chiave, motivo
    fotogramma = Signal(str, bytes, int, int)     # chiave, RGB, larghezza, altezza
    # entrambi
    chat = Signal(str, str)                       # chiave/id, testo
    appunti = Signal(str, str)                    # chiave/id, testo
    file_ricevuto = Signal(str, str)              # chiave/id, percorso
    file_in_arrivo = Signal(str, str, str, object)  # chiave/id, id del file, nome, dimensione: da accettare
    file_rifiutato = Signal(str, str, str)        # chiave/id, nome, motivo
    file_avanzamento = Signal(str, str, int, int) # chiave, nome, fatti, totale
    registrazione = Signal(str, str)              # chiave, percorso del video (vuoto = finita)
    # Mac: mouse e tastiera vanno usati SOLO dal thread principale (pynput fuori dal thread principale fa
    # chiudere l'app su macOS 14+). Il motore manda qui i comandi e la finestra li esegue.
    # Linux no: pynput con X11 e il portale con Wayland vanno bene da qualsiasi thread.
    comando = Signal(dict, dict)                  # comando, schermo condiviso
    voce_chiesta = Signal(str)                    # chiave/id: l'altro vuole parlare
    voce_stato = Signal(str, str, str)            # chiave/id, "attiva"|"chiusa"|"rifiutata", avviso audio
    cursore = Signal(str, float, float)           # chiave, posizione 0..1 del mouse dell'altro (x < 0 = fuori schermo)


class _Sessione:
    """Una sessione WebRTC, vista da uno dei due lati."""

    def __init__(self, chiave, remoto, pc):
        self.chiave = chiave          # per chi controlla: id remoto + contatore; per il controllato: id remoto
        self.remoto = remoto
        self.pc = pc
        self.canale = None
        self.info = {}
        self.chiusa = False
        self.file_in = {}             # id → [handle, percorso in attesa, nome, totale, fatti, scelta, finito]
        self.file_scartati = set()    # id dei file in arrivo rifiutati (i pezzi che arrivano ancora si buttano)
        self.file_fermati = set()     # id dei file che l'altro ha rifiutato (si smette di mandarli)
        self.registra = None          # (container, stream) quando si registra
        self.occupato = False         # il disegno precedente non è ancora stato mostrato
        self.voce = False             # chiamata vocale in corso
        self.voce_mia = False         # io ho chiesto (o accettato) la chiamata
        self.voce_remota = False      # l'altro l'ha chiesta (o accettata)


class Motore:
    def __init__(self, impostazioni, sorgente_factory=None, esecutore=None, centralino=None, audio=None):
        self.imp = impostazioni
        self.s = Segnali()
        self.ce = centralino or ce.Centralino(impostazioni)
        self._sorgente_factory = sorgente_factory
        self._esecutore = esecutore
        self.audio = audio or au.Audio()
        self.id = ""
        self.password = ce.nuova_password()
        self._chiave_monouso = b""
        self._password_creata = time.monotonic()
        self._chiamate = {}           # id remoto → coda dei messaggi della stretta di mano (lato di chi controlla)
        self._strette = {}            # id di chi chiama → Future dell'«offerta» (lato controllato)
        self._uscite = {}             # chiave → _Sessione (io controllo)
        self._entrate = {}            # id remoto → _Sessione (mi controllano)
        self._richieste = {}          # richiesta → (Future della conferma, id di chi chiama)
        self._sbagliate = {}          # id di chi chiama → [sbagliate di fila, quando l'ultima, bloccato fino a]
        self._sbagliate_tutte = []    # quando (monotonic), tutti gli ID insieme, nell'ultima ora
        self._bloccato_fino = 0.0     # blocco per tutti (troppe sbagliate da tanti ID)
        self._contatore = 0
        self.attivo = True
        self._migra_segreti()
        self.su_principale = sys.platform == "darwin" and esecutore is None
        self.loop = asyncio.new_event_loop()
        self._ice, self._ice_quando = [], 0.0
        self._thread = threading.Thread(target=self._gira, name="tk-desk-motore", daemon=True)
        _alza_bitrate()

    # ───────────────────────────────────────── ciclo
    def _gira(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._principale())

    def avvia(self):
        self._thread.start()

    def ferma(self):
        self.attivo = False
        if not self._thread.is_alive():    # mai partito (programma chiuso prima del benvenuto)
            return

        async def _chiudi_tutto():
            for s in list(self._uscite.values()) + list(self._entrate.values()):
                await self._chiudi(s, "chiusura del programma", avvisa=True)
        try:
            asyncio.run_coroutine_threadsafe(_chiudi_tutto(), self.loop).result(timeout=5)
        except Exception:
            pass

    def _nel_ciclo(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    async def _in_thread(self, fn, *a):
        return await self.loop.run_in_executor(None, fn, *a)

    async def _ponte(self):
        """Ponte TURN (Cloudflare) per le reti che bloccano il collegamento diretto (dati mobili, hotspot, aziende).
        Il permesso lo dà il centralino (/desk/ice) e vale 2 ore: si tiene per un'ora. Senza permesso (ponte spento,
        esaurito nel mese, niente rete) si va solo in diretto, come prima."""
        from aiortc import RTCIceServer
        if time.time() - self._ice_quando < 3600:
            return list(self._ice)
        try:
            r = await self._in_thread(lambda: self.ce._post("ice", {"id": self.id, "segreto": self.ce.segreto}))
            ice = []
            for s in r.get("ice") or []:
                # aiortc usa un solo ponte TURN: il primo indirizzo (UDP 3478), poi gli altri se il primo non va
                urls = [u for u in s.get("urls", []) if u.startswith(("turn:", "turns:"))]
                if urls:
                    ice.append(RTCIceServer(urls[0], username=s["username"], credential=s["credential"]))
            self._ice, self._ice_quando = ice, time.time()
            _diagnosi(f"ponte: {r.get('ponte')}")
        except Exception as exc:
            _diagnosi(f"ponte non disponibile: {exc!r}")
            self._ice = []
        return list(self._ice)

    @staticmethod
    def _passa_dal_ponte(pc):
        """Il collegamento scelto da ICE passa dal ponte (candidato «relay» da una delle due parti)?"""
        try:
            conn = pc.sctp.transport.transport._connection
            for coppia in conn._nominated.values():
                if "relay" in (coppia.local_candidate.type, coppia.remote_candidate.type):
                    return True
        except Exception:
            pass
        return False

    async def _segnala_uso(self, sess):
        """A fine sessione chi controlla dice al centralino quanti byte sono passati dal ponte (limite mensile)."""
        try:
            if not self._passa_dal_ponte(sess.pc):
                return
            byte = 0
            for ricevitore in sess.pc.getReceivers():
                for st in (await ricevitore.getStats()).values():
                    byte += int(getattr(st, "bytesReceived", 0) or 0)
            byte = int(byte * 1.1)   # più quello che va nell'altro verso (comandi, file, voce): piccolo
            _diagnosi(f"sessione {sess.chiave} passata dal ponte: {byte / 1e6:.1f} MB")
            await self._in_thread(lambda: self.ce._post("uso", {"id": self.id, "segreto": self.ce.segreto, "byte": byte}))
        except Exception as exc:
            _diagnosi(f"uso del ponte non segnalato: {exc!r}")

    async def _principale(self):
        attesa = 1
        id_ = ""
        while self.attivo and not id_:
            try:
                id_ = await self._in_thread(self.ce.registra)
            except ce.ErroreCentralino as e:
                self.s.errore_centralino.emit(str(e))
                await asyncio.sleep(min(attesa, 30))
                attesa *= 2
        if not self.attivo:
            return
        await self._rinnova_password(id_)   # prima le chiavi, poi l'ID: chi lo vede trova la password pronta
        self.id = id_
        self.s.pronto.emit(self.id)
        asyncio.ensure_future(self._scadenze())
        errori = 0
        while self.attivo:
            veloce = bool(self._chiamate) or any(not x.canale for x in self._entrate.values())
            try:
                messaggi = await self._in_thread(self.ce.ricevi)
                if errori:
                    self.s.pronto.emit(self.id)
                errori = 0
                for m in messaggi:
                    try:
                        await self._smista(m)
                    except Exception as exc:  # un messaggio storto non ferma il centralino
                        _diagnosi(f"messaggio {m.get('tipo')} da {m.get('da')} non gestito: {exc!r}", exc)
            except ce.ErroreCentralino as e:
                errori += 1
                if errori == 3:
                    self.s.errore_centralino.emit(str(e))
                if e.codice == "accesso":     # il server non ci riconosce più: nuova registrazione
                    try:
                        id_ = await self._in_thread(self.ce.registra)
                        await self._rinnova_password(id_)
                        self.id = id_
                        self.s.pronto.emit(self.id)
                    except ce.ErroreCentralino:
                        pass
            await asyncio.sleep(0.6 if veloce else 1.5)

    async def _smista(self, m):
        da, tipo, d = m["da"], m["tipo"], m["dati"] or {}
        if tipo == "chiamata":
            # in un compito a parte: la conferma di chi è davanti può durare 30 secondi e intanto il centralino
            # deve continuare a leggere i messaggi (es. «chiudi»)
            asyncio.ensure_future(self._chiamata_protetta(da, d))
        elif tipo in ("sfida", "risposta", "rifiuto"):
            coda = self._chiamate.get(da)
            if coda is not None:
                coda.put_nowait((tipo, d))
        elif tipo == "offerta":
            n, fut = self._strette.get(da, ("", None))
            if fut and not fut.done() and str(d.get("n", "")) == n:
                fut.set_result(d)
        elif tipo == "chiudi":
            s = self._entrate.get(da)
            if s:
                await self._chiudi(s, "chiusa dall'altro computer", avvisa=False)

    # ───────────────────────────────────────── password e accesso non presidiato
    async def _rinnova_password(self, id_=None):
        """Nuova monouso con la sua chiave (lenta apposta: si calcola fuori dal ciclo)."""
        id_ = id_ or self.id
        pw = ce.nuova_password()
        k = await self._in_thread(ce.chiave2, pw, id_)
        self.password, self._chiave_monouso = pw, k
        self._password_creata = time.monotonic()
        self.s.password_cambiata.emit(pw)

    def nuova_password(self):
        if self.id:
            self._nel_ciclo(self._rinnova_password())

    async def _scadenze(self):
        """La monouso cambia da sola dopo SCADENZA_PASSWORD secondi senza collegamenti (né richieste in corso)."""
        while self.attivo:
            await asyncio.sleep(CONTROLLO_SCADENZA)
            if (self.id and not self._entrate and not self._richieste and not self._strette
                    and time.monotonic() - self._password_creata >= SCADENZA_PASSWORD):
                await self._rinnova_password()

    def controllo_in_corso(self):
        """Vero se qualcuno controlla questo computer (o sta chiedendo di farlo): le impostazioni che aprono
        l'accesso (password fissa, accesso non presidiato, avvio con il computer) restano bloccate."""
        return bool(self._entrate or self._richieste)

    def _nome(self):
        return ce.nome_computer(self.imp)

    def imposta_password_fissa(self, password):
        """Accesso non presidiato: si conserva solo la chiave ricavata (600.000 giri, cifrata con DPAPI o nel
        Portachiavi), mai la password. Toglierla si può sempre, impostarla no mentre c'è un controllo in corso."""
        vecchia = self.imp.value("chiave_fissa", "")
        if not password:
            self.imp.setValue("chiave_fissa", "")
            util.dimentica(vecchia)
            return
        if self.controllo_in_corso():
            raise RuntimeError("Mentre qualcuno controlla questo computer la password fissa non si può impostare: "
                               "chiudi prima il collegamento.")
        if not self.id:
            raise RuntimeError("aspetta che tk-desk sia collegato al centralino")
        util.dimentica(vecchia)
        self.imp.setValue("chiave_fissa", util.proteggi("v2:" + ce.chiave2(password, self.id).hex(), "chiave-fissa"))

    def ha_password_fissa(self):
        return bool(self.imp.value("chiave_fissa", ""))

    def _chiave_fissa(self):
        """Chiave della password fissa, o b"" se non c'è o non si legge."""
        testo = util.svela(self.imp.value("chiave_fissa", ""))
        try:
            return bytes.fromhex(testo[3:]) if testo.startswith("v2:") else b""
        except ValueError:
            return b""

    def _migra_segreti(self):
        """Versioni di prima: chiavi in chiaro in impostazioni.json → si cifrano. Le chiavi v1 (fino alla 1.0.x) con
        il protocollo 3 non valgono più: si tolgono (password fissa e rubrica vanno riscritte)."""
        try:
            fissa = self.imp.value("chiave_fissa", "")
            testo = util.svela(fissa)
            if testo and not testo.startswith("v2:"):
                util.dimentica(fissa)
                self.imp.setValue("chiave_fissa", "")
                _diagnosi("password fissa delle versioni di prima tolta: va reimpostata")
            elif fissa and not util.protetto(fissa):
                self.imp.setValue("chiave_fissa", util.proteggi(fissa, "chiave-fissa"))
            rubrica = list(self.imp.value("rubrica", []) or [])
            cambiata = False
            for v in rubrica:
                if not isinstance(v, dict) or not v.get("chiave"):
                    continue
                testo = util.svela(v["chiave"])
                if testo and not testo.startswith("v2:"):
                    util.dimentica(v.pop("chiave"))
                    cambiata = True
                elif not util.protetto(v["chiave"]):
                    v["chiave"] = util.proteggi(v["chiave"], "rubrica-" + str(v.get("id", "")))
                    cambiata = True
            if cambiata:
                self.imp.setValue("rubrica", rubrica)
        except Exception as exc:
            _diagnosi(f"segreti non cifrati: {exc!r}")

    def _bloccato(self, da):
        voce = self._sbagliate.get(da)
        fino = max(self._bloccato_fino, voce[2] if voce else 0.0)
        return max(0, int(fino - time.monotonic() + 0.999))

    def azzera_tentativi(self):
        self._sbagliate, self._sbagliate_tutte, self._bloccato_fino = {}, [], 0.0

    async def _tentativo_sbagliato(self, da):
        """Password sbagliata da `da`: ogni 3 un blocco per quell'ID (1, 5, 15 minuti); oltre le 3 in un'ora (da
        chiunque) la monouso cambia a ogni errore, così chi prova a indovinarla ricomincia sempre da capo; oltre le
        MAX_SBAGLIATE_ORA non entra nessuno per BLOCCO_TUTTI secondi."""
        ora = time.monotonic()
        self._sbagliate_tutte = [t for t in self._sbagliate_tutte if ora - t < OBLIO_TENTATIVI] + [ora]
        voce = self._sbagliate.get(da)
        if voce is None or ora - voce[1] > OBLIO_TENTATIVI:
            voce = [0, 0.0, 0.0]
        voce[0] += 1
        voce[1] = ora
        self._sbagliate[da] = voce
        if len(self._sbagliate_tutte) > TENTATIVI_PER_BLOCCO:
            await self._rinnova_password()
        blocco = 0
        if voce[0] % TENTATIVI_PER_BLOCCO == 0:
            blocco = BLOCCHI[min(voce[0] // TENTATIVI_PER_BLOCCO, len(BLOCCHI)) - 1]
            voce[2] = ora + blocco
        if len(self._sbagliate_tutte) >= MAX_SBAGLIATE_ORA:
            self._bloccato_fino = ora + BLOCCO_TUTTI
            blocco = max(blocco, BLOCCO_TUTTI)
        self.s.tentativi.emit(voce[0], blocco)

    # ───────────────────────────────────────── lato CONTROLLATO
    async def _rifiuta(self, a, motivo, **altro):
        _diagnosi(f"chiamata da {a} rifiutata: {motivo}")
        try:
            # «v»: chi chiama capisce che qui c'è una tk-desk con il protocollo nuovo (senza = versione vecchia)
            await self._in_thread(self.ce.invia, a, "rifiuto", {"motivo": motivo, "v": ce.PROTOCOLLO, **altro})
        except ce.ErroreCentralino:
            pass

    async def _chiamata_protetta(self, da, d):
        try:
            await self._chiamata_in_arrivo(da, d)
        except Exception as exc:
            _diagnosi(f"chiamata da {da} non gestita: {exc!r}", exc)

    async def _stretta(self, da, d):
        """Lato controllato della stretta di mano SPAKE2: (Spake2, contenuto dell'offerta) se chi chiama conosce la
        password, None se no (già contato come tentativo sbagliato e rifiutato)."""
        n = str(d.get("n", ""))[:32]
        con_fissa = bool(d.get("fissa"))
        chiave = self._chiave_fissa() if con_fissa else self._chiave_monouso
        # senza password fissa si risponde lo stesso, con una chiave a caso: da fuori non si capisce se c'è
        sp = pake.Spake2("B", da, self.id, chiave or secrets.token_bytes(32))
        try:
            await self._in_thread(sp.finisci, d.get("p", ""))
        except pake.ErrorePake:
            await self._tentativo_sbagliato(da)
            await self._rifiuta(da, "password", n=n)
            return None
        fut = self.loop.create_future()
        self._strette[da] = (n, fut)
        try:
            await self._in_thread(self.ce.invia, da, "sfida", {"v": ce.PROTOCOLLO, "n": n, "p": sp.messaggio(),
                                                               "c": sp.conferma()})
            d3 = await asyncio.wait_for(fut, ATTESA_STRETTA)
        except (ce.ErroreCentralino, asyncio.TimeoutError):
            d3 = None     # chi chiama ha visto che la password è sbagliata e non va avanti: conta lo stesso
        finally:
            self._strette.pop(da, None)
        if d3 is None or not sp.conferma_valida(d3.get("c")):
            await self._tentativo_sbagliato(da)
            await self._rifiuta(da, "password", n=n)
            return None
        corpo = str(d3.get("corpo", ""))
        try:
            if not sp.sigillo_valido("offerta", corpo, d3.get("sigillo")):
                raise ValueError("sigillo")
            offerta = json.loads(corpo)
            if not isinstance(offerta, dict) or not offerta.get("sdp"):
                raise ValueError("offerta")
        except ValueError:
            await self._rifiuta(da, "manomesso", n=n)    # messaggio cambiato per strada
            return None
        return sp, offerta, con_fissa, n

    async def _chiedi_conferma(self, da, nome):
        """Finestra «… vuole controllare questo computer — Accetta / Rifiuta» sul computer controllato.
        Senza risposta entro ATTESA_CONFERMA secondi vale come rifiuto."""
        rid = secrets.token_hex(6)
        fut = self.loop.create_future()
        self._richieste[rid] = (fut, da)
        self.s.richiesta_accesso.emit(rid, da, nome)
        try:
            return bool(await asyncio.wait_for(fut, ATTESA_CONFERMA))
        except asyncio.TimeoutError:
            return False
        finally:
            self._richieste.pop(rid, None)
            self.s.richiesta_chiusa.emit(rid)

    def rispondi_accesso(self, rid, accetta):
        """Dalla finestra di conferma (thread della finestra)."""
        def fai():
            voce = self._richieste.get(rid)
            if voce and not voce[0].done():
                voce[0].set_result(bool(accetta))
        self.loop.call_soon_threadsafe(fai)

    async def _chiamata_in_arrivo(self, da, d):
        from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription

        n = str(d.get("n", ""))[:32]
        try:
            vecchia = int(d.get("v") or 0) < ce.PROTOCOLLO or not d.get("p")
        except (TypeError, ValueError):
            vecchia = True
        if vecchia:
            return await self._rifiuta(da, "aggiorna", n=n)   # tk-desk di prima della 1.2.0
        attesa = self._bloccato(da)
        if attesa:
            return await self._rifiuta(da, "bloccato", n=n, attesa=attesa)
        if da in self._strette or any(x[1] == da for x in self._richieste.values()):
            return   # la stessa chiamata ripetuta mentre la stretta di mano o chi è davanti sta decidendo
        stretta = await self._stretta(da, d)
        if stretta is None:
            return
        sp, offerta, con_fissa, n = stretta
        self._sbagliate.pop(da, None)
        sdp = str(offerta["sdp"])
        d = {"nome": str(offerta.get("nome", ""))[:60], "piattaforma": str(offerta.get("piattaforma", ""))[:20],
             "versione": str(offerta.get("versione", ""))[:20]}
        if (self._entrate and da not in self._entrate) or self._richieste:
            return await self._rifiuta(da, "occupato", n=n)
        if not con_fissa:
            # con la monouso decide sempre chi è davanti al computer (difesa dalle truffe al telefono)
            if not await self._chiedi_conferma(da, d["nome"]):
                await self._rinnova_password()   # chi aveva la password non può riprovare
                return await self._rifiuta(da, "rifiutato", n=n)
            if not self.attivo or (self._entrate and da not in self._entrate):
                return await self._rifiuta(da, "occupato", n=n)
        if da in self._entrate:
            await self._chiudi(self._entrate[da], "nuovo collegamento", avvisa=False)

        pc = RTCPeerConnection(RTCConfiguration([RTCIceServer(u) for u in STUN] + await self._ponte()))
        sess = _Sessione(da, da, pc)
        sess.info = {"nome": d.get("nome", ""), "piattaforma": d.get("piattaforma", ""), "fissa": con_fissa}
        sess.sorgente = (self._sorgente_factory or _sorgente_vera)()
        sess.esecutore = self._esecutore or (None if self.su_principale else Esecutore())
        self._entrate[da] = sess
        self._collega_sorgente(sess)

        @pc.on("datachannel")
        def _canale(canale):
            sess.canale = canale

            @canale.on("message")
            def _msg(m):
                asyncio.ensure_future(self._messaggio_controllato(sess, m))

            def _via():
                self._manda(sess, self._info_schermi(sess))
                if getattr(sess.sorgente, "errore", ""):
                    self._manda(sess, {"t": "avviso", "s": f"Schermo non disponibile: {sess.sorgente.errore}"[:300]})
                self.s.controllato_inizio.emit(da, sess.info.get("nome", ""))
                asyncio.ensure_future(self._manda_cursore(sess))
            if canale.readyState == "open":
                _via()
            else:
                canale.on("open", _via)

        @pc.on("connectionstatechange")
        async def _stato():
            _diagnosi(f"chiamata da {da} ({d.get('piattaforma')} {d.get('versione')}): {pc.connectionState}")
            if pc.connectionState in ("failed", "closed"):
                await self._chiudi(sess, "collegamento interrotto", avvisa=False)

        @pc.on("track")
        def _traccia(traccia):
            if traccia.kind == "audio":
                asyncio.ensure_future(au.ascolta(traccia, self.audio, lambda: sess.voce, lambda: sess.chiusa))

        from tkdesk.schermo import crea_traccia
        await pc.setRemoteDescription(RTCSessionDescription(sdp, "offer"))
        pc.addTrack(crea_traccia(sess.sorgente))
        pc.addTrack(au.crea_traccia(self.audio, lambda: sess.voce))
        await pc.setLocalDescription(await pc.createAnswer())
        corpo = json.dumps({"sdp": pc.localDescription.sdp, "nome": self._nome(), "versione": VERSION},
                           separators=(",", ":"))
        try:
            await self._in_thread(self.ce.invia, da, "risposta", {"n": n, "corpo": corpo,
                                                                  "sigillo": sp.sigilla("risposta", corpo)})
        except ce.ErroreCentralino:
            await self._chiudi(sess, "centralino non raggiungibile", avvisa=False)
            return
        # se in 30 secondi il canale non si apre, si chiude tutto (rete che non passa)
        async def _scadenza():
            await asyncio.sleep(ATTESA_COLLEGAMENTO + 5)
            if sess.canale is None and not sess.chiusa:
                await self._chiudi(sess, "collegamento non riuscito", avvisa=False)
        asyncio.ensure_future(_scadenza())

    def _collega_sorgente(self, sess):
        """Sorgenti che diventano pronte dopo (Linux con Wayland: il portale del desktop chiede il permesso a chi
        è davanti): quando lo sono si rimanda l'elenco degli schermi, i problemi vanno a chi controlla."""
        src = sess.sorgente
        if not hasattr(src, "avvia"):
            return

        def nel_ciclo(fn):
            try:
                self.loop.call_soon_threadsafe(lambda: None if sess.chiusa else fn())
            except RuntimeError:
                pass   # motore già fermo

        def problema(testo):
            _diagnosi(f"schermo: {testo}")
            nel_ciclo(lambda: self._manda(sess, {"t": "avviso", "s": str(testo)[:300]}))
        src.al_cambio = lambda: nel_ciclo(lambda: self._manda(sess, self._info_schermi(sess)))
        src.al_problema = problema
        src.avvia()

    async def _manda_cursore(self, sess):
        """La cattura dello schermo non contiene il puntatore: se ne manda la posizione 25 volte al secondo."""
        ultimo = None
        while not sess.chiusa:
            try:
                pos = await self._in_thread(sess.sorgente.cursore)
            except Exception:
                pos = None
            pos = (round(pos[0], 4), round(pos[1], 4)) if pos else (-1, -1)
            if pos != ultimo:
                ultimo = pos
                self._manda(sess, {"t": "cur", "x": pos[0], "y": pos[1]})
            await asyncio.sleep(0.04)

    def _info_schermi(self, sess):
        from tkdesk.tk_licenza import piattaforma
        from tkdesk.util import mac_permessi
        schermo, accesso = mac_permessi()
        return {"t": "info", "schermi": sess.sorgente.schermi, "attivo": sess.sorgente.indice,
                "nome": self._nome(), "piattaforma": piattaforma(), "versione": VERSION,
                "permessi": {"schermo": schermo, "accesso": accesso}}

    def avviso(self, chiave, testo):
        """Dal controllato a chi controlla: un problema da mostrare (es. comandi del mouse rifiutati)."""
        self.manda(chiave, {"t": "avviso", "s": str(testo)[:300]})

    async def _messaggio_controllato(self, sess, m):
        if isinstance(m, (bytes, bytearray)):
            return self._pezzo_file(sess, bytes(m))
        try:
            d = json.loads(m)
        except ValueError:
            return
        t = d.get("t")
        if t in ("mm", "mb", "mw", "k", "c"):
            if sess.esecutore is None:
                self.s.comando.emit(d, dict(sess.sorgente.attuale))
                return
            sess.esecutore.schermo = sess.sorgente.attuale
            try:
                await self._in_thread(sess.esecutore.esegui, d)
            except Exception as exc:
                print("tk-desk: comando non eseguito:", exc)
        elif t == "schermo":
            sess.sorgente.scegli(int(d.get("i", 0)))
            self._manda(sess, self._info_schermi(sess))
        elif t == "appunti":
            if self.appunti_attivi():
                self.s.appunti.emit(sess.chiave, str(d.get("s", ""))[:200000])
        elif t == "chat":
            self.s.chat.emit(sess.chiave, str(d.get("s", ""))[:4000])
        elif t in ("file", "file-fine", "file-no"):
            self._file_controllo(sess, d)
        elif t == "voce":
            await self._voce_ricevuta(sess, d)
        elif t == "rec":
            self.s.registrazione_remota.emit(sess.chiave, bool(d.get("on")))
        elif t == "fine":
            await self._chiudi(sess, "chiusa dall'altro computer", avvisa=False)

    # ───────────────────────────────────────── lato di chi CONTROLLA
    def connetti(self, id_remoto, password, chiave_salvata=""):
        """Avvia la chiamata; ritorna la chiave della sessione (gli esiti arrivano con i segnali).
        `chiave_salvata` = chiave ricavata dalla password fissa, conservata nella rubrica al posto della password
        («v2:<esadecimale>», o solo esadecimale = v1 delle versioni di prima)."""
        self._contatore += 1
        chiave = f"{id_remoto}#{self._contatore}"
        self._nel_ciclo(self._connetti(chiave, id_remoto, password, chiave_salvata))
        return chiave

    async def _connetti(self, chiave_s, id_remoto, password, chiave_salvata=""):
        from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
        from tkdesk.tk_licenza import piattaforma

        if not self.id:
            self.s.sessione_chiusa.emit(chiave_s, "tk-desk non è ancora collegato al centralino: riprova tra poco.")
            return
        if id_remoto == self.id:
            self.s.sessione_chiusa.emit(chiave_s, "Questo è l'ID di questo computer.")
            return
        self.s.stato_chiamata.emit(chiave_s, "Preparo il collegamento…")
        pc = RTCPeerConnection(RTCConfiguration([RTCIceServer(u) for u in STUN] + await self._ponte()))
        sess = _Sessione(chiave_s, id_remoto, pc)
        self._uscite[chiave_s] = sess
        pc.addTransceiver("video", direction="recvonly")
        pc.addTrack(au.crea_traccia(self.audio, lambda: sess.voce))
        sess.canale = pc.createDataChannel("tk")
        aperto = asyncio.Event()

        @sess.canale.on("open")
        def _aperto():
            aperto.set()

        @sess.canale.on("message")
        def _msg(m):
            asyncio.ensure_future(self._messaggio_controllore(sess, m))

        @pc.on("track")
        def _traccia(traccia):
            if traccia.kind == "audio":
                asyncio.ensure_future(au.ascolta(traccia, self.audio, lambda: sess.voce, lambda: sess.chiusa))
            else:
                asyncio.ensure_future(self._leggi_video(sess, traccia))

        @pc.on("connectionstatechange")
        async def _stato():
            if pc.connectionState in ("failed", "closed") and not sess.chiusa:
                await self._chiudi(sess, "Collegamento interrotto.", avvisa=False)

        await pc.setLocalDescription(await pc.createOffer())
        offerta = pc.localDescription.sdp
        if chiave_salvata and not chiave_salvata.startswith("v2:"):
            return await self._chiudi(sess, "La password salvata è di una versione vecchia di tk-desk: scrivila di "
                                            "nuovo.", avvisa=False)
        if chiave_salvata:
            chiave, fissa = bytes.fromhex(chiave_salvata[3:]), True
        else:
            chiave, fissa = await self._in_thread(ce.chiave2, password, id_remoto), ce.e_fissa(password)
        sp = pake.Spake2("A", self.id, id_remoto, chiave)
        n = secrets.token_hex(8)
        coda = asyncio.Queue()
        self._chiamate[id_remoto] = coda

        async def prendi(secondi):
            """Il prossimo messaggio di QUESTA chiamata (quelli di una chiamata di prima si buttano).
            Un rifiuto senza «n» viene da una tk-desk di prima: vale (dice che va aggiornata)."""
            fine = time.monotonic() + secondi
            while True:
                tipo_, d_ = await asyncio.wait_for(coda.get(), max(0.1, fine - time.monotonic()))
                if str(d_.get("n", "")) == n or (tipo_ == "rifiuto" and not d_.get("n")):
                    return tipo_, d_

        self.s.stato_chiamata.emit(chiave_s, "Chiamo il computer… Dall'altra parte devono premere «Accetta».")
        try:
            await self._in_thread(self.ce.invia, id_remoto, "chiamata",
                                  {"v": ce.PROTOCOLLO, "n": n, "p": sp.messaggio(), "fissa": fissa})
            tipo, d = await prendi(ATTESA_STRETTA + 10)
            if tipo == "sfida":
                try:
                    await self._in_thread(sp.finisci, d.get("p", ""))
                    giusta = sp.conferma_valida(d.get("c"))
                except pake.ErrorePake:
                    giusta = False
                if not giusta:
                    # l'altro computer conta il tentativo subito, senza aspettare
                    await self._in_thread(self.ce.invia, id_remoto, "offerta", {"n": n, "c": ""})
                    return await self._chiudi(sess, "Password sbagliata.", avvisa=False)
                corpo = json.dumps({"sdp": offerta, "nome": self._nome(), "piattaforma": piattaforma(),
                                    "versione": VERSION}, separators=(",", ":"))
                await self._in_thread(self.ce.invia, id_remoto, "offerta", {
                    "n": n, "c": sp.conferma(), "corpo": corpo, "sigillo": sp.sigilla("offerta", corpo)})
                tipo, d = await prendi(ATTESA_RISPOSTA)
        except ce.ErroreCentralino as e:
            return await self._chiudi(sess, str(e), avvisa=False)
        except asyncio.TimeoutError:
            return await self._chiudi(sess, "Il computer non risponde: controlla che tk-desk sia aperto e che "
                                            "l'altra persona abbia premuto «Accetta».", avvisa=False)
        finally:
            self._chiamate.pop(id_remoto, None)
        if tipo == "rifiuto":
            try:
                minuti = max(1, round(int(d.get("attesa") or 60) / 60))
            except (TypeError, ValueError):
                minuti = 1
            motivi = {"password": "Password sbagliata.",
                      "bloccato": f"Troppe password sbagliate: il computer non accetta tentativi per {minuti} "
                                  f"minut{'o' if minuti == 1 else 'i'}.",
                      "occupato": "Quel computer è già in una sessione con qualcun altro.",
                      "rifiutato": "L'altra persona non ha accettato il collegamento (o non ha risposto in 30 secondi).",
                      "manomesso": "Il collegamento è stato alterato per strada: interrotto per sicurezza.",
                      "aggiorna": "Questa versione di tk-desk non si collega più: aggiornala."}
            if (d.get("v") or 0) != ce.PROTOCOLLO:
                motivo = "Su quel computer c'è una versione vecchia di tk-desk: va aggiornata."
            else:
                motivo = motivi.get(d.get("motivo"), "Collegamento rifiutato.")
            return await self._chiudi(sess, motivo, avvisa=False)
        corpo = str(d.get("corpo", ""))
        try:
            if tipo != "risposta" or not sp.sigillo_valido("risposta", corpo, d.get("sigillo")):
                raise ValueError("sigillo")
            r = json.loads(corpo)
            risposta = str(r["sdp"])
        except (ValueError, KeyError, TypeError):
            return await self._chiudi(sess, "Risposta non firmata: collegamento interrotto per sicurezza.", avvisa=False)
        sess.info["nome"] = str(r.get("nome", ""))[:60]
        self.s.stato_chiamata.emit(chiave_s, "Collegamento in corso…")
        await pc.setRemoteDescription(RTCSessionDescription(risposta, "answer"))
        try:
            await asyncio.wait_for(aperto.wait(), ATTESA_COLLEGAMENTO)
        except asyncio.TimeoutError:
            return await self._chiudi(sess, "I due computer non riescono a collegarsi direttamente (rete aziendale o "
                                            "protetta). Prova da un'altra connessione.", avvisa=True)

    async def _leggi_video(self, sess, traccia):
        while not sess.chiusa:
            try:
                fr = await traccia.recv()
            except Exception:
                break
            if sess.registra:
                self._registra_fotogramma(sess, fr)
            if sess.occupato:          # la finestra non ha ancora disegnato il precedente: si salta
                continue
            sess.occupato = True
            rgb = await self._in_thread(lambda f=fr: f.to_ndarray(format="rgb24"))
            self.s.fotogramma.emit(sess.chiave, rgb.tobytes(), rgb.shape[1], rgb.shape[0])

    def disegnato(self, chiave):
        s = self._uscite.get(chiave)
        if s:
            s.occupato = False

    async def _messaggio_controllore(self, sess, m):
        if isinstance(m, (bytes, bytearray)):
            return self._pezzo_file(sess, bytes(m))
        try:
            d = json.loads(m)
        except ValueError:
            return
        t = d.get("t")
        if t == "info":
            prima = bool(sess.info.get("schermi"))
            sess.info.update({k: d.get(k) for k in ("schermi", "attivo", "nome", "piattaforma", "versione", "permessi")})
            if not prima:
                self.s.sessione_aperta.emit(sess.chiave, dict(sess.info))
            else:
                self.s.stato_chiamata.emit(sess.chiave, "schermi")
        elif t == "appunti":
            if self.appunti_attivi():
                self.s.appunti.emit(sess.chiave, str(d.get("s", ""))[:200000])
        elif t == "chat":
            self.s.chat.emit(sess.chiave, str(d.get("s", ""))[:4000])
        elif t in ("file", "file-fine", "file-no"):
            self._file_controllo(sess, d)
        elif t == "voce":
            await self._voce_ricevuta(sess, d)
        elif t == "cur":
            self.s.cursore.emit(sess.chiave, float(d.get("x", -1)), float(d.get("y", -1)))
        elif t == "avviso":
            self.s.stato_chiamata.emit(sess.chiave, "avviso:" + str(d.get("s", ""))[:300])
        elif t == "fine":
            await self._chiudi(sess, "Sessione chiusa dall'altro computer.", avvisa=False)

    def info(self, chiave):
        s = self._uscite.get(chiave)
        return dict(s.info) if s else {}

    # ───────────────────────────────────────── per entrambi i lati
    def _sessione(self, chiave):
        return self._uscite.get(chiave) or self._entrate.get(chiave)

    def _manda(self, sess, dati):
        try:
            if sess.canale is not None and sess.canale.readyState == "open":
                sess.canale.send(json.dumps(dati, separators=(",", ":")) if isinstance(dati, dict) else dati)
        except Exception:
            pass

    def manda(self, chiave, dati):
        """Dalla finestra: comandi, chat, scelta dello schermo (gli appunti con manda_appunti)."""
        if isinstance(dati, dict) and dati.get("t") == "appunti" and not self.appunti_attivi():
            return

        def fai():
            s = self._sessione(chiave)
            if s:
                self._manda(s, dati)
        self.loop.call_soon_threadsafe(fai)

    # ── appunti condivisi: solo se accesi nelle Impostazioni (spenti di default)
    def appunti_attivi(self):
        return bool(self.imp.value("appunti", False))

    def manda_appunti(self, chiave, testo):
        if self.appunti_attivi() and testo:
            self.manda(chiave, {"t": "appunti", "s": str(testo)[:200000]})

    def chiudi(self, chiave, motivo="Sessione chiusa."):
        s = self._sessione(chiave)
        if s:
            self._nel_ciclo(self._chiudi(s, motivo, avvisa=True))

    async def _chiudi(self, sess, motivo, avvisa):
        if sess.chiusa:
            return
        sess.chiusa = True
        if avvisa:
            self._manda(sess, {"t": "fine"})
            await asyncio.sleep(0.2)
        self._ferma_registrazione(sess)
        if sess.voce:
            sess.voce = False
            await self._in_thread(self.audio.ferma)
        for fid in list(sess.file_in):
            self._scarta_file(sess, fid, avvisa=False)   # i file non ancora accettati non arrivano
        if self._uscite.get(sess.chiave) is sess:
            await self._segnala_uso(sess)
        try:
            await sess.pc.close()
        except Exception:
            pass
        if self._uscite.get(sess.chiave) is sess:
            del self._uscite[sess.chiave]
            self.s.sessione_chiusa.emit(sess.chiave, motivo)
        if self._entrate.get(sess.remoto) is sess:
            del self._entrate[sess.remoto]
            try:
                if sess.esecutore is None:
                    self.s.comando.emit({"t": "rilascia"}, {})
                else:
                    sess.esecutore.rilascia_tutto()
                sess.sorgente.chiudi()
            except Exception:
                pass
            self.s.controllato_fine.emit(sess.remoto, motivo)
            # password monouso: dopo ogni sessione se ne fa una nuova
            await self._rinnova_password()

    # ── file
    def manda_file(self, chiave, percorso):
        self._nel_ciclo(self._manda_file(chiave, percorso))

    async def _manda_file(self, chiave, percorso):
        s = self._sessione(chiave)
        if not s or s.canale is None:
            return
        nome = os.path.basename(percorso)
        totale = os.path.getsize(percorso)
        if totale > util.LIMITE_FILE:
            self.s.file_rifiutato.emit(chiave, nome, "è più grande di 2 GB")
            return
        fid = secrets.token_hex(4)
        self._manda(s, {"t": "file", "id": fid, "n": nome, "size": totale})
        fatti = 0
        with open(percorso, "rb") as fh:
            while not s.chiusa and fid not in s.file_fermati:
                pezzo = fh.read(PEZZO_FILE)
                if not pezzo:
                    break
                while s.canale.bufferedAmount > 1_000_000 and not s.chiusa:
                    await asyncio.sleep(0.02)
                s.canale.send(fid.encode() + pezzo)
                fatti += len(pezzo)
                if fatti == totale or fatti % (PEZZO_FILE * 32) == 0:
                    self.s.file_avanzamento.emit(chiave, nome, fatti, totale)
        if fid in s.file_fermati or s.chiusa:
            return
        self._manda(s, {"t": "file-fine", "id": fid})
        self.s.file_avanzamento.emit(chiave, nome, totale, totale)

    def _file_controllo(self, sess, d):
        fid = str(d.get("id", ""))[:8]
        t = d.get("t")
        if t == "file-no":                      # l'altro non vuole il file che sto mandando
            sess.file_fermati.add(fid)
            self.s.file_rifiutato.emit(sess.chiave, str(d.get("n", ""))[:180], str(d.get("motivo", "rifiutato"))[:80])
            return
        if t == "file":
            nome = nome_file_sicuro(d.get("n", "file"))
            try:
                totale = int(d.get("size", 0))
            except (TypeError, ValueError):
                totale = -1
            if fid in sess.file_in or fid in sess.file_scartati:
                return
            if totale < 0 or totale > util.LIMITE_FILE:
                sess.file_scartati.add(fid)
                self._manda(sess, {"t": "file-no", "id": fid, "n": nome, "motivo": "più grande di 2 GB"})
                self.s.file_rifiutato.emit(sess.chiave, nome, "è più grande di 2 GB")
                return
            # finché chi è davanti non accetta, il file resta nella cartella di attesa (non sulla Scrivania)
            attesa = os.path.join(util.cartella_in_arrivo(), secrets.token_hex(8) + ".part")
            sess.file_in[fid] = [open(attesa, "wb"), attesa, nome, totale, 0, None, False]
            self.s.file_in_arrivo.emit(sess.chiave, fid, nome, totale)
            return
        voce = sess.file_in.get(fid)                # file-fine
        if voce:
            voce[6] = True
            if voce[5] is True:
                self._consegna_file(sess, fid)

    def _pezzo_file(self, sess, dati):
        fid = dati[:8].decode("ascii", "replace")
        voce = sess.file_in.get(fid)
        if not voce:
            return
        voce[4] += len(dati) - 8
        if voce[4] > voce[3]:                       # più dati di quelli annunciati: si butta tutto
            self._scarta_file(sess, fid, motivo="dimensione sbagliata")
            return
        voce[0].write(dati[8:])
        if voce[4] == voce[3] or voce[4] % (PEZZO_FILE * 32) == 0:
            self.s.file_avanzamento.emit(sess.chiave, voce[2], voce[4], voce[3])

    def accetta_file(self, chiave, fid, accetta):
        """Dalla finestra: chi è davanti ha detto sì o no a un file in arrivo."""
        def fai():
            s = self._sessione(chiave)
            voce = s.file_in.get(fid) if s else None
            if not voce:
                return
            if not accetta:
                self._scarta_file(s, fid)
                return
            voce[5] = True
            if voce[6]:
                self._consegna_file(s, fid)
        self.loop.call_soon_threadsafe(fai)

    def _consegna_file(self, sess, fid):
        """File accettato e arrivato tutto: sulla Scrivania, segnato come scaricato da internet."""
        import shutil
        voce = sess.file_in.pop(fid, None)
        if not voce:
            return
        try:
            voce[0].close()
            cartella = util.cartella_ricevuti()
            base, est = os.path.splitext(voce[2])
            percorso, n = os.path.join(cartella, voce[2]), 1
            while os.path.exists(percorso):
                n += 1
                percorso = os.path.join(cartella, f"{base} ({n}){est}")
            shutil.move(voce[1], percorso)
            util.segna_come_scaricato(percorso)
        except OSError as exc:
            _diagnosi(f"file «{voce[2]}» non salvato: {exc!r}")
            self.s.file_rifiutato.emit(sess.chiave, voce[2], f"non riesco a salvarlo ({exc})")
            return
        self.s.file_ricevuto.emit(sess.chiave, percorso)

    def _scarta_file(self, sess, fid, avvisa=True, motivo="rifiutato"):
        voce = sess.file_in.pop(fid, None)
        sess.file_scartati.add(fid)
        if not voce:
            return
        try:
            voce[0].close()
            os.remove(voce[1])
        except OSError:
            pass
        if avvisa:
            self._manda(sess, {"t": "file-no", "id": fid, "n": voce[2], "motivo": motivo})

    # ── chiamata vocale
    def voce(self, chiave, on):
        """Dalla finestra: chiede/accetta (on=True) o chiude/rifiuta (on=False) la chiamata."""
        self._nel_ciclo(self._voce(chiave, on))

    async def _voce(self, chiave, on):
        s = self._sessione(chiave)
        if not s or s.chiusa:
            return
        if on:
            s.voce_mia = True
            self._manda(s, {"t": "voce", "on": 1})
            if s.voce_remota:
                await self._voce_attiva(s)
        else:
            s.voce_mia = s.voce_remota = False
            self._manda(s, {"t": "voce", "on": 0})
            await self._voce_spenta(s, "chiusa")

    async def _voce_ricevuta(self, s, d):
        if d.get("on"):
            s.voce_remota = True
            if s.voce_mia:
                await self._voce_attiva(s)
            elif not s.voce:
                self.s.voce_chiesta.emit(s.chiave)
        else:
            rifiutata = s.voce_mia and not s.voce
            s.voce_mia = s.voce_remota = False
            await self._voce_spenta(s, "rifiutata" if rifiutata else "chiusa")

    async def _voce_attiva(self, s):
        if s.voce:
            return
        for altra in list(self._uscite.values()) + list(self._entrate.values()):   # una chiamata alla volta
            if altra is not s and altra.voce:
                await self._voce(altra.chiave, False)
        avviso = await self._in_thread(self.audio.avvia)
        s.voce = True
        self.s.voce_stato.emit(s.chiave, "attiva", avviso or "")

    async def _voce_spenta(self, s, motivo):
        if s.voce:
            s.voce = False
            await self._in_thread(self.audio.ferma)
        self.s.voce_stato.emit(s.chiave, motivo, "")

    # ── registrazione: video MPEG-4 apribile con VLC, QuickTime e il lettore di Windows
    def registra(self, chiave, percorso):
        def fai():
            s = self._uscite.get(chiave)
            if s:
                if percorso:
                    s.registra = ("da-aprire", percorso)
                else:
                    self._ferma_registrazione(s)
        self.loop.call_soon_threadsafe(fai)

    def _registra_fotogramma(self, sess, fr):
        import av
        try:
            if sess.registra[0] == "da-aprire":
                percorso = sess.registra[1]
                import fractions
                cont = av.open(percorso, "w")
                st = cont.add_stream("mpeg4", rate=30)
                st.width, st.height = fr.width // 2 * 2, fr.height // 2 * 2
                st.pix_fmt = "yuv420p"
                st.bit_rate = 4_000_000
                st.codec_context.time_base = fractions.Fraction(1, 1000)   # millesimi: i fotogrammi arrivano irregolari
                sess.registra = [cont, st, percorso, time.monotonic(), -1]
                self._manda(sess, {"t": "rec", "on": 1})   # chi è controllato deve saperlo: vede «REC»
                self.s.registrazione.emit(sess.chiave, percorso)
            cont, st, percorso, inizio, ultimo = sess.registra
            f = fr.reformat(width=st.width, height=st.height, format="yuv420p")
            pts = max(int((time.monotonic() - inizio) * 1000), ultimo + 1)
            sess.registra[4] = pts
            f.pts = pts
            f.time_base = st.codec_context.time_base
            for pk in st.encode(f):
                cont.mux(pk)
        except Exception as exc:
            print("tk-desk: registrazione interrotta:", exc)
            self._ferma_registrazione(sess)

    def _ferma_registrazione(self, sess):
        r = sess.registra
        sess.registra = None
        if r and r[0] != "da-aprire":
            try:
                cont, st = r[0], r[1]
                for pk in st.encode(None):
                    cont.mux(pk)
                cont.close()
            except Exception:
                pass
            self._manda(sess, {"t": "rec", "on": 0})
            self.s.registrazione.emit(sess.chiave, "")

    # ── rubrica
    def stato_rubrica(self, ids):
        """Chiamata bloccante (rete): quali ID della rubrica sono accesi adesso."""
        if not self.id or not ids:
            return {}
        return self.ce.stato(ids)

    def sessioni_uscita(self):
        return list(self._uscite.keys())

    def sessioni_entrata(self):
        return list(self._entrate.keys())


def _sorgente_vera():
    from tkdesk.schermo import crea_sorgente
    return crea_sorgente()
