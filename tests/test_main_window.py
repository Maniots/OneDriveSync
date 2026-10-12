from ui.main_window import MainWindow


def test_invalid_configuration_shows_error_page(qapp):
    class MissingConfiguration:
        def get_app_config(self):
            return None

    window = MainWindow(configuration_service=MissingConfiguration())
    try:
        assert window.config_error == "Configuration is not available or invalid."
        assert window.content_stack.count() == 1
        assert not window.sync_now_action.isEnabled()
    finally:
        window.tray_icon.hide()
        window.close()
