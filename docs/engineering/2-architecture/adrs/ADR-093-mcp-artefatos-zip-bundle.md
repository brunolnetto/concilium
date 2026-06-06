# ADR-093 — MCP como Serviço de Artefatos: Download de Relatórios, Gráficos e Planilhas

**Status:** ✅ Implementado — entrega real via Azure Blob/URL fica com ADR-096 (seam pronto)
**Data:** 2026-05-30
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-037 (MCP Facade), ADR-018 (Typed Artifacts), ADR-092

---

## Contexto

### Problema

P1. Para cada projeto executado, o pipeline Concilium gera artefatos ricos: relatórios
markdown, gráficos PNG, planilha Excel, PDFs. Esses artefatos vivem no `ProjectStore`
(disco local) mas não são servíveis via MCP tool call. Um agente ou usuário remoto não
tem acesso programático a eles.

P2. Com o deploy em Azure (ADR-096), os artefatos não estarão no filesystem local
do agente consumidor. É necessário um mecanismo de transporte independente de
localização.

P3. A entrega de resultados a engenheiros e decisores hoje requer acesso ao servidor
local. Isso impede o uso por qualquer stakeholder remoto — diretores, clientes, etc.

**Nota sobre calibração:** o mecanismo de calibração histórica (`concilium benchmark run`)
produz adicionalmente um `benchmark_report.json` de confronto contra referências humanas
validadas. Esse artefato é específico do fluxo de calibração e não pertence ao bundle
de entrega de produção.

---

## Decisão

D1. **Quatro tools MCP de artefatos.**

```python
@mcp.tool()
def listar_artefatos_projeto(project_id: str, versao: str | None = None) -> dict:
    """Lista artefatos disponíveis com nome, tipo, tamanho, audiência e data."""

@mcp.tool()
def ler_artefato_texto(project_id: str, nome_arquivo: str,
                        versao: str | None = None) -> str:
    """Retorna conteúdo de artefatos textuais (md, json, csv)."""

@mcp.tool()
def baixar_artefato_binario(project_id: str, nome_arquivo: str,
                             versao: str | None = None) -> dict:
    """Retorna artefato binário como base64 (PNG, XLSX, PDF).
    Em produção Azure, retorna URL pré-assinada com TTL=15min."""

@mcp.tool()
def baixar_bundle_zip(project_id: str, versao: str | None = None,
                       filtro: list[str] | None = None) -> dict:
    """Empacota todos os artefatos em zip e retorna base64 ou URL."""
```

D2. **Classificação de artefatos por audiência.**

```python
ARTEFATOS_AGENTES = {
    "relatorio.md",    # narrativa completa para LLMs
    "memorial_bdi.md", # memorial de cálculo BDI
}
ARTEFATOS_HUMANOS = {
    "resultado_planejamento.xlsx",
    "*.png",           # 17 gráficos (gantt, pool, scurve, etc.)
    "memorial_bdi.pdf",
    "relatorio.pdf",
}
```

`listar_artefatos_projeto` inclui `audiencia: "agente" | "humano" | "ambos"` para
que o agente saiba o que processar vs. o que apenas incluir no bundle.

D3. **Bundle zip com `MANIFESTO.md` auto-gerado.**

```
concilium_{projeto}_{versao}/
  MANIFESTO.md          ← índice legível: o que cada arquivo contém
  relatorio.md
  memorial_bdi.md
  memorial_bdi.pdf
  resultado_planejamento.xlsx
  graficos/
    gantt_cronograma.png  pool_ciclo_vida.png  scurve_custo.png  ...
```

D4. **Transporte adaptativo por ambiente.**
- **Local**: `base64` inline no response (arquivos < 10MB)
- **Azure (produção)**: URL pré-assinada do Azure Blob Storage com TTL=15min

D5. **`resumo_executivo.md` — novo artefato para decisores.** Documento de 1 página
gerado automaticamente (skill-15 ou nova skill), contendo: status de aprovação,
preço operacional e margem, top-3 atividades críticas, levers prioritários de PE.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| R1 | Artefatos apenas via filesystem local | Não funciona para deploy remoto (ADR-096) |
| R2 | Retornar tudo como base64 sempre | Ineficiente para bundles grandes (> 50MB) |
| R3 | Endpoint REST separado para artefatos | Duplica superfície de acesso; MCP é o canal unificado |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Agentes autônomos | LLMs obtêm relatórios e gráficos sem acesso ao filesystem |
| Stakeholders remotos | Diretores e clientes recebem bundle consolidado via URL |
| Entrega padronizada | `MANIFESTO.md` documenta o conteúdo de cada entrega |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Artefatos binários grandes podem exceder limites de resposta MCP | Sempre usar URL pré-assinada em produção; base64 apenas local |
| URL pré-assinada expira | TTL configurável; agente recebe `expira_em` e pode re-solicitar |
| Base64 de bundle completo pode ser > 100MB | Aplicar filtro de audiência por default; lazy loading por arquivo |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| 1 | Tools MCP: `listar_artefatos_projeto`, `ler_artefato_texto`, `baixar_artefato_binario` | ✅ Implementado |
| 2 | `baixar_bundle_zip` com `MANIFESTO.md` auto-gerado (PNGs sob `graficos/`) | ✅ Implementado |
| 3 | `resumo_executivo.md` auto-gerado (skill-09 side_effects) | ✅ Implementado |
| 4 | Transporte adaptativo (Port `ArtifactTransport`): local base64 hoje; Azure Blob + URL pré-assinada quando ADR-096 prover a infra | ✅ Implementado (seam; adapter Azure stub) |

### Notas de implementação

- **Camada de serviço:** `src/concilium/application/services/artifact_bundle.py` —
  classificação por audiência (`classify_audience`), descrição (`describe_artifact`),
  `list_artifacts`, `read_text`, `read_binary_b64`, `build_bundle`. Opera sobre o
  layout em disco do `ProjectStore` (`outputs/`, `intermediate/`, `artifacts/`),
  com proteção contra path traversal e exclusão de sidecars `.meta.json`.
- **Tools MCP:** `src/concilium/presentation/mcp_server/tools/artifacts.py`, registradas
  em `server.py`. 4 tools sobre as mesmas funções de serviço.
- **Resumo executivo (D5):** `reports/executive_summary.py::render_resumo_executivo`
  gera o `resumo_executivo.md` (1 página: status, preço operacional e margem, top-3
  atividades críticas via `cost_criticality_report`, levers de PE viáveis). Escrito em
  `skill-09` side_effects junto ao `relatorio.md`; incluído na cópia de benchmark.
- **Transporte (D4):** `services/artifact_transport.py` define a porta
  `ArtifactTransport` com `LocalBase64Transport` (base64 inline < limite; senão caminho)
  e `AzureBlobTransport` (stub que aponta para ADR-096). `get_transport()` seleciona via
  env `CONCILIUM__ARTIFACT_TRANSPORT`. Trocar para URL pré-assinada = trocar o adapter,
  sem alterar `read_binary_b64`/`build_bundle`.
- **Cobertura:** 26 testes unitários (classificação, leitura texto/binário, bundle,
  filtro por audiência, path traversal, transporte local/azure, resumo executivo) +
  smoke do servidor MCP (35 tools).

## Definition of Done

### Fase 1
- [ ] `listar_artefatos_projeto` retorna todos artefatos com audiência correta
- [ ] `ler_artefato_texto` retorna conteúdo de `relatorio.md` e `memorial_bdi.md`
- [ ] `baixar_artefato_binario` retorna PNG e XLSX como base64 válido

### Fase 2
- [ ] `baixar_bundle_zip` gera zip com todos artefatos + `MANIFESTO.md`
- [ ] `MANIFESTO.md` descreve cada arquivo em linguagem natural

### Fase 3
- [ ] `resumo_executivo.md` gerado para projeto AGIS com conteúdo correto (< 1 página)

### Fase 4
- [ ] URL pré-assinada funcional para artefatos no Azure Blob Storage
- [ ] TTL=15min e campo `expira_em` presentes no response

---

## Relacionados

[[adr037-mcp-facade-simplification]] [[adr018-typed-artifact-system]]
[[adr092-formulario-qqp-eap]] [[adr094-deploy-azure]]
