# ADR-163 — CRUD de Insumo no Catálogo Mestre via MCP

**Status:** ✅ Implementado
**Data:** 2026-07-28
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-025 (MCP Catalog & Tax Reference Policy), ADR-037 (MCP Facade: Micro → Macro-Ferramentas), ADR-041 (SCD Type 2), ADR-092 (Formulário QQP/EAP), ADR-099 (RBAC — Roles e Permissões), ADR-116 (Limpeza da Superfície de Tools MCP — teto), ADR-120 (Catalog RBAC Lifecycle), ADR-145 (Unificação do Caminho de Escrita de Preço no Catálogo Mestre)

---

## Contexto

### Problema

Um agente, ao tentar resolver via chat MCP um lote de 54 anomalias de plausibilidade (E0001–E0054, `auditar_catalogo(plausibilidade)`), reportou bloqueio real em dois pontos: não conseguia identificar de forma confiável a quais insumos as anomalias se referiam, e mesmo tendo pesquisado valores de mercado manualmente, não havia caminho de escrita para persistir o achado. Investigação confirmou 5 lacunas concretas na superfície MCP atual de catálogo (`presentation/mcp/tools/catalogo.py`, 17 tools registradas). Ao generalizar o achado (a pedido do usuário — "é basicamente um CRUD de catálogo"), confirmou-se que a superfície de **insumo** hoje cobre apenas fração de Read e de Update — Create e Delete são completamente inexistentes:

| Operação | Estado atual antes desta ADR |
|---|---|
| **C**reate | Inexistente — nenhuma tool para adicionar insumo novo ao catálogo mestre |
| **R**ead (lista/busca) | Inexistente — P1/P4 abaixo |
| **R**ead (detalhe) | Parcial — só se o `insumo_id` já for conhecido (`historico_preco_insumo`) |
| **U**pdate | Parcial — só `preco_unitario` (`atualizar_preco_insumo`) — P5 abaixo |
| **D**elete | Inexistente — nenhuma tool para remover/descontinuar insumo |

P1. Não existe tool para listar/buscar insumos por id+descrição sem já conhecer o id. `pesquisar_catalogo` (`catalogo.py:68-74`, implementada por `_buscar_cpus_por_texto`, `_catalogo_tools_helpers_a.py:78-95`) busca exclusivamente `catalogo.get("cpus", [])`. Toda tool que recebe `insumo_id` (`atualizar_preco_insumo`, `historico_preco_insumo`) assume que o chamador já o conhece — não há ponto de entrada para descobri-lo.

P2. `auditar_catalogo(plausibilidade)` inclui `"descricao"` no `detalhe` das anomalias tipo `ESTATISTICO` (`_pc_eq_zscore`/`_pc_mo_zscore`, `application/catalog/_plausibility_checks.py:234-250`) mas omite o mesmo campo nas anomalias tipo `INCOMPLETO` — especificamente `_pc_eq_locacao` (linhas 253-267), que só retorna `{"preco_h": ...}`. Um agente recebendo um lote de anomalias `INCOMPLETO` não consegue identificar de qual equipamento se trata sem uma segunda chamada (que não existe — P1).

P3. `calcular_pu_producao` (`catalogo.py:242-250`, via `calcular_pu`, `application/catalog/pu_calculator.py:250-272`) retorna só totais agregados por categoria (`BreakdownPU.to_dict()`: `mo`/`equipamento`/`diesel`/`material`/`total_h`). Já existe uma função irmã, `calcular_pu_composicao_itens` (linhas 162-204), que produz breakdown item-a-item — mas ela cobre apenas `composicao_itens` (material/diesel fixo de CPU volumétrica), nunca a composição de equipe (`funcoes`/`equipamentos`) que `calcular_pu` calcula. Não há visibilidade de quanto cada insumo de equipe contribui ao PU final.

P4. Mesma raiz de P1: `_buscar_cpus_por_texto` (linha 81) itera apenas `catalogo.get("cpus", [])`, nunca `catalogo.get("insumos", [])`. Uma busca textual por descrição de insumo (ex.: "Gerente de Contrato") ou por código de equipamento não retorna nada.

P5. `atualizar_preco_insumo` (`catalogo.py:132-143`, `_impl_atualizar_preco_insumo`, `_catalogo_tools_helpers_a.py:311+`) só aceita `novo_preco`. O modelo já tem `AtributosInsumo.valor_locacao_mensal` (`domain/models/catalog/catalogo.py:157`), lido por `_pc_eq_locacao` (P2) e hoje **só gravado por uma rotina de cura em lote** (`cure_plausibility.py:320-333`, que deriva `preco_unitario × horas_mes` como estimativa) — nenhuma tool MCP permite setá-lo diretamente com um valor de mercado real coletado por pesquisa.

P6. Não existe caminho MCP para **criar** um insumo novo. Um insumo que aparece pela primeira vez numa pesquisa de mercado (ex.: um equipamento ainda não catalogado) não tem como entrar no catálogo mestre via chat — hoje isso exige edição manual de arquivo (`config/catalogos/{catalogo_id}/insumos/{tipo}/{codigo}.json`, um arquivo por insumo, confirmado em `validate_and_resolve_insumo_file`, `application/orchestrators/catalog_governance.py:38-44`, que resolve por `rglob(f"{insumo_id}.json")`).

P7. Não existe caminho MCP para **remover/descontinuar** um insumo. `Insumo` (`domain/models/catalog/catalogo.py:173-206`) não tem nenhum campo de status (`ativo`/`descontinuado`) — um insumo obsoleto permanece indefinidamente em `listar_insumos`/buscas, sem forma de sinalizar que não deve mais ser usado em CPU nova.

### Por que o caminho de contorno não é confiável

A tool `exportar_pesquisa_mercado` (`catalogo.py:723-805`) já traz `descricao` por insumo — mas em um `.xlsx` codificado em base64, cujo propósito declarado é "envio a fornecedores" (documento para preenchimento humano, ADR-092/037), não leitura estruturada pelo próprio agente. Na tentativa relatada, o agente teve que retranscrever manualmente um blob de ~11KB para decodificá-lo, corrompendo o arquivo duas vezes — confirma que esse não é um caminho viável para um agente identificar insumos, apenas para gerar um documento de cotação para terceiros.

## Decisão

D1. Nova tool MCP `listar_insumos(contexto_id, tipo=None, query=None, limite=50, offset=0)` — retorna `insumo_id`, `descricao`, `tipo`, `categoria`, `unidade`, `preco_unitario` e, quando `tipo == "EQUIPAMENTO"`, `valor_locacao_mensal`, paginado. Generaliza o padrão de busca textual case-insensitive já usado por `_buscar_cpus_por_texto` para o domínio de insumos, com filtro opcional por `tipo` (`MATERIAL`/`MAO_OBRA`/`EQUIPAMENTO`). Fecha P1 e P4 numa única tool nova — `pesquisar_catalogo` permanece focada em CPU/EAP (consistente com sua descrição atual), evitando crescer o teto de tools do ADR-116 com duas ferramentas quando uma resolve os dois problemas.

D2. `_pc_eq_locacao` (`_plausibility_checks.py:253-267`) passa a incluir `"descricao": ins.get("descricao", "")` no `detalhe` da anomalia `INCOMPLETO`, no mesmo padrão já usado por `_pc_eq_zscore`/`_pc_mo_zscore`. Fecha P2.

D3. `BreakdownPU` (`pu_calculator.py:93-135`) ganha um campo `itens: list[dict]` (default `[]`), populado por `_acumular_custo_mo`/`_acumular_custo_equipamentos`/`_acumular_custo_materiais` com um dict por insumo (`insumo_id`, `categoria`, `preco_ou_salario`, `quantidade`, `contribuicao_h`), no mesmo formato de `calcular_pu_composicao_itens`. `calcular_pu_producao` ganha parâmetro opcional `detalhado: bool = False`; quando `True`, a resposta inclui `"itens"`. Default `False` preserva o formato de resposta atual para consumidores existentes (ex.: `catalog_excel.py::_cex_build_cpu_row`, chamado em laço por CPU). Fecha P3.

D4. `atualizar_preco_insumo` ganha parâmetro opcional `novo_valor_locacao_mensal: float | None = None`. Segue exatamente o mesmo caminho gated por rascunho estabelecido pela ADR-145 (D1/D2): quando informado, `_append_delta_to_rascunho` grava um delta adicional (`valor_locacao_mensal_anterior`/`valor_locacao_mensal_novo`) e uma extensão de `_apply_preco_insumo_delta` grava `atributos_especificos.valor_locacao_mensal` no insumo master no momento do merge (`aprovar_merge_catalogo`), nunca direto no master — mesma disciplina de quatro-olhos (ADR-120) e nota append-only (ADR-145 D4). Pelo menos um entre `novo_preco`/`novo_valor_locacao_mensal` deve ser informado por chamada. Fecha P5 sem reabrir o bypass de governança que a ADR-145 fechou.

D5. Nova tool MCP `criar_insumo(contexto_id, rascunho_id, codigo, tipo, descricao, unidade, preco_unitario, categoria, fonte_preco, atributos_especificos=None)` — cobre o **Create**. Mesma disciplina de D4: grava um delta `{"acao": "criacao", "insumo": {...}}` no rascunho (nunca no master); `aprovar_merge_catalogo` cria o arquivo `insumos/{tipo_dir}/{codigo}.json` no momento do merge, validado contra o schema `Insumo` (`domain/models/catalog/catalogo.py:173-206`, incluindo o padrão `^[A-Z0-9-]{3,40}$` de `codigo` e a restrição de `origem_material` a `tipo == MATERIAL`). Bloqueia se `codigo` já existir (mesma checagem de unicidade, invertida, de `validate_and_resolve_insumo_file`). Fecha P6.

D6. Novo campo `Insumo.status: Literal["ativo", "descontinuado"] = "ativo"` (default preserva retrocompatibilidade de todo catálogo existente) e nova tool MCP `descontinuar_insumo(contexto_id, rascunho_id, insumo_id, motivo)` — cobre o **Delete** como *soft delete*, nunca remoção física do arquivo. Remoção física quebraria a fidelidade retroativa de qualquer `resolved_catalog.json` (ADR-066) ou `CatalogSnapshot` (ADR-024) já congelado que referencie o `insumo_id`. Mesmo caminho gated por rascunho/merge de D4/D5. `listar_insumos` (D1) exclui `descontinuado` por padrão, com `incluir_descontinuados: bool = False` para expor o histórico completo quando necessário. Fecha P7.

D7. **[Emenda]** Decisão revisada — não apenas as tools novas, mas o próprio mapeamento `ROLE_PERMISSIONS` (`permission_guard.py:75-92`) muda. Decisão do usuário: escopo de `engineer` deve ficar restrito a domínio **projeto**; domínio **catálogo** (escrever/aprovar) fica exclusivo de `catalog-manager` (e `admin`). Isso reverte conscientemente a decisão da ADR-120 §D3 ("`engineer` mantém `catalog:write`") e da ADR-099 §D3 original (que primeiro concedeu `catalog:write` a `engineer`, antes de `catalog-manager` existir).

```python
# Antes                                              # Depois
_ENGINEER = _OPERATOR | frozenset(                    _ENGINEER = _OPERATOR | frozenset({PROJECT_APPROVE})
    {PROJECT_APPROVE, CATALOG_WRITE}
)
_ADMIN = _ENGINEER | frozenset(                       _ADMIN = _ENGINEER | frozenset(
    {AUTH_MANAGE, SYSTEM_READ, CATALOG_MERGE}             {AUTH_MANAGE, SYSTEM_READ, CATALOG_MERGE, CATALOG_WRITE}
)                                                      )
```

**Detalhe crítico de implementação:** `_ADMIN` hoje é definido como `_ENGINEER | {...}` — herda de `_ENGINEER` por composição de frozenset, não por permissão nomeada. Remover `CATALOG_WRITE` de `_ENGINEER` sem adicioná-la explicitamente a `_ADMIN` removeria silenciosamente o acesso de escrita de catálogo do próprio `admin` (uma regressão grave, não intencional). A correção acima adiciona `CATALOG_WRITE` de volta explicitamente no frozenset de `_ADMIN`.

`engineer` mantém `catalog:read`/`catalog:validate` (herdados de `_OPERATOR`, inalterados) — continua podendo **consultar** o catálogo para uso em projetos (orçamento, composição de CPU), só não pode mais **propor mudança** no catálogo mestre. `catalog-manager` não é afetado (seu frozenset já declara `CATALOG_WRITE`/`CATALOG_MERGE` diretamente, sem herdar de `_ENGINEER`).

**Composição por múltiplos roles já suporta o caso combinado** — nenhum código novo é necessário: `get_permissions(roles: list[str])` (`permission_guard.py`) já faz união de permissões sobre todos os roles do token. Um usuário com `roles=["engineer", "catalog-manager"]` (o "engenheiro com adicionalmente papel de cat-manager" do pedido) já recebe `catalog:write`/`catalog:merge` via o componente `catalog-manager`, e `project:*` via o componente `engineer` — esse padrão de composição já está documentado como mitigação na própria ADR-120 ("Role pode ser combinado: um user pode ter `engineer` + `catalog-manager`", linha 159).

Permissões das tools desta ADR (D1-D6), com o mapeamento já revisado:

| Tool | Decorator | Quem tem, pós-emenda |
|---|---|---|
| `listar_insumos` (D1) | `@permission("catalog:read")` | operator, engineer, admin, catalog-manager (mesma de `pesquisar_catalogo`/`listar_contextos`) — leitura não muda |
| `calcular_pu_producao(detalhado=...)` (D3) | `@permission("catalog:read")` — decorator existente, sem mudança | idem |
| `atualizar_preco_insumo(novo_valor_locacao_mensal=...)` (D4) | `@permission("catalog:write")` — decorator existente, sem mudança | **admin, catalog-manager** propõem e aprovam; `engineer` deixa de conseguir propor (mudança de comportamento vs. hoje) |
| `criar_insumo` (D5) | `@permission("catalog:write")` | admin, catalog-manager |
| `descontinuar_insumo` (D6) | `@permission("catalog:write")` | admin, catalog-manager |

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Estender `pesquisar_catalogo` para também buscar insumos, em vez de criar `listar_insumos` | Sua descrição/contrato atual é explicitamente "busca CPUs"; sobrecarregar a semântica e o formato de `busca_resultados` (hoje sempre lista de CPU) quebraria o contrato de resposta para consumidores existentes. |
| A2 | Tool dedicada `atualizar_valor_locacao_mensal` em vez de parâmetro em `atualizar_preco_insumo` | Duplicaria toda a lógica de rascunho/delta/merge já existente para um campo que é semanticamente "outro atributo de custo do mesmo insumo"; parâmetro opcional é consistente com como `nota`/`jurisdicao_id` já convivem na mesma tool. |
| A3 | Fazer `exportar_pesquisa_mercado` devolver também um JSON estruturado (id+descrição+preço), para leitura direta por agente | Fora do escopo mínimo — `listar_insumos` (D1) já cobre a necessidade de identificação sem exigir parsing de planilha/base64; mantém `exportar_pesquisa_mercado` focada em seu propósito original (documento para fornecedor humano). |
| A4 | `calcular_pu_producao` sempre retornar `itens`, sem flag `detalhado` | Aumentaria o payload de toda chamada existente (função chamada em laço por CPU em vários fluxos) sem necessidade na maioria dos casos; opt-in evita regressão de payload/performance. |
| A5 | `remover_insumo` como remoção física do arquivo (hard delete) | Quebra fidelidade retroativa: qualquer `resolved_catalog.json` (ADR-066) ou `CatalogSnapshot`/`CatalogDiff` (ADR-024) já gerado antes da remoção ficaria com uma referência pendurada, e `preco_na_data()` (ADR-041) perderia a capacidade de responder por um insumo historicamente válido. Soft delete (D6) preserva a mesma garantia de fidelidade temporal que a ADR-145 já estabeleceu para preço. |
| A6 | Bloquear `descontinuar_insumo` se alguma CPU ainda referenciar o insumo, em vez de só descontinuar e deixar o achado para a auditoria de plausibilidade | Bloquear exigiria uma varredura completa de todas as CPUs do catálogo a cada chamada (custo O(cpus×composição) síncrono na escrita) para um caso que já tem rede de segurança equivalente: `_pc_check_equipe_refs`/`auditar_catalogo` já audita referências; estender esse mesmo mecanismo para also achar CPUs ativas que referenciam insumo `descontinuado` é aditivo e assíncrono, sem travar a escrita. |
| A7 | Nova permissão dedicada (ex. `catalog:write-insumo-lifecycle`) restringindo `criar_insumo`/`descontinuar_insumo` a só admin+catalog-manager, distinta de `catalog:write`, mantendo `engineer` com `catalog:write` genérico | Superada pela emenda de D7 — com `catalog:write` removida de `engineer` por completo, não há mais necessidade de uma segunda permissão só para as operações estruturais; `catalog:write` já significa "domínio catálogo", exclusivo de catalog-manager/admin. |
| A8 (revisão) | Manter `catalog:write` em `engineer` (política original desta ADR, revista após o pedido do usuário) | Rejeitada — o usuário decidiu explicitamente que o escopo de `engineer` deve ficar restrito a domínio projeto; `catalog:write`/`catalog:merge` ficam exclusivos de `catalog-manager`/`admin`, com o caso combinado coberto por multi-role (`engineer`+`catalog-manager`), sem necessidade de lógica nova. |

**Impacto em código já em produção (fora do escopo de D1-D6, mas necessário para D7):** a emenda muda o comportamento de tools já implementadas e em uso — `atualizar_preco_insumo`, `adicionar_variante_producao` e `criar_rascunho_catalogo` (todas `@permission("catalog:write")`, ADR-145/ADR-120) deixam de aceitar o role `engineer` sozinho. Teste de regressão existente `test_engineer_still_has_catalog_write` (`tests/unit/infrastructure/auth/test_adr120_catalog_rbac.py:77-80`) precisa ser invertido para `test_engineer_no_longer_has_catalog_write` como parte desta mudança — é uma reversão consciente de uma asserção que documentava a decisão anterior (ADR-120 §D3), não uma regressão a evitar.

`test_catalog_draft_lifecycle.py` (`TestAssertPodePromoverProjeto`, linhas 318-384) usa `promotor_roles=["engineer"]` em vários casos, mas **não é afetado** — `assert_pode_promover_projeto` (`application/orchestrators/catalog_draft_lifecycle.py:207-236`) testa só ownership (`require_owner_or_admin`) e quatro-olhos (`_checar_quatro_olhos`); a checagem de `catalog:merge` em si acontece antes, no decorator `@permission` do tool MCP (`promover_override_projeto`, ADR-150), não nesta função. `engineer` ali é só um role não-admin qualquer, usado para testar o caminho de ownership — não exercita `catalog:write`.

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Fluxo de anomalias fecha via chat | Um agente consegue identificar, pesquisar, criar, corrigir e descontinuar insumos sem exportar/reimportar planilha manualmente. |
| `valor_locacao_mensal` ganha trilha de auditoria | Deixa de depender só da derivação automática em lote (`preco × horas_mes`); pode refletir cotação de mercado real, com a mesma disciplina de quatro-olhos/histórico do preço (ADR-145). |
| CRUD completo com uma única disciplina de governança | Create/Update/Delete de insumo (D4-D6) reaproveitam o mesmo caminho rascunho→merge da ADR-145 — nenhum mecanismo de escrita paralelo novo. |
| Crescimento mínimo de superfície | Três tools novas (`listar_insumos`, `criar_insumo`, `descontinuar_insumo`), cobrindo C+R+D; U estende uma tool existente — teto do ADR-116 cresce em 3, não em 4 tools + 1 parâmetro solto. |
| Separação clara de domínio (D7) | `engineer` = domínio projeto; `catalog-manager`/`admin` = domínio catálogo. Reduz blast radius de uma credencial `engineer` comprometida (não escreve mais catálogo mestre) e reflete a divisão de responsabilidade real da organização. |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| `listar_insumos` sobre o catálogo atual (557 insumos) usa paginação client-side ingênua (list slice), O(n) por chamada | Aceitável na escala atual (mesma abordagem simples de `_buscar_cpus_por_texto`); revisitar com um índice dedicado se o catálogo crescer uma ordem de grandeza. |
| Delta duplo (preço + locação mensal) no mesmo rascunho aumenta a superfície de `_apply_preco_insumo_delta` | Exigir teste explícito para "só locação, sem preço" e "os dois no mesmo delta". |
| `itens` em `BreakdownPU` expõe a composição de equipe em granularidade antes só agregada | `BreakdownPU` opera sobre o índice de catálogo (dado de referência), não sobre roster real de projeto (ADR-154/155) — nenhum dado de contrato individual é exposto. |
| `descontinuar_insumo` não impede que uma CPU continue referenciando o insumo (D6/A6) | `auditar_catalogo` ganha checagem adicional (referência ativa a insumo `descontinuado`) — ver Fase 6; até lá, é uma lacuna conhecida e documentada, não silenciosa. |
| `criar_insumo` permite duplicar `descricao`/dados próximos de um insumo já existente (sem dedup semântico, só por `codigo`) | Aceito por design — mesmo padrão de `pesquisar_catalogo`/catálogo hoje, que não tem dedup automático; `listar_insumos` (D1) com busca textual mitiga na prática (agente vê o item parecido antes de criar). |
| Remover `CATALOG_WRITE` de `_ENGINEER` sem adicioná-la explicitamente a `_ADMIN` removeria silenciosamente o acesso de escrita do próprio `admin` (herança via frozenset) | Correção já especificada em D7 (`_ADMIN` ganha `CATALOG_WRITE` explícito); DoD Fase 7 exige teste de regressão dedicado. |
| Usuários hoje com role só `engineer` perdem, sem aviso prévio, a capacidade de propor mudança de catálogo mestre | Comunicar a mudança antes do deploy; quem precisa de ambos os domínios recebe o segundo role (`catalog-manager`) — mecanismo de composição já existente, sem necessidade de novo tipo de conta. |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `listar_insumos` (D1) | ✅ Implementado |
| F2 | `descricao` em `_pc_eq_locacao` (D2) | ✅ Implementado |
| F3 | `itens` em `BreakdownPU` + `detalhado` em `calcular_pu_producao` (D3) | ✅ Implementado |
| F4 | `novo_valor_locacao_mensal` em `atualizar_preco_insumo`, gated por rascunho (D4) | ✅ Implementado |
| F5 | `criar_insumo`, gated por rascunho (D5) | ✅ Implementado |
| F6 | `Insumo.status` + `descontinuar_insumo`, gated por rascunho; `listar_insumos` ganha `incluir_descontinuados` (D6) | ✅ Implementado |
| F7 | Decorators `@permission` aplicados conforme D7 (`catalog:read` em D1/D3, `catalog:write` em D4/D5/D6); `CATALOG_WRITE` removida de `_ENGINEER` e adicionada explicitamente a `_ADMIN` | ✅ Implementado |

## Definition of Done

### Fase 1
- [x] `listar_insumos` registrada com permissão `catalog:read`, paginação (`limite`/`offset`) e filtro opcional `tipo`/`query`
- [x] Teste cobrindo: busca por `query` retorna insumo correto por descrição parcial e por código

### Fase 2
- [x] `_pc_eq_locacao` inclui `descricao` no `detalhe`
- [x] Teste cobrindo: anomalia `INCOMPLETO` de equipamento sem `valor_locacao_mensal` inclui `descricao` no `detalhe`

### Fase 3
- [x] `BreakdownPU.itens` populado por `_acumular_custo_mo`/`_acumular_custo_equipamentos`/`_acumular_custo_materiais`
- [x] `calcular_pu_producao(detalhado=True)` inclui `"itens"`; `detalhado=False` (default) mantém formato de resposta idêntico ao atual
- [x] Teste cobrindo: soma de `contribuicao_h` de `itens` bate com `custo_total_h` agregado

### Fase 4
- [x] `atualizar_preco_insumo` aceita `novo_valor_locacao_mensal` opcional; delta gravado no rascunho (nunca direto no master)
- [x] `aprovar_merge_catalogo` aplica o delta de `valor_locacao_mensal` no merge, com nota append-only (ADR-145 D4)
- [x] Teste cobrindo: rascunho rejeitado após alteração de `valor_locacao_mensal` → catálogo mestre permanece inalterado (mesmo padrão de teste do ADR-145)
- [x] Teste cobrindo: chamada sem `novo_preco` nem `novo_valor_locacao_mensal` retorna erro de validação

### Fase 5
- [x] `criar_insumo` valida `codigo` inexistente antes de aceitar o delta; grava `{"acao": "criacao", "insumo": {...}}` no rascunho
- [x] `aprovar_merge_catalogo` cria o arquivo `insumos/{tipo_dir}/{codigo}.json` validado contra o schema `Insumo` no momento do merge
- [x] Teste cobrindo: `criar_insumo` com `codigo` já existente retorna erro sem tocar o rascunho; rascunho rejeitado após `criar_insumo` → arquivo não é criado no master

### Fase 6
- [x] `Insumo.status` default `"ativo"`; todo catálogo existente carrega sem alteração (retrocompatibilidade)
- [x] `descontinuar_insumo` grava delta `{"acao": "descontinuacao", "insumo_id", "motivo"}`; `aprovar_merge_catalogo` seta `status="descontinuado"` no arquivo master (nunca remove o arquivo)
- [x] `listar_insumos` exclui `status="descontinuado"` por padrão; `incluir_descontinuados=True` os inclui
- [x] Teste cobrindo: insumo descontinuado nunca é fisicamente removido; segue resolvível por `insumo_id` para CPUs históricas/snapshots antigos

### Fase 7
- [x] `listar_insumos`/`calcular_pu_producao` decoradas com `@permission("catalog:read")`; `criar_insumo`/`descontinuar_insumo` cobertos por `@permission("catalog:write")` (mesmo decorator de `atualizar_preco_insumo`)
- [x] `_ENGINEER` (`permission_guard.py`) perde `CATALOG_WRITE`; `_ADMIN` ganha `CATALOG_WRITE` explicitamente (não mais só por herança de `_ENGINEER`)
- [x] `test_engineer_still_has_catalog_write` (`tests/unit/infrastructure/auth/test_adr120_catalog_rbac.py:77-80`) invertido para `test_engineer_no_longer_has_catalog_write`, asserindo `"catalog:write" not in ROLE_PERMISSIONS["engineer"]`
- [x] Teste novo: `"catalog:write" in ROLE_PERMISSIONS["admin"]` continua verdadeiro após a mudança (guarda de regressão contra a herança silenciosa)
- [x] Teste novo: `get_permissions(["engineer"])` não contém `catalog:write`; `get_permissions(["engineer", "catalog-manager"])` contém `catalog:write` e `catalog:merge` (composição multi-role já suportada, sem código novo)
- [x] Teste RBAC de tool cobrindo: role `engineer` (sozinho) recebe erro de permissão ao chamar `atualizar_preco_insumo`/`criar_insumo`/`descontinuar_insumo`/`adicionar_variante_producao`/`criar_rascunho_catalogo`; role `catalog-manager` e `admin` continuam permitidos

## Nota de Implementação

Implementada via TDD (teste vermelho → código verde) em 7 commits, um por fase, na ordem F7→F1→F2→F3→F4→F5→F6 (`d5f1a314`..`160b1493`; `d5f1a314` em si é um fix de performance não relacionado — reuso de `openpyxl.Font` no export Excel — encontrado e corrigido antes da ADR nesta mesma sessão). Suíte completa do repositório (14727 testes) verde após a implementação, sem regressões fora do escopo desta ADR.

---

## Relacionados

- ADR-024 — Referências em Planilha Editável com Snapshot Auditável (fidelidade retroativa que motiva soft delete em D6, em vez de remoção física)
- ADR-041 — SCD Type 2 (mecanismo de histórico reaproveitado para `valor_locacao_mensal`, se estendido em fase futura; também garante `preco_na_data()` para insumo descontinuado)
- ADR-066 — Catalog Overlay Model (fidelidade de `resolved_catalog.json` que D6 preserva ao nunca remover fisicamente um insumo)
- ADR-092 — Formulário QQP/EAP (contexto de por que `exportar_pesquisa_mercado` é documento humano, não canal de leitura de agente)
- ADR-099 — RBAC: Roles e Permissões (**emendada por D7** — §D3/D5 originais concediam `catalog:write` a `engineer`; esta ADR remove, restringindo `engineer` a domínio projeto)
- ADR-116 — Limpeza da Superfície de Tools MCP (teto de tools — esta ADR soma 3 tools novas, cobrindo C+R+D de insumo)
- ADR-120 — Catalog RBAC Lifecycle (**emendada por D7** — §D3 "`engineer` mantém `catalog:write`" e a tabela de remapeamento de roles são revertidas; princípio de quatro-olhos entre `catalog:write`/`catalog:merge` permanece, só que `catalog:write` deixa de incluir `engineer`)
- ADR-145 — Unificação do Caminho de Escrita de Preço no Catálogo Mestre (D4-D6 estendem o mesmo caminho gated por rascunho/merge para locação mensal, criação e descontinuação — nenhum mecanismo de escrita paralelo novo)
