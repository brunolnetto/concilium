"""Detecção de dispositivo desconhecido (ADR-123 F3).

Dispara `notify_new_device` (application/services/notifications.py) quando um
`device_id` passa a ter um `RefreshTokenRecord` ativo/tocado por
`activate_device_code()`/`use_refresh_token()` sem que já pertencesse à lista de
dispositivos ativos do `client_id` **antes** dessa operação.

Contrato com o call site: `known_device_ids_before` DEVE ser capturado chamando
`AuthStore.list_devices()` ANTES de invocar `activate_device_code`/
`use_refresh_token` — se for capturado depois, o dispositivo recém-ativado (ou
recém-tocado) já estará na lista e nunca será detectado como "desconhecido".
Como o `client_id` só é conhecido DEPOIS dessas operações (o chamador só tem
`client_code`/`refresh_token` antes), o call site deve capturar a lista COMPLETA
(`list_devices()` sem filtro) antes da operação e filtrar por `record.client_id`
depois — ver `presentation/api/routes/auth.py` e `presentation/mcp/tools/auth_self.py`.

Regra de ruído (decisão de design): o primeiro dispositivo de um usuário novo
NUNCA gera notificação. Um usuário que ainda não tinha nenhum dispositivo ativo
não tem contra o que comparar — todo primeiro acesso pareceria "desconhecido",
gerando alerta de segurança em 100% dos onboardings (ruído, não sinal). A
notificação só faz sentido a partir do 2º dispositivo em diante, quando um
device_id realmente novo aparece ao lado de dispositivos já estabelecidos.

Best-effort: esta função NUNCA propaga exceção. Falha de detecção/notificação
(SMTP fora do ar, storage indisponível) não pode derrubar login/ativação —
mesmo padrão de resiliência do restante do módulo de notificações (ADR-123/ADR-131).
"""

from __future__ import annotations

import logging

from concilium.infrastructure.auth.auth_store import AuthStore, RefreshTokenRecord

logger = logging.getLogger(__name__)


def list_devices_before(store: AuthStore) -> list:
    """Captura `store.list_devices()` para uso como snapshot "antes" (ADR-123 F3).

    Best-effort — nunca lança. `list_devices()` é uma leitura de storage extra
    inserida ANTES de `activate_device_code()`/`use_refresh_token()`; se essa
    leitura falhar (storage indisponível, JSON corrompido), a detecção de
    dispositivo desconhecido é só ruído a menos — degrada para lista vazia em
    vez de derrubar o login/ativação real (Copilot, PRs #77).
    """
    try:
        return store.list_devices()
    except Exception:
        logger.exception("Falha ao capturar devices_before — detecção de dispositivo desconhecido pulada.")
        return []


def notify_if_unknown_device(
    store: AuthStore,
    record: RefreshTokenRecord,
    known_device_ids_before: set[str],
) -> None:
    """Notifica por email se `record.device_id` era desconhecido antes desta operação.

    Best-effort — nunca lança. Chame após o sucesso de `activate_device_code()`/
    `use_refresh_token()`, passando o `RefreshTokenRecord` retornado e o conjunto
    de `device_id`s do MESMO client_id capturado antes da operação.
    """
    try:
        _notify_if_unknown_device(store, record, known_device_ids_before)
    except Exception:
        logger.exception(
            "Falha ao processar detecção de dispositivo desconhecido "
            "(client_id=%s, device_id=%s) — notificação não enviada.",
            record.client_id,
            record.device_id,
        )


def _notify_if_unknown_device(
    store: AuthStore,
    record: RefreshTokenRecord,
    known_device_ids_before: set[str],
) -> None:
    if not known_device_ids_before:
        # Primeiro dispositivo do usuário: onboarding, não anomalia. Ver docstring do módulo.
        return
    if record.device_id in known_device_ids_before:
        return

    clients = {c.client_id: c for c in store.list_clients()}
    client = clients.get(record.client_id)
    email = client.email if client else ""
    if not email:
        return

    from concilium.application.services.notifications import notify_new_device

    pending = store.create_revoke_pending(client_id=record.client_id, device_id=record.device_id)
    notify_new_device(
        client_id=record.client_id,
        device_id=record.device_id,
        device_name=record.device_name or record.device_id,
        email=email,
        revoke_token=pending.revoke_token,
    )
