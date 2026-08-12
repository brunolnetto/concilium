"""Testes issue #151 — Ponto de Equilíbrio (ADR-162) somando material real.

Reproduz o padrão observado no benchmark real (projeto "Rodovia MT — Trecho
Cuiabá", via `consultar_ponto_equilibrio`): equipes de terraplenagem (material
≈ 0) reportavam corretamente `custo_operacional > custo_venda`, mas CBUQ
(material — CAP/ligante asfáltico — dominante) reportava `custo_operacional`
~30x menor que `custo_venda`, porque `custo_operacional_agregado` (ADR-172) só
soma MO+EQ+diesel — material nunca era somado em nenhuma etapa do pipeline
(`custo_material_mensal` fica sempre 0.0, ver NEP-029 D4, nunca implementado).

Fix: `_pe_resolve_material_real` soma `plan.subtotal.sem_bdi.material` (mesma
fonte de catálogo que já alimenta `custo_venda_total`) ao custo operacional
usado pelo PE, sem tocar a semântica global de `EquipeDireta.custo_operacional_agregado`
(outros consumidores — decomposição categorial de BDI — assumem MO+EQ+COMB
apenas e quebrariam com double-counting se o campo global mudasse).
"""

from __future__ import annotations

# Importação direta do helper — sem carregar a skill completa (mesmo padrão de
# test_adr076_pe_calibracao.py).
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

_helpers_path = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "src"
    / "concilium"
    / "application"
    / "skills"
    / "manifests"
    / "06-resultado-financeiro"
    / "_consolidacao"
    / "_skill_helpers"
    / "__init__.py"
)
_spec = importlib.util.spec_from_file_location("skill06_helpers_issue151", _helpers_path)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
sys.modules["skill06_helpers_issue151"] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_build_pe_for_equipe = _mod._build_pe_for_equipe


# ── fixtures / helpers ──────────────────────────────────────────────────────


class _FakeSubtotalCat:
    def __init__(self, total: float, material: float = 0.0):
        self.total = total
        self.material = material


class _FakeSubtotal:
    def __init__(self, sem_bdi: float, com_bdi: float, material_sem_bdi: float = 0.0):
        self.sem_bdi = _FakeSubtotalCat(sem_bdi, material_sem_bdi)
        self.com_bdi = _FakeSubtotalCat(com_bdi)


class _FakePlan:
    def __init__(
        self,
        item_id: str,
        qty: float,
        sem_bdi: float,
        com_bdi: float,
        material_sem_bdi: float = 0.0,
        produtividade_catalogo: float | None = None,
        beta_praticabilidade: float = 1.0,
    ):
        self.item_id = item_id
        self.quantitativo = qty
        self.subtotal = _FakeSubtotal(sem_bdi, com_bdi, material_sem_bdi)
        self.produtividade_catalogo = produtividade_catalogo
        self.beta_praticabilidade = beta_praticabilidade


def _make_equipe(
    item_id: str = "eap-cbuq",
    custo_fixo_mensal: float = 50_000.0,
    permanencia_meses: float = 4.0,
    permanencia_efetiva_meses: float = 4.0,
    custo_total: float = 336_272.51,  # mo+eq+diesel — material NÃO incluído (ADR-172)
    custo_total_autonomo: float = 336_272.51,
) -> Any:
    return SimpleNamespace(
        item_id=item_id,
        custo_fixo_mensal=custo_fixo_mensal,
        permanencia_meses=permanencia_meses,
        permanencia_efetiva_meses=permanencia_efetiva_meses,
        custo_total=custo_total,
        custo_total_autonomo=custo_total_autonomo,
    )


class TestMaterialRealSomadoAoOperacional:
    """Issue #151: material real soma-se ao custo operacional do PE."""

    def test_cbuq_material_dominante_delta_deixa_de_ser_artificial(self):
        """Reproduz o padrão do benchmark real: venda ~10,3M, operacional (sem material)
        ~336k — sem o fix, delta/margem seria ~10M (artificial). Com o fix, material
        (9,5M, a maior parcela do custo real do CBUQ) é somado ao operacional."""
        venda_sem_bdi = 10_348_400.59
        material_sem_bdi = 9_500_000.0
        eq = _make_equipe(custo_total=336_272.51, custo_total_autonomo=336_272.51)
        plan = _FakePlan(
            "eap-cbuq",
            qty=200_000.0,
            sem_bdi=venda_sem_bdi,
            com_bdi=venda_sem_bdi * 1.15,
            material_sem_bdi=material_sem_bdi,
        )
        pe = _build_pe_for_equipe(eq, {"eap-cbuq": venda_sem_bdi}, {"eap-cbuq": plan})
        assert pe is not None

        custo_operacional_esperado = 336_272.51 + material_sem_bdi  # 9_836_272.51
        delta_esperado = venda_sem_bdi - custo_operacional_esperado  # ~512_128

        assert pe.custo_fixo_equipe == pytest.approx(custo_operacional_esperado, abs=1)
        assert pe.delta == pytest.approx(delta_esperado, abs=1)
        # Sem o fix, delta seria venda - 336_272.51 ≈ 10_012_128 — a asserção acima já
        # falharia contra esse valor; reforça explicitamente que o bug não regride.
        delta_sem_fix_bugado = venda_sem_bdi - 336_272.51
        assert pe.delta != pytest.approx(delta_sem_fix_bugado, abs=1)
        # margem realista (~5%), não os ~97% que o bug produzia
        margem_pct = pe.delta / venda_sem_bdi
        assert 0.0 < margem_pct < 0.10

    def test_pu_operacional_unitario_inclui_material(self):
        """pu_operacional_unitario = custo_operacional_agregado(+material) / Q."""
        venda_sem_bdi = 10_348_400.59
        material_sem_bdi = 9_500_000.0
        qty = 200_000.0
        eq = _make_equipe(custo_total=336_272.51, custo_total_autonomo=336_272.51)
        plan = _FakePlan(
            "eap-cbuq", qty=qty, sem_bdi=venda_sem_bdi, com_bdi=venda_sem_bdi * 1.15, material_sem_bdi=material_sem_bdi
        )
        pe = _build_pe_for_equipe(eq, {"eap-cbuq": venda_sem_bdi}, {"eap-cbuq": plan})
        assert pe is not None

        esperado = (336_272.51 + material_sem_bdi) / qty
        assert pe.pu_operacional_unitario == pytest.approx(esperado, abs=0.01)

    def test_terraplenagem_sem_material_comportamento_inalterado(self):
        """Itens sem material (terraplenagem: escavação/aterro) não mudam — material=0
        (default) não altera delta/custo_fixo_equipe, preservando o comportamento
        pré-fix para o caso que já funcionava corretamente."""
        eq = _make_equipe(item_id="eap-terraplenagem", custo_total=4_108_307.91, custo_total_autonomo=4_108_307.91)
        plan = _FakePlan(
            "eap-terraplenagem", qty=400_000.0, sem_bdi=3_559_670.41, com_bdi=3_559_670.41 * 1.15, material_sem_bdi=0.0
        )
        pe = _build_pe_for_equipe(eq, {"eap-terraplenagem": 3_559_670.41}, {"eap-terraplenagem": plan})
        assert pe is not None
        assert pe.custo_fixo_equipe == pytest.approx(4_108_307.91, abs=1)
        assert pe.delta == pytest.approx(3_559_670.41 - 4_108_307.91, abs=1)
        assert pe.status_validacao == "ERRO"  # margem negativa, esperado para terraplenagem

    def test_plan_ausente_nao_quebra(self):
        """Sem planejamento_por_item (plan=None), material real resolve para 0 —
        não deve lançar exceção nem alterar o fallback pré-existente."""
        eq = _make_equipe(custo_total=700_000.0, custo_total_autonomo=600_000.0)
        pe = _build_pe_for_equipe(eq, {"eap-cbuq": 575_000})
        assert pe is not None
        assert pe.custo_fixo_equipe == pytest.approx(700_000.0, abs=1)

    def test_subtotal_none_nao_quebra(self):
        """plan.subtotal == None (campo opcional no modelo) — não deve lançar exceção."""
        eq = _make_equipe(custo_total=700_000.0, custo_total_autonomo=600_000.0)
        plan = SimpleNamespace(item_id="eap-cbuq", quantitativo=1000.0, subtotal=None)
        pe = _build_pe_for_equipe(eq, {"eap-cbuq": 575_000}, {"eap-cbuq": plan})
        assert pe is not None
        assert pe.custo_fixo_equipe == pytest.approx(700_000.0, abs=1)

    def test_subtotal_sem_bdi_none_nao_quebra(self):
        """plan.subtotal existe mas plan.subtotal.sem_bdi == None (distinto do caso acima,
        onde o próprio subtotal é None) — apontado pela review do Copilot no PR #152 como
        gap de cobertura real: o teste anterior com esse nome não montava esse cenário."""
        eq = _make_equipe(custo_total=700_000.0, custo_total_autonomo=600_000.0)
        plan = SimpleNamespace(
            item_id="eap-cbuq", quantitativo=1000.0, subtotal=SimpleNamespace(sem_bdi=None, com_bdi=None)
        )
        pe = _build_pe_for_equipe(eq, {"eap-cbuq": 575_000}, {"eap-cbuq": plan})
        assert pe is not None
        assert pe.custo_fixo_equipe == pytest.approx(700_000.0, abs=1)


_REGIME = SimpleNamespace(horas_dia=8.0, dias_semana=6.0)


def _sched_com_producao(num_equipes: float = 2.0, semanas: int = 10) -> SimpleNamespace:
    dist = {
        f"2026-W{i:02d}": SimpleNamespace(num_equipes=num_equipes, fator_clima=1.0, fator_calendario=1.0)
        for i in range(semanas)
    }
    return SimpleNamespace(distribuicao_semanal=dist)


class TestMaterialNaoVazaParaCausaDominante:
    """Review do Copilot no PR #152: `_pe_causa_dominante` (D1) e `_pe_horas_reais_min_max`
    (D3) dividem por H_i/H_cat pra obter as taxas TIME-DRIVEN γ_i^v/γ_i^o — material não
    escala com H_i (segue Q, não calendário). Antes do fix, `_bpe_extrair_e_processar_features`
    repassava `custo_venda_total`/`custo_operacional_agregado` (ambos JÁ com material) direto
    pra essas duas funções.

    Testar isso comparando `causa_dominante`/`delta` "com vs sem material" fim-a-fim exigiria
    fazer `venda_por_item` co-variar com o material de um jeito que não corresponde à wiring
    real (o valor de venda de um item não é responsabilidade deste código) — por isso este
    teste espiona a chamada real via `__globals__` (as duas funções são referenciadas por nome
    dentro do próprio módulo `_ponto_equilibrio.py`, não importadas em `_bpe_extrair_e_...`) e
    confirma que os argumentos recebidos já vêm com o material subtraído."""

    def _run_com_spy(self, plan: Any) -> tuple[Any, dict[str, float], dict[str, float]]:
        _globals = _mod._build_pe_for_equipe.__globals__
        original_causa_dominante = _globals["_pe_causa_dominante"]
        original_horas_reais = _globals["_pe_horas_reais_min_max"]
        captured_causa: dict[str, float] = {}
        captured_horas: dict[str, float] = {}

        def _spy_causa_dominante(plan_arg, venda, fixo, *rest, **kwargs):
            captured_causa["venda"] = venda
            captured_causa["fixo"] = fixo
            return original_causa_dominante(plan_arg, venda, fixo, *rest, **kwargs)

        def _spy_horas_reais(venda, teto_rs, fixo, *rest, **kwargs):
            captured_horas["venda"] = venda
            captured_horas["fixo"] = fixo
            return original_horas_reais(venda, teto_rs, fixo, *rest, **kwargs)

        eq = _make_equipe(item_id="eap-cbuq", custo_total=336_272.51, custo_total_autonomo=336_272.51)
        with patch.dict(
            _globals,
            {"_pe_causa_dominante": _spy_causa_dominante, "_pe_horas_reais_min_max": _spy_horas_reais},
        ):
            pe = _build_pe_for_equipe(
                eq,
                venda_por_item={"eap-cbuq": 10_348_400.59},
                planejamento_por_item={"eap-cbuq": plan},
                sched_por_item={"eap-cbuq": _sched_com_producao()},
                regime=_REGIME,
                teto_rs=1_000_000.0,
            )
        return pe, captured_causa, captured_horas

    def test_causa_dominante_recebe_venda_e_operacional_sem_material(self):
        venda_sem_bdi = 10_348_400.59
        material_sem_bdi = 9_500_000.0
        plan = _FakePlan(
            "eap-cbuq",
            qty=200_000.0,
            sem_bdi=venda_sem_bdi,
            com_bdi=venda_sem_bdi * 1.15,
            material_sem_bdi=material_sem_bdi,
            produtividade_catalogo=25.0,
        )
        pe, captured_causa, _ = self._run_com_spy(plan)
        assert pe is not None
        assert captured_causa, "esperava que _pe_causa_dominante fosse chamada (regime+produtividade presentes)"
        assert captured_causa["venda"] == pytest.approx(venda_sem_bdi - material_sem_bdi, abs=0.01)
        assert captured_causa["fixo"] == pytest.approx(336_272.51, abs=0.01)

    def test_horas_reais_min_max_recebe_venda_e_operacional_sem_material(self):
        venda_sem_bdi = 10_348_400.59
        material_sem_bdi = 9_500_000.0
        plan = _FakePlan(
            "eap-cbuq",
            qty=200_000.0,
            sem_bdi=venda_sem_bdi,
            com_bdi=venda_sem_bdi * 1.15,
            material_sem_bdi=material_sem_bdi,
            produtividade_catalogo=25.0,
        )
        pe, _, captured_horas = self._run_com_spy(plan)
        assert pe is not None
        assert captured_horas, "esperava que _pe_horas_reais_min_max fosse chamada (teto_rs configurado)"
        assert captured_horas["venda"] == pytest.approx(venda_sem_bdi - material_sem_bdi, abs=0.01)
        assert captured_horas["fixo"] == pytest.approx(336_272.51, abs=0.01)

    def test_sem_material_valores_ficam_inalterados(self):
        """material_sem_bdi=0.0 (caso já coberto por test_terraplenagem..., reforçado aqui
        no ponto de espionagem): venda/fixo repassados devem ser exatamente os originais."""
        venda_sem_bdi = 10_348_400.59
        plan = _FakePlan(
            "eap-cbuq",
            qty=200_000.0,
            sem_bdi=venda_sem_bdi,
            com_bdi=venda_sem_bdi * 1.15,
            material_sem_bdi=0.0,
            produtividade_catalogo=25.0,
        )
        pe, captured_causa, captured_horas = self._run_com_spy(plan)
        assert pe is not None
        assert captured_causa["venda"] == pytest.approx(venda_sem_bdi, abs=0.01)
        assert captured_causa["fixo"] == pytest.approx(336_272.51, abs=0.01)
        assert captured_horas["venda"] == pytest.approx(venda_sem_bdi, abs=0.01)
        assert captured_horas["fixo"] == pytest.approx(336_272.51, abs=0.01)
