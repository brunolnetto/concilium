# Guia de Versionamento — Projeto e Catálogo

**Projeto:** Concilium — MendesLobo Construtora  
**Audiência:** Engenheiros de Planejamento, Orçamento e CEO  
**Versão:** 1.0 — 2026-06-12  
**Referências:** ADR-031, ADR-041, ADR-062

---

## Por que Versionamento

Em orçamentação de obras, o mesmo projeto passa por múltiplas rodadas de refinamento: o escopo muda, os preços de catálogo são atualizados, diferentes estratégias de pool são testadas. O versionamento garante que:

1. **Decisões passadas são auditáveis** — é possível reconstruir o raciocínio de cada rodada
2. **Mudanças de catálogo não quebram projetos existentes** — cada projeto captura a versão do catálogo usada
3. **Cenários alternativos coexistem** — o plano aprovado e os planos em exploração ficam separados

---

## Parte 1 — Versionamento de Projeto

### 1.1 Estrutura: Escopos e Planos (ADR-031)

Um projeto não tem versões lineares — tem uma estrutura de **escopos** e **planos**:

```
Projeto
└── Escopo 1 (ex: "Lote 09")
    ├── Plano Principal    ← aprovado, referência
    ├── Plano Alternativo  ← em exploração (mais frentes)
    └── Plano Cenário C    ← arquivado (descartado)
```

**Escopo** define os limites físicos e contratuais do trabalho (EAP, datas, localização).  
**Plano** é uma instância de planejamento dentro de um escopo — cronograma, pool, resultado financeiro.

### 1.2 Estados de um Plano

```
RASCUNHO → EM_ANDAMENTO → APROVADO
                       → ARQUIVADO
```

- `RASCUNHO`: recém-criado, pipeline ainda não executada
- `EM_ANDAMENTO`: pipeline em execução (skills sendo completadas)
- `APROVADO`: plano congelado como referência do escopo — não pode ser editado
- `ARQUIVADO`: descartado mas preservado para auditoria

### 1.3 Criando e Gerenciando Planos

**Via MCP:**
```
nova_versao(project_id, escopo_id, nome="Alternativa frentes +25%")
  → cria plano em RASCUNHO, sem afetar o plano aprovado

disparar_pipeline(project_id, skill_id, plano_id=novo_plano_id, ...)
  → executa pipeline no novo plano

aprovar_versao(project_id, escopo_id, plano_id=novo_plano_id)
  → congela plano como referência; outros planos ficam ARQUIVADO automaticamente
```

**Regra:** apenas um plano pode estar APROVADO por escopo a qualquer momento.

### 1.4 O Que é Versionado em Cada Plano

Cada plano preserva independentemente:
- **Canonical JSON** — estado completo após cada skill (escopo, cronograma, equipes, resultado financeiro)
- **Inputs de skill** — o que foi fornecido a cada skill (overrides de regime, pool_config, etc.)
- **Log de invocações** — sequência e status de cada skill executada
- **Artefatos** — PDFs, planilhas, relatórios gerados
- **Snapshot do catálogo** — versão do catálogo usada (ver Parte 2)
- **Perfil BDI** — taxas de markup com hash de conteúdo e diff

### 1.5 Comparando Planos

```
comparar_planos(project_id, escopo_id, plano_a="plan-001", plano_b="plan-002")
```

Retorna lado a lado:
- Custo direto (N3 — pool instancial)
- Custo indireto
- Margem bruta (%)
- Prazo (semanas)
- Composição BDI

---

## Parte 2 — Versionamento de Catálogo (ADR-062)

### 2.1 O que é versionado

O catálogo é composto por:
- **Insumos** — preços de mão-de-obra, equipamentos, materiais, combustível
- **CPUs** (Composições Padrão de Unidade) — equipes, produtividades, composições
- **Produções** — variantes de produtividade por condição
- **Jurisdições** — regimes tributários e encargos regionais

Cada **contexto** (ex: `mendeslobo`) agrupa todos esses elementos. Quando qualquer elemento é atualizado, uma **nova versão do contexto** é criada.

### 2.2 Estrutura de versões

```
config/contextos/mendeslobo/
├── contexto.json           ← metadados, aponta current_version
├── current                 ← contém "v3" (texto plano)
└── versions/
    ├── v1.json             ← versão inicial
    ├── v2.json             ← após atualização SINAPI jun/26
    └── v3.json             ← após calibração diesel set/26
```

Cada versão registra: quem criou, quando, qual o motivo da mudança.

### 2.3 Consultando versões via MCP

**Listar histórico:**
```
listar_versoes_catalogo("mendeslobo")

→ {
    "versao_atual": "v3",
    "total_versoes": 3,
    "historico": [
      {"version": "v1", "created_at": "2026-01-15", "created_by": "sistema", "motivo": "base_initial"},
      {"version": "v2", "created_at": "2026-06-01", "created_by": "joao.planejamento", "motivo": "SINAPI jun/26 aplicado"},
      {"version": "v3", "created_at": "2026-09-10", "created_by": "maria.orcamento", "motivo": "diesel R$6.80 set/26"}
    ]
  }
```

**Comparar duas versões:**
```
comparar_versoes_catalogo("mendeslobo", "v2", "v3")

→ {
    "diff": {
      "modificados": {
        "insumos.diesel.preco_unitario": {"v2": 6.50, "v3": 6.80},
        "insumos.diesel.data_referencia": {"v2": "2026-05-01", "v3": "2026-09-01"}
      },
      "adicionados": {},
      "removidos": {}
    }
  }
```

### 2.4 Impacto de uma nova versão de catálogo

Quando o catálogo é atualizado (nova versão), os **projetos existentes não são afetados** — cada projeto captura a versão do catálogo em `meta.json` no momento da criação:

```json
{
  "nome": "Lote 09 - Ferrovia Transnordestina",
  "contexto_id": "mendeslobo",
  "contexto_version": "v2",   ← versão usada na criação
  ...
}
```

Para aplicar uma nova versão do catálogo a um projeto existente:
1. Criar novo plano (`nova_versao`)
2. Re-executar a pipeline completa
3. Comparar resultado com o plano anterior (`comparar_planos`)
4. Aprovar o novo plano se a variação for aceitável

### 2.5 Verificar impacto de mudança de preço

Antes de criar nova versão do catálogo, é possível simular o impacto:

```
calcular_pu_producao("mendeslobo", "PROD-TERRA-ESCO-001",
                     preco_diesel=6.80)

→ PU recalculada com novo diesel, sem persistir nada
```

Para impacto sistêmico (todos os insumos):
```
verificar_integridade_catalogo("mendeslobo", ...)
→ mostra variação de PU em todas as CPUs afetadas
```

---

## Parte 3 — Snapshot de Catálogo por Execução

### 3.1 Imutabilidade de cada run

Cada execução da pipeline captura um **snapshot imutável** do catálogo no momento da execução:

```
projetos/{uuid}/snapshots/
├── insumos_overlay.json    ← preços usados (com overrides de projeto)
├── cpus_bundle.json        ← composições usadas
└── jurisdicao.json         ← regime tributário e encargos
```

Isso garante **reprodutibilidade**: re-executar a pipeline com o mesmo snapshot produz o mesmo resultado, mesmo que o catálogo tenha mudado depois.

### 3.2 Rastreabilidade catálogo → projeto

O `auditar_plano` e o `consultar_status` expõem qual versão do catálogo foi usada em cada plano. A trilha completa é:

```
Projeto {uuid}
  ↳ Plano {plano_id}
      ↳ contexto_version: "v2"
      ↳ snapshot: projetos/{uuid}/snapshots/v2_2026-06-01.json
      ↳ resultado.custo: R$ 43.8M
```

Se o cliente questionar um valor, é possível reconstruir exatamente o catálogo que gerou aquele custo.

---

## Parte 4 — BDI com Versionamento Próprio

O perfil de BDI (taxas de markup sobre MO, EQ, material, indireto) tem seu próprio versionamento dentro do projeto:

```
salvar_perfil_bdi(project_id,
    tributario={"iss": 0.03, "cofins": 0.03, ...},
    lucro={"mo": 0.08, "material": 0.05, ...},
    confirmado_por="engenheiro.senior",
    motivo_revisao="ISS negociado para 3%")

→ {
    "perfil_id": "bdi-004",
    "versao": 4,
    "content_hash": "sha256:abc123...",
    "diff": {
      "iss": {"antes": 0.05, "depois": 0.03}
    }
  }
```

O `content_hash` permite verificar integridade: se o BDI aplicado no resultado bate com o hash registrado, não houve adulteração.

---

## Resumo: O que Cada Mecanismo Versiona

| Mecanismo | O que versiona | Granularidade | Quem gerencia |
|---|---|---|---|
| **Escopos/Planos** | Iterações de planejamento | Por projeto | Engenheiro via MCP |
| **Versões de Catálogo** | Preços e composições | Por contexto | Responsável de catálogo via MCP |
| **Snapshot por execução** | Catálogo usado em cada run | Por plano | Sistema (automático) |
| **Perfil BDI** | Taxas de markup | Por projeto | Engenheiro via MCP |
| **Benchmark NEP-039** | Projetos de referência | Por benchmark | Sistema (imutável após aprovação) |

---

## Quando Criar uma Nova Versão do Catálogo

| Evento | Ação recomendada |
|---|---|
| Atualização SINAPI (mensal) | `comparar_rfi_catalogo` → `atualizar_preco_insumo` → nova versão de contexto |
| Mudança de preço de diesel | `atualizar_preco_insumo` → nova versão de contexto |
| Adição de CPU nova | Adicionar JSON na pasta de CPUs → nova versão de contexto |
| Calibração por dado histórico de obra | `atualizar_preco_insumo` com nota de calibração → nova versão |
| Mudança tributária (ISS, INSS, IRRF) | Atualizar jurisdição → nova versão de contexto |

A nova versão é criada automaticamente sempre que um insumo ou CPU é atualizado via `atualizar_preco_insumo` ou `adicionar_variante_producao`. Os projetos existentes só são afetados se o engenheiro criar um novo plano explicitamente.
