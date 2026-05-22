"""Paleta de cores compartilhada pelos geradores de gráficos de benchmark.

Módulo central para evitar duplicação de _CORES e BG entre chart_generator.py
e seus helpers. Não deve ser importado fora do pacote application/benchmarks/.
"""

from __future__ import annotations

# Paleta corporativa — baseada na identidade visual MendesLobo
_CORES: dict[str, str] = {
    "azul_escuro": "#1B3A6B",
    "azul": "#2563EB",
    "azul_claro": "#60A5FA",
    "teal": "#0D9488",
    "verde": "#16A34A",
    "verde_claro": "#86EFAC",
    "laranja": "#EA580C",
    "vermelho": "#DC2626",
    "amarelo": "#CA8A04",
    "cinza_escuro": "#374151",
    "cinza": "#6B7280",
    "cinza_claro": "#E5E7EB",
    "roxo": "#7C3AED",
}

# Cor de fundo padrão para figuras matplotlib
BG: str = "#F8FAFC"
