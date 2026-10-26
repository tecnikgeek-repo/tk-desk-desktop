"""Centralino di tk-desk: ID del computer e scambio dei messaggi per far conoscere i due computer.

Il server (tk-license-server, /desk/*) fa da cassetta delle lettere: passa le offerte WebRTC, non vede lo schermo,
i file né la chat (vanno diretti e cifrati da un computer all'altro) e la password non gli passa mai.
Dalla 1.2.0 (protocollo 3) la password la verificano i due computer con SPAKE2 (pake.py): dai messaggi del
centralino non si ricava, nemmeno provandole tutte. La chiave della password resta PBKDF2 (chiave2), lenta apposta
per chi rubasse il file delle impostazioni. Le versioni di prima (firma HMAC, chiavi v1 e v2) non si collegano più:
il centralino le rifiuta (Pietro, 26/10: «chi non aggiorna il software non funziona»).
"""
import hashlib
import json
import os
import platform
import secrets
import ssl
import string
import urllib.error
import urllib.request

from tkdesk import VERSION

SERVER = os.environ.get("TKDESK_SERVER", "https://pietrodefilippis.it/wp-json/tk-license/v1/desk")
PROTOCOLLO = 3               # SPAKE2: il centralino rifiuta chi ne dichiara uno più vecchio

# password monouso: 6 cifre, facili da dettare al telefono (Pietro, 25/10: «solo numerica»)
ALFABETO = "0123456789"


class ErroreCentralino(Exception):
    def __init__(self, messaggio, codice=""):
        super().__init__(messaggio)
        self.codice = codice


def nuova_password(lunghezza=6):
    return "".join(secrets.choice(ALFABETO) for _ in range(lunghezza))


def formatta_id(id_):
    s = "".join(c for c in str(id_) if c.isdigit())
    return " ".join(s[i:i + 3] for i in range(0, len(s), 3))


def pulisci_id(testo):
    s = "".join(c for c in str(testo) if c.isdigit())
    return s if len(s) == 9 else ""


GIRI = 600_000


def _normalizza(password):
    pw = (password or "").strip()
    if len(pw.replace(" ", "")) <= 6:   # monouso: si accetta anche scritta «123 456» o in maiuscolo
        pw = pw.replace(" ", "").lower()
    return pw.encode("utf-8")


def e_fissa(password):
    """La monouso ha 6 cifre, la fissa almeno 8 caratteri: chi chiama dice quale delle due sta usando."""
    return len((password or "").strip().replace(" ", "")) > 6


def chiave2(password, id_controllato):
    """Chiave della password per SPAKE2, ricavata anche dall'ID del computer controllato (lenta apposta: 600.000
    giri). Il computer controllato conserva solo questa (cifrata, vedi util.proteggi), mai la password fissa in
    chiaro; la rubrica di chi controlla idem («v2:<esadecimale>»)."""
    return hashlib.pbkdf2_hmac("sha256", _normalizza(password), f"tk-desk-v2|{id_controllato}".encode(), GIRI)


def id_dispositivo():
    """Codice anonimo per il centralino: casuale, creato la prima volta (non si legge nulla dal computer)."""
    return secrets.token_hex(20)


def nome_di_sistema():
    try:
        return (platform.node() or "").split(".")[0][:60]
    except Exception:
        return ""


def nome_computer(impostazioni=None):
    """Il nome con cui gli altri vedono questo computer (al centralino e nelle sessioni): quello scelto
    nelle Impostazioni, altrimenti il nome del computer."""
    try:
        scelto = str(impostazioni.value("nome_computer", "") or "").strip() if impostazioni is not None else ""
    except Exception:
        scelto = ""
    return (scelto or nome_di_sistema())[:60]


def _contesto():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


class Centralino:
    """Client del centralino. Tutti i metodi fanno rete: vanno chiamati fuori dal thread della finestra."""

    def __init__(self, impostazioni):
        self.imp = impostazioni
        self.id = ""
        segreto = self.imp.value("centralino_segreto", "")
        if len(segreto) < 32:
            segreto = secrets.token_hex(24)
            self.imp.setValue("centralino_segreto", segreto)
        self.segreto = segreto
        disp = self.imp.value("centralino_dispositivo", "") or id_dispositivo() or secrets.token_hex(20)
        self.imp.setValue("centralino_dispositivo", disp)
        self.dispositivo = disp

    def _post(self, rotta, dati, timeout=15):
        corpo = json.dumps(dati).encode("utf-8")
        req = urllib.request.Request(f"{SERVER}/{rotta}", data=corpo, method="POST", headers={
            "Content-Type": "application/json", "User-Agent": f"tk-desk/{VERSION}", "Cache-Control": "no-cache"})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_contesto()) as r:
                risposta = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                risposta = json.loads(e.read().decode("utf-8"))
            except Exception:
                raise ErroreCentralino(f"Il server ha risposto {e.code}", "http") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ErroreCentralino("Nessuna connessione a internet o server non raggiungibile.", "rete") from e
        if not isinstance(risposta, dict):
            raise ErroreCentralino("Risposta del server non valida.", "risposta")
        if not risposta.get("ok"):
            raise ErroreCentralino(risposta.get("message") or "Errore del server.", risposta.get("code", ""))
        return risposta

    def registra(self):
        from tkdesk.tk_licenza import piattaforma
        r = self._post("registra", {"dispositivo": self.dispositivo, "segreto": self.segreto, "nome": nome_computer(self.imp),
                                    "piattaforma": piattaforma(), "versione": VERSION, "protocollo": PROTOCOLLO})
        self.id = r["id"]
        self.imp.setValue("centralino_id", self.id)
        return self.id

    def invia(self, a, tipo, dati):
        self._post("invia", {"id": self.id, "segreto": self.segreto, "a": a, "tipo": tipo,
                             "dati": json.dumps(dati, separators=(",", ":"))})

    def ricevi(self):
        r = self._post("ricevi", {"id": self.id, "segreto": self.segreto}, timeout=20)
        out = []
        for m in r.get("messaggi") or []:
            try:
                out.append({"da": m["da"], "tipo": m["tipo"], "dati": json.loads(m["dati"])})
            except Exception:
                continue
        return out

    def stato(self, ids):
        r = self._post("stato", {"id": self.id, "segreto": self.segreto, "ids": list(ids)})
        return r.get("computer") or {}
