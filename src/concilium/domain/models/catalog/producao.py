"""ADR-007 — Produtividade como Artefato de Primeira Classe.

Cada instância de Producao representa um valor de produtividade calibrado,
com rastreabilidade de origem, histórico de observações e auditoria.

Vive em config/producoes/<id>.json e é referenciada pela CPU via producao_id.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from concilium.domain.models.catalog.catalogo import ComposicaoPadraoEquipe

# Recurso que limita (gargaleia) a taxa de produção desta atividade.
# equipamento — produção proporcional ao número de unidades do equipamento principal
# mao_obra    — produção proporcional ao tamanho total da equipe (atividades labor-limited)
LimiteProducao = Literal["equipamento", "mao_obra"]


class OrigemProducao(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tipo: Literal["calibrado_contra_obra_real", "tabela_referencia", "estimado", "regressao"]
    fonte_id: str
    data_calibracao: datetime
    referencia: str


class CondicoesCalibração(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tipo_solo: str | None = None
    dmt_medio: float | None = None
    season: str | None = None
    sequenciamento: str | None = None
    equipamento_idade: int | None = None
    notas: str = ""


class QualidadeProducao(BaseModel):
    model_config = ConfigDict(extra="ignore")

    confianca_pct: int = Field(ge=0, le=100)
    intervalo_confianca: tuple[float, float]
    quantidade_amostras: int = Field(ge=1)
    desvio_padrao: float = Field(ge=0)


class ObservacaoProducao(BaseModel):
    model_config = ConfigDict(extra="ignore")

    obra_id: str
    periodo: str
    producao_realizada: float = Field(gt=0)
    delta_pct: float
    contexto_observado: dict[str, Any] = Field(default_factory=dict)
    confiabilidade: float = Field(ge=0, le=1)
    notas: str | None = None
    timestamp: datetime


class AuditoriaProducao(BaseModel):
    model_config = ConfigDict(extra="ignore")

    criado_por: str
    data_criacao: datetime
    ultima_modificacao: datetime
    modificado_por: str
    versao: str


def _fator_by_equipamento(equips_calib: list, equips_nova: list) -> float:
    if not equips_calib:
        return 1.0
    equip_principal_id = equips_calib[0].equip_id
    qtd_calib = 0.0
    qtd_nova = 0.0
    for e in equips_calib:
        if e.equip_id == equip_principal_id:
            qtd_calib += e.num_unidades
    for e in equips_nova:
        if e.equip_id == equip_principal_id:
            qtd_nova += e.num_unidades
    if qtd_calib == 0 or qtd_nova == 0:
        return 1.0
    return round(qtd_nova / qtd_calib, 6)


# ── ADR-130: Composição de Equipe como Grafo de Sinergia ──────────────────────

TipoRelacaoSinergia = Literal["acoplamento", "dimensionamento", "precondicao"]
FonteCapacidade = Literal["catalogo", "fabricante", "medicao_obra"]


class RelacaoSinergia(BaseModel):
    """Aresta do grafo de sinergia intra-equipe (ADR-130 D1)."""

    model_config = ConfigDict(extra="forbid")

    tipo: TipoRelacaoSinergia
    origem: str  # ref a FuncaoEquipe.funcao_id | EquipamentoEquipe.equip_id | MaterialEquipe.insumo_id
    destino: str
    razao: float | None = None  # dimensionamento: unidades de destino por unidade de capacidade de origem
    descricao: str | None = None


class CapacidadeElemento(BaseModel):
    """Parâmetro de capacidade de um elemento da composição — os poucos números que mudam (ADR-130 D1)."""

    model_config = ConfigDict(extra="forbid")

    elemento_id: str
    capacidade_horaria: float = Field(gt=0)  # na unidade de produção da CPU (ex.: m³/h)
    unidade: str
    fonte: FonteCapacidade = "catalogo"
    # Memória de cálculo/rationale por trás de capacidade_horaria — fórmula e premissas
    # usadas (ex.: capacidade de caçamba × ciclos/hora × fator de enchimento ×
    # eficiência, especificação de fabricante consultada), não apenas o valor final.
    # Especialmente relevante quando fonte="fabricante" (estimativa a partir de
    # especificação técnica, não medição de obra) — permite auditar a estimativa em
    # vez de tratá-la como número dado, alinhado à política do projeto de nunca
    # inventar capacidade_horaria sem rastro (ADR-130 F4).
    justificativa: str | None = None


class GrafoSinergiaEquipe(BaseModel):
    """Estrutura de sinergia da equipe: relações + capacidades. Opcional por CPU (ADR-130 D1)."""

    model_config = ConfigDict(extra="forbid")

    relacoes: list[RelacaoSinergia] = Field(default_factory=list)
    capacidades: list[CapacidadeElemento] = Field(default_factory=list)
    gargalo_declarado: str | None = None  # elemento_id; se None, derivado (ADR-130 D2)


def _fator_by_mao_obra(funcoes_calib: list, funcoes_nova: list) -> float:
    total_calib = sum(f.num_pessoas for f in funcoes_calib)
    total_nova = sum(f.num_pessoas for f in funcoes_nova)
    if total_calib == 0 or total_nova == 0:
        return 1.0
    return round(total_nova / total_calib, 6)


class Producao(BaseModel):
    """Artefato de produtividade — primeira classe, versionado, rastreável."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    codigo: str  # compartilhado entre versões (ex: "ESCO-CARGA-1CAT")
    descricao: str

    valor_horario: float = Field(gt=0)
    unidade: str

    origem: OrigemProducao
    condicoes_calibracao: CondicoesCalibração
    qualidade: QualidadeProducao
    composicao_padrao_equipe: ComposicaoPadraoEquipe = Field(alias="equipe")

    # Recurso que condiciona a taxa de produção — define como fator_producao() escala.
    # Padrão: "equipamento" (atividades de terraplenagem/pavimentação são equipment-limited).
    limite_producao: LimiteProducao = "equipamento"

    historico_observacoes: list[ObservacaoProducao] = Field(default_factory=list)
    auditoria: AuditoriaProducao

    # ADR-130 D1: grafo de sinergia intra-equipe — opcional, retrocompatível.
    # None (padrão) preserva o comportamento atual integralmente (D3 fallback).
    grafo_sinergia: GrafoSinergiaEquipe | None = None

    def fator_producao(self, nova_composicao: ComposicaoPadraoEquipe) -> float:
        """Razão de produtividade entre nova composição e composição de calibração.

        Para atividades limitadas por equipamento (padrão):
            fator = Σ num_unidades(equip_principal, nova) / Σ num_unidades(equip_principal, calib)

        Para atividades limitadas por mão de obra:
            fator = Σ num_pessoas(nova) / Σ num_pessoas(calib)

        Retorna 1.0 quando a composição é idêntica à de calibração.
        Retorna 1.0 quando o recurso principal não está presente em nova_composicao
        (evita divisão por zero em composições parciais — o chamador deve validar).

        Exemplo — escavar com 2 escavadeiras em vez de 1:
            fator = 2 / 1 = 2.0  -> producao_ajustada = valor_horario * 2.0
        """
        if self.limite_producao == "equipamento":
            return _fator_by_equipamento(self.composicao_padrao_equipe.equipamentos, nova_composicao.equipamentos)
        return _fator_by_mao_obra(self.composicao_padrao_equipe.funcoes, nova_composicao.funcoes)

    def producao_ajustada(self, nova_composicao: ComposicaoPadraoEquipe) -> float:
        """Produtividade horária ajustada para nova composição de equipe.

        producao_ajustada = valor_horario × fator_producao(nova_composicao)
        """
        return round(self.valor_horario * self.fator_producao(nova_composicao), 4)


# ── ADR-011: Productivity as Computable Artifact ──────────────────────────────


class ComponenteEquipamento(BaseModel):
    """Componente A da CPU: custo horário de equipamentos."""

    model_config = ConfigDict(extra="ignore")

    equipamentos: list[dict] = Field(default_factory=list)
    custo_horario_total: float = Field(ge=0)


class ComponenteMaoDeObra(BaseModel):
    """Componente B da CPU: custo horário de mão de obra."""

    model_config = ConfigDict(extra="ignore")

    funcoes: list[dict] = Field(default_factory=list)
    custo_horario_total: float = Field(ge=0)


class ComponenteCombustivel(BaseModel):
    """Componente C da CPU: custo horário de combustível."""

    model_config = ConfigDict(extra="ignore")

    equipamentos: list[dict] = Field(default_factory=list)
    custo_horario_total: float = Field(ge=0)


class ProdutividadeDetalhada(BaseModel):
    """Produtividade derivada de CPU com granularidade hora/dia/semana (ADR-011).

    Derivada deterministicamente da composição da CPU — não um dado avulso.
    custo_unitario = custo_horario_total / producao_horaria
    """

    model_config = ConfigDict(extra="ignore")

    codigo: str
    descricao: str
    unidade: str

    # Componentes derivados da CPU
    componente_equipamento: ComponenteEquipamento
    componente_mao_de_obra: ComponenteMaoDeObra
    componente_combustivel: ComponenteCombustivel

    # Produtividade horária (fonte: planilha PRODUÇÕES ou cálculo)
    producao_horaria: float = Field(gt=0)

    # Granularidade derivada (padrão: 8h/dia, 5 dias/semana)
    horas_dia: int = Field(default=8, ge=1, le=24)
    dias_semana: int = Field(default=5, ge=1, le=7)

    @property
    def producao_diaria(self) -> float:
        return round(self.producao_horaria * self.horas_dia, 4)

    @property
    def producao_semanal(self) -> float:
        return round(self.producao_horaria * self.horas_dia * self.dias_semana, 4)

    @property
    def custo_horario_total(self) -> float:
        return round(
            self.componente_equipamento.custo_horario_total
            + self.componente_mao_de_obra.custo_horario_total
            + self.componente_combustivel.custo_horario_total,
            4,
        )

    @property
    def custo_unitario(self) -> float:
        if self.producao_horaria <= 0:
            return 0.0
        return round(self.custo_horario_total / self.producao_horaria, 6)

    def producao_n_equipes(self, n: int, eficiencia: float = 1.0) -> float:
        """Produção de N equipes com fator de eficiência [0,2]."""
        return round(self.producao_semanal * n * eficiencia, 4)
