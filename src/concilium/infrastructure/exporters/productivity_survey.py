from pathlib import Path

import pandas as pd

from .catalog_excel import CatalogExporterExcel


class ProductivitySurveyExporter(CatalogExporterExcel):
    """
    Exportador especializado em Pesquisa de Produtividade.
    Gera formulários para aferição de desempenho real vs benchmark.
    """

    def export(self, output_path: Path):
        producoes = self.catalogo.get("producoes", [])
        survey_data = []

        for p in producoes:
            base_info = {
                "ID Metodologia": p.get("id"),
                "Descrição": p.get("descricao"),
                "Unidade": p.get("unidade"),
                "Categoria": p.get("categoria"),
            }

            # Exporta a variante padrão/atual
            variants = p.get("variantes", [])
            if not variants:
                # Fallback se não houver variantes explícitas
                equipe = p.get("equipe", {})
                mo_bench = ", ".join([f"{f['funcao_id']}:{f['num_pessoas']}" for f in equipe.get("funcoes", [])])
                eq_bench = ", ".join([f"{e['equip_id']}:{e['num_unidades']}" for e in equipe.get("equipamentos", [])])

                survey_data.append(
                    {
                        **base_info,
                        "Variante": "Padrão",
                        "Produtividade Benchmark (h)": p.get("producao_horaria"),
                        "Equipe Benchmark": f"MO:[{mo_bench}] | EQ:[{eq_bench}]",
                        "PROD REAL (Aferido)": "",
                        "EQUIPE REAL (Aferido)": "",
                        "EQUIPAMENTO REAL (Aferido)": "",
                        "DMT Real (m)": "",
                        "Condição Climática": "",
                        "Notas de Campo": "",
                    }
                )
            else:
                for v in variants:
                    equipe = v.get("equipe", {})
                    mo_bench = ", ".join([f"{f['funcao_id']}:{f['num_pessoas']}" for f in equipe.get("funcoes", [])])
                    eq_bench = ", ".join(
                        [f"{e['equip_id']}:{e['num_unidades']}" for e in equipe.get("equipamentos", [])]
                    )

                    survey_data.append(
                        {
                            **base_info,
                            "Variante": v.get("nome", v.get("id")),
                            "Produtividade Benchmark (h)": v.get("producao_horaria"),
                            "Equipe Benchmark": f"MO:[{mo_bench}] | EQ:[{eq_bench}]",
                            "PROD REAL (Aferido)": "",
                            "EQUIPE REAL (Aferido)": "",
                            "EQUIPAMENTO REAL (Aferido)": "",
                            "DMT Real (m)": "",
                            "Condição Climática": "",
                            "Notas de Campo": "",
                        }
                    )

        df = pd.DataFrame(survey_data)

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Pesquisa_Produtividade")

            # Aplica estilo de formulário (Destaque Amarelo para campos de preenchimento)
            self._aplicar_estilo_survey_prod(writer)

        return output_path

    def _aplicar_estilo_survey_prod(self, writer):
        from openpyxl.styles import Font, PatternFill

        ws = writer.sheets["Pesquisa_Produtividade"]

        # Estilo base
        self._aplicar_estilo(writer)

        # Destaque para colunas de preenchimento (G a K)
        fill_input = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
        font_bold = Font(bold=True)

        # Colunas de G a K (7 a 11)
        for col_idx in range(7, 12):
            for row in range(2, ws.max_row + 1):
                cell = ws.cell(row=row, column=col_idx)
                cell.fill = fill_input
                cell.font = font_bold
