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
from concilium.domain.models.bdi import (
    DEFAULT_BDI_TABELA,
    TabelaBdi,
    TaxSimulationScenario,
    resolver_bdi_cbs_ibs,
    resolver_componentes_bdi,
)
from concilium.domain.models.canonical import (
    BdiCategorias,
    CanonicalModel,
    Planejamento,
    PrecoUnitarioCategoria,
    SubtotalCategorias,
    SubtotalSemBdiComBdi,
    ValidacaoItem,
)
from concilium.infrastructure.repositories.insumo import RepositorioInsumo


def _get_bdi_value(manual: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key in manual and manual.get(key) is not None:
            try:
                return float(manual.get(key) or 0.0)
            except Exception:
                continue
    return float(default)


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


def _build_lookups(catalogo: dict[str, Any]) -> tuple[dict[str, dict], dict[str, dict], dict[str, float]]:
    cpus = {c["codigo"]: c for c in catalogo.get("cpus", [])}
    insumos = {i["codigo"]: i for i in catalogo.get("insumos", [])}

    # Resolve produtividades do arquivo lateral se disponível no catálogo carregado
    prods_raw = catalogo.get("produtividades", []) or catalogo.get("producoes", [])
    produtividades: dict[str, float] = {}
    for p in prods_raw:
        pid = p.get("id")
        if not pid:
            continue
        valor = p.get("valor_horario")
        if valor is None:
            # Fase 2: campo legado em produtividade ainda aceito com depreciação.
            valor = p.get("producao_horaria")
        if isinstance(valor, (int, float)):
            produtividades[pid] = float(valor)

    return cpus, insumos, produtividades


def _resolve_bdi(
    inputs: dict[str, Any],
    validacoes: list[ValidacaoItem],
) -> dict[str, float]:
    """Resolve BDI efetivo para as 4 categorias do modelo flat (ADR-023 §D3).

    Ordem de precedência (unificada para auditabilidade):
      1. inputs["bdi_aplicado"]  — override manual (com aviso)
      2. inputs["tabela_bdi"]    — TabelaBdi serializada (preferido)
      3. DEFAULT_BDI_TABELA      — padrão da empresa (recomendado)
      4. inputs["perfil_bdi"]    — PerfilBdiProjeto (override local)

    Retorna dict com chaves: material, diesel, mao_obra, equipamentos.
    """
    # 0. ADR-055: TaxSimulationScenario CBS/IBS (novo path — mais alta prioridade que TabelaBdi)
    tax_scenario_raw = inputs.get("tax_scenario")
    if tax_scenario_raw and isinstance(tax_scenario_raw, dict):
        try:
            scenario = TaxSimulationScenario.from_dict(tax_scenario_raw)
            tabela_cbs_ibs = resolver_bdi_cbs_ibs(DEFAULT_BDI_TABELA, scenario)
            bdi_mo = tabela_cbs_ibs.mao_obra.bdi_total
            bdi_mat = tabela_cbs_ibs.material.bdi_total
            bdi_dies = tabela_cbs_ibs.diesel.bdi_total
            bdi_equip = round(0.70 * bdi_mo + 0.30 * bdi_dies, 6)
            t_ef = scenario.tributos_efetivos_por_categoria()
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-BDI-REGIME",
                    status="OK",
                    mensagem=(
                        f"BDI via TaxSimulationScenario ADR-055 "
                        f"(regime={scenario.regime_version.value}, "
                        f"CBS_IBS_bruto={scenario.cbs_ibs_combined_rate * 100:.1f}%, "
                        f"T_ef_MO={t_ef['mao_obra'] * 100:.2f}%, "
                        f"T_ef_MAT={t_ef['material'] * 100:.2f}%). "
                        + ("⚠️ split_payment ativo." if scenario.split_payment else "")
                    ),
                )
            )
            return {
                "material": round(bdi_mat, 6),
                "diesel": round(bdi_dies, 6),
                "mao_obra": round(bdi_mo, 6),
                "equipamentos": round(bdi_equip, 6),
            }
        except Exception as exc:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-BDI-REGIME",
                    status="AVISO",
                    mensagem=f"Falha ao aplicar tax_scenario CBS/IBS: {exc}. Usando path legado.",
                )
            )

    # 1. Override manual
    if inputs.get("bdi_aplicado"):
        manual = dict(inputs["bdi_aplicado"])
        mo = _get_bdi_value(manual, "mao_obra", "mo")
        mat = _get_bdi_value(manual, "material", "mat")
        diesel = _get_bdi_value(manual, "diesel", "combustivel", "comb")
        serv = _get_bdi_value(manual, "servicos", "serv", default=mo)
        eq = _get_bdi_value(manual, "equipamentos", "eq", default=serv)
        bdi = {
            "material": mat,
            "diesel": diesel,
            "mao_obra": mo,
            "equipamentos": eq,
        }
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-BDI-FONTE",
                status="AVISO",
                mensagem=(
                    "BDI aplicado via override manual (inputs.bdi_aplicado). "
                    f"MO={mo * 100:.2f}% | EQ={eq * 100:.2f}% | MAT={mat * 100:.2f}% | "
                    f"COMB={diesel * 100:.2f}% | SERV={serv * 100:.2f}%. "
                    "Preferir TabelaBdi (ADR-023)."
                ),
            )
        )
        return bdi

    # 2. TabelaBdi explícita nos inputs
    tabela: TabelaBdi | None = None
    tabela_raw = inputs.get("tabela_bdi")
    if tabela_raw is not None:
        try:
            tabela = TabelaBdi.model_validate(tabela_raw) if isinstance(tabela_raw, dict) else tabela_raw
            fonte = "inputs.tabela_bdi"
        except Exception as e:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-BDI-PARSE",
                    status="AVISO",
                    mensagem=f"Falha ao parsear inputs.tabela_bdi: {e}. Usando DEFAULT_BDI_TABELA.",
                )
            )
            tabela = None

    # 3. DEFAULT_BDI_TABELA (empresa)
    if tabela is None:
        tabela = DEFAULT_BDI_TABELA
        fonte = f"DEFAULT_BDI_TABELA (vigência {DEFAULT_BDI_TABELA.data_vigencia})"

    # Aplica perfil_bdi se disponível nos inputs (PerfilBdiProjeto serializado)
    perfil_bdi_raw = inputs.get("bdi_perfil") or inputs.get("perfil_bdi")
    if perfil_bdi_raw is not None:
        try:
            from concilium.domain.models.bdi import PerfilBdiProjeto

            perfil_bdi = (
                PerfilBdiProjeto.model_validate(perfil_bdi_raw) if isinstance(perfil_bdi_raw, dict) else perfil_bdi_raw
            )
            tabela = resolver_componentes_bdi(tabela, perfil_bdi)
            fonte += " + PerfilBdiProjeto"
        except Exception as e:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-BDI-PERFIL",
                    status="AVISO",
                    mensagem=f"Falha ao aplicar PerfilBdiProjeto: {e}. Usando TabelaBdi sem override de perfil.",
                )
            )

    # Extrai valores flat para o modelo Planejamento.bdi (4 categorias).
    # ADR-023 §D3: EQUIP BDI = 70% MAO_OBRA + 30% DIESEL (composição mista de equipamentos).
    bdi_mo = tabela.mao_obra.bdi_total
    bdi_mat = tabela.material.bdi_total
    bdi_dies = tabela.diesel.bdi_total
    bdi_serv = tabela.servicos.bdi_total
    bdi_equip = round(0.70 * bdi_mo + 0.30 * bdi_dies, 6)

    validacoes.append(
        ValidacaoItem(
            codigo="VAL-BDI-FONTE",
            status="OK",
            mensagem=(
                f"TabelaBdi aplicada ({fonte}): "
                f"MO={bdi_mo * 100:.2f}% | MAT={bdi_mat * 100:.2f}% | "
                f"DIESEL={bdi_dies * 100:.2f}% | SERV={bdi_serv * 100:.2f}% | EQUIP={bdi_equip * 100:.2f}%"
            ),
        )
    )
    return {
        "material": round(bdi_mat, 6),
        "diesel": round(bdi_dies, 6),
        "mao_obra": round(bdi_mo, 6),
        "equipamentos": round(bdi_equip, 6),
    }


def _validar_bdi_dentro_da_faixa(bdi: dict[str, float]) -> list[str]:
    """Valida política mínima de BDI (faixa percentual válida)."""
    violacoes: list[str] = []
    for cat, valor in bdi.items():
        if valor < 0 or valor > 1:
            violacoes.append(f"{cat}={valor * 100:.1f}% fora da faixa [0.0%, 100.0%]")
    return violacoes


def _resolve_insumo_preco(
    repo: RepositorioInsumo,
    insumo_id: str,
    jurisdicao_id: str | None,
    overrides: dict | None,
    data_base: Any,
    fallback: float = 0.0,
) -> float:
    preco, _ = repo.resolver_preco(
        insumo_id, jurisdicao_id=jurisdicao_id, overrides=overrides, data_referencia=data_base
    )
    return float(preco or fallback)


def _extract_overrides(inputs: dict) -> dict | None:
    val = inputs.get("insumos_override")
    if isinstance(val, dict):
        return val
    return None


def _build_equipe_lookup(canonical_in: CanonicalModel) -> dict:
    return {eq.item_id: eq for eq in (canonical_in.equipes_diretas or [])}


def _build_planejamento_entry(
    item: Any,
    preco_cat: dict,
    preco_cat_com_bdi: dict,
    bdi_aplicado: dict,
) -> Planejamento:
    q = item.quantitativo
    total_sem_bdi = sum(preco_cat.values())
    total_com_bdi = sum(preco_cat_com_bdi.values())
    return Planejamento(
        item_id=item.item_id,
        cpu_id=item.cpu_id,
        quantitativo=q,
        preco_unitario=PrecoUnitarioCategoria(
            material=round(preco_cat["material"], 4),
            diesel=round(preco_cat["diesel"], 4),
            mao_obra=round(preco_cat["mao_obra"], 4),
            equipamentos=round(preco_cat["equipamentos"], 4),
            total=round(total_sem_bdi, 4),
        ),
        bdi=BdiCategorias(**bdi_aplicado),
        preco_unitario_com_bdi=PrecoUnitarioCategoria(
            material=round(preco_cat_com_bdi["material"], 4),
            diesel=round(preco_cat_com_bdi["diesel"], 4),
            mao_obra=round(preco_cat_com_bdi["mao_obra"], 4),
            equipamentos=round(preco_cat_com_bdi["equipamentos"], 4),
            total=round(total_com_bdi, 4),
        ),
        subtotal=SubtotalSemBdiComBdi(
            sem_bdi=SubtotalCategorias(
                material=round(preco_cat["material"] * q, 2),
                diesel=round(preco_cat["diesel"] * q, 2),
                mao_obra=round(preco_cat["mao_obra"] * q, 2),
                equipamentos=round(preco_cat["equipamentos"] * q, 2),
                total=round(total_sem_bdi * q, 2),
            ),
            com_bdi=SubtotalCategorias(
                material=round(preco_cat_com_bdi["material"] * q, 2),
                diesel=round(preco_cat_com_bdi["diesel"] * q, 2),
                mao_obra=round(preco_cat_com_bdi["mao_obra"] * q, 2),
                equipamentos=round(preco_cat_com_bdi["equipamentos"] * q, 2),
                total=round(total_com_bdi * q, 2),
            ),
        ),
    )


def _try_early_override(
    item: Any,
    planejamento_item_overrides: Any,
    bdi_aplicado: dict,
    validacoes: list,
) -> Planejamento | None:
    _item_ovr_early = (
        planejamento_item_overrides.get(item.item_id, {}) if isinstance(planejamento_item_overrides, dict) else {}
    )
    _pu_early = _item_ovr_early.get("preco_unitario") if isinstance(_item_ovr_early, dict) else None
    if not isinstance(_pu_early, dict):
        return None
    if not any(float(v or 0) != 0 for v in _pu_early.values()):
        return None
    _preco_early = {
        "material": float(_pu_early.get("material", 0.0)),
        "diesel": float(_pu_early.get("diesel", 0.0)),
        "mao_obra": float(_pu_early.get("mao_obra", 0.0)),
        "equipamentos": float(_pu_early.get("equipamentos", 0.0)),
    }
    _com_bdi_early = {cat: _preco_early[cat] * (1 + bdi_aplicado[cat]) for cat in _preco_early}
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-PLAN-OVR-ITEM",
            status="INFO",
            mensagem=f"Item '{item.item_id}': preço unitário sem BDI calibrado por referência.",
        )
    )
    return _build_planejamento_entry(item, _preco_early, _com_bdi_early, bdi_aplicado)


def _apply_equip_decomp(
    ci: Any, insumo: dict, contribuicao: float, preco_cat: dict, equip_sem_decomp_item: set
) -> None:
    decomp_raw = (insumo.get("atributos_especificos") or {}).get("decomposicao_equip")
    if decomp_raw and decomp_raw.get("custo_hora_total", 0.0) > 0:
        total_h = decomp_raw["custo_hora_total"]
        frac_mo = (decomp_raw.get("custo_mao_obra_h", 0.0) + decomp_raw.get("custo_capital_h", 0.0)) / total_h
        frac_die = decomp_raw.get("custo_diesel_h", 0.0) / total_h
        frac_mat = decomp_raw.get("custo_material_h", 0.0) / total_h
        preco_cat["mao_obra"] += contribuicao * frac_mo
        preco_cat["diesel"] += contribuicao * frac_die
        preco_cat["material"] += contribuicao * frac_mat
        preco_cat["equipamentos"] += contribuicao * max(0.0, 1.0 - frac_mo - frac_die - frac_mat)
    else:
        equip_sem_decomp_item.add(ci.insumo_id)
        preco_cat["equipamentos"] += contribuicao


def _compute_preco_cat_from_cpu(
    cpu_model: Any,
    insumo_lookup: dict,
    repo: RepositorioInsumo,
    jurisdicao_id: str | None,
    overrides: dict | None,
    data_base: Any,
    cpu_codigo: str,
    erros_insumo: set,
    validacoes: list,
) -> tuple[dict, set]:
    from concilium.domain.services.conversor_unidades import ConversorUnidades

    preco_cat = {"material": 0.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
    equip_sem_decomp_item: set[str] = set()
    for ci in cpu_model.composicao_completa:
        insumo = insumo_lookup.get(ci.insumo_id)
        if insumo is None:
            erros_insumo.add(ci.insumo_id)
            continue
        categoria_raw = (ci.categoria_custo or "").strip().lower()
        categoria = _CATEGORIA_MAP.get(categoria_raw)
        if categoria is None:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-PLAN-CAT",
                    status="AVISO",
                    mensagem=f"CPU '{cpu_codigo}' usa categoria_custo desconhecida: '{ci.categoria_custo}'. Item ignorado no planejamento.",
                )
            )
            continue
        unidade_insumo = insumo.get("unidade")
        unidade_cpu = ci.unidade or unidade_insumo
        try:
            coeficiente_ajustado = ConversorUnidades.resolver_coeficiente_cpu(
                ci.coeficiente, unidade_cpu, unidade_insumo
            )
            preco_insumo = _resolve_insumo_preco(
                repo, ci.insumo_id, jurisdicao_id, overrides, data_base, float(insumo.get("preco_unitario", 0.0) or 0.0)
            )
            contribuicao = coeficiente_ajustado * preco_insumo
        except Exception as e:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-PLAN-UNIT", status="ERRO", mensagem=f"Erro de conversão na CPU '{cpu_codigo}': {e}"
                )
            )
            preco_insumo = _resolve_insumo_preco(
                repo, ci.insumo_id, jurisdicao_id, overrides, data_base, float(insumo.get("preco_unitario", 0.0) or 0.0)
            )
            contribuicao = ci.coeficiente * preco_insumo
        if categoria == "equipamentos":
            _apply_equip_decomp(ci, insumo, contribuicao, preco_cat, equip_sem_decomp_item)
            continue
        preco_cat[categoria] += contribuicao
    return preco_cat, equip_sem_decomp_item


def _apply_adr038_compensation(eq_real: Any, item: Any, preco_cat: dict) -> None:
    q = item.quantitativo
    p_meses = eq_real.permanencia_efetiva_meses or eq_real.permanencia_meses
    p_mo = (eq_real.custo_mao_obra_mensal * p_meses) / q
    p_eq = (eq_real.custo_equipamentos_mensal * p_meses) / q
    p_die = (eq_real.custo_combustivel_total_mensal * p_meses) / q
    p_mat_equipe = (eq_real.custo_material_mensal * p_meses) / q
    preco_cat["mao_obra"] = p_mo
    preco_cat["equipamentos"] = p_eq
    preco_cat["diesel"] = p_die
    preco_cat["material"] = preco_cat["material"] + p_mat_equipe


def _apply_sem_bdi_override(item_id: str, item_override: Any, preco_cat: dict, validacoes: list) -> None:
    override_sem = item_override.get("preco_unitario") if isinstance(item_override, dict) else None
    if not isinstance(override_sem, dict):
        return
    for cat in ("material", "diesel", "mao_obra", "equipamentos"):
        if cat in override_sem:
            try:
                preco_cat[cat] = float(override_sem[cat])
            except Exception:
                pass
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-PLAN-OVR-ITEM",
            status="INFO",
            mensagem=f"Item '{item_id}': preço unitário sem BDI calibrado por referência.",
        )
    )


def _apply_com_bdi_override(
    item_id: str, item_override: Any, preco_cat: dict, bdi_aplicado: dict, validacoes: list
) -> dict:
    override_com = item_override.get("preco_unitario_com_bdi") if isinstance(item_override, dict) else None
    if isinstance(override_com, dict):
        preco_cat_com_bdi = {
            "material": float(override_com.get("material", preco_cat["material"] * (1 + bdi_aplicado["material"]))),
            "diesel": float(override_com.get("diesel", preco_cat["diesel"] * (1 + bdi_aplicado["diesel"]))),
            "mao_obra": float(override_com.get("mao_obra", preco_cat["mao_obra"] * (1 + bdi_aplicado["mao_obra"]))),
            "equipamentos": float(
                override_com.get("equipamentos", preco_cat["equipamentos"] * (1 + bdi_aplicado["equipamentos"]))
            ),
        }
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PLAN-OVR-ITEM-BDI",
                status="INFO",
                mensagem=f"Item '{item_id}': preço unitário com BDI calibrado por referência.",
            )
        )
    else:
        preco_cat_com_bdi = {cat: preco_cat[cat] * (1 + bdi_aplicado[cat]) for cat in preco_cat}
    return preco_cat_com_bdi


def _validate_coverage(canonical_in: CanonicalModel, plan_out: list, validacoes: list) -> None:
    if not canonical_in.equipes_diretas:
        return
    from concilium.domain.services.validador_cobertura_item import validar_cobertura_item

    equipe_lookup_cob = {eq.item_id: eq for eq in canonical_in.equipes_diretas}
    planejamento_lookup_cob = {p.item_id: p for p in plan_out}
    for item in canonical_in.eap:
        equipe = equipe_lookup_cob.get(item.item_id)
        planej = planejamento_lookup_cob.get(item.item_id)
        if equipe and planej:
            validacoes.extend(validar_cobertura_item(item, equipe, planej))


def _process_eap_item(
    item: Any,
    cpu_lookup: dict,
    insumo_lookup: dict,
    prod_lookup: dict,
    equipe_lookup: dict,
    planejamento_item_overrides: Any,
    bdi_aplicado: dict,
    repo: RepositorioInsumo,
    jurisdicao_id: str | None,
    overrides: dict | None,
    data_base: Any,
    plan_out: list,
    erros_eap: list,
    erros_insumo: set,
    equip_sem_decomp: set,
    validacoes: list,
) -> None:
    cpu = cpu_lookup.get(item.cpu_id)
    if cpu is None:
        erros_eap.append(item.cpu_id)
        return
    prod_id_ref = cpu.get("producao_id_ref")
    if not prod_id_ref:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PLAN-PROD-REF-01", status="ERRO", mensagem=f"CPU '{cpu.get('codigo')}' sem producao_id_ref."
            )
        )
        return
    if prod_lookup.get(prod_id_ref) is None:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PLAN-PROD-REF-02",
                status="ERRO",
                mensagem=f"CPU '{cpu.get('codigo')}' referencia producao_id_ref inexistente: {prod_id_ref}.",
            )
        )
        return
    early = _try_early_override(item, planejamento_item_overrides, bdi_aplicado, validacoes)
    if early is not None:
        plan_out.append(early)
        return
    from concilium.domain.models.catalogo import CPU

    cpu_model = CPU.model_validate(cpu)
    preco_cat, equip_sem_decomp_item = _compute_preco_cat_from_cpu(
        cpu_model, insumo_lookup, repo, jurisdicao_id, overrides, data_base, cpu.get("codigo"), erros_insumo, validacoes
    )
    eq_real = equipe_lookup.get(item.item_id)
    if eq_real and item.quantitativo > 0:
        _apply_adr038_compensation(eq_real, item, preco_cat)
        equip_sem_decomp_item.clear()
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PLAN-PARAMETRICO",
                status="INFO",
                mensagem=f"Item '{item.item_id}': CPU recalculada com base operacional (ADR-038). Scale Factor: {eq_real.num_equipes_base} frentes.",
            )
        )  # noqa: E501
    equip_sem_decomp.update(equip_sem_decomp_item)
    item_override = (
        planejamento_item_overrides.get(item.item_id, {}) if isinstance(planejamento_item_overrides, dict) else {}
    )
    _apply_sem_bdi_override(item.item_id, item_override, preco_cat, validacoes)
    preco_cat_com_bdi = _apply_com_bdi_override(item.item_id, item_override, preco_cat, bdi_aplicado, validacoes)
    plan_out.append(_build_planejamento_entry(item, preco_cat, preco_cat_com_bdi, bdi_aplicado))


def run_precificacao_unitaria(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    catalogo: dict[str, Any],
    perfil: dict[str, Any],
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

    bdi_aplicado = _resolve_bdi(inputs, validacoes)
    planejamento_item_overrides = inputs.get("planejamento_item_overrides", {})

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
                    f"Insumos EQUIPAMENTO sem decomposicao_equip: {', '.join(sorted(equip_sem_decomp))}. Usando ponderação 70%/30% (MAO_OBRA+DIESEL). Enriqueça o catálogo com DecomposicaoEquipamento para BDI auditável (ADR-023 §D3)."
                ),
            )
        )

    _validate_coverage(canonical_in, plan_out, validacoes)
    novo = canonical_in.model_copy(update={"planejamento": plan_out})
    return SkillResult(novo, validacoes)
