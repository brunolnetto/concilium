"""Relatório financeiro PDF (parte extraída de financial_report_pdf.py, grupo _text_helpers)."""

from __future__ import annotations

import html
import re

_CHART_LABELS: dict[str, str] = {
    "scurve_custo": "Curva S de Custo Acumulado",
    "bar_direto_atividade_temporal": "Custo Direto por Atividade (Evolução Temporal)",
    "pool_utilizacao_temporal": "Utilização do Pool de Equipamentos",
    "pool_custo_estado": "Custo por Estado do Pool de Recursos",
    "pool_economia": "Economia de Pool vs. Execução Autônoma",
    "painel_equilibrio": "Painel de Ponto de Equilíbrio",
    "gantt_cronograma": "Cronograma de Execução (Gantt RCPSP)",
    "fluxo_financeiro": "Fluxo de Caixa do Projeto",
    "area_tempo_componente": "Evolução de Custos por Componente",
    "bar_atividade_componente": "Composição de Custos por Atividade",
    "bar_categoria_componente": "Composição de Custos por Categoria de Insumo",
    "bar_combustivel_tipo_temporal": "Consumo de Combustível por Tipo (Temporal)",
    "bar_diesel_temporal": "Consumo de Diesel ao Longo do Projeto",
    "bar_tempo_direto_categoria": "Custo Direto por Categoria (Evolução Temporal)",
    "bar_tempo_indireto_categoria": "Custos Indiretos por Categoria (Evolução Temporal)",
    "bar_tempo_natureza": "Distribuição de Custos por Natureza (Temporal)",
    "dependencia_eap": "Rede de Dependências da EAP",
    "hist_equipamentos": "Histograma de Utilização de Equipamentos",
    "hist_mao_obra": "Histograma de Utilização de Mão de Obra",
}


_CHART_CAPTIONS: dict[str, str] = {
    "scurve_custo": "Acúmulo de custos ao longo das semanas do projeto, comparado ao planejado.",
    "bar_direto_atividade_temporal": "Distribuição semanal do custo direto por atividade da EAP.",
    "pool_utilizacao_temporal": "Taxa de utilização de cada equipamento do pool ao longo do tempo.",
    "pool_custo_estado": "Custo de recursos agrupado por estado operacional (produtivo, standby, ocioso).",
    "pool_economia": "Comparativo de custo entre execução via pool e execução autônoma por atividade.",
    "painel_equilibrio": "Ponto de equilíbrio financeiro por atividade: receita atribuída vs. custo total.",
    "gantt_cronograma": "Cronograma RCPSP otimizado: barras indicam início, duração e folga de cada frente.",
    "fluxo_financeiro": "Entradas e saídas de caixa por período, evidenciando o saldo acumulado.",
    "area_tempo_componente": "Evolução semanal dos custos decompostos em MO, EQ, Diesel e Materiais.",
    "bar_atividade_componente": "Composição de custo (MO, EQ, Diesel, Mat) para cada atividade da EAP.",
    "bar_categoria_componente": "Participação de cada categoria de insumo no custo direto total.",
    "bar_combustivel_tipo_temporal": "Consumo semanal de combustível separado por tipo de equipamento.",
    "bar_diesel_temporal": "Volume e custo do diesel consumido semana a semana.",
    "bar_tempo_direto_categoria": "Evolução semanal do custo direto por categoria de insumo.",
    "bar_tempo_indireto_categoria": "Evolução semanal dos custos indiretos por categoria.",
    "bar_tempo_natureza": "Participação semanal de custos diretos vs. indiretos no custo total.",
    "dependencia_eap": "Grafo de precedências entre atividades da Estrutura Analítica de Projeto.",
    "hist_equipamentos": "Distribuição das horas de utilização por equipamento ao longo do projeto.",
    "hist_mao_obra": "Distribuição das horas trabalhadas por categoria de mão de obra.",
}


def _chart_label(filename: str) -> str:
    """Converte nome de arquivo PNG em título legível."""
    slug = filename.replace(".png", "")
    if slug in _CHART_LABELS:
        return _CHART_LABELS[slug]
    # Fallback: capitalize e substitui underscores por espaços
    return slug.replace("_", " ").title()


def _chart_caption(filename: str) -> str:
    """Retorna legenda/caption para o gráfico, ou string vazia."""
    slug = filename.replace(".png", "")
    return _CHART_CAPTIONS.get(slug, "")


def _fmt_localizacao(loc: str | None) -> str:
    """Converte 'lat=X, lng=Y' em formato legível; retorna original caso não seja coordenada."""
    if not loc:
        return "-"
    m = re.match(r"lat\s*=\s*([-\d.]+),?\s*lng\s*=\s*([-\d.]+)", str(loc))
    if not m:
        return loc
    lat, lng = float(m.group(1)), float(m.group(2))
    # Mapeamento simplificado de faixas de coordenadas para estados brasileiros
    # (cobre os principais biomas e faixas relevantes para obras de infraestrutura)
    estado = _br_estado_approx(lat, lng)
    lat_fmt = f"{abs(lat):.2f}°{'S' if lat < 0 else 'N'}"
    lng_fmt = f"{abs(lng):.2f}°{'O' if lng < 0 else 'L'}"
    if estado:
        return f"{estado}, Brasil ({lat_fmt}, {lng_fmt})"
    return f"Brasil ({lat_fmt}, {lng_fmt})"


def _br_estado_approx(lat: float, lng: float) -> str | None:
    """Aproximação grosseira de estado brasileiro por bounding box."""
    # Tabela compacta: (lat_min, lat_max, lng_min, lng_max, sigla, nome)
    _BOXES = [
        (-5.3, 2.8, -52.6, -44.0, "PA", "Pará"),
        (-18.4, -7.4, -48.0, -39.6, "TO/BA", "Tocantins / Bahia"),
        (-4.5, 0.0, -48.0, -43.0, "MA", "Maranhão"),
        (-7.5, -2.4, -41.5, -34.8, "CE", "Ceará"),
        (-9.0, -6.0, -38.0, -34.8, "BA/PE", "Bahia / Pernambuco"),
        (-10.0, -6.5, -41.5, -37.0, "BA", "Bahia"),
        (-23.0, -19.0, -53.0, -44.0, "SP/PR", "São Paulo / Paraná"),
        (-23.8, -19.8, -44.0, -40.3, "MG", "Minas Gerais"),
        (-33.8, -27.0, -57.0, -48.0, "RS", "Rio Grande do Sul"),
        (-15.0, -7.0, -61.0, -48.0, "MT/GO", "Mato Grosso / Goiás"),
    ]
    for lat_min, lat_max, lng_min, lng_max, _sigla, nome in _BOXES:
        if lat_min <= lat <= lat_max and lng_min <= lng <= lng_max:
            return nome
    return None


def _brl(v: float) -> str:
    v = float(v)
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(v: float) -> str:
    x = float(v)
    if -1.0 <= x <= 1.0:
        x *= 100.0
    return f"{x:.2f}%"


def _safe_text(v: object) -> str:
    return html.escape(str(v or ""), quote=False)


def _fmt_cpu_descricao(cpu_id: str) -> str:
    """Formata um cpu_id quando a descrição está ausente.

    'CPU-TERRA-ATI-003' → 'ATI 003'
    'CPU-TERRA-ESCO-CARGA-1CAT-DMT2000' → 'ESCO CARGA 1CAT DMT2000'
    """
    s = cpu_id
    # Remove prefixo 'CPU-TERRA-' ou 'CPU-' genérico
    for prefix in ("CPU-TERRA-", "CPU-"):
        if s.upper().startswith(prefix):
            s = s[len(prefix) :]
            break
    return s.replace("-", " ").title()


def _fmt_tipo_id(tipo_id: str) -> str:
    """Formata tipo_id de instância de recurso.

    Remove sufixo de hash hexadecimal como '-cdc3632643c1', substitui underscores.
    """
    # Sufixo hash: hífen seguido de 12+ chars hex
    s = re.sub(r"-[0-9a-f]{10,}$", "", tipo_id, flags=re.IGNORECASE)
    return s.replace("_", " ").replace("-", " ").title()


