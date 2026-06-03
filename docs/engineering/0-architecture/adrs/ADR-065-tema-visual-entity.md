# ADR-065: `TemaVisual` como Entidade de Primeira Classe — Separação de Identidade Visual

**Status:** Implementado  
**Data:** 2026-05-19  
**Autor:** Engenheiro Sênior  
**Relacionado:** ADR-062 (Versionamento de Contextos e Perfis), ADR-064 (Formulários Tipados), ADR-048 (API + UI)

---

## 1. Contexto

### 1.1 Estado atual

`identidade_visual` é um campo `dict[str, Any]` dentro de `ContextoObra`:

```python
class ContextoObra(BaseModel):
    id: str
    perfil_id: str
    jurisdicao_id: str
    referencia_id: str
    catalogo_id: str
    identidade_visual: dict[str, Any] | None = None  # ← aqui
```

O Runtime injeta esse dict no catálogo em 3 pontos (`runtime.py:1082, 1199, 1443`), e dois exportadores o consomem:

```python
# catalog_excel.py:138, price_survey.py:52
idv = self.catalogo.get("identidade_visual", {})
cores = idv.get("cores", {})
fontes = idv.get("fontes", {})
```

### 1.2 Os dois problemas de design

**Problema 1 — Responsabilidade errada no `contexto`**

`contexto` responde à pergunta: *"qual catálogo, qual jurisdição, qual régua fiscal usar?"*  
`identidade_visual` responde a: *"como apresentar os artefatos gerados?"*

Essas são perguntas ortogonais. Um projeto no Ceará com catálogo SICRO pode usar a identidade MendesLobo padrão *ou* uma identidade customizada para um cliente específico — independentemente da jurisdição. Um rebrand não deve exigir criar uma nova versão do contexto.

**Problema 2 — Schema não tipado**

`dict[str, Any]` aceita qualquer coisa. Na prática:
- Hex sem `#` (`"1F4E78"`) — mas código poderia aceitar `"#1F4E78"` ou `"blue"` sem validar
- Fontes como string livre (`"Arial"`) — mas `openpyxl` e `fpdf2` têm conjuntos restritos de fontes suportadas; uma fonte inválida quebra a geração silenciosamente
- Tamanhos sem bounds — nada impede `"tamanho_corpo": 0` ou `"tamanho_cabecalho": 999`

### 1.3 Por que não mover para `perfil`

`perfil` é a entidade de parâmetros financeiros (margem, BDI, razão indireto/direto). Misturar pantone com margem-alvo cria a mesma confusão de responsabilidades, só que em outra entidade. Além disso, a mesma identidade visual serve múltiplos perfis (e.g., `mendeslobo-padrao`, `mendeslobo-obragoverno` compartilham a mesma marca).

---

## 2. Forças em tensão

| Força | Descrição |
|---|---|
| **Responsabilidade única** | Branding não é configuração regional nem parâmetro financeiro |
| **Compartilhamento** | Uma empresa usa o mesmo tema em projetos com perfis financeiros distintos |
| **Tipo seguro** | Cores, fontes e tamanhos têm domínios restritos e conhecidos |
| **Backward compatibility** | Exportadores leem `catalogo["identidade_visual"]` — esse contrato não pode quebrar |
| **Versionamento** | Rebrands precisam ser auditáveis (ADR-062) |
| **Editabilidade** | ADR-064 exige formulários tipados — não `dict[str, Any]` |

---

## 3. Decisão

### D1 — Nova entidade `TemaVisual` com schema Pydantic tipado

```python
from typing import Literal
from pydantic import BaseModel, Field, field_validator
import re

_HEX_RE = re.compile(r"^[0-9A-Fa-f]{6}$")

FONTES_SUPORTADAS = ["Arial", "Helvetica", "Calibri", "Times New Roman", "Courier"]

class CoresTema(BaseModel):
    """Paleta cromática — hex de 6 dígitos sem '#'."""
    cabecalho_fundo: str = "1F4E78"
    cabecalho_texto: str = "FFFFFF"
    zebra_par:       str = "FFFFFF"
    zebra_impar:     str = "F2F2F2"
    borda:           str = "D9D9D9"
    destaque:        str = "FFC000"

    @field_validator("*", mode="before")
    @classmethod
    def validate_hex(cls, v: str) -> str:
        if not _HEX_RE.match(str(v)):
            raise ValueError(f"Cor inválida '{v}' — esperado hex de 6 dígitos sem '#'")
        return str(v).upper()


class FontesTema(BaseModel):
    """Tipografia — fontes da lista suportada, tamanhos com bounds explícitos."""
    cabecalho:           Literal["Arial", "Helvetica", "Calibri",
                                  "Times New Roman", "Courier"] = "Arial"
    corpo:               Literal["Arial", "Helvetica", "Calibri",
                                  "Times New Roman", "Courier"] = "Calibri"
    tamanho_cabecalho:   int = Field(default=11, ge=8, le=16)
    tamanho_corpo:       int = Field(default=10, ge=8, le=14)
    tamanho_titulo:      int = Field(default=14, ge=10, le=24)


class TemaVisual(BaseModel):
    """Identidade visual de uma empresa/cliente — entidade de primeira classe."""
    id: str
    empresa: str
    perfil_exibicao: Literal["EXECUTIVO", "SIMPLES", "TECNICO"] = "EXECUTIVO"
    cores:  CoresTema  = Field(default_factory=CoresTema)
    fontes: FontesTema = Field(default_factory=FontesTema)
```

**Por que `Literal` para fontes e não `selectbox` apenas:**  
`Literal` no Pydantic garante que o JSON persistido nunca contenha uma fonte não-suportada — a validação acontece na camada de domínio, antes de chegar ao exporter. O `selectbox` no formulário é a consequência UI, não a garantia.

**Por que hex sem `#`:**  
Os exportadores atuais (`catalog_excel.py`, `price_survey.py`) esperam hex sem `#` — mantemos o contrato de serialização.

### D2 — `config/temas/` como diretório de configuração

```
config/temas/
├── default/                        ← fallback para projetos sem tema_id
│   └── tema.json
└── mendeslobo-corporativo/         ← migração do identidade_visual atual
    ├── tema.json                   ← cópia da versão atual (current)
    └── versions/
        └── v1.json                 ← criada pela migração
```

`tema.json` = snapshot da versão corrente (espelha o padrão ADR-062).

### D3 — `ContextoObra` ganha `tema_id` e perde `identidade_visual`

```python
class ContextoObra(BaseModel):
    id: str
    perfil_id: str
    jurisdicao_id: str
    referencia_id: str
    catalogo_id: str
    tema_id: str | None = None          # ← novo; None → usa "default"
    # identidade_visual removido        ← migrado para TemaVisual
```

Backward-compat: contextos sem `tema_id` → Runtime carrega `config/temas/default/tema.json`.

### D4 — Runtime carrega `TemaVisual` e injeta via chave existente

O padrão de injeção `catalogo["identidade_visual"] = ...` **é preservado** — exportadores não mudam:

```python
def load_tema(self, tema_id: str | None = None) -> TemaVisual:
    """Carrega tema pelo ID. None → fallback 'default'."""
    tid = tema_id or "default"
    path = self._config_root / "temas" / tid / "tema.json"
    if not path.exists():
        return TemaVisual(id=tid, empresa="Concilium")
    return TemaVisual.model_validate_json(path.read_text(encoding="utf-8"))

# Nos 3 pontos de injeção no Runtime (linhas 1082, 1199, 1443):
# Antes:
if contexto.identidade_visual:
    catalogo["identidade_visual"] = contexto.identidade_visual
# Depois:
tema = self.load_tema(contexto.tema_id)
catalogo["identidade_visual"] = tema.model_dump()
```

A chave `"identidade_visual"` no dict do catálogo é mantida para não quebrar nenhum exporter.

### D5 — `TemaVisual` participa do `ConfigVersionService` (ADR-062)

```python
TemaVersionService = ConfigVersionService(
    config_dir=config_root / "temas",
    entity_file="tema.json",
    versions_subdir="versions",
)
```

Criação de versão ao rebranding: `TemaVersionService.create_version(tema_id, fields, motivo)`.

### D6 — Formulário tipado via ADR-064

```python
TEMA_EDITABLE_FIELDS: dict[str, FieldSpec] = {
    "empresa":           FieldSpec(label="Nome da empresa",    widget="text_input"),
    "perfil_exibicao":   FieldSpec(label="Perfil de exibição", widget="selectbox",
                                   options=["EXECUTIVO", "SIMPLES", "TECNICO"]),
    # ── Cores ──────────────────────────────────────────────────────────────
    "cores.cabecalho_fundo": FieldSpec(label="Cabeçalho — fundo", widget="color_hex",
                                        help="Hex 6 dígitos sem '#' (ex: 1F4E78)"),
    "cores.cabecalho_texto": FieldSpec(label="Cabeçalho — texto", widget="color_hex"),
    "cores.destaque":        FieldSpec(label="Cor destaque",       widget="color_hex"),
    "cores.zebra_impar":     FieldSpec(label="Zebra — linha ímpar", widget="color_hex"),
    "cores.borda":           FieldSpec(label="Cor de borda",        widget="color_hex"),
    # ── Fontes ─────────────────────────────────────────────────────────────
    "fontes.cabecalho":         FieldSpec(label="Fonte cabeçalho", widget="selectbox",
                                           options=["Arial", "Helvetica", "Calibri",
                                                    "Times New Roman", "Courier"]),
    "fontes.corpo":             FieldSpec(label="Fonte corpo",      widget="selectbox",
                                           options=["Arial", "Helvetica", "Calibri",
                                                    "Times New Roman", "Courier"]),
    "fontes.tamanho_cabecalho": FieldSpec(label="Tam. cabeçalho (pt)", widget="number_input",
                                           min_value=8, max_value=16, step=1),
    "fontes.tamanho_corpo":     FieldSpec(label="Tam. corpo (pt)", widget="number_input",
                                           min_value=8, max_value=14, step=1),
    "fontes.tamanho_titulo":    FieldSpec(label="Tam. título (pt)", widget="number_input",
                                           min_value=10, max_value=24, step=1),
}

TEMA_READONLY_FIELDS: set[str] = {"id"}
```

O widget `"color_hex"` é adicionado a `FieldSpec`/`render_typed_form` — renderiza `st.color_picker` com conversão automática para hex 6 dígitos sem `#`. É o único widget novo além dos já definidos no ADR-064.

### D7 — Migração do estado atual (zero-downtime)

1. Criar `config/temas/default/tema.json` com valores neutros (preto/branco/cinza)
2. Criar `config/temas/mendeslobo-corporativo/tema.json` com o `identidade_visual` atual do contexto `mendeslobo`
3. Adicionar `tema_id: "mendeslobo-corporativo"` ao `contextos/mendeslobo/versions/v1.json` (nova versão v2 via `TemaVersionService`)
4. Remover `identidade_visual` do contexto `mendeslobo` na mesma operação
5. Nenhum exporter ou test falha — a chave `catalogo["identidade_visual"]` é preservada

---

## 4. Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Mover para `perfil` como sub-campo | Mesma confusão de responsabilidades; tema compartilhado entre perfis requereria duplicação |
| A2 | Manter em `contexto` como antes | Não resolve o schema fraco; `dict[str, Any]` não valida hex nem fontes |
| A3 | `dict` tipado diretamente em `ContextoObra` | Perde o reuso entre contextos; impossível versionar independentemente |
| A4 | Resolver tema na UI (não no domínio) | Exportadores como `catalog_excel.py` e `price_survey.py` são camada de infraestrutura sem acesso à UI; o tema precisa chegar via catalogo dict |

---

## 5. Consequências

### Positivas

| Consequência | Benefício |
|---|---|
| `TemaVisual` com schema Pydantic | Validação de hex/fonte/tamanho na camada de domínio |
| `Literal` para fontes | Nenhum exporter recebe fonte inválida que quebra silenciosamente |
| `tema_id` em `contexto` | Um rebrand = criar novo tema, não versão de contexto |
| `config/temas/default/` | Novos contextos funcionam sem configurar tema |
| ADR-062 compatível | Rebranding auditável com versionamento e `motivo` |
| ADR-064 `color_hex` widget | `st.color_picker` com validação automática; sem caixa de texto livre para cor |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| 10 ocorrências de `contexto.identidade_visual` no código | Substituição mecânica pontual (runtime.py ×3, commands_manage.py ×2, domain model ×1) |
| Contextos antigos sem `tema_id` precisam de fallback | `None → "default"` já definido; `config/temas/default/tema.json` criado na migração |
| Novo widget `color_hex` em `form_contracts.py` | Adição de 1 case no `render_typed_form` switch; não afeta campos existentes |

---

## 6. Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| **F1 — Domínio** | `TemaVisual`, `CoresTema`, `FontesTema` em `domain/models/tema.py`; validadores de hex e `Literal` de fonte | Pendente |
| **F2 — Arquivos de config** | `config/temas/default/tema.json` + `config/temas/mendeslobo-corporativo/tema.json` + migração do contexto mendeslobo | Pendente |
| **F3 — Runtime** | `Runtime.load_tema(tema_id)` + substituição das 3 injeções `contexto.identidade_visual` | Pendente |
| **F4 — ContextoObra** | `tema_id: str | None = None` + remover `identidade_visual` do modelo + `ConfigVersionService` para temas | Pendente |
| **F5 — CLI** | Substituir `ctx.identidade_visual` por `runtime.load_tema(ctx.tema_id)` em commands_manage.py | Pendente |
| **F6 — UI** | `TEMA_EDITABLE_FIELDS` em `form_contracts.py`; widget `color_hex` em `render_typed_form`; aba de temas na página Perfis e Contextos | Pendente |
| **F7 — Testes** | Validação Pydantic de hex/fonte/tamanho; fallback para tema default; zero regressão nos exporters | Pendente |

---

## 7. Definition of Done

### Fase 1 — Domínio
- [x] `domain/models/tema.py`: `CoresTema`, `FontesTema`, `TemaVisual`, `TEMA_DEFAULT`
- [x] `field_validator` aceita `"#1f4e78"` → normaliza para `"1F4E78"`; rejeita `"blue"`, `"GGGGGG"`
- [x] `Literal` de fontes rejeita `"Comic Sans"` e aceita `"Arial"`, `"Calibri"`, etc.
- [x] `Field(ge=8, le=16)` em `tamanho_cabecalho` rejeita 0 e 99; `Field(ge=10, le=24)` em `tamanho_titulo`
- [x] `to_catalogo_dict()` preserva chaves `cores` e `fontes` para backward-compat com exporters

### Fase 2 — Arquivos de configuração
- [x] `config/temas/default/tema.json` criado com valores neutros
- [x] `config/temas/mendeslobo-corporativo/tema.json` + `versions/v1.json` criados com valores do contexto original
- [x] `config/contextos/mendeslobo/versions/v1.json` migrado: `tema_id: "mendeslobo-corporativo"`, sem `identidade_visual`

### Fase 3 — Runtime
- [x] `Runtime.load_tema(tema_id)` com cache + fallback para `TEMA_DEFAULT`
- [x] 3 injeções `contexto.identidade_visual` substituídas por `self.load_tema(contexto.tema_id).to_catalogo_dict()`
- [x] Chave `catalogo["identidade_visual"]` preservada (backward-compat)

### Fase 4 — ContextoObra + versioning
- [x] `ContextoObra.tema_id: str | None = None`; `identidade_visual` removido via `ConfigDict(extra="ignore")`
- [x] `TemaVersionService(ConfigVersionService)` em `contexto_version_service.py`
- [x] Endpoints REST `/api/temas`, `/api/temas/{id}/versions`, `/api/temas/compare`
- [x] Métodos `list_temas/create_tema_version/compare_tema_versions` em `ProjectService` + `ConciliumService`

### Fase 5 — CLI
- [x] `commands_manage.py`: 2 ocorrências de `ctx.identidade_visual` → `rt.load_tema(ctx.tema_id).to_catalogo_dict()`

### Fase 6 — UI
- [x] `form_contracts.py`: `TEMA_EDITABLE_FIELDS` com dotted keys (`"cores.destaque"`) + `TEMA_READONLY_FIELDS`
- [x] Widget `"color_hex"` em `render_typed_form`: `st.color_picker` → normaliza para hex 6 sem `#`
- [x] `_get_nested`/`_set_nested` para campos aninhados via dotted keys
- [x] Aba "🎨 Temas" em `perfis_contextos_page.py`: histórico, editor tipado, nova versão

### Fase 7 — Testes (24 testes)
- [x] CoresTema: 7 testes (hex válido/inválido, normalização `#` → sem `#`)
- [x] FontesTema: 6 testes (Literal fontes, bounds de tamanho)
- [x] TemaVisual: 5 testes (defaults, `to_catalogo_dict`, load from file)
- [x] ContextoObra: 4 testes (tema_id, sem identidade_visual, migração real)
- [x] Backward-compat: 2 testes (exporters ainda leem `cores`/`fontes` corretamente)
- [x] 1441 testes totais passando, 0 regressões
