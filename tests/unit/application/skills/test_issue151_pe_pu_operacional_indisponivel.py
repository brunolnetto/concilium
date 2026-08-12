"""Testes issue #151 (achado secundário) — VAL-PONTO-EQUILIBRIO-PU-INDISPONIVEL.

Contexto: no benchmark real investigado, `pu_operacional_unitario` veio `0.0` nas 6
linhas do Ponto de Equilíbrio, enquanto `custo_venda`/`pu_catalogo_unitario` vieram
corretamente populados. Investigação de código confirmou que, sob o pipeline ATUAL,
isso não pode ser causado por `Planejamento.quantitativo` divergir de
`subtotal.sem_bdi.total` — os dois derivam da MESMA variável `q`, num único
construtor (`_build_planejamento_entry`, skill-06 `_precificacao`,
`_planejamento_entry.py:29,35,60`): se `custo_venda_cpu` (via `subtotal.sem_bdi.total`)
é > 0, `quantitativo` também é, sob o código de hoje.

A causa mais provável é o registro persistido (`canonical.ponto_equilibrio`) ser
anterior à introdução do campo `pu_operacional_unitario` (ADR-162, commit `0bed4479`,
2026-08-05) — Pydantic preenche o default `0.0` para uma chave que nunca existiu no
JSON serializado. Não há bug de cálculo a corrigir; o gap real é que essa condição
era silenciosa (`pu_operacional_unitario=0.0` idêntico a "sem margem operacional").

Fix: `_validate_pe_pu_operacional_indisponivel` emite AVISO quando
`pu_operacional_unitario <= 0` e `custo_venda_cpu > 0` simultaneamente — torna a
condição visível em vez de se confundir com margem zero real.
"""

from __future__ import annotations

# Importação direta do helper — mesmo padrão dos demais testes deste diretório.
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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
_spec = importlib.util.spec_from_file_location("skill06_helpers_issue151_pu", _helpers_path)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
sys.modules["skill06_helpers_issue151_pu"] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_build_pe_for_equipe = _mod._build_pe_for_equipe
_validate_pe_pu_operacional_indisponivel = _mod._validate_pe_pu_operacional_indisponivel
_bpe_process_equipe = _mod._bpe_process_equipe


class _FakeSubtotalCat:
    def __init__(self, total: float, material: float = 0.0):
        self.total = total
        self.material = material


class _FakeSubtotal:
    def __init__(self, sem_bdi: float, com_bdi: float):
        self.sem_bdi = _FakeSubtotalCat(sem_bdi)
        self.com_bdi = _FakeSubtotalCat(com_bdi)


class _FakePlan:
    def __init__(self, item_id: str, qty: float, sem_bdi: float, com_bdi: float):
        self.item_id = item_id
        self.quantitativo = qty
        self.subtotal = _FakeSubtotal(sem_bdi, com_bdi)


def _make_equipe(item_id: str = "eap-01", custo_total: float = 700_000.0) -> Any:
    return SimpleNamespace(
        item_id=item_id,
        custo_fixo_mensal=100_000.0,
        permanencia_meses=6.0,
        permanencia_efetiva_meses=6.0,
        custo_total=custo_total,
        custo_total_autonomo=custo_total,
    )


class TestValidacaoPuOperacionalIndisponivel:
    def test_emite_aviso_quando_q_zero_e_venda_positiva(self):
        """plan.quantitativo=0 com custo_venda_cpu>0 → pu_operacional_unitario fica 0
        (Q<=0 no divisor) e o AVISO deve ser emitido."""
        eq = _make_equipe(custo_total=700_000.0)
        plan = _FakePlan("eap-01", qty=0.0, sem_bdi=575_000.0, com_bdi=660_000.0)
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000.0}, {"eap-01": plan})
        assert pe is not None
        assert pe.pu_operacional_unitario == 0.0
        validacoes: list = []
        _validate_pe_pu_operacional_indisponivel(pe, validacoes)
        assert any(v.codigo == "VAL-PONTO-EQUILIBRIO-PU-INDISPONIVEL" for v in validacoes)
        match = next(v for v in validacoes if v.codigo == "VAL-PONTO-EQUILIBRIO-PU-INDISPONIVEL")
        assert match.status == "AVISO"

    def test_nao_emite_quando_q_positivo(self):
        """Com quantitativo>0, pu_operacional_unitario resolve normalmente — sem aviso."""
        eq = _make_equipe(custo_total=700_000.0)
        plan = _FakePlan("eap-01", qty=1000.0, sem_bdi=575_000.0, com_bdi=660_000.0)
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000.0}, {"eap-01": plan})
        assert pe is not None
        assert pe.pu_operacional_unitario > 0.0
        validacoes: list = []
        _validate_pe_pu_operacional_indisponivel(pe, validacoes)
        assert not any(v.codigo == "VAL-PONTO-EQUILIBRIO-PU-INDISPONIVEL" for v in validacoes)

    def test_nao_emite_quando_venda_tambem_zero(self):
        """Sem venda (custo_venda_cpu<=0), nada para comparar — não emite (nada a
        diagnosticar; pu=0 é consistente com item sem preço de catálogo algum)."""
        eq = _make_equipe(custo_total=700_000.0)
        plan = _FakePlan("eap-01", qty=0.0, sem_bdi=0.0, com_bdi=0.0)
        pe = _build_pe_for_equipe(eq, {"eap-01": 0.0}, {"eap-01": plan})
        assert pe is not None
        assert pe.pu_operacional_unitario == 0.0
        validacoes: list = []
        _validate_pe_pu_operacional_indisponivel(pe, validacoes)
        assert not any(v.codigo == "VAL-PONTO-EQUILIBRIO-PU-INDISPONIVEL" for v in validacoes)

    def test_bpe_process_equipe_ja_dispara_a_validacao(self):
        """Integração: _bpe_process_equipe (chamado pelo pipeline real) já inclui a
        nova validação, sem precisar de chamada manual adicional."""
        eq = _make_equipe(custo_total=700_000.0)
        plan = _FakePlan("eap-01", qty=0.0, sem_bdi=575_000.0, com_bdi=660_000.0)
        validacoes: list = []
        pe = _bpe_process_equipe(eq, {"eap-01": 575_000.0}, validacoes, {"eap-01": plan})
        assert pe is not None
        assert any(v.codigo == "VAL-PONTO-EQUILIBRIO-PU-INDISPONIVEL" for v in validacoes)
