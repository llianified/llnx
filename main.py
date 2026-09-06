#!/usr/bin/env python3
"""llnx entry point: `python3 main.py`. Installed, the command is `llnx`.

  python3 main.py                       full-screen TUI
  python3 main.py backtest --cash 20
  python3 main.py run --mode paper
  python3 main.py run --mode live --yes
  python3 main.py stop
"""
from llnx.cli import main

if __name__ == "__main__":
    main()
