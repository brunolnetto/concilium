"""ADR-130 F3 — Ligação de `resolver_producao_efetiva` ao read-path real de skill-05.

Cobre:
- `_build_producao_para_sinergia`: constrói `Producao` mínimo a partir do dict bruto do
  catálogo apenas quando `grafo_sinergia` está presente; None quando ausente/inválido.
- `_validar_sinergia_producao`: no-op (zero validações) quando não há grafo; surfaced
  VAL-SINERGIA-02/03 quando há divergência/gargalo inconsistente.
- `_build_comp_para_item`/`_build_dimensionamento` end-to-end com um CPU real do
  catálogo rfi-r02 (CPU-TERRA-ESCO-CARGA-1CAT-DMT2000, populado no PR #91): a
  produtividade/custo usados no dimensionamento NUNCA mudam por causa do grafo —
  apenas validações informativas são adicionadas.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

import pytest

import concilium.application.skills as _skills_pkg
from concilium.application.skills import run_cronograma
from concilium.application.skills import run_equipes_e_alocacao as run_equipes_diretas
from concilium.domain.constants import SEMANAS_POR_MES
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    EapItem,
    Meta,
    Praticabilidade,
    Projeto,
    RegimeTrabalho,
)

_ = _skills_pkg.run_equipes_e_alocacao  # trigger lazy load so _skill_helpers lands in sys.modules
_MOD = sys.modules["_concilium_skillpkg_05_equipes_e_alocacao._skill_helpers"]

_build_comp_para_item = _MOD._build_comp_para_item
_build_producao_para_sinergia = _MOD._build_producao_para_sinergia
_validar_sinergia_producao = _MOD._validar_sinergia_producao
_calcular_custo_equipamento = _MOD._calcular_custo_equipamento

# ── fixtures: CPU real do catálogo rfi-r02 (PR #91) ─────────────────────────
# CPU-TERRA-ESCO-CARGA-1CAT-DMT2000-PROD-001 —
# config/catalogos/rfi-r02/produtividades/CPU-TERRA-ESCO-CARGA-1CAT-DMT2000-PROD-001.json
_PROD_ID = "CPU-TERRA-ESCO-CARGA-1CAT-DMT2000-PROD-001"
_CPU_ID = "CPU-TERRA-ESCO-CARGA-1CAT-DMT2000"
_VALOR_HORARIO_REAL = 231.87
_CAP_ESCAVADEIRA_REAL = 230.4
_CAP_CAMINHAO_REAL = 42.7


def _composicao_padrao_equipe_real() -> dict:
    return {
        "funcoes": [
            {"funcao_id": "P0040", "num_pessoas": 1},
            {"funcao_id": "P0001", "num_pessoas": 1},
            {"funcao_id": "P0022", "num_pessoas": 1},
            {"funcao_id": "P0032", "num_pessoas": 7},
        ],
        "equipamentos": [
            {"equip_id": "E0016", "num_unidades": 1, "consumo_litros_hora": 28.58},
            {"equip_id": "E0007", "num_unidades": 7, "consumo_litros_hora": 2.76},
        ],
    }


def _grafo_sinergia_real(
    capacidade_escavadeira: float = _CAP_ESCAVADEIRA_REAL,
    capacidade_caminhao: float = _CAP_CAMINHAO_REAL,
    gargalo_declarado: str | None = "E0016",
) -> dict:
    return {
        "relacoes": [],
        "capacidades": [
            {
                "elemento_id": "E0016",
                "capacidade_horaria": capacidade_escavadeira,
                "unidade": "m3",
                "fonte": "fabricante",
            },
            {
                "elemento_id": "E0007",
                "capacidade_horaria": capacidade_caminhao,
                "unidade": "m3",
                "fonte": "fabricante",
            },
        ],
        "gargalo_declarado": gargalo_declarado,
    }


def _prod_dict(
    grafo_sinergia: dict | None = None,
    producao_horaria: float = _VALOR_HORARIO_REAL,
) -> dict:
    d = {
        "id": _PROD_ID,
        "codigo": _CPU_ID,
        "descricao": "Esc/carg/transp 1a cat DMT<=2000m",
        "producao_horaria": producao_horaria,
        "unidade": "m3",
        "origem": {
            "tipo": "calibrado_agis_rfi",
            "data_calibracao": "2026-05-08",
            "referencia": "Híbrido: composição/produtividade mendeslobo + precos RFI-R02.",
        },
        "composicao_padrao_equipe": _composicao_padrao_equipe_real(),
        "categoria": "TERRAPLENAGEM",
    }
    if grafo_sinergia is not None:
        d["grafo_sinergia"] = grafo_sinergia
    return d


def _cpu_dict() -> dict:
    return {
        "codigo": _CPU_ID,
        "descricao": "Esc/carg/transp 1a cat DMT<=2000m",
        "unidade": "m3",
        "origem": "PROPRIA",
        "categoria": "TERRAPLENAGEM",
        "producao_id_ref": _PROD_ID,
        "composicao_itens": [],
    }


def _insumos_reais() -> list[dict]:
    def _mo(codigo: str, desc: str) -> dict:
        return {
            "codigo": codigo,
            "tipo": "MAO_OBRA",
            "descricao": desc,
            "unidade": "mes",
            "preco_unitario": 2000.0,
            "fonte_preco": "catalogo",
            "atributos_especificos": {},
        }

    def _eq(codigo: str, desc: str) -> dict:
        return {
            "codigo": codigo,
            "tipo": "EQUIPAMENTO",
            "descricao": desc,
            "unidade": "h",
            "preco_unitario": 150.0,
            "fonte_preco": "catalogo",
            "atributos_especificos": {"consumo_litros_hora": 20.0},
        }

    return [
        _mo("P0040", "Encarregado"),
        _mo("P0001", "Operador escavadeira"),
        _mo("P0022", "Motorista caminhão basculante"),
        _mo("P0032", "Ajudante"),
        _eq("E0016", "Escavadeira hidráulica 22t"),
        _eq("E0007", "Caminhão basculante 14m3"),
        {
            "codigo": "MAT-TESTE",
            "tipo": "MATERIAL",
            "descricao": "Material de consumo de teste",
            "unidade": "un",
            "preco_unitario": 10.0,
            "fonte_preco": "catalogo",
            "atributos_especificos": {},
        },
    ]


def _catalogo(prod: dict) -> dict:
    return {
        "cpus": [_cpu_dict()],
        "insumos": _insumos_reais(),
        "producoes": [prod],
    }


def _make_canonical(item_id: str = "EAP-01") -> CanonicalModel:
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
            cpu_id=_CPU_ID,
            descricao="Escavação teste",
            unidade="m3",
            quantitativo=1000.0,
        )
    ]
    return CanonicalModel(meta=meta, projeto=proj, eap=eap, praticabilidade=prat)


def _physical_capacity_first_week(
    prod: dict, item_id: str = "EAP-01", cpu_hourly_override: float | None = None
) -> float:
    """Read the materialized physical F(m)*H from skill-04, not cost proxies."""
    can = _make_canonical(item_id=item_id)
    catalog = _catalogo(prod)
    if cpu_hourly_override is not None:
        catalog["cpus"][0]["cpu_meta"] = {"producao_horaria": cpu_hourly_override}
    out = run_cronograma(
        can, {"num_equipes_por_item": {item_id: {"2026-W23": 1}}}, catalog
    )
    assert out.canonical.cronograma is not None
    dist = out.canonical.cronograma.scheduled_activities[0].distribuicao_semanal
    return dist["2026-W23"].q_max_celula


def _run_skill05(prod: dict, item_id: str = "EAP-01") -> tuple:
    """Roda cronograma + skill-05 end-to-end; retorna (EquipeDireta, validacoes)."""
    can = _make_canonical(item_id=item_id)
    cat = _catalogo(prod)
    cron_inputs = {"num_equipes_por_item": {item_id: {"2026-W23": 1}}}
    can_cron = run_cronograma(can, cron_inputs, cat).canonical
    result = run_equipes_diretas(can_cron, {"preco_diesel": 6.20}, cat)
    equipe = result.canonical.equipes_diretas[0]
    return equipe, result.validacoes


# ─────────────────────────────────────────────────────────────────────────────
# _build_producao_para_sinergia
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildProducaoParaSinergia:
    def test_none_quando_sem_grafo_sinergia(self):
        assert _build_producao_para_sinergia(_prod_dict(grafo_sinergia=None)) is None

    def test_none_quando_grafo_sinergia_vazio(self):
        assert _build_producao_para_sinergia(_prod_dict(grafo_sinergia={})) is None

    def test_none_quando_prod_vazio(self):
        assert _build_producao_para_sinergia({}) is None

    def test_producao_construida_quando_grafo_presente(self):
        prod = _prod_dict(grafo_sinergia=_grafo_sinergia_real())
        producao = _build_producao_para_sinergia(prod)
        assert producao is not None
        assert producao.producao_horaria == _VALOR_HORARIO_REAL
        assert producao.grafo_sinergia is not None
        assert {c.elemento_id for c in producao.grafo_sinergia.capacidades} == {"E0016", "E0007"}

    def test_ignora_chaves_extras_do_catalogo_bruto(self):
        """`consumo_litros_hora` (chave legada, não `consumo_litros_hora_estimado`) não
        deve quebrar a reconstrução tipada (ADR-130 F3 — sanitização)."""
        prod = _prod_dict(grafo_sinergia=_grafo_sinergia_real())
        producao = _build_producao_para_sinergia(prod)
        assert producao is not None
        equips = producao.composicao_padrao_equipe.equipamentos
        assert {e.equip_id: e.num_unidades for e in equips} == {"E0016": 1, "E0007": 7}

    def test_none_quando_valor_horario_invalido(self):
        """Quando a construção do `Producao` mínimo falha (aqui, `producao_horaria`
        não-numérico → ValueError em `float(...)`), a função captura a exceção e
        retorna None em vez de propagar — no-op silencioso (ADR-130 F3)."""
        prod = _prod_dict(grafo_sinergia=_grafo_sinergia_real(), producao_horaria="nao-numerico")
        assert _build_producao_para_sinergia(prod) is None

    def test_producao_construida_quando_origem_e_string_solta(self):
        """Regressão: 119/169 produções do mendeslobo têm `origem` como string
        solta (ex.: "PROPRIA") em vez do dict {tipo, fonte_id, ...} — legado de
        como foram enriquecidas com grafo_sinergia (ADR-179). Reproduzia
        AttributeError('str' object has no attribute 'get') em produção
        (skill-05, ERRO_PRECONDICAO) sempre que o CPU referenciado tinha essa
        combinação (origem=string + grafo_sinergia presente)."""
        prod = _prod_dict(grafo_sinergia=_grafo_sinergia_real())
        prod["origem"] = "PROPRIA"

        producao = _build_producao_para_sinergia(prod)

        assert producao is not None
        assert producao.origem.referencia == "PROPRIA"
        assert producao.grafo_sinergia is not None


# ─────────────────────────────────────────────────────────────────────────────
# _calcular_custo_equipamento — custo_mensal_override
# ─────────────────────────────────────────────────────────────────────────────


class TestCalcularCustoEquipamentoCustoMensalOverride:
    def test_custo_mensal_override_substitui_custo_base_convertido(self):
        """custo_mensal_override != None descarta o custo_base derivado de
        preço/unidade (via _converter_preco_equip) e usa o valor do override
        (convertido para float)."""
        insumo = {
            "codigo": "EQ-01",
            "descricao": "Escavadeira",
            "preco_unitario": 100.0,
            "unidade": "h",
            "atributos_especificos": {"consumo_litros_hora": 20.0, "rental_unit": "hora_produtiva"},
        }
        sem_override, _ = _calcular_custo_equipamento(insumo, 1, 8, 21.4, 6.20)
        assert sem_override.custo_mensal == round(100.0 * 8 * 21.4, 2)

        com_override, _ = _calcular_custo_equipamento(insumo, 1, 8, 21.4, 6.20, custo_mensal_override="9999.5")
        assert com_override.custo_mensal == 9999.5
        assert com_override.custo_mensal != sem_override.custo_mensal


# ─────────────────────────────────────────────────────────────────────────────
# _validar_sinergia_producao — no-op e emissão de VAL-SINERGIA-02/03
# ─────────────────────────────────────────────────────────────────────────────


class TestValidarSinergiaProducao:
    def test_no_op_sem_grafo_sinergia(self):
        """ADR-130 F3: retrocompatibilidade total — a vasta maioria do catálogo hoje
        não tem grafo_sinergia; nenhuma validação deve ser adicionada."""
        validacoes: list = []
        _validar_sinergia_producao(_prod_dict(grafo_sinergia=None), validacoes)
        assert validacoes == []

    def test_sem_divergencia_quando_dados_calibrados_reais(self):
        """Os dados reais do PR #91 foram calibrados para <1% de divergência —
        nenhum VAL-SINERGIA-02/03 deve aparecer para o CPU real."""
        validacoes: list = []
        _validar_sinergia_producao(_prod_dict(grafo_sinergia=_grafo_sinergia_real()), validacoes)
        codigos = [v.codigo for v in validacoes]
        assert "VAL-SINERGIA-02" not in codigos
        assert "VAL-SINERGIA-03" not in codigos

    def test_val_sinergia_02_emitido_em_divergencia(self):
        """Capacidade da escavadeira reduzida à metade → produção derivada diverge
        > 15% do producao_horaria declarado → VAL-SINERGIA-02 (AVISO)."""
        validacoes: list = []
        grafo = _grafo_sinergia_real(capacidade_escavadeira=_CAP_ESCAVADEIRA_REAL / 2)
        _validar_sinergia_producao(_prod_dict(grafo_sinergia=grafo), validacoes)
        val02 = [v for v in validacoes if v.codigo == "VAL-SINERGIA-02"]
        assert len(val02) == 1
        assert val02[0].status == "AVISO"

    def test_val_sinergia_03_emitido_quando_gargalo_declarado_diverge(self):
        """gargalo_declarado="E0007" não bate com o gargalo real (E0016, capacidade
        efetiva menor) → VAL-SINERGIA-03 (AVISO)."""
        validacoes: list = []
        grafo = _grafo_sinergia_real(gargalo_declarado="E0007")
        _validar_sinergia_producao(_prod_dict(grafo_sinergia=grafo), validacoes)
        val03 = [v for v in validacoes if v.codigo == "VAL-SINERGIA-03"]
        assert len(val03) == 1
        assert val03[0].status == "AVISO"


# ─────────────────────────────────────────────────────────────────────────────
# _build_comp_para_item — composição retornada nunca muda por causa do grafo
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildCompParaItemComGrafo:
    def test_comp_identica_com_ou_sem_grafo(self):
        """O grafo de sinergia é puramente informativo — a composição usada para
        custear a equipe não muda (D3/A3: nenhuma sobrescrita silenciosa)."""
        cpu = _cpu_dict()

        validacoes_sem: list = []
        prod_lookup_sem = {_PROD_ID: _prod_dict(grafo_sinergia=None)}
        comp_sem = _build_comp_para_item(cpu, prod_lookup_sem, validacoes_sem)

        validacoes_com: list = []
        prod_lookup_com = {_PROD_ID: _prod_dict(grafo_sinergia=_grafo_sinergia_real())}
        comp_com = _build_comp_para_item(cpu, prod_lookup_com, validacoes_com)

        assert comp_sem == comp_com
        # A única diferença é a ausência/presença de validações VAL-SINERGIA-*
        assert [v.codigo for v in validacoes_sem if v.codigo.startswith("VAL-SINERGIA")] == []


# ─────────────────────────────────────────────────────────────────────────────
# Regressão: item malformado (string em vez de dict) em composicao_itens/
# prod_lookup não pode travar skill-05 com AttributeError ('str' object has no
# attribute 'get') — dado de catálogo/overlay resolvido sem validação de schema
# (CatalogResolver) pode conter isso após um merge/rascunho incompleto.
# ─────────────────────────────────────────────────────────────────────────────


class TestDimensionamentoComItemMalformado:
    def test_build_comp_para_item_prod_lookup_resolve_string(self):
        """prod_lookup[prod_id_ref] é uma string (não Producao dict) — não deve
        propagar AttributeError; cai para composição vazia (fallback)."""
        cpu = _cpu_dict()
        prod_lookup = {_PROD_ID: "PROD-SUGERIDA-APROXIMADA"}
        validacoes: list = []

        comp = _build_comp_para_item(cpu, prod_lookup, validacoes)

        assert isinstance(comp, dict)

    def test_validar_materiais_item_composicao_itens_com_string_solta(self):
        """composicao_itens com um elemento string solto (não {insumo_id, ...}) —
        não deve propagar AttributeError; item malformado é ignorado."""
        _validar_materiais_item = _MOD._validar_materiais_item
        comp = {"materiais": [], "funcoes": [], "equipamentos": []}
        cpu = {
            "codigo": "CPU-TESTE-MALFORMADO",
            "composicao_itens": [
                {"insumo_id": "AREIA", "categoria_custo": "MATERIAL", "coeficiente": 1.0},
                "DIESEL-S10",  # malformado: string em vez de dict
            ],
        }
        validacoes: list = []

        _validar_materiais_item(comp, cpu, validacoes)

        # AREIA está em composicao_itens (MATERIAL) mas não em comp["materiais"] —
        # gera VAL-EQUIP-MAT-02; a string solta não gera exceção nem entra na comparação.
        assert any(v.codigo == "VAL-EQUIP-MAT-02" for v in validacoes)


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end via _build_dimensionamento / _dimensionar_item_equipe (skill-05 real)
# ─────────────────────────────────────────────────────────────────────────────


class TestDimensionamentoEndToEndComGrafoSinergia:
    def test_material_catalogado_persiste_gamma_material_na_base_horaria_semanal(self):
        prod = _prod_dict(grafo_sinergia=None)
        prod["composicao_padrao_equipe"]["materiais"] = [
            {"insumo_id": "MAT-TESTE", "consumo_por_hora": 2.5},
        ]

        equipe, _ = _run_skill05(prod)

        horas_mes = 8.0 * (30.0 * 5.0 / 7.0)
        custo_material_esperado = 2.5 * 10.0 * horas_mes
        fator_hora_catalogo = SEMANAS_POR_MES * 8.0 * 5.0

        assert equipe.custo_material_mensal == pytest.approx(custo_material_esperado)
        assert equipe.gamma_material_catalogo == pytest.approx(equipe.custo_material_mensal / fator_hora_catalogo)

    def test_custo_mensal_eh_identico_mas_custo_total_segue_cronograma_com_sinergia(self):
        """Composição e presença contratual fixas: F(m) altera capacidade, não tarifa."""
        equipe_sem, validacoes_sem = _run_skill05(_prod_dict(grafo_sinergia=None))
        equipe_com, validacoes_com = _run_skill05(_prod_dict(grafo_sinergia=_grafo_sinergia_real()))

        # In manual mode the SAME contracted front is paid for the SAME
        # week; altering physical productivity does not retroactively change
        # that contractual presence or invent an eta_s loss.
        assert equipe_com.custo_total == equipe_sem.custo_total
        assert _physical_capacity_first_week(_prod_dict(grafo_sinergia=_grafo_sinergia_real())) == pytest.approx(
            40 * _CAP_ESCAVADEIRA_REAL
        )
        assert _physical_capacity_first_week(_prod_dict(grafo_sinergia=None)) == pytest.approx(
            40 * _VALOR_HORARIO_REAL
        )
        assert equipe_com.custo_fixo_mensal == equipe_sem.custo_fixo_mensal
        assert equipe_com.custo_mao_obra_mensal == equipe_sem.custo_mao_obra_mensal
        assert equipe_com.custo_equipamentos_mensal == equipe_sem.custo_equipamentos_mensal

        sinergia_sem = [v for v in validacoes_sem if v.codigo.startswith("VAL-SINERGIA")]
        sinergia_com = [v for v in validacoes_com if v.codigo.startswith("VAL-SINERGIA")]
        assert sinergia_sem == []
        assert sinergia_com == []  # dados reais calibrados: sem divergência/gargalo inconsistente

    def test_horas_contratuais_nao_derivam_da_produtividade_do_catalogo(self):
        """F(m)*40 h: a taxa de CPU pode diferir do catálogo e do grafo."""
        prod = _prod_dict(grafo_sinergia=_grafo_sinergia_real())
        assert _physical_capacity_first_week(
            prod, cpu_hourly_override=100.0
        ) == pytest.approx(40 * _CAP_ESCAVADEIRA_REAL)

    def test_val_sinergia_02_e_03_surfaced_end_to_end_com_custo_total_derivado(self):
        """With a divergent physical bottleneck, diagnostics surface while a
        fixed manual allocation retains the same contract cost."""
        equipe_base, _ = _run_skill05(_prod_dict(grafo_sinergia=None))
        grafo_divergente = _grafo_sinergia_real(
            capacidade_escavadeira=_CAP_ESCAVADEIRA_REAL / 2,
            gargalo_declarado="E0007",
        )
        equipe_div, validacoes_div = _run_skill05(_prod_dict(grafo_sinergia=grafo_divergente))

        # Physical output drops with the bottleneck, but the manually
        # contracted one-week resource remains billed for the whole week.
        # A cost difference requires a different feasible allocation/span.
        assert equipe_div.custo_total == equipe_base.custo_total
        assert _physical_capacity_first_week(
            _prod_dict(grafo_sinergia=grafo_divergente)
        ) == pytest.approx(40 * _CAP_ESCAVADEIRA_REAL / 2)
        assert equipe_div.custo_fixo_mensal == equipe_base.custo_fixo_mensal

        codigos = {v.codigo for v in validacoes_div}
        assert "VAL-SINERGIA-02" in codigos
        assert "VAL-SINERGIA-03" in codigos


def test_rcpsp_nominal_duration_uses_physical_graph_capacity() -> None:
    """A catalog P calibrated for the graph must NOT be multiplied by four teams."""
    mod = _skills_pkg._load_skill_module("04-cronograma")
    can = _make_canonical()
    can = can.model_copy(
        update={"eap": [can.eap[0].model_copy(update={"quantitativo": 1200.0})]}
    )
    graph = {
        "fonte": "s",
        "sorvedouro": "t",
        "dominio": ["s", "mid", "t"],
        "arestas_fluxo": [
            {"aresta_id": "supply", "origem": "s", "destino": "mid", "capacidade_horaria": 40},
            {"aresta_id": "shared", "origem": "mid", "destino": "t", "capacidade_horaria": 15},
        ],
    }
    prod = _prod_dict(grafo_sinergia=graph, producao_horaria=15.0)
    duration = mod._compute_productive_weeks(
        "EAP-01",
        4,
        can,
        {_CPU_ID: _cpu_dict()},
        {_PROD_ID: prod},
        [],
    )
    # F(4)=15 u/h with shared bottleneck, 40 h/week => 600/wk,
    # thus Q=1,200 takes 2 weeks, not ceil(1,200/(15*40*4))=1.
    assert duration == 2
