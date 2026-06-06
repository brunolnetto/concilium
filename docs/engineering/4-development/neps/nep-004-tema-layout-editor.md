# NEP-004: Layout do editor de tema desorganizado e campo com mapeamento errado

**Status:** Concluído  
**Prioridade:** 🟡 Médio  
**Área:** Configuração  
**Tipo:** UX + Bug  
**Esforço:** S  
**Identificado em:** 2026-05-20  

---

## Contexto

O editor de tema na aba "🎨 Temas" exibe campos na seguinte ordem vertical sem agrupamento:

```
Cabeçalho — fundo: [color]
Cabeçalho — texto: [color]
Destaque: [color]
Zebra — linha ímpar: [color]   ← mapeado para cores.borda (ERRADO)
Bordas: [color]
Fonte cabeçalho: [select]
Fonte corpo: [select]
Tamanho título (pt): [number]
Tamanho cabeçalho (pt): [number]
Tamanho corpo (pt): [number]
Motivo da alteração: [text]
```

**Problemas identificados:**
1. Campo "Zebra — linha ímpar" está mapeado para `cores.borda` no `TEMA_EDITABLE_FIELDS` — deveria ser `cores.zebra_impar`
2. Campo "Bordas" que deveria existir mapeia `cores.borda`, mas o campo exibido com esse label não é "Bordas"
3. Cores e tipografia misturadas sem separação visual
4. Color pickers ficam todos em coluna única vertical, desperdiçando largura
5. Campo "Motivo" aparece colado aos campos de tipografia sem separador

## Critério de Aceite

Formulário reorganizado em duas seções com separadores:

**Seção "🎨 Cores"** (grid de 3 colunas):
```
[Cabeçalho — fundo] [Cabeçalho — texto] [Destaque    ]
[Zebra ímpar       ] [Bordas            ] [             ]
```

**Seção "🔤 Tipografia"** (grid de 2 colunas):
```
[Fonte cabeçalho] [Fonte corpo    ]
[Tam. título    ] [Tam. cabeçalho ] [Tam. corpo]
```

**Separador + motivo** no rodapé.

Mapeamento correto de campos:
- `"Zebra — linha ímpar"` → `cores.zebra_impar`
- `"Bordas"` → `cores.borda`

## Notas Técnicas

- Correção do mapeamento: 2 linhas em `TEMA_EDITABLE_FIELDS` no `form_contracts.py`
- Reorganização visual: reformular `TEMA_EDITABLE_FIELDS` para usar seções, ou renderizar em grupos no `_render_tema_editor`
- O widget `color_hex` já funciona via `render_typed_form` — só precisamos reorganizar a ordem
