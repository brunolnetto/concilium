"""Serviço de tributação individual — ADR-097 F5.

Cálculos de INSS empregado, IRRF e custo total do empregador CLT.
Usado para simulação People & Finance (não para custo de projeto —
para isso usar ENCARGOS_CLT / ENCARGOS_MENSALISTA diretamente).

Referências legais:
  - INSS: Portaria MPS/MF nº 13/2026 (tabela progressiva)
  - IRRF: RFB 2026 + isenção efetiva Lei 15.270/2025
  - Encargos patronais: SINTRACON-SP / rfi_catalog.xlsm (MendesLobo, abril/2026)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from concilium.domain.constants import (
    _ENC_A_FGTS,
    _ENC_A_INSS_EMPRESA,
    _ENC_A_RAT,
    _ENC_A_SAL_EDUC,
    _ENC_A_TERCEIROS,
    _ENC_B_HORISTA,
    _ENC_B_MENSALISTA,
    _ENC_C_HORISTA,
    _ENC_C_MENSALISTA,
    _ENC_D_HORISTA,
    _ENC_D_MENSALISTA,
    _ENC_E_HORISTA,
    _ENC_E_MENSALISTA,
    _ENC_F_HORISTA,
    _ENC_F_MENSALISTA,
    _ENC_JUDICIAL,
    ENCARGOS_CLT,
    ENCARGOS_MENSALISTA,
    INSS_BRACKETS_2026,
    IRRF_BRACKETS_2026,
    IRRF_DESCONTO_PROGRESSIVO_A,
    IRRF_DESCONTO_PROGRESSIVO_B,
    IRRF_ISENCAO_EFETIVA_2026,
)


@dataclass
class ChargeItem:
    """Encargo individual com rastreabilidade legal."""

    nome: str
    percentual: float
    valor: float
    base_legal: str = ""


@dataclass
class TaxationResult:
    """Resultado auditável do custo do empregador para um salário base."""

    salario_base: float
    custo_total: float
    itens: list[ChargeItem] = field(default_factory=list)


def calculate_inss_employee(salary: float) -> float:
    """Calcula INSS do empregado pela tabela progressiva 2026 (Portaria MPS/MF nº 13/2026).

    Usa o método progressivo: alíquota × base − parcela_a_deduzir.
    O valor é limitado ao teto (salário > R$ 8.475,55 → INSS máximo ≈ R$ 988,09).

    Args:
        salary: salário bruto mensal em R$.

    Returns:
        Valor do INSS do empregado em R$.
    """
    if salary <= 0:
        return 0.0
    # Limitar ao teto contributivo
    base = min(salary, 8_475.55)
    for limit, aliq, deducao in INSS_BRACKETS_2026:
        if limit is None or base <= limit:
            return round(max(0.0, base * aliq - deducao), 2)
    return round(base * INSS_BRACKETS_2026[-1][1] - INSS_BRACKETS_2026[-1][2], 2)


def calculate_irrf(base_calculo: float) -> float:
    """Calcula IRRF mensal com isenção efetiva Lei 15.270/2025.

    A base de cálculo já deve ter sido deduzida do INSS do empregado
    e das deduções por dependentes (R$ 189,59/dependente) pelo caller.

    Isenção efetiva: base ≤ R$ 5.000 → IRRF = 0.
    Desconto progressivo: 5.000,01 ≤ base ≤ 7.350 → redução aplicada.

    Args:
        base_calculo: base de cálculo líquida (salário − INSS − deduções).

    Returns:
        Valor do IRRF em R$.
    """
    if base_calculo <= IRRF_ISENCAO_EFETIVA_2026:
        return 0.0

    irrf_bruto = 0.0
    for limit, aliq, deducao in IRRF_BRACKETS_2026:
        if limit is None or base_calculo <= limit:
            irrf_bruto = max(0.0, base_calculo * aliq - deducao)
            break

    if base_calculo <= 7_350.0:
        desconto = IRRF_DESCONTO_PROGRESSIVO_A - IRRF_DESCONTO_PROGRESSIVO_B * base_calculo
        irrf_bruto = max(0.0, irrf_bruto - max(0.0, desconto))

    return round(irrf_bruto, 2)


def calculate_employer_clt(
    salario_base: float,
    categoria: str = "horista",
) -> TaxationResult:
    """Calcula custo total do empregador para um funcionário CLT com breakdown por Grupo.

    Decompõe o multiplicador (ENCARGOS_CLT ou ENCARGOS_MENSALISTA) em itens
    auditáveis por Grupo A–F + Judicial, com base legal citada.

    Args:
        salario_base: salário base mensal puro (sem encargos) em R$.
        categoria: "horista" (default, obra/campo) ou "mensalista" (gestão/admin).

    Returns:
        TaxationResult com custo_total e lista de ChargeItem por grupo.
    """
    is_horista = categoria.lower() not in ("mensalista", "administrativo", "gestao")

    enc_b = _ENC_B_HORISTA if is_horista else _ENC_B_MENSALISTA
    enc_c = _ENC_C_HORISTA if is_horista else _ENC_C_MENSALISTA
    enc_d = _ENC_D_HORISTA if is_horista else _ENC_D_MENSALISTA
    enc_e = _ENC_E_HORISTA if is_horista else _ENC_E_MENSALISTA
    enc_f = _ENC_F_HORISTA if is_horista else _ENC_F_MENSALISTA

    def v(pct: float) -> float:
        return round(salario_base * pct, 2)

    itens: list[ChargeItem] = [
        ChargeItem(
            nome="Grupo A — INSS Patronal",
            percentual=_ENC_A_INSS_EMPRESA,
            valor=v(_ENC_A_INSS_EMPRESA),
            base_legal="Lei 8.212/91 art. 22 — 20%",
        ),
        ChargeItem(
            nome="Grupo A — FGTS",
            percentual=_ENC_A_FGTS,
            valor=v(_ENC_A_FGTS),
            base_legal="Lei 8.036/90 — 8%",
        ),
        ChargeItem(
            nome="Grupo A — RAT/SAT",
            percentual=_ENC_A_RAT,
            valor=v(_ENC_A_RAT),
            base_legal="Lei 8.212/91 — grau médio 3%",
        ),
        ChargeItem(
            nome="Grupo A — Salário-Educação",
            percentual=_ENC_A_SAL_EDUC,
            valor=v(_ENC_A_SAL_EDUC),
            base_legal="Lei 9.424/96 — 2,5%",
        ),
        ChargeItem(
            nome="Grupo A — Sistema S (SEBRAE+SENAI+SESI+INCRA+SECONCI)",
            percentual=_ENC_A_TERCEIROS,
            valor=v(_ENC_A_TERCEIROS),
            base_legal="Lei 8.029/90 e CFs — 4,3%",
        ),
        ChargeItem(
            nome="Grupo B — Provisões legais (férias, 13º, DSR)",
            percentual=enc_b,
            valor=v(enc_b),
            base_legal="CLT arts. 129, 457, 7º CF/88",
        ),
        ChargeItem(
            nome="Grupo C — Rescisão e substitutos (aviso prévio, multa FGTS)",
            percentual=enc_c,
            valor=v(enc_c),
            base_legal="FGTS art. 18 §1º; CLT art. 487",
        ),
        ChargeItem(
            nome="Grupo D — Reincidências de B sobre C",
            percentual=enc_d,
            valor=v(enc_d),
            base_legal="Incidência reflexa sobre B+C",
        ),
        ChargeItem(
            nome="Grupo E — Benefícios (saúde, seguro vida, EPI, cesta)",
            percentual=enc_e,
            valor=v(enc_e),
            base_legal="Convenção Coletiva SINTRACON-SP",
        ),
        ChargeItem(
            nome="Grupo F — Vale-transporte + Vale-refeição",
            percentual=enc_f,
            valor=v(enc_f),
            base_legal="Lei 7.418/85 (VT); CCT SINTRACON-SP (VR)",
        ),
        ChargeItem(
            nome="Judicial — Provisão passivo trabalhista",
            percentual=_ENC_JUDICIAL,
            valor=v(_ENC_JUDICIAL),
            base_legal="Provisão preventiva — SINTRACON-SP",
        ),
    ]

    encargos_total = ENCARGOS_CLT if is_horista else ENCARGOS_MENSALISTA
    custo_total = round(salario_base * (1.0 + encargos_total), 2)

    return TaxationResult(
        salario_base=salario_base,
        custo_total=custo_total,
        itens=itens,
    )
