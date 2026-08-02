# ADR-174 — Cubo de Roster Real: Custo por Instância (Categoria/Grupo/Instância)

**Status:** Proposta
**Data:** 2026-08-02
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-086 (Cubo Pool Instancial), ADR-128 F6 (Cubo de Estoque Consumível — precedente de cubo-irmão), ADR-154/155 (Roster Real MO/EQ), ADR-173 (Roster Real Persistido por Escopo + `custo_semanal_individual_mo`/`_eq`, D13)

---

## Contexto

### Problema

P1. ADR-173 D13 entregou `custo_semanal_individual_mo`/`custo_semanal_individual_eq` — lista de custo por semana (direto+indireto para MO, só direto para EQ) por indivíduo/ativo real, cuja soma é o custo total de permanência da instância no pool. Nenhum cubo analítico hoje consome essa granularidade.

P2. Os cubos analíticos existentes (`CuboPoolInstancial`, ADR-086) operam no grão de **slot fungível do pool** (`instancia_numero`), nunca por `individuo_id`/`ativo_id` real — misturar as duas noções de "instância" no mesmo cubo borraria a separação física/causal que é a razão de ser da ADR-086 (H4). `cubo_pool_real.py` (ADR-160) está mais próximo em espírito, mas amarrado a slots de pool + taxa "sombra" recalculada, não ao custo do indivíduo específico.

P3. Precedente direto: `CuboEstoqueConsumivel` (ADR-128 F6) resolveu um problema estrutural análogo — grão que não cabia no `CuboPoolInstancial` — criando um **cubo-irmão**, não fundindo. Mesmo padrão se aplica aqui.

P4. Achado durante o levantamento: `Escopo.roster_mo` (ADR-173) é persistido, mas **não existe `Escopo.roster_eq`** — o roster real de equipamento (`AtivoEquipamentoReal`, ADR-155) nunca foi persistido em lugar nenhum, permanece no mesmo estado transiente que a ADR-160 originalmente impôs a ambos. Sem isso, o lado `EQUIPAMENTO` do novo cubo nunca teria dado real para consumir.

P5. O padrão de acesso dos cubos-irmãos existentes (`CuboEstoqueConsumivelBuilder.build(canonical_in, ...)`) lê exclusivamente do `CanonicalModel` — porque o dado de entrada (`recursos_consumiveis`) é escrito no canonical por uma skill (04). Roster (ADR-160 D1/ADR-173 D1) é, por decisão deliberada, **nunca** persistido no canonical — vive só em `Escopo`. O builder deste cubo não pode seguir o mesmo padrão de "só canonical"; precisa também do `Escopo` (via `repository.get_project(project_id).escopo(escopo_id)`, já usado por `gerir_escopo`).

## Decisão

D1. Novo cubo-irmão `CuboRosterReal` (`domain/models/analytics/cubo_roster_real.py`), `@dataclass(frozen=True)`, mesmo padrão de `CuboEstoqueConsumivel`:
- `CelulaRosterReal`: `categoria: Literal["MAO_OBRA","EQUIPAMENTO"]`, `grupo_id: str` (funcao_id/equip_id), `instancia_id: str` (individuo_id/ativo_id), `semana_iso: str`, `custo_direto: float`, `custo_indireto: float` (sempre `0.0` para `EQUIPAMENTO` — não é campo omitido, é medida presente e zerada, para manter célula uniforme entre categorias), `custo_total: float`.
- `CuboRosterReal`: `projeto_id`, `gerado_em`, `celulas: tuple[CelulaRosterReal, ...]`. Mesmas primitivas de query (`slice(**filtros)`, `group_by(*dims, measure=...)`) + projeções de conveniência (`custo_por_instancia`, `custo_por_grupo`, `custo_por_categoria`, `custo_total_geral`).

D2. **Fecha a assimetria MO/EQ (P4)**: `Escopo.roster_eq: list[AtivoEquipamentoReal] = Field(default_factory=list)` — mesmo padrão de `roster_mo` (ADR-173 D2), mesma persistência (`EscopoStore`/`ProjectStore.create_escopo`), mesma ação incremental em `gerir_escopo` (`acao="editar_roster_eq"`, merge por `ativo_id`, nunca remove).

D3. `CuboRosterRealBuilder.build(canonical_in, roster_mo, roster_eq, catalogo, *, gerado_em="") -> CuboRosterReal` (`application/services/analytics/cubo_roster_real_builder.py`) — mora em `application/` (não `domain/services/analytics/`) pela mesma razão documentada em `CuboEstoqueConsumivelBuilder`: depende de `domain/services/financial/roster_custo_mo.py`/`roster_custo_equipamento.py`, que por sua vez é `domain/`, então na verdade poderia morar em `domain/services/analytics/` — mas segue `application/` por consistência de onde os OUTROS builders de cubo residem nesta versão do repo, e porque recebe `roster_mo`/`roster_eq`/`catalogo` como parâmetros explícitos (não lidos de canonical), espelhando a assinatura de builders que já tomam múltiplas fontes.

Usa `canonical_in.projeto.data_inicio`/`data_termino` (convertidas a semana ISO) como span — mesma convenção de todo o resto da cadeia ADR-154→173 (span explícito, nunca `date.today()`). Para cada `membro` em `roster_mo`: chama `custo_semanal_individual_mo(membro, semana_inicio, semana_fim, catalogo)`, mapeia cada item para `CelulaRosterReal(categoria="MAO_OBRA", grupo_id=membro.funcao_id, instancia_id=membro.individuo_id, ...)`. Para cada `ativo` em `roster_eq`: `custo_semanal_individual_eq(ativo, semana_inicio, semana_fim)`, mapeia para `CelulaRosterReal(categoria="EQUIPAMENTO", grupo_id=ativo.equip_id, instancia_id=ativo.ativo_id, custo_indireto=0.0, ...)`. Roster vazio (ou ambos vazios) → `celulas=()`, sem erro (degradação segura, mesmo padrão de `CuboEstoqueConsumivelBuilder`).

D4. Projeção `resolve_cubo_roster_real_projection(canonical_in, roster_mo, roster_eq, catalogo, *, face="resumo_por_instancia", granularidade="mes", top_n=300, categoria=None, grupo_id=None, instancia_id=None, gerado_em="") -> dict` (`application/services/analytics/cubo_roster_real_projection/_dispatch.py`), mesmo contrato de retorno dos cubos-irmãos (`version`, `face`, `columns`, `rows`, `narrativa`, `operator_meta`, `totais`, `invariantes_ok`, `filtros_aplicados`). Faces:
- `resumo_por_instancia` (default) — uma linha por `instancia_id`, com `categoria`/`grupo_id` como colunas de contexto, custo_direto/indireto/total somados no span.
- `resumo_por_grupo` — uma linha por `grupo_id` (dentro da categoria), agregando as instâncias.
- `resumo_por_categoria` — uma linha por categoria (MAO_OBRA/EQUIPAMENTO) — corte mais alto.
- `custo_temporal` — uma linha por período (bucket por `granularidade`), somado sobre todas as instâncias — série temporal.

Filtros por `categoria`/`grupo_id`/`instancia_id` (qualquer combinação) — diferença estrutural frente ao estoque consumível (que só filtra por `resource_id`, sem grupo intermediário).

D5. Exposição, mesmo padrão dos cubos-irmãos: serviço (`application/services/concilium_service/_cubo_roster_real.py`, mixin `_CuboRosterRealMixin`), API (`GET /{project_id}/cubo-roster-real/projecao[?escopo_id=...]` + `.../contrato`), MCP (`explorar_roster_real`, `presentation/mcp/tools/analise.py`).

D6. **Desvio documentado do padrão de acesso a dado dos cubos-irmãos**: o serviço deste cubo precisa carregar tanto o canonical (`_load_canonical_for_version`, para as datas do projeto) quanto o `Escopo` (`repository.get_project(project_id).escopo(escopo_id).to_escopo()`, para `roster_mo`/`roster_eq`) — os outros cubos só precisam do canonical, porque seu dado de entrada já foi baked-in por uma skill. Roster nunca é baked-in (decisão deliberada da ADR-160/173); o serviço precisa buscá-lo à parte. `escopo_id` ganha um parâmetro novo (default `"default"`) que os outros cubos-irmãos não têm.

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Estender `CuboPoolInstancial` (ADR-086) com um eixo de instância real | Rejeitada — mistura grão de slot fungível (calibrado) com indivíduo real (dado real), borrando a separação física/causal que é a razão de existir do cubo ADR-086 (mesmo raciocínio que levou à criação do `CuboEstoqueConsumivel` como irmão, ADR-128 F6). |
| A2 | Acordar `cubo_pool_real.py` (ADR-160) em vez de criar cubo novo | Rejeitada — esse módulo modela custo por **slot do pool** via taxa média "sombra" recalculada do roster, não por indivíduo com seu próprio custo; a hierarquia confirmada nesta conversa (categoria/grupo/instância, `individuo_id`/`ativo_id` como folha) não tem relação com `InstanciaRecurso.instancia_id` (slot numerado) — são dois conceitos de "instância" genuinamente diferentes, não o mesmo módulo generalizado. |
| A3 | Tratar `custo_direto`/`custo_indireto`/`custo_total` como nível de hierarquia (dimensão), não medida | Rejeitada explicitamente na conversa — uma instância de MO tem os dois valores simultaneamente; forçar como dimensão criaria uma bifurcação artificial inexistente no dado. |
| A4 | Deixar `roster_eq` fora deste ADR, cubo só cobre MO por ora | Rejeitada — usuário reafirmou explicitamente que "equipamentos têm custos diretos apenas" como parte do requisito do cubo; sem `roster_eq` persistido, a categoria `EQUIPAMENTO` do cubo nunca teria dado real, tornando a metade do cubo permanentemente vazia por omissão, não por design. |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Fecha o gap identificado na conversa | Existe agora um cubo consultável por API/MCP com a granularidade exata que `custo_semanal_individual_mo/_eq` (ADR-173) foi desenhada para alimentar. |
| Simetria MO/EQ restaurada | `roster_eq` passa a ter o mesmo caminho de persistência de `roster_mo` — fecha uma assimetria que existia desde a ADR-155/157 (equipamento sempre um passo atrás de MO nessa cadeia). |
| Reaproveita 100% do padrão de cubo-irmão já validado | Mesma estrutura model/builder/projection/facade/API/MCP do `CuboEstoqueConsumivel` — sem inventar mecanismo novo. |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Serviço deste cubo tem assinatura diferente dos irmãos (`escopo_id` novo) | Documentado explicitamente em D6 — consequência inevitável de roster ser transiente por design; não é inconsistência acidental. |
| `roster_eq` novo campo em `Escopo` sem uso histórico — risco de campo "cego" se ninguém popular via `gerir_escopo` | Mesmo risco aceito para `roster_mo` na ADR-173; mitigado pela mesma ação incremental via MCP. |
| Cubo pode ficar vazio (roster_mo e roster_eq ambos `[]`) na maioria dos projetos hoje, já que popular o roster real ainda é opt-in | Aceito — degradação seguro (`celulas=()`), mesmo padrão de todos os cubos-irmãos quando o dado de entrada está ausente. |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | D2 — `Escopo.roster_eq` + persistência (`EscopoStore`, `ProjectStore.create_escopo`) + `gerir_escopo acao="editar_roster_eq"` | Pendente |
| F2 | D1 — `CelulaRosterReal`/`CuboRosterReal` (domain model) | Pendente |
| F3 | D3 — `CuboRosterRealBuilder` | Pendente |
| F4 | D4 — `resolve_cubo_roster_real_projection` + `cubo_roster_real_projection_contract` | Pendente |
| F5 | D5/D6 — serviço (`_CuboRosterRealMixin`) + API + MCP | Pendente |

## Definition of Done

### Fase 1
- [ ] `Escopo.roster_eq: list[AtivoEquipamentoReal] = Field(default_factory=list)`
- [ ] `ProjectStore.create_escopo()` aceita `roster_eq`; `EscopoStore.upsert_roster_eq_ativo()` (merge por `ativo_id`)
- [ ] `gerir_escopo` aceita `acao="editar_roster_eq"` + `roster_eq_ativo`

### Fase 2
- [ ] `CelulaRosterReal`/`CuboRosterReal` — `slice`/`group_by`/projeções de conveniência; teste puro sem fixtures externas

### Fase 3
- [ ] `CuboRosterRealBuilder.build` — MO+EQ, span do projeto, degradação segura (roster vazio → `celulas=()`)
- [ ] Teste: soma das células de uma instância == `custo_semanal_individual_mo/_eq` chamada direta para a mesma instância/span

### Fase 4
- [ ] 4 faces implementadas + contrato navegável
- [ ] Teste: cada face, filtros por categoria/grupo/instância, fallback de face/granularidade inválida, truncamento top_n

### Fase 5
- [ ] Serviço carrega canonical (datas) + Escopo (roster) via `repository.get_project`
- [ ] Rotas API + tool MCP registradas e testadas

## Nota de Implementação

_(preenchida ao final da implementação)_

---

## Relacionados

- ADR-086 — Cubo Pool Instancial (grão de slot, "irmão" preservado, não fundido)
- ADR-128 F6 — Cubo de Estoque Consumível (precedente direto do padrão de cubo-irmão replicado aqui)
- ADR-173 — Roster Real Persistido (`custo_semanal_individual_mo/_eq`, D13, fonte de dado deste cubo)
