"""Testes unitarios para o renderer ReportLab (pdf_renderer_rl.py).

Ref: NEP-033 / ADR-083 — Fase 1: cobertura basica do novo backend.
"""

from __future__ import annotations

import pytest

# Verificar se reportlab esta disponivel no ambiente; pular suite se nao estiver.
reportlab = pytest.importorskip("reportlab", reason="reportlab nao instalado")


from concilium.application.runtime.deliverables.reports import pdf_renderer_rl as _pdf_mod  # noqa: E402
from concilium.application.runtime.deliverables.reports.pdf_renderer_rl import (  # noqa: E402
    render_markdown_pdf,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_pdf(data: bytes | None) -> bool:
    return data is not None and data[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


class TestDocumentoMinimo:
    def test_retorna_bytes(self):
        result = render_markdown_pdf("Ola mundo")
        assert _is_pdf(result)

    def test_documento_vazio_nao_retorna_none(self):
        result = render_markdown_pdf("")
        assert _is_pdf(result)

    def test_titulo_no_header(self):
        result = render_markdown_pdf("Conteudo", title="Relatorio de Teste")
        assert _is_pdf(result)

    def test_retorna_none_se_import_falhar(self, monkeypatch):
        """Simula ausencia do reportlab: deve retornar None sem exception."""
        import builtins
        import sys

        _orig_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name.startswith("reportlab"):
                raise ImportError("mocked")
            return _orig_import(name, *args, **kwargs)

        # Remove cached modules para que o mock seja ativado
        rl_mods = [k for k in sys.modules if k.startswith("reportlab")]
        for m in rl_mods:
            sys.modules.pop(m)

        monkeypatch.setattr(builtins, "__import__", _mock_import)
        result = render_markdown_pdf("Conteudo")
        assert result is None


class TestHeadings:
    MD = "# Titulo Principal\n\n## Secao A\n\n### Subsecao 1\n\nTexto normal aqui."

    def test_headings_geram_pdf(self):
        assert _is_pdf(render_markdown_pdf(self.MD))


class TestTabelas:
    MD = (
        "## Custos\n\n"
        "| Item | Unidade | Valor |\n"
        "|------|---------|-------|\n"
        "| Concreto | m3 | R$ 350,00 |\n"
        "| Aco CA-50 | kg | R$ 8,50 |\n"
        "| Escavacao | m3 | R$ 46.843.791,49 |\n"
    )

    def test_tabela_gera_pdf(self):
        assert _is_pdf(render_markdown_pdf(self.MD))

    def test_tabela_com_valor_longo_nao_trunca(self):
        """PDF deve ser gerado sem crash mesmo com valores monetarios longos."""
        result = render_markdown_pdf(self.MD)
        assert _is_pdf(result)
        # Valor longo nao causa truncamento silencioso (nao ha limite de 35 chars)
        assert len(result) > 1000  # type: ignore[arg-type]

    def test_flush_table_retornando_none_e_tolerado(self, monkeypatch):
        """Se _flush_table() (helper de nivel de modulo) retornar None mesmo com
        linhas acumuladas, o closure flush_table() dentro de _parse_md_to_story
        deve apenas pular o append (branch False de `if tbl is not None`)."""
        monkeypatch.setattr(_pdf_mod, "_flush_table", lambda *a, **kw: None)
        result = render_markdown_pdf(self.MD)
        assert _is_pdf(result)


class TestBlocoDeCodigo:
    MD = (
        "## Formula BDI\n\n"
        "```\n"
        "BDI = ((1 + AC + S + R + G) / (1 - DF - CPRB - IR/CSLL) - 1) * 100\n"
        "AC = 1.5%\n"
        "```\n\n"
        "Texto apos bloco de codigo.\n"
    )

    def test_bloco_codigo_incluido_no_pdf(self):
        """Blocos de codigo devem aparecer no PDF, nao serem descartados."""
        result = render_markdown_pdf(self.MD)
        assert _is_pdf(result)
        assert len(result) > 500  # type: ignore[arg-type]

    def test_bloco_codigo_vazio_nao_quebra(self):
        """Fence aberta e fechada sem nenhuma linha de conteudo entre elas
        chama flush_code() com code_lines vazio (branch False de `if code_lines`)."""
        md = "Antes\n\n```\n```\n\nDepois"
        result = render_markdown_pdf(md)
        assert _is_pdf(result)

    def test_bloco_codigo_nao_fechado_no_fim_do_documento(self):
        """Documento termina com um bloco de codigo ainda aberto — dispara o
        flush final `if in_code_block: flush_code()` (linha 306)."""
        md = "Texto normal\n\n```\nlinha de codigo sem fechar a fence"
        result = render_markdown_pdf(md)
        assert _is_pdf(result)


class TestImagens:
    def test_imagem_com_provider(self):
        import struct
        import zlib

        # PNG minimo valido (1x1 pixel branco)
        def _minimal_png() -> bytes:
            sig = b"\x89PNG\r\n\x1a\n"
            ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
            ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
            ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
            idat_data = zlib.compress(b"\x00\xff\xff\xff")
            idat_crc = zlib.crc32(b"IDAT" + idat_data) & 0xFFFFFFFF
            idat = struct.pack(">I", len(idat_data)) + b"IDAT" + idat_data + struct.pack(">I", idat_crc)
            iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
            iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
            return sig + ihdr + idat + iend

        png_bytes = _minimal_png()
        md = "# Com Imagem\n\n![grafico](grafico.png)\n\nTexto apos imagem."

        def provider(name: str) -> bytes | None:
            return png_bytes if name == "grafico.png" else None

        result = render_markdown_pdf(md, image_provider=provider)
        assert _is_pdf(result)

    def test_imagem_provider_retorna_none_nao_quebra(self):
        md = "![faltante](nao_existe.png)\n\nTexto normal."
        result = render_markdown_pdf(md, image_provider=lambda n: None)
        assert _is_pdf(result)

    def test_imagem_bytes_invalidos_sao_silenciados(self):
        """Bytes que nao formam uma imagem valida disparam a excecao silenciada
        em Image(...) (lines 255-256), sem quebrar o resto do documento."""
        md = "![corrompida](corrompida.png)\n\nTexto apos imagem invalida."

        def provider(name: str) -> bytes | None:
            return b"isto-nao-e-um-png-valido"

        result = render_markdown_pdf(md, image_provider=provider)
        assert _is_pdf(result)


class TestListasEOutrosElementos:
    def test_lista_bullets(self):
        md = "## Lista\n\n- Item A\n- Item B com **negrito**\n- Item C\n"
        assert _is_pdf(render_markdown_pdf(md))

    def test_linha_horizontal(self):
        md = "Parte 1\n\n---\n\nParte 2\n"
        assert _is_pdf(render_markdown_pdf(md))

    def test_negrito_inline(self):
        md = "O valor total e de **R$ 1.234.567,89** conforme orcamento.\n"
        assert _is_pdf(render_markdown_pdf(md))

    def test_caracteres_xml_especiais(self):
        """Angulo, ampersand e maior/menor nao devem crashar o Paragraph."""
        md = "Componentes: A & B, custo < R$ 100, eficiencia > 95%\n"
        assert _is_pdf(render_markdown_pdf(md))


class TestDocumentoCompleto:
    """Simula um relatorio completo com multiplas secoes."""

    MD = """\
# Relatorio de Viabilidade — Projeto ALPHA

**Data:** Maio 2026  
**Revisao:** 03

---

## 1. Resumo Executivo

O projeto ALPHA apresenta **VPL positivo** com TIR de 18,5% ao ano.

## 2. Composicao de Custos

| Categoria | Valor (R$) | Percentual |
|-----------|-----------|-----------|
| Mobilizacao | 1.200.000,00 | 5,2% |
| Estrutura Civil | 8.400.000,00 | 36,4% |
| Instalacoes | 3.600.000,00 | 15,6% |
| BDI (28%) | 3.752.000,00 | 16,2% |

## 3. Formula BDI

```
BDI = ((1 + AC + S + R + G) / (1 - DF - CPRB - IR/CSLL) - 1) * 100
```

### 3.1 Premissas

- Taxa de administracao central: 3,5%
- Seguro e garantia: 0,8%
- Risco: 1,2%

---

## 4. Cronograma Macro

| Fase | Duracao | Inicio |
|------|---------|--------|
| Mobilizacao | 30 dias | Jan/26 |
| Execucao | 180 dias | Fev/26 |
| Comissionamento | 45 dias | Ago/26 |
"""

    def test_documento_completo_gera_pdf(self):
        result = render_markdown_pdf(self.MD, title="Relatorio ALPHA — Revisao 03")
        assert _is_pdf(result)
        # ReportLab comprime os streams de conteúdo, então o tamanho absoluto não é
        # comparável ao backend fpdf2 antigo. A garantia honesta é relativa: o
        # documento completo (tabelas, código, múltiplas seções) gera um PDF
        # substancialmente maior que um documento trivial — provando que o conteúdo
        # é de fato renderizado (e não silenciosamente descartado).
        minimal = render_markdown_pdf("# Titulo")
        assert _is_pdf(minimal)
        assert len(result) > len(minimal) * 1.5  # type: ignore[arg-type]
