# ADR-175 — `mesclar_catalogo`: Escrita Durável + Governança (4-Olhos/Snapshot)

**Status:** ✅ Implementado
**Data:** 2026-08-03
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-041 (SCD Type 2 de preço), ADR-120 (Regra dos Quatro Olhos), ADR-145 (Unificação do Caminho de Escrita de Preço no Catálogo Mestre), ADR-150 (Rascunho de Catálogo por Projeto — mesmo padrão de risco fechado para `promover_override_projeto`), issue #141

---

## Contexto

### Problema

P1. **Bug de durabilidade (o mais grave).** `mesclar_catalogo(dry_run=False)` (`_impl_mesclar_catalogo`, `_catalogo_tools_helpers_b.py:200-282`) escreve o resultado do merge **só no cache derivado** `.catalog_bundle.json` do destino (`bundle_path.write_text(...)`, linha 279) — nunca nos arquivos individuais por insumo/CPU/produção (`insumos/{tipo}/{codigo}.json`, `cpus/{codigo}.json`, `producoes/{id}.json`) que são a fonte de verdade real, ao contrário de **todo** o resto da infraestrutura de escrita (`_apply_criar_insumo_delta`, `_apply_preco_insumo_delta` via `RepositorioInsumo`, `_apply_cpu_override_delta`), que sempre escreve nos arquivos individuais.

P2. Consequência: `_catalog_bundle_valid` (`application/runtime/mixins/catalog.py:112-124`) invalida o cache sempre que QUALQUER arquivo individual tiver mtime ≥ mtime do bundle. A primeira vez que outra operação de catálogo tocar um arquivo individual depois do merge (ex.: `atualizar_preco_insumo` num insumo não relacionado, ou mesmo o próprio ciclo natural de invalidação), `_load_catalogo_from_disk` reconstrói o bundle inteiro a partir dos arquivos individuais (que nunca foram atualizados pelo merge) — **revertendo silenciosamente o merge, sem erro, sem aviso**. O merge não é permanente.

P3. **Bypass de governança**, mesmo padrão de risco que motivou a ADR-145 (para `atualizar_preco_insumo`) e a ADR-150 (para `catalog promote`/`promover_override_projeto`) — nenhuma das duas analisou `mesclar_catalogo`:
- Exige só `catalog:write`, não `catalog:merge` (permissão mais fraca que `aprovar_merge_catalogo`/`promover_override_projeto`).
- Sem SCD2 (`RepositorioInsumo.atualizar_preco`) — preço de insumo trocado por sobrescrita direta do campo, sem histórico append-only.
- Sem `CatalogSnapshot`/`CatalogDiff` — nenhuma trilha de auditoria do que mudou, quem mudou, por quê.
- Sem regra de quatro olhos (ADR-120) — uma única chamada, de um único ator, aplica a mudança.

O próprio código já documentava a lacuna (comentário em `_impl_mesclar_catalogo`, linha ~208-211): *"issue #134 não resolve a governança de escrita direta em catálogo, ver ADR-145"*.

P4. `mesclar_catalogo` opera sobre **bundles inteiros** (`insumos`/`producoes`/`cpus`), incluindo mudanças de CPU e produção — o sistema de `_deltas` de rascunho (ADR-145/163/164) só cobre 4 tipos (`preco_insumo`, `variante_producao`, `criacao_insumo`, `descontinuacao_insumo`); **não existe hoje nenhum delta de "criação/atualização de CPU" no catálogo mestre** (`_apply_cpu_override_delta` só existe para override de *projeto*, ADR-150, não para o master). Rotear `mesclar_catalogo` pelo sistema de deltas exigiria estendê-lo primeiro — fora de escopo proporcional a este fix.

## Decisão

D1. **Corrige a escrita para os arquivos individuais** (fecha P1/P2). Nova função `_persistir_merge_em_arquivos_individuais(catalog_root, tipo, relatorio, merged, id_key)`:
- Para cada item de `relatorio.inner_high` com `delta` (atualização): resolve o arquivo existente via `validate_and_resolve_insumo_file`/`validate_and_resolve_producao_file`/`validate_and_resolve_cpu_file` (mesmos helpers de `catalog_governance.py` já usados por `_apply_*_delta`) e sobrescreve com a entidade mesclada.
- Para cada item de `relatorio.right_only` (novo): grava um arquivo novo na convenção já estabelecida — `insumos/{tipo_lower}/{codigo}.json` (mesma de `_apply_criar_insumo_delta`), `cpus/{codigo}.json`, `producoes/{id}.json`.
- Nunca escreve `.catalog_bundle.json` diretamente — a próxima leitura via `rt.load_catalogo()` reconstrói o cache a partir dos arquivos individuais corretos (mesmo mecanismo que já serve todo o resto do sistema, incluindo o fix de empate de mtime já corrigido separadamente).

D2. **Permissão elevada**: `mesclar_catalogo` passa a exigir `catalog:merge` (não `catalog:write`) quando `dry_run=False` — mesma permissão de `aprovar_merge_catalogo`/`promover_override_projeto`. `dry_run=True` continua exigindo só `catalog:write` (ou até `catalog:read`? — decisão: mantém `catalog:write`, já que agora gera um preview persistido, uma escrita leve de metadado, não pura leitura).

D3. **Confirmação em duas etapas com quatro-olhos, sem estender o sistema de deltas** (fecha P3, considerando P4): como o merge de bundle não cabe no sistema de deltas existente (P4), a ADR introduz um mecanismo **próprio e mais leve**, mesma disciplina de `assert_pode_aprovar`/`assert_pode_promover_projeto`, mas sem os estados RASCUNHO/REVISADO completos (não há "revisão" incremental de um bundle-diff, só preview→aplicação):

- `dry_run=True` (inalterado no resultado visível) passa a **também** gerar um `merge_id` (`uuid4`) e persistir um preview em `catalogos/{catalogo_id_destino}/merges_pendentes/{merge_id}.json`: `{"destino", "origem", "tipo", "resumo", "criado_por": actor, "criado_em": isoformat}`.
- `dry_run=False` passa a **exigir** `merge_id` (novo parâmetro obrigatório para aplicar). Valida, nesta ordem:
  1. Preview existe e não expirou (TTL 24h, mesmo valor de `JOB_TTL_HOURS` usado em `pipeline.py` — consistência de convenção, não um número novo).
  2. `destino`/`origem`/`tipo` da chamada atual coincidem com os do preview (evita aplicar um preview para um par diferente do que foi revisado).
  3. Quatro olhos: `actor != preview["criado_por"]`, via `_checar_quatro_olhos` (reusada de `catalog_draft_lifecycle.py`, mesma primitiva usada por `assert_pode_aprovar`).
  4. Recomputa `gerar_relatorios` fresh e compara o `resumo` (contadores de atualização/novos/colisões) contra o persistido no preview — se divergir, rejeita pedindo um preview novo (guarda contra TOCTOU: catálogo mudou entre o preview e a aplicação).
  5. Aplica via D1, gera snapshot (D4), e apaga o arquivo de preview (estado terminal, não reutilizável).

D4. **Auditoria**: após aplicar, chama `build_and_persist_snapshot` (mesmo mecanismo de `aprovar_merge_catalogo`/`promover_override_projeto`) para gerar `CatalogSnapshot`/`CatalogDiff` persistido, com `contexto_id=destino`, `rascunho_id=merge_id` (reaproveitando o campo existente do diff record para guardar a referência do preview, já que não há um `rascunho_id` real de `ContextoVersionService` neste fluxo), `justificativa` (novo parâmetro opcional em `mesclar_catalogo`, default `"Merge de catálogo"`).

D5. **Sem SCD2 por ora** — `RepositorioInsumo.atualizar_preco()` grava histórico por-insumo (append-only) para mudanças de preço; `mesclar_catalogo` mexe potencialmente em CPUs/produções também, não só preço, então não há um único "tipo de mudança" para rotear por SCD2 sem reimplementar boa parte do `_apply_preco_insumo_delta`. **Fora de escopo desta ADR** — aceito como risco residual (fica sem histórico incremental de preço quando a mudança vem de `mesclar_catalogo`, só o snapshot completo pré/pós via D4). Documentado para revisão futura se o volume de uso de `mesclar_catalogo` para preço justificar.

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Rotear `mesclar_catalogo` pelo sistema de `_deltas` de rascunho existente (`ContextoVersionService`) | Rejeitada (P4) — o sistema de deltas não cobre criação/atualização de CPU no master; estendê-lo primeiro é uma ADR maior, desproporcional a corrigir um bug de durabilidade + gap de permissão. |
| A2 | Só corrigir a durabilidade (D1), deixar a governança (D2/D3) para depois | Rejeitada — entregar só a correção de dados sem fechar o gap de permissão/4-olhos deixaria a tool ainda mais fácil de chamar (agora com efeito duradouro) sem controle, pior do que hoje em termos de risco de uso indevido. |
| A3 | Exigir 4-olhos via dois atores humanos distintos numa aprovação síncrona (como Slack/email) | Rejeitada — não há esse mecanismo hoje para nenhuma tool MCP (nem `aprovar_merge_catalogo` tem); o padrão do repo é "actor diferente na segunda chamada", que é o que D3 replica. |
| A4 | Adicionar SCD2 completo para as mudanças de `mesclar_catalogo` | Rejeitada por ora (D5) — mudanças de CPU/produção não têm um "tipo de delta" único para rotear por SCD2 sem uma ADR própria; snapshot completo (D4) já dá trilha de auditoria pré/pós. |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Fecha bug de dados real | Merge deixa de ser uma escrita fantasma que desaparece na próxima invalidação de cache. |
| Governança em paridade com os outros dois caminhos de escrita | `mesclar_catalogo` passa a exigir `catalog:merge` + 4-olhos + snapshot, mesmo nível de `aprovar_merge_catalogo`/`promover_override_projeto`. |
| Mecanismo novo é reaproveitável | Preview com TTL + 4-olhos sem passar por rascunho de deltas é um padrão que pode servir outras tools futuras que mexam em bundle inteiro (não item a item). |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| `dry_run=False` passa a exigir 2 chamadas (preview + apply com `merge_id`) — breaking change de assinatura | Aceito — o comportamento anterior (uma chamada, sem confirmação) é exatamente o problema sendo corrigido; documentado em `Erros comuns` do tutorial. |
| Sem SCD2 (D5) | Aceito como risco residual, documentado; revisar se o uso real de `mesclar_catalogo` para preço crescer. |
| Preview persistido em disco (`merges_pendentes/`) nunca limpo automaticamente se ninguém aplicar | TTL de 24h checado na aplicação, mas arquivos expirados não são varridos proativamente — aceito (mesmo padrão de jobs em memória com TTL, `pipeline.py`, que também não faz GC proativo de tudo). |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | D1 — escrita em arquivos individuais (`_persistir_merge_em_arquivos_individuais`) | ✅ |
| F2 | D3 — preview com `merge_id` + TTL + 4-olhos + validação de consistência | ✅ |
| F3 | D2 — permissão `catalog:merge` para `dry_run=False` | ✅ |
| F4 | D4 — snapshot/diff via `build_and_persist_snapshot` | ✅ |

## Definition of Done

### Fase 1
- [x] `dry_run=False` escreve nos arquivos individuais corretos (insumo/cpu/producao), nunca no `.catalog_bundle.json`
- [x] Teste cobrindo: após o merge, uma leitura fresca via `rt.load_catalogo()` reflete o merge mesmo depois do cache ser invalidado por outra escrita não relacionada (prova a durabilidade — regressão do bug real)

### Fase 2
- [x] `dry_run=True` retorna `merge_id`; `dry_run=False` sem `merge_id` retorna erro
- [x] Teste cobrindo: mesmo ator não pode aplicar seu próprio preview (4-olhos); preview expirado (TTL) rejeitado; `destino`/`origem`/`tipo` divergentes do preview rejeitados; catálogo mudou entre preview e apply (resumo diverge) rejeitado; preview aplicado com sucesso é removido (não reaplicável)

### Fase 3
- [x] `dry_run=False` exige `catalog:merge`; `dry_run=True` continua com `catalog:write`

### Fase 4
- [x] Merge aplicado com sucesso gera `CatalogSnapshot`/`CatalogDiff` persistido, com `justificativa` gravada

## Nota de Implementação

Implementado em `_catalogo_tools_helpers_b.py` (`_impl_mesclar_catalogo` e helpers
`_persistir_merge_em_arquivos_individuais`/`_persistir_preview_merge`/
`_carregar_preview_merge`/`_validar_preview_merge`/`_apagar_preview_merge`) e no
wrapper MCP `mesclar_catalogo` (`catalogo.py`), que agora resolve `actor` via
`get_current_user_id()` e propaga `merge_id`/`justificativa`.

Um desvio do D1 literal: em vez de replicar a categorização interna de
`aplicar_merge` (percorrer `inner_high`/`right_only` separadamente),
`_persistir_merge_em_arquivos_individuais` compara o resultado final (`merged`)
diretamente contra o estado anterior (`base`) por `id_key` e escreve só o que é
novo ou mudou. Isso cobre uniformemente INNER_HIGH atualizado, RIGHT_ONLY novo
e colisões INNER_LOW reimportadas com prefixo `RFI-` sem duplicar a lógica de
`aplicar_merge` — mais robusto a mudanças futuras nesse motor.

O gate `catalog:merge` (D2) é um segundo gate inline (`require_permission`),
dentro de `_impl_mesclar_catalogo`, sobre a base do `@permission("catalog:write")`
do decorator — mesmo padrão de "gate duplo" já usado por `require_owner_or_admin`
em `promover_override_projeto` (ADR-150), já que o decorator `@permission` só
aceita uma permissão estática por tool e aqui a exigência depende de `dry_run`.

Suíte completa: 15.1xx testes, todos verdes (nenhuma regressão introduzida).

---

## Relacionados

- ADR-041 — SCD Type 2 de preço (risco residual documentado em D5)
- ADR-120 — Regra dos Quatro Olhos (`_checar_quatro_olhos` reusada em D3)
- ADR-145 — Unificação do Caminho de Escrita de Preço (mesmo padrão de risco, escopo não coberto — P3)
- ADR-150 — Rascunho de Catálogo por Projeto (mesmo padrão de risco fechado para `promover_override_projeto` — precedente direto de D3/D4)
- issue #141 — achado original desta ADR
