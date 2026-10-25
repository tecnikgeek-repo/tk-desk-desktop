# tk-desk

Controllo remoto e assistenza: detti il tuo ID e una password monouso di 6 cifre a chi ti aiuta,
tu premi «Accetta» e lui vede il tuo schermo e usa mouse e tastiera. Passaggio di file, chat, chiamata
vocale, più schermi, rubrica dei computer, più sessioni insieme, registrazione e accesso non presidiato
(password fissa). Il collegamento è diretto e cifrato (WebRTC); il server fa solo da centralino.

**Piattaforme:** Windows 10/11 e macOS (Apple Silicon e Intel).

**Licenza:** software libero sotto [GNU AGPL-3.0-or-later](COPYING), tutte le funzioni per tutti.
Una donazione è benvenuta ma non sblocca nulla.

> Non dare mai ID e password a chi ti chiama o ti scrive dicendo di essere un tecnico, la banca o la
> polizia. Usa tk-desk solo con persone che conosci.

## Avviarlo dal sorgente

Serve Python 3.13.

```
python -m venv .venv
.venv\Scripts\activate          (su Mac: source .venv/bin/activate)
pip install "pyside6-essentials==6.12.*" certifi aiortc mss pynput numpy sounddevice
python run.py
```

Prove senza rete né schermo: `python tests/test_core.py` e `python tests/test_finestre.py`.
Pacchetti: `installer\build.ps1` (Windows) e `mac/build_mac.sh` (Mac).

## Cosa va in rete

- Centralino su pietrodefilippis.it (ID del computer e messaggi per far conoscere i due computer);
- server STUN di Google per il collegamento diretto;
- controllo degli aggiornamenti (si installano solo quelli firmati);
- statistiche anonime solo col consenso.

## Nome e logo

Il nome tk-desk e il logo non sono coperti dalla licenza (AGPL sez. 7): una versione modificata deve
avere un nome diverso.

© 2026 Pietro De Filippis (TecnikGeek) — https://pietrodefilippis.it
