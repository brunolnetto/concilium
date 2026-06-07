from __future__ import annotations


def _print_pe_referencia(ponto_eq_ref) -> None:
    if not ponto_eq_ref:
        return
    print("\n  [PE] Ponto de Equilibrio (referencia):")
    print(f"     HC total          : {ponto_eq_ref.get('total_hc') or '?'}")
    custo_fixo = ponto_eq_ref.get("total_custo_fixo") or 0.0
    print(f"     Custo fixo total  : R$ {custo_fixo:>14,.2f}")
    print(f"     Num equipes       : {ponto_eq_ref.get('equipes') or '?'}")


def _print_pe_ferramenta(ponto_eq_tool) -> None:
    if not ponto_eq_tool:
        return
    print("\n  [PE] Ponto de Equilibrio Estrutural (Ferramenta):")
    print(f"     HC operacional    : {ponto_eq_tool.get('total_hc_operacional') or '0'}")
    print(f"     HC indireto       : {ponto_eq_tool.get('total_hc_indireto') or '0'}")
    print(f"     HC total          : {ponto_eq_tool.get('total_hc') or '0'}")
    custo_fixo_mensal = ponto_eq_tool.get("custo_fixo_mensal") or 0.0
    custo_fixo_total = ponto_eq_tool.get("custo_fixo_total") or 0.0
    print(f"     Custo fixo mensal : R$ {custo_fixo_mensal:>14,.2f}")
    print(f"     Custo fixo total  : R$ {custo_fixo_total:>14,.2f}")
    print(f"     Num equipes       : {ponto_eq_tool.get('equipes') or '0'}")


class BenchmarkReportPrinter:
    def _print_header(self, report: dict) -> None:
        quality_gates = report.get("quality_gates", {})
        status_final = report.get("status_final") or quality_gates.get("decision")
        print(f"\n  {'-' * 60}")
        print(f"  RELATORIO DE CONFRONTO: {report['projeto']}")
        print(f"  {'-' * 60}")
        if status_final:
            print(f"\n  [GATE] Status final      : {status_final}")
            print(f"  [GATE] Pior severidade   : {quality_gates.get('worst_severity') or 'S0'}")
            if quality_gates.get("critical_metric_over_10pct"):
                print("  [GATE] Regra 10% criticos: BLOQUEIO de aprovacao automatica ativa")

    def _print_referencia(self, confronto: dict) -> None:
        if not confronto.get("referencia"):
            return
        ref = confronto["referencia"]
        print("\n  [REF] Referencia (planilha real):")
        for key, value in ref.items():
            if value is not None:
                print(f"     {key:20s}: R$ {value:>14,.2f}")
            else:
                print(f"     {key:20s}: (nao disponivel)")

    def _print_ferramenta(self, confronto: dict) -> None:
        if not confronto.get("ferramenta"):
            return
        ferramenta = confronto["ferramenta"]
        print("  [TOOL] Ferramenta (Concilium):")
        if not ferramenta:
            print("     (sem resultado computado)")
            return
        direto_pu_q = ferramenta.get("custo_direto_pu_q")
        fmt_pu_q = f"R$ {direto_pu_q:>14,.2f}" if direto_pu_q is not None else "  (nao disponivel)"
        indireto = ferramenta.get("custo_indireto")
        preco_venda = ferramenta.get("preco_venda")
        bdi = ferramenta.get("bdi_lucro_impostos")
        fmt_indireto = f"R$ {indireto:>14,.2f}" if indireto is not None else "  (nao disponivel)"
        fmt_venda = f"R$ {preco_venda:>14,.2f}" if preco_venda is not None else "  (nao disponivel)"
        bdi_pct = f"{bdi * 100:.2f}%" if bdi is not None else "N/A"
        # Preço operacional honesto (total_com_bdi = custo instancial × BDI)
        preco_venda_cat = ferramenta.get("preco_venda_catalogo")
        fmt_venda_cat = f"R$ {preco_venda_cat:>14,.2f}" if preco_venda_cat is not None else ""
        print("     base metodologia        : Operacional (custo instancial x BDI)")
        print(f"     custo_direto_pu_q       : {fmt_pu_q}   <- PUxQ (alinhado c/ Referencia)")
        print(f"     custo_indireto          : {fmt_indireto}")
        print(
            f"     preco_venda (operac.)   : {fmt_venda}   <- custo instancial x BDI + indireto x BDI = markup efetivo {bdi_pct}"  # noqa: E501
        )
        if fmt_venda_cat:
            print(
                f"     preco_venda (PUxQ)      : {fmt_venda_cat}   <- PUxQ x BDI (ref. mercado)"  # noqa: E501
            )

    def _print_composicao_final(self, confronto: dict) -> None:
        if not confronto.get("composicao_final"):
            return
        composicao_final = confronto["composicao_final"]
        print("\n  [COMPOSICAO FINAL]:")
        for key, item in composicao_final.items():
            ref_val = item.get("referencia")
            tool_val = item.get("ferramenta")
            delta_abs = item.get("delta_absoluto")
            delta_pct = item.get("delta_percentual")
            delta_str = f"{delta_pct:+.2f}%" if delta_pct is not None else "N/A"
            ref_str = f"R$ {ref_val:>14,.2f}" if ref_val is not None else "  (nao disponivel)"
            tool_str = f"R$ {tool_val:>14,.2f}" if tool_val is not None else "  (nao disponivel)"
            delta_abs_str = f"R$ {delta_abs:+>14,.2f}" if delta_abs is not None else "  (nao disponivel)"
            print(f"     {key:20s}: ref {ref_str} | tool {tool_str} | delta {delta_abs_str} ({delta_str})")

    def _print_breakdown(self, confronto: dict) -> None:
        if not confronto.get("breakdown_por_fase"):
            return
        breakdown_por_fase = confronto["breakdown_por_fase"]
        print("\n  [BREAKDOWN POR FASE]:")
        direto = breakdown_por_fase.get("direto") or {}
        if direto:
            base = direto.get("base", "equipes")
            total_direto = direto.get("direto_total") or direto.get("direto_total_equipes", 0)
            print("     [DIRETO]")
            print(f"       base          : {base}")
            print(f"       mao_obra      : R$ {direto.get('mao_obra_total', 0):>14,.2f}")
            print(f"       equipamentos  : R$ {direto.get('equipamentos_total', 0):>14,.2f}")
            print(f"       diesel        : R$ {direto.get('diesel_total', 0):>14,.2f}")
            print(f"       materiais     : R$ {direto.get('materiais_total', 0):>14,.2f}")
            print(f"       total         : R$ {total_direto:>14,.2f}")
        indireto = breakdown_por_fase.get("indireto") or {}
        if indireto:
            print("     [INDIRETO]")
            print(f"       adm           : R$ {indireto.get('adm', 0):>14,.2f}")
            print(f"       top           : R$ {indireto.get('top', 0):>14,.2f}")
            print(f"       lab           : R$ {indireto.get('lab', 0):>14,.2f}")
            print(f"       qsms          : R$ {indireto.get('qsms', 0):>14,.2f}")
            print(f"       mob           : R$ {indireto.get('mob', 0):>14,.2f}")
            print(f"       total         : R$ {indireto.get('total', 0):>14,.2f}")

    def _print_ponto_equilibrio(self, confronto: dict) -> None:
        _print_pe_referencia(confronto.get("ponto_equilibrio_referencia"))
        _print_pe_ferramenta(confronto.get("ponto_equilibrio_ferramenta"))

    def _print_insights(self, confronto: dict) -> None:
        if not confronto.get("actionable_insights"):
            return
        insights = confronto["actionable_insights"]
        print("\n  [ACTIONABLE INSIGHTS]:")
        if "criticidade" in insights:
            print(f"     Criticidade       : {insights['criticidade']}")
        if "sensibilidade" in insights:
            print(f"     Sensibilidade     : {insights['sensibilidade']}")
        if "intervencao" in insights:
            print(f"     Intervencao       : {insights['intervencao']}")

    def _print_acoes(self, report: dict) -> None:
        if not report.get("action_report"):
            return
        print("\n  [ACOES GRANULARES]:")
        for item in report["action_report"]:
            delta_pct = item.get("delta_percentual")
            delta_str = f"{delta_pct:+.2f}%" if delta_pct is not None else "N/A"
            print(
                f"     {item.get('fase'):18s} | {item.get('metric'):20s} | "
                f"{item.get('classe'):13s} | {item.get('severidade')} | {delta_str} | {item.get('acao_recomendada')}"  # noqa: E501
            )

    def print(self, report: dict) -> None:
        confronto = report.get("confronto", {})
        self._print_header(report)
        self._print_referencia(confronto)
        self._print_ferramenta(confronto)
        self._print_composicao_final(confronto)
        self._print_breakdown(confronto)
        self._print_ponto_equilibrio(confronto)
        self._print_insights(confronto)
        self._print_acoes(report)
        if not confronto.get("referencia"):
            print("\n  [WARN] Sem dados de referencia para confronto.")
