# ADR-067: API de Escrita no Catálogo Mestre

**Status:** Implementado  
**Data:** 2026-05-19  
**Autor:** Engenheiro Sênior  
**Relacionado:** ADR-040 (Master vs. Project Layer), ADR-066 (Catalog Overlay), ADR-064 (Formulários Tipados), ADR-041 (SCD Type 2)

---

## 1. Contexto

O catálogo mestre (`config/catalogos/{id}/`) é hoje **somente-leitura via API** — editável apenas diretamente no filesystem. Isso força o engenheiro a:

1. SSH ou acesso direto aos arquivos JSON para adicionar/corrigir CPUs
2. Reiniciar o servidor para invalidar o bundle cache
3. Sem trilha de auditoria de quem mudou o quê

Com a UI de catálogo mestre criada (ADR via `render_catalogo_master_page`), o formulário tipado está pronto (ADR-064) mas o botão "Salvar no mestre" mostra aviso de não-implementado.

### 1.1 Relação com ADR-066

ADR-066 define overlays por projeto/jurisdição como o mecanismo preferido de customização. A escrita no mestre é a operação de **manutenção do catálogo corporativo canônico** — não um override de projeto. São complementares:

- **Mestre**: fonte canônica corporativa (ex: nova CPU SICRO, correção de composição)
- **Overlay de projeto**: ajuste local sem alterar o mestre

---

## 2. Decisão

### D1 — `PUT /api/catalogs/{catalog_id}/cpus/{cpu_id}`

Cria ou substitui uma CPU no catálogo mestre. `cpu_id` no path deve coincidir com `cpu_data.codigo`.

```
Body: { "cpu_data": {...}, "motivo": "string (obrigatório)" }
Response: { "catalog_id": str, "cpu_id": str, "version": str, "saved_at": str }
```

### D2 — Invalidação de bundle cache automática

Após escrita, o arquivo `.catalog_bundle.json` do catálogo é deletado. O próximo `load_catalogo()` reconstrói o bundle a partir dos arquivos individuais.

### D3 — Trilha de auditoria por catálogo

Cada escrita é registrada em `config/catalogos/{id}/.catalog_audit.jsonl`:

```json
{"event": "upsert_cpu", "cpu_id": "...", "actor": "...", "motivo": "...", "timestamp": "..."}
```

### D4 — Validação mínima antes da escrita

- `codigo` presente e coincide com `cpu_id` do path
- `descricao`, `unidade` presentes e não-vazios
- `composicao_itens` é uma lista (pode ser vazia)

Sem validação de regras de negócio (composição completa, produtividade calculável) — essas são responsabilidade dos gates do pipeline (ADR-022).

### D5 — UI: habilitar botão "Salvar no mestre" em `catalogo_master_page`

O formulário tipado (ADR-064) já está renderizado — basta construir o payload e chamar o endpoint.

---

## 3. Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Editar arquivos diretamente (status atual) | Sem auditoria, sem invalidação de cache, requer acesso ao servidor |
| A2 | Versionar cada CPU com `ConfigVersionService` | Overhead excessivo para catálogos com 500+ CPUs; SCD Type 2 (ADR-041) já cobre histórico de preços |
| A3 | Endpoint de patch de campo único | Complexidade extra sem benefício; o formulário tipado já controla quais campos são editáveis |

---

## 4. Consequências

### Positivas
- Engenheiro edita CPUs diretamente na UI sem acesso ao servidor
- Trilha de auditoria completa no catálogo
- Cache invalidado automaticamente — sem restart necessário

### Negativas / Riscos
| Risco | Mitigação |
|---|---|
| Escrita simultânea corrompendo arquivo | Lock por arquivo (`fcntl` ou similar); para volume baixo do catálogo, risco aceitável |
| Escrita de dado inválido no mestre | Validação D4 na camada de serviço; validação completa pelo pipeline na próxima execução |
| Perda de histórico de CPU anterior | Arquivo antigo preservado em `.catalog_audit.jsonl` com snapshot do estado anterior |

---

## 5. Plano de Implementação

| Fase | Entrega |
|---|---|
| F1 | `ConciliumService.upsert_catalog_cpu()` + validação + audit + cache bust |
| F2 | `PUT /api/catalogs/{id}/cpus/{cpu_id}` endpoint |
| F3 | UI: habilitar botão "Salvar no mestre" em `catalogo_master_page.py` |
| F4 | Testes unitários |

---

## 6. Definition of Done

- [x] `PUT /api/catalogs/{id}/cpus/{cpu_id}` retorna 200 com CPU salva
- [x] `.catalog_bundle.json` deletado após escrita
- [x] `.catalog_audit.jsonl` contém entrada com actor, motivo e snapshot anterior
- [x] Validação rejeita payload sem `codigo`, `descricao` ou `unidade`
- [x] UI: salvar CPU do catálogo mestre funciona end-to-end
- [x] Testes: upsert cria arquivo, invalida bundle, registra auditoria
