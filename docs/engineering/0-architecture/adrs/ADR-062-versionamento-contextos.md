# ADR-062: Versionamento Explícito de Contextos e Perfis — `ConfigVersionService`

**Status:** Implementado  
**Data:** 2026-05-18  
**Autor:** Engenheiro Sênior  
**Relacionado:** ADR-040 (Hierarquia Project Layer), ADR-023 (BDI), ADR-053 (CPU/Produtividade), ADR-056 (Débito Técnico)

---

## 1. Contexto

Esta ADR cobre o versionamento de **duas entidades de configuração**:

| Entidade | Diretório | Descrição |
|---|---|---|
| **Contexto** | `config/contextos/` | Catálogo + jurisdição + perfil + referência |
| **Perfil** | `config/perfis/` | Metas financeiras (margem, BDI, razão indireto/direto) |

Ambas compartilham a mesma lógica de versionamento via `ConfigVersionService`, com `ContextoVersionService` e `PerfilVersionService` como aliases de conveniência.

---

Um **Contexto** (`config/contextos/*.json`) é a entidade que une os quatro componentes de configuração de um projeto:

```
contexto
  ├── catalogo_id    → qual catálogo de CPUs, insumos e produtividades usar
  ├── jurisdicao_id  → qual régua de encargos, impostos e BDI padrão
  ├── perfil_id      → parâmetros financeiros (tabela BDI, regime tributário)
  └── referencia_id  → benchmark de referência (opcional)
```

Atualmente os contextos são **arquivos JSON estáticos em disco** (`config/contextos/`). Cada execução de pipeline captura um snapshot imutável do catálogo e da jurisdição no momento do run — garantindo rastreabilidade histórica dos resultados já calculados.

O problema: contextos não têm versão própria. Quando um contexto precisa mudar (atualização de catálogo, novo regime tributário, revisão de encargos), a equipe tem três opções insatisfatórias:

1. **Editar o arquivo** → todos os projetos novos usam o contexto novo; não há forma de comparar "projeto com contexto antigo vs. novo contexto"
2. **Criar novo arquivo** (`mendeslobo_v2.json`) → proliferação de arquivos sem semântica clara
3. **Recriar projetos** → perda de histórico de runs anteriores

Nenhuma delas é auditável, segura ou expressa intenção.

---

## 2. Forças em tensão

| Força | Descrição |
|---|---|
| **Rastreabilidade** | Um run armazena snapshot do catálogo/jurisdição usado — o resultado já é imutável. O problema é na _configuração pré-run_. |
| **Reutilização** | Múltiplos projetos referenciam o mesmo contexto. Versionar contextos não deve exigir duplicação por projeto. |
| **Auditoria** | A equipe precisa saber "qual versão do contexto estava em vigor quando o projeto X foi criado" e "qual mudança no contexto causou a diferença entre v3 e v4 de um projeto". |
| **Simplicidade operacional** | A equipe não pode gerenciar dezenas de arquivos de contexto manualmente. O sistema deve abstrair o versionamento. |
| **Imutabilidade de runs** | Runs anteriores não devem ser afetados por mudanças futuras no contexto — já garantido pelo snapshot atual. |

---

## 3. Decisão

### 3.1 Serviço genérico `ConfigVersionService`

O versionamento é implementado por `ConfigVersionService(config_root, subdir)` — um serviço parametrizado que funciona para qualquer entidade cujo diretório segue a convenção abaixo. Aliases:

```python
ContextoVersionService(config_root)  ≡  ConfigVersionService(config_root, "contextos")
PerfilVersionService(config_root)    ≡  ConfigVersionService(config_root, "perfis")
```

### 3.2 Modelo de dados

Introduzir o conceito de **EntidadeVersão** como entidade de primeira classe, armazenada em `config/<subdir>/<id>/`:

```
config/
  contextos/
    mendeslobo/
      contexto.json        ← metadados (nome, current_version)
      current              ← aponta para a versão ativa ("v3")
      versions/
        v1.json            ← contexto original
        v2.json            ← atualização de catálogo (2026-Q2)
        v3.json            ← reforma tributária CBS/IBS (2027)

  perfis/
    mendeslobo/
      perfil.json          ← metadados (nome, current_version)
      current              ← aponta para "v2"
      versions/
        v1.json            ← perfil original
        v2.json            ← revisão de metas de margem (2026-Q3)
```

Cada `versions/vN.json` contém os mesmos campos do contexto atual, mais metadados de versionamento:

```json
{
  "version": "v2",
  "created_at": "2026-05-18T10:30:00Z",
  "created_by": "bruno.peixoto@mendesloboconstrucao.com.br",
  "motivo": "Atualização do catálogo com CPUs de terraplanagem v2026.2",
  "catalogo_id": "mendeslobo_v2026_2",
  "jurisdicao_id": "BR-CE",
  "perfil_id": "padrao_mendeslobo_v2",
  "referencia_id": null
}
```

### 3.2 Resolução de versão por projeto

Quando um projeto é criado, o campo `contexto_version` é gravado em `meta.json`:

```json
{
  "contexto_id": "mendeslobo",
  "contexto_version": "v2",
  "criado_em": "2026-05-18T..."
}
```

O `ProjectInputBuilder` resolve `(contexto_id, contexto_version)` → contexto versionado, em vez de simplesmente `contexto_id` → arquivo estático.

### 3.3 Snapshot permanece como âncora de imutabilidade

O snapshot do catálogo/jurisdição gravado em `projetos/{uuid}/snapshots/` **não muda** — é a âncora final de imutabilidade dos runs. O versionamento de contextos adiciona uma camada de **intenção configurável** acima do snapshot:

```
Contexto v2 (intenção configurável)
  ↓ resolve para
catalogo_id = "mendeslobo_v2026_2"
  ↓ ao criar/rodar o projeto
snapshot catalogo-{hash}.json (imutável, por run)
```

### 3.4 Comparação entre versões de contexto

Uma nova operação `compare_contexts(contexto_id, vA, vB)` expõe as diferenças entre duas versões:

```json
{
  "catalogo_id": {"de": "mendeslobo_v2026_1", "para": "mendeslobo_v2026_2"},
  "perfil_id":   {"de": "padrao_mendeslobo_v1", "para": "padrao_mendeslobo_v2"}
}
```

Isso permite ao usuário entender o impacto antes de migrar projetos para um novo contexto.

### 3.5 Migração de projetos existentes

Projetos criados antes desta ADR recebem retroativamente `contexto_version: "v1"` inferido pela data de criação. O arquivo `config/contextos/mendeslobo/versions/v1.json` é gerado a partir do `mendeslobo.json` existente.

---

## 4. Consequências

### 4.1 Positivas

- **Auditabilidade completa**: cada projeto registra explicitamente qual versão de contexto estava em vigor
- **Comparação controlada**: é possível criar um run com contexto v2 e comparar com run anterior (contexto v1) do mesmo projeto, separando o impacto das mudanças de contexto dos inputs de planejamento
- **Evolução sem ruptura**: o catálogo pode evoluir sem forçar todos os projetos ativos a usar a nova versão imediatamente
- **Semântica clara**: `mendeslobo/v3` é mais expressivo que `mendeslobo_reforma_tributaria_2027_v2_final.json`

### 4.2 Negativas / Custos

- **Migração estrutural**: `config/contextos/*.json` (flat) → `config/contextos/<id>/versions/vN.json` (hierárquico) requer script de migração
- **`BenchmarkSpecLoader` e `ProjectInputBuilder`**: precisam ser atualizados para resolver a versão
- **UI `Perfis e Contextos`**: a página scaffolded na ADR-062 sprint precisa ser completada para exibir o histórico de versões
- **Compatibilidade retroativa**: projetos sem `contexto_version` em `meta.json` devem ser tratados como `v1` implícito

---

## 5. Alternativas consideradas

### 5A — Continuar com arquivos estáticos + convenção de nome
`mendeslobo_v2026_2.json`, `mendeslobo_reforma_tributaria.json`. Rejeitado: proliferação semântica nula, sem comparação automatizada, sem history.

### 5B — Git como backend de versão
Usar `git log config/contextos/mendeslobo.json` para obter histórico. Rejeitado: acopla o sistema ao Git; não funciona em ambientes SaaS ou CI/CD containerizados; não expõe versionamento via API.

### 5C — Banco de dados relacional para contextos
Tabela `context_versions(id, version, payload, created_at, author)`. Rejeitado neste estágio: introduz dependência de RDBMS sem benefício incremental suficiente sobre arquivos JSON versionados; incompatível com o modelo `config/` em disco.

---

## 6. Critérios de aceitação (Definition of Done)

### Implementado ✅

- [x] Migração: `config/contextos/*.json` → `config/contextos/<id>/versions/v1.json`
- [x] Migração: `config/perfis/*.json` → `config/perfis/<id>/versions/v1.json`
- [x] `ConfigVersionService(config_root, subdir)` — serviço genérico com aliases `ContextoVersionService` e `PerfilVersionService`
- [x] `BenchmarkSpecLoader.resolve_contexto(id, version=None)` — resolve versão versionada
- [x] `ProjectInputBuilder.prepare()` grava `contexto_version` em `meta.json`
- [x] `GET /api/contextos` e `GET /api/perfis` retornam lista com versões
- [x] `GET /api/{contextos|perfis}/{id}/versions` lista versões com metadados
- [x] `POST /api/{contextos|perfis}/{id}/versions` cria nova versão (`motivo` obrigatório)
- [x] `GET /api/{contextos|perfis}/compare?id=X&vA=v1&vB=v2` retorna diff estruturado
- [x] UI `Perfis e Contextos` com tabs Histórico / Comparar / Nova versão para ambas as entidades
- [x] Projetos sem `contexto_version` tratados como `v1` implícito (backward compat)

### Concluído na sessão de implementação ✅

- [x] Testes unitários `test_adr062_config_version_service.py` — 20+ testes cobrindo resolução, listagem, criação, comparação e backward compat
- [x] `BenchmarkSpecLoader.load_from_dict()` resolve contexto versionado via `ContextoVersionService`, merge de `catalogo_id`/`jurisdicao_id`/`perfil_id` no ref, propaga `contexto_version` e `perfil_version` no `ProjectSpec`
- [x] `ProjectInputBuilder` registra `perfil_id` e `perfil_version` além de `contexto_version` em `meta.json`
- [x] CLI `concilium context {list,versions,new-version,compare}` e `concilium perfil {list,versions,new-version,compare}`

### Pendente (decisão arquitetural futura)

- [ ] Decidir se o `contexto_id` deve ser obrigatório na `referencia.json` ou continuar com default `"mendeslobo"`
- [ ] Estratégia de propagação de mudanças de contexto para projetos existentes (notificação vs. migração automática)

---

## 7. Dependências de implementação

```
ADR-062 (esta)
  ├── Migração estrutural de config/contextos/     [pré-requisito]
  ├── BenchmarkSpecLoader update                   [sprint dedicada]
  ├── ProjectInputBuilder update                   [sprint dedicada]
  ├── API endpoints /contextos/*                   [sprint dedicada]
  └── UI Perfis e Contextos (scaffolded ADR-062)  [sprint dedicada]
```

A página `perfis_contextos_page.py` scaffolded durante a implementação da nota arquitetural serve como ponto de entrada para a UI desta ADR.

