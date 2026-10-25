"""Cattura dello schermo per la sessione: schermi disponibili e fotogrammi da mandare in WebRTC.

La cattura vera (mss) gira in un thread suo: la libreria non va usata da più thread insieme.
`SorgenteFinta` disegna uno schermo di prova: serve ai test e al selftest del pacchetto, che girano
anche dove non c'è un desktop da catturare.
"""
import concurrent.futures
import threading
import time

import numpy as np

LATO_MAX = 2560          # oltre, il fotogramma si riduce (Retina 2880 → 2560: testo ancora nitido)
FPS = 25


class SorgenteSchermo:
    def __init__(self):
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="cattura")
        self._locale = threading.local()
        self.indice = 0
        self.schermi = self._pool.submit(self._elenco).result(timeout=15)

    def _mss(self):
        s = getattr(self._locale, "mss", None)
        if s is None:
            import mss
            s = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
            self._locale.mss = s
        return s

    def _elenco(self):
        mon = self._mss().monitors[1:] or self._mss().monitors[:1]
        return [{"left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]} for m in mon]

    def scegli(self, indice):
        if 0 <= indice < len(self.schermi):
            self.indice = indice

    @property
    def attuale(self):
        return self.schermi[self.indice]

    def _cattura(self):
        img = self._mss().grab(self.attuale)
        return np.asarray(img)  # BGRA

    def cattura(self):
        """Fotogramma BGRA dello schermo scelto (dal thread della cattura)."""
        return self._pool.submit(self._cattura)

    def chiudi(self):
        self._pool.shutdown(wait=False, cancel_futures=True)

    def cursore(self):
        """Posizione del puntatore (0..1) sullo schermo condiviso, None se è su un altro schermo."""
        pos = posizione_puntatore()
        if pos is None:
            return None
        s = self.attuale
        x, y = (pos[0] - s["left"]) / s["width"], (pos[1] - s["top"]) / s["height"]
        return (x, y) if 0 <= x <= 1 and 0 <= y <= 1 else None


def posizione_puntatore():
    """Puntatore nelle stesse unità di mss: pixel su Windows (il processo è DPI-aware), punti su Mac."""
    import ctypes
    import sys
    try:
        if sys.platform == "win32":
            class P(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            p = P()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(p)):
                return p.x, p.y
        elif sys.platform == "darwin":
            # prima Quartz (pyobjc, lo stesso che usa pynput per muovere il mouse), poi ctypes
            try:
                import Quartz
                pt = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
                return pt.x, pt.y
            except Exception as exc:
                _segnala("Quartz", exc)
            import ctypes.util

            class CGPoint(ctypes.Structure):
                _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]
            cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))
            cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
            cg.CGEventCreate.restype = ctypes.c_void_p
            cg.CGEventCreate.argtypes = [ctypes.c_void_p]
            cg.CGEventGetLocation.restype = CGPoint
            cg.CGEventGetLocation.argtypes = [ctypes.c_void_p]
            cf.CFRelease.argtypes = [ctypes.c_void_p]
            ev = cg.CGEventCreate(None)
            if ev:
                pt = cg.CGEventGetLocation(ev)
                cf.CFRelease(ev)
                return pt.x, pt.y
    except Exception as exc:
        _segnala("ctypes", exc)
    return None


_segnalati = set()


def _segnala(dove, exc):
    """Una riga in diagnosi.log (cartella dei dati) la prima volta che la posizione del puntatore non si legge."""
    if dove in _segnalati:
        return
    _segnalati.add(dove)
    try:
        import os
        import time
        from tkdesk.util import log_dir
        with open(os.path.join(log_dir(), "diagnosi.log"), "a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] puntatore ({dove}): {exc!r}\n")
    except Exception:
        pass


class SorgenteFinta:
    """Schermo di prova: sfondo a fasce e un quadrato che si muove; due «schermi» di misure diverse."""

    def __init__(self):
        self.schermi = [{"left": 0, "top": 0, "width": 1280, "height": 720},
                        {"left": 1280, "top": 0, "width": 800, "height": 600}]
        self.indice = 0
        self.n = 0
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def scegli(self, indice):
        if 0 <= indice < len(self.schermi):
            self.indice = indice

    @property
    def attuale(self):
        return self.schermi[self.indice]

    def _cattura(self):
        s = self.attuale
        h, w = s["height"], s["width"]
        img = np.zeros((h, w, 4), dtype=np.uint8)
        img[:, :, 0] = np.linspace(80, 180, w, dtype=np.uint8)[None, :]     # B
        img[:, :, 1] = np.linspace(40, 120, h, dtype=np.uint8)[:, None]     # G
        img[:, :, 2] = 30 + 60 * self.indice                                # R: cambia con lo schermo
        img[:, :, 3] = 255
        self.n += 1
        x = (self.n * 12) % max(1, w - 120)
        img[h // 3:h // 3 + 120, x:x + 120, :3] = 255
        return img

    def cattura(self):
        return self._pool.submit(self._cattura)

    def chiudi(self):
        self._pool.shutdown(wait=False, cancel_futures=True)

    def cursore(self):
        return (0.25, 0.5)


def crea_traccia(sorgente):
    """Traccia video WebRTC che legge dalla sorgente al massimo FPS volte al secondo."""
    import asyncio
    import fractions

    import av
    from aiortc import MediaStreamTrack

    class TracciaSchermo(MediaStreamTrack):
        kind = "video"

        def __init__(self):
            super().__init__()
            self._inizio = None
            self._ultimo = 0.0

        async def recv(self):
            attesa = 1.0 / FPS - (time.monotonic() - self._ultimo)
            if attesa > 0:
                await asyncio.sleep(attesa)
            self._ultimo = time.monotonic()
            if self._inizio is None:
                self._inizio = self._ultimo
            try:
                img = await asyncio.wrap_future(sorgente.cattura())
            except Exception:
                # schermo bloccato, UAC o cambio di risoluzione: si ripete un fotogramma nero
                s = sorgente.attuale
                img = np.zeros((max(2, s["height"]), max(2, s["width"]), 4), dtype=np.uint8)
            fr = av.VideoFrame.from_ndarray(np.ascontiguousarray(img[:, :, :3]), format="bgr24")
            w, h = fr.width, fr.height
            scala = min(1.0, LATO_MAX / max(w, h))
            nw, nh = int(w * scala) // 2 * 2, int(h * scala) // 2 * 2
            if (nw, nh) != (w, h):
                fr = fr.reformat(width=nw, height=nh)
            fr.pts = int((self._ultimo - self._inizio) * 90000)
            fr.time_base = fractions.Fraction(1, 90000)
            return fr

    return TracciaSchermo()
