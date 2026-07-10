"""Tests for application/services/device_detection.py (ADR-123 F3).

Cobertura (ver PR/ADR-123 F3):
  a) dispositivo desconhecido com outros dispositivos existentes -> notifica
     com device_name/device_id/revoke_token
  b) primeiro dispositivo de usuário novo (known_device_ids_before vazio) -> não notifica
  c) dispositivo já conhecido (device_id em known_device_ids_before) -> não notifica
  d) sem email cadastrado -> não notifica nem lança
  e) falha durante o processamento (ex.: create_revoke_pending lança) -> nunca propaga
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from concilium.application.services.device_detection import list_devices_before, notify_if_unknown_device


def _record(client_id="client-1", device_id="dev-new", device_name="notebook-novo"):
    return MagicMock(client_id=client_id, device_id=device_id, device_name=device_name)


class TestListDevicesBefore:
    """Copilot (PRs #77): list_devices() é uma leitura extra ANTES da ativação/
    refresh — se falhar, a detecção deve degradar para lista vazia, nunca
    propagar e derrubar o login/ativação real."""

    def test_returns_devices_on_success(self):
        store = MagicMock()
        store.list_devices.return_value = ["d1", "d2"]
        assert list_devices_before(store) == ["d1", "d2"]

    def test_returns_empty_list_when_store_raises(self):
        store = MagicMock()
        store.list_devices.side_effect = RuntimeError("storage indisponível")
        assert list_devices_before(store) == []


class TestNotifyIfUnknownDevice:
    def test_unknown_device_with_existing_devices_notifies(self):
        record = _record()
        client = MagicMock(client_id="client-1", email="user@example.com")
        pending = MagicMock(revoke_token="REVOKE-1")
        store = MagicMock()
        store.list_clients.return_value = [client]
        store.create_revoke_pending.return_value = pending

        with patch(
            "concilium.application.services.notifications.notify_new_device"
        ) as notify_mock:
            notify_if_unknown_device(store, record, known_device_ids_before={"dev-old"})

        store.create_revoke_pending.assert_called_once_with(client_id="client-1", device_id="dev-new")
        notify_mock.assert_called_once_with(
            client_id="client-1",
            device_id="dev-new",
            device_name="notebook-novo",
            email="user@example.com",
            revoke_token="REVOKE-1",
        )

    def test_first_device_of_new_user_does_not_notify(self):
        record = _record()
        store = MagicMock()

        with patch(
            "concilium.application.services.notifications.notify_new_device"
        ) as notify_mock:
            notify_if_unknown_device(store, record, known_device_ids_before=set())

        notify_mock.assert_not_called()
        store.list_clients.assert_not_called()
        store.create_revoke_pending.assert_not_called()

    def test_already_known_device_does_not_notify(self):
        record = _record(device_id="dev-old")
        store = MagicMock()

        with patch(
            "concilium.application.services.notifications.notify_new_device"
        ) as notify_mock:
            notify_if_unknown_device(store, record, known_device_ids_before={"dev-old", "dev-other"})

        notify_mock.assert_not_called()
        store.list_clients.assert_not_called()
        store.create_revoke_pending.assert_not_called()

    def test_no_email_registered_does_not_notify_nor_raise(self):
        record = _record()
        client = MagicMock(client_id="client-1", email="")
        store = MagicMock()
        store.list_clients.return_value = [client]

        with patch(
            "concilium.application.services.notifications.notify_new_device"
        ) as notify_mock:
            notify_if_unknown_device(store, record, known_device_ids_before={"dev-old"})

        notify_mock.assert_not_called()
        store.create_revoke_pending.assert_not_called()

    def test_client_not_found_does_not_notify_nor_raise(self):
        record = _record()
        store = MagicMock()
        store.list_clients.return_value = []

        with patch(
            "concilium.application.services.notifications.notify_new_device"
        ) as notify_mock:
            notify_if_unknown_device(store, record, known_device_ids_before={"dev-old"})

        notify_mock.assert_not_called()

    def test_failure_never_propagates(self):
        record = _record()
        store = MagicMock()
        store.list_clients.side_effect = RuntimeError("storage indisponível")

        # Não deve lançar.
        notify_if_unknown_device(store, record, known_device_ids_before={"dev-old"})

    def test_notify_new_device_failure_never_propagates(self):
        record = _record()
        client = MagicMock(client_id="client-1", email="user@example.com")
        pending = MagicMock(revoke_token="REVOKE-1")
        store = MagicMock()
        store.list_clients.return_value = [client]
        store.create_revoke_pending.return_value = pending

        with patch(
            "concilium.application.services.notifications.notify_new_device",
            side_effect=RuntimeError("smtp fora do ar"),
        ):
            notify_if_unknown_device(store, record, known_device_ids_before={"dev-old"})
