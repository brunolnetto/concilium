"""Unit tests for _skill_helpers_b.py (Skill 05 — Equipes e Alocação).

Covers:
- _resolve_salario: with/without override, ConversorUnidades success/failure
- _resolve_encargo_funcao: priority chain (override > percentual_encargos_local > categoria)
- _calcular_custo_funcao: PJ, custo_com_encargos, full enc+he, custo_unitario_override
- _converter_preco_equip: success, fallback h, error unmapped unit
- _consumo_from_decomposicao: with/without custo_diesel_h/preco_diesel
- _build_requisitos_e_tipos: with and without cronograma (VAL-EQUIP-SEM-CRON)
- _build_alocacoes_pool: pool auto-creation, Alocacao fields
- _processar_funcoes_requisitos: tipo creation, requisitos added
- _processar_equipamentos_requisitos: tipo creation, requisitos added
"""

from __future__ import annotations

# ── Import the module under test ────────────────────────────────────────────
# The module lives in "05-equipes-e-alocacao/" which is not a valid Python
# identifier, so we load it via importlib below instead of a direct import.
# ---------------------------------------------------------------------------
# Helpers to import from the actual file path since the module lives in a
# directory whose name starts with a digit ("05-equipes-e-alocacao") and the
# public entrypoint re-exports everything.
# ---------------------------------------------------------------------------
import importlib.util
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_HELPERS_PATH = str(
    Path(__file__).resolve().parents[2]
    / "src"
    / "concilium"
    / "application"
    / "skills"
    / "manifests"
    / "05-equipes-e-alocacao"
    / "_skill_helpers_b.py"
)


def _load_helpers():
    """Load _skill_helpers_b directly by file path (dir name is not a valid identifier)."""
    spec = importlib.util.spec_from_file_location("_skill_helpers_b", _HELPERS_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Load once at module level
_mod = _load_helpers()

_resolve_salario = _mod._resolve_salario
_resolve_encargo_funcao = _mod._resolve_encargo_funcao
_calcular_custo_funcao = _mod._calcular_custo_funcao
_converter_preco_equip = _mod._converter_preco_equip
_consumo_from_decomposicao = _mod._consumo_from_decomposicao
_build_requisitos_e_tipos = _mod._build_requisitos_e_tipos
_build_alocacoes_pool = _mod._build_alocacoes_pool
_processar_funcoes_requisitos = _mod._processar_funcoes_requisitos
_processar_equipamentos_requisitos = _mod._processar_equipamentos_requisitos

# ── Domain model imports ─────────────────────────────────────────────────────
from concilium.domain.models.canonical import (  # noqa: E402
    Atividade,
    CanonicalModel,
    Coordenadas,
    EquipamentoEquipeDireta,
    EquipeDireta,
    FuncaoEquipeDireta,
    Meta,
    Projeto,
    RecursoPool,
    RegimeTrabalho,
    RequisitoRecurso,
    TipoRecurso,
)

# ── ConversorUnidades path ───────────────────────────────────────────────────
_CONV_PATH = "concilium.domain.services.conversor_unidades.ConversorUnidades"

# ============================================================================
# Shared fixtures
# ============================================================================


def _make_projeto() -> Projeto:
    return Projeto(
        id=str(uuid.uuid4()),
        nome="Projeto Teste",
        tipo_obra="terraplenagem",
        localizacao="Brasil",
        coordenadas=Coordenadas(lat=-15.0, lng=-47.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2025, 1, 1),
        data_termino=date(2025, 12, 31),
        snapshot_catalogo_id="cat-001",
        snapshot_perfil_id="perfil-001",
    )


def _make_meta() -> Meta:
    return Meta(
        gerado_em=datetime(2025, 1, 1, tzinfo=UTC),
        contexto_id="ctx-001",
    )


def _make_canonical(
    atividades=None,
    tipos_recurso=None,
    recurso_pool=None,
) -> CanonicalModel:
    return CanonicalModel(
        meta=_make_meta(),
        projeto=_make_projeto(),
        atividades=atividades or [],
        tipos_recurso=tipos_recurso or [],
        recurso_pool=recurso_pool or [],
    )


def _make_atividade(atividade_id: str, eap_item_id: str) -> Atividade:
    return Atividade(
        atividade_id=atividade_id,
        eap_item_id=eap_item_id,
        descricao="Atividade de teste",
        fracao_quantitativo=1.0,
        quantitativo_atividade=100.0,
        cpu_id="cpu-001",
    )


def _make_equipe(item_id: str, funcoes=None, equipamentos=None) -> EquipeDireta:
    return EquipeDireta(
        equipe_id=str(uuid.uuid4()),
        item_id=item_id,
        cpu_id="cpu-001",
        nome="Equipe A",
        funcoes=funcoes or [],
        equipamentos=equipamentos or [],
    )


def _make_funcao(
    funcao_id: str = "F1", descricao: str = "Operador", num_pessoas: int = 2, custo_mensal_unitario: float = 3000.0
) -> FuncaoEquipeDireta:
    return FuncaoEquipeDireta(
        funcao_id=funcao_id,
        descricao=descricao,
        num_pessoas=num_pessoas,
        custo_mensal_unitario=custo_mensal_unitario,
    )


def _make_equipamento(
    equip_id: str = "E1", descricao: str = "Escavadeira", num_unidades: int = 1, custo_mensal: float = 10000.0
) -> EquipamentoEquipeDireta:
    return EquipamentoEquipeDireta(
        equip_id=equip_id,
        descricao=descricao,
        num_unidades=num_unidades,
        custo_mensal=custo_mensal,
    )


# ============================================================================
# Tests for _resolve_salario
# ============================================================================


class TestResolveSalario:
    def test_salario_override_returns_override(self):
        result = _resolve_salario(1000.0, "mes", 5000.0)
        assert result == 5000.0

    def test_salario_override_zero_is_honoured(self):
        result = _resolve_salario(1000.0, "mes", 0.0)
        assert result == 0.0

    def test_no_override_calls_conversor(self):
        with patch(f"{_CONV_PATH}.converter_preco", return_value=2200.0) as mock_conv:
            result = _resolve_salario(10.0, "h", None)
        mock_conv.assert_called_once_with(10.0, "h", "mes")
        assert result == 2200.0

    def test_no_override_mes_unit_passthrough(self):
        # "mes" -> "mes" should return same value (ConversorUnidades identity)
        with patch(f"{_CONV_PATH}.converter_preco", return_value=3000.0):
            result = _resolve_salario(3000.0, "mes", None)
        assert result == 3000.0

    def test_conversor_exception_falls_back_to_raw_price(self):
        with patch(f"{_CONV_PATH}.converter_preco", side_effect=ValueError("no path")):
            result = _resolve_salario(999.0, "xyz", None)
        assert result == 999.0


# ============================================================================
# Tests for _resolve_encargo_funcao
# ============================================================================


class TestResolveEncargoFuncao:
    def test_encargo_override_takes_priority(self):
        atrib = {"percentual_encargos_local": 0.50}
        result = _resolve_encargo_funcao(atrib, 0.72, 0.80, 0.60, "horista")
        assert result == 0.72

    def test_percentual_encargos_local_second_priority(self):
        atrib = {"percentual_encargos_local": 0.45}
        result = _resolve_encargo_funcao(atrib, None, 0.80, 0.60, "horista")
        assert result == 0.45

    def test_horista_categoria_uses_enc_horista(self):
        atrib = {}
        result = _resolve_encargo_funcao(atrib, None, 0.80, 0.60, "horista")
        assert result == 0.80

    def test_horista_prefix_match(self):
        atrib = {}
        result = _resolve_encargo_funcao(atrib, None, 0.80, 0.60, "horista_qualificado")
        assert result == 0.80

    def test_mensalista_uses_enc_mensalista(self):
        atrib = {}
        result = _resolve_encargo_funcao(atrib, None, 0.80, 0.60, "mensalista")
        assert result == 0.60

    def test_mensalista_fallback_to_horista_when_mensalista_none(self):
        atrib = {}
        result = _resolve_encargo_funcao(atrib, None, 0.80, None, "mensalista")
        assert result == 0.80

    def test_empty_categoria_uses_mensalista_path(self):
        atrib = {}
        result = _resolve_encargo_funcao(atrib, None, 0.80, 0.55, "")
        assert result == 0.55

    def test_encargo_override_as_string_converted_to_float(self):
        atrib = {}
        result = _resolve_encargo_funcao(atrib, "0.35", 0.80, 0.60, "horista")
        assert result == pytest.approx(0.35)


# ============================================================================
# Tests for _calcular_custo_funcao
# ============================================================================


class TestCalcularCustoFuncao:
    def _base_insumo(self, preco=3000.0, unidade="mes", atrib=None):
        return {
            "preco_unitario": preco,
            "unidade": unidade,
            "atributos_especificos": atrib or {},
        }

    def test_pj_categoria_custo_unit_equals_salario(self):
        insumo = self._base_insumo(atrib={"categoria_sindical": "PJ"})
        with patch(f"{_CONV_PATH}.converter_preco", return_value=3000.0):
            salario, he_pct, custo = _calcular_custo_funcao(
                insumo, num_pessoas=1, enc_horista=0.8, he_override=None, enc_mensalista=0.6
            )
        assert salario == 3000.0
        assert custo == 3000.0

    def test_custo_com_encargos_path(self):
        """When atrib has custo_com_encargos > 0, use it directly."""
        insumo = self._base_insumo(atrib={"custo_com_encargos": 4000.0})
        with patch(f"{_CONV_PATH}.converter_preco", return_value=3000.0):
            salario, he_pct, custo = _calcular_custo_funcao(
                insumo, num_pessoas=1, enc_horista=0.8, he_override=0.0, enc_mensalista=0.6
            )
        assert custo == 4000.0

    def test_custo_com_encargos_with_he(self):
        """custo_com_encargos * (1 + he_pct)."""
        insumo = self._base_insumo(atrib={"custo_com_encargos": 4000.0})
        with patch(f"{_CONV_PATH}.converter_preco", return_value=3000.0):
            salario, he_pct, custo = _calcular_custo_funcao(
                insumo, num_pessoas=1, enc_horista=0.8, he_override=0.20, enc_mensalista=0.6
            )
        assert custo == pytest.approx(4800.0)

    def test_full_enc_he_path(self):
        """salario * (1 + enc) * (1 + he_pct)."""
        insumo = self._base_insumo(atrib={"categoria_sindical": "mensalista"})
        with patch(f"{_CONV_PATH}.converter_preco", return_value=2000.0):
            salario, he_pct, custo = _calcular_custo_funcao(
                insumo, num_pessoas=1, enc_horista=0.8, he_override=0.10, enc_mensalista=0.60
            )
        # 2000 * 1.60 * 1.10 = 3520
        assert custo == pytest.approx(3520.0)
        assert salario == 2000.0
        assert he_pct == 0.10

    def test_custo_unitario_override_short_circuits(self):
        insumo = self._base_insumo(atrib={"categoria_sindical": "horista"})
        with patch(f"{_CONV_PATH}.converter_preco", return_value=2000.0):
            salario, he_pct, custo = _calcular_custo_funcao(
                insumo,
                num_pessoas=1,
                enc_horista=0.8,
                he_override=None,
                enc_mensalista=0.6,
                custo_unitario_override=9999.99,
            )
        assert custo == 9999.99
        # salario and he_pct are still computed even with override
        assert salario == 2000.0

    def test_he_override_none_uses_atrib_default(self):
        insumo = self._base_insumo(
            atrib={
                "categoria_sindical": "mensalista",
                "horas_extras_pct_padrao": 0.05,
            }
        )
        with patch(f"{_CONV_PATH}.converter_preco", return_value=2000.0):
            salario, he_pct, custo = _calcular_custo_funcao(
                insumo, num_pessoas=1, enc_horista=0.8, he_override=None, enc_mensalista=0.60
            )
        assert he_pct == 0.05
        # 2000 * 1.60 * 1.05 = 3360
        assert custo == pytest.approx(3360.0)

    def test_pj_with_he_override_zero(self):
        insumo = self._base_insumo(atrib={"categoria_sindical": "pj-autonomo"})
        with patch(f"{_CONV_PATH}.converter_preco", return_value=5000.0):
            salario, he_pct, custo = _calcular_custo_funcao(
                insumo, num_pessoas=1, enc_horista=0.8, he_override=0.0, enc_mensalista=0.6
            )
        assert custo == 5000.0  # PJ path: custo_unit = salario (he not applied for PJ)

    def test_salario_override_used(self):
        insumo = self._base_insumo(atrib={"categoria_sindical": "PJ"})
        with patch(f"{_CONV_PATH}.converter_preco", return_value=3000.0):
            salario, he_pct, custo = _calcular_custo_funcao(
                insumo, num_pessoas=1, enc_horista=0.8, he_override=None, enc_mensalista=0.6, salario_override=8000.0
            )
        assert salario == 8000.0
        assert custo == 8000.0


# ============================================================================
# Tests for _converter_preco_equip
# ============================================================================


class TestConverterPrecoEquip:
    def test_successful_conversion(self):
        insumo = {"preco_unitario": 10.0, "unidade": "h", "codigo": "EQ-01"}
        with patch(f"{_CONV_PATH}.converter_preco", return_value=2200.0):
            result = _converter_preco_equip(insumo, horas_dia=8.0, dias_uteis=26.0)
        assert result == 2200.0

    def test_fallback_for_unidade_h(self):
        insumo = {"preco_unitario": 100.0, "unidade": "h", "codigo": "EQ-02"}
        with patch(f"{_CONV_PATH}.converter_preco", side_effect=Exception("no path")):
            result = _converter_preco_equip(insumo, horas_dia=8.0, dias_uteis=26.0)
        # fallback: 100 * (8 * 26) = 100 * 208 = 20800
        assert result == pytest.approx(20800.0)

    def test_error_path_unmapped_unit_returns_raw_price(self):
        insumo = {"preco_unitario": 500.0, "unidade": "km", "codigo": "EQ-03"}
        with patch(f"{_CONV_PATH}.converter_preco", side_effect=Exception("no path")):
            result = _converter_preco_equip(insumo, horas_dia=8.0, dias_uteis=26.0)
        # unidade != "h" so returns raw preco
        assert result == 500.0

    def test_missing_unidade_defaults_to_h(self):
        """When unidade key is missing, defaults to 'h', so fallback uses horas_mes."""
        insumo = {"preco_unitario": 50.0}  # no "unidade" key
        with patch(f"{_CONV_PATH}.converter_preco", side_effect=Exception("fail")):
            result = _converter_preco_equip(insumo, horas_dia=8.0, dias_uteis=26.0)
        # default unidade="h", fallback = 50 * (8*26) = 10400
        assert result == pytest.approx(10400.0)

    def test_no_exception_returns_conversor_result_directly(self):
        insumo = {"preco_unitario": 30.0, "unidade": "dia", "codigo": "EQ-04"}
        with patch(f"{_CONV_PATH}.converter_preco", return_value=780.0):
            result = _converter_preco_equip(insumo, horas_dia=8.0, dias_uteis=26.0)
        assert result == 780.0


# ============================================================================
# Tests for _consumo_from_decomposicao
# ============================================================================


class TestConsumoFromDecomposicao:
    def test_with_custo_diesel_h_and_preco_diesel(self):
        decomp = {"custo_diesel_h": 50.0}
        result = _consumo_from_decomposicao(decomp, preco_diesel=5.0)
        assert result == pytest.approx(10.0)

    def test_zero_custo_diesel_h_returns_zero(self):
        decomp = {"custo_diesel_h": 0.0}
        result = _consumo_from_decomposicao(decomp, preco_diesel=5.0)
        assert result == 0.0

    def test_missing_custo_diesel_h_returns_zero(self):
        decomp = {}
        result = _consumo_from_decomposicao(decomp, preco_diesel=5.0)
        assert result == 0.0

    def test_zero_preco_diesel_returns_zero(self):
        decomp = {"custo_diesel_h": 50.0}
        result = _consumo_from_decomposicao(decomp, preco_diesel=0.0)
        assert result == 0.0

    def test_none_custo_diesel_h_treated_as_zero(self):
        decomp = {"custo_diesel_h": None}
        result = _consumo_from_decomposicao(decomp, preco_diesel=5.0)
        assert result == 0.0

    def test_both_positive_divides_correctly(self):
        decomp = {"custo_diesel_h": 30.0}
        result = _consumo_from_decomposicao(decomp, preco_diesel=6.0)
        assert result == pytest.approx(5.0)


# ============================================================================
# Tests for _processar_funcoes_requisitos
# ============================================================================


class TestProcessarFuncoesRequisitos:
    def test_creates_tipo_for_new_funcao(self):
        eq = _make_equipe("item-1", funcoes=[_make_funcao("F1", "Operador", 2, 3000.0)])
        atv = _make_atividade("atv-1", "item-1")
        atvs_por_item = defaultdict(list, {"item-1": [atv]})
        tipos = {}
        requisitos = []
        d_ini = date(2025, 1, 1)
        d_fim = date(2025, 12, 31)

        _processar_funcoes_requisitos(eq, d_ini, d_fim, atvs_por_item, tipos, requisitos)

        assert "FUNC-F1" in tipos
        t = tipos["FUNC-F1"]
        assert t.nome == "Operador"
        assert t.categoria == "EQUIPE"
        assert t.custo_unitario_dia == round(3000.0 / 26, 2)

    def test_creates_requisito_per_atividade(self):
        eq = _make_equipe("item-1", funcoes=[_make_funcao("F1", num_pessoas=3)])
        atv1 = _make_atividade("atv-1", "item-1")
        atv2 = _make_atividade("atv-2", "item-1")
        atvs_por_item = defaultdict(list, {"item-1": [atv1, atv2]})
        tipos = {}
        requisitos = []

        _processar_funcoes_requisitos(eq, date(2025, 1, 1), date(2025, 12, 31), atvs_por_item, tipos, requisitos)

        assert len(requisitos) == 2
        for req in requisitos:
            assert req.tipo_recurso_id == "FUNC-F1"
            assert req.quantidade == 3.0

    def test_does_not_overwrite_existing_tipo(self):
        existing_tipo = TipoRecurso(id="FUNC-F1", nome="Existente", categoria="EQUIPE", custo_unitario_dia=99.0)
        eq = _make_equipe("item-1", funcoes=[_make_funcao("F1", "Novo")])
        atvs_por_item = defaultdict(list, {"item-1": []})
        tipos = {"FUNC-F1": existing_tipo}
        requisitos = []

        _processar_funcoes_requisitos(eq, date(2025, 1, 1), date(2025, 12, 31), atvs_por_item, tipos, requisitos)

        assert tipos["FUNC-F1"].nome == "Existente"


# ============================================================================
# Tests for _processar_equipamentos_requisitos
# ============================================================================


class TestProcessarEquipamentosRequisitos:
    def test_creates_tipo_for_new_equip(self):
        eq = _make_equipe("item-2", equipamentos=[_make_equipamento("E1", "Escavadeira", 1, 10000.0)])
        atv = _make_atividade("atv-3", "item-2")
        atvs_por_item = defaultdict(list, {"item-2": [atv]})
        tipos = {}
        requisitos = []

        _processar_equipamentos_requisitos(eq, date(2025, 1, 1), date(2025, 12, 31), atvs_por_item, tipos, requisitos)

        assert "EQUIP-E1" in tipos
        t = tipos["EQUIP-E1"]
        assert t.nome == "Escavadeira"
        assert t.categoria == "EQUIPAMENTO"
        assert t.custo_unitario_dia == round(10000.0 / 26, 2)

    def test_creates_requisito_with_num_unidades(self):
        eq = _make_equipe("item-2", equipamentos=[_make_equipamento("E1", num_unidades=3)])
        atv = _make_atividade("atv-3", "item-2")
        atvs_por_item = defaultdict(list, {"item-2": [atv]})
        tipos = {}
        requisitos = []

        _processar_equipamentos_requisitos(eq, date(2025, 1, 1), date(2025, 12, 31), atvs_por_item, tipos, requisitos)

        assert len(requisitos) == 1
        assert requisitos[0].quantidade == 3.0


# ============================================================================
# Tests for _build_requisitos_e_tipos
# ============================================================================


class TestBuildRequisitosETipos:
    def _cron_lookup_with_dist(self, item_id: str) -> dict:
        """Fake cron_lookup where item has distribuicao_semanal."""
        mock_cron = MagicMock()
        mock_cron.distribuicao_semanal = {"2025-W01": MagicMock(), "2025-W52": MagicMock()}
        return {item_id: mock_cron}

    def test_emits_val_equip_sem_cron_when_no_cron(self):
        eq = _make_equipe("item-X")
        canonical = _make_canonical(atividades=[])
        validacoes = []

        _build_requisitos_e_tipos(
            equipes=[eq],
            canonical_in=canonical,
            cron_lookup={},  # no entry for item-X
            validacoes=validacoes,
        )

        codes = [v.codigo for v in validacoes]
        assert "VAL-EQUIP-SEM-CRON" in codes

    def test_emits_val_equip_sem_cron_when_no_distribuicao(self):
        eq = _make_equipe("item-Y")
        canonical = _make_canonical(atividades=[])
        validacoes = []
        mock_cron = MagicMock()
        mock_cron.distribuicao_semanal = {}  # empty dict

        _build_requisitos_e_tipos(
            equipes=[eq],
            canonical_in=canonical,
            cron_lookup={"item-Y": mock_cron},
            validacoes=validacoes,
        )

        codes = [v.codigo for v in validacoes]
        assert "VAL-EQUIP-SEM-CRON" in codes

    def test_uses_projeto_data_inicio_when_no_cron(self):
        eq = _make_equipe("item-Z")
        canonical = _make_canonical(atividades=[])
        validacoes = []

        requisitos, tipos = _build_requisitos_e_tipos(
            equipes=[eq],
            canonical_in=canonical,
            cron_lookup={},
            validacoes=validacoes,
        )
        # No atividades -> no requisitos, but validation should fire
        assert any(v.codigo == "VAL-EQUIP-SEM-CRON" for v in validacoes)

    def test_with_cron_no_warning(self):
        item_id = "item-A"
        funcao = _make_funcao("F1", "Operador", 2, 2600.0)
        eq = _make_equipe(item_id, funcoes=[funcao])
        atv = _make_atividade("atv-1", item_id)
        canonical = _make_canonical(atividades=[atv])
        validacoes = []
        cron_lookup = self._cron_lookup_with_dist(item_id)

        requisitos, tipos = _build_requisitos_e_tipos(
            equipes=[eq],
            canonical_in=canonical,
            cron_lookup=cron_lookup,
            validacoes=validacoes,
        )

        assert not any(v.codigo == "VAL-EQUIP-SEM-CRON" for v in validacoes)
        assert "FUNC-F1" in tipos
        assert len(requisitos) == 1

    def test_with_cron_sets_dates_from_distribuicao(self):
        item_id = "item-B"
        funcao = _make_funcao("F2", "Motorista", 1, 2000.0)
        eq = _make_equipe(item_id, funcoes=[funcao])
        atv = _make_atividade("atv-2", item_id)
        canonical = _make_canonical(atividades=[atv])
        validacoes = []
        mock_cron = MagicMock()
        mock_cron.distribuicao_semanal = {"2025-W01": MagicMock(), "2025-W26": MagicMock()}
        cron_lookup = {item_id: mock_cron}

        requisitos, tipos = _build_requisitos_e_tipos(
            equipes=[eq],
            canonical_in=canonical,
            cron_lookup=cron_lookup,
            validacoes=validacoes,
        )

        assert len(requisitos) == 1
        req = requisitos[0]
        # d_ini from "2025-W01".split("-W")[0] + "-01-01" = 2025-01-01
        assert req.data_inicio == date(2025, 1, 1)
        # d_fim from "2025-W26".split("-W")[0] + "-12-31" = 2025-12-31
        assert req.data_termino == date(2025, 12, 31)

    def test_existing_tipos_recurso_preserved(self):
        """Tipos already in canonical_in are included in returned tipos dict."""
        existing = TipoRecurso(id="EXISTING-001", nome="Existente", categoria="EQUIPE", custo_unitario_dia=100.0)
        canonical = _make_canonical(atividades=[], tipos_recurso=[existing])
        validacoes = []

        _, tipos = _build_requisitos_e_tipos(
            equipes=[],
            canonical_in=canonical,
            cron_lookup={},
            validacoes=validacoes,
        )

        assert "EXISTING-001" in tipos


# ============================================================================
# Tests for _build_alocacoes_pool
# ============================================================================


class TestBuildAlocacoesPool:
    def _make_requisito(
        self, tipo_recurso_id: str, atividade_id: str = "atv-1", quantidade: float = 2.0
    ) -> RequisitoRecurso:
        return RequisitoRecurso(
            requisito_id=str(uuid.uuid4()),
            atividade_id=atividade_id,
            tipo_recurso_id=tipo_recurso_id,
            descricao="Req de teste",
            quantidade=quantidade,
            data_inicio=date(2025, 1, 1),
            data_termino=date(2025, 6, 30),
        )

    def test_pool_auto_created_for_new_tipo(self):
        canonical = _make_canonical()
        tid = "FUNC-F99"
        tipos = {tid: TipoRecurso(id=tid, nome="Operador", categoria="EQUIPE", custo_unitario_dia=100.0)}
        requisitos = [self._make_requisito(tid)]

        alocacoes, pool_dict = _build_alocacoes_pool(requisitos, canonical, tipos)

        assert tid in pool_dict
        pool = pool_dict[tid]
        assert pool.quantidade_total == 1000
        assert pool.quantidade_disponivel == 1000
        assert str(canonical.projeto.id) == pool.projeto_id

    def test_alocacao_fields_are_correct(self):
        canonical = _make_canonical()
        tid = "EQUIP-E99"
        tipos = {tid: TipoRecurso(id=tid, nome="Trator", categoria="EQUIPAMENTO", custo_unitario_dia=500.0)}
        req = self._make_requisito(tid, atividade_id="atv-42", quantidade=3.0)
        alocacoes, pool_dict = _build_alocacoes_pool([req], canonical, tipos)

        assert len(alocacoes) == 1
        aloc = alocacoes[0]
        assert aloc.atividade_id == "atv-42"
        assert aloc.quantidade_alocada == 3.0
        assert aloc.status == "PLANEJADA"
        assert aloc.recurso_id == pool_dict[tid].id
        assert aloc.data_inicio == date(2025, 1, 1)
        assert aloc.data_termino == date(2025, 6, 30)

    def test_existing_pool_not_overwritten(self):
        """RecursoPool already in canonical_in should be preserved."""
        tid = "FUNC-F10"
        existing_pool = RecursoPool(
            id="existing-pool-id",
            tipo_id=tid,
            projeto_id="proj-001",
            quantidade_total=5,
            quantidade_disponivel=5,
        )
        canonical = _make_canonical(recurso_pool=[existing_pool])
        tipos = {tid: TipoRecurso(id=tid, nome="Encarregado", categoria="EQUIPE", custo_unitario_dia=200.0)}
        req = self._make_requisito(tid)
        alocacoes, pool_dict = _build_alocacoes_pool([req], canonical, tipos)

        # existing pool preserved (not replaced by auto-created)
        assert pool_dict[tid].id == "existing-pool-id"
        assert pool_dict[tid].quantidade_total == 5

    def test_requisito_without_matching_tipo_skipped(self):
        """Requisito whose tipo_recurso_id not in tipos or pool is silently skipped."""
        canonical = _make_canonical()
        tipos = {}  # no tipos
        req = self._make_requisito("UNKNOWN-TYPE")
        alocacoes, pool_dict = _build_alocacoes_pool([req], canonical, tipos)

        assert len(alocacoes) == 0

    def test_multiple_requisitos_sorted_by_data_inicio(self):
        canonical = _make_canonical()
        tid = "FUNC-F20"
        tipos = {tid: TipoRecurso(id=tid, nome="Operador", categoria="EQUIPE", custo_unitario_dia=150.0)}
        req_late = RequisitoRecurso(
            requisito_id=str(uuid.uuid4()),
            atividade_id="atv-late",
            tipo_recurso_id=tid,
            descricao="Late",
            quantidade=1.0,
            data_inicio=date(2025, 6, 1),
            data_termino=date(2025, 12, 31),
        )
        req_early = RequisitoRecurso(
            requisito_id=str(uuid.uuid4()),
            atividade_id="atv-early",
            tipo_recurso_id=tid,
            descricao="Early",
            quantidade=1.0,
            data_inicio=date(2025, 1, 1),
            data_termino=date(2025, 3, 31),
        )
        alocacoes, _ = _build_alocacoes_pool([req_late, req_early], canonical, tipos)

        assert len(alocacoes) == 2
        # sorted by data_inicio: early first
        assert alocacoes[0].atividade_id == "atv-early"
        assert alocacoes[1].atividade_id == "atv-late"

    def test_pool_dict_values_are_copies(self):
        """pool_dict should contain copies of original RecursoPool (model_copy)."""
        tid = "FUNC-F30"
        original_pool = RecursoPool(
            id="orig-id",
            tipo_id=tid,
            projeto_id="proj-X",
            quantidade_total=10,
            quantidade_disponivel=10,
        )
        canonical = _make_canonical(recurso_pool=[original_pool])
        tipos = {}
        alocacoes, pool_dict = _build_alocacoes_pool([], canonical, tipos)

        # Modifying pool_dict shouldn't affect original
        assert pool_dict[tid] is not original_pool
