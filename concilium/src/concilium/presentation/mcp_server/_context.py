"""Helpers compartilhados do MCP Server — configuração, acesso a projetos e utilitários."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from concilium.application.runtime import _GATE_SKILLS, Runtime  # noqa: F401 (re-exportado)
from concilium.application.runtime import RuntimeError as ConciliumRuntimeError  # noqa: F401 (re-exportado)
from concilium.application.skills.registry import SkillRegistry
from concilium.infrastructure.storage.project import ProjectStore


def _tools_root() -> Path:
    """Raiz do repositório, independente do CWD."""
    # Sobe 4 níveis: mcp_server -> presentation -> concilium -> src -> RAIZ
    return Path(__file__).resolve().parents[4]


# ── Configuração via env vars ──────────────────────────────────────────────


def _resolve_env_path(*, primary: str, default: str) -> Path:
    if os.environ.get(primary):
        return Path(os.environ[primary])
    return Path(default)


def _config_root() -> Path:
    return _resolve_env_path(
        primary="CONCILIUM_CONFIG_ROOT",
        default=_tools_root() / "config",  # type: ignore[arg-type]
    )


def _projetos_root() -> Path:
    return _resolve_env_path(
        primary="CONCILIUM_PROJECTS_ROOT",
        default=_tools_root() / "projetos",  # type: ignore[arg-type]
    )


def _runtime() -> Runtime:
    return Runtime(_config_root())


def _lifecycle_coordinator() -> Any:
    from concilium.application.orchestrators.lifecycle_coordinator import LifecycleCoordinator

    return LifecycleCoordinator(_runtime())


def _project(project_id: str) -> ProjectStore:
    proj_root = _projetos_root() / project_id
    if not proj_root.exists():
        raise ValueError(f"Projeto '{project_id}' não encontrado em {_projetos_root()}")
    return ProjectStore(proj_root)


# ── ADR-022: Mapa de predecessores GATE por skill ──────────────────────────
# Construído dinamicamente a partir do SkillRegistry.
# Chave: skill_id  ->  conjunto de skills GATE que devem ter executado com sucesso.
# Se qualquer membro do conjunto estiver em canonical.pipeline_blocked_from, a skill
# é marcada BLOQUEADO sem executar, e seu ID é adicionado ao pipeline_blocked_from.


def _build_gate_predecessors() -> dict[str, frozenset[str]]:
    """Constrói _GATE_PREDECESSORS a partir do SkillRegistry.

    Usa _GATE_SKILLS (importado de runtime) como conjunto autoritativo de skills
    GATE — eliminando a re-derivação a partir do registry (DRY).
    Para cada skill, extrai suas dependências diretas e mantém apenas as GATE.
    """
    try:
        registry = SkillRegistry()
        result: dict[str, frozenset[str]] = {}
        for skill_id, metadata in registry.get_all_skills().items():
            gate_deps = frozenset(
                dep_id
                for dep_id in metadata.depends_on_skills
                if dep_id in _GATE_SKILLS  # fonte única: runtime._GATE_SKILLS
            )
            result[skill_id] = gate_deps
        return result
    except Exception as e:
        import warnings

        warnings.warn(f"Erro ao construir _GATE_PREDECESSORS: {e}", stacklevel=2)
        return {}


_GATE_PREDECESSORS: dict[str, frozenset[str]] = _build_gate_predecessors()

# ── Versão do schema de resposta MCP (ADR-018 §D5) ─────────────────────────

RESPONSE_SCHEMA_VERSION = "2026-05-03"

# Contexto de sessão — trace_id gerado uma vez por sessão do servidor
_session_context: dict[str, str] = {}


def _get_or_create_trace_id() -> str:
    if "trace_id" not in _session_context:
        _session_context["trace_id"] = str(uuid.uuid4())
    return _session_context["trace_id"]


def _wrap_response(data: dict[str, Any]) -> dict[str, Any]:
    """Envolve resposta MCP com schema_version e trace_id (ADR-018 §D5)."""
    return {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "trace_id": _get_or_create_trace_id(),
        **data,
    }


# ── Helpers de negócio (fora do server para testabilidade) ─────────────────


def _di_build_indices(catalogo: dict) -> tuple[dict, dict]:
    """Build insumos_idx and cpus_idx lookup dicts from the catalog."""
    insumos_idx: dict = {}
    for ins in catalogo.get("insumos", []):
        cod = ins.get("codigo") or ins.get("id")
        if cod:
            insumos_idx[cod] = ins
    cpus_idx: dict = {c["codigo"]: c for c in catalogo.get("cpus", []) if "codigo" in c}
    return insumos_idx, cpus_idx


def _di_collect_max_equipe(canonical, cpus_idx: dict) -> tuple[dict, dict]:
    """Collect max equipamento quantities and max funcao pessoas across all EAP items."""
    equip_max: dict = {}
    func_max: dict = {}
    for item in canonical.eap or []:
        cpu = cpus_idx.get(item.cpu_id, {})
        equipe = cpu.get("equipe") or cpu.get("composicao_padrao_equipe") or {}
        for eq in equipe.get("equipamentos", []):
            eid = eq.get("equip_id")
            qtd = int(eq.get("num_unidades", 1))
            if eid:
                key = f"EQUIP-{eid}"
                equip_max[key] = max(equip_max.get(key, 0), qtd)
        for fn in equipe.get("funcoes", []):
            fid = fn.get("funcao_id")
            npessoas = int(fn.get("num_pessoas", 1))
            if fid:
                key = f"FUNC-{fid}"
                func_max[key] = max(func_max.get(key, 0), npessoas)
    return equip_max, func_max


def _di_build_equip_resources(
    equip_max: dict, insumos_idx: dict, horas_mes: float, dias_mes: float
) -> tuple[list, list]:
    """Build tipos_recurso and pool_inicial entries for equipamentos."""
    tipos: list = []
    pool: list = []
    for tipo_id, qtd in equip_max.items():
        raw_id = tipo_id.removeprefix("EQUIP-")
        ins = insumos_idx.get(raw_id, {})
        custo_hora = float(ins.get("preco_unitario", 0) or 0)
        horas_ins = float((ins.get("atributos_especificos") or {}).get("horas_mes", horas_mes))
        custo_dia = round(custo_hora * (horas_ins / dias_mes), 2)
        tipos.append(
            {
                "id": tipo_id,
                "nome": ins.get("descricao", raw_id),
                "categoria": "EQUIPAMENTO",
                "custo_unitario_dia": custo_dia,
            }
        )
        pool.append({"tipo_id": tipo_id, "quantidade_total": qtd})
    return tipos, pool


def _di_build_func_resources(func_max: dict, insumos_idx: dict, horas_mes: float, dias_mes: float) -> tuple[list, list]:
    """Build tipos_recurso and pool_inicial entries for funcoes/MO."""
    tipos: list = []
    pool: list = []
    for tipo_id, npessoas in func_max.items():
        raw_id = tipo_id.removeprefix("FUNC-")
        ins = insumos_idx.get(raw_id, {})
        preco_unit = float(ins.get("preco_unitario", 0) or 0)
        unidade = ins.get("unidade", "mes")
        salario_mensal = preco_unit * horas_mes if unidade == "h" else preco_unit
        custo_dia = round(salario_mensal / dias_mes, 2)
        tipos.append(
            {
                "id": tipo_id,
                "nome": ins.get("descricao", raw_id),
                "categoria": "EQUIPE",
                "custo_unitario_dia": custo_dia,
            }
        )
        pool.append({"tipo_id": tipo_id, "quantidade_total": npessoas})
    return tipos, pool


def _derivar_inputs_01A(rt: Runtime, store: ProjectStore, version: str) -> dict[str, Any]:
    """
    Deriva tipos_recurso e pool_inicial para 01A a partir das CPUs da EAP.

    Lê composicao_padrao_equipe.equipamentos E .funcoes de cada CPU usada no projeto,
    cruza com o catálogo de insumos para obter custo_unitario_dia, e retorna
    o dict de inputs pronto para run_skill('03-catalogo-de-recursos', ..., inputs=...).

    Convenção de IDs (alinhada com 03A-derivar-requisitos):
        Equipamentos -> 'EQUIP-{equip_id}'  (ex: 'EQUIP-ESCAV-HID-38T')
        Funções/MO   -> 'FUNC-{funcao_id}'  (ex: 'FUNC-OPER-ESCAV-HID')

    Usado por avancar_pipeline quando o agente não fornece inputs explícitos.
    """
    canonical = store.load_canonical(version)
    if canonical is None:
        return {}

    try:
        contexto = rt.load_contexto(store.meta["contexto_id"])
        catalogo = rt.load_catalogo(contexto.catalogo_id)
    except Exception:
        return {}

    insumos_idx, cpus_idx = _di_build_indices(catalogo)
    equip_max, func_max = _di_collect_max_equipe(canonical, cpus_idx)
    if not equip_max and not func_max:
        return {}

    from concilium.domain.constants import SEMANAS_POR_MES as _SEMANAS_POR_MES
    from concilium.domain.constants import HORAS_MES_REGIME_6x1 as _HORAS_MES_CONST

    _HORAS_MES = _HORAS_MES_CONST
    _DIAS_MES = _SEMANAS_POR_MES * 7.0

    tipos_e, pool_e = _di_build_equip_resources(equip_max, insumos_idx, _HORAS_MES, _DIAS_MES)
    tipos_f, pool_f = _di_build_func_resources(func_max, insumos_idx, _HORAS_MES, _DIAS_MES)
    return {"tipos_recurso": tipos_e + tipos_f, "pool_inicial": pool_e + pool_f}
