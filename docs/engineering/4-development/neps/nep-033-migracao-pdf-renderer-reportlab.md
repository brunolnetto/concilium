# ADR-083 — Migração do Renderizador PDF para ReportLab

**Status:** Proposto  
**Autor:** Engenharia de Produto  
**Data:** 2025  
**Categoria:** Infraestrutura de Deliverables  
**Arquivo relacionado:** `src/concilium/application/runtime/deliverables/reports/pdf_renderer.py`

---

## Contexto

O Concilium gera PDFs de deliverables a partir de Markdown em dois fluxos principais:

| Deliverable | Template de origem | Renderer atual |
|---|---|---|
| `relatorio.pdf` | `relatorio.md` (skill-09) | `render_markdown_pdf` via fpdf2 |
| `memorial_bdi.pdf` | `memorial_bdi.md` (skill-12) | `render_markdown_pdf` via fpdf2 |

O renderizador atual (`pdf_renderer.py`) é uma implementação ad-hoc que converte Markdown para PDF usando a biblioteca `fpdf2` diretamente, com parsing manual linha a linha. Isso impõe limitações estruturais que degradam a qualidade dos PDFs entregues ao cliente.

---

## Problemas com a Implementação Atual (fpdf2 manual)

### 1. Parsing manual frágil
O parser linha a linha (`for line in md_text.splitlines()`) não suporta:
- Markdown multi-linha (ex.: células de tabela com quebras internas)
- Listas aninhadas (`- item\n  - sub-item`)
- Blocos de citação (`>`)
- Texto corrido em parágrafos que cruzam múltiplas linhas (concatenação implícita)

### 2. Tabelas truncadas
A linha `text = cell[:35]` trunca o conteúdo de cada célula em 35 caracteres de forma incondicional. Tabelas com valores monetários longos (ex.: `R$ 46.843.791,49`) são cortadas, distorcendo os números entregues ao cliente.

### 3. Ausência de estilos consistentes
O fpdf2 manual usa `set_font(...)` explicitamente a cada bloco sem sistema de estilos. Mudanças de tipografia (fonte, tamanho, cor) precisam ser alteradas em múltiplos pontos do código. Não há suporte para indentação proporcional por nível de heading.

### 4. Código blocks silenciosamente descartados
Blocos delimitados por ` ``` ` são completamente ignorados (`continue`). O memorial de cálculo BDI usa blocos de código para apresentar fórmulas; esses blocos desaparecem no PDF.

### 5. Imagens sem controle de espaçamento
Imagens são inseridas com `w=pdf.epw` (largura máxima) sem respeitar aspect ratio ou controle de posicionamento. Figuras estreitas aparecem distorcidas.

### 6. Ausência de cabeçalho/rodapé
Não há cabeçalho com nome do projeto/versão nem rodapé com numeração de página — elementos obrigatórios em documentos técnicos de engenharia.

---

## Decisão

Migrar o renderizador para **ReportLab** (pacote `reportlab`) usando o framework **Platypus** (Page Layout and Typography Using Scripts), que fornece:

- Flowables de alto nível (`Paragraph`, `Table`, `Image`, `Spacer`)
- Estilos tipográficos declarativos via `ParagraphStyle`
- Cabeçalho e rodapé automáticos via `BaseDocTemplate` + `PageTemplate`
- Suporte a tabelas com wrapping automático de células
- Inserção de imagens com controle de aspecto

A API pública permanece **idêntica**:

```python
def render_markdown_pdf(
    md_text: str,
    title: str = "",
    image_provider: Callable[[str], bytes | None] | None = None,
) -> bytes | None:
    ...
```

O contrato de entrada/saída não muda. A migração é **transparente para todos os callers** (`side_effects.py`, `runner.py`, `layout.py`).

---

## Design da Nova Implementação

### Dependência

```toml
# pyproject.toml
[project.dependencies]
reportlab = ">=4.0"
```

`reportlab` está disponível no PyPI e não tem dependências compiladas além de `Pillow` (já presente no ambiente).

### Estrutura interna do novo `pdf_renderer.py`

```
render_markdown_pdf(md_text, title, image_provider)
│
├── _parse_md_to_story(md_text, image_provider) -> list[Flowable]
│   ├── Detecta headings (#, ##, ###)
│   ├── Detecta tabelas Markdown (|...|)
│   ├── Detecta imagens (![](path))
│   ├── Detecta blocos de código (``` ... ```) → renderiza com fundo cinza
│   └── Texto corrido → Paragraph com bold inline via XML tags
│
└── _build_doc(story, title) -> bytes
    ├── SimpleDocTemplate (A4, margens 20mm)
    ├── PageTemplate com _on_page (cabeçalho + rodapé + numeração)
    └── doc.build(story)
```

### Sistema de estilos (`_STYLES`)

| Estilo | Fonte | Tamanho | Uso |
|---|---|---|---|
| `h1` | Helvetica-Bold | 14pt | `# Título` |
| `h2` | Helvetica-Bold | 12pt | `## Seção` |
| `h3` | Helvetica-Bold | 10pt | `### Subseção` |
| `body` | Helvetica | 9pt | Texto corrido |
| `code` | Courier | 8pt | Blocos de código |
| `table_header` | Helvetica-Bold | 8pt | Cabeçalho de tabela |
| `table_cell` | Helvetica | 8pt | Células de tabela |

### Tabelas

Células de tabela Markdown são mapeadas para `reportlab.platypus.Table` com:
- `GRID` style para bordas
- Wrapping automático via `Paragraph` em cada célula
- Primeira linha em bold (header)
- Largura distribuída proporcionalmente (sem truncamento)

### Imagens

```python
img_bytes = image_provider(name)
img = Image(BytesIO(img_bytes), width=usable_width)
img.hAlign = "LEFT"
story.append(img)
```

`Image` do ReportLab preserva aspect ratio automaticamente quando apenas `width` é especificado.

### Cabeçalho e Rodapé

```python
def _on_page(canvas, doc):
    # Cabeçalho: título do documento à esquerda, versão à direita
    canvas.setFont("Helvetica", 7)
    canvas.drawString(margin, A4[1] - 14, title)
    # Rodapé: número de página centralizado
    canvas.drawCentredString(A4[0] / 2, 10, f"Pág. {doc.page}")
```

---

## Plano de Migração

### Fase 1 — Implementação paralela (sem risco)
- Criar `pdf_renderer_rl.py` com a nova implementação ReportLab
- Cobrir com testes unitários em `tests/unit/test_pdf_renderer_rl.py` (documento mínimo, tabela, imagem, heading)
- A implementação fpdf2 (`pdf_renderer.py`) permanece inalterada

### Fase 2 — Feature flag por ambiente
```python
# pdf_renderer.py
_USE_REPORTLAB = os.getenv("CONCILIUM__PDF_RENDERER", "fpdf2") == "reportlab"

def render_markdown_pdf(...) -> bytes | None:
    if _USE_REPORTLAB:
        from .pdf_renderer_rl import render_markdown_pdf as _rl
        return _rl(md_text, title, image_provider)
    ...  # implementação fpdf2 atual
```

Isso permite ativar ReportLab no ambiente de benchmark (`CONCILIUM__PDF_RENDERER=reportlab`) sem afetar produção.

### Fase 3 — Validação em benchmark
- Executar `run_all.py` com `CONCILIUM__PDF_RENDERER=reportlab`
- Verificar que `relatorio.pdf` e `memorial_bdi.pdf` são gerados sem erros em todos os 12 projetos de benchmark
- Comparação visual side-by-side dos PDFs (spot-check manual de 3 projetos)

### Fase 4 — Remoção da implementação fpdf2
- Remover flag e implementação fpdf2
- Atualizar `pyproject.toml`: substituir `fpdf2` por `reportlab`
- Deletar `pdf_renderer_rl.py` e renomear para `pdf_renderer.py`

---

## Consequências

### Positivas
- PDFs com qualidade profissional (tipografia, espaçamento, bordas de tabela)
- Tabelas sem truncamento de conteúdo
- Blocos de código com fundo diferenciado e fonte monoespaçada
- Cabeçalho e rodapé com numeração de página
- Código de renderização mais declarativo e fácil de manter

### Negativas / Riscos
- `reportlab` adiciona ~6MB ao ambiente virtual (aceitável)
- A API XML do ReportLab exige escape de caracteres especiais (`<`, `>`, `&`) nos textos
- Tabelas muito largas podem requerer ajuste manual de `colWidths`

### Mitigação
- Usar `xml.sax.saxutils.escape()` no pipeline de geração de parágrafos
- Implementar fallback para tabelas que excedem a largura da página (dividir em sub-tabelas ou usar `FONTSIZE` menor)

---

## Alternativas Consideradas

| Alternativa | Motivo de rejeição |
|---|---|
| **WeasyPrint** (HTML/CSS → PDF) | Requer conversão Markdown → HTML (dependência adicional); tamanho binário maior; difícil em ambientes headless containerizados |
| **Pandoc** (via subprocess) | Dependência de binário externo não gerenciável via pip; não adequado para execução em workers serverless |
| **pdfkit / wkhtmltopdf** | Mesmos problemas de dependência binária que Pandoc |
| **Manter fpdf2** | Não resolve os problemas de truncamento e ausência de estilos |

---

## Referências

- [ReportLab User Guide (PDF)](https://www.reportlab.com/docs/reportlab-userguide.pdf)
- `src/concilium/application/runtime/deliverables/reports/pdf_renderer.py` — implementação atual
- `src/concilium/application/runtime/deliverables/side_effects.py` — caller principal
- ADR-026: Fase de saída multicanal e relatórios analíticos
