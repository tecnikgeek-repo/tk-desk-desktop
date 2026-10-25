"""Chiamata vocale: microfono → traccia WebRTC (Opus) e voce ricevuta → altoparlanti, con sounddevice (PortAudio).

La traccia audio c'è da subito in ogni sessione e manda silenzio finché la chiamata non è attiva: così la
chiamata parte e si chiude senza rinegoziare il collegamento. `AudioFinto` serve alle prove (tono al posto
del microfono, conta i campioni ricevuti).
"""
import asyncio
import fractions
import queue
import threading
import time

import numpy as np

RATE = 48000
CAMPIONI = 960          # 20 ms a 48 kHz
MAX_RITARDO = RATE // 4  # oltre 250 ms in coda si butta il vecchio: meglio un salto che una voce in ritardo


def _ricampiona(dati, da, a):
    if da == a or len(dati) == 0:
        return dati
    n = max(1, int(round(len(dati) * a / da)))
    x = np.linspace(0, len(dati) - 1, n)
    return np.interp(x, np.arange(len(dati)), dati.astype(np.float32)).astype(np.int16)


class Audio:
    def __init__(self):
        self._mic = None
        self._out = None
        self._rate_mic = RATE
        self._rate_out = RATE
        self._coda_mic = queue.Queue(maxsize=50)
        self._buf_mic = np.zeros(0, np.int16)
        self._buf_out = np.zeros(0, np.int16)
        self._blocco = threading.Lock()

    def avvia(self):
        """Apre microfono e altoparlanti. Ritorna "" o la descrizione di cosa non va (la chiamata parte lo stesso)."""
        self.ferma()
        try:
            import sounddevice as sd
        except Exception as exc:
            return f"audio non disponibile ({exc})"
        errori = []
        for tipo in ("input", "output"):
            stream = None
            for rate in (RATE, None):
                try:
                    if rate is None:
                        rate = int(sd.query_devices(kind=tipo)["default_samplerate"])
                    classe = sd.InputStream if tipo == "input" else sd.OutputStream
                    cb = self._dal_mic if tipo == "input" else self._agli_altoparlanti
                    stream = classe(samplerate=rate, channels=1, dtype="int16", callback=cb,
                                    blocksize=int(rate * 0.02), latency="low")
                    stream.start()
                    break
                except Exception as exc:
                    stream = None
                    err = exc
            if stream is None:
                errori.append(("microfono" if tipo == "input" else "altoparlanti") + f": {err}")
            elif tipo == "input":
                self._mic, self._rate_mic = stream, rate
            else:
                self._out, self._rate_out = stream, rate
        return " · ".join(errori)

    def ferma(self):
        for s in (self._mic, self._out):
            if s is not None:
                try:
                    s.stop()
                    s.close()
                except Exception:
                    pass
        self._mic = self._out = None
        with self._blocco:
            self._buf_out = np.zeros(0, np.int16)
            self._buf_mic = np.zeros(0, np.int16)
        while not self._coda_mic.empty():
            self._coda_mic.get_nowait()

    # PortAudio chiama queste due dal suo thread
    def _dal_mic(self, dati, n, t, stato):
        try:
            self._coda_mic.put_nowait(dati[:, 0].copy())
        except queue.Full:
            pass

    def _agli_altoparlanti(self, out, n, t, stato):
        with self._blocco:
            pezzo = self._buf_out[:n]
            self._buf_out = self._buf_out[n:]
        out[:len(pezzo), 0] = pezzo
        out[len(pezzo):, 0] = 0

    # dal motore
    def leggi_mic(self):
        """20 ms di microfono a 48 kHz, o None (si manda silenzio)."""
        while True:
            try:
                d = self._coda_mic.get_nowait()
            except queue.Empty:
                break
            d = _ricampiona(d, self._rate_mic, RATE)
            self._buf_mic = np.concatenate([self._buf_mic, d])[-MAX_RITARDO:]
        if len(self._buf_mic) < CAMPIONI:
            return None
        out, self._buf_mic = self._buf_mic[:CAMPIONI], self._buf_mic[CAMPIONI:]
        return out

    def suona(self, campioni):
        if self._out is None:
            return
        campioni = _ricampiona(campioni, RATE, self._rate_out)
        with self._blocco:
            self._buf_out = np.concatenate([self._buf_out, campioni])[-MAX_RITARDO:]


class AudioFinto(Audio):
    """Per le prove: il «microfono» è un tono a 440 Hz, gli «altoparlanti» contano i campioni non silenziosi."""

    def __init__(self):
        super().__init__()
        self.attivo = False
        self.suonati = 0
        self._fase = 0

    def avvia(self):
        self.attivo = True
        return ""

    def ferma(self):
        self.attivo = False

    def leggi_mic(self):
        if not self.attivo:
            return None
        t = (np.arange(CAMPIONI) + self._fase) / RATE
        self._fase += CAMPIONI
        return (np.sin(2 * np.pi * 440 * t) * 8000).astype(np.int16)

    def suona(self, campioni):
        if self.attivo:
            self.suonati += int(np.count_nonzero(np.abs(campioni) > 500))


def crea_traccia(audio, attiva):
    """Traccia audio WebRTC: ogni 20 ms il microfono se la chiamata è attiva (`attiva()`), altrimenti silenzio."""
    import av
    from aiortc import MediaStreamTrack

    class TracciaVoce(MediaStreamTrack):
        kind = "audio"

        def __init__(self):
            super().__init__()
            self._inizio = None
            self._n = 0

        async def recv(self):
            if self._inizio is None:
                self._inizio = time.monotonic()
            self._n += 1
            attesa = self._inizio + self._n * 0.02 - time.monotonic()
            if attesa > 0:
                await asyncio.sleep(attesa)
            campioni = audio.leggi_mic() if attiva() else None
            if campioni is None:
                campioni = np.zeros(CAMPIONI, np.int16)
            fr = av.AudioFrame.from_ndarray(campioni.reshape(1, -1), format="s16", layout="mono")
            fr.sample_rate = RATE
            fr.pts = self._n * CAMPIONI
            fr.time_base = fractions.Fraction(1, RATE)
            return fr

    return TracciaVoce()


def ascolta(traccia, audio, attiva, chiusa):
    """Legge la voce dell'altro computer e la manda agli altoparlanti mentre la chiamata è attiva."""
    import av
    ricampionatore = av.AudioResampler(format="s16", layout="mono", rate=RATE)

    async def ciclo():
        while not chiusa():
            try:
                fr = await traccia.recv()
            except Exception:
                break
            if not attiva():
                continue
            try:
                for f in ricampionatore.resample(fr):
                    audio.suona(f.to_ndarray().reshape(-1).astype(np.int16))
            except Exception:
                pass
    return ciclo()
