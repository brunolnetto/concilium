"""Skill 07 — Adapter de Saída (gera JSON + Excel .xlsm).

Skill 07 produz o output principal:
1. JSON estruturado (para validação, logs, API)
2. Excel .xlsm auditável (para stakeholders, relatórios)

Estrutura Excel gerada:
  - RESUMO: metadados do projeto + indicadores financeiros
  - PLANEJAMENTO: itens da EAP com preços, BDI, subtotais
  - EQUIPES: composição, custos e ponto de equilíbrio
  - INDIRETOS: custos indiretos por categoria
  - RESULTADO: resultado financeiro consolidado
"""

from typing import Any

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import CanonicalModel, ValidacaoItem

try:
    from ._skill_helpers_a import (
        _add_criticidade_validacoes,
        _build_equipe_rows,
        _build_graficos_section,
        _build_indireto_rows,
        _build_planejamento_rows,
        _gerar_excel_bytes,
        _gerar_live_model,
        _gerar_memorial_json_bytes,
        _rra_build_criticidade_lookup,
        _rra_build_relatorio,
        _week_to_month,
    )
except ImportError:
    import importlib.util
    from pathlib import Path

    _here = Path(__file__).resolve().parent
    _spec = importlib.util.spec_from_file_location("skill09_helpers_a", _here / "_skill_helpers_a.py")
    _mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]

    _add_criticidade_validacoes = _mod._add_criticidade_validacoes
    _build_equipe_rows = _mod._build_equipe_rows
    _build_graficos_section = _mod._build_graficos_section
    _build_indireto_rows = _mod._build_indireto_rows
    _build_planejamento_rows = _mod._build_planejamento_rows
    _gerar_excel_bytes = _mod._gerar_excel_bytes
    _gerar_live_model = _mod._gerar_live_model
    _gerar_memorial_json_bytes = _mod._gerar_memorial_json_bytes
    _rra_build_criticidade_lookup = _mod._rra_build_criticidade_lookup
    _rra_build_relatorio = _mod._rra_build_relatorio
    _week_to_month = _mod._week_to_month

_MESES_PT = {
    1: "Jan",
    2: "Fev",
    3: "Mar",
    4: "Abr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Out",
    11: "Nov",
    12: "Dez",
}


def run_relatorio_e_artefatos(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    perfil: dict[str, Any] | None = None,
) -> SkillResult:
    """Produz relatório estruturado baseado em template."""
    validacoes: list[ValidacaoItem] = []
    gerar_excel = bool(inputs.get("gerar_excel", True))
    gerar_modelo_vivo = bool(inputs.get("gerar_modelo_vivo", False))

    if canonical_in.resultado is None:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ADAPTER-PRECONDICAO",
                status="ERRO",
                mensagem="Adapter requer resultado consolidado (skill 06)",
            )
        )
        return SkillResult(canonical_in, validacoes)

    proj = canonical_in.projeto
    res = canonical_in.resultado

    criticidade_lookup = _rra_build_criticidade_lookup(canonical_in)
    has_criticidade = bool(criticidade_lookup)
    _add_criticidade_validacoes(canonical_in, has_criticidade, criticidade_lookup, validacoes)

    eap_by_item_id = {e.item_id: e for e in canonical_in.eap}
    planejamento_rows = _build_planejamento_rows(canonical_in, criticidade_lookup, has_criticidade)
    equipe_rows, analise_composicional = _build_equipe_rows(canonical_in)
    indireto_rows = _build_indireto_rows(canonical_in, inputs)

    if not canonical_in.planejamento:
        validacoes.append(
            ValidacaoItem(codigo="VAL-ADAPTER-01", status="AVISO", mensagem="Planejamento vazio — relatório parcial")
        )
    else:
        validacoes.append(ValidacaoItem(codigo="VAL-ADAPTER-01", status="OK"))

    acts = canonical_in.cronograma.scheduled_activities if canonical_in.cronograma else []
    _month_set: set = set()
    for _act in acts:
        for _wk in _act.distribuicao_semanal:
            _month_set.add(_week_to_month(_wk))
    project_months = sorted(_month_set)
    graficos = _build_graficos_section(canonical_in, eap_by_item_id, project_months)

    relatorio = _rra_build_relatorio(
        canonical_in,
        proj,
        res,
        planejamento_rows,
        equipe_rows,
        analise_composicional,
        indireto_rows,
        graficos,
        eap_by_item_id,
        project_months,
    )

    novo = canonical_in.model_copy(update={})
    novo._relatorio_saida = relatorio  # type: ignore[attr-defined]

    excel_bytes = _gerar_excel_bytes(canonical_in, validacoes, gerar_excel)
    live_bytes = _gerar_live_model(canonical_in, validacoes, gerar_modelo_vivo)
    memorial_json_bytes = _gerar_memorial_json_bytes(canonical_in)

    result = SkillResult(novo, validacoes)
    result.relatorio = relatorio  # type: ignore[attr-defined]
    result.excel_bytes = excel_bytes  # type: ignore[attr-defined]
    result.excel_live_bytes = live_bytes  # type: ignore[attr-defined]
    result.memorial_bdi_json = memorial_json_bytes  # type: ignore[attr-defined]
    return result
