"""Novidades entregues via ping() — deploy e skill desatualizado (ADR-144 D2/D3).

Diverge deliberadamente do padrão de digest por email (ADR-140/141/143): não
há scheduler, não há email — a entrega é embutida na resposta de `ping()`,
o tool que já é convenção documentada de início de sessão. O princípio de
dedup por transição de estado (ADR-140 D2) é reaproveitado, mas por
`client_id` em vez de por ciclo de digest.
"""

from __future__ import annotations

from typing import Any

from concilium.application.services.skill_content import get_skill_version
from concilium.infrastructure.auth.auth_store import get_auth_store


def _get_deploy_log_store():
    from concilium.infrastructure.deploy.deploy_log_store import DeployLogStore
    from concilium.infrastructure.storage.store_factory import build_system_blob_storage

    return DeployLogStore(build_system_blob_storage())


def check_and_report_novidades(client_id: str | None) -> dict[str, Any] | None:
    """Retorna o que há de novo para `client_id`, ou None se nada há a reportar.

    Efeito colateral: se houver deploy novo, marca `last_deploy_seen` como
    visto (D3) — `ping()` está entregando o aviso nesse mesmo instante. O
    cursor de skill (`last_skill_version_seen`) NUNCA é atualizado aqui — só
    avança quando `obter_instrucoes_atualizadas()` é de fato chamada (D3/A7):
    um usuário que ignorasse o aviso de `ping()` uma vez não pode perdê-lo
    para sempre.
    """
    if client_id is None:
        return None

    store = get_auth_store()
    client = store.get_client(client_id)
    if client is None:
        return None

    deploy_notice: dict[str, str] | None = None
    entry = _get_deploy_log_store().load_latest()
    if entry is not None and entry.promoted_at != client.last_deploy_seen:
        deploy_notice = {"resumo": entry.resumo, "promoted_at": entry.promoted_at}
        store.mark_deploy_seen(client_id, entry.promoted_at)

    skill_desatualizado = get_skill_version() > client.last_skill_version_seen

    if deploy_notice is None and not skill_desatualizado:
        return None

    return {"deploy": deploy_notice, "skill_desatualizado": skill_desatualizado}
