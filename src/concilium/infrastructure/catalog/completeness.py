"""ADR-012 — Catalog Gap Detection and Resolution.

Detects gaps between expected service types and actual catalog CPUs,
and proposes resolutions from authoritative sources.
"""

from __future__ import annotations

from datetime import date

from concilium.domain.models.catalog.health import (
    CatalogGap,
    CatalogHealthReport,
    CoberturaConfig,
    FonteAutoritativa,
    ResolutionProposal,
)


def _count_status(gaps, status: str) -> int:
    count = 0
    for g in gaps:
        if g.status == status:
            count += 1
    return count


def _safe_pct(part: int, total: int) -> float:
    return (part / total * 100) if total > 0 else 0.0


def _analyze_producoes_quality(producoes: list) -> tuple:
    prods_reais = 0
    prods_tabela = 0
    prods_baixa = 0
    confiancas = []
    for p in producoes:
        tipo = p.get("origem", {}).get("tipo")
        if tipo == "calibrado_contra_obra_real":
            prods_reais += 1
        elif tipo == "tabela_referencia":
            prods_tabela += 1
        conf = p.get("qualidade", {}).get("confianca_pct", 0)
        confiancas.append(conf)
        if p.get("qualidade", {}).get("confianca_pct", 100) < 60:
            prods_baixa += 1
    confianca_media = sum(confiancas) / len(confiancas) if confiancas else 0.0
    return prods_reais, prods_tabela, prods_baixa, confianca_media


class CatalogGapDetector:
    """Detecta gaps entre cobertura esperada e catálogo atual (ADR-012 §D3)."""

    def _check_servico_gap(self, grupo_nome, grupo, servico, cpus, producoes_por_id, confianca_minima):
        match_cpu = self._find_cpu_by_description(servico, cpus)
        if match_cpu is None:
            return CatalogGap(
                grupo=grupo_nome,
                servico_esperado=servico,
                status="AUSENTE",
                fonte_sugerida=grupo.fonte_preenchimento or "SICRO",
                prioridade="ALTA",
            )
        producao_id = match_cpu.get("producao_id")
        if not producao_id:
            return CatalogGap(
                grupo=grupo_nome,
                servico_esperado=servico,
                status="SEM_PRODUTIVIDADE",
                cpu_existente=match_cpu.get("codigo"),
                fonte_sugerida="AGIS_OBRAS_REAIS ou SICRO",
                prioridade="MEDIA",
            )
        producao = producoes_por_id.get(producao_id)
        if producao:
            confianca = producao.get("qualidade", {}).get("confianca_pct", 100)
            if confianca < confianca_minima:
                return CatalogGap(
                    grupo=grupo_nome,
                    servico_esperado=servico,
                    status="BAIXA_CONFIANCA",
                    cpu_existente=match_cpu.get("codigo"),
                    confianca_atual=float(confianca),
                    fonte_sugerida="Calibrar contra obra real",
                    prioridade="BAIXA",
                )
        return None

    def detect_gaps(
        self,
        dominio: str,
        cpus: list[dict],
        cobertura_config: CoberturaConfig,
        producoes: list[dict] | None = None,
        confianca_minima: float = 60.0,
    ) -> list[CatalogGap]:
        """Compara serviços esperados com CPUs presentes no catálogo."""
        {c.get("descricao", "").lower() for c in cpus}
        {c.get("codigo", ""): c for c in cpus}
        producoes_por_id = {p.get("id", ""): p for p in (producoes or [])}

        gaps: list[CatalogGap] = []

        for grupo_nome, grupo in cobertura_config.grupos_servico.items():
            for servico in grupo.servicos_esperados:
                gap = self._check_servico_gap(grupo_nome, grupo, servico, cpus, producoes_por_id, confianca_minima)
                if gap is not None:
                    gaps.append(gap)

        return gaps

    def _find_cpu_by_description(self, descricao: str, cpus: list[dict]) -> dict | None:
        descricao_lower = descricao.lower()
        for cpu in cpus:
            if descricao_lower in cpu.get("descricao", "").lower():
                return cpu
            if cpu.get("descricao", "").lower() in descricao_lower:
                return cpu
        return None

    def build_health_report(
        self,
        dominio: str,
        jurisdicao: str,
        gaps: list[CatalogGap],
        total_servicos_esperados: int,
        cpus: list[dict],
        producoes: list[dict] | None = None,
    ) -> CatalogHealthReport:
        """Gera relatório de saúde do catálogo."""
        producoes = producoes or []
        gaps_ausente = _count_status(gaps, "AUSENTE")
        gaps_sem_prod = _count_status(gaps, "SEM_PRODUTIVIDADE")
        gaps_baixa = _count_status(gaps, "BAIXA_CONFIANCA")

        total_cpus_presentes = total_servicos_esperados - gaps_ausente
        cobertura_pct = _safe_pct(total_cpus_presentes, total_servicos_esperados)

        prods_reais, prods_tabela, prods_baixa_conf, confianca_media = _analyze_producoes_quality(producoes)
        prods_baixa = prods_baixa_conf

        status = CatalogHealthReport.compute_status(cobertura_pct, confianca_media)

        return CatalogHealthReport(
            dominio=dominio,
            jurisdicao=jurisdicao,
            data_avaliacao=date.today(),
            total_servicos_esperados=total_servicos_esperados,
            total_cpus_presentes=total_cpus_presentes,
            total_gaps=len(gaps),
            cobertura_pct=round(cobertura_pct, 1),
            producoes_com_dados_reais=prods_reais,
            producoes_apenas_tabulares=prods_tabela,
            producoes_confianca_baixa=prods_baixa,
            confianca_media=round(confianca_media, 1),
            gaps_ausente=gaps_ausente,
            gaps_sem_produtividade=gaps_sem_prod,
            gaps_baixa_confianca=gaps_baixa,
            status=status,  # type: ignore[arg-type]
            gaps=gaps,
        )


class CatalogGapResolver:
    """Propõe resolução de gaps a partir de fontes autoritativas (ADR-012 §D3)."""

    def resolve(
        self,
        gap: CatalogGap,
        fonte: FonteAutoritativa,
        dados_fonte: dict | None = None,
    ) -> ResolutionProposal:
        """Gera proposta de CPU + produtividade para um gap."""
        if dados_fonte is None:
            return ResolutionProposal(
                gap=gap,
                status="NAO_ENCONTRADO",
                fonte_id=fonte.id,
            )

        return ResolutionProposal(
            gap=gap,
            status="PROPOSTO",
            cpu_codigo_proposto=dados_fonte.get("codigo"),
            producao_horaria_proposta=dados_fonte.get("producao_horaria"),
            custo_unitario_proposto=dados_fonte.get("custo_unitario"),
            unidade=dados_fonte.get("unidade"),
            fonte_id=fonte.id,
            requer_aprovacao=True,
        )
