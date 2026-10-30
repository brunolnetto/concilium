"""ADR-128 F6 — Contabilização canônica de consumíveis (paridade com pool), fim a fim.

Reusa os mesmos 4 cenários de `test_adr128_f5_skill04_consumiveis.py` (fixtures
duplicadas deliberadamente — arquivo irmão, sem tocar no arquivo já fechado do F5),
verificando agora que `CanonicalModel.recursos_consumiveis`/`resumo_estoque_consumiveis`
são persistidos corretamente através de `run_cronograma`.
"""

from __future__ import annotations

from datetime import date, timedelta

from concilium.application.skills import run_cronograma, run_escopo_e_eap

_INSUMO_DIESEL = "MA-DIESEL-TESTE"


def _catalogo(consumo_por_hora: float, disponibilidade: dict | None = None) -> dict:
    insumo: dict = {
        "codigo": _INSUMO_DIESEL,
        "tipo": "MATERIAL",
        "descricao": "Diesel de teste",
        "unidade": "l",
        "preco_unitario": 6.5,
        "fonte_preco": "cotacao_mercado",
        "origem_material": "AQUISICAO_EXTERNA",
    }
    if disponibilidade is not None:
        insumo["atributos_especificos"] = {"disponibilidade": disponibilidade}

    return {
        "cpus": [{"codigo": "CPU-01", "descricao": "CPU teste", "producao_id_ref": "PROD-01"}],
        "produtividades": [
            {
                "id": "PROD-01",
                "codigo": "PROD-01",
                "descricao": "Producao teste",
                "producao_horaria": 50.0,
                "unidade": "m3",
                "composicao_padrao_equipe": {
                    "equipamentos": [{"equip_id": "EQ-X", "num_unidades": 1}],
                    "materiais": [{"insumo_id": _INSUMO_DIESEL, "consumo_por_hora": consumo_por_hora}],
                },
            }
        ],
        "insumos": [insumo],
    }


def _canonical():
    inputs = {
        "nome": "Teste F6 Diesel",
        "tipo_obra": "terraplenagem",
        "localizacao": "Test, CE",
        "coordenadas": {"lat": -4.0, "lng": -38.0},
        "regime_trabalho": {"dias_semana": 5, "horas_dia": 8},
        "data_inicio": "2026-06-01",
        "data_termino": (date(2026, 6, 1) + timedelta(days=90)).isoformat(),
        "eap": [
            {
                "item_id": "eap-01",
                "ordem": 1,
                "cpu_id": "CPU-01",
                "descricao": "Item único",
                "unidade": "m3",
                "quantitativo": 1000.0,
            }
        ],
        "contexto_id": "test",
        "snapshot_catalogo_id": "snap-cat",
        "snapshot_perfil_id": "snap-perfil",
    }
    return run_escopo_e_eap(None, inputs, catalogo=None).canonical


_RCPSP_SPEC = {
    "activities": [
        {"item_id": "eap-01", "descricao": "Item único", "duration_weeks": 1, "required_resources": {"EQ-X": 1}},
    ],
    "resource_pool": {"EQ-X": 1},
    "precedence": [],
    "deadline_weeks": 8,
}


class TestPersistenciaZeroRegressao:
    def test_sem_config_nenhuma_listas_vazias(self):
        canonical = _canonical()
        catalogo = _catalogo(consumo_por_hora=1.0)
        result = run_cronograma(canonical, {"rcpsp_spec": dict(_RCPSP_SPEC)}, catalogo=catalogo)

        assert result.canonical.recursos_consumiveis == []
        assert result.canonical.resumo_estoque_consumiveis == []

    def test_catalogo_apenas_status_ok(self):
        canonical = _canonical()
        catalogo = _catalogo(consumo_por_hora=1.0, disponibilidade={"estoque_inicial": 100000.0})
        result = run_cronograma(canonical, {"rcpsp_spec": dict(_RCPSP_SPEC)}, catalogo=catalogo)

        assert result.canonical.cronograma is not None, "\n".join(
            f"{v.codigo} [{v.status}]: {v.mensagem}" for v in result.validacoes
        )
        assert len(result.canonical.recursos_consumiveis) == 1
        recurso = result.canonical.recursos_consumiveis[0]
        assert recurso.resource_id == _INSUMO_DIESEL
        assert recurso.disponibilidade.estoque_inicial == 100000.0
        assert recurso.consumo_por_semana == {"eap-01": 40.0}  # 1.0 l/h × 40h/sem

        assert len(result.canonical.resumo_estoque_consumiveis) == 1
        resumo = result.canonical.resumo_estoque_consumiveis[0]
        assert resumo.resource_id == _INSUMO_DIESEL
        assert resumo.status_estoque == "OK"
        assert resumo.delay_total_semanas == 0
        assert resumo.n_atividades_atrasadas == 0
        assert resumo.overflow_total == 0.0
        assert resumo.estoque_minimo >= 0


class TestPersistenciaAtrasoCausal:
    def test_atraso_reparavel_status_aviso(self):
        canonical = _canonical()
        catalogo = _catalogo(consumo_por_hora=1.0)
        inputs = {
            "rcpsp_spec": dict(_RCPSP_SPEC),
            "logistica_consumiveis": {_INSUMO_DIESEL: {"estoque_inicial": 0.0, "taxa_reabastecimento_max": 10.0}},
        }
        result = run_cronograma(canonical, inputs, catalogo=catalogo)

        assert result.canonical.cronograma is not None, "\n".join(
            f"{v.codigo} [{v.status}]: {v.mensagem}" for v in result.validacoes
        )
        assert len(result.canonical.resumo_estoque_consumiveis) == 1
        resumo = result.canonical.resumo_estoque_consumiveis[0]
        assert resumo.status_estoque == "AVISO"
        assert resumo.delay_total_semanas == 3
        assert resumo.n_atividades_atrasadas == 1
        # Cronograma final (pós-reparo) não deve mais ter estoque negativo.
        assert resumo.estoque_minimo >= 0


class TestPersistenciaInfeasibilidade:
    def test_estoque_irreparavel_nao_persiste_contabilizacao(self):
        """Skill-04 já tinha o contrato "cronograma inviável -> nenhum canonical
        mutado" (VAL-SCHED-05, ver test_02_auto_infeasivel_quando_tudo_falha) antes do
        F5/F6 — infeasibilidade retorna cedo (`failed=True`) e nunca chega ao ponto
        onde `recursos_consumiveis`/`resumo_estoque_consumiveis` seriam calculados.
        O status CRITICO da regra de _build_resumo_estoque é real e coberto por teste
        unitário direto (test_adr128_f6_estoque_consumivel_builder.py), mas não é
        observável end-to-end aqui — mesma limitação estrutural que já existia para
        `cronograma` em qualquer cronograma inviável, não uma lacuna nova do F6."""
        canonical = _canonical()
        catalogo = _catalogo(consumo_por_hora=1.0)
        inputs = {
            "rcpsp_spec": dict(_RCPSP_SPEC),
            "logistica_consumiveis": {_INSUMO_DIESEL: {"estoque_inicial": 0.0, "taxa_reabastecimento_max": 0.0}},
        }
        result = run_cronograma(canonical, inputs, catalogo=catalogo)

        assert result.canonical.cronograma is None
        assert result.canonical.recursos_consumiveis == []
        assert result.canonical.resumo_estoque_consumiveis == []
        assert any(v.codigo == "VAL-ESTOQUE-DELAY-02" and v.status == "ERRO" for v in result.validacoes)
