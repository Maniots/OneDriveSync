"""Provider error continuations must not become blank answer questions."""
from tests.test_cloud_ui import setup_page, spin


def test_onedrive_drive_discovery_error_retries_listing_without_blank_answer(qapp, tmp_path):
    config, factory, service, page = setup_page(tmp_path, [
        {"State": "driveid", "Option": None,
         "Error": "Failed to query available drives: https://private.invalid/?token=private-token"},
        {"State": "driveid_final", "Option": {"Name": "config_driveid", "Help": "Select your drive",
         "Exclusive": True, "Examples": [{"Value": "chosen", "Help": "Personal drive"}]}},
        {},
    ])
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    assert len(factory.calls) == 1
    assert page.answer_edit.isHidden() and page.answer_combo.isHidden()
    assert page.continue_button.text() == "Retry account setup"
    assert "Microsoft could not list" in page.question_label.text()
    assert "private" not in page.question_label.text()
    assert "Choose an account setup option" not in page.question_label.text()
    assert not config.get_app_config().connections
    page.continue_button.click()
    spin(qapp, lambda: not service.busy)
    assert factory.calls[-1] == {"state": "onedrive", "answer": ""}
    assert not page.answer_combo.isHidden()
    assert page.continue_button.text() == "Continue setup"
    assert page.answer_combo.currentData() == "chosen"
    page.continue_button.click()
    spin(qapp, lambda: not service.busy)
    assert not page.folder_group.isHidden()
    page.save_root_button.click()
    spin(qapp, lambda: not service.busy)
    assert len(config.get_app_config().connections) == 1
    assert "private-token" not in (tmp_path / "config.json").read_text()


def test_repeated_error_requires_user_retry_and_cancel_cleans_pending(qapp, tmp_path):
    response = {"State": "choose_type", "Option": None, "Error": "No drives found"}
    config, factory, service, page = setup_page(tmp_path, [response, response])
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    pending = service.pending_connection.id
    assert len(factory.calls) == 1
    assert "OneDrive" in page.question_label.text()
    assert not config.get_app_config().connections
    page.continue_button.click()
    spin(qapp, lambda: not service.busy)
    assert len(factory.calls) == 2
    assert page.answer_edit.isHidden() and page.answer_combo.isHidden()
    page.cancel_button.click()
    spin(qapp, lambda: not service.busy)
    assert factory.deleted == ["es_" + pending]
    assert service.pending_connection is None


def test_error_free_internal_state_advances_without_asking_for_input(qapp, tmp_path):
    config, factory, service, page = setup_page(tmp_path, [
        {"State": "internal", "Option": None},
        {"State": "drive", "Option": {"Help": "Choose a drive", "Exclusive": True,
         "Examples": [{"Value": "one", "Help": "OneDrive"}]}},
    ])
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    assert len(factory.calls) == 2
    assert factory.calls[-1] == {"state": "internal", "answer": ""}
    assert page.question_label.text().strip() == "Choose a drive"
    service.wait_for_finished()


def test_internal_state_loop_stops_without_saving_or_leaking(qapp, tmp_path):
    config, factory, service, page = setup_page(tmp_path, [{"State": "internal", "Option": None}] * 10)
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    assert not config.get_app_config().connections
    assert service.pending_connection is None
    assert len(factory.calls) <= 9
    assert "repeated" in page.status_label.text()
