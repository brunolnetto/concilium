"""Verificações de plausibilidade auxiliares (extraído de plausibility_checker)."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from concilium.domain.constants import ALPHA_MAX_ENCARGOS as ALPHA_MAX
from concilium.domain.constants import ALPHA_MIN_ENCARGOS as ALPHA_MIN
from concilium.domain.constants import (
    DIESEL_L_POR_CV_MAX,
    DIESEL_L_POR_CV_MIN,
    DIESEL_L_POR_CV_PONT,
    DIESEL_TOLERANCIA,
    SMH,
    VH_MAX,
    ZSCORE_EXTREMO,
)
from concilium.domain.constants import HORAS_MES_CLT as HORAS_MES_PADRAO
from concilium.domain.constants import VALIDADE_PRECO_DIAS as VALIDADE_DIAS


@dataclass
class Anomalia:
    codigo: str
    tipo: str
    severidade: str
    mensagem: str
    detalhe: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "codigo": self.codigo,
            "tipo": self.tipo,
            "severidade": self.severidade,
            "mensagem": self.mensagem,
            "detalhe": self.detalhe,
        }


_ESTAGIARIO_KW = {"estagi", "intern", "bolsist"}


def _is_estagiario(ins: dict) -> bool:
    import unicodedata as _uc

    def norm(s: str) -> str:
        t = _uc.normalize("NFD", str(s).lower())
        return "".join(c for c in t if _uc.category(c) != "Mn")

    text = norm(ins.get("descricao", "")) + " " + norm(ins.get("codigo", ""))
    return any(k in text for k in _ESTAGIARIO_KW)


def _today() -> date:
    return datetime.now(UTC).date()


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def _zscore_map(values: list[float]) -> dict[int, float]:
    if len(values) < 2:
        return {}
    mu = statistics.mean(values)
    sd = statistics.stdev(values)
    if sd == 0:
        return {i: 0.0 for i in range(len(values))}
    return {i: (v - mu) / sd for i, v in enumerate(values)}


# ── Helpers for _check_mao_obra ───────────────────────────────────────────────


def _pc_mo_zscore(mo: list[dict]) -> list[Anomalia]:
    precos = [float(i["preco_unitario"]) for i in mo]
    zmap = _zscore_map(precos)
    result = []
    for idx, ins in enumerate(mo):
        z = zmap.get(idx, 0.0)
        if abs(z) > ZSCORE_EXTREMO:
            result.append(
                Anomalia(
                    codigo=ins["codigo"],
                    tipo="ESTATISTICO",
                    severidade="AVISO",
                    mensagem=f"Salário extremamente fora da média (z={z:+.2f})",
                    detalhe={"preco": ins["preco_unitario"], "z": round(z, 2), "descricao": ins.get("descricao", "")},
                )
            )
    return result


def _pc_mo_salario_minimo(mo: list[dict]) -> list[Anomalia]:
    result = []
    for ins in mo:
        if _is_estagiario(ins):
            continue
        attrs = ins.get("atributos_especificos") or {}
        hm = float(attrs.get("horas_mes") or HORAS_MES_PADRAO)
        preco_h = float(ins["preco_unitario"]) / hm
        if preco_h < SMH * 0.95:
            result.append(
                Anomalia(
                    codigo=ins["codigo"],
                    tipo="FISICO",
                    severidade="ERRO",
                    mensagem=f"Salário horário R${preco_h:.2f}/h abaixo do mínimo legal R${SMH:.2f}/h",
                    detalhe={"preco_mensal": ins["preco_unitario"], "horas_mes": hm, "preco_hora": round(preco_h, 2)},
                )
            )
    return result


def _pc_mo_encargos(mo: list[dict]) -> list[Anomalia]:
    result = []
    for ins in mo:
        attrs = ins.get("atributos_especificos") or {}
        enc = attrs.get("percentual_encargos_local")
        if enc is not None:
            alpha = 1.0 + float(enc)
            if not (ALPHA_MIN <= alpha <= ALPHA_MAX):
                result.append(
                    Anomalia(
                        codigo=ins["codigo"],
                        tipo="FISICO",
                        severidade="ERRO",
                        mensagem=f"Fator de encargos α={alpha:.3f} fora do range [{ALPHA_MIN}, {ALPHA_MAX}]",
                        detalhe={"percentual_encargos_local": enc, "alpha": alpha},
                    )
                )
    return result


def _pc_mo_duplicatas(mo: list[dict]) -> list[Anomalia]:
    seen: dict[tuple, str] = {}
    result = []
    for ins in mo:
        key = (ins.get("descricao", "").strip().lower(), ins.get("preco_unitario"))
        if key in seen:
            result.append(
                Anomalia(
                    codigo=ins["codigo"],
                    tipo="DUPLICATA",
                    severidade="AVISO",
                    mensagem=f"Possível duplicata de '{seen[key]}' (mesma descrição e preço)",
                    detalhe={"duplicata_de": seen[key], "descricao": ins.get("descricao"), "preco": key[1]},
                )
            )
        else:
            seen[key] = ins["codigo"]
    return result


def _pc_mo_semantica(mo: list[dict]) -> list[Anomalia]:
    result = []
    for ins in mo:
        u = (ins.get("unidade") or "").lower().strip()
        if u not in ("mes", "mês", "h", "hr"):
            result.append(
                Anomalia(
                    codigo=ins["codigo"],
                    tipo="SEMANTICO",
                    severidade="AVISO",
                    mensagem=f"Unidade '{u}' incomum para MAO_OBRA (esperado: mes/h)",
                    detalhe={"unidade": u},
                )
            )
    return result


def _pc_mo_staleness(mo: list[dict]) -> list[Anomalia]:
    result = []
    hoje = _today()
    for ins in mo:
        d = _parse_date(ins.get("data_referencia_preco"))
        if d and (hoje - d).days > VALIDADE_DIAS:
            result.append(
                Anomalia(
                    codigo=ins["codigo"],
                    tipo="STALE",
                    severidade="INFO",
                    mensagem=f"Preço desatualizado há {(hoje - d).days} dias (data: {d})",
                    detalhe={"data_referencia_preco": str(d), "dias_atraso": (hoje - d).days},
                )
            )
    return result


# ── Helpers for _check_equipamento ───────────────────────────────────────────


def _pc_eq_diesel(eq: list[dict]) -> list[Anomalia]:
    result = []
    for ins in eq:
        attrs = ins.get("atributos_especificos") or {}
        consumo = attrs.get("consumo_litros_hora")
        pot_cv = attrs.get("potencia_cv") or attrs.get("potencia_hp")
        if consumo is None or pot_cv is None:
            continue
        c, p = float(consumo), float(pot_cv)
        if p <= 0:
            continue
        esperado = p * DIESEL_L_POR_CV_PONT
        delta = abs(c - esperado) / esperado if esperado else 1.0
        if delta > DIESEL_TOLERANCIA:
            limite_inf = p * DIESEL_L_POR_CV_MIN
            limite_sup = p * DIESEL_L_POR_CV_MAX
            result.append(
                Anomalia(
                    codigo=ins["codigo"],
                    tipo="FISICO",
                    severidade="AVISO" if delta < 1.0 else "ERRO",
                    mensagem=f"Consumo {c:.2f} L/h fora do range físico [{limite_inf:.2f}–{limite_sup:.2f}] para {p} CV",  # noqa: E501
                    detalhe={
                        "consumo_real": c,
                        "potencia_cv": p,
                        "esperado_range": f"{limite_inf:.2f}–{limite_sup:.2f}",
                        "delta_pct": round(delta * 100),
                    },
                )
            )
    return result


def _pc_eq_zscore(eq: list[dict]) -> list[Anomalia]:
    result = []
    precos = [float(i["preco_unitario"]) for i in eq]
    zmap = _zscore_map(precos)
    for idx, ins in enumerate(eq):
        z = zmap.get(idx, 0.0)
        if abs(z) > ZSCORE_EXTREMO:
            result.append(
                Anomalia(
                    codigo=ins["codigo"],
                    tipo="ESTATISTICO",
                    severidade="AVISO",
                    mensagem=f"Preço R${ins['preco_unitario']}/h extremamente fora da média (z={z:+.2f})",
                    detalhe={"preco": ins["preco_unitario"], "z": round(z, 2), "descricao": ins.get("descricao", "")},
                )
            )
    return result


def _pc_eq_locacao(eq: list[dict]) -> list[Anomalia]:
    result = []
    for ins in eq:
        attrs = ins.get("atributos_especificos") or {}
        if not attrs.get("valor_locacao_mensal") and ins.get("preco_unitario", 0) > 0:
            result.append(
                Anomalia(
                    codigo=ins["codigo"],
                    tipo="INCOMPLETO",
                    severidade="INFO",
                    mensagem="valor_locacao_mensal ausente — custo de manutenção não calculável",
                    detalhe={"preco_h": ins["preco_unitario"]},
                )
            )
    return result


# ── Helpers for _check_produtividades ─────────────────────────────────────────


def _pc_check_equipe_refs(pid: str, equipe: dict, insumo_index: dict) -> list[Anomalia]:
    result = []
    for func in equipe.get("funcoes", []) or []:
        fid = func.get("funcao_id", "")
        if fid and fid not in insumo_index:
            result.append(
                Anomalia(
                    codigo=pid,
                    tipo="INCOMPLETO",
                    severidade="ERRO",
                    mensagem=f"funcao_id '{fid}' não existe no catálogo",
                    detalhe={"funcao_id": fid},
                )
            )
    for equip in equipe.get("equipamentos", []) or []:
        eid = equip.get("equip_id", "")
        if eid and eid not in insumo_index:
            result.append(
                Anomalia(
                    codigo=pid,
                    tipo="INCOMPLETO",
                    severidade="ERRO",
                    mensagem=f"equip_id '{eid}' não existe no catálogo",
                    detalhe={"equip_id": eid},
                )
            )
    return result


def _pc_check_prod_item(prod: dict, insumo_index: dict) -> list[Anomalia]:
    result = []
    pid = prod.get("id") or prod.get("codigo", "?")
    vh = prod.get("valor_horario")
    if not vh or float(vh) <= 0:
        result.append(
            Anomalia(
                codigo=pid,
                tipo="INCOMPLETO",
                severidade="ERRO",
                mensagem="valor_horario ausente ou zero — PU não calculável",
                detalhe={},
            )
        )
        return result
    vh_f = float(vh)
    if vh_f > VH_MAX:
        result.append(
            Anomalia(
                codigo=pid,
                tipo="FISICO",
                severidade="AVISO",
                mensagem=f"valor_horario {vh_f} un/h parece excessivo (limite técnico: {VH_MAX})",
                detalhe={"valor_horario": vh_f},
            )
        )
    equipe = prod.get("composicao_padrao_equipe") or prod.get("equipe") or {}
    tem_equipe = bool(equipe.get("funcoes") or equipe.get("equipamentos"))
    if not tem_equipe:
        result.append(
            Anomalia(
                codigo=pid,
                tipo="INCOMPLETO",
                severidade="AVISO",
                mensagem="Sem composição de equipe — PU de equipe não calculável (pode ser material-only)",
                detalhe={"valor_horario": vh_f, "origem": str(prod.get("origem", ""))[:30]},
            )
        )
    result.extend(_pc_check_equipe_refs(pid, equipe, insumo_index))
    return result


def _pc_prod_vhs(producoes: list[dict]) -> list[tuple]:
    result = []
    for prod in producoes:
        vh = prod.get("valor_horario", 0)
        if vh and float(vh) > 0:
            result.append((prod.get("id") or prod.get("codigo", "?"), float(vh)))
    return result


def _pc_check_prod_zscore(producoes: list[dict]) -> list[Anomalia]:
    result = []
    vhs = _pc_prod_vhs(producoes)
    if len(vhs) < 3:
        return result
    # vals é derivado de vhs 1:1, e o guard acima já garante len(vhs) >= 3,
    # logo len(vals) >= 2 é sempre verdadeiro aqui (statistics.stdev exige >= 2).
    vals = [v for _, v in vhs]
    mu, sd = statistics.mean(vals), statistics.stdev(vals)
    for pid, vh_f in vhs:
        z = (vh_f - mu) / sd if sd > 0 else 0
        if z > ZSCORE_EXTREMO * 2:
            result.append(
                Anomalia(
                    codigo=pid,
                    tipo="ESTATISTICO",
                    severidade="INFO",
                    mensagem=f"valor_horario {vh_f:.1f} un/h muito acima da média (z={z:+.1f}) — revisar unidade",
                    detalhe={"valor_horario": vh_f, "z": round(z, 2)},
                )
            )
    return result
