"""Acceptance checks for the actual Windows EXE, using isolated local folders.

Usage: python scripts/verify_windows_bundle.py dist/OneDrivePCSync/OneDrivePCSync.exe
No global shutdown broadcast or production scheduled task is sent/changed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def verify(executable: Path, root: Path) -> dict:
    import win32con
    import win32gui
    import win32process

    env = dict(os.environ, LOCALAPPDATA=str(root / "user"))
    unrelated_cwd = root / "unrelated working directory"
    unrelated_cwd.mkdir()

    def run(*args):
        result = subprocess.run([str(executable), *map(str, args)], env=env,
                                cwd=unrelated_cwd, timeout=75,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            crash = root / "user/OneDrivePCSync/logs/desktop_crash.log"
            raise RuntimeError(f"EXE {args} returned {result.returncode}: "
                               f"{crash.read_text() if crash.exists() else 'see logs'}")

    report_path = root / "desktop.json"
    run("--smoke-test", report_path)
    report = json.loads(report_path.read_text())
    assert report["frozen"] and report["ui_rendered"] and report["folder_count"] == 0
    config_path = Path(report["config"])
    config = json.loads(config_path.read_text())
    local, cloud = root / "local", root / "cloud"
    local.mkdir()
    cloud.mkdir()
    config["folders"] = [{"id": "test", "name": "Isolated acceptance test",
                          "enabled": True, "local_path": str(local),
                          "onedrive_path": str(cloud), "minimum_sync_percentage": 0}]
    config_path.write_text(json.dumps(config), encoding="utf-8")
    (local / "save.txt").write_text("local save")
    run("--mode", "shutdown", "--dry-run")
    assert not (cloud / "save.txt").exists(), "Dry run copied data"
    run("--mode", "shutdown")
    assert (cloud / "save.txt").read_text() == "local save"

    # Offscreen rendering cannot detect Windows worker-disposal races.
    # Exercise the shipping Qt platform while startup checks complete.
    for index in range(1, 4):
        (root / f"local-{index}").mkdir()
        (root / f"cloud-{index}").mkdir()
        config["folders"].append({
            "id": f"test-{index}", "name": f"Acceptance folder {index}",
            "enabled": True, "local_path": str(root / f"local-{index}"),
            "onedrive_path": str(root / f"cloud-{index}"), "minimum_sync_percentage": 0,
        })
    config_path.write_text(json.dumps(config), encoding="utf-8")
    native_report = root / "native-interactions.json"
    run("--interaction-test", native_report)
    interactions = json.loads(native_report.read_text())
    assert interactions["folder_count"] == 4
    assert interactions["native_navigation_clicks"] >= 28
    assert interactions["manual_update_check_verified"]
    assert interactions["startup_setting_verified"]

    # Exercise the existing native monitor on its own HWND with isolated data.
    # This message asks only this process to sync; it does not end a session.
    (local / "monitor-save.txt").write_text("monitor save")
    monitor = subprocess.Popen([str(executable), "--monitor"], env=env,
                               cwd=unrelated_cwd, creationflags=subprocess.CREATE_NO_WINDOW)
    hwnd = None
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and monitor.poll() is None:
            windows = []
            def find_window(candidate, _):
                if win32process.GetWindowThreadProcessId(candidate)[1] == monitor.pid:
                    windows.append(candidate)
            win32gui.EnumWindows(find_window, None)
            if windows:
                hwnd = windows[0]
                break
            time.sleep(0.1)
        assert hwnd, f"Monitor window not created (exit={monitor.poll()})"
        win32gui.SendMessageTimeout(hwnd, 0x0011, 0, 0, win32con.SMTO_ABORTIFHUNG, 15000)
        assert (cloud / "monitor-save.txt").read_text() == "monitor save"
        status = json.loads((config_path.parent / "shutdown_monitor_status.json").read_text())
        assert status["last_detected_event"] and status["last_shutdown_sync"]
        win32gui.PostMessage(hwnd, 0x0016, 1, 0)
        assert monitor.wait(timeout=10) == 0
    finally:
        if monitor.poll() is None:
            monitor.terminate()
            monitor.wait(timeout=10)
    report.update(dry_run_preserved=True, sync_copy_verified=True,
                  native_navigation_clicks=interactions["native_navigation_clicks"],
                  manual_update_check_verified=True,
                  startup_setting_verified=True,
                  native_monitor_sync_verified=True, native_monitor_exit_verified=True)
    (root / "acceptance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    executable = Path(sys.argv[1]).resolve()
    validation_root = Path(__file__).resolve().parents[1] / "build"
    validation_root.mkdir(exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="windows-acceptance-", dir=validation_root))
    result = verify(executable, root)
    print(json.dumps(result, indent=2))
