"""P17-B: non-authoritative audit of legacy Skill 05 instance costs.

Do not confuse legacy MAT/COMB monetary estimates with measured purchases.
Only a future P17-C/P18-B/P20 journal may authorize finance certificates.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from collections.abc import Sequence

from concilium.domain.models.canonical import InstanciaRecurso, RecursoContrato, ValidacaoItem

_CENT = Fraction(1, 100)


def _legacy_money(value: object, context: str) -> Fraction:
    """Parse the persisted legacy decimal rendering without additional rounding."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError(f"{context}: unsupported legacy monetary value")
    try:
        decimal = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{context}: invalid legacy monetary value") from exc
    if not decimal.is_finite() or decimal < 0:
        raise ValueError(f"{context}: nonfinite or negative monetary value")
    return Fraction(decimal)


@dataclass(frozen=True)
class InstanceFinancialSlice:
    contract_id: str
    instance_id: str
    mo_active: Fraction
    eq_active: Fraction
    mo_idle: Fraction
    eq_idle: Fraction
    legacy_consumption_unverified: Fraction
    mobilization_indirect: Fraction
    demobilization_indirect: Fraction
    reported_total: Fraction

    @property
    def contractual_k(self) -> Fraction:
        return self.mo_active + self.eq_active + self.mo_idle + self.eq_idle

    @property
    def indirect_mobility(self) -> Fraction:
        return self.mobilization_indirect + self.demobilization_indirect

    @property
    def reconstructed(self) -> Fraction:
        return self.contractual_k + self.legacy_consumption_unverified + self.indirect_mobility

    @property
    def reconciled(self) -> bool:
        # Original Skill 05 components are stored as decimal-cent floats.
        # A one-cent tolerance is diagnostic, NOT a GO rounding permission.
        return abs(self.reported_total - self.reconstructed) <= _CENT


@dataclass(frozen=True)
class Skill05CostOwnershipAudit:
    slices: tuple[InstanceFinancialSlice, ...]
    validations: tuple[ValidacaoItem, ...]
    authority: str = "PREVIEW_ONLY_LEGACY_MONETARY_COMPONENTS"

    @property
    def contractual_k(self) -> Fraction:
        return sum((s.contractual_k for s in self.slices), Fraction(0))

    @property
    def legacy_consumption_unverified(self) -> Fraction:
        return sum((s.legacy_consumption_unverified for s in self.slices), Fraction(0))

    @property
    def indirect_mobility(self) -> Fraction:
        return sum((s.indirect_mobility for s in self.slices), Fraction(0))

    @property
    def reconstructed(self) -> Fraction:
        return self.contractual_k + self.legacy_consumption_unverified + self.indirect_mobility


def audit_skill05_cost_ownership(
    contracts: Sequence[RecursoContrato],
    instances: Sequence[InstanciaRecurso],
) -> Skill05CostOwnershipAudit:
    """Split K/V/mobility, retaining UNKNOWN for legacy monetary consumption.

    Every instance is assigned to exactly one declared contract. Money from
    legacy MAT/COMB cannot be treated as a physically observed acquisition;
    P17-C/P18-B must supply an independent invoice/volume event.
    """
    if not contracts and not instances:
        return Skill05CostOwnershipAudit((), (
            ValidacaoItem(
                codigo="VAL-P17-SEM-EVIDENCIA",
                status="AVISO",
                mensagem="Nenhum contrato/instância demonstrado; custo não certificado.",
            ),
        ))

    known = {contract.contrato_id: contract for contract in contracts}
    validations: list[ValidacaoItem] = []
    if len(known) != len(contracts):
        validations.append(ValidacaoItem(
            codigo="VAL-P17-CONTRATO-DUPLICADO", status="ERRO",
            mensagem="IDs contratuais duplicados; propriedade financeira ambígua.",
        ))
    groups: dict[str, list[InstanceFinancialSlice]] = {k: [] for k in known}
    seen: set[tuple[str, str]] = set()
    slices: list[InstanceFinancialSlice] = []
    for instance in instances:
        key = (instance.contrato_id, instance.instancia_id)
        if key in seen:
            validations.append(ValidacaoItem(
                codigo="VAL-P17-INSTANCIA-DUPLICADA", status="ERRO",
                mensagem=f"Instância financeira repetida: {key!r}.",
            ))
            continue
        seen.add(key)
        if instance.contrato_id not in known:
            validations.append(ValidacaoItem(
                codigo="VAL-P17-CONTRATO-AUSENTE", status="ERRO",
                mensagem=f"Instância {instance.instancia_id} sem contrato financeiro.",
            ))
            continue
        try:
            ctx = f"{instance.contrato_id}/{instance.instancia_id}"
            def read(field: str) -> Fraction:
                return _legacy_money(getattr(instance, field), f"{ctx}.{field}")
            row = InstanceFinancialSlice(
                contract_id=instance.contrato_id,
                instance_id=instance.instancia_id,
                mo_active=read("custo_ativo_mo"),
                eq_active=read("custo_ativo_eq"),
                mo_idle=read("custo_idle_mo"),
                eq_idle=read("custo_idle_eq"),
                legacy_consumption_unverified=(
                    read("custo_ativo_mat") + read("custo_ativo_comb")
                ),
                mobilization_indirect=read("custo_mob_instancia"),
                demobilization_indirect=read("custo_demob_instancia"),
                reported_total=read("custo_instancia_total"),
            )
        except ValueError as exc:
            validations.append(ValidacaoItem(
                codigo="VAL-P17-VALOR-INVALIDO", status="ERRO", mensagem=str(exc),
            ))
            continue
        slices.append(row)
        groups[instance.contrato_id].append(row)
        if not row.reconciled:
            validations.append(ValidacaoItem(
                codigo="VAL-P17-INSTANCIA-NAO-CONCILIADA", status="ERRO",
                mensagem=f"{ctx}: total legado não coincide com K + V legado + MOB/DEMOB.",
            ))
        if row.legacy_consumption_unverified > 0:
            validations.append(ValidacaoItem(
                codigo="VAL-P17-CONSUMO-LEGADO", status="AVISO",
                mensagem=f"{ctx}: MAT/COMB monetário sem compra física U_g comprovada; não certificável.",
            ))

    for contract_id, contract in known.items():
        rows = groups[contract_id]
        if not rows:
            validations.append(ValidacaoItem(
                codigo="VAL-P17-CUSTO-INSTANCIAL-AUSENTE", status="AVISO",
                mensagem=f"{contract_id}: sem linha instancial; total não certificado.",
            ))
            continue
        try:
            reported = _legacy_money(contract.custo_total_contrato, f"{contract_id}.total")
        except ValueError as exc:
            validations.append(ValidacaoItem(
                codigo="VAL-P17-CONTRATO-INVALIDO", status="ERRO", mensagem=str(exc),
            ))
            continue
        reconstructed = sum((row.reported_total for row in rows), Fraction(0))
        if abs(reconstructed - reported) > _CENT:
            validations.append(ValidacaoItem(
                codigo="VAL-P17-CONTRATO-NAO-CONCILIADO", status="ERRO",
                mensagem=f"{contract_id}: total do contrato difere da soma das instâncias.",
            ))
    return Skill05CostOwnershipAudit(tuple(slices), tuple(validations))
