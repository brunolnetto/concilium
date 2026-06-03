"""ADR-029 Fase 1 — camada infrastructure.

Pacote raiz da camada de infraestrutura DDD. Subpacotes:
  infrastructure/storage      — filesystem, copy-on-write (ProjectStore, SnapshotStore)
  infrastructure/clients      — clientes externos (OpenMeteo, FuelPriceClient)
  infrastructure/adapters     — renderizadores Excel, interpretador de templates
  infrastructure/catalog      — loader, updater, completeness do catálogo
  infrastructure/repositories — implementações concretas dos ports de domain/repositories
"""
