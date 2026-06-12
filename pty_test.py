"""Drive the curses UI through a pty to verify the interactive path.

Run:  python3 pty_test.py
"""

import os
import pty
import select
import struct
import subprocess
import sys
import termios
import fcntl
import time

SAVE = os.path.expanduser("~/.myar_save.pkl")


def run_session(keys, timeout=15):
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    env = dict(os.environ, TERM="xterm-256color", LINES="24", COLUMNS="80")
    proc = subprocess.Popen(
        [sys.executable, "-m", "rogue"],
        stdin=slave, stdout=slave, stderr=subprocess.PIPE,
        env=env, cwd=os.path.dirname(os.path.abspath(__file__)))
    os.close(slave)
    output = b""
    deadline = time.time() + timeout
    key_iter = iter(keys)
    next_send = time.time() + 0.4
    try:
        while proc.poll() is None and time.time() < deadline:
            r, _, _ = select.select([master], [], [], 0.05)
            if r:
                try:
                    output += os.read(master, 4096)
                except OSError:
                    break
            if time.time() >= next_send:
                try:
                    k = next(key_iter)
                    os.write(master, k.encode())
                    next_send = time.time() + 0.15
                except StopIteration:
                    next_send = deadline
        proc.wait(timeout=5)
    finally:
        os.close(master)
        if proc.poll() is None:
            proc.kill()
    stderr = proc.stderr.read().decode("utf-8", "replace")
    return proc.returncode, output.decode("utf-8", "replace"), stderr


def main():
    # Never destroy a real save: set it aside and restore it afterwards.
    backup = SAVE + ".pty_backup"
    if os.path.exists(SAVE):
        os.replace(SAVE, backup)
    try:
        _run_scenarios()
    finally:
        if os.path.exists(SAVE):
            os.remove(SAVE)  # leftover test save
        if os.path.exists(backup):
            os.replace(backup, SAVE)


def _run_scenarios():

    # Session 1: new game -> race a, class a, name, reroll stats once then
    # accept, move/look around, character sheet, save+exit
    keys = ["a", "a", "Test\n", "r", "a",
            "l", "j", "h", "k", "y", "u", "b", "n",
            "i", " ", "?", " ", "@", " ", ".", "s", ",", " ",
            "S", "y"]
    rc, out, err = run_session(keys)
    assert rc == 0, f"session 1 exit code {rc}\nstderr:\n{err}"
    assert "Traceback" not in err, err
    assert "M.Y.A.R." in out, "title screen not shown"
    assert os.path.exists(SAVE), "save file not written"
    print("ok  session 1: new game, commands, save+exit")

    # Session 2: load save -> quit without saving
    keys = [" ", "Q", "y"]
    rc, out, err = run_session(keys)
    assert rc == 0, f"session 2 exit code {rc}\nstderr:\n{err}"
    assert "Traceback" not in err, err
    assert "saved game" in out, "save was not loaded"
    assert not os.path.exists(SAVE), "save not consumed on load"
    print("ok  session 2: save loaded and consumed, quit")
    print("PTY OK")


if __name__ == "__main__":
    main()
