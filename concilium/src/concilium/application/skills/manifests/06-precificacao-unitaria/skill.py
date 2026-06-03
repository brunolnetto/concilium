"""Skill 04 — Planejamento e BDI.

Calcula preço unitário (sem e com BDI) por item da EAP, decomposto em 4 categorias:
material, diesel, mão de obra, equipamentos (ADR-023: BDI auditável via TabelaBdi).

Ordem de precedência para BDI:
    1. inputs["bdi_aplicado"]  — override manual (4 categorias flat)
    2. inputs["tabela_bdi"]    — TabelaBdi serializada (ADR-023)
    3. DEFAULT_BDI_TABELA       — valores padrão da planilha rfi_catalog.xlsm (abril/2026)

Mapeamento de categorias ADR-023 -> modelo flat Planejamento.bdi:
    MAO_OBRA  -> mao_obra
    MATERIAL  -> material
    DIESEL    -> diesel
    SERVICOS  -> equipamentos (via tabela_bdi.servicos)
"""

from __future__ import annotations

from typing import Any

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import (
    CanonicalModel,
    Planejamento,
    ValidacaoItem,
)
from concilium.infrastructure.repositories.insumo import RepositorioInsumo

try:
    from concilium.domain.models.bdi import DEFAULT_BDI_TABELA, TabelaBdi
except Exception:
    DEFAULT_BDI_TABELA = None  # type: ignore[assignment]
    TabelaBdi = None  # type: ignore[assignment,misc]

try:
    from ._skill_helpers_a import (
        _build_equipe_lookup,
        _build_lookups,
        _process_eap_item,
        _validate_coverage,
    )
except ImportError:
    import importlib.util
    from pathlib import Path

    _here = Path(__file__).resolve().parent
    _spec = importlib.util.spec_from_file_location("skill06_helpers_a", _here / "_skill_helpers_a.py")
    _mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
    _build_equipe_lookup = _mod._build_equipe_lookup
    _build_lookups = _mod._build_lookups
    _process_eap_item = _mod._process_eap_item
    _validate_coverage = _mod._validate_coverage

_CATEGORIA_MAP = {
    "material": "material",
    "diesel": "diesel",
    "mao_obra": "mao_obra",
    "mão_obra": "mao_obra",
    "mao de obra": "mao_obra",
    "mão de obra": "mao_obra",
    "equipamento": "equipamentos",
    "equipamentos": "equipamentos",
}


def _extract_overrides(inputs: dict[str, Any]) -> dict | None:
    val = inputs.get("insumos_override")
    if isinstance(val, dict):
        return val
    return None


def _resolve_bdi(inputs: dict[str, Any], validacoes: list[ValidacaoItem]) -> dict[str, float]:
    def _to_flat_bdi(base: dict[str, Any]) -> dict[str, float]:
        material = float(base.get("material", 0.0) or 0.0)
        diesel = float(base.get("diesel", 0.0) or 0.0)
        mao_obra = float(base.get("mao_obra", 0.0) or 0.0)
        equipamentos_raw = base.get("equipamentos")

        if equipamentos_raw is None:
            # ADR-023 §D3: EQUIP BDI = 70% MAO_OBRA + 30% DIESEL
            equip = round((0.70 * mao_obra) + (0.30 * diesel), 6)
        else:
            equip = float(equipamentos_raw or 0.0)

        return {
            "material": material,
            "diesel": diesel,
            "mao_obra": mao_obra,
            "equipamentos": float(equip),
        }

    manual = inputs.get("bdi_aplicado")
    if isinstance(manual, dict):
        resolved = _to_flat_bdi(
            {
                "material": float(manual.get("material", 0.0) or 0.0),
                "diesel": float(manual.get("diesel", 0.0) or 0.0),
                "mao_obra": float(manual.get("mao_obra", 0.0) or 0.0),
                "servicos": manual.get("servicos"),
                "equipamentos": manual.get("equipamentos"),
            }
        )
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-BDI-FONTE",
                status="AVISO",
                mensagem="BDI aplicado via override manual (inputs.bdi_aplicado).",
            )
        )
        return resolved

    tabela = None
    tabela_raw = inputs.get("tabela_bdi")
    if TabelaBdi is not None and tabela_raw is not None:
        try:
            tabela = TabelaBdi.model_validate(tabela_raw) if isinstance(tabela_raw, dict) else tabela_raw
        except Exception as exc:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-BDI-PARSE",
                    status="AVISO",
                    mensagem=f"Falha ao parsear tabela_bdi: {exc}. Usando default.",
                )
            )

    if tabela is None:
        if DEFAULT_BDI_TABELA is not None:
            tabela = DEFAULT_BDI_TABELA
        else:
            return {"material": 0.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}

    result = _to_flat_bdi(
        {
            "material": float(tabela.material.bdi_total),
            "diesel": float(tabela.diesel.bdi_total),
            "mao_obra": float(tabela.mao_obra.bdi_total),
            "servicos": float(tabela.servicos.bdi_total),
        }
    )
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-BDI-FONTE",
            status="OK",
            mensagem="BDI aplicado via tabela (inputs.tabela_bdi ou DEFAULT_BDI_TABELA).",
        )
    )
    return result


def _validar_bdi_dentro_da_faixa(bdi_aplicado: dict[str, float]) -> list[str]:
    violacoes: list[str] = []
    for categoria, valor in bdi_aplicado.items():
        if valor < 0 or valor > 1:
            violacoes.append(f"{categoria}={valor:.4f} (esperado entre 0 e 1)")
    return violacoes


def _as_bool(value: Any) -> bool:
    """Converte entradas heterogêneas em bool sem tratar 'false' como True."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "f", "no", "n", "off", ""}:
            return False
    return False


def run_precificacao_unitaria(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    catalogo: dict[str, Any],
    perfil: dict[str, Any],
    catalog_session: object | None = None,  # ADR-100
) -> SkillResult:
    """Popula seção 'planejamento' do canônico."""
    validacoes: list[ValidacaoItem] = []

    if not canonical_in.eap:
        validacoes.append(ValidacaoItem(codigo="VAL-PLAN-PRECONDICAO", status="ERRO", mensagem="EAP vazia"))
        return SkillResult(canonical_in, validacoes)

    cpu_lookup, insumo_lookup, prod_lookup = _build_lookups(catalogo)
    repo = RepositorioInsumo(catalogo)
    data_base = canonical_in.projeto.data_base_orcamento
    overrides = _extract_overrides(inputs)
    jurisdicao_id = inputs.get("jurisdicao_id")

    # NEP-032: parâmetros para precificação bottom-up (diesel + encargos)
    from concilium.domain.constants import ENCARGOS_CLT, ENCARGOS_MENSALISTA, PRECO_DIESEL_REFERENCIA
    preco_diesel = float(inputs.get("preco_diesel", PRECO_DIESEL_REFERENCIA))
    for _ins in catalogo.get("insumos", []):
        if _ins.get("codigo") in ("MA-DIESEL-S10", "DIESEL-S10"):
            preco_diesel = float(_ins.get("preco_unitario", preco_diesel) or preco_diesel)
            break
    alpha_clt = float(inputs.get("percentual_encargos", ENCARGOS_CLT))
    alpha_mensalista = float(inputs.get("percentual_encargos_mensalista", ENCARGOS_MENSALISTA))

    bdi_aplicado = _resolve_bdi(inputs, validacoes)
    planejamento_item_overrides = inputs.get("planejamento_item_overrides", {})
    benchmark_mode = _as_bool(inputs.get("benchmark_mode")) or _as_bool(inputs.get("modo_benchmark"))
    # ADR-038: compensação por custo real de equipe — opt-in (default False).
    # Quando True, substitui o preço unitário pelo custo total da equipe dividido
    # pela quantidade, tornando o custo total INDEPENDENTE da quantidade (bug latente
    # quando duas EAPs usam a mesma configuração de equipe com quantidades diferentes).
    # Use apenas se as equipes de skill-05 forem dimensionadas proporcionalmente às
    # quantidades de cada item; caso contrário itens idênticos ficam com custo igual
    # independentemente do volume. Para precificação baseline, manter False.
    apply_compensation = (
        _as_bool(inputs.get("apply_adr038_compensation", False)) and not benchmark_mode
    )

    violacoes_bdi = _validar_bdi_dentro_da_faixa(bdi_aplicado)
    if violacoes_bdi:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-POL-BDI",
                status="AVISO",
                mensagem=f"BDI fora da faixa permitida: {'; '.join(violacoes_bdi)}",
            )
        )
    else:
        validacoes.append(ValidacaoItem(codigo="VAL-POL-BDI", status="OK"))

    plan_out: list[Planejamento] = []
    erros_eap: list[str] = []
    erros_insumo: set[str] = set()
    equip_sem_decomp: set[str] = set()
    equipe_lookup = _build_equipe_lookup(canonical_in)

    for item in canonical_in.eap:
        _process_eap_item(
            item,
            cpu_lookup,
            insumo_lookup,
            prod_lookup,
            equipe_lookup,
            planejamento_item_overrides,
            bdi_aplicado,
            repo,
            jurisdicao_id,
            overrides,
            data_base,
            plan_out,
            erros_eap,
            erros_insumo,
            equip_sem_decomp,
            validacoes,
            apply_compensation,
            benchmark_mode,
            preco_diesel=preco_diesel,
            alpha_clt=alpha_clt,
            alpha_mensalista=alpha_mensalista,
            catalog_session=catalog_session,  # ADR-100
        )

    if benchmark_mode:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PLAN-BENCHMARK",
                status="INFO",
                mensagem="Modo benchmark: precificacao mantida no baseline de catalogo (ADR-038 desabilitada).",
            )
        )

    if erros_eap:
        validacoes.append(
            ValidacaoItem(codigo="VAL-EAP-01", status="ERRO", mensagem=f"CPUs não encontradas: {', '.join(erros_eap)}")
        )
    if erros_insumo:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PLAN-INSUMO",
                status="ERRO",
                mensagem=f"Insumos da CPU não encontrados no catálogo: {', '.join(erros_insumo)}",
            )
        )
    if equip_sem_decomp:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-EQUIP-DECOMP",
                status="AVISO",
                mensagem=(
                    f"Insumos EQUIPAMENTO sem decomposicao_equip: {', '.join(sorted(equip_sem_decomp))}."
                    " Mantendo custo na categoria equipamentos."
                    " Enriqueça o catálogo com DecomposicaoEquipamento para BDI auditável (ADR-023 §D3)."
                ),
            )
        )

    if benchmark_mode:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-COB-SKIPPED-BENCHMARK",
                status="INFO",
                mensagem=(
                    "Modo benchmark: validacao de cobertura operacional (VAL-COB-*) desabilitada "
                    "para preservar comparacao em baseline de catalogo."
                ),
            )
        )
    else:
        _validate_coverage(canonical_in, plan_out, validacoes)
    novo = canonical_in.model_copy(update={"planejamento": plan_out})
    return SkillResult(novo, validacoes)
