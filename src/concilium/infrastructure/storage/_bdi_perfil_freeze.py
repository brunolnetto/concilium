"""Helpers compartilhados: proteção do perfil BDI versionado (issue #123).

O perfil de BDI (`bdi/perfil_bdi.json` cabeça + snapshots imutáveis
`bdi/perfil_bdi_v{NNN:03d}.json`, gravados por `salvar_perfil_bdi` em
`presentation/mcp/tools/projeto.py`) vive na raiz do projeto, fora de qualquer
vN/plano — o congelamento de premissas do issue #121 não protegia esses
arquivos: nada impedia que uma versão/plano JÁ APROVADO ficasse órfão de uma
edição posterior do perfil de BDI que ele efetivamente usou.

A skill 06 (`_bdi_resolucao.py::_rbf_resolve_tabela_perfil`) resolve o perfil a
partir de `inputs.get("bdi_perfil") or inputs.get("perfil_bdi")` — um dict cru
(o mesmo payload persistido em `perfil_bdi_v{NNN}.json`, com campo `versao`
inteiro). Como esse dict só fica visível no `normalized_inputs` da skill que o
usa (normalmente "06-resultado-financeiro"), e `premissas_efetivas.json`
guarda só o ÚLTIMO snapshot completo (potencialmente de uma skill posterior,
ex. "09-relatorio-e-artefatos"), a versão de perfil BDI usada é extraída aqui
e gravada por-skill em `premissas_por_skill.json` (campo `bdi_perfil_versao`)
no momento do congelamento — sobrevive a skills subsequentes na mesma
aprovação.
"""

from __future__ import annotations

from typing import Any


def extract_bdi_perfil_versao(normalized_inputs: dict[str, Any]) -> int | None:
    """Extrai o campo inteiro `versao` de `inputs.bdi_perfil`/`inputs.perfil_bdi`, se presente e íntegro."""
    raw = normalized_inputs.get("bdi_perfil") or normalized_inputs.get("perfil_bdi")
    if isinstance(raw, dict):
        versao = raw.get("versao")
        if isinstance(versao, int) and not isinstance(versao, bool) and versao > 0:
            return versao
    return None


def bdi_perfil_versoes_referenciadas(por_skill: dict[str, dict[str, Any]]) -> set[int]:
    """Coleta o conjunto de versões de perfil BDI referenciadas nas premissas por skill."""
    versoes: set[int] = set()
    for registro in por_skill.values():
        if not isinstance(registro, dict):
            continue
        versao = registro.get("bdi_perfil_versao")
        if isinstance(versao, int) and not isinstance(versao, bool):
            versoes.add(versao)
    return versoes


def bdi_perfil_versao_filename(versao: int) -> str:
    return f"perfil_bdi_v{versao:03d}.json"
