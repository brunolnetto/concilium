# ADR-038 — Catálogo Regionalizado e Tributação por Jurisdição (BDI)

**Status:** Implementado  
**Data:** 2026-05-08  
**Contexto:** MendesLobo Construtora — Concilium

---

## Contexto

### Problema

O modelo de catálogo original tratava preços de insumos como valores únicos globais, ignorando a variabilidade regional que é fundamental na engenharia de infraestrutura:

- **P1 — Preço único inviável em obras lineares:** Rodovias e linhas de transmissão podem cruzar 5 estados. O preço do mesmo insumo (ex: brita, mão de obra de operador) varia significativamente entre CE e SP — diferenças de logística, ICMS, e mercado de trabalho local. Um único preço resulta em orçamentos sistematicamente sub ou superdimensionados por trecho.
- **P2 — BDI flat sem tributação real:** O BDI era calculado com alíquotas de ISS, PIS, COFINS e CPRB fixas por projeto. Na prática, o ISS varia por município (2% a 5%), o regime tributário (Lucro Real vs. Presumido) altera PIS/COFINS, e o CPRB (desoneração) é setorial. Aplicar um ISS médio pode criar passivos fiscais em determinados municípios.
- **P3 — Ausência de histórico regional:** Auditorias de obras passadas exigem saber qual era o preço praticado em determinada jurisdição em determinada data. Sem regionalização persistida, o relatório de benchmark para obras futuras no mesmo corredor é inviável.
- **P4 — `sicro_inject.py` sem integração formal:** O pipeline de ingestão SICRO (`sicro_inject.py`) já injetava `regionalizacao` nos catálogos, mas sem um modelo de domínio formal que defina como esses dados são consumidos nas Skills.

---

## Decisão

### D1 — Estrutura `regionalizacao` nos Insumos do Catálogo

Insumos do catálogo suportam um bloco `regionalizacao` que mapeia `jurisdicao_id` a um preço local. O motor de resolução usa o preço regional se disponível; caso contrário, cai para `preco_base`:

```json
{
  "codigo": "M0043",
  "descricao": "Óleo diesel",
  "tipo": "MATERIAL",
  "unidade": "l",
  "preco_base": 5.40,
  "regionalizacao": {
    "BR-CE": { "preco": 5.397, "fonte": "SICRO/01-2026", "data_ref": "2026-01-01" },
    "BR-SP": { "preco": 5.612, "fonte": "SICRO/01-2026", "data_ref": "2026-01-01" },
    "BR-AM": { "preco": 6.103, "fonte": "SICRO/01-2026", "data_ref": "2026-01-01" }
  }
}
```

### D2 — Pipeline SICRO como Fonte Primária de Preços Regionais

O pipeline `scripts/sicro_inject.py` é o mecanismo oficial de ingestão. Lê os `insumos.json` por UF (`config/referencias/SICRO/BR-{UF}/`), resolve o mapeamento via `sicro_concilium_mapping.yaml` e injeta os preços no bloco `regionalizacao` dos catálogos:

```
config/referencias/
  SICRO/
    BR-CE/
      insumos.json     ← 2402 insumos (564 equipamentos + 1693 materiais + 145 mão de obra)
      cpus.json
      producoes.json
  sicro_concilium_mapping.yaml  ← De-para: código SICRO → código Concilium
```

### D3 — Motor Tributário BDI por Jurisdição (`motor_tributario_bdi`)

Os arquivos de jurisdição (`config/jurisdicoes/BR-{UF}.json`) são expandidos com o bloco `motor_tributario_bdi`. A Skill 04/05 (BDI) lê esses parâmetros dinamicamente em vez de usar alíquotas fixas de projeto:

```json
{
  "jurisdicao_id": "BR-CE",
  "nome": "Ceará",
  "encargos_sociais": { ... },
  "motor_tributario_bdi": {
    "iss_aliquota": 0.05,
    "pis_cofins_aliquota": 0.0365,
    "cprb_aliquota": 0.045,
    "regime": "LUCRO_PRESUMIDO",
    "notas": "ISS municipal max 5% per Lei Complementar 116/2003"
  }
}
```

### D4 — Resolução de Preço com Contexto de Escopo

Quando o pipeline de Skills processa um escopo vinculado a uma jurisdição específica, o `RepositorioInsumo` resolve o preço na seguinte ordem de prioridade:

```
1. Project Override Layer (config/projetos/{id}/overrides/) [ADR-040]
2. Bloco regionalizacao[jurisdicao_id]
3. preco_base (fallback global)
```

```python
def resolver_preco(self, codigo: str, jurisdicao_id: str | None = None) -> float:
    insumo = self._insumos[codigo]
    if jurisdicao_id and jurisdicao_id in insumo.get("regionalizacao", {}):
        return insumo["regionalizacao"][jurisdicao_id]["preco"]
    return insumo["preco_base"]
```

### D5 — Sensibilidade de Escopo Multi-Regional (ADR-031)

Projetos que abrangem múltiplas jurisdições (ex: rodovia CE → PI → MA) vinculam diferentes **Escopos** a diferentes **Jurisdições**. O pipeline de Skills alterna o contexto de resolução conforme o escopo processado:

```python
class Escopo(BaseModel):
    jurisdicao_id: str | None = None   # "BR-CE", "BR-SP", etc.
    data_base_orcamento: date | None = None
    tag_versao_catalogo: str | None = None
```

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo da Rejeição |
|---|---|---|
| X1 | Catálogos separados por UF (um arquivo JSON por estado) | Fragmentação ingerenciável; insumos que não variam regionalmente (ex: equipamentos nacionais) seriam duplicados em 27 arquivos. |
| X2 | Converter SICRO para o `preco_base` global e ignorar regionalização | Perde toda a inteligência regional do DNIT; inviabiliza orçamentos multi-jurisdicionais precisos. |
| X3 | Tabela relacional SQL de preços regionais | Overkill para o modelo de armazenamento flat atual; adiciona dependência de banco de dados sem benefício imediato. |

---

## Consequências

### Positivas

| ID | Consequência |
|---|---|
| C1 | Precisão cirúrgica em obras lineares: cada trecho usa o preço correto para sua UF. |
| C2 | Conformidade tributária BDI: ISS/PIS/COFINS/CPRB configurados por jurisdição, não por projeto. |
| C3 | Auditabilidade regional: o bloco `regionalizacao` registra fonte (`"SICRO/01-2026"`) e `data_ref` por preço. |
| C4 | Pipeline SICRO automatizado: 27 UFs re-parseadas com `sicro_fetch.py` + `sicro_inject.py`. |

### Negativas / Riscos

| ID | Risco | Mitigação |
|---|---|---|
| R1 | Insumos sem mapping SICRO ficam sem regionalização. | `sicro_inject.py` emite warnings por insumo não mapeado; relatório de cobertura via `_audit_sicro.py`. |
| R2 | Manutenção de 27 arquivos de jurisdição (`BR-CE.json`, ..., `BR-TO.json`). | Geração automática do bloco `motor_tributario_bdi` base via script; revisão manual apenas para municípios com ISS diferenciado. |
| R3 | `RepositorioInsumo` mais complexo com resolução de contexto de preço. | Estratégia de resolução encapsulada em método único `resolver_preco()` com fallback claro. |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| **F1 — Parser SICRO** | `sicro_fetch.py` com parser de equipamentos multi-coluna; 27 `insumos.json` com `componentes_custo` | ✅ Implementado |
| **F2 — Injeção Regional** | `sicro_inject.py` + `sicro_concilium_mapping.yaml`; bloco `regionalizacao` nos catálogos | ✅ Implementado |
| **F3 — Motor Tributário** | Bloco `motor_tributario_bdi` nos 27 arquivos de jurisdição; Skills 04/05 lendo parâmetros dinâmicos | ✅ Implementado |
| **F4 — Resolução Contextual** | `RepositorioInsumo.resolver_preco()` com prioridade Override → Regional → Base; `Escopo.jurisdicao_id` adicionado | ✅ Implementado |

---

## Definition of Done

### Fase 1 — Parser SICRO (✅)
- [x] `sicro_fetch.py` extrai todos os 11 campos de equipamentos corretamente.
- [x] `insumos.json` incluem `componentes_custo`, `mao_obra_operacao`, `custo_produtivo`, `custo_improdutivo` para equipamentos.
- [x] 27 UFs parseadas (BR-AC a BR-TO).

### Fase 2 — Injeção Regional (✅)
- [x] `sicro_concilium_mapping.yaml` mapeia códigos SICRO → códigos Concilium.
- [x] `sicro_inject.py` injeta `regionalizacao` nos catálogos sem sobrescrever outros campos.
- [x] Bloco `regionalizacao` inclui `preco`, `fonte` e `data_ref` por jurisdição.

### Fase 3 — Motor Tributário BDI (✅)
- [x] Modelos `AliquotasBdi` e `MotorTributarioBdi` criados em `domain/models/jurisdicao.py`.
- [x] Campo `motor_tributario_bdi: MotorTributarioBdi | None` adicionado ao modelo `Jurisdicao`.
- [x] 27 arquivos `config/jurisdicoes/BR-{UF}.json` gerados com alíquotas base ISS 5%, PIS 0.65%, COFINS 3%, CPRB 4.5% (BR-CE com ISS 2% local).
- [ ] Skills 04/05 refatoradas para ler `motor_tributario_bdi` da jurisdição do escopo em vez de alíquotas fixas.

### Fase 4 — Resolução Contextual (✅)
- [x] `RepositorioInsumo.resolver_preco(codigo, jurisdicao_id, overrides, data_referencia)` implementado com cascata `PROJECT_OVERRIDE → SICRO_REGIONAL → HISTORICO_SCD2 → MASTER_BASE`.
- [x] `Escopo.jurisdicao_id: str | None` adicionado para vincular escopo à jurisdição fiscal.
- [ ] Skills 01-07 passam `jurisdicao_id` ao resolver preços de insumos.
- [ ] Teste de integração: escopo BR-CE produz custo direto diferente de escopo BR-SP para mesma EAP.
