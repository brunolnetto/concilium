# /adr

Gerencia o ciclo de vida de Architecture Decision Records.

Uso:
- `/adr new <título>` — cria novo ADR
- `/adr check` — verifica se o diff atual precisa de ADR
- `/adr status <N> <status>` — atualiza status de um ADR existente

---

## `/adr new <título>`

1. **Descubra a convenção do projeto:**
   - Encontre o diretório de ADRs (busca por `ADR-*.md` ou `adr-*.md`)
   - Leia o INDEX.md ou liste os arquivos para determinar o próximo número
   - Leia 1-2 ADRs recentes para capturar o formato exato (seções, idioma, estilo)

2. **Crie o arquivo** com o próximo número no formato detectado. Template base:

```markdown
# ADR-NNN — <Título>

**Status:** Proposta
**Data:** YYYY-MM-DD
**Contexto:** <projeto>
**Dependências:** <ADRs relacionados, se houver>

---

## Contexto

### Problema

P1. <problema principal>

## Decisão

D1. <decisão principal>

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|

### Negativas / Riscos

| Risco | Mitigação |
|---|---|

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|

## Definition of Done

### Fase 1
- [ ] item

---

## Relacionados
```

3. **Atualize o INDEX.md** (ou equivalente): adicione linha na seção apropriada com número, título, status e dependências.

4. Confirme os arquivos criados/modificados ao usuário.

---

## `/adr check`

Analise o diff atual (`git diff main...HEAD` ou `git diff --staged`) e determine se uma decisão arquitetural foi tomada sem ADR correspondente.

Sinais de que um ADR é necessário:
- Nova dependência externa adicionada ao `pyproject.toml`
- Novo padrão de integração entre camadas
- Mudança de protocolo de comunicação (REST → gRPC, stdio → HTTP, etc.)
- Novo mecanismo de autenticação ou segurança
- Mudança de convenção de nomenclatura global (como `CONCILIUM_` → `CONCILIUM__`)
- Adição de nova camada ou novo entry point de apresentação
- Decisão de storage ou persistência

Sinais de que **não** precisa de ADR:
- Bugfix dentro de uma skill/feature existente
- Refactor interno sem mudança de interface
- Adição de teste
- Atualização de dados de referência

Reporte: "**ADR recomendado**" / "**ADR não necessário**" com justificativa em 1-2 frases.

---

## `/adr status <N> <novo-status>`

1. Encontre o arquivo `ADR-<N>-*.md`
2. Atualize a linha `**Status:**` para o novo status
3. Se o novo status for `APROVADO` ou equivalente, atualize também o INDEX.md
4. Statuses válidos (adapte ao detectado no projeto): `Proposta`, `Aceito`, `APROVADO`, `Parcialmente Implementado`, `Implementado`, `Supersedido`
