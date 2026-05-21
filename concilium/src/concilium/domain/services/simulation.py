from dataclasses import dataclass
from math import ceil
from typing import Any


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


class SimuladorEngenharia:
    def __init__(self, catalogo: dict[str, Any]):
        self.catalogo = catalogo
        self.cpus = {c["codigo"]: c for c in catalogo.get("cpus", [])}
        self.insumos = {i["codigo"]: i for i in catalogo.get("insumos", [])}
        producoes = catalogo.get("produtividades", []) or catalogo.get("producoes", [])
        self.producoes = {p["id"]: p.get("valor_horario", 0) for p in producoes if p.get("id")}
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
        if not equipe:
            if prod_id_ref:
                ficha = self.producao_fichas.get(prod_id_ref)
                if ficha:
                    equipe = ficha.get("composicao_padrao_equipe")

        if not equipe:
            equipe = {}

        # 2.1 Mão de Obra Direta
        for f in equipe.get("funcoes", []):
            insumo = self.insumos.get(f["funcao_id"], {})
            preco_base = insumo.get("preco_unitario", 0)
            if insumo.get("unidade") == "mes":
                preco_base = preco_base / 208.0

            subtotal_base = f["num_pessoas"] * preco_base * horas_totais
            custo_mo_base += subtotal_base
            custo_mo_encargos += subtotal_base * FATOR_ENCARGOS

        # 2.2 Equipamentos (Com Decomposição ADR-023)
        for e in equipe.get("equipamentos", []):
            insumo = self.insumos.get(e["equip_id"], {})
            preco_total_h = insumo.get("preco_unitario", 0)

            # Tenta decomposição
            decomp = (insumo.get("atributos_especificos") or {}).get("decomposicao_equip", {})
            if decomp:
                # Frações do custo horário
                total_h = decomp.get("custo_hora_total", preco_total_h) or 1.0
                f_mo = decomp.get("custo_mao_obra_h", 0) / total_h
                f_diesel = decomp.get("custo_diesel_h", 0) / total_h
                f_material = decomp.get("custo_material_h", 0) / total_h
                f_capital = decomp.get("custo_capital_h", 0) / total_h

                contribuicao = e["num_unidades"] * preco_total_h * horas_totais
                custo_diesel += contribuicao * f_diesel
                custo_eq_manut += contribuicao * f_material
                custo_eq_capital += contribuicao * f_capital

                # A parcela de MO do equipamento também sofre encargos
                mo_equip = contribuicao * f_mo
                custo_mo_base += mo_equip
                custo_mo_encargos += mo_equip * FATOR_ENCARGOS
            else:
                # Fallback: 70% MO / 10% Manut / 20% Diesel se não houver decomposição
                contribuicao = e["num_unidades"] * preco_total_h * horas_totais
                custo_mo_base += contribuicao * 0.7
                custo_mo_encargos += (contribuicao * 0.7) * FATOR_ENCARGOS
                custo_eq_manut += contribuicao * 0.1
                custo_diesel += contribuicao * 0.2

        # 3. Custos de Materiais (Consumo Volumétrico)
        custo_mat = 0.0
        for item in cpu.get("composicao_itens", []):
            insumo = self.insumos.get(item["insumo_id"], {})
            preco = insumo.get("preco_unitario", 0)
            custo_mat += item["coeficiente"] * producao_total * preco

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
