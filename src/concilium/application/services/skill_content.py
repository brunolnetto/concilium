"""Conteúdo compartilhado do skill de instruções do Concilium (ADR-144 D5/D6).

Promovido de `application/services/notifications.py::_read_skill_tutorial`
(ADR-123, anexo de onboarding) para uso compartilhado — a tool MCP
`obter_instrucoes_atualizadas` (ADR-144 D6) lê o mesmo arquivo, sem duplicar
path/fallback. `read_skill_content()` sempre lê do disco, nunca cacheia entre
chamadas — achado da investigação do ADR-144: o padrão de recurso `ui://`
(ADR-101) lê uma vez no boot do servidor, o que aqui anularia o propósito de
"sempre pegar a versão mais atual".

O conteúdo vive em `SKILL.md` dentro de uma pasta própria (formato oficial de
Skill da Anthropic: pasta como raiz do zip, front matter YAML com `name` e
`description`) — não mais um arquivo `.skill` solto contendo markdown puro.
Isso permite empacotar um `.skill` que é de fato um zip válido
(`package_skill_zip()`), importável como Skill real no Claude, em vez de um
anexo de email cujo conteúdo nunca foi um zip.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "infrastructure" / "services" / "templates"
SKILL_DIR = _TEMPLATES_DIR / "concilium-usage-tutorial"
SKILL_PATH = SKILL_DIR / "SKILL.md"

SKILL_FALLBACK = (
    b"O tutorial de instalacao nao pode ser carregado neste envio. "
    b"Contate o administrador do Concilium para receber os passos de instalacao."
)

# ADR-144 D5: campo `version:` no front matter YAML do SKILL.md — contador
# manual incrementado a cada edição de conteúdo relevante (não a cada commit
# trivial). Mtime foi rejeitado como versão (ADR-144 A5) — não sobrevive a
# cópias/anexos de email. O front matter (delimitado por `---`) é o único
# lugar buscado — evita casar "version:" citado incidentalmente no corpo.
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---", re.DOTALL)
_VERSION_FIELD_RE = re.compile(r"^version:\s*(\d+)\s*$", re.IGNORECASE | re.MULTILINE)


def read_skill_content() -> bytes:
    """Lê o conteúdo atual do SKILL.md — sempre do disco, nunca cacheado.

    Best-effort: erro de leitura (ex.: instalação empacotada sem o arquivo)
    não deve abortar o chamador — cai num placeholder.
    """
    try:
        return SKILL_PATH.read_bytes()
    except OSError:
        logger.warning("Falha ao ler %s — usando fallback.", SKILL_PATH)
        return SKILL_FALLBACK


def get_skill_version(content: bytes | None = None) -> int:
    """Extrai a versão do campo `version:` no front matter do SKILL.md.

    Retorna 0 se o conteúdo não tem front matter reconhecível (ex.: fallback
    de erro, conteúdo vazio, ou arquivo sem front matter).
    """
    body = content if content is not None else read_skill_content()
    if not body:
        return 0
    text = body.decode("utf-8", errors="replace")
    frontmatter_match = _FRONTMATTER_RE.match(text)
    if not frontmatter_match:
        return 0
    version_match = _VERSION_FIELD_RE.search(frontmatter_match.group(1))
    return int(version_match.group(1)) if version_match else 0


def package_skill_zip() -> bytes:
    """Empacota o SKILL.md atual num `.skill` que é de fato um zip válido.

    Formato oficial de Skill da Anthropic: a pasta do skill (`SKILL_DIR.name`)
    é a raiz do zip — não o conteúdo solto, nem uma subpasta aninhada. Usado
    só para o anexo de email (ADR-134); a tool MCP `obter_instrucoes_atualizadas`
    continua lendo `read_skill_content()` puro, pois entrega texto para o
    agente ler, não um pacote para importar.
    """
    content = read_skill_content()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{SKILL_DIR.name}/SKILL.md", content)
    return buffer.getvalue()
