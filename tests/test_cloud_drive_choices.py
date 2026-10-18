import pytest

from tests.test_cloud_ui import setup_page, spin


def drive_question(**overrides):
    option = {
        "Help": "Select drive you want to use",
        "Exclusive": False,
        "Default": "synthetic-work-drive",
        "Examples": [
            {"Value": "synthetic-personal-drive", "Help": "Personal (personal)"},
            {"Value": "synthetic-work-drive", "Help": "Documents (business)"},
        ],
    }
    option.update(overrides)
    return {"State": "config_driveid", "Option": option}


@pytest.mark.parametrize("selection, expected", [
    (None, "synthetic-work-drive"),
    (0, "synthetic-personal-drive"),
    ("custom-drive-id", "custom-drive-id"),
])
def test_drive_choices_show_names_and_submit_identifiers(qapp, tmp_path, selection, expected):
    _, factory, service, page = setup_page(tmp_path, [drive_question(), {}])
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    assert not page.answer_combo.isHidden()
    assert page.answer_edit.isHidden()
    assert page.answer_combo.currentText() == "Documents (business)"
    if isinstance(selection, int):
        page.answer_combo.setCurrentIndex(selection)
    elif selection is not None:
        page.answer_combo.setEditText(selection)
    page.continue_button.click()
    spin(qapp, lambda: not service.busy)
    assert factory.calls[-1] == {"state": "config_driveid", "answer": expected}
    service.wait_for_finished()


def test_exclusive_choices_honor_provider_default(qapp, tmp_path):
    _, _, service, page = setup_page(tmp_path, [drive_question(Exclusive=True)])
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    assert not page.answer_combo.isEditable()
    assert page.answer_combo.currentText() == "Documents (business)"
    service.wait_for_finished()


def test_password_question_ignores_examples_and_default(qapp, tmp_path):
    from PySide6.QtWidgets import QLineEdit
    _, _, service, page = setup_page(tmp_path, [drive_question(IsPassword=True, Exclusive=True)])
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    assert page.answer_combo.isHidden()
    assert page.answer_combo.count() == 0
    assert not page.answer_edit.isHidden()
    assert page.answer_edit.echoMode() == QLineEdit.EchoMode.Password
    assert page.answer_edit.text() == ""
    service.wait_for_finished()


@pytest.mark.parametrize("default, expected", [("unlisted-drive", "unlisted-drive"), (0, "0"), ("", ""), (None, "")])
def test_unlisted_default_is_preserved_as_manual_choice(qapp, tmp_path, default, expected):
    _, factory, service, page = setup_page(tmp_path, [drive_question(Default=default), {}])
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    assert page.answer_combo.currentText() == expected
    page.continue_button.click()
    spin(qapp, lambda: not service.busy)
    assert factory.calls[-1]["answer"] == expected
    service.wait_for_finished()


def test_choice_modes_reset_between_questions(qapp, tmp_path):
    from PySide6.QtWidgets import QLineEdit
    _, factory, service, page = setup_page(tmp_path, [
        drive_question(), drive_question(Exclusive=True),
        drive_question(IsPassword=True), {},
    ])
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    page.answer_combo.setEditText("old-manual-answer")
    page.continue_button.click()
    spin(qapp, lambda: not service.busy)
    assert not page.answer_combo.isEditable()
    assert page.answer_combo.currentText() == "Documents (business)"
    page.continue_button.click()
    spin(qapp, lambda: not service.busy)
    assert page.answer_combo.isHidden()
    assert page.answer_combo.count() == 0
    assert page.answer_edit.echoMode() == QLineEdit.EchoMode.Password
    assert page.answer_edit.text() == ""
    page.answer_edit.setText("synthetic-secret-answer")
    page.continue_button.click()
    spin(qapp, lambda: not service.busy)
    assert factory.calls[-1]["answer"] == "synthetic-secret-answer"
    service.wait_for_finished()
