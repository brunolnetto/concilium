"""Skill 03 — Equipes e Alocação (Consolidado).

Consolida:
1. Dimensionamento de Equipes (antiga 03)
2. Derivação de Requisitos (antiga 03A)
3. Alocação de Recursos (antiga 03B)
4. Validação de Compartilhamento (antiga 03C)

Objetivo: Reduzir fragmentação e garantir consistência atômica entre dimensionamento e alocação.
"""

from __future__ import annotations

from typing import Any

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import (
    CanonicalModel,
    ConflitoPico,
    RecursoContrato,
    ValidacaoItem,
)
from concilium.infrastructure.repositories.insumo import RepositorioInsumo

# --- Utils de Dimensionamento (da Skill 03) ---

try:
    from . import _skill_helpers_compartilhamento as _mod_compartilhamento  # ty: ignore[unresolved-import]
    from . import _skill_helpers_instancias as _mod_instancias  # ty: ignore[unresolved-import]
    from . import _skill_helpers_planejamento as _mod_planejamento  # ty: ignore[unresolved-import]
    from . import _skill_helpers_pool as _mod_pool  # ty: ignore[unresolved-import]
    from ._skill_helpers_a import (  # ty: ignore[unresolved-import]  # runtime-only: loaded via importlib below
        _build_dimensionamento,
        _calcular_permanencia_e_custo_total,
        _RepoCtx,
        particionar_contrato,
    )
    from ._skill_helpers_b import (  # ty: ignore[unresolved-import]  # runtime-only: loaded via importlib below
        _build_alocacoes_pool,
        _build_requisitos_e_tipos,
    )
    from ._skill_helpers_compartilhamento import (  # ty: ignore[unresolved-import]  # runtime-only: loaded via importlib below
        _deve_processar_compartilhamento,
        _processar_oportunidades_paralelo,
    )
    from ._skill_helpers_instancias import (  # ty: ignore[unresolved-import]  # runtime-only: loaded via importlib below
        _preencher_custo_inst_estagio_f3,
        _processar_instancias_recurso,
    )
    from ._skill_helpers_planejamento import (  # ty: ignore[unresolved-import]  # runtime-only: loaded via importlib below
        _aplicar_reconciliacao_planejamento,
        _resolve_planejamento_maps,
    )
    from ._skill_helpers_pool import (  # ty: ignore[unresolved-import]  # runtime-only: loaded via importlib below
        _build_pool_setup,
        _processar_pool_contratos,
        _resolve_rcpsp_spec,
        _validar_estagio1_inst_none,
    )
    from ._skill_helpers_pre import (  # ty: ignore[unresolved-import]  # runtime-only: loaded via importlib below
        _build_pre_processamento_compartilhamento,
    )
except ImportError:
    import importlib.util
    import sys
    import types
    from pathlib import Path

    _here = Path(__file__).resolve().parent
    _spec_a = importlib.util.spec_from_file_location(
        "skill05_helpers_a", _here / "_skill_helpers_a" / "__init__.py"
    )
    if _spec_a is None or _spec_a.loader is None:
        raise ImportError("Cannot load _skill_helpers_a.py via importlib") from None
    _mod_a = importlib.util.module_from_spec(_spec_a)
    sys.modules["skill05_helpers_a"] = _mod_a  # necessário p/ imports relativos entre seus submódulos
    _spec_a.loader.exec_module(_mod_a)

    _spec_b = importlib.util.spec_from_file_location("skill05_helpers_b", _here / "_skill_helpers_b.py")
    if _spec_b is None or _spec_b.loader is None:
        raise ImportError("Cannot load _skill_helpers_b.py via importlib") from None
    _mod_b = importlib.util.module_from_spec(_spec_b)
    _spec_b.loader.exec_module(_mod_b)

    _spec_pre = importlib.util.spec_from_file_location(
        "skill05_helpers_pre", _here / "_skill_helpers_pre" / "__init__.py"
    )
    if _spec_pre is None or _spec_pre.loader is None:
        raise ImportError("Cannot load _skill_helpers_pre.py via importlib") from None
    _mod_pre = importlib.util.module_from_spec(_spec_pre)
    sys.modules["skill05_helpers_pre"] = _mod_pre  # necessário p/ imports relativos entre seus submódulos
    _spec_pre.loader.exec_module(_mod_pre)

    # Os submódulos extraídos de skill.py (_skill_helpers_planejamento/pool/
    # instancias/compartilhamento) fazem imports relativos entre si e para
    # _skill_helpers_a/_skill_helpers_pre (ex.: _skill_helpers_instancias importa
    # de _skill_helpers_planejamento e de _skill_helpers_a). Para que essas
    # referências resolvam quando skill.py é carregado standalone, registramos
    # aqui um pacote sintético mínimo — mesma técnica de `_ensure_skill_package`.
    _pkg_name = "_skill05_equipes_helpers"
    if _pkg_name not in sys.modules:
        _pkg = types.ModuleType(_pkg_name)
        _pkg.__path__ = [str(_here)]
        _pkg.__package__ = _pkg_name
        sys.modules[_pkg_name] = _pkg

    def _load_sibling(short_name: str, filename: str):
        mod_name = f"{_pkg_name}.{short_name}"
        if mod_name in sys.modules:
            return sys.modules[mod_name]
        spec = importlib.util.spec_from_file_location(mod_name, _here / filename)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {filename} via importlib") from None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod

    _mod_planejamento = _load_sibling("_skill_helpers_planejamento", "_skill_helpers_planejamento.py")
    _mod_pool = _load_sibling("_skill_helpers_pool", "_skill_helpers_pool.py")
    _mod_instancias = _load_sibling("_skill_helpers_instancias", "_skill_helpers_instancias.py")
    _mod_compartilhamento = _load_sibling("_skill_helpers_compartilhamento", "_skill_helpers_compartilhamento.py")

    _RepoCtx = _mod_a._RepoCtx
    _build_dimensionamento = _mod_a._build_dimensionamento
    _calcular_permanencia_e_custo_total = _mod_a._calcular_permanencia_e_custo_total
    particionar_contrato = _mod_a.particionar_contrato
    _build_alocacoes_pool = _mod_b._build_alocacoes_pool
    _build_requisitos_e_tipos = _mod_b._build_requisitos_e_tipos
    _build_pre_processamento_compartilhamento = _mod_pre._build_pre_processamento_compartilhamento
    _resolve_planejamento_maps = _mod_planejamento._resolve_planejamento_maps
    _aplicar_reconciliacao_planejamento = _mod_planejamento._aplicar_reconciliacao_planejamento
    _validar_estagio1_inst_none = _mod_pool._validar_estagio1_inst_none
    _build_pool_setup = _mod_pool._build_pool_setup
    _resolve_rcpsp_spec = _mod_pool._resolve_rcpsp_spec
    _processar_pool_contratos = _mod_pool._processar_pool_contratos
    _processar_instancias_recurso = _mod_instancias._processar_instancias_recurso
    _preencher_custo_inst_estagio_f3 = _mod_instancias._preencher_custo_inst_estagio_f3
    _deve_processar_compartilhamento = _mod_compartilhamento._deve_processar_compartilhamento
    _processar_oportunidades_paralelo = _mod_compartilhamento._processar_oportunidades_paralelo


def run_equipes_e_alocacao(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    catalogo: dict[str, Any],
) -> SkillResult:
    """Consolida dimensionamento, requisitos e alocação de equipes diretas."""
    benchmark_mode = bool(inputs.get("benchmark_mode") or inputs.get("modo_benchmark"))
    validacoes: list[ValidacaoItem] = []
    repo = RepositorioInsumo(catalogo)
    data_base = canonical_in.projeto.data_base_orcamento
    overrides = inputs.get("insumos_override") if isinstance(inputs.get("insumos_override"), dict) else None
    jurisdicao_id = inputs.get("jurisdicao_id")
    ctx = _RepoCtx(repo, jurisdicao_id, overrides, data_base)

    equipes = _build_dimensionamento(canonical_in, inputs, catalogo, ctx, validacoes)

    # ADR-107: Reconciliar custo_total com planejamento (fonte de verdade)
    # Se spec.planejamento[item_id] existe, use seu custo_sem_bdi como custo_total
    planejamento_map, planejamento_ref_map = _resolve_planejamento_maps(canonical_in, inputs, benchmark_mode)
    _aplicar_reconciliacao_planejamento(equipes, planejamento_map, planejamento_ref_map, validacoes)

    # ADR-104 Checkpoint 1: Estágio 1 — custo_inst_* deve estar None (sem pool contracts ainda)
    _validar_estagio1_inst_none(equipes, validacoes)

    cron_lookup, cpu_lookup, prod_lookup, horas_semana = _build_pool_setup(canonical_in, catalogo)

    # ADR-071/073: Pool Contract Model + Perpetuation Chains
    contratos_recurso: list[RecursoContrato] = []
    cadeias_perpetuacao: list = []
    rcpsp_spec, rcpsp_derivado = _resolve_rcpsp_spec(inputs, canonical_in, catalogo)
    if rcpsp_spec:
        contratos_recurso, cadeias_perpetuacao = _processar_pool_contratos(
            equipes,
            rcpsp_spec,
            rcpsp_derivado,
            cron_lookup,
            validacoes,
            cpu_lookup,
            prod_lookup,
            horas_semana,
            benchmark_mode,
        )

    # ADR-077: mapa instancial de utilização — executado quando há pool contracts
    instancias_recurso, composicao_equipes_atividade, resumo_utilizacao_contratos = _processar_instancias_recurso(
        contratos_recurso,
        rcpsp_spec,
        cron_lookup,
        validacoes,
        cadeias_perpetuacao,
        equipes,
        benchmark_mode,
        planejamento_map,
        planejamento_ref_map,
    )

    # ADR-106 F3: preenche custo_inst_* para equipes sem pool contract (NEP-040 Fase 4 completa)
    _preencher_custo_inst_estagio_f3(equipes)

    # ADR-078: pré-processamento estrutural de compartilhamento
    relatorio_oportunidades = None
    if _deve_processar_compartilhamento(contratos_recurso, rcpsp_spec):
        relatorio_oportunidades = _build_pre_processamento_compartilhamento(
            contratos_recurso, rcpsp_spec, cron_lookup, validacoes
        )

    # ADR-110: detecção automática de oportunidades de compartilhamento paralelo
    # Executado quando há schedule, resource_costs e pool contracts disponíveis.
    relatorio_oportunidades = _processar_oportunidades_paralelo(
        relatorio_oportunidades, canonical_in, contratos_recurso, rcpsp_spec, validacoes
    )

    requisitos, tipos = _build_requisitos_e_tipos(equipes, canonical_in, cron_lookup, validacoes)
    alocacoes, pool_dict = _build_alocacoes_pool(requisitos, canonical_in, tipos)
    conflitos: list[ConflitoPico] = []
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-EQP-ALOC",
            status="OK",
            mensagem=f"Equipes ({len(equipes)}) e Alocações ({len(alocacoes)}) processadas.",
        )
    )
    novo = canonical_in.model_copy(
        update={
            "equipes_diretas": equipes,
            "contratos_recurso": contratos_recurso,
            "cadeias_perpetuacao": cadeias_perpetuacao,
            "instancias_recurso": instancias_recurso,
            "composicao_equipes_atividade": composicao_equipes_atividade,
            "resumo_utilizacao_contratos": resumo_utilizacao_contratos,
            "relatorio_oportunidades": relatorio_oportunidades,
            "tipos_recurso": list(tipos.values()),
            "recurso_pool": list(pool_dict.values()),
            "requisitos": requisitos,
            "alocacoes": alocacoes,
            "conflitos_pico": conflitos,
        }
    )
    return SkillResult(novo, validacoes)
