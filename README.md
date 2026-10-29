<!-- README generato da Dropbox/CLAUDE/dev/agpl-rollout/readme/genera_readme.py: modificare lì -->
<div align="center">

<img src="docs/vetrina.png" alt="tk-desk: Assistenza remota semplice e sicura. Decide sempre chi sta al computer." width="100%">

<br><br>

<a href="https://pietrodefilippis.it/scarica-programma/tk-desk/windows/"><img alt="Scarica per Windows" src="https://img.shields.io/badge/%E2%AC%87%20%20Windows-scarica%20gratis-0078D4?style=for-the-badge&logo=windows&logoColor=white"></a> &nbsp; <a href="https://pietrodefilippis.it/scarica-programma/tk-desk/mac/"><img alt="Scarica per macOS" src="https://img.shields.io/badge/%E2%AC%87%20%20macOS-scarica%20gratis-111111?style=for-the-badge&logo=apple&logoColor=white"></a> &nbsp; <a href="https://pietrodefilippis.it/donazione/"><img alt="Offrimi un caffè" src="https://img.shields.io/badge/%E2%98%95%20%20Offrimi%20un%20caff%C3%A8-facoltativo-f59e0b?style=for-the-badge"></a>

<br><br>

<a href="COPYING"><img alt="Licenza AGPL-3.0" src="https://img.shields.io/badge/licenza-AGPL--3.0-16a34a?style=for-the-badge"></a> <img alt="Windows" src="https://img.shields.io/badge/Windows-10%20%C2%B7%2011-0078D4?style=for-the-badge&logo=windows&logoColor=white"> <img alt="macOS" src="https://img.shields.io/badge/macOS-Intel%20%C2%B7%20Apple%20Silicon-111111?style=for-the-badge&logo=apple&logoColor=white"> <img alt="Linux" src="https://img.shields.io/badge/Linux-Ubuntu%2022.04%2B-E95420?style=for-the-badge&logo=ubuntu&logoColor=white"> <img alt="Versione" src="https://img.shields.io/github/v/tag/tecnikgeek-repo/tk-desk-desktop?label=versione&style=for-the-badge&color=059669"> <img alt="Zero pubblicità" src="https://img.shields.io/badge/pubblicit%C3%A0-zero-0f172a?style=for-the-badge">

<br>

### Assistenza remota semplice e sicura. Decide sempre chi sta al computer.

ID e password monouso da dettare al telefono, collegamento cifrato e diretto tra i due computer, conferma «Accetta» di chi riceve.

</div>

---

## ✨ Cosa fa

<table>
<tr>
<td width="50%" valign="top">

### 🖥️&nbsp; Controllo a distanza
Vedi lo schermo e usi mouse e tastiera dell'altro computer, anche con più schermi.

</td>
<td width="50%" valign="top">

### ✅&nbsp; Decidi tu
A ogni collegamento compare «Accetta / Rifiuta»: senza il tuo sì nessuno entra.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 🔑&nbsp; Password che cambia
La password monouso cambia dopo ogni sessione, da sola dopo 10 minuti e dopo i tentativi sbagliati.

</td>
<td width="50%" valign="top">

### 🛡️&nbsp; Contro le truffe
Avviso contro i finti tecnici; durante un controllo nessuno può attivare accessi permanenti.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 📁&nbsp; File, chat e voce
Invii file (da accettare), scrivi in chat, parli in chiamata e registri la sessione con avviso «REC».

</td>
<td width="50%" valign="top">

### 🏢&nbsp; Accesso non presidiato
Per i tuoi computer: password fissa, rubrica e più sessioni insieme. Tutto gratis.

</td>
</tr>
</table>

## 🖥️ Com'è fatto

<div align="center">
<img src="docs/screenshot.png" alt="tk-desk in funzione" width="100%">
</div>

## 📱 Anche sul telefono

**tk-desk** c'è anche per Android, gratis e libera come questo programma:
[tk-desk-app](https://github.com/tecnikgeek-repo/tk-desk-app).

<a href="https://github.com/tecnikgeek-repo/tk-desk-app"><img alt="tk-desk per Android" src="https://img.shields.io/badge/%F0%9F%93%B1%20%20tk--desk-per%20Android-059669?style=for-the-badge&logo=android&logoColor=white"></a>

## 🔒 I tuoi dati

Il collegamento è **cifrato e diretto** tra i due computer (WebRTC): lo schermo non passa da nessun server. Il centralino su pietrodefilippis.it serve solo a far trovare i due computer.
La password non gli arriva mai: la verificano i due computer tra loro (SPAKE2), e dai messaggi che passano dal
centralino non si ricava, nemmeno provandole tutte.

| Resta sul tuo computer | Va in rete (e perché) |
|---|---|
| Schermo, file, chat e registrazioni | Il centralino: ID, nome scelto del computer, messaggi per avviare il collegamento |
| Password fissa e rubrica, cifrate | Un server STUN di Google per trovare la strada diretta tra i due computer |
| Le impostazioni | Aggiornamenti e, solo se le accetti, statistiche anonime |

Nessuna pubblicità, nessun account da creare. Le statistiche anonime partono **solo se le accetti** al primo avvio
(si cambiano quando vuoi). Gli aggiornamenti sono **firmati digitalmente**: il programma installa solo quelli
pubblicati dall'autore.

## 📥 Installazione

- **Windows 10 / 11** — scarica l'installer `.exe` e avvialo. Non servono i permessi di amministratore.
- **macOS** (Intel o Apple Silicon) — apri il `.dmg` e trascina l'app in *Applicazioni*. Al primo avvio: clic destro sull'app → *Apri*.
- **macOS** — al primo avvio concedi *Registrazione schermo* e *Accessibilità* (Impostazioni di Sistema → Privacy e sicurezza): servono per farti controllare.
- **Linux** (Ubuntu 22.04 o più recente, x86_64, Wayland o X11) — scarica il file `.AppImage`, rendilo avviabile (Proprietà → *Esegui come programma*) e aprilo: si aggiunge da solo al menu delle applicazioni. Con Wayland, per farti controllare, il sistema chiede il permesso con la sua finestra «Condividi lo schermo».

Gli aggiornamenti arrivano da soli: quando esce una versione nuova il programma te lo propone.

<details>
<summary><b>🛠️ Avviarlo dal codice sorgente</b></summary>

<br>

Serve **Python 3.13**.

```bash
python -m venv .venv
.venv\Scripts\activate          (su macOS e Linux: source .venv/bin/activate)
pip install "pyside6-essentials==6.12.*" certifi aiortc mss pynput numpy sounddevice
# solo Linux: pip install secretstorage jeepney python-xlib
python run.py
```

Prove senza rete né schermo: `python tests/test_core.py` e `python tests/test_finestre.py`.
Pacchetti: `installer\build.ps1` (Windows), `mac/build_mac.sh` (macOS), `linux/build_linux.sh` (Linux, AppImage).
Prove su Linux dal pacchetto: `tk-desk-….AppImage --prova-portale` (cosa offre il sistema, nessuna finestra),
`--prova-cattura schermo.png` e `--prova-comandi` (la prima volta con Wayland il sistema chiede il permesso).

</details>

## 📜 Licenza

**tk-desk** è software libero: © 2026 Pietro De Filippis (TecnikGeek), licenza
**[GNU Affero General Public License v3.0](COPYING)** o successiva. Puoi usarlo, studiarlo, modificarlo e
condividerlo; è fornito **così com'è, senza alcuna garanzia**. I testi delle licenze dei componenti inclusi
(aiortc, PyAV/FFmpeg, Qt/PySide6, pynput, mss, numpy, sounddevice, Python, certifi) sono nella cartella [`licenze/`](licenze/) e nel programma, in *Informazioni → Licenze e codice
sorgente*.

> Il nome **tk-desk** e il logo non sono coperti dalla licenza (AGPL, sezione 7): una versione modificata deve
> avere un nome e un logo diversi.

---

<div align="center">

**Ti è utile?** Tutte le funzioni sono gratis per tutti. Se vuoi, un caffè aiuta a migliorarlo e a crearne altri.

<a href="https://pietrodefilippis.it/donazione/"><img alt="Offrimi un caffè" src="https://img.shields.io/badge/%E2%98%95%20%20Offrimi%20un%20caff%C3%A8-pietrodefilippis.it-f59e0b?style=for-the-badge"></a>

<sub>Creato da <a href="https://pietrodefilippis.it">Pietro De Filippis · TecnikGeek</a> — Webmaster & UX/UI Designer</sub>

</div>
