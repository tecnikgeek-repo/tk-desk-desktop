"""Pezzi finti per le prove e per il selftest del pacchetto: centralino in memoria e impostazioni in un dizionario.
Con questi due tk-desk si parlano nello stesso processo senza rete (la sessione WebRTC resta vera)."""
import json
import threading

from tkdesk import centralino as ce


class Imp(dict):
    def value(self, k, d=None):
        return self.get(k, d)

    def setValue(self, k, v):
        self[k] = v


class CentralinoFinto:
    cassette = {}
    blocco = threading.Lock()
    numero = 100000000

    def __init__(self, imp=None):
        self.id = ""

    def registra(self):
        with self.blocco:
            CentralinoFinto.numero += 1
            self.id = str(CentralinoFinto.numero)
            self.cassette[self.id] = []
        return self.id

    def invia(self, a, tipo, dati):
        if a not in self.cassette:
            raise ce.ErroreCentralino("Nessun computer con questo ID.", "sconosciuto")
        with self.blocco:
            self.cassette[a].append({"da": self.id, "tipo": tipo, "dati": json.loads(json.dumps(dati))})

    def ricevi(self):
        with self.blocco:
            out, self.cassette[self.id] = self.cassette[self.id], []
        return out

    def stato(self, ids):
        return {i: {"acceso": i in self.cassette, "nome": "", "piattaforma": ""} for i in ids}
