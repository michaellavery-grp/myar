import curses
import sys

from .ui import main

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except SystemExit as e:
        if e.code:
            print(e.code, file=sys.stderr)
            sys.exit(1)
