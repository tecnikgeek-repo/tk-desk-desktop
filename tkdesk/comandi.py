"""Mouse e tastiera: dal computer che controlla (eventi Qt → messaggi) al computer controllato (messaggi → sistema).

Messaggi (JSON nel canale dati):
  {"t":"mm","x":0..1,"y":0..1}                 mouse spostato (coordinate relative allo schermo condiviso)
  {"t":"mb","b":"l|r|m","d":1|0,"x":..,"y":..} tasto del mouse giù/su
  {"t":"mw","dx":n,"dy":n}                     rotella (scatti)
  {"t":"k","k":nome,"d":1|0}                   tasto speciale o lettera con Ctrl/Cmd (giù/su)
  {"t":"c","c":"à"}                            carattere da scrivere così com'è (lettere, accenti, simboli)

Ctrl e Cmd: Qt su Mac scambia i nomi (il tasto Cmd arriva come Control). Per questo il computer che controlla
manda i nomi di Qt («ctrl», «meta») e quello controllato li traduce per il suo sistema: su Mac ctrl → Cmd e
meta → Control, su Windows ctrl → Ctrl e meta → tasto Windows. Così Cmd+C da un Mac fa Ctrl+C su Windows.
"""
import sys

from PySide6.QtCore import Qt

SPECIALI = {
    Qt.Key.Key_Return: "enter", Qt.Key.Key_Enter: "enter", Qt.Key.Key_Escape: "esc", Qt.Key.Key_Tab: "tab",
    Qt.Key.Key_Backtab: "tab", Qt.Key.Key_Backspace: "backspace", Qt.Key.Key_Delete: "delete",
    Qt.Key.Key_Insert: "insert", Qt.Key.Key_Home: "home", Qt.Key.Key_End: "end", Qt.Key.Key_PageUp: "page_up",
    Qt.Key.Key_PageDown: "page_down", Qt.Key.Key_Left: "left", Qt.Key.Key_Right: "right", Qt.Key.Key_Up: "up",
    Qt.Key.Key_Down: "down", Qt.Key.Key_Space: "space", Qt.Key.Key_CapsLock: "caps_lock",
    Qt.Key.Key_Shift: "shift", Qt.Key.Key_Control: "ctrl", Qt.Key.Key_Alt: "alt", Qt.Key.Key_AltGr: "alt_gr",
    Qt.Key.Key_Meta: "meta", Qt.Key.Key_Print: "print_screen", Qt.Key.Key_Pause: "pause",
    Qt.Key.Key_Menu: "menu", Qt.Key.Key_NumLock: "num_lock", Qt.Key.Key_ScrollLock: "scroll_lock",
}
for _n in range(1, 21):
    SPECIALI[getattr(Qt.Key, f"Key_F{_n}")] = f"f{_n}"

MODIFICATORI = {"shift", "ctrl", "alt", "alt_gr", "meta"}


# ───────────────────────────────────────── lato di chi controlla

def da_evento_tasto(ev, giu):
    """Evento tastiera Qt → messaggio (o None se non va mandato)."""
    if ev.isAutoRepeat() and not giu:
        return None
    k = ev.key()
    if k in SPECIALI:
        return {"t": "k", "k": SPECIALI[k], "d": 1 if giu else 0}
    mods = ev.modifiers()
    con_comando = bool(mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
    # lettere e cifre con Ctrl/Cmd: si manda il tasto (Ctrl+C), non il carattere di controllo
    if con_comando and (Qt.Key.Key_A <= k <= Qt.Key.Key_Z or Qt.Key.Key_0 <= k <= Qt.Key.Key_9):
        return {"t": "k", "k": chr(k).lower(), "d": 1 if giu else 0}
    testo = ev.text()
    if giu and testo and testo.isprintable():
        return {"t": "c", "c": testo}
    return None


# ───────────────────────────────────────── lato del computer controllato

class Esecutore:
    """Esegue i messaggi sul sistema con pynput. `schermo` = {left, top, width, height} dello schermo condiviso,
    nelle stesse unità che usa pynput (pixel su Windows, punti su Mac)."""

    def __init__(self, finto=False):
        self.finto = finto
        self.registro = []            # nei test: cosa sarebbe stato fatto
        self.schermo = {"left": 0, "top": 0, "width": 1920, "height": 1080}
        self.premuti = set()
        if not finto:
            from pynput import keyboard, mouse
            self._k = keyboard
            self._m = mouse
            self.tastiera = keyboard.Controller()
            self.mouse = mouse.Controller()

    def _punto(self, x, y):
        s = self.schermo
        x = min(max(float(x), 0.0), 1.0)
        y = min(max(float(y), 0.0), 1.0)
        return int(s["left"] + x * (s["width"] - 1)), int(s["top"] + y * (s["height"] - 1))

    def _tasto(self, nome):
        if self.finto:
            return nome
        Key = self._k.Key
        mac = sys.platform == "darwin"
        traduci = {"ctrl": "cmd" if mac else "ctrl", "meta": "ctrl" if mac else "cmd", "alt_gr": "alt_gr"}
        nome = traduci.get(nome, nome)
        if len(nome) == 1:
            return self._k.KeyCode.from_char(nome)
        return getattr(Key, nome, None)

    def esegui(self, m):
        t = m.get("t")
        if t == "mm":
            p = self._punto(m.get("x", 0), m.get("y", 0))
            if self.finto:
                self.registro.append(("sposta", p))
            else:
                self.mouse.position = p
        elif t == "mb":
            if "x" in m:
                p = self._punto(m["x"], m["y"])
                if not self.finto:
                    self.mouse.position = p
            nome = {"l": "left", "r": "right", "m": "middle"}.get(m.get("b"), "left")
            if self.finto:
                self.registro.append(("clic", nome, m.get("d")))
            else:
                b = getattr(self._m.Button, nome)
                (self.mouse.press if m.get("d") else self.mouse.release)(b)
        elif t == "mw":
            dx, dy = int(m.get("dx", 0)), int(m.get("dy", 0))
            if self.finto:
                self.registro.append(("rotella", dx, dy))
            else:
                self.mouse.scroll(dx, dy)
        elif t == "k":
            nome = str(m.get("k", ""))
            tasto = self._tasto(nome)
            if tasto is None:
                return
            if self.finto:
                self.registro.append(("tasto", tasto, m.get("d")))
                return
            if m.get("d"):
                self.tastiera.press(tasto)
                self.premuti.add(tasto)
            else:
                self.tastiera.release(tasto)
                self.premuti.discard(tasto)
        elif t == "c":
            c = str(m.get("c", ""))[:64]
            if self.finto:
                self.registro.append(("scrivi", c))
            else:
                self.tastiera.type(c)

    def rilascia_tutto(self):
        """A fine sessione nessun tasto resta premuto (Ctrl bloccato sul computer di un cliente è un disastro)."""
        if self.finto:
            self.premuti.clear()
            return
        for t in list(self.premuti):
            try:
                self.tastiera.release(t)
            except Exception:
                pass
        self.premuti.clear()
