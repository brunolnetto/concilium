# ADR-165 — Catálogo de Treinamentos, Exames, EPIs e Benefícios de Mão de Obra

**Status:** ✅ Implementado
**Data:** 2026-07-29
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-032 (Entidades Versionadas — `InsumoVersionado` estendido), ADR-107 (Combustível/Categoria de Custo), ADR-116 (Limpeza da Superfície de Tools MCP), ADR-139 (Origem de Material), ADR-145 (Unificação do Caminho de Escrita de Preço no Catálogo Mestre), ADR-163 (CRUD de Insumo no Catálogo Mestre), ADR-164 (Operações em Lote de CRUD de Insumo)

---

## Contexto

### Problema

P1. O custo de QSMS (Qualidade, Segurança, Meio Ambiente e Saúde) hoje entra no cálculo de indiretos como uma única verba mensal fixa — `_composicao_default_por_categoria` (`application/skills/manifests/06-resultado-financeiro/_indiretos/_skill_helpers/_dimensionamento.py:86`) atribui literalmente `{"descricao": "EPIs e treinamentos", "valor_mensal": 3000.0}` por equipe/mês. Não há decomposição por item, por função, nem trilha de custo unitário — é um número de bolso, não um cálculo bottom-up.

P2. O catálogo mestre não tem nenhum lugar para representar EPI, treinamento, exame ocupacional ou benefício (alimentação, seguro de vida) como itens de custo individualizados. Uma varredura completa do repositório não encontrou nenhuma ocorrência de "exame admissional/periódico" em código; EPI/treinamento/benefício aparecem só como texto livre em comentários de BDI e encargos sociais (`domain/constants.py:64-67`, `domain/services/financial/tributacao.py:192`), nunca como dado estruturado.

P3. Não existe hoje nenhum conceito de "função" (cargo) separado do próprio `Insumo` tipo `MAO_OBRA` — o código do insumo (ex.: `MO-ARMADOR`, `MO-AJUDANTE`) já é a função. Isso significa que qualquer mecanismo de "este item se aplica só à função X" precisa apontar para códigos de insumo `MAO_OBRA` já existentes, não para uma entidade nova de cargo.

P4. Os quatro grupos de dado trazidos pelo usuário têm exigências de modelagem distintas, que o modelo atual de `Insumo`/`AtributosInsumo` não cobre:
- **EPI** — bem físico consumível com preço unitário e ciclo de substituição ("vida útil" em dias). Encaixa na semântica de `TipoInsumo.MATERIAL` já existente, faltando apenas o campo de ciclo de substituição.
- **Treinamento** — específico por função, recorrente (revalidação após a "vida útil"), sem quantidade consumida por CPU. Não é material nem mão de obra nem equipamento nem terceirizado.
- **Exame** — comum a todas as funções, recorrente por período (equivalente a PCMSO anual), sem vínculo de função específica.
- **Benefício** (alimentação, seguro de vida) — recorrente por dia ou por mês, comum a todas as funções, mas com pelo menos um caso de aplicabilidade condicionada ao regime de contratação (jantar não se aplica a PJ).

P5. `tipo_contrato` (`AtributosInsumo.tipo_contrato`, `"CLT" | "PJ"`) hoje só é lido para decidir se encargos sociais são aplicados (`_resolve_custo_unit_funcao`, `application/skills/manifests/05-.../_dimensionamento_custos.py:91-103`) — não há hoje nenhum mecanismo para diferenciar benefício por regime de contratação.

### Dados trazidos pelo usuário

**EPIs** (12 itens, preço unitário R$ e vida útil em dias — 2 sem preço informado: CINTO TIPO PARAQUEDISTA, AVENTAL DE COURO):

| Código proposto | Descrição | R$ unit. | Vida útil (dias) |
|---|---|---|---|
| EPI-PROTETOR-SOLAR | Protetor solar FPS 60 | 60,00 | 60 |
| EPI-ABAFADOR-CONCHA | Abafador de ruídos tipo concha | 90,00 | 360 |
| EPI-CINTO-PARAQUEDISTA | Cinto tipo paraquedista | *(pendente)* | 1095 |
| EPI-BOTA-COURO | Bota de couro com biqueira de aço | 100,00 | 180 |
| EPI-UNIFORME | Uniforme | 255,00 | 180 |
| EPI-PERNEIRA | Perneira | 100,00 | 180 |
| EPI-CAPACETE-3M | Capacete 3M | 170,00 | 360 |
| EPI-ROUPA-MOTOSSERRA | Roupa operador de motosserra | 620,00 | 360 |
| EPI-OCULOS-SEGURANCA | Óculos de segurança | 40,00 | 180 |
| EPI-LUVA-VAQUETA | Luvas de vaqueta | 50,00 | 120 |
| EPI-PROTETOR-FACIAL | Protetor facial | 110,00 | 360 |
| EPI-AVENTAL-COURO | Avental de couro | *(pendente)* | 180 |

**Treinamentos** (9 itens, todos vida útil 360 dias — específicos por função):

| Código proposto | Descrição | R$ unit. |
|---|---|---|
| TRE-NR22-MINERACAO | NR-22 (Mineração) | 315,00 |
| TRE-PLANO-TRANSITO | Plano de Trânsito Integrado | 300,00 |
| TRE-OP-MOTOSSERRA | Operador de Motosserra | 450,00 |
| TRE-OP-MOTOPODA | Operador de Motopoda | 400,00 |
| TRE-FERRAMENTAS-MANUAIS | Ferramentas Manuais | 175,00 |
| TRE-PRODUTOS-QUIMICOS | Produtos Químicos | 315,00 |
| TRE-NR12-MAQUINAS | NR-12 (Máquinas e Equipamentos) | 300,00 |
| TRE-NR6-USO-EPI | NR-6 (Uso de EPIs) | 150,00 |
| TRE-NR35-ALTURA | NR-35 (Trabalho em Altura) | 350,00 |

**Exames** (9 itens, todos vida útil 360 dias, comuns a todas as funções — total do pacote R$681,20, soma exata dos 9 itens abaixo):

| Código proposto | Descrição | R$ unit. |
|---|---|---|
| EXA-ASO-ADMISSIONAL | ASO — Admissional e Demissional | 400,00 |
| EXA-CLINICO | Exame Clínico | 46,00 |
| EXA-AUDIOMETRIA | Audiometria | 35,00 |
| EXA-LIPIDOGRAMA | Lipidograma | 19,50 |
| EXA-HEMOGRAMA | Hemograma Completo | 19,50 |
| EXA-URINA | Urina | 15,60 |
| EXA-GLICEMIA | Glicemia | 15,60 |
| EXA-ELETROCARDIOGRAMA | Eletrocardiograma | 65,00 |
| EXA-TIPAGEM-SANGUINEA | Tipagem Sanguínea | 65,00 |

**Benefícios** (comuns a todas as funções; jantar opcional para PJ):

| Código proposto | Descrição | R$ unit. | Periodicidade |
|---|---|---|---|
| BEN-CAFE-MANHA | Café da manhã | 9,00 | diária |
| BEN-ALMOCO | Almoço | 16,50 | diária |
| BEN-JANTAR | Jantar (opcional para PJ) | 16,50 | diária |
| BEN-VALE-ALIMENTACAO | Vale-alimentação | 1.260,00 | mensal |
| BEN-CESTA-BASICA | Cesta básica | 462,25 | mensal |
| BEN-SEGURO-VIDA | Seguro de vida | 35,00 | mensal |

**Nota de gap (não resolvida nesta ADR):** café/almoço/jantar (modelo de refeição servida) e vale-alimentação/cesta básica (modelo de benefício em pecúnia/ticket) são tipicamente políticas de RH concorrentes, não cumulativas — qual das duas se aplica a qual função/contrato é uma decisão de política de benefícios, não uma decisão técnica desta ADR.

## Decisão

D1. `TipoInsumo` (`domain/models/catalog/catalogo.py:15`) ganha três novos valores: `"TREINAMENTO"`, `"EXAME"`, `"BENEFICIO"`. EPI **não** ganha um tipo novo — é modelado como `Insumo` tipo `MATERIAL` (prefixo de código `EPI-`), reaproveitando por completo a semântica de bem físico consumível já existente (preço unitário, `fornecedor_referencia`, governança de rascunho/merge).

```python
TipoInsumo = Literal["MATERIAL", "MAO_OBRA", "EQUIPAMENTO", "TERCEIRIZADO", "TREINAMENTO", "EXAME", "BENEFICIO"]
```

D2. Novo campo `AtributosInsumo.vida_util_dias: int | None = Field(default=None, gt=0)` — dimensão de recorrência/substituição periódica, ortogonal à quantidade consumida por CPU que já existe para material. Aplica-se a `MATERIAL` classificado como EPI, e a `TREINAMENTO`/`EXAME` (intervalo de revalidação).

D3. Novo campo `AtributosInsumo.funcoes_aplicaveis: list[str] | None = None` — dimensão de elegibilidade por função. `None` = comum a todas as funções `MAO_OBRA`; uma lista de códigos (ex.: `["MO-OP-MOTOSSERRA"]`) restringe o item às funções listadas. Aplica-se a `MATERIAL` (EPI específico) e `TREINAMENTO`. Cada código listado deve apontar para um `Insumo` tipo `MAO_OBRA` existente — a validação de existência/atividade fica para a auditoria de plausibilidade (ver Riscos), não bloqueia a escrita.

D4. Dois campos novos, exclusivos de `BENEFICIO`:
- `AtributosInsumo.periodicidade_beneficio: Literal["diaria", "mensal"] | None = None` — base temporal do `preco_unitario` (diária: café/almoço/jantar; mensal: vale-alimentação/cesta básica/seguro de vida).
- `AtributosInsumo.aplicavel_tipo_contrato: list[Literal["CLT", "PJ"]] | None = None` — `None` = aplica a ambos os regimes; usado para modelar itens opcionais por regime (ex.: `BEN-JANTAR` com `aplicavel_tipo_contrato=["CLT"]`, excluindo PJ).

D5. `Insumo` ganha um `model_validator` (mesmo padrão de `_validar_origem_material`, linha 203-210) restringindo os campos novos ao(s) tipo(s) correto(s):

```python
@model_validator(mode="after")
def _validar_campos_rh(self) -> Insumo:
    a = self.atributos_especificos
    if a.vida_util_dias is not None and self.tipo not in ("MATERIAL", "TREINAMENTO", "EXAME"):
        raise ValueError(f"VAL-INSUMO-VIDA-UTIL-01: vida_util_dias só é válido para MATERIAL/TREINAMENTO/EXAME, recebido '{self.tipo}'")
    if a.funcoes_aplicaveis is not None and self.tipo not in ("MATERIAL", "TREINAMENTO"):
        raise ValueError(f"VAL-INSUMO-FUNCOES-01: funcoes_aplicaveis só é válido para MATERIAL/TREINAMENTO, recebido '{self.tipo}'")
    if (a.periodicidade_beneficio is not None or a.aplicavel_tipo_contrato is not None) and self.tipo != "BENEFICIO":
        raise ValueError(f"VAL-INSUMO-BENEFICIO-01: periodicidade_beneficio/aplicavel_tipo_contrato só válidos para BENEFICIO, recebido '{self.tipo}'")
    return self
```

D6. Convenção de prefixo de código por tipo, análoga ao `MO-` já usado para `MAO_OBRA`: `EPI-`, `TRE-`, `EXA-`, `BEN-`. Não é uma regra validada em código (mesma situação de `MO-` hoje, que é convenção, não `pattern` do Pydantic) — documentada aqui para consistência de dado.

D7. Nenhuma tool MCP nova é necessária. `criar_insumo`/`criar_insumos_lote` (ADR-163 D5, ADR-164) já aceitam qualquer `TipoInsumo` via parâmetro genérico; `_impl_criar_insumo` deriva o diretório de armazenamento como `tipo_dir = str(tipo).lower()` (`_catalogo_tools_helpers_a.py:432`) — `"TREINAMENTO"` → `insumos/treinamento/`, `"EXAME"` → `insumos/exame/`, `"BENEFICIO"` → `insumos/beneficio/`, sem nenhuma mudança de código além de D1. `listar_insumos`/`atualizar_preco_insumo`/`descontinuar_insumo` (ADR-163) também generalizam automaticamente. Only os docstrings de `tipo` (`_catalogo_tools_helpers_a.py:156,461`, hoje enumerando só os 4 tipos antigos) precisam ser atualizados para mencionar os 3 novos.

D8. Carga inicial dos itens listados em "Dados trazidos pelo usuário" via `criar_insumos_lote` (ADR-164), gated pelo caminho rascunho→merge padrão (ADR-145) no catálogo `mendeslobo`. `EPI-CINTO-PARAQUEDISTA` e `EPI-AVENTAL-COURO` (sem preço informado) ficam pendentes de carga até o usuário fornecer `preco_unitario` — não são criados com preço `0.0` silencioso.

D9. **Explicitamente fora de escopo desta ADR** (decisão do usuário): (a) wiring no pipeline de custo — a verba QSMS lump de R$3.000/mês (`_dimensionamento.py:86`) permanece inalterada; uma ADR futura decide como/se o custo itemizado por função passa a alimentar `skill-06`/indiretos substituindo o lump; (b) preenchimento completo do mapeamento função→treinamento/EPI específico via `funcoes_aplicaveis` — D3 define o mecanismo, o preenchimento de qual função usa qual item específico é tarefa de dados subsequente.

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Manter EPI como verba agregada, criar tipo genérico "RH" único para EPI+Treinamento+Exame+Benefício | EPI já se encaixa em `MATERIAL` sem necessidade de tipo novo (bem físico consumível, preço unitário, fornecedor); forçar um tipo genérico misturaria semânticas muito distintas (consumível físico vs. serviço recorrente vs. benefício em pecúnia) sob um único rótulo, perdendo a especificidade que `fonte_preco`/`fornecedor_referencia` já dão a `MATERIAL`. |
| A2 | Modelar Treinamento/Exame como `TERCEIRIZADO` (já que são serviços prestados por terceiros) | `TERCEIRIZADO` hoje representa equipe/mão de obra terceirizada substituindo MO própria numa CPU — semântica de "substituto de posto de trabalho", incompatível com um evento pontual e recorrente de capacitação/exame que não substitui ninguém. |
| A3 | Nova entidade separada (`PerfilFuncaoRH`) para o relacionamento função→item específico, em vez de campo `funcoes_aplicaveis` no próprio insumo | Adicionaria uma segunda fonte de verdade para o mesmo relacionamento sem necessidade — o mapeamento completo nem existe ainda (D9); um campo no próprio insumo é suficiente e mais simples, revisitável se a granularidade N:N crescer a ponto de justificar uma tabela dedicada. |
| A4 | Já popular o mapeamento função→treinamento/EPI específico nesta ADR | Rejeitada por decisão explícita do usuário — os dados fornecidos são só as tabelas de item/custo, sem o mapeamento função→item; preenchê-lo por inferência de nome (ex.: "óbvio que motosserra liga a operador de motosserra") arriscaria fixar suposições erradas no catálogo mestre sem validação de RH. |
| A5 | Já substituir a verba QSMS lump pelo cálculo itemizado nesta mesma ADR | Rejeitada por decisão explícita do usuário — reduz o raio de impacto desta ADR a "só modelo de dados", evitando reabrir o pipeline de indiretos logo após a correção de regressão do commit `dca2708f`. |
| A6 | Nova unidade canônica `"dia"` em `domain/units.py` para café/almoço/jantar | Rejeitada — `"unid"` (ocorrência/evento) já cobre semanticamente "uma refeição servida"; `periodicidade_beneficio="diaria"` carrega a informação temporal necessária sem exigir extensão do módulo de unidades para um caso de uso único. |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Custo de RH ganha trilha auditável | EPI/treinamento/exame/benefício passam a ter preço unitário rastreável, histórico de preço (`historico_precos`) e governança de quatro-olhos (ADR-145), em vez de uma verba de bolso sem decomposição. |
| Zero tooling novo | Reaproveita 100% da superfície MCP existente (`criar_insumo(s)`, `listar_insumos`, `atualizar_preco_insumo`, `descontinuar_insumo`) — `tipo_dir` já deriva automaticamente do valor do `Literal`, sem mudança estrutural em `catalog_governance.py`. |
| Base pronta para ADR de wiring futura | Uma vez carregados, os itens já existem com `vida_util_dias`/`funcoes_aplicaveis`/`periodicidade_beneficio` prontos para alimentar um cálculo bottom-up por função, sem precisar remodelar o dado outra vez. |
| Distinção correta EPI vs. serviço recorrente | Reconhece que EPI é fisicamente um material (reaproveita toda a semântica de `MATERIAL`), enquanto treinamento/exame/benefício exigem uma dimensão temporal/elegibilidade que `MATERIAL` não tinha — em vez de forçar os quatro num único modelo genérico. |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Dados carregados não afetam nenhum cálculo de custo real até uma ADR de wiring acontecer | Documentado explicitamente em D9 como próximo passo obrigatório (não opcional); risco aceito por decisão do usuário de limitar o escopo desta ADR. |
| `funcoes_aplicaveis` referencia códigos `MAO_OBRA` sem checagem de existência/atividade no momento da escrita | Mesmo padrão de risco aceito em `auditar_catalogo` para outras referências cruzadas (ex.: A6 do ADR-163) — estender a auditoria de plausibilidade para checar `funcoes_aplicaveis` órfão/descontinuado fica como item futuro, não bloqueia esta ADR. |
| Café/almoço/jantar vs. vale-alimentação/cesta básica podem ser políticas de benefício concorrentes, não cumulativas | Não resolvido tecnicamente aqui — marcado como gap de política de RH; carga inicial (D8) registra os 6 itens sem impor qual conjunto está ativo para qual função/contrato. |
| `preco_unitario` de 2 EPIs (cinto paraquedista, avental de couro) não foi informado | D8: esses 2 itens ficam fora da carga inicial até o usuário fornecer valor — não entram com `0.0` silencioso, que poluiria auditoria de plausibilidade (`_pc_eq_zscore`-like) com falso zero. |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `TipoInsumo` ganha `TREINAMENTO`/`EXAME`/`BENEFICIO` (D1) | ✅ Implementado |
| F2 | `AtributosInsumo` ganha `vida_util_dias`/`funcoes_aplicaveis`/`periodicidade_beneficio`/`aplicavel_tipo_contrato` + `model_validator` de restrição por tipo (D2-D5) | ✅ Implementado |
| F3 | Docstrings de `tipo` em `listar_insumos`/`criar_insumo` (`_catalogo_tools_helpers_a.py:156,461`) atualizados para mencionar os 3 tipos novos (D7) | ✅ Implementado |
| F4 | Carga inicial via `criar_insumos_lote`: 10 EPIs (2 pendentes de preço), 9 treinamentos, 9 exames, 6 benefícios — rascunho→merge no catálogo `mendeslobo` (D8) | ✅ Implementado |

## Definition of Done

### Fase 1
- [x] `TipoInsumo` inclui `"TREINAMENTO"`, `"EXAME"`, `"BENEFICIO"`
- [x] Teste cobrindo: `Insumo(tipo="TREINAMENTO", ...)` valida corretamente com os campos novos

### Fase 2
- [x] `AtributosInsumo` ganha os 4 campos novos, todos opcionais, default `None` (retrocompatibilidade de catálogo existente)
- [x] `model_validator` bloqueia `vida_util_dias` em `MAO_OBRA`/`EQUIPAMENTO`/`TERCEIRIZADO`, `funcoes_aplicaveis` fora de `MATERIAL`/`TREINAMENTO`, `periodicidade_beneficio`/`aplicavel_tipo_contrato` fora de `BENEFICIO`
- [x] Teste cobrindo: cada combinação inválida levanta o `ValueError` correspondente (`VAL-INSUMO-VIDA-UTIL-01`/`VAL-INSUMO-FUNCOES-01`/`VAL-INSUMO-BENEFICIO-01`)
- [x] Teste cobrindo: catálogo existente (sem os campos novos) continua carregando sem alteração

### Fase 3
- [x] Docstrings atualizados; nenhuma mudança de comportamento (só documentação)

### Fase 4
- [x] `criar_insumos_lote` cria os itens listados em "Dados trazidos pelo usuário" (exceto os 2 EPIs sem preço) via rascunho, aprovados por `aprovar_merge_catalogo`
- [x] Verificado manualmente: `insumos/treinamento/`, `insumos/exame/`, `insumos/beneficio/` criados com um arquivo por código (9+9+6), validados contra o schema `Insumo`; `insumos/material/` ganha 10 `EPI-*.json`
- [x] Verificado manualmente: `listar_insumos(tipo="BENEFICIO")` retorna os 6 benefícios; `auditar_catalogo(modo="saude")` reporta `SAUDAVEL` após o merge

## Nota de Implementação

Implementada via TDD nas fases F1-F2 (`tests/unit/domain/models/test_adr165_catalogo_rh.py`, 36 casos cobrindo tipos novos, campos novos e as 3 validações VAL-INSUMO-*), com um achado adicional fora do escopo original: `InsumoVersionado` (ADR-032, `domain/models/catalog/versioned.py`) tinha o mesmo `Literal` de 4 tipos e é usado de fato por `RepositorioInsumo.preco_na_data` (SCD Type 2) — estendido para os 3 tipos novos com teste dedicado, senão um insumo `TREINAMENTO`/`EXAME`/`BENEFICIO` versionado cairia silenciosamente no fallback de preço plano.

F4 (carga inicial) foi feita por um script novo, `scripts/catalog/adr165_carga_inicial_rh.py`, que **não escreve arquivo diretamente** — invoca a mesma sequência de governança das tools MCP (`criar_rascunho_catalogo` → `criar_insumos_lote` → `listar_divergencias_rascunho` para marcar `REVISADO` → `aprovar_merge_catalogo`) via `FastMCP` + extração das funções registradas, com o aprovador (`adr165-carga-inicial-aprovador`) sendo um ator distinto do criador (`adr165-carga-inicial`), satisfazendo a regra dos quatro olhos (ADR-120) sem precisar de uma sessão MCP autenticada ao vivo. Testado primeiro com `--dry-run` (cópia temporária de `config/`) antes de `--apply` no catálogo real. Resultado: 34/34 itens criados, `aprovar_merge_catalogo` retornou `status: APROVADO`, snapshot novo (ADR-024) gerado, `auditar_catalogo` continua `SAUDAVEL`. Suíte completa (14.795 testes) verde após a mudança, com 1 falha pré-existente e não relacionada (`test_golden_evaluation.py`, confirmada falhando de forma idêntica antes desta ADR).

---

## Relacionados

- ADR-107 — Categoria de Custo Combustível (mesmo padrão de `Literal` estendido incrementalmente sem quebrar retrocompatibilidade)
- ADR-116 — Limpeza da Superfície de Tools MCP (esta ADR soma zero tools novas — D7)
- ADR-139 — Origem de Material (padrão de `model_validator` restringindo campo a tipo específico, reaproveitado em D5)
- ADR-145 — Unificação do Caminho de Escrita de Preço no Catálogo Mestre (governança de rascunho→merge reaproveitada integralmente para a carga inicial, D8)
- ADR-163 — CRUD de Insumo no Catálogo Mestre via MCP (`criar_insumo`/`listar_insumos`/`atualizar_preco_insumo`/`descontinuar_insumo` generalizam automaticamente para os tipos novos, D7)
- ADR-164 — Operações em Lote para CRUD de Insumo (`criar_insumos_lote` usado na carga inicial, D8)
