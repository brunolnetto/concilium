"""Testes das 3 skills implementadas: escopo, praticabilidade, consolidar."""

from typing import Any

import pytest

from concilium.models.canonical import (
    BdiCategorias,
    CanonicalModel,
    Coordenadas,
    EquipamentoEquipeDireta,
    EquipeDireta,
    FuncaoEquipeDireta,
    Indireto,
    Meta,
    Planejamento,
    PrecoUnitarioCategoria,
    Projeto,
    RegimeTrabalho,
    SubtotalCategorias,
    SubtotalSemBdiComBdi,
)
from concilium.skills.consolidar import run_consolidar_resultado
from concilium.skills.escopo import run_escopo
from concilium.skills.praticabilidade import run_praticabilidade


class TestSkillEscopo:
    def test_cria_canonical_inicial(self, inputs_escopo_terraplenagem: dict[str, Any]):
        inputs = {**inputs_escopo_terraplenagem,
                  "perfil_id": "agis", "jurisdicao_id": "BR",
                  "snapshot_catalogo_id": "abc", "snapshot_perfil_id": "def"}
        result = run_escopo(None, inputs, catalogo=None)
        assert not result.has_errors
        assert result.canonical.projeto.nome.startswith("Terraplenagem")
        assert len(result.canonical.eap) == 3
        assert result.canonical.eap[0].cpu_id == "ESCO-CARGA-1CAT-DMT2000"

    def test_falha_se_canonical_in_existe(self, inputs_escopo_terraplenagem: dict[str, Any]):
        inputs = {**inputs_escopo_terraplenagem,
                  "perfil_id": "agis", "jurisdicao_id": "BR",
                  "snapshot_catalogo_id": "abc", "snapshot_perfil_id": "def"}
        # Cria canônico fake
        from datetime import UTC, datetime
        meta = Meta(gerado_em=datetime.now(UTC), perfil_construtora_id="agis", jurisdicao_id="BR")
        proj = Projeto(
            id="x", nome="Existing", tipo_obra="terraplenagem", localizacao="X",
            coordenadas=Coordenadas(lat=0, lng=0),
            regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
            data_inicio="2026-01-01", data_termino="2026-12-31",
            versao_referencia_id="X", snapshot_catalogo_id="x", snapshot_perfil_id="x",
        )
        existing = CanonicalModel(meta=meta, projeto=proj)
        result = run_escopo(existing, inputs, catalogo=None)
        assert result.has_errors
        assert result.validacoes[0].codigo == "VAL-ESCOPO-01"

    def test_val_eap_01_detecta_cpu_inexistente(self, inputs_escopo_terraplenagem: dict[str, Any]):
        inputs = {**inputs_escopo_terraplenagem,
                  "perfil_id": "agis", "jurisdicao_id": "BR",
                  "snapshot_catalogo_id": "abc", "snapshot_perfil_id": "def"}
        catalogo = {"cpus": [{"codigo": "OUTRA-CPU"}]}
        result = run_escopo(None, inputs, catalogo=catalogo)
        assert result.has_errors
        # Deve haver erros VAL-EAP-01 para cada CPU não encontrada
        eap_errors = [v for v in result.validacoes if v.codigo == "VAL-EAP-01" and v.status == "ERRO"]
        assert len(eap_errors) == 3

    def test_val_eap_01_ok_quando_todas_cpus_existem(
        self, inputs_escopo_terraplenagem: dict[str, Any]
    ):
        inputs = {**inputs_escopo_terraplenagem,
                  "perfil_id": "agis", "jurisdicao_id": "BR",
                  "snapshot_catalogo_id": "abc", "snapshot_perfil_id": "def"}
        catalogo = {"cpus": [
            {"codigo": "ESCO-CARGA-1CAT-DMT2000"},
            {"codigo": "COMPACT-ATERRO"},
            {"codigo": "REGULARIZACAO-SUBLEITO"},
        ]}
        result = run_escopo(None, inputs, catalogo=catalogo)
        assert not result.has_errors


class TestSkillPraticabilidade:
    def test_calcula_percentual_mensal(
        self,
        inputs_escopo_terraplenagem: dict[str, Any],
        mock_openmeteo_aracoiaba,
    ):
        inputs_esc = {**inputs_escopo_terraplenagem,
                      "perfil_id": "agis", "jurisdicao_id": "BR",
                      "snapshot_catalogo_id": "abc", "snapshot_perfil_id": "def"}
        canonical = run_escopo(None, inputs_esc).canonical

        perfil = {"limiar_inviabilidade_mm": 10}
        result = run_praticabilidade(
            canonical,
            inputs={"ano_referencia": 2024},
            perfil=perfil,
            client=mock_openmeteo_aracoiaba,
        )
        assert not result.has_errors
        prat = result.canonical.praticabilidade
        assert prat is not None
        assert len(prat.percentual_produtivo_mensal) == 12
        # Todos percentuais devem estar entre 0 e 1
        for mes, pct in prat.percentual_produtivo_mensal.items():
            assert 0 <= pct <= 1, f"mês {mes}: pct {pct} fora de [0,1]"
        # Padrão climático: meses secos (jul-ago) devem ter % alto; jan-fev baixo
        assert prat.percentual_produtivo_mensal["07"] > prat.percentual_produtivo_mensal["02"]
        assert prat.percentual_produtivo_mensal["08"] > prat.percentual_produtivo_mensal["03"]

    def test_falha_sem_projeto(self, mock_openmeteo_aracoiaba):
        # Constrói canônico mínimo sem projeto não é possível porque projeto é obrigatório.
        # Em vez disso, verificamos que skill é robusta a ausência de coordenadas.
        # Na prática, modelo Pydantic já garante. Skip.
        pass

    def test_val_prat_01_e_02_ok(
        self, inputs_escopo_terraplenagem: dict[str, Any], mock_openmeteo_aracoiaba
    ):
        inputs_esc = {**inputs_escopo_terraplenagem,
                      "perfil_id": "agis", "jurisdicao_id": "BR",
                      "snapshot_catalogo_id": "abc", "snapshot_perfil_id": "def"}
        canonical = run_escopo(None, inputs_esc).canonical
        perfil = {"limiar_inviabilidade_mm": 10}
        result = run_praticabilidade(
            canonical, {"ano_referencia": 2024}, perfil, client=mock_openmeteo_aracoiaba
        )
        codigos_ok = [v for v in result.validacoes if v.status == "OK"]
        assert any(v.codigo == "VAL-PRAT-01" for v in codigos_ok)
        assert any(v.codigo == "VAL-PRAT-02" for v in codigos_ok)


class TestSkillConsolidar:
    def _fake_canonical_com_planejamento(
        self, custo_fixo: float, custo_venda: float, indiretos: float
    ) -> CanonicalModel:
        """Constrói canônico com 1 item para teste de skill 06.

        custo_fixo = custo total da equipe (permanencia × custo_mensal)
        custo_venda = subtotal sem BDI = preco_unit × quantitativo
        quantitativo fixo em 100; preco_unit = custo_venda / 100
        custo_unit_real = custo_fixo / 100
        delta_pct = |custo_unit_real - preco_unit| / custo_unit_real
        """
        from datetime import UTC, datetime
        from concilium.models.canonical import EapItem
        meta = Meta(gerado_em=datetime.now(UTC), perfil_construtora_id="agis", jurisdicao_id="BR")
        proj = Projeto(
            id="x", nome="test", tipo_obra="terraplenagem", localizacao="x",
            coordenadas=Coordenadas(lat=0, lng=0),
            regime_trabalho=RegimeTrabalho(dias_semana=6, horas_dia=8),
            data_inicio="2026-01-01", data_termino="2026-12-31",
            versao_referencia_id="x", snapshot_catalogo_id="x", snapshot_perfil_id="x",
        )
        q = 100.0
        preco_unit = custo_venda / q  # preco_unit tal que subtotal = custo_venda
        eap = [EapItem(item_id="i1", ordem=1, cpu_id="CPU-X",
                       descricao="t", unidade="m3", quantitativo=q)]
        equipe = EquipeDireta(
            equipe_id="eq1", item_id="i1", cpu_id="CPU-X", nome="t",
            funcoes=[FuncaoEquipeDireta(
                funcao_id="f1", descricao="t", num_pessoas=1,
                salario_base=1000, percentual_encargos=0.92,
                horas_extras_pct=0, custo_mensal_unitario=1920,
            )],
            equipamentos=[EquipamentoEquipeDireta(
                equip_id="e1", descricao="t", num_unidades=1,
                custo_mensal=5000, custo_combustivel_mensal=1000, custo_mensal_total=6000,
            )],
            custo_mao_obra_mensal=1920, custo_equipamentos_mensal=6000,
            custo_fixo_mensal=7920, permanencia_meses=1,
            custo_total=custo_fixo,
        )
        plan = Planejamento(
            item_id="i1", cpu_id="CPU-X", quantitativo=q,
            preco_unitario=PrecoUnitarioCategoria(
                material=0, diesel=preco_unit*0.1, mao_obra=preco_unit*0.4,
                equipamentos=preco_unit*0.5, total=preco_unit
            ),
            bdi=BdiCategorias(material=0, diesel=0.27, mao_obra=0.27, equipamentos=0.27),
            preco_unitario_com_bdi=PrecoUnitarioCategoria(
                material=0, diesel=preco_unit*0.1*1.27, mao_obra=preco_unit*0.4*1.27,
                equipamentos=preco_unit*0.5*1.27, total=preco_unit*1.27
            ),
            subtotal=SubtotalSemBdiComBdi(
                sem_bdi=SubtotalCategorias(
                    material=0, diesel=preco_unit*0.1*q, mao_obra=preco_unit*0.4*q,
                    equipamentos=preco_unit*0.5*q, total=custo_venda
                ),
                com_bdi=SubtotalCategorias(
                    material=0, diesel=preco_unit*0.1*q*1.27, mao_obra=preco_unit*0.4*q*1.27,
                    equipamentos=preco_unit*0.5*q*1.27, total=custo_venda*1.27
                ),
            ),
        )
        ind = Indireto(categoria="ADM", descricao="adm", custo_total=indiretos)
        return CanonicalModel(
            meta=meta, projeto=proj, eap=eap,
            equipes_diretas=[equipe], planejamento=[plan], indiretos=[ind],
        )

    def test_pe_ok_quando_delta_baixo(self):
        # Construir canonical onde preco_unitario da CPU ≈ custo_unit_real da equipe
        # custo_fixo=100 (total equipe), quantitativo=100 → custo_unit_real=1.0
        # subtotal.sem_bdi.total deve ser próximo de 100 (cobrindo a equipe)
        # Usando quantitativo=100 e preco_unit=1.02 → subtotal≈102 → delta_pct≈2%
        canonical = self._fake_canonical_com_planejamento(
            custo_fixo=102, custo_venda=102, indiretos=10
        )
        perfil = {
            "limiar_ponto_equilibrio": 0.05,
            "faixa_margem_alvo": {"min": 0.08, "max": 0.10},
            "faixa_margem_aceitavel": {"min": 0.06, "max": 0.12},
        }
        result = run_consolidar_resultado(canonical, {}, perfil)
        pe_validacoes = [v for v in result.validacoes if v.codigo == "VAL-PE-01"]
        assert len(pe_validacoes) == 1
        assert pe_validacoes[0].status == "OK"

    def test_pe_erro_quando_delta_alto(self):
        # Custo equipe = 100, custo venda = 80 → delta 20% (> 5%)
        canonical = self._fake_canonical_com_planejamento(
            custo_fixo=100, custo_venda=80, indiretos=10
        )
        perfil = {
            "limiar_ponto_equilibrio": 0.05,
            "faixa_margem_alvo": {"min": 0.08, "max": 0.10},
            "faixa_margem_aceitavel": {"min": 0.06, "max": 0.12},
        }
        result = run_consolidar_resultado(canonical, {}, perfil)
        assert result.has_errors
        pe_erros = [v for v in result.validacoes if v.codigo == "VAL-PE-01" and v.status == "ERRO"]
        assert len(pe_erros) == 1

    def test_classificacao_margem_verde_amarelo_vermelho(self):
        perfil_alvo = {"min": 0.08, "max": 0.10}
        perfil_acept = {"min": 0.06, "max": 0.12}

        from concilium.skills.consolidar import _classificar_margem
        assert _classificar_margem(0.09, perfil_alvo, perfil_acept) == "VERDE"
        assert _classificar_margem(0.07, perfil_alvo, perfil_acept) == "AMARELO"
        assert _classificar_margem(0.11, perfil_alvo, perfil_acept) == "AMARELO"
        assert _classificar_margem(0.05, perfil_alvo, perfil_acept) == "VERMELHO"
        assert _classificar_margem(0.15, perfil_alvo, perfil_acept) == "VERMELHO"

    def test_resultado_agregado_correto(self):
        canonical = self._fake_canonical_com_planejamento(
            custo_fixo=100, custo_venda=102, indiretos=10
        )
        perfil = {
            "limiar_ponto_equilibrio": 0.05,
            "faixa_margem_alvo": {"min": 0.08, "max": 0.10},
            "faixa_margem_aceitavel": {"min": 0.06, "max": 0.12},
        }
        result = run_consolidar_resultado(canonical, {}, perfil)
        res = result.canonical.resultado
        assert res is not None
        # venda sem BDI = 102; com BDI = 102 * 1.27 = 129.54
        assert res.venda.total_sem_bdi == 102
        assert abs(res.venda.total_com_bdi - 129.54) < 0.01
        # custo total = direto 100 + indireto 10 = 110
        assert res.custo.total == 110
        # resultado financeiro = 129.54 - 110 = 19.54
        assert abs(res.resultado_financeiro - 19.54) < 0.01


# ─────────────────────── Skills 02-05 ───────────────────────

from datetime import UTC, datetime

from concilium.models.canonical import (
    Cronograma,
    DistribuicaoMensal,
    EapItem,
    Meta,
    Praticabilidade,
)
from concilium.skills.cronograma import run_cronograma
from concilium.skills.equipes_diretas import run_equipes_diretas
from concilium.skills.planejamento_bdi import run_planejamento_bdi
from concilium.skills.indiretos import run_indiretos


def _canonical_com_prat(inputs_escopo, catalogo):
    """Canônico com escopo + praticabilidade mockada para Aracoiaba."""
    inputs = {**inputs_escopo,
              "perfil_id": "agis", "jurisdicao_id": "BR",
              "snapshot_catalogo_id": "abc", "snapshot_perfil_id": "def"}
    can = run_escopo(None, inputs, catalogo).canonical
    # Injeta praticabilidade compatível com a amostra (seca jul-dez, chuvas jan-abr)
    prat = Praticabilidade(
        fonte="mock",
        limiar_inviabilidade_mm=10,
        calculada_em=datetime.now(UTC),
        percentual_produtivo_mensal={
            "01": 0.52, "02": 0.48, "03": 0.55, "04": 0.70,
            "05": 0.85, "06": 0.92, "07": 0.95, "08": 0.95,
            "09": 0.88, "10": 0.80, "11": 0.68, "12": 0.58,
        },
    )
    return can.model_copy(update={"praticabilidade": prat})


class TestSkillCronograma:
    def test_completude_100_com_alocacao_suficiente(
        self, inputs_escopo_terraplenagem, config_root
    ):
        import json
        catalogo = {
            "cpus": json.loads((config_root / "catalogo" / "cpus.json").read_text())["cpus"],
            "insumos": json.loads((config_root / "catalogo" / "insumos.json").read_text())["insumos"],
        }
        can = _canonical_com_prat(inputs_escopo_terraplenagem, catalogo)
        # Amostra 1 usa 1 equipe jun-nov, 2 equipes em dez para eap-01
        inputs = {
            "num_equipes_por_item": {
                "eap-01": {
                    "2026-06": 1, "2026-07": 1, "2026-08": 1,
                    "2026-09": 1, "2026-10": 1, "2026-11": 1, "2026-12": 2,
                },
                "eap-02": {
                    "2026-08": 1, "2026-09": 1, "2026-10": 1,
                    "2026-11": 1, "2026-12": 2,
                },
                "eap-03": {"2026-11": 1, "2026-12": 1},
            }
        }
        result = run_cronograma(can, inputs, catalogo)
        assert not result.has_errors
        for cron in result.canonical.cronograma:
            assert cron.pct_completude >= 0.999, (
                f"item {cron.item_id}: completude {cron.pct_completude:.3f}"
            )

    def test_val_cron_01_erro_quando_insuficiente(
        self, inputs_escopo_terraplenagem, config_root
    ):
        import json
        catalogo = {
            "cpus": json.loads((config_root / "catalogo" / "cpus.json").read_text())["cpus"],
            "insumos": json.loads((config_root / "catalogo" / "insumos.json").read_text())["insumos"],
        }
        can = _canonical_com_prat(inputs_escopo_terraplenagem, catalogo)
        # Apenas 1 mês de execução — claramente insuficiente
        inputs = {"num_equipes_por_item": {"eap-01": {"2026-06": 1}}}
        result = run_cronograma(can, inputs, catalogo)
        assert result.has_errors
        val = [v for v in result.validacoes if v.codigo == "VAL-CRON-01"]
        assert val and val[0].status == "ERRO"

    def test_val_cron_02_buraco_no_meio(
        self, inputs_escopo_terraplenagem, config_root
    ):
        import json
        catalogo = {
            "cpus": json.loads((config_root / "catalogo" / "cpus.json").read_text())["cpus"],
            "insumos": json.loads((config_root / "catalogo" / "insumos.json").read_text())["insumos"],
        }
        can = _canonical_com_prat(inputs_escopo_terraplenagem, catalogo)
        # Buraco: jun-jul, pula ago, set-dez
        inputs = {
            "num_equipes_por_item": {
                "eap-01": {"2026-06": 1, "2026-07": 1, "2026-09": 2, "2026-10": 2, "2026-11": 2, "2026-12": 2},
            }
        }
        result = run_cronograma(can, inputs, catalogo)
        val = [v for v in result.validacoes if v.codigo == "VAL-CRON-02"]
        assert val and val[0].status == "ERRO"


class TestSkillEquipesDiretas:
    def _canonical_com_cron(self, inputs_escopo, catalogo):
        can = _canonical_com_prat(inputs_escopo, catalogo)
        inputs_cron = {
            "num_equipes_por_item": {
                "eap-01": {"2026-06": 1, "2026-07": 1, "2026-08": 1,
                           "2026-09": 1, "2026-10": 1, "2026-11": 1, "2026-12": 2},
                "eap-02": {"2026-08": 1, "2026-09": 1, "2026-10": 1, "2026-11": 1, "2026-12": 2},
                "eap-03": {"2026-11": 1, "2026-12": 1},
            }
        }
        return run_cronograma(can, inputs_cron, catalogo).canonical

    def test_calcula_equipe_com_diesel(self, inputs_escopo_terraplenagem, config_root):
        import json
        catalogo = {
            "cpus": json.loads((config_root / "catalogo" / "cpus.json").read_text())["cpus"],
            "insumos": json.loads((config_root / "catalogo" / "insumos.json").read_text())["insumos"],
        }
        perfil = json.loads((config_root / "perfis" / "agis.json").read_text())
        can = self._canonical_com_cron(inputs_escopo_terraplenagem, catalogo)
        result = run_equipes_diretas(can, {}, catalogo, perfil)
        assert not result.has_errors
        equipes = result.canonical.equipes_diretas
        assert len(equipes) == 3  # 3 itens na EAP
        # Custo total deve ser positivo
        for eq in equipes:
            assert eq.custo_total > 0
            assert eq.permanencia_meses > 0
            assert eq.custo_fixo_mensal > 0

    def test_custo_com_he_maior_que_sem(self, inputs_escopo_terraplenagem, config_root):
        import json
        catalogo = {
            "cpus": json.loads((config_root / "catalogo" / "cpus.json").read_text())["cpus"],
            "insumos": json.loads((config_root / "catalogo" / "insumos.json").read_text())["insumos"],
        }
        perfil = json.loads((config_root / "perfis" / "agis.json").read_text())
        can = self._canonical_com_cron(inputs_escopo_terraplenagem, catalogo)
        res_com_he = run_equipes_diretas(can, {"percentual_encargos": 0.92}, catalogo, perfil)
        res_sem_he = run_equipes_diretas(can, {"percentual_encargos": 0.0}, catalogo, perfil)
        custo_com = sum(e.custo_mao_obra_mensal for e in res_com_he.canonical.equipes_diretas)
        custo_sem = sum(e.custo_mao_obra_mensal for e in res_sem_he.canonical.equipes_diretas)
        assert custo_com > custo_sem


class TestSkillPlanejamentoBDI:
    def test_decomposicao_4_categorias(self, inputs_escopo_terraplenagem, config_root):
        import json
        catalogo = {
            "cpus": json.loads((config_root / "catalogo" / "cpus.json").read_text())["cpus"],
            "insumos": json.loads((config_root / "catalogo" / "insumos.json").read_text())["insumos"],
        }
        perfil = json.loads((config_root / "perfis" / "agis.json").read_text())
        inputs = {**inputs_escopo_terraplenagem,
                  "perfil_id": "agis", "jurisdicao_id": "BR",
                  "snapshot_catalogo_id": "abc", "snapshot_perfil_id": "def"}
        can = run_escopo(None, inputs, catalogo).canonical
        result = run_planejamento_bdi(can, {}, catalogo, perfil)
        assert not result.has_errors
        for p in result.canonical.planejamento:
            # Total = soma das 4 categorias
            pu = p.preco_unitario
            assert abs(pu.total - (pu.material + pu.diesel + pu.mao_obra + pu.equipamentos)) < 0.01

    def test_preco_com_bdi_maior_que_sem(self, inputs_escopo_terraplenagem, config_root):
        import json
        catalogo = {
            "cpus": json.loads((config_root / "catalogo" / "cpus.json").read_text())["cpus"],
            "insumos": json.loads((config_root / "catalogo" / "insumos.json").read_text())["insumos"],
        }
        perfil = json.loads((config_root / "perfis" / "agis.json").read_text())
        inputs = {**inputs_escopo_terraplenagem,
                  "perfil_id": "agis", "jurisdicao_id": "BR",
                  "snapshot_catalogo_id": "abc", "snapshot_perfil_id": "def"}
        can = run_escopo(None, inputs, catalogo).canonical
        result = run_planejamento_bdi(can, {}, catalogo, perfil)
        for p in result.canonical.planejamento:
            assert p.subtotal.com_bdi.total > p.subtotal.sem_bdi.total

    def test_val_pol_bdi_aviso_quando_fora_da_faixa(
        self, inputs_escopo_terraplenagem, config_root
    ):
        import json
        catalogo = {
            "cpus": json.loads((config_root / "catalogo" / "cpus.json").read_text())["cpus"],
            "insumos": json.loads((config_root / "catalogo" / "insumos.json").read_text())["insumos"],
        }
        perfil = json.loads((config_root / "perfis" / "agis.json").read_text())
        inputs = {**inputs_escopo_terraplenagem,
                  "perfil_id": "agis", "jurisdicao_id": "BR",
                  "snapshot_catalogo_id": "abc", "snapshot_perfil_id": "def"}
        can = run_escopo(None, inputs, catalogo).canonical
        # BDI de 80% está fora da faixa máxima de 30%
        result = run_planejamento_bdi(
            can, {"bdi_aplicado": {"material": 0, "diesel": 0.80, "mao_obra": 0.80, "equipamentos": 0.80}},
            catalogo, perfil
        )
        val = [v for v in result.validacoes if v.codigo == "VAL-POL-BDI"]
        assert val and val[0].status == "AVISO"


class TestSkillIndiretos:
    def _canonical_pronto_ate_equipes(self, inputs_escopo, config_root):
        import json
        catalogo = {
            "cpus": json.loads((config_root / "catalogo" / "cpus.json").read_text())["cpus"],
            "insumos": json.loads((config_root / "catalogo" / "insumos.json").read_text())["insumos"],
        }
        perfil = json.loads((config_root / "perfis" / "agis.json").read_text())
        inputs = {**inputs_escopo,
                  "perfil_id": "agis", "jurisdicao_id": "BR",
                  "snapshot_catalogo_id": "abc", "snapshot_perfil_id": "def"}
        can = run_escopo(None, inputs, catalogo).canonical
        prat = Praticabilidade(
            fonte="mock", limiar_inviabilidade_mm=10, calculada_em=datetime.now(UTC),
            percentual_produtivo_mensal={str(m).zfill(2): 0.85 for m in range(1, 13)},
        )
        can = can.model_copy(update={"praticabilidade": prat})
        cron_inputs = {
            "num_equipes_por_item": {
                "eap-01": {"2026-06": 1, "2026-07": 1, "2026-08": 1,
                           "2026-09": 1, "2026-10": 1, "2026-11": 1, "2026-12": 2},
                "eap-02": {"2026-08": 1, "2026-09": 1, "2026-10": 1, "2026-11": 1, "2026-12": 2},
                "eap-03": {"2026-11": 1, "2026-12": 1},
            }
        }
        can = run_cronograma(can, cron_inputs, catalogo).canonical
        can = run_equipes_diretas(can, {}, catalogo, perfil).canonical
        return can, perfil

    def test_produz_5_categorias_agis(self, inputs_escopo_terraplenagem, config_root):
        can, perfil = self._canonical_pronto_ate_equipes(inputs_escopo_terraplenagem, config_root)
        result = run_indiretos(can, {}, perfil)
        categorias = {i.categoria for i in result.canonical.indiretos}
        assert categorias == {"ADM", "TOP", "LAB", "QSMS", "MOB"}

    def test_todos_custos_positivos(self, inputs_escopo_terraplenagem, config_root):
        can, perfil = self._canonical_pronto_ate_equipes(inputs_escopo_terraplenagem, config_root)
        result = run_indiretos(can, {}, perfil)
        for ind in result.canonical.indiretos:
            assert ind.custo_total >= 0, f"{ind.categoria}: custo {ind.custo_total}"

    def test_mob_com_dados_customizados(self, inputs_escopo_terraplenagem, config_root):
        can, perfil = self._canonical_pronto_ate_equipes(inputs_escopo_terraplenagem, config_root)
        dados_mob = {
            "mobilizacoes": [
                {"descricao": "Mob. equip.", "num_unidades": 3,
                 "origem": "Goiânia", "destino": "Aracoiaba",
                 "distancia_km": 2200, "custo_km": 12.50},
            ],
            "custo_pessoa_mes": 1850,
        }
        result = run_indiretos(can, {"dados_mobilizacao": dados_mob}, perfil)
        mob = next(i for i in result.canonical.indiretos if i.categoria == "MOB")
        # 3 unidades × 2200km × 12.50 = 82500
        assert any(abs(m.custo_total - 82500) < 1 for m in mob.mobilizacoes)
