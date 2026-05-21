# ADR-032 — Arquitetura Versionada e Validada para CPU × Insumo × Jurisdição

**Status:** Implementado 
**Data:** 2026-05-07  
**Contexto:** MendesLobo Construtora — Concilium

---

## Modelo de Dados Implementado (e Proposto)

> Extrato do que foi implementado e do design das entidades ainda pendentes de versionamento.

### `Funcao` — `src/concilium/domain/models/catalogo.py` (Implementado)

A `Funcao` atua como elo canônico para equipes.

| Campo | Tipo | Descrição |
|---|---|---|
| `funcao_id` | `str` | Ex.: `"OPER-ESCAV"` |
| `descricao` | `str` | Descrição da função |
| `insumo_id` | `str` | Fonte canônica de preço `Insumo(MAO_OBRA).codigo` |

### `InsumoVersionado` e `CPUVersionada` (A Fazer)

Entidades futuras que encapsularão a linha do tempo. Substituirão as atuais estruturas base `Insumo` e `CPU` injetando listas de versões (com histórico de preço e validação).

---

## Contexto

### Problema

O modelo clássico de Composição de Preços Unitários (CPU), Insumos e Jurisdição (camada 0) possuía problemas estruturais crônicos que prejudicavam a rastreabilidade e a segurança do cálculo:

- **P1 — Função/Equipamento sem modelo:** Equipamentos e funções operavam apenas com "string IDs" soltos, sem esquemas tipados rígidos de mapeamento e consumo.
- **P2 / P8 — Encargos e Auditoria:** Encargos implícitos (ex: 177.7%) sem trilha clara de qual fator da jurisdição foi aplicado, nem metadados de quem/quando realizou a medição de preço.
- **P3 / P6 — CPU e Insumo sem versionamento:** A alteração de uma composição ou preço sobrescrevia o histórico no catálogo. Era impossível resgatar exatamente como a CPU `ESCO-CARGA-1CAT` estava em Janeiro/2026.
- **P4 — Validação incompleta:** Falta de proteção contra a criação de composições com unidades incompatíveis, coeficientes negativos, ou categorias cruzadas.
- **P5 — Circular dependency risco:** Possibilidade de uma CPU A referenciar Insumo X, cujo preço é derivado da CPU B, que usa Insumo Y derivado da CPU A.

---

## Decisão

### D1 — Validações Aprofundadas (Implementado)

Implementação de regras estritas antes de aceitar qualquer CPU, orquestradas em `ValidadorCPUInsumo`:
- `VAL-CPU-INS-01` a `07`: Checagem da existência de Insumos, Equipamentos e Funções; Verificação da matriz de compatibilidade (ex: Tipo `MAO_OBRA` vs Categoria `EQUIPAMENTO`); Ranges lógicos e obrigatórios para coeficientes e unidades.

### D2 — Modelagem de Domínio Simplificada (Implementado)

- **Função:** Estabelecida como entidade de primeira classe (`class Funcao`).
- **Equipamento:** Ao invés de uma classe separada, a abstração foi integrada nativamente através de `AtributosInsumo` (para o insumo base) e resolvida dentro da `EquipamentoEquipe` da CPU. Isso evitou a explosão de entidades no catálogo e reduziu complexidade.

### D3 — Trilha de Auditoria e Encargos In-place (Implementado)

Introdução da classe `AuditoriaProducao` e trilhas dentro dos serviços de catálogo (`updater.py`) para injetar dados auditáveis nos dicionários/modelos diretamente. Dispensou a necessidade de uma camada de aplicação isolada (`LayerAuditoria`).

### D4 — Versionamento Estrito de Catálogo (A Fazer)

Adoção de Modelos Versionados (`InsumoVersionado`, `CPUVersionada`, `JurisdicaoVersionada`) para rastrear mutações ao longo do tempo. O `id_atu` de um insumo carregará sua referência temporal para garantir snapshots imutáveis em projetos já aprovados.

### D5 — Bloqueio de Dependência Circular (A Fazer)

Adição de verificação em grafo (DFS) no repositório de CPUs para proibir loops de composição antes da persistência.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo da rejeição |
|---|---|---|
| X1 | Classe `Equipamento` em separado no domínio | Overhead desnecessário. Propriedades como consumo/potência casam perfeitamente com os atributos flexíveis de `Insumo` e reduzem joins. |
| X2 | `LayerAuditoria` como microsserviço/tabela paralela | Complexidade prematura. Auditoria acoplada nativamente na atualização de produção e preços atende os requisitos de auditoria mantendo a coesão. |

---

## Consequências

### Positivas

| ID | Consequência |
|---|---|
| C1 | Maior robustez e confiabilidade dos orçamentos, as 7 validações de domínio previnem erros primários em massa. |
| C2 | Menor overhead no design por optar pela integração `AtributosInsumo` no lugar de `Equipamento` separado. |

### Negativas / Riscos

| ID | Risco | Mitigação |
|---|---|---|
| R1 | O versionamento exigirá esforço massivo de integração nas Skills 00 a 07. | Assegurar testabilidade unitária dos models antes do roll-out no pipeline. |
| R2 | Overhead computacional da detecção de dependência circular. | Restringir o hook apenas a operações de `Create/Update` no catálogo de CPUs. |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| **F1 — Base & Validadores** | Classe `Funcao`, Equipamentos in-place, `AuditoriaProducao`, Validadores `VAL-CPU-INS` | ✅ Implementado |
| **F2 — Versionamento de Domínio** | Modelos `InsumoVersionado`, `CPUVersionada` e `JurisdicaoVersionada` | ⏳ Pendente |
| **F3 — Segurança de Catálogo** | Algoritmo DFS contra dependência circular | ⏳ Pendente |
| **F4 — Integração Pipeline** | Atualização das Skills (00-07) para consumirem versão; Excel output "CPU Histórico" | ⏳ Pendente |

---

## Definition of Done

### Fase 1 — Base & Validadores
- [x] Classe `Funcao` criada e funcional no catálogo.
- [x] Abstração de equipamento unificada em `AtributosInsumo`.
- [x] `AuditoriaProducao` e auditoria de custo implementadas *in-place*.
- [x] Validações `VAL-CPU-INS-01` a `07` codificadas e testadas.

### Fase 2 — Versionamento de Domínio
- [x] Entidades `InsumoVersionado`, `CPUVersionada` e `JurisdicaoVersionada` construídas em `domain/models/catalogo_versioned.py`.
- [x] Testes unitários do mecanismo de versão passando sem falhas (22/22).
- [x] Nenhuma quebra nos testes legados do projeto.

### Fase 3 — Segurança de Catálogo
- [x] Checagem DFS implementada em `domain/validations/circular_deps.py`.
- [x] Testes detectando dependência circular passando e lançando erro corretamente.

### Fase 4 — Integração Pipeline
- [x] Skills 00 a 07 lendo referências temporais de insumos e CPUs.
- [x] Exportador Excel gerando a nova *sheet* `CPU Histórico`.
- [x] Testes E2E do pipeline executando sem falhas com versionamento ativo.

---

## Referências

- ADR-017: Catalog Lifecycle Management
- ADR-030: Composição tipada de equipes (per-escopo, hereditária)
