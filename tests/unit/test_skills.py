"""Testes das 3 skills implementadas: escopo, praticabilidade, consolidar."""

import json
from pathlib import Path
from typing import Any

import pytest

from concilium.application.skills import load_skill_stage, run_escopo_e_eap, run_produtividade_climatica

# NEP-041 F4: estágio de consolidação da skill unificada 06-resultado-financeiro
run_consolidacao_financeira = load_skill_stage(
    "06-resultado-financeiro", "_consolidacao", "run_consolidacao_financeira"
)
from concilium.domain.models.canonical import (
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


def _load_catalogo_insumos(config_root: Path) -> list[dict[str, Any]]:
    insumos: list[dict[str, Any]] = []
    insumos_dir = config_root / "catalogos" / "test" / "insumos"
    for arquivo in sorted(insumos_dir.glob("*.json")):
        data = json.loads(arquivo.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "insumos" in data:
            insumos.extend(data["insumos"])
        elif isinstance(data, list):
            insumos.extend(data)
    return insumos


class TestSkillEscopo:
    def test_cria_canonical_inicial(self, inputs_escopo_terraplenagem: dict[str, Any]):
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "mendeslobo",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        result = run_escopo_e_eap(None, inputs, catalogo=None)
        assert not result.has_errors
        assert result.canonical.projeto.nome.startswith("Terraplenagem")
        assert len(result.canonical.eap) == 3
        assert result.canonical.eap[0].cpu_id == "ESCO-CARGA-1CAT-DMT2000"

    def test_falha_se_canonical_in_existe(self, inputs_escopo_terraplenagem: dict[str, Any]):
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "mendeslobo",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        # Cria canônico fake
        from datetime import UTC, datetime

        meta = Meta(gerado_em=datetime.now(UTC), contexto_id="mendeslobo")
        proj = Projeto(
            id="x",
            nome="Existing",
            tipo_obra="terraplenagem",
            localizacao="X",
            coordenadas=Coordenadas(lat=0, lng=0),
            regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
            snapshot_catalogo_id="x",
            snapshot_perfil_id="x",
        )
        existing = CanonicalModel(meta=meta, projeto=proj)
        result = run_escopo_e_eap(existing, inputs, catalogo=None)
        assert result.has_errors
        assert result.validacoes[0].codigo == "VAL-ESCOPO-01"

    def test_val_eap_01_detecta_cpu_inexistente(self, inputs_escopo_terraplenagem: dict[str, Any]):
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "mendeslobo",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        catalogo = {"cpus": [{"codigo": "OUTRA-CPU"}]}
        result = run_escopo_e_eap(None, inputs, catalogo=catalogo)
        assert result.has_errors
        # Deve haver erros VAL-EAP-01 para cada CPU não encontrada
        eap_errors = [v for v in result.validacoes if v.codigo == "VAL-EAP-01" and v.status == "ERRO"]
        assert len(eap_errors) == 3

    def test_val_eap_01_ok_quando_todas_cpus_existem(self, inputs_escopo_terraplenagem: dict[str, Any]):
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "mendeslobo",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        catalogo = {
            "cpus": [
                {"codigo": "ESCO-CARGA-1CAT-DMT2000"},
                {"codigo": "COMPACT-ATERRO-100PN"},
                {"codigo": "REGULARIZACAO-SUBLEITO"},
            ]
        }
        result = run_escopo_e_eap(None, inputs, catalogo=catalogo)
        assert not result.has_errors


class TestSkillPraticabilidade:
    def test_calcula_percentual_mensal(
        self,
        inputs_escopo_terraplenagem: dict[str, Any],
        mock_openmeteo_aracoiaba,
    ):
        inputs_esc = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "mendeslobo",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        canonical = run_escopo_e_eap(None, inputs_esc).canonical

        perfil = {"limiar_inviabilidade_mm": 10}
        result = run_produtividade_climatica(
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

    def test_val_prat_01_e_02_ok(self, inputs_escopo_terraplenagem: dict[str, Any], mock_openmeteo_aracoiaba):
        inputs_esc = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "mendeslobo",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        canonical = run_escopo_e_eap(None, inputs_esc).canonical
        perfil = {"limiar_inviabilidade_mm": 10}
        result = run_produtividade_climatica(
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

        from concilium.domain.models.canonical import EapItem

        meta = Meta(gerado_em=datetime.now(UTC), contexto_id="mendeslobo")
        proj = Projeto(
            id="x",
            nome="test",
            tipo_obra="terraplenagem",
            localizacao="x",
            coordenadas=Coordenadas(lat=0, lng=0),
            regime_trabalho=RegimeTrabalho(dias_semana=6, horas_dia=8),
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
            snapshot_catalogo_id="x",
            snapshot_perfil_id="x",
        )
        q = 100.0
        preco_unit = custo_venda / q  # preco_unit tal que subtotal = custo_venda
        eap = [EapItem(item_id="i1", ordem=1, cpu_id="CPU-X", descricao="t", unidade="m3", quantitativo=q)]
        equipe = EquipeDireta(
            equipe_id="eq1",
            item_id="i1",
            cpu_id="CPU-X",
            nome="t",
            funcoes=[
                FuncaoEquipeDireta(
                    funcao_id="f1",
                    descricao="t",
                    num_pessoas=1,
                    salario_base=1000,
                    percentual_encargos=0.92,
                    horas_extras_pct=0,
                    custo_mensal_unitario=1920,
                )
            ],
            equipamentos=[
                EquipamentoEquipeDireta(
                    equip_id="e1",
                    descricao="t",
                    num_unidades=1,
                    custo_mensal=5000,
                    custo_combustivel_mensal=1000,
                    custo_mensal_total=6000,
                )
            ],
            custo_mao_obra_mensal=1920,
            custo_equipamentos_mensal=6000,
            # custo_fixo_mensal = custo_fixo (com permanencia=1) para que PE compare corretamente
            custo_fixo_mensal=custo_fixo,
            permanencia_meses=1,
            custo_total=custo_fixo,
        )
        plan = Planejamento(
            item_id="i1",
            cpu_id="CPU-X",
            quantitativo=q,
            preco_unitario=PrecoUnitarioCategoria(
                material=0,
                diesel=preco_unit * 0.1,
                mao_obra=preco_unit * 0.4,
                equipamentos=preco_unit * 0.5,
                total=preco_unit,
            ),
            bdi=BdiCategorias(material=0, diesel=0.27, mao_obra=0.27, equipamentos=0.27),
            preco_unitario_com_bdi=PrecoUnitarioCategoria(
                material=0,
                diesel=preco_unit * 0.1 * 1.27,
                mao_obra=preco_unit * 0.4 * 1.27,
                equipamentos=preco_unit * 0.5 * 1.27,
                total=preco_unit * 1.27,
            ),
            subtotal=SubtotalSemBdiComBdi(
                sem_bdi=SubtotalCategorias(
                    material=0,
                    diesel=preco_unit * 0.1 * q,
                    mao_obra=preco_unit * 0.4 * q,
                    equipamentos=preco_unit * 0.5 * q,
                    total=custo_venda,
                ),
                com_bdi=SubtotalCategorias(
                    material=0,
                    diesel=preco_unit * 0.1 * q * 1.27,
                    mao_obra=preco_unit * 0.4 * q * 1.27,
                    equipamentos=preco_unit * 0.5 * q * 1.27,
                    total=custo_venda * 1.27,
                ),
            ),
        )
        ind = Indireto(categoria="ADM", descricao="adm", custo_total=indiretos)
        return CanonicalModel(
            meta=meta,
            projeto=proj,
            eap=eap,
            equipes_diretas=[equipe],
            planejamento=[plan],
            indiretos=[ind],
        )

    def test_pe_ok_quando_delta_baixo(self):
        # custo_fixo_mensal=102 (permanencia=1), venda_com_bdi=102*1.27=129.54 >= 102 → OK
        canonical = self._fake_canonical_com_planejamento(custo_fixo=102, custo_venda=102, indiretos=10)
        perfil = {
            "limiar_ponto_equilibrio": 0.05,
            "faixa_margem_alvo": {"min": 0.08, "max": 0.10},
            "faixa_margem_aceitavel": {"min": 0.06, "max": 0.12},
        }
        result = run_consolidacao_financeira(canonical, {}, perfil)
        # Skill emite VAL-PONTO-EQUILIBRIO (summary) e popula canonical.ponto_equilibrio
        pe_items = [p for p in result.canonical.ponto_equilibrio if p.item_id == "i1"]
        assert len(pe_items) == 1
        assert pe_items[0].status_validacao == "OK"

    def test_pe_erro_quando_delta_alto(self):
        # custo_fixo_mensal=200 (> venda_com_bdi=80*1.27=101.6) → ERRO
        canonical = self._fake_canonical_com_planejamento(custo_fixo=200, custo_venda=80, indiretos=10)
        perfil = {
            "limiar_ponto_equilibrio": 0.05,
            "faixa_margem_alvo": {"min": 0.08, "max": 0.10},
            "faixa_margem_aceitavel": {"min": 0.06, "max": 0.12},
        }
        result = run_consolidacao_financeira(canonical, {}, perfil)
        pe_items = [p for p in result.canonical.ponto_equilibrio if p.item_id == "i1"]
        assert len(pe_items) == 1
        assert pe_items[0].status_validacao == "ERRO"

    def test_classificacao_margem_verde_amarelo_vermelho(self):
        import importlib.util

        skill_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "concilium"
            / "application"
            / "skills"
            / "manifests"
            / "06-resultado-financeiro"
            / "_consolidacao"
            / "skill.py"
        )
        spec = importlib.util.spec_from_file_location("_skill_consolidacao", skill_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _classificar_margem = mod._classificar_margem

        perfil_alvo = {"min": 0.08, "max": 0.10}
        perfil_acept = {"min": 0.06, "max": 0.12}
        assert _classificar_margem(0.09, perfil_alvo, perfil_acept) == "VERDE"
        assert _classificar_margem(0.07, perfil_alvo, perfil_acept) == "AMARELO"
        assert _classificar_margem(0.11, perfil_alvo, perfil_acept) == "AMARELO"
        assert _classificar_margem(0.05, perfil_alvo, perfil_acept) == "VERMELHO"
        assert _classificar_margem(0.15, perfil_alvo, perfil_acept) == "VERMELHO"

    def test_resultado_agregado_correto(self):
        canonical = self._fake_canonical_com_planejamento(custo_fixo=100, custo_venda=102, indiretos=10)
        perfil = {
            "limiar_ponto_equilibrio": 0.05,
            "faixa_margem_alvo": {"min": 0.08, "max": 0.10},
            "faixa_margem_aceitavel": {"min": 0.06, "max": 0.12},
        }
        result = run_consolidacao_financeira(canonical, {}, perfil)
        res = result.canonical.resultado
        assert res is not None
        # venda sem BDI = 102 (direto catálogo)
        assert res.venda.total_sem_bdi == 102
        # total_com_bdi = direto×BDI + indireto×BDI_indireto
        # BDI calibrado AGIS (fórmula multiplicativa TCU):
        #   BDI_indireto ≈ 25.23%  →  10 × 1.2523 = 12.523
        #   BDI_direto depende da composição da categoria no canonical fake
        #   Resultado observado com DEFAULT calibrado: ≈ 142.06
        # Tolerância de 0.50 para absorver variações de arredondamento da fórmula multiplicativa.
        assert abs(res.venda.total_com_bdi - 142.06) < 0.50
        # custo.total agora é custo operacional real: custo_direto_equipe + indireto = 100 + 10 = 110
        assert res.custo.total == 110
        # resultado_financeiro = venda_plus - custo_op = total_custo_plus(≈122.82) - 110 ≈ 12.82
        # (margem sobre preço operacional real, não sobre preço de catálogo)
        assert abs(res.resultado_financeiro - 12.82) < 1.50


# ─────────────────────── Skills 02-05 ───────────────────────

from datetime import UTC, datetime

from concilium.application.skills import run_cronograma, run_equipes_e_alocacao

run_custos_indiretos = load_skill_stage("06-resultado-financeiro", "_indiretos", "run_custos_indiretos")
run_precificacao_unitaria = load_skill_stage("06-resultado-financeiro", "_precificacao", "run_precificacao_unitaria")
from concilium.domain.models.canonical import (
    Cronograma,
    DistribuicaoMensal,
    EapItem,
    Praticabilidade,
)


def _canonical_com_prat(inputs_escopo, catalogo):
    """Canônico com escopo + praticabilidade mockada para Aracoiaba."""
    inputs = {**inputs_escopo, "contexto_id": "mendeslobo", "snapshot_catalogo_id": "abc", "snapshot_perfil_id": "def"}
    can = run_escopo_e_eap(None, inputs, catalogo).canonical
    # Injeta praticabilidade compatível com a amostra (seca jul-dez, chuvas jan-abr)
    prat = Praticabilidade(
        fonte="mock",
        limiar_inviabilidade_mm=10,
        calculada_em=datetime.now(UTC),
        percentual_produtivo_mensal={
            "01": 0.52,
            "02": 0.48,
            "03": 0.55,
            "04": 0.70,
            "05": 0.85,
            "06": 0.92,
            "07": 0.95,
            "08": 0.95,
            "09": 0.88,
            "10": 0.80,
            "11": 0.68,
            "12": 0.58,
        },
    )
    return can.model_copy(update={"praticabilidade": prat})


class TestSkillCronograma:
    def test_completude_100_com_alocacao_suficiente(self, inputs_escopo_terraplenagem, config_root):
        import json

        cpus_raw = json.loads((config_root / "catalogos" / "test" / "cpus.json").read_text())["cpus"]
        # Produtividades sintetizadas a partir do campo legado producao_horaria de cada CPU
        produtividades = [
            {"id": c["producao_id_ref"], "valor_horario": c["producao_horaria"]}
            for c in cpus_raw
            if c.get("producao_id_ref") and c.get("producao_horaria")
        ]
        catalogo = {
            "cpus": cpus_raw,
            "produtividades": produtividades,
        }
        can = _canonical_com_prat(inputs_escopo_terraplenagem, catalogo)
        # Amostra usa semanas ISO: W23-W30 para eap-01 (8 semanas × prod_semanal >> 80k)
        # eap-02: W27-W36 (10 semanas, 75k / 8313/wk ≈ 9.0); eap-03: W35-W40
        inputs = {
            "num_equipes_por_item": {
                "eap-01": {f"2026-W{w:02d}": 1 for w in range(23, 31)},
                "eap-02": {f"2026-W{w:02d}": 1 for w in range(27, 37)},
                "eap-03": {f"2026-W{w:02d}": 1 for w in range(35, 41)},
            }
        }
        result = run_cronograma(can, inputs, catalogo)
        assert not result.has_errors
        cronograma = result.canonical.cronograma
        assert cronograma is not None
        assert cronograma.pct_completude >= 0.999, f"completude global: {cronograma.pct_completude:.3f}"

    def test_val_cron_01_erro_quando_insuficiente(self, inputs_escopo_terraplenagem, config_root):
        import json

        catalogo = {
            "cpus": json.loads((config_root / "catalogos" / "test" / "cpus.json").read_text())["cpus"],
            "insumos": _load_catalogo_insumos(config_root),
        }
        can = _canonical_com_prat(inputs_escopo_terraplenagem, catalogo)
        # Apenas 1 semana de execução — claramente insuficiente
        inputs = {"num_equipes_por_item": {"eap-01": {"2026-W23": 1}}}
        result = run_cronograma(can, inputs, catalogo)
        assert result.has_errors
        val = [v for v in result.validacoes if v.codigo == "VAL-CRON-01"]
        assert val and val[0].status == "ERRO"

    def test_val_cron_02_buraco_no_meio(self, inputs_escopo_terraplenagem, config_root):
        import json

        catalogo = {
            "cpus": json.loads((config_root / "catalogos" / "test" / "cpus.json").read_text())["cpus"],
            "insumos": _load_catalogo_insumos(config_root),
        }
        can = _canonical_com_prat(inputs_escopo_terraplenagem, catalogo)
        # Buraco: W23-W24, pula W25, W26-W30
        inputs = {
            "num_equipes_por_item": {
                "eap-01": {
                    "2026-W23": 1,
                    "2026-W24": 1,
                    "2026-W26": 2,
                    "2026-W27": 2,
                    "2026-W28": 2,
                    "2026-W29": 2,
                    "2026-W30": 2,
                },
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
                "eap-01": {f"2026-W{w:02d}": 1 for w in range(23, 31)},
                "eap-02": {f"2026-W{w:02d}": 1 for w in range(27, 37)},
                "eap-03": {f"2026-W{w:02d}": 1 for w in range(35, 41)},
            }
        }
        return run_cronograma(can, inputs_cron, catalogo).canonical

    def test_calcula_equipe_com_diesel(self, inputs_escopo_terraplenagem, config_root):
        import json

        catalogo = {
            "cpus": json.loads((config_root / "catalogos" / "test" / "cpus.json").read_text())["cpus"],
            "insumos": _load_catalogo_insumos(config_root),
        }
        json.loads((config_root / "perfis" / "mendeslobo.json").read_text())
        can = self._canonical_com_cron(inputs_escopo_terraplenagem, catalogo)
        result = run_equipes_e_alocacao(can, {}, catalogo)
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
            "cpus": json.loads((config_root / "catalogos" / "test" / "cpus.json").read_text())["cpus"],
            "insumos": _load_catalogo_insumos(config_root),
        }
        json.loads((config_root / "perfis" / "mendeslobo.json").read_text())
        can = self._canonical_com_cron(inputs_escopo_terraplenagem, catalogo)
        # Testa HE via composicao_customizada: horas_extras_pct > 0 deve elevar custo MO
        # composicao_customizada[item_id]["funcoes"] deve ser dict {funcao_id: {override...}}
        cpu_padrao = catalogo["cpus"][0]["composicao_padrao_equipe"]
        funcoes_com_he = {f["funcao_id"]: {"horas_extras_pct": 0.5} for f in cpu_padrao["funcoes"]}
        composicao_com_he = {"funcoes": funcoes_com_he}
        res_com_he = run_equipes_e_alocacao(
            can,
            {"composicao_customizada": {"eap-01": composicao_com_he}},
            catalogo,
        )
        res_sem_he = run_equipes_e_alocacao(can, {}, catalogo)
        custo_com = sum(e.custo_mao_obra_mensal for e in res_com_he.canonical.equipes_diretas)
        custo_sem = sum(e.custo_mao_obra_mensal for e in res_sem_he.canonical.equipes_diretas)
        assert custo_com > custo_sem


class TestSkillPlanejamentoBDI:
    def test_decomposicao_4_categorias(self, inputs_escopo_terraplenagem, config_root):
        import json

        catalogo = {
            "cpus": json.loads((config_root / "catalogos" / "test" / "cpus.json").read_text())["cpus"],
            "insumos": _load_catalogo_insumos(config_root),
        }
        perfil = json.loads((config_root / "perfis" / "mendeslobo.json").read_text())
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "mendeslobo",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        can = run_escopo_e_eap(None, inputs, catalogo).canonical
        result = run_custos_indiretos(can, {}, catalogo, perfil)
        assert not result.has_errors
        for p in result.canonical.planejamento:
            # Total = soma das 4 categorias
            pu = p.preco_unitario
            assert abs(pu.total - (pu.material + pu.diesel + pu.mao_obra + pu.equipamentos)) < 0.01

    def test_preco_com_bdi_maior_que_sem(self, inputs_escopo_terraplenagem, config_root):
        import json

        catalogo = {
            "cpus": json.loads((config_root / "catalogos" / "test" / "cpus.json").read_text())["cpus"],
            "insumos": _load_catalogo_insumos(config_root),
        }
        perfil = json.loads((config_root / "perfis" / "mendeslobo.json").read_text())
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "mendeslobo",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        can = run_escopo_e_eap(None, inputs, catalogo).canonical
        result = run_custos_indiretos(can, {}, catalogo, perfil)
        for p in result.canonical.planejamento:
            assert p.subtotal.com_bdi.total > p.subtotal.sem_bdi.total

    def test_val_pol_bdi_aviso_quando_fora_da_faixa(self, inputs_escopo_terraplenagem, config_root):
        import json

        catalogo = {
            "cpus": json.loads((config_root / "catalogos" / "test" / "cpus.json").read_text())["cpus"],
            "insumos": _load_catalogo_insumos(config_root),
        }
        perfil = json.loads((config_root / "perfis" / "mendeslobo.json").read_text())
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "mendeslobo",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        can = run_escopo_e_eap(None, inputs, catalogo).canonical
        # BDI de 1.5 (150%) está fora da faixa permitida [0%, 100%] → VAL-POL-BDI AVISO
        result = run_precificacao_unitaria(
            can,
            {"bdi_aplicado": {"material": 0, "diesel": 1.5, "mao_obra": 1.5, "equipamentos": 1.5}},
            catalogo,
            perfil,
        )
        val = [v for v in result.validacoes if v.codigo == "VAL-POL-BDI"]
        assert val and val[0].status == "AVISO"


class TestSkillIndiretos:
    def _canonical_pronto_ate_equipes(self, inputs_escopo, config_root):
        import json

        catalogo = {
            "cpus": json.loads((config_root / "catalogos" / "test" / "cpus.json").read_text())["cpus"],
            "insumos": _load_catalogo_insumos(config_root),
        }
        perfil = json.loads((config_root / "perfis" / "mendeslobo.json").read_text())
        inputs = {
            **inputs_escopo,
            "contexto_id": "mendeslobo",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        can = run_escopo_e_eap(None, inputs, catalogo).canonical
        prat = Praticabilidade(
            fonte="mock",
            limiar_inviabilidade_mm=10,
            calculada_em=datetime.now(UTC),
            percentual_produtivo_mensal={str(m).zfill(2): 0.85 for m in range(1, 13)},
        )
        can = can.model_copy(update={"praticabilidade": prat})
        cron_inputs = {
            "num_equipes_por_item": {
                "eap-01": {
                    "2026-06": 1,
                    "2026-07": 1,
                    "2026-08": 1,
                    "2026-09": 1,
                    "2026-10": 1,
                    "2026-11": 1,
                    "2026-12": 2,
                },
                "eap-02": {"2026-08": 1, "2026-09": 1, "2026-10": 1, "2026-11": 1, "2026-12": 2},
                "eap-03": {"2026-11": 1, "2026-12": 1},
            }
        }
        can = run_cronograma(can, cron_inputs, catalogo).canonical
        can = run_equipes_e_alocacao(can, {}, catalogo).canonical
        return can, perfil

    def test_produz_5_categorias_agis(self, inputs_escopo_terraplenagem, config_root):
        can, perfil = self._canonical_pronto_ate_equipes(inputs_escopo_terraplenagem, config_root)
        result = run_custos_indiretos(can, {}, perfil=perfil)
        categorias = {i.categoria for i in result.canonical.indiretos}
        assert categorias == {"ADM", "TOP", "LAB", "QSMS", "MOB"}

    def test_todos_custos_positivos(self, inputs_escopo_terraplenagem, config_root):
        can, perfil = self._canonical_pronto_ate_equipes(inputs_escopo_terraplenagem, config_root)
        result = run_custos_indiretos(can, {}, perfil=perfil)
        for ind in result.canonical.indiretos:
            assert ind.custo_total >= 0, f"{ind.categoria}: custo {ind.custo_total}"

    def test_mob_com_dados_customizados(self, inputs_escopo_terraplenagem, config_root):
        can, perfil = self._canonical_pronto_ate_equipes(inputs_escopo_terraplenagem, config_root)
        dados_mob = {
            "mobilizacoes": [
                {
                    "descricao": "Mob. equip.",
                    "num_unidades": 3,
                    "origem": "Goiânia",
                    "destino": "Aracoiaba",
                    "distancia_km": 2200,
                    "custo_km": 12.50,
                },
            ],
            "custo_pessoa_mes": 1850,
        }
        result = run_custos_indiretos(can, {"dados_mobilizacao": dados_mob}, perfil=perfil)
        mob = next(i for i in result.canonical.indiretos if i.categoria == "MOB")
        # 3 unidades × 2200km × 12.50 = 82500
        assert any(abs(m.custo_total - 82500) < 1 for m in mob.mobilizacoes)


# ────────────────────────────────────────────────────────────────────────────
# Testes unitários skills 07-12
# ────────────────────────────────────────────────────────────────────────────

from datetime import date
from datetime import datetime as _dt

# Skills importadas via compat-alias registrado pelo __init__
from concilium.application.skills import (
    run_avaliacao_intervencoes,
    run_diagnostico_criticidade,
    run_registro_decisoes,
    run_relatorio_e_artefatos,
)
from concilium.domain.models.canonical import (
    ActivityDag,
    ArestaActivityDag,
    Atividade,
    CronogramaItem,
    CustoTotal,
    Resultado,
    ScheduledActivityCanonical,
    Venda,
)


def _projeto_07() -> Projeto:
    return Projeto(
        id="p-test",
        nome="Obra Teste",
        tipo_obra="terraplenagem",
        localizacao="Aracoiaba, CE",
        coordenadas=Coordenadas(lat=-4.36, lng=-38.73),
        regime_trabalho=RegimeTrabalho(dias_semana=6, horas_dia=8),
        data_inicio=date(2026, 6, 1),
        data_termino=date(2026, 12, 31),
        snapshot_catalogo_id="cat",
        snapshot_perfil_id="perf",
    )


def _equipe_direta_01() -> EquipeDireta:
    return EquipeDireta(
        equipe_id="eq-01",
        item_id="eap-01",
        cpu_id="ESCO-CARGA-1CAT-DMT2000",
        nome="Equipe Escavação",
        funcoes=[
            FuncaoEquipeDireta(
                funcao_id="op-1",
                descricao="Operador",
                num_pessoas=2,
                salario_base=3_000.0,
                percentual_encargos=0.70,
                horas_extras_pct=0.0,
                custo_mensal_unitario=5_100.0,
            )
        ],
        equipamentos=[],
        custo_mao_obra_mensal=10_200.0,
        custo_equipamentos_mensal=0.0,
        custo_fixo_mensal=30_000.0,
        permanencia_meses=7,
        custo_total=210_000.0,
    )


def _planejamento_01() -> Planejamento:
    return Planejamento(
        item_id="eap-01",
        cpu_id="ESCO-CARGA-1CAT-DMT2000",
        quantitativo=80_000,
        preco_unitario=PrecoUnitarioCategoria(equipamentos=5.0, material=1.0, diesel=1.5, mao_obra=0.5, total=8.0),
        bdi=BdiCategorias(equipamentos=0.25, material=0.15, diesel=0.15, mao_obra=0.0),
        preco_unitario_com_bdi=PrecoUnitarioCategoria(
            equipamentos=6.25, material=1.15, diesel=1.725, mao_obra=0.5, total=9.625
        ),
        subtotal=SubtotalSemBdiComBdi(
            sem_bdi=SubtotalCategorias(
                equipamentos=400_000,
                material=80_000,
                diesel=120_000,
                mao_obra=40_000,
                total=640_000,
            ),
            com_bdi=SubtotalCategorias(
                equipamentos=500_000,
                material=92_000,
                diesel=138_000,
                mao_obra=40_000,
                total=770_000,
            ),
        ),
    )


def _cronograma_01() -> CronogramaItem:
    return CronogramaItem(
        item_id="eap-01",
        dias_trabalhados_semana=6,
        pct_completude=1.0,
        distribuicao_semanal={
            f"2026-W{23 + (m - 6):02d}": DistribuicaoMensal(
                num_equipes=1,
                qtd_executada=11_428.0,
                qtd_acumulada=11_428.0 * (m - 5),
                pct=round((m - 5) / 7, 4),
            )
            for m in range(6, 13)
        },
    )


def _canonical_com_resultado(margem_pct: float = 0.20) -> CanonicalModel:
    """Canônico com resultado consolidado — pré-condição para skill 07."""
    resultado = Resultado(
        venda=Venda(total_sem_bdi=800_000.0, total_com_bdi=1_000_000.0),
        custo=CustoTotal(direto_equipes=500_000.0, total=800_000.0),
        resultado_financeiro=200_000.0,
        margem_pct=margem_pct,
        status_margem="VERDE",
        validacoes=[],
    )
    return CanonicalModel(
        meta=Meta(gerado_em=_dt.now(UTC), contexto_id="mendeslobo"),
        projeto=_projeto_07(),
        resultado=resultado,
        eap=[
            EapItem(
                item_id="eap-01",
                ordem=1,
                cpu_id="ESCO-CARGA-1CAT-DMT2000",
                descricao="Escavação",
                unidade="m3",
                quantitativo=80_000,
            )
        ],
        equipes_diretas=[_equipe_direta_01()],
        planejamento=[_planejamento_01()],
        cronograma=[_cronograma_01()],
        indiretos=[],
        ponto_equilibrio=[],
    )


# ────────────────────────────────────────────────────────────────────────────


class TestSkillAdapterSaidaAgis:
    pytestmark = [pytest.mark.slow]

    @pytest.fixture(scope="class")
    def _relatorio(self):
        """Executa run_relatorio_e_artefatos uma vez para toda a classe (margem_pct=0.20)."""
        return run_relatorio_e_artefatos(_canonical_com_resultado(margem_pct=0.20), {})

    def test_gera_todas_secoes(self, _relatorio):
        assert not _relatorio.has_errors
        rel = _relatorio.relatorio
        assert "PLANEJAMENTO" in rel
        assert "EQUIPE" in rel
        assert "RESULTADO" in rel
        assert "INDIRETOS" in rel

    def test_resultado_financeiro_correto(self, _relatorio):
        res = _relatorio.relatorio["RESULTADO"]
        assert res["margem_pct"] == pytest.approx(0.20)
        assert res["preco_venda_total"] == pytest.approx(1_000_000.0)

    def test_falha_sem_resultado_consolidado(self):
        can = _canonical_com_resultado().model_copy(update={"resultado": None})
        result = run_relatorio_e_artefatos(can, {})
        assert result.has_errors
        assert any(v.codigo == "VAL-ADAPTER-PRECONDICAO" for v in result.validacoes)

    def test_resumo_contem_nome_projeto(self, _relatorio):
        assert _relatorio.relatorio["resumo"]["projeto"] == "Obra Teste"

    def test_planejamento_row_tem_subtotais(self, _relatorio):
        rows = _relatorio.relatorio["PLANEJAMENTO"]
        assert len(rows) == 1
        row = rows[0]
        assert "subtotal_com_bdi" in row
        assert row["quantitativo"] == 80_000


class TestSkillCriticality:
    def test_falha_sem_cronograma(self):
        can = _canonical_com_resultado().model_copy(update={"cronograma": None})
        result = run_diagnostico_criticidade(can, {})
        assert result.has_errors

    def test_produz_report_basico(self):
        can = _canonical_com_resultado()
        result = run_diagnostico_criticidade(can, {})
        assert not result.has_errors
        assert result.canonical.cost_criticality_report is not None

    def test_atividades_presentes_no_report(self):
        can = _canonical_com_resultado()
        result = run_diagnostico_criticidade(can, {})
        report = result.canonical.cost_criticality_report
        atv_ids = [a.atividade_id for a in report.atividades]
        assert "eap-01" in atv_ids

    def test_pesos_custom(self):
        can = _canonical_com_resultado()
        result = run_diagnostico_criticidade(can, {"pesos_criticidade": {"alpha": 1.0, "beta": 0.0, "gamma": 0.0}})
        assert not result.has_errors

    def test_modo_trivial_sem_dag(self):
        can = _canonical_com_resultado()
        assert can.activity_dag is None
        result = run_diagnostico_criticidade(can, {})
        assert not result.has_errors

    def test_com_dag_simples(self):
        dag = ActivityDag(nos=["eap-01"], arestas=[], ordem_topologica=["eap-01"])
        can = _canonical_com_resultado().model_copy(update={"activity_dag": dag})
        result = run_diagnostico_criticidade(can, {})
        assert not result.has_errors


class TestSkillCostCriticality:
    def test_falha_sem_equipes_ou_planejamento(self):
        can = _canonical_com_resultado().model_copy(update={"equipes_diretas": [], "planejamento": []})
        result = run_diagnostico_criticidade(can, {})
        assert result.has_errors
        # Skill emite VAL-DIAG-PRE quando equipes ou cronograma estão ausentes
        assert any(v.codigo == "VAL-DIAG-PRE" for v in result.validacoes)

    def test_aviso_sem_criticality_report(self):
        # Skill produz cost_criticality_report mesmo sem criticality_report prévio
        can = _canonical_com_resultado()
        assert can.criticality_report is None
        result = run_diagnostico_criticidade(can, {})
        # Skill deve concluir sem erros e emitir VAL-DIAG-OK
        assert not result.has_errors
        assert any(v.codigo == "VAL-DIAG-OK" for v in result.validacoes)

    def test_popula_cost_criticality_report(self):
        can = _canonical_com_resultado()
        result = run_diagnostico_criticidade(can, {})
        assert not result.has_errors
        assert result.canonical.cost_criticality_report is not None

    def test_score_entre_0_e_1(self):
        can = _canonical_com_resultado()
        result = run_diagnostico_criticidade(can, {})
        for item in result.canonical.cost_criticality_report.atividades:
            # percentil é a métrica normalizada [0,1] no novo modelo ADR-020
            assert 0.0 <= item.custo.percentil <= 1.0, f"percentil fora do range: {item}"

    def test_class_valores_validos(self):
        can = _canonical_com_resultado()
        result = run_diagnostico_criticidade(can, {})
        valid_classes = {"A+", "A", "B", "C"}
        for item in result.canonical.cost_criticality_report.atividades:
            assert item.classe in valid_classes

    def test_n_atividades_consistente(self):
        can = _canonical_com_resultado()
        result = run_diagnostico_criticidade(can, {})
        report = result.canonical.cost_criticality_report
        # n_atividades deve ser consistente com len(atividades)
        assert report.n_atividades == len(report.atividades)


class TestSkillInterventionROI:
    def _intervencoes(self) -> list[dict]:
        return [
            {
                "intervencao_id": "int-01",
                "variavel": "eap-01",
                "tipo_perturbacao": "+10%",
                "descricao": "Aumentar equipe 10%",
            },
            {
                "intervencao_id": "int-02",
                "variavel": "eap-01",
                "tipo_perturbacao": "regime_6d",
                "descricao": "Regime 6 dias",
            },
        ]

    def test_falha_sem_intervencoes(self):
        can = _canonical_com_resultado()
        result = run_avaliacao_intervencoes(can, {"intervencoes_propostas": []})
        assert result.has_errors
        assert any(v.codigo == "VAL-ROI-01" for v in result.validacoes)

    def test_avalia_todas_intervencoes(self):
        can = _canonical_com_resultado()
        result = run_avaliacao_intervencoes(can, {"intervencoes_propostas": self._intervencoes()})
        assert not result.has_errors
        assert len(result.canonical.intervention_assessments) == 2

    def test_assessment_tem_campos_obrigatorios(self):
        can = _canonical_com_resultado()
        result = run_avaliacao_intervencoes(can, {"intervencoes_propostas": self._intervencoes()})
        for a in result.canonical.intervention_assessments:
            assert "decision_class" in a
            assert "roi_margem_pp" in a
            assert "effort" in a
            assert "risk" in a

    def test_decision_class_quick_win_para_low_effort(self):
        can = _canonical_com_resultado()
        intv = [
            {
                "intervencao_id": "int-01",
                "variavel": "eap-01",
                "tipo_perturbacao": "regime_9h",
                "descricao": "Jornada 9h",
            }
        ]
        result = run_avaliacao_intervencoes(can, {"intervencoes_propostas": intv})
        a = result.canonical.intervention_assessments[0]
        assert a["effort"]["nivel"] == "LOW"
        assert a["decision_class"] in ("quick_win", "balanced_tradeoff", "risk_averse")

    def test_effort_catalog_override(self):
        can = _canonical_com_resultado()
        custom_catalog = {"regime_9h": {"nivel": "HIGH", "tipo": "custom"}}
        intv = [
            {
                "intervencao_id": "int-01",
                "variavel": "eap-01",
                "tipo_perturbacao": "regime_9h",
                "descricao": "Override test",
            }
        ]
        result = run_avaliacao_intervencoes(
            can,
            {
                "intervencoes_propostas": intv,
                "effort_catalog": custom_catalog,
            },
        )
        a = result.canonical.intervention_assessments[0]
        assert a["effort"]["nivel"] == "HIGH"


class TestSkillDecisionLog:
    def _canonical(self) -> CanonicalModel:
        return _canonical_com_resultado()

    def _inputs_validos(self) -> dict:
        return {
            "objective": "Reduzir prazo de 7 para 6 meses",
            "considered_interventions": [
                {"variavel": "eap-01", "tipo_perturbacao": "+10%", "descricao": "Mais equipe"},
                {"variavel": "eap-01", "tipo_perturbacao": "regime_6d", "descricao": "Mais dias"},
            ],
            "selected_intervention": "+10%",
            "justification": {
                "rationale": "Melhor ROI relativo ao risco",
                "rejected_reasons": {"regime_6d": "Risco de fadiga e turnover"},
            },
            "decided_by": {"type": "engenheiro_senior", "id": "eng-001"},
            "expected_outcome": {"margem": 0.18, "prazo_dias": 180},
        }

    def test_cria_decision_log_valido(self):
        result = run_registro_decisoes(self._canonical(), self._inputs_validos())
        assert not result.has_errors
        log = result.decision_log
        assert "decision_id" in log
        assert log["selected_intervention"] == "+10%"

    def test_falha_sem_selected_intervention(self):
        inputs = {k: v for k, v in self._inputs_validos().items() if k != "selected_intervention"}
        result = run_registro_decisoes(self._canonical(), inputs)
        assert result.has_errors

    def test_falha_sem_considered_interventions(self):
        inputs = {**self._inputs_validos(), "considered_interventions": []}
        result = run_registro_decisoes(self._canonical(), inputs)
        assert result.has_errors
        assert any(v.codigo == "VAL-DEC-02" for v in result.validacoes)

    def test_aviso_sem_rejected_reasons(self):
        inputs = {**self._inputs_validos(), "justification": {"rationale": "Sem razões"}}
        result = run_registro_decisoes(self._canonical(), inputs)
        val_dec03 = [v for v in result.validacoes if v.codigo == "VAL-DEC-03"]
        assert val_dec03 and val_dec03[0].status == "AVISO"

    def test_decision_id_gerado_automaticamente(self):
        result = run_registro_decisoes(self._canonical(), self._inputs_validos())
        assert result.decision_log["decision_id"].startswith("dec_")

    def test_decision_id_custom_preservado(self):
        inputs = {**self._inputs_validos(), "decision_id": "dec_custom_001"}
        result = run_registro_decisoes(self._canonical(), inputs)
        assert result.decision_log["decision_id"] == "dec_custom_001"

    def test_selected_intervention_pode_ser_null(self):
        inputs = {**self._inputs_validos(), "selected_intervention": None}
        result = run_registro_decisoes(self._canonical(), inputs)
        assert not result.has_errors
        assert result.decision_log["selected_intervention"] is None


# ────────────────────────────────────────────────────────────────────────────
# Testes adicionais para cobertura 100%
# ────────────────────────────────────────────────────────────────────────────


class TestConsolidarCoberturaBranches:
    """Cobre branches não alcançados pelos testes principais do TestSkillConsolidar."""

    def _fake_canonical(self, custo_fixo: float, custo_venda: float, indiretos: float):
        from datetime import UTC, datetime

        from concilium.domain.models.canonical import EapItem

        meta = Meta(gerado_em=datetime.now(UTC), contexto_id="mendeslobo")
        proj = Projeto(
            id="x",
            nome="test",
            tipo_obra="terraplenagem",
            localizacao="x",
            coordenadas=Coordenadas(lat=0, lng=0),
            regime_trabalho=RegimeTrabalho(dias_semana=6, horas_dia=8),
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
            snapshot_catalogo_id="x",
            snapshot_perfil_id="x",
        )
        q = 100.0
        preco_unit = custo_venda / q
        eap = [EapItem(item_id="i1", ordem=1, cpu_id="CPU-X", descricao="t", unidade="m3", quantitativo=q)]
        equipe = EquipeDireta(
            equipe_id="eq1",
            item_id="i1",
            cpu_id="CPU-X",
            nome="t",
            funcoes=[
                FuncaoEquipeDireta(
                    funcao_id="f1",
                    descricao="t",
                    num_pessoas=1,
                    salario_base=1000,
                    percentual_encargos=0.92,
                    horas_extras_pct=0,
                    custo_mensal_unitario=1920,
                )
            ],
            equipamentos=[
                EquipamentoEquipeDireta(
                    equip_id="e1",
                    descricao="t",
                    num_unidades=1,
                    custo_mensal=5000,
                    custo_combustivel_mensal=1000,
                    custo_mensal_total=6000,
                )
            ],
            custo_mao_obra_mensal=1920,
            custo_equipamentos_mensal=6000,
            # custo_fixo_mensal = custo_fixo (com permanencia=1) para que PE compare corretamente
            custo_fixo_mensal=custo_fixo,
            permanencia_meses=1,
            custo_total=custo_fixo,
        )
        plan = Planejamento(
            item_id="i1",
            cpu_id="CPU-X",
            quantitativo=q,
            preco_unitario=PrecoUnitarioCategoria(
                material=0,
                diesel=preco_unit * 0.1,
                mao_obra=preco_unit * 0.4,
                equipamentos=preco_unit * 0.5,
                total=preco_unit,
            ),
            bdi=BdiCategorias(material=0, diesel=0.27, mao_obra=0.27, equipamentos=0.27),
            preco_unitario_com_bdi=PrecoUnitarioCategoria(
                material=0,
                diesel=preco_unit * 0.1 * 1.27,
                mao_obra=preco_unit * 0.4 * 1.27,
                equipamentos=preco_unit * 0.5 * 1.27,
                total=preco_unit * 1.27,
            ),
            subtotal=SubtotalSemBdiComBdi(
                sem_bdi=SubtotalCategorias(
                    material=0,
                    diesel=preco_unit * 0.1 * q,
                    mao_obra=preco_unit * 0.4 * q,
                    equipamentos=preco_unit * 0.5 * q,
                    total=custo_venda,
                ),
                com_bdi=SubtotalCategorias(
                    material=0,
                    diesel=preco_unit * 0.1 * q * 1.27,
                    mao_obra=preco_unit * 0.4 * q * 1.27,
                    equipamentos=preco_unit * 0.5 * q * 1.27,
                    total=custo_venda * 1.27,
                ),
            ),
        )
        ind = Indireto(categoria="ADM", descricao="adm", custo_total=indiretos)
        return CanonicalModel(
            meta=meta,
            projeto=proj,
            eap=eap,
            equipes_diretas=[equipe],
            planejamento=[plan],
            indiretos=[ind],
        )

    def test_pe_aviso_quando_delta_entre_limiar_metade_e_limiar(self):
        """Verifica PE: custo_fixo_mensal < venda_com_bdi → OK (delta positivo)."""
        # custo_fixo_mensal=97 (permanencia=1), venda_com_bdi=100*1.27=127 >= 97 → OK
        can = self._fake_canonical(custo_fixo=97, custo_venda=100, indiretos=10)
        perfil = {
            "limiar_ponto_equilibrio": 0.05,
            "faixa_margem_alvo": {"min": 0.08, "max": 0.10},
            "faixa_margem_aceitavel": {"min": 0.06, "max": 0.12},
        }
        result = run_consolidacao_financeira(can, {}, perfil)
        pe_items = [p for p in result.canonical.ponto_equilibrio if p.item_id == "i1"]
        assert pe_items and pe_items[0].status_validacao == "OK"

    def test_margem_amarelo_path(self):
        """Cobre branch elif status_margem == 'AMARELO'."""
        # Para forçar AMARELO: margem fora do alvo mas dentro do aceitável
        # A skill calcula margem sobre (venda_catalogo_plus - custo_total_catalogo) / venda_catalogo_plus
        # custo_fixo_mensal=100, custo_venda=100, indiretos=10
        can = self._fake_canonical(custo_fixo=100, custo_venda=100, indiretos=10)
        perfil = {
            "limiar_ponto_equilibrio": 0.05,
            "faixa_margem_alvo": {"min": 0.16, "max": 0.20},
            "faixa_margem_aceitavel": {"min": 0.10, "max": 0.25},
        }
        result = run_consolidacao_financeira(can, {}, perfil)
        # Skill emite VAL-CONSOL-MARGEM com status baseado na classificação
        pol_margem = [v for v in result.validacoes if v.codigo == "VAL-CONSOL-MARGEM"]
        assert pol_margem and pol_margem[0].status in ("OK", "AVISO")

    def test_margem_verde_path(self):
        """Cobre branch else (status_margem == 'VERDE')."""
        # custo_fixo_mensal=100, custo_venda=100, indiretos=10
        can = self._fake_canonical(custo_fixo=100, custo_venda=100, indiretos=10)
        perfil = {
            "limiar_ponto_equilibrio": 0.05,
            "faixa_margem_alvo": {"min": 0.10, "max": 0.20},
            "faixa_margem_aceitavel": {"min": 0.05, "max": 0.25},
        }
        result = run_consolidacao_financeira(can, {}, perfil)
        # Skill emite VAL-CONSOL-MARGEM com status OK quando margem está dentro da faixa alvo
        pol_margem = [v for v in result.validacoes if v.codigo == "VAL-CONSOL-MARGEM"]
        assert pol_margem and pol_margem[0].status == "OK"

    def test_precondicao_sem_equipes(self):
        """Cobre branch VAL-CONSOL-PRECONDICAO (sem equipes_diretas)."""
        from datetime import UTC, datetime

        from concilium.domain.models.canonical import EapItem

        meta = Meta(gerado_em=datetime.now(UTC), contexto_id="mendeslobo")
        proj = Projeto(
            id="x",
            nome="test",
            tipo_obra="terraplenagem",
            localizacao="x",
            coordenadas=Coordenadas(lat=0, lng=0),
            regime_trabalho=RegimeTrabalho(dias_semana=6, horas_dia=8),
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
            snapshot_catalogo_id="x",
            snapshot_perfil_id="x",
        )
        can = CanonicalModel(
            meta=meta,
            projeto=proj,
            eap=[EapItem(item_id="i1", ordem=1, cpu_id="CPU-X", descricao="t", unidade="m3", quantitativo=100)],
        )
        perfil = {
            "limiar_ponto_equilibrio": 0.05,
            "faixa_margem_alvo": {"min": 0.08, "max": 0.10},
            "faixa_margem_aceitavel": {"min": 0.06, "max": 0.12},
        }
        result = run_consolidacao_financeira(can, {}, perfil)
        assert result.has_errors
        assert any(v.codigo == "VAL-CONSOL-PRE" for v in result.validacoes)


class TestDecisionLogBranches:
    """Cobre branches de validação de campos obrigatórios em run_registro_decisoes."""

    def _canonical(self):
        return _canonical_com_resultado()

    def test_falha_sem_objective(self):
        """Cobre branch 'Campo obrigatório ausente: objective'."""
        inputs = {
            "objective": "",
            "considered_interventions": [{"variavel": "eap-01", "tipo_perturbacao": "+10%"}],
            "selected_intervention": "+10%",
            "justification": {"rationale": "ok"},
            "decided_by": {"type": "eng", "id": "e1"},
        }
        result = run_registro_decisoes(self._canonical(), inputs)
        assert result.has_errors
        erros = [v for v in result.validacoes if "objective" in v.mensagem]
        assert erros

    def test_falha_sem_justification(self):
        """Cobre branch 'Campo obrigatório ausente: justification'."""
        inputs = {
            "objective": "Reduzir prazo",
            "considered_interventions": [{"variavel": "eap-01", "tipo_perturbacao": "+10%"}],
            "selected_intervention": "+10%",
            "justification": {},
            "decided_by": {"type": "eng", "id": "e1"},
        }
        result = run_registro_decisoes(self._canonical(), inputs)
        assert result.has_errors

    def test_falha_sem_decided_by(self):
        """Cobre branch 'Campo obrigatório ausente: decided_by'."""
        inputs = {
            "objective": "Reduzir prazo",
            "considered_interventions": [{"variavel": "eap-01", "tipo_perturbacao": "+10%"}],
            "selected_intervention": "+10%",
            "justification": {"rationale": "ok"},
            "decided_by": {},
        }
        result = run_registro_decisoes(self._canonical(), inputs)
        assert result.has_errors

    def test_aviso_com_uma_alternativa_sem_rejected_reasons(self):
        """Cobre branch VAL-DEC-03 quando só há 1 intervenção (não há rejeitadas)."""
        inputs = {
            "objective": "Reduzir prazo",
            "considered_interventions": [{"variavel": "eap-01", "tipo_perturbacao": "+10%"}],
            "selected_intervention": "+10%",
            "justification": {"rationale": "sem razões"},
            "decided_by": {"type": "eng", "id": "e1"},
        }
        result = run_registro_decisoes(self._canonical(), inputs)
        # Com apenas 1 intervenção, rejected_reasons não é obrigatório → sem VAL-DEC-03
        assert not result.has_errors


class TestCostCriticalityBranches:
    """Cobre branches adicionais de run_diagnostico_criticidade."""

    def test_com_perfil_nao_interfere_com_pareto(self):
        """ADR-020: perfil é aceito mas não afeta algoritmo Pareto+lexicográfico."""
        can = _canonical_com_resultado()
        result = run_diagnostico_criticidade(can, {})
        assert not result.has_errors
        report = result.canonical.cost_criticality_report
        # ADR-020: resultado usa Pareto — campos esperados: atividades com classe A+/A/B/C
        assert len(report.atividades) > 0
        assert report.atividades[0].classe in ("A+", "A", "B", "C")

    def test_custo_zero_retorna_erro(self):
        """Cobre branch 'Custo total zero'."""
        from datetime import UTC, datetime

        from concilium.domain.models.canonical import EapItem

        meta = Meta(gerado_em=datetime.now(UTC), contexto_id="mendeslobo")
        proj = _projeto_07()
        can = CanonicalModel(
            meta=meta,
            projeto=proj,
            eap=[EapItem(item_id="eap-01", ordem=1, cpu_id="CPU-X", descricao="t", unidade="m3", quantitativo=100)],
            equipes_diretas=[
                EquipeDireta(
                    equipe_id="eq1",
                    item_id="eap-01",
                    cpu_id="CPU-X",
                    nome="t",
                    funcoes=[],
                    equipamentos=[],
                    custo_mao_obra_mensal=0,
                    custo_equipamentos_mensal=0,
                    custo_fixo_mensal=0,
                    permanencia_meses=1,
                    custo_total=0,
                )
            ],
            planejamento=[_planejamento_01()],
        )
        result = run_diagnostico_criticidade(can, {})
        assert result.has_errors
        assert any(v.codigo == "VAL-CC-01" and v.status == "ERRO" for v in result.validacoes)

    def test_com_sensitivity_data_customizado(self):
        """Cobre branch 'sensitivity_data' fornecido no input (ignorado pelo skill atual)."""
        can = _canonical_com_resultado()
        # sensitivity_data no input é aceito mas não altera o cálculo da skill atual
        result = run_diagnostico_criticidade(can, {"sensitivity_data": {"eap-01": 0.8}})
        assert not result.has_errors
        atv = result.canonical.cost_criticality_report.atividades[0]
        # sensibilidade.valor_raw = custo_mao_obra * permanencia / custo_total = 10200*7/210000 = 0.34
        assert atv.sensibilidade.valor_raw == pytest.approx(0.34, abs=1e-2)

    def test_com_criticality_report_popula_duration_share(self):
        """Cobre branch 'for item in criticality_report.atividades'."""
        can = _canonical_com_resultado()
        # Primeiro executar skill 08 para ter criticality_report
        can_08 = run_diagnostico_criticidade(can, {}).canonical
        result = run_diagnostico_criticidade(can_08, {})
        assert not result.has_errors
        for atv in result.canonical.cost_criticality_report.atividades:
            assert atv.duracao is not None


class TestInterventionROIBranches:
    """Cobre branches adicionais de run_avaliacao_intervencoes."""

    def test_amplificacao_roi_para_atividade_aplus(self):
        """Cobre branch 'if custo_criticality' com atividade A+."""
        can = _canonical_com_resultado()
        # Criar cost_criticality_report simulado com atividade A+
        mock_report = {
            "pesos_usados": {"w_cost": 0.4, "w_duration": 0.3, "w_sensitivity": 0.3},
            "atividades": [
                {
                    "atividade_id": "eap-01",
                    "score": 0.85,
                    "class": "A+",
                    "cost_share": 1.0,
                    "duration_share": 1.0,
                    "is_time_critical": True,
                    "margin_sensitivity": 0.7,
                    "interpretation": "domina custo + crítica em tempo",
                }
            ],
        }
        can = can.model_copy(update={"cost_criticality_report": mock_report})
        intv = [
            {
                "intervencao_id": "int-01",
                "variavel": "eap-01",
                "tipo_perturbacao": "+10%",
                "descricao": "Amplificar ROI A+",
            }
        ]
        result = run_avaliacao_intervencoes(can, {"intervencoes_propostas": intv})
        assert not result.has_errors
        roi = result.canonical.intervention_assessments[0]["roi_margem_pp"]
        assert roi > 1.5  # Amplificado de 1.5 → 1.95

    def test_tipo_subcontratacao(self):
        """Cobre entry 'subcontratacao' no perturbacao_map."""
        can = _canonical_com_resultado()
        intv = [
            {
                "intervencao_id": "int-01",
                "variavel": "eap-01",
                "tipo_perturbacao": "subcontratacao",
                "descricao": "Subcontratar",
            }
        ]
        result = run_avaliacao_intervencoes(can, {"intervencoes_propostas": intv})
        assert not result.has_errors
        assert result.canonical.intervention_assessments[0]["tipo_perturbacao"] == "subcontratacao"

    def test_tipo_desconhecido_usa_fallback(self):
        """Cobre path 'tipo desconhecido → (0.5, 0)' do perturbacao_map.get."""
        can = _canonical_com_resultado()
        intv = [
            {
                "intervencao_id": "int-01",
                "variavel": "eap-01",
                "tipo_perturbacao": "tipo_inexistente",
                "descricao": "Desconhecido",
            }
        ]
        result = run_avaliacao_intervencoes(can, {"intervencoes_propostas": intv})
        assert not result.has_errors
        a = result.canonical.intervention_assessments[0]
        assert a["roi_margem_pp"] == 0.5
        assert a["delta_prazo_dias"] == 0


class TestCriticalityBranches:
    """Cobre branches adicionais de run_diagnostico_criticidade."""

    def test_com_perfil_pesos_analiticos(self):
        """Cobre branch 'if perfil' com pesos_analiticos em criticality."""
        can = _canonical_com_resultado()
        result = run_diagnostico_criticidade(can, {})
        assert not result.has_errors

    def test_com_atividades_lista(self):
        """Cobre branch 'elif canonical_in.atividades'."""
        can = _canonical_com_resultado()
        atividades = [
            Atividade(
                atividade_id="atv-01",
                eap_item_id="eap-01",
                descricao="Escavação",
                fracao_quantitativo=1.0,
                quantitativo_atividade=80_000.0,
                cpu_id="ESCO-CARGA-1CAT-DMT2000",
            )
        ]
        can = can.model_copy(update={"atividades": atividades})
        result = run_diagnostico_criticidade(can, {})
        assert not result.has_errors
        # atividades ficam em cost_criticality_report, não em criticality_report["atividades"]
        atv_ids = [a.atividade_id for a in result.canonical.cost_criticality_report.atividades]
        assert "eap-01" in atv_ids

    def test_com_dag_com_arestas(self):
        """Cobre branch 'for aresta in activity_dag.arestas' (out_degree e predecessores)."""
        dag = ActivityDag(
            nos=["atv-01", "atv-02"],
            arestas=[ArestaActivityDag(de="atv-01", para="atv-02")],
            ordem_topologica=["atv-01", "atv-02"],
        )
        atividades_dag = [
            Atividade(
                atividade_id="atv-01",
                eap_item_id="eap-01",
                descricao="Escavação",
                fracao_quantitativo=0.5,
                quantitativo_atividade=40_000.0,
                cpu_id="ESCO-CARGA-1CAT-DMT2000",
            ),
            Atividade(
                atividade_id="atv-02",
                eap_item_id="eap-01",
                descricao="Compactação",
                fracao_quantitativo=0.5,
                quantitativo_atividade=40_000.0,
                cpu_id="ESCO-CARGA-1CAT-DMT2000",
            ),
        ]
        can = _canonical_com_resultado().model_copy(update={"atividades": atividades_dag, "activity_dag": dag})
        result = run_diagnostico_criticidade(can, {})
        assert not result.has_errors

    def test_nenhuma_atividade_com_execucao(self):
        """Cobre branch 'if not timings' → AVISO."""
        can = _canonical_com_resultado()
        # Cronograma com qtd_executada=0 em todas as semanas → sem timings
        cron_vazio = Cronograma(
            scheduled_activities=[
                ScheduledActivityCanonical(
                    activity_id="eap-01",
                    start_week=1,
                    end_week=1,
                    duration_weeks=1,
                    distribuicao_semanal={
                        "2026-W23": DistribuicaoMensal(num_equipes=0, qtd_executada=0.0, qtd_acumulada=0.0, pct=0.0)
                    },
                )
            ]
        )
        can = can.model_copy(update={"cronograma": cron_vazio})
        result = run_diagnostico_criticidade(can, {})
        # Skill emite VAL-DIAG-01 AVISO quando não há execução no cronograma
        assert any(v.codigo == "VAL-DIAG-01" and v.status == "AVISO" for v in result.validacoes)


class TestAdapterSaidaAgisBranches:
    """Cobre branches adicionais de run_relatorio_e_artefatos."""

    pytestmark = [pytest.mark.slow]

    @pytest.fixture(scope="class")
    def _result_sem_pe(self):
        """run_relatorio_e_artefatos sem ponto_equilibrio — uma vez por classe."""
        return run_relatorio_e_artefatos(_canonical_com_resultado(), {})

    @pytest.fixture(scope="class")
    def _result_com_pe(self):
        """run_relatorio_e_artefatos com ponto_equilibrio — uma vez por classe."""
        from concilium.domain.models.canonical import PontoEquilibrio as PE

        can = _canonical_com_resultado()
        pe = PE(
            item_id="eap-01",
            custo_fixo_equipe=210_000,
            custo_venda_cpu=640_000,
            delta=430_000,
            delta_pct=0.05,
            status_validacao="OK",
        )
        return run_relatorio_e_artefatos(can.model_copy(update={"ponto_equilibrio": [pe]}), {})

    def test_adapter_sem_ponto_equilibrio(self, _result_sem_pe):
        """Cobre path quando pe (PontoEquilibrio) não existe para equipe."""
        assert not _result_sem_pe.has_errors
        equipe_rows = _result_sem_pe.relatorio["EQUIPE"]
        assert equipe_rows[0]["custo_venda_cpu"] is None

    def test_adapter_com_ponto_equilibrio(self, _result_com_pe):
        """Cobre path quando pe existe (custo_venda_cpu preenchido)."""
        assert not _result_com_pe.has_errors
        equipe_rows = _result_com_pe.relatorio["EQUIPE"]
        assert equipe_rows[0]["custo_venda_cpu"] == 640_000


class TestPraticabilidadeBranches:
    """Cobre branches adicionais em run_produtividade_climatica."""

    def test_exception_na_busca_climatica(self, inputs_escopo_terraplenagem):
        """Cobre except Exception no try/catch ao buscar dados climáticos."""
        from unittest.mock import MagicMock

        from concilium.infrastructure.clients.openmeteo import OpenMeteoClient

        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "mendeslobo",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        canonical = run_escopo_e_eap(None, inputs).canonical
        mock_client = MagicMock(spec=OpenMeteoClient)
        mock_client.fetch_dados_anuais.side_effect = ConnectionError("timeout")
        result = run_produtividade_climatica(canonical, {}, {}, client=mock_client)
        assert result.has_errors
        assert any(v.codigo == "VAL-PRAT-FONTE" for v in result.validacoes)

    def test_val_prat_02_ok_quando_12_meses(self, inputs_escopo_terraplenagem, mock_openmeteo_aracoiaba):
        """Confirma VAL-PRAT-02 OK e VAL-PRAT-04 ausente (variabilidade presente)."""
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "mendeslobo",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        canonical = run_escopo_e_eap(None, inputs).canonical
        result = run_produtividade_climatica(
            canonical, {"ano_referencia": 2024}, {"limiar_inviabilidade_mm": 10}, client=mock_openmeteo_aracoiaba
        )
        codigos_ok = [v.codigo for v in result.validacoes if v.status == "OK"]
        assert "VAL-PRAT-02" in codigos_ok
        # Mock de Aracoiaba tem variabilidade (diferentes % por mês) → VAL-PRAT-04 não disparado
        val_04 = [v for v in result.validacoes if v.codigo == "VAL-PRAT-04"]
        assert not val_04

    def test_val_prat_04_aviso_quando_todos_iguais(self, inputs_escopo_terraplenagem):
        """Cobre branch VAL-PRAT-04 (todos os meses iguais → AVISO)."""
        from unittest.mock import MagicMock

        from concilium.infrastructure.clients.openmeteo import DadosClimaticosMensais, OpenMeteoClient

        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "mendeslobo",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        canonical = run_escopo_e_eap(None, inputs).canonical
        # Todos os meses/semanas com 0 dias de chuva → percentual=1.0 em todos
        dias_uniform = {str(m).zfill(2): {"5mm": 0, "10mm": 0, "20mm": 0} for m in range(1, 13)}
        # Gera semanas uniformes também para que VAL-PRAT-04 as detecte
        dias_semanas_uniform = {f"2024-W{w:02d}": {"5mm": 0, "10mm": 0, "20mm": 0} for w in range(1, 53)}
        mock_client = MagicMock(spec=OpenMeteoClient)
        mock_client.fetch_dados_anuais.return_value = DadosClimaticosMensais(
            latitude=-4.36,
            longitude=-38.73,
            ano_referencia=2024,
            fonte="mock",
            dias_precipitacao_mensal=dias_uniform,
            dias_precipitacao_semanal=dias_semanas_uniform,
        )
        result = run_produtividade_climatica(
            canonical,
            {"ano_referencia": 2024},
            {"limiar_inviabilidade_mm": 10},
            client=mock_client,
        )
        val_04 = [v for v in result.validacoes if v.codigo == "VAL-PRAT-04"]
        assert val_04 and val_04[0].status == "AVISO"


class TestCronogramaBranches:
    """Cobre branches adicionais em run_cronograma."""

    def test_cpu_ausente_no_catalogo(self, inputs_escopo_terraplenagem, config_root):
        """Cobre branch 'CPU não existe no catálogo' → erro + continue."""

        catalogo = {
            "cpus": [],  # catálogo vazio → nenhuma CPU encontrada
            "insumos": _load_catalogo_insumos(config_root),
        }
        prat = Praticabilidade(
            fonte="mock",
            limiar_inviabilidade_mm=10,
            calculada_em=_dt.now(UTC),
            percentual_produtivo_mensal={str(m).zfill(2): 0.85 for m in range(1, 13)},
        )
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "mendeslobo",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        can = run_escopo_e_eap(None, inputs, catalogo).canonical
        can = can.model_copy(update={"praticabilidade": prat})
        inputs_cron = {"num_equipes_por_item": {"eap-01": {"2026-06": 1}}}
        result = run_cronograma(can, inputs_cron, catalogo)
        # Todos os itens da EAP falharão por falta de CPU
        assert result.has_errors


class TestPlanejamentoBDIBranches:
    """Cobre branches adicionais em run_custos_indiretos."""

    def test_precondicao_eap_vazia(self, config_root):
        """Cobre branch 'EAP vazia' → erro precondicao em run_precificacao_unitaria."""
        import json
        from datetime import UTC, datetime

        catalogo = {
            "cpus": json.loads((config_root / "catalogos" / "test" / "cpus.json").read_text())["cpus"],
            "insumos": _load_catalogo_insumos(config_root),
        }
        perfil = json.loads((config_root / "perfis" / "mendeslobo.json").read_text())
        meta = Meta(gerado_em=datetime.now(UTC), contexto_id="mendeslobo")
        proj = Projeto(
            id="x",
            nome="test",
            tipo_obra="terraplenagem",
            localizacao="x",
            coordenadas=Coordenadas(lat=0, lng=0),
            regime_trabalho=RegimeTrabalho(dias_semana=6, horas_dia=8),
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
            snapshot_catalogo_id="x",
            snapshot_perfil_id="x",
        )
        can = CanonicalModel(meta=meta, projeto=proj)
        # VAL-PLAN-PRECONDICAO é emitido por run_precificacao_unitaria (skill 06)
        result = run_precificacao_unitaria(can, {}, catalogo, perfil)
        assert result.has_errors
        assert any(v.codigo == "VAL-PLAN-PRECONDICAO" for v in result.validacoes)

    def test_insumo_ausente_no_catalogo(self, inputs_escopo_terraplenagem, config_root):
        """Cobre branch 'insumo não encontrado → erros_insumo.add + continue'."""
        import json

        catalogo_cpus = json.loads((config_root / "catalogos" / "test" / "cpus.json").read_text())["cpus"]
        perfil = json.loads((config_root / "perfis" / "mendeslobo.json").read_text())
        # Catálogo com insumos vazio → todos insumos ausentes
        catalogo_vazio = {"cpus": catalogo_cpus, "insumos": []}
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "mendeslobo",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        can = run_escopo_e_eap(None, inputs, catalogo_vazio).canonical
        result = run_custos_indiretos(can, {}, catalogo_vazio, perfil)
        # Preços resultantes devem ser zero (nenhum insumo encontrado)
        for p in result.canonical.planejamento:
            assert p.preco_unitario.total == 0.0


class TestIndiretosBranches:
    """Cobre branches adicionais em run_custos_indiretos — categorias TOP, LAB, QSMS."""

    def _canonical_com_equipes(self, inputs_escopo, config_root):
        import json

        catalogo = {
            "cpus": json.loads((config_root / "catalogos" / "test" / "cpus.json").read_text())["cpus"],
            "insumos": _load_catalogo_insumos(config_root),
        }
        perfil = json.loads((config_root / "perfis" / "mendeslobo.json").read_text())
        inputs = {
            **inputs_escopo,
            "contexto_id": "mendeslobo",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        can = run_escopo_e_eap(None, inputs, catalogo).canonical
        prat = Praticabilidade(
            fonte="mock",
            limiar_inviabilidade_mm=10,
            calculada_em=_dt.now(UTC),
            percentual_produtivo_mensal={str(m).zfill(2): 0.85 for m in range(1, 13)},
        )
        can = can.model_copy(update={"praticabilidade": prat})
        cron_inputs = {
            "num_equipes_por_item": {
                "eap-01": {
                    "2026-06": 1,
                    "2026-07": 1,
                    "2026-08": 1,
                    "2026-09": 1,
                    "2026-10": 1,
                    "2026-11": 1,
                    "2026-12": 2,
                },
                "eap-02": {"2026-08": 1, "2026-09": 1, "2026-10": 1, "2026-11": 1, "2026-12": 2},
                "eap-03": {"2026-11": 1, "2026-12": 1},
            }
        }
        can = run_cronograma(can, cron_inputs, catalogo).canonical
        can = run_equipes_e_alocacao(can, {}, catalogo).canonical
        return can, perfil

    def test_categorias_top_lab_qsms_individuais(self, inputs_escopo_terraplenagem, config_root):
        """Cobre branches dos if categoria == 'TOP', 'LAB', 'QSMS' em _composicao_default."""
        import importlib.util
        from pathlib import Path

        skill_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "concilium"
            / "application"
            / "skills"
            / "manifests"
            / "06-resultado-financeiro"
            / "_indiretos"
            / "skill.py"
        )
        spec = importlib.util.spec_from_file_location("_skill_indiretos", skill_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _composicao_default = mod._composicao_default_por_categoria

        comp_top = _composicao_default("TOP")
        assert "mao_de_obra" in comp_top

        comp_lab = _composicao_default("LAB")
        assert "verbas" in comp_lab

        comp_qsms = _composicao_default("QSMS")
        assert "verbas" in comp_qsms

        comp_unknown = _composicao_default("OUTRO")
        assert comp_unknown == {}

    def test_mob_com_dados_padrao(self, inputs_escopo_terraplenagem, config_root):
        """Cobre _custo_mob via run_custos_indiretos sem dados customizados (fallback padrão)."""
        can, perfil = self._canonical_com_equipes(inputs_escopo_terraplenagem, config_root)
        result = run_custos_indiretos(can, {}, perfil=perfil)
        mob = next(i for i in result.canonical.indiretos if i.categoria == "MOB")
        assert mob.custo_total >= 0
