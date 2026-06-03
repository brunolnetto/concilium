"""
Enriquece o referencia.json do benchmark AGIS com composições detalhadas
dos times indiretos (ADM, TOP, LAB, QSMS) extraídas da planilha XLSM.

Fontes:
  ABA ADM:  45 pessoas, MO R$448.860,63 + EQ R$268.330,57 + Verbas mensais
  ABA TOP:   5 pessoas, MO R$ 64.670,34 + EQ R$ 15.146,67 + Verbas R$ 3.000
  ABA LAB:   1 pessoa,  MO R$ 10.847,25 (sem EQ)
  ABA QSMS:  3 pessoas, MO R$ 34.050,00 + EQ R$ 15.146,67 + Verbas R$ 8.220
"""
import io, json, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
REF  = ROOT / "benchmarks/data/AGIS/referencia.json"

data = json.loads(REF.read_text(encoding="utf-8"))
PERM = 12.566666  # meses de permanência (377 dias / 30 = 12,57)

# ── Composições dos times indiretos (extraídas do XLSM) ──────────────────────

EQUIPES_INDIRETAS = [
    {
        "id": "INDIR-ADM",
        "nome": "ADMINISTRAÇÃO",
        "categoria": "ADM",
        "permanencia_meses": PERM,
        "custo_fixo_mensal": 1175935.55,
        "custo_total": 14777590.04,
        "mao_obra": [
            {"codigo": "P0013",  "funcao": "ADMINISTRATIVO",                  "quantidade": 1,  "salario_base": 10000.00, "horas_extras_mensal": 0,       "encargos_pct": 0,        "custo_unitario": 10000.00, "tipo_contratacao": "PJ"},
            {"codigo": "P0006",  "funcao": "AUXILIAR ADMINISTRATIVO",         "quantidade": 3,  "salario_base": 3358.08,  "horas_extras_mensal": 839.52,  "encargos_pct": 2561.52,  "custo_unitario": 6759.12},
            {"codigo": "P0003",  "funcao": "ALMOXARIFE",                      "quantidade": 1,  "salario_base": 3078.24,  "horas_extras_mensal": 769.56,  "encargos_pct": 2347.16,  "custo_unitario": 6194.96},
            {"codigo": "P0007",  "funcao": "AUXILIAR DE ALMOXARIFE",          "quantidade": 1,  "salario_base": 2217.60,  "horas_extras_mensal": 554.40,  "encargos_pct": 1691.06,  "custo_unitario": 4463.06},
            {"codigo": "P0027",  "funcao": "GERENTE DE CONTRATO",             "quantidade": 1,  "salario_base": 30000.00, "horas_extras_mensal": 0,       "encargos_pct": 0,        "custo_unitario": 30000.00, "tipo_contratacao": "PJ"},
            {"codigo": "P0075",  "funcao": "TÉCNICO DE PLANEJAMENTO",         "quantidade": 1,  "salario_base": 14000.00, "horas_extras_mensal": 0,       "encargos_pct": 0,        "custo_unitario": 14000.00, "tipo_contratacao": "PJ"},
            {"codigo": "P0018",  "funcao": "ENCARREGADO GERAL",               "quantidade": 2,  "salario_base": 18000.00, "horas_extras_mensal": 0,       "encargos_pct": 0,        "custo_unitario": 18000.00, "tipo_contratacao": "PJ"},
            {"codigo": "P0024",  "funcao": "ENGENHEIRO CIVIL",                "quantidade": 1,  "salario_base": 22000.00, "horas_extras_mensal": 0,       "encargos_pct": 0,        "custo_unitario": 22000.00, "tipo_contratacao": "PJ"},
            {"codigo": "P0073",  "funcao": "MECÂNICO",                        "quantidade": 2,  "salario_base": 7200.00,  "horas_extras_mensal": 1800.00, "encargos_pct": 5493.60,  "custo_unitario": 14493.60},
            {"codigo": "P0011",  "funcao": "AUXILIAR MECÂNICO",               "quantidade": 2,  "salario_base": 2217.60,  "horas_extras_mensal": 554.40,  "encargos_pct": 1691.06,  "custo_unitario": 4463.06},
            {"codigo": "P0086",  "funcao": "ENCARREGADO DE MECÂNICA",         "quantidade": 1,  "salario_base": 4485.36,  "horas_extras_mensal": 1121.34, "encargos_pct": 3420.46,  "custo_unitario": 9027.16},
            {"codigo": "P0014",  "funcao": "BORRACHEIRO",                     "quantidade": 2,  "salario_base": 3078.24,  "horas_extras_mensal": 769.56,  "encargos_pct": 2347.16,  "custo_unitario": 6194.96},
            {"codigo": "P0088",  "funcao": "AUXILIAR DE BORRACHEIRO",         "quantidade": 2,  "salario_base": 2217.60,  "horas_extras_mensal": 554.40,  "encargos_pct": 1691.06,  "custo_unitario": 4463.06},
            {"codigo": "P0087",  "funcao": "CONTROLADOR",                     "quantidade": 1,  "salario_base": 3960.00,  "horas_extras_mensal": 990.00,  "encargos_pct": 3020.40,  "custo_unitario": 7970.40},
            {"codigo": "P0034",  "funcao": "MOTORISTA DE CAMINHÃO COMBOIO",   "quantidade": 2,  "salario_base": 4001.71,  "horas_extras_mensal": 1000.43, "encargos_pct": 3051.31,  "custo_unitario": 8053.44},
            {"codigo": "P0001",  "funcao": "AJUDANTE",                        "quantidade": 2,  "salario_base": 2656.37,  "horas_extras_mensal": 664.09,  "encargos_pct": 2026.12,  "custo_unitario": 5346.58},
            {"codigo": "P0052",  "funcao": "OFICIAL",                         "quantidade": 1,  "salario_base": 3078.24,  "horas_extras_mensal": 769.56,  "encargos_pct": 2347.16,  "custo_unitario": 6194.96},
            {"codigo": "P0063",  "funcao": "AUXILIAR DE SERVIÇOS GERAIS",     "quantidade": 2,  "salario_base": 2043.36,  "horas_extras_mensal": 510.84,  "encargos_pct": 1558.06,  "custo_unitario": 4112.26},
            {"codigo": "P0072",  "funcao": "APONTADOR",                       "quantidade": 9,  "salario_base": 3078.24,  "horas_extras_mensal": 769.56,  "encargos_pct": 2347.16,  "custo_unitario": 6194.96},
            {"codigo": "P0089",  "funcao": "MOTORISTA DE CAMINHÃO PRANCHA",   "quantidade": 1,  "salario_base": 4002.24,  "horas_extras_mensal": 1000.56, "encargos_pct": 3051.71,  "custo_unitario": 8054.51},
            {"codigo": "P0036",  "funcao": "MOTORISTA DE ÔNIBUS",             "quantidade": 4,  "salario_base": 2656.50,  "horas_extras_mensal": 664.13,  "encargos_pct": 2026.09,  "custo_unitario": 5346.71},
            {"codigo": "PREFEITO","funcao": "PREFEITO DE ALOJAMENTO",         "quantidade": 3,  "salario_base": 4000.00,  "horas_extras_mensal": 1000.00, "encargos_pct": 3051.00,  "custo_unitario": 8051.00},
        ],
        "equipamentos": [
            {"codigo": "E0023", "tipo": "ÔNIBUS 52 PASSAGEIROS",   "quantidade": 4, "aluguel_mensal": 26000.0, "consumo_mes": 3600.0, "unidade_consumo": "KM", "combustivel": "S1"},
            {"codigo": "E0008", "tipo": "CAMINHÃO COMBOIO",        "quantidade": 2, "aluguel_mensal": 25000.0, "consumo_mes": 3600.0, "unidade_consumo": "KM", "combustivel": "S1"},
            {"codigo": "E0040", "tipo": "VEÍCULO PICAPE 4X4",      "quantidade": 1, "aluguel_mensal":  9000.0, "consumo_mes": 4800.0, "unidade_consumo": "KM", "combustivel": "S1"},
            {"codigo": "E0009", "tipo": "CAMINHÃO PRANCHA",        "quantidade": 1, "aluguel_mensal": 30000.0, "consumo_mes": 2400.0, "unidade_consumo": "KM", "combustivel": "S1"},
            {"codigo": "E0039", "tipo": "VEÍCULO LEVE",            "quantidade": 6, "aluguel_mensal":  4000.0, "consumo_mes": 4800.0, "unidade_consumo": "KM", "combustivel": "G"},
        ],
        "verbas_mensais": {
            "conteiner_banheiro": 3600.0,
            "conteiner_vestiario": 2000.0,
            "banheiro_quimico": 7200.0,
            "lavatório": 1300.0,
            "aluguel_conteiner": 8250.0,
            "alojamento": 148500.0,
            "energia_alojamento": 39600.0,
            "agua_alojamento": 19800.0,
            "vigilancia_armada": 60000.0,
            "agua_mineral": 34050.0,
            "_nota": "Verbas mensais do canteiro — ADM é responsável pelo canteiro central"
        },
        "_nota_planilha": "ABA ADM — PLANEJAMENTO_AGIS_LOTE09_10_CE_abr2026.xlsm",
        "_total_pessoas_mo": 45,
        "_custo_mo_total": 448860.63,
        "_custo_eq_total": 268330.57,
    },
    {
        "id": "INDIR-TOP",
        "nome": "TOPOGRAFIA",
        "categoria": "TOP",
        "permanencia_meses": PERM,
        "custo_fixo_mensal": 82817.01,
        "custo_total": 1040733.72,
        "mao_obra": [
            {"codigo": "P0057", "funcao": "TOPÓGRAFO",              "quantidade": 2, "salario_base": 18000.00, "horas_extras_mensal": 0,      "encargos_pct": 0,       "custo_unitario": 18000.00, "tipo_contratacao": "PJ"},
            {"codigo": "P0010", "funcao": "AUXILIAR DE TOPOGRAFIA", "quantidade": 2, "salario_base":  2217.60, "horas_extras_mensal": 554.40, "encargos_pct": 1691.06, "custo_unitario":  4463.06},
            {"codigo": "P0058", "funcao": "SALA TÉCNICA",           "quantidade": 1, "salario_base": 12000.00, "horas_extras_mensal": 0,      "encargos_pct": 0,       "custo_unitario": 12000.00, "tipo_contratacao": "PJ",
             "_nota": "P0058 = Sala Técnica: profissional de apoio técnico/planejamento de campo"},
            {"codigo": "P0001", "funcao": "AJUDANTE",               "quantidade": 1, "salario_base":  2043.36, "horas_extras_mensal": 510.84, "encargos_pct": 1558.06, "custo_unitario":  4112.26},
        ],
        "equipamentos": [
            {"codigo": "E0039", "tipo": "VEÍCULO LEVE", "quantidade": 2, "aluguel_mensal": 4000.0, "consumo_mes": 4800.0, "unidade_consumo": "KM", "combustivel": "G"},
        ],
        "verbas_mensais": {
            "estacas_topograficas": 3000.0,
            "_nota": "Material de campo para locação de eixo e pontos topográficos"
        },
        "_nota_planilha": "ABA TOP — PLANEJAMENTO_AGIS_LOTE09_10_CE_abr2026.xlsm",
        "_total_pessoas_mo": 5,
        "_custo_mo_total": 64670.34,
        "_custo_eq_total": 15146.67,
    },
    {
        "id": "INDIR-LAB",
        "nome": "LABORATÓRIO",
        "categoria": "LAB",
        "permanencia_meses": PERM,
        "custo_fixo_mensal": 10847.25,
        "custo_total": 136313.78,
        "mao_obra": [
            {"codigo": "P0030", "funcao": "LABORATORISTA", "quantidade": 1, "salario_base": 9000.00, "horas_extras_mensal": 0, "encargos_pct": 0, "custo_unitario": 9000.00, "tipo_contratacao": "PJ",
             "_nota": "P0030 = Laboratorista PJ: ensaios de compactação, CBR, granulometria"},
        ],
        "equipamentos": [],
        "verbas_mensais": {
            "alimentacao_cesta_basica": 1847.25,
            "_nota": "Sem equipamentos próprios — usa laboratório de campo do canteiro"
        },
        "_nota_planilha": "ABA LAB — PLANEJAMENTO_AGIS_LOTE09_10_CE_abr2026.xlsm",
        "_total_pessoas_mo": 1,
        "_custo_mo_total": 10847.25,
        "_custo_eq_total": 0.0,
        "_nota_melhoria": "Equipe mínima. Para projeto com maior volume, considerar Técnico de Lab CLT (P0009) adicional",
    },
    {
        "id": "INDIR-QSMS",
        "nome": "QSMS — QUALIDADE, SAÚDE, MEIO AMBIENTE E SEGURANÇA",
        "categoria": "QSMS",
        "permanencia_meses": PERM,
        "custo_fixo_mensal": 57416.67,
        "custo_total": 721536.11,
        "mao_obra": [
            {"codigo": "P0056", "funcao": "TÉCNICO DE SEGURANÇA DO TRABALHO", "quantidade": 2, "salario_base": 7500.00, "horas_extras_mensal": 0, "encargos_pct": 0, "custo_unitario": 7500.00, "tipo_contratacao": "PJ"},
            {"codigo": "P0002", "funcao": "AJUDANTE ESPECIALIZADO",           "quantidade": 1, "salario_base": 2217.60, "horas_extras_mensal": 554.40, "encargos_pct": 1691.06, "custo_unitario": 4463.06,
             "_nota": "Auxiliar de campo para QSMS — coleta de amostras, inspeção de EPI, registros"},
            {"codigo": "GERENTE-QSMS", "funcao": "GERENTE DE QSMS",           "quantidade": 1, "salario_base": 15000.00, "horas_extras_mensal": 0, "encargos_pct": 0, "custo_unitario": 15000.00, "tipo_contratacao": "PJ",
             "_nota": "Sem código P no catálogo atual — criar MO-GERENTE-QSMS. Responsável pelo PCA, PBA e PGRCC"},
        ],
        "equipamentos": [
            {"codigo": "E0039", "tipo": "VEÍCULO LEVE", "quantidade": 2, "aluguel_mensal": 4000.0, "consumo_mes": 4800.0, "unidade_consumo": "KM", "combustivel": "G"},
        ],
        "verbas_mensais": {
            "sinalizacao_viaria": 8220.0,
            "_nota": "Sinalização de canteiro, desvios e faixas de obra — obrigatória pelo DNIT"
        },
        "_nota_planilha": "ABA QSMS — PLANEJAMENTO_AGIS_LOTE09_10_CE_abr2026.xlsm",
        "_total_pessoas_mo": 3,
        "_custo_mo_total": 34050.0,
        "_custo_eq_total": 15146.67,
        "_lacunas_identificadas": [
            "Biólogo e Botânico mencionados na planilha sem código P definido — presença sazonal (supressão vegetal)",
            "Gerente QSMS sem código P no catálogo — necessário criar MO-GERENTE-QSMS",
            "PGRCC (Plano de Resíduos) requer profissional habilitado — pode ser o Gerente QSMS"
        ]
    },
]

# Atualiza o JSON
# Enriquece indiretos_detalhamento com as composições
for eq in EQUIPES_INDIRETAS:
    cat = eq["categoria"]
    if cat in data.get("indiretos_detalhamento", {}):
        data["indiretos_detalhamento"][cat]["composicao_equipe"] = {
            "id_equipe": eq["id"],
            "mao_obra": eq["mao_obra"],
            "equipamentos": eq["equipamentos"],
            "verbas_mensais": eq.get("verbas_mensais", {}),
            "total_pessoas": eq["_total_pessoas_mo"],
            "custo_mo_mensal": eq["_custo_mo_total"],
            "custo_eq_mensal": eq["_custo_eq_total"],
            "permanencia_meses": eq["permanencia_meses"],
            "_fonte": eq.get("_nota_planilha", ""),
        }
        # Recalcula custo_fixo_mensal_total para conferência
        data["indiretos_detalhamento"][cat]["custo_fixo_mensal_calculado"] = eq["custo_fixo_mensal"]
        data["indiretos_detalhamento"][cat]["custo_total_calculado"] = eq["custo_total"]
        if "_lacunas_identificadas" in eq:
            data["indiretos_detalhamento"][cat]["lacunas_identificadas"] = eq["_lacunas_identificadas"]

# Adiciona campo equipes_indiretas no topo (referência completa para benchmark)
data["equipes_indiretas"] = EQUIPES_INDIRETAS

REF.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
print("referencia.json atualizado com composições de times indiretos.")

# Sumário
for eq in EQUIPES_INDIRETAS:
    n = eq["_total_pessoas_mo"]
    mo = eq["_custo_mo_total"]
    eq_ = eq["_custo_eq_total"]
    vb = sum(v for k, v in eq.get("verbas_mensais", {}).items() if not k.startswith("_"))
    total = mo + eq_ + vb
    print(f"  {eq['categoria']:5} | {n:2d} pessoas | MO={mo:>12,.2f} | EQ={eq_:>10,.2f} | VB={vb:>10,.2f} | TOTAL={total:>12,.2f}/mês")
