from dataclasses import replace

import pytest

from backend.services.cloud_service import CloudService
from src.cloud_models import ConnectionConfig
from src.cloud_providers import PROVIDER_SETUP
from tests.test_cloud_ui import configuration, setup_page, spin, SetupFactory


@pytest.mark.parametrize("provider", sorted(set(PROVIDER_SETUP) - {"local"}))
def test_duplicate_provider_is_rejected_before_authorization(qapp, tmp_path, provider):
    config = configuration(tmp_path)
    existing = ConnectionConfig("existing", "Existing", provider, "bucket/EverySync")
    config.save(replace(config.get_app_config(), connections=[existing]))
    factory = SetupFactory([{}])
    service = CloudService(config, transport_factory=factory, parent=qapp)
    with pytest.raises(ValueError, match="already connected"):
        service.configure_connection(replace(existing, id="new_account"), {})
    assert not factory.calls
    assert service.pending_connection is None


def test_connected_provider_disables_signin_and_disconnect_reenables_it(qapp, tmp_path):
    config, _, service, page = setup_page(tmp_path, [{}])
    existing = ConnectionConfig("existing", "Existing", "onedrive", "EverySync")
    config.save(replace(config.get_app_config(), connections=[existing]))
    assert not page.connect_button.isEnabled()
    assert "already connected" in page.provider_hint.text()
    page.provider_combo.setCurrentIndex(page.provider_combo.findData("dropbox"))
    assert page.connect_button.isEnabled()
    page.provider_combo.setCurrentIndex(page.provider_combo.findData("onedrive"))
    service.remove_connection(existing.id)
    spin(qapp, lambda: not service.busy)
    assert page.connect_button.isEnabled()
    assert "already connected" not in page.provider_hint.text()


def test_legacy_duplicates_remain_loadable_and_removable(qapp, tmp_path):
    config, _, service, page = setup_page(tmp_path, [])
    first = ConnectionConfig("first", "First", "onedrive", "EverySync")
    second = replace(first, id="second", name="Second")
    config.save(replace(config.get_app_config(), connections=[first, second]))
    assert page.connection_list.count() == 2
    assert not page.connect_button.isEnabled()
    service.remove_connection(first.id)
    spin(qapp, lambda: not service.busy)
    assert config.get_app_config().connections == [second]
    assert not page.connect_button.isEnabled()


def test_provider_conflict_before_final_save_discards_only_pending_credentials(qapp, tmp_path):
    config, factory, service, page = setup_page(tmp_path, [{}])
    page.connect_button.click()
    spin(qapp, lambda: not service.busy)
    pending = page.pending
    existing = ConnectionConfig("existing", "Existing", "onedrive", "EverySync")
    config.save(replace(config.get_app_config(), connections=[existing]))
    page.save_root_button.click()
    spin(qapp, lambda: not service.busy)
    assert config.get_app_config().connections == [existing]
    assert factory.deleted == ["es_" + pending.id]
    assert service.pending_connection is None


def test_local_connections_remain_multiple(qapp, tmp_path):
    config = configuration(tmp_path)
    root = tmp_path / "storage"
    root.mkdir()
    existing = ConnectionConfig("existing", "NAS", "local", str(root))
    config.save(replace(config.get_app_config(), connections=[existing]))
    factory = SetupFactory([{}])
    service = CloudService(config, transport_factory=factory, parent=qapp)
    service.configure_connection(replace(existing, id="another"), {})
    spin(qapp, lambda: not service.busy)
    assert len(config.get_app_config().connections) == 2
