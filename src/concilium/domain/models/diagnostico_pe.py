"""Diagnóstico do Ponto de Equilíbrio — decomposição causal (ADR-060).

Todos os termos técnicos internos (η, F1, Cov) ficam neste módulo.
A UI usa somente os campos com sufixo _label e _descricao.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── Nomes para apresentação ao usuário ───────────────────────────────────────

_FATOR_LABELS: dict[str, str] = {
    "F_ETA_CLIMA": "Clima e sazonalidade",
    "F_CALENDARIO": "Feriados e recesso operacional",
    "F_CALENDARIO_ESTRUTURAL": "Ineficiência estrutural de calendário",
    "F_ETA_CROSS": "Mobilização na época errada",
    "F_IND_CLIMA": "Projeto mais longo por clima",
    "F_IND_RAMP": "Projeto mais longo pela entrada gradual",
    "F1_QUANTIZACAO": "Arredondamento de equipes",
    "F_RESIDUAL": "Variação operacional",
}

_FATOR_DESCRICOES: dict[str, str] = {
    "F_ETA_CLIMA": "Dias improdutivos por chuva ou condições adversas aumentam o custo "
    "porque a equipe continua sendo paga mesmo sem produzir.",
    "F_CALENDARIO": "Dias não úteis por feriados, pontos facultativos e recesso reduzem "
    "a capacidade civil da semana e elevam custo de permanência.",
    "F_CALENDARIO_ESTRUTURAL": "Parcela estrutural não evitável da indisponibilidade civil "
    "(feriados e recesso), análoga à quantização e restrições de mobilização.",
    "F_ETA_CROSS": "A mobilização foi iniciada no período de maior adversidade climática. "
    "Se iniciada em outra época, este custo seria evitável.",
    "F_IND_CLIMA": "Como o projeto durou mais por causa do clima, os custos fixos do canteiro "
    "(administração, laboratório, segurança) foram alocados por mais tempo.",
    "F_IND_RAMP": "A mobilização gradual estendeu o calendário do projeto, aumentando "
    "o overhead fixo alocado a esta atividade.",
    "F1_QUANTIZACAO": "O projeto precisa de X,Y equipes para este serviço. Na obra usamos "
    "X+1 equipes. O custo da fração extra é estrutural e inevitável.",
    "F_RESIDUAL": "Diferença não explicada pelos fatores acima — pode indicar desvio "
    "de produtividade real em relação ao catálogo.",
}

_FATOR_EVITAVEL: dict[str, bool] = {
    "F_ETA_CLIMA": False,
    "F_CALENDARIO": True,
    "F_CALENDARIO_ESTRUTURAL": False,
    "F_ETA_CROSS": True,
    "F_IND_CLIMA": False,
    "F_IND_RAMP": True,
    "F1_QUANTIZACAO": False,
    "F_RESIDUAL": True,
}


@dataclass(frozen=True)
class FatorPE:
    """Um fator que contribui para o desequilíbrio financeiro de uma atividade."""

    codigo: str  # "F_ETA_CLIMA" | "F_ETA_CROSS" | "F_IND_CLIMA" | ...
    gap_rs: float  # R$ atribuídos a este fator (positivo = custo extra)
    pct_gap: float  # fração do gap total (0–1)

    @property
    def label(self) -> str:
        return _FATOR_LABELS.get(self.codigo, self.codigo)

    @property
    def descricao(self) -> str:
        return _FATOR_DESCRICOES.get(self.codigo, "")

    @property
    def evitavel(self) -> bool:
        """True = este custo pode ser reduzido por uma decisão do planejador."""
        return _FATOR_EVITAVEL.get(self.codigo, True)


@dataclass(frozen=True)
class DiagnosticoPEItem:
    """Diagnóstico financeiro de uma atividade com PE em desequilíbrio."""

    atividade_id: str
    cpu_id: str
    descricao: str

    # Financeiro
    preco_venda: float
    custo_realizado: float
    gap_rs: float  # negativo = déficit
    pct_gap_sobre_venda: float

    # Métricas internas (usadas pelos builders, não pela UI diretamente)
    eta_real: float  # aproveitamento efetivo η = Q̃/N_total
    p_medio_uniforme: float  # praticabilidade média temporal
    cov_n_p: float  # Cov(n(t), p(t))
    eps_cross: float  # desvio da aproximação aditiva
    validez_aproximacao: bool  # True se |Cov/(n̄×p̄)| < 5%
    n_total: float  # team-weeks totais implantadas

    # Decomposição causal
    fatores: tuple[FatorPE, ...]  # ordenados por gap_rs desc

    # Recalibração
    l_aplicado: float
    l_requerido: float
    delta_l: float

    # Contexto de explicação vindo do cubo analítico (NEP-024/025)
    janela_critica_iso: str | None = None
    natureza_dominante: str | None = None  # "direto" | "indireto"
    custo_direto_cubo_rs: float = 0.0
    custo_indireto_cubo_rs: float = 0.0
    explicacao_janela: str | None = None

    # Labels para UI
    @property
    def aproveitamento_pct(self) -> float:
        """Aproveitamento de campo em %."""
        return round(self.eta_real * 100, 1)

    @property
    def aproveitamento_necessario_pct(self) -> float:
        """Aproveitamento mínimo necessário para PE = 0."""
        if self.gap_rs >= 0:
            return self.aproveitamento_pct
        return round((self.eta_real / (1 + self.gap_rs / self.custo_realizado)) * 100, 1)

    @property
    def gap_evitavel_rs(self) -> float:
        """Parcela do gap que é evitável por decisão do planejador."""
        return sum(f.gap_rs for f in self.fatores if f.evitavel)

    @property
    def gap_estrutural_rs(self) -> float:
        """Parcela inevitável do gap."""
        return sum(f.gap_rs for f in self.fatores if not f.evitavel)

    def to_dict(self) -> dict:
        import dataclasses

        def _c(o):
            if dataclasses.is_dataclass(o) and not isinstance(o, type):
                return {k: _c(v) for k, v in dataclasses.asdict(o).items()}
            if isinstance(o, (list, tuple)):
                return [_c(v) for v in o]
            return o

        return _c(self)


@dataclass(frozen=True)
class DiagnosticoPERelatorio:
    """Diagnóstico completo de PE para o projeto."""

    projeto_id: str
    gerado_em: str
    n_itens_deficit: int
    gap_total_rs: float
    gap_evitavel_rs: float
    gap_estrutural_rs: float
    fator_dominante_label: str
    aviso_cross_term: bool  # True se algum item tem timing-clima correlacionado
    l_medio_requerido: float
    itens_deficit: tuple[DiagnosticoPEItem, ...]
    consistencia_validada: bool  # invariante F1+Fη+Find+Fcross ≈ gap_total (±2%)
    # ADR-060: validações emitidas como ValidacaoItem-like codes
    validacoes_emitidas: tuple[str, ...] = ()  # ex: ("VAL-PE-CROSS-TERM",)
    # NEP-025: bloco para wizard de ação (natureza de custo por período)
    explicacao_natureza_periodo: dict = field(default_factory=dict)

    @property
    def resumo_causas(self) -> dict[str, float]:
        """Soma de cada fator pelo label, para o gráfico de barras do Overview."""
        totais: dict[str, float] = {}
        for item in self.itens_deficit:
            for f in item.fatores:
                totais[f.label] = totais.get(f.label, 0.0) + f.gap_rs
        return dict(sorted(totais.items(), key=lambda kv: kv[1], reverse=True))

    def to_dict(self) -> dict:
        import dataclasses

        def _c(o):
            if dataclasses.is_dataclass(o) and not isinstance(o, type):
                return {k: _c(v) for k, v in dataclasses.asdict(o).items()}
            if isinstance(o, (list, tuple)):
                return [_c(v) for v in o]
            return o

        return _c(self)
