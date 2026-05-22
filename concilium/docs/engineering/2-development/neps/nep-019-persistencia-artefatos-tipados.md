# NEP-019: Persistência e exposição de artefatos tipados de skills

**Status:** Concluído  
**Prioridade:** 🟠 Alto  
**Área:** Domínio  
**Tipo:** Feature + Governança  
**Esforço:** M  
**Identificado em:** 2026-05-21  
**Concluído em:** 2026-05-21

---

## Contexto

Skills como `15-relatorio-executivo` produzem `ArtifactEnvelope`, mas o runtime não persistia esses artefatos de forma padronizada para consumo operacional.

## Causa Raiz

Side effects do runtime estavam especializados por skill e focados em outputs/intermediate clássicos.

## Implementação

- Introdução de persistência genérica best-effort para `result.artifacts` em `vN/artifacts/`.
- Robustez no `FileSystemArtifactStore.save` para payload não-Pydantic (ex.: dict).
- API de projeto expandida para listar e baixar `typed_artifacts`.

## Critério de Aceite

1. `ArtifactEnvelope` produzido por skill resulta em payload + sidecar em disco.
2. `GET /artifacts` retorna lista `typed_artifacts`.
3. Download aceita `kind=typed_artifacts`.

## Evidências

- `src/concilium/application/runtime.py`
- `src/concilium/infrastructure/storage/artifact_store.py`
- `src/concilium/application/services/project_service.py`
