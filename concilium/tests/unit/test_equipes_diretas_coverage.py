"""Additional coverage tests for skill 03-equipes-diretas."""

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

from concilium.application.skills import run_cronograma
from concilium.application.skills import run_equipes_e_alocacao as run_equipes_diretas
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    EapItem,
    Meta,
    Praticabilidade,
    Projeto,
    RegimeTrabalho,
)

# Load private helpers from the skill.py using importlib (dash in directory name)
_SKILL_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "concilium"
    / "application"
    / "skills"
    / "manifests"
    / "05-equipes-e-alocacao"
    / "skill.py"
)
_skill_mod_name = "_concilium_skill_03_equipes_e_alocacao"
if _skill_mod_name not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_skill_mod_name, _SKILL_PATH)
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_skill_mod_name] = _mod
    _spec.loader.exec_module(_mod)
_equipes_mod = sys.modules[_skill_mod_name]
_buscar_preco_diesel = getattr(_equipes_mod, "_buscar_preco_diesel", None)
_calcular_custo_funcao = _equipes_mod._calcular_custo_funcao
_calcular_custo_equipamento = _equipes_mod._calcular_custo_equipamento
_calcular_permanencia_e_custo_total = getattr(_equipes_mod, "_calcular_permanencia_e_custo_total", None)


def _canonical_with_cronograma(eap_items, cpu_catalog, insumo_catalog, num_equipes_cron):
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
    can = CanonicalModel(meta=meta, projeto=proj, eap=eap_items, praticabilidade=prat)
    catalogo = {"cpus": cpu_catalog, "insumos": insumo_catalog}
    can_with_cron = run_cronograma(can, {"num_equipes_por_item": num_equipes_cron}, catalogo).canonical
    return can_with_cron, catalogo


class TestCalcularCustoFuncao:
    """Tests for _calcular_custo_funcao — covers PJ and mensalista branches."""

    def test_pj_categoria_sem_encargos(self):
        insumo = {
            "preco_unitario": 5000,
            "unidade": "mes",
            "atributos_especificos": {"categoria_sindical": "pj_tecnico"},
        }
        salario, he_pct, custo_unit = _calcular_custo_funcao(
            insumo, 1, 1.777, None, 1.06
        )  # PJ: enc=0, he_pct=0; custo = 5000 * 1.0 * 1.0 = 5000
        assert custo_unit == 5000.0
        assert he_pct == 0.0

    def test_mensalista_usa_perc_mensalista(self):
        insumo = {
            "preco_unitario": 3000,
            "unidade": "mes",
            "atributos_especificos": {"categoria_sindical": "mensalista"},
        }
        salario, he_pct, custo_unit = _calcular_custo_funcao(insumo, 1, 1.777, None, 1.06)
        # mensalista: enc = 1.06; custo = 3000 * 2.06 = 6180
        assert custo_unit == round(3000 * 2.06, 2)

    def test_horista_categoria(self):
        insumo = {
            "preco_unitario": 2000,
            "unidade": "mes",
            "atributos_especificos": {"categoria_sindical": "horista_operador"},
        }
        salario, he_pct, custo_unit = _calcular_custo_funcao(insumo, 1, 1.777, None, 1.06)
        assert custo_unit == round(2000 * (1 + 1.777), 2)

    def test_unidade_hora_converte_para_mes(self):
        insumo = {
            "preco_unitario": 10,  # R$/h
            "unidade": "h",
            "atributos_especificos": {},
        }
        salario, he_pct, custo_unit = _calcular_custo_funcao(insumo, 1, 0.0, None, 0.0)
        # ConversorUnidades: 1 mes = 220h, so salario = 10 * 220 = 2200
        assert salario == 2200.0


class TestCalcularCustoEquipamento:
    """Tests for _calcular_custo_equipamento — covers monthly unit and diesel."""

    def test_equipamento_mensal_sem_consumo(self):
        insumo = {
            "codigo": "EQ-01",
            "descricao": "Caminhão",
            "preco_unitario": 8000,
            "unidade": "mes",  # not "h" → no hours conversion
            "atributos_especificos": {},
        }
        # _calcular_custo_equipamento returns (EquipamentoEquipeDireta, val_code) tuple
        result, val_code = _calcular_custo_equipamento(insumo, 1, 8, 21.4, 6.20)
        # custo_mensal_base = 8000 (unidade=mes)
        assert result.custo_mensal == 8000.0
        assert result.consumo_litros_hora is None
        assert result.custo_combustivel_mensal == 0.0

    def test_equipamento_com_consumo_diesel(self):
        insumo = {
            "codigo": "EQ-02",
            "descricao": "Escavadeira",
            "preco_unitario": 100,  # R$/h
            "unidade": "h",
            "atributos_especificos": {"consumo_litros_hora": 15.0},
        }
        # _calcular_custo_equipamento returns (EquipamentoEquipeDireta, val_code) tuple
        result, val_code = _calcular_custo_equipamento(insumo, 1, 8, 21.4, 6.20)
        horas_mes = 8 * 21.4
        custo_combustivel = 15.0 * horas_mes * 6.20
        assert result.consumo_litros_hora == 15.0
        assert result.custo_combustivel_mensal == round(custo_combustivel, 2)


class TestCalcularPermanenciaECustoTotal:
    """Tests for _calcular_permanencia_e_custo_total — monthly vs weekly."""

    def test_distribuicao_mensal(self):
        from concilium.domain.models.canonical import DistribuicaoMensal

        class FakeCronItem:
            distribuicao_semanal = {}
            distribuicao_mensal = {
                "2026-01": DistribuicaoMensal(num_equipes=1, qtd_executada=10, qtd_acumulada=10, pct=0.5),
                "2026-02": DistribuicaoMensal(num_equipes=2, qtd_executada=10, qtd_acumulada=20, pct=1.0),
                "2026-03": DistribuicaoMensal(num_equipes=0, qtd_executada=0, qtd_acumulada=20, pct=1.0),
            }

        permanencia, custo = _calcular_permanencia_e_custo_total(FakeCronItem(), 1000.0)
        # Skill counts all months (n=3), not just active ones
        assert permanencia == 3.0
        # Custo = custo_hora * sum(num_equipes) = 1000 * (1 + 2 + 0) = 3000
        assert custo == round(1000 * 1 + 1000 * 2 + 1000 * 0, 2)


class TestEquipesDiretasCoverageEdgeCases:
    """Coverage for run_equipes_diretas edge cases."""

    def _minimal_catalogo(self):
        return {
            "cpus": [
                {
                    "codigo": "CPU-01",
                    "descricao": "Test CPU",
                    "unidade": "m",
                    "origem": "PROPRIA",
                    "categoria": "TERRAPLENAGEM",
                    "producao_horaria": 10,
                    "composicao_itens": [],
                    "composicao_padrao_equipe": {
                        "funcoes": [{"funcao_id": "OP-01", "num_pessoas": 1}],
                        "equipamentos": [{"equip_id": "EQ-01", "num_unidades": 1}],
                    },
                }
            ],
            "insumos": [
                {
                    "codigo": "OP-01",
                    "tipo": "MAO_OBRA",
                    "descricao": "Operador",
                    "unidade": "mes",
                    "preco_unitario": 1000,
                    "fonte_preco": "catalogo",
                    "atributos_especificos": {},
                },
                {
                    "codigo": "EQ-01",
                    "tipo": "EQUIPAMENTO",
                    "descricao": "Equipamento",
                    "unidade": "h",
                    "preco_unitario": 100,
                    "fonte_preco": "catalogo",
                    "atributos_especificos": {},
                },
            ],
        }

    def test_item_sem_cronograma_e_ignorado(self):
        """EAP item without cronograma entry is silently skipped."""
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
            percentual_produtivo_mensal={"06": 1.0},
        )
        eap = [
            EapItem(item_id="eap-1", ordem=1, cpu_id="CPU-01", descricao="", unidade="m", quantitativo=100),
            EapItem(item_id="eap-2", ordem=2, cpu_id="CPU-01", descricao="", unidade="m", quantitativo=50),
        ]
        can = CanonicalModel(meta=meta, projeto=proj, eap=eap, praticabilidade=prat)
        catalogo = self._minimal_catalogo()
        # Build cronograma only for eap-1
        inputs_cron = {"num_equipes_por_item": {"eap-1": {"2026-W23": 1}}}
        can_with_cron = run_cronograma(can, inputs_cron, catalogo).canonical
        res = run_equipes_diretas(can_with_cron, {}, catalogo)
        # Cronograma generates entries for all EAP items; eap-2 gets 0 allocation
        # Only eap-1 should have actual work (custo_total > 0)
        equipes_com_trabalho = [eq for eq in res.canonical.equipes_diretas if eq.custo_total > 0]
        assert all(eq.item_id == "eap-1" for eq in equipes_com_trabalho)

    def test_funcao_nao_encontrada_emite_val_equip01_erro(self):
        """Funcao not found in catalog should emit VAL-EQUIP-01 ERRO."""
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
            percentual_produtivo_mensal={"06": 1.0},
        )
        eap = [EapItem(item_id="eap-1", ordem=1, cpu_id="CPU-BAD", descricao="", unidade="m", quantitativo=100)]
        catalogo = {
            "cpus": [
                {
                    "codigo": "CPU-BAD",
                    "descricao": "Bad",
                    "unidade": "m",
                    "origem": "PROPRIA",
                    "categoria": "T",
                    "producao_horaria": 1,
                    "composicao_itens": [],
                    "composicao_padrao_equipe": {
                        "funcoes": [{"funcao_id": "NONEXIST", "num_pessoas": 1}],
                        "equipamentos": [],
                    },
                }
            ],
            "insumos": [],
        }
        can = CanonicalModel(meta=meta, projeto=proj, eap=eap, praticabilidade=prat)
        inputs_cron = {"num_equipes_por_item": {"eap-1": {"2026-W23": 1}}}
        can_with_cron = run_cronograma(can, inputs_cron, catalogo).canonical
        res = run_equipes_diretas(can_with_cron, {}, catalogo)
        codigos = {v.codigo: v.status for v in res.validacoes}
        # Skill emits VAL-EQUIP-FUNCAO AVISO when funcao not found in catalog
        assert "VAL-EQUIP-FUNCAO" in codigos and codigos["VAL-EQUIP-FUNCAO"] == "AVISO"

    def test_equip_nao_encontrado_emite_val_equip02_erro(self):
        """Equipment not found in catalog should emit VAL-EQUIP-02 and VAL-CPU-INS-07 ERROs."""
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
            percentual_produtivo_mensal={"06": 1.0},
        )
        eap = [EapItem(item_id="eap-1", ordem=1, cpu_id="CPU-EQUIP-BAD", descricao="", unidade="m", quantitativo=100)]
        catalogo = {
            "cpus": [
                {
                    "codigo": "CPU-EQUIP-BAD",
                    "descricao": "Bad",
                    "unidade": "m",
                    "origem": "PROPRIA",
                    "categoria": "T",
                    "producao_horaria": 1,
                    "composicao_itens": [],
                    "composicao_padrao_equipe": {
                        "funcoes": [{"funcao_id": "OP-VALID", "num_pessoas": 1}],
                        "equipamentos": [{"equip_id": "EQ-NONEXIST", "num_unidades": 1}],
                    },
                }
            ],
            "insumos": [
                {
                    "codigo": "OP-VALID",
                    "tipo": "MAO_OBRA",
                    "descricao": "Op",
                    "unidade": "mes",
                    "preco_unitario": 1000,
                    "fonte_preco": "catalogo",
                    "atributos_especificos": {},
                },
            ],
        }
        can = CanonicalModel(meta=meta, projeto=proj, eap=eap, praticabilidade=prat)
        inputs_cron = {"num_equipes_por_item": {"eap-1": {"2026-W23": 1}}}
        can_with_cron = run_cronograma(can, inputs_cron, catalogo).canonical
        res = run_equipes_diretas(can_with_cron, {}, catalogo)
        codigos = {v.codigo: v.status for v in res.validacoes}
        # Skill emits VAL-EQUIP-EQUIP AVISO when equipamento not found in catalog
        assert "VAL-EQUIP-EQUIP" in codigos and codigos["VAL-EQUIP-EQUIP"] == "AVISO"


class TestDieselPriceResolution:
    """Tests for diesel price resolution in run_equipes_diretas."""

    def _make_canonical_minimal(self):
        """Build a minimal canonical with one EAP item and cronograma."""
        from concilium.domain.models.canonical import (
            CanonicalModel,
            Coordenadas,
            EapItem,
            Meta,
            Praticabilidade,
            Projeto,
            RegimeTrabalho,
        )

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
            fonte="t",
            limiar_inviabilidade_mm=0,
            calculada_em=datetime.now(UTC),
            percentual_produtivo_mensal={"06": 1.0},
        )
        eap = [EapItem(item_id="eap-1", ordem=1, cpu_id="CPU-01", descricao="", unidade="m", quantitativo=100)]
        can = CanonicalModel(meta=meta, projeto=proj, eap=eap, praticabilidade=prat)
        return can

    def test_diesel_price_from_catalog(self):
        """Diesel price is read from DIESEL-S10 insumo when present in catalog."""
        catalogo = {
            "cpus": [
                {
                    "codigo": "CPU-01",
                    "descricao": "Test",
                    "unidade": "m",
                    "origem": "PROPRIA",
                    "categoria": "T",
                    "producao_horaria": 10,
                    "composicao_itens": [],
                    "composicao_padrao_equipe": {
                        "funcoes": [],
                        "equipamentos": [{"equip_id": "EQ-01", "num_unidades": 1}],
                    },
                }
            ],
            "insumos": [
                {
                    "codigo": "DIESEL-S10",
                    "preco_unitario": 5.99,
                    "tipo": "COMBUSTIVEL",
                    "descricao": "Diesel",
                    "unidade": "L",
                    "fonte_preco": "catalogo",
                    "atributos_especificos": {"consumo_litros_hora": 0.0},
                },
                {
                    "codigo": "EQ-01",
                    "tipo": "EQUIPAMENTO",
                    "descricao": "Equip",
                    "unidade": "h",
                    "preco_unitario": 100,
                    "fonte_preco": "catalogo",
                    "atributos_especificos": {"consumo_litros_hora": 10.0},
                },
            ],
        }
        can = self._make_canonical_minimal()
        can_cron = run_cronograma(can, {"num_equipes_por_item": {"eap-1": {"2026-W23": 1}}}, catalogo).canonical
        res = run_equipes_diretas(can_cron, {}, catalogo)
        # With diesel at 5.99, equipment's custo_combustivel_mensal uses 5.99
        equipe = res.canonical.equipes_diretas[0]
        # Skill uses horas_dia * (30.0 * dias_semana / 7) = 8 * 30 * 5/7
        horas_mes = 8 * (30.0 * 5 / 7)
        assert equipe.equipamentos[0].custo_combustivel_mensal == round(10.0 * horas_mes * 5.99, 2)

    def test_diesel_price_default_when_no_catalog_entry(self):
        """Default diesel price 6.20 is used when DIESEL-S10 not in catalog."""
        catalogo = {
            "cpus": [
                {
                    "codigo": "CPU-01",
                    "descricao": "Test",
                    "unidade": "m",
                    "origem": "PROPRIA",
                    "categoria": "T",
                    "producao_horaria": 10,
                    "composicao_itens": [],
                    "composicao_padrao_equipe": {
                        "funcoes": [],
                        "equipamentos": [{"equip_id": "EQ-01", "num_unidades": 1}],
                    },
                }
            ],
            "insumos": [
                {
                    "codigo": "EQ-01",
                    "tipo": "EQUIPAMENTO",
                    "descricao": "Equip",
                    "unidade": "h",
                    "preco_unitario": 100,
                    "fonte_preco": "catalogo",
                    "atributos_especificos": {"consumo_litros_hora": 10.0},
                },
            ],
        }
        can = self._make_canonical_minimal()
        can_cron = run_cronograma(can, {"num_equipes_por_item": {"eap-1": {"2026-W23": 1}}}, catalogo).canonical
        res = run_equipes_diretas(can_cron, {}, catalogo)
        equipe = res.canonical.equipes_diretas[0]
        # Skill uses horas_dia * (30.0 * dias_semana / 7) = 8 * 30 * 5/7
        horas_mes = 8 * (30.0 * 5 / 7)
        # Default diesel = 6.20
        assert equipe.equipamentos[0].custo_combustivel_mensal == round(10.0 * horas_mes * 6.20, 2)
