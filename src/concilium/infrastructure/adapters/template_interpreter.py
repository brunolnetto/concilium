"""Template Interpreter — Converte especificação JSON para operações Excel.

Lê planilha_planejamento.json e interpreta:
- Mapeamentos de sheets
- Seções dentro de sheets
- Origem canônica (dados para popular)
- Layout (linhas, colunas, estilos)
"""

import json
from pathlib import Path
from typing import Any


class TemplateInterpreter:
    """Interpreta template JSON de planilha_planejamento."""

    def __init__(self, template_path: Path | None = None):
        """Carrega template de especificação de planilha.

        Args:
            template_path: Caminho para planilha_planejamento.json.
                           Se None, usa padrão do projeto.
        """
        if template_path is None:
            # Tentar localizar template no projeto
            possible_paths = [
                Path(__file__).parent.parent.parent.parent / "config" / "templates" / "planilha_planejamento.json",
                Path("config/templates/planilha_planejamento.json"),
            ]
            for p in possible_paths:
                if p.exists():
                    template_path = p
                    break

        if template_path is None:
            raise FileNotFoundError("Template planilha_planejamento.json não encontrado")

        with open(template_path) as f:
            self.spec = json.load(f)

    def get_sheet_names(self) -> list[str]:
        """Retorna nomes de sheets em ordem."""
        sheets = self.spec.get("abas", {})
        return sorted(sheets.keys(), key=lambda k: sheets[k].get("ordem", 999))

    def get_sheet_spec(self, sheet_name: str) -> dict[str, Any]:
        """Retorna especificação completa de uma sheet."""
        return self.spec["abas"].get(sheet_name, {})

    def get_sheet_sections(self, sheet_name: str) -> list[dict[str, Any]]:
        """Retorna seções de uma sheet."""
        spec = self.get_sheet_spec(sheet_name)
        return spec.get("secoes", [])

    def get_sheet_category(self, sheet_name: str) -> str | None:
        """Retorna categoria de custos indiretos, se aplicável."""
        spec = self.get_sheet_spec(sheet_name)
        return spec.get("categoria_indireto")

    def is_indirect_cost_sheet(self, sheet_name: str) -> bool:
        """Verifica se sheet é de custos indiretos."""
        return self.get_sheet_category(sheet_name) is not None

    def get_indirect_cost_sheets(self) -> list[str]:
        """Retorna lista de sheets de custos indiretos em ordem."""
        sheets = self.get_sheet_names()
        return [s for s in sheets if self.is_indirect_cost_sheet(s)]

    def section_is_repetitive(self, section: dict[str, Any]) -> bool:
        """Verifica se seção é repetitiva (por item EAP, equipe, etc)."""
        return "repeticao" in section or "template_linhas" in section

    def get_section_source_path(self, section: dict[str, Any]) -> str | None:
        """Retorna caminho JMESPath para dados de uma seção."""
        return section.get("origem_canonico")

    def get_section_line_range(self, section: dict[str, Any]) -> tuple[int, int] | None:
        """Retorna intervalo de linhas (start, end) da seção."""
        if "linhas" in section:
            lines = section["linhas"]
            if isinstance(lines, list) and len(lines) > 0:
                return (min(lines), max(lines))

        if "template_linhas" in section:
            lines = section["template_linhas"]
            if isinstance(lines, list) and len(lines) > 0:
                return (min(lines), max(lines))

        return None

    def get_section_column_range(self, section: dict[str, Any]) -> tuple[str, str] | None:
        """Retorna intervalo de colunas (start, end) como letras Excel."""
        col_spec = section.get("colunas")
        if isinstance(col_spec, str) and ":" in col_spec:
            parts = col_spec.split(":")
            return (parts[0].strip(), parts[1].strip())
        return None

    def get_section_mapping(self, section: dict[str, Any]) -> dict[str, str]:
        """Retorna mapeamento de campos -> posições de células."""
        return section.get("mapeamento", {})

    def describe_sheet(self, sheet_name: str) -> str:
        """Retorna descrição legível de uma sheet."""
        spec = self.get_sheet_spec(sheet_name)
        desc = spec.get("descricao", "")
        cat = self.get_sheet_category(sheet_name)
        if cat:
            desc += f" (Categoria: {cat})"
        return desc
