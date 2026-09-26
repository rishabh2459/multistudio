"""Entry point of the frozen backend (PyInstaller): same as `multicam-api`."""

import multiprocessing
import sys

from multicam_api.main import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
