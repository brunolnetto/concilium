# ADR-064: Proibição de Edição de JSON Bruto — Contrato de Formulários Tipados

**Status:** Implementado  
**Data:** 2026-05-19  
**Autor:** Engenheiro Sênior  
**Relacionado:** ADR-048 (API + UI Iteração Rápida), ADR-063 (Discriminador de Tipo de Projeto), ADR-025 (MCP Catalog Policy)

---

## 1. Contexto

### 1.1 O antipadrão

A UI Streamlit do Concilium expõe objetos de domínio como texto JSON editável em campos `st.text_area`:

```python
# catalogo_page.py:312 — THE OFFENDER
cpu_json = st.text_area(
    "JSON da CPU (edite para sobrescrever)",
    value=json.dumps(cpu_data, indent=2, ensure_ascii=False),
    height=300,
)
cpu_obj = json.loads(cpu_json)  # sem validação de estrutura
```

O usuário edita texto livre representando um objeto de domínio (`CPU`, `insumo`, `contexto`...) e o sistema faz `json.loads` antes de enviar à API. Isso é o equivalente de um formulário bancário cujo campo "valor" é uma caixa de texto que aceita Python arbitrário.

### 1.2 Inventário atual de ocorrências

| Arquivo | Linha | Campo exposto | Gravidade |
|---|---|---|---|
| `templates/catalogo_page.py` | 312–325 | Objeto `CPU` inteiro | **CRÍTICA** — edição raw JSON + `json.loads` direto na API |

**Já corretos** (referência de bom padrão):

| Arquivo | Linha | Padrão usado | Campo |
|---|---|---|---|
| `organisms/layout.py` | 622 | `st.data_editor` tipado | Custos indiretos MO/equip |
| `organisms/layout.py` | 1192 | `st.data_editor` tipado | Políticas de mobilização |
| `organisms/layout.py` | 1807 | `st.data_editor` tipado | Produtividade de CPU |
| `organisms/layout.py` | 1972 | `st.data_editor` tipado | Composição de CPU |
| `templates/projetos_page.py` | — | Tabela + `number_input` | EAP (ADR-063) |
| `templates/perfis_contextos_page.py` | 180, 332 | `st.json()` | Read-only — sem edição |

### 1.3 Por que o padrão de JSON bruto é inaceitável

| Problema | Consequência |
|---|---|
| Qualquer erro de digitação quebra `json.loads` sem feedback útil | Usuário perde edição sem mensagem de erro clara |
| Sem validação de schema antes da API | Campos inexistentes ou com tipo errado passam silenciosamente |
| Engenheiro não-desenvolvedor nunca sabe quais campos são válidos | Fricção cognitiva altíssima; formulário ininteligível |
| Não há distinção entre campos editáveis e campos calculados/auditados | Usuário pode sobrescrever `historico_precos`, `scd_version`, etc. |
| Impossível de testar automaticamente | Input é texto opaco; não há schema a validar |

---

## 2. Forças em tensão

| Força | Descrição |
|---|---|
| **Velocidade de prototipagem** | JSON bruto é rápido de implementar — um `text_area` cobre qualquer schema |
| **Completude de campos** | Formulários tipados só mostram o que o desenvolvedor explicitou; JSON mostra tudo |
| **Auditoria** | Campos calculados (custo, scd_version, hashes) não devem ser editáveis; JSON os expõe |
| **Extensibilidade** | Novos campos no schema precisam aparecer no formulário sem reimplantar |
| **Segurança** | JSON bruto permite injeção de campos não-intencionados na camada de persistência |

---

## 3. Decisão

### D1 — Regra de ouro: nenhum objeto de domínio é editado como texto JSON

A regra é binária e sem exceções:

> **Todo campo editável na UI deve ter um widget tipado correspondente.**  
> `st.text_area` com `json.loads()` como parse é código a ser eliminado.

Read-only `st.json()` para inspeção/auditoria (sem `key` de edição) é permitido.

### D2 — Hierarquia de widgets por tipo de campo

| Tipo de dado | Widget obrigatório |
|---|---|
| `str` livre | `st.text_input` |
| `str` enumerado | `st.selectbox` ou `st.radio` |
| `float` / `int` | `st.number_input` (com `min_value`, `max_value`, `step` explícitos) |
| `bool` | `st.checkbox` ou `st.toggle` |
| `list[str]` | `st.multiselect` |
| `list[dict]` (tabular) | `st.data_editor` com `column_config` explícito por coluna |
| `dict` aninhado (objeto de domínio) | Formulário expandível com campos D2 para cada chave editável |
| Campo calculado / auditado | Widget `disabled=True` ou ausente do formulário |

### D3 — Campos editáveis vs. campos protegidos devem ser explícitos no contrato

Cada formulário que edita um objeto de domínio declara:

```python
# Campos que o usuário pode editar
EDITABLE_FIELDS: dict[str, FieldSpec] = {
    "descricao": FieldSpec(widget="text_input", label="Descrição"),
    "producao_horaria": FieldSpec(widget="number_input", label="Produção horária (un/h)",
                                   min_value=0.0, step=0.1),
    "unidade": FieldSpec(widget="selectbox", label="Unidade", options=VALID_UNITS),
}

# Campos que só aparecem read-only (display)
READONLY_FIELDS = {"codigo", "historico_precos", "scd_version", "categoria"}

# Campos ignorados (nunca aparecem)
INTERNAL_FIELDS = {"_id", "created_at", "updated_at", "hash"}
```

### D4 — Formulário de CPU como caso de referência (substitui `catalogo_page.py:312`)

O editor de CPU atual (`st.text_area` com JSON) é substituído por um formulário estruturado:

```
┌─────────────────────────────────────────────────────────────────┐
│  Editar CPU: ESCO-CARGA-1CAT-DMT2000                           │
├─────────────────────┬───────────────────────────────────────────┤
│  Código             │  ESCO-CARGA-1CAT-DMT2000  [read-only]    │
│  Descrição          │  [text_input]                             │
│  Unidade            │  [selectbox: m³, m², m, un, h]           │
│  Produção horária   │  [number_input min=0 step=0.1]            │
│  Categoria          │  [selectbox]  [read-only]                 │
├─────────────────────┴───────────────────────────────────────────┤
│  Composição (itens de custo)                                    │
│  [data_editor com colunas: insumo_id, coef, unidade, categoria] │
├─────────────────────────────────────────────────────────────────┤
│  Motivo da edição   │  [text_input]                             │
│  [ Salvar override ]                                            │
└─────────────────────────────────────────────────────────────────┘
```

O payload enviado à API é construído **programaticamente** a partir dos widgets — nunca do texto do usuário.

### D5 — Escape hatch para power users: modo "inspecionar JSON"

O JSON bruto pode ser exibido em modo **somente-leitura** como referência, sem possibilidade de edição:

```python
with st.expander("🔍 Inspecionar JSON completo (read-only)"):
    st.json(cpu_data)  # sem key= → não editável
```

Nenhum botão de "salvar a partir do JSON" pode existir próximo a esse bloco.

---

## 4. Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Manter JSON bruto mas adicionar validação de schema com `jsonschema` | Não resolve a usabilidade; usuário ainda edita texto sem autocompletar, sem labels, sem constraints de tipo |
| A2 | Editor JSON com sintaxe highlighting (ex: ace-editor via componente customizado) | Melhora a experiência de desenvolvedor, não de engenheiro de obra; o problema é epistêmico, não de formatação |
| A3 | Formulários gerados automaticamente do schema Pydantic | Atraente mas frágil: schema muda, formulário quebra; além disso, nem todo campo Pydantic deve ser editável |
| A4 | Formulários somente para campos mais usados + JSON para o resto | Cria dois caminhos; o JSON "de escape" tende a se tornar o padrão |

---

## 5. Consequências

### Positivas

| Consequência | Benefício |
|---|---|
| Formulários tipados com labels em português | Engenheiro de obra consegue editar sem manual |
| `min_value`/`max_value`/`step` em campos numéricos | Previne valores fisicamente impossíveis antes da API |
| Campos calculados explicitamente `disabled` | Elimina sobrescrita acidental de dados auditados |
| Payload construído programaticamente | Testável; API recebe exatamente o que o contrato espera |
| Inspeção via `st.json` somente-leitura | Developer experience preservado sem abrir edição |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Formulário precisa ser mantido quando o schema muda | `EDITABLE_FIELDS` centralizado por formulário; mudança de schema = mudança explícita e rastreável |
| Campos novos não aparecem automaticamente | Trade-off aceitável: explicitação é melhor que exposição inadvertida |
| CPU tem composição variável (lista de itens de custo) | `st.data_editor` com `num_rows="dynamic"` suporta adição/remoção de linhas |

---

## 6. Plano de Implementação

| Fase | Entrega | Status |
|---|---|---|
| **F1 — Correção imediata** | Substituir `st.text_area(json.dumps(...))` em `catalogo_page.py:312` por formulário estruturado de CPU | Pendente |
| **F2 — Regra de lint** | Adicionar regra ao `lint_report.py` que detecta padrão `st.text_area` + `json.loads` na mesma função | Pendente |
| **F3 — Documentar contrato de formulários** | Módulo `atoms/form_contracts.py` com `FieldSpec`, `EDITABLE_FIELDS` e helpers de renderização | Pendente |
| **F4 — Auditoria periódica** | `make lint` detecta `json.loads.*text_area\|text_area.*json.loads` no código de UI | Pendente |

---

## 7. Definition of Done

### Fase 1 — Correção imediata
- [x] `catalogo_page.py:312` removido — `st.text_area(json.dumps(...))` eliminado
- [x] Formulário de CPU usa `render_typed_form()` com `CPU_EDITABLE_FIELDS` (descricao, unidade, categoria, producao_id_ref, composicao_itens como data_editor)
- [x] Payload `cpu_obj = {**cpu_data, **edited_fields}` — construído programaticamente
- [x] `st.json(cpu_data)` presente em expander read-only "Inspecionar JSON"

### Fase 2 — Regra de lint
- [x] `scripts/lint_report.py`: `_scan_raw_json_ui()` com detecção AST-level (evita falsos positivos em docstrings/comentários)
- [x] `_has_call(node, module, func)` verifica apenas chamadas reais, não string literals
- [x] Report inclui `ui_json_raw_violations` no summary e seção `ui_json_raw` com hits detalhados
- [x] Teste `test_ui_directory_is_clean` passa: zero violações no diretório UI atual

### Fase 3 — Contrato de formulários
- [x] `atoms/form_contracts.py`: `FieldSpec`, `CPU_EDITABLE_FIELDS`, `CPU_READONLY_FIELDS`, `CPU_INTERNAL_FIELDS`
- [x] `render_typed_form(obj, editable_fields, readonly_fields, key)` com suporte a text_input, number_input, selectbox, multiselect, checkbox, text_area_plain, data_editor
- [x] `_render_data_editor_field()` para campos tabulares com column_config por tipo
- [x] `catalogo_page.py` migrado como caso de referência
- [x] 16 testes: F1 (4), F2 (4), F3 (8) — 1417 testes totais passando
