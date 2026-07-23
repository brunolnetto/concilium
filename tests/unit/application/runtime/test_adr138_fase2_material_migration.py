"""ADR-138 Fase 2 (MATERIAL): migração de BOM real de `composicao_itens` para
`Producao.composicao_padrao_equipe.materiais` (`MaterialEquipe`, ADR-030 D2).

Contexto: 30 CPUs de `mendeslobo` têm linhas `composicao_itens` MATERIAL com BOM
real (cimento, areia, brita, tubos, emulsão, pavers) que hoje são dead data —
`_resolve_preco_cat_item` (NEP-032 D1) é winner-take-all: como a Fonte 1
(bottom-up via `composicao_padrao_equipe`) já resolve MAO_OBRA/EQUIPAMENTO para
essas CPUs, a Fonte 2 (`composicao_itens`) nunca é consultada — nem mesmo para
MATERIAL. Resultado: `preco_cat["material"] == 0.0` silenciosamente para essas
30 CPUs, apesar de haver BOM real e completo no catálogo.

A migração converte cada linha `composicao_itens` MATERIAL dessas 30 CPUs em uma
entrada `MaterialEquipe` na `Producao` referenciada, via:

    consumo_por_hora = coeficiente × Producao.valor_horario

`coeficiente` é quantidade por unidade de produto da CPU; `valor_horario` (ρ) é
unidades de produto por hora; o produto é quantidade por hora — exatamente a
definição de `MaterialEquipe.consumo_por_hora`. Isso é *price-preserving por
construção*: a Fonte 1 calcula `Σ(consumo_por_hora × preco_insumo) / valor_horario`;
substituindo a fórmula acima, isso se reduz a `Σ(coeficiente × preco_insumo)` —
exatamente o que a Fonte 2 (`_compute_preco_cat_from_cpu`) já calculava
diretamente a partir de `composicao_itens`. Ver ADR-138 (Fase 2) para o
levantamento completo e a lista das 30 CPUs.

Os 40 CPUs com o placeholder sintético `MA-AGIS-CPU-<codigo>` (preço = preço
legado da própria CPU, não material real) são deliberadamente EXCLUÍDOS desta
migração — ver ADR-138 Fase 2 / nota de exclusão.

Dois níveis de teste:
  1. `TestFormulaPriceLoserving` — prova algébrica/determinística da fórmula
     com um catálogo sintético mínimo (mesma forma do exemplo concreto do ADR:
     28 sacos de cimento por poço, valor_horario=0.25 poço/h -> 7.0 sacos/h).
  2. `TestMigracaoDados30Cpus` — roda o pipeline real (`run_precificacao_unitaria`)
     sobre o catálogo `mendeslobo` de verdade e verifica, para as 30 CPUs, que o
     preço de MATERIAL bate com o valor pré-computado via Fonte 2
     (`_compute_preco_cat_from_cpu`) antes da migração (tolerância 1e-4
     relativa) — a garantia dura de "price-preserving" exigida pelo ADR.
     Antes da migração de dado, este teste falha (material fica 0.0); depois,
     passa (material vem da Fonte 1, `VAL-PLAN-BOTTOM-UP`).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from concilium.application.runtime import Runtime
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

# Valores de MATERIAL pré-computados pela Fonte 2 (`_compute_preco_cat_from_cpu`)
# diretamente a partir de `composicao_itens`, ANTES da migração de dado — usados
# como alvo de verificação price-preserving (ADR-138 Fase 2). Fonte: investigação
# prévia (script de quantificação de gap), re-verificada nesta sessão.
_MATERIAL_ESPERADO_30_CPUS: dict[str, float] = {
    "CPU-DIVER-ATI-063": 125.0,
    "CPU-DIVER-ATI-064": 63.21,
    "CPU-DIVER-ATI-069": 8.29,
    "CPU-DIVER-ATI-071": 125.0,
    "CPU-DIVER-ATI-072": 63.21,
    "CPU-OBRAS-ATI-025": 249.5,
    "CPU-OBRAS-ATI-026": 299.5,
    "CPU-OBRAS-ATI-027": 299.5,
    "CPU-OBRAS-ATI-028": 331.5,
    "CPU-OBRAS-ATI-029": 249.5,
    "CPU-OBRAS-ATI-030": 299.5,
    "CPU-OBRAS-ATI-031": 299.5,
    "CPU-OBRAS-ATI-032": 299.5,
    "CPU-PAVIM-ATI-053": 85.000015,
    "CPU-PAVIM-ATI-054": 85.000015,
    "CPU-PAVIM-ATI-055": 85.00001999999999,
    "CPU-PAVIM-ATI-056": 3.08,
    "CPU-PAVIM-ATI-057": 1.5015,
    # ADR-139 F4 (cura AGIS + consolidação de agregados): ATI-058/061 consumiam massa
    # asfáltica (72 kg/m²) a preço de CAP puro (R$ 5.300/t) — material 381,60/m² era
    # ~10× o real. Repontadas para MA-CBUQ-FAIXA-C (massa usinada gerada; preço
    # re-concluído na base de cotações da empresa: R$ 466,30/t): 0,072 t/m² × 466,30.
    "CPU-PAVIM-ATI-058": 33.5736,
    "CPU-PAVIM-ATI-059": 147.0,
    "CPU-PAVIM-ATI-061": 33.5736,
    "CPU-PAVIM-ATI-062": 3.85,
    # ADR-139 F4: preço do MA-BGTC-MIX é concluído por composição de usinagem
    # (92,50 → 245,63/m³ na base de cotações da empresa, PROD-USINAGEM-BGTC-001);
    # o snapshot pré-migração (97,125 = 1,05 × 92,50) ficou obsoleto por mudança
    # INTENCIONAL de preço — o mecanismo price-preserving da migração segue provado
    # pelas outras 29 CPUs.
    "CPU-PAVIM-PAV-BASE-BGTC": 257.9115,  # = 23,1 m³/h × 245,63 ÷ 22 m³/h
    "CPU-SANEA-DREN-MAN-DN300": 110.46000000000001,
    "CPU-SANEA-POCO-VISITA-PADRAO": 1387.6000000000001,
    "CPU-TERRA-ATI-019": 360.05,
    "CPU-TERRA-ATI-020": 165.0,
    "CPU-TERRA-ATI-022": 147.0,
    # ADR-139 F4 (cura AGIS + consolidação): duplicata MA-BRITA-GRADUADA (360,05)
    # consolidada no MA-BGTC-MIX gerado pela usinagem (re-concluído a 245,63/m³ na
    # base de cotações da empresa).
    "CPU-TERRA-ATI-023": 245.63,
    "CPU-TERRA-ATI-024": 165.0,
}

_REL_TOL = 1e-4


def _canonical(cpu_id: str, unidade: str = "un", quantitativo: float = 1.0) -> CanonicalModel:
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
    eap = [EapItem(item_id="i1", ordem=1, cpu_id=cpu_id, descricao="Item", unidade=unidade, quantitativo=quantitativo)]
    return CanonicalModel(meta=meta, projeto=projeto, eap=eap)


class TestFormulaPriceLoserving:
    """Prova determinística: consumo_por_hora = coeficiente × valor_horario é price-preserving.

    Mesmo exemplo concreto do ADR-138: poço de visita, 28 sacos de cimento por
    poço, valor_horario=0.25 poço/h -> consumo_por_hora=7.0 sacos/h. Com um
    catálogo mínimo onde a Fonte 1 (bottom-up) resolve via MaterialEquipe (sem
    nenhuma linha MATERIAL em composicao_itens), o preço de MATERIAL deve bater
    exatamente com coeficiente × preco_insumo (o que a Fonte 2 teria calculado
    diretamente do dado não migrado).
    """

    def _catalogo(self, *, materiais: list[dict], composicao_itens: list[dict]) -> dict:
        return {
            "cpus": [
                {
                    "codigo": "CPU-FORMULA",
                    "descricao": "CPU teste fórmula",
                    "unidade": "un",
                    "origem": "PROPRIA",
                    "categoria": "SANEAMENTO",
                    "producao_id_ref": "PROD-FORMULA",
                    "composicao_itens": composicao_itens,
                }
            ],
            "insumos": [
                {"codigo": "MO-OFICIAL", "unidade": "h", "preco_unitario": 15.0},
                {"codigo": "MA-CIMENTO-CPII-50KG", "unidade": "saco", "preco_unitario": 38.5},
            ],
            "produtividades": [
                {
                    "id": "PROD-FORMULA",
                    "valor_horario": 0.25,
                    "composicao_padrao_equipe": {
                        "funcoes": [{"funcao_id": "MO-OFICIAL", "num_pessoas": 1}],
                        "equipamentos": [],
                        "materiais": materiais,
                    },
                }
            ],
        }

    def test_consumo_por_hora_igual_coeficiente_vezes_valor_horario_preserva_preco(self):
        coeficiente = 28.0
        valor_horario = 0.25
        preco_insumo = 38.5
        consumo_por_hora = coeficiente * valor_horario
        assert consumo_por_hora == pytest.approx(7.0)

        # Fonte 1 (bottom-up) via MaterialEquipe migrada — composicao_itens SEM MATERIAL.
        catalogo_migrado = self._catalogo(
            materiais=[
                {
                    "insumo_id": "MA-CIMENTO-CPII-50KG",
                    "consumo_por_hora": consumo_por_hora,
                    "unidade": "saco",
                }
            ],
            composicao_itens=[],
        )
        res = run_precificacao_unitaria(self._canonical(), {}, catalogo_migrado, {})
        assert len(res.canonical.planejamento) == 1
        item = res.canonical.planejamento[0]
        codigos = {v.codigo for v in res.validacoes}
        assert "VAL-PLAN-BOTTOM-UP" in codigos

        preco_material_fonte1 = item.preco_unitario.material
        preco_material_esperado = coeficiente * preco_insumo  # o que a Fonte 2 calcularia direto do dado antigo
        assert preco_material_fonte1 == pytest.approx(preco_material_esperado, rel=_REL_TOL)

    def _canonical(self) -> CanonicalModel:
        return _canonical("CPU-FORMULA")


class TestMigracaoDados30Cpus:
    """Roda o pipeline real sobre `config/catalogos/mendeslobo` (dado de produção).

    ANTES da migração de dado (Fase 2): material == 0.0 para as 30 CPUs (Fonte 1
    resolve MAO_OBRA/EQUIPAMENTO e nunca consulta composicao_itens para MATERIAL).
    DEPOIS: material bate com o valor pré-computado da Fonte 2 (tolerância 1e-4
    relativa) e VAL-PLAN-BOTTOM-UP é emitida (preço integralmente Fonte 1).
    """

    @pytest.fixture(scope="class")
    def catalogo_mendeslobo(self, config_root) -> dict:
        rt = Runtime(config_root)
        return rt.load_catalogo("mendeslobo")

    @pytest.mark.parametrize("cpu_id", sorted(_MATERIAL_ESPERADO_30_CPUS))
    def test_material_migrado_bate_com_fonte2_price_preserving(self, catalogo_mendeslobo, cpu_id):
        canonical = _canonical(cpu_id)
        res = run_precificacao_unitaria(canonical, {}, catalogo_mendeslobo, {})

        assert len(res.canonical.planejamento) == 1, (
            f"{cpu_id}: item não precificado — validacoes={[v.codigo for v in res.validacoes]}"
        )
        item = res.canonical.planejamento[0]
        codigos = {v.codigo for v in res.validacoes}
        assert "VAL-PLAN-BOTTOM-UP" in codigos, f"{cpu_id}: esperado Fonte 1 (bottom-up), validacoes={codigos}"

        esperado = _MATERIAL_ESPERADO_30_CPUS[cpu_id]
        obtido = item.preco_unitario.material
        assert obtido == pytest.approx(esperado, rel=_REL_TOL), (
            f"{cpu_id}: material={obtido} != esperado(Fonte 2 pré-migração)={esperado}"
        )

    def test_agis_placeholder_cpus_permanecem_intocadas(self, catalogo_mendeslobo):
        """CPU-DREN-CORPO-BTCC-100 (placeholder MA-AGIS-CPU-*) NÃO é migrada — fora de escopo."""
        cpu = next(c for c in catalogo_mendeslobo["cpus"] if c["codigo"] == "CPU-DREN-CORPO-BTCC-100")
        mat_rows = [ci for ci in cpu.get("composicao_itens", []) if ci.get("categoria_custo") == "MATERIAL"]
        assert mat_rows, "CPU-DREN-CORPO-BTCC-100 deveria manter sua linha MATERIAL (placeholder AGIS) intocada"
        assert all(str(m["insumo_id"]).startswith("MA-AGIS-CPU-") for m in mat_rows)
