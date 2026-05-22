"""Constantes de domínio do Concilium (ADR-056 §T3+M1).

Fonte única de verdade para valores numéricos compartilhados entre skills e serviços.
Cada constante é derivada de seus componentes, tornando o cálculo auditável.

REGRA: skills leem estas constantes como default, mas aceitam override via inputs.
PROIBIDO: hardcodar estes valores em qualquer outro arquivo.

Fonte dos encargos: planilha rfi_catalog.xlsm (MendesLobo, vigência abril/2026).
Modelo Pydantic com validação completa: domain/models/bdi.py → DEFAULT_ENCARGOS.
"""

from __future__ import annotations

# ── Regime de trabalho (MendesLobo padrão: 6×1, 8h/dia) ──────────────────────

DIAS_SEMANA_PADRAO: int = 6  # dias úteis por semana no regime de obra (6×1)
HORAS_DIA_PADRAO: int = 8  # horas produtivas por dia

# ── Calendário ────────────────────────────────────────────────────────────────

# Semanas por mês: 365,25 / 7 / 12 = 4,3482...
# Usado para converter custo mensal de equipe → custo semanal (Skills 05, 08)
SEMANAS_POR_MES: float = 365.25 / 7 / 12  # ≈ 4,3482 semanas/mês

# Horas produtivas por mês no regime 6×8h:
#   6 dias/semana × 8 h/dia × (365,25/7/12 semanas/mês) ≈ 208 h/mês
# Usado em: Skills 05, 07, 08; pu_calculator; validador_pu_convergencia
HORAS_MES_REGIME_6x1: float = DIAS_SEMANA_PADRAO * HORAS_DIA_PADRAO * SEMANAS_POR_MES  # ≈ 208 h/mês

# Horas/mês CLT — convenção legal brasileira para contratação e precificação de MO:
#   44 h/semana × 5 semanas = 220 h/mês  (NR-6 / CLT art. 58 — convenção contábil)
# ATENÇÃO: usado para conversão de preços de mercado (R$/h → R$/mês) e verificação
# de plausibilidade de salários. NÃO usar em custo de projeto — regime obra = 6×8h.
HORAS_MES_CLT: float = 220.0  # h/mês — convenção CLT 44h/sem × 5 sem/mês

# ── Encargos sociais — Grupos A–F + Judicial (vigência abril/2026) ────────────
#
# Metodologia: encargos são aplicados sobre o salário base ANTES do BDI.
# Custo mensal total = salário_base × (1 + encargos_total)
#
# Referência normativa: MTE, INSS, FGTS, convenção coletiva SINTRACON-SP.
# Fonte dos valores: rfi_catalog.xlsm (MendesLobo, abril/2026) — tabela "Encargos".
# Modelo Pydantic auditável: domain/models/bdi.py → EncargosRegime + DEFAULT_ENCARGOS.
#
# ┌─────┬──────────────────────────────────────────────────────────┬─────────┬──────────┐
# │ Grp │ Descrição                                                │ Horist. │ Mensali. │
# ├─────┼──────────────────────────────────────────────────────────┼─────────┼──────────┤
# │  A  │ Básicos: INSS Emp. (20%), RAT (3%), Sal.Educ (2,5%),     │  37,80% │   37,80% │
# │     │ FGTS (8%), SEBRAE (0,6%), SENAI (1%), SESI (1,5%)        │         │          │
# │     │ INCRA (0,2%), SECONCI (1%), Contribuição Sindical (1,2%) │         │          │
# ├─────┼──────────────────────────────────────────────────────────┼─────────┼──────────┤
# │  B  │ Com incidência de A: férias (11,11%), abono férias       │  47,84% │    9,94% │
# │     │ (3,70%), 13º salário (8,33%), DSR (18,70%)               │         │          │
# │     │ Nota: horistas têm DSR alto; mensalistas não têm DSR     │         │          │
# ├─────┼──────────────────────────────────────────────────────────┼─────────┼──────────┤
# │  C  │ Sem incidência de A: aviso prévio (8,33%),               │  40,53% │   40,30% │
# │     │ multa FGTS rescisão (5%), indeniz. adicional (5%),       │         │          │
# │     │ salário substituto acidente/doença (18,33%),             │         │          │
# │     │ repouso remunerado dias parados (3,87%)                  │         │          │
# ├─────┼──────────────────────────────────────────────────────────┼─────────┼──────────┤
# │  D  │ Reincidências de B sobre C                               │  19,07% │    4,74% │
# ├─────┼──────────────────────────────────────────────────────────┼─────────┼──────────┤
# │  E  │ Seguros e benefícios: plano de saúde, seguro de vida,    │  10,22% │   10,22% │
# │     │ EPI, cesta básica (quando não computada em F)            │         │          │
# ├─────┼──────────────────────────────────────────────────────────┼─────────┼──────────┤
# │  F  │ Vale-transporte + vale-refeição (horistas de campo)      │  19,24% │    0,00% │
# │     │ Mensalistas: benefícios incluídos em pacote separado     │         │          │
# ├─────┼──────────────────────────────────────────────────────────┼─────────┼──────────┤
# │ Jud │ Provisão para despesas judiciais trabalhistas            │   3,00% │    3,00% │
# ├─────┼──────────────────────────────────────────────────────────┼─────────┼──────────┤
# │     │ TOTAL                                                    │ 177,70% │  106,00% │
# └─────┴──────────────────────────────────────────────────────────┴─────────┴──────────┘

# Grupo A — encargos básicos (idêntico para horistas e mensalistas)
_ENC_A_INSS_EMPRESA: float = 0.2000  # INSS patronal
_ENC_A_RAT: float = 0.0300  # Risco de Acidente de Trabalho (grau médio)
_ENC_A_SAL_EDUC: float = 0.0250  # Salário-educação
_ENC_A_FGTS: float = 0.0800  # FGTS
_ENC_A_TERCEIROS: float = 0.0430  # SEBRAE(0,6%) + SENAI(1%) + SESI(1,5%) + INCRA(0,2%) + SECONCI(1%)
_ENC_A_SIND: float = 0.0000  # Contribuição sindical (zerada desde 2017)
_ENC_A_TOTAL: float = round(
    _ENC_A_INSS_EMPRESA + _ENC_A_RAT + _ENC_A_SAL_EDUC + _ENC_A_FGTS + _ENC_A_TERCEIROS + _ENC_A_SIND, 4
)  # = 0.3780 = 37,80%

# Grupo B — com incidência de A (horistas: DSR alto por horas extras e turnos)
_ENC_B_HORISTA: float = 0.4784  # férias(11,11%) + abono(3,70%) + 13º(8,33%) + DSR(18,70%) + incid.A
_ENC_B_MENSALISTA: float = 0.0994  # férias(11,11%) + abono(3,70%) - sem DSR significativo

# Grupo C — sem incidência de A
_ENC_C_HORISTA: float = 0.4053
_ENC_C_MENSALISTA: float = 0.4030

# Grupo D — reincidências de B sobre C
_ENC_D_HORISTA: float = 0.1907
_ENC_D_MENSALISTA: float = 0.0474

# Grupo E — seguros e benefícios (idêntico)
_ENC_E_HORISTA: float = 0.1022
_ENC_E_MENSALISTA: float = 0.1022

# Grupo F — vale-transporte + vale-refeição (horistas de campo: sim; mensalistas: não)
_ENC_F_HORISTA: float = 0.1924
_ENC_F_MENSALISTA: float = 0.0000  # mensalistas recebem benefícios via pacote separado

# Judicial — provisão para passivo trabalhista
_ENC_JUDICIAL: float = 0.0300

# ── Totais derivados (usados pelas skills) ────────────────────────────────────

# Horista CLT — campo + obra: total 177,70%
ENCARGOS_CLT: float = round(
    _ENC_A_TOTAL + _ENC_B_HORISTA + _ENC_C_HORISTA + _ENC_D_HORISTA + _ENC_E_HORISTA + _ENC_F_HORISTA + _ENC_JUDICIAL,
    4,
)  # = 1.7770 ≈ 177,70%

# Mensalista CLT — gestão, administração, supervisão: total 106,00%
ENCARGOS_MENSALISTA: float = round(
    _ENC_A_TOTAL
    + _ENC_B_MENSALISTA
    + _ENC_C_MENSALISTA
    + _ENC_D_MENSALISTA
    + _ENC_E_MENSALISTA
    + _ENC_F_MENSALISTA
    + _ENC_JUDICIAL,
    4,
)  # = 1.0600 = 106,00%

# PJ — prestador de serviços pessoa jurídica
# Encargos estimados: ISS (~5%), contribuições mínimas (~1%).
# Não há breakdown padronizado — depende do regime tributário do PJ.
# Este valor é uma referência conservadora para orçamentação.
ENCARGOS_PJ: float = 0.06  # 6% sobre o valor do serviço (estimativa)

# ── Limites de plausibilidade de encargos (ADR-051) ──────────────────────────
# Fator mínimo/máximo de encargos sociais aceitável em dados de catálogo.
# custo_mensal = salário_base × alpha → alpha ∈ [ALPHA_MIN, ALPHA_MAX]
ALPHA_MIN_ENCARGOS: float = 1.0  # 100% — sem encargos (PJ puro)
ALPHA_MAX_ENCARGOS: float = 2.5  # 250% — encargos máximos observados em obras

# ── Salário mínimo (vigência 2025) ────────────────────────────────────────────
# Atualizar a cada reajuste do governo federal.
SALARIO_MINIMO_MENSAL: float = 1_518.0  # R$ — Portaria MTE nº 3.659/2024
SMH: float = SALARIO_MINIMO_MENSAL / HORAS_MES_CLT  # R$/h ≈ 6.90 (salário mínimo horário)

# ── Faixas de convergência de PU (ADR-051) ───────────────────────────────────
# Thresholds de desvio entre PU calculado pelo pipeline e PU do catálogo.
# Usado em validador_pu_catalogo.py e validador_pu_convergencia.py.
FAIXAS_CONVERGENCIA_PU: dict[str, float | None] = {
    "verde": 5.0,  # até 5% de desvio — convergência OK
    "amarelo": 10.0,  # 5% a 10% — atenção, verificar assumptions
    "vermelho": None,  # acima de 10% — divergência significativa
}

# ── Limites físicos de produtividade (plausibilidade) ────────────────────────
VH_MAX: float = 10_000.0  # un/h — limite técnico razoável de produtividade
VALIDADE_PRECO_DIAS: int = 180  # dados de preço com mais de N dias → stale


# ── Tributos no BDI — regime Pré-Reforma (Lucro Presumido, construção civil) ──
#
# Estas são TAXAS EFETIVAS SOBRE RECEITA (não alíquotas estatutárias sobre renda).
# Aplicam-se no DENOMINADOR da fórmula TCU: BDI = (1 + OH) / (1 - T) - 1
# Fonte: rfi_catalog.xlsm (MendesLobo, vigência abril/2026) — tabela "BDI".
#
# Distinção importante vs. ADR-055 (CBS/IBS):
#   Aqui: taxas EFETIVAS sobre receita → usadas diretamente no BDI
#   ADR-055: alíquotas ESTATUTÁRIAS sobre renda → requerem cálculo de base presumida
#
# ┌──────────────────────────────────────────────────────────────────────────────┐
# │ TRIBUTO     │ ALÍQUOTA │ BASE LEGAL                                          │
# ├─────────────┼──────────┼─────────────────────────────────────────────────────┤
# │ COFINS      │   3,00%  │ Lei 9.718/98 — cumulativo, construção civil         │
# │ ISS         │   5,00%  │ LC 116/2003 — alíquota máxima (varia por município) │
# │ PIS/PASEP   │   0,65%  │ Lei 9.718/98 — cumulativo, construção civil         │
# │ CSSL (CSLL) │   1,99%  │ 9% × ~22,1% (base presumida construção)            │
# │ IR (IRPJ)   │   2,74%  │ 15% × ~8% + adicional (base presumida Lucro Pres.) │
# ├─────────────┼──────────┼─────────────────────────────────────────────────────┤
# │ TOTAL T     │  13,38%  │ Fração do preço de venda destinada a tributos       │
# └──────────────────────────────────────────────────────────────────────────────┘
#
# MATERIAL não incide estes tributos (fornecimento de bens, não serviço).

BDI_COFINS: float = 0.0300  # 3,00% — COFINS cumulativo sobre receita bruta
BDI_ISS: float = 0.0500  # 5,00% — ISS máximo legal (construção civil)
BDI_PIS: float = 0.0065  # 0,65% — PIS/PASEP cumulativo sobre receita bruta
BDI_CSSL: float = 0.0199  # 1,99% — CSLL efetivo sobre receita (base presumida)
BDI_IR: float = 0.0274  # 2,74% — IRPJ efetivo sobre receita (Lucro Presumido)

# Tributos totais T = cofins + iss + pis + cssl + ir (denominador da fórmula TCU)
BDI_TRIBUTOS_PRE_REFORMA: float = round(BDI_COFINS + BDI_ISS + BDI_PIS + BDI_CSSL + BDI_IR, 6)
# = 0.1338 = 13,38%

# Material não incide ISS/COFINS/PIS em fornecimento puro — tributos zerados no BDI
BDI_TRIBUTOS_MATERIAL: float = 0.0


# ── Preço de referência de insumos de mercado ─────────────────────────────────
#
# Valores de referência para orçamentação. Devem ser atualizados a cada revisão
# periódica, da mesma forma que SALARIO_MINIMO_MENSAL.
# Fonte: ANP (diesel) — média nacional, vigência maio/2026.
PRECO_DIESEL_REFERENCIA: float = 6.50  # R$/litro — referência ANP maio/2026


# ── Limites de plausibilidade — equipamentos e consumo de diesel ──────────────
#
# Faixas físicas derivadas de ensaios de campo e literatura técnica (SICRO/DNIT).
# Usadas pelo validador de catálogo para detectar valores implausíveis em CPUs.
#
# Consumo específico de diesel por CV instalado (litros/hora por CV):
#   Faixa observada em equipamentos de terraplanagem: 0,18–0,32 l/h/CV
#   Ponto central (referência para interpolação): 0,245 l/h/CV
#   Tolerância de aceitação (fração do ponto central): ±50%
DIESEL_L_POR_CV_MIN: float = 0.18  # l/h/CV — limite inferior (equipamento eficiente)
DIESEL_L_POR_CV_MAX: float = 0.32  # l/h/CV — limite superior (equipamento convencional)
DIESEL_L_POR_CV_PONT: float = 0.245  # l/h/CV — ponto central de referência
DIESEL_TOLERANCIA: float = 0.50  # fração — janela de aceitação em torno do ponto central


# ── Limites estatísticos para detecção de outliers em catálogo ───────────────
#
# Z-score aplicado sobre a distribuição de preços de insumos similares.
# Valores acima de ZSCORE_EXTREMO são tratados como erros de entrada; entre
# ZSCORE_OUTLIER e ZSCORE_EXTREMO são marcados como aviso (revisão recomendada).
ZSCORE_OUTLIER: float = 2.5  # desvios-padrão — threshold de aviso (outlier leve)
ZSCORE_EXTREMO: float = 3.5  # desvios-padrão — threshold de erro (outlier severo)


# ── Limites financeiros de plausibilidade por item ────────────────────────────
#
# Margem mínima aceitável entre preço de venda (com BDI) e custo direto da equipe.
# Abaixo deste limiar o item apresenta risco financeiro e deve ser sinalizado.
# Referência: política de precificação MendesLobo (Revisão 2024).
MARGEM_MINIMA: float = 0.05  # 5 % — margem mínima sobre preço de venda por item
