"""NEP-029 D2: derivação canônica de P_i = custo_hora_equipe / PU_sbdi.

Garante que P_engine = P_catalog por construção:
    custo_direto_engine = custo_hora × Q / P_canonico = PU_sbdi × Q
    fe_nec → 1/η_p  (apenas clima, sem resíduo de base)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SKILL = Path(__file__).parent.parent.parent / "src/concilium/application/skills/manifests/04-cronograma/skill.py"


def _load_skill() -> object:
    spec = importlib.util.spec_from_file_location("_cron_nep029", _SKILL)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_cron_nep029"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_s = _load_skill()


# ── _custo_hora_equipe ────────────────────────────────────────────────────────

INSUMOS = {
    # MO mensal — encargos aplicados (100%)
    "MO-OP": {"codigo": "MO-OP", "tipo": "MAO_OBRA", "preco_unitario": 4000.0, "unidade": "mes"},
    # MO horária AGIS — encargos JÁ INCLUÍDOS (não duplicar)
    "MO-AGIS": {
        "codigo": "MO-AGIS",
        "tipo": "MAO_OBRA",
        "preco_unitario": 42.70,
        "unidade": "h",
        "atributos_especificos": {"nota": "Taxa horária já inclui encargos (convenção planilha AGIS)"},
    },
    "EQ-01": {"codigo": "EQ-01", "tipo": "EQUIPAMENTO", "preco_unitario": 100.0, "unidade": "h"},
    # Diesel com regionalização — deve usar preco_unitario (planilha), NÃO o regionalizado
    "MA-DIESEL-S10": {
        "codigo": "MA-DIESEL-S10",
        "tipo": "MATERIAL",
        "preco_unitario": 6.99,
        "unidade": "litro",
        "regionalizacao": [{"preco_unitario": 5.397}],
    },
}
HORAS_MES = 200.0
ENCARGOS = 1.0  # 100% — aplicado apenas a MO mensal; MO horária já inclui


class TestCustoHoraEquipe:
    def _comp(self, funcoes=None, equipamentos=None):
        return {"funcoes": funcoes or [], "equipamentos": equipamentos or []}

    def test_mo_mensal_aplica_encargos(self):
        # MO mensal (R$/mês) → converte para horária E aplica encargos
        comp = self._comp(funcoes=[{"funcao_id": "MO-OP", "num_pessoas": 2}])
        ch = _s._custo_hora_equipe(comp, INSUMOS, HORAS_MES, ENCARGOS)
        # 2 × (4000/200) × (1+1.0) = 2 × 20 × 2 = 80
        assert abs(ch - 80.0) < 1e-6

    def test_mo_horaria_agis_sem_encargos_duplicados(self):
        # MO horária AGIS com nota "já inclui encargos" → NÃO duplicar
        comp = self._comp(funcoes=[{"funcao_id": "MO-AGIS", "num_pessoas": 1}])
        ch = _s._custo_hora_equipe(comp, INSUMOS, HORAS_MES, ENCARGOS)
        # 1 × 42.70 × (1+0) = 42.70 (NÃO × 2)
        assert abs(ch - 42.70) < 1e-6

    def test_so_equipamento(self):
        comp = self._comp(equipamentos=[{"equip_id": "EQ-01", "num_unidades": 3}])
        ch = _s._custo_hora_equipe(comp, INSUMOS, HORAS_MES, ENCARGOS)
        assert abs(ch - 300.0) < 1e-6

    def test_diesel_usa_preco_unitario_nao_regionalizado(self):
        # diesel_ins tem preco_unitario=6.99 E regionalizacao=[5.397]
        # deve usar 6.99 (planilha), NÃO 5.397 (SICRO)
        comp = self._comp(equipamentos=[{"equip_id": "EQ-01", "num_unidades": 1, "consumo_litros_hora_estimado": 10.0}])
        ch = _s._custo_hora_equipe(comp, INSUMOS, HORAS_MES, ENCARGOS)
        # 100 (equip) + 1×10×6.99 = 169.9 (não 155 com 5.5)
        assert abs(ch - 169.9) < 1e-4

    def test_calibracao_agis_esc1cat_dmt2000(self):
        """Verifica que a composição ESC 1CAT DMT2000 reproduz o custo horário da planilha.

        Planilha (cpus.txt): A(equip)=1125.73 + B(MO_base)=345.93 + comb=304.07 = 1775.73 R$/h
        P_canonico = 1775.73 / 7.6583 = 231.9 ≈ 231.87 m³/h (C da planilha).
        """
        # Composição simplificada mas fiel: 1 Esc38T + 7 Cam14m³ + 1 Oper + 7 MotorBasc + 0.5 Encar + 1 Ajud
        insumos_agis = {
            "AGIS-E0015": {"preco_unitario": 268.40, "unidade": "h"},
            "AGIS-E0002": {"preco_unitario": 122.48, "unidade": "h"},
            "AGIS-FN-OPER-ESCAV": {
                "preco_unitario": 42.70,
                "unidade": "h",
                "atributos_especificos": {"nota": "Taxa horária já inclui encargos (convenção planilha AGIS)"},
            },
            "AGIS-FN-MOTOR-BASC": {
                "preco_unitario": 38.10,
                "unidade": "h",
                "atributos_especificos": {"nota": "Taxa horária já inclui encargos (convenção planilha AGIS)"},
            },
            "AGIS-FN-ENCAR": {
                "preco_unitario": 34.09,
                "unidade": "h",
                "atributos_especificos": {"nota": "Taxa horária já inclui encargos (convenção planilha AGIS)"},
            },
            "AGIS-FN-AJUD": {
                "preco_unitario": 19.45,
                "unidade": "h",
                "atributos_especificos": {"nota": "Taxa horária já inclui encargos (convenção planilha AGIS)"},
            },
            "MA-DIESEL-S10": {"preco_unitario": 6.99, "unidade": "litro"},
        }
        comp = {
            "funcoes": [
                {"funcao_id": "AGIS-FN-OPER-ESCAV", "num_pessoas": 1},
                {"funcao_id": "AGIS-FN-MOTOR-BASC", "num_pessoas": 7},
                {"funcao_id": "AGIS-FN-ENCAR", "num_pessoas": 0.5},
                {"funcao_id": "AGIS-FN-AJUD", "num_pessoas": 1},
            ],
            "equipamentos": [
                {"equip_id": "AGIS-E0015", "num_unidades": 1, "consumo_litros_hora": 26.0},
                {"equip_id": "AGIS-E0002", "num_unidades": 7, "consumo_litros_hora": 2.5},
            ],
        }
        ch = _s._custo_hora_equipe(comp, insumos_agis, 208.56, 1.0)
        # Planilha: 1125.73 + 345.93 + 304.07 = 1775.73
        assert abs(ch - 1775.73) < 1.0, f"custo_hora={ch:.2f} esperado≈1775.73"

    def test_custo_hora_referencia_overrides_composicao(self):
        """Se custo_hora_total_referencia está no registro, usa diretamente sem lookup."""
        comp = self._comp()  # vazio — não importa
        ch = _s._custo_hora_equipe(comp, {}, HORAS_MES, ENCARGOS, custo_hora_referencia=1775.73)
        assert abs(ch - 1775.73) < 1e-9
        # P_canonico ≈ 231.87 (C da planilha)
        pu_sbdi = 7.6583
        P_can = ch / pu_sbdi
        assert abs(P_can - 231.87) < 1.0, f"P_canonico={P_can:.2f} esperado≈231.87"

    def test_sem_insumos_retorna_zero(self):
        comp = self._comp(funcoes=[{"funcao_id": "MO-INEXISTENTE", "num_pessoas": 1}])
        ch = _s._custo_hora_equipe(comp, {}, HORAS_MES, ENCARGOS)
        assert ch == 0.0


# ── _enrich_producao_canonico ─────────────────────────────────────────────────


class TestEnrichProducaoCanonico:
    def _setup(self, pu_sbdi: float, custo_hora_expected: float = None):
        """
        Monta cpu_lookup + producao_lookup com dados controlados.
        custo_hora_expected = 2 MO-OP × (4000/200) × 2 encargos + EQ-01 = 80 + 100 = 180 R$/h
        """
        comp = {
            "funcoes": [{"funcao_id": "MO-OP", "num_pessoas": 2}],
            "equipamentos": [{"equip_id": "EQ-01", "num_unidades": 1}],
        }
        cpu_lookup = {
            "CPU-X": {
                "codigo": "CPU-X",
                "producao_id_ref": "PROD-X",
                "precos_unitarios_sbdi": {
                    "total": pu_sbdi,
                    "mo": 0.5,
                    "diesel": 0.0,
                    "equipamentos": 0.5,
                    "material": 0.0,
                },
            }
        }
        producao_lookup = {
            "PROD-X": {
                "id": "PROD-X",
                "valor_horario": 100.0,  # "errado" — queremos substituir
                "composicao_padrao_equipe": comp,
            }
        }
        return cpu_lookup, producao_lookup

    def test_p_canonico_igual_custo_hora_sobre_pu(self):
        pu = 0.9  # R$/unidade
        # custo_hora = 2×(4000/200)×2 + 1×100 = 80 + 100 = 180
        cpu_lookup, prod_lookup = self._setup(pu)
        val = []
        _s._enrich_producao_canonico(cpu_lookup, prod_lookup, INSUMOS, HORAS_MES, ENCARGOS, val)
        P_can = prod_lookup["PROD-X"]["valor_horario_canonico"]
        custo_hora = 180.0
        assert abs(P_can - custo_hora / pu) < 1e-6

    def test_custo_engine_igual_catalogo(self):
        """
        Identidade fundamental: custo_hora × Q / P_canonico = PU_sbdi × Q
        i.e., custo direto engine = custo direto catálogo.
        """
        pu = 0.9
        Q = 50_000.0
        cpu_lookup, prod_lookup = self._setup(pu)
        _s._enrich_producao_canonico(cpu_lookup, prod_lookup, INSUMOS, HORAS_MES, ENCARGOS, [])
        P_can = prod_lookup["PROD-X"]["valor_horario_canonico"]
        custo_hora = 180.0
        custo_engine = custo_hora * Q / P_can  # = custo_hora × Q × pu / custo_hora = pu × Q
        custo_catalog = pu * Q
        assert abs(custo_engine - custo_catalog) < 1e-6

    def test_emite_val_prod_canonico(self):
        cpu_lookup, prod_lookup = self._setup(0.9)
        val = []
        _s._enrich_producao_canonico(cpu_lookup, prod_lookup, INSUMOS, HORAS_MES, ENCARGOS, val)
        assert any(v.codigo == "VAL-PROD-CANONICO" for v in val)

    def test_sem_pu_sbdi_nao_enriquece(self):
        cpu_lookup, prod_lookup = self._setup(pu_sbdi=0.0)
        _s._enrich_producao_canonico(cpu_lookup, prod_lookup, INSUMOS, HORAS_MES, ENCARGOS, [])
        assert "valor_horario_canonico" not in prod_lookup["PROD-X"]

    def test_ratio_extremo_nao_aplica_e_emite_inconsistencia(self):
        # PU_sbdi muito alto (87.26) vs custo_hora (180) → P_can=2.06, ratio=2.06/100=0.02
        # ratio < 0.5 → não aplica, emite VAL-PROD-INCONSISTENCIA
        cpu_lookup = {
            "CPU-Z": {
                "codigo": "CPU-Z",
                "producao_id_ref": "PROD-Z",
                "precos_unitarios_sbdi": {"total": 87.26},
            }
        }
        comp = {
            "funcoes": [{"funcao_id": "MO-OP", "num_pessoas": 2}],
            "equipamentos": [{"equip_id": "EQ-01", "num_unidades": 1}],
        }
        prod_lookup = {"PROD-Z": {"id": "PROD-Z", "valor_horario": 149.51, "composicao_padrao_equipe": comp}}
        val = []
        _s._enrich_producao_canonico(cpu_lookup, prod_lookup, INSUMOS, HORAS_MES, ENCARGOS, val)
        assert "valor_horario_canonico" not in prod_lookup["PROD-Z"]
        assert any(v.codigo == "VAL-PROD-INCONSISTENCIA" for v in val)

    def test_sem_composicao_nao_enriquece(self):
        cpu_lookup = {
            "CPU-Y": {
                "codigo": "CPU-Y",
                "producao_id_ref": "PROD-Y",
                "precos_unitarios_sbdi": {"total": 0.5},
            }
        }
        prod_lookup = {"PROD-Y": {"id": "PROD-Y", "valor_horario": 100.0}}  # sem composicao
        _s._enrich_producao_canonico(cpu_lookup, prod_lookup, INSUMOS, HORAS_MES, ENCARGOS, [])
        assert "valor_horario_canonico" not in prod_lookup["PROD-Y"]


# ── _resolve_productivity com canonico ────────────────────────────────────────


class TestResolveProdutividadeCanonica:
    def test_usa_valor_horario_para_scheduling(self):
        # _resolve_productivity usa valor_horario (não canonical) para scheduling.
        # valor_horario_canonico é diagnóstico — não afeta o scheduler.
        cpu = {"codigo": "CPU-Z", "producao_id_ref": "PROD-Z"}
        prod_lookup = {
            "PROD-Z": {
                "id": "PROD-Z",
                "valor_horario": 50.0,
                "valor_horario_canonico": 200.0,  # diagnóstico, não usado pelo scheduler
            }
        }
        P = _s._resolve_productivity(cpu, prod_lookup, [])
        assert P == 50.0  # scheduling usa valor_horario, não canonico

    def test_fallback_para_producao_horaria_quando_sem_valor_horario(self):
        cpu = {"codigo": "CPU-Z", "producao_id_ref": "PROD-Z"}
        prod_lookup = {"PROD-Z": {"id": "PROD-Z", "producao_horaria": 80.0}}
        P = _s._resolve_productivity(cpu, prod_lookup, [])
        assert P == 80.0


# ── Propriedade fe_nec = 1/η_p ────────────────────────────────────────────────


class TestFeNecEhInversoEtaP:
    """
    Com P_canonico, a única "ineficiência" esperada é o clima.
    fe_nec = custo_operacional / (PU_sbdi × Q) deve ser igual a 1/η_p.

    Simulamos: custo_operacional = custo_hora × permanencia
    permanencia = Q / (P_canonico × horas_mes × n_equipes)
    """

    def test_fe_nec_igual_1_sem_clima(self):
        pu = 1.0
        Q = 10_000.0
        custo_hora = 180.0
        P_can = custo_hora / pu
        permanencia_semanas = Q / (P_can * 8 * 5)  # h/dia × dias/sem
        custo_op = custo_hora * permanencia_semanas * 8 * 5  # simplified
        # custo_op = custo_hora × Q / P_can = pu × Q
        assert abs(custo_op - pu * Q) < 1e-4  # fe_nec = 1.0

    def test_fe_nec_igual_1_sobre_eta_p_com_clima(self):
        """
        Com clima η_p = 0.90, permanência aumenta para Q / (P_can × η_p):
            custo_op = custo_hora × Q / (P_can × η_p) = PU × Q / η_p
            fe_nec   = custo_op / (PU × Q)            = 1/η_p
        """
        pu = 1.0
        Q = 10_000.0
        eta_p = 0.90
        custo_hora = 180.0
        P_can = custo_hora / pu
        # Permanência aumenta por fator 1/η_p (horas produtivas reduzidas)
        permanencia_eff = Q / (P_can * eta_p)  # em unidades de tempo
        custo_op = custo_hora * permanencia_eff
        fe_nec = custo_op / (pu * Q)
        assert abs(fe_nec - 1.0 / eta_p) < 1e-9
