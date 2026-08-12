"""Camada 2 — Catálogo: Insumo, CPU, TemplateObra."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from concilium.domain.models.catalog.disponibilidade_consumivel import DisponibilidadeConsumivel
from concilium.domain.models.financial.bdi import DecomposicaoEquipamento
from concilium.domain.units import normalize_unidade

TipoInsumo = Literal[
    "MATERIAL", "MAO_OBRA", "EQUIPAMENTO", "TERCEIRIZADO", "TREINAMENTO", "EXAME", "BENEFICIO"
]

# ADR-139 D1: origem de material consumível — atributo ortogonal a TipoInsumo.
# AQUISICAO_EXTERNA — comprado de fornecedor (tinta, areia comprada, aço).
# GERACAO_INTERNA  — produzido pela própria obra (terra escavada de corte,
#                    brita de usina própria); preco_unitario passa a representar
#                    custo interno de produção (ou 0.0 quando já capturado na
#                    CPU produtora), e análises de cotação devem excluí-lo.
# None             — não classificado (retrocompatível).
OrigemMaterial = Literal["AQUISICAO_EXTERNA", "GERACAO_INTERNA"]

# ADR-107 D1: "DIESEL" mantido como alias legado; "COMBUSTIVEL" é o termo canônico.
# Novos dados devem usar "COMBUSTIVEL"; leitura de dados legados aceita "DIESEL".
CategoriaCusto = Literal["MATERIAL", "COMBUSTIVEL", "DIESEL", "MAO_OBRA", "EQUIPAMENTO"]


class TipoCombustivel(StrEnum):
    """ADR-107 D3 — Tipos de combustível suportados."""

    DIESEL_S10 = "diesel_s10"
    DIESEL_S500 = "diesel_s500"
    CNG = "cng"  # Gás Natural Comprimido (GNV)
    BIODIESEL = "biodiesel"
    ELETRICO = "eletrico"
    OUTRO = "outro"


def _infer_tipo_combustivel(insumo_id: str) -> TipoCombustivel:
    """ADR-107 D6 — Infere TipoCombustivel a partir do código do insumo (fallback para DIESEL_S10)."""
    upper = insumo_id.upper()
    if "GNV" in upper or "CNG" in upper or "GAS-NATURAL" in upper:
        return TipoCombustivel.CNG
    if "BIODIESEL" in upper or "B100" in upper:
        return TipoCombustivel.BIODIESEL
    if "ELETRIC" in upper or "ELÉTR" in upper:
        return TipoCombustivel.ELETRICO
    if "S500" in upper:
        return TipoCombustivel.DIESEL_S500
    return TipoCombustivel.DIESEL_S10  # fallback seguro para todo diesel legacy


CategoriaCPU = Literal["TERRAPLENAGEM", "PAVIMENTACAO", "DRENAGEM", "SANEAMENTO", "OBRAS_ARTE", "DIVERSOS"]

ClasseInsumo = Literal[
    "exclusivo_dedicado",  # Classe A: uma instância -> uma atividade
    "exclusivo_compartilhavel",  # Classe B: alterna entre atividades no mesmo período
    "concorrente_compartilhavel",  # Classe C: cobre N atividades simultâneas
]

PapelFuncao = Literal[
    "direto",  # Produção direta — custo contabilizado em equipes diretas
    "indireto",  # Suporte de campo — custo contabilizado em indiretos (skill 05)
    "gestao",  # Gestão de obra — atribuído separadamente, fora da CPU padrão
]


class ClasseCompartilhamento(BaseModel):
    """Taxonomia de compartilhamento de insumo (ADR-016).

    Classe A — exclusivo_dedicado: custo integral por atividade.
    Classe B — exclusivo_compartilhavel: custo pro-rated por fracao_uso.
    Classe C — concorrente_compartilhavel: custo dividido por n_atividades_simultaneas,
               limitado a capacidade_cobertura instâncias.
    """

    model_config = ConfigDict(extra="forbid")

    classe: ClasseInsumo
    fracao_uso: float | None = Field(default=None, gt=0, le=1)
    capacidade_cobertura: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _validate_fields_per_class(self) -> ClasseCompartilhamento:
        if self.classe == "exclusivo_compartilhavel" and self.fracao_uso is None:
            raise ValueError("exclusivo_compartilhavel requer fracao_uso definida")
        if self.classe == "concorrente_compartilhavel" and self.fracao_uso is not None:
            raise ValueError("concorrente_compartilhavel não usa fracao_uso")
        return self


class HistoricoPreco(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preco_unitario: float = Field(ge=0)
    data_inicio_vigencia: date
    data_fim_vigencia: date | None = None
    fonte: str | None = None


class AtributosInsumo(BaseModel):
    """Atributos específicos por tipo de insumo.

    Campos cobrem os três tipos elementares (MAO_OBRA, EQUIPAMENTO, MATERIAL).
    Todos são opcionais; campos irrelevantes para um dado tipo ficam como None.

    MAO_OBRA
    --------
    categoria_sindical      : categoria sindical / faixa salarial (ex: "horista_CE")
    horas_extras_pct_padrao : percentual padrão de horas extras (ex: 0.25 = 25 %)
    custo_com_encargos      : custo mensal total incluindo encargos sociais (R$/mês)
    tipo_contrato           : regime de contratação ("CLT" ou "PJ")
    salario_mensal          : salário mensal base sem encargos (R$/mês)
    horas_mes               : horas trabalhadas por mês (h/mês) — também usado em EQ

    EQUIPAMENTO
    -----------
    consumo_litros_hora     : consumo de combustível (L/h)
    potencia_cv             : potência nominal (cv)
    codigo_planilha         : código na planilha de origem (ex: "E0001")
    valor_locacao_mensal    : custo mensal de locação (R$/mês)
    horas_mes               : horas produtivas por mês (h/mês)
    tipo_propriedade        : forma de aquisição ("proprio" ou "locacao")
    custo_produtivo_hora    : parcela produtiva do custo horário (R$/h)
    pct_manutencao          : percentual de manutenção aplicado sobre custo produtivo
    custo_manutencao_hora   : custo de manutenção por hora (R$/h)
    decomposicao_equip      : decomposição BDI por sub-categoria (ADR-023 §D3)

    MATERIAL
    --------
    fornecedor_referencia   : fornecedor de referência para cotação
    prazo_entrega           : prazo de entrega típico (texto livre, ex: "Imediato")

    MATERIAL / EQUIPAMENTO (COMBUSTIVEL)
    -------------------------------------
    disponibilidade         : estoque/capacidade/reabastecimento (ADR-128), opcional —
                               None = disponibilidade irrestrita (comportamento atual)

    MATERIAL (EPI) / TREINAMENTO / EXAME — ADR-165
    ------------------------------------------------
    vida_util_dias          : ciclo de substituição (EPI) ou revalidação (treinamento/exame), em dias
    funcoes_aplicaveis      : códigos de Insumo(MAO_OBRA) a que este item é específico —
                               None = comum a todas as funções (ex.: EPIs/treinamentos gerais)

    BENEFICIO — ADR-165
    --------------------
    periodicidade_beneficio : base temporal do preco_unitario ("diaria" ou "mensal")
    aplicavel_tipo_contrato : regimes a que o benefício se aplica — None = CLT e PJ
                               (ex.: jantar com ["CLT"] exclui PJ)
    quartos_por_casa        : ADR-170 — capacidade compartilhada (ex.: BEN-ALOJAMENTO,
                               uma casa serve várias pessoas, não é um benefício direto por pessoa)
    pessoas_por_quarto      : ADR-170 — usado junto de quartos_por_casa para derivar a
                               capacidade de pessoas por unidade do benefício
    """

    model_config = ConfigDict(extra="ignore")

    # ── MAO_OBRA ──────────────────────────────────────────────────────
    categoria_sindical: str | None = None
    horas_extras_pct_padrao: float | None = Field(default=None, ge=0, le=1)
    custo_com_encargos: float | None = Field(default=None, ge=0)
    tipo_contrato: Literal["CLT", "PJ"] | None = None
    salario_mensal: float | None = Field(default=None, ge=0)
    horas_mes: float | None = Field(default=None, gt=0)

    # ── EQUIPAMENTO ───────────────────────────────────────────────────
    consumo_litros_hora: float | None = Field(default=None, ge=0)
    potencia_cv: float | None = None
    codigo_planilha: str | None = None
    valor_locacao_mensal: float | None = Field(default=None, ge=0)
    tipo_propriedade: Literal["proprio", "locacao"] | None = None
    custo_produtivo_hora: float | None = Field(default=None, ge=0)
    pct_manutencao: float | None = Field(default=None, ge=0, le=1)
    custo_manutencao_hora: float | None = Field(default=None, ge=0)
    # ADR-023 §D3: decomposição de custo por sub-categoria para BDI correto (Phase 5)
    decomposicao_equip: DecomposicaoEquipamento | None = None

    # ── MATERIAL ──────────────────────────────────────────────────────
    fornecedor_referencia: str | None = None
    prazo_entrega: str | None = None

    # ── MATERIAL / EQUIPAMENTO (COMBUSTIVEL) — ADR-128 ─────────────────
    disponibilidade: DisponibilidadeConsumivel | None = None

    # ── MATERIAL (EPI) / TREINAMENTO / EXAME — ADR-165 ─────────────────
    vida_util_dias: int | None = Field(default=None, gt=0)
    funcoes_aplicaveis: list[str] | None = None

    # ── BENEFICIO — ADR-165 ─────────────────────────────────────────────
    periodicidade_beneficio: Literal["diaria", "mensal"] | None = None
    aplicavel_tipo_contrato: list[Literal["CLT", "PJ"]] | None = None
    # ── BENEFICIO (capacidade compartilhada) — ADR-170 ───────────────────
    quartos_por_casa: int | None = Field(default=None, gt=0)
    pessoas_por_quarto: int | None = Field(default=None, gt=0)

    # ── QUALQUER TIPO — ADR-181 D6 ────────────────────────────────────────
    # memoria_calculo : texto livre explicando como um preço fonte_preco="negociado"
    #                   acima do teto de materialidade foi obtido (headcount, distância,
    #                   verba, cotação de fornecedor, planilha do cliente, etc.) — mesmo
    #                   que rudimentar. Evita lump-sum sem rastro auditável (caso do
    #                   v7.json do RFI CMOC Ouvidor: 4 valores negociados de R$71,91 a
    #                   R$1,37M sem nenhuma composição documentada em lugar nenhum do
    #                   repositório). Ver ValidadorCPUInsumo.validar_composicao_negociado.
    memoria_calculo: str | None = None


class Insumo(BaseModel):
    """Item elementar do catálogo: material, mão de obra, equipamento ou terceirizado."""

    model_config = ConfigDict(extra="ignore")

    codigo: str = Field(pattern=r"^[A-Z0-9-]{3,40}$")
    tipo: TipoInsumo
    descricao: str
    unidade: str
    preco_unitario: float = Field(ge=0)

    @field_validator("unidade", mode="before")
    @classmethod
    def _normalizar_unidade(cls, v: str) -> str:
        return normalize_unidade(v)

    fonte_preco: Literal["catalogo_proprio", "tabela_referencia", "cotacao_mercado", "negociado"]
    tabela_referencia_id: str | None = None
    codigo_referencia_externa: str | None = None
    historico_precos: list[HistoricoPreco] = Field(default_factory=list)
    atributos_especificos: AtributosInsumo = Field(default_factory=AtributosInsumo)
    # ADR-016: classe de compartilhamento (None = não anotado ainda -> VAL-INS-CLASS-01)
    classe_compartilhamento: ClasseCompartilhamento | None = None
    # ADR-139 D1: origem do material (None = não classificado). Restrito a tipo MATERIAL.
    origem_material: OrigemMaterial | None = None
    # ADR-163 D6: soft delete — descontinuado nunca remove o arquivo (preserva
    # fidelidade retroativa de resolved_catalog.json/CatalogSnapshot). Default
    # "ativo" preserva retrocompatibilidade de todo catálogo existente.
    status: Literal["ativo", "descontinuado"] = "ativo"
    # ADR-181 D4: marca insumo cujo custo é evento físico de mobilização/desmobilização
    # (transporte de recurso até o canteiro, canteiro/instalação) — independente do
    # `tipo` (TERCEIRIZADO/SERVICO na prática, ex.: SUPVEG-MOB-*/CANTEIRO-* do v12.json
    # do CMOC Ouvidor). Usado pelo guard anti-double-count generalizado da skill-06
    # (`_mob.py`) para descontar do indireto MOB o que já foi contabilizado como
    # custo direto via `composicao_itens` de uma CPU na EAP — sem esta tag, o guard
    # da ADR-176 só enxergava `EquipeDireta.custo_mobilizacao_mensal` (double-count
    # confirmado em SERRA_VERDE, ADR-176 P5). Default False = comportamento anterior.
    classificacao_mob_demob: bool = False

    @model_validator(mode="after")
    def _validar_origem_material(self) -> Insumo:
        if self.origem_material is not None and self.tipo != "MATERIAL":
            raise ValueError(
                f"VAL-INSUMO-ORIGEM-01: origem_material ('{self.origem_material}') só é válido "
                f"para insumo tipo MATERIAL, recebido tipo '{self.tipo}' (insumo '{self.codigo}')"
            )
        return self

    @model_validator(mode="after")
    def _validar_campos_rh_adr165(self) -> Insumo:
        a = self.atributos_especificos
        if a.vida_util_dias is not None and self.tipo not in ("MATERIAL", "TREINAMENTO", "EXAME"):
            raise ValueError(
                f"VAL-INSUMO-VIDA-UTIL-01: vida_util_dias só é válido para insumo tipo "
                f"MATERIAL/TREINAMENTO/EXAME, recebido tipo '{self.tipo}' (insumo '{self.codigo}')"
            )
        if a.funcoes_aplicaveis is not None and self.tipo not in ("MATERIAL", "TREINAMENTO"):
            raise ValueError(
                f"VAL-INSUMO-FUNCOES-01: funcoes_aplicaveis só é válido para insumo tipo "
                f"MATERIAL/TREINAMENTO, recebido tipo '{self.tipo}' (insumo '{self.codigo}')"
            )
        if (
            a.periodicidade_beneficio is not None
            or a.aplicavel_tipo_contrato is not None
            or a.quartos_por_casa is not None
            or a.pessoas_por_quarto is not None
        ) and self.tipo != "BENEFICIO":
            raise ValueError(
                f"VAL-INSUMO-BENEFICIO-01: periodicidade_beneficio/aplicavel_tipo_contrato/"
                f"quartos_por_casa/pessoas_por_quarto só são válidos para insumo tipo BENEFICIO, "
                f"recebido tipo '{self.tipo}' (insumo '{self.codigo}')"
            )
        return self


class ComposicaoItem(BaseModel):
    """Linha da composição de uma CPU: insumo × coeficiente × categoria de custo.

    ADR-138 (Fase 1): escopo reduzido a `categoria_custo` MATERIAL/DIESEL.
    MAO_OBRA/EQUIPAMENTO foram removidos dos catálogos de produção
    (`mendeslobo`/`rfi-r02`/`samples`) — essas categorias eram redundantes com
    `Producao.composicao_padrao_equipe` (via `producao_id_ref`), que é a única
    fonte confiável de MAO_OBRA/EQUIPAMENTO na precificação bottom-up canônica
    (NEP-032 D1). O tipo `CategoriaCusto` ainda aceita MAO_OBRA/EQUIPAMENTO por
    retrocompatibilidade com catálogos legados/fixtures de teste, e o fallback
    de precificação (`_preco_cat_fallback_composicao`) falha alto
    (`VAL-PLAN-MO-EQ-SEM-FONTE`) se for acionado sem nenhuma linha dessas
    categorias — não deve ser usado para popular dado novo. MATERIAL/DIESEL
    permanecem aqui porque não têm hoje outra fonte no modelo (ADR-138 Fase 2
    pendente — ver docs/engineering/2-architecture/adrs/adr-138-*.md).
    """

    model_config = ConfigDict(extra="forbid")

    insumo_id: str
    coeficiente: float = Field(gt=0)
    categoria_custo: CategoriaCusto
    unidade: str | None = None
    # ADR-107 D2: tipo de combustível quando categoria_custo == "COMBUSTIVEL".
    # None = legado (assume DIESEL_S10 quando categoria == COMBUSTIVEL/DIESEL).
    tipo_combustivel: TipoCombustivel | None = None


class FuncaoEquipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    funcao_id: str
    num_pessoas: int = Field(ge=1)
    # ADR-132 D2 (revisão): fração de dedicação a esta frente quando o mesmo
    # headcount é compartilhado entre n_frentes simultâneas. None == 1,0
    # (dedicação integral, retrocompatível). Ver pu_calculator._acumular_custo_mo.
    fracao_dedicacao: float | None = Field(default=None, gt=0, le=1)
    horas_extras_pct: float | None = Field(default=None, ge=0, le=1)
    # Papel funcional na atividade — determina em qual pool de custo este membro é contabilizado.
    # direto   -> equipes diretas (skill 03)    | padrão para retrocompatibilidade
    # indireto -> custos indiretos de campo (skill 05)
    # gestao   -> equipe de gestão de obra (atribuída fora da CPU, per-projeto)
    papel: PapelFuncao = "direto"


class EquipamentoEquipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equip_id: str
    num_unidades: int = Field(ge=1)
    # ADR-132 D2 (revisão): fração de dedicação a esta frente quando a mesma
    # unidade é compartilhada entre n_frentes simultâneas. None == 1,0
    # (dedicação integral, retrocompatível). Ver pu_calculator._acumular_custo_equipamentos.
    fracao_dedicacao: float | None = Field(default=None, gt=0, le=1)
    # ADR-030 D1: consumo estimado na especificação da equipe (sobrepõe Insumo.atributos_especificos)
    consumo_litros_hora_estimado: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Consumo de combustível por unidade de equipamento por hora, em L/h. "
            "Sobrepõe Insumo.atributos_especificos.consumo_litros_hora na skill 03. "
            "Permite estimativas iniciais sem catálogo de insumos completo."
        ),
    )


class MaterialEquipe(BaseModel):
    """ADR-030 D2: Material direto consumido por hora de operação da equipe."""

    model_config = ConfigDict(extra="forbid")

    insumo_id: str
    consumo_por_hora: float = Field(
        gt=0,
        description="Quantidade consumida por hora de operação (ex: m³/h, kg/h, t/h)",
    )
    unidade: str
    descricao: str | None = None
    # ADR-139 D2 (resolve nota de design da ADR-138 §D7): proveniência da entrada.
    # consumo_operacional — semântica original ADR-030 D2 (água de umectação, aditivo).
    # bom_convertido      — BOM por unidade de produto convertido via
    #                       consumo_por_hora = coeficiente × valor_horario (ADR-138 F2).
    # None                — não classificado (retrocompatível).
    origem_entrada: Literal["consumo_operacional", "bom_convertido"] | None = None


class MaterialGerado(BaseModel):
    """ADR-139 D3: Material gerado por hora de operação da equipe — o lado produtor.

    Simétrico a `MaterialEquipe` (consumo_por_hora), na mesma base horária:
    quem tem o dado por unidade de produto converte com a mesma fórmula
    price-preserving `geracao_por_hora = geracao_por_unidade × valor_horario`.
    `insumo_id` deve referenciar Insumo com origem_material == "GERACAO_INTERNA"
    (VAL-PROD-GERACAO-01).
    """

    model_config = ConfigDict(extra="forbid")

    insumo_id: str
    geracao_por_hora: float = Field(
        gt=0,
        description="Quantidade gerada por hora de operação (ex: m³/h de solo de corte)",
    )
    unidade: str
    descricao: str | None = None


class ComposicaoPadraoEquipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    funcoes: list[FuncaoEquipe]
    equipamentos: list[EquipamentoEquipe]
    # ADR-030 D2: materiais diretos consumidos pela equipe por hora
    materiais: list[MaterialEquipe] = Field(default_factory=list)

    @property
    def funcoes_diretas(self) -> list[FuncaoEquipe]:
        """Membros com papel='direto' — contabilizados em equipes diretas."""
        return [f for f in self.funcoes if f.papel == "direto"]

    @property
    def funcoes_indiretas(self) -> list[FuncaoEquipe]:
        """Membros com papel='indireto' — contabilizados em custos indiretos."""
        return [f for f in self.funcoes if f.papel == "indireto"]

    @property
    def funcoes_gestao(self) -> list[FuncaoEquipe]:
        """Membros com papel='gestao' — atribuídos separadamente, fora da CPU."""
        return [f for f in self.funcoes if f.papel == "gestao"]

    @property
    def num_pessoas_diretas(self) -> int:
        return sum(f.num_pessoas for f in self.funcoes_diretas)

    @property
    def num_pessoas_total(self) -> int:
        return sum(f.num_pessoas for f in self.funcoes)


class AtributosCategoriaCPU(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dmt_min_metros: float | None = Field(default=None, ge=0)
    dmt_max_metros: float | None = None
    # DMT médio das condições de calibração desta CPU (rastreabilidade ADR-007)
    dmt_referencia_m: float | None = Field(default=None, ge=0)


class CPU(BaseModel):
    """Composição de Preço Unitário — dimensão de insumos e custos (ADR-053 Fase 3).

    CPU é responsável por: composicao_itens (coeficientes de insumo), atributos de categoria
    e a referência estrangeira producao_id_ref para a entidade Produtividade.

    NÃO contém mais: producao_horaria (removido), composicao_padrao_equipe (removido).
    Esses campos eram redundantes e geravam assincronia com o catálogo de Produtividades.
    Catálogos legados que ainda enviam esses campos têm-nos silenciosamente ignorados
    via extra='ignore' e devem ser migrados com scripts/refactor_cpu_producao_adr053.py.

    ADR-138 (Fase 1): composicao_itens NÃO contém mais linhas MAO_OBRA/EQUIPAMENTO
    em mendeslobo/rfi-r02 — essas categorias são sourced exclusivamente de
    Produtividade.composicao_padrao_equipe (via producao_id_ref), a mesma entidade
    referenciada acima. composicao_itens agora é escopo de MATERIAL/DIESEL nesses
    catálogos, que ainda não têm outra fonte no modelo (Fase 2 pendente). Migração
    feita com scripts/catalog/strip_composicao_itens_mo_eq.py. O catálogo `samples`
    é deliberadamente EXCLUÍDO dessa migração — sua Produtividade não tem
    composicao_padrao_equipe (dado incompleto), então ali composicao_itens
    MAO_OBRA/EQUIPAMENTO ainda é a fonte de preço ativa (ver ADR-138 §P5).
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    codigo: str = Field(pattern=r"^[A-Z0-9-]{4,40}$")
    descricao: str
    unidade: str
    origem: Literal["REFERENCIA", "PROPRIA"]

    @field_validator("unidade", mode="before")
    @classmethod
    def _normalizar_unidade(cls, v: str) -> str:
        return normalize_unidade(v)

    cpu_referencia_id: str | None = None
    # FK para Produtividade — única fonte de producao_horaria e composicao_padrao_equipe.
    producao_id_ref: str
    categoria: CategoriaCPU
    composicao_itens: list[ComposicaoItem] = Field(default_factory=list)
    # composicao_padrao_equipe REMOVIDO em ADR-053 Fase 3 — leia de Produtividade via producao_id_ref.
    atributos_categoria: AtributosCategoriaCPU = Field(default_factory=AtributosCategoriaCPU)

    @property
    def composicao_completa(self) -> list[ComposicaoItem]:
        """Retorna composição fixa da CPU (somente insumos da própria CPU)."""
        return list(self.composicao_itens)

    @model_validator(mode="after")
    def _validar_producao_e_coeficientes(self) -> CPU:
        if not self.producao_id_ref:
            raise ValueError(f"CPU {self.codigo!r}: producao_id_ref é obrigatório (ADR-053)")
        return self


class ServicoSugerido(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpu_id: str
    ordem: int = Field(ge=1)
    obrigatoriedade: Literal["essencial", "tipico", "opcional"]
    nota: str | None = None


class AtividadeSugerida(BaseModel):
    model_config = ConfigDict(extra="forbid")

    atividade_id: str
    cpu_id_pai: str
    fracao_quantitativo: float = Field(gt=0, le=1)
    descricao: str | None = None


class PrecedenciaSugerida(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predecessora: str
    sucessora: str


class TemplateObra(BaseModel):
    """EAP-base sugerida por tipo de obra (DEC-03)."""

    model_config = ConfigDict(extra="ignore")

    codigo: str = Field(pattern=r"^TPL-[A-Z0-9-]+$")
    tipo_obra: Literal["TERRAPLENAGEM", "PAVIMENTACAO", "SANEAMENTO"]
    descricao: str
    criterios_aplicacao: str | None = None
    servicos_sugeridos: list[ServicoSugerido] = Field(min_length=1)
    atividades_sugeridas: list[AtividadeSugerida] = Field(default_factory=list)
    precedencias_sugeridas: list[PrecedenciaSugerida] = Field(default_factory=list)
