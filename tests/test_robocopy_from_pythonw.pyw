"""
test_robocopy_from_pythonw.py

Standalone diagnostic - NOT part of the real app. Run this by DOUBLE
CLICKING it (renamed to .pyw so it launches via pythonw.exe, exactly
like the real monitor, but completely bypassing Task Scheduler/
RunHidden.vbs). This isolates whether the 0xc0000142 failure is caused
by:
  (a) pythonw.exe itself (no console), regardless of launch method, or
  (b) something specific to the Task Scheduler -> wscript.exe ->
      RunHidden.vbs launch chain (e.g. a broken/reduced environment
      block).

It also dumps key environment variables that Win32 process creation
depends on (SystemRoot, PATH, ComSpec) - if any of these are missing
or malformed, new child processes can fail to initialize.

HOW TO USE:
1. Save this file as test_robocopy_from_pythonw.pyw (note: .pyw
   extension so double-clicking runs it with pythonw.exe automatically,
   just like the real monitor).
2. Create two folders anywhere, e.g. C:\Temp\rc_src and C:\Temp\rc_dst,
   and put a small test file in rc_src.
3. Edit SOURCE / DEST below to point at them.
4. Double click the .pyw file. Nothing will appear on screen (that's
   expected - pythonw.exe has no console).
5. Check test_robocopy_result.log next to this script afterwards.
"""
import ctypes
import datetime
import os
import subprocess

SOURCE = r"C:\Temp\rc_src"
DEST = r"C:\Temp\rc_dst"

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_robocopy_result.log")


def log(msg: str) -> None:
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().isoformat()} PID={os.getpid()} {msg}\n")
        f.flush()
        os.fsync(f.fileno())


def main():
    log("=== test starting ===")
    log(f"SystemRoot={os.environ.get('SystemRoot')!r}")
    log(f"ComSpec={os.environ.get('ComSpec')!r}")
    path_val = os.environ.get('PATH', '')
    log(f"PATH length={len(path_val)}")
    log(f"PATH contains System32={'System32' in path_val}")

    os.makedirs(SOURCE, exist_ok=True)
    os.makedirs(DEST, exist_ok=True)
    test_file = os.path.join(SOURCE, "test.txt")
    if not os.path.exists(test_file):
        with open(test_file, "w") as f:
            f.write("test")

    command = ["robocopy", SOURCE, DEST, "/E", "/XO", "/R:2", "/W:2", "/NP"]
    log(f"command={command}")

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
            stdin=subprocess.DEVNULL,
        )
        log(f"returncode={completed.returncode} (hex={completed.returncode & 0xFFFFFFFF:#010x})")
        log(f"stdout={completed.stdout!r}")
        log(f"stderr={completed.stderr!r}")
    except Exception as e:
        log(f"EXCEPTION: {e!r}")

    log("=== test finished ===")


if __name__ == "__main__":
    main()
