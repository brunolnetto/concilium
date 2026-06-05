"""ADR-029 Fase 1 — camada domain.

Pacote raiz da camada de domínio DDD. Subpacotes:
  domain/models        — entidades, value objects, modelos Pydantic
  domain/validations   — validadores de regras de negócio
  domain/repositories  — port interfaces (ABCs) + re-exports dos repositórios
  domain/resolution    — resolução semântica de insumos
  domain/scheduling    — algoritmos de agendamento
  domain/semantic      — camada semântica de vocabulário
"""
