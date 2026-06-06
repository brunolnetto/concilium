"""Máquina de estados para jobs de pipeline.

ADR-103: Jobs na Camada de Aplicação
ADR-102: Pipeline Jobs — Estado gerenciado por python-statemachine

Esta máquina define os estados possíveis e transições válidas para jobs de pipeline.
Garante que transições inválidas sejam bloqueadas e fornece auditoria clara.

Estados:
    - AGUARDANDO_FILA: Job criado, esperando worker disponível
    - EM_EXECUCAO: Worker pegou o job e está executando skill
    - CONCLUIDO: Skill finalizada com sucesso
    - ERRO: Skill falhou ou job foi cancelado
    - CANCELADO: Job foi cancelado manualmente (futuro)

Transições válidas:
    AGUARDANDO_FILA → EM_EXECUCAO → CONCLUIDO
                                  → ERRO
    AGUARDANDO_FILA → CANCELADO (futuro: cancelar antes de iniciar)
    EM_EXECUCAO → CANCELADO (futuro: cancelar durante execução)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from statemachine import State, StateMachine


class PipelineJobStateMachine(StateMachine):
    """Máquina de estados para gerenciar ciclo de vida de jobs de pipeline."""

    # ── Estados ────────────────────────────────────────────────────────────
    aguardando_fila = State(initial=True, value="AGUARDANDO_FILA")
    em_execucao = State(value="EM_EXECUCAO")
    concluido = State(value="CONCLUIDO", final=True)
    erro = State(value="ERRO", final=True)
    cancelado = State(value="CANCELADO", final=True)

    # ── Transições ─────────────────────────────────────────────────────────
    iniciar = aguardando_fila.to(em_execucao)
    completar = em_execucao.to(concluido)
    falhar = em_execucao.to(erro) | aguardando_fila.to(erro)
    cancelar = aguardando_fila.to(cancelado) | em_execucao.to(cancelado)

    def __init__(self, job_data: dict[str, Any]):
        """Inicializa state machine com dados do job.

        Args:
            job_data: Dicionário do job contendo todos os campos
        """
        self.job_data = job_data
        super().__init__()

    def on_enter_state(self, event: str, state: State) -> None:
        """Hook chamado ao entrar em qualquer estado."""
        # Log de auditoria para debugging
        import sys

        print(
            f"[job-state] Job {self.job_data['job_id'][:8]}... → {state.value} via {event}",
            file=sys.stderr,
        )

    def on_iniciar(self) -> None:
        """Hook executado ao iniciar execução."""
        self.job_data["iniciado_em"] = datetime.now(timezone.utc).isoformat()
        self.job_data["progresso"] = "Iniciando execução..."
        self.job_data["progresso_percentual"] = 0.0

    def on_completar(self, resultado: dict[str, Any]) -> None:
        """Hook executado ao completar com sucesso.

        Args:
            resultado: Dicionário com resultado da skill
        """
        self.job_data["finalizado_em"] = datetime.now(timezone.utc).isoformat()
        self.job_data["resultado"] = resultado
        self.job_data["progresso"] = "Concluído"
        self.job_data["progresso_percentual"] = 1.0

    def on_falhar(self, erro: str) -> None:
        """Hook executado ao falhar.

        Args:
            erro: Mensagem de erro
        """
        self.job_data["finalizado_em"] = datetime.now(timezone.utc).isoformat()
        self.job_data["erro"] = erro

    def on_cancelar(self, motivo: str = "Cancelado pelo usuário") -> None:
        """Hook executado ao cancelar.

        Args:
            motivo: Motivo do cancelamento
        """
        self.job_data["finalizado_em"] = datetime.now(timezone.utc).isoformat()
        self.job_data["erro"] = motivo

    @property
    def status_str(self) -> str:
        """Retorna status atual como string."""
        return str(self.current_state_value)

    @property
    def is_terminal(self) -> bool:
        """Verifica se job está em estado final."""
        return self.status_str in {"CONCLUIDO", "ERRO", "CANCELADO"}

    @property
    def pode_cancelar(self) -> bool:
        """Verifica se job pode ser cancelado."""
        return self.status_str in {"AGUARDANDO_FILA", "EM_EXECUCAO"}

    def validar_transicao(self, transicao: str) -> bool:
        """Valida se transição é possível sem executá-la.

        Args:
            transicao: Nome da transição ('iniciar', 'completar', 'falhar', 'cancelar')

        Returns:
            True se transição é válida
        """
        try:
            # Tenta obter o evento da máquina
            event = getattr(self, transicao, None)
            if event is None:
                return False

            # Verifica se transição está disponível
            return event.is_valid(self)
        except Exception:
            return False


def criar_state_machine(job_data: dict[str, Any]) -> PipelineJobStateMachine:
    """Factory para criar state machine a partir de job existente.

    Args:
        job_data: Dicionário do job

    Returns:
        State machine inicializada no estado correto
    """
    sm = PipelineJobStateMachine(job_data)

    # Se job já tem status diferente de inicial, atualiza a máquina
    status_atual = job_data.get("status", "AGUARDANDO_FILA")

    if status_atual == "EM_EXECUCAO":
        sm.iniciar()
    elif status_atual == "CONCLUIDO":
        sm.iniciar()
        sm.completar(resultado=job_data.get("resultado", {}))
    elif status_atual == "ERRO":
        if job_data.get("iniciado_em"):
            sm.iniciar()
        sm.falhar(erro=job_data.get("erro", "Erro desconhecido"))
    elif status_atual == "CANCELADO":
        sm.cancelar(motivo=job_data.get("erro", "Cancelado"))

    return sm
