"""ADR-007 — Produtividade como Artefato de Primeira Classe.

Cada instância de Producao representa um valor de produtividade calibrado,
com rastreabilidade de origem, histórico de observações e auditoria.

Vive em config/producoes/<id>.json e é referenciada pela CPU via producao_id.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from concilium.domain.models.catalogo import ComposicaoPadraoEquipe

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
            equips_calib = self.composicao_padrao_equipe.equipamentos
            if not equips_calib:
                return 1.0
            # Equipamento principal: o primeiro na lista de calibração (mais representativo)
            equip_principal_id = equips_calib[0].equip_id
            qtd_calib = sum(e.num_unidades for e in equips_calib if e.equip_id == equip_principal_id)
            qtd_nova = sum(e.num_unidades for e in nova_composicao.equipamentos if e.equip_id == equip_principal_id)
            if qtd_calib == 0 or qtd_nova == 0:
                return 1.0
            return round(qtd_nova / qtd_calib, 6)
        else:  # mao_obra
            total_calib = sum(f.num_pessoas for f in self.composicao_padrao_equipe.funcoes)
            total_nova = sum(f.num_pessoas for f in nova_composicao.funcoes)
            if total_calib == 0 or total_nova == 0:
                return 1.0
            return round(total_nova / total_calib, 6)

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
