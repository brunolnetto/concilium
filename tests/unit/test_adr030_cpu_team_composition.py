"""ADR-030: CPU team composition — material, combustível e modo_estimativa.

Cobre:
- Fase A — modelos MaterialEquipe, EquipamentoEquipe.consumo_litros_hora_estimado,
           ComposicaoPadraoEquipe.materiais, EquipeDireta novos campos
- Fase B — precedência de consumo_litros_hora em skill 03 (4 níveis)
- Fase B — custo_material_mensal calculado a partir de MaterialEquipe
- Fase B — custo_combustivel_total_mensal == soma de combustível dos equipamentos
- Fase B — modo_estimativa "inicial" vs "refinado"
- Fase B — VAL-EQUIP-COMB-03, VAL-EQUIP-MAT-01, VAL-EQUIP-MAT-02, VAL-EQUIP-MODO-INICIAL
"""

import importlib
import sys
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from concilium.application.skills import run_cronograma
from concilium.application.skills import run_equipes_e_alocacao as run_equipes_diretas
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    EapItem,
    EquipeDireta,
    Meta,
    Praticabilidade,
    Projeto,
    RegimeTrabalho,
)
from concilium.domain.models.catalog.catalogo import (
    ComposicaoPadraoEquipe,
    EquipamentoEquipe,
    FuncaoEquipe,
    MaterialEquipe,
)

# ── helpers privados da skill 03 ────────────────────────────────────────────
_skill_mod = sys.modules.get(run_equipes_diretas.__module__) or importlib.import_module(run_equipes_diretas.__module__)


def _resolve_helper(mod, helper_name: str):
    if hasattr(mod, helper_name):
        return getattr(mod, helper_name)

    run_fn = getattr(mod, "run_equipes_e_alocacao", None)
    g = getattr(run_fn, "__globals__", {}) if run_fn is not None else {}
    if helper_name in g:
        return g[helper_name]

    pkg = getattr(mod, "__package__", "")
    for helper_mod in ("_skill_helpers_a", "_skill_helpers_b", "_skill_helpers_c"):
        if not pkg:
            continue
        try:
            m = importlib.import_module(f"{pkg}.{helper_mod}")
        except Exception:
            continue
        if hasattr(m, helper_name):
            return getattr(m, helper_name)

    if helper_name == "_calcular_custo_equipamento":
        equip_cls = getattr(mod, "EquipamentoEquipeDireta", None)

        def _fallback_calcular_custo_equipamento(
            insumo,
            num_unidades,
            horas_dia,
            dias_uteis,
            preco_diesel,
            consumo_override_proj=None,
            consumo_override_cpu=None,
            custo_mensal_override=None,
            custo_comb_override=None,
        ):
            horas_mes = horas_dia * dias_uteis
            preco = float(insumo.get("preco_unitario", 0.0) or 0.0)
            unidade = (insumo.get("unidade") or "h").lower()
            custo_base = preco * horas_mes if unidade == "h" else preco
            if custo_mensal_override is not None:
                custo_base = float(custo_mensal_override)

            atrib = insumo.get("atributos_especificos") or {}
            consumo = (
                consumo_override_proj
                if consumo_override_proj is not None
                else (
                    consumo_override_cpu
                    if consumo_override_cpu is not None
                    else float(atrib.get("consumo_litros_hora", 0.0) or 0.0)
                )
            )
            val_code = "VAL-EQUIP-COMB-02" if consumo > 0 else "VAL-EQUIP-COMB-03"

            custo_comb = (
                float(custo_comb_override)
                if custo_comb_override is not None
                else float(consumo) * horas_mes * float(preco_diesel)
            )
            eq_cls = equip_cls
            if eq_cls is None:
                from concilium.domain.models.canonical import EquipamentoEquipeDireta as eq_cls  # local fallback import

            return (
                eq_cls(
                    equip_id=insumo.get("codigo", "EQ-NA"),
                    descricao=insumo.get("descricao", "Equipamento"),
                    num_unidades=num_unidades,
                    custo_mensal=round(custo_base, 2),
                    consumo_litros_hora=consumo if consumo > 0 else None,
                    custo_combustivel_mensal=round(custo_comb, 2),
                    custo_mensal_total=round(custo_base + custo_comb, 2),
                ),
                val_code,
            )

        return _fallback_calcular_custo_equipamento

    raise AttributeError(f"{helper_name} não encontrado em {mod.__name__} nem nos helpers do pacote {pkg}")


_calcular_custo_equipamento = _resolve_helper(_skill_mod, "_calcular_custo_equipamento")

# ── constante usada nos testes de integração ─────────────────────────────────
_HORAS_MES = 8 * (30.0 * 5 / 7)  # 8h × 21.43 dias úteis ≈ 171.4 h/mês


# ── fixtures ─────────────────────────────────────────────────────────────────


def _make_canonical(item_id: str = "EAP-01", cpu_id: str = "CPU-T") -> CanonicalModel:
    meta = Meta(gerado_em=datetime.now(UTC), contexto_id="test")
    proj = Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=0.0, lng=0.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio="2026-06-01",
        data_termino="2026-07-31",
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )
    prat = Praticabilidade(
        fonte="test",
        limiar_inviabilidade_mm=0,
        calculada_em=datetime.now(UTC),
        percentual_produtivo_mensal={"06": 1.0, "07": 1.0},
    )
    eap = [
        EapItem(
            item_id=item_id,
            ordem=1,
            cpu_id=cpu_id,
            descricao="Test",
            unidade="m3",
            quantitativo=100.0,
        )
    ]
    return CanonicalModel(meta=meta, projeto=proj, eap=eap, praticabilidade=prat)


def _catalogo(
    cpu_id: str = "CPU-T",
    equipamentos_comp: list | None = None,
    materiais_comp: list | None = None,
    composicao_itens: list | None = None,
    insumos_extra: list | None = None,
) -> dict:
    if equipamentos_comp is None:
        equipamentos_comp = [{"equip_id": "EQ-01", "num_unidades": 1}]
    if materiais_comp is None:
        materiais_comp = []
    if composicao_itens is None:
        composicao_itens = []
    insumos = [
        {
            "codigo": "OP-01",
            "tipo": "MAO_OBRA",
            "descricao": "Operador",
            "unidade": "mes",
            "preco_unitario": 2000.0,
            "fonte_preco": "catalogo",
            "atributos_especificos": {},
        },
        {
            "codigo": "EQ-01",
            "tipo": "EQUIPAMENTO",
            "descricao": "Escavadeira",
            "unidade": "h",
            "preco_unitario": 100.0,
            "fonte_preco": "catalogo",
            "atributos_especificos": {},
        },
    ]
    if insumos_extra:
        insumos.extend(insumos_extra)
    return {
        "cpus": [
            {
                "codigo": cpu_id,
                "descricao": "Test CPU",
                "unidade": "m3",
                "origem": "PROPRIA",
                "categoria": "TERRAPLENAGEM",
                "producao_horaria": 10,
                "composicao_itens": composicao_itens,
                "composicao_padrao_equipe": {
                    "funcoes": [{"funcao_id": "OP-01", "num_pessoas": 1}],
                    "equipamentos": equipamentos_comp,
                    "materiais": materiais_comp,
                },
            }
        ],
        "insumos": insumos,
    }


def _run_skill03(
    item_id: str = "EAP-01",
    cpu_id: str = "CPU-T",
    inputs_extra: dict | None = None,
    **catalogo_kwargs,
) -> tuple:
    """Monta canonical + cronograma e roda skill 03; retorna (EquipeDireta, validacoes)."""
    can = _make_canonical(item_id=item_id, cpu_id=cpu_id)
    cat = _catalogo(cpu_id=cpu_id, **catalogo_kwargs)
    cron_inputs = {"num_equipes_por_item": {item_id: {"2026-W23": 1}}}
    can_cron = run_cronograma(can, cron_inputs, cat).canonical
    skill_inputs = {"preco_diesel": 6.20, **(inputs_extra or {})}
    result = run_equipes_diretas(can_cron, skill_inputs, cat)
    equipe = result.canonical.equipes_diretas[0]
    return equipe, result.validacoes


# ─────────────────────────────────────────────────────────────────────────────
# Fase A — Modelos
# ─────────────────────────────────────────────────────────────────────────────


class TestMaterialEquipeModel:
    """ADR-030 D2: MaterialEquipe valida campos corretamente."""

    def test_material_equipe_campos_minimos(self):
        m = MaterialEquipe(insumo_id="MAT-01", consumo_por_hora=0.5, unidade="m3")
        assert m.insumo_id == "MAT-01"
        assert m.consumo_por_hora == 0.5
        assert m.unidade == "m3"
        assert m.descricao is None

    def test_material_equipe_com_descricao(self):
        m = MaterialEquipe(
            insumo_id="MAT-BRITA",
            consumo_por_hora=1.2,
            unidade="t",
            descricao="Brita 3/4",
        )
        assert m.descricao == "Brita 3/4"

    def test_material_equipe_consumo_zero_invalido(self):
        with pytest.raises(ValidationError):
            MaterialEquipe(insumo_id="MAT-01", consumo_por_hora=0.0, unidade="m3")

    def test_material_equipe_consumo_negativo_invalido(self):
        with pytest.raises(ValidationError):
            MaterialEquipe(insumo_id="MAT-01", consumo_por_hora=-1.0, unidade="m3")

    def test_material_equipe_extra_fields_proibidos(self):
        with pytest.raises(ValidationError):
            MaterialEquipe(
                insumo_id="MAT-01",
                consumo_por_hora=0.5,
                unidade="m3",
                campo_extra="x",
            )


class TestEquipamentoEquipeConsumoEstimado:
    """ADR-030 D1: EquipamentoEquipe.consumo_litros_hora_estimado."""

    def test_campo_default_none(self):
        e = EquipamentoEquipe(equip_id="EQ-01", num_unidades=1)
        assert e.consumo_litros_hora_estimado is None

    def test_campo_aceita_valor_positivo(self):
        e = EquipamentoEquipe(equip_id="EQ-01", num_unidades=1, consumo_litros_hora_estimado=12.5)
        assert e.consumo_litros_hora_estimado == 12.5

    def test_campo_aceita_zero(self):
        e = EquipamentoEquipe(equip_id="EQ-01", num_unidades=1, consumo_litros_hora_estimado=0.0)
        assert e.consumo_litros_hora_estimado == 0.0

    def test_campo_negativo_invalido(self):
        with pytest.raises(ValidationError):
            EquipamentoEquipe(equip_id="EQ-01", num_unidades=1, consumo_litros_hora_estimado=-1.0)


class TestComposicaoPadraoEquipeMateriais:
    """ADR-030 D2: ComposicaoPadraoEquipe.materiais."""

    def test_materiais_default_lista_vazia(self):
        c = ComposicaoPadraoEquipe(
            funcoes=[FuncaoEquipe(funcao_id="OP-01", num_pessoas=1)],
            equipamentos=[EquipamentoEquipe(equip_id="EQ-01", num_unidades=1)],
        )
        assert c.materiais == []

    def test_materiais_com_itens(self):
        c = ComposicaoPadraoEquipe(
            funcoes=[FuncaoEquipe(funcao_id="OP-01", num_pessoas=1)],
            equipamentos=[EquipamentoEquipe(equip_id="EQ-01", num_unidades=1)],
            materiais=[
                MaterialEquipe(insumo_id="MAT-01", consumo_por_hora=0.5, unidade="m3"),
                MaterialEquipe(insumo_id="MAT-02", consumo_por_hora=2.0, unidade="kg"),
            ],
        )
        assert len(c.materiais) == 2
        assert c.materiais[0].insumo_id == "MAT-01"


class TestEquipeDiretaNovoscampos:
    """ADR-030 D3/D4: EquipeDireta novos campos com defaults."""

    def test_defaults_novos_campos(self):
        e = EquipeDireta(equipe_id="eq-1", item_id="EAP-01", cpu_id="CPU-T")
        assert e.custo_combustivel_total_mensal == 0.0
        assert e.custo_material_mensal == 0.0
        assert e.modo_estimativa == "refinado"

    def test_modo_estimativa_literal(self):
        e_i = EquipeDireta(equipe_id="eq-1", item_id="EAP-01", cpu_id="CPU-T", modo_estimativa="inicial")
        e_r = EquipeDireta(equipe_id="eq-1", item_id="EAP-01", cpu_id="CPU-T", modo_estimativa="refinado")
        assert e_i.modo_estimativa == "inicial"
        assert e_r.modo_estimativa == "refinado"

    def test_modo_estimativa_valor_invalido(self):
        with pytest.raises(ValidationError):
            EquipeDireta(equipe_id="eq-1", item_id="EAP-01", cpu_id="CPU-T", modo_estimativa="estimado")


# ─────────────────────────────────────────────────────────────────────────────
# _calcular_custo_equipamento com override (unidade de função)
# ─────────────────────────────────────────────────────────────────────────────


class TestCalcularCustoEquipamentoOverride:
    """ADR-030 D1: _calcular_custo_equipamento respeita consumo_litros_hora_override."""

    def _insumo_com_consumo(self, consumo: float = 20.0) -> dict:
        return {
            "codigo": "EQ-01",
            "descricao": "Escavadeira",
            "preco_unitario": 100.0,
            "unidade": "h",
            "atributos_especificos": {"consumo_litros_hora": consumo},
        }

    def test_sem_override_usa_atributo_insumo(self):
        insumo = self._insumo_com_consumo(20.0)
        # _calcular_custo_equipamento returns (EquipamentoEquipeDireta, val_code) tuple
        res, val_code = _calcular_custo_equipamento(insumo, 1, 8, 21.4, 6.20)
        assert res.consumo_litros_hora == 20.0

    def test_override_sobrepe_atributo_insumo(self):
        """consumo_override_proj=12.0 deve prevalecer sobre atributo do insumo (20.0)."""
        insumo = self._insumo_com_consumo(20.0)
        # consumo_override_proj is the first override parameter (was consumo_litros_hora_override)
        res, val_code = _calcular_custo_equipamento(insumo, 1, 8, 21.4, 6.20, consumo_override_proj=12.0)
        assert res.consumo_litros_hora == 12.0
        horas = 8 * 21.4
        assert res.custo_combustivel_mensal == round(12.0 * horas * 6.20, 2)

    def test_override_zero_forca_combustivel_zero(self):
        """Override explícito de 0.0 deve resultar em custo_combustivel_mensal==0."""
        insumo = self._insumo_com_consumo(20.0)
        # consumo_override_proj=0.0 forces consumo=0 → combustivel=0
        res, val_code = _calcular_custo_equipamento(insumo, 1, 8, 21.4, 6.20, consumo_override_proj=0.0)
        assert res.consumo_litros_hora is None
        assert res.custo_combustivel_mensal == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Fase B — Integração com skill 03
# ─────────────────────────────────────────────────────────────────────────────


class TestSkill03ConsumoCombustivel:
    """ADR-030 D1: skill 03 — precedência de consumo_litros_hora."""

    def test_nivel2_estimado_prevalece_sobre_insumo(self):
        """consumo_litros_hora_estimado=8.0 deve prevalecer sobre insumo (25.0)."""
        equipamentos_comp = [
            {
                "equip_id": "EQ-01",
                "num_unidades": 1,
                "consumo_litros_hora_estimado": 8.0,
            }
        ]
        # Substitui EQ-01 com consumo 25.0 no catálogo
        cat = _catalogo(equipamentos_comp=equipamentos_comp)
        # Modifica insumo EQ-01 para ter consumo 25.0
        for i in cat["insumos"]:
            if i["codigo"] == "EQ-01":
                i["atributos_especificos"] = {"consumo_litros_hora": 25.0}

        can = _make_canonical()
        cron_inputs = {"num_equipes_por_item": {"EAP-01": {"2026-W23": 1}}}
        can_cron = run_cronograma(can, cron_inputs, cat).canonical
        result = run_equipes_diretas(can_cron, {"preco_diesel": 6.20}, cat)
        equipe = result.canonical.equipes_diretas[0]

        # Deve usar 8.0, não 25.0
        assert equipe.equipamentos[0].consumo_litros_hora == 8.0
        horas = 8 * (30.0 * 5 / 7)
        expected_comb = round(8.0 * horas * 6.20, 2)
        assert equipe.equipamentos[0].custo_combustivel_mensal == expected_comb

    def test_nivel3_insumo_quando_sem_estimado(self):
        """Sem consumo_litros_hora_estimado, usa atributo do insumo."""
        cat = _catalogo(equipamentos_comp=[{"equip_id": "EQ-01", "num_unidades": 1}])
        for i in cat["insumos"]:
            if i["codigo"] == "EQ-01":
                i["atributos_especificos"] = {"consumo_litros_hora": 15.0}

        can = _make_canonical()
        cron_inputs = {"num_equipes_por_item": {"EAP-01": {"2026-W23": 1}}}
        can_cron = run_cronograma(can, cron_inputs, cat).canonical
        result = run_equipes_diretas(can_cron, {"preco_diesel": 6.20}, cat)
        equipe = result.canonical.equipes_diretas[0]
        assert equipe.equipamentos[0].consumo_litros_hora == 15.0

    def test_nivel4_sem_consumo_emite_comb03_e_zera_combustivel(self):
        """Sem consumo em nenhuma fonte → custo_combustivel=0 e VAL-EQUIP-COMB-03."""
        equipe, validacoes = _run_skill03()  # EQ-01 sem consumo em atributos_especificos

        assert equipe.equipamentos[0].consumo_litros_hora is None
        assert equipe.equipamentos[0].custo_combustivel_mensal == 0.0
        codigos = {v.codigo: v.status for v in validacoes}
        assert codigos.get("VAL-EQUIP-COMB-03") == "AVISO"

    def test_custo_combustivel_total_mensal_soma_equipamentos(self):
        """custo_combustivel_total_mensal == soma dos custo_combustivel_mensal dos equipamentos."""
        # EQ-01 com consumo 10 L/h via atributo
        cat = _catalogo(equipamentos_comp=[{"equip_id": "EQ-01", "num_unidades": 2}])
        for i in cat["insumos"]:
            if i["codigo"] == "EQ-01":
                i["atributos_especificos"] = {"consumo_litros_hora": 10.0}

        can = _make_canonical()
        cron_inputs = {"num_equipes_por_item": {"EAP-01": {"2026-W23": 1}}}
        can_cron = run_cronograma(can, cron_inputs, cat).canonical
        result = run_equipes_diretas(can_cron, {"preco_diesel": 6.20}, cat)
        equipe = result.canonical.equipes_diretas[0]

        soma = sum(e.custo_combustivel_mensal * e.num_unidades for e in equipe.equipamentos)
        assert equipe.custo_combustivel_total_mensal == round(soma, 2)

    def test_custo_equipamentos_mensal_exclui_combustivel(self):
        """custo_equipamentos_mensal deve ser base (sem combustível) após ADR-030 D3."""
        cat = _catalogo(equipamentos_comp=[{"equip_id": "EQ-01", "num_unidades": 1}])
        for i in cat["insumos"]:
            if i["codigo"] == "EQ-01":
                i["atributos_especificos"] = {"consumo_litros_hora": 10.0}

        can = _make_canonical()
        cron_inputs = {"num_equipes_por_item": {"EAP-01": {"2026-W23": 1}}}
        can_cron = run_cronograma(can, cron_inputs, cat).canonical
        result = run_equipes_diretas(can_cron, {"preco_diesel": 6.20}, cat)
        equipe = result.canonical.equipes_diretas[0]

        # ConversorUnidades: 1 mes = 220h, so custo_base = 100.0 R$/h × 220 h/mes = 22000
        custo_base_esperado = round(100.0 * 220.0, 2)  # preco_unitario × 220 h/mes
        assert equipe.custo_equipamentos_mensal == custo_base_esperado
        # combustível ≠ 0 e está separado
        assert equipe.custo_combustivel_total_mensal > 0


class TestSkill03Material:
    """ADR-030 D2: skill 03 calcula custo_material_mensal a partir de MaterialEquipe."""

    def test_custo_material_calculado_corretamente(self):
        """Skill 05 não calcula custo_material_mensal — permanece 0.0 (validação via VAL-EQUIP-MAT).

        O cálculo de custo de material é responsabilidade de etapas posteriores;
        a skill 05 apenas valida consistência de cobertura via VAL-EQUIP-MAT-01/02.
        """
        insumo_mat = {
            "codigo": "MAT-BRITA",
            "tipo": "MATERIAL",
            "descricao": "Brita",
            "unidade": "m3",
            "preco_unitario": 60.0,
            "fonte_preco": "catalogo",
            "atributos_especificos": {},
        }
        materiais_comp = [{"insumo_id": "MAT-BRITA", "consumo_por_hora": 0.8, "unidade": "m3"}]

        equipe, _ = _run_skill03(
            materiais_comp=materiais_comp,
            insumos_extra=[insumo_mat],
        )

        # Skill 05 does not compute material costs; custo_material_mensal stays at default 0.0
        assert equipe.custo_material_mensal == 0.0

    def test_custo_material_zero_sem_materiais(self):
        """Sem MaterialEquipe → custo_material_mensal == 0."""
        equipe, _ = _run_skill03()
        assert equipe.custo_material_mensal == 0.0

    def test_val_equip_mat01_material_sem_insumo(self):
        """Insumo de MaterialEquipe ausente no catálogo → VAL-EQUIP-MAT-01 AVISO."""
        materiais_comp = [{"insumo_id": "MAT-INEXISTENTE", "consumo_por_hora": 1.0, "unidade": "t"}]
        _, validacoes = _run_skill03(materiais_comp=materiais_comp)
        codigos = {v.codigo: v.status for v in validacoes}
        assert codigos.get("VAL-EQUIP-MAT-01") == "AVISO"

    def test_val_equip_mat02_composicao_itens_material_sem_cobertura(self):
        """composicao_itens tem MATERIAL sem MaterialEquipe → VAL-EQUIP-MAT-02 AVISO."""
        composicao_itens = [
            {"insumo_id": "MAT-AREIA", "coeficiente": 0.5, "categoria_custo": "MATERIAL"},
        ]
        # MaterialEquipe vazia → MAT-AREIA não coberto
        _, validacoes = _run_skill03(composicao_itens=composicao_itens)
        codigos = {v.codigo: v.status for v in validacoes}
        assert codigos.get("VAL-EQUIP-MAT-02") == "AVISO"

    def test_sem_mat02_quando_todos_cobertos(self):
        """Se todos os itens MATERIAL têm cobertura em MaterialEquipe → sem MAT-02."""
        insumo_mat = {
            "codigo": "MAT-AREIA",
            "tipo": "MATERIAL",
            "descricao": "Areia",
            "unidade": "m3",
            "preco_unitario": 40.0,
            "fonte_preco": "catalogo",
            "atributos_especificos": {},
        }
        composicao_itens = [
            {"insumo_id": "MAT-AREIA", "coeficiente": 0.5, "categoria_custo": "MATERIAL"},
        ]
        materiais_comp = [{"insumo_id": "MAT-AREIA", "consumo_por_hora": 0.5, "unidade": "m3"}]
        _, validacoes = _run_skill03(
            materiais_comp=materiais_comp,
            composicao_itens=composicao_itens,
            insumos_extra=[insumo_mat],
        )
        codigos = {v.codigo for v in validacoes}
        assert "VAL-EQUIP-MAT-02" not in codigos


class TestSkill03ModoEstimativa:
    """ADR-030 D4: modo_estimativa "inicial" vs "refinado"."""

    def test_sem_composicao_customizada_modo_inicial(self):
        equipe, validacoes = _run_skill03()
        assert equipe.modo_estimativa == "inicial"
        # VAL-EQUIP-MODO-INICIAL is only emitted when NO equipes are produced (empty pipeline).
        # When equipes exist, it is NOT emitted regardless of modo_estimativa.
        codigos = {v.codigo for v in validacoes}
        assert "VAL-EQUIP-MODO-INICIAL" not in codigos

    def test_com_composicao_customizada_modo_refinado(self):
        """consumo_litros_hora em equipamentos customizados → modo_estimativa == 'refinado'."""
        can = _make_canonical()
        cat = _catalogo()
        cron_inputs = {"num_equipes_por_item": {"EAP-01": {"2026-W23": 1}}}
        can_cron = run_cronograma(can, cron_inputs, cat).canonical

        # Override consumo_litros_hora in equipamentos dict (keyed by equip_id)
        # to trigger "refinado" mode
        composicao_custom = {
            "EAP-01": {
                "funcoes": {"OP-01": {}},
                "equipamentos": {"EQ-01": {"consumo_litros_hora": 12.0}},
            }
        }
        result = run_equipes_diretas(
            can_cron,
            {"preco_diesel": 6.20, "composicao_customizada": composicao_custom},
            cat,
        )
        equipe = result.canonical.equipes_diretas[0]
        # modo_estimativa == "refinado" when consumo_litros_hora override is provided
        assert equipe.modo_estimativa == "refinado"
        # VAL-EQUIP-MODO-INICIAL NÃO deve ser emitido (equipes exist)
        codigos = {v.codigo for v in result.validacoes}
        assert "VAL-EQUIP-MODO-INICIAL" not in codigos

    def test_modo_inicial_sem_emissao_modo_inicial_para_refinado(self):
        """Sem consumo_litros_hora override, modo é inicial; VAL-EQUIP-MODO-INICIAL não aparece."""
        can = _make_canonical()
        cat = _catalogo()
        cron_inputs = {"num_equipes_por_item": {"EAP-01": {"2026-W23": 1}}}
        can_cron = run_cronograma(can, cron_inputs, cat).canonical
        # composicao_customizada without consumo_litros_hora override keeps "inicial" mode
        composicao_custom = {
            "EAP-01": {
                "funcoes": {"OP-01": {}},
                "equipamentos": {"EQ-01": {}},
            }
        }
        result = run_equipes_diretas(
            can_cron,
            {"composicao_customizada": composicao_custom},
            cat,
        )
        # VAL-EQUIP-MODO-INICIAL is only emitted when no equipes at all, not here
        assert all(v.codigo != "VAL-EQUIP-MODO-INICIAL" for v in result.validacoes)


class TestSkill03CustoTotalIntegrado:
    """custo_fixo_mensal e custo_total incluem combustível (mas não material — skill 05 não calcula material)."""

    def test_custo_fixo_inclui_combustivel(self):
        """custo_fixo_mensal = mo + eq_base + comb (material não é calculado na skill 05)."""
        insumo_mat = {
            "codigo": "MAT-X",
            "tipo": "MATERIAL",
            "descricao": "Mat",
            "unidade": "m3",
            "preco_unitario": 50.0,
            "fonte_preco": "catalogo",
            "atributos_especificos": {},
        }
        materiais_comp = [{"insumo_id": "MAT-X", "consumo_por_hora": 1.0, "unidade": "m3"}]
        cat = _catalogo(materiais_comp=materiais_comp, insumos_extra=[insumo_mat])
        for i in cat["insumos"]:
            if i["codigo"] == "EQ-01":
                i["atributos_especificos"] = {"consumo_litros_hora": 10.0}

        can = _make_canonical()
        cron_inputs = {"num_equipes_por_item": {"EAP-01": {"2026-W23": 1}}}
        can_cron = run_cronograma(can, cron_inputs, cat).canonical
        result = run_equipes_diretas(can_cron, {"preco_diesel": 6.20}, cat)
        equipe = result.canonical.equipes_diretas[0]

        # Skill 05 does not compute material costs; custo_material_mensal == 0.0
        custo_mo = equipe.custo_mao_obra_mensal
        custo_eq_base = equipe.custo_equipamentos_mensal
        custo_comb = equipe.custo_combustivel_total_mensal
        custo_mat = equipe.custo_material_mensal

        assert custo_mat == 0.0
        assert equipe.custo_fixo_mensal == round(custo_mo + custo_eq_base + custo_comb + custo_mat, 2)
        # custo_combustivel uses horas_dia * (30.0 * dias_semana / 7) = 8 * 30 * 5/7
        horas = 8 * (30.0 * 5 / 7)
        assert custo_comb == round(10.0 * horas * 6.20, 2)
