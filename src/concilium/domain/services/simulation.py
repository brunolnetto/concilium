import logging
from dataclasses import dataclass
from math import ceil
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ResultadoSimulacao:
    cpu_id: str
    periodo_dias: int
    regime: str
    contratacao: str  # "clt" ou "pj"
    horas_dia: float
    dias_trabalhados: int
    producao_total: float
    unidade: str
    # Particionamento Granular
    custo_material: float
    custo_mao_obra_base: float
    custo_mao_obra_encargos: float
    custo_equipamento_capital: float
    custo_equipamento_manutencao: float
    custo_diesel_total: float
    total_direto: float


def _sim_calc_funcoes(equipe: dict, insumos: dict, horas_totais: float, fator: float):
    custo_mo_base = 0.0
    custo_mo_encargos = 0.0
    for f in equipe.get("funcoes", []):
        insumo = insumos.get(f["funcao_id"], {})
        preco_base = insumo.get("preco_unitario")
        if preco_base is None:
            logger.warning("Função %s sem preco_unitario no catálogo — custo MO zerado", f.get("funcao_id", "?"))
            preco_base = 0
        if insumo.get("unidade") == "mes":
            preco_base = preco_base / 208.0
        subtotal_base = f["num_pessoas"] * preco_base * horas_totais
        custo_mo_base += subtotal_base
        custo_mo_encargos += subtotal_base * fator
    return custo_mo_base, custo_mo_encargos


def _sim_calc_equipamentos(equipe: dict, insumos: dict, horas_totais: float, fator: float):
    eq_cap = eq_manut = diesel = mo_eq = mo_eq_enc = 0.0
    for e in equipe.get("equipamentos", []):
        insumo = insumos.get(e["equip_id"], {})
        preco_total_h = insumo.get("preco_unitario")
        if preco_total_h is None:
            logger.warning("Equipamento %s sem preco_unitario no catálogo — custo equip zerado", e.get("equip_id", "?"))
            preco_total_h = 0
        decomp = (insumo.get("atributos_especificos") or {}).get("decomposicao_equip", {})
        contribuicao = e["num_unidades"] * preco_total_h * horas_totais
        if decomp:
            total_h = decomp.get("custo_hora_total", preco_total_h) or 1.0
            diesel += contribuicao * decomp.get("custo_diesel_h", 0) / total_h
            eq_manut += contribuicao * decomp.get("custo_material_h", 0) / total_h
            eq_cap += contribuicao * decomp.get("custo_capital_h", 0) / total_h
            mo_part = contribuicao * decomp.get("custo_mao_obra_h", 0) / total_h
            mo_eq += mo_part
            mo_eq_enc += mo_part * fator
        else:
            mo_eq += contribuicao * 0.7
            mo_eq_enc += (contribuicao * 0.7) * fator
            eq_manut += contribuicao * 0.1
            diesel += contribuicao * 0.2
    return eq_cap, eq_manut, diesel, mo_eq, mo_eq_enc


def _sim_calc_materiais(cpu: dict, insumos: dict, producao_total: float) -> float:
    custo_mat = 0.0
    for item in cpu.get("composicao_itens", []):
        insumo = insumos.get(item["insumo_id"], {})
        preco = insumo.get("preco_unitario")
        if preco is None:
            logger.warning(
                "Material %s sem preco_unitario no catálogo — custo material zerado", item.get("insumo_id", "?")
            )
            preco = 0
        custo_mat += item["coeficiente"] * producao_total * preco
    return custo_mat


class SimuladorEngenharia:
    def __init__(self, catalogo: dict[str, Any]):
        self.catalogo = catalogo
        self.cpus = {c["codigo"]: c for c in catalogo.get("cpus", [])}
        self.insumos = {i["codigo"]: i for i in catalogo.get("insumos", [])}
        producoes = catalogo.get("produtividades", []) or catalogo.get("producoes", [])
        self.producoes = {p["id"]: p.get("producao_horaria", 0) for p in producoes if p.get("id")}
        self.producao_fichas = {p["id"]: p for p in producoes if p.get("id")}

    def _calcular_dias_trabalhados(self, periodo_dias: int, regime: str) -> int:
        if regime == "7x0" or regime == "continuo":
            return periodo_dias
        elif regime == "6x1":
            # Aproximadamente 6/7 dos dias
            semanas = periodo_dias / 7
            return ceil(semanas * 6)
        elif regime == "5x2":
            # Aproximadamente 5/7 dos dias
            semanas = periodo_dias / 7
            return ceil(semanas * 5)
        return periodo_dias

    def simular_cpu(
        self, cpu_id: str, periodo_dias: int, regime: str, horas_dia: float, contratacao: str = "clt"
    ) -> ResultadoSimulacao:
        cpu = self.cpus.get(cpu_id)
        if not cpu:
            raise ValueError(f"CPU {cpu_id} não encontrada")

        # Fatores de Encargos Mendes Lobo (Multiplicadores)
        # CLT: 1.77 (77% encargos) | PJ: 1.06 (6% encargos)
        FATOR_ENCARGOS = 0.77 if contratacao == "clt" else 0.06

        # 1. Determina Produção
        prod_id_ref = cpu.get("producao_id_ref")
        prod_h = self.producoes.get(prod_id_ref, 0) if prod_id_ref else 0

        dias_uteis = self._calcular_dias_trabalhados(periodo_dias, regime)
        horas_totais = dias_uteis * horas_dia
        producao_total = (prod_h or 0) * horas_totais

        # 2. Custos Operacionais (Equipe)
        custo_mo_base = 0.0
        custo_mo_encargos = 0.0
        custo_eq_capital = 0.0
        custo_eq_manut = 0.0
        custo_diesel = 0.0

        equipe = None
        if not equipe:  # pragma: no branch
            if prod_id_ref:
                ficha = self.producao_fichas.get(prod_id_ref)
                if ficha:
                    equipe = ficha.get("composicao_padrao_equipe")

        if not equipe:
            equipe = {}

        # 2.1 Mão de Obra Direta
        mo_base_f, mo_enc_f = _sim_calc_funcoes(equipe, self.insumos, horas_totais, FATOR_ENCARGOS)
        custo_mo_base += mo_base_f
        custo_mo_encargos += mo_enc_f

        # 2.2 Equipamentos (Com Decomposição ADR-023)
        eq_cap, eq_manut, diesel, mo_eq, mo_eq_enc = _sim_calc_equipamentos(
            equipe, self.insumos, horas_totais, FATOR_ENCARGOS
        )
        custo_eq_capital += eq_cap
        custo_eq_manut += eq_manut
        custo_diesel += diesel
        custo_mo_base += mo_eq
        custo_mo_encargos += mo_eq_enc

        # 3. Custos de Materiais (Consumo Volumétrico)
        custo_mat = _sim_calc_materiais(cpu, self.insumos, producao_total)

        return ResultadoSimulacao(
            cpu_id=cpu_id,
            periodo_dias=periodo_dias,
            regime=regime,
            contratacao=contratacao,
            horas_dia=horas_dia,
            dias_trabalhados=dias_uteis,
            producao_total=round(producao_total, 2),
            unidade=cpu.get("unidade", "un"),
            custo_material=round(custo_mat, 2),
            custo_mao_obra_base=round(custo_mo_base, 2),
            custo_mao_obra_encargos=round(custo_mo_encargos, 2),
            custo_equipamento_capital=round(custo_eq_capital, 2),
            custo_equipamento_manutencao=round(custo_eq_manut, 2),
            custo_diesel_total=round(custo_diesel, 2),
            total_direto=round(
                custo_mat + custo_mo_base + custo_mo_encargos + custo_eq_capital + custo_eq_manut + custo_diesel, 2
            ),
        )
