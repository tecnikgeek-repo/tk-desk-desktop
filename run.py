import os
import site
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# Sviluppo su Windows: avviato con il pythonw di sistema, aggiunge le librerie del venv del progetto.
DEV_SITE = os.path.join(ROOT, ".venv", "Lib", "site-packages")
if sys.prefix == sys.base_prefix and not os.path.isdir(os.path.join(ROOT, "python")) and os.path.isdir(DEV_SITE):
    site.addsitedir(DEV_SITE)
sys.path.insert(0, ROOT)

from tkdesk.app import main

if __name__ == "__main__":
    main()
