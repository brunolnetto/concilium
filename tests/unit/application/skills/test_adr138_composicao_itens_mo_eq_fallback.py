"""ADR-138: composicao_itens restrito a MATERIAL/DIESEL — fail loud no fallback.

Antes do ADR-138, `composicao_itens` podia conter linhas MAO_OBRA/EQUIPAMENTO
redundantes com `Producao.composicao_padrao_equipe`. O censo do catálogo mostrou
que essas linhas nunca são a fonte real de preço em `mendeslobo`/`rfi-r02`
(Fonte 1 — bottom-up via produção — sempre resolve primeiro nesses dois
catálogos). O ADR-138 remove essas linhas dos catálogos de produção
(`mendeslobo`/`rfi-r02` — NÃO `samples`/`test`, ver ADR-138 §P5/§D4/§D6).

Isso expõe um bug pré-existente no Fonte 2 (`_preco_cat_fallback_composicao`):
se o fallback for realmente acionado (Fonte 1 falhou) e `composicao_itens` não
tiver NENHUMA linha MAO_OBRA nem EQUIPAMENTO, o cálculo retorna silenciosamente
`mao_obra=0.0`/`equipamentos=0.0` — um preço sem nenhuma cobertura dessas
categorias, apresentado como correto.

Estes testes cobrem o comportamento corrigido: "falha alto, não corrompe"
(mesma filosofia de CatalogUpdater/atualizar_capacidade_gargalo) — quando o
fallback não tem NENHUMA fonte (nem MAO_OBRA, nem EQUIPAMENTO), emite
VAL-PLAN-MO-EQ-SEM-FONTE (ERRO) e não precifica o item (equivalente a
preco_cat=None), em vez de retornar um dict incompleto disfarçado de completo.

O gate é deliberadamente uma condição "E", não "OU": ter apenas uma das duas
categorias (MAO_OBRA presente sem EQUIPAMENTO, ou vice-versa) NÃO dispara o
ERRO — são cenários legítimos já cobertos pelo restante do sistema:
  - EQUIPAMENTO presente sem MAO_OBRA: mecanismo pré-existente VAL-EQUIP-DECOMP
    (ADR-023 §D3) já assume que o rate do equipamento pode embutir o operador
    e emite um AVISO deliberado, não bloqueia — ver
    tests/unit/test_adr023_bdi_diferenciado.py::TestSkill04EquipamentoDecomp.
  - MAO_OBRA presente sem EQUIPAMENTO: atividade legitimamente sem máquina
    (ex.: serviço 100% manual).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from concilium.application.skills import load_skill_stage
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    EapItem,
    Meta,
    Projeto,
    RegimeTrabalho,
)

run_precificacao_unitaria = load_skill_stage("06-resultado-financeiro", "_precificacao", "run_precificacao_unitaria")


def _canonical(cpu_id: str = "CPU-Y", quantitativo: float = 10.0) -> CanonicalModel:
    meta = Meta(gerado_em=datetime.now(UTC), contexto_id="test")
    projeto = Projeto(
        id="p1",
        nome="Projeto Teste",
        tipo_obra="terraplenagem",
        localizacao="BR",
        coordenadas=Coordenadas(lat=0, lng=0),
        regime_trabalho=RegimeTrabalho(dias_semana=6, horas_dia=8),
        data_inicio="2026-01-01",
        data_termino="2026-12-31",
        snapshot_catalogo_id="cat",
        snapshot_perfil_id="perf",
    )
    eap = [EapItem(item_id="i1", ordem=1, cpu_id=cpu_id, descricao="Item", unidade="m3", quantitativo=quantitativo)]
    return CanonicalModel(meta=meta, projeto=projeto, eap=eap)


def _catalogo(composicao_itens: list[dict], insumos_extra: list[dict] | None = None) -> dict:
    """Catálogo com Fonte 1 sempre falhando (producao_horaria=0) — força Fonte 2."""
    return {
        "cpus": [
            {
                "codigo": "CPU-Y",
                "descricao": "CPU teste",
                "unidade": "m3",
                "origem": "REFERENCIA",
                "categoria": "TERRAPLENAGEM",
                "producao_id_ref": "P-Y",
                "composicao_itens": composicao_itens,
            }
        ],
        "insumos": [
            {"codigo": "MAT-1", "unidade": "m3", "preco_unitario": 10.0},
            {"codigo": "MO-1", "unidade": "h", "preco_unitario": 5.0},
            {"codigo": "EQ-1", "unidade": "h", "preco_unitario": 20.0},
            *(insumos_extra or []),
        ],
        # Fonte 1 (bottom-up) deve falhar: producao_horaria=0 -> _resolve_producao_valida retorna None.
        "produtividades": [{"id": "P-Y", "producao_horaria": 0.0}],
    }


def _codigos(validacoes) -> set[str]:
    return {v.codigo for v in validacoes}


class TestFallbackFailsLoudSemMaoObraNemEquipamento:
    def test_falha_quando_composicao_itens_nao_tem_mao_obra_nem_equipamento(self):
        """Só MATERIAL em composicao_itens + Fonte 1 falha -> ERRO, item não precificado."""
        canonical = _canonical()
        catalogo = _catalogo([{"insumo_id": "MAT-1", "categoria_custo": "MATERIAL", "coeficiente": 1.0}])

        res = run_precificacao_unitaria(canonical, {}, catalogo, {})

        assert res.canonical.planejamento == []
        codigos = _codigos(res.validacoes)
        assert "VAL-PLAN-MO-EQ-SEM-FONTE" in codigos
        erro = next(v for v in res.validacoes if v.codigo == "VAL-PLAN-MO-EQ-SEM-FONTE")
        assert erro.status == "ERRO"

    def test_sucesso_quando_falta_apenas_mao_obra(self):
        """EQUIPAMENTO presente sem MAO_OBRA -> NÃO é ERRO (coberto por VAL-EQUIP-DECOMP, ADR-023)."""
        canonical = _canonical()
        catalogo = _catalogo(
            [
                {"insumo_id": "MAT-1", "categoria_custo": "MATERIAL", "coeficiente": 1.0},
                {"insumo_id": "EQ-1", "categoria_custo": "EQUIPAMENTO", "coeficiente": 1.0},
            ]
        )

        res = run_precificacao_unitaria(canonical, {}, catalogo, {})

        assert len(res.canonical.planejamento) == 1
        codigos = _codigos(res.validacoes)
        assert "VAL-PLAN-MO-EQ-SEM-FONTE" not in codigos
        assert "VAL-EQUIP-DECOMP" in codigos  # equipamento sem decomposicao_equip -> AVISO, não bloqueia
        item = res.canonical.planejamento[0]
        assert item.preco_unitario.mao_obra == pytest.approx(0.0)
        assert item.preco_unitario.equipamentos == pytest.approx(20.0)

    def test_sucesso_quando_falta_apenas_equipamento(self):
        """MAO_OBRA presente sem EQUIPAMENTO -> NÃO é ERRO (atividade legitimamente sem máquina)."""
        canonical = _canonical()
        catalogo = _catalogo(
            [
                {"insumo_id": "MAT-1", "categoria_custo": "MATERIAL", "coeficiente": 1.0},
                {"insumo_id": "MO-1", "categoria_custo": "MAO_OBRA", "coeficiente": 1.0},
            ]
        )

        res = run_precificacao_unitaria(canonical, {}, catalogo, {})

        assert len(res.canonical.planejamento) == 1
        codigos = _codigos(res.validacoes)
        assert "VAL-PLAN-MO-EQ-SEM-FONTE" not in codigos
        item = res.canonical.planejamento[0]
        assert item.preco_unitario.mao_obra == pytest.approx(5.0)
        assert item.preco_unitario.equipamentos == pytest.approx(0.0)

    def test_sucesso_quando_mao_obra_e_equipamento_presentes(self):
        """Com as duas categorias presentes, o fallback funciona normalmente (comportamento preservado)."""
        canonical = _canonical()
        catalogo = _catalogo(
            [
                {"insumo_id": "MAT-1", "categoria_custo": "MATERIAL", "coeficiente": 1.0},
                {"insumo_id": "MO-1", "categoria_custo": "MAO_OBRA", "coeficiente": 1.0},
                {"insumo_id": "EQ-1", "categoria_custo": "EQUIPAMENTO", "coeficiente": 1.0},
            ]
        )

        res = run_precificacao_unitaria(canonical, {}, catalogo, {})

        assert len(res.canonical.planejamento) == 1
        codigos = _codigos(res.validacoes)
        assert "VAL-PLAN-MO-EQ-SEM-FONTE" not in codigos
        assert "VAL-PLAN-COMPOSICAO-FALLBACK" in codigos
        item = res.canonical.planejamento[0]
        # MAT-1: 1.0 × 10.0 = 10 | MO-1: 1.0 × 5.0 = 5 | EQ-1: 1.0 × 20.0 = 20 -> total 35 por unidade × 10 qtd
        assert item.subtotal.sem_bdi.total == pytest.approx(350.0)
