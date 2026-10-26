"""SPAKE2 (RFC 9382) su edwards25519: i due computer si accordano su una chiave segreta partendo dalla password,
senza che dai messaggi si possa ricavare la password.

Prima (fino alla 1.1.x) chi chiamava mandava una firma HMAC fatta con la chiave della password: chi leggeva i
messaggi del centralino poteva provare tutte le monouso di 6 cifre a casa sua (un minuto con una scheda video).
Con SPAKE2 dai messaggi non si ricava niente: ogni tentativo è un tentativo vero verso il computer, e quelli
sono contati e bloccati (sessione.py).

  A = chi chiama (controlla), B = chi è chiamato (controllato), w = chiave della password (centralino.chiave2) mod Q
  A: x casuale, pA = x·G + w·M          B: y casuale, pB = y·G + w·N
  A: K = 8·x·(pB − w·N)                 B: K = 8·y·(pA − w·M)
  TT = A, B, pA, pB, K, w (ognuno con la sua lunghezza su 8 byte) → s = SHA-256(TT)
  conferme: cA = HMAC(HMAC(s, «tk-desk conferma A»), TT), cB = idem con B; sigillo dei messaggi: HMAC(s, «tk-desk messaggi»)

M e N: punti senza logaritmo noto, ricavati da SHA-256(«tk-desk SPAKE2 M|N» + contatore) per 8 (vedi _ricava_punto:
la prova li ricalcola). Gemello in Dart: tk-desk-app/lib/pake.dart (stessi numeri, provato con test/pake_test.dart).
"""
import hashlib
import hmac
import secrets

_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)
_ZERO = (0, 1, 1, 0)

M_HEX = "386914f26c2e1caac68649408df3fbdbf67e3f3b363f0aa1c5293286992596a8"   # _ricava_punto(b"tk-desk SPAKE2 M")
N_HEX = "f63c33fd12a038342e218573ce338c1124caf4664b116b00f5bc280db2e2a3e8"   # _ricava_punto(b"tk-desk SPAKE2 N")


def _somma(a, b):
    x = (a[1] - a[0]) * (b[1] - b[0]) % _P
    y = (a[1] + a[0]) * (b[1] + b[0]) % _P
    c = 2 * a[3] * b[3] * _D % _P
    d = 2 * a[2] * b[2] % _P
    e, f, g, h = y - x, d - c, d + c, y + x
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _per(n, a):
    r = _ZERO
    while n > 0:
        if n & 1:
            r = _somma(r, a)
        a = _somma(a, a)
        n >>= 1
    return r


def _meno(a):
    return (-a[0] % _P, a[1], a[2], -a[3] % _P)


def _x(y, segno):
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)
    if x2 % _P == 0:
        return None if segno else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _I % _P
    if (x * x - x2) % _P:
        return None
    if (x & 1) != segno:
        x = _P - x
    return x


def decodifica(b):
    """32 byte → punto, o None se non è un punto della curva."""
    if len(b) != 32:
        return None
    y = int.from_bytes(b, "little")
    segno = y >> 255
    y &= (1 << 255) - 1
    x = _x(y, segno)
    return None if x is None else (x, y, 1, x * y % _P)


def codifica(p):
    zi = pow(p[2], _P - 2, _P)
    x, y = p[0] * zi % _P, p[1] * zi % _P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


_GY = 4 * pow(5, _P - 2, _P) % _P
G = (_x(_GY, 0), _GY, 1, _x(_GY, 0) * _GY % _P)
_IDENTITA = codifica(_ZERO)


def _ricava_punto(seme):
    """Primo SHA-256(seme + contatore) che è un punto, per 8 (fuori dai sottogruppi piccoli): nessuno ne conosce il logaritmo."""
    for i in range(256):
        p = decodifica(hashlib.sha256(seme + bytes([i])).digest())
        if p is not None:
            p8 = _per(8, p)
            if codifica(p8) != _IDENTITA:
                return codifica(p8)
    raise RuntimeError("nessun punto")


M = decodifica(bytes.fromhex(M_HEX))
N = decodifica(bytes.fromhex(N_HEX))


def _pezzo(b):
    return len(b).to_bytes(8, "little") + b


class ErrorePake(Exception):
    pass


class Spake2:
    """Una parte della stretta di mano. `ruolo` "A" (chi chiama) o "B"; `chiave` = 32 byte da centralino.chiave2."""

    def __init__(self, ruolo, id_a, id_b, chiave, casuale=None):
        if ruolo not in ("A", "B"):
            raise ValueError("ruolo")
        self.ruolo = ruolo
        self.id_a, self.id_b = str(id_a).encode(), str(id_b).encode()
        self.w = int.from_bytes(chiave, "little") % _Q
        self._s = casuale if casuale is not None else secrets.randbelow(_Q - 1) + 1
        mio, self._altro_punto = (M, N) if ruolo == "A" else (N, M)
        self.mio = codifica(_somma(_per(self._s, G), _per(self.w, mio)))
        self._chiavi = None

    def messaggio(self):
        """Da mandare all'altra parte (esadecimale)."""
        return self.mio.hex()

    def finisci(self, altro_hex):
        """Messaggio dell'altra parte → chiavi della sessione. ErrorePake se il messaggio non è valido."""
        try:
            altro = bytes.fromhex(str(altro_hex))
        except ValueError:
            raise ErrorePake("messaggio non valido") from None
        punto = decodifica(altro)
        if punto is None or altro == self.mio or codifica(_per(8, punto)) == _IDENTITA:   # niente punti di ordine piccolo
            raise ErrorePake("messaggio non valido")
        k = _per(self._s, _per(8, _somma(punto, _meno(_per(self.w, self._altro_punto)))))
        kb = codifica(k)
        if kb == _IDENTITA:
            raise ErrorePake("messaggio non valido")
        pa, pb = (self.mio, altro) if self.ruolo == "A" else (altro, self.mio)
        tt = b"".join(_pezzo(x) for x in (self.id_a, self.id_b, pa, pb, kb, self.w.to_bytes(32, "little")))
        s = hashlib.sha256(tt).digest()
        ka = hmac.new(s, b"tk-desk conferma A", hashlib.sha256).digest()
        kb_ = hmac.new(s, b"tk-desk conferma B", hashlib.sha256).digest()
        self._chiavi = {
            "A": hmac.new(ka, tt, hashlib.sha256).hexdigest(),
            "B": hmac.new(kb_, tt, hashlib.sha256).hexdigest(),
            "sigillo": hmac.new(s, b"tk-desk messaggi", hashlib.sha256).digest(),
        }

    def conferma(self):
        """La mia conferma: dimostra all'altro che conosco la password (e che abbiamo la stessa chiave)."""
        return self._chiavi[self.ruolo]

    def conferma_valida(self, c):
        altro = "B" if self.ruolo == "A" else "A"
        return self._chiavi is not None and hmac.compare_digest(self._chiavi[altro], str(c or ""))

    def sigilla(self, etichetta, testo):
        return hmac.new(self._chiavi["sigillo"], f"{etichetta}|".encode() + testo.encode("utf-8"),
                        hashlib.sha256).hexdigest()

    def sigillo_valido(self, etichetta, testo, sigillo):
        return self._chiavi is not None and hmac.compare_digest(self.sigilla(etichetta, testo), str(sigillo or ""))
