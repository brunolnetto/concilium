# ADR-092 — Formulário QQP/EAP: Interface de Entrada Estruturada para Agentes e Humanos Semi-Instruídos

**Status:** Implementado (Fases 1-4 ✅ — Fase 5 pendente validação real)
**Data:** 2026-05-30
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-091, ADR-093, ADR-037 (MCP Facade)

---

## Contexto

### Problema

P1. Criar um projeto novo no Concilium exige montar manualmente estruturas técnicas
internas: EAP com IDs de CPU explícitos, composições de equipe, regime de trabalho,
precedências tipadas, etc. Não existe interface de criação para usuários finais.

P2. O `referencia.json` é o formato do mecanismo de **calibração histórica** —
usado para carregar projetos de referência validados por humanos. Ele foi adotado
como forma de entrada de projeto por ausência de alternativa, mas não é adequado
para o fluxo de produção.

P3. Engenheiros de campo têm o QQP (lista de serviços + quantidades) como documento
natural de trabalho. A tradução QQP → EAP é feita hoje manualmente, o que introduz
erros e exige tempo de engenheiro de software.

P4. Agentes LLM (Claude, Copilot) precisam de uma tool MCP estruturada para criar
projetos. Sem ela, só podem usar o sistema de forma assistida — não autônoma.

---

## Decisão

D1. **Estrutura do formulário em três seções.**

**Seção 1 — Identificação do Projeto**
```
nome, tipo_obra, localizacao, data_inicio, data_termino_desejado
regime_trabalho: {dias_semana, horas_dia}
objetivo_pool: "minimizar_prazo" | "minimizar_custo" | "balanceado"
```

**Seção 2 — QQP (Quantitativos)**
```
servico: "Escavação de material de 3ª categoria"  → sugere CPU: ESC-3CAT
quantidade: 450000.0
unidade: "m³"
[aceitar sugestão ou selecionar alternativa]
```

**Seção 3 — EAP (Hierarquia + Precedências)**
```
eap:
  - item_id: eap-1_0  descricao: "Supressão vegetal"  cpu_id: DESMAT
    predecessores: []
  - item_id: eap-1_5  descricao: "Escavação 3ª categoria"
    predecessores: [{predecessor_id: eap-1_0, threshold: 0.5}]
```

D2. **Busca semântica de CPU no catálogo.** O campo `servico` (texto livre) é
vetorizado e comparado ao catálogo. O sistema retorna top-3 candidatos com scores.
O usuário confirma ou corrige. Elimina a necessidade de conhecer IDs de CPU.

D3. **Tool MCP `criar_projeto_formulario`.**

```python
@mcp.tool()
def criar_projeto_formulario(
    nome: str, tipo_obra: str, localizacao: str,
    data_inicio: str, data_termino: str | None,
    objetivo_pool: str = "balanceado",
    servicos: list[dict],    # [{descricao, quantidade, unidade}]
) -> dict:
    """Cria um projeto a partir de uma lista de serviços em linguagem natural."""
    # Busca semântica → CPU_id por serviço
    # Estrutura EAP automática
    # Inicializa ProjectStore com canonical vazio (pronto para avancar_pipeline)
    # Retorna: {projeto_id, eap_preview, sugestoes_cpu, proximos_passos}
```

D4. **`AGENT_SKILL_TUTORIAL.md` — instrução para agentes.** Descreve o fluxo completo:
1. Chamar `criar_projeto_formulario` com a lista de serviços
2. Confirmar sugestões de CPU
3. Chamar `avancar_pipeline` para executar skills
4. Consultar artefatos via `listar_artefatos_projeto` (ADR-093)

D5. **`claude_settings.json` configura o MCP** como ferramenta disponível para
Claude Code e Copilot, com `criar_projeto_formulario` como entry point principal.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| R1 | Usar `referencia.json` como formato de entrada de produção | É o formato do mecanismo de calibração histórica, não da interface de usuário |
| R2 | Form JSON estruturado sem busca semântica | Ainda exige conhecimento de IDs de CPU |
| R3 | Apenas UI visual (sem MCP tool) | Exclui agentes; duplica lógica |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Barreira de entrada eliminada | Engenheiro de campo cria projeto sem conhecer estrutura interna |
| Agentes autônomos | LLMs podem criar e executar projetos sem intervenção humana intermediária |
| CPU correto | Busca semântica reduz erros de mapeamento serviço→composição |
| Separação clara | `referencia.json` fica exclusivo do mecanismo de calibração histórica |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Busca semântica pode sugerir CPU incorreto | Score de confiança + confirmação obrigatória antes de prosseguir |
| Índice semântico precisa manutenção com atualização de catálogo | Re-indexação automática em CI quando catálogo muda |
| EAP auto-gerada pode omitir precedências não óbvias | Fase de revisão de EAP antes de executar pipeline |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| 1 | Índice semântico do catálogo (word-overlap em catálogo) | 🟢 Implementado |
| 2 | Tool MCP `criar_projeto_formulario` com busca e geração de EAP | 🟢 Implementado |
| 3 | `AGENT_SKILL_TUTORIAL.md` + `claude_settings.json.template` | 🟢 Implementado |
| 4 | UI Streamlit para humanos semi-instruídos | 🟢 Implementado |
| 5 | Validação end-to-end com projeto real de produção | 🟡 Pendente validação real |

## Definition of Done

### Fase 1
- [ ] Embeddings gerados para todos os CPUs do catálogo
- [ ] Top-3 busca semântica retorna CPU correto para serviços representativos

### Fase 2
- [ ] `criar_projeto_formulario` cria projeto válido e inicia pipeline
- [ ] EAP gerada passa na skill-01 sem erros de validação
- [ ] Sugestões de CPU apresentadas com score de confiança

### Fase 3
- [ ] `AGENT_SKILL_TUTORIAL.md` cobre os fluxos setup, execução e consulta de artefatos
- [ ] `claude_settings.json` configurado e testado com Claude Code

### Fase 4
- [ ] UI Streamlit funcional com as três seções do formulário

### Fase 5
- [ ] Projeto de produção criado, executado e artefatos entregues sem uso de `referencia.json`

---

## Relacionados

[[adr091-pool-minimo-variavel-otimizacao]] [[adr093-mcp-artefatos]]
[[adr037-mcp-facade-simplification]]