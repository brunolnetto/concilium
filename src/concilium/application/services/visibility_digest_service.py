"""Digest periódico de "quem me consultou" (ADR-143 D7/D8).

Aplica o critério do ADR-140 D1 (condições d/e): ser consultado é subproduto
da leitura de outro usuário, não uma ação humana distinta do próprio
consultado — nunca notificação atômica por consulta. Agrupa os eventos
pendentes desde o último digest (drenados via `pop_pending_visibility_queries`)
e envia um resumo por destinatário.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from concilium.application.services.notifications import notify_visibility_queried
from concilium.infrastructure.auth.auth_store import get_auth_store


def _agrupar_por_alvo(pending: list) -> dict[str, list]:
    by_target: dict[str, list] = defaultdict(list)
    for record in pending:
        by_target[record.target_client_id].append(record)
    return by_target


def _resumo_por_observador(records: list) -> list[tuple]:
    counts = Counter((r.observer_client_id, ", ".join(sorted(r.observer_roles))) for r in records)
    return [(observer_id, roles, count) for (observer_id, roles), count in sorted(counts.items())]


def _enviar_digest_do_alvo(target_id: str, records: list, clients_by_id: dict) -> bool:
    """Envia o digest de um alvo; descarta silenciosamente alvo inativo ou sem email."""
    client = clients_by_id.get(target_id)
    if client is None or not client.active or not client.email:
        return False

    resumo = _resumo_por_observador(records)
    return notify_visibility_queried(client.email, resumo)


def enviar_digest_visibilidade() -> int:
    """Drena consultas pendentes, agrupa por alvo e envia um digest por destinatário.

    Retorna quantos emails foram efetivamente enviados. Se não há nenhuma
    consulta pendente, não drena o store (nada a esvaziar) nem envia nada —
    mesmo princípio de silêncio do ADR-141 D4 (sem "0 consultas" recorrente).
    Alvo inativo ou sem email cadastrado é descartado sem notificação.
    """
    store = get_auth_store()
    pending = store.pop_pending_visibility_queries()
    if not pending:
        return 0

    by_target = _agrupar_por_alvo(pending)
    clients_by_id = {c.client_id: c for c in store.list_clients()}
    return sum(
        1 for target_id, records in by_target.items() if _enviar_digest_do_alvo(target_id, records, clients_by_id)
    )
