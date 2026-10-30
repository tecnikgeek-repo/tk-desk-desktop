"""Finestre di tk-desk: principale (questo computer + controlla un altro), sessione, barra «sei controllato»,
rubrica, accesso non presidiato, icona vicino all'orologio."""
import os
import sys
import threading
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu,
    QPushButton, QScrollArea, QSizePolicy, QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget,
)

from tkdesk import APP_TITLE, URL_SORGENTE, VERSION, centralino as ce, pro, updater, util
from tkdesk.comandi import da_evento_tasto
from tkdesk.kit import (
    ACCENT, ACCENT_2, ACCENT_L, ANTITRUFFA, GRAY_200, GRAY_300, GRAY_400, GRAY_500, GREEN, NAVY, NAVY_2, NAVY_3, RED,
    STYLE, Card, DownloadThread, TkDialog, TkProgress, UpdateDialog, Worker, ic, mini_btn, render_icon,
    righe_benvenuto, shadow, text_btn, tk_choice, tk_info, tk_warn,
)
from tkdesk.sessione import ATTESA_CONFERMA, Motore
from tkdesk.tk_licenza_qt import dentro_lo_schermo, testata_compatta
from tkdesk.util import (
    IS_LINUX, IS_MAC, IS_WIN, Settings, Veglia, avvio_automatico, human_size, is_installed, log_dir,
    nascondi_dalla_cattura, open_path, videos_dir,
)

BLOCCATO = ("Mentre qualcuno controlla questo computer non si può attivare l'accesso non presidiato, la password "
            "fissa o l'avvio con il computer: chiudi prima il collegamento con «Termina».")

STYLE_DESK = STYLE + f"""
QLabel#bigid {{ font-size:34px; font-weight:800; color:{NAVY}; letter-spacing:1px; }}
QLabel#bigpw {{ font-size:26px; font-weight:800; color:{NAVY}; font-family:Consolas, Menlo, 'DejaVu Sans Mono', monospace; letter-spacing:3px; }}
QLabel#pill {{ border-radius:10px; padding:3px 10px; font-size:11px; font-weight:800; color:#fff; }}
QFrame#pwbox {{ background:{ACCENT_L}; border-radius:12px; }}
QFrame#idbox {{ background:#f8fafc; border:1px solid {GRAY_200}; border-radius:12px; }}
QLineEdit#bigin {{ font-size:20px; font-weight:700; min-height:46px; letter-spacing:1px; }}
QPushButton#big {{ min-height:46px; font-size:15px; }}
QFrame#recente {{ background:#f8fafc; border:1px solid {GRAY_200}; border-radius:12px; }}
QFrame#recente:hover {{ border-color:{ACCENT}; }}
QWidget#sessbar {{ background:{NAVY}; }}
QLabel#sesstitle {{ color:#fff; font-size:14px; font-weight:800; }}
QLabel#sesssub {{ color:{GRAY_300}; font-size:11px; }}
QComboBox#schermi {{ background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.14); color:#fff; border-radius:10px; padding:0 10px; min-height:34px; }}
QComboBox#schermi QAbstractItemView {{ background:{NAVY_2}; color:#fff; selection-background-color:{ACCENT}; }}
QPushButton#rec {{ background:rgba(220,38,38,.85); border:0; color:#fff; font-weight:800; }}
QPushButton#voce {{ background:{ACCENT}; border:0; color:#fff; font-weight:800; }}
QFrame#chatbox {{ background:#ffffff; border-left:1px solid {GRAY_200}; }}
QTextEdit#chatlog {{ background:#f8fafc; border:1px solid {GRAY_200}; border-radius:10px; padding:6px; }}
QWidget#banner {{ background:transparent; }}
QFrame#bannercard {{ background:{NAVY}; border-radius:16px; border:1px solid {NAVY_3}; }}
QLabel#bannertxt {{ color:#fff; font-weight:700; }}
QLabel#recpill {{ background:{RED}; color:#fff; border-radius:9px; padding:2px 8px; font-size:11px; font-weight:800; }}
QLabel#truffa {{ background:#fef3c7; color:#92400e; border-radius:10px; padding:8px 10px; font-size:12px; font-weight:600; }}
QLabel#tentativi {{ color:{RED}; font-size:12px; font-weight:700; }}
"""


def pill(testo, colore):
    lab = QLabel(testo.upper())
    lab.setObjectName("pill")
    lab.setStyleSheet(f"background:{colore};")
    return lab


def copia(testo):
    QApplication.clipboard().setText(testo)


# ───────────────────────────────────────────── chat (sessione e barra del controllato)
class Chat(QFrame):
    invia = Signal(str)

    def __init__(self, titolo="CHAT"):
        super().__init__()
        self.setObjectName("chatbox")
        self.setFixedWidth(300)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)
        lay.addWidget(QLabel(titolo, objectName="cardtitle"))
        self.log = QTextEdit(objectName="chatlog")
        self.log.setReadOnly(True)
        lay.addWidget(self.log, 1)
        riga = QHBoxLayout()
        self.campo = QLineEdit()
        self.campo.setPlaceholderText("Scrivi un messaggio…")
        self.campo.returnPressed.connect(self._manda)
        riga.addWidget(self.campo, 1)
        riga.addWidget(mini_btn("chat", "Invia", self._manda, ACCENT))
        lay.addLayout(riga)

    def _manda(self):
        t = self.campo.text().strip()
        if t:
            self.invia.emit(t)
            self.aggiungi("Tu", t)
            self.campo.clear()

    def aggiungi(self, chi, testo):
        import html
        ora = time.strftime("%H:%M")
        col = ACCENT if chi == "Tu" else NAVY
        self.log.append(f'<span style="color:{GRAY_500};font-size:11px">{ora}</span> '
                        f'<b style="color:{col}">{html.escape(chi)}</b><br>{html.escape(testo)}<br>')


# ───────────────────────────────────────────── schermo remoto
class Video(QWidget):
    """Mostra lo schermo dell'altro computer e manda mouse e tastiera."""
    comando = Signal(dict)
    file_trascinati = Signal(list)

    def __init__(self):
        super().__init__()
        self.img = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self.setMinimumSize(320, 200)
        self._mossa = None
        self._ultima = None
        self.timer = QTimer(self, interval=16, timeout=self._manda_mossa)
        self.timer.start()
        self.messaggio = "Collegamento in corso…"
        self.trascino = False
        self.remoto = None      # posizione 0..1 del puntatore dell'altro computer
        # la tua freccia resta (Pietro: «deve apparire il mio cursore che prende il controllo del suo»);
        # quella dell'altro computer è disegnata sul video e la segue
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def mostra(self, dati, w, h):
        self.img = QImage(dati, w, h, w * 3, QImage.Format.Format_RGB888).copy()
        self.messaggio = ""
        self.update()

    def _rett(self):
        if self.img is None:
            return QRectF()
        W, H = self.width(), self.height()
        s = min(W / self.img.width(), H / self.img.height())
        w, h = self.img.width() * s, self.img.height() * s
        return QRectF((W - w) / 2, (H - h) / 2, w, h)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0b1220"))
        if self.img is not None:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(self._rett(), self.img)
            if self.remoto:
                r = self._rett()
                x, y = r.x() + self.remoto[0] * r.width(), r.y() + self.remoto[1] * r.height()
                from PySide6.QtGui import QPainterPath
                freccia = QPainterPath(QPointF(x, y))
                for dx, dy in ((0, 17), (4.5, 12.8), (7.5, 19.5), (10.5, 18.2), (7.6, 11.6), (13, 11.6)):
                    freccia.lineTo(QPointF(x + dx, y + dy))
                freccia.closeSubpath()
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                from PySide6.QtGui import QPen
                p.setPen(QPen(QColor("#ffffff"), 1.4))
                p.setBrush(QColor("#0f172a"))
                p.drawPath(freccia)
        if self.trascino:
            p.fillRect(self.rect(), QColor(5, 150, 105, 150))
            p.setPen(QColor("#ffffff"))
            f = QFont(self.font())
            f.setPointSize(16)
            f.setBold(True)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                       "Rilascia qui: i file vanno sulla Scrivania dell'altro computer")
        if self.messaggio:
            p.setPen(QColor("#e2e8f0"))
            f = QFont(self.font())
            f.setPointSize(13)
            f.setBold(True)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.messaggio)
        p.end()

    def _norm(self, pos):
        r = self._rett()
        if r.isEmpty():
            return None
        return (min(max((pos.x() - r.x()) / r.width(), 0.0), 1.0), min(max((pos.y() - r.y()) / r.height(), 0.0), 1.0))

    def mouseMoveEvent(self, e):
        n = self._norm(e.position())
        if n:
            self._mossa = n

    def _manda_mossa(self):
        if self._mossa and self._mossa != self._ultima:
            self._ultima = self._mossa
            self.comando.emit({"t": "mm", "x": round(self._mossa[0], 5), "y": round(self._mossa[1], 5)})

    def _tasto_mouse(self, e, giu):
        b = {Qt.MouseButton.LeftButton: "l", Qt.MouseButton.RightButton: "r", Qt.MouseButton.MiddleButton: "m"}.get(e.button())
        n = self._norm(e.position())
        if b and n:
            self.comando.emit({"t": "mb", "b": b, "d": 1 if giu else 0, "x": round(n[0], 5), "y": round(n[1], 5)})

    def mousePressEvent(self, e):
        self.setFocus()
        self._tasto_mouse(e, True)

    def mouseReleaseEvent(self, e):
        self._tasto_mouse(e, False)

    def mouseDoubleClickEvent(self, e):
        # il doppio clic arriva come pressione: il sistema dall'altra parte lo riconosce da solo
        self._tasto_mouse(e, True)

    def wheelEvent(self, e):
        d = e.angleDelta()
        dy, dx = round(d.y() / 120), round(d.x() / 120)
        if dy or dx:
            self.comando.emit({"t": "mw", "dx": dx, "dy": dy})

    def keyPressEvent(self, e):
        m = da_evento_tasto(e, True)
        if m:
            self.comando.emit(m)

    def keyReleaseEvent(self, e):
        m = da_evento_tasto(e, False)
        if m:
            self.comando.emit(m)

    def focusNextPrevChild(self, _):
        return False  # il Tab va all'altro computer, non al pulsante successivo

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.trascino = True
            self.update()

    def dragLeaveEvent(self, e):
        self.trascino = False
        self.update()

    def dropEvent(self, e):
        self.trascino = False
        self.update()
        file = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile() and os.path.isfile(u.toLocalFile())]
        if file:
            e.acceptProposedAction()
            self.file_trascinati.emit(file)


class Sessione(QMainWindow):
    """Finestra di una sessione: barra in alto, schermo remoto, chat a destra."""

    def __init__(self, principale, chiave, id_remoto, nome=""):
        super().__init__()
        self.p = principale
        self.m = principale.motore
        self.chiave = chiave
        self.id_remoto = id_remoto
        self.nome = nome
        self.aperta = False
        self.registrando = False
        self.setWindowTitle(f"{nome or ce.formatta_id(id_remoto)} · {APP_TITLE}")
        self.setWindowIcon(QIcon(render_icon(128)))
        corpo = QWidget()
        v = QVBoxLayout(corpo)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        barra = QWidget(objectName="sessbar")
        b = QHBoxLayout(barra)
        b.setContentsMargins(12, 8, 12, 8)
        b.setSpacing(8)
        logo = QLabel()
        logo.setPixmap(render_icon(32))
        b.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.titolo = QLabel(nome or ce.formatta_id(id_remoto), objectName="sesstitle")
        self.titolo.setTextFormat(Qt.TextFormat.PlainText)   # il nome lo sceglie l'altro computer
        self.sotto = QLabel(f"ID {ce.formatta_id(id_remoto)}", objectName="sesssub")
        col.addWidget(self.titolo)
        col.addWidget(self.sotto)
        b.addLayout(col)
        b.addStretch(1)
        self.schermi = QComboBox(objectName="schermi")
        self.schermi.setToolTip("Schermo dell'altro computer")
        self.schermi.hide()
        self.schermi.activated.connect(lambda i: self.m.manda(self.chiave, {"t": "schermo", "i": i}))
        b.addWidget(self.schermi)
        self.b_file = text_btn("file", "Invia file", self._scegli_file, "#fff", "ghost", "Manda un file all'altro computer (o trascinalo sullo schermo)")
        self.b_chat = text_btn("chat", "Chat", self._chat, "#fff", "ghost", "Scrivi all'altro computer")
        self.b_voce = text_btn("phone", "Chiamata", self._voce, "#fff", "ghost", "Parla con l'altra persona (microfono e altoparlanti)")
        self.voce = ""
        self.b_rec = text_btn("record", "Registra", self._registra, "#fff", "ghost",
                              "Salva la sessione in un video (l'altra persona vede «REC»)")
        self.b_full = text_btn("full", "", self._schermo_intero, "#fff", "ghost", "Schermo intero")
        self.b_chiudi = text_btn("close", "Chiudi", self.close, "#fff", "ghost", "Chiudi la sessione")
        for w in (self.b_file, self.b_chat, self.b_voce, self.b_rec, self.b_full, self.b_chiudi):
            b.addWidget(w)
        v.addWidget(barra)
        riga = QHBoxLayout()
        riga.setSpacing(0)
        self.video = Video()
        self.video.comando.connect(lambda d: self.m.manda(self.chiave, d))
        self.video.file_trascinati.connect(self._manda_file)
        riga.addWidget(self.video, 1)
        self.chat = Chat()
        self.chat.invia.connect(lambda t: self.m.manda(self.chiave, {"t": "chat", "s": t}))
        self.chat.hide()
        riga.addWidget(self.chat)
        v.addLayout(riga, 1)
        self.setCentralWidget(corpo)
        self.stato = QLabel("")
        self.statusBar().addWidget(self.stato, 1)
        self.setMinimumWidth(700)
        testata_compatta(self, [(self.b_file, ""), (self.b_chat, ""), (self.b_voce, ""), (self.b_rec, ""),
                                (self.b_chiudi, "")], 1150)
        dentro_lo_schermo(self, 1280, 820)

    # dal motore
    def fotogramma(self, dati, w, h):
        self.video.mostra(dati, w, h)
        self.m.disegnato(self.chiave)

    def cursore(self, x, y):
        self.video.remoto = (x, y) if x >= 0 else None
        self.video.update()

    def _avviso(self, testo):
        self.stato.setText(testo)
        self.stato.setStyleSheet(f"color:{RED}; font-weight:700;")

    def stato_chiamata(self, testo):
        if testo.startswith("avviso:"):
            self._avviso(testo[7:])
            return
        if testo == "schermi":
            self._schermi(self.m.info(self.chiave))
        elif not self.aperta:
            self.video.messaggio = testo
            self.video.update()

    def apri(self, info):
        self.aperta = True
        nome = info.get("nome") or self.nome
        if nome:
            self.titolo.setText(nome)
            self.setWindowTitle(f"{nome} · {APP_TITLE}")
        sistema = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}.get(info.get("piattaforma"), "")
        self.sotto.setText(f"ID {ce.formatta_id(self.id_remoto)}" + (f" · {sistema}" if sistema else ""))
        self._schermi(info)
        manca = [n for k, n in (("accesso", "Accessibilità (mouse e tastiera)"), ("schermo", "Registrazione schermo"))
                 if (info.get("permessi") or {}).get(k) is False]
        if manca:
            self._avviso("Sull'altro computer manca il permesso " + " e ".join(manca)
                         + ": chi è davanti deve concederlo (tk-desk gli mostra come).")
        self.video.messaggio = "In attesa dello schermo…"
        self.video.setFocus()
        self.p.ricorda_recente(self.id_remoto, nome)

    def _schermi(self, info):
        schermi = info.get("schermi") or []
        self.schermi.clear()
        for i, s in enumerate(schermi):
            self.schermi.addItem(f"Schermo {i + 1} · {s['width']}×{s['height']}")
        self.schermi.setCurrentIndex(int(info.get("attivo") or 0))
        self.schermi.setVisible(len(schermi) > 1)

    def chiusa(self, motivo):
        if self.registrando:
            self.registrando = False
        if not self.aperta:
            self.video.messaggio = motivo
            self.video.update()
            self.stato.setText(motivo)
            self.aperta = None
            return
        self.aperta = None
        tk_info(self, APP_TITLE, motivo or "Sessione chiusa.")
        self.close()

    def chat_ricevuta(self, testo):
        self.chat.show()
        self.chat.aggiungi(self.titolo.text(), testo)
        QApplication.alert(self)

    def file_ricevuto(self, percorso):
        self.stato.setText(f"File ricevuto, è sulla tua Scrivania: {os.path.basename(percorso)}")

    def avanzamento(self, nome, fatti, totale):
        if fatti >= totale:
            self.stato.setText(f"«{nome}» inviato ({human_size(totale)}): se l'altra persona lo accetta, lo trova "
                               f"sulla sua Scrivania.")
        else:
            self.stato.setText(f"Invio «{nome}»: {human_size(fatti)} di {human_size(totale)}")

    def registrazione(self, percorso):
        if percorso:
            self.registrando = True
            self.b_rec.setObjectName("rec")
            self.b_rec.setText("Ferma")
            self.stato.setText(f"Registrazione in corso: {percorso}")
        else:
            self.registrando = False
            self.b_rec.setObjectName("ghost")
            self.b_rec.setText("Registra")
            self.stato.setText("Registrazione salvata nella cartella Video/tk-desk.")
        self.b_rec.style().unpolish(self.b_rec)
        self.b_rec.style().polish(self.b_rec)

    # azioni
    def _scegli_file(self):
        if not self.aperta:
            return
        file, _ = QFileDialog.getOpenFileNames(self, "File da mandare all'altro computer")
        self._manda_file(file)

    def _manda_file(self, file):
        for f in file:
            self.m.manda_file(self.chiave, f)

    def _voce(self):
        if not self.aperta:
            return
        if self.voce:
            self.m.voce(self.chiave, False)
        else:
            self.m.voce(self.chiave, True)
            self.voce_stato("chiamo", "")

    def voce_stato(self, stato, avviso):
        self.voce = "" if stato in ("chiusa", "rifiutata") else stato
        testi = {"chiamo": "Chiamo…", "attiva": "Riaggancia"}
        self.b_voce.setText(testi.get(self.voce, "Chiamata"))
        self.b_voce.setObjectName("rec" if self.voce == "attiva" else "voce" if self.voce else "ghost")
        self.b_voce.style().unpolish(self.b_voce)
        self.b_voce.style().polish(self.b_voce)
        if stato == "attiva":
            self.stato.setText("Chiamata vocale attiva." + (f" Attenzione: {avviso}" if avviso else ""))
        elif stato == "rifiutata":
            self.stato.setText("L'altra persona non ha accettato la chiamata.")
        elif stato == "chiusa":
            self.stato.setText("Chiamata vocale chiusa.")
        elif stato == "chiamo":
            self.stato.setText("Chiamata in corso: aspetto che l'altra persona risponda…")

    def voce_chiesta(self):
        QApplication.alert(self)
        scelta = tk_choice(self, "Chiamata vocale", f"{self.titolo.text()} vuole parlare con te.",
                           [("Rifiuta", "ghost"), ("Rispondi", "accent")], "ask")
        self.m.voce(self.chiave, scelta == 1)
        if scelta == 1:
            self.voce_stato("chiamo", "")

    def _chat(self):
        self.chat.setVisible(not self.chat.isVisible())
        if self.chat.isVisible():
            self.chat.campo.setFocus()

    def _registra(self):
        if not self.aperta:
            return
        if self.registrando:
            self.m.registra(self.chiave, "")
            return
        nome = f"tk-desk {self.id_remoto} {time.strftime('%Y-%m-%d %H.%M')}.mp4"
        self.m.registra(self.chiave, os.path.join(videos_dir(), nome))

    def _schermo_intero(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
        self.video.setFocus()

    def changeEvent(self, e):
        # appunti con più sessioni: vanno solo verso quella in primo piano (l'ultima finestra attiva)
        if e.type() == e.Type.ActivationChange and self.isActiveWindow():
            self.p.sessione_attiva = self.chiave
        super().changeEvent(e)

    def closeEvent(self, e):
        if self.aperta is not None:
            self.m.chiudi(self.chiave)
        self.p.sessione_finestra_chiusa(self.chiave)
        e.accept()


# ───────────────────────────────────────────── barra di chi è controllato
class Barra(QWidget):
    """In alto al centro dello schermo finché qualcuno controlla questo computer: chi è, chat, Termina.
    Si sposta trascinandola (dalla maniglia o da un punto senza pulsanti) e si riduce a una pillola con «—»;
    «Termina» resta sempre visibile. Finché non la sposti resta centrata sullo schermo di tk-desk."""
    termina = Signal()
    chat = Signal()
    file = Signal(list)
    voce = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("banner")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        out = QVBoxLayout(self)
        out.setContentsMargins(14, 8, 14, 18)
        card = QFrame(objectName="bannercard")
        shadow(card, 30, 6, 90)
        out.addWidget(card)
        riga = QHBoxLayout(card)
        riga.setContentsMargins(8, 8, 10, 8)
        riga.setSpacing(10)
        maniglia = QLabel("⠿")
        maniglia.setToolTip("Trascina per spostare la barra")
        maniglia.setStyleSheet("color:#94a3b8; font-size:18px; padding:0 2px;")
        maniglia.setCursor(Qt.CursorShape.SizeAllCursor)
        riga.addWidget(maniglia)
        punto = QLabel()
        punto.setPixmap(ic("dot", "#f87171", 14).pixmap(14, 14))
        riga.addWidget(punto)
        # barra intera
        self.pieno = QWidget()
        h = QHBoxLayout(self.pieno)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        riga.addWidget(self.pieno)
        # barra ridotta: solo «Controllato», Apri e Termina
        self.ridotto = QWidget()
        hr = QHBoxLayout(self.ridotto)
        hr.setContentsMargins(0, 0, 0, 0)
        hr.setSpacing(8)
        corto = QLabel("Controllato", objectName="bannertxt")
        hr.addWidget(corto)
        hr.addWidget(text_btn("full", "Apri", lambda: self._riduci(False), "#fff", "ghost", "Mostra la barra intera"))
        hr.addWidget(text_btn("power", "Termina", self.termina.emit, "#fff", "accent", "Chiudi il collegamento adesso"))
        self.ridotto.hide()
        riga.addWidget(self.ridotto)
        self._trascino = None
        self._spostata = False
        self.testo = QLabel("", objectName="bannertxt")
        self.testo.setTextFormat(Qt.TextFormat.PlainText)   # c'è il nome scelto dall'altro computer
        self.testo.setToolTip("Trascina qui dei file per mandarli a chi ti assiste")
        h.addWidget(self.testo)
        self.p_rec = QLabel("REC", objectName="recpill")
        self.p_rec.setToolTip("Chi ti assiste sta registrando lo schermo in un video")
        self.p_rec.hide()
        h.addWidget(self.p_rec)
        h.addWidget(text_btn("chat", "Chat", self.chat.emit, "#fff", "ghost"))
        self.b_voce = text_btn("phone", "Chiamata", self.voce.emit, "#fff", "ghost", "Parla con chi ti assiste")
        h.addWidget(self.b_voce)
        h.addWidget(text_btn("file", "Invia file", self._scegli, "#fff", "ghost", "Manda file a chi ti assiste (o trascinali qui)"))
        self.setAcceptDrops(True)
        h.addWidget(text_btn("power", "Termina", self.termina.emit, "#fff", "accent", "Chiudi il collegamento adesso"))
        h.addWidget(text_btn("", "—", lambda: self._riduci(True), "#fff", "ghost", "Riduci la barra"))

    # ── spostare e ridurre
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._trascino = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._trascino is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._trascino)
            self._spostata = True

    def mouseReleaseEvent(self, e):
        self._trascino = None

    def _riduci(self, si):
        centro = self.frameGeometry().center().x()
        self.pieno.setVisible(not si)
        self.ridotto.setVisible(si)
        self._adatta(centro)

    def _schermo(self):
        """Lo schermo dove c'è la finestra di tk-desk (con più schermi), altrimenti il principale."""
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QMainWindow) and w.isVisible() and w.screen() is not None:
                return w.screen()
        return QApplication.primaryScreen()

    def _adatta(self, centro=None):
        """Dopo un cambio di larghezza: centrata in alto finché non l'hai spostata, altrimenti resta dove l'hai
        messa (con lo stesso centro, se si riduce o si allarga)."""
        self.layout().activate()
        self.adjustSize()
        if not self._spostata:
            geo = self._schermo().availableGeometry()
            self.move(geo.center().x() - self.width() // 2, geo.top())
        elif centro is not None:
            self.move(centro - self.width() // 2, self.y())

    def _scegli(self):
        file, _ = QFileDialog.getOpenFileNames(None, "File da mandare a chi ti assiste")
        if file:
            self.file.emit(file)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        file = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile() and os.path.isfile(u.toLocalFile())]
        if file:
            e.acceptProposedAction()
            self.file.emit(file)

    def voce_stato(self, stato):
        testi = {"chiamo": "Chiamo…", "attiva": "Riaggancia"}
        self.b_voce.setText(testi.get(stato, "Chiamata"))
        self.b_voce.setObjectName("rec" if stato == "attiva" else "voce" if stato == "chiamo" else "ghost")
        self.b_voce.style().unpolish(self.b_voce)
        self.b_voce.style().polish(self.b_voce)
        self._adatta(self.frameGeometry().center().x())

    def showEvent(self, e):
        super().showEvent(e)
        nascondi_dalla_cattura(self)

    def rec(self, acceso):
        self.p_rec.setVisible(bool(acceso))
        self._adatta(self.frameGeometry().center().x())

    def mostra(self, testo):
        """A ogni nuovo controllo la barra torna intera e centrata."""
        self.testo.setText(testo)
        self._spostata = False
        self.pieno.show()
        self.ridotto.hide()
        self.show()
        self._adatta()
        self.raise_()
        # la larghezza vera si sa solo dopo il primo disegno: si ricentra un attimo dopo
        QTimer.singleShot(50, lambda: self.isVisible() and self._adatta())


class ChatControllato(TkDialog):
    """Chat dal lato di chi è controllato (non modale: si può continuare a lavorare)."""

    def __init__(self, parent, titolo):
        super().__init__(parent, 340)
        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.head(render_icon(40), "Chat", titolo)
        self.chat = Chat("MESSAGGI")
        self.chat.setFixedWidth(300)
        self.chat.setFixedHeight(320)
        self.body.addWidget(self.chat)
        self.body.addWidget(text_btn("", "Chiudi", self.hide))


class ConfermaAccesso(TkDialog):
    """«… vuole controllare questo computer — Accetta / Rifiuta», in primo piano. Senza risposta in
    ATTESA_CONFERMA secondi vale come rifiuto. «Rifiuta» è il pulsante predefinito e «Accetta» si attiva dopo un
    secondo: un Invio o un clic dato per caso non apre il computer."""
    scelta = Signal(bool)

    def __init__(self, id_, nome):
        super().__init__(None, 480)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setModal(False)
        self.deciso = False
        chi = f"Il computer {ce.formatta_id(id_)}" + (f" («{nome}»)" if nome else "")
        self.head(ic("alert", "#fbbf24", 40).pixmap(44, 44), "Richiesta di controllo",
                  "Qualcuno ha scritto il tuo ID e la tua password monouso.")
        t = QLabel(f"{chi} vuole controllare questo computer: vedrà lo schermo e userà mouse e tastiera.")
        t.setTextFormat(Qt.TextFormat.PlainText)
        t.setWordWrap(True)
        t.setStyleSheet("font-size:14px; color:#e2e8f0;")
        self.body.addWidget(t)
        avviso = QLabel(ANTITRUFFA)
        avviso.setWordWrap(True)
        avviso.setStyleSheet("background:#fef3c7; color:#92400e; border-radius:10px; padding:8px 10px; "
                             "font-size:13px; font-weight:700;")
        self.body.addWidget(avviso)
        self.resto = ATTESA_CONFERMA
        self.conto = QLabel("")
        self.conto.setObjectName("asub")
        self.body.addWidget(self.conto)
        riga = QHBoxLayout()
        riga.addStretch(1)
        self.b_no = text_btn("close", "Rifiuta", lambda: self._decidi(False), "#fff", "ghost")
        self.b_si = text_btn("check", "Accetta", lambda: self._decidi(True), "#fff", "accent")
        self.b_si.setEnabled(False)
        self.b_si.setAutoDefault(False)
        self.b_no.setDefault(True)
        riga.addWidget(self.b_no)
        riga.addWidget(self.b_si)
        self.body.addLayout(riga)
        self._timer = QTimer(self, interval=1000, timeout=self._passa)
        self._timer.start()
        QTimer.singleShot(1000, lambda: self.b_si.setEnabled(True))
        self._passa(primo=True)

    def _passa(self, primo=False):
        if not primo:
            self.resto -= 1
        if self.resto <= 0:
            return self._decidi(False)
        self.conto.setText(f"Se non rispondi, tra {self.resto} secondi la richiesta viene rifiutata.")

    def _decidi(self, si):
        if self.deciso:
            return
        self.deciso = True
        self._timer.stop()
        # prima sparisce (chi clicca vede subito che è stato preso), poi la scelta: se quello che parte con
        # «Accetta» si blocca o dà errore, la finestra non resta comunque aperta (1.1.3: restava visibile)
        self.hide()
        try:
            self.scelta.emit(bool(si))
        finally:
            self._via()

    def chiudi(self):
        """Richiesta scaduta o decisa altrove: si chiude senza scegliere."""
        self.deciso = True
        self._timer.stop()
        self._via()

    def _via(self):
        self.hide()
        self.done(0)
        self.deleteLater()

    def closeEvent(self, e):
        if not self.deciso:          # chiusa con Esc o Alt+F4 = rifiutata
            self.deciso = True
            self._timer.stop()
            self.scelta.emit(False)
        super().closeEvent(e)

    def reject(self):
        self.close()


# ───────────────────────────────────────────── finestre di impostazione
class PermessiMac(TkDialog):
    """Mac: i due permessi che servono per essere controllati, passo per passo, con i pulsanti che aprono la voce
    giusta. Da Impostazioni si apre anche con i permessi già concessi (tutte e due le voci, con lo stato)."""

    PASSI = ("1. Premi «Apri l'impostazione» (oppure: menu Apple, la mela in alto a sinistra → Impostazioni di "
             "Sistema → Privacy e sicurezza).\n"
             "2. Accendi l'interruttore accanto a tk-desk. Se non c'è, premi «+» in fondo all'elenco e scegli "
             "tk-desk dalla cartella Applicazioni.\n"
             "3. Conferma con la password del Mac (o con il dito sul Touch ID).\n"
             "4. Premi «Riapri tk-desk»: il Mac fa valere i permessi solo dopo la riapertura.")

    def __init__(self, win, schermo, accesso, tutte=False):
        super().__init__(win, 500)
        from tkdesk.util import apri_impostazioni_mac
        ok = schermo and accesso
        self.head(ic("check" if ok else "alert", "#6ee7b7" if ok else "#fbbf24", 40).pixmap(44, 44),
                  "Due permessi per farti aiutare",
                  "Servono solo se altri devono controllare questo Mac. Per controllare un altro computer no.")
        righe = []
        if tutte or not schermo:
            righe.append(("REGISTRAZIONE SCHERMO", schermo, "Senza, chi ti aiuta vede solo lo sfondo della scrivania. "
                          "Sui Mac più nuovi la voce si chiama «Registrazione schermo e audio di sistema».", "schermo"))
        if tutte or not accesso:
            righe.append(("ACCESSIBILITÀ (MOUSE E TASTIERA)", accesso,
                          "Senza, chi ti aiuta vede lo schermo ma non può usare mouse e tastiera.", "accessibilita"))
        for titolo, concesso, testo, quale in righe:
            card = QFrame(objectName="acard")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 12)
            cl.addWidget(QLabel(titolo + ("  ·  CONCESSO" if concesso else ""), objectName="atitle"))
            lab = QLabel("Tutto OK: tk-desk ha questo permesso." if concesso else testo)
            lab.setWordWrap(True)
            cl.addWidget(lab)
            if not concesso:
                cl.addWidget(text_btn("gear", "Apri l'impostazione",
                                      lambda _=False, q=quale: apri_impostazioni_mac(q), "#fff", "accent"))
            self.body.addWidget(card)
        if not ok:
            card = QFrame(objectName="acard")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 12)
            cl.addWidget(QLabel("COME SI FA", objectName="atitle"))
            lab = QLabel(self.PASSI)
            lab.setWordWrap(True)
            cl.addWidget(lab)
            self.body.addWidget(card)
        nota = QLabel("Se nelle Impostazioni tk-desk risulta già acceso ma qui manca (succede dopo un aggiornamento), "
                      "premi «Ripristina i permessi», concedili di nuovo e tk-desk si riapre da solo.")
        nota.setObjectName("asub")
        nota.setWordWrap(True)
        self.body.addWidget(nota)
        self.err = QLabel("", objectName="err")
        self.err.setWordWrap(True)
        self.body.addWidget(self.err)
        riga0 = QHBoxLayout()
        riga0.addWidget(text_btn("refresh", "Ripristina i permessi", self._ripristina, "#fff", "ghost"))
        riga0.addStretch(1)
        if not ok:
            riga0.addWidget(text_btn("refresh", "Riapri tk-desk", self._riapri, "#fff", "accent"))
        self.body.addLayout(riga0)
        self.mai = False
        riga = QHBoxLayout()
        if not tutte:
            riga.addWidget(text_btn("", "Non chiedere più", lambda: (setattr(self, "mai", True), self.accept()),
                                    "#fff", "ghost"))
        riga.addStretch(1)
        riga.addWidget(text_btn("", "Chiudi" if tutte else "Più tardi", self.accept, "#fff", "ghost"))
        self.body.addLayout(riga)

    def _riapri(self):
        from tkdesk.util import riavvia
        riavvia()
        win = self.parent()
        if win is not None:
            win.uscita = True
            QTimer.singleShot(300, win.close)
        self.accept()


def _ripristina_e_riavvia(dlg):
    from tkdesk.util import mac_ripristina_permessi
    errore = mac_ripristina_permessi()
    if errore:
        dlg.err.setText("Non sono riuscito a togliere le voci vecchie: toglile tu con «−» nelle Impostazioni. " + errore)
        return
    dlg.err.setText("")
    scelta = tk_choice(dlg, "Permessi richiesti", "Concedi a tk-desk «Registrazione schermo» e «Accessibilità» nelle "
                                                  "finestre del Mac, poi premi «Riapri tk-desk».",
                       [("Più tardi", "ghost"), ("Riapri tk-desk", "accent")], "ask")
    if scelta == 1:
        from tkdesk.util import riavvia
        riavvia()
        win = dlg.parent()
        if win is not None:
            win.uscita = True
            QTimer.singleShot(300, win.close)
    dlg.accept()


PermessiMac._ripristina = lambda self: _ripristina_e_riavvia(self)


class NonPresidiato(TkDialog):
    """Accesso non presidiato: password fissa e avvio con il computer."""

    def __init__(self, win):
        super().__init__(win, 480)
        self.win = win
        self.head(ic("key", "#6ee7b7", 40).pixmap(44, 44), "Accesso non presidiato",
                  "Per entrare in questo computer anche quando non c'è nessuno davanti.")
        lab = QLabel("Scegli una password fissa (almeno 8 caratteri). Chi la conosce entra in questo computer SENZA "
                     "che nessuno debba premere «Accetta»: dalla solo a chi ti fidi, mai a chi ti telefona.")
        lab.setWordWrap(True)
        lab.setObjectName("asub")
        self.body.addWidget(lab)
        self.bloccato = win.motore.controllo_in_corso()
        if self.bloccato:
            avviso = QLabel(BLOCCATO)
            avviso.setWordWrap(True)
            avviso.setObjectName("err")
            self.body.addWidget(avviso)
        self.p1 = QLineEdit()
        self.p1.setEchoMode(QLineEdit.EchoMode.Password)
        self.p1.setPlaceholderText("Password fissa")
        self.p2 = QLineEdit()
        self.p2.setEchoMode(QLineEdit.EchoMode.Password)
        self.p2.setPlaceholderText("Ripeti la password")
        self.body.addWidget(self.p1)
        self.body.addWidget(self.p2)
        self.avvio = QCheckBox("Avvia tk-desk con il computer (resta vicino all'orologio)")
        self.avvio.setStyleSheet("color:#e2e8f0;")
        try:
            self.avvio.setChecked(avvio_automatico())
        except Exception:
            self.avvio.setEnabled(False)
        if not is_installed():
            self.avvio.setEnabled(False)
        self.body.addWidget(self.avvio)
        self.err = QLabel("", objectName="err")
        self.err.setWordWrap(True)
        self.body.addWidget(self.err)
        stato = "attiva" if win.motore.ha_password_fissa() else "non impostata"
        if win.motore.ha_password_fissa() and win.motore._chiave_fissa()[0] != 2:
            stato += " (impostata con una versione di prima: scrivila di nuovo qui sopra per la protezione più forte)"
        info = QLabel(f"Password fissa: {stato}.")
        info.setObjectName("asub")
        info.setWordWrap(True)
        self.body.addWidget(info)
        if self.bloccato:
            for w in (self.p1, self.p2):
                w.setEnabled(False)
            if not self.avvio.isChecked():
                self.avvio.setEnabled(False)
        riga = QHBoxLayout()
        if win.motore.ha_password_fissa():
            riga.addWidget(text_btn("trash", "Togli la password fissa", self._togli, "#fff", "ghost"))
        riga.addStretch(1)
        riga.addWidget(text_btn("", "Annulla", self.reject, "#fff", "ghost"))
        riga.addWidget(text_btn("check", "Salva", self._salva, "#fff", "accent"))
        self.body.addLayout(riga)

    def _salva(self):
        a, b = self.p1.text(), self.p2.text()
        accende_avvio = self.avvio.isEnabled() and self.avvio.isChecked() and not Principale._avvio()
        # si ricontrolla al clic: la finestra può essere stata aperta prima che iniziasse il controllo
        if (a or b or accende_avvio) and self.win.motore.controllo_in_corso():
            self.err.setText(BLOCCATO)
            return
        if a or b:
            if len(a) < 8:
                self.err.setText("La password fissa deve avere almeno 8 caratteri.")
                return
            if a != b:
                self.err.setText("Le due password non sono uguali.")
                return
            try:
                self.win.motore.imposta_password_fissa(a)
            except RuntimeError as exc:
                self.err.setText(str(exc))
                return
        try:
            if self.avvio.isEnabled() and self.avvio.isChecked() != avvio_automatico():
                avvio_automatico(self.avvio.isChecked())
        except Exception as exc:
            self.err.setText(f"Non riesco a impostare l'avvio con il computer: {exc}")
            return
        self.win.aggiorna_stato()
        self.accept()

    def _togli(self):
        self.win.motore.imposta_password_fissa("")
        self.win.aggiorna_stato()
        self.accept()


class Rubrica(TkDialog):
    """Rubrica dei computer: nome, ID, acceso/spento, collegamento con un clic. La password fissa non si salva:
    si salva la chiave ricavata, cifrata (DPAPI su Windows, Portachiavi sul Mac, portachiavi del sistema su Linux)."""

    def __init__(self, win):
        super().__init__(win, 560)
        self.win = win
        self.head(ic("book", "#6ee7b7", 40).pixmap(44, 44), "Rubrica dei computer",
                  "I computer che controlli spesso. Il punto verde dice quali sono accesi adesso.")
        self.lista = QVBoxLayout()
        self.lista.setSpacing(6)
        box = QWidget()
        box.setLayout(self.lista)
        scorri = QScrollArea()
        scorri.setWidgetResizable(True)
        scorri.setWidget(box)
        scorri.setFixedHeight(300)
        scorri.setStyleSheet("background:transparent;")
        self.body.addWidget(scorri)
        nuovo = QHBoxLayout()
        self.n_nome = QLineEdit()
        self.n_nome.setPlaceholderText("Nome (es. Ufficio Rossi)")
        self.n_id = QLineEdit()
        self.n_id.setPlaceholderText("ID")
        self.n_id.setFixedWidth(130)
        self.n_pw = QLineEdit()
        self.n_pw.setPlaceholderText("Password fissa (facoltativa)")
        self.n_pw.setEchoMode(QLineEdit.EchoMode.Password)
        nuovo.addWidget(self.n_nome, 1)
        nuovo.addWidget(self.n_id)
        self.body.addLayout(nuovo)
        self.body.addWidget(self.n_pw)
        self.err = QLabel("", objectName="err")
        self.body.addWidget(self.err)
        riga = QHBoxLayout()
        riga.addWidget(text_btn("plus", "Aggiungi", self._aggiungi, "#fff", "accent"))
        riga.addStretch(1)
        riga.addWidget(text_btn("", "Chiudi", self.accept, "#fff", "ghost"))
        self.body.addLayout(riga)
        self.stati = {}
        self._disegna()
        self._controlla()

    def _voci(self):
        return list(self.win.settings.value("rubrica", []) or [])

    def _disegna(self):
        while self.lista.count():
            w = self.lista.takeAt(0).widget()
            if w:
                w.deleteLater()
        voci = self._voci()
        if not voci:
            vuoto = QLabel("Ancora nessun computer: aggiungilo qui sotto con nome e ID.")
            vuoto.setObjectName("asub")
            self.lista.addWidget(vuoto)
        for v in voci:
            card = QFrame(objectName="acard")
            h = QHBoxLayout(card)
            h.setContentsMargins(12, 8, 8, 8)
            acceso = (self.stati.get(v["id"]) or {}).get("acceso")
            punto = QLabel()
            punto.setPixmap(ic("dot", "#4ade80" if acceso else "#64748b", 14).pixmap(14, 14))
            punto.setToolTip("Acceso" if acceso else "Spento o tk-desk chiuso")
            h.addWidget(punto)
            col = QVBoxLayout()
            col.setSpacing(0)
            t = QLabel(v.get("nome") or ce.formatta_id(v["id"]))
            t.setStyleSheet("font-weight:800;")
            col.addWidget(t)
            s = QLabel(ce.formatta_id(v["id"]) + (" · password salvata" if v.get("chiave") else ""))
            s.setObjectName("asub")
            col.addWidget(s)
            h.addLayout(col, 1)
            h.addWidget(text_btn("link", "Collegati", lambda _=False, x=v: self._collega(x), "#fff", "accent"))
            h.addWidget(mini_btn("trash", "Togli dalla rubrica", lambda _=False, x=v: self._togli(x), "#fca5a5"))
            self.lista.addWidget(card)
        self.lista.addStretch(1)

    def _controlla(self):
        ids = [v["id"] for v in self._voci()]
        if not ids:
            return
        self._w = Worker(lambda: self.win.motore.stato_rubrica(ids), self)
        self._w.done.connect(lambda st: (self.stati.update(st or {}), self._disegna()))
        self._w.start()

    def _aggiungi(self):
        id_ = ce.pulisci_id(self.n_id.text())
        if not id_:
            self.err.setText("L'ID ha 9 cifre.")
            return
        voci = [v for v in self._voci() if v["id"] != id_]
        voce = {"id": id_, "nome": self.n_nome.text().strip()[:60]}
        if self.n_pw.text():   # mai la password in chiaro: la chiave ricavata (v2), cifrata
            voce["chiave"] = util.proteggi("v2:" + ce.chiave2(self.n_pw.text(), id_).hex(), "rubrica-" + id_)
        voci.append(voce)
        voci.sort(key=lambda v: (v.get("nome") or v["id"]).lower())
        self.win.settings.setValue("rubrica", voci)
        for c in (self.n_nome, self.n_id, self.n_pw):
            c.clear()
        self.err.setText("")
        self._disegna()
        self._controlla()

    def _togli(self, voce):
        util.dimentica(voce.get("chiave"))
        self.win.settings.setValue("rubrica", [v for v in self._voci() if v["id"] != voce["id"]])
        self._disegna()

    def _collega(self, voce):
        chiave = util.svela(voce.get("chiave")) if voce.get("chiave") else ""
        self.accept()
        if chiave:
            self.win.collega(voce["id"], "", chiave, voce.get("nome", ""))
            return
        self.win.campo_id.setText(ce.formatta_id(voce["id"]))
        self.win.campo_pw.setFocus()
        if voce.get("chiave"):
            self.win.err.setText("La password salvata non si legge su questo computer (o con questo utente): "
                                 "scrivila qui.")


class Impostazioni(TkDialog):
    """Nome del computer, appunti condivisi, statistiche, accesso non presidiato (Mac e Linux: cancella tutto)."""

    def __init__(self, win):
        super().__init__(win, 500)
        self.win = win
        self.head(ic("gear", "#6ee7b7", 40).pixmap(44, 44), "Impostazioni", "")
        card = QFrame(objectName="acard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.addWidget(QLabel("NOME DI QUESTO COMPUTER", objectName="atitle"))
        self.nome = QLineEdit(str(win.settings.value("nome_computer", "") or ""))
        self.nome.setPlaceholderText(ce.nome_di_sistema() or "Nome del computer")
        self.nome.setMaxLength(60)
        cl.addWidget(self.nome)
        lab = QLabel("Lo vede chi ti controlla e chi controlli, e va al centralino (dal prossimo avvio). "
                     "Vuoto = il nome del computer.")
        lab.setObjectName("asub")
        lab.setWordWrap(True)
        cl.addWidget(lab)
        self.body.addWidget(card)
        card2 = QFrame(objectName="acard")
        c2 = QVBoxLayout(card2)
        c2.setContentsMargins(16, 12, 16, 12)
        c2.addWidget(QLabel("DURANTE LE SESSIONI", objectName="atitle"))
        self.appunti = QCheckBox("Condividi gli appunti (il testo copiato passa all'altro computer)")
        self.appunti.setChecked(bool(win.settings.value("appunti", False)))
        self.appunti.setStyleSheet("color:#e2e8f0;")
        c2.addWidget(self.appunti)
        nota = QLabel("Spento di default: negli appunti finiscono anche password e dati copiati. Con più sessioni "
                      "aperte va solo a quella in primo piano.")
        nota.setObjectName("asub")
        nota.setWordWrap(True)
        c2.addWidget(nota)
        from tkdesk.tk_licenza_qt import casella_statistiche
        self.stat = casella_statistiche(pro.licenza())
        self.stat.setStyleSheet("color:#e2e8f0;")
        c2.addWidget(self.stat)
        self.body.addWidget(card2)
        riga = QHBoxLayout()
        riga.addWidget(text_btn("key", "Accesso non presidiato", self._non_presidiato, "#fff", "ghost"))
        if IS_MAC:
            riga.addWidget(text_btn("lock", "Permessi del Mac", self._permessi, "#fff", "ghost"))
        riga.addStretch(1)
        self.body.addLayout(riga)
        if IS_MAC or IS_LINUX:      # riga a sé: accanto agli altri il testo veniva tagliato
            riga_c = QHBoxLayout()
            riga_c.addWidget(text_btn("trash", "Cancella tutto e togli l'avvio automatico", self._cancella, "#fca5a5",
                                      "ghost"))
            riga_c.addStretch(1)
            self.body.addLayout(riga_c)
        riga2 = QHBoxLayout()
        riga2.addStretch(1)
        riga2.addWidget(text_btn("", "Annulla", self.reject, "#fff", "ghost"))
        riga2.addWidget(text_btn("check", "Salva", self._salva, "#fff", "accent"))
        self.body.addLayout(riga2)

    def _salva(self):
        self.win.settings.setValue("nome_computer", self.nome.text().strip()[:60])
        self.win.settings.setValue("appunti", self.appunti.isChecked())
        self.accept()

    def _non_presidiato(self):
        self.accept()
        self.win._non_presidiato()

    def _permessi(self):
        from tkdesk.util import mac_permessi
        self.accept()
        schermo, accesso = mac_permessi()
        PermessiMac(self.win, schermo, accesso, tutte=True).exec()

    def _cancella(self):
        if IS_LINUX:
            testo = ("Tolgo l'avvio automatico, la password fissa, la rubrica, le impostazioni, i dati di tk-desk e la "
                     "voce nel menu delle applicazioni da questo computer, poi chiudo tk-desk. Per finire cancella il "
                     "file AppImage di tk-desk.")
        else:
            testo = ("Tolgo l'avvio automatico, la password fissa, la rubrica, le impostazioni e i dati di tk-desk da "
                     "questo Mac, poi chiudo tk-desk. Per finire trascina tk-desk dalle Applicazioni al Cestino.")
        scelta = tk_choice(self, "Cancella tutto", testo, [("Annulla", "ghost"), ("Cancella tutto", "accent")], "warn")
        if scelta != 1:
            return
        if self.win.motore.sessioni_entrata():
            self.win._termina_controllo()
        util.cancella_tutto(self.win.settings)
        self.win.settings.path = ""   # da qui in poi niente più scritture (la cartella dei dati non c'è più)
        self.accept()
        self.win.uscita = True
        QTimer.singleShot(200, self.win.close)


# ───────────────────────────────────────────── finestra principale
class Principale(QMainWindow):
    def __init__(self, settings, motore):
        super().__init__()
        self.settings = settings
        self.motore = motore
        self.sessioni = {}          # chiave → finestra Sessione
        self.chat_ctrl = {}         # id di chi mi controlla → ChatControllato
        self.manifest = None
        self.check_thread = None
        self.dl_thread = None
        self.closing_for_update = False
        self.uscita = False
        self._ultimi_appunti = ""
        self._esecutore = None
        self.sessione_attiva = None  # chiave della finestra di sessione in primo piano (per gli appunti)
        self._conferme = {}          # richiesta → finestra «Accetta / Rifiuta»
        self._rete = False           # centralino e aggiornamenti partono solo dopo il benvenuto
        self._primo_fatto = False
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(QIcon(render_icon(128)))
        self.setMinimumWidth(760)
        self._build()
        self.barra = Barra()
        self.barra.termina.connect(self._termina_controllo)
        self.barra.chat.connect(self._chat_controllato)
        self.barra.file.connect(self._manda_file_controllato)
        self.barra.voce.connect(self._voce_barra)
        self._voce_ctrl = ""
        self.veglia = Veglia()
        self._timer_veglia = QTimer(self, interval=30000, timeout=self.veglia.sveglia)
        self._collega_motore()
        self._icona_orologio()
        QApplication.clipboard().dataChanged.connect(self._appunti_cambiati)
        testata_compatta(self, [(self.b_rubrica, ""), (self.b_imp, ""), (self.b_conf, "")], 1040)
        dentro_lo_schermo(self, 1000, 660)

    # ---- primo avvio e rete
    def primo_avvio(self):
        """Finestra aperta: benvenuto (una volta sola, con le righe di tk-desk), poi la rete, poi l'invito al caffè."""
        if self._primo_fatto:
            return
        self._primo_fatto = True
        from tkdesk.tk_licenza_qt import benvenuto
        try:
            benvenuto(pro.licenza(), APP_TITLE, URL_SORGENTE, parent=self, logo=render_icon(104),
                      righe_extra=righe_benvenuto(ce.nome_computer(self.settings)))
        except Exception as exc:
            print("tk-desk: benvenuto non mostrato:", exc)
        self.settings.setValue("welcome_ok", True)
        self.avvia_rete()
        pro.invito(self)

    def avvia_rete(self):
        """Centralino (ID e chiamate), statistiche col consenso e controllo degli aggiornamenti."""
        if self._rete:
            return
        self._rete = True
        self.motore.avvia()
        lic = pro.licenza()
        if lic is not None:
            try:
                lic.avvia()     # il segnale del giorno parte solo se l'utente ha detto sì
            except Exception:
                pass
        QTimer.singleShot(2500, lambda: self.check_updates(False))
        QTimer.singleShot(1500, self.ensure_shortcut)

    # ---- costruzione
    def _build(self):
        central = QWidget(objectName="canvas")
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(14)
        header = QFrame(objectName="header")
        shadow(header, 30, 8, 70)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(18, 12, 18, 12)
        hl.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(render_icon(44))
        hl.addWidget(icon)
        hl.addSpacing(4)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(QLabel(APP_TITLE, objectName="brand"))
        col.addWidget(QLabel(f"Versione {VERSION}", objectName="ver"))
        hl.addLayout(col)
        hl.addStretch(1)
        self.update_btn = text_btn("refresh", "Aggiorna", self.show_update_dialog, "#fff", "accent")
        self.update_btn.hide()
        hl.addWidget(self.update_btn)
        self.b_rubrica = text_btn("book", "Rubrica", self._rubrica, tip="I tuoi computer, con chi è acceso")
        self.b_imp = text_btn("key", "Accesso non presidiato", self._non_presidiato,
                              tip="Password fissa e avvio con il computer")
        self.b_conf = text_btn("gear", "Impostazioni", self._impostazioni,
                               tip="Nome del computer, appunti condivisi, statistiche")
        hl.addWidget(self.b_rubrica)
        hl.addWidget(self.b_imp)
        hl.addWidget(self.b_conf)
        hl.addWidget(text_btn("info", "", self.act_about, tip="Informazioni e aggiornamenti"))
        root.addWidget(header)

        riga = QHBoxLayout()
        riga.setSpacing(14)
        # questo computer
        c1 = Card("monitor", "Questo computer")
        c1.head.addWidget(self._pill_stato())
        t = QLabel("Per farti aiutare, detta ID e password a chi ti assiste.")
        t.setObjectName("hint")
        t.setWordWrap(True)
        c1.lay.addWidget(t)
        idbox = QFrame(objectName="idbox")
        il = QHBoxLayout(idbox)
        il.setContentsMargins(16, 10, 10, 10)
        colid = QVBoxLayout()
        colid.setSpacing(0)
        colid.addWidget(QLabel("IL TUO ID", objectName="field"))
        self.lab_id = QLabel("…", objectName="bigid")
        self.lab_id.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        colid.addWidget(self.lab_id)
        il.addLayout(colid, 1)
        il.addWidget(mini_btn("copy", "Copia l'ID", lambda: copia(self.motore.id)))
        c1.lay.addWidget(idbox)
        pwbox = QFrame(objectName="pwbox")
        pl = QHBoxLayout(pwbox)
        pl.setContentsMargins(16, 10, 10, 10)
        colpw = QVBoxLayout()
        colpw.setSpacing(0)
        colpw.addWidget(QLabel("PASSWORD MONOUSO", objectName="field"))
        self.lab_pw = QLabel("……", objectName="bigpw")
        self.lab_pw.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        colpw.addWidget(self.lab_pw)
        pl.addLayout(colpw, 1)
        pl.addWidget(mini_btn("copy", "Copia la password", lambda: copia(self.motore.password)))
        pl.addWidget(mini_btn("refresh", "Nuova password", self.motore.nuova_password))
        c1.lay.addWidget(pwbox)
        truffa = QLabel(ANTITRUFFA, objectName="truffa")
        truffa.setWordWrap(True)
        c1.lay.addWidget(truffa)
        self.lab_tent = QLabel("", objectName="tentativi")
        self.lab_tent.setWordWrap(True)
        self.lab_tent.hide()
        c1.lay.addWidget(self.lab_tent)
        self.lab_np = QLabel("")
        self.lab_np.setObjectName("hint")
        self.lab_np.setWordWrap(True)
        c1.lay.addWidget(self.lab_np)
        c1.lay.addStretch(1)
        nota = QLabel("A ogni collegamento decidi tu con «Accetta». La password cambia dopo ogni sessione e da sola "
                      "dopo 10 minuti. Puoi chiudere il collegamento quando vuoi.")
        nota.setObjectName("hint")
        nota.setWordWrap(True)
        c1.lay.addWidget(nota)
        riga.addWidget(c1, 1)
        # controlla un altro computer
        c2 = Card("link", "Controlla un altro computer")
        t2 = QLabel("Scrivi ID e password che ti detta l'altra persona.")
        t2.setObjectName("hint")
        t2.setWordWrap(True)
        c2.lay.addWidget(t2)
        self.campo_id = QLineEdit(objectName="bigin")
        self.campo_id.setPlaceholderText("ID del computer (9 cifre)")
        self.campo_id.textEdited.connect(self._formatta_campo)
        self.campo_pw = QLineEdit(objectName="bigin")
        self.campo_pw.setPlaceholderText("Password (6 cifre)")
        # in chiaro: è la monouso che ti dettano, così vedi se l'hai scritta giusta (Pietro, 25/10)
        self.campo_pw.returnPressed.connect(self._collegati)
        self.campo_pw.textEdited.connect(self._formatta_pw)
        self.campo_id.returnPressed.connect(self.campo_pw.setFocus)
        c2.lay.addWidget(self.campo_id)
        c2.lay.addWidget(self.campo_pw)
        self.b_collega = text_btn("link", "Collegati", self._collegati, "#fff", "accent")
        self.b_collega.setObjectName("accent")
        self.b_collega.setMinimumHeight(46)
        c2.lay.addWidget(self.b_collega)
        self.err = QLabel("")
        self.err.setStyleSheet(f"color:{RED}; font-weight:600;")
        self.err.setWordWrap(True)
        c2.lay.addWidget(self.err)
        c2.lay.addWidget(QLabel("RECENTI", objectName="field"))
        self.recenti = QVBoxLayout()
        self.recenti.setSpacing(6)
        c2.lay.addLayout(self.recenti)
        c2.lay.addStretch(1)
        riga.addWidget(c2, 1)
        root.addLayout(riga, 1)
        self.setCentralWidget(central)
        self._disegna_recenti()
        self.aggiorna_stato()

    def _pill_stato(self):
        self.p_stato = QLabel("COLLEGAMENTO…")
        self.p_stato.setObjectName("pill")
        self.p_stato.setStyleSheet(f"background:{GRAY_400};")
        return self.p_stato

    def _formatta_campo(self, testo):
        cifre = "".join(c for c in testo if c.isdigit())[:9]
        nuovo = ce.formatta_id(cifre)
        if nuovo != testo:
            self.campo_id.setText(nuovo)

    def _formatta_pw(self, testo):
        """La monouso a gruppi come sul computer ospite («123 456»). Una password fissa (più di 6 caratteri o con
        lettere) resta com'è: lo spazio messo da qui si toglie."""
        cifre = testo.replace(" ", "")
        if cifre.isdigit() and len(cifre) <= 6:
            nuovo = cifre if len(cifre) <= 3 else f"{cifre[:3]} {cifre[3:]}"
        elif len(testo) > 3 and testo[3] == " " and testo[:3].isdigit() and " " not in testo[4:]:
            nuovo = testo[:3] + testo[4:]
        else:
            return
        if nuovo != testo:
            self.campo_pw.setText(nuovo)

    def aggiorna_stato(self):
        if self.motore.ha_password_fissa():
            extra = " · parte con il computer" if self._avvio() else ""
            self.lab_np.setText(f"Accesso non presidiato attivo (password fissa){extra}.")
        else:
            self.lab_np.setText("")

    @staticmethod
    def _avvio():
        try:
            return avvio_automatico()
        except Exception:
            return False

    def _disegna_recenti(self):
        while self.recenti.count():
            w = self.recenti.takeAt(0).widget()
            if w:
                w.deleteLater()
        voci = list(self.settings.value("recenti", []) or [])[:4]
        if not voci:
            vuoto = QLabel("I computer che controlli compariranno qui.")
            vuoto.setObjectName("hint")
            self.recenti.addWidget(vuoto)
        for v in voci:
            b = QPushButton(f"{v.get('nome') or 'Computer'}   ·   {ce.formatta_id(v['id'])}")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("text-align:left; padding-left:14px;")
            b.clicked.connect(lambda _=False, x=v: (self.campo_id.setText(ce.formatta_id(x["id"])), self.campo_pw.setFocus()))
            self.recenti.addWidget(b)

    def ricorda_recente(self, id_, nome):
        voci = [v for v in (self.settings.value("recenti", []) or []) if v.get("id") != id_]
        voci.insert(0, {"id": id_, "nome": nome or "", "quando": int(time.time())})
        self.settings.setValue("recenti", voci[:8])
        self._disegna_recenti()

    # ---- motore
    def _collega_motore(self):
        s = self.motore.s
        s.pronto.connect(self._pronto)
        s.errore_centralino.connect(self._errore_centralino)
        s.password_cambiata.connect(lambda pw: self.lab_pw.setText(f"{pw[:3]} {pw[3:]}"))
        s.controllato_inizio.connect(self._controllato_inizio)
        s.controllato_fine.connect(self._controllato_fine)
        s.stato_chiamata.connect(lambda k, t: self._a(k, "stato_chiamata", t))
        s.sessione_aperta.connect(lambda k, info: self._a(k, "apri", info))
        s.sessione_chiusa.connect(self._sessione_chiusa)
        s.fotogramma.connect(lambda k, d, w, h: self._a(k, "fotogramma", d, w, h))
        s.chat.connect(self._chat)
        s.appunti.connect(self._appunti_ricevuti)
        s.file_ricevuto.connect(self._file_ricevuto)
        s.file_avanzamento.connect(lambda k, n, f, t: self._a(k, "avanzamento", n, f, t))
        s.registrazione.connect(lambda k, p: self._a(k, "registrazione", p))
        s.comando.connect(self._comando)
        s.cursore.connect(lambda k, x, y: self._a(k, "cursore", x, y))
        s.voce_chiesta.connect(self._voce_chiesta)
        s.voce_stato.connect(self._voce_stato)
        s.richiesta_accesso.connect(self._richiesta_accesso)
        s.richiesta_chiusa.connect(self._richiesta_chiusa)
        s.tentativi.connect(self._tentativi)
        s.registrazione_remota.connect(self._rec_remota)
        s.file_in_arrivo.connect(self._file_in_arrivo)
        s.file_rifiutato.connect(self._file_rifiutato)

    # ---- conferma locale dei collegamenti in entrata (password monouso)
    @staticmethod
    def _chiudi_modali():
        """Una finestra modale aperta (invito al caffè, Impostazioni, Informazioni, Rubrica…) blocca i clic su
        tutte le altre, anche sulla conferma «Accetta» che è senza genitore e magari su un altro schermo:
        si annullano prima di mostrarla (Impostazioni = Annulla, nessun salvataggio)."""
        for _ in range(10):
            m = QApplication.activeModalWidget()
            if m is None:
                break
            try:
                m.reject() if hasattr(m, "reject") else m.close()
            except Exception:
                m.close()
            QApplication.processEvents()

    def _richiesta_accesso(self, rid, id_, nome):
        self._chiudi_modali()
        dlg = ConfermaAccesso(id_, nome)
        dlg.scelta.connect(lambda si, r=rid: (self.motore.rispondi_accesso(r, si), self._conferme.pop(r, None)))
        self._conferme[rid] = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        QApplication.alert(dlg)
        if self.tray:
            self.tray.showMessage(APP_TITLE, "Qualcuno vuole controllare questo computer: Accetta o Rifiuta.",
                                  QSystemTrayIcon.MessageIcon.Warning, 8000)

    def _richiesta_chiusa(self, rid):
        dlg = self._conferme.pop(rid, None)
        if dlg is not None:
            dlg.chiudi()

    def _tentativi(self, n, blocco):
        testo = f"Attenzione: {n} password sbagliate di fila."
        if n > 3:
            testo += " La password monouso è cambiata."
        if blocco:
            testo += f" Nuovi tentativi bloccati per {blocco // 60} minut{'o' if blocco < 120 else 'i'}."
        self.lab_tent.setText(testo)
        self.lab_tent.show()

    def _rec_remota(self, id_, acceso):
        self.barra.rec(acceso)
        if acceso and self.tray:
            self.tray.showMessage(APP_TITLE, "Chi ti assiste sta registrando lo schermo in un video.",
                                  QSystemTrayIcon.MessageIcon.Information, 6000)

    def _file_in_arrivo(self, chiave, fid, nome, totale):
        da_sessione = chiave in self.sessioni
        chi = self.sessioni[chiave].titolo.text() if da_sessione else "Chi ti assiste"
        from tkdesk.sessione import e_programma
        testo = (f"{chi} vuole mandarti «{nome}» ({human_size(int(totale or 0))}).\n\n"
                 + ("ATTENZIONE: è un PROGRAMMA. Se lo apri può fare qualsiasi cosa sul computer.\n\n"
                    if e_programma(nome) else "")
                 + "Accettalo solo se lo aspettavi. Non aprire programmi o documenti ricevuti da chi non conosci: "
                 "possono rubarti dati e password.")
        scelta = tk_choice(self.sessioni.get(chiave), "File in arrivo", testo,
                           [("Rifiuta", "ghost"), ("Accetta", "accent")], "ask")
        self.motore.accetta_file(chiave, fid, scelta == 1)

    def _file_rifiutato(self, chiave, nome, motivo):
        testo = f"«{nome}» non è passato: {motivo}." if nome else f"File non passato: {motivo}."
        if chiave in self.sessioni:
            self.sessioni[chiave]._avviso(testo)
        elif self.tray:
            self.tray.showMessage(APP_TITLE, testo, QSystemTrayIcon.MessageIcon.Warning, 6000)

    def _comando(self, cmd, schermo):
        """Mac: mouse e tastiera dal thread principale (vedi Segnali.comando)."""
        if cmd.get("t") != "rilascia" and not getattr(self, "_accesso_ok", False):
            from tkdesk.util import mac_permessi
            if not mac_permessi()[1]:
                if not getattr(self, "_avvisato_accesso", False):
                    self._avvisato_accesso = True
                    for id_ in self.motore.sessioni_entrata():
                        self.motore.avviso(id_, "Sul Mac manca il permesso Accessibilità: mouse e tastiera non arrivano.")
                    QTimer.singleShot(0, lambda: self._permessi_mac(True))
                return
            self._accesso_ok = True
        try:
            if self._esecutore is None:
                from tkdesk.comandi import Esecutore
                self._esecutore = Esecutore()
            if cmd.get("t") == "rilascia":
                self._esecutore.rilascia_tutto()
                return
            if schermo:
                self._esecutore.schermo = schermo
            self._esecutore.esegui(cmd)
        except Exception as exc:
            print("tk-desk: comando non eseguito:", exc)
            if not getattr(self, "_avvisato_errore", False):
                self._avvisato_errore = True
                try:
                    import os as _os
                    with open(_os.path.join(log_dir(), "diagnosi.log"), "a", encoding="utf-8") as fh:
                        fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] comando {cmd.get('t')}: {exc!r}\n")
                except Exception:
                    pass
                for id_ in self.motore.sessioni_entrata():
                    self.motore.avviso(id_, f"Il mouse non funziona sull'altro computer: {exc}")

    def _a(self, chiave, metodo, *args):
        w = self.sessioni.get(chiave)
        if w is not None:
            getattr(w, metodo)(*args)
        elif metodo == "fotogramma":
            self.motore.disegnato(chiave)

    def _pronto(self, id_):
        self.lab_id.setText(ce.formatta_id(id_))
        self.p_stato.setText("PRONTO")
        self.p_stato.setStyleSheet(f"background:{GREEN};")
        self.aggiorna_stato()

    def _errore_centralino(self, msg):
        self.p_stato.setText("NON COLLEGATO")
        self.p_stato.setStyleSheet(f"background:{RED};")
        self.p_stato.setToolTip(msg)

    def _collegati(self):
        id_ = ce.pulisci_id(self.campo_id.text())
        pw = self.campo_pw.text().strip()
        if not id_:
            self.err.setText("L'ID ha 9 cifre: controlla di averlo scritto tutto.")
            return
        if not pw:
            self.err.setText("Scrivi la password che ti ha detto l'altra persona.")
            self.campo_pw.setFocus()
            return
        self.err.setText("")
        self.collega(id_, pw)
        self.campo_pw.clear()

    def collega(self, id_, password, chiave_salvata="", nome=""):
        chiave = self.motore.connetti(id_, password, chiave_salvata)
        w = Sessione(self, chiave, id_, nome)
        self.sessioni[chiave] = w
        w.show()

    def _sessione_chiusa(self, chiave, motivo):
        w = self.sessioni.get(chiave)
        if w is not None:
            w.chiusa(motivo)

    def sessione_finestra_chiusa(self, chiave):
        self.sessioni.pop(chiave, None)
        if self.sessione_attiva == chiave:
            self.sessione_attiva = None

    # ---- lato controllato
    def _controllato_inizio(self, id_, nome):
        chi = f"{nome} ({ce.formatta_id(id_)})" if nome else ce.formatta_id(id_)
        TkDialog.nascondi_dalla_cattura = True
        self.veglia.accendi()
        self._timer_veglia.start()
        self.lab_tent.hide()
        self.barra.rec(False)
        self.barra.mostra(f"Questo computer è controllato da {chi}")
        if self.tray:
            self.tray.showMessage(APP_TITLE, f"{chi} ora controlla questo computer.", QSystemTrayIcon.MessageIcon.Information, 5000)

    def _controllato_fine(self, id_, motivo):
        if not self.motore.sessioni_entrata():
            self.barra.hide()
            self._voce_ctrl = ""
            TkDialog.nascondi_dalla_cattura = False
            self._timer_veglia.stop()
            self.veglia.spegni()
            self.barra.voce_stato("")
            self.barra.rec(False)
        c = self.chat_ctrl.pop(id_, None)
        if c:
            c.close()

    def _permessi_mac(self, durante_sessione):
        """Mac: all'avvio (la prima volta solo le richieste del Mac) o quando qualcuno prova a controllare questo Mac
        senza Accessibilità. La nostra finestra spiega e offre «Ripristina i permessi»."""
        if not IS_MAC or getattr(self, "_finestra_permessi", False):
            return
        from tkdesk.util import mac_permessi
        if not durante_sessione and not self.settings.value("permessi_chiesti2", False):
            mac_permessi(chiedi=True)
            self.settings.setValue("permessi_chiesti2", True)
            return
        schermo, accesso = mac_permessi()
        if schermo and accesso:
            return
        if not durante_sessione and (self.settings.value("permessi_mai", False) or not self.isVisible()):
            return
        self._finestra_permessi = True
        try:
            dlg = PermessiMac(self, schermo, accesso)
            dlg.exec()
            if dlg.mai:
                self.settings.setValue("permessi_mai", True)
        finally:
            self._finestra_permessi = False

    def _manda_file_controllato(self, file):
        for id_ in self.motore.sessioni_entrata():
            for f in file:
                self.motore.manda_file(id_, f)

    # ---- chiamata vocale
    def _voce_chiesta(self, chiave):
        if chiave in self.sessioni:
            self.sessioni[chiave].voce_chiesta()
            return
        scelta = tk_choice(None, "Chiamata vocale", "Chi ti assiste vuole parlare con te.",
                           [("Rifiuta", "ghost"), ("Rispondi", "accent")], "ask")
        self.motore.voce(chiave, scelta == 1)
        if scelta == 1:
            self._voce_ctrl = "chiamo"
            self.barra.voce_stato("chiamo")

    def _voce_stato(self, chiave, stato, avviso):
        if chiave in self.sessioni:
            self.sessioni[chiave].voce_stato(stato, avviso)
            return
        self._voce_ctrl = "" if stato in ("chiusa", "rifiutata") else stato
        self.barra.voce_stato(self._voce_ctrl)
        if stato == "attiva" and avviso:
            tk_warn(None, "Chiamata vocale", f"La chiamata è partita, ma: {avviso}")

    def _voce_barra(self):
        ids = self.motore.sessioni_entrata()
        if not ids:
            return
        if self._voce_ctrl:
            self.motore.voce(ids[0], False)
        else:
            self.motore.voce(ids[0], True)
            self._voce_ctrl = "chiamo"
            self.barra.voce_stato("chiamo")

    def _termina_controllo(self):
        for id_ in self.motore.sessioni_entrata():
            self.motore.chiudi(id_, "Chiusa dal computer controllato.")

    def _chat_controllato(self, id_=None):
        ids = self.motore.sessioni_entrata()
        if not ids:
            return
        id_ = id_ or ids[0]
        c = self.chat_ctrl.get(id_)
        if c is None:
            c = ChatControllato(None, f"con {ce.formatta_id(id_)}")
            c.chat.invia.connect(lambda t, x=id_: self.motore.manda(x, {"t": "chat", "s": t}))
            self.chat_ctrl[id_] = c
        c.show()
        c.raise_()
        return c

    def _chat(self, chiave, testo):
        if chiave in self.sessioni:
            self.sessioni[chiave].chat_ricevuta(testo)
        elif chiave in self.motore.sessioni_entrata():
            c = self._chat_controllato(chiave)
            c.chat.aggiungi("Assistenza", testo)

    def _file_ricevuto(self, chiave, percorso):
        if chiave in self.sessioni:
            self.sessioni[chiave].file_ricevuto(percorso)
            return
        scelta = tk_choice(None, "File ricevuto", f"È arrivato «{os.path.basename(percorso)}».\n"
                                                    f"L'ho messo sulla Scrivania.",
                           [("Apri la cartella", "ghost"), ("OK", "accent")], "ok")
        if scelta == 0:
            open_path(os.path.dirname(percorso))

    # ---- appunti condivisi (testo), nei due sensi: solo se accesi nelle Impostazioni
    def _destinatari_appunti(self):
        """Con più sessioni aperte, solo quella in primo piano (l'ultima finestra di sessione attiva)."""
        if self.sessione_attiva in self.sessioni:
            uscita = [self.sessione_attiva]
        else:
            uscita = list(self.sessioni) if len(self.sessioni) == 1 else []
        return uscita + self.motore.sessioni_entrata()

    def _appunti_cambiati(self):
        if not self.motore.appunti_attivi():
            return
        testo = QApplication.clipboard().text()
        if not testo or testo == self._ultimi_appunti or len(testo) > 200000:
            return
        self._ultimi_appunti = testo
        for k in self._destinatari_appunti():
            self.motore.manda_appunti(k, testo)

    def _appunti_ricevuti(self, chiave, testo):
        if not self.motore.appunti_attivi() or chiave not in self._destinatari_appunti():
            return
        if testo and testo != self._ultimi_appunti:
            self._ultimi_appunti = testo
            QApplication.clipboard().setText(testo)

    # ---- rubrica e impostazioni
    def _rubrica(self):
        Rubrica(self).exec()

    def _non_presidiato(self):
        NonPresidiato(self).exec()

    def _impostazioni(self):
        Impostazioni(self).exec()

    # ---- icona vicino all'orologio
    def _icona_orologio(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(QIcon(render_icon(64)), self)
        self.tray.setToolTip(APP_TITLE)
        menu = QMenu()
        menu.addAction(QAction("Apri tk-desk", self, triggered=self._mostra))
        menu.addSeparator()
        menu.addAction(QAction("Esci da tk-desk", self, triggered=self._esci))
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self._mostra() if r == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def _mostra(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if not self._primo_fatto:     # partito in sottofondo senza aver ancora visto il benvenuto
            QTimer.singleShot(300, self.primo_avvio)

    def _esci(self):
        self.uscita = True
        self.close()

    # ---- informazioni e aggiornamenti (come negli altri software TK)
    def ensure_shortcut(self):
        from tkdesk.util import APP_ROOT, ensure_folder_shortcut
        if IS_LINUX and is_installed():
            # voce nel menu delle applicazioni con l'icona (si corregge da sola se il file AppImage è stato spostato)
            def menu():
                try:
                    util.installa_menu_linux()
                except Exception as exc:
                    print("tk-desk: voce nel menu non creata:", exc)
            threading.Thread(target=menu, daemon=True).start()
            return
        if not IS_WIN or not is_installed() or self.settings.value("lnk_root", "") == APP_ROOT:
            return

        def work():
            try:
                ensure_folder_shortcut()
                self.settings.setValue("lnk_root", APP_ROOT)
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def act_about(self):
        """Informazioni: finestra comune a tutti i software TK (libreria), colore di tk-desk."""
        self._informazioni().exec()

    def _informazioni(self):
        from tkdesk.tk_licenza_qt import InformazioniDialog
        return InformazioniDialog(
            pro.licenza(), APP_TITLE, VERSION, "Assistenza remota: schermo, mouse, tastiera, file e chat, con la "
            "conferma di chi sta al computer.", render_icon(136), "#059669",
            dati=[("Impostazioni e rubrica", util.data_dir(), "Password fissa e rubrica sono cifrate su questo computer.")],
            url_sorgente=URL_SORGENTE, cartella_licenze=util.cartella_licenze(),
            su_aggiornamenti=lambda: self.check_updates(True),
            su_icona_desktop=self._icona_desktop if util.IS_WIN else None, parent=self)

    def _icona_desktop(self):
        try:
            path = util.create_desktop_shortcut()
        except Exception as exc:
            tk_warn(self, APP_TITLE, f"Non riesco a creare l'icona sul Desktop:\n{exc}")
            return
        tk_info(self, APP_TITLE, f"Icona creata sul Desktop:\n{path}", "ok")

    def show_update_button(self, version):
        self.update_btn.setVisible(bool(version))
        if version:
            self.update_btn.setText(f"Aggiorna a {version}")

    def check_updates(self, manual):
        if self.check_thread is not None and self.check_thread.isRunning():
            return
        if not manual and time.time() - float(self.settings.value("last_check", 0)) < updater.CHECK_INTERVAL:
            cached = self.settings.value("available", "")
            if cached and updater.is_newer(cached):
                self.show_update_button(cached)
            return
        self.check_thread = Worker(updater.fetch_manifest, self)
        self.check_thread.done.connect(lambda m: self._checked(m, "", manual))
        self.check_thread.failed.connect(lambda err: self._checked(None, err, manual))
        self.check_thread.start()

    def _checked(self, manifest, error, manual):
        if manifest is None:
            if manual:
                tk_warn(self, APP_TITLE, f"Impossibile controllare gli aggiornamenti.\n"
                                         f"Verifica la connessione a internet.\n\n{error}")
            return
        self.settings.setValue("last_check", time.time())
        version = str(manifest["version"])
        if not updater.is_newer(version):
            self.settings.setValue("available", "")
            self.show_update_button(None)
            if manual:
                tk_info(self, APP_TITLE, f"Hai già l'ultima versione di {APP_TITLE} ({VERSION}).", "ok")
            return
        self.manifest = manifest
        self.settings.setValue("available", version)
        self.show_update_button(version)
        if manual or (self.settings.value("skip_version", "") != version and not self.motore.sessioni_entrata()):
            self.show_update_dialog()

    def show_update_dialog(self):
        m = self.manifest
        if m is None:
            self.check_updates(True)
            return
        dlg = UpdateDialog(self, m)
        dlg.exec()
        if dlg.choice == "skip":
            self.settings.setValue("skip_version", str(m["version"]))
        elif dlg.choice == "go":
            self.start_update()

    def start_update(self):
        asset = updater.asset_for(self.manifest)
        if asset is None:
            tk_info(self, APP_TITLE, "Questa versione non è ancora disponibile per il tuo sistema.")
            return
        if not is_installed():
            tk_info(self, APP_TITLE, "Stai usando la versione di sviluppo: l'aggiornamento automatico "
                                     "funziona solo con la versione installata.")
            return
        dest = os.path.join(updater.download_dir(), os.path.basename(asset["url"].split("?")[0]))
        prog = TkProgress(self, "Aggiornamento in corso", f"Scarico {APP_TITLE} {self.manifest['version']}", True)
        prog.show()
        self.dl_thread = t = DownloadThread(asset["url"], dest, asset.get("sha256"), self)

        def on_ok(path):
            prog.bar.setRange(0, 0)
            prog.status.setText("Installazione dell'aggiornamento…")
            try:
                updater.apply_update(path, new_version=str(self.manifest["version"]))
            except Exception as exc:
                prog.close()
                tk_warn(self, APP_TITLE, f"Aggiornamento non riuscito:\n{exc}")
                return
            self.closing_for_update = True
            self.uscita = True
            QTimer.singleShot(300, self.close)

        def on_fail(msg):
            prog.close()
            if msg:
                tk_warn(self, APP_TITLE, f"Aggiornamento non riuscito:\n{msg}")

        prog.canceled.connect(t.cancel)
        t.progress.connect(lambda d, tot: prog.set_progress(d, tot, f"{human_size(d)} di {human_size(tot)}"))
        t.ok.connect(on_ok)
        t.failed.connect(on_fail)
        t.start()

    def closeEvent(self, e):
        # con l'accesso non presidiato tk-desk resta acceso vicino all'orologio
        resta = self.tray is not None and not self.uscita and (self.motore.ha_password_fissa() or self._avvio())
        if resta:
            e.ignore()
            self.hide()
            if not self.settings.value("avviso_orologio", False):
                self.tray.showMessage(APP_TITLE, "tk-desk resta acceso qui per l'accesso non presidiato. "
                                                 "Per chiuderlo: tasto destro sull'icona → Esci.",
                                      QSystemTrayIcon.MessageIcon.Information, 6000)
                self.settings.setValue("avviso_orologio", True)
            return
        for w in list(self.sessioni.values()):
            w.close()
        self.motore.ferma()
        self.veglia.spegni()
        self.barra.close()
        if self.tray:
            self.tray.hide()
        e.accept()
        QApplication.instance().quit()


# ───────────────────────────────────────────── avvio
def cli_update_test(argv):
    url = argv[argv.index("--update-test") + 1]
    log = os.path.join(log_dir(), "update-test.log")

    def write(msg):
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")

    try:
        m = updater.fetch_manifest(url)
        write(f"manifest {m['version']} (installata {VERSION})")
        if not updater.is_newer(m["version"]):
            write("nessun aggiornamento")
            return 0
        asset = updater.asset_for(m)
        if asset is None:
            write(f"aggiornamento rifiutato: nessun file firmato valido per {updater.platform_key()}")
            return 2
        dest = os.path.join(updater.download_dir(), os.path.basename(asset["url"].split("?")[0]))
        updater.download(asset["url"], dest, asset.get("sha256"))
        write(f"scaricato e verificato: {dest}")
        if not is_installed():
            write("versione di sviluppo: aggiornamento non applicato")
            return 3
        updater.apply_update(dest, relaunch="--no-relaunch" not in argv, new_version=m["version"])
        write("installazione avviata")
        return 0
    except Exception as exc:
        write(f"ERRORE: {exc}")
        return 1


def _selftest(app, settings, shot):
    """Verifica del pacchetto senza rete né schermo vero: due tk-desk nello stesso processo (centralino finto,
    schermo di prova), sessione WebRTC vera, finestra principale e finestra di sessione fotografate."""
    from tkdesk.comandi import Esecutore
    from tkdesk.prova import CentralinoFinto, Imp
    from tkdesk.schermo import SorgenteFinta
    registro = open(os.path.splitext(shot)[0] + ".log", "a", encoding="utf-8", buffering=1)

    def scrivi(*a):
        registro.write(f"[{time.strftime('%H:%M:%S')}] " + " ".join(str(x) for x in a) + "\n")

    def eccezione(tipo, valore, tb):
        import traceback
        scrivi("ERRORE:", "".join(traceback.format_exception(tipo, valore, tb)))
    sys.excepthook = eccezione
    threading.excepthook = lambda a: eccezione(a.exc_type, a.exc_value, a.exc_traceback)
    scrivi("selftest avviato", sys.platform, sys.version.split()[0])
    scrivi("traduzione qt:", getattr(app, "traduzione_qt", "") or "NON TROVATA",
           "| Esci:", QApplication.translate("MAC_APPLICATION_MENU", "Quit %1"))
    from tkdesk.schermo import posizione_puntatore
    scrivi("puntatore:", posizione_puntatore())
    if IS_LINUX:
        from tkdesk.portale import e_wayland, gst_launch
        scrivi("linux: sessione", os.environ.get("XDG_SESSION_TYPE", "?"), "| wayland:", e_wayland(),
               "| gst-launch:", gst_launch() or "no", "| AppImage:", is_installed())
    try:
        import HIServices
        import Quartz
        scrivi("permessi: pyobjc ok", HIServices.AXIsProcessTrusted(), Quartz.CGPreflightScreenCaptureAccess())
    except Exception as exc:
        scrivi("permessi: pyobjc NON disponibile", repr(exc))
    try:
        import aiortc
        import av
        scrivi("aiortc", aiortc.__version__, "av", av.__version__)
    except Exception as exc:
        scrivi("import WebRTC fallito:", repr(exc))
    ospite = Motore(Imp(), sorgente_factory=SorgenteFinta, esecutore=Esecutore(finto=True), centralino=CentralinoFinto())
    # l'ospite di prova non ha una finestra: la richiesta di controllo si accetta da sola
    ospite.s.richiesta_accesso.connect(lambda rid, *_: ospite.rispondi_accesso(rid, True))
    motore = Motore(settings, centralino=CentralinoFinto())
    for nome in ("pronto", "errore_centralino", "stato_chiamata", "sessione_aperta", "sessione_chiusa"):
        getattr(motore.s, nome).connect(lambda *a, n=nome: scrivi("motore", n, *[x for x in a if not isinstance(x, bytes)]))
    for nome in ("controllato_inizio", "controllato_fine"):
        getattr(ospite.s, nome).connect(lambda *a, n=nome: scrivi("ospite", n, *a))
    win = Principale(settings, motore)
    win.resize(1000, 640)
    win.show()
    ospite.avvia()
    motore.avvia()
    stato = {"fatto": False, "inizio": time.time()}

    def collega():
        if not (ospite.id and motore.id):
            return QTimer.singleShot(200, collega)
        win.collega(ospite.id, ospite.password)

    def controlla():
        sess = next(iter(win.sessioni.values()), None)
        pronto = sess is not None and sess.video.img is not None
        if pronto or time.time() - stato["inizio"] > 50:
            img_p = win.grab()
            img_s = sess.grab() if sess is not None else QPixmap(10, 10)
            out = QPixmap(max(img_p.width(), img_s.width()), img_p.height() + img_s.height() + 10)
            out.fill(QColor("#e9edf4"))
            pt = QPainter(out)
            pt.drawPixmap(0, 0, img_p)
            pt.drawPixmap(0, img_p.height() + 10, img_s)
            pt.end()
            scrivi("fine:", "video arrivato" if pronto else "NESSUN VIDEO", f"{time.time() - stato['inizio']:.1f}s")
            if pronto:
                out.save(shot)
                with open(os.path.splitext(shot)[0] + ".txt", "w", encoding="utf-8") as fh:
                    fh.write(f"ok {sess.video.img.width()}x{sess.video.img.height()}\n")
            ospite.ferma()
            win.uscita = True
            win.close()
            return
        QTimer.singleShot(250, controlla)

    QTimer.singleShot(300, collega)
    QTimer.singleShot(1000, controlla)
    app.exec()


def main():
    argv = sys.argv[1:]
    if "--update-test" in argv:
        sys.exit(cli_update_test(argv))
    if IS_LINUX and any(a.startswith("--prova-") for a in argv):
        from tkdesk.prove_linux import esegui
        codice = esegui(argv)
        if codice is not None:
            sys.exit(codice)
    selftest = argv[argv.index("--selftest") + 1] if "--selftest" in argv else ""
    try:
        import faulthandler
        sys._tk_crash = open(os.path.join(log_dir(), "crash.log"), "a", encoding="utf-8")
        sys._tk_crash.write(f"\n== avvio {VERSION} {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        sys._tk_crash.flush()
        faulthandler.enable(sys._tk_crash, all_threads=True)
    except Exception:
        pass
    if selftest:
        import tempfile
        os.environ["TKDESK_DATA"] = tempfile.mkdtemp(prefix="tkdesk-selftest-")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)   # le sessioni e la barra sono finestre a sé: si esce solo da Principale
    app.licenza = pro.crea_licenza(VERSION)
    app.setApplicationName(APP_TITLE)
    if IS_LINUX:
        app.setDesktopFileName(util.LINUX_DESKTOP_ID)   # Wayland: la barra delle applicazioni trova l'icona dal .desktop
        from tkdesk.tk_linux_qt import instrada_link
        instrada_link(app)  # link e cartelle con l'ambiente del sistema, non con quello del pacchetto
    app.setStyle("Fusion")
    from tkdesk.tk_licenza_qt import stile_caselle_globale
    app.setStyleSheet(STYLE_DESK + stile_caselle_globale())
    import PySide6
    from PySide6.QtCore import QLibraryInfo, QTranslator
    # traduzioni di Qt (menu dell'app sul Mac, finestre dei file, menu del testo): prima di creare le finestre
    tr = QTranslator(app)
    app.traduzione_qt = ""
    cartelle = [os.path.join(os.path.dirname(PySide6.__file__), "translations"),
                os.path.join(os.path.dirname(PySide6.__file__), "Qt", "translations"),
                QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)]
    if getattr(sys, "_MEIPASS", ""):
        cartelle += [os.path.join(sys._MEIPASS, "PySide6", "Qt", "translations"),
                     os.path.join(sys._MEIPASS, "PySide6", "translations")]
    for folder in cartelle:
        if tr.load("qtbase_it", folder):
            app.installTranslator(tr)
            app.traduzione_qt = folder
            break
    if IS_WIN:
        app.setFont(QFont("Segoe UI", 10))
    settings = Settings()
    if selftest:
        _selftest(app, settings, selftest)
        return
    util.pulisci_in_arrivo()
    motore = Motore(settings)
    win = Principale(settings, motore)
    lic = app.licenza
    # chi ha già visto il benvenuto di una versione di prima ha già acconsentito al centralino
    gia_visto = bool(settings.value("welcome_ok", False)) or bool(lic is not None and lic.ricordo("benvenuto_agpl"))
    if "--in-sottofondo" in argv and win.tray is not None:
        # parte vicino all'orologio, pronto per l'accesso non presidiato; il benvenuto nuovo arriva quando si apre
        if gia_visto:
            win.avvia_rete()
    else:
        win.show()
        if gia_visto and motore.ha_password_fissa():
            win.avvia_rete()   # accesso non presidiato: subito, anche se il benvenuto nuovo aspetta qualcuno davanti
        QTimer.singleShot(300, win.primo_avvio)   # nessuna rete prima della risposta al benvenuto
    if IS_MAC:
        QTimer.singleShot(2500, lambda: win._permessi_mac(False))
    sys.exit(app.exec())
