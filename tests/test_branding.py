from pathlib import Path

from PySide6.QtWidgets import QLabel

from backend.services.configuration_service import ConfigurationService
from ui.main_window import MainWindow


def test_desktop_displays_everysync_identity(qapp, tmp_path):
    config = tmp_path / "config.json"
    config.write_bytes((Path(__file__).resolve().parents[1] / "packaging/default-config.json").read_bytes())
    window = MainWindow(configuration_service=ConfigurationService(config))
    try:
        assert window.windowTitle() == "EverySync"
        assert window.tray_icon.toolTip() == "EverySync - Idle"
        labels = [label.text() for label in window.findChildren(QLabel)]
        assert "EverySync" in labels
        assert not any("OneDrive PC Sync" in text for text in labels)
    finally:
        window.prepare_for_exit()
        window.tray_icon.hide()
        window.hide()


def test_tray_keeps_product_logo_and_distinguishes_sync_states(qapp):
    from ui.resources.icons import get_app_icon

    logo = get_app_icon().pixmap(64, 64).toImage()
    assert not logo.isNull()
    images = [get_app_icon(state).pixmap(64, 64).toImage()
              for state in ("idle", "running", "success", "error")]
    for index, image in enumerate(images):
        assert not image.isNull()
        assert all(image != other for other in images[index + 1:])
        # A badge occupies the bottom right; the upper logo remains intact.
        assert image.copy(0, 0, 40, 32) == logo.copy(0, 0, 40, 32)
