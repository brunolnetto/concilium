# ADR-168 — Alojamento (ADM) Bottom-Up por Número de Casas

**Status:** ✅ Implementado — capacidade/valor passaram a ter fonte de catálogo na **ADR-170** (`BEN-ALOJAMENTO`)
**Data:** 2026-07-29
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-166 (Wiring de Indiretos — mesmo padrão de degradação segura), ADR-167 (ADM/TOP com Função Real — deferiu "Alojamento" para esta ADR)

---

## Contexto

### Problema

P1. A ADR-167 (D6) deixou explicitamente de fora a verba "Alojamento" da categoria ADM — R$3.500/mês fixo, independente do tamanho da equipe em campo, porque não havia até então um modelo de negócio para substituí-la por um cálculo real (diferente de QSMS/MOB, "Alojamento" não é um custo por-item de catálogo com preço unitário, é uma capacidade física — uma casa alugada comporta um número finito de pessoas).

P2. O usuário forneceu o modelo: uma casa de referência tem 3 quartos, 2 pessoas por quarto (capacidade 6 pessoas), configurável; o aluguel de cada casa custa R$4.000/mês.

## Decisão

D1. Nova função `_custo_alojamento_bottom_up(headcount, quartos_por_casa=3, pessoas_por_quarto=2, valor_aluguel_mensal=4000.0)` (`_dimensionamento.py`): `num_casas = ceil(headcount / (quartos_por_casa × pessoas_por_quarto))`, custo = `num_casas × valor_aluguel_mensal`. Retorna `None` se `headcount<=0` ou capacidade inválida — o chamador cai para a verba lump antiga (R$3.500/mês), mesma degradação segura da ADR-166 D2/D3. `headcount` é a soma de `num_pessoas` de todas as funções de `equipes_diretas` (`_headcount_direto`, mesmo escopo de "quem está em campo" já usado pelo bottom-up de QSMS).

D2. Capacidade e valor de aluguel são configuráveis via `cat["alojamento"]` (uma nova chave opcional no dicionário de categoria do perfil, `{"quartos_por_casa": ..., "pessoas_por_quarto": ..., "valor_aluguel_mensal": ...}`) — threaded desde `_resolve_categoria_comp`/`_dimensionar_automatico` (este último via `regra["alojamento"]`, mesmo padrão de override por parâmetro de `regra_dimensionamento`). Ausência da chave usa os defaults (3, 2, R$4.000).

D3. `_composicao_default_por_categoria` ganha parâmetros opcionais `equipes_diretas`/`alojamento_config`; o item "Coordenador" (`P0092`, ADR-167) não é afetado — continua no mesmo componente `mao_de_obra`, independente do cálculo de alojamento na `verbas`.

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Modelar "Alojamento" como um novo tipo de insumo catalogável (ex.: `INFRAESTRUTURA`) | Rejeitada por ora — ao contrário de EPI/treinamento/exame/benefício (custo por pessoa), alojamento é uma restrição de capacidade física (pessoas por casa), não um preço unitário direto; o cálculo cabe inteiramente dentro do driver de indiretos, sem precisar de um novo tipo de `Insumo`. |
| A2 | Arredondar para baixo ou usar fração de casa | Rejeitada — não é possível alugar "0,8 de uma casa"; `math.ceil` é o comportamento correto para uma restrição de capacidade discreta. |
| A3 | Headcount fixo/agregado do projeto em vez de `equipes_diretas` | Rejeitada — mesmo raciocínio já usado no QSMS (ADR-166): `equipes_diretas` já é a fonte real de headcount por função, disponível em `canonical_in`, sem precisar de um input novo. |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Alojamento reflete o tamanho real da obra | Uma equipe de 30 pessoas paga 5 casas (R$20.000/mês), não o mesmo R$3.500/mês fixo de uma equipe de 3 pessoas. |
| Configurável sem mudar código | `cat["alojamento"]` no perfil ajusta capacidade/valor por projeto, sem precisar de uma nova versão do driver. |
| Degradação segura preservada | Perfis/chamadas sem `equipes_diretas` (ou headcount zero) mantêm o lump antigo — nenhum caso existente quebra. |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| `valor_aluguel_mensal` (R$4.000) é um número de mercado único, sem variação regional/por tipo de imóvel | Aceito por ora — mesmo nível de precisão que o restante do modelo de indiretos; ajustável via `cat["alojamento"]` quando necessário. |
| LAB (R$4.000/mês, "Ensaios laboratoriais") continua hardcoded — não fazia parte do modelo fornecido nesta conversa | Gap conhecido, documentado — ADR-167 D6 já havia adiado explicitamente; sem dado de negócio ainda para modelá-lo. |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `_custo_alojamento_bottom_up` + wiring em `_composicao_default_por_categoria("ADM")` | ✅ Implementado |
| F2 | `cat["alojamento"]`/`regra["alojamento"]` threaded em `_resolve_categoria_comp`/`_dimensionar_automatico` | ✅ Implementado |

## Definition of Done

- [x] Teste cobrindo: headcount 0/negativo → `None` (fallback); headcount exato na capacidade (6→1 casa); acima da capacidade arredonda para cima (7→2 casas); headcount pequeno ainda paga 1 casa inteira; capacidade customizada; capacidade zero → `None`
- [x] Teste cobrindo: ADM sem `equipes_diretas` usa lump R$3.500; com `equipes_diretas` usa número de casas real; com `cat["alojamento"]` customizado usa a configuração do perfil
- [x] Teste cobrindo: item "Coordenador" (`P0092`) não afetado pela mudança em "Alojamento"
- [x] Suíte completa verde (só a falha pré-existente do golden test)

---

## Relacionados

- ADR-166 — Wiring de Indiretos + Mapeamento Função→Item (padrão de degradação segura reaplicado aqui)
- ADR-167 — ADM/TOP com Função Real + Paridade de Catálogo (deferiu "Alojamento" para esta ADR — D6)
