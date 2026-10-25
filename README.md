<!-- README generato da Dropbox/CLAUDE/dev/agpl-rollout/readme/genera_readme.py: modificare lì -->
<div align="center">

<img src="docs/logo.png" width="120" alt="tk-desk">

# tk-desk

### Assistenza remota semplice e sicura. Decide sempre chi sta al computer.

ID e password monouso da dettare al telefono, collegamento cifrato e diretto tra i due computer, conferma «Accetta» di chi riceve.

<a href="COPYING"><img alt="Licenza AGPL-3.0" src="https://img.shields.io/badge/licenza-AGPL--3.0-16a34a?style=for-the-badge"></a> <img alt="Windows" src="https://img.shields.io/badge/Windows-10%20%C2%B7%2011-0078D4?style=for-the-badge&logo=windows&logoColor=white"> <img alt="macOS" src="https://img.shields.io/badge/macOS-Intel%20%C2%B7%20Apple%20Silicon-111111?style=for-the-badge&logo=apple&logoColor=white"> <img alt="Versione" src="https://img.shields.io/github/v/tag/tecnikgeek-repo/tk-desk-desktop?label=versione&style=for-the-badge&color=059669"> <img alt="Gratis" src="https://img.shields.io/badge/prezzo-gratis-f59e0b?style=for-the-badge">

<br>

<a href="https://pietrodefilippis.it/software/"><img alt="Scarica" src="https://img.shields.io/badge/%E2%AC%87%20%20Scarica-gratis-059669?style=for-the-badge"></a> &nbsp; <a href="https://pietrodefilippis.it/donazione/"><img alt="Offrimi un caffè" src="https://img.shields.io/badge/%E2%98%95%20%20Offrimi%20un%20caff%C3%A8-facoltativo-f59e0b?style=for-the-badge"></a>

<br><br>

<img src="docs/screenshot.png" alt="tk-desk in funzione" width="920">

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

## 🔒 I tuoi dati

Il collegamento è **cifrato e diretto** tra i due computer (WebRTC): lo schermo non passa da nessun server. Il centralino su pietrodefilippis.it serve solo a far trovare i due computer.

| Resta sul tuo computer | Va in rete (e perché) |
|---|---|
| Schermo, file, chat e registrazioni | Il centralino: ID, nome scelto del computer, messaggi per avviare il collegamento |
| Password fissa e rubrica, cifrate | Un server STUN di Google per trovare la strada diretta tra i due computer |
| Le impostazioni | Aggiornamenti e, solo se le accetti, statistiche anonime |

Nessuna pubblicità, nessun account da creare. Le statistiche anonime partono **solo se le accetti** al primo avvio
(si cambiano quando vuoi). Gli aggiornamenti sono **firmati digitalmente**: il programma installa solo quelli
pubblicati dall'autore.

## 📥 Installazione

- **Windows 10 / 11** â€” scarica lo ZIP o l'installer, estrai e avvia. Non servono i permessi di amministratore.
- **macOS** (Intel o Apple Silicon) â€” apri il `.dmg` e trascina l'app in *Applicazioni*. Al primo avvio: clic destro sull'app â†’ *Apri*.
- **macOS** — al primo avvio concedi *Registrazione schermo* e *Accessibilità* (Impostazioni di Sistema → Privacy e sicurezza): servono per farti controllare.

Gli aggiornamenti arrivano da soli: quando esce una versione nuova il programma te lo propone.

<details>
<summary><b>🛠️ Avviarlo dal codice sorgente</b></summary>

<br>

Serve **Python 3.13**.

```bash
python -m venv .venv
.venv\Scripts\activate          (su macOS: source .venv/bin/activate)
pip install "pyside6-essentials==6.12.*" certifi aiortc mss pynput numpy sounddevice
python run.py
```

Prove senza rete né schermo: `python tests/test_core.py` e `python tests/test_finestre.py`.
Pacchetti: `installer\build.ps1` (Windows), `mac/build_mac.sh` (macOS).

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
