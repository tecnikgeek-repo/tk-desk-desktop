"""Licenza (statistiche col consenso, ricordi del programma) e donazione libera di tk-desk.

Dal 2026-10-25 tk-desk è software libero (AGPL-3.0) con tutte le funzioni per tutti: accesso non presidiato,
rubrica, più sessioni e registrazione non chiedono più nulla. La donazione è libera e non sblocca niente.
Il nome del file resta pro.py per non rompere gli import.
"""
import os
import sys

from PySide6.QtWidgets import QApplication


def cartella_licenza():
    """La licenza sta nella cartella dell'utente, non accanto al programma: tk-desk gira anche da pennetta."""
    if os.environ.get("TKDESK_DATA"):
        base = os.environ["TKDESK_DATA"]
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "tk-desk")


def crea_licenza(versione):
    try:
        from tkdesk.tk_licenza import Licenza
        return Licenza("tk-desk", versione, cartella_licenza())
    except Exception:
        return None


def licenza():
    return getattr(QApplication.instance(), "licenza", None)


def _logo():
    from tkdesk.kit import render_icon
    return render_icon(104)


def invito(parent=None, puo_mostrare=None):
    """Invito al caffè all'avvio: la prima volta e poi al massimo una volta al mese (vedi tk_licenza_qt)."""
    try:
        from tkdesk.tk_licenza_qt import invito_caffe
        invito_caffe(licenza(), "tk-desk", parent, _logo(), puo_mostrare)
    except Exception:
        pass


def pulsante_caffe(nome_oggetto=""):
    from tkdesk.tk_licenza_qt import pulsante_caffe as crea
    return crea(licenza(), nome_oggetto=nome_oggetto)
