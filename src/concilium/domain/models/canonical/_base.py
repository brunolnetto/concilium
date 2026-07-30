"""Camada 4 — Modelo canônico do orçamento (parte extraída de canonical.py)."""

from datetime import date, datetime
from typing import Literal, cast, get_args
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from statemachine import State, StateMachine

StatusValidacao = Literal["OK", "AVISO", "ERRO", "INFO"]
StatusMargem = Literal["VERDE", "AMARELO", "VERMELHO"]
StatusProjeto = Literal["RASCUNHO", "EM_VALIDACAO", "APROVADO", "EM_EXECUCAO", "CONCLUIDO"]


class ProjetoStatusMachine(StateMachine):
    """Máquina de estados do ciclo de vida do projeto."""

    rascunho = State("RASCUNHO", value="RASCUNHO", initial=True)
    em_validacao = State("EM_VALIDACAO", value="EM_VALIDACAO")
    aprovado = State("APROVADO", value="APROVADO")
    em_execucao = State("EM_EXECUCAO", value="EM_EXECUCAO")
    concluido = State("CONCLUIDO", value="CONCLUIDO", final=True)

    enviar_validacao = rascunho.to(em_validacao)
    cancelar_validacao = em_validacao.to(rascunho)
    # Compatibilidade com fluxo atual do CLI: aprovar também a partir de RASCUNHO.
    aprovar = rascunho.to(aprovado) | em_validacao.to(aprovado)
    iniciar_execucao = aprovado.to(em_execucao)
    concluir = em_execucao.to(concluido)


def transition_status_projeto(status_atual: StatusProjeto, status_destino: StatusProjeto) -> StatusProjeto:
    """Valida e aplica transição de status via `python-statemachine`."""
    if status_atual == status_destino:
        return status_atual

    machine = ProjetoStatusMachine(start_value=status_atual)
    eventos_por_destino: dict[StatusProjeto, tuple[str, ...]] = {
        "RASCUNHO": ("cancelar_validacao",),
        "EM_VALIDACAO": ("enviar_validacao",),
        "APROVADO": ("aprovar",),
        "EM_EXECUCAO": ("iniciar_execucao",),
        "CONCLUIDO": ("concluir",),
    }

    eventos_disponiveis = {evento.id for evento in machine.allowed_events}
    for nome_evento in eventos_por_destino[status_destino]:
        if nome_evento in eventos_disponiveis:
            getattr(machine, nome_evento)()
            return cast(StatusProjeto, machine.current_state_value)

    raise ValueError(
        f"Transição de status inválida: {status_atual} -> {status_destino}. "
        f"Permitidas a partir de {status_atual}: {sorted(eventos_disponiveis)}"
    )


class ValidacaoItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    codigo: str
    status: StatusValidacao
    mensagem: str | None = None


class Meta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    versao_schema: str = "1.0.0"
    gerado_em: datetime
    framework: Literal["concilium"] = "concilium"
    contexto_id: str
    # ADR-031: escopo e plano que geraram este canônico
    escopo_id: str = "default"
    plano_id: str | None = None


class Coordenadas(BaseModel):
    model_config = ConfigDict(extra="ignore")

    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class RegimeTrabalho(BaseModel):
    """ADR-148: `horas_improdutivas_dia` é tempo fixo por dia (não fração da
    jornada) perdido por ineficiência estrutural (deslocamento interno,
    preparação de frente de serviço). Afeta só a produção operacional
    (`eta_jornada`) — não recalibra custo/PU de catálogo.
    """

    model_config = ConfigDict(extra="ignore")

    dias_semana: int = Field(ge=1, le=7)
    horas_dia: int = Field(ge=1, le=24)
    # ADR-148 D5: ge=0 (não gt=0) para acomodar a migração de specs legados, que
    # gravam 0.0 explicitamente para preservar comportamento. 0.0 = "sem
    # ineficiência modelada" (legado); >0 é o padrão recomendado para specs novos
    # (default abaixo), reforçado na camada de apresentação, não no modelo.
    horas_improdutivas_dia: float = Field(default=0.5, ge=0)

    @model_validator(mode="after")
    def _valida_horas_improdutivas(self) -> "RegimeTrabalho":
        if self.horas_improdutivas_dia >= self.horas_dia:
            raise ValueError(
                "horas_improdutivas_dia deve ser menor que horas_dia "
                f"(recebido {self.horas_improdutivas_dia} >= {self.horas_dia})"
            )
        return self

    @property
    def eta_jornada(self) -> float:
        """ADR-148: fração produtiva do dia = (horas_dia - horas_improdutivas_dia) / horas_dia."""
        return (self.horas_dia - self.horas_improdutivas_dia) / self.horas_dia


class Projeto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID | str
    nome: str
    tipo_obra: Literal["terraplenagem", "pavimentacao", "saneamento"]
    # localizacao aceita string legada ("Brasil") ou Coordenadas {lat, lng} (normalizado)
    localizacao: str | Coordenadas
    coordenadas: Coordenadas
    regime_trabalho: RegimeTrabalho
    data_inicio: date
    data_termino: date
    # ADR-041: data de referência para resolução histórica de preços (SCD Type 2)
    data_base_orcamento: date | None = None
    status: StatusProjeto = "RASCUNHO"
    snapshot_catalogo_id: str
    snapshot_perfil_id: str
    revisao: int = Field(default=1, ge=1)
    # ADR-023: snapshot do PerfilBdiProjeto confirmado em `concilium project create`
    bdi_perfil_id: str | None = None

    def can_transition_to(self, status_destino: StatusProjeto) -> bool:
        try:
            transition_status_projeto(self.status, status_destino)
        except ValueError:
            return False
        return True

    def with_status(self, status_destino: StatusProjeto) -> "Projeto":
        novo_status = transition_status_projeto(self.status, status_destino)
        return self.model_copy(update={"status": novo_status})


def tipos_obra_validos() -> tuple[str, ...]:
    """Valores válidos de `Projeto.tipo_obra` — fonte única de verdade, derivada do próprio
    `Literal` do modelo (nunca duplicar como lista solta em ferramentas MCP/schemas JSON, que
    podem divergir do modelo silenciosamente — ver issue de projeto órfão sem versão criado
    com `tipo_obra` inválido: a persistência acontecia antes de qualquer validação)."""
    return get_args(Projeto.model_fields["tipo_obra"].annotation)


class Praticabilidade(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fonte: str
    limiar_inviabilidade_mm: float = Field(ge=0)
    calculada_em: datetime
    # Chave: ISO week "AAAA-Www" (ex. "2026-W23"). Valor: fração produtiva [0,1].
    # Dict vazio = dados não disponíveis (skill 02 fará fallback para percentual_produtivo_mensal)
    percentual_produtivo_semanal: dict[str, float] = Field(default_factory=dict)
    # Chave mensal "MM" (ex. "06") — mantido para retrocompatibilidade e fallback
    percentual_produtivo_mensal: dict[str, float] = Field(default_factory=dict)
