"""ADR-032 — Entidades Versionadas: InsumoVersionado, CPUVersionada, JurisdicaoVersionada.

Cada entidade encapsula a linha do tempo de modificações via lista de versões datadas,
garantindo snapshots imutáveis em projetos aprovados.

Identificadores temporais seguem o padrão `id@YYYY-MM`:
    ex.: "AJUDANTE-BR-CE@2026-04" referencia a versão de Abril/2026 do insumo AJUDANTE-BR-CE.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ── Tipos compartilhados ─────────────────────────────────────────────────────


class DateRange(BaseModel):
    """Intervalo de vigência semi-aberto [inicio, fim)."""

    model_config = ConfigDict(extra="forbid")

    inicio: date
    fim: date | None = None  # None = vigência indefinida (versão atual)

    def vigente_em(self, data: date) -> bool:
        """Retorna True se `data` cai dentro deste intervalo."""
        if data < self.inicio:
            return False
        if self.fim is not None and data >= self.fim:
            return False
        return True


class RegistroAlteracao(BaseModel):
    """Entrada do trilha de alteração — quem, quando, por quê."""

    model_config = ConfigDict(extra="forbid")

    alterado_por: str
    data_alteracao: datetime
    motivo: str
    valor_anterior: float | None = None
    valor_novo: float | None = None


# ── InsumoVersionado ─────────────────────────────────────────────────────────


class VersaoInsumo(BaseModel):
    """Snapshot imutável de um insumo em um período específico."""

    model_config = ConfigDict(extra="forbid")

    versao: str = Field(
        pattern=r"^\d{4}-\d{2}$",
        description="Identificador de período: 'YYYY-MM'",
    )
    validade: DateRange
    preco_unitario: float = Field(ge=0)
    fonte_preco: Literal["catalogo_proprio", "tabela_referencia", "cotacao_mercado", "negociado"]
    tabela_referencia_id: str | None = None
    # NEP-031 L1: rental_unit especifica como equipamento e alugado
    rental_unit: Literal["hora_produtiva", "dia_calendario", "mes"] | None = None
    historico_alteracoes: list[RegistroAlteracao] = Field(default_factory=list)
    auditado_por: str
    auditado_em: datetime


class InsumoVersionado(BaseModel):
    """Insumo com linha do tempo completa de preços e fontes (ADR-032 §D4).

    Permite resgatar o preço vigente em qualquer data passada, garantindo
    imutabilidade dos canônicos aprovados.

    O campo `id_atu` carrega a referência temporal canônica:
        ex.: "AJUDANTE-BR-CE@2026-04"
    """

    model_config = ConfigDict(extra="ignore")

    id: str = Field(description="Identificador base sem timestamp. Ex.: 'AJUDANTE-BR-CE'")
    # ADR-165: acompanha TipoInsumo (catalogo.py) — TREINAMENTO/EXAME/BENEFICIO também
    # passam pela mesma SCD Type 2 de preço via `preco_na_data` (infrastructure/repositories/insumo.py).
    tipo: Literal["MATERIAL", "MAO_OBRA", "EQUIPAMENTO", "TERCEIRIZADO", "TREINAMENTO", "EXAME", "BENEFICIO"]
    descricao: str
    unidade: str
    versoes: list[VersaoInsumo] = Field(min_length=1)

    @property
    def id_atu(self) -> str:
        """Referência temporal da versão mais recente (vigente ou última)."""
        versao_atual = self.versao_vigente()
        tag = versao_atual.versao if versao_atual else (self.versoes[-1].versao if self.versoes else "?")
        return f"{self.id}@{tag}"

    def versao_vigente(self, data: date | None = None) -> VersaoInsumo | None:
        """Retorna a VersaoInsumo vigente na data informada (padrão: hoje)."""
        referencia = data or date.today()
        for v in reversed(self.versoes):
            if v.validade.vigente_em(referencia):
                return v
        return None

    def preco_em(self, data: date | None = None) -> float | None:
        """Retorna o preço unitário vigente na data, ou None se não encontrado."""
        v = self.versao_vigente(data)
        return v.preco_unitario if v else None


# ── CPUVersionada ────────────────────────────────────────────────────────────


class VersaoCPU(BaseModel):
    """Snapshot imutável de uma CPU em um período específico."""

    model_config = ConfigDict(extra="forbid")

    versao: str = Field(
        pattern=r"^\d{4}-\d{2}$",
        description="Identificador de período: 'YYYY-MM'",
    )
    validade: DateRange
    producao_horaria: float = Field(gt=0)
    custo_unitario_sem_encargos: float = Field(ge=0)
    encargos_aplicados_pct: float = Field(
        ge=0,
        le=5,
        description="Percentual de encargos sociais aplicado (ex: 1.777 = 177.7%)",
    )
    jurisdicao_id_atu: str = Field(description="ID@período da jurisdição usada. Ex.: 'BR-CE@2026-04'")
    historico_alteracoes: list[RegistroAlteracao] = Field(default_factory=list)
    auditado_por: str
    auditado_em: datetime


class CPUVersionada(BaseModel):
    """CPU com histórico completo de composições e custos (ADR-032 §D4).

    Garante que cálculos de projetos aprovados no passado sejam reproduzíveis
    usando exatamente o snapshot da CPU vigente à época.

    O campo `id_atu` carrega a referência temporal canônica:
        ex.: "ESCO-CARGA-1CAT-DMT2000@2026-04"
    """

    model_config = ConfigDict(extra="ignore")

    id: str = Field(description="Identificador base. Ex.: 'ESCO-CARGA-1CAT-DMT2000'")
    descricao: str
    unidade: str
    categoria: Literal["TERRAPLENAGEM", "PAVIMENTACAO", "DRENAGEM", "SANEAMENTO", "OBRAS_ARTE", "DIVERSOS"]
    versoes: list[VersaoCPU] = Field(min_length=1)

    @property
    def id_atu(self) -> str:
        """Referência temporal da versão mais recente."""
        versao_atual = self.versao_vigente()
        tag = versao_atual.versao if versao_atual else (self.versoes[-1].versao if self.versoes else "?")
        return f"{self.id}@{tag}"

    def versao_vigente(self, data: date | None = None) -> VersaoCPU | None:
        """Retorna a VersaoCPU vigente na data informada (padrão: hoje)."""
        referencia = data or date.today()
        for v in reversed(self.versoes):
            if v.validade.vigente_em(referencia):
                return v
        return None

    def custo_unitario_em(self, data: date | None = None) -> float | None:
        """Retorna custo unitário total (com encargos) vigente na data."""
        v = self.versao_vigente(data)
        if v is None:
            return None
        return round(v.custo_unitario_sem_encargos * (1 + v.encargos_aplicados_pct), 6)


# ── JurisdicaoVersionada ─────────────────────────────────────────────────────


class VersaoJurisdicao(BaseModel):
    """Snapshot imutável de uma jurisdição em um período específico."""

    model_config = ConfigDict(extra="forbid")

    versao: str = Field(
        pattern=r"^\d{4}-\d{2}$",
        description="Identificador de período: 'YYYY-MM'",
    )
    validade: DateRange
    percentual_encargos_clt: float = Field(
        ge=0,
        le=5,
        description="Percentual de encargos CLT (ex: 1.777 = 177.7%)",
    )
    percentual_encargos_pj: float = Field(
        ge=0,
        le=1,
        description="Percentual de encargos PJ (ex: 0.0 = 0%)",
    )
    moeda: str = Field(pattern=r"^[A-Z]{3}$")
    auditado_por: str
    auditado_em: datetime
    notas: str | None = None


class JurisdicaoVersionada(BaseModel):
    """Jurisdição com histórico de encargos e parâmetros regulatórios (ADR-032 §D4).

    Permite que um snapshot de projeto aprovado referencie exatamente quais
    percentuais de encargos foram válidos à época do orçamento.

    O campo `id_atu` carrega a referência temporal canônica:
        ex.: "BR-CE@2026-04"
    """

    model_config = ConfigDict(extra="ignore")

    # O pattern anterior (^[A-Z]{2,10}$) rejeitava hífen — incompatível com o próprio
    # exemplo da descrição ("BR-CE") e com id_atu (ex.: "BR-CE@2026-04"). O 3º
    # segmento opcional é o município (ADR-142, ex.: "BR-CE-FORTALEZA"), aninhado
    # dentro do grupo de UF (não irmão independente) para não aceitar um "UF"
    # mal formada reinterpretada como município sem UF — ver jurisdicao.py.
    id: str = Field(
        pattern=r"^[A-Z]{2,15}(-[A-Z]{2,15}(-[A-Z0-9_]{2,40})?)?$",
        description="Código da jurisdição. Ex.: 'BR-CE', 'GOIANIA', 'BR-CE-FORTALEZA'",
    )
    nome: str
    regime_trabalhista: Literal["CLT", "OUTRO"]
    versoes: list[VersaoJurisdicao] = Field(min_length=1)

    @property
    def id_atu(self) -> str:
        """Referência temporal da versão mais recente."""
        versao_atual = self.versao_vigente()
        tag = versao_atual.versao if versao_atual else (self.versoes[-1].versao if self.versoes else "?")
        return f"{self.id}@{tag}"

    def versao_vigente(self, data: date | None = None) -> VersaoJurisdicao | None:
        """Retorna a VersaoJurisdicao vigente na data informada (padrão: hoje)."""
        referencia = data or date.today()
        for v in reversed(self.versoes):
            if v.validade.vigente_em(referencia):
                return v
        return None

    def encargos_em(self, data: date | None = None, regime: Literal["CLT", "PJ"] = "CLT") -> float | None:
        """Retorna o percentual de encargos (como decimal) para o regime na data."""
        v = self.versao_vigente(data)
        if v is None:
            return None
        return v.percentual_encargos_clt if regime == "CLT" else v.percentual_encargos_pj
