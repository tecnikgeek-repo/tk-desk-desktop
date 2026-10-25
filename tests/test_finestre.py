"""Prove delle finestre di tk-desk senza schermo vero (offscreen) e senza rete: Benvenuto, Licenze, Informazioni,
Impostazioni, Accesso non presidiato (bloccato durante un controllo) e «Accetta / Rifiuta».
Uso: python tests/test_finestre.py
"""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["TKDESK_DATA"] = tempfile.mkdtemp(prefix="tkdesk-finestre-")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from tkdesk import URL_SORGENTE, VERSION, pro, util  # noqa: E402
from tkdesk.prova import CentralinoFinto, Imp  # noqa: E402

FALLITI = []


def prova(nome, fn):
    try:
        fn()
        print(f"  ok  {nome}", flush=True)
    except Exception as exc:
        FALLITI.append(nome)
        print(f"  NO  {nome}: {exc!r}", flush=True)


def gira(secondi):
    fine = time.time() + secondi
    while time.time() < fine:
        QApplication.processEvents()
        time.sleep(0.02)


def main():
    app = QApplication(sys.argv)
    app.licenza = pro.crea_licenza(VERSION)
    from tkdesk import app as finestre
    from tkdesk.kit import righe_benvenuto
    from tkdesk.sessione import Motore
    from tkdesk.tk_licenza_qt import BenvenutoDialog, LicenzeDialog
    app.setStyleSheet(finestre.STYLE_DESK)
    settings = Imp()
    motore = Motore(settings, centralino=CentralinoFinto())
    win = finestre.Principale(settings, motore)
    win.show()
    gira(0.3)

    def niente_rete():
        assert not motore._thread.is_alive(), "il motore (centralino) non deve partire prima del benvenuto"
        assert not win._rete
        assert app.licenza is not None and app.licenza.sbloccato() and not app.licenza.free_pro()
    prova("finestra principale senza rete prima del benvenuto; tutto sbloccato", niente_rete)

    def benvenuto():
        righe = righe_benvenuto("Ufficio <b>Rossi</b>")
        assert any("tecnico, la banca o la polizia" in r for r in righe), "manca l'avviso antitruffa"
        assert any("STUN di Google" in r for r in righe) and any("&lt;b&gt;" in r for r in righe)
        d = BenvenutoDialog(app.licenza, "tk-desk", URL_SORGENTE, win, None, righe)
        d.show()
        gira(0.1)
        assert not d.casella.isChecked(), "statistiche spente di default"
        d.reject()
        assert app.licenza.consenso_statistiche() is False
    prova("benvenuto comune con le righe di tk-desk (antitruffa, rete, STUN)", benvenuto)

    def licenze():
        cartella = util.cartella_licenze()
        assert os.path.isdir(cartella), cartella
        d = LicenzeDialog("tk-desk", VERSION, URL_SORGENTE, cartella, win)
        assert d.elenco.count() >= 1, "nessun testo di licenza"
        d.close()
    prova("finestra Licenze e codice sorgente", licenze)

    def informazioni():
        d = win._informazioni()   # finestra comune della libreria
        testi = " ".join(w.text() for w in d.findChildren(finestre.QLabel)) + " ".join(
            b.text() for b in d.findChildren(finestre.QPushButton))
        assert "AGPL-3.0" in testi and "Licenze e codice sorgente" in testi, testi
        assert "Pro" not in testi.replace("Programma", ""), testi
        d.close()
    prova("Informazioni: «Software libero · AGPL-3.0», licenze, niente Pro", informazioni)

    def impostazioni():
        d = finestre.Impostazioni(win)
        assert not d.appunti.isChecked(), "appunti condivisi spenti di default"
        d.nome.setText("Ufficio Rossi")
        d.appunti.setChecked(True)
        d._salva()
        assert settings.value("nome_computer") == "Ufficio Rossi" and settings.value("appunti") is True
        from tkdesk import centralino as ce
        assert ce.nome_computer(settings) == "Ufficio Rossi"
        settings["appunti"] = False
    prova("Impostazioni: nome del computer, appunti (spenti di default), statistiche", impostazioni)

    def bloccato():
        motore._entrate["123456789"] = object()     # qualcuno sta controllando questo computer
        try:
            d = finestre.NonPresidiato(win)
            assert d.bloccato and not d.p1.isEnabled() and not d.p2.isEnabled()
            d.p1.setEnabled(True)
            d.p2.setEnabled(True)
            d.p1.setText("Passw0rd-lunga")
            d.p2.setText("Passw0rd-lunga")
            d._salva()
            assert "non si può" in d.err.text(), d.err.text()
            assert not motore.ha_password_fissa()
            d.close()
        finally:
            motore._entrate.clear()
        d = finestre.NonPresidiato(win)
        assert not d.bloccato and d.p1.isEnabled()
        d.close()
    prova("Accesso non presidiato bloccato durante un controllo in entrata", bloccato)

    def conferma():
        d = finestre.ConfermaAccesso("123456789", "<b>Tecnico</b>")
        scelte = []
        d.scelta.connect(scelte.append)
        d.show()
        assert not d.b_si.isEnabled() and d.b_no.isDefault(), "Accetta si attiva dopo un secondo, Rifiuta è predefinito"
        gira(1.3)
        assert d.b_si.isEnabled()
        d.b_si.click()
        assert scelte == [True], scelte
        d = finestre.ConfermaAccesso("123456789", "")
        scelte = []
        d.scelta.connect(scelte.append)
        d.show()
        d.resto = 2                                  # nel programma 30 secondi
        gira(2.5)
        assert scelte == [False], f"senza risposta deve rifiutare: {scelte}"
        d = finestre.ConfermaAccesso("123456789", "")
        scelte = []
        d.scelta.connect(scelte.append)
        d.show()
        d.close()                                    # chiusa con la X = rifiutata
        assert scelte == [False], scelte
    prova("finestra «Accetta / Rifiuta»: accetta, scade dopo il tempo, chiusa = rifiuto", conferma)

    def conferma_sopra_modale():
        # bug 1.1.1 (Pietro: «non mi fa cliccare su Accetta»): con una finestra modale aperta (caffè, Impostazioni…)
        # la conferma senza genitore non riceveva i clic. Ora le modali si chiudono prima di mostrarla.
        visto = {}

        def arriva_richiesta():
            visto["modale_prima"] = QApplication.activeModalWidget()
            win._richiesta_accesso("r-prova", "123456789", "Tecnico")
            visto["modale_dopo"] = QApplication.activeModalWidget()

        imp = finestre.Impostazioni(win)
        QTimer.singleShot(300, arriva_richiesta)
        imp.exec()                                   # modale: si chiude da sola quando arriva la richiesta
        assert visto.get("modale_prima") is imp, visto
        assert visto.get("modale_dopo") is None, f"resta una finestra modale che blocca «Accetta»: {visto}"
        d = win._conferme.pop("r-prova", None)
        assert d is not None and d.isVisible(), "la conferma deve essere visibile"
        d.close()
    prova("con una finestra modale aperta la conferma «Accetta» riceve i clic (le modali si chiudono)",
          conferma_sopra_modale)

    print("TUTTO OK" if not FALLITI else f"FALLITE: {FALLITI}", flush=True)
    codice = 1 if FALLITI else 0
    if sys.platform == "win32":
        # con finestre Qt ancora aperte l'uscita normale di Windows (scarico delle DLL) può andare in crash
        # in offscreen anche con la 1.0.9: si chiude il processo di netto, col codice giusto
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        k32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        k32.TerminateProcess(k32.GetCurrentProcess(), codice)
    os._exit(codice)


if __name__ == "__main__":
    main()
