"""Notificações de negócio por email (ADR-134 D4/D5/D6).

Uma função fina por evento de negócio — monta o `context` (ADR-134 D2) e chama
`NotificationService.send()` (infraestrutura, ADR-134 D1). Nenhum destes casos de
uso vive mais em `infrastructure/services/notification_service.py`: a infra não
conhece nenhum evento de negócio, só sabe renderizar template + enviar.

Call sites: `presentation/cli/commands_auth.py`, `presentation/api/routes/auth.py`,
`presentation/mcp/tools/auth_self.py`,
`application/services/project/_ownership_helpers.py` (ADR-126, D6).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from concilium.infrastructure.services.notification_service import get_notification_service

logger = logging.getLogger(__name__)

# ── Helpers de conteúdo ──────────────────────────────────────────────────────────

_SKILL_TUTORIAL_PATH = (
    Path(__file__).resolve().parents[2] / "infrastructure" / "services" / "templates" / "concilium_usage_tutorial.skill"
)

_SKILL_TUTORIAL_FALLBACK = (
    b"O tutorial de instalacao nao pode ser carregado neste envio. "
    b"Contate o administrador do Concilium para receber os passos de instalacao."
)


def _read_skill_tutorial() -> bytes:
    """Lê o tutorial de instalação/uso enviado como anexo — agnóstico de SO,

    não depende do build do proxy (build-proxy.yml), por isso vive junto com os
    demais templates de notificação em vez de ser publicado por CI.

    Best-effort: um erro de leitura (ex.: instalação empacotada sem o arquivo)
    não deve abortar o email de boas-vindas/migração — cai num placeholder.
    """
    try:
        return _SKILL_TUTORIAL_PATH.read_bytes()
    except OSError:
        logger.warning("Falha ao ler %s — usando tutorial fallback no anexo.", _SKILL_TUTORIAL_PATH)
        return _SKILL_TUTORIAL_FALLBACK


def _build_proxy_download_note(proxy_download_urls: dict[str, str | None] | None) -> str:
    """Monta o trecho do email com os links de download do executável standalone.

    Um link por SO (Windows/Linux/macOS) — não há PyPI/wheel publicado para o
    usuário final instalar via pip. Retorna string vazia se nenhum link estiver
    disponível (ex.: backend de storage sem suporte a URL assinada em dev).

    Os links são gerados com scope="organization" (ver
    _get_proxy_exe_download_urls) — abrem sem confirmação extra para quem já
    está logado com a conta Microsoft/M365 da MendesLobo; se pedir login, é
    só entrar com a conta da empresa (o arquivo não é público).
    """
    urls = proxy_download_urls or {}
    windows_url = urls.get("windows")
    linux_url = urls.get("linux")
    macos_url = urls.get("macos")
    if not (windows_url or linux_url or macos_url):
        return ""

    lines = [
        "Antes de colar a configuração, baixe o executável do proxy correspondente ao\n"
        "seu sistema operacional e salve no caminho indicado (o link abre com a sua\n"
        "conta Microsoft/M365 da empresa — não precisa de senha adicional):\n",
    ]
    if windows_url:
        lines.append(f"  Windows : {windows_url}")
        lines.append(r"            salvar em C:\Concilium\concilium-mcp-proxy.exe" + "\n")
    if linux_url:
        lines.append(f"  Linux   : {linux_url}")
        lines.append("            salvar em ~/.concilium/bin/concilium-mcp-proxy (chmod +x)\n")
    if macos_url:
        lines.append(f"  macOS   : {macos_url}")
        lines.append("            salvar em ~/.concilium/bin/concilium-mcp-proxy (chmod +x)\n")
    return "\n".join(lines) + "\n\n"


def _base_url() -> str:
    from concilium.infrastructure.settings import get_api

    api = get_api()
    return (api.base_url or f"http://{api.host}:{api.port}").rstrip("/")


# ── ADR-123/ADR-131: os 7 casos de uso originais (ADR-134 D5) ───────────────────


def _distribution_attachments(config_json_unix: str, config_json_windows: str) -> list[tuple[str, bytes, str]]:
    """Anexos comuns a notify_user_created/notify_client_code_migrated.

    O executável do proxy NUNCA vai em anexo (nem solto, nem em zip) — provedores
    de email (Gmail incluso, confirmado em produção: SMTP 552 5.7.0 "potential
    security issue") bloqueiam mensagens com payload executável, zipado ou não.
    A entrega do executável é só pelo link assinado (`download_note`, ver
    `_build_proxy_download_note`); aqui só vão os configs (texto) e o tutorial.
    """
    return [
        ("claude_desktop_config-macos-linux.json", config_json_unix.encode("utf-8"), "application/json"),
        ("claude_desktop_config-windows.json", config_json_windows.encode("utf-8"), "application/json"),
        ("concilium_usage_tutorial.skill", _read_skill_tutorial(), "text/plain"),
    ]


def notify_user_created(
    client_id: str,
    role: str,
    email: str,
    config_json_unix: str,
    config_json_windows: str,
    proxy_download_urls: dict[str, str | None] | None = None,
) -> bool:
    """Email de boas-vindas com os dois configs (macOS/Linux e Windows) em anexo.

    O admin não sabe necessariamente o SO do dispositivo do usuário no momento do
    cadastro — manda os dois e deixa o próprio usuário escolher o que corresponde
    ao seu sistema, em vez de arriscar mandar o formato errado.
    """
    return get_notification_service().send(
        to=email,
        subject=f"[Concilium] Bem-vindo, {client_id}! Sua conta foi criada.",
        template="user_created",  # layout próprio — anexo com passos (ADR-134 D2, exceção justificada)
        context={
            "heading": f"Bem-vindo ao Concilium, {client_id}!",
            "intro": "Sua conta no Concilium foi criada com sucesso.",
            "details": [("Usuário", client_id), ("Perfil", role)],
            "download_note": _build_proxy_download_note(proxy_download_urls),
            "config_json_unix": config_json_unix,
            "config_json_windows": config_json_windows,
        },
        attachments=_distribution_attachments(config_json_unix, config_json_windows),
    )


def notify_client_code_migrated(
    client_id: str,
    email: str,
    config_json_unix: str,
    config_json_windows: str,
    proxy_download_urls: dict[str, str | None] | None = None,
) -> bool:
    """Notifica um client migrado (client_code gerado retroativamente) com os dois configs."""
    return get_notification_service().send(
        to=email,
        subject=f"[Concilium] Novo código de ativação para '{client_id}'",
        template="user_created",
        context={
            "heading": f"Novo código de ativação para '{client_id}'",
            "intro": (
                "Sua conta no Concilium recebeu um código de ativação de dispositivo novo "
                "(atualização do sistema de autenticação — nenhuma ação sua causou isso)."
            ),
            "details": None,
            "download_note": _build_proxy_download_note(proxy_download_urls),
            "config_json_unix": config_json_unix,
            "config_json_windows": config_json_windows,
        },
        attachments=_distribution_attachments(config_json_unix, config_json_windows),
    )


def notify_user_removed(client_id: str, email: str) -> bool:
    """Informa a remoção do usuário e a revogação de todos os seus dispositivos."""
    return get_notification_service().send(
        to=email,
        subject=f"[Concilium] Acesso de '{client_id}' removido.",
        template="notification",
        context={
            "heading": f"Acesso de '{client_id}' removido",
            "intro": (
                f"O acesso do usuário '{client_id}' ao Concilium foi removido e todos "
                "os dispositivos associados foram revogados."
            ),
            "details": None,
            "cta": None,
            "footer_note": "Se isso foi feito por engano, entre em contato com o administrador.",
        },
    )


def notify_user_edited(client_id: str, email: str, changes: dict[str, str]) -> bool:
    """Informa alteração nos dados do usuário (ADR-131 D2).

    `changes` é um dict descritivo (chave → descrição da mudança), ex.:
    {"client_code": "regenerado"} — não expõe segredos/hashes no corpo do email.
    """
    return get_notification_service().send(
        to=email,
        subject=f"[Concilium] Dados da conta '{client_id}' foram alterados.",
        template="notification",
        context={
            "heading": f"Dados da conta '{client_id}' foram alterados",
            "intro": (
                f"Os seguintes dados da sua conta '{client_id}' no Concilium foram alterados por um administrador:"
            ),
            "details": list(changes.items()),
            "cta": None,
            "footer_note": "Se isso foi feito por engano, entre em contato com o administrador.",
        },
    )


def notify_device_revoked_admin(client_id: str, device_id: str, email: str) -> bool:
    """Informa revogação administrativa direta de um dispositivo (ADR-131 D3).

    Distinto de `notify_revoke_pending`: aqui não há opt-in/confirmação do usuário
    — a ação já foi tomada unilateralmente pelo admin. O corpo deixa isso explícito
    para reduzir o risco de o usuário interpretar o email como phishing.
    """
    return get_notification_service().send(
        to=email,
        subject=f"[Concilium] Dispositivo '{device_id}' revogado por um administrador.",
        template="notification",
        context={
            "heading": f"Dispositivo '{device_id}' revogado por um administrador",
            "intro": (
                f"O acesso do dispositivo '{device_id}' à sua conta no Concilium foi "
                "revogado por um administrador — esta ação não foi solicitada por você "
                "e não exige nenhuma confirmação de sua parte."
            ),
            "details": [("Usuário", client_id), ("Dispositivo", device_id)],
            "cta": None,
            "footer_note": "Se você não esperava esta revogação, entre em contato com o administrador.",
        },
    )


def notify_new_device(
    client_id: str,
    device_id: str,
    device_name: str,
    email: str,
    revoke_token: str,
) -> bool:
    """Alerta de novo dispositivo com link de revogação."""
    revoke_link = f"{_base_url()}/auth/revoke-pending/{revoke_token}"
    return get_notification_service().send(
        to=email,
        subject=f"[Concilium] Novo dispositivo conectado: {device_name}",
        template="notification",
        context={
            "heading": "Novo dispositivo conectado",
            "intro": "Um novo dispositivo foi conectado à sua conta:",
            "details": [("Dispositivo", device_name), ("Device ID", device_id)],
            "cta": {"label": "Revogar este dispositivo", "url": revoke_link},
            "footer_note": "Se foi você quem configurou este dispositivo, ignore este email.",
        },
    )


def notify_revoke_pending(
    client_id: str,
    device_id: str,
    email: str,
    revoke_token: str,
) -> bool:
    """Confirmação de revogação solicitada via MCP self-service."""
    confirm_link = f"{_base_url()}/auth/revoke-confirm/{revoke_token}"
    return get_notification_service().send(
        to=email,
        subject=f"[Concilium] Confirme a revogação do dispositivo '{device_id}'",
        template="notification",
        context={
            "heading": f"Confirme a revogação do dispositivo '{device_id}'",
            "intro": f"Você solicitou a revogação do dispositivo '{device_id}'.",
            "details": None,
            "cta": {"label": "Confirmar revogação", "url": confirm_link},
            "footer_note": "Válido por 24h. Se não foi você, ignore este email — nenhuma ação será tomada.",
        },
    )


# ── ADR-126: 5 notificações de ownership handover (ADR-134 D6) ─────────────────
#
# Mapeamento 1:1 com OwnershipTransferAction.action (application/services/
# project/audit_service.py). Wiring em application/services/project/
# _ownership_helpers.py — condicionado a email cadastrado, nunca lançando
# exceção (mesmo padrão condicional das notificações ADR-123/ADR-131).


def notify_ownership_transfer_forced(email: str, project_id: str, owner_anterior: str | None, owner_novo: str) -> bool:
    """D4.1/D7: admin (ou `remove-user --reassign-to`) transferiu o projeto sem aceite."""
    return get_notification_service().send(
        to=email,
        subject=f"[Concilium] Você é o novo responsável pelo projeto '{project_id}'",
        template="notification",
        context={
            "heading": f"Você é o novo responsável pelo projeto '{project_id}'",
            "intro": "A responsabilidade por este projeto foi transferida para você por um administrador.",
            "details": [
                ("Projeto", project_id),
                ("Dono anterior", owner_anterior or "—"),
                ("Novo dono", owner_novo),
            ],
            "cta": None,
            "footer_note": "Se você não esperava esta transferência, entre em contato com o administrador.",
        },
    )


def notify_ownership_invite_created(
    email: str, project_id: str, owner_atual: str, owner_proposto: str, token: str
) -> bool:
    """D4.2: dono atual iniciou um handover voluntário — destinatário decide aceitar/rejeitar."""
    base = _base_url()
    accept_link = f"{base}/api/projects/{project_id}/transfer-ownership/{token}/accept"
    reject_link = f"{base}/api/projects/{project_id}/transfer-ownership/{token}/reject"
    return get_notification_service().send(
        to=email,
        subject=f"[Concilium] Convite para assumir o projeto '{project_id}'",
        template="notification",
        context={
            "heading": f"Convite para assumir o projeto '{project_id}'",
            "intro": f"'{owner_atual}' propôs transferir a responsabilidade deste projeto para você.",
            "details": [("Projeto", project_id), ("Dono atual", owner_atual)],
            "cta": {"label": "Aceitar transferência", "url": accept_link},
            "footer_note": f"Para rejeitar, acesse: {reject_link}. Este convite expira em 24h.",
        },
    )


def notify_ownership_invite_accepted(email: str, project_id: str, owner_novo: str) -> bool:
    """F3: destinatário aceitou — notifica o dono anterior."""
    return get_notification_service().send(
        to=email,
        subject=f"[Concilium] '{owner_novo}' aceitou a transferência do projeto '{project_id}'",
        template="notification",
        context={
            "heading": f"Transferência de '{project_id}' aceita",
            "intro": f"'{owner_novo}' aceitou a transferência de responsabilidade do projeto.",
            "details": [("Projeto", project_id), ("Novo dono", owner_novo)],
            "cta": None,
            "footer_note": None,
        },
    )


def notify_ownership_invite_rejected(email: str, project_id: str, owner_proposto: str) -> bool:
    """F3: destinatário rejeitou — notifica o dono anterior (que permanece dono)."""
    return get_notification_service().send(
        to=email,
        subject=f"[Concilium] '{owner_proposto}' rejeitou a transferência do projeto '{project_id}'",
        template="notification",
        context={
            "heading": f"Transferência de '{project_id}' rejeitada",
            "intro": (
                f"'{owner_proposto}' rejeitou o convite para assumir a responsabilidade do "
                "projeto. Você continua sendo o dono."
            ),
            "details": [("Projeto", project_id), ("Destinatário", owner_proposto)],
            "cta": None,
            "footer_note": None,
        },
    )


def notify_ownership_invite_expired(email: str, project_id: str, owner_proposto: str) -> bool:
    """D6: convite venceu sem resposta (TTL) — notifica o dono anterior (que permanece dono)."""
    return get_notification_service().send(
        to=email,
        subject=f"[Concilium] Convite de transferência do projeto '{project_id}' expirou",
        template="notification",
        context={
            "heading": f"Convite de transferência do projeto '{project_id}' expirou",
            "intro": (
                f"O convite para '{owner_proposto}' assumir a responsabilidade do projeto "
                "expirou sem resposta. Você continua sendo o dono."
            ),
            "details": [("Projeto", project_id), ("Destinatário", owner_proposto)],
            "cta": None,
            "footer_note": "Você pode criar um novo convite quando quiser.",
        },
    )


# ── ADR-141: digest de rascunhos de catálogo pendentes (ADR-140 D1 condição e) ──


def notify_catalog_drafts_pending(email: str, rascunhos_por_contexto: dict[str, list[dict[str, Any]]]) -> bool:
    """Digest consolidado de rascunhos de catálogo aguardando aprovação/rejeição.

    Um email por catalog-manager (não um email por rascunho — ver ADR-141) com
    todos os contextos/rascunhos pendentes no momento da execução do digest.
    """
    total = sum(len(versoes) for versoes in rascunhos_por_contexto.values())
    details = [
        (
            versao["version"],
            f"{contexto_id} — {versao.get('motivo', '')} (criado por {versao.get('created_by', '—')})",
        )
        for contexto_id, versoes in rascunhos_por_contexto.items()
        for versao in versoes
    ]
    return get_notification_service().send(
        to=email,
        subject=f"[Concilium] {total} rascunho(s) de catálogo aguardando aprovação",
        template="notification",
        context={
            "heading": f"{total} rascunho(s) de catálogo aguardando aprovação",
            "intro": (
                "Os seguintes rascunhos de contexto de catálogo estão pendentes de revisão "
                "(use aprovar_merge_catalogo ou rejeitar_rascunho_catalogo):"
            ),
            "details": details,
            "cta": None,
            "footer_note": "Este é um resumo periódico — novos rascunhos aparecem no próximo envio.",
        },
    )


# ── ADR-143 D7/D8: digest de visibilidade — "você foi consultado" ──────────────


def notify_visibility_queried(email: str, resumo: list[tuple[str, str, int]]) -> bool:
    """Digest consolidado de quem consultou a visibilidade deste usuário.

    Um email por destinatário (não um email por consulta — ADR-140 D1
    condições d/e: ser consultado é subproduto da leitura de terceiro, pode
    se repetir várias vezes em pouco tempo). `resumo`: lista de
    (observer_client_id, roles_do_observador_formatado, contagem).
    """
    total = sum(count for _, _, count in resumo)
    details = [(observer_id, f"{roles} — {count}x") for observer_id, roles, count in resumo]
    return get_notification_service().send(
        to=email,
        subject=f"[Concilium] Seu contato foi consultado {total}x desde o último aviso",
        template="notification",
        context={
            "heading": f"Seu contato foi consultado {total}x desde o último aviso",
            "intro": "Os seguintes usuários consultaram sua visibilidade (role/email) via listar_usuarios_visiveis:",
            "details": details,
            "cta": None,
            "footer_note": "Este é um resumo periódico — nenhuma ação é necessária.",
        },
    )
