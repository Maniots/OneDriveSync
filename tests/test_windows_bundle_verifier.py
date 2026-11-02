"""Release acceptance helpers must tolerate a slow native monitor."""
import json
import threading
import time


def test_wait_for_monitor_completion_survives_file_before_final_status(tmp_path):
    from scripts.verify_windows_bundle import wait_for_monitor_completion

    output = tmp_path / "monitor-save.txt"
    status = tmp_path / "shutdown_monitor_status.json"
    status.write_text(json.dumps({"last_shutdown_sync": None, "last_error": None}))

    def finish_monitor():
        time.sleep(0.05)
        output.write_text("monitor save")
        time.sleep(0.05)
        status.write_text(json.dumps({"last_shutdown_sync": "2026-11-02T12:00:00", "last_error": None}))

    writer = threading.Thread(target=finish_monitor)
    writer.start()
    try:
        result = wait_for_monitor_completion(output, status, process=lambda: None, timeout=1)
    finally:
        writer.join()

    assert output.read_text() == "monitor save"
    assert result["last_shutdown_sync"]
