"""Reconciliação de Planejamento.txt ↔ Canonical.

Compara dados de planejamento original (curado em .txt) com dados processados
pelo pipeline (canonical), identificando disparidades e rastreando:

1. Custos diretos: MO, EQ, COMB, MAT
2. Custos indiretos: ADM, TOP, LAB, QSMS, MOB/DESMOB
3. Com/sem BDI
4. Por atividade/item

Objetivo: Auditoria e validação de precisão do motor financeiro.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from concilium.domain.models.canonical import CanonicalModel

_log = logging.getLogger(__name__)


@dataclass
class CustoPlanejamento:
    """Custo de um item conforme planejamento.txt."""

    item_id: str
    descricao: str
    quantidade: float
    unidade: str
    # Sem BDI
    mo_sem_bdi: float = 0.0
    eq_sem_bdi: float = 0.0  # SERVIÇOS/EQ
    combustivel_sem_bdi: float = 0.0  # DIESEL
    material_sem_bdi: float = 0.0  # MATERIAL
    total_sem_bdi: float = 0.0
    # Com BDI
    mo_com_bdi: float = 0.0
    eq_com_bdi: float = 0.0
    combustivel_com_bdi: float = 0.0
    material_com_bdi: float = 0.0
    total_com_bdi: float = 0.0
    # BDI
    bdi_valor: float = 0.0
    bdi_pct: float = 0.0
    # Tipo
    tipo: str = "DIRETO"  # DIRETO ou INDIRETO


@dataclass
class DisparityAnalysis:
    """Resultado da análise de disparidades."""

    planejamento: dict[str, CustoPlanejamento] = field(default_factory=dict)
    canonical_direto: dict[str, float] = field(default_factory=dict)
    canonical_indireto: dict[str, float] = field(default_factory=dict)
    # Resumos
    total_planej_direto_sem_bdi: float = 0.0
    total_planej_direto_com_bdi: float = 0.0
    total_planej_indireto: float = 0.0
    total_canonical_direto: float = 0.0
    total_canonical_indireto: float = 0.0
    # Disparidades
    disparidades: list[dict[str, Any]] = field(default_factory=list)


def _sniff_dialect(f) -> type[csv.Dialect]:
    """Detecta o delimiter do arquivo (tab/virgula/ponto-e-virgula)."""
    sample = f.read(4096)
    f.seek(0)
    return csv.Sniffer().sniff(sample, delimiters="\t,;")


def _parse_quantidade(row: list[str]) -> float:
    """Extrai a quantidade (coluna 3) da linha, tolerando formato pt-BR."""
    try:
        return float(row[3].replace(",", ".")) if len(row) > 3 else 0.0
    except (ValueError, IndexError):
        return 0.0


def _parse_linha_planejamento(row: list[str], current_section: str) -> CustoPlanejamento | None:
    """Parse de uma linha de dados de planejamento.txt, ou None se vazia/descartável.

    Sem try/except aqui: todos os acessos a `row` são guardados por `len(row)`,
    o parse de quantidade tem seu próprio try/except e `_parse_valor` nunca
    levanta — não há exceção a capturar.
    """
    item_id = row[0].strip()
    if not item_id or item_id in ("ITEM", ""):
        return None

    descricao = row[1].strip() if len(row) > 1 else ""
    unidade = row[2].strip() if len(row) > 2 else ""
    quantidade = _parse_quantidade(row)

    # Custos estão em colunas variáveis dependendo do layout
    # Para DIRETO: procurar padrão de valores numéricos após quantidade
    # Para INDIRETO: o total está normalmente em uma coluna específica
    custo = CustoPlanejamento(
        item_id=item_id,
        descricao=descricao,
        quantidade=quantidade,
        unidade=unidade,
        tipo=current_section,
    )

    # Extrair valores do final da linha (último valor é geralmente total)
    if len(row) >= 10:
        # Últimas colunas geralmente têm valores numéricos
        # Esta é uma heurística que pode precisar ajuste
        custo.total_com_bdi = _parse_valor(row[-2])
        custo.total_sem_bdi = _parse_valor(row[-3]) if len(row) > 3 else custo.total_com_bdi

    if custo.total_com_bdi > 0 or custo.total_sem_bdi > 0:
        return custo
    return None


class PlanejamentoParser:
    """Faz parse de planejamento.txt (formato TSV Excel)."""

    @staticmethod
    def parse(path: Path) -> dict[str, CustoPlanejamento]:
        """Parse planejamento.txt e retorna dict {item_id: CustoPlanejamento}."""
        dados = {}

        with open(path, encoding="utf-8") as f:
            dialect = _sniff_dialect(f)
            reader = csv.reader(f, dialect=dialect)

            # Skip cabeçalhos (linhas 1-3)
            for _ in range(3):
                next(reader)

            current_section = "DIRETO"

            for row in reader:
                if not row or not row[0].strip():
                    continue

                # Detectar seção INDIRETOS
                if "INDIRETOS" in row[0].upper():
                    current_section = "INDIRETO"
                    continue

                custo = _parse_linha_planejamento(row, current_section)
                if custo is not None:
                    dados[custo.item_id] = custo

        return dados


def _parse_valor(valor_str: str | None) -> float:
    """Parse valor monetário em português (1.234,56 → 1234.56)."""
    if not valor_str:
        return 0.0
    valor_str = valor_str.strip()
    if not valor_str or valor_str == "-":
        return 0.0
    # Converter 1.234,56 → 1234.56
    valor_str = valor_str.replace("R$", "").strip()
    valor_str = valor_str.replace(".", "").replace(",", ".")
    try:
        return float(valor_str)
    except ValueError:
        return 0.0


class ReconciliadorPlanejamento:
    """Reconcilia planejamento.txt com canonical model."""

    def __init__(self, canonical: CanonicalModel, planejamento_path: Path):
        self.canonical = canonical
        self.planejamento_path = planejamento_path

    def analisar(self) -> DisparityAnalysis:
        """Executa análise completa de reconciliação."""
        analise = DisparityAnalysis()

        # Parse planejamento
        analise.planejamento = PlanejamentoParser.parse(self.planejamento_path)

        # Agregar dados do canonical
        self._agregar_canonical(analise)

        # Identificar disparidades
        self._identificar_disparidades(analise)

        return analise

    def _agregar_canonical(self, analise: DisparityAnalysis) -> None:
        """Agrupa dados do canonical por item."""
        # Diretos
        for eq in self.canonical.equipes_diretas:
            _neb = getattr(eq, "num_equipes_base", None)
            n_base = max(1, _neb if _neb is not None else 1)
            analise.canonical_direto[eq.item_id] = (
                analise.canonical_direto.get(eq.item_id, 0.0) + eq.custo_total * n_base
            )
            analise.total_canonical_direto += eq.custo_total * n_base

        # Indiretos (do resultado)
        if self.canonical.resultado:
            custo = self.canonical.resultado.custo
            if custo:
                analise.total_canonical_indireto = (
                    (custo.indireto_adm or 0.0)
                    + (custo.indireto_top or 0.0)
                    + (custo.indireto_lab or 0.0)
                    + (custo.indireto_qsms or 0.0)
                    + (custo.indireto_mob or 0.0)
                )

    @staticmethod
    def _disparidade_ambos(item_id: str, planej: CustoPlanejamento, canon: float) -> dict[str, Any] | None:
        """Disparidade para item presente em ambos planejamento e canonical, se acima do limiar."""
        delta = canon - planej.total_sem_bdi
        delta_pct = (delta / planej.total_sem_bdi * 100) if planej.total_sem_bdi > 0 else 0

        if abs(delta) <= 1.0:  # Desvios acima de R$ 1
            return None
        return {
            "item_id": item_id,
            "descricao": planej.descricao,
            "planejamento_sem_bdi": planej.total_sem_bdi,
            "planejamento_com_bdi": planej.total_com_bdi,
            "canonical": canon,
            "delta": delta,
            "delta_pct": delta_pct,
            "tipo": "FALTA_PLANEJ" if canon > planej.total_sem_bdi else "SOBRA_PLANEJ",
        }

    @staticmethod
    def _disparidade_nao_executado(item_id: str, planej: CustoPlanejamento) -> dict[str, Any]:
        """Disparidade para item planejado sem execução registrada no canonical."""
        return {
            "item_id": item_id,
            "descricao": planej.descricao,
            "planejamento_sem_bdi": planej.total_sem_bdi,
            "planejamento_com_bdi": planej.total_com_bdi,
            "canonical": 0.0,
            "delta": -planej.total_sem_bdi,
            "delta_pct": -100,
            "tipo": "NAO_EXECUTADO",
        }

    @staticmethod
    def _disparidade_nao_planejado(item_id: str, canon: float) -> dict[str, Any]:
        """Disparidade para item executado no canonical sem planejamento correspondente."""
        return {
            "item_id": item_id,
            "descricao": "Não planejado",
            "planejamento_sem_bdi": 0.0,
            "planejamento_com_bdi": 0.0,
            "canonical": canon,
            "delta": canon,
            "delta_pct": float("inf"),
            "tipo": "NAO_PLANEJADO",
        }

    def _disparidade_para_item(self, item_id: str, analise: DisparityAnalysis) -> dict[str, Any] | None:
        """Resolve a disparidade (se houver) para um único item_id."""
        planej = analise.planejamento.get(item_id)
        canon = analise.canonical_direto.get(item_id, 0.0)

        if planej and canon:
            return self._disparidade_ambos(item_id, planej, canon)
        if planej and not canon:
            return self._disparidade_nao_executado(item_id, planej)
        if canon and not planej:
            return self._disparidade_nao_planejado(item_id, canon)
        return None

    @staticmethod
    def _calcular_totais_planejamento(analise: DisparityAnalysis) -> None:
        """Calcula os totais agregados de planejamento por tipo (DIRETO/INDIRETO)."""
        analise.total_planej_direto_sem_bdi = sum(
            p.total_sem_bdi for p in analise.planejamento.values() if p.tipo == "DIRETO"
        )
        analise.total_planej_direto_com_bdi = sum(
            p.total_com_bdi for p in analise.planejamento.values() if p.tipo == "DIRETO"
        )
        analise.total_planej_indireto = sum(
            p.total_com_bdi for p in analise.planejamento.values() if p.tipo == "INDIRETO"
        )

    def _identificar_disparidades(self, analise: DisparityAnalysis) -> None:
        """Identifica e registra disparidades."""
        # Disparidades por item
        todos_items = set(analise.planejamento.keys()) | set(analise.canonical_direto.keys())

        for item_id in todos_items:
            disparidade = self._disparidade_para_item(item_id, analise)
            if disparidade is not None:
                analise.disparidades.append(disparidade)

        self._calcular_totais_planejamento(analise)


def gerar_relatorio_reconciliacao(analise: DisparityAnalysis) -> str:
    """Gera relatório em formato texto."""
    linhas = [
        "=" * 100,
        "RECONCILIAÇÃO: Planejamento.txt ↔ Canonical Model",
        "=" * 100,
        "",
        "[RESUMO]",
        f"  Planejamento Direto (s/ BDI):     R$ {analise.total_planej_direto_sem_bdi:,.2f}",
        f"  Planejamento Direto (c/ BDI):     R$ {analise.total_planej_direto_com_bdi:,.2f}",
        f"  Canonical Direto:                 R$ {analise.total_canonical_direto:,.2f}",
        f"  Delta Direto (c/ BDI):            R$ "
        f"{analise.total_canonical_direto - analise.total_planej_direto_com_bdi:,.2f}",
        "",
        f"  Planejamento Indireto:            R$ {analise.total_planej_indireto:,.2f}",
        f"  Canonical Indireto:               R$ {analise.total_canonical_indireto:,.2f}",
        f"  Delta Indireto:                   R$ "
        f"{analise.total_canonical_indireto - analise.total_planej_indireto:,.2f}",
        "",
        "[DISPARIDADES CRÍTICAS]",
    ]

    disparidades_criticas = [d for d in analise.disparidades if abs(d["delta_pct"]) > 5.0]
    disparidades_criticas.sort(key=lambda x: abs(x["delta"]), reverse=True)

    if disparidades_criticas:
        for d in disparidades_criticas[:20]:  # Top 20
            linhas.append(
                f"  {d['item_id']:20} | {d['tipo']:20} | "
                f"Planej: R$ {d['planejamento_sem_bdi']:12,.2f} | "
                f"Canon: R$ {d['canonical']:12,.2f} | "
                f"Delta: R$ {d['delta']:12,.2f} ({d['delta_pct']:+6.1f}%)"
            )
    else:
        linhas.append("  (Nenhuma disparidade > 5%)")

    linhas.extend(
        [
            "",
            "=" * 100,
        ]
    )

    return "\n".join(linhas)
