# Tutorial — Criar e Executar Projetos via MCP

Este tutorial cobre o fluxo completo de uso do Concilium MCP, desde a criação de um
projeto até a entrega de artefatos. Destinado a agentes LLM (Claude Desktop, Copilot)
e a humanos que utilizam o sistema via API.

---

## Pré-requisitos

1. `concilium-mcp-proxy` instalado e configurado no `claude_desktop_config.json`  
   → Ver `cd/development/claude_settings.json.template` para obter o bloco correto.
2. Device code fornecido pelo admin (`concilium auth new-device`).
3. Contexto de cálculo disponível (use `listar_contextos()` para confirmar).

---

## Fluxo 1 — Criação via QQP (forma recomendada)

### Passo 1 — Listar contextos disponíveis

```python
listar_contextos()
# → [{id: "mendeslobo-ce", perfil_id: "...", catalogo_id: "..."}, ...]
```

### Passo 2 — Criar projeto a partir da lista de serviços

```python
criar_projeto_formulario(
    nome="Rodovia CE-040 — Lote 09/10",
    contexto_id="mendeslobo-ce",
    tipo_obra="terraplenagem",
    localizacao="Aracoiaba, CE",
    data_inicio="2026-09-01",
    servicos=[
        {"descricao": "Supressão vegetal",             "quantidade": 8,      "unidade": "ha"},
        {"descricao": "Escavação de material 3ª cat",  "quantidade": 450000, "unidade": "m³"},
        {"descricao": "Aterro compactado",             "quantidade": 120000, "unidade": "m³"},
        {"descricao": "Carga e transporte DMT 3km",    "quantidade": 450000, "unidade": "m³"},
    ]
)
```

**Resposta possível A — todos mapeados:**
```json
{
  "status": "criado",
  "project_id": "rodovia-ce040-lote09",
  "version": "v1",
  "eap_preview": [...],
  "proxima_skill_sugerida": "02-produtividade-climatica"
}
```

**Resposta possível B — itens sem CPU:**
```json
{
  "status": "pendente_mapeamento",
  "nao_mapeados": [{"descricao": "Carga e transporte DMT 3km", "item_id": "eap-1_4"}],
  "instrucoes": "Use buscar_cpu(termo) para encontrar o cpu_id correto..."
}
```

Se B, pesquise o CPU:
```python
buscar_cpu("carga transporte terraplenagem")
# → [{cpu_id: "CPU-TERRA-CARGA-01", descricao: "Carga e transporte..."}, ...]
```

Repita `criar_projeto_formulario` com `cpu_id` preenchido nos itens pendentes.

---

## Fluxo 2 — Execução do Pipeline

Após criar o projeto, execute as skills em sequência:

### Passo 3 — Avançar pipeline (skill a skill)

```python
# Repita até receber proxima_sugerida = null ou pipeline completo
avancar_pipeline(project_id="rodovia-ce040-lote09")
# → {skill_executada: "02-produtividade-climatica", status: "OK", proxima_sugerida: "03-catalogo-de-recursos"}

avancar_pipeline(project_id="rodovia-ce040-lote09")
# → {skill_executada: "03-catalogo-de-recursos", status: "OK", ...}

# ...continua até skill 09-relatorio-e-artefatos
```

### Passo 4 — Verificar status

```python
consultar_status(project_id="rodovia-ce040-lote09")
# → {pipeline_integridade: "COMPLETO", resultado_atual: {preco_venda: 4_200_000.0, ...}}
```

> ⚠️ Se `pipeline_integridade == "CORROMPIDO"`, os valores financeiros **não devem ser usados**.
> Corrija os erros e re-execute a partir do checkpoint falho.

---

## Fluxo 3 — Consultar e baixar artefatos

### Passo 5 — Listar artefatos disponíveis

```python
listar_artefatos_projeto(project_id="rodovia-ce040-lote09")
# → [{kind: "relatorio_pdf", filename: "relatorio_final.pdf"}, 
#    {kind: "planilha_excel", filename: "orcamento.xlsx"}, ...]
```

### Passo 6 — Baixar artefato

```python
ler_artefato(project_id="rodovia-ce040-lote09", kind="relatorio_pdf", filename="relatorio_final.pdf")
# → {url: "https://...", expires_in: 900}  # URL pré-assinada válida por 15 min
```

### Passo 7 — Bundle completo (ZIP)

```python
baixar_bundle_zip(project_id="rodovia-ce040-lote09")
# → {url: "https://...", filename: "rodovia-ce040-lote09-bundle.zip"}
```

---

## Escopos necessários por operação

| Operação | Scope necessário |
|---|---|
| `listar_projetos`, `consultar_status`, `listar_artefatos_projeto` | `mcp:read` |
| `ler_artefato`, `baixar_bundle_zip` | `mcp:read` |
| `criar_projeto_formulario`, `avancar_pipeline` | `pipeline:run` |
| `aprovar_versao` | `pipeline:run` |

---

## Referência rápida de tools MCP

| Tool | Descrição |
|---|---|
| `listar_contextos()` | Lista contextos de cálculo disponíveis |
| `listar_projetos()` | Lista todos os projetos existentes |
| `criar_projeto_formulario(nome, contexto_id, tipo_obra, localizacao, data_inicio, servicos)` | Cria projeto a partir de QQP |
| `buscar_cpu(termo)` | Busca CPUs no catálogo por descrição |
| `avancar_pipeline(project_id)` | Executa próxima skill pendente |
| `consultar_status(project_id)` | Retorna estado do pipeline e resultado financeiro |
| `listar_artefatos_projeto(project_id)` | Lista artefatos gerados |
| `ler_artefato(project_id, kind, filename)` | Retorna URL de download |
| `baixar_bundle_zip(project_id)` | ZIP com todos os artefatos |
| `aprovar_versao(project_id)` | Congela versão (irreversível — confirmar com usuário) |

---

## Erros comuns

| Código / Mensagem | Causa | Solução |
|---|---|---|
| `CONCILIUM_DEVICE_CODE não configurado` | Proxy sem device code | Solicitar novo código ao admin |
| `401 Unauthorized` | Token expirado | Aguardar renovação automática (~10s) ou reiniciar Claude Desktop |
| `pipeline_integridade: CORROMPIDO` | Skill GATE falhou | Ver `validacoes` em `consultar_status`, corrigir inputs e re-executar |
| `status: pendente_mapeamento` | Serviço sem CPU | Usar `buscar_cpu()` e repassar com `cpu_id` |
| `Rate limit atingido` | Muitas chamadas em 60s | Aguardar `Retry-After` segundos |
