# ADR-149 — Contexto de Projeto complementar à descrição de CPU (catálogo)

**Status:** ✅ Implementado
**Data:** 2026-07-24
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-040 (Schemas de Override de Catálogo a nível de Projeto — `CPUOverride`/`InsumoOverride`/`BDIOverride`), ADR-066 (snapshot de catálogo por-run)

---

## Contexto

### Problema

P1. Uma CPU do catálogo master (`CPU.descricao`, `domain/models/catalog/catalogo.py`) carrega uma única descrição textual, compartilhada por todos os projetos que a referenciam. Não existe hoje nenhum campo para o engenheiro anexar uma explicação específica do projeto em questão (ex.: uma particularidade de execução, uma condição de campo, uma justificativa de uso daquela CPU naquele contexto) — via investigação de código, confirmado que não existe `descricao_contexto`/`contexto_projeto`/`descricao_customizada` em nenhum schema, storage ou API do repositório.

P2. Os mecanismos mais próximos existentes servem outro propósito e não resolvem a necessidade:
- `CPUOverride` (ADR-040, `domain/models/project/overrides.py`) — exige `motivo`/`aprovado_por`/`aprovado_em`, workflow de calibração de produtividade/permanência. Forçar um texto explicativo por esse caminho sobrecarregaria uma governança pensada para mudanças que afetam preço/cálculo, não para uma anotação descritiva.
- `EapItem.descricao` (`domain/models/canonical/_eap.py`) — é por item de EAP (a atividade), funciona como **override** de exibição: quando presente, a UI (`_project_page_helpers_a.py::_render_eap_item_descricao`) mostra só ela, com a descrição da CPU aparecendo apenas como fallback. Não é complementar, e é por atividade — não por CPU.
- `extend_cpu`/`cpus_override.json` (`ProjectStore.extend_cpu`) — substitui a CPU inteira (dict arbitrário, sem schema) no contexto do projeto; reescrever `descricao` ali é uma substituição total, não um campo adicional exibido junto da descrição original.

P3. Decisão de produto já validada com o usuário (ver Decisão): o campo deve ser texto livre, sem exigir aprovação; deve viver por-CPU dentro do projeto (reaproveitado em todas as atividades que referenciam aquela CPU, evitando duplicação); e deve ser exibido sempre em conjunto com a descrição herdada do catálogo, nunca a substituindo.

## Decisão

**D1 — Novo campo `contexto_projeto: str`, por CPU, por projeto, sem workflow de aprovação.** Não estende `CPUOverride` (que continua exclusivo para calibração de produtividade/permanência sob governança ADR-040) nem usa `extend_cpu` (que substitui a CPU inteira). É armazenado em um arquivo próprio, desacoplado de ambos os mecanismos:

```
projetos/{uuid}/overrides/cpus_contexto.json   — dict[cpu_id, str]
```

Usa exclusivamente a interface genérica já existente no `ProjectHandle` Protocol (`read_json`/`write_json`), implementada tanto por `FileProjectHandle` quanto por `StorageProjectHandle` (SharePoint) — **nenhuma mudança de protocolo, nenhum novo método na interface `ProjectHandle`/`ProjectRepository`**, evitando a classe de bug de paridade File×SharePoint já vista nos issues #41/#45/#47/#48 (`StorageProjectHandle` não implementando algo que `FileProjectHandle` implementa).

**D2 — Camada de serviço: `OverrideService.set_cpu_contexto`/`get_cpu_contexto`**, seguindo o padrão já existente de `upsert_override`/`delete_override` (leitura/escrita de um dict JSON simples + log de auditoria via `AuditService`). Exposto em `ConciliumService` (`_CpuResolutionMixin`) como passthrough, mesmo padrão de `extend_cpu`/`resolve_cpu` hoje.

**D3 — `resolve_cpu` passa a anexar `contexto_projeto` ao dict resolvido, sempre que existir, independentemente de qual fonte resolveu a CPU (override/catálogo base/snapshot).** Como é uma chave nova e distinta de `descricao`, isso satisfaz "sempre complementar" (P3) sem precisar de lógica de fallback — a UI simplesmente lê `cpu_data.get("descricao")` e `cpu_data.get("contexto_projeto")` como dois campos independentes e os renderiza juntos.

**D4 — API: `PUT /api/projects/{project_id}/catalog/cpus/{cpu_id}/contexto`** com corpo `{"contexto": str}`. O `GET /api/projects/{project_id}/catalog/cpus/{cpu_id}` existente (resolve_cpu) já passa a incluir `contexto_projeto` na resposta por força de D3, sem precisar de endpoint de leitura dedicado.

**D5 — UI:**
- `_render_cpu_comp_expander` (`_cpu_composition_override.py`) ganha um campo de texto editável ("Contexto do projeto") com botão de salvar, chamando D4. Fica no mesmo expander por-CPU já usado para editar composição — reaproveitando a dedução de que alterações ali "aplicam-se a **todas** as atividades que usam essa CPU" (mesmo texto de ajuda já presente na tela, coerente com o escopo por-CPU de D1).
- `_render_eap_item_descricao`/`_render_eap_item_body` (`_project_page_helpers_a.py`) passam a exibir `contexto_projeto` (quando presente) junto da descrição da CPU/EAP, sem alterar a lógica de fallback existente entre `descricao_item` e `descricao_cpu` (P2) — é uma terceira linha complementar, não uma substituição da lógica atual.

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Estender `CPUOverride` com um campo `descricao_contexto` | Acopla uma anotação descritiva a um workflow de aprovação (`motivo`/`aprovado_por`/`aprovado_em`) pensado para mudanças de cálculo/preço — decisão de produto explícita do usuário rejeitou essa governança para este campo (P3) |
| A2 | Usar `EapItem.descricao`/campo `observacao` do item de EAP | É por atividade, não por CPU — duplicaria o mesmo texto em toda atividade que referencia a mesma CPU; além disso `descricao` já tem semântica de override/fallback estabelecida (P2), que colidiria com o requisito de "sempre complementar" |
| A3 | Sobrescrever `descricao` da CPU via `extend_cpu` | É substituição total da CPU (dict arbitrário), não um campo adicional exibido junto da descrição original — perde a descrição herdada do catálogo |
| A4 | Adicionar campo tipado `CPUContexto` na interface `ProjectHandle`/`ProjectRepository` (novo método dedicado) | Reintroduz risco de paridade File×SharePoint (issues #41/#45/#47/#48); a interface genérica `read_json`/`write_json` já implementada por ambos os backends é suficiente para um dict simples, sem necessidade de contrato tipado adicional |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Engenheiros podem anotar contexto específico do projeto por CPU | Sem esperar aprovação, sem duplicar texto por atividade |
| Zero mudança de protocolo/interface | `read_json`/`write_json` genéricos já cobrem File e SharePoint — sem risco de regressão de paridade |
| Descrição do catálogo nunca é perdida/sobrescrita | `contexto_projeto` é uma chave nova, sempre complementar (D3) |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Texto livre sem aprovação pode divergir do padrão de qualidade de outras anotações do catálogo | Aceito deliberadamente (P3) — é uma anotação informativa, não um dado que afeta cálculo/preço; auditoria via `AuditService` (D2) preserva histórico de quem escreveu o quê |
| Mais um arquivo `overrides/*.json` por projeto para o time se lembrar de considerar em ferramentas de migração/dump de projeto | Segue exatamente o padrão já estabelecido por `cpus_override.json`/`insumos_override.json`/`bdi_override.json` (ADR-040) — nenhuma ferramenta nova de manutenção necessária |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| Fase 1 | `OverrideService.set_cpu_contexto`/`get_cpu_contexto`; passthrough em `ConciliumService`; `resolve_cpu` anexando `contexto_projeto`; endpoint `PUT .../cpus/{cpu_id}/contexto`; UI de edição (`_cpu_composition_override.py`) e exibição complementar (`_project_page_helpers_a.py`); testes unitários | ✅ Implementado |

## Definition of Done

### Fase 1
- [x] `OverrideService.set_cpu_contexto`/`get_cpu_contexto` implementados e testados (armazenamento em `overrides/cpus_contexto.json`, auditoria via `AuditService`)
- [x] `ConciliumService.set_cpu_contexto`/`get_cpu_contexto` (passthrough) implementados
- [x] `resolve_cpu` (`_cpu_resolution.py`) anexa `contexto_projeto` ao dict resolvido em todos os caminhos de retorno, com teste cobrindo presença/ausência
- [x] Endpoint `PUT /api/projects/{project_id}/catalog/cpus/{cpu_id}/contexto` implementado e testado
- [x] UI de edição do contexto no expander de composição de CPU (`_cpu_composition_override.py`)
- [x] UI de exibição complementar (descrição do catálogo + contexto do projeto, ambas visíveis) em `_project_page_helpers_a.py`
- [x] Suíte de testes sem regressões; `ruff check`/`ty check src` limpos

---

## Relacionados

- ADR-040 — Schemas de Override de Catálogo a nível de Projeto (`CPUOverride`, base de comparação para a decisão de não exigir aprovação neste ADR).
- ADR-066 — Snapshot de catálogo por-run (contexto de como a CPU resolvida chega à UI/relatórios).
- Issue #115 — issue de rastreio desta implementação.
- Issues #41/#45/#47/#48 — histórico de bugs de paridade `FileProjectHandle`×`StorageProjectHandle`, motivo de D1 evitar novo método de protocolo.
