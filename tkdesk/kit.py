"""Kit grafico di tk-desk: colori, stile, icone disegnate, card, finestre nel nostro stile, aggiornamenti.
Ripreso da tk-iscrizioni (stesso aspetto in tutti i software TK): cambia solo l'accento, verde smeraldo."""
import html
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QDialog, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLayout, QProgressBar,
                               QPushButton, QVBoxLayout)

from tkdesk import APP_TITLE, AUTHOR, AUTHOR_URL, PRIVACY_URL, TERMS_URL, URL_SORGENTE, VERSION, pro, updater
from tkdesk.util import IS_WIN, cartella_licenze, create_desktop_shortcut, data_dir

NAVY = "#0f172a"
NAVY_2 = "#1e293b"
NAVY_3 = "#334155"
ACCENT = "#059669"
ACCENT_D = "#047857"
ACCENT_L = "#d1fae5"
ACCENT_2 = "#10b981"
GRAY_50 = "#f8fafc"
GRAY_100 = "#f1f5f9"
GRAY_200 = "#e2e8f0"
GRAY_300 = "#cbd5e1"
GRAY_400 = "#94a3b8"
GRAY_500 = "#64748b"
GREEN = "#16a34a"
RED = "#dc2626"

STYLE = f"""
QMainWindow {{ background:#e9edf4; }}
QWidget {{ font-size:13px; color:{NAVY}; }}
QWidget#canvas {{ background:transparent; }}
QScrollArea {{ background:transparent; border:0; }}
QFrame#header {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {NAVY},stop:1 #1b2a4a); border-radius:16px; }}
QFrame#card {{ background:#ffffff; border-radius:16px; }}
QFrame#tile {{ background:#ffffff; border-radius:14px; }}
QLabel#brand {{ color:#fff; font-size:19px; font-weight:800; }}
QLabel#ver {{ color:{GRAY_300}; font-size:11px; }}
QLabel#cardtitle {{ color:{NAVY}; font-size:12px; font-weight:800; letter-spacing:1.5px; }}
QLabel#hint {{ color:{GRAY_500}; font-size:12px; }}
QLabel#field {{ color:{GRAY_500}; font-size:11px; font-weight:700; }}
QLabel#icobox {{ background:{ACCENT_L}; border-radius:10px; }}
QLabel#tilenum {{ font-size:26px; font-weight:800; color:{NAVY}; }}
QLabel#tilelab {{ font-size:11px; font-weight:700; color:{GRAY_500}; letter-spacing:.5px; }}
QLabel#bigname {{ font-size:22px; font-weight:800; color:{NAVY}; }}
QPushButton {{ background:#fff; border:1px solid {GRAY_300}; border-radius:10px; padding:0 14px; min-height:36px; color:{NAVY}; font-weight:600; }}
QPushButton:hover {{ background:{GRAY_100}; border-color:{GRAY_400}; }}
QPushButton:disabled {{ color:{GRAY_300}; background:{GRAY_50}; }}
QPushButton#ghost {{ background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.14); color:#fff; }}
QPushButton#ghost:hover {{ background:rgba(255,255,255,.18); }}
QPushButton#accent {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {ACCENT_2},stop:1 {ACCENT_D}); border:0; color:#fff; font-weight:800; padding:0 18px; }}
QPushButton#accent:hover {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #34d399,stop:1 {ACCENT}); }}
QPushButton#accent:disabled {{ background:{GRAY_300}; color:#fff; }}
QPushButton#mini {{ min-width:32px; max-width:32px; min-height:32px; padding:0; border-radius:9px; }}
QPushButton#chip {{ background:{GRAY_100}; border:1px solid {GRAY_200}; border-radius:15px; min-height:30px; padding:0 12px; color:{NAVY_3}; }}
QPushButton#chip:hover {{ background:{GRAY_200}; }}
QPushButton#chip:checked {{ background:{NAVY}; border-color:{NAVY}; color:#fff; }}
QPushButton#seg {{ background:#fff; border:1px solid {GRAY_200}; border-radius:10px; min-height:34px; padding:0 8px; font-size:12px; }}
QPushButton#seg:checked {{ background:{NAVY}; border-color:{NAVY}; color:#fff; }}
QPushButton#link {{ background:transparent; border:0; color:{ACCENT_D}; font-weight:700; padding:0; min-height:22px; text-align:left; }}
QPushButton#link:hover {{ text-decoration:underline; }}
QFrame#acct {{ background:{GRAY_50}; border:1px solid {GRAY_200}; border-radius:12px; }}
QLineEdit {{ background:{GRAY_50}; border:1px solid {GRAY_200}; border-radius:10px; padding:0 12px; min-height:36px; selection-background-color:{ACCENT}; }}
QLineEdit:focus {{ background:#fff; border:1px solid {ACCENT}; }}
QCheckBox {{ color:{NAVY_3}; spacing:8px; }}
QTableView {{ background:#fff; border:0; gridline-color:transparent; selection-background-color:{ACCENT_L}; selection-color:{NAVY}; outline:0; alternate-background-color:{GRAY_50}; }}
QTableView::item {{ padding:0 8px; border-bottom:1px solid {GRAY_100}; }}
QHeaderView::section {{ background:{NAVY}; border:0; padding:8px; color:#fff; font-size:11px; font-weight:800; }}
QHeaderView::section:first {{ border-top-left-radius:10px; }}
QHeaderView::section:last {{ border-top-right-radius:10px; }}
QScrollBar:vertical {{ background:transparent; width:12px; margin:2px; }}
QScrollBar::handle:vertical {{ background:{GRAY_300}; border-radius:5px; min-height:30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height:0; width:0; }}
QScrollBar:horizontal {{ height:0; }}
QStatusBar {{ background:transparent; color:{GRAY_500}; }}
QProgressBar#scan {{ background:{GRAY_200}; border:0; border-radius:4px; max-height:8px; }}
QProgressBar#scan::chunk {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {NAVY},stop:1 {ACCENT}); border-radius:4px; }}
QToolTip {{ background:{NAVY}; color:#fff; border:0; padding:5px 8px; }}
QDialog#tk {{ background:transparent; }}
QFrame#tkcard {{ background:{NAVY}; border-radius:20px; border:1px solid {NAVY_3}; }}
QDialog#tk QLabel {{ color:#fff; }}
QDialog#tk QLabel#asub {{ color:{GRAY_300}; }}
QDialog#tk QLabel#err {{ color:#fca5a5; font-weight:600; }}
QDialog#tk QLabel#afield {{ color:{GRAY_300}; font-size:11px; font-weight:700; }}
QDialog#tk QFrame#acard {{ background:{NAVY_2}; border-radius:14px; }}
QDialog#tk QLabel#atitle {{ color:#6ee7b7; font-size:11px; font-weight:800; letter-spacing:1.5px; }}
QDialog#tk QLineEdit, QDialog#tk QComboBox {{ background:{NAVY_2}; border:1px solid {NAVY_3}; color:#fff; border-radius:10px; padding:0 12px; min-height:38px; selection-background-color:{ACCENT}; }}
QDialog#tk QLineEdit:focus, QDialog#tk QComboBox:focus {{ border-color:{ACCENT_2}; }}
QDialog#tk QComboBox::drop-down {{ border:0; width:28px; }}
QDialog#tk QComboBox QAbstractItemView {{ background:{NAVY_2}; color:#fff; selection-background-color:{ACCENT}; border:1px solid {NAVY_3}; }}
QDialog#tk QProgressBar {{ background:{NAVY_2}; border:0; border-radius:5px; }}
QDialog#tk QProgressBar::chunk {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {ACCENT},stop:1 #34d399); border-radius:5px; }}
QDialog#tk QPushButton#link {{ color:#6ee7b7; }}
"""


# ---------------------------------------------------------------- icone e grafica
def ic(name, color="#ffffff", size=20):
    """Icone a tratto disegnate a mano (niente emoji)."""
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size * 2 / 24, size * 2 / 24)
    pen = QPen(QColor(color), 2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    L = lambda *a: p.drawLine(QPointF(a[0], a[1]), QPointF(a[2], a[3]))
    R = lambda x, y, w, h, r=2: p.drawRoundedRect(QRectF(x, y, w, h), r, r)

    def poly(*pts):
        path = QPainterPath(QPointF(*pts[0]))
        for pt in pts[1:]:
            path.lineTo(QPointF(*pt))
        p.drawPath(path)

    if name == "plus":
        L(12, 5, 12, 19); L(5, 12, 19, 12)
    elif name == "mail":
        R(3, 5, 18, 14, 3); poly((4, 7), (12, 13), (20, 7))
    elif name == "refresh":
        p.drawArc(QRectF(4, 4, 16, 16), 40 * 16, 270 * 16); poly((17, 3), (19, 8), (14, 9))
    elif name == "info":
        p.drawEllipse(QPointF(12, 12), 9, 9); L(12, 11, 12, 17); L(12, 7.5, 12, 7.6)
    elif name == "trash":
        L(5, 7, 19, 7); R(7, 7, 10, 13); poly((9, 7), (9, 4), (15, 4), (15, 7)); L(10, 11, 10, 17); L(14, 11, 14, 17)
    elif name == "export":
        L(12, 4, 12, 15); poly((7, 10), (12, 15), (17, 10)); poly((4, 15), (4, 20), (20, 20), (20, 15))
    elif name == "heart":
        path = QPainterPath(QPointF(12, 20))
        path.cubicTo(QPointF(2, 13), QPointF(3, 4), QPointF(12, 8))
        path.cubicTo(QPointF(21, 4), QPointF(22, 13), QPointF(12, 20))
        p.drawPath(path)
    elif name == "search":
        p.drawEllipse(QPointF(10.5, 10.5), 6.5, 6.5); L(15.5, 15.5, 20, 20)
    elif name == "globe":
        p.drawEllipse(QPointF(12, 12), 9, 9); L(3, 12, 21, 12); p.drawEllipse(QPointF(12, 12), 4, 9)
    elif name == "unsub":
        R(3, 5, 18, 14, 3); poly((4, 7), (12, 13), (20, 7)); L(15, 3, 21, 9); L(21, 3, 15, 9)
    elif name == "user-x":
        p.drawEllipse(QPointF(9, 8), 4, 4); poly((2, 20), (3, 15), (9, 13), (14, 15), (15, 18)); L(16, 9, 21, 14); L(21, 9, 16, 14)
    elif name == "alert":
        poly((12, 3), (22, 20), (2, 20), (12, 3)); L(12, 10, 12, 14); L(12, 17, 12, 17.1)
    elif name == "help":
        p.drawEllipse(QPointF(12, 12), 9, 9); L(12, 17, 12, 17.1); p.drawArc(QRectF(9, 7, 6, 6), 120 * 16, -250 * 16)
    elif name == "lock":
        R(5, 11, 14, 10, 3); p.drawArc(QRectF(8, 4, 8, 12), 0, 180 * 16); L(8, 10, 8, 11); L(16, 10, 16, 11)
    elif name == "check":
        poly((5, 12), (10, 17), (19, 7))
    elif name == "stop":
        R(6, 6, 12, 12, 2)
    elif name == "eye":
        path = QPainterPath(QPointF(2, 12))
        path.quadTo(QPointF(12, 2), QPointF(22, 12)); path.quadTo(QPointF(12, 22), QPointF(2, 12))
        p.drawPath(path); p.drawEllipse(QPointF(12, 12), 3, 3)
    elif name == "doc":
        poly((6, 3), (14, 3), (19, 8), (19, 21), (6, 21), (6, 3)); poly((14, 3), (14, 8), (19, 8))
    elif name == "monitor":
        R(3, 4, 18, 12, 2); L(12, 16, 12, 20); L(8, 20, 16, 20)
    elif name == "copy":
        R(8, 8, 12, 12, 2); poly((16, 8), (16, 4), (4, 4), (4, 16), (8, 16))
    elif name == "key":
        p.drawEllipse(QPointF(8, 12), 4, 4); L(12, 12, 21, 12); L(18, 12, 18, 15); L(21, 12, 21, 15)
    elif name == "book":
        R(5, 3, 14, 18, 2); L(9, 3, 9, 21); L(12, 8, 16, 8); L(12, 12, 16, 12)
    elif name == "chat":
        R(3, 4, 18, 13, 3); poly((8, 17), (7, 21), (12, 17))
    elif name == "file":
        poly((6, 3), (14, 3), (19, 8), (19, 21), (6, 21), (6, 3)); L(12.5, 10, 12.5, 17); poly((9.5, 13), (12.5, 10), (15.5, 13))
    elif name == "record":
        p.drawEllipse(QPointF(12, 12), 8, 8); p.setBrush(QColor(color)); p.drawEllipse(QPointF(12, 12), 3.5, 3.5)
    elif name == "full":
        poly((4, 9), (4, 4), (9, 4)); poly((15, 4), (20, 4), (20, 9)); poly((20, 15), (20, 20), (15, 20)); poly((9, 20), (4, 20), (4, 15))
    elif name == "close":
        L(6, 6, 18, 18); L(18, 6, 6, 18)
    elif name == "gear":
        import math
        p.drawEllipse(QPointF(12, 12), 3.2, 3.2)
        for k in range(8):
            a = k * math.pi / 4
            L(12 + 6.5 * math.cos(a), 12 + 6.5 * math.sin(a), 12 + 9 * math.cos(a), 12 + 9 * math.sin(a))
        p.drawEllipse(QPointF(12, 12), 6.5, 6.5)
    elif name == "link":
        p.drawArc(QRectF(3, 8, 10, 8), 90 * 16, 180 * 16); p.drawArc(QRectF(11, 8, 10, 8), -90 * 16, 180 * 16); L(8, 12, 16, 12)
    elif name == "power":
        p.drawArc(QRectF(5, 5, 14, 14), 120 * 16, 300 * 16); L(12, 3, 12, 11)
    elif name == "phone":
        path = QPainterPath(QPointF(5, 4))
        path.lineTo(QPointF(9, 4)); path.lineTo(QPointF(11, 9)); path.lineTo(QPointF(8.5, 10.5))
        path.cubicTo(QPointF(9.5, 12.5), QPointF(11.5, 14.5), QPointF(13.5, 15.5))
        path.lineTo(QPointF(15, 13)); path.lineTo(QPointF(20, 15)); path.lineTo(QPointF(20, 19))
        path.cubicTo(QPointF(20, 20), QPointF(19, 21), QPointF(18, 21))
        path.cubicTo(QPointF(10, 20), QPointF(4, 14), QPointF(3, 6))
        path.cubicTo(QPointF(3, 5), QPointF(4, 4), QPointF(5, 4))
        p.drawPath(path)
    elif name == "dot":
        p.setBrush(QColor(color)); p.drawEllipse(QPointF(12, 12), 5, 5)
    elif name == "microsoft":
        p.setPen(Qt.PenStyle.NoPen)
        for (x, y, c) in ((3, 3, "#f25022"), (12.5, 3, "#7fba00"), (3, 12.5, "#00a4ef"), (12.5, 12.5, "#ffb900")):
            p.setBrush(QColor(c)); p.drawRect(QRectF(x, y, 8.5, 8.5))
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


def render_icon(size=64):
    """Logo di tk-desk: quadrato navy, schermo bianco con il piede e la freccia del mouse verde smeraldo."""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor("#1e293b"))
    g.setColorAt(1, QColor(NAVY))
    p.setBrush(QBrush(g))
    p.drawRoundedRect(0, 0, size, size, size * 0.24, size * 0.24)
    # schermo
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(QRectF(size * .14, size * .2, size * .72, size * .48), size * .06, size * .06)
    p.setBrush(QColor(NAVY_2))
    p.drawRoundedRect(QRectF(size * .19, size * .25, size * .62, size * .38), size * .03, size * .03)
    # piede
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(QRectF(size * .44, size * .68, size * .12, size * .08), size * .01, size * .01)
    p.drawRoundedRect(QRectF(size * .32, size * .75, size * .36, size * .06), size * .03, size * .03)
    # freccia del mouse
    path = QPainterPath(QPointF(size * .42, size * .3))
    for x, y in ((.42, .58), (.49, .51), (.54, .62), (.59, .6), (.54, .49), (.64, .49)):
        path.lineTo(QPointF(size * x, size * y))
    path.closeSubpath()
    p.setBrush(QColor(ACCENT_2))
    pen = QPen(QColor("#ffffff"), max(1.0, size * .02))
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawPath(path)
    p.end()
    return QPixmap.fromImage(img)


def shadow(widget, blur=30, dy=6, alpha=45):
    e = QGraphicsDropShadowEffect(widget)
    e.setBlurRadius(blur)
    e.setOffset(0, dy)
    e.setColor(QColor(15, 23, 42, alpha))
    widget.setGraphicsEffect(e)


def text_btn(icon_name, text, fn, color="#ffffff", name="ghost", tip=""):
    b = QPushButton(text)
    b.setObjectName(name)
    if icon_name:
        b.setIcon(ic(icon_name, color, 18))
        b.setIconSize(QSize(18, 18))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if tip:
        b.setToolTip(tip)
    b.clicked.connect(fn)
    return b


def mini_btn(icon_name, tip, fn, color=NAVY):
    b = QPushButton()
    b.setObjectName("mini")
    b.setIcon(ic(icon_name, color, 16))
    b.setIconSize(QSize(16, 16))
    b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(fn)
    return b


class Card(QFrame):
    def __init__(self, icon_name, title):
        super().__init__()
        self.setObjectName("card")
        shadow(self, 26, 5, 38)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(18, 16, 18, 18)
        self.lay.setSpacing(10)
        head = QHBoxLayout()
        box = QLabel(objectName="icobox")
        box.setFixedSize(32, 32)
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.setPixmap(ic(icon_name, ACCENT, 17).pixmap(17, 17))
        head.addWidget(box)
        head.addSpacing(4)
        head.addWidget(QLabel(title.upper(), objectName="cardtitle"))
        head.addStretch(1)
        self.head = head
        self.lay.addLayout(head)


def fmt_date(ts, with_time=False):
    if not ts:
        return "—"
    return time.strftime("%d/%m/%Y %H:%M" if with_time else "%d/%m/%Y", time.localtime(ts))


def open_url(url):
    QDesktopServices.openUrl(QUrl(url))


# ---------------------------------------------------------------- finestre nel nostro stile
class TkDialog(QDialog):
    """Scheda navy arrotondata con ombra, senza la barra di sistema."""

    def __init__(self, parent, width=460):
        super().__init__(parent)
        self.setObjectName("tk")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 34)
        # la finestra segue sempre il contenuto (testi che vanno a capo, campi che compaiono)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        self.card = QFrame(objectName="tkcard")
        self.card.setFixedWidth(width)
        shadow(self.card, 44, 12, 110)
        outer.addWidget(self.card)
        self.body = QVBoxLayout(self.card)
        self.body.setContentsMargins(26, 24, 26, 24)
        self.body.setSpacing(12)
        self._drag = None

    # tk-desk: mentre questo computer è controllato le finestre non compaiono nello schermo trasmesso
    nascondi_dalla_cattura = False

    def showEvent(self, e):
        super().showEvent(e)
        if TkDialog.nascondi_dalla_cattura:
            from tkdesk.util import nascondi_dalla_cattura
            nascondi_dalla_cattura(self)

    def head(self, icon_pixmap, title, sub=""):
        row = QHBoxLayout()
        row.setSpacing(14)
        ico = QLabel()
        ico.setPixmap(icon_pixmap)
        ico.setAlignment(Qt.AlignmentFlag.AlignTop)
        row.addWidget(ico)
        col = QVBoxLayout()
        col.setSpacing(3)
        t = QLabel(title)
        t.setWordWrap(True)
        t.setStyleSheet("font-size:20px; font-weight:800; color:#ffffff;")
        col.addWidget(t)
        if sub:
            s = QLabel(sub)
            s.setObjectName("asub")
            s.setWordWrap(True)
            col.addWidget(s)
        row.addLayout(col, 1)
        self.body.addLayout(row)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None


def _kind_icon(kind):
    names = {"info": ("info", "#7dd3fc"), "warn": ("alert", "#fbbf24"), "ask": ("help", "#6ee7b7"),
             "ok": ("check", "#86efac")}
    name, color = names[kind]
    box = QPixmap(52, 52)
    box.fill(Qt.GlobalColor.transparent)
    p = QPainter(box)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 22))
    p.drawRoundedRect(0, 0, 52, 52, 16, 16)
    p.drawPixmap(10, 10, ic(name, color, 32).pixmap(32, 32))
    p.end()
    return box


def tk_choice(parent, title, text, buttons, kind="ask", sub=""):
    """Domanda con più pulsanti [(testo, 'accent'|'ghost')]. Ritorna l'indice scelto (-1 se chiusa)."""
    dlg = TkDialog(parent, 440)
    dlg.head(_kind_icon(kind), title, sub)
    if text:
        lab = QLabel(text)
        lab.setWordWrap(True)
        lab.setTextFormat(Qt.TextFormat.PlainText)
        lab.setStyleSheet("font-size:14px; color:#e2e8f0;")
        dlg.body.addWidget(lab)
    row = QHBoxLayout()
    row.setSpacing(8)
    row.addStretch(1)
    result = {"i": -1}
    for i, (label, style) in enumerate(buttons):
        b = QPushButton(label)
        b.setObjectName(style)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda _=False, k=i: (result.__setitem__("i", k), dlg.accept()))
        if style == "accent":
            b.setDefault(True)
        row.addWidget(b)
    dlg.body.addLayout(row)
    dlg.exec()
    return result["i"]


def tk_info(parent, title, text, kind="info"):
    tk_choice(parent, title, text, [("OK", "accent")], kind)


def tk_warn(parent, title, text):
    tk_choice(parent, title, text, [("OK", "accent")], "warn")


class UpdateDialog(TkDialog):
    def __init__(self, parent, manifest):
        super().__init__(parent, 460)
        self.choice = "later"
        self.head(render_icon(56), f"È disponibile {APP_TITLE} {manifest['version']}",
                  f"Stai usando la versione {VERSION}" +
                  (f" · pubblicata il {manifest['date']}" if manifest.get("date") else ""))
        notes = manifest.get("notes") or []
        if isinstance(notes, str):
            notes = [notes]
        if notes:
            card = QFrame(objectName="acard")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 12)
            cl.setSpacing(4)
            cl.addWidget(QLabel("NOVITÀ", objectName="atitle"))
            for n in notes:
                lab = QLabel("•  " + str(n))
                lab.setWordWrap(True)
                lab.setStyleSheet("font-size:13px; font-weight:600;")
                cl.addWidget(lab)
            self.body.addWidget(card)
        row = QHBoxLayout()
        row.setSpacing(8)
        for label, value in (("Salta questa versione", "skip"), ("Più tardi", "later")):
            b = QPushButton(label)
            b.setObjectName("ghost")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, v=value: self._done(v))
            row.addWidget(b)
        row.addStretch(1)
        go = text_btn("refresh", "Aggiorna ora", lambda: self._done("go"), "#fff", "accent")
        go.setDefault(True)
        row.addWidget(go)
        self.body.addLayout(row)

    def _done(self, value):
        self.choice = value
        self.accept()


class TkProgress(TkDialog):
    canceled = Signal()

    def __init__(self, parent, title, sub, cancelable=False):
        super().__init__(parent, 420)
        self.head(render_icon(56), title, sub)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        self.bar.setRange(0, 0)
        self.body.addWidget(self.bar)
        self.status = QLabel("")
        self.status.setObjectName("asub")
        self.body.addWidget(self.status)
        if cancelable:
            row = QHBoxLayout()
            row.addStretch(1)
            b = QPushButton("Annulla")
            b.setObjectName("ghost")
            b.clicked.connect(lambda: (self.canceled.emit(), self.close()))
            row.addWidget(b)
            self.body.addLayout(row)

    def set_progress(self, done, total, text=""):
        if total > 0:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(done * 1000 / total))
        self.status.setText(text)

    def keyPressEvent(self, e):
        if e.key() != Qt.Key.Key_Escape:
            super().keyPressEvent(e)


def _info_card(title, body):
    card = QFrame(objectName="acard")
    cl = QVBoxLayout(card)
    cl.setContentsMargins(16, 12, 16, 12)
    cl.setSpacing(3)
    cl.addWidget(QLabel(title, objectName="atitle"))
    v = QLabel(body)
    v.setWordWrap(True)
    v.setStyleSheet("font-size:13px; font-weight:600;")
    cl.addWidget(v)
    return card


# Avviso antitruffa: nel benvenuto, sotto ID e password e nella finestra «Accetta / Rifiuta»
ANTITRUFFA = ("Non dare mai ID e password a chi ti chiama o ti scrive dicendo di essere un tecnico, la banca o "
              "la polizia. Usa tk-desk solo con persone che conosci.")


def righe_benvenuto(nome):
    """Righe di tk-desk nella finestra di benvenuto comune (una sola finestra al primo avvio)."""
    nome = html.escape(nome or "questo computer")
    return [
        f"<b style='color:#fbbf24'>Attenzione alle truffe.</b> {ANTITRUFFA} A ogni collegamento decidi tu con "
        "«Accetta» o «Rifiuta».",
        f"<b>Cosa va in rete.</b> Il centralino su pietrodefilippis.it (codice casuale e nome «{nome}», lo cambi "
        "nelle Impostazioni), i server STUN di Google per il collegamento diretto e il controllo degli "
        "aggiornamenti. Schermo, file e chat vanno diretti e cifrati da un computer all'altro.",
    ]


class AboutDialog(TkDialog):
    def __init__(self, win):
        super().__init__(win, 460)
        self.check = False
        top = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(render_icon(72))
        top.addWidget(icon)
        top.addSpacing(10)
        col = QVBoxLayout()
        t = QLabel(APP_TITLE)
        t.setStyleSheet("font-size:24px; font-weight:800; color:#fff;")
        col.addWidget(t)
        s = QLabel("Controllo remoto e assistenza:\nschermo, mouse, tastiera, file e chat.")
        s.setObjectName("asub")
        col.addWidget(s)
        top.addLayout(col, 1)
        self.body.addLayout(top)
        for title, body in (("VERSIONE", f"{VERSION} · tutte le funzioni, gratis"),
                            ("LICENZA", "Software libero · AGPL-3.0"),
                            ("SVILUPPATORE", f"{AUTHOR} · {AUTHOR_URL.split('//')[1]}"),
                            ("IMPOSTAZIONI E RUBRICA", html.escape(data_dir()))):
            self.body.addWidget(_info_card(title, body))
        self.body.addWidget(text_btn("refresh", "Controlla aggiornamenti", self._check, "#fff", "accent"))
        self.body.addWidget(text_btn("doc", "Licenze e codice sorgente", self._licenze))
        row = QHBoxLayout()
        row.setSpacing(8)
        caffe = pro.pulsante_caffe("ghost")  # ambra, uguale in tutti i software
        if caffe is not None:
            row.addWidget(caffe, 1)
        if IS_WIN:
            row.addWidget(text_btn("doc", "Icona sul Desktop", self._shortcut), 1)
        row.addWidget(text_btn("", "Chiudi", self.accept), 1)
        self.body.addLayout(row)
        links = QHBoxLayout()
        links.addStretch(1)
        for label, url in (("Termini e condizioni", TERMS_URL), ("Privacy", PRIVACY_URL),
                           ("Contatti", AUTHOR_URL + "/contatti/")):
            b = QPushButton(label)
            b.setObjectName("link")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, u=url: open_url(u))
            links.addWidget(b)
        links.addStretch(1)
        self.body.addLayout(links)

    def _shortcut(self):
        try:
            path = create_desktop_shortcut()
        except Exception as exc:
            tk_warn(self.parent(), APP_TITLE, f"Non riesco a creare l'icona sul Desktop:\n{exc}")
            return
        tk_info(self.parent(), APP_TITLE, f"Icona creata sul Desktop:\n{path}", "ok")

    def _check(self):
        self.check = True
        self.accept()

    def _licenze(self):
        from tkdesk.tk_licenza_qt import LicenzeDialog
        LicenzeDialog(APP_TITLE, VERSION, URL_SORGENTE, cartella_licenze(), self).exec()


# ---------------------------------------------------------------- lavori in sottofondo
class Worker(QThread):
    """Esegue fn() in un thread: done(risultato) oppure failed(messaggio)."""
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn())
        except Exception as exc:
            self.failed.emit(str(exc) or exc.__class__.__name__)


class DownloadThread(QThread):
    progress = Signal(float, float)
    ok = Signal(str)
    failed = Signal(str)

    def __init__(self, url, dest, sha256, parent=None):
        super().__init__(parent)
        self.url, self.dest, self.sha256 = url, dest, sha256
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            updater.download(self.url, self.dest, self.sha256,
                             lambda d, t: self.progress.emit(float(d), float(t)), lambda: self._cancel)
            self.ok.emit(self.dest)
        except InterruptedError:
            self.failed.emit("")
        except Exception as exc:
            self.failed.emit(str(exc))
