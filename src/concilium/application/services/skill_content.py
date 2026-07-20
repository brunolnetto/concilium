"""Conteúdo compartilhado do skill de instruções do Concilium (ADR-144 D5/D6).

Promovido de `application/services/notifications.py::_read_skill_tutorial`
(ADR-123, anexo de onboarding) para uso compartilhado — a tool MCP
`obter_instrucoes_atualizadas` (ADR-144 D6) lê o mesmo arquivo, sem duplicar
path/fallback. `read_skill_content()` sempre lê do disco, nunca cacheia entre
chamadas — achado da investigação do ADR-144: o padrão de recurso `ui://`
(ADR-101) lê uma vez no boot do servidor, o que aqui anularia o propósito de
"sempre pegar a versão mais atual".
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

SKILL_PATH = (
    Path(__file__).resolve().parents[2] / "infrastructure" / "services" / "templates" / "concilium_usage_tutorial.skill"
)

SKILL_FALLBACK = (
    b"O tutorial de instalacao nao pode ser carregado neste envio. "
    b"Contate o administrador do Concilium para receber os passos de instalacao."
)

# ADR-144 D5: cabeçalho `# Versão: N` na primeira linha do .skill — contador
# manual incrementado a cada edição de conteúdo relevante (não a cada commit
# trivial). Mtime foi rejeitado como versão (ADR-144 A5) — não sobrevive a
# cópias/anexos de email.
_VERSION_HEADER_RE = re.compile(r"^#\s*Vers[aã]o:\s*(\d+)", re.IGNORECASE)


def read_skill_content() -> bytes:
    """Lê o conteúdo atual do skill de instruções — sempre do disco, nunca cacheado.

    Best-effort: erro de leitura (ex.: instalação empacotada sem o arquivo)
    não deve abortar o chamador — cai num placeholder.
    """
    try:
        return SKILL_PATH.read_bytes()
    except OSError:
        logger.warning("Falha ao ler %s — usando fallback.", SKILL_PATH)
        return SKILL_FALLBACK


def get_skill_version(content: bytes | None = None) -> int:
    """Extrai a versão do cabeçalho `# Versão: N` da primeira linha do skill.

    Retorna 0 se o conteúdo não tem cabeçalho de versão reconhecível (ex.:
    fallback de erro, conteúdo vazio, ou arquivo sem o header).
    """
    body = content if content is not None else read_skill_content()
    if not body:
        return 0
    first_line = body.decode("utf-8", errors="replace").splitlines()[0]
    match = _VERSION_HEADER_RE.match(first_line)
    return int(match.group(1)) if match else 0
